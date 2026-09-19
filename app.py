"""MonkeyForge DEMO-Lite v0.6.2 -- HTTP API + dashboard server.

Run:    python cli.py serve            (or: uvicorn app:app --port 8480)
Docs:   http://localhost:8480/docs     (auto-generated OpenAPI)
UI:     http://localhost:8480/

Public endpoints:   health, clusters, equations, search, frameworks, register, login
Protected (X-API-Key / Basic / session token): generate, analyze, simulate,
geodesic, ricci, me, rotate-key, axioms CRUD, ledger, files, analysis, profiles,
notifications, audit, batches, export, file preview, file visibility, export-all.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import auth
import audit as audit_mod
from core import (Coordinates, FieldSimulator, MetaEngine, SeedProcessor,
                  load_config, AxiomStore)
from explorer import EquationExplorer
from frameworks import FrameworkLoader
from ledger import LedgerService
from storage import FileService
from analysis import analyze as run_analysis

BASE = Path(__file__).parent
OUTPUT_DIR = BASE / load_config().get("output_dir", "output")
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="MonkeyForge DEMO-Lite API",
    version="0.6.3",
    description=("Public API for the MonkeyForge symbolic ontology engine v0.6.3. "
                 "Explorer endpoints are open; generation endpoints need an "
                 "API key, session token, or Basic auth. v0.6.3 adds RBAC: "
                 "roles (user/moderator/admin) and stored permissions. "
                 "All generator scores are heuristic creative metrics."),
)

# CORS middleware — allows dev-server or cross-origin access
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8480", "http://127.0.0.1:8480"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# module singletons
explorer = EquationExplorer()
loader = FrameworkLoader()
seedproc = SeedProcessor()
axiom_store = AxiomStore()
ledger_svc = LedgerService()
file_svc = FileService()


# -- auth dependency -----------------------------------------------------------

def current_user(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None),
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
) -> str:
    username = auth.authenticate(x_api_key, authorization, x_session_token)
    if not username:
        raise HTTPException(
            status_code=401,
            detail="provide X-API-Key header, X-Session-Token, or HTTP Basic credentials",
            headers={"WWW-Authenticate": "Basic realm=monkeyforge"},
        )
    if not auth.check_rate_limit(username):
        raise HTTPException(429, "rate limit exceeded")
    return username


# -- RBAC dependencies --------------------------------------------------------
# Usage:
#   @app.get("/api/users", dependencies=[Depends(require_role("admin"))])
#   def list_users(...): ...
#
# Or to also keep the authenticated user object:
#   def handler(user: str = Depends(require_permission("axioms:write"))):
#       ...

def require_role(required_role: str):
    """FastAPI dependency factory. Grants access if the current user's role
    matches OR the user is an admin (admins implicitly satisfy every role)."""
    role_rank = {"user": 0, "moderator": 1, "admin": 2}

    def dep(user: str = Depends(current_user)) -> str:
        user_role = auth.get_role(user)
        if role_rank.get(user_role, 0) < role_rank.get(required_role, 0):
            raise HTTPException(
                403,
                f"this endpoint requires role={required_role!r} (your role: {user_role!r})",
            )
        return user
    return dep


def require_permission(perm: str):
    """FastAPI dependency factory. Grants access if the user has `perm` or the
    wildcard '*'."""
    def dep(user: str = Depends(current_user)) -> str:
        if not auth.has_permission(user, perm):
            raise HTTPException(
                403,
                f"missing permission: {perm!r}",
            )
        return user
    return dep


# -- request models ------------------------------------------------------------

class RegisterBody(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    email: Optional[str] = Field(default=None, max_length=254)

class LoginBody(BaseModel):
    username: str
    password: str

class GenerateBody(BaseModel):
    seed: Optional[str] = Field(default=None, max_length=500)
    count: int = Field(default=1, ge=1, le=24)
    force_phase_transition: bool = False
    use_relativity: bool = True

class AnalyzeBody(BaseModel):
    seed: str = Field(min_length=1, max_length=500)

class AnalyzeAxiomBody(BaseModel):
    axiom_id: str
    mode: str = Field(default="basic", pattern="^(basic|deepseek)$")

class CoordsBody(BaseModel):
    coordinates: list[float] = Field(min_length=5, max_length=5)

class GeodesicBody(BaseModel):
    start: list[float] = Field(min_length=5, max_length=5)
    end: list[float] = Field(min_length=5, max_length=5)
    steps: int = Field(default=24, ge=2, le=200)

class UpdateProfileBody(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    bio: Optional[str] = None
    organization: Optional[str] = None
    title: Optional[str] = None
    website: Optional[str] = None
    orcid_id: Optional[str] = None
    research_interests: Optional[list[str]] = None
    skills: Optional[list[str]] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None
    profile_visibility: Optional[str] = None
    theme_preference: Optional[str] = None

class ShareToLedgerBody(BaseModel):
    axiom_id: str
    license: Optional[str] = None

class UpdateAxiomBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    visibility: Optional[str] = None
    tags: Optional[list[str]] = None
    keywords: Optional[list[str]] = None
    license: Optional[str] = None


# =============================== PUBLIC =======================================

@app.get("/api/health", tags=["public"])
def health():
    return {"status": "ok", "app": "MonkeyForge DEMO-Lite", "version": "0.6.3",
            "equations": explorer.stats(), "frameworks": len(loader.frameworks),
            "ledger": ledger_svc.stats(),
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

@app.get("/api/clusters", tags=["public"])
def clusters():
    return {"clusters": explorer.clusters()}

@app.get("/api/equations", tags=["public"])
def equations(cluster: str = Query(min_length=1)):
    found = explorer.in_cluster(cluster)
    if not found:
        raise HTTPException(404, f"no equations in cluster matching {cluster!r}")
    return {"cluster": cluster, "count": len(found), "equations": found}

@app.get("/api/search", tags=["public"])
def search(q: str = Query(min_length=1, max_length=120)):
    return {"query": q, "results": explorer.search(q)}

@app.get("/api/equation/{eq_id}", tags=["public"])
def equation(eq_id: str):
    eq = explorer.show(eq_id)
    if not eq:
        raise HTTPException(404, f"no equation with id {eq_id!r}")
    return eq

@app.get("/api/frameworks", tags=["public"])
def frameworks():
    return {"count": len(loader.frameworks), "names": loader.names(),
            "loader": loader.summary()}

@app.get("/api/framework/{name}", tags=["public"])
def framework(name: str):
    fw = loader.get(name)
    if not fw:
        raise HTTPException(404, f"no framework named {name!r}")
    return fw

@app.post("/api/register", tags=["public"], status_code=201)
def register(body: RegisterBody):
    try:
        result = auth.register(body.username, body.password, body.email)
        audit_mod.AuditLog.record(body.username, "register", "user")
        return result
    except auth.AuthError as exc:
        raise HTTPException(400, str(exc))

@app.post("/api/login", tags=["public"])
def login(body: LoginBody):
    if not auth.verify_password(body.username, body.password):
        raise HTTPException(401, "invalid credentials")
    token = auth.create_session(body.username)
    profile_data = auth.profile(body.username)
    audit_mod.AuditLog.record(body.username, "login", "user",
                     metadata={"role": profile_data.get("role")})
    return {"ok": True, "session_token": token, **profile_data}

# =============================== PROTECTED ====================================

@app.get("/api/me", tags=["protected"])
def me(user: str = Depends(current_user)):
    return auth.profile(user)

@app.post("/api/rotate-key", tags=["protected"])
def rotate_key(user: str = Depends(current_user)):
    audit_mod.AuditLog.record(user, "rotate_key", "user")
    return auth.rotate_api_key(user)

@app.get("/api/stats", tags=["protected"])
def user_stats(user: str = Depends(current_user)):
    astats = axiom_store.stats(user)
    ustats = auth.get_user_stats(user)
    return {**ustats, "axioms": astats}

# -- profile ------------------------------------------------------------------

@app.get("/api/profile/{username}", tags=["public"])
def get_profile(username: str):
    p = auth.profile(username)
    if not p.get("created"):
        raise HTTPException(404, f"user {username!r} not found")
    return p

@app.put("/api/profile", tags=["protected"])
def update_profile(body: UpdateProfileBody, user: str = Depends(current_user)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "no fields to update")
    audit_mod.AuditLog.record(user, "update", "user", metadata=updates)
    return auth.update_profile(user, updates)

# -- generation ---------------------------------------------------------------

@app.post("/api/generate", tags=["protected"])
def generate(body: GenerateBody, user: str = Depends(current_user)):
    engine = MetaEngine(axiom_store=axiom_store)
    result = engine.generate(seed=body.seed, count=body.count,
                             force_phase_transition=body.force_phase_transition,
                             use_relativity=body.use_relativity,
                             username=user, persist=True)
    auth.bump_generations(user, len(result["axioms"]))
    # Save output file
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    out = OUTPUT_DIR / f"{user}-{stamp}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"user": user, **result}, f, indent=1, ensure_ascii=False)
    result["saved_as"] = out.name
    audit_mod.AuditLog.record(user, "generate", "axiom",
                     metadata={"count": body.count, "seed": body.seed,
                               "batch_id": result.get("batch_id")})
    return result

@app.post("/api/analyze", tags=["protected"])
def analyze_seed(body: AnalyzeBody, user: str = Depends(current_user)):
    return seedproc.analyze(body.seed)

# -- simulation ---------------------------------------------------------------

@app.post("/api/simulate", tags=["protected"])
def simulate(body: CoordsBody, user: str = Depends(current_user)):
    sim = FieldSimulator()
    curv = sim.curvature(body.coordinates)
    flow = sim.gradient_flow(body.coordinates)
    return {"curvature": curv, "gradient_flow": flow,
            "note": "diagnostics of a toy conformal metric"}

@app.post("/api/ricci", tags=["protected"])
def ricci(body: CoordsBody, user: str = Depends(current_user)):
    return FieldSimulator().curvature(body.coordinates)

@app.post("/api/geodesic", tags=["protected"])
def geodesic(body: GeodesicBody, user: str = Depends(current_user)):
    path = FieldSimulator().geodesic(body.start, body.end, body.steps)
    return {"steps": body.steps, "path": path,
            "dims": list(Coordinates([0.5] * 5).as_dict())}

# -- axioms CRUD --------------------------------------------------------------

@app.get("/api/axioms", tags=["protected"])
def list_axioms(user: str = Depends(current_user),
                status: Optional[str] = None, visibility: Optional[str] = None,
                category: Optional[str] = None, page: int = 1, limit: int = 20):
    return axiom_store.list_by_user(user, status=status, visibility=visibility,
                                    category=category, page=page, limit=limit)

@app.get("/api/axioms/public", tags=["public"])
def list_public_axioms(page: int = 1, limit: int = 20,
                       category: Optional[str] = None, search: Optional[str] = None,
                       sort_by: str = "created_at", sort_order: str = "desc"):
    return axiom_store.list_public(page=page, limit=limit, category=category,
                                  search=search, sort_by=sort_by, sort_order=sort_order)

@app.get("/api/axiom/{axiom_id}", tags=["public"])
def get_axiom(axiom_id: str):
    a = axiom_store.get(axiom_id)
    if not a:
        raise HTTPException(404, f"axiom {axiom_id!r} not found")
    axiom_store.increment_view(axiom_id)
    return a

@app.put("/api/axiom/{axiom_id}", tags=["protected"])
def update_axiom(axiom_id: str, body: UpdateAxiomBody, user: str = Depends(current_user)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    result = axiom_store.update(axiom_id, updates)
    if not result:
        raise HTTPException(404, "axiom not found or not owned by you")
    audit_mod.AuditLog.record(user, "update", "axiom", axiom_id, metadata=updates)
    return result

@app.delete("/api/axiom/{axiom_id}", tags=["protected"])
def delete_axiom(axiom_id: str, user: str = Depends(current_user)):
    if not axiom_store.delete(axiom_id, user):
        raise HTTPException(404, "axiom not found or not owned by you")
    audit_mod.AuditLog.record(user, "delete", "axiom", axiom_id)
    return {"ok": True}

# -- analysis -----------------------------------------------------------------

@app.post("/api/analyze/axiom", tags=["protected"])
def analyze_axiom(body: AnalyzeAxiomBody, user: str = Depends(current_user)):
    a = axiom_store.get(body.axiom_id)
    if not a:
        raise HTTPException(404, f"axiom {body.axiom_id!r} not found")
    result = run_analysis(a, mode=body.mode)
    audit_mod.AuditLog.record(user, "analyze", "axiom", body.axiom_id,
                     metadata={"mode": body.mode, "status": result.get("status")})
    return result

# -- ledger -------------------------------------------------------------------

@app.get("/api/ledger", tags=["public"])
def ledger_feed(page: int = 1, limit: int = 20,
                category: Optional[str] = None, search: Optional[str] = None,
                sort_by: str = "date"):
    return ledger_svc.feed(page=page, limit=limit, category=category,
                           search=search, sort_by=sort_by)

@app.post("/api/share", tags=["protected"])
def share_to_ledger(body: ShareToLedgerBody, user: str = Depends(current_user)):
    a = axiom_store.get(body.axiom_id)
    if not a:
        raise HTTPException(404, f"axiom {body.axiom_id!r} not found")
    if a["user"] != user:
        raise HTTPException(403, "can only share your own axioms")
    if a.get("visibility") == "public":
        raise HTTPException(400, "axiom is already public/shared")
    # Update axiom visibility
    axiom_store.update(body.axiom_id, {"visibility": "public", "status": "published"})
    entry = ledger_svc.share(a, user, body.license)
    # Update user stats
    with auth._LOCK:
        users = auth._load()
        if user in users:
            users[user]["total_axioms_shared"] = users[user].get("total_axioms_shared", 0) + 1
            users[user]["reputation_score"] = round(users[user].get("reputation_score", 0) + 0.5, 2)
            auth._save(users)
    audit_mod.AuditLog.record(user, "share", "axiom", body.axiom_id)
    return entry

@app.get("/api/ledger/verify", tags=["public"])
def verify_ledger():
    return ledger_svc.verify_integrity()

@app.post("/api/ledger/{ledger_hash}/like", tags=["protected"])
def like_ledger(ledger_hash: str, user: str = Depends(current_user)):
    result = ledger_svc.toggle_like(ledger_hash, delta=1)
    if not result:
        raise HTTPException(404, "ledger entry not found")
    audit_mod.AuditLog.record(user, "like", "ledger", ledger_hash)
    return result

@app.get("/api/ledger/featured", tags=["public"])
def featured():
    return {"featured": ledger_svc.get_featured()}

@app.get("/api/ledger/stats", tags=["public"])
def ledger_stats():
    return ledger_svc.stats()

# -- file upload --------------------------------------------------------------

@app.post("/api/upload", tags=["protected"])
async def upload_file(user: str = Depends(current_user),
                      file: UploadFile = File(...),
                      file_type: str = "supporting_evidence",
                      description: str = "",
                      is_public: bool = False):
    content = await file.read()
    try:
        entry = file_svc.save(content, file.filename or "unnamed", user,
                              mime_type=file.content_type or "application/octet-stream",
                              file_type=file_type, description=description,
                              is_public=is_public)
        audit_mod.AuditLog.record(user, "upload", "file", entry["id"],
                         metadata={"filename": file.filename, "size": len(content)})
        return entry
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/api/files", tags=["protected"])
def list_files(user: str = Depends(current_user)):
    return {"files": file_svc.list_by_user(user)}

@app.get("/api/files/{file_id}", tags=["protected"])
def get_file(file_id: str, user: str = Depends(current_user)):
    meta = file_svc.get(file_id)
    if not meta:
        raise HTTPException(404, "file not found")
    return meta

@app.get("/api/files/{file_id}/download", tags=["protected"])
def download_file(file_id: str, user: str = Depends(current_user)):
    result = file_svc.read(file_id)
    if not result:
        raise HTTPException(404, "file not found or integrity check failed")
    content, meta = result
    return JSONResponse(content={"filename": meta["original_name"],
                                "size": meta["file_size"],
                                "hash": meta["file_hash"],
                                "content_b64": __import__("base64").b64encode(content).decode()})

@app.delete("/api/files/{file_id}", tags=["protected"])
def delete_file_endpoint(file_id: str, user: str = Depends(current_user)):
    if not file_svc.delete(file_id, user):
        raise HTTPException(404, "file not found")
    audit_mod.AuditLog.record(user, "delete", "file", file_id)
    return {"ok": True}

# -- notifications ------------------------------------------------------------

@app.get("/api/notifications", tags=["protected"])
def notifications(user: str = Depends(current_user), unread: bool = False):
    return {"notifications": auth.get_notifications(user, unread_only=unread)}

@app.post("/api/notifications/{notif_id}/read", tags=["protected"])
def mark_read(notif_id: str, user: str = Depends(current_user)):
    if not auth.mark_notification_read(notif_id):
        raise HTTPException(404, "notification not found")
    return {"ok": True}

# -- audit --------------------------------------------------------------------

@app.get("/api/audit", tags=["protected"])
def get_audit(user: str = Depends(current_user), action: Optional[str] = None,
              resource_type: Optional[str] = None, limit: int = 100):
    # Users can only see their own audit logs
    return {"entries": audit_mod.AuditLog.query(
        username=user, action=action, resource_type=resource_type, limit=limit)}

@app.get("/api/audit/stats", tags=["protected"])
def audit_stats(user: str = Depends(current_user)):
    return audit_mod.AuditLog.stats()

# -- logout -------------------------------------------------------------------

@app.post("/api/logout", tags=["protected"])
def logout(x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
           user: str = Depends(current_user)):
    if x_session_token:
        auth.delete_session(x_session_token)
    return {"ok": True}

# =============================== ADMIN (RBAC) =================================
# All endpoints in this section require role=admin. They expose user management
# and a full-system audit view that is NOT scoped to the requesting user.

class UpdateRoleBody(BaseModel):
    role: str = Field(pattern="^(user|moderator|admin)$")
    permissions: Optional[list[str]] = None


@app.get("/api/users", tags=["admin"])
def list_users(user: str = Depends(require_role("admin"))):
    """Return a sanitized list of every user (admin only). Strips pwd_hash,
    salt, api_keys, and sessions."""
    return {"users": auth.list_users(), "count": len(auth.list_users())}


@app.put("/api/user/{username}/role", tags=["admin"])
def update_user_role(username: str, body: UpdateRoleBody,
                      user: str = Depends(require_role("admin"))):
    """Update a user's role and (optionally) their permission list.
    Admins always receive the wildcard permission set regardless of input."""
    try:
        result = auth.set_role(username, body.role, body.permissions)
        audit_mod.AuditLog.record(
            user, "update_role", "user", username,
            metadata={"new_role": body.role, "permissions": body.permissions})
        return result
    except auth.AuthError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/audit/full", tags=["admin"])
def full_audit(user: str = Depends(require_role("admin")),
               action: Optional[str] = None,
               resource_type: Optional[str] = None,
               username: Optional[str] = None,
               limit: int = 100):
    """Full audit log view (admin only). Unlike /api/audit, this is NOT
    scoped to the requesting user — admins can filter by any user."""
    return {"entries": audit_mod.AuditLog.query(
        username=username, action=action,
        resource_type=resource_type, limit=limit),
        "queried_by": user}

# =============================== DASHBOARD ====================================

@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(BASE / "static" / "dashboard.html")

# -- export all (batch) ---------------------------------------------------

@app.post("/api/export/batch", tags=["protected"])
def export_batch(body: dict, user: str = Depends(current_user)):
    """Export all axioms from a batch or from the last generate call as a single JSON."""
    batch_id = body.get("batch_id")
    axiom_ids = body.get("axiom_ids", [])
    if not batch_id and not axiom_ids:
        raise HTTPException(400, "provide batch_id or axiom_ids")
    if axiom_ids:
        axioms = []
        for aid in axiom_ids:
            a = axiom_store.get(aid)
            if a and a.get("user") == user:
                axioms.append(a)
    else:
        all_axioms = axiom_store._cache["axioms"]
        axioms = [a for a in all_axioms if a.get("batch_id") == batch_id and a.get("user") == user]
    if not axioms:
        raise HTTPException(404, "no axioms found for this batch")
    # Build metric-based unique filename
    avg_metrics = {}
    if axioms:
        mkeys = ["novelty", "coherence", "elegance", "alienness", "sophia_score"]
        for k in mkeys:
            vals = [a.get("metrics", {}).get(k, 0) for a in axioms]
            avg_metrics[k] = round(sum(vals) / len(vals), 3)
    # Create a descriptive filename from metrics
    top_metric = max(avg_metrics, key=avg_metrics.get) if avg_metrics else "axioms"
    top_val = avg_metrics.get(top_metric, 0)
    sophia_count = sum(1 for a in axioms if a.get("sophia_point"))
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    filename = f"{user}_{top_metric}{top_val:.2f}_s{sophia_count}_{stamp}.json"
    export_data = {
        "export_version": "0.6.3",
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "exported_by": user,
        "batch_id": batch_id,
        "axiom_count": len(axioms),
        "avg_metrics": avg_metrics,
        "sophia_points_in_batch": sophia_count,
        "axioms": axioms,
    }
    out_path = OUTPUT_DIR / filename
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    audit_mod.AuditLog.record(user, "export_batch", "axiom", batch_id,
                     metadata={"count": len(axioms), "filename": filename})
    return JSONResponse(content=export_data,
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# -- seed presets -----------------------------------------------------------

@app.get("/api/seeds/presets", tags=["public"])
def seed_presets():
    return {"presets": [
        {"id": "paradox", "label": "Recursive Paradox", "seed": "recursive paradox of observer time"},
        {"id": "consciousness", "label": "Consciousness & Space", "seed": "consciousness as topological invariant of spacetime manifold"},
        {"id": "quantum", "label": "Quantum Entanglement", "seed": "quantum entanglement as nonlocal information channel"},
        {"id": "emergence", "label": "Emergent Complexity", "seed": "emergent complexity from simple autopoietic rules"},
        {"id": "godel", "label": "Gödel Incompleteness", "seed": "godel incompleteness applied to physical law"},
        {"id": "information", "label": "Information Theory", "seed": "information as fundamental substrate of reality"},
        {"id": "entropy", "label": "Entropy & Time", "seed": "entropy arrow of time and memory formation"},
        {"id": "fractal", "label": "Fractal Ontology", "seed": "fractal self-similarity across ontological scales"},
        {"id": "void", "label": "Void & Potential", "seed": "the void as generative potential field"},
        {"id": "mirror", "label": "Mirror Symmetry", "seed": "mirror of the void reflecting consciousness back"},
        {"id": "autopoiesis", "label": "Autopoiesis", "seed": "mind-dust autopoietic ricci observer collapse"},
        {"id": "holographic", "label": "Holographic Principle", "seed": "holographic principle encoding 3D information on 2D boundary"},
    ]}


# -- file visibility & preview ----------------------------------------------

@app.put("/api/files/{file_id}/visibility", tags=["protected"])
def update_file_visibility(file_id: str, body: dict, user: str = Depends(current_user)):
    vis = body.get("visibility")
    if vis not in ("public", "private", "link_only"):
        raise HTTPException(400, "visibility must be public, private, or link_only")
    result = file_svc.update_visibility(file_id, user, vis)
    if not result:
        raise HTTPException(404, "file not found or not owned by you")
    return result


@app.get("/api/files/{file_id}/preview", tags=["protected"])
def preview_file(file_id: str, user: str = Depends(current_user)):
    result = file_svc.read(file_id)
    if not result:
        raise HTTPException(404, "file not found")
    content, meta = result
    mime = meta.get("mime_type", "")
    fname = meta.get("original_name", "").lower()
    if fname.endswith(".md") or mime == "text/markdown":
        text = content.decode("utf-8", errors="replace")
        return {"type": "markdown", "content": text, "filename": meta["original_name"]}
    elif fname.endswith(".pdf") or mime == "application/pdf":
        # Extract text from PDF (first 5000 chars)
        try:
            import io
            text = _extract_pdf_text(content)
            return {"type": "pdf", "content": text, "filename": meta["original_name"],
                    "page_count": text.count("\n\n") + 1 if text else 0}
        except Exception:
            return {"type": "pdf", "content": "[PDF preview not available - binary file]",
                    "filename": meta["original_name"], "page_count": 0}
    elif any(fname.endswith(x) for x in (".txt", ".json", ".csv", ".yaml", ".yml")) or "text/" in mime:
        text = content.decode("utf-8", errors="replace")[:10000]
        return {"type": "text", "content": text, "filename": meta["original_name"]}
    return {"type": "unsupported", "content": None, "filename": meta["original_name"]}


def _extract_pdf_text(data: bytes) -> str:
    """Basic PDF text extraction without external deps. Extracts visible text strings."""
    import re
    text_parts = []
    try:
        raw = data.decode("latin-1", errors="replace")
        # Find text between BT and ET markers (basic PDF text objects)
        for match in re.finditer(r'\(([^)]*)\)\s*Tj', raw):
            text_parts.append(match.group(1))
        # Also try streams
        for match in re.finditer(r'stream\r?\n(.*?)\r?\nendstream', raw, re.DOTALL):
            stream = match.group(1)
            for tj in re.finditer(r'\(([^)]*)\)\s*Tj', stream):
                text_parts.append(tj.group(1))
    except Exception:
        pass
    return "\n".join(text_parts)[:5000] if text_parts else "[Could not extract text from PDF]"


# -- file-ledger linking ----------------------------------------------------

@app.post("/api/files/{file_id}/link-ledger", tags=["protected"])
def link_file_to_ledger(file_id: str, body: dict, user: str = Depends(current_user)):
    ledger_hash = body.get("ledger_hash")
    if not ledger_hash:
        raise HTTPException(400, "ledger_hash required")
    result = file_svc.link_to_ledger(file_id, user, ledger_hash)
    if not result:
        raise HTTPException(404, "file not found or not owned by you")
    # Also update ledger entry to reference the file
    ledger_svc.attach_file(ledger_hash, file_id, meta=result)
    audit_mod.AuditLog.record(user, "link_file", "file", file_id,
                     metadata={"ledger_hash": ledger_hash})
    return {"ok": True, "file": result, "ledger_hash": ledger_hash}


@app.get("/api/files/public", tags=["public"])
def list_public_files():
    return {"files": file_svc.list_public()}


# -- public file download by link -------------------------------------------

@app.get("/api/files/link/{file_id}", tags=["public"])
def download_by_link(file_id: str):
    meta = file_svc.get(file_id)
    if not meta:
        raise HTTPException(404, "file not found")
    if meta.get("visibility") not in ("public", "link_only"):
        raise HTTPException(403, "file is private")
    result = file_svc.read(file_id)
    if not result:
        raise HTTPException(404, "file content not found")
    content, _ = result
    return JSONResponse(content={"filename": meta["original_name"],
                                "size": meta["file_size"],
                                "hash": meta["file_hash"],
                                "content_b64": __import__("base64").b64encode(content).decode()})


# -- 404 fallback -----------------------------------------------------------

@app.exception_handler(404)
async def not_found(request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": getattr(exc, "detail", "not found")},
                            status_code=404)
    return FileResponse(BASE / "static" / "dashboard.html")
