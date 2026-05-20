"""CSV brew import + export service (BREW-10, BREW-11; D-12..D-15).

The Wave 3/4 routes (`/brew/import`, `/brew/export`) consume this module;
isolating the resolve/dedup/transaction logic here keeps the router thin and
makes the per-row outcome behavior unit-testable.

Import (BREW-11)
================
:func:`import_brews` is **header-driven** (reads ``csv.DictReader.fieldnames``,
maps known headers case-insensitively via :data:`_HEADER_ALIASES`, ignores
unknown columns), so the literal Beanconqueror export headers can be confirmed
against a real file and added to the alias table WITHOUT touching the algorithm.
The Snobbery-native export headers (:data:`EXPORT_FIELDNAMES`) are the
authoritative round-trip format; Beanconqueror headers are a best-effort alias
superset, flagged ``TODO-confirm`` below.

Per-row resolution order (RESEARCH §Import algorithm):

1. **Coffee (D-12)** — citext ``Coffee.name == name``; roaster-qualified by
   ``(name, roaster_id)`` when a roaster column is present; ambiguous
   multi-match → refused; no match → refused.
2. **Bag (D-13)** — when the row names a bag (coffee + ``roast_date``) and it
   resolves → link; named-but-unmatched → refused; not named → ``bag_id=None``.
3. **Dedup (D-14)** — probe ``(user_id, coffee_id, brewed_at)`` via ``select``
   (no UNIQUE constraint exists — Plan 01 deferred it); existing → skipped.
4. **Validate** the accepted row through :class:`app.schemas.brew_csv.BrewCsvRow`.
5. **Insert** all accepted rows + auto-create observed notes (D-09) in ONE
   transaction; ``db.commit()`` once. A DB error mid-batch rolls back
   everything (no partial commit — Pitfall 4). Refused/skipped rows never
   enter the txn.

``extraction_yield_pct`` is GENERATED — NEVER written on import. ``user_id``
comes from ``by_user_id`` only, never from the file (mass-assignment defense,
T-05-10).

Export (D-15)
=============
:func:`export_brews` writes a name-resolved CSV (the same canonical headers the
importer treats as primary, so export → import round-trips) including the
read-only computed brew-ratio and the GENERATED ``extraction_yield_pct``.
Free-text cells beginning with ``= + - @`` are prefixed with ``'`` to neutralize
spreadsheet formula injection (T-05-13).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.events import BREW_CSV_EXPORTED, BREW_CSV_IMPORTED
from app.models.bag import Bag
from app.models.brew_session import BrewSession
from app.models.coffee import Coffee
from app.models.equipment import Equipment
from app.models.flavor_note import FlavorNote
from app.models.recipe import Recipe
from app.models.roaster import Roaster
from app.schemas.brew_csv import BrewCsvRow
from app.services.flavor_notes import create_flavor_note

log = structlog.get_logger(__name__)

# Upload guard ceiling for the router (T-05-11 DoS): a brew CSV at household
# scale is tiny; 5 MiB is a generous ceiling that still rejects a junk payload
# before the full body is buffered into memory.
MAX_CSV_BYTES = 5 * 1024 * 1024

# A non-CSV content-type set the router rejects before buffering (T-05-11).
ALLOWED_CSV_CONTENT_TYPES = frozenset(
    {"text/csv", "application/csv", "application/vnd.ms-excel", "text/plain", ""}
)

# Delimiter used to join/split the observed-flavor-note name list in one cell.
_NOTE_DELIMITER = ";"

# Leading characters that turn a spreadsheet cell into a formula when opened in
# Excel/Sheets — neutralized on export by prefixing a single quote (T-05-13).
_FORMULA_TRIGGERS = ("=", "+", "-", "@")

# Canonical Snobbery-native CSV header set — THE authoritative round-trip format
# (D-15). The importer maps these as primary; the export writer emits exactly
# this set so export → import round-trips. ``brew_ratio`` and
# ``extraction_yield_pct`` are read-only computed columns (ignored on import).
EXPORT_FIELDNAMES = [
    "coffee_name",
    "roaster_name",
    "roast_date",
    "recipe_name",
    "brewer",
    "grinder",
    "kettle",
    "water_type",
    "dose_grams",
    "water_grams",
    "yield_grams",
    "tds_pct",
    "water_temp_c",
    "grind_setting",
    "rating",
    "observed_flavor_notes",
    "notes",
    "brewed_at",
    # read-only computed (export-only; importer ignores these):
    "brew_ratio",
    "extraction_yield_pct",
]

# Header → canonical-field alias map (case-insensitive on lookup). The
# Snobbery-native headers map to themselves (authoritative round-trip format).
# Beanconqueror aliases are a best-effort superset and are marked TODO-confirm
# until verified against a real Beanconqueror "Export → Excel" file (see the
# plan's <unverified_assumption>: literal header strings, the rating scale, and
# the brew_quantity-vs-brew_beverage_quantity water-in/yield-out distinction are
# unconfirmed).
_HEADER_ALIASES: dict[str, str] = {
    # --- Snobbery-native (authoritative) ---
    "coffee_name": "coffee_name",
    "roaster_name": "roaster_name",
    "roast_date": "roast_date",
    "recipe_name": "recipe_name",
    "brewer": "brewer",
    "grinder": "grinder",
    "kettle": "kettle",
    "water_type": "water_type",
    "dose_grams": "dose_grams",
    "water_grams": "water_grams",
    "yield_grams": "yield_grams",
    "tds_pct": "tds_pct",
    "water_temp_c": "water_temp_c",
    "grind_setting": "grind_setting",
    "rating": "rating",
    "observed_flavor_notes": "observed_flavor_notes",
    "notes": "notes",
    "brewed_at": "brewed_at",
    # --- Beanconqueror best-effort aliases (TODO-confirm against a real export;
    #     verified from internal field names, NOT the literal CSV header text) ---
    "bean": "coffee_name",  # TODO-confirm
    "grind_weight": "dose_grams",  # TODO-confirm
    "grind_size": "grind_setting",  # TODO-confirm
    "brew_temperature": "water_temp_c",  # TODO-confirm
    "brew_beverage_quantity": "yield_grams",  # TODO-confirm (yield-out)
    "brew_quantity": "water_grams",  # TODO-confirm (water-in vs yield-out — A2)
    "tds": "tds_pct",  # TODO-confirm
    "note": "notes",  # TODO-confirm
    "method_of_preparation": "brewer",  # TODO-confirm
    "mill": "grinder",  # TODO-confirm
}


@dataclass(frozen=True)
class RowOutcome:
    """The disposition of one source CSV row.

    ``status`` is one of ``"inserted"``, ``"skipped"``, ``"refused"``;
    ``row_number`` is 1-based on the data rows (the header is row 1, the first
    data row is row 2 — matching what a spreadsheet shows); ``reason`` is a
    human-readable explanation the import-result UI renders verbatim.
    """

    status: str
    row_number: int
    reason: str


# --------------------------------------------------------------------------- #
# Header mapping                                                               #
# --------------------------------------------------------------------------- #


def _canonical_field_map(fieldnames: list[str] | None) -> dict[str, str]:
    """Map each present CSV header to its canonical field (case-insensitive).

    Unknown columns are dropped (header-driven resilience). Returns
    ``{original_header: canonical_field}`` so a row dict can be normalized.
    """
    out: dict[str, str] = {}
    for header in fieldnames or []:
        if header is None:
            continue
        canonical = _HEADER_ALIASES.get(header.strip().lower())
        if canonical is not None:
            out[header] = canonical
    return out


def _normalize_row(raw_row: dict[str, Any], header_map: dict[str, str]) -> dict[str, str]:
    """Project a raw DictReader row onto canonical field names, trimming values.

    A later duplicate canonical header wins only if the earlier one was blank,
    so a Snobbery-native header beats a blank Beanconqueror alias for the same
    field. ``None`` values (short rows) become empty strings.
    """
    out: dict[str, str] = {}
    for header, value in raw_row.items():
        canonical = header_map.get(header)
        if canonical is None:
            continue
        text_val = "" if value is None else str(value).strip()
        if canonical not in out or (not out[canonical] and text_val):
            out[canonical] = text_val
    return out


# --------------------------------------------------------------------------- #
# Per-row resolution (D-12 / D-13 / D-14)                                      #
# --------------------------------------------------------------------------- #


def _resolve_coffee(db: Session, *, name: str, roaster_name: str) -> tuple[int | None, str | None]:
    """Resolve a coffee id from its (citext) name, optionally roaster-qualified.

    Returns ``(coffee_id, None)`` on a unique match, or ``(None, reason)`` when
    the coffee is missing or ambiguous (D-12). CITEXT makes ``== name``
    case-insensitive natively (no ``func.lower`` wrapper).
    """
    stmt = select(Coffee.id).where(Coffee.name == name)
    if roaster_name:
        stmt = stmt.join(Roaster, Coffee.roaster_id == Roaster.id).where(
            Roaster.name == roaster_name
        )
    matches = db.execute(stmt).scalars().all()
    if not matches:
        return None, f'coffee "{name}" not in catalog'
    if len(matches) > 1:
        return None, f'coffee "{name}" ambiguous (matches multiple roasters)'
    return matches[0], None


def _resolve_bag(
    db: Session, *, coffee_id: int, roast_date_raw: str
) -> tuple[int | None, str | None]:
    """Resolve an optional bag for the row (D-13).

    No ``roast_date`` named → ``(None, None)`` (freestyle import, ``bag_id``
    stays null). Named but unmatched (or unparseable) → ``(None, reason)``
    (refused). A matched bag → ``(bag_id, None)``.
    """
    if not roast_date_raw:
        return None, None
    try:
        roast_date = datetime.fromisoformat(roast_date_raw).date()
    except ValueError:
        return None, f"bag (roast {roast_date_raw}) not found"
    bag_id = (
        db.execute(select(Bag.id).where(Bag.coffee_id == coffee_id, Bag.roast_date == roast_date))
        .scalars()
        .first()
    )
    if bag_id is None:
        return None, f"bag (roast {roast_date}) not found"
    return bag_id, None


def _parse_brewed_at(raw: str) -> datetime:
    """Parse the row's ``brewed_at`` to a tz-aware UTC datetime.

    Empty → ``now()``. A naive timestamp is assumed UTC (store UTC; the router
    renders in ``APP_TIMEZONE``). ISO-8601 only — anything else raises so the
    row is refused with a parse reason by the caller.
    """
    if not raw:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _session_exists(db: Session, *, user_id: int, coffee_id: int, brewed_at: datetime) -> bool:
    """D-14 dedup probe: a session already at ``(user_id, coffee_id, brewed_at)``."""
    return (
        db.execute(
            select(BrewSession.id).where(
                BrewSession.user_id == user_id,
                BrewSession.coffee_id == coffee_id,
                BrewSession.brewed_at == brewed_at,
            )
        )
        .scalars()
        .first()
        is not None
    )


def _resolve_observed_notes(db: Session, *, names_raw: str, by_user_id: int) -> list[int]:
    """Resolve/auto-create observed flavor notes by citext name (D-09).

    Splits the delimited cell, links existing notes (CITEXT case-insensitive),
    and auto-creates the rest with ``category="other"`` WITHIN the importer's
    single open transaction — ``create_flavor_note(..., commit=False)`` only
    flushes, so the whole batch commits exactly once at the end and a later-row
    failure rolls every auto-created note back too (BREW-11 / Pitfall 4 / CR-01).

    A concurrent UNIQUE-citext collision is treated as "link existing": the
    no-commit create runs inside a SAVEPOINT (``begin_nested``) so a collision
    rolls back only that note's insert (not the batch), then the now-existing
    row is re-queried.
    """
    ids: list[int] = []
    for part in names_raw.split(_NOTE_DELIMITER):
        name = part.strip()
        if not name:
            continue
        existing = (
            db.execute(select(FlavorNote.id).where(FlavorNote.name == name)).scalars().first()
        )
        if existing is not None:
            if existing not in ids:
                ids.append(existing)
            continue
        try:
            with db.begin_nested():
                created = create_flavor_note(
                    db, name=name, category="other", by_user_id=by_user_id, commit=False
                )
            note_id = created.id
        except IntegrityError:
            # Concurrent insert won the race — the SAVEPOINT rolled back this
            # note only; link the now-existing row (outer batch txn intact).
            note_id = (
                db.execute(select(FlavorNote.id).where(FlavorNote.name == name)).scalars().one()
            )
        if note_id not in ids:
            ids.append(note_id)
    return ids


# --------------------------------------------------------------------------- #
# Import (BREW-11) — single transaction                                        #
# --------------------------------------------------------------------------- #


def import_brews(db: Session, *, raw_bytes: bytes, by_user_id: int) -> list[RowOutcome]:
    """Header-driven, single-transaction brew CSV import.

    Resolves + dedups + validates every row first; inserts all accepted rows
    (plus their D-09 observed notes) in ONE transaction with a single
    ``db.commit()``. Refused/skipped rows never enter the transaction; a DB
    error during the batch rolls everything back (no partial commit). Returns a
    per-row :class:`RowOutcome` list (header is row 1; data rows start at 2).
    """
    reader = csv.DictReader(io.StringIO(raw_bytes.decode("utf-8-sig")))
    header_map = _canonical_field_map(reader.fieldnames)

    outcomes: list[RowOutcome] = []
    # Pending inserts: (row_number, BrewSession, observed_note_names_raw).
    pending: list[tuple[int, BrewSession, str]] = []

    for row_number, raw_row in enumerate(reader, start=2):
        row = _normalize_row(raw_row, header_map)

        coffee_id, reason = _resolve_coffee(
            db, name=row.get("coffee_name", ""), roaster_name=row.get("roaster_name", "")
        )
        if coffee_id is None:
            outcomes.append(RowOutcome("refused", row_number, reason or "coffee not resolved"))
            continue

        bag_id, bag_reason = _resolve_bag(
            db, coffee_id=coffee_id, roast_date_raw=row.get("roast_date", "")
        )
        if bag_reason is not None:
            outcomes.append(RowOutcome("refused", row_number, bag_reason))
            continue

        try:
            brewed_at = _parse_brewed_at(row.get("brewed_at", ""))
        except ValueError:
            outcomes.append(
                RowOutcome("refused", row_number, f'invalid brewed_at "{row.get("brewed_at")}"')
            )
            continue

        if _session_exists(db, user_id=by_user_id, coffee_id=coffee_id, brewed_at=brewed_at):
            outcomes.append(RowOutcome("skipped", row_number, "duplicate of an existing session"))
            continue

        # Validate brew parameters through the per-row schema (numeric ranges +
        # Decimal rating). Name/equipment fields are resolved separately.
        try:
            validated = BrewCsvRow(
                coffee_name=row.get("coffee_name", ""),
                roaster_name=row.get("roaster_name", ""),
                bag_label=row.get("roast_date", ""),
                brewer=row.get("brewer", ""),
                grinder=row.get("grinder", ""),
                kettle=row.get("kettle", ""),
                water_type=row.get("water_type", ""),
                dose_grams_actual=row.get("dose_grams", ""),
                water_grams_actual=row.get("water_grams", ""),
                yield_grams_actual=row.get("yield_grams") or None,
                tds_pct=row.get("tds_pct") or None,
                water_temp_c_actual=row.get("water_temp_c") or None,
                grind_setting_actual=row.get("grind_setting", ""),
                rating=row.get("rating") or None,
                notes=row.get("notes", ""),
            )
        except ValidationError as exc:
            first = exc.errors()[0]
            field = first.get("loc", ("?",))[-1]
            outcomes.append(
                RowOutcome("refused", row_number, f"{field}: {first.get('msg', 'invalid value')}")
            )
            continue

        brewer_id = _resolve_equipment_id(db, type_="brewer", name=validated.brewer)
        grinder_id = _resolve_equipment_id(db, type_="grinder", name=validated.grinder)
        kettle_id = _resolve_equipment_id(db, type_="kettle", name=validated.kettle)
        recipe_id = _resolve_recipe_id(db, name=row.get("recipe_name", ""))

        session = BrewSession(
            user_id=by_user_id,  # server-owned; never from the file (T-05-10)
            coffee_id=coffee_id,
            bag_id=bag_id,
            recipe_id=recipe_id,
            brewer_id=brewer_id,
            grinder_id=grinder_id,
            kettle_id=kettle_id,
            water_type=validated.water_type or None,
            dose_grams_actual=validated.dose_grams_actual,
            water_grams_actual=validated.water_grams_actual,
            yield_grams_actual=validated.yield_grams_actual,
            tds_pct=validated.tds_pct,
            water_temp_c_actual=validated.water_temp_c_actual,
            grind_setting_actual=validated.grind_setting_actual or None,
            rating=validated.rating,
            notes=validated.notes,
            brewed_at=brewed_at,
            # extraction_yield_pct is GENERATED — never set here.
        )
        pending.append((row_number, session, row.get("observed_flavor_notes", "")))

    # Single transaction: auto-create observed notes + add all sessions, commit
    # once. A DB error here rolls back the entire batch (Pitfall 4).
    inserted = 0
    if pending:
        try:
            for _row_number, session, notes_raw in pending:
                session.flavor_note_ids_observed = _resolve_observed_notes(
                    db, names_raw=notes_raw, by_user_id=by_user_id
                )
                db.add(session)
            db.commit()
        except Exception:
            db.rollback()
            raise
        for row_number, _session, _notes_raw in pending:
            outcomes.append(RowOutcome("inserted", row_number, "imported"))
            inserted += 1

    skipped = sum(1 for o in outcomes if o.status == "skipped")
    refused = sum(1 for o in outcomes if o.status == "refused")
    log.info(
        BREW_CSV_IMPORTED,
        user_id=by_user_id,
        inserted=inserted,
        skipped=skipped,
        refused=refused,
    )
    # Return outcomes in source-row order (inserts were appended after the
    # refused/skipped of later rows during the batch phase).
    return sorted(outcomes, key=lambda o: o.row_number)


def _resolve_equipment_id(db: Session, *, type_: str, name: str) -> int | None:
    """Resolve an equipment id by free-text ``name`` against ``brand``/``model``.

    Optional on import (RESEARCH: refuse-or-skip is the planner's pick — chosen
    here as best-effort link, leave null when unmatched so a row is never
    refused on equipment alone). Matches the brand or "brand model" combination
    case-insensitively, scoped to the equipment ``type``.
    """
    if not name:
        return None
    candidates = db.execute(
        select(Equipment.id, Equipment.brand, Equipment.model).where(
            Equipment.type == type_, Equipment.archived.is_(False)
        )
    ).all()
    target = name.strip().lower()
    for eq_id, brand, model in candidates:
        if target in {brand.lower(), f"{brand} {model}".strip().lower(), model.lower()}:
            return eq_id
    return None


def _resolve_recipe_id(db: Session, *, name: str) -> int | None:
    """Resolve a recipe id by name (best-effort; null when unmatched/blank)."""
    if not name:
        return None
    return (
        db.execute(select(Recipe.id).where(Recipe.name == name, Recipe.archived.is_(False)))
        .scalars()
        .first()
    )


# --------------------------------------------------------------------------- #
# Export (D-15) — name-based, round-trip-safe                                  #
# --------------------------------------------------------------------------- #


def _neutralize_formula(value: str) -> str:
    """Prefix a leading formula-trigger char with ``'`` (T-05-13).

    Only applied to free-text columns on export; numeric columns are not at
    risk. Blank/None values pass through unchanged.
    """
    if value and value[0] in _FORMULA_TRIGGERS:
        return "'" + value
    return value


def _decimal_str(value: Decimal | None) -> str:
    """Render a Decimal/number column as a plain string (blank when None)."""
    if value is None:
        return ""
    return str(value)


def _brew_ratio(dose: Decimal | None, water: Decimal | None) -> str:
    """``water / dose`` to 2 dp; blank when dose is 0/null (never NaN/Inf)."""
    if not dose or water is None:
        return ""
    try:
        return str((Decimal(water) / Decimal(dose)).quantize(Decimal("0.01")))
    except (InvalidOperation, ZeroDivisionError):
        return ""


def export_brews(
    db: Session,
    *,
    by_user_id: int,
    coffee_id: int | None = None,
    brewer_id: int | None = None,
    rating_min: Decimal | None = None,
    rating_max: Decimal | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> str:
    """Export the user's (optionally filtered) sessions as name-resolved CSV.

    Same filter kwargs as ``brew_sessions.list_brew_sessions`` (the export is
    the currently-filtered view). Resolves ids → human names, includes the
    read-only computed ``brew_ratio`` (water/dose) and the GENERATED
    ``extraction_yield_pct``, and emits exactly :data:`EXPORT_FIELDNAMES` so the
    output round-trips back through :func:`import_brews`. Free-text cells are
    formula-injection-neutralized (T-05-13). User-scoped (T-05-14).
    """
    stmt = select(BrewSession).where(BrewSession.user_id == by_user_id)
    if coffee_id is not None:
        stmt = stmt.where(BrewSession.coffee_id == coffee_id)
    if brewer_id is not None:
        stmt = stmt.where(BrewSession.brewer_id == brewer_id)
    if rating_min is not None:
        stmt = stmt.where(BrewSession.rating >= rating_min)
    if rating_max is not None:
        stmt = stmt.where(BrewSession.rating <= rating_max)
    if date_from is not None:
        stmt = stmt.where(BrewSession.brewed_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(BrewSession.brewed_at <= date_to)
    stmt = stmt.order_by(BrewSession.brewed_at.desc())
    sessions = list(db.execute(stmt).scalars().all())

    # Build id → name lookups for the referenced rows in one round-trip each.
    name_caches = _build_name_caches(db, sessions)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=EXPORT_FIELDNAMES, extrasaction="ignore")
    writer.writeheader()
    for s in sessions:
        coffee_name, roaster_name = name_caches["coffee"].get(s.coffee_id, ("", ""))
        bag_roast = name_caches["bag"].get(s.bag_id, "") if s.bag_id else ""
        observed = _NOTE_DELIMITER.join(
            name_caches["note"].get(nid, "") for nid in (s.flavor_note_ids_observed or [])
        )
        writer.writerow(
            {
                "coffee_name": _neutralize_formula(coffee_name),
                "roaster_name": _neutralize_formula(roaster_name),
                "roast_date": bag_roast,
                "recipe_name": _neutralize_formula(name_caches["recipe"].get(s.recipe_id, "")),
                "brewer": _neutralize_formula(name_caches["equipment"].get(s.brewer_id, "")),
                "grinder": _neutralize_formula(name_caches["equipment"].get(s.grinder_id, "")),
                "kettle": _neutralize_formula(name_caches["equipment"].get(s.kettle_id, "")),
                "water_type": _neutralize_formula(s.water_type or ""),
                "dose_grams": _decimal_str(s.dose_grams_actual),
                "water_grams": _decimal_str(s.water_grams_actual),
                "yield_grams": _decimal_str(s.yield_grams_actual),
                "tds_pct": _decimal_str(s.tds_pct),
                "water_temp_c": _decimal_str(s.water_temp_c_actual),
                "grind_setting": _neutralize_formula(s.grind_setting_actual or ""),
                "rating": _decimal_str(s.rating),
                "observed_flavor_notes": _neutralize_formula(observed),
                "notes": _neutralize_formula(s.notes or ""),
                "brewed_at": s.brewed_at.isoformat() if s.brewed_at else "",
                "brew_ratio": _brew_ratio(s.dose_grams_actual, s.water_grams_actual),
                "extraction_yield_pct": _decimal_str(s.extraction_yield_pct),
            }
        )

    log.info(BREW_CSV_EXPORTED, user_id=by_user_id, row_count=len(sessions))
    return buf.getvalue()


def _build_name_caches(db: Session, sessions: list[BrewSession]) -> dict[str, dict]:
    """Resolve every referenced id → name in one query per entity type.

    Returns ``{"coffee": {id: (coffee_name, roaster_name)}, "bag": {id: roast},
    "recipe": {id: name}, "equipment": {id: label}, "note": {id: name}}``.
    """
    coffee_ids = {s.coffee_id for s in sessions}
    bag_ids = {s.bag_id for s in sessions if s.bag_id}
    recipe_ids = {s.recipe_id for s in sessions if s.recipe_id}
    equipment_ids = {eq for s in sessions for eq in (s.brewer_id, s.grinder_id, s.kettle_id) if eq}
    note_ids = {nid for s in sessions for nid in (s.flavor_note_ids_observed or [])}

    coffee: dict[int, tuple[str, str]] = {}
    if coffee_ids:
        for cid, cname, rname in db.execute(
            select(Coffee.id, Coffee.name, Roaster.name)
            .outerjoin(Roaster, Coffee.roaster_id == Roaster.id)
            .where(Coffee.id.in_(coffee_ids))
        ).all():
            coffee[cid] = (cname or "", rname or "")

    bag: dict[int, str] = {}
    if bag_ids:
        for bid, roast_date in db.execute(
            select(Bag.id, Bag.roast_date).where(Bag.id.in_(bag_ids))
        ).all():
            bag[bid] = roast_date.isoformat() if roast_date else ""

    recipe: dict[int, str] = {}
    if recipe_ids:
        for rid, rname in db.execute(
            select(Recipe.id, Recipe.name).where(Recipe.id.in_(recipe_ids))
        ).all():
            recipe[rid] = rname or ""

    equipment: dict[int, str] = {}
    if equipment_ids:
        for eid, brand, model in db.execute(
            select(Equipment.id, Equipment.brand, Equipment.model).where(
                Equipment.id.in_(equipment_ids)
            )
        ).all():
            equipment[eid] = f"{brand} {model}".strip()

    note: dict[int, str] = {}
    if note_ids:
        for nid, nname in db.execute(
            select(FlavorNote.id, FlavorNote.name).where(FlavorNote.id.in_(note_ids))
        ).all():
            note[nid] = nname or ""

    return {"coffee": coffee, "bag": bag, "recipe": recipe, "equipment": equipment, "note": note}


__all__ = [
    "ALLOWED_CSV_CONTENT_TYPES",
    "EXPORT_FIELDNAMES",
    "MAX_CSV_BYTES",
    "RowOutcome",
    "export_brews",
    "import_brews",
]
