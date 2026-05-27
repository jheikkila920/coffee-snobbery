# Deferred Items — Phase 15.1

Items discovered during execution that are outside the scope of the plan that found them.
Do NOT fix these unless assigned to a specific plan.

## From Plan 15.1-01 (Multi-Origin Catalog Refactor)

### Pre-existing Coffee.origin references in app/ (outside migrations)

These files reference `Coffee.origin` which no longer exists as a mapped column after p15_1_multi_origin migration. They will cause SQLAlchemy `InvalidRequestError` or `AttributeError` at query execution time if the affected code paths are exercised.

| File | Line(s) | Reference | Notes |
|------|---------|-----------|-------|
| app/services/ai_service.py | 419, 488 | `func.lower(Coffee.origin) == func.lower(origin)` | Used in SQLAlchemy WHERE clauses for AI recommendation queries |
| app/services/analytics.py | 125 | `_dim_query(Coffee.origin, Coffee.origin)` | Origin dimension query for preference derivation |
| app/services/analytics.py | 236, 251 | `Coffee.origin.label("origin")`, `Coffee.origin` in select | get_sweet_spots query |
| app/services/analytics.py | 308 | `Coffee.origin` in select for recent brews | get_recent_brews query |
| app/services/search.py | 139 | `Coffee.origin` in search select | Global search result set |

**Impact:** Home page analytics, AI recommendation system, and global search will fail at runtime if any coffee is searched, the home page analytics query runs, or AI regeneration triggers. These are blocked until the owning plans update these services.

**Recommended fix timing:** Plan 15.1-02 (freshness removal) or a dedicated analytics/search update plan.

### test_analytics.py line 503

```python
assert rows[0].origin == "Ethiopia"
```

This test accesses `rows[0].origin` which is a SQLAlchemy result column from `analytics.get_sweet_spots`. That function uses `Coffee.origin` (deferred above). Test will fail when Postgres is reachable until analytics.py is updated.
