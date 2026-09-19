"""MonkeyForge DEMO-Lite v0.6.2 -- framework loader.

Implements dual-schema loader. v0.6 adds: category filtering, enhanced search,
framework stats.
"""

from __future__ import annotations
import hashlib, json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

def _derived_coordinates(name: str) -> list:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return [round(digest[i] / 255, 4) for i in range(5)]

def _normalize(name: str, body: dict, source: str) -> dict:
    fw = dict(body)
    fw["name"] = name
    fw["source"] = source
    coords = fw.get("coordinates")
    if (not isinstance(coords, list) or len(coords) != 5
            or not all(isinstance(c, (int, float)) for c in coords)):
        fw["coordinates"] = _derived_coordinates(name)
        fw["coordinates_derived"] = True
    else:
        fw["coordinates"] = [max(0.0, min(1.0, float(c))) for c in coords]
    return fw

class FrameworkLoader:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self.frameworks: dict[str, dict] = {}
        self.skipped: list[dict] = []
        self.reload()

    def reload(self) -> None:
        self.frameworks.clear()
        self.skipped.clear()
        self._load_file(self.data_dir / "frameworks.json")
        fw_dir = self.data_dir / "frameworks"
        if fw_dir.is_dir():
            for path in sorted(fw_dir.glob("*.json")):
                self._load_file(path)

    def _load_file(self, path: Path) -> None:
        if not path.exists():
            self.skipped.append({"file": path.name, "reason": "missing"})
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            self.skipped.append({"file": path.name, "reason": str(exc)})
            return
        # Schema C: top-level list of framework objects
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "name" in item:
                    self._add(str(item["name"]), item, path.name)
            return
        if not isinstance(data, dict):
            self.skipped.append({"file": path.name, "reason": "top level is not an object or list"})
            return
        if "name" in data and not any(isinstance(v, dict) for v in data.values()):
            self._add(str(data["name"]), data, path.name)
            return
        loaded_any = False
        for key, body in data.items():
            if key.startswith("_"):
                continue
            if isinstance(body, dict):
                self._add(key, body, path.name)
                loaded_any = True
        if not loaded_any:
            self._add(path.stem, data, path.name)

    def _add(self, name: str, body: dict, source: str) -> None:
        if name in self.frameworks:
            name = f"{name}::{source}"
        self.frameworks[name] = _normalize(name, body, source)

    def summary(self) -> dict:
        return {
            "loaded": len(self.frameworks),
            "skipped": self.skipped,
            "derived_coordinates": sorted(n for n, fw in self.frameworks.items() if fw.get("coordinates_derived")),
        }

    def get(self, name: str) -> dict | None:
        if name in self.frameworks:
            return self.frameworks[name]
        low = name.lower()
        for key, fw in self.frameworks.items():
            if key.lower() == low:
                return fw
        return None

    def nearest(self, coords: list, k: int = 3) -> list:
        def dist(fw):
            return sum((a - b) ** 2 for a, b in zip(fw["coordinates"], coords)) ** 0.5
        ranked = sorted(self.frameworks.values(), key=dist)
        return [{"name": fw["name"], "coordinates": fw["coordinates"],
                 "distance": round(dist(fw), 4)} for fw in ranked[:k]]

    def names(self) -> list:
        return sorted(self.frameworks)

    def by_category(self, category: str) -> list:
        low = category.lower()
        return [fw for fw in self.frameworks.values()
                if low in fw.get("category", "").lower()]

    def search(self, keyword: str) -> list:
        kw = keyword.lower()
        return [fw for name, fw in self.frameworks.items()
                if kw in name.lower() or kw in fw.get("description", "").lower()]
