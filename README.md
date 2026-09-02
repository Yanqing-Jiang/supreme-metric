<p align="center"><img src="docs/banner.svg" alt="Supreme Metric" width="100%"></p>

<p align="center"><b>A spec and a linter for governed metric topology.</b><br>
Which metric may answer which question, in what role, on what surface, against what benchmark.<br>
It never computes a number. It decides whether a number is allowed to speak.</p>

<p align="center"><code>pipx install supreme-metric</code> · <code>supreme compile</code> · <code>supreme lint</code></p>

---

## Eight claims walk into a meeting

> **SALES** · Sales are up 14%. · Share is up 1.8 pts.
> **FINANCE** · Margin is flat. · Forecast says a softer Q4.
> **MARKETING** · Impression share is 5.4 pts down. · New shoppers are up.
> **LOGISTICS** · Inventory is piling up. · Shipped items are blocked.

Every claim is true. Every claim is reproducible. Nobody can answer *"How's my business performance?"*

Supreme Metric gives each question exactly one metric that carries the verdict, the **score**. Every other number is a **companion** or a **diagnostic**. Owners, windows, benchmarks, and the pairs that must never be compared are written down once, in YAML, in git. A linter checks every claim against that before it reaches a page.

## The tree

```mermaid
flowchart TD
  T([Business performance]):::topic
  T --> Q1["Are we growing?"]:::sales
  T --> Q2["Are we winning?"]:::sales
  T --> Q3["Are we growing profitably?"]:::finance
  T --> Q4["Will it hold next quarter?"]:::finance
  T --> Q5["Are we capturing search demand?"]:::marketing
  T --> Q6["Are we recruiting customers?"]:::marketing
  T --> Q7["Can we serve the demand?"]:::logistics
  Q1 ==> M1["Net sales, consumption"]:::sales
  Q1 -.-> M8["Net sales, shipped"]:::finance
  Q2 ==> M2["Market share"]:::sales
  Q2 -.-> M9["Share of category growth"]:::marketing
  Q3 ==> M3["Contribution margin"]:::finance
  Q3 -.-> M10["Cost to serve"]:::logistics
  Q4 ==> M4["Forecast vs. target"]:::finance
  Q4 -.-> M11["Open order backlog"]:::sales
  Q5 ==> M5["Search impression share"]:::marketing
  Q5 -.-> M12["Search click share"]:::marketing
  Q6 ==> M6["New-to-brand customers"]:::marketing
  Q6 -.-> M13["New shopper rate"]:::sales
  Q7 ==> M7["Inventory weeks of cover"]:::logistics
  Q7 -.-> M14["Fill rate"]:::logistics
  classDef topic fill:#0E1218,stroke:#7DE0C8,color:#F2EFE8
  classDef sales fill:#1D2A12,stroke:#B8F27D,color:#F2EFE8
  classDef finance fill:#2C2410,stroke:#F5C542,color:#F2EFE8
  classDef marketing fill:#141F36,stroke:#8AB4FF,color:#F2EFE8
  classDef logistics fill:#331510,stroke:#FF4D2E,color:#F2EFE8
```

Thick line: the score. Dotted line: the sibling. Color: the owner of the verdict. This picture is not drawn by hand; it is what `supreme compile` derives from the seven question files in [`registry/questions/`](registry/questions).

## Three files

<table>
<tr><th>question</th><th>metric</th><th>ruling</th></tr>
<tr><td>

```yaml
# registry/questions/growing.yaml
id: growing
label: Are we growing?
surface: weekly_leadership
order: 1
score: sales.net_sales_consumption
companions: [finance.net_sales_shipped]
prohibited:
  - metric: sales.units
    reason: Units are not a leadership metric
```

</td><td>

```yaml
# registry/metrics/sales.yaml
- id: sales.net_sales_consumption
  label: Net sales, consumption
  owner: sales
  universe: retailer_sell_out
  grain: week x bu
  roles_allowed: [score, companion]
  windows: [p4w, fytd]
  benchmarks: [iya]
  not_comparable_with:
    - metric: finance.net_sales_shipped
```

</td><td>

```yaml
# registry/rulings/finance/
#   RULING-2026-07-01-....yaml
id: RULING-2026-07-01-CONSUMPTION-IS-GROWTH
date: 2026-07-01
owner: finance
statement: Growth is consumption.
  Shipped sales sit beside it and
  are never netted against it.
applies_to: [growing]
```

</td></tr>
</table>

A `profile.yaml` names your vocabulary: owners, surfaces, windows, benchmarks. Nothing in the tool knows what `p4w` or `iya` means. Nothing in the tool knows there are seven questions.

## Five minutes

```bash
git clone https://github.com/Yanqing-Jiang/supreme-metric && cd supreme-metric
pipx install .                                  # or: pip install -e ".[dev]"

supreme compile registry --out dist/topology.json
# ✓ reference-sales-org: 7 questions, 16 metrics, 19 edges, 7 rulings
#   sha256:…  →  dist/topology.json

supreme lint fixtures/clean/pack.yaml --topology dist/topology.json
# ✓ 14 claims, 0 error(s), 0 warning(s)

supreme lint fixtures/invalid/MT041-wow-benchmark.yaml --topology dist/topology.json
# MT041 error   claim c1   benchmark `wow` not allowed for `sales.net_sales_consumption`; allowed: iya  [RULING-…]
# ✗ 14 claims, 1 error(s), 0 warning(s)
```

A **claim pack** is what you lint. One entry per number a report wants to show:

```yaml
surface: weekly_leadership
claims:
  - {id: c1, owner: sales, text: Sales are up 14%.,
     metric: sales.net_sales_consumption, question: growing, role: score, window: p4w, benchmark: iya}
```

| code | the claim is rejected because |
|---|---|
| `MT010` | it names no metric |
| `MT020` | its metric is not the score, companion, or diagnostic for that question |
| `MT021` | the question was scored without its required companion |
| `MT030` | a closed surface got the wrong count or order of scored questions |
| `MT040` / `MT041` | the window or benchmark is not allowed there |
| `MT050` | it compares two metrics a ruling says are not comparable |
| `MT060` | the metric may never play that role |
| `MT070` | the pack was pinned to a different compile |

Every code has one fixture in [`fixtures/invalid/`](fixtures/invalid) that must keep failing. CI runs them all.

## Start yours

```bash
mkdir -p my-registry/{questions,metrics,rulings}
cp profiles/minimal.yaml my-registry/profile.yaml   # rename one owner, one surface, one window, one benchmark
```

Write one question. Write its two metrics. Write one ruling saying why. Compile.

```bash
supreme compile my-registry --out dist/mine.json
```

That is the whole product loop. [`examples/minimal-registry/`](examples/minimal-registry) is that loop, finished, in six small files. Put the registry in git, point `CODEOWNERS` at the owner of each metric file, and a pull request becomes the approval workflow. `impl_ref` on a metric can point at a Databricks metric view or a versioned SQL file; that is optional, and `compile` and `lint` never need credentials.

## What it is not

**Not Atlan.** No crawler, no lineage, no access control. It catalogs only what a page is allowed to say.
**Not dbt MetricFlow or Cube.** It does not define joins, compute, cache, or serve a metric.
**Not a BI tool.** No charts. It runs before the chart.

## Roadmap

| | |
|---|---|
| **M1** | spec, neutral profile, reference registry, `supreme compile` with a stable digest ✓ |
| **M2** | claim-pack linter, ten fixtures, CI, CODEOWNERS flow ✓ |
| **M3** | `supreme sync databricks`: inspect Unity Catalog metric views, report verified / drifted / unverifiable |
| **M4** | markdown reader that emits a claim pack; the landing page that renders `dist/topology.json` |

## License

Apache-2.0
