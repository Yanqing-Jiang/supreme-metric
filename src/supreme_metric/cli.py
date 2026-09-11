import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .compile import CompileError, compile_registry, read_yaml, write_manifest
from .init import InitError, init_registry
from .lint import lint_pack
from .pack import PackError, emit_pack, write_pack
from .sync import sync_databricks
from .validate import ValidationError, validate_document, validate_registry


def _errors(errors) -> int:
    print(f"✗ {len(errors)} error(s)", file=sys.stderr)
    for error in errors:
        print(f"  {error}", file=sys.stderr)
    return 2


def _github_escape(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A").replace(":", "%3A").replace(",", "%2C")


def _lint_output(findings, pack, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps([f.to_dict() for f in findings], indent=2))
        return
    if fmt == "github":
        for finding in findings:
            attrs = []
            if finding.path:
                attrs.append(f"file={_github_escape(finding.path)}")
            if finding.line:
                attrs.append(f"line={finding.line}")
            attrs.append(f"title={finding.code}")
            print(f"::error {','.join(attrs)}::{_github_escape(finding.message)}")
        return
    for finding in findings:
        where = f"claim {finding.claim}" if finding.claim else "pack"
        location = f" {finding.path}:{finding.line}" if finding.path and finding.line else ""
        tail = f"  [{', '.join(finding.rulings)}]" if finding.rulings else ""
        print(f"{finding.code} {finding.severity:<7} {where:<10}{location} {finding.message}{tail}")
    errors = [f for f in findings if f.severity == "error"]
    print(("✓ " if not errors else "✗ ") + f"{len(pack.get('claims', []))} claims, {len(errors)} error(s), {len(findings) - len(errors)} warning(s)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="supreme", description="One metric per question sits above the rest.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    compile_p = sub.add_parser("compile", help="validate a registry and emit its topology manifest")
    compile_p.add_argument("registry", type=Path); compile_p.add_argument("--out", type=Path, default=Path("dist/topology.json"))
    lint_p = sub.add_parser("lint", help="check a claim pack against a compiled manifest")
    lint_p.add_argument("pack", type=Path); lint_p.add_argument("--topology", type=Path, default=Path("dist/topology.json"))
    lint_p.add_argument("--format", choices=("text", "json", "github"), default="text")
    lint_p.add_argument("--json", dest="format", action="store_const", const="json", help="alias for --format json")
    validate_p = sub.add_parser("validate", help="validate authored YAML with published JSON Schemas")
    validate_p.add_argument("target", type=Path); validate_p.add_argument("--kind", choices=("profile", "metric", "metrics", "question", "ruling", "claim-pack", "discovery", "sync"))
    init_p = sub.add_parser("init", help="create an empty registry around an approved profile")
    init_p.add_argument("directory", type=Path); init_p.add_argument("--profile", type=Path, required=True)
    inspect_p = sub.add_parser("inspect", help="inspect implementation metadata")
    inspect_sub = inspect_p.add_subparsers(dest="adapter", required=True)
    db_inspect = inspect_sub.add_parser("databricks")
    db_inspect.add_argument("--profile", required=True); db_inspect.add_argument("--warehouse-id", required=True); db_inspect.add_argument("--catalog", required=True); db_inspect.add_argument("--schema", required=True); db_inspect.add_argument("--out", type=Path, required=True)
    sync_p = sub.add_parser("sync", help="verify implementation fingerprints without writing the registry")
    sync_sub = sync_p.add_subparsers(dest="adapter", required=True)
    db_sync = sync_sub.add_parser("databricks")
    db_sync.add_argument("registry", type=Path); db_sync.add_argument("--profile", required=True); db_sync.add_argument("--warehouse-id", required=True); db_sync.add_argument("--out", type=Path); db_sync.add_argument("--require-verified", action="store_true")
    pack_p = sub.add_parser("pack", help="emit a digest-pinned claim pack from annotated Markdown")
    pack_p.add_argument("report", type=Path); pack_p.add_argument("--topology", type=Path, required=True); pack_p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "compile":
            manifest = compile_registry(args.registry); write_manifest(manifest, args.out)
            print(f"✓ {manifest['name']}: {len(manifest['questions'])} questions, {len(manifest['metrics'])} metrics, {len(manifest['edges'])} edges, {len(manifest['rulings'])} rulings")
            print(f"  {manifest['topology_digest']}  →  {args.out}")
            return 0
        if args.cmd == "validate":
            if not args.target.is_dir() and not args.kind:
                return _errors(["--kind is required when validating a single file"])
            errors = validate_registry(args.target) if args.target.is_dir() else validate_document(args.target, args.kind)
            if errors: return _errors(errors)
            print(f"✓ {args.target}: valid"); return 0
        if args.cmd == "init":
            init_registry(args.directory, args.profile); print(f"✓ initialized {args.directory}"); return 0
        if args.cmd == "inspect":
            from .adapters.databricks import inspect_databricks
            result = inspect_databricks(args.profile, args.warehouse_id, args.catalog, args.schema)
            args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(json.dumps(result, indent=2) + "\n")
            print(f"✓ discovered {len(result['relations'])} relation(s) → {args.out}"); return 0
        if args.cmd == "sync":
            result = sync_databricks(args.registry, args.profile, args.warehouse_id)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(json.dumps(result, indent=2) + "\n")
            for item in result["results"]: print(f"{item['status']:<12} {item['metric']} {item.get('reason', '')}")
            return 1 if args.require_verified and any(item["status"] != "verified" for item in result["results"]) else 0
        if args.cmd == "pack":
            result = emit_pack(args.report, args.topology); write_pack(result, args.out); print(f"✓ {len(result['claims'])} claims → {args.out}"); return 0
        manifest = json.loads(args.topology.read_text()); pack = read_yaml(args.pack)
        findings = lint_pack(pack, manifest, str(args.pack)); _lint_output(findings, pack, args.format)
        return 1 if any(f.severity == "error" for f in findings) else 0
    except (CompileError, ValidationError, InitError, PackError) as exc:
        return _errors(exc.errors if hasattr(exc, "errors") else [str(exc)])
    except OSError as exc:
        return _errors([str(exc)])
    except Exception as exc:
        # Vendor adapters deliberately expose concise operational errors, not SDK tracebacks.
        if exc.__class__.__name__ == "DatabricksError":
            return _errors([str(exc)])
        raise


if __name__ == "__main__":
    sys.exit(main())
