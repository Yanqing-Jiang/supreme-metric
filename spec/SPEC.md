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
| MT030 | closed surface: wrong count or order of scored questions |
| MT040 | window not allowed for the metric or question |
| MT041 | benchmark not allowed for the metric or on the surface |
| MT050 | denied comparison |
| MT060 | role not in the metric's `roles_allowed` |
| MT070 | pack digest does not match the manifest |

Severity is `error` or `warning`. The CLI exits non-zero on any error.
