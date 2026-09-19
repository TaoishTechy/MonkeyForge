# Changelog

## v0.6.3 — 2026-07-05

### Added
- **RBAC layer** in `auth.py`:
  - Constants: `VALID_ROLES = ("user", "moderator", "admin")`,
    `DEFAULT_USER_PERMISSIONS`, `DEFAULT_MODERATOR_PERMISSIONS`,
    `ADMIN_PERMISSIONS = ["*"]`, `ROLE_PERMISSIONS`.
  - Helpers: `get_role`, `get_permissions`, `has_permission`, `set_role`,
    `list_users`.
  - `_backfill_rbac()` migrates legacy user records on first read so
    pre-0.6.3 `users.json` files keep working without manual edits.
  - First registered user on a fresh `users.json` is auto-promoted to
    `admin`; subsequent registrations get `role="user"`.
  - `profile()` now returns `role` and `permissions`.
- **FastAPI dependency factories** in `app.py`:
  - `require_role(role)` — role-rank comparison; admin implicitly satisfies
    every role check.
  - `require_permission(perm)` — wildcard `*` short-circuit.
- **New admin endpoints** in `app.py`:
  - `GET /api/users` — sanitized user list (strips `pwd_hash`, `salt`,
    `api_keys`, `sessions`).
  - `PUT /api/user/{username}/role` — update role + optional permission
    list. Admins always receive `["*"]`.
  - `GET /api/audit/full` — full audit log view, not scoped to the
    requesting user.
- **Login response** now includes `role` and `permissions`; the audit
  record for `login` actions records the user's role.
- **CLI** — new `promote` and `list-users` subcommands.
- **Dashboard**:
  - New `👑 Admin` tab with per-user role `<select>` and Save buttons.
  - Admin-only "Full System Audit" card inside the Audit tab.
  - `renderRoleUI()` shows/hides every `.admin-only` element based on the
    current user's role.
  - `Profile` panel gains a role badge.

### Tests
- 23/23 original selftest checks still pass (`python cli.py test`).
- 27/27 new RBAC checks pass (`python /home/z/my-project/scripts/test_rbac.py`).
- 13/13 live HTTP smoke tests pass against a running server.

### Migration
No action required. Existing `users.json` files are backfilled automatically
on first read. To explicitly promote an existing user to admin:
```bash
python cli.py promote <username> --role admin
```

## v0.6.2

- Fixed `audit_mod.record()` → `audit_mod.AuditLog.record()` at all 12 call
  sites (was causing 500s on every register/login/generate/share/delete).
- Re-aligned all 22 dashboard API calls to actual backend routes.
- Relative API base (`/api`) eliminates CORS preflight errors.

## v0.6

- Axiom store with versioning, ledger chain with SHA-256 integrity, file
  upload with SHA-256 verification, audit log, profile management,
  notifications, session tokens, API key rotation, batch export.

## v0.5

- File upload, ledger sharing, audit log, profile, notifications.

## v0.1

- Equation explorer, framework loader, seed analyzer, MetaEngine generator,
  curvature / geodesic simulator, CLI.
