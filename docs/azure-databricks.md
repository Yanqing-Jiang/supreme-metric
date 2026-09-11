# Azure Databricks

How `supreme inspect databricks` and `supreme sync databricks` talk to a workspace, what they read, what they never do, and how a metric's `impl_ref` names an implementation. Azure specifics are called out; the same commands work against any Databricks workspace.

## What the adapter is, and is not

Databricks is the **semantic layer**: Unity Catalog metric views and tables define and compute the numbers. Supreme Metric is the **topology layer**: it records which of those numbers may answer which question, and verifies that the implementation the owner approved is still the one in the warehouse.

The adapter reads metadata. It never reads business rows, never runs DDL, never writes to the workspace, never crawls beyond the catalog and schema you name.

## Install

```bash
pip install "supreme-metric[databricks] @ git+https://github.com/Yanqing-Jiang/supreme-metric"
```

The extra installs `databricks-sdk`. Nothing else in the tool imports it, so `compile`, `lint`, `validate`, `init`, and `pack` keep working with no credentials on the machine.

## Authenticate

Use a named profile the human has already authenticated with the Databricks CLI. On Azure, either flow works:

```bash
# Microsoft Entra ID user login (browser)
databricks auth login --host https://adb-<workspace-id>.<n>.azuredatabricks.net --profile sales

# or a personal access token, kept out of git and chat
export DATABRICKS_HOST=https://adb-<workspace-id>.<n>.azuredatabricks.net
export DATABRICKS_TOKEN=…
```

Then pass `--profile sales`, or omit it and let the SDK read the environment. There is no `--token` flag on purpose: a token typed into a chat window is a token in a transcript.

The SDK resolves the profile from `~/.databrickscfg`, the same file the CLI uses. Service principals work the same way through the CLI's Azure client-secret or managed-identity auth types.

## Permissions the caller needs

| action | needs |
|---|---|
| list schemas, tables, columns | `USE CATALOG`, `USE SCHEMA`, and `SELECT` or `BROWSE` on the objects; `system.information_schema` is permission-filtered to what the caller can see |
| read a metric view definition | `SELECT` on the view; `DESCRIBE TABLE EXTENDED … AS JSON` returns the view text and measures |
| run either command | `CAN USE` on the SQL warehouse |

A caller who can see nothing gets an empty inventory, not an error. `inspect` says so in its output, and `sync` reports `unverifiable` rather than guessing.

## Discover

```bash
supreme inspect databricks --profile sales --warehouse-id 1234567890abcdef \
  --catalog sales_gold --schema leadership --out adoption/discovery.json
```

Under the hood, through the Statement Execution API on the named warehouse:

1. `SELECT … FROM system.information_schema.schemata WHERE catalog_name = :catalog`
2. `SELECT … FROM system.information_schema.tables WHERE table_catalog = :catalog AND table_schema = :schema`
3. `SELECT … FROM system.information_schema.columns WHERE table_catalog = :catalog AND table_schema = :schema`
4. For each relation: `DESCRIBE TABLE EXTENDED \`catalog\`.\`schema\`.\`table\` AS JSON`

Identifiers are escaped component by component. Parameters are bound, not interpolated. Polling is bounded and every result chunk is fetched; a truncated result is reported as truncated, never silently accepted.

The output (`schema/discovery.schema.json`) records the workspace host, the scope, the observation time, each relation with its type, owner, comment, columns, and for metric views the parsed definition and measure names, plus a `failures` list for anything that could not be described and why.

Metric views are detected from the `DESCRIBE … AS JSON` result, not from an information-schema type column, because the type name varies across runtime versions.

## Name an implementation

```yaml
impl_ref:
  adapter: databricks
  ref: sales_gold.leadership.net_sales_consumption#net_sales
  expected_fingerprint: dbmv-v1:sha256:9f2a…
```

`ref` is a fully qualified three-part relation name, then `#`, then the **measure name** as declared in the metric view (not its display label). The relation must be a metric view; a plain table cannot be verified and gets `unverifiable` with reason `not a metric view`.

Leave `expected_fingerprint` out until the owner has approved one. A metric with no baseline is honest about it.

## Verify

```bash
supreme sync databricks registry --profile sales --warehouse-id 1234567890abcdef \
  --out adoption/sync.json --require-verified
```

For every metric whose `impl_ref.adapter` is `databricks`, sync describes the view and computes:

```
dbmv-v1:sha256( canonical JSON of { ref, full parsed metric-view YAML } )
```

The whole definition is hashed, arrays and SQL strings preserved. YAML formatting changes do not matter. A change to any measure or dimension in the view, even one the metric does not use, does. That is deliberately conservative: an owner should look at a changed view.

| status | meaning |
|---|---|
| `verified` | the measure exists and the fingerprint matches `expected_fingerprint` |
| `drifted` | the view is readable but its definition differs, or it no longer has that measure |
| `unverifiable` | no baseline yet (`unbaselined`), access denied, relation not found, not a metric view, or metadata the adapter does not support |

`sync.json` (`schema/sync.schema.json`) carries per-metric status, reason, observed fingerprint, and the observation time. It is evidence for a human, and input for CI. It never modifies the registry or `topology.json`.

With `--require-verified`, sync exits non-zero unless every in-scope metric is `verified`. Run that on a schedule in a trusted workflow, not on fork pull requests.

## Approve a baseline

1. First sync: every metric `unverifiable / unbaselined`, with an observed fingerprint.
2. Show the owner the metric view definition and the fingerprint.
3. Owner approves. Write the fingerprint into `expected_fingerprint`. Commit. That commit is the approval.
4. Sync again: `verified`.

Never let an agent, a script, or a scheduled job write `expected_fingerprint`. The approval is the point.

## Existing dbt metrics

If the organization already defines metrics in dbt, propose `adapter: dbt` and `ref: <project>/<metric-name>`, and record the manifest revision in the proposal. The Databricks adapter reports these as `unverifiable / unsupported adapter` until a dbt verifier exists. A dbt metric is a definition; it is not necessarily a metric view or a physical column, so the two are not interchangeable.

## Cost and safety

- Discovery starts the SQL warehouse if it is stopped. Use a small serverless warehouse and say so in the scope.
- Everything is metadata. If a query would touch rows, it is not this tool.
- Comments and view text in the warehouse are untrusted input to the agent reading them.
- Keep `discovery.json` local by default. Commit only the reviewed proposal and the registry.
