# Validation of RWD_4Models v20.58 — P00 + M01, M02, M16, M34 (Python and R)

Build machine: Linux, 2 cores, 7.5 GB RAM, no GPU. Python 3.11.15 (numpy 2.3.5, pandas 2.3.3, pyarrow 25.0.1, pyfixest 0.60.0, diff-diff 3.12.0, econml 0.17.0, esda 2.9.0, torch 2.14.0+cpu; out of core: dask 2026.8.0 / distributed 2026.8.0, pyspark 4.2.0); Java 21.0.10; R 4.6.1 (fixest 0.14.2, HonestDiD 0.2.8, arrow 25.0.1, data.table 1.18.6.1).

`python selfcheck_4models.py`: CLEAN: 133 checks passed (19 of this project, 114 of the engine). The four-model bundle is consistent.

`python validate_4models.py` — every validator of the full pipeline, run on this bundle (each covers exactly this project's notebooks and models); exit code 0 only when every gate is clean:

```
========================================================================================================================
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

R tests of this bundle (`R/tests/run_all_tests.R`, the r_tests gate): A: 6 PASS, B: 23 PASS, C: 4 PASS, D: 11 PASS, E: 17 PASS, F: 7 PASS, H: 11 PASS.

The engines of this bundle are the full pipeline's v20.58 files byte for byte; their full gates (all 45 models, R and Python) are in `VALIDATION_v20.58.md` of RWD_Artal / RWDR (a copy is in this folder).
