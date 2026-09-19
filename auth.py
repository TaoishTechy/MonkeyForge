"""MonkeyForge DEMO-Lite v0.6.2 -- users, API keys, sessions, profiles, rate limiting.

JSON-backed user store (data/users.json). Passwords hashed with PBKDF2-HMAC-SHA256
(200k iterations, per-user salt). API keys stored as SHA-256 digests.
v0.6 adds: improved session management, notification preferences.

DEMO-grade: single-process file locking only. Thread-safe via threading.Lock.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
USERS_PATH = DATA_DIR / "users.json"
NOTIFS_PATH = DATA_DIR / "notifications.json"

_ITERATIONS = 200_000
_LOCK = threading.Lock()
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SESSION_SECRET = "monkeyforge-demo-lite-v0.6.2-session-secret"
_SESSION_TIMEOUT = 480 * 60  # 8 hours in seconds

# -- RBAC ----------------------------------------------------------------------
# Roles: user, moderator, admin
# Permissions are stored as a JSON array on each user record. The literal "*"
# grants every permission (admin). New users get the default user permission
# set below; the first registered user is auto-promoted to admin so a fresh
# install always has an administrator available.
VALID_ROLES = ("user", "moderator", "admin")

DEFAULT_USER_PERMISSIONS = [
    "axioms:read", "axioms:write", "axioms:delete",
    "ledger:read", "ledger:share", "ledger:like",
    "profile:edit", "profile:view",
    "files:read", "files:write", "files:delete",
    "audit:own",
]

DEFAULT_MODERATOR_PERMISSIONS = [
    *DEFAULT_USER_PERMISSIONS,
    "ledger:moderate", "axioms:moderate", "audit:view",
]

ADMIN_PERMISSIONS = ["*"]  # wildcard — grants every check

ROLE_PERMISSIONS = {
    "user": DEFAULT_USER_PERMISSIONS,
    "moderator": DEFAULT_MODERATOR_PERMISSIONS,
    "admin": ADMIN_PERMISSIONS,
}


def _backfill_rbac(user_record: dict) -> dict:
    """Ensure legacy user records (pre-0.6.3) have role + permissions fields."""
    if "role" not in user_record:
        user_record["role"] = "user"
    if user_record["role"] not in VALID_ROLES:
        user_record["role"] = "user"
    if "permissions" not in user_record:
        user_record["permissions"] = ROLE_PERMISSIONS[user_record["role"]]
    return user_record


def _load() -> dict:
    if not USERS_PATH.exists():
        return {}
    with open(USERS_PATH, encoding="utf-8") as f:
        users = json.load(f)
    # Backfill any legacy records on read so RBAC fields always exist
    needs_save = False
    for uname, rec in users.items():
        before = ("role" in rec, "permissions" in rec)
        _backfill_rbac(rec)
        if ("role" in rec, "permissions" in rec) != before:
            needs_save = True
    if needs_save:
        _save(users)
    return users


def get_role(username: str) -> str:
    """Return the user's role, or 'user' if unknown."""
    return _load().get(username, {}).get("role", "user")


def get_permissions(username: str) -> list[str]:
    """Return the user's permission list. Admins get ['*']."""
    rec = _load().get(username, {})
    if rec.get("role") == "admin":
        return ["*"]
    return rec.get("permissions", DEFAULT_USER_PERMISSIONS)


def has_permission(username: str, permission: str) -> bool:
    perms = get_permissions(username)
    return "*" in perms or permission in perms


def set_role(username: str, role: str, permissions: list[str] | None = None) -> dict:
    """Update a user's role and (optionally) permissions. Returns the new profile."""
    if role not in VALID_ROLES:
        raise AuthError(f"invalid role: {role!r} (must be one of {VALID_ROLES})")
    with _LOCK:
        users = _load()
        if username not in users:
            raise AuthError(f"unknown user: {username!r}")
        users[username]["role"] = role
        if permissions is None:
            users[username]["permissions"] = ROLE_PERMISSIONS[role]
        else:
            # Validate list shape; dedupe; admins always get the wildcard
            if not isinstance(permissions, list):
                raise AuthError("permissions must be a list of strings")
            users[username]["permissions"] = (list(permissions) if role != "admin"
                                              else ["*"])
        users[username]["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _save(users)
    return profile(username)


def list_users() -> list[dict]:
    """Return a sanitized list of all users (admin view). Strips pwd_hash, salt,
    api_keys, sessions."""
    users = _load()
    out = []
    for uname, rec in users.items():
        out.append({
            "username": uname,
            "email": rec.get("email", ""),
            "display_name": rec.get("display_name", uname),
            "role": rec.get("role", "user"),
            "permissions": rec.get("permissions", DEFAULT_USER_PERMISSIONS),
            "plan_type": rec.get("plan_type", "free"),
            "profile_visibility": rec.get("profile_visibility", "public"),
            "total_axioms_generated": rec.get("total_axioms_generated", 0),
            "total_axioms_shared": rec.get("total_axioms_shared", 0),
            "reputation_score": rec.get("reputation_score", 0.0),
            "created": rec.get("created"),
            "last_login_at": rec.get("last_login_at"),
            "active_sessions": len(rec.get("sessions", [])),
        })
    return sorted(out, key=lambda u: u["username"])


# -- rate limiter (in-memory token bucket) -------------------------------------

class _RateLimiter:
    def __init__(self, rate: float = 60.0, burst: int = 80):
        self.rate = rate
        self.burst = burst
        self._buckets: dict[str, dict] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            b = self._buckets.get(key)
            if not b:
                self._buckets[key] = {"tokens": float(self.burst) - 1, "last": now}
                return True
            elapsed = now - b["last"]
            b["tokens"] = min(self.burst, b["tokens"] + elapsed * self.rate / 60.0)
            b["last"] = now
            if b["tokens"] >= 1.0:
                b["tokens"] -= 1.0
                return True
            return False

    def reset(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)

rate_limiter = _RateLimiter()


# -- storage -----------------------------------------------------------------
# NOTE: _load() is defined above (in the RBAC section) so it can backfill
# legacy user records on read. _save() is the only storage primitive here.

def _save(users: dict) -> None:
    tmp = USERS_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=1, ensure_ascii=False)
    tmp.replace(USERS_PATH)


def _load_notifs() -> dict:
    if not NOTIFS_PATH.exists():
        return {"notifications": []}
    with open(NOTIFS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_notifs(data: dict) -> None:
    tmp = NOTIFS_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    tmp.replace(NOTIFS_PATH)


# -- primitives ----------------------------------------------------------------

def _hash_password(password: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return dk.hex()


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _new_api_key() -> str:
    return "mk_" + secrets.token_urlsafe(30)


def _make_session_token(username: str) -> str:
    raw = f"{username}:{time.time()}:{secrets.token_hex(16)}"
    sig = hmac.new(_SESSION_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]
    return f"mf_sess_{secrets.token_hex(8)}_{sig}"


def _verify_session_token(token: str) -> str | None:
    if not token or not token.startswith("mf_sess_"):
        return None
    users = _load()
    now = time.time()
    for uname, user in users.items():
        for sess in user.get("sessions", []):
            if sess["token"] == token:
                if now - sess.get("created_at", 0) > _SESSION_TIMEOUT:
                    return None
                return uname
    return None


# -- public API ----------------------------------------------------------------

class AuthError(Exception):
    """Raised with a human-readable message; maps to HTTP 400/401."""


def register(username: str, password: str, email: str | None = None) -> dict:
    username = (username or "").strip()
    if not _USERNAME_RE.match(username):
        raise AuthError("username must be 3-32 chars: letters, digits, _ . -")
    if len(password or "") < 8:
        raise AuthError("password must be at least 8 characters")
    if email and not _EMAIL_RE.match(email):
        raise AuthError("invalid email address")
    with _LOCK:
        users = _load()
        if username.lower() in (u.lower() for u in users):
            raise AuthError("username already taken")
        if email and any(u.get("email", "").lower() == email.lower() for u in users.values()):
            raise AuthError("email already registered")
        salt = secrets.token_bytes(16)
        api_key = _new_api_key()
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # RBAC: the first user to register becomes the initial admin so a
        # fresh install always has an administrator. Subsequent users get
        # the default 'user' role.
        is_first_user = len(users) == 0
        role = "admin" if is_first_user else "user"
        users[username] = {
            "email": email or "",
            "salt": salt.hex(),
            "pwd_hash": _hash_password(password, salt),
            "api_keys": [{"key_hash": _hash_key(api_key), "name": "default",
                         "created": now, "last_used": None, "is_active": True}],
            "role": role,
            "permissions": list(ROLE_PERMISSIONS[role]),
            "display_name": username,
            "bio": "",
            "organization": "",
            "title": "",
            "website": "",
            "orcid_id": "",
            "research_interests": [],
            "skills": [],
            "github_url": "",
            "linkedin_url": "",
            "twitter_url": "",
            "profile_visibility": "public",
            "theme_preference": "system",
            "language": "en",
            "plan_type": "free",
            "total_axioms_generated": 0,
            "total_axioms_shared": 0,
            "reputation_score": 0.0,
            "created": now,
            "updated_at": now,
            "last_login_at": None,
            "generations": 0,
            "sessions": [],
        }
        _save(users)
    return {"username": username, "email": email, "api_key": api_key,
            "note": "store this key now; it is not shown again"}


def verify_password(username: str, password: str) -> bool:
    users = _load()
    user = users.get(username)
    if not user:
        _hash_password(password or "", b"x" * 16)
        return False
    expected = user["pwd_hash"]
    actual = _hash_password(password or "", bytes.fromhex(user["salt"]))
    return hmac.compare_digest(expected, actual)


def verify_api_key(key: str) -> str | None:
    if not key:
        return None
    digest = _hash_key(key)
    users = _load()
    for username, user in users.items():
        for ak in user.get("api_keys", []):
            if ak.get("is_active", True) and hmac.compare_digest(ak.get("key_hash", ""), digest):
                # Update last used
                ak["last_used"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                return username
    return None


def create_session(username: str) -> str:
    token = _make_session_token(username)
    with _LOCK:
        users = _load()
        if username not in users:
            raise AuthError("unknown user")
        now = time.time()
        # Clean expired sessions
        users[username]["sessions"] = [
            s for s in users[username].get("sessions", [])
            if now - s.get("created_at", 0) <= _SESSION_TIMEOUT
        ]
        users[username]["sessions"].append({
            "token": token,
            "created_at": now,
            "user_agent": "",
            "ip_address": "",
        })
        users[username]["last_login_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _save(users)
    return token


def delete_session(token: str) -> None:
    with _LOCK:
        users = _load()
        for user in users.values():
            before = len(user.get("sessions", []))
            user["sessions"] = [s for s in user.get("sessions", []) if s["token"] != token]
            if len(user["sessions"]) < before:
                _save(users)
                return


def rotate_api_key(username: str, key_name: str = "default") -> dict:
    with _LOCK:
        users = _load()
        if username not in users:
            raise AuthError("unknown user")
        api_key = _new_api_key()
        key_hash = _hash_key(api_key)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        keys = users[username].get("api_keys", [])
        # Deactivate old key with same name
        for k in keys:
            if k.get("name") == key_name:
                k["is_active"] = False
        keys.append({"key_hash": key_hash, "name": key_name,
                     "created": now, "last_used": None, "is_active": True})
        users[username]["api_keys"] = keys
        _save(users)
    return {"username": username, "api_key": api_key,
            "key_name": key_name, "note": "previous key is now invalid"}


def bump_generations(username: str, n: int = 1) -> None:
    with _LOCK:
        users = _load()
        if username in users:
            users[username]["generations"] = users[username].get("generations", 0) + n
            users[username]["total_axioms_generated"] = users[username].get("total_axioms_generated", 0) + n
            _save(users)


def profile(username: str) -> dict:
    user = _load().get(username, {})
    return {
        "username": username,
        "email": user.get("email", ""),
        "display_name": user.get("display_name", username),
        "role": user.get("role", "user"),
        "permissions": (user.get("permissions", DEFAULT_USER_PERMISSIONS)
                       if user.get("role") != "admin" else ["*"]),
        "bio": user.get("bio", ""),
        "organization": user.get("organization", ""),
        "title": user.get("title", ""),
        "website": user.get("website", ""),
        "orcid_id": user.get("orcid_id", ""),
        "research_interests": user.get("research_interests", []),
        "skills": user.get("skills", []),
        "github_url": user.get("github_url", ""),
        "linkedin_url": user.get("linkedin_url", ""),
        "twitter_url": user.get("twitter_url", ""),
        "profile_visibility": user.get("profile_visibility", "public"),
        "plan_type": user.get("plan_type", "free"),
        "total_axioms_generated": user.get("total_axioms_generated", 0),
        "total_axioms_shared": user.get("total_axioms_shared", 0),
        "reputation_score": user.get("reputation_score", 0.0),
        "created": user.get("created"),
        "last_login_at": user.get("last_login_at"),
        "generations": user.get("generations", 0),
        "api_key_count": len([k for k in user.get("api_keys", []) if k.get("is_active", True)]),
    }


def update_profile(username: str, updates: dict) -> dict:
    allowed = {"display_name", "bio", "organization", "title", "website", "orcid_id",
               "research_interests", "skills", "github_url", "linkedin_url", "twitter_url",
               "profile_visibility", "theme_preference", "language", "email"}
    with _LOCK:
        users = _load()
        if username not in users:
            raise AuthError("unknown user")
        for key, val in updates.items():
            if key in allowed:
                users[username][key] = val
        users[username]["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _save(users)
    return profile(username)


def authenticate(api_key_header: str | None, basic_header: str | None,
                 session_header: str | None = None) -> str | None:
    if session_header and session_header.startswith("mf_sess_"):
        username = _verify_session_token(session_header.strip())
        if username:
            return username
    if api_key_header:
        username = verify_api_key(api_key_header.strip())
        if username:
            return username
    if basic_header and basic_header.lower().startswith("basic "):
        try:
            raw = base64.b64decode(basic_header[6:]).decode("utf-8")
            username, _, password = raw.partition(":")
        except Exception:
            return None
        if verify_password(username, password):
            return username
    return None


def check_rate_limit(username: str) -> bool:
    return rate_limiter.allow(username)


def add_notification(username: str, ntype: str, title: str, message: str,
                     data: dict | None = None, action_url: str | None = None) -> dict:
    notifs = _load_notifs()
    entry = {
        "id": f"notif_{secrets.token_hex(8)}",
        "username": username,
        "type": ntype,
        "title": title,
        "message": message,
        "data": data,
        "action_url": action_url,
        "is_read": False,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    notifs["notifications"].append(entry)
    _save_notifs(notifs)
    return entry


def get_notifications(username: str, unread_only: bool = False) -> list:
    notifs = _load_notifs()
    results = [n for n in notifs["notifications"] if n["username"] == username]
    if unread_only:
        results = [n for n in results if not n["is_read"]]
    return sorted(results, key=lambda n: n["created_at"], reverse=True)[:50]


def mark_notification_read(notif_id: str) -> bool:
    notifs = _load_notifs()
    for n in notifs["notifications"]:
        if n["id"] == notif_id:
            n["is_read"] = True
            _save_notifs(notifs)
            return True
    return False


def get_user_stats(username: str) -> dict:
    user = _load().get(username, {})
    return {
        "username": username,
        "total_axioms_generated": user.get("total_axioms_generated", 0),
        "total_axioms_shared": user.get("total_axioms_shared", 0),
        "reputation_score": user.get("reputation_score", 0.0),
        "plan_type": user.get("plan_type", "free"),
        "member_since": user.get("created"),
        "last_active": user.get("last_login_at"),
    }
