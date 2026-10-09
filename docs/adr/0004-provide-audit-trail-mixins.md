# 0004. Provide audit trail mixins

- Status: accepted
- Date: 2026-02-16

## Context
The design called tracking record creation and updates a common requirement.

## Decision
`mixins.py` provides `AuditMixin`, which adds `created_at` and `updated_at` timestamps plus optional `created_by` and `updated_by` user fields. A model opts in by inheriting from it. As implemented in `mixins.py`, `created_at` uses a Python-side `default_factory` and `updated_at` uses a Python-side SQLAlchemy `onupdate`, both from `_utc_now`, rather than database defaults. The design had described the database updating them.

## Consequences
- Because the defaults are Python-side, Core `UPDATE` and bulk helpers do not refresh `updated_at` for `AuditMixin` models. `TimestampMixin` (added later, using `server_default=func.now()`) covers the timestamp-only case.
- Opt-in only: models that do not inherit the mixin are unaffected.
- The design's security notes say audit user IDs must not leak sensitive information.
