"""Phase 10 global search: six GIN trigram indexes for ILIKE accelerated search.

Revision ID: p10_search_indexes
Revises: p5_brew_sessions
Create Date: 2026-05-22

Adds GIN trigram indexes on the six searchable columns identified in
10-RESEARCH.md §"Index DDL for the Migration" and 10-PATTERNS.md
§"app/migrations/versions/p10_search_indexes.py".

Indexes created:

1. ix_search_coffees_name        ON coffees        (name gin_trgm_ops)
2. ix_search_roasters_name       ON roasters       (name gin_trgm_ops)
3. ix_search_flavor_notes_name   ON flavor_notes   (name gin_trgm_ops)
4. ix_search_recipes_name        ON recipes        (name gin_trgm_ops)
5. ix_search_equipment_brand_model ON equipment    ((brand || ' ' || model) gin_trgm_ops)
6. ix_search_brew_sessions_notes ON brew_sessions  (notes gin_trgm_ops)

Design notes:

* ``USING GIN (... gin_trgm_ops)`` — hand-edited via ``op.execute()``. SQLAlchemy
  2.0 autogenerate cannot emit ``USING GIN``; this is the established pattern from
  p4_shared_catalog.py lines 174-178.

* ``IF NOT EXISTS`` — prevents re-run failures if the migration is accidentally
  applied twice. Harmless on first apply.

* NO ``CONCURRENTLY`` — Alembic wraps each migration in a transaction by default;
  ``CREATE INDEX CONCURRENTLY`` cannot run inside a transaction block and raises
  ``ERROR: CREATE INDEX CONCURRENTLY cannot run inside a transaction block``
  (RESEARCH.md Pitfall 7). These tables have no production traffic at first
  Phase 10 deploy; a non-concurrent index build is safe and fast.

* NO ``CREATE EXTENSION`` — both ``pg_trgm`` and ``unaccent`` are already
  installed in ``0001_initial.py`` lines 60-62. Do not re-create them; they
  are cluster-shared and ``IF NOT EXISTS`` would mask an error if the extension
  install fails.

* Expression index on equipment — ``(brand || ' ' || model)`` is the display
  identity for equipment rows (no ``name`` column exists on the Equipment model;
  see RESEARCH.md Pitfall 2 and D-14). The GIN trigram index on the expression
  accelerates ``ILIKE`` on ``func.concat(Equipment.brand, ' ', Equipment.model)``
  queries in the search service.

Alembic-safe convention (mirrors p4_shared_catalog.py lines 32-35):
this migration body does NOT import from ``app.models``. Schema is described
inline via ``op.execute()`` SQL strings. A future model rename does not
invalidate this migration.

Requirements traceability:

* SEARCH-01 — search across coffee names (coffees GIN index)
* SEARCH-02 — search across roasters, recipes, equipment, flavor_notes
* SEARCH-04 — search across brew_sessions.notes (per-user scoped in service)
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p10_search_indexes"
down_revision: str | Sequence[str] | None = "p5_brew_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create six GIN trigram indexes for global search acceleration."""
    # pg_trgm already installed in 0001_initial.py — no CREATE EXTENSION needed.

    # coffees.name — CITEXT column; GIN trigram index for ILIKE substring matching
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_coffees_name ON coffees USING GIN (name gin_trgm_ops)"
    )

    # roasters.name — CITEXT column
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_roasters_name "
        "ON roasters USING GIN (name gin_trgm_ops)"
    )

    # flavor_notes.name — CITEXT column
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_flavor_notes_name "
        "ON flavor_notes USING GIN (name gin_trgm_ops)"
    )

    # recipes.name — Text column (no description column exists; RESEARCH.md Pitfall 1)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_recipes_name ON recipes USING GIN (name gin_trgm_ops)"
    )

    # equipment — no name column; expression index on brand || ' ' || model (D-14)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_equipment_brand_model "
        "ON equipment USING GIN ((brand || ' ' || model) gin_trgm_ops)"
    )

    # brew_sessions.notes — Text column; per-user scoping enforced in service layer
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_search_brew_sessions_notes "
        "ON brew_sessions USING GIN (notes gin_trgm_ops)"
    )


def downgrade() -> None:
    """Drop the six GIN trigram search indexes in reverse creation order."""
    op.execute("DROP INDEX IF EXISTS ix_search_brew_sessions_notes")
    op.execute("DROP INDEX IF EXISTS ix_search_equipment_brand_model")
    op.execute("DROP INDEX IF EXISTS ix_search_recipes_name")
    op.execute("DROP INDEX IF EXISTS ix_search_flavor_notes_name")
    op.execute("DROP INDEX IF EXISTS ix_search_roasters_name")
    op.execute("DROP INDEX IF EXISTS ix_search_coffees_name")
