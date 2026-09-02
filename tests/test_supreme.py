import json
from pathlib import Path

import pytest
import yaml

from supreme_metric.compile import compile_registry
from supreme_metric.lint import lint_pack

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def manifest():
    return compile_registry(ROOT / "registry")


def test_reference_topology_shape(manifest):
    assert len(manifest["questions"]) == 7
    governed = {e["from"] for e in manifest["edges"] if e["kind"] in ("scores", "companion_of", "diagnoses")}
    assert len(governed) == 14
    assert sum(e["kind"] == "scores" for e in manifest["edges"]) == 7
    assert [q["order"] for q in manifest["questions"]] == list(range(1, 8))


def test_digest_is_stable():
    a = compile_registry(ROOT / "registry")
    b = compile_registry(ROOT / "registry")
    assert a["topology_digest"] == b["topology_digest"]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_minimal_example_compiles_and_lints_clean():
    m = compile_registry(ROOT / "examples" / "minimal-registry")
    pack = yaml.safe_load((ROOT / "examples" / "minimal-registry" / "pack.yaml").read_text())
    assert lint_pack(pack, m) == []


def test_clean_pack_has_no_findings(manifest):
    pack = yaml.safe_load((ROOT / "fixtures" / "clean" / "pack.yaml").read_text())
    assert [f.to_dict() for f in lint_pack(pack, manifest)] == []


@pytest.mark.parametrize("path", sorted((ROOT / "fixtures" / "invalid").glob("MT*.yaml")), ids=lambda p: p.stem)
def test_each_invalid_fixture_raises_its_code(path, manifest):
    expected = path.stem.split("-")[0]
    pack = yaml.safe_load(path.read_text())
    codes = {f.code for f in lint_pack(pack, manifest)}
    assert expected in codes, f"{path.name} produced {codes}"
