"""MonkeyForge DEMO-Lite v0.6.2 -- UHAS equation explorer.

Read-only browser over data/equations.json (183 equations, 15 clusters).
v0.6 adds: pagination, category filter, improved search.
"""

from __future__ import annotations
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

class EquationExplorer:
    def __init__(self, path: Path = DATA_DIR / "equations.json"):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.equations: list[dict] = (data["equations"] if isinstance(data, dict) and "equations" in data
                                      else data if isinstance(data, list) else [])
        self._by_id = {self._norm(e.get("id", "")): e for e in self.equations}

    @staticmethod
    def _norm(eq_id: str) -> str:
        return str(eq_id).strip().upper().replace("_", "-")

    def clusters(self) -> list:
        counts: dict[str, int] = {}
        for eq in self.equations:
            c = eq.get("cluster", "Unclustered")
            counts[c] = counts.get(c, 0) + 1
        return [{"cluster": c, "count": n} for c, n in sorted(counts.items())]

    def in_cluster(self, cluster: str) -> list:
        low = cluster.strip().lower()
        return [eq for eq in self.equations if low in eq.get("cluster", "").lower()]

    def search(self, keyword: str) -> list:
        kw = keyword.strip().lower()
        if not kw:
            return []
        fields = ("id", "title", "equation", "description", "cluster")
        return [eq for eq in self.equations
                if any(kw in str(eq.get(f, "")).lower() for f in fields)]

    def show(self, eq_id: str) -> dict | None:
        return self._by_id.get(self._norm(eq_id))

    def stats(self) -> dict:
        return {"equations": len(self.equations), "clusters": len(self.clusters())}

    def paginate(self, page: int = 1, limit: int = 20, cluster: str | None = None) -> dict:
        eqs = self.equations
        if cluster:
            low = cluster.lower()
            eqs = [e for e in eqs if low in e.get("cluster", "").lower()]
        total = len(eqs)
        start = (page - 1) * limit
        return {
            "items": eqs[start:start + limit],
            "total": total, "page": page, "limit": limit,
            "pages": max(1, -(-total // limit)),
        }
