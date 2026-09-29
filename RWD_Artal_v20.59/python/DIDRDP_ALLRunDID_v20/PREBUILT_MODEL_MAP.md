# Every model, both pipelines, both languages (v20.23)

Input for all pre-built models: `C.export_for_packages(outcome)` -> `estimator_files/package_input/<outcome>_<scenario>.parquet`
(pixel_id, site_id, subwshed_id, cluster_id, Year, Season, period, treat, post, did, event_time, cohort [Inf = never treated],
buff_km, outcome, covariates, latitude, longitude, dose). Staggered and factor-model packages need one row per unit-period:
`to_unit_period()` (Python) / `unit_year()` (R) collapse the seasons to pixel-year means. ML models use the pixel long difference.
Sources: pyfixest 0.30 (feols, Sun-Abraham event_study, did2s, lpdid, wildboottest, ritest, CCV); diff-diff (Gerber 2026, 13
estimators validated against R); csdid / drdid (Sant'Anna); EconML; DoubleML; esda; R CRAN/GitHub packages named below.

**Inside the notebooks (v20.43): a verified Python package, else a verified R package, else the existing implementation** -- 43 of 45 models have a pre-built route: 24 in Python (as in v20.42) and 34 in R through `R/lib/run_one.R` (19 of them the only package route: M03, M04, M10, M12, M13, M14, M15, M19, M26, M28, M29, M30, M32, M33, M35, M37, M38, M44, M45; for M20, M24, M25 and M36 the complete R package model is primary over the Python engine function). The existing implementation alone: M08 (needs an instrument) and M16 (the rank-safe joint test; its leads come from pyfixest).

**Inside the notebooks (v20.42): a verified package FIRST for every model that has one** -- 10 models inside the engine functions they call (pyfixest / wildboottest / diff-diff CS: M01, M02, M05, M07, M20, M21, M23, M24, M25, M36) and 14 as model runs before the engine code (diff-diff: M06, M09, M11, M22, M27, M31, M34; econml: M39-M43; esda: M17, M18), each verified on a known answer per installed version (P00 P12); the engine only when no verified package exists, and as the cross-check when one does. `C.prebuilt_readiness()` -> PREBUILT_READINESS.md says what computes each model and why. Before v20.42:

**Inside the notebooks (v20.29):** after P12 verifies them on your machine, `estimate_twfe_did` (M01 and the models
that call it), `estimate_event_study` (M02 and its callers), `wild_cluster_bootstrap_pvalue` (M23) and
`callaway_santanna_att` (M05 and its callers) are computed by pyfixest / diff-diff; the rest keep the validated
engine in the notebooks and have the package counterparts below in `python_prebuilt/` and `R/`. All of them now use
the same pixel x season unit (`unit`) as the engine.

| model | what it estimates | custom engine (Python) | pre-built Python | pre-built R | accuracy note |
|---|---|---|---|---|---|
| M01 | 2x2 TWFE | estimate_twfe_did / streaming | pyfixest feols; diff-diff DifferenceInDifferences | fixest::feols | identical point estimates; report t(G-1) / Webb bootstrap p |
| M02 | event study | estimate_event_study | pyfixest i(); diff-diff MultiPeriodDiD | fixest i() | universal base period (-1); coverage notes |
| M03 | doubly-robust DiD | aipw_did | drdid (drdid.drdid_dr) | DRDID::drdid | DR is consistent if either nuisance model is right |
| M04 | changes-in-changes | changes_in_changes | pycinc | qte::CiC | quantile-level effects, bootstrap SE |
| M05 | Callaway-Sant'Anna | callaway_santanna_att | diff-diff CallawaySantAnna; csdid | did::att_gt | needs >= 2 cohorts (pooled sites); universal base period |
| M06 | dose-response | dose_response | diff-diff ContinuousDiD | contdid | needs dose variation across sites |
| M07 | surrogate index | custom | statsmodels/econml | - | needs ground-truth file |
| M08 | IV-DiD | custom | pyfixest 2SLS | fixest IV | needs an instrument |
| M09 | Sun-Abraham | sun_abraham_iw | diff-diff SunAbraham; pyfixest.did.event_study | fixest::sunab | interaction-weighted; needs cohorts |
| M10 | triple differences | ddd | pyfixest feols i(LandUse)xdid | fixest | site^period^group FE in pooled runs |
| M11 | synthetic DiD | synthetic_did | diff-diff SyntheticDiD | synthdid | placebo SE |
| M12 | chained DiD | custom | pyfixest first differences | fixest | - |
| M13 | switchers | custom | - | DIDmultiplegtDYN | needs treatment that switches |
| M14 | PSM-DiD | psm_did | sklearn matching + pyfixest | MatchIt + fixest | caliper 0.2, pre-period covariates |
| M15 | placebo timing | custom | pyfixest with shifted year | fixest | - |
| M16 | joint pre-trends | pretrends_joint_ftest | pyfixest wald; diff-diff check_parallel_trends | fixest::wald; pretrends | rank-capped at G-1; anchored on ref |
| M17 | Moran's I | custom | esda.Moran | spdep::moran.test | on pixel long differences, KNN weights |
| M18 | LISA | custom | esda.Moran_Local | spdep::localmoran | - |
| M19 | ICC | custom | statsmodels MixedLM | lme4 + performance::icc | - |
| M20 | Q / I2 | custom | scipy | metafor::rma | per-cluster effects, REML tau2 |
| M21 | season->annual | custom | pandas + pyfixest | fixest | - |
| M22 | Goodman-Bacon | goodman_bacon_diagnostic | diff-diff BaconDecomposition | bacondecomp | needs cohorts |
| M23 | wild bootstrap | wild_cluster_bootstrap_pvalue (Webb) | wildboottest (Webb) | fwildclusterboot (Webb) | Webb weights below 12 clusters |
| M24 | spillover gradient | spillover_gradient_test | pyfixest i(ring) x post | fixest | ring 5 as reference |
| M25 | permutation | custom | pyfixest ritest | ritest | cluster-level permutations |
| M26 | treatment x covariate | custom | pyfixest | fixest | - |
| M27 | BJS imputation | bjs_imputation | diff-diff ImputationDiD | didimputation | never/not-yet treated only |
| M28 | Gardner two-stage | gardner_two_stage | pyfixest.did.did2s | did2s | - |
| M29 | exposure duration | custom | pyfixest exposure bins | fixest | - |
| M30 | cohort heterogeneity | custom | diff-diff CS aggregate=group | did::aggte(type='group') | - |
| M31 | stacked DiD | stacked_did | diff-diff StackedDiD | stacked (fixest) | clean controls per stack |
| M32 | extended TWFE | custom | pyfixest saturated | etwfe | Wooldridge (2021) |
| M33 | entropy balancing | custom | - | WeightIt(method='ebal') + fixest | ATT weights on pre-period covariates |
| M34 | HonestDiD | honest_did_relative_magnitudes | diff-diff HonestDiD (RM + smoothness) | HonestDiD (FLCI) | package gives the full interval |
| M35 | quantile DiD | custom | pyfixest quantreg | quantreg / qte::QDiD | within-transformed |
| M36 | interactive FE | custom | - | fect(method='ife') | CV on factors |
| M37 | matrix completion | custom | - | fect(method='mc') | needs treated units with pre series |
| M38 | gsynth | custom | - | gsynth | idem |
| M39 | ML CATE summary | custom | econml CausalForestDML CATE | grf | CATE by covariate quartile |
| M40 | double ML | custom | econml LinearDML / DoubleML | DoubleML | cross-fitting, 3 folds |
| M41 | meta-learners | custom | econml S/T/X | grf / SuperLearner | - |
| M42 | DR-learner | custom | econml DRLearner | grf | - |
| M43 | honest causal forest | custom | econml CausalForestDML (honest) | grf::causal_forest (clustered) | cluster-aware forest in R |
| M44 | BART | custom | - (no maintained Python BART) | bartCause | - |
| M45 | ML synthetic control | custom | mlsynth (site level) | synthdid / augsynth (site level) | one treated unit per site |

Run: `python python_prebuilt/ml_spatial_pipeline.py NDVI` (all Python pre-built models that apply) · R: open `R/rstudio/R_RUN_ALL_MODELS.Rmd` in RStudio (the bundle's R pipeline; see R/README_R.md).
