"""Optional JSON Schema validation for authored Supreme Metric documents."""
from __future__ import annotations

import importlib.resources
import json
from pathlib import Path
from typing import Any

from .compile import CompileError, read_yaml

KINDS = {"profile", "metric", "metrics", "question", "ruling", "claim-pack", "discovery", "sync"}


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


def _schemas() -> dict[str, dict[str, Any]]:
    """Load the complete local schema set so references never need a network fetch."""
    checkout = Path(__file__).resolve().parents[2] / "schema"
    if checkout.is_dir():
        files = sorted(checkout.glob("*.schema.json"))
        return {path.name.removesuffix(".schema.json"): json.loads(path.read_text()) for path in files}

    schema_dir = importlib.resources.files("supreme_metric").joinpath("schema")
    files = sorted(
        (path for path in schema_dir.iterdir() if path.name.endswith(".schema.json")),
        key=lambda path: path.name,
    )
    return {path.name.removesuffix(".schema.json"): json.loads(path.read_text()) for path in files}


def _normalise(value: Any) -> Any:
    """PyYAML turns ISO dates into date objects; JSON Schema operates on JSON."""
    if hasattr(value, "isoformat") and value.__class__.__module__ == "datetime":
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _normalise(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalise(v) for v in value]
    return value


def validate_document(path: Path, kind: str) -> list[str]:
    if kind not in KINDS:
        raise ValidationError([f"unknown document kind `{kind}`"])
    try:
        doc = _normalise(read_yaml(Path(path)))
    except CompileError as exc:
        raise ValidationError(exc.errors) from None
    try:
        import jsonschema
        from referencing import Registry, Resource
        from referencing.exceptions import Unresolvable, Unretrievable
        from referencing.jsonschema import DRAFT202012
    except ImportError as exc:
        raise ValidationError(['JSON Schema support is optional; install it with pip install "supreme-metric[schema]".']) from exc
    schemas = _schemas()
    if kind not in schemas:
        raise ValidationError([f"no schema is published for `{kind}`"])
    try:
        registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema, default_specification=DRAFT202012))
            for schema in schemas.values()
        )
        validator = jsonschema.Draft202012Validator(schemas[kind], registry=registry)
        errors = []
        for error in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
            loc = ".".join(str(p) for p in error.absolute_path) or "document"
            errors.append(f"{path}: {loc}: {error.message}")
        return errors
    except (jsonschema.exceptions.SchemaError, jsonschema.exceptions.ValidationError, Unresolvable, Unretrievable) as exc:
        message = str(exc).splitlines()[0] or exc.__class__.__name__
        raise ValidationError([f"{path}: schema validation failed: {message}"]) from None


def validate_registry(root: Path) -> list[str]:
    root = Path(root)
    paths: list[tuple[Path, str]] = [(root / "profile.yaml", "profile")]
    paths += [(p, "metrics") for p in sorted((root / "metrics").glob("*.yaml"))]
    paths += [(p, "question") for p in sorted((root / "questions").glob("*.yaml"))]
    paths += [(p, "ruling") for p in sorted((root / "rulings").rglob("*.yaml"))]
    errors: list[str] = []
    for path, kind in paths:
        if not path.exists():
            errors.append(f"{path}: missing")
        else:
            errors.extend(validate_document(path, kind))
    return errors
