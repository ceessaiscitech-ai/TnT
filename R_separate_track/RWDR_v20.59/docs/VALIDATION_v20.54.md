# Validation of v20.54 (each project tested on its own)

**Environment**
- Ubuntu 24.04 on 2 cores and 7 GB of RAM.
- R 4.6.1 with all 40 packages. synthdid was installed from its r-universe copy, because GitHub cannot be reached from here;
  it reproduces the published Proposition 99 estimate, −15.60. qte is version 2.0.0.
- JupyterLab with the R kernel (IRkernel).
- Python 3.11 with pyfixest 0.60, diff-diff 3.12, econml 0.17, DoubleML 0.11, esda 2.9, pandas 2.3.3, pyarrow 25 and torch 2.14.
- There is no GPU here. The GPU code runs on a stand-in device; on your A40 the same checks run on the real one.

| project | check | result |
|---|---|---|
| RWD_Artal | `selfcheck.py` | 138 checks, 0 failures |
| RWD_Artal | `validate_requests.py` (new: each of your rules, run on the code) | 20 PASS, 2 DECIDE (your decisions, see REGRESSION_AUDIT), 1 NOT HERE (the A40 check: no GPU here), 0 FAIL |
| RWD_Artal | `validate_preprocessing.py` | CLEAN (including: the process pool equals the sequential panel; the negative barrier on / off / 'missing') |
| RWD_Artal | `validate_inference.py` | CLEAN: bias ≤ 0.0003; the design-based 95 % intervals cover 96 %, 97 % and 95.5 %; false positives 4.5 % |
| RWD_Artal | `validate_all_models.py` | all 45 models run in both scenarios, with no placeholder value and no all-NaN file. 37 estimate and 8 stop at documented data gaps. With the routes verified, 40 estimate and 5 stop at gaps |
| RWD_Artal | `06_Validation/V00_RUN_ALL_VALIDATIONS.py` | 29/29. D7, the paths check, now runs on every system; 2 checks are skipped because your workbooks are not here |
| RWD_Artal | `V00b` streaming / `V00c` process pool / `V00d` GPU path | 8/8 / 8/8 / 5/5 |
| RWD_Artal | `validate_notebooks_cold.py` / `validate_prep_notebooks.py` | 54 notebooks start from their own folders / P00, MS01 and two sub-watersheds run end to end |
| RWD_Artal | P12 on the installed packages | 4/4 estimator routes and 14/14 model routes verified on the known answer. 33/34 R routes verified: M27's R package fails inside the package, so M27 uses its verified diff-diff route |
| RWD_Artal1 | `selfcheck.py`, `V00`, `V00c`, `validate_requests.py`, cold-start notebooks | 138 / 29/29 / 8/8 / 20 PASS + 2 DECIDE + 1 NOT HERE / 54 clean. The engine is identical to RWD_Artal's except `_paths.py` |
| RWDR | `tests/run_all_tests.R` (full) | **190 PASS, 6 data gaps, 0 FAIL**. Scenario A: one sub-watershed. Scenario B: eight sub-watersheds, two cohorts, names-only folders and a fund file. Scenario C (new): the covariate rules, MEMORY_SHARE, and paths off Windows. Then all 49 notebooks were knitted as RStudio does it (49/49) and run in Jupyter through IRkernel (49/49) |
| all | v20.47's own tests on the v20.54 code | the same results as on v20.53, plus one intended difference; see REGRESSION_AUDIT_v20.54.md §4 |

The 6 R data gaps are real, because the synthetic data lack what these models need:
- In scenario A, one sub-watershed has no fund dose (M06), no ground truth (M07), no instrument (M08), no second
  sub-watershed (M20) and no pooled set of sites (M45).
- In scenario B there is no instrument (M08).

**Independent review.** A separate reviewer re-ran selfcheck (138), V00 (29/29), V00c, validate_preprocessing,
validate_requests and the quick R test on copies of v20.54. It confirmed every fix and found four edge cases, which
were fixed before delivery (see REGRESSION_AUDIT_v20.54.md §8). The gates above were then run again on the final code.
