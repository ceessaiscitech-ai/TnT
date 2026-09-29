# Validation of v20.59 — what ran on the delivered code, where, and what could not

Build machine for this version: a Linux sandbox with 4 cores and 15 GB RAM, Python 3.11 (numpy 2.4.6, pandas 3.0.6, pyarrow 25.0.1,
scipy 1.17.1). **R is not installed there**, and neither are the estimator packages (pyfixest, diff-diff, econml, esda), Dask or Spark:
every Python model below ran on the engine's own implementation (the fall-back v20.58 verified against the packages), in memory.
The R code of this version was reviewed and syntax-balanced but **not executed** — `tests/run_all_tests.R` (scenarios A–H, with the new
scenario-E checks), `tests/selftest.R`, `validate_r_parity.py`, `validate_model_parity.py` and the R halves of `validate_design_options.py`
must be run where R is installed (RStudio: Source `tests/run_all_tests.R`; it must end with `RESULT: PASS`).

## 1. Gates that ran here (RWD_4Models_v20.59, the bundle behind your v20.58 run)

| Gate | Result |
|---|---|
| `selfcheck_4models.py` | CLEAN: 137 checks passed (17 of this project, 120 of the engine, `check_v20_59` among them); the R checks did not run (R not found) |
| `validate_preprocessing.py` (P00 on synthetic exports: PASS A / PASS B, the flag-based design case, the rebuild on a changed `POST_FROM_EXPORT_TREAT`) | CLEAN: the preparation path works end to end on synthetic exports |
| `validate_known_answers.py M01 M02 M16` (true effect +0.05; one sub-watershed and eight staggered) | single: M01 0.0497, M02 0.0503, M16 p 0.62 — PASS; staggered: M01 0.0500, M02 0.0503, M16 p 0.031 — PASS (CLEAN) |
| `validate_design_options.py` (every design option at the model stage; the Python parts) | 1,167 PASS, 4 FAIL -- the 4 are `R model stage available: Rscript or the R lib not found` (one per panel: the R half could not run here); every Python check of every variant passed, the new `pre2018_post2024`, `pre_at_start_2022` and `screen_keep` variants among them |
| an end-to-end run on 150 pixels inside the real Haligeri polygons (core + rings 1–5, 2016–2025, four seasons, the exports' `Treat` flag, one fill year-season 2018 Yearly): P00 -> load_panel -> build_treatment_columns -> the screen -> M01 | the panel carries `treat, control, pre, post, did`; `panel_variation_by_block.csv` names 2018 Yearly as the one constant cell; the screen leaves it out with its evidence file (`150 rows of 150 pixels, every value 0.3456`); DESIGN vs PANEL: 0 of 5,850 rows differ under fixed 2022, 600 of 5,850 (2022) under fixed 2023; M01 0.0510 (SE 0.0006) for a true 0.05; `OUTCOME_SCREEN = "keep"` keeps the cell and tags the folder `_screenKept`, `"off"` runs no screen; a frame constant in 38 of 39 cells is refused with the evidence path and the option named |
| the R library (`reward_design.R`, `reward_prep.R`, `reward_prep_ooc.R`, `reward_outofcore.R`, `reward_paths.R`) and `tests/run_all_tests.R` | brackets, quotes and braces balanced after the edits (a Python check; no R here) |

## 2. What changed in the delivered validation lists, and the "failed" entries of v20.58

v20.58's own lists (`VALIDATION_v20.58.md`, `VALIDATION_4Models_v20.58.md`) show every gate PASS; the entries that read as failures
there are data gaps, not code: `VALIDATION_KNOWN_ANSWERS_v20.58.csv` marks M07 `NO ANSWER ... failed` (it needs the BM ground-truth
file, absent on synthetic data), and `tests/LAST_TEST_RESULTS.csv` of RWDR lists `DATA GAP` rows for M06 / M07 / M08 / M20 (no dose,
no ground file, no instrument, one sub-watershed — expected on those scenarios). One real gap: the four-model bundle's
`R/tests/LAST_TEST_RESULTS.csv` was shipped EMPTY (a header only), so the R test run reported in `VALIDATION_4Models_v20.58.md`
(A 6, B 23, C 4, D 11, E 17, F 7, H 11 PASS) left no result file in the bundle. Running `tests/run_all_tests.R` on this version writes it
again, with the new scenario-E rows.

## 3. Still to be run on your machine (R, packages, your data)

1. `RWD_4Models_v20.59/R/tests/run_all_tests.R` and `RWDR_v20.59/tests/run_all_tests.R` (scenario E now checks the calendar years,
   the bound at the start, `OUTCOME_SCREEN = "keep"`, the panel's five columns, the two P00 reports, DESIGN vs PANEL and the evidence file).
2. `python validate_design_options.py` with R on the PATH (R == Python row for row on the new variants), `validate_r_parity.py`,
   `validate_model_parity.py`, `validate_out_of_core.py` (Dask / Spark).
3. Your data: R_P00 / P00, then `R_M01` — the run that stopped in v20.58. Read `panel_variation_by_block.csv` and, if the screen still
   flags year-seasons, `OUTCOME_SCREEN_NDVI.csv`: `min == max` on a cell means the export holds one value there.
