# Getting a credible DiD estimate from the REWARD panel — what to change, and what never to change

*Written against your M01 log of 30 Sep 2026 (194.7 M rows, 5.76 M pixels, sub-watersheds 10 and 15, rings 0–5, 2015–2025, four
seasons; NDVI canonical beta −0.00215, SE 0.00221; covariate-adjusted −0.00232, SE 0.00242).*

## 1. The honest starting point

A p-value is not a dial. Any rule that picks the control group, the years or the rings **because the estimate then becomes
significant** turns the estimate into a description of that choice, not of the programme (specification search; the SE no longer
means what it says). Every option below is therefore chosen on **design facts** — the treatment history, the geography, the pre-period
data — and is fixed before the post period is looked at. The pipeline enforces this: `CONTROL_SELECTION` accepts only pre-period
rules and refuses any rule whose name mentions the post period, the outcome's overall mean or the result.

The estimate in your log is small and imprecise for identifiable reasons, most of them not about the control rings:

| What the log shows | Why it pushes the estimate towards zero or inflates the SE | The change |
|---|---|---|
| `DESIGN vs PANEL ... differs on 44,577,841 of 194,671,345 rows (22.9%)`; the estimator file was built for `treat2024`, the run used `treat2022` | The exporter's `Treat` flag says post from 2022; your fund workbook says the works started in 2024. With post = 2022, two untreated years (2022, 2023) sit in the "post" group of the treated area: the effect is averaged with two years of nothing. | Use the timing that reflects the ground: `DESIGN_SOURCE = "model"`, `TREATMENT_TIMING = "fund"` (or `"fixed"`, `TREATMENT_YEAR = 2024`), and `EXCLUDE_TRANSITION_YEAR = True` for the first works year. Then run M02 (event study): the lead coefficients must be flat, the lags show when the effect appears. |
| `OUTCOME_SCREEN = 'keep'` with three collapsed year-seasons (2023 Zaid, 2025 Kharif, 2025 Zaid: 3–4 k treated rows against a typical 528 k) | These cells carry no comparable treated coverage; kept, they add noise to the post period and pull the two-way FE towards them. | `OUTCOME_SCREEN = "drop"` (the default). Read `OUTCOME_SCREEN_NDVI.csv` first; if a cell is a real cloud gap, dropping it is the correct call. |
| `1,461,609 unit_id series are seen ONCE (2025 Rabi)` | Singleton series identify nothing; harmless for the point estimate, but they signal an unbalanced last season. | With `EXCLUDE_TRANSITION_YEAR` and the screen in place this shrinks; M02 with `BALANCED_PIXELS` shows whether the balanced footprint changes the answer. |
| Clusters: 2 sub-watersheds → the engine clusters on years (10–11 clusters) | Inference with ~10 clusters is fragile; pixels 10 m apart are strongly correlated, so pixel-level or year-level clustering understates the spatial dependence. | `CLUSTER = "block"` (new): ~1 km spatial blocks of pixels as clusters — hundreds to thousands of clusters, the neighbour correlation absorbed. Use it in the main specification; report the year-cluster SE beside it. |
| All four seasons pooled into one coefficient | Watershed works (bunds, check dams, farm ponds) act on post-monsoon soil moisture. The Rabi/Zaid effect is what the programme is designed to produce; Kharif is rain-fed and the Yearly composite dilutes both. | Run `SEASONS = "Rabi"` (and `"Zaid"`) as the primary estimates, `"all"` as the pooled summary. |
| NDVI as the only headline | NDVI saturates on dense canopy and is dominated by rainfall. | Report EVI / SAVI / LAI beside NDVI (P09 builds every variable's file); consider the log of the outcome for a proportional effect. |
| Every land-use class in the sample | The works target agricultural land; forest, scrub and built-up pixels cannot respond and only widen the SE. | Filter the panel to cropland (`LandUse`) for the primary estimate; M10's land-use groups show the rest. |
| The whole 0–5 km control area as one group | Ring 1 borders the treated core: water and sediment flow across the boundary (spillover), which biases the DiD towards zero. Rings 4–5 are far and less comparable. | A donut: `CONTROL_RINGS = 2:4` (leave ring 1 out as the spillover buffer). Better: let the pre period choose — below. |

Do these first, in this order: timing → screen → seasons → cluster. Each is a design fact, not a search. If after these the Rabi
effect is still indistinguishable from zero with block-clustered SEs, that is the finding; the minimum detectable effect the engine
prints with every TWFE result says how small an effect the data could have found.

## 2. Your proposal: pick the control buffer(s) by closeness to the treatment area, per variable

Your instinct is right and it has a name — **matched difference-in-differences**. Two rules make it valid:

1. **Only the PRE period may decide.** Closeness measured on post-period or on the overall means uses the outcome you are about to
   estimate; the chosen control is then the one that happens to make the difference large (or small). Pre-period closeness is a
   legitimate design choice: it is the same information a matching estimator or a synthetic control uses.
2. **What must be close is the trend, not the level.** DiD never needs the treated and control areas to have the same NDVI; the
   pixel fixed effect absorbs any constant gap. It needs them to **move together before treatment** (parallel trends). A ring with a
   different level but the same pre-trend is a better control than a ring with the same level and a different trend. So the primary
   rule is `"trend"`; `"level"` and `"both"` are available for comparison.
3. **The control pixels must be the same in every year and season** — exactly as you wrote. The choice is made once per outcome on
   the pre period and applied to the whole panel; a control set that changes across periods is a different estimand in every period.

This is now in both pipelines (`CONTROL_SELECTION`, CELL 1 of every model notebook and `R_Mxx`):

| Setting | Meaning |
|---|---|
| `CONTROL_SELECTION = "rings"` | as before: every ring of `CONTROL_RINGS` is the control group |
| `CONTROL_SELECTION = "pre_rings"`, `CONTROL_SELECT_K = 2` | per outcome, the 2 (or 1) rings whose **pre-period** series is closest to the treatment area's |
| `CONTROL_SELECTION = "pre_blocks"`, `CONTROL_SELECT_RATIO = 3` | per outcome, ~1 km blocks of control pixels anywhere in rings 1–5, the closest first, until 3 x the treated pixels — your "clusters from any part of the buffers" |
| `CONTROL_SELECT_ON = "trend"` (`"level"`, `"both"`) | the distance: mean absolute gap between the demeaned pre series (the parallel-trend distance); the pre-mean gap; their sum |
| `CONTROL_BLOCK_DEG = 0.01` | the block side (0.01° ≈ 1.1 km) |
| `CLUSTER = "block"` | the same blocks as the clusters of the SE |
| `SAME_PIXELS = "pre_post"` (`"all"`, `"off"`) | your rule 3 enforced on every sample: a pixel observed only before or only after treatment leaves; `"all"` keeps only pixels observed in every year-season (a balanced pixel set) |

What the run writes: `CONTROL_SELECTION_<outcome>.csv` (R: `_R.csv`) beside the results — every candidate ring or block with its
pre-period rows, pixels, level gap, trend distance, slope difference, score, rank and whether it was chosen; the log says the
decision in one line; the results folder is tagged `_ctrlPre2r` / `_ctrlPreBlk3x` (`L` / `B` for the level / both rules); the
design report (`DESIGN IN EFFECT`) carries the row `CONTROL_SELECTION`. Out of core the parent decides once on the merged pre-period
facts of every partition and the workers apply the same set. A rule named after the post period or the outcome's mean is refused with
the reason.

**Recommended primary specification** (then report the alternatives beside it):

```
TREATMENT_TIMING = "fund"        # or "fixed" with TREATMENT_YEAR = 2024
DESIGN_SOURCE    = "model"
EXCLUDE_TRANSITION_YEAR = True
OUTCOME_SCREEN   = "drop"
SEASONS          = "Rabi"        # and "Zaid"; "all" as the pooled summary
CONTROL_SELECTION = "pre_rings"; CONTROL_SELECT_K = 2; CONTROL_SELECT_ON = "trend"
CLUSTER          = "block"
```

and M02 (event study) with the same settings: the leads are the test of the design; a flat pre-period with a rising post-period is
the evidence a reader will believe. Report the `"rings"` estimate (all rings) and the donut `2:4` beside it, with the same clusters,
so the reader sees that the choice of controls moved the estimate for the reason the evidence file shows, not by search.
