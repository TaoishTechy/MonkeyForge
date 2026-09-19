#!/usr/bin/env python3
"""MonkeyForge DEMO-Lite v0.6.3 -- CLI.

v0.6.3 adds RBAC: 'promote' and 'list-users' subcommands.

Preserves the v0.1 command surface with v0.6 additions:

  python cli.py serve [--host H] [--port P]     start API + dashboard
  python cli.py list-clusters
  python cli.py list-equations <cluster>
  python cli.py search <keyword>
  python cli.py show <eq-id>
  python cli.py generate [--seed TEXT] [--count N] [--force-pt] [--numeric-seed N]
  python cli.py analyze --seed TEXT
  python cli.py framework <name>
  python cli.py frameworks
  python cli.py simulate --coords 5floats
  python cli.py ricci --coords 5floats
  python cli.py geodesic --start 5floats --end 5floats [--steps N]
  python cli.py register <username>           (prompts for password)
  python cli.py profile [username]             (show user profile)
  python cli.py share <axiom-id>              (share axiom to ledger)
  python cli.py ledger [--page N] [--search KW]  (browse ledger)
  python cli.py ledger-verify                 (verify chain integrity)
  python cli.py analyze-axiom <axiom-id> [--mode basic|deepseek]
  python cli.py upload <file-path>            (upload file)
  python cli.py my-axioms [--page N]          (list own axioms)
  python cli.py audit [--action ACT]          (view audit log)
  python cli.py test
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys

import auth as _auth_module  # for VALID_ROLES at parser-construction time


def _floats(text: str) -> list:
    vals = [float(v) for v in text.replace(",", " ").split()]
    if len(vals) != 5:
        raise argparse.ArgumentTypeError("need exactly 5 floats")
    return vals


def _emit(obj) -> None:
    print(json.dumps(obj, indent=1, ensure_ascii=False))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="monkeyforge-lite",
                                description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8480)

    sub.add_parser("list-clusters")
    sub.add_parser("list-equations").add_argument("cluster")
    sub.add_parser("search").add_argument("keyword")
    sub.add_parser("show").add_argument("eq_id")

    g = sub.add_parser("generate")
    g.add_argument("--seed", default=None)
    g.add_argument("--count", type=int, default=1)
    g.add_argument("--force-pt", action="store_true", help="force a Sophia phase transition")
    g.add_argument("--numeric-seed", type=int, default=None, help="deterministic RNG seed")

    a = sub.add_parser("analyze")
    a.add_argument("--seed", required=True)

    sub.add_parser("framework").add_argument("name")
    sub.add_parser("frameworks")

    for name in ("simulate", "ricci"):
        c = sub.add_parser(name)
        c.add_argument("--coords", type=_floats, required=True)

    ge = sub.add_parser("geodesic")
    ge.add_argument("--start", type=_floats, required=True)
    ge.add_argument("--end", type=_floats, required=True)
    ge.add_argument("--steps", type=int, default=24)

    sub.add_parser("register").add_argument("username")

    # v0.6.3 RBAC: promote/demote users from the CLI
    promo = sub.add_parser("promote")
    promo.add_argument("username")
    promo.add_argument("--role", default="user", choices=list(_auth_module.VALID_ROLES),
                      help="target role (default: user)")
    promo.add_argument("--permissions", nargs="*", default=None,
                      help="override permission list (admin role always gets ['*'])")

    sub.add_parser("list-users")

    # v0.5 commands
    sub.add_parser("profile").add_argument("username", nargs="?", default=None)

    sub.add_parser("share").add_argument("axiom_id")

    le = sub.add_parser("ledger")
    le.add_argument("--page", type=int, default=1)
    le.add_argument("--search", default=None)
    le.add_argument("--category", default=None)

    sub.add_parser("ledger-verify")

    aa = sub.add_parser("analyze-axiom")
    aa.add_argument("axiom_id")
    aa.add_argument("--mode", default="basic", choices=["basic", "deepseek"])

    sub.add_parser("upload").add_argument("filepath")

    ma = sub.add_parser("my-axioms")
    ma.add_argument("--page", type=int, default=1)

    au = sub.add_parser("audit")
    au.add_argument("--action", default=None)
    au.add_argument("--limit", type=int, default=20)

    sub.add_parser("test")

    args = p.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn
        uvicorn.run("app:app", host=args.host, port=args.port)
        return 0

    from explorer import EquationExplorer
    from frameworks import FrameworkLoader
    from core import FieldSimulator, MetaEngine, SeedProcessor, AxiomStore

    if args.cmd == "list-clusters":
        _emit(EquationExplorer().clusters())
    elif args.cmd == "list-equations":
        _emit(EquationExplorer().in_cluster(args.cluster))
    elif args.cmd == "search":
        _emit(EquationExplorer().search(args.keyword))
    elif args.cmd == "show":
        eq = EquationExplorer().show(args.eq_id)
        _emit(eq or {"error": f"no equation {args.eq_id!r}"})
    elif args.cmd == "generate":
        engine = MetaEngine(numeric_seed=args.numeric_seed)
        _emit(engine.generate(seed=args.seed, count=args.count,
                              force_phase_transition=args.force_pt))
    elif args.cmd == "analyze":
        _emit(SeedProcessor().analyze(args.seed))
    elif args.cmd == "framework":
        fw = FrameworkLoader().get(args.name)
        _emit(fw or {"error": f"no framework {args.name!r}"})
    elif args.cmd == "frameworks":
        _emit(FrameworkLoader().summary())
    elif args.cmd == "simulate":
        sim = FieldSimulator()
        _emit({"curvature": sim.curvature(args.coords),
               "gradient_flow": sim.gradient_flow(args.coords)})
    elif args.cmd == "ricci":
        _emit(FieldSimulator().curvature(args.coords))
    elif args.cmd == "geodesic":
        _emit(FieldSimulator().geodesic(args.start, args.end, args.steps))
    elif args.cmd == "register":
        import auth
        pwd = getpass.getpass("password (min 8 chars): ")
        email = input("email (optional, press Enter to skip): ").strip() or None
        try:
            _emit(auth.register(args.username, pwd, email))
        except auth.AuthError as exc:
            _emit({"error": str(exc)})
            return 1
    elif args.cmd == "promote":
        # v0.6.3 RBAC: change a user's role/permissions from the CLI.
        # Note: the FIRST registered user is automatically admin (see auth.register),
        # so this command is for subsequent promotions / demotions.
        import auth
        try:
            result = auth.set_role(args.username, args.role, args.permissions)
            _emit(result)
        except auth.AuthError as exc:
            _emit({"error": str(exc)})
            return 1
    elif args.cmd == "list-users":
        import auth
        _emit({"users": auth.list_users()})
    elif args.cmd == "profile":
        import auth
        name = args.username
        if not name:
            name = input("username: ").strip()
        _emit(auth.profile(name))
    elif args.cmd == "share":
        from ledger import LedgerService
        store = AxiomStore()
        axiom = store.get(args.axiom_id)
        if not axiom:
            _emit({"error": f"axiom {args.axiom_id} not found"})
            return 1
        user = axiom.get("user", "unknown")
        store.update(args.axiom_id, {"visibility": "public", "status": "published"})
        entry = LedgerService().share(axiom, user)
        _emit(entry)
    elif args.cmd == "ledger":
        from ledger import LedgerService
        _emit(LedgerService().feed(page=args.page, search=args.search, category=args.category))
    elif args.cmd == "ledger-verify":
        from ledger import LedgerService
        _emit(LedgerService().verify_integrity())
    elif args.cmd == "analyze-axiom":
        from analysis import analyze as run_analysis
        store = AxiomStore()
        axiom = store.get(args.axiom_id)
        if not axiom:
            _emit({"error": f"axiom {args.axiom_id} not found"})
            return 1
        _emit(run_analysis(axiom, mode=args.mode))
    elif args.cmd == "upload":
        from storage import FileService
        path = args.filepath
        try:
            content = open(path, "rb").read()
        except FileNotFoundError:
            _emit({"error": f"file not found: {path}"})
            return 1
        import os
        name = os.path.basename(path)
        entry = FileService().save(content, name, "cli-user")
        _emit(entry)
    elif args.cmd == "my-axioms":
        store = AxiomStore()
        _emit(store.list_by_user("cli-user", page=args.page))
    elif args.cmd == "audit":
        from audit import AuditLog
        _emit(AuditLog.query(action=args.action, limit=args.limit))
    elif args.cmd == "test":
        return run_selftest()
    return 0


def run_selftest() -> int:
    """Self-test: v0.1 checks + v0.5 module imports + axiom store + ledger."""
    from explorer import EquationExplorer
    from frameworks import FrameworkLoader
    from core import (FieldSimulator, MetaEngine, SeedProcessor, AxiomStore, Coordinates)
    from ledger import LedgerService
    from storage import FileService
    from analysis import analyze as run_analysis
    from audit import AuditLog

    failures = []

    def check(label, cond):
        print(("  ok    " if cond else "  FAIL  ") + label)
        if not cond:
            failures.append(label)

    # v0.1 checks
    ex = EquationExplorer()
    check("equations loaded (>100)", len(ex.equations) > 100)
    check("clusters present (>5)", len(ex.clusters()) > 5)
    check("search finds hits", len(ex.search("entropy")) > 0)

    fl = FrameworkLoader()
    check("frameworks loaded (>30)", len(fl.frameworks) > 30)
    check("no silent skips", all("reason" in s for s in fl.skipped))

    sim = FieldSimulator()
    curv = sim.curvature([0.2, 0.4, 0.6, 0.8, 0.5])
    check("default simulator computes curvature", isinstance(curv["ricci_scalar"], float))
    geo = sim.geodesic([0.1] * 5, [0.9] * 5, steps=10)
    check("geodesic returns full path", len(geo) == 11)

    sp = SeedProcessor().analyze("recursive paradox of observer time")
    check("seed analysis yields coordinates", len(sp["target_coordinates"]) == 5)

    eng = MetaEngine(numeric_seed=42)
    forced = eng.generate(seed="mirror of the void", count=3, force_phase_transition=True)
    check("force_phase_transition honored", all(a["sophia_point"] for a in forced["axioms"]))

    a1 = MetaEngine(numeric_seed=7).generate(count=2)
    a2 = MetaEngine(numeric_seed=7).generate(count=2)
    check("numeric seed is deterministic",
          [x["axiom"] for x in a1["axioms"]] == [x["axiom"] for x in a2["axioms"]])

    # v0.5 checks
    store = AxiomStore()
    check("axiom store initializes", store is not None)

    # Test axiom create/retrieve
    test_axiom = {
        "axiom": "Test axiom for self-validation purposes.",
        "name": "Self-Test Axiom",
        "framework": "TestFramework",
        "mechanism": "self-validation",
        "coordinates": {"participation": 0.5, "plasticity": 0.5, "substrate": 0.5, "temporal": 0.5, "generative": 0.5},
        "metrics": {"novelty": 0.8, "coherence": 0.7, "paradox_intensity": 0.3, "alienness": 0.4, "elegance": 0.9, "ricci_scalar": 1.5, "sophia_score": 0.7},
        "equation_ref": {"id": "TEST-01", "title": "Test Equation"},
        "sophia_point": True,
        "phase_transition_forced": False,
        "seed_analysis": None,
        "generated_at": "2026-07-04T00:00:00Z",
    }
    created = store.create(test_axiom, "test_user")
    check("axiom create returns id", created["id"].startswith("AXM-"))
    retrieved = store.get(created["id"])
    check("axiom retrieve by id", retrieved is not None and retrieved["id"] == created["id"])

    # Test axiom update (versioning)
    updated = store.update(created["id"], {"name": "Updated Self-Test"})
    check("axiom update versioning", updated is not None and updated["version"] == 2)
    check("axiom version history", len(updated.get("versions", [])) == 1)

    # Test axiom delete
    deleted = store.delete(created["id"], "test_user")
    check("axiom delete", deleted)
    check("axiom gone after delete", store.get(created["id"]) is None)

    # Test ledger
    ledger = LedgerService()
    test_entry = ledger.share(test_axiom, "test_user")
    check("ledger share creates entry", test_entry["ledger_hash"] is not None)
    check("ledger chain links", test_entry["previous_hash"] is None)  # first entry = genesis

    # Share a second entry to test chain
    test_axiom2 = dict(test_axiom, axiom="Second test axiom for chain validation.")
    test_entry2 = ledger.share(test_axiom2, "test_user")
    check("ledger chain grows", test_entry2["previous_hash"] == test_entry["ledger_hash"])

    # Verify integrity
    integrity = ledger.verify_integrity()
    check("ledger integrity valid", integrity["is_valid"])

    # Test analysis
    basic = run_analysis(test_axiom)
    check("basic analysis completes", basic["status"] == "completed")
    check("basic analysis has quality_score", "quality_score" in basic)

    # Test file service
    fs = FileService()
    uploaded = fs.save(b"test file content", "test.txt", "test_user", "text/plain", "supporting_evidence")
    check("file upload works", uploaded["id"] is not None)
    content, meta = fs.read(uploaded["id"])
    check("file download with integrity", content == b"test file content")

    # Test audit log
    AuditLog.record("test_user", "test_action", "test_resource", "test_123")
    audit_entries = AuditLog.query(username="test_user", action="test_action")
    check("audit log records", len(audit_entries) > 0)

    # Test Coordinates clamping
    c = Coordinates([1.5, -0.3, 0.5, 2.0, 0.0])
    check("coordinates clamped to [0,1]", all(0.0 <= v <= 1.0 for v in c.values))

    # Cleanup test data
    store.delete(test_entry2.get("axiom_id", ""), "test_user")
    ledger.data["entries"] = []
    ledger.data["chain_head"] = None
    from ledger import _save as _ledger_save
    _ledger_save(ledger.data)
    fs.delete(uploaded["id"], "test_user")

    total = 9 + 14  # 9 v0.1 + 14 v0.5
    print(f"\n{'PASS' if not failures else 'FAIL'}: "
          f"{total - len(failures)}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
