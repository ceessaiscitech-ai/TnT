# Which models to trust on THIS data (v20.32)

Your design, as the panel now stands: ~90.9 M rows, one treatment cohort (2022), treated = buffer 0 cores, controls =
the 1-5 km rings around those same cores, 12 clusters (sub-watersheds), annual + seasonal rows 2015-2026, ground inputs
present, fund-release dose available, no never-treated units outside the rings.

Three facts drive the ranking. (1) **12 clusters** -- t-statistics and normal p-values overstate significance; the wild
cluster bootstrap is the inference that holds. (2) **One cohort** -- every staggered-adoption estimator (Callaway-
Sant'Anna, Sun-Abraham, stacked, BJS by cohort) has nothing to exploit unless the two saturation phases have different
treatment years in `data/sites/sites.csv`. (3) **Controls are rings around the treated core** -- if the works help the
ring (recharge, moisture, sediment), the DiD differences the effect away and reports ~0 or negative. Ranking that
without a spillover test is the single biggest risk to your conclusions.

## Tier 1 -- the evidence to report (run in this order)
| # | model | why it ranks here | needs |
|---|-------|-------------------|-------|
| 1 | **M16 pre-trends F-test** | decides whether ANY DiD number is admissible; without parallel pre-trends nothing below means anything | >= 2 clean pre years |
| 2 | **M02 event study** | shows year-by-year dynamics, exposes a frozen or footprint-shifted series instantly, and is the figure reviewers read first | the same |
| 3 | **M24 spillover / ring gradient** | tests the assumption your control group rests on; if ring 1 moves with the core, re-run with rings 3-5 as controls | rings 1-5 |
| 4 | **M23 wild cluster bootstrap** | the p-value to quote with 12 clusters (Webb weights); t(G-1) p-values are optimistic | >= 5 clusters |
| 5 | **M01 canonical 2x2** | the headline effect size -- but only after 1-4 pass | -- |
| 6 | **M34 HonestDiD** | states how large a pre-trend violation your conclusion survives; turns a fragile result into an honest bound | M02 output |
| 7 | **M15 placebo timing** | a fake 2019/2020 treatment must produce nothing; catches a design that manufactures effects | >= 3 pre years |
| 8 | **M25 permutation inference** | assignment-based p-value that does not rely on 12 clusters behaving asymptotically | -- |

## Tier 2 -- robustness and interpretation (report what matters, not all)
| # | model | what it adds |
|---|-------|--------------|
| 9 | **M21 season-to-annual aggregation** | you now estimate on annual AND seasonal rows; this shows whether the effect is a season-mix artefact |
| 10 | **M03 doubly robust (AIPW)** | consistent if either the outcome model or the weighting is right -- the strongest single-cohort alternative to TWFE |
| 11 | **M14 PSM-DiD / M33 entropy balancing** | balances the core against rings on pre-period levels and trends |
| 12 | **M35 quantile DiD** | where in the distribution the change sits -- directly relevant to your negative-value concern |
| 13 | **M04 changes-in-changes** | distributional, invariant to monotone rescaling of an index |
| 14 | **M17 / M18 Moran's I and LISA** | spatial dependence: if residuals cluster spatially, clustered SEs at 12 sub-watersheds are too small |
| 15 | **M19 ICC / M20 Cochran Q, I2** | how much of the effect varies between sub-watersheds; the basis for per-site reporting |
| 16 | **M26 treatment x covariate heterogeneity** | whether the effect depends on rainfall, land use or baseline greenness |
| 17 | **M12 chained DiD** | robust to the changing export footprint across years |
| 18 | **M30 BJS imputation / M28 Gardner two-stage** | efficient alternatives that use the never-treated rings as the comparison; work with one cohort |
| 19 | **M22 Goodman-Bacon** | with one cohort it is a diagnostic, not an estimate: it shows which comparisons carry the weight |

## Tier 3 -- descriptive or heterogeneity only (never the headline)
M39-M44 (DML, meta-learners, DR-learner, causal forest, BART) map WHERE effects differ across pixels. With 12 clusters
their confidence intervals are not trustworthy for an average effect; use them to target follow-up, not to conclude.
M27 stacked and M29 / M32 variants add little with a single cohort.

## Blocked on this data (what would unlock each)
| model | blocked because | unlock |
|-------|-----------------|--------|
| M05, M09, M31 (Callaway-Sant'Anna, Sun-Abraham, cohort ATT) | one treatment cohort | fill Phase 1's treatment year in `data/sites/sites.csv` if it differs from 2022 |
| M06 dose-response | no usable dose variation | P05 fund-release dose per sub-watershed |
| M07 ground-truth validation | needs the linked ground outcomes | P08 writes them; then M07 runs |
| M08 rollout instrument | no instrument file | `rollout_instrument.csv` |
| M13 switchers | nothing switches off | -- |
| M36-M38, M45 (gsynth, fect, synthetic control) | need treated units at cluster level and long clean pre-periods | the 20-site pooled panel |

## The order I would actually run
`M16 -> M02 -> M24 -> M23 -> M01 -> M34 -> M15 -> M25`, then choose from Tier 2 by what the reviewer will ask.
If M16 fails or M24 shows ring contamination, fix the design before reporting any effect size: re-run with rings 3-5 as
controls, or with the annual composite only (`SEASONS = "yearly"`), and compare.
