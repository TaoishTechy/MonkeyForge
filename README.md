# MonkeyForge DEMO-Lite v0.6.3

Symbolic ontology / equation engine with a public HTTP API, shared axiom
ledger, file upload, DeepSeek AI analysis, and a full-featured user dashboard.

**10 Python scripts. Everything else is JSON.** Stdlib core; the only
dependencies are FastAPI + Uvicorn + python-multipart for the HTTP layer.

> **Epistemic note:** all generator outputs are symbolic creative artifacts.
> Scores (novelty, coherence, alienness, elegance, Sophia score) are
> **heuristic creative metrics**, not calibrated measurements. Curvature
> values are diagnostics of a toy conformal metric.

## What's New in v0.6.3

- **RBAC** — roles (`user` < `moderator` < `admin`) and stored permission
  lists added to the user model. Admins implicitly satisfy every role check
  and receive the `["*"]` wildcard permission. The first user to register on
  a fresh `users.json` is auto-promoted to admin; subsequent users get the
  default `user` role.
- **Legacy backfill** — pre-0.6.3 user records are transparently migrated
  to `role=user` with the default permission set on first read.
- **New endpoints** — `GET /api/users`, `PUT /api/user/{username}/role`,
  `GET /api/audit/full` (all admin-only). `/api/login` and `/api/me` now
  return `role` + `permissions`.
- **New CLI** — `python cli.py promote <username> --role admin` and
  `python cli.py list-users`.
- **Dashboard** — new `👑 Admin` tab with per-user role editor and an
  admin-only "Full System Audit" card inside the Audit tab.
- **Dependencies** — `require_role(role)` and `require_permission(perm)`
  FastAPI dependency factories ready to drop into any protected route.

## What Was in v0.6.2

- **Critical Fix** — `audit_mod.record()` was calling a non-existent module-level function;
  all 12 call sites now correctly use `audit_mod.AuditLog.record()`. This was causing a
  500 Internal Server Error on every register, login, generate, share, and delete action.
- **Note** — if your browser cached the v0.5 dashboard, hard-refresh (Ctrl+Shift+R) to
  load the v0.6.2 dashboard with correct API routes.

## What Was in v0.6

- **Dashboard Fixes** — all 22 API calls realigned to actual backend routes;
  relative API base (`/api`) eliminates CORS preflight errors regardless of
  whether you visit via `localhost` or `127.0.0.1`
- **CORS Middleware** — explicit CORS headers for dev-server and cross-origin
  access (live-reload, file://, separate frontend port)
- **Email Field** — profile update form now sends email; backend Pydantic model
  and `update_profile()` both accept it
- **Files Tab** — drag-and-drop file upload with description, public toggle,
  download (base64 integrity-verified), and delete
- **Audit Tab** — view your own audit trail with action filter, stats summary,
  and metadata display
- **Like Button** — heart button on each ledger entry calls `POST /api/ledger/{hash}/like`
- **Notification Mark-Read** — click any unread notification to dismiss it
- **Export JSON** — one-click export of any forged axiom as a `.json` file
- **Logout API Call** — sign-out now invalidates the server-side session token
- **8-Tab Dashboard** — Forge, Explore, Simulate, Ledger, Axioms, Profile,
  Files, Audit

## What Was in v0.5

- **Axiom Store** — JSON-backed persistence with CRUD, versioning, batching, search, and pagination
- **Shared Ledger** — blockchain-like hash chain (SHA-256) for immutable axiom sharing with integrity verification
- **File Upload** — SHA-256 integrity-checked uploads with deduplication and download tracking
- **Analysis System** — built-in heuristic analysis + optional DeepSeek AI integration
- **Extended Profiles** — display name, bio, organization, research interests, skills, social links, ORCID
- **Session Tokens** — HMAC-signed session tokens with configurable expiry (default 8 hours)
- **Rate Limiting** — in-memory token bucket (60 req/min, burst 80)
- **Audit Logging** — configurable audit trail for all user actions
- **Notifications** — in-app notification system for sharing, analysis, and system events
- **Enhanced Dashboard** — dark-theme SPA, mobile-responsive, ledger feed, axiom management, profile editing

## Layout

```text
mf-lite/
  core.py            engine: coordinates, field simulator, seed processor,
                      Sophia scoring, meta generator, axiom store with versioning
  frameworks.py      dual/triple-schema framework loader (mapping, single-object, list)
  explorer.py        UHAS equation explorer (183 equations, 15 clusters, pagination)
  auth.py            registration, profiles, sessions, PBKDF2, API keys, rate limiting, notifications
  app.py             FastAPI: 46 endpoints (public + protected), CORS, serves the dashboard
  cli.py             CLI with 20 subcommands + 23-check self-test
  ledger.py          shared axiom ledger with hash chain and integrity verification
  storage.py         file upload/download with SHA-256 integrity checks
  analysis.py        basic heuristic analysis + optional DeepSeek AI integration
  audit.py           configurable audit logging
  static/dashboard.html   user dashboard (8 tabs: Forge, Explore, Simulate, Ledger, Axioms, Profile, Files, Audit)
  data/              10 JSON files: equations, 50+ frameworks, corpus, config, user/axiom/ledger stores
  output/            generated axiom batches (per user, per run)
  uploads/           uploaded files (per user)
```

## Quickstart

```bash
pip install -r requirements.txt
python cli.py test        # 23-check self-test, should print PASS 23/23
python cli.py serve       # http://localhost:8480
```

* **Dashboard:** http://localhost:8480/ — register, get your API key,
  forge axioms, browse equations, probe the simulator, share to ledger,
  upload files, view audit log.
* **API docs (OpenAPI):** http://localhost:8480/docs

## API

### Public — no auth

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | status + dataset counts + ledger stats |
| GET | `/api/clusters` | the 15 equation clusters |
| GET | `/api/equations?cluster=` | equations in a cluster |
| GET | `/api/search?q=` | keyword search across equations |
| GET | `/api/equation/{id}` | one equation by id (e.g. `QG-01`) |
| GET | `/api/frameworks` | all frameworks + loader report |
| GET | `/api/framework/{name}` | one framework |
| POST | `/api/register` | create account, returns API key once |
| POST | `/api/login` | password check, returns session token |
| GET | `/api/profile/{username}` | public user profile |
| GET | `/api/axioms/public` | paginated public axioms with search/sort |
| GET | `/api/ledger` | paginated shared ledger feed |
| GET | `/api/ledger/verify` | verify full chain integrity |
| GET | `/api/ledger/featured` | featured/verified axioms |
| GET | `/api/ledger/stats` | ledger statistics |

### Protected — send `X-API-Key`, `X-Session-Token`, or HTTP Basic

| Method | Path | What it does |
|---|---|---|
| GET | `/api/me` | full profile + stats |
| POST | `/api/rotate-key` | new API key; old one dies |
| GET | `/api/stats` | user + axiom statistics |
| PUT | `/api/profile` | update profile fields (including email) |
| POST | `/api/generate` | `{seed?, count, force_phase_transition?}` → scored axioms, persisted |
| POST | `/api/analyze` | seed → semantic features + target 5D coordinates |
| POST | `/api/analyze/axiom` | `{axiom_id, mode}` → basic or DeepSeek analysis |
| POST | `/api/simulate` | 5 coords → curvature diagnostics + gradient flow |
| POST | `/api/ricci` | 5 coords → curvature only |
| POST | `/api/geodesic` | `{start, end, steps}` → conformal geodesic path |
| GET | `/api/axioms` | list own axioms (filter by status/visibility/category) |
| GET | `/api/axiom/{id}` | get axiom detail (increments view count) |
| PUT | `/api/axiom/{id}` | update axiom (name, tags, status, visibility) |
| DELETE | `/api/axiom/{id}` | delete own axiom |
| POST | `/api/share` | share axiom to ledger (hash chain) |
| POST | `/api/ledger/{hash}/like` | like a ledger entry |
| POST | `/api/upload` | upload file (multipart, SHA-256 integrity) |
| GET | `/api/files` | list own uploaded files |
| GET | `/api/files/{id}` | file metadata |
| GET | `/api/files/{id}/download` | download file (integrity-verified) |
| DELETE | `/api/files/{id}` | delete own file |
| GET | `/api/notifications` | list notifications (unread filter) |
| POST | `/api/notifications/{id}/read` | mark notification read |
| GET | `/api/audit` | audit log (own actions only) |
| GET | `/api/audit/stats` | audit statistics |
| POST | `/api/logout` | invalidate session token |

Example:

```bash
# Register and get API key
KEY=$(curl -s -X POST localhost:8480/api/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"ghost","password":"mesh-demo-pass","email":"ghost@example.com"}' | jq -r .api_key)

# Generate axioms (persisted to store)
curl -s -X POST localhost:8480/api/generate \
  -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"seed":"recursive mirror of observer time","count":3}' | jq .

# Analyze an axiom with basic analysis
curl -s -X POST localhost:8480/api/analyze/axiom \
  -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"axiom_id":"AXM-00001","mode":"basic"}' | jq .

# Share to ledger
curl -s -X POST localhost:8480/api/share \
  -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"axiom_id":"AXM-00001"}' | jq .

# Browse the ledger
curl -s localhost:8480/api/ledger?page=1 | jq .

# Verify chain integrity
curl -s localhost:8480/api/ledger/verify | jq .
```

## CLI

```text
python cli.py serve [--host H] [--port P]     start API + dashboard
python cli.py list-clusters
python cli.py list-equations <cluster>
python cli.py search <keyword>
python cli.py show <eq-id>
python cli.py generate [--seed TEXT] [--count N] [--force-pt] [--numeric-seed N]
python cli.py analyze --seed TEXT
python cli.py framework <name>
python cli.py frameworks
python cli.py simulate --coords "0.2 0.8 0.5 0.3 0.9"
python cli.py ricci --coords "0.2 0.8 0.5 0.3 0.9"
python cli.py geodesic --start "0.1 0.1 0.1 0.1 0.1" --end "0.9 0.9 0.9 0.9 0.9"
python cli.py register <username>             (prompts for password + email)
python cli.py profile [username]              (show user profile)
python cli.py share <axiom-id>               (share axiom to ledger)
python cli.py ledger [--page N] [--search KW] (browse shared ledger)
python cli.py ledger-verify                   (verify chain integrity)
python cli.py analyze-axiom <id> [--mode basic|deepseek]
python cli.py upload <filepath>               (upload file)
python cli.py my-axioms [--page N]           (list own axioms)
python cli.py audit [--action ACT]           (view audit log)
python cli.py test                           # 23-check self-test
```

## v0.6 Architecture

### Axiom Lifecycle

```
Generate → Store (draft/private) → Analyze → Edit → Publish → Share to Ledger
                                                    ↓
                                              Version History
```

### Ledger Chain

Each shared axiom creates a hash-chained entry:

```
Genesis → [hash_1] → [hash_2] → [hash_3] → ...
            ↑              ↑              ↑
    content_hash +  content_hash +  content_hash +
    previous=null  previous=hash_1  previous=hash_2
```

### Authentication Priority

1. `X-Session-Token` header (HMAC-signed, 8h expiry)
2. `X-API-Key` header (SHA-256 digested, shown once)
3. `Authorization: Basic` (username:password, timing-safe compare)

### v0.5 → v0.6 Root Cause Fix

`OPTIONS /api/auth/register 404` was two bugs stacked:

1. **Origin mismatch** — the frontend hardcoded `http://localhost:8480/api`
   while the page was opened at `http://127.0.0.1:8480`. Different origin →
   browser sends a CORS preflight (OPTIONS) before the POST.
2. **Route mismatch** — the entire dashboard script was written against an
   imagined API (`/auth/register`, `/axioms/generate`, `/axioms/mine`,
   `/ledger/share`, `/simulate/geodesic`, `/profile/rotate-key`, PATCH verbs)
   that doesn't exist in app.py. So the preflight hit a nonexistent path → 404.
   Even same-origin, every one of those calls would have 404'd.

Fix #1 makes the API base relative (`/api`); fix #2 realigns all 22 calls and
their request/response shapes to the actual app.py surface.

## Fixes Carried Over from v0.1 (vs. Original Monolith)

* **P0-1** — default-constructed simulator derives its attractor from loaded
  frameworks with a neutral fallback; never crashes.
* **P0-2** — triple-schema framework loader accepts mapping files, single-object
  files, and top-level lists; every skip reported with a reason.
* **P0-4** — `force_phase_transition` is implemented; forced generations are
  marked `phase_transition_forced: true`.
* **P1-6** — all IDs/derived coordinates use SHA-256, never Python `hash()`;
  `--numeric-seed` gives deterministic generation.
* **P1-7** — one coordinate bound everywhere: `[0, 1]` per dimension.
* **S5F** — Ricci feedback enters the Sophia score through `tanh`, acting as
  a gradient rather than a saturating switch.

## Security Notes

DEMO-grade, honest limits:

* Passwords: PBKDF2-HMAC-SHA256, 200k iterations, per-user salt. API keys are
  stored as SHA-256 digests — shown once at registration/rotation.
* Session tokens: HMAC-SHA256 signed, 8-hour configurable expiry.
* Storage is JSON files with process-level locking: **single process only**.
  Run behind one uvicorn worker, or swap in SQLite/PostgreSQL before scaling.
* Rate limiting: in-memory token bucket (60/min, burst 80). Not persistent
  across restarts.
* CORS: restricted to localhost/127.0.0.1 on port 8480. Expand before exposing.
* No TLS, no email verification, no password reset. Put a reverse proxy
  with TLS in front before exposing beyond localhost.
* The dashboard stores your session token in localStorage for convenience;
  use "Sign out" on shared machines.

## License

MIT. Part of the GhostMesh open-source collective.
----------------------------------------
