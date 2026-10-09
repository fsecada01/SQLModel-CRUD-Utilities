# 0004. Provide audit trail mixins

- Status: accepted
- Date: 2026-02-16

## Context
The design called tracking record creation and updates a common requirement.

## Decision
`mixins.py` provides `AuditMixin`, which adds `created_at` and `updated_at` timestamps plus optional `created_by` and `updated_by` user fields. A model opts in by inheriting from it. The design described timestamps as updated automatically by the database.

## Consequences
- Opt-in only: models that do not inherit the mixin are unaffected.
- The design's security notes say audit user IDs must not leak sensitive information.
