# Validation of v20.58 — every gate, run on the delivered bundles

Build machine: Linux, 2 cores, 7.5 GB RAM, no GPU. Python 3.11.15 (numpy 2.3.5, pandas 2.3.3, pyarrow 25.0.1, pyfixest 0.60.0, diff-diff 3.12.0, econml 0.17.0, esda 2.9.0, torch 2.14.0+cpu; out of core: dask 2026.8.0 / distributed 2026.8.0, pyspark 4.2.0); Java 21.0.10 (Spark); R 4.6.1 (fixest 0.14.2, HonestDiD 0.2.8, arrow 25.0.1, data.table 1.18.6.1); JupyterLab with the R kernel (IRkernel).
Inputs: synthetic exports inside your real shapefile polygons (your Koranahalli layout for the poison test: named exports + repeating tiles, pixels outside every polygon, a piece of Kodihalli's core, ring flips, a shifted grid, cloud gaps), your fund workbook (`Districtwise_Month_wise_Progress_with_DoseIntensity_and_SWS.xlsx`) and your crosswalk (`RWD_Sub_watershed_final_list.xlsx`). Not verifiable here: your A40 (`06_Validation\V00d_GPU_PATH_CHECK.py` runs on it), Windows paths, your own exports.

**When:** the gates ran on the delivered code. The last two fixes changed R files only: (1) R_P00 writes the same parquet metadata in memory and out of core, and the R test's scenario G guard -- after it the complete R test suite (in five chunks: the sandbox restarted twice during one long run), `validate_r_parity.py`, `validate_design_options.py`, the self-check and the requests ran again; (2) R M01 no longer stops when a covariate cannot be fitted (found by `tests/selftest.R` run from the delivered zip) -- after it `tests/selftest.R` and the scenarios that run M01 (A: known answers; H: out of core) ran again in both R projects, with the same results. The Python-only gates ran on the same Python code as delivered. Every gate of the four-model bundle ran on its final engines (the four-model R tests' A and H after fix 2).

## 1. The gates (RWD_Artal_v20.58 + RWDR_v20.58)

| Gate | Project | Result |
|---|---|---|
| `selfcheck.py` | RWD_Artal | CLEAN: 168 checks passed. The bundle is consistent. |
| `validate_requests.py` (every rule you set) | RWD_Artal | 39 PASS / 2 DECIDE (your decision, nothing changed) / 1 NOT HERE (needs your A40) / 0 FAIL |
| `validate_design_options.py` (every design option at the model stage, R == Python) | RWD_Artal + R | CLEAN: every option does exactly what it says, in Python and R, and the panel is never rebuilt. — 1,573 checks: 1573 PASS |
| `validate_known_answers.py` (every model against a known effect, +0.05) | RWD_Artal | CLEAN: every model with a known answer meets it. — single: 1 DATA GAP, 2 NO ANSWER, 42 PASS; staggered: 2 NO ANSWER, 43 PASS |
| `validate_location_poison.py` (YOUR RULE: every excluded row +5 — no number may move) | RWD_Artal | CLEAN: no excluded row reaches any model, and every effect model finds the truth. — 45 of 45 models identical clean vs poisoned; 36 effect models at the truth |
| `validate_model_parity.py` (R vs Python, primary routes, on the poison test's clean exports) | RWD_Artal + R | 36 IDENTICAL / 1 CLOSE / 5 CLOSE-ML / 3 both a data gap / 0 to read: [] / SE conventions differ: ['M39', 'M40', 'M42', 'M43'] |
| `validate_model_parity.py --engine` (R vs Python's own implementations) | RWD_Artal + R | 35 IDENTICAL / 5 CLOSE / 2 CLOSE-ML / 3 both a data gap / 0 to read: [] / SE conventions differ: ['M39', 'M40', 'M42', 'M43', 'M44'] |
| `validate_r_parity.py` (R structures the data as Python) | RWD_Artal + R | CLEAN: the R pipeline structures the data exactly as the Python pipeline does (14 checks). |
| `validate_all_models.py` (every model honours two scenarios; no placeholder, no all-NaN, no stray file) | RWD_Artal | CLEAN: every model honours the scenario; no placeholder, no all-NaN file, nothing written outside its folder. — 45 models: honours the scenario 43 yes, 2 data_gap |
| `validate_preprocessing.py` | RWD_Artal | CLEAN: the preparation path works end to end on synthetic exports. |
| `validate_inference.py` | RWD_Artal | CLEAN: inference validated -- no bias, design-based intervals cover the truth at the nominal rate. |
| `06_Validation\V00_RUN_ALL_VALIDATIONS.py` | RWD_Artal | 29/29 PASSED  (2 skipped: input only on another machine / session) |
| `validate_prep_notebooks.py` (P00 and MS01 end to end) | RWD_Artal | CLEAN: the preparation notebooks run end to end. |
| `validate_notebooks_cold.py` | RWD_Artal | CLEAN: every notebook finds and imports the engine on its own. |
| `validate_out_of_core.py` (beyond 98 %: Dask, Spark, batches == in memory) | RWD_Artal | CLEAN: the out-of-core path gives the in-memory numbers everywhere (15 checks IDENTICAL) — 15 of 15 checks IDENTICAL |
| `tests/run_all_tests.R` (scenarios A–H, the models on known answers, every notebook knitted and run in Jupyter) | RWDR | RESULT: PASS -- the R pipeline works on this machine — 8 DATA GAP, 290 PASS |
| `tests/selftest.R` (the whole R pipeline on a small export, known effect +0.05; two constant covariates) | RWDR | SELF-TEST: estimate 0.0504 (truth 0.0500) -> PASS |
| `nothing_missing` (every v20.57 file, Python name and R function still here) | both | NOTHING MISSING |

## 2. Your rule — only the current sub-watershed's own rows (the poison test)

Every row the design must leave out — other sub-watersheds' rows (Kodihalli's core piece), pixels outside every polygon, repeated tiles, the three pixels whose ring flips between exports (all their rows), rings 4–5 with `CONTROL_ZONES = 1-3`, the years before the window, the annual composite — is POISONED (+5 on the outcomes, +100 mm / +5 °C on the covariates) in every year, season and group (treated and control, pre and post). The same exports are written once clean and once poisoned; every number every model writes must be identical.

| Model | Identical (clean vs poisoned) | Cells differing | Kind | Estimate | SE | p | Near the truth |
|---|---|---|---|---|---|---|---|
| M01 | True | 0 | effect | 0.050389 | 0.000407 | 6.53e-10 | True |
| M02 | True | 0 | effect | 0.049894 | 0.000335 | 6.68e-07 | True |
| M03 | True | 0 | effect | 0.050560 | 0.000858 | 2.67e-08 | True |
| M04 | True | 0 | effect | 0.050618 | 0.000875 | 2.92e-08 | True |
| M05 | True | 0 | effect | 0.048814 | 0.00152 | 5.59e-07 | True |
| M06 | True | 0 | effect | 2.820920 | 0.196 | 2.9e-05 | — (no truth for this kind) |
| M07 | True | 0 | data gap | — | — | — | — (no truth for this kind) |
| M08 | True | 0 | data gap | — | — | — | — (no truth for this kind) |
| M09 | True | 0 | effect | 0.049954 | 0.000335 | 6.65e-07 | True |
| M10 | True | 0 | effect | -0.000943 | 0.000775 | 0.278 | True |
| M11 | True | 0 | effect | 0.048995 | 0.00115 | 1.32e-07 | True |
| M12 | True | 0 | effect | 0.050516 | 0.000427 | 3.06e-08 | True |
| M13 | True | 0 | effect | 0.050531 | 0.00121 | 1.51e-07 | True |
| M14 | True | 0 | effect | 0.050807 | 0.0006 | 4.35e-09 | True |
| M15 | True | 0 | effect | 0.000208 | 0.000291 | 0.514 | True |
| M16 | True | 0 | test | 0.000457 | — | 0.984 | — (no truth for this kind) |
| M17 | True | 0 | statistic | 0.579045 | 0.037 | 1.68e-56 | — (no truth for this kind) |
| M18 | True | 0 | statistic | 0.579045 | 0.037 | 1.68e-56 | — (no truth for this kind) |
| M19 | True | 0 | diagnostic | 0.060775 | — | — | — (no truth for this kind) |
| M20 | True | 0 | data gap | — | — | — | — (no truth for this kind) |
| M21 | True | 0 | effect | 0.051416 | 0.00186 | 1.17e-06 | True |
| M22 | True | 0 | effect | 0.049518 | 0.000704 | 1.1e-08 | True |
| M23 | True | 0 | effect | 0.050389 | 0.00037 | 0.0001 | True |
| M24 | True | 0 | effect | 0.000152 | 0.000724 | 0.842 | True |
| M25 | True | 0 | effect | 0.050429 | 0.00255 | 0.001 | True |
| M26 | True | 0 | effect | 0.050416 | 0.000376 | 4.36e-10 | — (no truth for this kind) |
| M27 | True | 0 | effect | 0.050420 | 0.000796 | 1.86e-08 | True |
| M28 | True | 0 | effect | 0.049890 | 0.000335 | 6.68e-07 | True |
| M29 | True | 0 | effect | 0.050039 | 0.000442 | 1.02e-09 | True |
| M30 | True | 0 | effect | 0.049464 | 0.00137 | 3.09e-07 | True |
| M31 | True | 0 | effect | 0.050603 | 0.000441 | 9.5e-10 | True |
| M32 | True | 0 | effect | 0.049346 | 0.000262 | 8.03e-11 | True |
| M33 | True | 0 | effect | 0.050180 | 0.000418 | 7.59e-10 | True |
| M34 | True | 0 | effect | 0.049894 | 0.000335 | 6.68e-07 | True |
| M35 | True | 0 | effect | 0.050318 | 0.000306 | 4.95e-07 | True |
| M36 | True | 0 | effect | 0.049393 | 0.000258 | 7.39e-11 | True |
| M37 | True | 0 | effect | 0.049393 | 0.000258 | 7.39e-11 | True |
| M38 | True | 0 | effect | 0.049393 | 0.000772 | 1.76e-08 | True |
| M39 | True | 0 | effect | 0.051069 | 0.00091 | 0 | True |
| M40 | True | 0 | effect | 0.050857 | 0.000869 | 0 | True |
| M41 | True | 0 | effect | 0.050578 | 0.000306 | 4.88e-07 | True |
| M42 | True | 0 | effect | 0.050455 | 0.000937 | 0 | True |
| M43 | True | 0 | effect | 0.051069 | 0.00091 | 0 | True |
| M44 | True | 0 | effect | 0.050251 | 0.00133 | 4.74e-313 | True |
| M45 | True | 0 | effect | 0.049612 | 0.000306 | 5.17e-07 | True |

R (`tests/run_all_tests.R` scenario F, the same layout and poison): 45 PASS, 3 DATA GAP.

## 3. R = Python, model by model

**Primary routes (verified packages / R routes first; what a run uses by default):** 36 IDENTICAL, 5 CLOSE-ML, 3 BOTH DATA GAP, 1 CLOSE.

| Model | Verdict | Python | R | SE (Python / R) | Detail |
|---|---|---|---|---|---|
| M07 | BOTH DATA GAP | — | — | — / — | no BM (benchmark-site) sub-watershed means in the panel -- the BM table was not found |
| M08 | BOTH DATA GAP | — | — | — / — | IV-DiD needs an instrument (a variable that shifts treatment but not the outcome) -- none exists in the data |
| M20 | BOTH DATA GAP | — | — | — / — | heterogeneity across sub-watersheds needs >= 2 sub-watersheds in the panel (the pooled run) |
| M39 | CLOSE-ML | 0.0510695 | 0.0506294 | 0.00091 / 0.00086 | Python 0.0510695 (SE 0.00091) / R 0.0506294 (SE 0.00086) / difference +0.00044 |
| M40 | CLOSE-ML | 0.0508565 | 0.049258 | 0.000869 / 0.000915 | Python 0.0508565 (SE 0.000869) / R 0.049258 (SE 0.000915) / difference +0.0016 |
| M41 | CLOSE-ML | 0.0505781 | 0.0503891 | 0.000306 / 0.000306 | Python 0.0505781 (SE 0.000306) / R 0.0503891 (SE 0.000306) / difference +0.000189 |
| M42 | CLOSE-ML | 0.0504553 | 0.0506983 | 0.000937 / 0.000869 | Python 0.0504553 (SE 0.000937) / R 0.0506983 (SE 0.000869) / difference -0.000243 |
| M43 | CLOSE-ML | 0.0510695 | 0.0506294 | 0.00091 / 0.00086 | Python 0.0510695 (SE 0.00091) / R 0.0506294 (SE 0.00086) / difference +0.00044 |
| M44 | CLOSE | 0.0502512 | 0.0502202 | 0.00133 / 0.00133 | Python 0.0502512 (SE 0.00133) / R 0.0502202 (SE 0.00133) / difference +3.1e-05 |

**Python's own implementations (no package, no R: `PREBUILT_MODE = "off"`):** 35 IDENTICAL, 5 CLOSE, 3 BOTH DATA GAP, 2 CLOSE-ML.

| Model | Verdict | Python | R | SE (Python / R) | Detail |
|---|---|---|---|---|---|
| M07 | BOTH DATA GAP | — | — | — / — | no BM (benchmark-site) sub-watershed means in the panel -- the BM table was not found |
| M08 | BOTH DATA GAP | — | — | — / — | IV-DiD needs an instrument (a variable that shifts treatment but not the outcome) -- none exists in the data |
| M19 | CLOSE | 0.0607765 | 0.0607747 | — / — | Python 0.0607765 (SE nan) / R 0.0607747 (SE nan) / difference +1.87e-06 |
| M20 | BOTH DATA GAP | — | — | — / — | heterogeneity across sub-watersheds needs >= 2 sub-watersheds in the panel (the pooled run) |
| M39 | CLOSE | 0.0508462 | 0.0506294 | 0.00104 / 0.00086 | Python 0.0508462 (SE 0.00104) / R 0.0506294 (SE 0.00086) / difference +0.000217 |
| M40 | CLOSE-ML | 0.0507905 | 0.049258 | 0.000869 / 0.000915 | Python 0.0507905 (SE 0.000869) / R 0.049258 (SE 0.000915) / difference +0.00153 |
| M41 | CLOSE-ML | 0.0502579 | 0.0503891 | 0.000306 / 0.000306 | Python 0.0502579 (SE 0.000306) / R 0.0503891 (SE 0.000306) / difference -0.000131 |
| M42 | CLOSE | 0.05055 | 0.0506983 | 0.000937 / 0.000869 | Python 0.05055 (SE 0.000937) / R 0.0506983 (SE 0.000869) / difference -0.000148 |
| M43 | CLOSE | 0.0508462 | 0.0506294 | 0.00104 / 0.00086 | Python 0.0508462 (SE 0.00104) / R 0.0506294 (SE 0.00086) / difference +0.000217 |
| M44 | CLOSE | 0.0499453 | 0.0502202 | 0.000306 / 0.00133 | Python 0.0499453 (SE 0.000306) / R 0.0502202 (SE 0.00133) / difference -0.000275 |

CLOSE = the same estimator, a difference from the packages' own numerical tolerance; CLOSE-ML = the machine-learning models (different random forests in the two languages), within 2 SE of each other and each at the known answer; BOTH DATA GAP = the same data gap in both.

## 4. Beyond 98 % of the RAM: out of core on Dask, Spark and the built-in batches

Python (`validate_out_of_core.py`; every file of every model compared with the in-memory run):

| Check | Engine | Files | Differences | Verdict | Detail |
|---|---|---|---|---|---|
| engine available | dask | 0 | 0 | AVAILABLE | dask 2026.8.0 / distributed 2026.8.0 |
| engine available | spark | 0 | 0 | AVAILABLE | pyspark 4.2.0 (Java: /usr/lib/jvm/java-21-openjdk-amd64/bin/java) |
| engine available | batches | 0 | 0 | AVAILABLE | built-in (one partition after another, in this process) |
| known answers: single | dask | 29 | 0 | IDENTICAL | 14 s, 5 pixel partitions |
| known answers: single | spark | 29 | 0 | IDENTICAL | 23 s, 5 pixel partitions |
| known answers: single | batches | 29 | 0 | IDENTICAL | 7 s, 5 pixel partitions |
| known answers: staggered | dask | 29 | 0 | IDENTICAL | 15 s, 5 pixel partitions |
| known answers: staggered | spark | 29 | 0 | IDENTICAL | 27 s, 5 pixel partitions |
| known answers: staggered | batches | 29 | 0 | IDENTICAL | 10 s, 5 pixel partitions |
| your layout: fund timing, location rule, fragments, overlaps | dask | 29 | 0 | IDENTICAL | 6 pixel partitions |
| your layout: fund timing, location rule, fragments, overlaps | spark | 29 | 0 | IDENTICAL | 6 pixel partitions |
| your layout: fund timing, location rule, fragments, overlaps | batches | 29 | 0 | IDENTICAL | 6 pixel partitions |
| your layout POISONED, out of core (every excluded row +5): the clean numbers | dask | 29 | 0 | IDENTICAL | no excluded row reaches any model |
| P00 PASS A + PASS B, every block out of core (pixel-range pieces) | dask | 4 | 0 | IDENTICAL | the same panel: 9,786 rows x 60 columns, row for row |
| P00 PASS A + PASS B, every block out of core (pixel-range pieces) | spark | 4 | 0 | IDENTICAL | the same panel: 9,786 rows x 60 columns, row for row |
| P00 PASS A + PASS B, every block out of core (pixel-range pieces) | batches | 4 | 0 | IDENTICAL | the same panel: 9,786 rows x 60 columns, row for row |
| the switch at 98 %: a budget below the need -> out of core by itself (M01) | first available | 12 | 0 | IDENTICAL | run_mode -> out_of_core; the in-memory numbers |
| streaming (row group by row group): the location table and the outcome identities | batches | 2 | 0 | IDENTICAL | 4 identities, 0 near-duplicate pairs, 3 ring conflicts -- the same |

R (`tests/run_all_tests.R` scenario H):

| Step | Status | Detail |
|---|---|---|
| M01 M02 M16 M34 out of core on Dask (5 pixel partitions) == in memory | PASS | 487 numbers in 17 files; largest difference 2.7e-11 (relative 1.4e-08: fixest converges to 1e-8) |
| M01 M02 M16 M34 out of core on Apache Spark (5 pixel partitions) == in memory | PASS | 487 numbers in 17 files; largest difference 2.7e-11 (relative 1.4e-08: fixest converges to 1e-8) |
| M01 M02 M16 M34 out of core on R batches (5 pixel partitions) == in memory | PASS | 487 numbers in 17 files; largest difference 2.7e-11 (relative 1.4e-08: fixest converges to 1e-8) |
| Apache Spark == Dask: every number identical (the same R code on every engine) | PASS | 487 numbers |
| R batches == Dask: every number identical (the same R code on every engine) | PASS | 487 numbers |
| the switch at 98 %: a RAM budget below the need -> out of core BY ITSELF, the in-memory numbers | PASS | run_mode_R: out_of_core (the sample needs ~0.01 GB in RAM and 0.00 GB are free below 98 %); 487 numbers, largest difference 2.7e-1 |
| the design from the data out of core (pixel partitions) == in memory: the same cells and the same choice | PASS | pre 2016,2017,2018,2019,2020,2021,2022,2023, post 2024,2025, rings 1,2,3,4,5, seasons all |
| the outcome identities row group by row group == all rows at once | PASS | 4 identities: NDMI = -0.1 +0.6 x NDVI; LSWI = -0.1 +0.6 x NDVI; LSWI = 0 +1 x NDMI; WSSI = 1 -1 x ESI |
| R_P00 block by block on R batches, every block in 3 pixel groups == in memory: the panel row for row (schema too) and every report | PASS | 9,812 rows x 41 columns |
| R_P00 block by block on Dask == in memory: the panel row for row (schema too) and every report | PASS | 9,812 rows x 41 columns |
| R_P00 block by block on Apache Spark == in memory: the panel row for row (schema too) and every report | PASS | 9,812 rows x 41 columns |

## 5. The four-model pipeline (RWD_4Models_v20.58)

`python validate_4models.py` on the delivered bundle:

```
gate             verdict     min  the validator's last line
selfcheck        PASS        2.9  CLEAN: 133 checks passed (19 of this project, 114 of the engine). The four-model bundle is consistent.
known_answers    PASS        0.1  CLEAN: every model with a known answer meets it.
poison           PASS       10.0  CLEAN: no excluded row reaches any model, and every effect model finds the truth.
parity_primary   PASS        1.4  4 IDENTICAL | 0 CLOSE | 0 CLOSE-ML | 0 both a data gap | 0 to read: [] | SE conventions differ: []
parity_engine    PASS        4.8  4 IDENTICAL | 0 CLOSE | 0 CLOSE-ML | 0 both a data gap | 0 to read: [] | SE conventions differ: []
r_parity         PASS        3.6  CLEAN: the R pipeline structures the data exactly as the Python pipeline does (14 checks).
design_options   PASS        0.8  CLEAN: every option does exactly what it says, in Python and R, and the panel is never rebuilt.
all_models       PASS        3.2  CLEAN: every model honours the scenario; no placeholder, no all-NaN file, nothing written outside its folder.
preprocessing    PASS        0.5  CLEAN: the preparation path works end to end on synthetic exports.
inference        PASS        0.9  CLEAN: inference validated -- no bias, design-based intervals cover the truth at the nominal rate.
prep_notebooks   PASS        6.1  CLEAN: the preparation notebooks run end to end.
notebooks_cold   PASS        0.3  CLEAN: every notebook finds and imports the engine on its own.
V00              PASS        0.7  29/29 PASSED  (2 skipped: input only on another machine / session)
out_of_core      PASS       10.8  CLEAN: the out-of-core path gives the in-memory numbers everywhere (15 checks IDENTICAL)
r_tests          PASS       26.2  RESULT: PASS -- the R pipeline works on this machine
========================================================================================================================
CLEAN: every gate of the four-model bundle passed (15 gates; run in four parts: --only)
```

## 6. Nothing missing

```
== RWD_Artal_v20.57 -> RWD_Artal_v20.58: 184 files -> 198; missing 0; new 14
   new     R/lib/reward_ooc_engine.py
   new     R/lib/reward_ooc_task.R
   new     R/lib/reward_outofcore.R
   new     R/lib/reward_prep_ooc.R
   new     docs/VALIDATION_LOCATION_POISON_v20.58.csv
   new     docs/VALIDATION_MODEL_PARITY_ENGINE_v20.58.csv
   new     docs/VALIDATION_MODEL_PARITY_v20.58.csv
   new     docs/VALIDATION_OUT_OF_CORE_v20.58.csv
   new     python/DIDRDP_ALLRunDID_v20/_location.py
   new     python/DIDRDP_ALLRunDID_v20/_ooc_models.py
   new     python/DIDRDP_ALLRunDID_v20/_outofcore.py
   new     python/DIDRDP_ALLRunDID_v20/validate_location_poison.py
   new     python/DIDRDP_ALLRunDID_v20/validate_model_parity.py
   new     python/DIDRDP_ALLRunDID_v20/validate_out_of_core.py
== RWDR_v20.57 -> RWDR_v20.58: 140 files -> 148; missing 0; new 8
   new     docs/VALIDATION_LOCATION_POISON_v20.58.csv
   new     docs/VALIDATION_MODEL_PARITY_ENGINE_v20.58.csv
   new     docs/VALIDATION_MODEL_PARITY_v20.58.csv
   new     docs/VALIDATION_OUT_OF_CORE_v20.58.csv
   new     lib/reward_ooc_engine.py
   new     lib/reward_ooc_task.R
   new     lib/reward_outofcore.R
   new     lib/reward_prep_ooc.R
NOTHING MISSING
```

Every file, Python function / class / constant and R function of v20.57 is in v20.58 (RWD_Artal1 dropped by your instruction: one Python project and one R project). Your paths (`_paths.py`, `reward_paths.R`) are unchanged.
