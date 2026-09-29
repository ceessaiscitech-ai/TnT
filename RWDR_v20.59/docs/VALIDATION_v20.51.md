# Validation of RWDR v20.51

| check | result |
|---|---|
| `tests/run_all_tests.R quick` | PASS: 89 pass, 6 genuine data gaps, 0 failures (fund file read in both layouts) |
| your sequence replayed: R_P00 setup -> `tests/selftest.R` -> R_P00 setup | data root `D:/LKT/RWDR/data` before and after; self-test 0.0504 (truth 0.05) |
| fund workbook in your layout ("<SWS> SWS in <District>") | R dose == Python dose for 18 of 18 sub-watershed-seasons (difference 0) |
| `00_SETUP.R` | 40 of 40 packages ready; out-of-date packages updated; missing dependencies installed |

# Validation of v20.50 (the three projects, each tested on its own)

Environment: Ubuntu 24.04, R 4.6.1 + all packages + polars, JupyterLab 4.6 with the R kernel (IRkernel), Python 3.12 with
pyfixest 0.60, diff-diff 3.12, econml 0.17, pyarrow 25, pandas 2.3 (and 3.0), torch 2.14 (CPU build — no GPU here; the GPU
code ran on a stand-in device; on your A40 the same checks run on the real device).

| project | check | result |
|---|---|---|
| RWD_Artal | `selfcheck.py` (stand-alone: no R project beside it) | 134 checks, 0 failures, engine 20.50 |
| RWD_Artal | `validate_preprocessing.py` incl. the NEW process-pool test (in-RAM blocks handed to 2 worker processes as files vs the sequential panel) | CLEAN — identical panels |
| RWD_Artal | `06_Validation/V00d_GPU_PATH_CHECK.py` | 5/5 (stand-in device) |
| RWD_Artal | P12 estimator routes; permutation inference now through the package | 4/4 verified; M25 via pyfixest 0.60 (0.0492 for a true 0.05), package setting left unchanged |
| RWD_Artal | automatic GPU self-test | a correct device stays on; a device that computes wrongly (0.1 % error) is switched off, the CPU computes |
| RWD_Artal1 | `selfcheck.py` (stand-alone) | 134 checks, 0 failures, engine 20.50 |
| RWDR | `tests/run_all_tests.R quick` (stand-alone) | PASS, 0 failures — one sub-watershed: 41 pass + 5 genuine data gaps; eight sub-watersheds: 48 pass + 1 (M08, no instrument). From the project folder: `R_M01.Rmd` knitted and `R_M16.ipynb` run in Jupyter (IRkernel) — both clean |
| all | v20.49 results carried over (unchanged code paths): Python gates under pandas 2.3 and 3.0, 18/18 Python package routes, 33/34 R routes, all 48 R notebooks knitted (RStudio engine) and run in Jupyter / IRkernel | see CHANGELOG v20.49 |

Tested before the split and unchanged by it: the R notebooks (v20.49: 48/48 knitted, 48/48 in Jupyter, no hidden model error).
