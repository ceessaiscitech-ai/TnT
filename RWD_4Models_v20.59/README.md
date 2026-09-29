# RWD_4Models v20.59 — panel preparation + M01, M02, M16, M34 (Python and R)

> **v20.59 — what changed for you** (details: `docs/CHANGELOG_v20.59.md`; what ran here: `docs/VALIDATION_v20.59.md`)
> * **The panel carries the DiD design columns** — `treat` (buffer 0), `control` (rings 1–5), `post` = the exports' `Treat` flag
>   (1 = post, 0 = pre), `pre` = 1 − post, `did` = treat × post — from P00 / R_P00 (`POST_FROM_EXPORT_TREAT`), with
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


One pipeline for four models, in both languages:

| model | what it estimates | Python notebook | R notebook |
|---|---|---|---|
| **M01** | canonical 2x2 / static TWFE DiD (the headline effect) | `02_Core_DiD_Models/M01_Canonical_2x2_Static_TWFE.ipynb` | `R_M01` |
| **M02** | event study (dynamic TWFE): the effect year by year, and its post-period mean | `02_Core_DiD_Models/M02_Event_Study_dynamic_TWFE.ipynb` | `R_M02` |
| **M16** | formal joint pre-trends test (are the pre-period effects jointly zero?) | `02_Core_DiD_Models/M16_Formal_Joint_Pre_Trends_F_test.ipynb` | `R_M16` |
| **M34** | Honest DiD sensitivity (Rambachan–Roth): how large a violation of parallel trends the post-period effect survives (breakdown M̄) | `04_Advanced_Staggered_Robustness/M34_Honest_DiD_parallel_trends_sensitivity.ipynb` | `R_M34` |

It is filtered from the full pipeline of the same version (RWD_Artal v20.58 + RWDR v20.58). **The engines are the full pipeline's files,
byte for byte** (`python/DIDRDP_4Models_v20/_common.py`, `_prep_common.py`, … and `R/lib/*.R`) — the same code that passed every gate there.
What makes this project *four-model* is its configuration and its notebooks:

* `python/DIDRDP_4Models_v20/_paths.py`: `PIPELINE_MODELS = ("M01", "M02", "M16", "M34")`, `OUTPUT_SUBDIR = "output_4Models"`
* `R/lib/reward_paths.R` and `R/lib/reward_packages.R`: `PIPELINE_MODELS <- c("M01", "M02", "M16", "M34")`, `OUTPUT_SUBDIR <- "output_4Models"`

With it, **the panel preparation prepares the panel for these four models only**: the panel leaves out every column only other models read
(`District`, the dose columns, `area_hectare`, `first_treat_agri_year` / `first_treat_season`, `LandUse`, `LandUseDW`); P00 has no ground
linkage, no benchmark surrogates, no dose table, no preview workbook, no effect-size diagnostics and no SWS audit; R_P00 computes no
benchmark-site means; the package installs, the pre-built route checks and the readiness report cover these four models only
(Python: pyfixest; R: fixest, HonestDiD, plus the pipeline's own packages); R's `MODEL_FUN` holds these four only.

## Where it reads and writes (your paths are unchanged)

| | reads | writes |
|---|---|---|
| Python | `D:\LKT\RWD_Artal\data` (`INPUT_DIR` in `_paths.py`) | `D:\LKT\RWD_Artal\data\output_4Models` |
| R | `D:/LKT/RWDR/data` (`DEFAULT_ROOT` in `R/lib/reward_paths.R`) | `D:/LKT/RWDR/data/output_4Models` |
| both | crosswalk `D:\LKT\RWD_Sub_watershed_final_list.xlsx`, fund workbook `D:\LKT\Districtwise_Month_wise_Progress_with_DoseIntensity_and_SWS.xlsx` | — |

The full pipeline's own folders (`…\data\output`) are never touched: the two projects can run side by side on the same exports.

## Run it

**Python** — `python/START_JUPYTER.bat`, then:
1. `01_Panel_Preparation/P00_RUN_ALL_Panel_Preparation.ipynb` — top to bottom, once (settings in its first cell `P00_Settings`).
2. `02_Core_DiD_Models/M01…`, `M02…`, `M16…`, then `04_Advanced_Staggered_Robustness/M34…` — each with the design of its run in its CELL 1 (timing from your fund workbook by
   default, control rings, years, seasons, covariates, `FRAGMENT_RULE` / `OVERLAP_ROWS` = `"drop"`); CELL 9 repeats it for every outcome.
3. `08_Multisite_Runs/MS01_Multisite_Runs.ipynb` (per-site + pooled runs of M01), `06_Validation/V01_Results_Audit.ipynb` (every result audited).

**R** — open `R/RWD_4Models.Rproj` in RStudio; `00_SETUP.R` once (installs this project's packages only); then `rstudio/R_P00_Prepare_Panel.Rmd`,
`R_M01` / `R_M02` / `R_M16` / `R_M34` (or `R_RUN_ALL_MODELS`), `R_V01_Results_Audit`. The same notebooks for Jupyter are in `R/jupyter/`.

## Your rules, in force in both languages

* **Only the current sub-watershed's own rows** reach the models: every row is located in the 20-sub-watershed shapefile; rows of another
  sub-watershed (from any group — treated or control, pre or post), rows outside every polygon, overlapping / repeated / near-duplicate pixels
  and pixels whose ring the exports disagree on are dropped (`FRAGMENT_RULE` / `OVERLAP_ROWS` = `"drop"`; another choice only when you set it).
  **SAMPLE INTEGRITY** confirms it at every model run and stops the model if anything leaks.
* **A repeated row is dropped whole**: the newer export's row is kept as it is (its gaps stay gaps); none of the dropped row's values enters
  the panel (`P.DEDUP_FILL_FROM_DUPLICATES = False` in `P00_Settings`; R: `DEDUP_FILL_FROM_DUPLICATES` in `lib/reward_prep.R`).
* **Seasons and years together** (annual composite + Kharif / Rabi / Zaid) by default; the fund workbook as each sub-watershed's timing.
* **No cap**: RAM / GPU memory to 98 % of the total, every core; every row in memory (and on the GPU) at once, one regression.
* **Beyond 98 % of the RAM — out of core, never sampled**: the four models and the panel preparation (P00 / R_P00) do not stop — they run
  on **pixel partitions** (every row of a pixel together) with the same code, and the two-way fixed-effects regressions are solved EXACTLY
  from the partitions' cross-products. The engines, in your order (`OUT_OF_CORE` in `_paths.py` / `R/lib/reward_paths.R`): **Dask**
  (the PyData stack, no Java), then **Apache Spark** (pyspark; Java 17+), then the built-in batches (always available). An engine that is
  not installed is named with the reason. `validate_out_of_core.py` (Python) and `tests/run_all_tests.R` scenario H (R) prove the numbers
  equal the in-memory ones on every engine.
* **No placeholder, no silent pass**: a model without a result says why; every result carries its SE (and the design-based SE).

## Validate

* `python selfcheck_4models.py` (in `python/DIDRDP_4Models_v20`) — the bundle, its configuration and scope, your rules on small known answers,
  the R side, and the full pipeline's engine checks.
* `python validate_4models.py` — every gate on this bundle (known answers, the poison test, R vs Python parity, design options, preparation,
  notebooks, R tests); one table at the end. Results of the release run: `docs/VALIDATION_4Models_v20.58.md`.
* The version's changes (shared with the full pipeline): `docs/CHANGELOG_v20.58.md`; the full pipeline's gates (all 45 models, R and
  Python) on the same engines: `docs/VALIDATION_v20.58.md`.

## What is not here (it is in the full pipeline RWD_Artal / RWDR)

The other 41 models (M03–M15, M17–M33, M35–M45), the ground-data steps (P08 / P08b, M07, V06), the dose models, the ML / spatial package layer,
the model guides, `MIGRATE_DATA.bat` (the data were moved by the full projects). Details of the filtering: `docs/CHANGELOG_4Models_v20.58.md`.
