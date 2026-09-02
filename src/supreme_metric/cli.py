import argparse
import json
import sys
from pathlib import Path

import yaml

from . import __version__
from .compile import CompileError, compile_registry, write_manifest
from .lint import lint_pack


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="supreme", description="One metric per question sits above the rest.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile", help="validate a registry and emit its topology manifest")
    c.add_argument("registry", type=Path)
    c.add_argument("--out", type=Path, default=Path("dist/topology.json"))
    l = sub.add_parser("lint", help="check a claim pack against a compiled manifest")
    l.add_argument("pack", type=Path)
    l.add_argument("--topology", type=Path, default=Path("dist/topology.json"))
    l.add_argument("--json", action="store_true", help="emit findings as JSON")
    a = p.parse_args(argv)

    if a.cmd == "compile":
        try:
            manifest = compile_registry(a.registry)
        except CompileError as e:
            print(f"✗ {len(e.errors)} compile error(s)", file=sys.stderr)
            for err in e.errors:
                print(f"  {err}", file=sys.stderr)
            return 2
        write_manifest(manifest, a.out)
        nq, nm = len(manifest["questions"]), len(manifest["metrics"])
        print(f"✓ {manifest['name']}: {nq} questions, {nm} metrics, {len(manifest['edges'])} edges, {len(manifest['rulings'])} rulings")
        print(f"  {manifest['topology_digest']}  →  {a.out}")
        return 0

    manifest = json.loads(Path(a.topology).read_text())
    pack = yaml.safe_load(Path(a.pack).read_text()) or {}
    findings = lint_pack(pack, manifest)
    errors = [f for f in findings if f.severity == "error"]
    if a.json:
        print(json.dumps([f.to_dict() for f in findings], indent=2))
    else:
        for f in findings:
            where = f"claim {f.claim}" if f.claim else "pack"
            tail = f"  [{', '.join(f.rulings)}]" if f.rulings else ""
            print(f"{f.code} {f.severity:<7} {where:<10} {f.message}{tail}")
        n = len(pack.get("claims", []))
        print(("✓ " if not errors else "✗ ") + f"{n} claims, {len(errors)} error(s), {len(findings) - len(errors)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
