# A sales team pilot

One question, from an argument in a meeting to a governed line in the weekly review, with a deliberate drift at the end so the team sees what the tool is for. Two working sessions. No new infrastructure.

The example registry this pilot produces is in [`../examples/databricks-sales/`](../examples/databricks-sales/).

## The argument

"Are we growing?" Sales says yes: consumption is up 14% on a four-week basis. Finance says the shipped number is flat and that is what hits the P&L. Both are right. The leadership page shows both, colored differently, and the meeting spends ten minutes on which one counts.

## Session one: the question

**Scope.** Surface: `weekly_leadership`, closed. First question: `growing`. Owners: Sales for consumption, Finance for shipped. Warehouse scope: `sales_gold.leadership`. Profile `sales`, serverless warehouse.

**Discover.** `supreme inspect databricks` finds two metric views, `net_sales_consumption` and `net_sales_shipped`, each with a `net_sales` measure, plus a `units_sold` table with no metric view.

**Propose.** The agent writes `adoption/proposal.md`:

- Score: Net sales, consumption. Owner Sales. Windows P4W and FYTD. Benchmark IYA.
- Companion: Net sales, shipped. Owner Finance. Not comparable with the score: different universe, different timing.
- Prohibited on this question: Units sold. Not a leadership metric. No metric view exists for it anyway.
- Open: does fiscal year start in July? Finance confirms.

**Decide.** The head of sales and the finance lead agree: growth is consumption, shipped sits beside it, the two are never netted. That sentence becomes `RULING-<date>-CONSUMPTION-IS-GROWTH`.

**Author and check.** `supreme init`, one question file, two metric files, one ruling. `supreme validate`, `supreme compile`. The topology has one question, two metrics, one companion edge, one prohibition, one denied comparison.

**Baseline.** `supreme sync` reports both metrics `unbaselined`. Each owner looks at their view's definition and the fingerprint. Both approve. Fingerprints go into the registry. Sync again: two `verified`.

**Enforce.** `CODEOWNERS`: `metrics/sales.yaml` to the sales analytics lead, `metrics/finance.yaml` to the finance lead, `questions/` and `rulings/` to the surface owner. CI runs validate, compile, lint. Branch protection requires code-owner review.

## Session two: the report

The weekly page already exists as Markdown. The author wraps the growth line:

````markdown
```supreme-claim
id: growth-score
metric: sales.net_sales_consumption
question: growing
role: score
window: p4w
benchmark: iya
text: Net sales are up 14% versus a year ago on a four-week basis.
```

```supreme-claim
id: growth-companion
metric: finance.net_sales_shipped
question: growing
role: companion
window: p4w
benchmark: iya
text: Shipped sales are flat versus a year ago.
```
````

`supreme pack`, `supreme lint`: clean. The page ships with two governed numbers and a footnote that the rest are not yet claims. Next week the author annotates two more.

## What changes in the meeting

The growth line has one color. The shipped line sits under it, labeled as a companion. When someone asks why shipped does not count, the answer is a link to the ruling, dated, with both owners' approval in the pull request. The ten minutes go somewhere else.

## The drift exercise

Two weeks in, have the finance lead change the `net_sales_shipped` view: add a returns adjustment to the measure expression. Do not tell the agent or the analytics team.

The scheduled `supreme sync --require-verified` fails that night: `finance.net_sales_shipped: drifted`. The failure names the metric, the owner, the approved fingerprint, and the observed one.

The finance lead has two honest options: revert the view, or open a pull request with the new fingerprint and a ruling that says returns are now netted from shipped sales. Either way, the change is visible, owned, and dated. That is what the pilot was for.

## Then

Add the second question in the same way. "Are we winning?" is usually next, because share has the same two-definitions problem as growth. Seven questions is a reasonable steady state for a closed weekly surface; the reference registry has that shape. Resist the eighth.

## What this pilot does not do

It does not prove that 14% is correct. It proves that the number is the approved definition, in the approved role, against the approved benchmark, on a page whose questions and order are fixed. Arithmetic is the warehouse's job. This is the referee's.
