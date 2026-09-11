"""Scoped, read-only Databricks metadata inspection and metric-view verification."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Protocol

import yaml


class DatabricksError(Exception):
    pass


@dataclass
class StatementResult:
    rows: list[dict[str, Any]]
    truncated: bool = False


class StatementRunner(Protocol):
    def run(self, statement: str, parameters: dict[str, str] | None = None) -> StatementResult: ...


def quote_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def qualified(catalog: str, schema: str, relation: str) -> str:
    return ".".join(quote_identifier(part) for part in (catalog, schema, relation))


def parse_ref(ref: str) -> tuple[str, str, str, str]:
    try:
        relation, measure = ref.split("#", 1)
        catalog, schema, view = relation.split(".")
    except ValueError:
        raise DatabricksError(f"invalid Databricks ref `{ref}`; expected catalog.schema.view#measure") from None
    if not all((catalog, schema, view, measure)):
        raise DatabricksError(f"invalid Databricks ref `{ref}`; components cannot be empty")
    return catalog, schema, view, measure


class SDKStatementRunner:
    """The only class that imports databricks-sdk; polling and chunks are bounded."""
    def __init__(self, profile: str, warehouse_id: str, max_polls: int = 60):
        try:
            from databricks.sdk import WorkspaceClient
        except ImportError as exc:
            raise DatabricksError('Databricks support is optional; install it with pip install "supreme-metric[databricks]".') from exc
        self.client = WorkspaceClient(profile=profile)
        self.warehouse_id, self.max_polls = warehouse_id, max_polls
        self.workspace_host = getattr(getattr(self.client, "config", None), "host", None)

    @staticmethod
    def _value(obj: Any, key: str, default=None):
        return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

    def run(self, statement: str, parameters: dict[str, str] | None = None) -> StatementResult:
        # The API accepts named parameters; keeping them separate prevents values becoming SQL.
        params = [{"name": name, "value": value} for name, value in (parameters or {}).items()]
        response = self.client.statement_execution.execute_statement(
            statement=statement, warehouse_id=self.warehouse_id, parameters=params or None, wait_timeout="10s",
        )
        for _ in range(self.max_polls):
            state = self._value(self._value(response, "status"), "state", "")
            if str(state).upper() in {"SUCCEEDED", "FAILED", "CANCELED", "CLOSED"}:
                break
            time.sleep(1)
            response = self.client.statement_execution.get_statement(self._value(response, "statement_id"))
        else:
            raise DatabricksError("statement timed out while polling metadata")
        status = str(self._value(self._value(response, "status"), "state", "")).upper()
        if status != "SUCCEEDED":
            raise DatabricksError(str(self._value(self._value(response, "status"), "error", status)))
        result = self._value(response, "result")
        manifest = self._value(result, "manifest", {})
        schema = self._value(manifest, "schema", {})
        columns = [self._value(c, "name") for c in self._value(schema, "columns", []) or []]
        data = self._value(result, "data_array", []) or []
        rows = [dict(zip(columns, row)) for row in data]
        chunk = self._value(result, "next_chunk_index")
        while chunk is not None:
            more = self.client.statement_execution.get_statement_result_chunk_n(self._value(response, "statement_id"), chunk)
            data = self._value(more, "data_array", []) or []
            rows.extend(dict(zip(columns, row)) for row in data)
            chunk = self._value(more, "next_chunk_index")
        return StatementResult(rows=rows, truncated=bool(self._value(result, "truncated", False)))


def _rows(result: StatementResult) -> list[dict[str, Any]]:
    if result.truncated:
        raise DatabricksError("metadata result was truncated")
    return result.rows


def _describe(runner: StatementRunner, catalog: str, schema: str, relation: str) -> tuple[dict[str, Any], bool]:
    rows = _rows(runner.run(f"DESCRIBE TABLE EXTENDED {qualified(catalog, schema, relation)} AS JSON"))
    if not rows:
        raise DatabricksError("DESCRIBE returned no metadata")
    raw = rows[0].get("json") or rows[0].get("result") or next(iter(rows[0].values()))
    if isinstance(raw, str):
        try:
            metadata = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DatabricksError("unsupported metadata: DESCRIBE did not return JSON") from exc
    elif isinstance(raw, dict):
        metadata = raw
    else:
        raise DatabricksError("unsupported metadata: DESCRIBE did not return an object")
    view_text = metadata.get("view_text") or metadata.get("viewText")
    kind = " ".join(str(metadata.get(key, "")) for key in ("type", "table_type", "language")).lower()
    is_metric = "metric" in kind or bool(metadata.get("measure_columns") or metadata.get("measures"))
    return metadata, is_metric


def inspect_databricks(profile: str, warehouse_id: str, catalog: str, schema: str, runner: StatementRunner | None = None) -> dict:
    runner = runner or SDKStatementRunner(profile, warehouse_id)
    params = {"catalog": catalog, "schema": schema}
    # These parameterized queries are intentionally metadata-only.
    failures = []
    try:
        _rows(runner.run("SELECT catalog_name, schema_name, schema_owner FROM system.information_schema.schemata WHERE catalog_name = :catalog", {"catalog": catalog}))
        tables = _rows(runner.run("SELECT table_catalog, table_schema, table_name, table_type, table_owner, comment FROM system.information_schema.tables WHERE table_catalog = :catalog AND table_schema = :schema", params))
        columns = _rows(runner.run("SELECT table_name, column_name, data_type, ordinal_position, comment FROM system.information_schema.columns WHERE table_catalog = :catalog AND table_schema = :schema", params))
    except DatabricksError as exc:
        return {"schema_version": 1, "workspace_host": getattr(runner, "workspace_host", None), "scope": {"catalog": catalog, "schema": schema}, "observed_at": datetime.now(timezone.utc).isoformat(), "relations": [], "failures": [{"object": f"{catalog}.{schema}", "error": str(exc)}]}
    by_table: dict[str, list[dict[str, Any]]] = {}
    for col in columns:
        by_table.setdefault(col.get("table_name", ""), []).append(col)
    relations = []
    for table in tables:
        name = table.get("table_name")
        relation = {"catalog": table.get("table_catalog", catalog), "schema": table.get("table_schema", schema), "name": name, "table_type": table.get("table_type", ""), "owner": table.get("table_owner"), "comment": table.get("comment"), "columns": by_table.get(name, []), "definition": None, "metric_view": False, "view_text": None}
        try:
            definition, metric_view = _describe(runner, catalog, schema, name)
            relation.update(definition=definition, metric_view=metric_view, view_text=definition.get("view_text") or definition.get("viewText"))
        except DatabricksError as exc:
            failures.append({"object": f"{catalog}.{schema}.{name}", "error": str(exc)})
        relations.append(relation)
    return {"schema_version": 1, "workspace_host": getattr(runner, "workspace_host", None), "scope": {"catalog": catalog, "schema": schema}, "observed_at": datetime.now(timezone.utc).isoformat(), "relations": relations, "failures": failures}


def metric_view_fingerprint(ref: str, view_text: str) -> str:
    try:
        parsed = yaml.safe_load(view_text)
    except yaml.YAMLError as exc:
        raise DatabricksError("unsupported metric-view YAML") from exc
    body = json.dumps({"ref": ref, "metric_view": parsed}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "dbmv-v1:sha256:" + sha256(body.encode()).hexdigest()


def observe_ref(ref: str, runner: StatementRunner) -> tuple[str, str | None]:
    catalog, schema, view, measure = parse_ref(ref)
    metadata, is_metric = _describe(runner, catalog, schema, view)
    text = metadata.get("view_text") or metadata.get("viewText")
    if not is_metric or not isinstance(text, str):
        raise DatabricksError("unsupported metadata: relation is not a readable metric view")
    parsed = yaml.safe_load(text) or {}
    measures = parsed.get("measures", []) if isinstance(parsed, dict) else []
    names = {m.get("name") for m in measures if isinstance(m, dict)}
    if measure not in names:
        return "missing-measure", metric_view_fingerprint(ref, text)
    return "ok", metric_view_fingerprint(ref, text)
