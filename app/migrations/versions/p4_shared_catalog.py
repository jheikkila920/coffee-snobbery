"""Phase 4 shared catalog: roasters + flavor_notes + coffees + equipment + recipes + bag FK/photo.

Revision ID: p4_shared_catalog
Revises: p3_api_credentials
Create Date: 2026-05-18

One migration per logical change (CONTEXT D-02) — the entire Phase 4
shared-catalog schema lands here so the wave-2 entity routers
(plans 04-04..04-08) can run against the full target schema from one
``alembic upgrade head``.

Tables created (FK-order matters):

1. ``roasters``     (no FK dependencies)
2. ``flavor_notes`` (no FK dependencies)
3. ``coffees``      (FK -> roasters; SET NULL on delete)
4. ``equipment``    (no FK dependencies)
5. ``recipes``      (no FK dependencies)

Plus two ``bags`` modifications: the FK constraint to ``coffees.id`` with
``ondelete='RESTRICT'`` (CAT-04 promise from Phase 0, finally landed), and
the new ``photo_filename`` column (CAT-08 storage; consumed by the
photos pipeline shipped in plan 04-01 and the serving route in plan 04-10).

Hand-edited DDL (autogenerate cannot emit it):

* ``CREATE INDEX ix_coffees_advertised_flavor_note_ids ON coffees USING GIN
  (advertised_flavor_note_ids)`` — Pitfall 3 in 04-RESEARCH.md.
  SQLAlchemy 2.0 + Alembic do not understand ``USING GIN`` for array
  indexes; emit via raw ``op.execute``.

Alembic-safe convention (mirrors ``0001_initial.py`` + ``p3_api_credentials.py``):
this migration body does NOT import from ``app.models``. Schema is described
inline with ``sa.Column`` / ``sa.CheckConstraint`` / ``sa.ForeignKey``.
A future model rename does not invalidate this migration.

Extensions (citext, pg_trgm, unaccent) are already installed in
``0001_initial.py:59-61`` — DO NOT re-create or drop them. They are
cluster-shared.

Requirements traceability:

* CAT-01 — roasters table
* CAT-02 — flavor_notes table + category CHECK
* CAT-03 — coffees table + advertised_flavor_note_ids ARRAY + GIN index
* CAT-05 — equipment table + type CHECK + usage_count denormalization
* CAT-06 — recipes table + JSONB steps
* CAT-08 — bags.photo_filename column + bags.coffee_id FK
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "p4_shared_catalog"
down_revision: str | Sequence[str] | None = "p3_api_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the five Phase 4 catalog tables + add bags FK + bags.photo_filename."""
    # ---- 1) roasters (CAT-01) --------------------------------------------
    # No FK dependencies — created first so coffees can FK to it.
    op.create_table(
        "roasters",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column("name", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("location", sa.Text, nullable=True),
        sa.Column("website", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_roasters_archived", "roasters", ["archived"])

    # ---- 2) flavor_notes (CAT-02) ----------------------------------------
    # 9-value category CHECK matches Pydantic schema regex (plan 04-02).
    op.create_table(
        "flavor_notes",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column("name", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "category IN ('fruit','floral','sweet','chocolate','nutty',"
            "'spice','savory','fermented','other')",
            name="flavor_notes_category_check",
        ),
    )

    # ---- 3) coffees (CAT-03) ---------------------------------------------
    # FK -> roasters.id with SET NULL: a coffee can outlive its roaster
    # (orphaned coffee rows are intentional, per 04-PATTERNS.md §coffee).
    # The reverse direction (bags.coffee_id) uses RESTRICT (step 6 below).
    op.create_table(
        "coffees",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        # NOT unique — different roasters can share a name.
        sa.Column("name", postgresql.CITEXT(), nullable=False),
        sa.Column(
            "roaster_id",
            sa.BigInteger,
            sa.ForeignKey("roasters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("country", sa.Text, nullable=True),
        sa.Column("origin", sa.Text, nullable=True),
        sa.Column("process", sa.Text, nullable=True),
        sa.Column("roast_level", sa.Text, nullable=True),
        sa.Column("varietal", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "advertised_flavor_note_ids",
            postgresql.ARRAY(sa.BigInteger),
            nullable=False,
            server_default=sa.text("'{}'::bigint[]"),
        ),
        sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # CHECK constraints — IS NULL OR shape because both columns are nullable.
        sa.CheckConstraint(
            "process IS NULL OR process IN "
            "('washed','natural','honey','anaerobic','experimental','unknown')",
            name="coffees_process_check",
        ),
        sa.CheckConstraint(
            "roast_level IS NULL OR roast_level IN "
            "('light','medium-light','medium','medium-dark','dark','unknown')",
            name="coffees_roast_level_check",
        ),
    )
    op.create_index("ix_coffees_roaster_id", "coffees", ["roaster_id"])
    op.create_index("ix_coffees_archived", "coffees", ["archived"])
    # GIN index — hand-edited per Pitfall 3 (autogenerate cannot emit USING GIN).
    op.execute(
        "CREATE INDEX ix_coffees_advertised_flavor_note_ids "
        "ON coffees USING GIN (advertised_flavor_note_ids)"
    )

    # ---- 4) equipment (CAT-05) -------------------------------------------
    op.create_table(
        "equipment",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("brand", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("usage_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "type IN ('brewer','grinder','kettle','scale','water_filter','other')",
            name="equipment_type_check",
        ),
    )
    op.create_index("ix_equipment_type", "equipment", ["type"])

    # ---- 5) recipes (CAT-06) ---------------------------------------------
    op.create_table(
        "recipes",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("dose_grams", sa.Integer, nullable=False),
        sa.Column("water_grams", sa.Integer, nullable=False),
        sa.Column("water_temp_c", sa.Integer, nullable=False),
        sa.Column("grind_setting", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "steps",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ---- 6) Modify bags (CAT-04 FK completion + CAT-08 photo column) -----
    # The FK constraint is added LAST so coffees exists by the time the FK
    # is validated against existing bags rows. On a fresh DB the table is
    # empty and validation is trivial; on a populated DB the deployer must
    # ensure every bag.coffee_id corresponds to a real coffees.id before
    # this migration runs (none should exist yet — Phase 4 is the first
    # phase to ship a UI for inserting bags). The named constraint
    # ``fk_bags_coffee_id`` lets future migrations target it by name.
    op.add_column("bags", sa.Column("photo_filename", sa.Text, nullable=True))
    op.create_foreign_key(
        "fk_bags_coffee_id",
        "bags",
        "coffees",
        ["coffee_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Reverse the upgrade in strict reverse order.

    Notes:
    * Postgres extensions (citext, pg_trgm, unaccent) are NOT dropped —
      they were installed by ``0001_initial.py`` and are cluster-shared.
    * The GIN index on coffees is dropped via raw SQL with IF EXISTS so
      the downgrade is idempotent even if the index was manually rebuilt.
    """
    # 1) Reverse the bags modifications.
    op.drop_constraint("fk_bags_coffee_id", "bags", type_="foreignkey")
    op.drop_column("bags", "photo_filename")

    # 2) Drop the five tables in reverse creation order.
    op.drop_table("recipes")

    op.drop_index("ix_equipment_type", table_name="equipment")
    op.drop_table("equipment")

    op.execute("DROP INDEX IF EXISTS ix_coffees_advertised_flavor_note_ids")
    op.drop_index("ix_coffees_archived", table_name="coffees")
    op.drop_index("ix_coffees_roaster_id", table_name="coffees")
    op.drop_table("coffees")

    op.drop_table("flavor_notes")

    op.drop_index("ix_roasters_archived", table_name="roasters")
    op.drop_table("roasters")
