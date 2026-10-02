# Validation of v20.56 — every gate, run on the delivered bundles

Machine: Ubuntu, 2 cores / 7 GB, no GPU; Python 3.11 (pyfixest 0.60, diff-diff 3.12, econml 0.17, pandas 2.3.3,
pyarrow 25); R 4.6.1 with all 40 packages; IRkernel registered. The three bundles were tested as unzipped
(`RWD_Artal_v20.56`, `RWD_Artal1_v20.56`, `RWDR_v20.56`). Your A40 checks (rule 22, V00d) run on your machine.

## Python — RWD_Artal_v20.56 and RWD_Artal1_v20.56 (the same engine; Artal1 keeps its own `_paths.py`)

| Gate | Result |
|---|---|
| `selfcheck.py` | **CLEAN — 152 checks** (new `check_v20_56`: no chunking -- MEMORY_POLICY raise, recommend_mode memory, M01_MODE memory, the GPU demeaner whole-matrix; R packages binary-first with Rtools awareness; `check_v20_55`: season modes, the overlap option on a pooled frame, the one-to-one pixel merge, the common-shock rule, the period-level design SE, the package chain and run-time install, the 10× limits, every R mirror) |
| `validate_requests.py` | **28 PASS, 2 DECIDE, 1 NOT HERE, 0 FAIL** (rules 30–31 new: no chunking -- 180 of 180 rows loaded and estimated; R packages pre-built first, Rtools only when unavoidable; rules 24–29 from v20.55: seasons + years, R == Python, packages, overlap option, unbalanced panel, defects fixed) |
| `validate_r_parity.py` (needs R) | **CLEAN — 14 checks**: the same design (pre 2016–2021, post 2022–2025, rings, seasons), the 7,800-row panel value by value, the NDVI (5,006 rows) and EVI (5,121 rows) samples, the rows selected under `all` / `seasonal` / `yearly` / `rabi` / `kharif+rabi` and `OVERLAP_ROWS = keep`, the unbalanced-panel rule (115 cells, 84 pixels keep their other periods, in both), M01 0.05109550 (Python engine) vs 0.05109549 (R fixest) |
| `validate_preprocessing.py` | CLEAN — the preparation path end to end on synthetic exports |
| `validate_inference.py` | CLEAN — no bias; design-based intervals cover the truth at the nominal rate |
| `validate_all_models.py` | 45 / 45 models ok under both scenarios; 40 honour the scenario, 5 documented data gaps; no placeholder value in any result |
| `06_Validation/V00_RUN_ALL_VALIDATIONS.py` | 29 / 29 passed (2 skipped: input on another machine / the GPU) |
| `validate_prep_notebooks.py all` | P00 (22 cells), MS01, TWO_SWS (the pooled two-sub-watershed path): every cell ran, no exception, no [FAILED] |
| `validate_notebooks_cold.py` | 54 notebooks start from their own folders with nothing injected |
| P00 as you run it (in the gate) | `Python packages: 16 of 16 installed` · `R packages: 40 of 40 installed (R 4.6.1)` · pre-built readiness: 43 of 45 models computed by a verified package |

The package chain was exercised: a package absent here was installed through `pip --prefer-binary` (route recorded), a
non-existent name went through wheel → source → local wheels and ended as "NOT installed" with the engine fallback named; in
R, `install_package_chain()` installed a missing CRAN package from source into a temporary library.

## R — RWDR_v20.56

| Gate | Result |
|---|---|
| `tests/selftest.R` | PASS — estimate 0.0504 (truth 0.0500) |
| `tests/run_all_tests.R` (full) | **201 PASS, 6 DATA GAP, 0 FAIL** — scenario A (one sub-watershed) 45 models; **scenario D (new)** 11 checks; scenario C (covariate rules, `MEMORY_SHARE`, paths) 3; scenario B (eight sub-watersheds, two cohorts, fund file, folder names) 45 models + 3 structure checks; then **all 49 notebooks knitted** as RStudio does and **all 49 executed in Jupyter through IRkernel** |
| the 6 data gaps | A: M06 (no dose without a fund file), M07 (BM means need the pooled run), M08 (no instrument), M20 (needs ≥ 2 sub-watersheds), M45 (needs the pooled multi-site input); B: M08 — each the data lacking what that model needs, as documented |
| scenario D, each PASS | preparation (two sub-watersheds, Rabi in some years only, a 3 m-shifted 2025 grid, an annual composite without weather, an overlap pixel) · `SEASONS = "all"` kept although the data-driven choice is `yearly` · 2023 reported as a common shock, post window 2022–2025 kept, 2025 grid merged (linkage 1) · one-to-one merge (144 pixels onto 144) · season modes: all = 2,610 rows = seasonal 1,740 + yearly 870 · unbalanced panel: 3 NDVI cells leave the NDVI estimation only · annual weather filled with the pixel-year's seasonal mean (490 rows, exact) · `OVERLAP_ROWS` drop / keep · `POOLED_FE` site × year × season · M01 on seasons + years recovers +0.05 · 40 of 40 packages confirmed |

## What changed in the numbers you will see
- With `SEASONS = "all"` the estimation samples hold the annual composite **and** the seasonal rows (3–4× the rows of the
  annual-only runs until v20.54), the units are pixel × season series, the periods year × season cells, and the design-based
  inference reports both the year-level and the year × season draws.
- A year in which the core and the rings move together is no longer cut out of the post period; the year fixed effects absorb it.
- In a pooled panel the period effect is sub-watershed × year × season in both languages (Python already did this; R now does).
- No regression is chunked, streamed, thinned or sampled: every DiD model runs on all its rows in RAM (GPU below 95 % VRAM), or stops with a message.
- The results are what your exports give: the code no longer removes seasons, years or pixels that carry information, and the
  two pipelines agree row for row.
