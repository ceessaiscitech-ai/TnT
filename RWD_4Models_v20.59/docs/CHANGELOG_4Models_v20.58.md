# RWD_4Models v20.58 — how the four-model pipeline was made

**Your request:** one separate pipeline, for both languages, for the panel generation and the models M01, M02, M16 and M34 only (your
latest message: M34 in place of M04), filtered from v20.58; the panel preparation prepares the panel for only these four models; Dask AND
Spark kept as fall-back processing options when the memory limit is exceeded, in every code and pipeline. (And: the RWD_Artal1 copy is dropped
from all code — from now on one Python pipeline, RWD_Artal, and one R pipeline, RWDR.)

## The principle

The engines are **not** rewritten: `python/DIDRDP_4Models_v20/*.py` (except `_paths.py`) and `R/lib/*.R` (except `reward_paths.R`,
`reward_packages.R`) are the full pipeline's v20.58 files byte for byte — the code that passed the full gates (168 self-checks, the known
answers of all 45 models, the poison test, R vs Python parity, …). The scope of this project is **configuration** the engines already honour:

| where | setting | effect |
|---|---|---|
| `_paths.py` | `PIPELINE_MODELS = ("M01", "M02", "M16", "M34")` | the panel's columns (`PANEL_COLUMNS_USED_BY`), the Python packages, the pre-built route checks (P12), readiness (P10), the R package list the Python side asks for |
| `_paths.py` | `OUTPUT_SUBDIR = "output_4Models"` | panel, results, estimator files, logs under `<data>\output_4Models` |
| `R/lib/reward_paths.R`, `reward_packages.R`, `00_SETUP.R` | `PIPELINE_MODELS <- c("M01", "M02", "M16", "M34")` | R's `MODEL_FUN`, the packages installed / confirmed, the panel's columns, no benchmark-site means |
| `R/lib/reward_paths.R` | `OUTPUT_SUBDIR <- "output_4Models"` | R's panel and results under `ROOT/output_4Models` |

## The panel for the four models

Left out of the panel (read by other models only): `District`, `dose_per_subwshed`, `dose_amount_sws`, `dose_intensity_per_ha`, `area_hectare`,
`first_treat_agri_year`, `first_treat_season` (M05, M06, M09, M22, M27, M28, M30–M32), `LandUse`, `LandUseDW` (M10, M26, M39–M45). Everything the
four models read stays (outcomes, weather covariates, rings, years, seasons, the location codes, pixel ids and coordinates, GapFilled / Coverage).
The four models take each sub-watershed's timing from your fund workbook when they run (as in the full pipeline).

P00's 12 steps: settings → file inventory → column harmonisation → validate-or-skip → PASS A (ingest, pixel ids, every row located in the
shapefile) → fund timing → PASS B (cross-file dedup: repeated rows dropped whole; pixel linking) → integrity (duplicates confirmed) → design
defaults → estimator files → readiness (the four) → packages (the four). Left out: P02b (SWS audit), P07 (preview workbook), P08 (ground
linkage, 4 cells), P08b (benchmark surrogates), P13 (effect-size diagnostics), the dose table of P05.

## Beyond 98 % of the RAM: out of core (Dask -> Spark -> built-in batches)

The four models and the panel preparation never stop and are never sampled when the data exceed the RAM: they run on pixel partitions (every
row of a pixel in one partition) with the same code as in memory; only additive statistics cross partitions, and the two-way fixed effects are
solved exactly from the partitions' cross-products (Frisch-Waugh-Lovell + the Schur complement of the period block; the CR1 sandwich from
per-cluster score sums). Python: `_outofcore.py`, `_ooc_models.py` (Dask LocalCluster / Spark local[cores] / batches), proven by
`validate_out_of_core.py` (a gate of `validate_4models.py`). R: `lib/reward_outofcore.R` (the four models), `lib/reward_prep_ooc.R` (R_P00 block
by block), the partition tasks on Dask / Spark through `lib/reward_ooc_engine.py` or in R itself, proven by `tests/run_all_tests.R` scenario H.

## What was filtered (build log)

- left out: python/DIDRDP_4Models_v20/02_Core_DiD_Models/M05_Callaway_Sant_Anna_staggered_ATT_g_t.ipynb
- left out: python/DIDRDP_4Models_v20/02_Core_DiD_Models/M11_Synthetic_DiD.ipynb
- left out: python/DIDRDP_4Models_v20/02_Core_DiD_Models/M09_Sun_Abraham_interaction_weighted.ipynb
- left out: python/DIDRDP_4Models_v20/02_Core_DiD_Models/M04_Changes_in_Changes.ipynb
- left out: python/DIDRDP_4Models_v20/02_Core_DiD_Models/M08_Instrumented_DiD_2SLS.ipynb
- left out: python/DIDRDP_4Models_v20/02_Core_DiD_Models/M14_Propensity_Score_Matched_DiD.ipynb
- left out: python/DIDRDP_4Models_v20/02_Core_DiD_Models/M10_Triple_Differences_DDD.ipynb
- left out: python/DIDRDP_4Models_v20/02_Core_DiD_Models/M15_Placebo_False_Timing_Test.ipynb
- left out: python/DIDRDP_4Models_v20/02_Core_DiD_Models/M13_Switcher_DiD_de_Chaisemartin_D_Haultfoeuille_simplified.ipynb
- left out: python/DIDRDP_4Models_v20/02_Core_DiD_Models/M12_Chained_DiD_unbalanced_panels.ipynb
- left out: python/DIDRDP_4Models_v20/02_Core_DiD_Models/M03_Doubly_Robust_DiD_AIPW.ipynb
- left out: python/DIDRDP_4Models_v20/02_Core_DiD_Models/M06_Continuous_Dose_Response_DiD.ipynb
- left out: python/DIDRDP_4Models_v20/02_Core_DiD_Models/M07_Surrogate_Index_DiD.ipynb
- left out: python/DIDRDP_4Models_v20/03_Spatial_Heterogeneity_Diagnostics
- left out: python/DIDRDP_4Models_v20/05_Causal_AI_ML
- left out: python/DIDRDP_4Models_v20/04_Advanced_Staggered_Robustness/M28_Gardner_Two_Stage_DiD.ipynb
- left out: python/DIDRDP_4Models_v20/04_Advanced_Staggered_Robustness/M38_Generalized_Synthetic_Control_Xu_2017.ipynb
- left out: python/DIDRDP_4Models_v20/04_Advanced_Staggered_Robustness/M33_Entropy_Balancing_DiD.ipynb
- left out: python/DIDRDP_4Models_v20/04_Advanced_Staggered_Robustness/M37_Matrix_Completion_DiD.ipynb
- left out: python/DIDRDP_4Models_v20/04_Advanced_Staggered_Robustness/M30_Cohort_Heterogeneity.ipynb
- left out: python/DIDRDP_4Models_v20/04_Advanced_Staggered_Robustness/M32_Extended_TWFE_ETWFE.ipynb
- left out: python/DIDRDP_4Models_v20/04_Advanced_Staggered_Robustness/M36_Interactive_Fixed_Effects_Bai_2009.ipynb
- left out: python/DIDRDP_4Models_v20/04_Advanced_Staggered_Robustness/M35_Quantile_DiD_distributional_effects.ipynb
- left out: python/DIDRDP_4Models_v20/04_Advanced_Staggered_Robustness/M31_Stacked_DiD.ipynb
- left out: python/DIDRDP_4Models_v20/04_Advanced_Staggered_Robustness/M39_ML_CATE_causal_forest_style.ipynb
- left out: python/DIDRDP_4Models_v20/04_Advanced_Staggered_Robustness/M27_BJS_Imputation_Estimator.ipynb
- left out: python/DIDRDP_4Models_v20/04_Advanced_Staggered_Robustness/M29_Exposure_Duration_Heterogeneity.ipynb
- left out: python/DIDRDP_4Models_v20/06_Validation/V01_Analytical_Formula_Verification.ipynb
- left out: python/DIDRDP_4Models_v20/06_Validation/V06_Ground_Validation.ipynb
- left out: python/DIDRDP_4Models_v20/06_Validation/V04_results.csv
- left out: python/DIDRDP_4Models_v20/06_Validation/V03_Classical_Estimator_Simulation_Validation.ipynb
- left out: python/DIDRDP_4Models_v20/06_Validation/V05_Counterfactual_Construction_Check.ipynb
- left out: python/DIDRDP_4Models_v20/06_Validation/V03_results.csv
- left out: python/DIDRDP_4Models_v20/06_Validation/V02_Fixed_Effects_Consistency_Check.ipynb
- left out: python/DIDRDP_4Models_v20/06_Validation/V04_ML_Causal_Method_Validation.ipynb
- left out: python/DIDRDP_4Models_v20/selfcheck.py
- left out: python/DIDRDP_4Models_v20/validate_requests.py
- left out: python/DIDRDP_4Models_v20/_ground_common.py
- left out: python/DIDRDP_4Models_v20/ground_utils.py
- left out: python/DIDRDP_4Models_v20/_bm_means.py
- left out: python/DIDRDP_4Models_v20/MODEL_GUIDE_CATEGORY_WISE.md
- left out: python/DIDRDP_4Models_v20/PIPELINES_GUIDE.md
- left out: python/DIDRDP_4Models_v20/PREBUILT_MODEL_MAP.md
- left out: python/DIDRDP_4Models_v20/RANKED_MODELS.md
- left out: python/DIDRDP_4Models_v20/python_prebuilt/ml_spatial_pipeline.py
- _paths.py: PIPELINE_MODELS = (M01, M02, M16, M34); OUTPUT_SUBDIR = output_4Models
- M01_Canonical_2x2_Static_TWFE.ipynb: CELL 1 without the settings of other models (dose, spatial, bootstrap / permutation / factor counts, heterogeneity / CATE covariates); its text names only this project's models
- M02_Event_Study_dynamic_TWFE.ipynb: CELL 1 without the settings of other models (dose, spatial, bootstrap / permutation / factor counts, heterogeneity / CATE covariates); its text names only this project's models
- M16_Formal_Joint_Pre_Trends_F_test.ipynb: CELL 1 without the settings of other models (dose, spatial, bootstrap / permutation / factor counts, heterogeneity / CATE covariates); its text names only this project's models
- M34_Honest_DiD_parallel_trends_sensitivity.ipynb: CELL 1 without the settings of other models (dose, spatial, bootstrap / permutation / factor counts, heterogeneity / CATE covariates); its text names only this project's models
- P00: 12 steps for the four models (left out: P02b SWS audit, P07 preview, P08 ground linkage x4, P08b BM surrogates, P13 effect diagnostics; P05 without the dose table; settings without RUN_SWS_AUDIT / RUN_GROUND_* / RUN_DIAGNOSTICS / DOSE_VARIABLE)
- R/rstudio: R_P00_Prepare_Panel, R_M01, R_M02, R_M16, R_M34, R_RUN_ALL_MODELS, R_V01_Results_Audit (left out: R_M03 ... R_M45 except M16 / M34, R_D01)
- R/jupyter: R_P00_Prepare_Panel, R_M01, R_M02, R_M16, R_M34, R_RUN_ALL_MODELS, R_V01_Results_Audit (left out: R_M03 ... R_M45 except M16 / M34, R_D01)
- R/lib: reward_paths.R + reward_packages.R PIPELINE_MODELS = c(M01, M02, M16, M34); OUTPUT_SUBDIR = output_4Models
- R notebooks: settings without DOSE_VARIABLE; texts name this project's models and ROOT/output_4Models

## Changes made to the full pipeline v20.58 for this (in RWD_Artal / RWDR too — they do nothing there, where every model is in the project)

- `readiness.py` (the gate's readiness tool) classifies the project's models only (`_readiness.py`, P10's tool, did already).
- `validate_all_models.py`: the readiness check expects the project's models (was: 45); the gate now FAILS when a model does not honour a
  scenario, writes a placeholder / an all-NaN file / a file outside its folder (until v20.58 it printed these and returned 0 — a silent pass).
- `validate_preprocessing.py`: a project whose P00 has no P08 (no ground data) says so instead of looking for the ground inputs.
- `00_SETUP.R` (R): installs the project's CRAN packages and their dependencies only (was: every CRAN package's dependencies).
- the validators find the output folder from `_paths.OUTPUT_SUBDIR` (was: `output`); R's tests guard the checks of models outside the project.
- R_P00's text: repeated rows are dropped whole (it still said "duplicates merged").
