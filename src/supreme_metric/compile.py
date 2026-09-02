"""Load a registry, validate every reference, derive the topology, emit one manifest with a digest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

SPEC_VERSION = 1
ROLES = ("score", "companion", "diagnostic", "context")
REQUIRED = {
    "metric": ("id", "label", "definition", "owner", "universe", "grain", "roles_allowed", "windows", "benchmarks"),
    "question": ("id", "label", "purpose", "surface", "order", "score", "companions"),
    "ruling": ("id", "date", "owner", "statement", "applies_to"),
    "profile": ("spec_version", "owners", "surfaces", "windows", "benchmarks"),
}


class CompileError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(obj) -> str:
    return "sha256:" + hashlib.sha256(canonical(obj).encode()).hexdigest()


def _read(path: Path):
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def load_registry(root: Path) -> dict:
    root = Path(root)
    if not (root / "profile.yaml").exists():
        raise CompileError([f"{root}: no profile.yaml. A registry starts with a profile."])
    sources: dict[str, str] = {}

    def track(path: Path):
        sources[path.relative_to(root).as_posix()] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        return _read(path)

    profile = track(root / "profile.yaml")
    metrics, questions, rulings = [], [], []
    for path in sorted((root / "metrics").glob("*.yaml")):
        doc = track(path)
        for m in doc.get("metrics", []):
            m["_source"] = path.relative_to(root).as_posix()
            metrics.append(m)
    for path in sorted((root / "questions").glob("*.yaml")):
        q = track(path)
        q["_source"] = path.relative_to(root).as_posix()
        questions.append(q)
    for path in sorted((root / "rulings").rglob("*.yaml")):
        r = track(path)
        r["_source"] = path.relative_to(root).as_posix()
        rulings.append(r)
    return {"profile": profile, "metrics": metrics, "questions": questions, "rulings": rulings, "sources": sources}


def validate(reg: dict) -> list[str]:
    errs: list[str] = []
    prof = reg["profile"]
    for f in REQUIRED["profile"]:
        if f not in prof:
            errs.append(f"profile.yaml: missing `{f}`")
    if errs:
        return errs
    owners, surfaces = set(prof["owners"]), set(prof["surfaces"])
    windows, benchmarks = set(prof["windows"]), set(prof["benchmarks"])
    for wid, w in prof["windows"].items():
        if w.get("kind") not in ("flow", "snapshot"):
            errs.append(f"profile.yaml: window `{wid}` needs kind flow or snapshot")

    def need(kind, obj):
        missing = [f for f in REQUIRED[kind] if f not in obj]
        if missing:
            errs.append(f"{obj.get('_source')}: {kind} `{obj.get('id', '?')}` missing {', '.join(missing)}")
        return not missing

    metrics = {}
    for m in reg["metrics"]:
        if not need("metric", m):
            continue
        if m["id"] in metrics:
            errs.append(f"{m['_source']}: duplicate metric id `{m['id']}`")
        metrics[m["id"]] = m
        src = m["_source"]
        if m["owner"] not in owners:
            errs.append(f"{src}: metric `{m['id']}` owner `{m['owner']}` is not in profile.owners")
        for r in m["roles_allowed"]:
            if r not in ROLES:
                errs.append(f"{src}: metric `{m['id']}` role `{r}` is not one of {', '.join(ROLES)}")
        for w in m["windows"]:
            if w not in windows:
                errs.append(f"{src}: metric `{m['id']}` window `{w}` is not in profile.windows")
        for b in m["benchmarks"]:
            if b not in benchmarks:
                errs.append(f"{src}: metric `{m['id']}` benchmark `{b}` is not in profile.benchmarks")
    for m in metrics.values():
        for nc in m.get("not_comparable_with", []):
            if nc.get("metric") not in metrics:
                errs.append(f"{m['_source']}: metric `{m['id']}` not_comparable_with unknown metric `{nc.get('metric')}`")

    rulings = {}
    for r in reg["rulings"]:
        if not need("ruling", r):
            continue
        if r["id"] in rulings:
            errs.append(f"{r['_source']}: duplicate ruling id `{r['id']}`")
        rulings[r["id"]] = r
        if r["owner"] not in owners:
            errs.append(f"{r['_source']}: ruling `{r['id']}` owner `{r['owner']}` is not in profile.owners")
    for r in rulings.values():
        sup = r.get("supersedes")
        if sup and sup not in rulings:
            errs.append(f"{r['_source']}: ruling `{r['id']}` supersedes unknown ruling `{sup}`")

    questions = {}
    orders: dict[tuple, str] = {}
    for q in reg["questions"]:
        if not need("question", q):
            continue
        if q["id"] in questions:
            errs.append(f"{q['_source']}: duplicate question id `{q['id']}`")
        questions[q["id"]] = q
        src = q["_source"]
        if q["surface"] not in surfaces:
            errs.append(f"{src}: question `{q['id']}` surface `{q['surface']}` is not in profile.surfaces")
        key = (q["surface"], q["order"])
        if key in orders:
            errs.append(f"{src}: question `{q['id']}` shares order {q['order']} with `{orders[key]}` on `{q['surface']}`")
        orders[key] = q["id"]

        def role_ok(mid, role, what):
            m = metrics.get(mid)
            if not m:
                errs.append(f"{src}: question `{q['id']}` {what} unknown metric `{mid}`")
            elif role not in m["roles_allowed"]:
                errs.append(f"{src}: question `{q['id']}` uses `{mid}` as {role} but its roles_allowed are {m['roles_allowed']}")

        role_ok(q["score"], "score", "score is")
        for c in q["companions"]:
            role_ok(c, "companion", "companion")
            if c == q["score"]:
                errs.append(f"{src}: question `{q['id']}` lists its score `{c}` as a companion too")
        for d in q.get("diagnostics", []):
            role_ok(d, "diagnostic", "diagnostic")
        for p in q.get("prohibited", []):
            if p.get("metric") not in metrics:
                errs.append(f"{src}: question `{q['id']}` prohibits unknown metric `{p.get('metric')}`")
        for w in q.get("windows", []):
            if w not in windows:
                errs.append(f"{src}: question `{q['id']}` window `{w}` is not in profile.windows")
        for rid in q.get("rulings", []):
            if rid not in rulings:
                errs.append(f"{src}: question `{q['id']}` cites unknown ruling `{rid}`")
    for m in metrics.values():
        for rid in m.get("rulings", []):
            if rid not in rulings:
                errs.append(f"{m['_source']}: metric `{m['id']}` cites unknown ruling `{rid}`")
    return errs


def derive_edges(questions: list[dict], metrics: list[dict]) -> list[dict]:
    edges = []
    for q in questions:
        edges.append({"kind": "scores", "from": q["score"], "to": q["id"]})
        edges += [{"kind": "companion_of", "from": c, "to": q["id"]} for c in q["companions"]]
        edges += [{"kind": "diagnoses", "from": d, "to": q["id"]} for d in q.get("diagnostics", [])]
        edges += [{"kind": "prohibited", "from": p["metric"], "to": q["id"], "reason": p.get("reason", "")} for p in q.get("prohibited", [])]
    seen = set()
    for m in metrics:
        for nc in m.get("not_comparable_with", []):
            a, b = sorted([m["id"], nc["metric"]])
            if (a, b) not in seen:
                seen.add((a, b))
                edges.append({"kind": "not_comparable_with", "a": a, "b": b, "reason": nc.get("reason", "")})
    return edges


def _strip(obj: dict) -> dict:
    return {k: v for k, v in obj.items() if not k.startswith("_")}


def compile_registry(root: Path) -> dict:
    reg = load_registry(Path(root))
    errs = validate(reg)
    if errs:
        raise CompileError(errs)
    questions = sorted(reg["questions"], key=lambda q: (q["surface"], q["order"]))
    metrics = sorted(reg["metrics"], key=lambda m: m["id"])
    rulings = sorted(reg["rulings"], key=lambda r: (str(r["date"]), r["id"]))
    body = {
        "spec_version": SPEC_VERSION,
        "name": reg["profile"].get("name", "registry"),
        "profile": reg["profile"],
        "questions": [_strip(q) for q in questions],
        "metrics": [_strip(m) for m in metrics],
        "rulings": [{**_strip(r), "date": str(r["date"])} for r in rulings],
        "edges": derive_edges(questions, metrics),
        "sources": reg["sources"],
    }
    return {"topology_digest": digest(body), **body}


def write_manifest(manifest: dict, out: Path) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
