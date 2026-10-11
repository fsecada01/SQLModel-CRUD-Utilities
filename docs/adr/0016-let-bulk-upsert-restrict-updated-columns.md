# 0016. Let bulk_upsert_mappings restrict the columns updated on conflict

- Status: accepted (amends 0011 and 0012)
- Date: 2026-10-10

## Context
`bulk_upsert_mappings` / `a_bulk_upsert_mappings` overwrite every column of the first payload mapping on conflict. There is no way to say "insert, but on conflict only touch `updated_at`" (or only `value`), so a caller who needs that has to drop to raw SQLAlchemy and its `set_` argument. Issue #50 raised it in the body of #41 and left it to the maintainer; the maintainer decided to add it.

ADR-0011 and ADR-0012 are the ADRs that describe the bulk helpers as Core-statement helpers (no ORM events, no change history, explicit cache invalidation after commit); ADR-0004 and ADR-0005 record that Core statements bypass Python-side defaults and `SoftDeleteMixin`; ADR-0008 requires additive, backward-compatible changes. This ADR adds one opt-in parameter to a helper those ADRs describe and leaves every behaviour they record unchanged.

## Decision
Add an optional keyword parameter `update_columns: Sequence[str] | None = None` to `bulk_upsert_mappings` and `a_bulk_upsert_mappings`, appended after `pk_fields` so positional callers are unaffected, with an identical signature in both modules (the parity test enforces it).

- `None` (default): unchanged. Every column in the first mapping is written on conflict.
- A sequence of column names: the `ON CONFLICT ... DO UPDATE SET` clause lists only those columns, each as `col = excluded.col`. A conflicting row keeps its other columns. A row that does not conflict is inserted with every provided column, exactly as before.
- Names are table column keys, the same keys the payload uses. Duplicates are ignored; order is irrelevant.

### Validation
All of it runs before a statement is sent, and raises `ValueError`, like the key-column checks in the other bulk helpers (`validate_primary_key_field`, `validate_update_columns`):

| Input | Result |
|---|---|
| empty sequence | `ValueError` (pass `None` for "all columns") |
| a bare `str` | `ValueError` (it would otherwise be iterated as characters) |
| a name that is not a column of the model, including a different case | `ValueError` naming the unknown columns |
| a primary-key column of the model | `ValueError` |
| a `pk_fields` (conflict-target) column | `ValueError` |
| a column that is not a key of the first mapping in `payload` | `ValueError` |

The last rule exists because the first mapping decides which columns the `INSERT` carries. `excluded.<col>` for a column the statement does not insert is `NULL` (or the database default), so accepting it would silently wipe that column on every conflict. Rejecting it also means "update only `updated_at`" requires the caller to put `updated_at` in the payload, which fits ADR-0004: the bulk helpers do not refresh Python-side defaults on update, so the caller supplies the value.

### Dialects
The clause is built with `on_conflict_do_update(set_=...)` and `excluded`, as before, so the behaviour is the same for `postgresql` and `sqlite`: the real SQLite path is tested sync and async, and the PostgreSQL SQL is compile-checked. MySQL is not changed: `sqlalchemy.dialects.mysql.insert` has `on_duplicate_key_update` and `inserted`, not `on_conflict_do_update` and `excluded`, and MySQL has no `RETURNING` clause. `bulk_upsert_mappings` already raises `AttributeError` there with or without this parameter, so `update_columns` does not make that worse, and this ADR does not add MySQL support. That would be a separate decision.

### Unchanged
The `(True, rows)` return value, the single `RETURNING` statement, the pre-commit read of the returned rows, and cache invalidation after commit (ADR-0012) are untouched. As ADR-0011 says, the bulk helpers still write no change history.

## Consequences
- Callers can express "insert, update only these columns on conflict" without raw SQLAlchemy, with the same validation guarantees as the other bulk helpers.
- Passing `update_columns` is not a way to write different values on conflict than on insert; for that, callers still need their own statement.
- The first mapping's keys remain load-bearing (inherited, not new): a later mapping with an extra key has it silently dropped from the `INSERT`, and a later mapping missing a key the first one has fails at compile time.
- `update_columns` cannot include the conflict target. A conflict on a non-primary-key unique column therefore also protects that column, which is the least surprising outcome and is easy to relax later.
- Revisit if MySQL support is wanted (`on_duplicate_key_update`, no `RETURNING`).

## Alternatives considered
- Do nothing and record "no": rejected by the maintainer in the decision on #50; the gap forces raw SQLAlchemy for a common upsert shape.
- Default-off versus a new default: the parameter is opt-in, `None` meaning today's behaviour, so no caller changes (ADR-0008). A default that restricted columns would silently change what existing callers write.
- A different name (`set_columns`, `on_conflict_set`, `exclude_columns`): `update_columns` matches the "update" vocabulary of `validate_update_columns` and `bulk_update_rows`. An exclusion list was rejected because "everything but these" depends on the payload's keys and is easier to get wrong than an explicit list.
- Accept SQLAlchemy's `set_` dict directly: rejected. It exposes `excluded` and, on other dialects, `inserted`, ties the public API to SQLAlchemy objects, lets arbitrary SQL expressions through where we validate names, and gives the helper no column list to check against the payload and model.
- A separate function (`bulk_upsert_restricted`): rejected; the parameter is additive and keeps one name to discover and one parity pair to maintain.
- Validate only against the model, not the payload: rejected, because it allows the silent `NULL` write described above.
