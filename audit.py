"""MonkeyForge DEMO-Lite v0.6.2 -- audit logging.

JSON-backed audit trail (data/audit_log.json).
Records: create, update, delete, share, download, view, export, login, register, rotate_key.
v0.6: no changes — stable.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
AUDIT_PATH = DATA_DIR / "audit_log.json"
_LOCK = threading.Lock()


def _load() -> dict:
    if not AUDIT_PATH.exists():
        return {"entries": []}
    with open(AUDIT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    tmp = AUDIT_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    tmp.replace(AUDIT_PATH)


class AuditLog:
    @staticmethod
    def record(username: str | None, action: str, resource_type: str,
               resource_id: str | None = None, metadata: dict | None = None,
               ip_address: str | None = None, user_agent: str | None = None) -> dict:
        from core import load_config
        cfg = load_config()
        if not cfg.get("audit_enabled", True):
            return {"skipped": True}
        entry = {
            "id": f"aud_{int(time.time()*1000)}_{hash(username or 'anon') % 10000}",
            "username": username,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "metadata": metadata,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with _LOCK:
            data = _load()
            data["entries"].append(entry)
            # Keep last 10000 entries
            if len(data["entries"]) > 10000:
                data["entries"] = data["entries"][-10000:]
            _save(data)
        return entry

    @staticmethod
    def query(username: str | None = None, action: str | None = None,
              resource_type: str | None = None, limit: int = 100) -> list:
        data = _load()
        entries = data["entries"]
        if username:
            entries = [e for e in entries if e["username"] == username]
        if action:
            entries = [e for e in entries if e["action"] == action]
        if resource_type:
            entries = [e for e in entries if e["resource_type"] == resource_type]
        return list(reversed(entries[-limit:]))

    @staticmethod
    def stats() -> dict:
        data = _load()
        entries = data["entries"]
        actions = {}
        for e in entries:
            a = e["action"]
            actions[a] = actions.get(a, 0) + 1
        return {"total_entries": len(entries), "actions": actions}
