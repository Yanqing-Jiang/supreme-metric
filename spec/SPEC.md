# Supreme Metric spec, version 1

Three authored object types, one profile, two interchange documents, one derived manifest.

## Layers

| layer | who writes it | contains |
|---|---|---|
| **spec** | this repo | shapes, role semantics, finding codes, digest rules |
| **profile** | one organization | vocabulary: owners, surfaces, windows, benchmarks, display |
| **registry** | one organization | questions, metrics, rulings |

The spec never enumerates an organization's vocabulary. `p4w`, `iya`, team names, and the number of questions are registry and profile content.

## Roles

| role | meaning |
|---|---|
| `score` | the one metric that carries the verdict for a question on a surface |
| `companion` | must be read beside the score; may not decide or recolor it |
| `diagnostic` | explains movement in the score; never a scored row |
| `context` | supplies non-verdict context; never on a scorecard |

## profile.yaml

```yaml
spec_version: 1
name: string
owners:     {id: {label, color?}}
surfaces:   {id: {label, cadence, closed: bool}}
windows:    {id: {label, kind: flow|snapshot}}
benchmarks: {id: {label, allowed_on_surfaces?: [surface ids]}}
display:    {currency?, magnitude?: words|symbols}
```

## metric

Required: `id`, `label`, `definition`, `owner`, `universe`, `grain`, `roles_allowed`, `windows`, `benchmarks`.
Optional: `not_comparable_with: [{metric, reason}]`, `reason_codes`, `freshness_expectation`, `impl_ref: {adapter, ref, expected_fingerprint?}`, `rulings`.
Metrics are authored as a list under `metrics:` in one file per owner.

## question

Required: `id`, `label`, `purpose`, `surface`, `order`, `score`, `companions`.
Optional: `diagnostics`, `prohibited: [{metric, reason}]`, `windows`, `verdicts`, `rulings`.
One file per question. The set of questions on a surface, their count, and their order are derived from these files.

## ruling

Required: `id`, `date`, `owner`, `statement`, `applies_to`. Optional: `supersedes`, `source`.
Append-only. The checked-in registry is authoritative; rulings are evidence for why it looks the way it does and are never replayed.

## Compile

`supreme compile <registry>` validates every reference, derives edges (`scores`, `companion_of`, `diagnoses`, `prohibited`, `not_comparable_with`), and emits `topology.json` with a `topology_digest`: sha256 over the canonical JSON of the manifest body (sorted keys, no whitespace). Two compiles of the same files on any machine produce the same digest.

Authored documents use `spec_version: 1`; unknown top-level keys and duplicate identifiers are rejected. Ruling `applies_to` and benchmark `allowed_on_surfaces` references must resolve in the profile or registry. Published Draft 2020-12 schemas in `schema/` make the same document shapes independently checkable with `supreme validate`.

## Claim pack

```yaml
topology_digest?: sha256:…
surface: surface id
claims:
  - {id, owner?, text?, metric, question, role, window, benchmark, compares_with?: [metric ids]}
```

## Findings

| code | check |
|---|---|
| MT001 | unknown reference (metric, question, owner, window, benchmark, surface) |
| MT010 | claim names no metric |
| MT020 | metric is not assigned that role for that question, or is prohibited there |
| MT021 | question scored without a required companion |
| MT022 | question scored more than once in one pack |
| MT023 | claim's question is not on the pack surface |
| MT030 | closed surface: wrong count or order of scored questions |
| MT040 | window not allowed for the metric or question |
| MT041 | benchmark not allowed for the metric or on the surface |
| MT050 | denied comparison |
| MT060 | role not in the metric's `roles_allowed` |
| MT070 | pack digest does not match the manifest |

Severity is `error` or `warning`. The CLI exits non-zero on any error.

## Implementation evidence

`impl_ref` is evidence of an implementation, not proof of a result. Databricks references use `catalog.schema.view#measure`; each identifier component is quoted independently when inspected. `supreme sync databricks` fingerprints canonical JSON containing the reference and the complete parsed metric-view YAML as `dbmv-v1:sha256:<hex>`. A matching approved fingerprint is `verified`; a readable mismatch or missing measure is `drifted`; unbaselined, denied, incomplete, or unsupported metadata is `unverifiable`. Sync is read-only and never accepts a baseline automatically.

## Annotated reports

`supreme pack` reads YAML front matter containing `surface` and ordered fenced `supreme-claim` YAML blocks. It requires unique claim IDs, carries block `text`, records `{path, line}` source data, and pins the compiled topology digest. It intentionally does not infer claims from prose.
