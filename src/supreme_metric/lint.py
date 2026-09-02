"""Check a claim pack against a compiled manifest. Every finding has a stable code."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

CODES = {
    "MT001": "unknown reference",
    "MT010": "claim has no metric",
    "MT020": "role not assigned to this metric for this question",
    "MT021": "required companion missing",
    "MT030": "closed surface: wrong count or order of scored questions",
    "MT040": "window not allowed",
    "MT041": "benchmark not allowed",
    "MT050": "denied comparison",
    "MT060": "role not in metric.roles_allowed",
    "MT070": "pack digest does not match manifest",
}


@dataclass
class Finding:
    code: str
    claim: str | None
    message: str
    severity: str = "error"
    rulings: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def _index(manifest: dict):
    return (
        {m["id"]: m for m in manifest["metrics"]},
        {q["id"]: q for q in manifest["questions"]},
        {(e["a"], e["b"]): e for e in manifest["edges"] if e["kind"] == "not_comparable_with"},
    )


def lint_pack(pack: dict, manifest: dict) -> list[Finding]:
    out: list[Finding] = []
    metrics, questions, denied = _index(manifest)
    prof = manifest["profile"]

    if pack.get("topology_digest") and pack["topology_digest"] != manifest["topology_digest"]:
        out.append(Finding("MT070", None, f"pack pinned to {pack['topology_digest'][:19]}…, manifest is {manifest['topology_digest'][:19]}…"))

    surface = pack.get("surface")
    if surface not in prof["surfaces"]:
        out.append(Finding("MT001", None, f"unknown surface `{surface}`"))
        return out

    scored: dict[str, str] = {}  # question -> first claim id with role score
    scored_order: list[str] = []
    for c in pack.get("claims", []):
        cid = c.get("id", "?")
        rulings: list[str] = []
        if "metric" not in c:
            out.append(Finding("MT010", cid, f"“{c.get('text', '')}” names no metric"))
            continue
        m = metrics.get(c["metric"])
        q = questions.get(c.get("question"))
        role = c.get("role")
        if m is None:
            out.append(Finding("MT001", cid, f"unknown metric `{c['metric']}`"))
        if q is None:
            out.append(Finding("MT001", cid, f"unknown question `{c.get('question')}`"))
        if role == "score":
            scored.setdefault(c.get("question"), cid)
            if c.get("question") not in scored_order:
                scored_order.append(c.get("question"))
        if c.get("owner") and c["owner"] not in prof["owners"]:
            out.append(Finding("MT001", cid, f"unknown owner `{c['owner']}`"))
        if m is None or q is None:
            continue
        rulings = list(dict.fromkeys(list(m.get("rulings", [])) + list(q.get("rulings", []))))

        if role not in m["roles_allowed"]:
            out.append(Finding("MT060", cid, f"`{m['id']}` may be {', '.join(m['roles_allowed'])}, not {role}", rulings=rulings))
        for p in q.get("prohibited", []):
            if p["metric"] == m["id"]:
                out.append(Finding("MT020", cid, f"`{m['id']}` is prohibited on `{q['id']}`: {p.get('reason', '')}", rulings=rulings))
                break
        else:
            assigned = {"score": [q["score"]], "companion": q["companions"], "diagnostic": q.get("diagnostics", []), "context": [m["id"]]}
            if m["id"] not in assigned.get(role, []):
                out.append(Finding("MT020", cid, f"`{m['id']}` is not the {role} for `{q['id']}`" + (f"; the score is `{q['score']}`" if role == "score" else ""), rulings=rulings))

        w = c.get("window")
        if w not in prof["windows"]:
            out.append(Finding("MT001", cid, f"unknown window `{w}`"))
        elif w not in m["windows"] or (q.get("windows") and w not in q["windows"]):
            out.append(Finding("MT040", cid, f"window `{w}` not allowed for `{m['id']}` on `{q['id']}`", rulings=rulings))

        b = c.get("benchmark")
        if b not in prof["benchmarks"]:
            out.append(Finding("MT001", cid, f"unknown benchmark `{b}`"))
        else:
            allowed_on = prof["benchmarks"][b].get("allowed_on_surfaces")
            if b not in m["benchmarks"]:
                out.append(Finding("MT041", cid, f"benchmark `{b}` not allowed for `{m['id']}`; allowed: {', '.join(m['benchmarks'])}", rulings=rulings))
            elif allowed_on is not None and surface not in allowed_on:
                out.append(Finding("MT041", cid, f"benchmark `{b}` is not allowed on surface `{surface}`", rulings=rulings))

        for other in c.get("compares_with", []) or []:
            if other not in metrics:
                out.append(Finding("MT001", cid, f"unknown metric `{other}` in compares_with"))
                continue
            e = denied.get(tuple(sorted([m["id"], other])))
            if e:
                out.append(Finding("MT050", cid, f"`{m['id']}` vs `{other}`: {e.get('reason', 'denied comparison')}", rulings=rulings))

    # surface-level checks
    surf_qs = [q for q in manifest["questions"] if q["surface"] == surface]
    expected = [q["id"] for q in sorted(surf_qs, key=lambda q: q["order"])]
    if prof["surfaces"][surface].get("closed"):
        got = [qid for qid in scored_order]
        if set(got) != set(expected):
            missing = [q for q in expected if q not in got]
            extra = [q for q in got if q not in expected]
            out.append(Finding("MT030", None, f"closed surface `{surface}` expects {len(expected)} scored questions, got {len(got)}"
                               + (f"; missing {missing}" if missing else "") + (f"; extra {extra}" if extra else "")))
        elif got != expected:
            out.append(Finding("MT030", None, f"scored questions out of order: {got}"))
    for qid, cid in scored.items():
        q = questions.get(qid)
        if not q:
            continue
        present = {(c.get("question"), c.get("metric")) for c in pack.get("claims", []) if c.get("role") == "companion"}
        for comp in q["companions"]:
            if (qid, comp) not in present:
                out.append(Finding("MT021", cid, f"`{qid}` scored without its companion `{comp}`", rulings=list(q.get("rulings", []))))
    return out
