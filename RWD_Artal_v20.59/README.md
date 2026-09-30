# RWD_Artal — the REWARD DiD pipeline (Python) for the Artal data — v20.59

> **v20.59 — what changed for you** (details: `docs/CHANGELOG_v20.59.md`; what ran here: `docs/VALIDATION_v20.59.md`)
> * **The panel carries the DiD design columns** — `treat` (buffer 0), `control` (rings 1–5), `post` = the exports' `Treat` flag
>   (1 = post, 0 = pre), `pre` = 1 − post, `did` = treat × post — from P00 / R_P00 (`PERIOD_RULE`: `"treat"` the exports' column,
>   `"year"` the rule `Year >= TREATMENT_YEAR`, `"both"` = the two must agree, a disagreeing row leaves), with
>   `input_design_audit(_R).csv` — every input file confirmed: `Treat` 1 = post / 0 = pre, `buff_km` 0 = treatment / 1–5 = control —
>   The panel KEEPS every fill value and gap-filled row (P00 / R_P00 say so with the counts); `OUTCOME_SCREEN` (drop | keep | off) and
>   `EXCLUDE_GAPFILLED` decide what a MODEL estimates on — set as defaults in P00_Settings / R_P00 and, for each model, in its own first cell.
>   Keeping a fill year-season dilutes the DiD (the treated-control gap in it is 0); the screen's warning says so under keep.
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
D:\LKT\RWD_Artal\
├── RWD_Artal_v20.59\        ← this project (unzip here); a newer version sits beside it
└── data\                    ← your exports (was D:\LKT\TST_Artal) -- MIGRATE_DATA.bat moves them
    └── output\              ← everything the pipeline writes (panel, results, logs)
```
1. Unzip into `D:\LKT\RWD_Artal\`. Double-click `MIGRATE_DATA.bat` once (moves `D:\LKT\TST_Artal` to `D:\LKT\RWD_Artal\data`;
   until then the pipeline uses the old folder and says so).
2. Close older bundles' Jupyter tabs, restart every kernel. Double-click `python\START_JUPYTER.bat`.
3. `python\DIDRDP_ALLRunDID_v20\01_Panel_Preparation\P00_RUN_ALL_Panel_Preparation.ipynb` → Run All — builds the panel ONCE (v20.57: the design is
   not set there). Its P12 cell installs what is missing, confirms every Python and R package and verifies each pre-built package on a
   known answer; the A40 self-tests on first use; STEP 4 reads your fund workbook (`FUND_TIMING_AND_DOSE.md`).
4. Any model notebook (`02_…` – `05_…`), one at a time: **set the design of the run in its CELL 1** (`TREATMENT_TIMING` = `"fund"` by
   default, `TREATMENT_YEAR`, `CONTROL_ZONES`, `PRE_YEARS`, `POST_YEARS`, `SEASONS`, `FRAGMENT_RULE`, `OVERLAP_ROWS`, `POOLED_FE`,
   `DOSE_VARIABLE`, …) → Run All. What you set is used exactly as set (`"data"` = the data decide); DESIGN IN EFFECT is printed and
   saved as `DESIGN_IN_EFFECT.csv` beside the results. Change a setting and re-run that model only. `06_Validation\V01_Results_Audit.ipynb` → the audit.

**Implementation years:** `python\DIDRDP_ALLRunDID_v20\data\sites\sites.csv` (the project's own `data` folder — shapefile, sites —
not your exports folder).

**Contents:** `python\DIDRDP_ALLRunDID_v20` (engine + notebooks), `python\REWARD_ground_inputs` (BM + survey inputs),
`python\exporter_v111` (the Earth Engine exporter), `R\lib` (the R routes the Python pipeline calls — the full R pipeline is the
project RWDR), `docs\` (changelog, validation, request map).

**One Python project and one R project (v20.58, your instruction):** this project (RWD_Artal) for Python and RWDR for R — the RWD_Artal1
copy is dropped from every code, path and check. The four-model bundle (RWD_4Models) is discontinued in v20.59 at your request:
M01, M02, M16 and M34 are part of this pipeline. Each run uses the whole machine (v20.52: no split, no cap).

**Checks you can run:** `selfcheck.py`, `validate_preprocessing.py`, `validate_inference.py`, `validate_all_models.py`,
`06_Validation\V00_RUN_ALL_VALIDATIONS.py`, `06_Validation\V00d_GPU_PATH_CHECK.py` (on the A40), and (v20.54)
`validate_requests.py` — every rule you set, checked on the code (PASS / DECIDE / NOT HERE / FAIL); (v20.55) `validate_r_parity.py` — R == Python;
(v20.57) `validate_design_options.py` — every design option at the model stage, R == Python, the panel never rebuilt; `validate_known_answers.py`
— every model against a known effect; (v20.58) `validate_location_poison.py` — every row the design must leave out is poisoned and every number every
model writes must stay identical; `validate_model_parity.py` (and `--engine`) — every model's headline in R and in Python on the same exports.

**v20.54 (regression audit):** every file, function and setting of v20.47–v20.53 is still here; the defects the audit found are
fixed (`docs\REGRESSION_AUDIT_v20.54.md`). Most important: the pre-built package routes re-used an old copy of the panel after
P00 rebuilt it, and in per-site runs every site after the first used the first site's rows. **Re-run the models whose result
came from a package** (the `…_PACKAGE_…csv` files). `MEMORY_SHARE` in `_paths.py` works again (1.0 = no cap, the default).

**v20.55 (seasons + years; R == Python; packages first; your options):**
- `SEASONS = "all"` (the default; since v20.57 set in each model's CELL 1) estimates on the annual composite **and** the Kharif / Rabi / Zaid rows — year AND
  season variation, pixel × season and year × season fixed effects — and the recommended design **no longer replaces it with
  "yearly"** when a season is missing in some year (that override is why every model until v20.54 ran on the annual composite
  alone). Options: `"seasonal"`, `"yearly"`, `"Rabi"`, `"Kharif+Rabi"`, `"auto"`. Every result also carries the year × season
  design-based SE (`se_design_period`, `p_design_period`).
- `OVERLAP_ROWS = "drop" | "keep"` (control rows of pixels TREATED in another sub-watershed), `POOLED_FE = "site_period" | "period"`.
- An unbalanced panel is kept as it is: a missing pixel-period leaves only the estimation that needs it (`load_panel` says how many).
- Packages first: a missing estimator package is installed when a step needs it (pre-built wheel → source → local wheel folder) and
  verified before it computes; P00's P12 confirms **every** Python and R package (`results\PACKAGE_STATUS.csv`); each notebook prints
  `Python packages: N of N installed`. `AUTO_INSTALL_PACKAGES` / `INSTALL_PACKAGES = False` reports only.
- `validate_r_parity.py` (needs R): proves the R pipeline structures the data exactly as this one (design, panel, samples, season
  modes, overlap option, unbalanced rule, M01) — CLEAN before comparing an R result with a Python one.
- Fixed in both pipelines: the near-duplicate pixel merge was many-to-one on a shifted grid; a common year shock (a drought) ended
  the post window as an "export break"; the pixel-history linkage counted finite outcomes per row group; P00 overrode
  `PIXEL_OVERLAP_MIN`. **Re-run P00 and the models.** Data-volume limits × 10. Details: `docs\CHANGELOG_v20.md`.

**v20.57 (the design in the models; your fund workbook as the timing and the dose; fragments dropped; the 98 % rule; biases fixed):**
- **Every design option is set in the model's CELL 1 and applied when the model runs** (R as well: each R_Mxx notebook). P00 builds
  the panel once; nothing has to be rebuilt for v20.57 or for any design choice — your v20.56 panel works.
- **Your fund workbook is the treatment timing and the dose** (`TREATMENT_TIMING = "fund"`, the default): each sub-watershed's first
  treated SEASON from its release timing — back-cast before the file's first month at its own release rate, the season after the start
  — and the dose = the amount released by the end of the previous season / the treatment area. Staggered from Zaid 2024 (Murlapura,
  Jantapur, Kodihalli) to Zaid 2025 (Chhatrakodihalli, Kyatagondanahalli, Sirur); Artal: Rabi 2024 (every other season from 2025).
  With the true start in Rabi 2024, the v20.56 `TREATMENT_YEAR = 2022` recovered only 0.016 of a +0.05 effect; the fund timing 0.0499.
- **Fragments of other sub-watersheds are dropped** (`FRAGMENT_RULE = "drop"`), core and rings alike; `"keep"` keeps them (tagged).
- **The 98 % rule:** RAM and GPU memory usable to 98 % of the TOTAL, every core, no fixed sample size (ML, spatial weights, k-NN).
- **Biases found by `validate_known_answers.py` and fixed:** M03, M04, M05, M09, M11, M15, M21, M24, M35, M36–M38, M45, M06's dose;
  M01 adds a bad-control check. **Re-run the models** (every result changes with the timing). Details: `docs\CHANGELOG_v20.md`,
  `docs\VALIDATION_v20.57.md`.

**v20.58 (only the current sub-watershed's rows in every model; your rings / years / seasons everywhere; R = Python model by model; every number
with its own SE and p; double precision; the 98 % rule with 5 × batches):**
- **Only the current sub-watershed(s)' own rows in any DiD model.** Every row carries a location code: another sub-watershed's data, outside every
  polygon, an overlapping / repeated / near-duplicate pixel or a control row of a pixel treated in another sub-watershed, a pixel whose ring
  differs between its rows. `FRAGMENT_RULE = "drop"` and `OVERLAP_ROWS = "drop"` (the defaults) leave them out of EVERY group — treated and
  control, pre and post; `"keep"` is your option (tagged). Every model confirms its OWN estimation sample (`SAMPLE_INTEGRITY_<outcome>.csv`:
  every pixel-year-season once, one ring per pixel, no pixel both treated and a control, nothing outside the processed sub-watersheds) and
  prints the rows left out per reason and group (`LOCATION_RULE_<outcome>.csv`). Proof: `validate_location_poison.py`.
- **Your rings, years and seasons in every model** (`CONTROL_ZONES = 1-3` is rings 1–3 in M17 / M18 / M24 too — they used every ring until
  v20.57).
- **Every headline says what it is and carries its own SE and p** (`HEADLINE_<outcome>.csv`, the same columns in R), with how each was computed
  (`se_how`, `p_how`); no NA SE, no p of exactly 0, no capped value; a data gap is written with its reason. Outcomes that are the same variable
  in your exports (LSWI = NDMI, WSSI = 1 − ESI) are said at every run.
- **R = Python, model by model** (`validate_model_parity.py`), and Python's own implementations (used when no verified package or R route can
  run) compute what R's package computes — ported from the package sources (M03, M04, M09, M11, M14, M19, M22, M27–M31, M33, M35, M36–M38
  fect / gsynth, the ML models on R's long difference).
- **Repeated rows dropped whole (P00 and R_P00).** When two exports hold the same pixel, year and season, the newer row is kept AS IT IS:
  until v20.57 its gaps were filled with the repeated (older) row's values, and a newer row that a cloud left empty was dropped before
  the duplicates were compared, so the older repeated row took its place (the poison test with cloud gaps: M01 0.087 for the true 0.050).
  `P.DEDUP_FILL_FROM_DUPLICATES = True` (P00_Settings) is the option for exports split by variable. **P00 rebuilds the panel by itself.**
- **Beyond 98 % of the RAM — Dask, then Apache Spark, then the built-in batches (your instruction).** M01, M02, M16, M34 and P00 do not
  stop and are never sampled: they go OUT OF CORE on pixel partitions (every row of a pixel together, the same code as in memory, the two-way
  fixed effects solved exactly from the partitions' cross-products). `OUT_OF_CORE` in `_paths.py` sets the order; P12 lists the engines this
  machine has (`dask[distributed]`; `pyspark` + Java 17+; the batches always). Proof: `validate_out_of_core.py` (every number == in memory, on
  every engine). The other models keep their batch fall-backs (every unit used once). The R pipeline has the same layer (RWDR).
- **Every calculation in double precision**; **no cap**: all rows in RAM / GPU up to 98 % of the total, the batch fall-back only beyond it
  (5 × larger). **Re-run P00, then the models** (results change). Details: `docs\CHANGELOG_v20.md`, `docs\VALIDATION_v20.58.md`.
