# RWDR — the REWARD DiD pipeline in R (RStudio and Jupyter) — v20.59

> **3 Oct — this bundle is the R pipeline on its own** (details: `docs/CHANGELOG_R_v20.59.md`; what ran: `docs/VALIDATION_R_v20.59.md`).
> * **Your R_P00 run that hung for hours after the duplicate step:** the pixel-variation step gathered every column per group per outcome
>   (2–8 hours at 71 M rows, silent); it, the de-duplication and the pixel registry were rewritten (same numbers, checked against the old
>   bodies), the per-file list is freed, and **every step prints a line before it starts and when it ends**. A valid panel on disk is kept
>   (`FORCE_REBUILD <- FALSE`); the panel is written beside its name and renamed into place.
> * **From the Python side (1–2 Oct):** a p-value on every result row (`ensure_p_value_R`), `results/HEADLINES_ALL_VARIABLES_R.csv` across
>   variables, `output/panel_precision_report_R.csv` (R stores doubles; the report proves it and flags a rounding upstream), the pipeline's
>   own products inside the exports folder never read as exports, worker processes capped at 60 on Windows.
> * `tests/test_3oct_additions.R` (27 checks) and `tests/benchmark_prep_scale.R` (time R_P00 on your machine) are new.
>
> **v20.59 — what changed for you** (details: `docs/CHANGELOG_v20.59.md`; what ran here: `docs/VALIDATION_v20.59.md`)
> * **The panel carries the DiD design columns** — `treat` (buffer 0), `control` (rings 1–5), `post` = the exports' `Treat` flag
>   (1 = post, 0 = pre), `pre` = 1 − post, `did` = treat × post — from P00 / R_P00 (`PERIOD_RULE`: `"treat"` the exports' column,
>   `"year"` the rule `Year >= TREATMENT_YEAR`, `"both"` = the two must agree, a disagreeing row leaves), with
>   `input_design_audit(_R).csv` — every input file confirmed: `Treat` 1 = post / 0 = pre, `buff_km` 0 = treatment / 1–5 = control —
>   The panel KEEPS every fill value and gap-filled row (P00 / R_P00 say so with the counts); `OUTCOME_SCREEN` (drop | keep | off) and
>   `EXCLUDE_GAPFILLED` decide what a MODEL estimates on — set as defaults in P00_Settings / R_P00 and, for each model, in its own first cell.
>   Keeping a fill year-season dilutes the DiD (the treated-control gap in it is 0); the screen's warning says so under keep.
>   Every logical processor of every Windows processor group works (P00 pools without the 61-worker limit; R's `N_THREADS` likewise);
>   blocks above 256 MB go to shard files at once instead of holding RAM; the GPU line is printed at PASS A. The working sub-watershed
>   rule (every row by its latitude / longitude; one run = the majority sub-watershed, pooled = each row in its own) is printed with the
>   run's numbers, and its switches (`SUB_WATERSHEDS`, `SITE_GEOMETRY_CHECK`, `BUFF_FROM_GEOMETRY`) sit in P00_Settings and R_P00.
>   `panel_design_check(_R).csv` and `panel_variation_by_block.csv` (which year-seasons hold one value for every pixel).
>   Every model still applies ITS OWN design when it runs and prints **`DESIGN vs PANEL`**: on how many rows your settings
>   (the fund timing, `TREATMENT_YEAR`, the transition year) change the period split against the panel's columns.
> * **`PRE_YEARS` / `POST_YEARS` take a calendar year** (`2015` = the first pre year, `2025` = the last post year) as well as
>   a count (`4`); a year that leaves no pre year (`2022` with the start in 2022 — v20.58 printed `USED: from 0`) is said and
>   every year before the start is used.
> * **The outcome screen explains itself and can be kept:** `OUTCOME_SCREEN_<outcome>.csv` (rows, pixels, mean, SD, min, max per
>   year-season) beside every result; the model option `OUTCOME_SCREEN = "drop" | "keep" | "off"`; a refusal names the file and the
>   option instead of only "Re-export it".
> * Re-run P00 / R_P00 first (the panel gains the five columns), then the models.


**Where things go**
```
D:\LKT\RWDR\
├── RWDR_v20.59\             ← this project (unzip here)
└── data\                    ← your exports (was D:\LKT\TST_ArtalR) -- MIGRATE_DATA.bat moves them
    └── output\              ← everything the pipeline writes
```
## A. Once
1. R >= 4.3 (and on Windows Rtools) from cran.r-project.org; RStudio.
2. Unzip into `D:\LKT\RWDR\`; double-click `MIGRATE_DATA.bat` (until then the pipeline uses `D:\LKT\TST_ArtalR` and says so).
3. RStudio → File → Open Project → `RWDR.Rproj`. Session → Restart R, then open `00_SETUP.R` → **Source** (every package: a pre-built
   binary where one exists, else the source — CRAN → the author's r-universe → GitHub → its source archive → a mirror; registers the R
   kernel with Anaconda's Jupyter). The same chain runs at run time: a package a model needs and lacks is installed then
   (`AUTO_INSTALL_PACKAGES` in `lib/reward_paths.R`), and every notebook starts with `R packages: 40 of 40 installed`.
4. `tests\run_all_tests.R` → **Source**. It must end with `RESULT: PASS`: two synthetic data sets (one sub-watershed; eight with
   two implementation years, a fund file and folders named only by name; v20.55: a third with seasons missing in some years, a
   shifted grid, an overlap pixel; v20.57: a fourth with a fragment of another sub-watershed, a stray file and a fund workbook, on which
   every design option is set as a model notebook sets it and must do exactly that; v20.58: F -- your Koranahalli layout written twice, the
   second time with every row the design must leave out poisoned: every number must stay identical -- and G -- the batch paths give the
   all-at-once answer), all 45 models against their known answers, then all 49 notebooks knitted as RStudio does and run in Jupyter
   through IRkernel. (`Rscript tests/run_all_tests.R quick` = models only.)

## B. Your data
1. Exports under one folder (any sub-folders). **4 Oct:** set it as `PARENT_DIR` in the FIRST chunk of `R_P00_Prepare_Panel` (default
   `D:/LKT/RWDR/data`); it is the parent directory of the whole processing (output = `PARENT_DIR/output`) and the model notebooks follow it. Fill each sub-watershed's implementation year in `RWDR_v20.59\data\sites\sites.csv` (the project's own
   `data` folder — shapefile, sites, BM means — not your exports folder).
2. `rstudio\R_P00_Prepare_Panel.Rmd` → Run All — builds the panel ONCE (v20.57: it takes no design setting; nothing of the design is
   written into the panel). It also reads your fund workbook (`results\FUND\FUND_TIMING_AND_DOSE.md`).
3. Any `rstudio\R_Mxx.Rmd` → its settings chunk: `OUTCOME` and **the design of this run** — `DESIGN_MODE`, `TREATMENT_TIMING`
   (`"fund"` = your fund workbook, the default | `"registry"` | `"fixed"`), `TREATMENT_YEAR`, `FUND_START_RULE`, `DOSE_VARIABLE`,
   `CONTROL_RINGS`, `PRE_YEARS`, `POST_YEARS`, `SEASONS`, `EXCLUDE_TRANSITION_YEAR`, `UNIT_FE`, `OVERLAP_ROWS`, `FRAGMENT_RULE`,
   `POOLED_FE`, `EXCLUDE_GAPFILLED`, `COVARIATES` → Run All. A value you set is used exactly as set; `"data"` lets the data decide.
   The run prints DESIGN IN EFFECT (your setting, the value used, where it came from) and saves it as `DESIGN_IN_EFFECT.csv` beside
   the results. Change a setting and re-run that notebook only — never R_P00. 4. `R_V01_Results_Audit.Rmd`.
Results: `<PARENT_DIR>\output\results\<model>\<design tag>\` — each with the estimate, SE, the design-based SE and its p-value.

## Jupyter
The same 49 notebooks are in `jupyter\` (kernel **R**). RStudio is the recommended place for long runs.

## Notes
- Names >= 80 % similar are the same sub-watershed (export folders, file names, the fund file); control names never match.
- Running beside the Python projects: each pipeline uses the whole machine (v20.52: no split, no cap). Optional: `AUTO_SPLIT <- TRUE`
  (reward_design.R) splits it automatically; `MEMORY_SHARE` (reward_paths.R) caps this one by hand.
- On Linux, HonestDiD (M34) needs GLPK (`apt install libglpk-dev`); `tests/install_and_test_linux.sh` does everything there.

## v20.51
- After a test, the session points at your data again (the tests used to leave their sample folder set, so `R_P00` read the 10 sample files instead of your exports).
- The fund workbook is read (the dose was empty in every R run before).
- `00_SETUP.R` updates out-of-date packages and installs missing dependencies (M14 needed `chk`).

## v20.52
- `rstudio/R_D01_Effect_Diagnostics.Rmd` (and the `.ipynb`): why the effect is what it is -- nine checks on your panel.
- Rows filled from history are left out of every estimate (as in Python); HonestDiD uses a design-based covariance.
- No caps: every core, no split.

## v20.54
- Regression audit against every earlier version: nothing lost (`docs/REGRESSION_AUDIT_v20.54.md`).
- Your covariate rules as in Python: an exported exact 0 of Rain / Tmax / Tmean / Tmin is a masked cell (missing), fill values
  (-9999, the -10 C clamp) are missing, negatives are floored at 0 -- and `ALLOW_NEGATIVE_COVARIATES <- TRUE` (reward_paths.R)
  removes that barrier, as in Python. Re-run `R_P00` to rebuild the panel with these rules.
- `MEMORY_SHARE` works again (1.0 = no cap, the default). M04 / M09 / M28 no longer print qte's inapplicable notes or
  "NAs introduced by coercion" (results unchanged). The model line shows the model's own p-value next to the design p-value
  (M16: the pre-trend test's p). `00_SETUP.R` has a last-resort source for synthdid when GitHub cannot be reached.

## v20.55
- **Seasons AND years together, as you asked.** `SEASONS <- "all"` (the default in reward_paths.R; since v20.57 set in each model notebook) estimates on the annual composite
  and the Kharif / Rabi / Zaid rows with pixel × season and year × season fixed effects — and the recommended design no longer
  replaces it with `"yearly"` when a season is missing in some year (until v20.54 that override put every model on the annual
  composite alone). Options: `"seasonal"`, `"yearly"`, `"Rabi"`, `c("Kharif", "Rabi")`, `"auto"`. Every result also carries the year ×
  season design-based SE (`se_design_period`, `p_design_period`). **Re-run R_P00 and the models.**
- **The data are structured exactly as in Python.** `lib/reward_prep.R` is a step-by-step port of the Python preparation (formats,
  file names, column names, "1 km" rings, the zero rule, negatives, pixel ids, the shapefile overlay, the near-duplicate merge, the
  duplicate rule, the annual covariate fill, the pooled sub-watershed × period effect). Proof: the Python project's
  `validate_r_parity.py` — the same design, panel, samples, season modes, overlap option and M01 to 1e-8 (CLEAN, 14 checks).
- Your options: `OVERLAP_ROWS <- "drop" | "keep"`, `POOLED_FE <- "site_period" | "period"`. An unbalanced panel is kept as it is: a
  missing pixel-period leaves only the estimation that needs it (`load_panel_R` says how many rows leave THIS estimation).
- Packages first (see A.3): `lib/reward_packages.R` — one install chain for `00_SETUP.R`, run time and the Python bridge;
  `confirm_packages()` in every notebook; `results/PACKAGE_STATUS_R.csv`.
- Fixed with Python: a common year shock no longer ends the post window ("export break"); the pixel-history linkage counts pixels
  present; the design keeps your windows when the data give none (R stopped in the outcome screen before). Data-volume limits × 10
  (`N_MAX_UNITS` 2,000,000, `N_MAX_PIXELS_MIXED` 400,000, `N_MAX_ML` 4,000,000, spatial 3,000,000).

## v20.57
- **Every design option is set in the MODEL notebook and applied when it runs** (B.3) — as the Python pipeline does. `R_P00` builds the
  panel once and never has to be re-run for a design choice; your v20.56 panel works as it is. In v20.56 `DESIGN_MODE = "recommended"`
  replaced your `CONTROL_RINGS <- 1:3` / `PRE_YEARS <- 4` with the data's choice (the `1 2 3 4 5` you saw); now what you set is what
  runs, and only `"data"` asks the data.
- **Your fund workbook is the treatment timing and the dose** (`TREATMENT_TIMING <- "fund"`, the default): each sub-watershed's first
  treated SEASON from its release timing (back-cast before the file's first month at its own rate; the season after the start), the
  dose = the amount released by the end of the previous season / the treatment area. Staggered: Zaid 2024 (Murlapura, Jantapur,
  Kodihalli) to Zaid 2025 (Chhatrakodihalli, Kyatagondanahalli, Sirur); Artal Rabi 2024. `"registry"` / `"fixed"` remain.
- **Fragments of other sub-watersheds are dropped** (`FRAGMENT_RULE <- "drop"`): rows inside another sub-watershed's polygon or outside
  every polygon with another id — core and rings alike — and minor sub-watersheds of the panel.
- **The 98 % rule:** no fixed sample size is left (`N_MAX_* <- NULL`): the CiC bootstrap, lme4, quantile regression, ML and spatial
  weights take every unit that fits below 98 % of the RAM (was 95 % and fixed numbers); every core.
- Fixed: `COVARIATES <- "all"` reached no model; M27 (didimputation) failed on large pixel ids; M01 adds a bad-control check (does a
  covariate move with the treatment?). **Re-run the models** (not R_P00). Details: `docs/CHANGELOG_v20.md`, `docs/VALIDATION_v20.57.md`.

## v20.58
- **Your v20.56 log, explained and fixed:** `CONTROL_RINGS <- 1:3` with rings 1-5 in some results (M17 / M18 / M24 read every ring; now
  every model takes your rings); effects without an SE, p-values printed as `< 1e-300` or exactly 0, a HonestDiD breakdown capped at 5,
  a design-based p beside an estimate it did not belong to -- each fixed: every headline says what it is and carries its own SE and p
  and how each was computed (`HEADLINE_<outcome>.csv`, the same columns as Python). LSWI = NDMI and WSSI = 1 - ESI in your exports:
  said at every run.
- **Only the current sub-watershed's own rows in any model:** every row carries a location code (another sub-watershed's data, outside
  every polygon, an overlapping / repeated / near-duplicate pixel or a control row of a pixel treated elsewhere, a ring that differs
  between a pixel's rows); `FRAGMENT_RULE` / `OVERLAP_ROWS <- "drop"` leave them out of every group -- treated and control, pre and
  post (`"keep"` is your option). Every model confirms its own sample (`SAMPLE_INTEGRITY_<outcome>.csv`); tests scenario F proves it.
- **R structured as Python, model by model** -- the same estimator and the same numbers on the same exports (the Python bundle's
  `validate_model_parity.py`), e.g. M11 synthdid per cohort x season, M22 Goodman-Bacon's exact weights, M34 HonestDiD on M02's event
  study, M36-M38 fect / gsynth per cohort x season (the cross-validation now SEEDED: the chosen number of factors no longer changes
  between runs), the ML models on one long difference per pixel x season series with the package's own SE.
- **Fixed:** R's location rule stopped ("table is type 'integer'") whenever near-duplicate pixels were present; M09 crashed with several
  cohorts; fect's series order depended on the locale; DoubleML's forests now those of the Python primary.
- **A repeated row is dropped WHOLE** (the poison test with cloud gaps found it): when two exports hold the same pixel, year and season,
  the newer row is kept AS IT IS -- until v20.57 its gaps were filled from the dropped (older) row, so values of dropped rows reached
  every model. `DEDUP_FILL_FROM_DUPLICATES <- FALSE` (lib/reward_prep.R; `TRUE` = the old fill, for exports split by variable); a newer
  export's EMPTY row still claims its pixel-year-season (rows without an outcome leave after the de-duplication).
- **The same numbers on every machine:** M04 qte's bootstrap sequential with integer series ids (its draws depended on the number of
  cores on Linux / macOS), M11 synthdid's and M25 ritest's series in a fixed order; the R bridge no longer leaves a copy of each model's
  input in the temp folder.
- **One Python project and one R project (your instruction):** RWD_Artal (Python) and this project (R); the RWD_Artal1 copy is gone.
  The four-model bundle (RWD_4Models) is discontinued in v20.59 at your request: M01, M02, M16 and M34 are part of this pipeline.
- **Beyond 98 % of the RAM -- OUT OF CORE, never sampled (your instruction: Dask and Spark as the fall-backs):** M01, M02, M16 and M34
  (`run_model_R`) and R_P00 (`run_prep`) no longer stop when the data do not fit. They run on **pixel partitions** (every row of a pixel
  together) with the SAME R code as in memory; the two-way fixed effects are solved EXACTLY from the partitions' cross-products (the unit
  effects inside each partition, the period effects jointly; the CR1 sandwich from per-cluster scores; fixest's own small-sample rule);
  R_P00 builds the panel block by block (year x season). The partition tasks run on **Dask**, then **Apache Spark** (through
  `lib/reward_ooc_engine.py`: set `PYTHON_EXE` in `lib/reward_paths.R` to a Python with `dask[distributed]` / `pyspark`), then **R itself**
  (always) -- `OUT_OF_CORE` in `lib/reward_paths.R` sets the order; `00_SETUP.R` shows which this machine has. Below 98 % nothing changes.
  `tests/run_all_tests.R` scenario H proves it: in memory == out of core on every engine (to fixest's convergence, 1e-8), every engine the
  same numbers, R_P00 block by block == in memory row for row.
- **Double precision** and **no cap**. **Re-run R_P00 first** (it rebuilds the panel: repeated rows are now dropped whole), **then the
  models**. Details: `docs/CHANGELOG_v20.md`, `docs/VALIDATION_v20.58.md`.
