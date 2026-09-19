"""MonkeyForge DEMO-Lite v0.6.2 -- core engine.

Slim rewrite of the Meta-AxiomForge generator. Stdlib only for computation.
v0.6.2 adds: external axiom store injection, seed presets, enhanced axiom naming.

Epistemic note: novelty / coherence / alienness / elegance / sophia_score are
heuristic creative scores, not calibrated measurements.
"""

from __future__ import annotations
import hashlib, json, math, random, re, time, os
from pathlib import Path
from typing import Optional

DIMS = ("participation", "plasticity", "substrate", "temporal", "generative")
PHI = (1 + 5 ** 0.5) / 2
INV_PHI = 1 / PHI
DATA_DIR = Path(__file__).parent / "data"

def load_config() -> dict:
    with open(DATA_DIR / "config.json", encoding="utf-8") as f:
        return json.load(f)

def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, float(v)))

class Coordinates:
    """A point in the 5D ontology phase space. All dims clamped to [0, 1]."""
    def __init__(self, values):
        vals = list(values)
        if len(vals) != 5:
            raise ValueError(f"Coordinates require exactly 5 values ({', '.join(DIMS)}); got {len(vals)}")
        self.values = [clamp(v) for v in vals]

    @classmethod
    def random(cls, rng: random.Random) -> "Coordinates":
        return cls([rng.random() for _ in range(5)])

    def as_dict(self) -> dict:
        return dict(zip(DIMS, [round(v, 4) for v in self.values]))

    def distance(self, other: "Coordinates") -> float:
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(self.values, other.values)))

    def __iter__(self):
        return iter(self.values)

class FieldSimulator:
    """Conformal factor Omega(x) = -k * |x - attractor|^2 on flat 5-space."""
    N = 5

    def __init__(self, attractor=None, k: float | None = None):
        cfg = load_config()
        self.k = float(k if k is not None else cfg.get("curvature_k", 0.8))
        if attractor is not None:
            self.attractor = [clamp(v) for v in attractor]
        else:
            self.attractor = self._default_attractor()

    @staticmethod
    def _default_attractor():
        try:
            from frameworks import FrameworkLoader
            fws = FrameworkLoader().frameworks
            coords = [fw["coordinates"] for fw in fws.values()
                      if isinstance(fw.get("coordinates"), list) and len(fw["coordinates"]) == 5]
            if coords:
                return [sum(c[i] for c in coords) / len(coords) for i in range(5)]
        except Exception:
            pass
        return [0.5] * 5

    def _omega(self, x) -> float:
        r2 = sum((xi - ai) ** 2 for xi, ai in zip(x, self.attractor))
        return -self.k * r2

    def _grad_omega(self, x):
        return [-2 * self.k * (xi - ai) for xi, ai in zip(x, self.attractor)]

    def ricci_scalar(self, coords) -> float:
        x = list(coords)
        n = self.N
        omega = self._omega(x)
        grad = self._grad_omega(x)
        lap = -2 * self.k * n
        g2 = sum(g * g for g in grad)
        return -2 * (n - 1) * math.exp(-2 * omega) * (lap + (n - 2) / 2 * g2)

    def curvature(self, coords) -> dict:
        x = [clamp(v) for v in coords]
        grad = self._grad_omega(x)
        return {
            "coordinates": Coordinates(x).as_dict(),
            "conformal_factor": round(self._omega(x), 6),
            "ricci_scalar": round(self.ricci_scalar(x), 6),
            "gradient_norm": round(math.sqrt(sum(g * g for g in grad)), 6),
            "attractor": [round(a, 4) for a in self.attractor],
        }

    def gradient_flow(self, coords, steps: int = 24, lr: float = 0.05) -> list:
        x = [clamp(v) for v in coords]
        path = [list(x)]
        h = 1e-4
        for _ in range(steps):
            grad = []
            for i in range(self.N):
                xp, xm = list(x), list(x)
                xp[i] += h
                xm[i] -= h
                grad.append((self.ricci_scalar(xp) - self.ricci_scalar(xm)) / (2 * h))
            norm = math.sqrt(sum(g * g for g in grad)) or 1.0
            x = [clamp(xi - lr * gi / norm) for xi, gi in zip(x, grad)]
            path.append([round(v, 5) for v in x])
        return path

    def geodesic(self, start, end, steps: int = 24) -> list:
        a = [clamp(v) for v in start]
        b = [clamp(v) for v in end]
        path = []
        for s in range(steps + 1):
            t = s / steps
            base = [ai + t * (bi - ai) for ai, bi in zip(a, b)]
            grad = self._grad_omega(base)
            bend = t * (1 - t)
            pt = [clamp(bi + 0.25 * bend * gi) for bi, gi in zip(base, grad)]
            path.append([round(v, 5) for v in pt])
        return path


def _flatten_bank(bank) -> list:
    out = []
    if isinstance(bank, dict):
        for v in bank.values():
            out.extend(_flatten_bank(v))
    elif isinstance(bank, list):
        for v in bank:
            out.extend(_flatten_bank(v))
    elif isinstance(bank, str):
        out.append(bank.lower())
    return out


class SeedProcessor:
    _PARADOX_HINTS = {"paradox", "contradiction", "impossible", "infinite",
                      "recursive", "self", "loop", "godel", "gödel",
                      "undecidable", "mirror", "void"}

    def __init__(self):
        with open(DATA_DIR / "corpus.json", encoding="utf-8") as f:
            corpus = json.load(f)
        self.nouns = set(_flatten_bank(corpus.get("nouns", {})))
        self.verbs = set(_flatten_bank(corpus.get("verbs", {})))
        self.concepts = set(_flatten_bank(corpus.get("concepts", {})))
        self.paradox = (set(_flatten_bank(corpus.get("paradox", {}))) | self._PARADOX_HINTS)
        self.corpus = corpus

    @staticmethod
    def _tokens(text: str) -> list:
        return re.findall(r"[a-zA-Z][a-zA-Z'-]+", text.lower())

    def analyze(self, seed: str) -> dict:
        toks = self._tokens(seed)
        if not toks:
            return {"error": "empty seed"}
        tokset = set(toks)
        abstract = tokset & self.concepts
        action = tokset & self.verbs
        noun_hits = tokset & self.nouns
        paradox = {t for t in tokset if t in self.paradox or any(p in t for p in ("paradox", "recurs", "self"))}
        n = len(toks)
        complexity = round(len(tokset) / n, 4)
        density = round((len(abstract) + len(noun_hits)) / n, 4)
        coherence = round(clamp(0.25 + 0.75 * (len(abstract | action | noun_hits) / max(4, n)) * (0.5 + 0.5 * complexity)), 4)
        coords = Coordinates([
            clamp(0.30 + 0.10 * len(action) + 0.05 * n / 12),
            clamp(0.25 + 0.15 * len(paradox) + 0.30 * complexity),
            clamp(0.20 + 0.12 * len(noun_hits)),
            clamp(0.30 + 0.08 * sum(t in ("time", "temporal", "history", "future", "past", "now", "moment", "clock") for t in toks) + 0.2 * density),
            clamp(0.25 + 0.12 * len(abstract) + 0.25 * coherence),
        ])
        key_concepts = sorted(abstract | noun_hits)[:8] or sorted(tokset)[:5]
        return {
            "seed": seed, "token_count": n, "abstract_count": len(abstract),
            "action_count": len(action), "paradox_count": len(paradox),
            "complexity": complexity, "semantic_density": density,
            "coherence_score": coherence, "key_concepts": key_concepts,
            "target_coordinates": coords.as_dict(),
            "note": "heuristic creative-steering scores; not calibrated measurements",
        }


class Sophia:
    def __init__(self, threshold: float | None = None):
        cfg = load_config()
        self.threshold = float(threshold if threshold is not None else cfg.get("sophia_threshold", INV_PHI))

    def score(self, coherence, paradox_intensity, innovation, hybridization, ricci) -> float:
        curvature_term = math.tanh(abs(ricci) / 50.0)
        s = (0.30 * coherence + 0.20 * paradox_intensity + 0.25 * innovation
             + 0.15 * hybridization + 0.10 * curvature_term)
        return round(clamp(s), 4)

    def crossed(self, score: float) -> bool:
        return score >= self.threshold


_OPERATORS = {
    "CREATES": ["{x} creates {y}", "{x} gives rise to {y}", "{x} generates {y}", "from {x}, {y} condenses"],
    "ENTAILS": ["{x} entails {y}", "given {x}, then {y}", "{x} necessitates {y}"],
    "VIA": ["via {x}", "through {x}", "by way of {x}", "mediated by {x}"],
    "ENCODED_AS": ["encoded as {x}", "formalized as {x}", "written into the manifold as {x}"],
}

def _jaccard(a: str, b: str) -> float:
    sa, sb = set(a.lower().split()), set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# ── Axiom Store (JSON-backed, thread-safe) ──────────────────────────────────

class AxiomStore:
    """JSON-backed axiom persistence with versioning, batches, and search."""

    def __init__(self, path: Path = DATA_DIR / "axioms.json"):
        self._path = path
        self._lock = __import__("threading").Lock()
        self._cache = self._load()

    def _load(self) -> dict:
        if not self._path.exists():
            return {"axioms": [], "next_id": 1}
        with open(self._path, encoding="utf-8") as f:
            return json.load(f)

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, indent=1, ensure_ascii=False)
        tmp.replace(self._path)

    def create(self, axiom_data: dict, username: str, batch_id: str | None = None) -> dict:
        with self._lock:
            axioms = self._cache["axioms"]
            aid = f"AXM-{self._cache['next_id']:05d}"
            self._cache["next_id"] += 1
            entry = {
                "id": aid,
                "user": username,
                "batch_id": batch_id,
                "status": "draft",
                "visibility": "private",
                "license": load_config().get("default_axiom_license", "CC-BY-4.0"),
                "tags": [],
                "keywords": [],
                "category": axiom_data.get("category", "custom"),
                "view_count": 0,
                "download_count": 0,
                "citation_count": 0,
                "version": 1,
                "versions": [],
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                **axiom_data,
            }
            axioms.append(entry)
            self._save()
            return entry

    def get(self, axiom_id: str) -> dict | None:
        for a in self._cache["axioms"]:
            if a["id"] == axiom_id:
                return a
        return None

    def update(self, axiom_id: str, updates: dict) -> dict | None:
        with self._lock:
            for a in self._cache["axioms"]:
                if a["id"] == axiom_id:
                    # Save version history
                    snapshot = {k: v for k, v in a.items() if k != "versions"}
                    a.setdefault("versions", []).append(snapshot)
                    a["version"] = len(a["versions"]) + 1
                    a.update(updates)
                    a["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    self._save()
                    return a
        return None

    def delete(self, axiom_id: str, username: str) -> bool:
        with self._lock:
            before = len(self._cache["axioms"])
            self._cache["axioms"] = [a for a in self._cache["axioms"]
                                      if not (a["id"] == axiom_id and a["user"] == username)]
            if len(self._cache["axioms"]) < before:
                self._save()
                return True
        return False

    def list_by_user(self, username: str, status: str | None = None,
                     visibility: str | None = None, category: str | None = None,
                     page: int = 1, limit: int = 20) -> dict:
        axioms = self._cache["axioms"]
        if username:
            axioms = [a for a in axioms if a["user"] == username]
        if status:
            axioms = [a for a in axioms if a.get("status") == status]
        if visibility:
            axioms = [a for a in axioms if a.get("visibility") == visibility]
        if category:
            axioms = [a for a in axioms if a.get("category") == category]
        # search within list
        total = len(axioms)
        start = (page - 1) * limit
        page_items = axioms[start:start + limit]
        return {"items": page_items, "total": total, "page": page,
                "limit": limit, "pages": max(1, -(-total // limit))}

    def list_public(self, page: int = 1, limit: int = 20,
                    category: str | None = None, search: str | None = None,
                    sort_by: str = "created_at", sort_order: str = "desc") -> dict:
        axioms = [a for a in self._cache["axioms"] if a.get("visibility") == "public"]
        if category:
            axioms = [a for a in axioms if a.get("category") == category]
        if search:
            kw = search.lower()
            axioms = [a for a in axioms
                      if kw in a.get("axiom", "").lower()
                      or kw in a.get("name", "").lower()
                      or kw in str(a.get("description", "")).lower()
                      or any(kw in t.lower() for t in a.get("tags", []))
                      or any(kw in k.lower() for k in a.get("keywords", []))]
        reverse = sort_order == "desc"
        axioms.sort(key=lambda a: a.get(sort_by, ""), reverse=reverse)
        total = len(axioms)
        start = (page - 1) * limit
        return {"items": axioms[start:start + limit], "total": total,
                "page": page, "limit": limit, "pages": max(1, -(-total // limit))}

    def increment_view(self, axiom_id: str) -> None:
        with self._lock:
            for a in self._cache["axioms"]:
                if a["id"] == axiom_id:
                    a["view_count"] = a.get("view_count", 0) + 1
                    self._save()
                    return

    def stats(self, username: str | None = None) -> dict:
        axioms = self._cache["axioms"]
        if username:
            axioms = [a for a in axioms if a["user"] == username]
        return {
            "total": len(axioms),
            "draft": len([a for a in axioms if a.get("status") == "draft"]),
            "published": len([a for a in axioms if a.get("status") == "published"]),
            "public": len([a for a in axioms if a.get("visibility") == "public"]),
            "shared": len([a for a in axioms if a.get("visibility") == "shared"]),
        }


class MetaEngine:
    """Generation loop: coordinates -> framework -> axiom -> diversity check -> score -> history -> persist."""

    def __init__(self, numeric_seed: int | None = None,
                 axiom_store: AxiomStore | None = None):
        from frameworks import FrameworkLoader
        from explorer import EquationExplorer
        self.cfg = load_config()
        self.rng = random.Random(numeric_seed)
        self.loader = FrameworkLoader()
        self.explorer = EquationExplorer()
        self.seedproc = SeedProcessor()
        self.sim = FieldSimulator()
        self.sophia = Sophia()
        self.axiom_store = axiom_store or AxiomStore()
        self.history: list[str] = []
        self.stats = {"generated": 0, "sophia_points": 0, "hybrids": 0, "diversity_retries": 0}

    def _pick_framework(self, coords: Coordinates):
        near = self.loader.nearest(list(coords), k=3)
        name = self.rng.choice(near)["name"] if near else None
        return name, (self.loader.frameworks.get(name, {}) if name else {})

    def _hybridize(self, coords: Coordinates):
        parents = self.loader.nearest(list(coords), k=6)
        if len(parents) < 2:
            return None
        pair = self.rng.sample(parents, 2)
        mix = Coordinates([(a + b) / 2 for a, b in zip(pair[0]["coordinates"], pair[1]["coordinates"])])
        mechs = []
        for p in pair:
            mechs += self.loader.frameworks[p["name"]].get("mechanisms", [])[:3]
        return {
            "name": f"HYBRID::{pair[0]['name']}::{pair[1]['name']}",
            "parents": [p["name"] for p in pair],
            "coordinates": list(mix), "mechanisms": mechs,
        }

    def _phrase(self, op: str, **kw) -> str:
        return self.rng.choice(_OPERATORS[op]).format(**kw)

    def _vocab(self, kind: str) -> str:
        bank = _flatten_bank(self.seedproc.corpus.get(kind, {}))
        return self.rng.choice(bank) if bank else kind

    @staticmethod
    def _clean_mechanism(text: str) -> str:
        t = re.sub(r"\\\(.*?\\\)|\$[^$]*\$", "", text)
        t = re.sub(r"[*_`#>]+|^\s*-\s*", "", t.strip())
        t = re.sub(r"\s+", " ", t).strip(" :;,-")
        if len(t) > 90:
            t = t[:90].rsplit(" ", 1)[0] + "..."
        return t or "an unnamed mechanism"

    def generate(self, seed: str | None = None, count: int = 1,
                 force_phase_transition: bool = False,
                 use_relativity: bool = True,
                 username: str | None = None,
                 persist: bool = True) -> dict:
        max_count = self.cfg.get("max_axioms_per_batch", 24)
        count = max(1, min(count, max_count))
        batch_id = f"BAT-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}" if count > 1 else None
        axioms = [self._one(seed, force_phase_transition, use_relativity, username, batch_id, persist)
                  for _ in range(count)]
        result = {"axioms": axioms, "stats": dict(self.stats), "engine": "MetaEngine/DEMO-Lite v0.6"}
        if batch_id:
            result["batch_id"] = batch_id
        return result

    def _one(self, seed, force_pt, use_rel, username, batch_id, persist) -> dict:
        analysis = self.seedproc.analyze(seed) if seed else None
        coords = (Coordinates(analysis["target_coordinates"].values())
                  if analysis else Coordinates.random(self.rng))

        hybrid = None
        if force_pt or self.rng.random() < self.cfg.get("hybrid_chance", 0.3):
            hybrid = self._hybridize(coords)
        if hybrid:
            self.stats["hybrids"] += 1
            fw_name, fw = hybrid["name"], hybrid
            coords = Coordinates(hybrid["coordinates"])
        else:
            fw_name, fw = self._pick_framework(coords)

        ricci = self.sim.ricci_scalar(list(coords)) if use_rel else 0.0

        diversity_threshold = self.cfg.get("diversity_threshold", 0.72)
        text, mech, eq = "", "", {}
        for attempt in range(4):
            x = self._vocab("concepts")
            y = self._vocab("nouns")
            mechs = fw.get("mechanisms") or [self._vocab("verbs")]
            mech = self._clean_mechanism(str(self.rng.choice(mechs)))
            eq = self.rng.choice(self.explorer.equations)
            text = (f"{self._phrase('CREATES', x=x, y=y).capitalize()} "
                    f"{self._phrase('VIA', x=mech.lower())}, "
                    f"{self._phrase('ENCODED_AS', x=eq['equation'])}.")
            worst = max((_jaccard(text, h) for h in self.history), default=0)
            if worst < diversity_threshold:
                break
            self.stats["diversity_retries"] += 1

        novelty = round(1 - max((_jaccard(text, h) for h in self.history), default=0), 4)
        coherence = (analysis["coherence_score"] if analysis
                     else round(self.rng.uniform(0.35, 0.8), 4))
        paradox_i = (min(1.0, analysis["paradox_count"] / 3) if analysis
                     else round(self.rng.random() * 0.6, 4))
        center_d = coords.distance(Coordinates([0.5] * 5))
        alienness = round(clamp(center_d / math.sqrt(1.25)), 4)
        elegance = round(clamp(1 - abs(len(text) - 160) / 400), 4)

        s = self.sophia.score(coherence, paradox_i, novelty, 1.0 if hybrid else 0.0, ricci)
        is_sophia = force_pt or self.sophia.crossed(s)
        if is_sophia:
            self.stats["sophia_points"] += 1

        self.history.append(text)
        self.history[:] = self.history[-self.cfg.get("history_window", 20):]
        self.stats["generated"] += 1

        axiom_data = {
            "axiom": text,
            "name": f"Axiom {self.stats['generated']}",
            "framework": fw_name,
            "hybrid_parents": hybrid["parents"] if hybrid else None,
            "equation_ref": {"id": eq.get("id"), "title": eq.get("title")},
            "mechanism": mech,
            "coordinates": coords.as_dict(),
            "metrics": {
                "novelty": novelty, "coherence": coherence,
                "paradox_intensity": paradox_i, "alienness": alienness,
                "elegance": elegance, "ricci_scalar": round(ricci, 4),
                "sophia_score": s,
            },
            "sophia_point": is_sophia,
            "phase_transition_forced": bool(force_pt),
            "seed_analysis": analysis,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        # Persist to axiom store
        stored = None
        if persist and username:
            stored = self.axiom_store.create(axiom_data, username, batch_id)
            axiom_data["id"] = stored["id"]
            axiom_data["status"] = stored["status"]
        else:
            axiom_data["id"] = hashlib.sha256(f"{text}{time.time_ns()}".encode()).hexdigest()[:12]

        return axiom_data
