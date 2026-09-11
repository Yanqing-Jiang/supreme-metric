"""Emit a digest-pinned claim pack from explicit Markdown annotations."""
from __future__ import annotations

import json
from pathlib import Path

import yaml


class PackError(Exception):
    pass


def emit_pack(report: Path, topology: Path) -> dict:
    report = Path(report)
    lines = report.read_text().splitlines()
    if not lines or lines[0].strip() != "---":
        raise PackError(f"{report}: report needs YAML front matter with surface")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise PackError(f"{report}: unterminated front matter")
    front = yaml.safe_load("\n".join(lines[1:end])) or {}
    if not isinstance(front, dict) or not front.get("surface"):
        raise PackError(f"{report}: front matter needs `surface`")
    claims, ids = [], set()
    index = end + 1
    while index < len(lines):
        if lines[index].strip() != "```supreme-claim":
            index += 1
            continue
        start = index + 1
        index += 1
        body = []
        while index < len(lines) and lines[index].strip() != "```":
            body.append(lines[index])
            index += 1
        if index == len(lines):
            raise PackError(f"{report}:{start + 1}: unterminated supreme-claim block")
        try:
            claim = yaml.safe_load("\n".join(body)) or {}
        except yaml.YAMLError as exc:
            raise PackError(f"{report}:{start + 1}: malformed claim YAML: {exc.problem}") from None
        if not isinstance(claim, dict):
            raise PackError(f"{report}:{start + 1}: claim must be a mapping")
        required = ("id", "metric", "question", "role", "window", "benchmark")
        missing = [key for key in required if key not in claim]
        if missing:
            raise PackError(f"{report}:{start + 1}: claim missing {', '.join(missing)}")
        if claim["id"] in ids:
            raise PackError(f"{report}:{start + 1}: duplicate claim id `{claim['id']}`")
        ids.add(claim["id"])
        claim["source"] = {"path": str(report), "line": start + 1}
        claims.append(claim)
        index += 1
    manifest = json.loads(Path(topology).read_text())
    if "topology_digest" not in manifest:
        raise PackError(f"{topology}: no topology_digest")
    return {"topology_digest": manifest["topology_digest"], "surface": front["surface"], "claims": claims}


def write_pack(pack: dict, out: Path) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(pack, sort_keys=False, allow_unicode=True))
