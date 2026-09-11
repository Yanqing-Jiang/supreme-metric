import json
from pathlib import Path

import pytest
import yaml

from supreme_metric.adapters.databricks import StatementResult, inspect_databricks, metric_view_fingerprint
from supreme_metric.compile import compile_registry
from supreme_metric.init import init_registry
from supreme_metric.lint import lint_pack
from supreme_metric.pack import emit_pack
from supreme_metric.sync import sync_databricks
from supreme_metric.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_new_pack_findings():
    manifest = compile_registry(ROOT / "registry")
    duplicate = yaml.safe_load((ROOT / "fixtures/invalid/MT022-duplicate-score.yaml").read_text())
    assert "MT022" in {f.code for f in lint_pack(duplicate, manifest)}
    # Use the repository question against the same valid surface, then alter its surface in a copy.
    other = {"surface": "weekly_leadership", "claims": [{"id": "x", "metric": "sales.net_sales_consumption", "question": "activation", "role": "score", "window": "p4w", "benchmark": "iya"}]}
    changed = dict(manifest)
    changed["questions"] = manifest["questions"] + [{"id": "activation", "surface": "other", "order": 1, "score": "sales.net_sales_consumption", "companions": []}]
    assert "MT023" in {f.code for f in lint_pack(other, changed)}


def test_schemas_validate_authored_documents_when_extra_installed():
    pytest.importorskip("jsonschema")
    from supreme_metric.validate import validate_document, validate_registry
    assert validate_registry(ROOT / "registry") == []
    assert validate_registry(ROOT / "examples/minimal-registry") == []
    assert validate_registry(ROOT / "examples/databricks-sales/registry") == []
    assert validate_document(ROOT / "fixtures/clean/pack.yaml", "claim-pack") == []
    for path in sorted((ROOT / "registry/metrics").glob("*.yaml")):
        assert validate_document(path, "metrics") == []


def test_metrics_schema_reports_unknown_keys_at_the_authored_path(tmp_path):
    pytest.importorskip("jsonschema")
    from supreme_metric.validate import validate_document

    path = tmp_path / "metrics.yaml"
    path.write_text("metrics:\n  - id: sales.net_sales\n    unexpected: true\n")
    errors = validate_document(path, "metrics")
    assert errors
    assert errors[0].startswith(f"{path}: metrics.0:")
    assert "Additional properties are not allowed" in errors[0]


def test_unresolvable_schema_reference_returns_a_concise_cli_error(tmp_path, monkeypatch, capsys):
    pytest.importorskip("jsonschema")
    import supreme_metric.validate as validation

    schemas = validation._schemas()
    schemas["claim-pack"] = {"$id": "https://supreme-metric.dev/schema/broken.schema.json", "$ref": "missing.schema.json"}
    monkeypatch.setattr(validation, "_schemas", lambda: schemas)
    path = tmp_path / "pack.yaml"
    path.write_text("surface: weekly_leadership\nclaims: []\n")

    assert main(["validate", str(path), "--kind", "claim-pack"]) == 2
    error = capsys.readouterr().err
    assert "schema validation failed" in error
    assert "traceback" not in error.lower()


def test_init_accepts_first_authored_registry(tmp_path):
    target = tmp_path / "registry"
    init_registry(target, ROOT / "profiles/minimal.yaml")
    for rel in ("questions/activation.yaml", "metrics/product.yaml", "rulings/product/RULING-001-ACTIVATION.yaml"):
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((ROOT / "examples/minimal-registry" / rel).read_text())
    assert compile_registry(target)["name"] == "my-org"
    assert (tmp_path / "CODEOWNERS.template").exists()


def test_pack_emits_clean_example(tmp_path):
    topology = tmp_path / "topology.json"
    topology.write_text(json.dumps(compile_registry(ROOT / "examples/databricks-sales/registry")))
    pack = emit_pack(ROOT / "examples/databricks-sales/report.md", topology)
    assert [claim["id"] for claim in pack["claims"]] == ["revenue", "orders", "margin", "returns"]
    assert lint_pack(pack, json.loads(topology.read_text())) == []


class FakeRunner:
    workspace_host = "https://example.cloud.databricks.com"
    def __init__(self):
        self.metadata = json.loads((ROOT / "fixtures/databricks/metric_view.json").read_text())
    def run(self, statement, parameters=None):
        if "information_schema.schemata" in statement:
            return StatementResult([{"catalog_name": "sales_gold"}])
        if "information_schema.tables" in statement:
            return StatementResult([{"table_catalog": "sales_gold", "table_schema": "leadership", "table_name": "net_sales_consumption", "table_type": "VIEW", "table_owner": "sales", "comment": None}])
        if "information_schema.columns" in statement:
            return StatementResult([])
        return StatementResult([{"json": json.dumps(self.metadata)}])


def test_databricks_inspect_and_sync_fixture():
    runner = FakeRunner()
    discovery = inspect_databricks("ignored", "warehouse", "sales_gold", "leadership", runner)
    assert discovery["relations"][0]["metric_view"]
    result = sync_databricks(ROOT / "registry", "ignored", "warehouse", runner)
    states = {item["metric"]: item["status"] for item in result["results"]}
    assert states["sales.net_sales_consumption"] == "verified"
    assert states["sales.market_share"] == "drifted"
    assert states["sales.open_order_backlog"] == "unverifiable"


def test_malformed_yaml_is_located_without_traceback(tmp_path, capsys):
    broken = tmp_path / "broken.yaml"
    broken.write_text("surface: [\n")
    assert main(["validate", str(broken), "--kind", "claim-pack"]) == 2
    assert f"{broken}:2:" in capsys.readouterr().err
