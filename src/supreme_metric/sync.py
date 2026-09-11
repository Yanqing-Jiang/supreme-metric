"""Read-only implementation verification; observations never mutate a registry."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .adapters.databricks import DatabricksError, SDKStatementRunner, StatementRunner, observe_ref
from .compile import load_registry


def sync_databricks(root: Path, profile: str, warehouse_id: str, runner: StatementRunner | None = None) -> dict:
    runner = runner or SDKStatementRunner(profile, warehouse_id)
    registry = load_registry(Path(root))
    results = []
    for metric in registry["metrics"]:
        impl = metric.get("impl_ref", {})
        if impl.get("adapter") != "databricks":
            continue
        ref, expected = impl.get("ref", ""), impl.get("expected_fingerprint")
        result = {"metric": metric.get("id", "?"), "ref": ref, "status": "unverifiable"}
        if expected:
            result["expected_fingerprint"] = expected
        try:
            state, observed = observe_ref(ref, runner)
            if observed:
                result["observed_fingerprint"] = observed
            if not expected:
                result.update(status="unverifiable", reason="unbaselined")
            elif state == "missing-measure":
                result.update(status="drifted", reason="measure-missing")
            elif expected == observed:
                result.update(status="verified")
            else:
                result.update(status="drifted", reason="fingerprint-mismatch")
        except DatabricksError as exc:
            result.update(status="unverifiable", reason=str(exc))
        results.append(result)
    return {"schema_version": 1, "observed_at": datetime.now(timezone.utc).isoformat(), "results": results}
