"""MonkeyForge DEMO-Lite v0.6.2 -- shared axiom ledger.

Blockchain-like hash chain for shared axioms. JSON-backed (data/ledger.json).
Each shared axiom gets a ledger entry with:
  - ledger_hash: SHA-256 of (content_hash + previous_hash + timestamp + nonce)
  - previous_hash: the ledger_hash of the previous entry (or null for genesis)
  - content_hash: SHA-256 of the axiom content

Provides: share, feed, verify integrity, like/unlike, feature, search.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
LEDGER_PATH = DATA_DIR / "ledger.json"
_LOCK = threading.Lock()


def _load() -> dict:
    if not LEDGER_PATH.exists():
        return {"entries": [], "chain_head": None, "chain_name": "MonkeyForge-Ledger"}
    with open(LEDGER_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    tmp = LEDGER_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    tmp.replace(LEDGER_PATH)


def _content_hash(axiom_data: dict) -> str:
    content = json.dumps({
        "id": axiom_data.get("id"),
        "axiom": axiom_data.get("axiom", ""),
        "name": axiom_data.get("name", ""),
        "metrics": axiom_data.get("metrics", {}),
    }, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def _ledger_hash(content_hash: str, previous_hash: str | None, timestamp: str, nonce: str) -> str:
    raw = f"{content_hash}|{previous_hash or 'GENESIS'}|{timestamp}|{nonce}"
    return hashlib.sha256(raw.encode()).hexdigest()


class LedgerService:
    def __init__(self):
        self.data = _load()

    def _refresh(self) -> None:
        self.data = _load()

    def share(self, axiom_data: dict, username: str, license: str | None = None) -> dict:
        with _LOCK:
            self._refresh()
            ch = _content_hash(axiom_data)
            prev = self.data.get("chain_head")
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            nonce = secrets.token_hex(16)
            lh = _ledger_hash(ch, prev, ts, nonce)
            entry = {
                "ledger_hash": lh,
                "previous_hash": prev,
                "content_hash": ch,
                "axiom_id": axiom_data.get("id"),
                "axiom_data": {
                    "id": axiom_data.get("id"),
                    "name": axiom_data.get("name", ""),
                    "axiom": axiom_data.get("axiom", ""),
                    "framework": axiom_data.get("framework"),
                    "equation_ref": axiom_data.get("equation_ref"),
                    "mechanism": axiom_data.get("mechanism"),
                    "coordinates": axiom_data.get("coordinates"),
                    "metrics": axiom_data.get("metrics", {}),
                    "sophia_point": axiom_data.get("sophia_point"),
                    "category": axiom_data.get("category", "custom"),
                    "tags": axiom_data.get("tags", []),
                },
                "shared_by": username,
                "license": license or "CC-BY-4.0",
                "attribution": username,
                "nonce": nonce,
                "likes": 0,
                "dislikes": 0,
                "bookmark_count": 0,
                "is_featured": False,
                "is_verified": False,
                "attached_files": [],
                "created_at": ts,
            }
            self.data["entries"].append(entry)
            self.data["chain_head"] = lh
            _save(self.data)
            return entry

    def feed(self, page: int = 1, limit: int = 20, category: str | None = None,
             search: str | None = None, sort_by: str = "date") -> dict:
        self._refresh()
        entries = list(reversed(self.data["entries"]))
        if category:
            entries = [e for e in entries if e["axiom_data"].get("category") == category]
        if search:
            kw = search.lower()
            entries = [e for e in entries
                       if kw in e["axiom_data"].get("axiom", "").lower()
                       or kw in e["axiom_data"].get("name", "").lower()
                       or kw in e.get("attribution", "").lower()
                       or any(kw in t.lower() for t in e["axiom_data"].get("tags", []))]
        if sort_by == "popularity":
            entries.sort(key=lambda e: e.get("likes", 0), reverse=True)
        elif sort_by == "verified":
            entries.sort(key=lambda e: (e.get("is_verified", False), e.get("likes", 0)), reverse=True)
        total = len(entries)
        start = (page - 1) * limit
        return {"items": entries[start:start + limit], "total": total,
                "page": page, "limit": limit, "pages": max(1, -(-total // limit))}

    def verify_integrity(self) -> dict:
        self._refresh()
        entries = self.data["entries"]
        broken = []
        verified = 0
        for i, entry in enumerate(entries):
            # Verify content hash
            expected_ch = _content_hash(entry["axiom_data"])
            if entry["content_hash"] != expected_ch:
                broken.append({"index": i, "ledger_hash": entry["ledger_hash"],
                               "issue": "content hash mismatch"})
                continue
            # Verify ledger hash
            expected_lh = _ledger_hash(
                entry["content_hash"], entry["previous_hash"],
                entry["created_at"], entry["nonce"])
            if entry["ledger_hash"] != expected_lh:
                broken.append({"index": i, "ledger_hash": entry["ledger_hash"],
                               "issue": "ledger hash mismatch"})
                continue
            # Verify chain linkage
            if i > 0 and entry["previous_hash"] != entries[i - 1]["ledger_hash"]:
                broken.append({"index": i, "ledger_hash": entry["ledger_hash"],
                               "issue": "chain link broken"})
                continue
            verified += 1
        return {"is_valid": len(broken) == 0, "total_entries": len(entries),
                "verified_entries": verified, "broken_chains": broken}

    def toggle_like(self, ledger_hash: str, delta: int = 1) -> dict | None:
        with _LOCK:
            self._refresh()
            for entry in self.data["entries"]:
                if entry["ledger_hash"] == ledger_hash:
                    entry["likes"] = max(0, entry.get("likes", 0) + delta)
                    _save(self.data)
                    return entry
        return None

    def get_featured(self, limit: int = 5) -> list:
        self._refresh()
        entries = [e for e in self.data["entries"]
                    if e.get("is_featured") or e.get("is_verified")]
        entries.sort(key=lambda e: e.get("likes", 0), reverse=True)
        return entries[:limit]

    def stats(self) -> dict:
        self._refresh()
        entries = self.data["entries"]
        return {
            "total_shared": len(entries),
            "total_likes": sum(e.get("likes", 0) for e in entries),
            "featured_count": len([e for e in entries if e.get("is_featured")]),
            "verified_count": len([e for e in entries if e.get("is_verified")]),
            "chain_head": self.data.get("chain_head"),
        }

    def attach_file(self, ledger_hash: str, file_id: str, meta: dict | None = None) -> bool:
        """Attach a file reference to a ledger entry."""
        with _LOCK:
            self._refresh()
            for entry in self.data["entries"]:
                if entry["ledger_hash"] == ledger_hash:
                    files = entry.setdefault("attached_files", [])
                    if file_id not in files:
                        files.append({"file_id": file_id, "name": meta.get("original_name", "unknown") if meta else "unknown"})
                    _save(self.data)
                    return True
        return False
