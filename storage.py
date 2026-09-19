"""MonkeyForge DEMO-Lite v0.6.2 -- file upload & storage.

Local filesystem storage with SHA-256 integrity verification.
Tracks files in data/files_index.json.

Supports: upload, download, list, delete, integrity check, visibility control,
ledger linking.

v0.6.2 adds: visibility (public/private/link_only), ledger linking.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import threading
import time
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
INDEX_PATH = DATA_DIR / "files_index.json"
_LOCK = threading.Lock()


def _load_index() -> dict:
    if not INDEX_PATH.exists():
        return {"files": []}
    with open(INDEX_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_index(data: dict) -> None:
    tmp = INDEX_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    tmp.replace(INDEX_PATH)


class FileService:
    def __init__(self, upload_dir: Path | None = None):
        from core import load_config
        cfg = load_config()
        self.upload_dir = Path(upload_dir or cfg.get("upload_dir", "uploads"))
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.max_size = cfg.get("max_upload_size_mb", 10) * 1024 * 1024

    def save(self, file_content: bytes, original_name: str, username: str,
             mime_type: str = "application/octet-stream",
             file_type: str = "supporting_evidence",
             description: str = "", is_public: bool = False, **kwargs) -> dict:
        if len(file_content) > self.max_size:
            raise ValueError(f"file too large (max {self.max_size // (1024*1024)}MB)")

        file_hash = hashlib.sha256(file_content).hexdigest()
        ext = Path(original_name).suffix or ".bin"
        stored_name = f"{file_hash[:16]}{ext}"
        rel_path = f"{username}/{stored_name}"
        abs_path = self.upload_dir / rel_path

        with _LOCK:
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_bytes(file_content)

            idx = _load_index()
            # Check for duplicate hash
            for f in idx["files"]:
                if f["file_hash"] == file_hash and f["username"] == username:
                    return {**f, "note": "file already exists"}

            entry = {
                "id": f"file_{secrets.token_hex(8)}",
                "username": username,
                "original_name": original_name,
                "stored_name": stored_name,
                "storage_path": rel_path,
                "mime_type": mime_type,
                "file_size": len(file_content),
                "file_hash": file_hash,
                "file_type": file_type,
                "description": description,
                "is_public": is_public,
                "visibility": kwargs.get("visibility", "public" if is_public else "private"),
                "linked_ledger": [],
                "download_count": 0,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            idx["files"].append(entry)
            _save_index(idx)
            return entry

    def get(self, file_id: str) -> dict | None:
        idx = _load_index()
        for f in idx["files"]:
            if f["id"] == file_id:
                return f
        return None

    def read(self, file_id: str) -> tuple[bytes, dict] | None:
        meta = self.get(file_id)
        if not meta:
            return None
        abs_path = self.upload_dir / meta["storage_path"]
        if not abs_path.exists():
            return None
        content = abs_path.read_bytes()
        # Verify integrity
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != meta["file_hash"]:
            return None
        # Increment download count
        with _LOCK:
            idx = _load_index()
            for f in idx["files"]:
                if f["id"] == file_id:
                    f["download_count"] = f.get("download_count", 0) + 1
                    break
            _save_index(idx)
        return content, meta

    def list_by_user(self, username: str) -> list:
        idx = _load_index()
        return [f for f in idx["files"] if f["username"] == username]

    def list_public(self) -> list:
        idx = _load_index()
        return [f for f in idx["files"] if f.get("visibility") in ("public", "link_only")]

    def update_visibility(self, file_id: str, username: str, visibility: str) -> dict | None:
        with _LOCK:
            idx = _load_index()
            for f in idx["files"]:
                if f["id"] == file_id and f["username"] == username:
                    f["visibility"] = visibility
                    f["is_public"] = visibility in ("public", "link_only")
                    _save_index(idx)
                    return f
        return None

    def link_to_ledger(self, file_id: str, username: str, ledger_hash: str) -> dict | None:
        with _LOCK:
            idx = _load_index()
            for f in idx["files"]:
                if f["id"] == file_id and f["username"] == username:
                    linked = f.get("linked_ledger", [])
                    if ledger_hash not in linked:
                        linked.append(ledger_hash)
                    f["linked_ledger"] = linked
                    _save_index(idx)
                    return f
        return None

    def get_files_for_ledger(self, ledger_hash: str) -> list:
        idx = _load_index()
        return [f for f in idx["files"] if ledger_hash in f.get("linked_ledger", [])]

    def delete(self, file_id: str, username: str) -> bool:
        with _LOCK:
            idx = _load_index()
            before = len(idx["files"])
            idx["files"] = [f for f in idx["files"]
                            if not (f["id"] == file_id and f["username"] == username)]
            if len(idx["files"]) < before:
                _save_index(idx)
                return True
        return False

    def verify_integrity(self) -> list[dict]:
        idx = _load_index()
        issues = []
        for f in idx["files"]:
            abs_path = self.upload_dir / f["storage_path"]
            if not abs_path.exists():
                issues.append({"file_id": f["id"], "issue": "file missing"})
                continue
            content = abs_path.read_bytes()
            actual = hashlib.sha256(content).hexdigest()
            if actual != f["file_hash"]:
                issues.append({"file_id": f["id"], "issue": "hash mismatch"})
        return issues
