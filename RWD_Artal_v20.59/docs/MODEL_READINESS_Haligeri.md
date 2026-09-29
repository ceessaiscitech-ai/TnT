# Model readiness -- complete / limited / incomplete-need data

_v20.58: re-assessed with the v20.58 rules (the core-vs-ring series design of M11 / M36-M38 / M45 -- the ring series are the donors; M20 needs >= 2 sub-watersheds; M07 >= 6 sub-watershed x season means of the ground data; M13 measured switchers). The facts below are those measured on 23 Sep 2026._

_measured 23 Sep 2026 from your M01 effect-size diagnostics (effect_size_diagnostics_NDVI.csv and the _yearly files), site_id_mapping.csv and the P00 log -- Haligeri (SWS 7, Phase 1) staged in TST_Artal; scenario ctrl1-3_treat2022_all_nonneg_covMeanTempRain_yr2018-end_

**complete** -- every prerequisite is met on this panel; **limited** -- the model runs, but a panel-wide caveat below bounds what its result can claim; **incomplete-need data** -- a prerequisite is missing: the model refuses by design (DATA GAP) and its row names the data that would complete it.

## Summary -- Haligeri (SWS 7, Phase 1)

| | complete | limited | incomplete-need data |
|---|---|---|---|
| **as the data stand now** | 0 | 37 | 8 |
| **all 20 sub-watersheds, projected** | 40 | 4 | 1 |

_Projection: PROJECTION (not measured): all 20 sub-watersheds pooled, Phase-1 implementation years filled in data/sites/sites.csv AND DIFFERENT from Phase 2's 2022 (two cohorts; if Phase 1 also began in 2022 the staggered models M05, M09, M22, M30, M31 stay as they are now), the panel rebuilt at PIXEL_OVERLAP_MIN 0.65 and 2025 held out (POST_YEARS) or re-exported_

## The panel

Implementation year **2022** (ASSUMED) | years 2018-2025 | clean pre 2018-2021 | clean post [2022, 2023, 2024] | years to hold out: [2025]

Sub-watersheds 1 | inference clusters 8 = years (one sub-watershed = one cluster; the engine clusters on the 8 years) | control rings [1, 2, 3] | cohorts among treated 1 | never-treated comparison True | seasons [0, 1, 2, 3]

| year | treated pixels | with a pre-period history | control pixels |
|---|---|---|---|
| 2018 | 619,271 | 619,271 (100%) | 1,248,914 |
| 2019 | 619,271 | 619,271 (100%) | 1,248,914 |
| 2020 | 619,271 | 619,271 (100%) | 1,248,914 |
| 2021 | 619,271 | 619,271 (100%) | 1,248,914 |
| 2022 | 619,271 | 619,271 (100%) | 1,248,914 |
| 2023 | 619,271 | 619,271 (100%) | 1,248,914 |
| 2024 | 619,271 | 619,271 (100%) | 1,248,914 |
| 2025 | 621,909 | 313,308 (50%) | 1,252,048 |

## PANEL-WIDE CAVEATS -- what is missing, why it matters, what fixes it

### C1 -- ONE sub-watershed  *(turns complete models into limited)*

- **Missing:** other sub-watersheds (treated areas)
- **Why it matters:** the sub-watershed is the cluster; one cluster cannot carry cluster-robust inference, so the engine clusters on the 8 years -- each year's core-vs-ring contrast is ONE independent draw. Standard errors are honest but wide, and nothing separates the programme from anything else that hit this sub-watershed's core and not its rings in the same years.
- **What fixes it:** the pooled 20-sub-watershed run (every model pools the sub-watersheds of its panel automatically -- v20.57: after the fragment rule)
- **Affects:** every model

### C2 -- implementation year ASSUMED  *(turns complete models into limited)*

- **Missing:** the Phase-1 implementation year (blank in data/sites/sites.csv)
- **Why it matters:** 2022 is used. If works began earlier, the 'pre' years already hold treated years and every effect is pulled toward zero; if later, 'post' years hold untreated years (same bias).
- **What fixes it:** date it: TREATMENT_TIMING = 'fund' (your fund workbook, the v20.57 default) or fill treatment_year for the Phase-1 rows of data/sites/sites.csv ('registry'); every model uses it when it runs
- **Affects:** every model

### C3 -- 2025 is a different export  *(turns complete models into limited)*

- **Missing:** one export for every year, on one pixel grid
- **Why it matters:** levels jump for BOTH groups in [2025] (AGB, EVI, LAI, NDVI, SAVI, VCI, VHI) -- processing changed; only 50% of the treated rows of [2025] have a pre-period history (grid shifted ~3 m); unlinked rows identify nothing and composition changes. Your raw NDVI difference (+0.018) comes almost entirely from 2025; 2022-2024 on the same pixels: +0.003.
- **What fixes it:** rebuild P00 at PIXEL_OVERLAP_MIN 0.65 (links ~95 %), report POST_YEARS to 2024 as the main result and the full window as robustness -- or re-export [2025] with the earlier processing
- **Affects:** every model using those years (event time +3 in M02 most)

### C4 -- outcomes without a usable pre-period

- **Missing:** pre-2022 values of ['LSWI', 'NDMI']
- **Why it matters:** their core-vs-ring gap is exactly 0 or missing before 2025 -- no baseline, no DiD
- **What fixes it:** re-export those indices for the pre-period, or leave them out of every model
- **Affects:** those outcomes only

### C5 -- fund releases before the file starts  *(turns complete models into limited)*

- **Missing:** releases from implementation (2022) to the file's start (Oct 2024 (file covers 2024-10 .. 2026-07))
- **Why it matters:** the dose (amount released, intensity per ha) is unknown -- left missing, not 0 -- for the first post seasons
- **What fixes it:** a fund file from the programme start
- **Affects:** dose models (M06, M27, M30 and dose-intensity variants)

### C6 -- ground data are post-period only

- **Missing:** benchmark-site (BM) values before 2022
- **Why it matters:** your BM data cover 2023-2024: no DiD on ground values alone. They enter as SURROGATE outcomes (GND_*): each sub-watershed's BM mean (the mean of its three sites) is mapped to the satellite indices of its treatment area, season by season, and predicted for every pixel and year -- which needs >= 6 sub-watershed x season means
- **What fixes it:** the pooled run over the sub-watersheds (P00 P08b fits the surrogates automatically)
- **Affects:** M07

### C7 -- no structure-level data

- **Missing:** locations, amounts and completion dates of works inside each sub-watershed
- **Why it matters:** the dose is uniform over each treatment area; within-sub-watershed intensity and heterogeneity are not identified
- **What fixes it:** a structures table -> C.within_sws_dose() / WITHIN_SWS_DOSE_PATH (ready in the code)
- **Affects:** within-SWS dose and heterogeneity

### C8 -- results produced before v20.38

- **Missing:** valid standard errors in earlier result files
- **Why it matters:** they clustered on within-sub-watershed units that are not clusters; SEs of ~1e-5 understated the uncertainty (the year-to-year core-vs-ring gap varies by ~0.01)
- **What fixes it:** re-run the models with v20.38+
- **Affects:** every earlier result file

**Settings for the main result:** POST_YEARS = 3 (post period 2022-2024; [2025] carry a different treated population / index level); BALANCED_PIXELS = True in M02 (or C.common_pixel_mask) when the window includes [2025]

Yearly-only outcomes (no seasonal rows): ['ESI', 'RUSLE', 'WSI', 'WSSI'] -- seasonal models skip them.

## Model by model

| model | name | status now | what is missing | what completes it | all 20 (projected) |
|---|---|---|---|---|---|
| M01 | Canonical 2x2 TWFE | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M02 | Event study | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M03 | Doubly robust AIPW | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M04 | Changes-in-changes | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M10 | Triple differences | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M11 | Synthetic DiD | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M12 | Chained DiD | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M13 | Switcher DiD | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M14 | PSM DiD | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M15 | Placebo false timing | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M16 | Joint pre-trends F | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M17 | Global Moran's I | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M18 | Local Moran / LISA | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M19 | Variance decomposition ICC | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M21 | Season-to-annual aggregation | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M22 | Goodman-Bacon | **limited** | needs >=2 treatment cohorts; treated pixels form 1 cohort; panel-wide C1, C2, C3 | the pooled 20-sub-watershed run with Phase-1 years filled (two cohorts); fix C1, C2, C3 (above) | complete |
| M23 | Wild-cluster bootstrap | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M24 | Spillover ring gradient | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M25 | Permutation inference | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M26 | Treatment x covariate | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M27 | BJS imputation | **limited** | panel-wide C1, C2, C3, C5 | fix C1, C2, C3, C5 (above) | limited |
| M28 | Gardner two-stage | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M29 | Exposure duration | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M32 | Extended TWFE | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M33 | Entropy balancing | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M34 | HonestDiD sensitivity | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M35 | Quantile DiD | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M36 | Interactive FE (Bai) | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M37 | Matrix completion | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M38 | Generalised synthetic control | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M39 | ML CATE (forest) | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M40 | Double ML | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M41 | Meta-learners | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M42 | DR-learner | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M43 | Honest causal forest | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M44 | BART-style | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M45 | ML synthetic control | **limited** | panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M05 | Callaway-Sant'Anna | **incomplete-need data** | needs >=2 treatment cohorts; treated pixels form 1 cohort (single site) -- collapses to the 2x2 design M01 already gives; panel-wide C1, C2, C3 | the pooled 20-sub-watershed run with Phase-1 years filled (two cohorts); fix C1, C2, C3 (above) | complete |
| M06 | Continuous dose-response | **incomplete-need data** | dose_per_subwshed does not vary across treated units (one site, one dose); panel-wide C1, C2, C3, C5 | the pooled 20-sub-watershed run; fix C1, C2, C3, C5 (above) | limited |
| M07 | Surrogate index | **incomplete-need data** | needs ground_truth_outcomes.csv (field survey / benchmark workbooks linked by P08); needs >= 6 sub-watershed x season means of the ground data (this panel gives 3) -- the pooled run over the sub-watersheds; panel-wide C1, C2, C3, C6 | ground_truth_outcomes.csv (field outcomes per site x year); fix C1, C2, C3, C6 (above) | limited |
| M08 | Instrumented DiD | **incomplete-need data** | needs rollout_instrument.csv (no instrument for programme timing exists); panel-wide C1, C2, C3 | rollout_instrument.csv; fix C1, C2, C3 (above) | incomplete-need data |
| M09 | Sun-Abraham | **incomplete-need data** | needs >=2 treatment cohorts; treated pixels form 1 cohort (single site) -- collapses to the 2x2 design M01 already gives; panel-wide C1, C2, C3 | the pooled 20-sub-watershed run with Phase-1 years filled (two cohorts); fix C1, C2, C3 (above) | complete |
| M20 | Spatial heterogeneity Q/I2 | **incomplete-need data** | needs >= 2 sub-watersheds, each with its own DiD (heterogeneity ACROSS sub-watersheds); this panel holds 1 -- the pooled run; panel-wide C1, C2, C3 | fix C1, C2, C3 (above) | complete |
| M30 | Cohort heterogeneity | **incomplete-need data** | needs >=2 treatment cohorts; treated pixels form 1 cohort (single site) -- collapses to the 2x2 design M01 already gives; panel-wide C1, C2, C3, C5 | the pooled 20-sub-watershed run with Phase-1 years filled (two cohorts); fix C1, C2, C3, C5 (above) | limited |
| M31 | Stacked DiD | **incomplete-need data** | needs >=2 treatment cohorts; treated pixels form 1 cohort (single site) -- collapses to the 2x2 design M01 already gives; panel-wide C1, C2, C3 | the pooled 20-sub-watershed run with Phase-1 years filled (two cohorts); fix C1, C2, C3 (above) | complete |

## Notes on reading specific models

- **M01**: treated group = 619,271 pixels seen throughout
- **M02**: 2025 coefficient = footprint/level change, not an effect; read identification_note
- **M10**: assumes LandUse varies among the treated pixels -- run R.model_readiness() on the machine to confirm
- **M23**: report p_wild / permutation p instead of t-stats (8 clusters)
- **M25**: report p_wild / permutation p instead of t-stats (8 clusters)
