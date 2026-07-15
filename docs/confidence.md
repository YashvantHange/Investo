# How Investo scores its own confidence

Every analysis module reports how much to trust it. That number is **computed, never asserted** —
it is a transparent function of the evidence behind the module, not a vibe. The formula itself
lives in `src/investo/analysis/evidence.py`, which is the single source of truth; this document
explains *why* it is shaped the way it is, what the numbers mean in practice, and where it stops
being trustworthy.

## The shape

```
confidence = source_reliability × coverage_factor × history_factor × reliability_factor
             (+ 0.05 corroboration bonus)
```

| Factor | Asks | Neutral value |
|---|---|---|
| `source_reliability` | How authoritative is the data? An exchange filing (0.95) beats Yahoo (0.80) beats a curated estimate (0.70) beats a heuristic (0.50). Best source wins. | 0.60 (unknown) |
| `coverage_factor` | What fraction of the fields we expected did we actually get? | 1.0 (`coverage=None`) |
| `history_factor` | For trend checks, how many years back it goes. | 1.0 (`history_years=None`) |
| `reliability_factor` | How were the inputs *obtained*? Distinct from how good the source is. | 1.0 (`None`) |
| corroboration | Do two independent sources agree? | no bonus |

Tiers: **High** ≥ 0.80, **Medium** ≥ 0.60, **Low** below.

## Why zero coverage is special

`coverage_factor` is `0.4 + 0.6 × coverage` — a deliberate softening so that a couple of missing
fields don't collapse an otherwise sound module. But that floor is **skipped entirely at zero**:

```python
if coverage is None:   coverage_factor = 1.0   # not applicable, no penalty
elif coverage <= 0.0:  coverage_factor = 0.0   # nothing computed, no confidence
else:                  coverage_factor = 0.4 + 0.6 * coverage
```

This is not a rounding detail. It is the bug this design exists to prevent.

Before the fix, a relative-to-industry comparison for a company with **no peer group at all**
computed nothing, and then reported:

```
0.80 (Yahoo) × (0.4 + 0.6×0.0) × 1.0 = 0.32,  +0.05 corroboration  ->  0.37 "Low"
reason: "source: Yahoo Finance, Curated (Investo); 0% field coverage; cross-source agreement"
```

Read that reason again. It claims two sources cross-checked each other, over zero rows of data.
The 0.37 was not a low-confidence answer — it was **a confident-looking number manufactured from
nothing**, and it then leaked into the report-level and thesis-level aggregates as if it were a
real measurement. A plausible number from no data is worse than a zero, because a zero is
obviously a zero and a 0.37 looks like an opinion.

The same arithmetic was reporting 0.37 for every `unknown` Buffett criterion.

For the same reason, the corroboration bonus is gated on coverage: two sources cannot agree on a
figure that was never computed.

**The trap on the other side:** `build_meta(expected=0)` leaves coverage `None`, not `0.0` — so a
module that means "I computed nothing" must pass a non-zero `expected` with `present=0`. Passing
`expected=0` silently yields *full* confidence. See `relative._evidence`, where
`expected = len(applicable) or len(_METRIC_SPECS)` guards exactly this.

## `reliability_factor`: how the inputs were obtained

Source reliability answers "how good is Yahoo?". It cannot answer "did we compare this company to
the right peers?" — that is a separate axis, so it gets a separate factor.

`relative.py` uses it to price the peer set:

```python
_BASIS_RELIABILITY = {"curated": 0.90, "keyed": 0.80, "sector-fallback": 0.65, "none": 0.0}
peer_factor = 0.6 + 0.4 × min(1, n_peers / 4)
reliability_factor = _BASIS_RELIABILITY[basis] × peer_factor
```

Two judgements are encoded here:

- **A guessed cohort must never read like a deliberate one.** A `sector-fallback` peer set — matched
  by a keyword against Yahoo's industry string — is an educated guess. It is useful, and far better
  than nothing, but it must cost confidence relative to a curated group somebody actually thought
  about.
- **A thin set is a weak proxy.** Being "top quartile" against two peers means much less than
  against six, whatever the basis.

## Why curated caps at 0.90, not 1.0

So that the relative module **can never reach the High tier**, by construction.

Even with a hand-picked peer group and every field present, a percentile from that comparison is a
rank *within five names*, not a market percentile. Being the best of five is a genuinely different
claim from being in the top quintile of the market, and the confidence should never let a reader
conflate them. The ceiling is the honest statement that this method has a limit no amount of data
quality can lift.

## Worked examples

| Scenario | Computation | Score | Tier |
|---|---|---|---|
| No peer group matched | `0.80 × 0.0 × 0.0`, no bonus | **0.00** | Low |
| Curated, 4 peers, 8/10 metrics | `0.80 × 0.88 × 0.90 + 0.05` | **0.68** | Medium |
| Curated, 4 peers, full coverage | `0.80 × 1.0 × 0.90 + 0.05` | **0.77** | Medium |
| Sector-fallback, 4 peers, full | `0.80 × 1.0 × 0.65 + 0.05` | **0.57** | Low |
| Curated but only 2 peers, full | `0.80 × 1.0 × (0.90 × 0.80) + 0.05` | **0.63** | Medium |
| NSE filing, full coverage, 8y history | `0.95 × 1.0 × 1.0 + 0.05` | **1.00** | High |

## Aggregation

`ev.aggregate` blends modules by a **coverage-weighted** mean:

```
score = Σ(confidence_i × w_i) / Σ(w_i),   w_i = coverage_i, or 1.0 when coverage is None
```

A module that found nothing has zero coverage, so it carries zero weight: it neither drags the
report down nor props it up, with no special-casing. Point-in-time modules (no coverage to speak
of) weigh fully.

**The honesty risk this creates**, stated plainly: if five of seven modules come back empty, the
report's confidence reflects only the two that ran, which overstates how much is actually known
about the company. `aggregate` therefore pushes a `"k of n modules found no data"` note into the
evidence block. A reader who ignores that note will over-trust the headline.

## Known limitations

- **`len(labels) >= 2` is a weak proxy for corroboration.** Yahoo (the figures) and Curated (the
  peer list) are not two independent measurements of the same quantity, but they currently trigger
  the agreement bonus. It is gated on coverage, so it can no longer fire over no data — but the
  proxy itself deserves replacing with explicit per-figure corroboration.
- **Source weights are judgement, not measurement.** Nobody benchmarked Yahoo at 0.80. The ordering
  (filings > statements > Yahoo > curated > heuristic) is defensible; the exact gaps are not.
- **Curated CAGR and outlook are Investo's own estimates**, not third-party forecasts, and they age.
  Each peer group carries `updated_at` so a reader can judge staleness rather than assume freshness.
- **Confidence is about evidence quality, not about being right.** A high-confidence read of
  complete, authoritative data can still be a bad investment call.
