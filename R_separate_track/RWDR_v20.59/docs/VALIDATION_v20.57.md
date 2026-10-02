# Validation of v20.57 — every gate, run on the delivered bundles

Build machine: Linux, 2 cores, 7.5 GB RAM, no GPU. Python 3.11 (numpy 2.3.5, pandas 2.3.3, pyarrow 25.0.1, pyfixest 0.60,
diff-diff 3.12, econml 0.17, esda 2.9, torch 2.14 CPU); R 4.6.1 with all 40 packages; JupyterLab with the R kernel (IRkernel).
Inputs: synthetic exports inside your real shapefile polygons, your fund workbook
(`Districtwise_Month_wise_Progress_with_DoseIntensity_and_SWS.xlsx`) and your crosswalk (`RWD_Sub_watershed_final_list.xlsx`).
Not verifiable here: your A40 (`06_Validation\V00d_GPU_PATH_CHECK.py` runs on it), Windows paths, your own exports.

## 1. The gates

| Gate | Project | Result |
|---|---|---|
| `selfcheck.py` | RWD_Artal / RWD_Artal1 | CLEAN: 160 checks (RWD_Artal, with the model gate's report present) / 159 (RWD_Artal1) |
| `validate_requests.py` (every rule you set) | RWD_Artal / RWD_Artal1 | 33 PASS, 2 DECIDE (your decisions, unchanged), 1 NOT HERE (the A40), 0 FAIL — both projects |
| `validate_design_options.py` (every design option at the model stage, R == Python) | RWD_Artal + R | CLEAN: 1,545 checks — 27 option settings × 4 panels (one and two sub-watersheds, each also without the v20.57 `fragment` column, as a v20.56 panel): the same rows, treat / post / did / cohort / event time / dose, unit / period / cluster partitions in R and Python; each option does what it says; the panel file byte-identical afterwards |
| `validate_known_answers.py` (every model against a known effect, +0.05) | RWD_Artal | CLEAN: 82 PASS, 6 without an answer on such data (M07 ground data, M08 an instrument, M13 switchers; both panels), 2 right data gaps (M19 / M20 need ≥ 2 sub-watersheds; one-sub-watershed panel) |
| Package verification (P00 P12: every pre-built route on a known answer) | RWD_Artal + R | Python: 4 function-layer routes (pyfixest TWFE / event study / wild bootstrap, diff-diff CS) and 14 model routes verified; R: 34 of 34 routes verified (M27's didimputation for the first time) |
| `validate_r_parity.py` (R structures the data as Python) | RWD_Artal + R | CLEAN, 14 checks (design, panel, samples, season modes, overlap option, M01 0.05109550 vs 0.05109549) |
| `validate_preprocessing.py` | RWD_Artal | CLEAN |
| `validate_inference.py` | RWD_Artal | CLEAN |
| `validate_all_models.py` (every model honours the scenario, no placeholder value) | RWD_Artal | 45 of 45 run under two scenarios: 43 honour the scenario, 2 documented data gaps (M07 needs ground data, M08 an instrument); no placeholder value, no all-NaN result |
| `06_Validation\V00_RUN_ALL_VALIDATIONS.py` | RWD_Artal | 29 of 29 PASSED (2 skipped: inputs that exist only on another machine / session) |
| `validate_prep_notebooks.py` (P00 and MS01 end to end, one and two sub-watersheds) | RWD_Artal | CLEAN: P00 (22 cells), MS01 (4 cells), P00 on two sub-watersheds (pooled design, overlay audit, assumed-year warning) |
| `validate_notebooks_cold.py` (every notebook finds the engine on its own) | RWD_Artal | CLEAN |
| `tests/run_all_tests.R` (scenarios A–E, 45 models on known answers, 49 notebooks knitted and run in Jupyter) | RWDR | RESULT: PASS — 220 PASS, 6 DATA GAP, 0 FAIL: scenarios A–E (E: 17 checks of every design option on one panel built once, the panel's md5 unchanged), 45 models on known answers, 49 notebooks knitted as RStudio does and 49 run in Jupyter through IRkernel; the gaps are the right answers (A: M06 no fund workbook in that scenario, M07 ground data, M08 an instrument, M20 ≥ 2 sub-watersheds, M45 pooled donors; B: M08) |
| `tests/selftest.R` | RWDR | PASS (estimate 0.0504, truth 0.0500) |
| A panel built by the **v20.56** P00, used by the v20.57 models (no rebuild) | RWD_Artal | M01, M04, M05: results and `DESIGN_IN_EFFECT.csv` (fragment rule from the export ids; fund timing → registry years without a workbook, tagged `_fundMissing`); M06: the right data gap without a dose |

## 2. Your R settings, run through the v20.57 model stage

Your v20.56 `R_P00` settings (`DESIGN_MODE <- "recommended"`, `TREATMENT_YEAR <- 2022`, `CONTROL_RINGS <- 1:3`, `PRE_YEARS <- 4`,
`POST_YEARS <- NA`, `SEASONS <- "seasonal"`, `OVERLAP_ROWS <- "drop"`, `POOLED_FE <- "site_period"`), set in a model notebook's settings
chunk, on a two-sub-watershed panel (Artal + Haligeri) with your fund workbook:

```
######## 1. TREATMENT_TIMING <- "fixed" (as in v20.56: 2022 for every sub-watershed)
USED -> control rings 1,2,3 | years 2018-2025 | seasons 1,2,3 | treated from 2022

######## 2. TREATMENT_TIMING <- 'fund' (the v20.57 default: your fund workbook)
[INFO]    DESIGN IN EFFECT (v20.57: every option is applied here, at the model stage -- the panel is not rebuilt):
  DESIGN_MODE                 your setting: recommended                         USED: recommended                                       <- your setting
  TREATMENT_TIMING            your setting: fund                                USED: fund: first treated season per sub-watershed      <- the fund workbook Districtwise_Month_wise_Progress_with_DoseIntensity_and_SWS.xlsx
  TREATMENT_YEAR              your setting: 2022                                USED: 2024                                              <- the earliest first treated year of t
    start of sub-watershed 1  your setting: (from TREATMENT_TIMING = fund)      USED: Rabi 2024                                         <- fund file: start 2024-07 (backcast; 
    start of sub-watershed 7  your setting: (from TREATMENT_TIMING = fund)      USED: Kharif 2024                                       <- fund file: start 2024-04 (backcast; 
  CONTROL_RINGS               your setting: 1,2,3                               USED: 1,2,3                                             <- your setting
  PRE_YEARS                   your setting: 4                                   USED: from 2020                                         <- your setting
  POST_YEARS                  your setting: all                                 USED: every year from the start                         <- your setting
  SEASONS                     your setting: seasonal                            USED: seasonal                                          <- your setting
  EXCLUDE_TRANSITION_YEAR     your setting: FALSE                               USED: FALSE                                             <- your setting
  UNIT_FE                     your setting: pixel_season                        USED: pixel_season                                      <- your setting
  COHORT_OFFSET               your setting: 0                                   USED: 0                                                 <- your setting
  OVERLAP_ROWS                your setting: drop                                USED: drop                                              <- your setting
  FRAGMENT_RULE               your setting: drop                                USED: drop                                              <- your setting (column: minor sub-wate
  POOLED_FE                   your setting: site_period                         USED: site_period                                       <- your setting
  DOSE_VARIABLE               your setting: dose_intensity_per_ha               USED: dose_intensity_per_ha                             <- your setting (fund file; controls an
  FUND_START_RULE             your setting: backcast                            USED: backcast                                          <- your setting
  EXCLUDE_GAPFILLED           your setting: TRUE                                USED: TRUE                                              <- your setting
  COVARIATES                  your setting: Rain,Tmax,Tmean,Tmin                USED: Rain,Tmax,Tmean,Tmin                              <- your setting
  SUB-WATERSHEDS              your setting: (from FRAGMENT_RULE = drop)         USED: 1,7                                               <- the panel after the fragment rule
USED -> control rings 1,2,3 | years 2020-2025 | seasons 1,2,3 | treated cohorts 2024,2025 | dose per ha (treated, post): 0.0116 - 0.155
```

In v20.56 the same settings gave `control_rings 1 2 3 4 5` and the data's pre / post windows: the recommended mode replaced your
values. Now the value you set is the value used (`"data"` asks the data), in both modes.

## 3. The treatment timing from your fund workbook

| Sub-watershed | Treatment area (ha) | Amount in Oct 2024 (first month of the file) | Release rate / month (first 12 months) | Start (back-cast) | First treated season | Annual cohort | Downward revisions corrected |
|---|---|---|---|---|---|---|---|
| Murlapura | 5,988 | 443.44 (29.5 % of target) | 36.78 | 2023-10 | Zaid 2024 | 2024 | 3 |
| Jantapur | 6,470 | 311.31 (24.5 % of target) | 34.25 | 2024-01 | Zaid 2024 | 2024 | 1 |
| Kodihalli | 4,399 | 231.62 (25.8 % of target) | 25.74 | 2024-02 | Zaid 2024 | 2024 | 3 |
| Hunasehadagi | 6,681 | 378.39 (21.4 % of target) | 48.92 | 2024-03 | Kharif 2024 | 2024 | 1 |
| Haligeri | 6,192 | 371.26 (22.7 % of target) | 53.25 | 2024-04 | Kharif 2024 | 2024 | 1 |
| Jammapur | 4,946 | 107.34 (22.8 % of target) | 16.84 | 2024-04 | Kharif 2024 | 2024 | 3 |
| Nilgund | 6,478 | 388.04 (24.8 % of target) | 63.16 | 2024-04 | Kharif 2024 | 2024 | 0 |
| Pashapur | 6,405 | 398.83 (27.8 % of target) | 59.02 | 2024-04 | Kharif 2024 | 2024 | 4 |
| Doddenahalli | 6,985 | 136.60 (9.5 % of target) | 28.77 | 2024-06 | Rabi 2024 | 2025 | 4 |
| Artal | 4,632 | 71.54 (8.4 % of target) | 23.59 | 2024-07 | Rabi 2024 | 2025 | 2 |
| Honnutagi | 6,166 | 243.38 (15.3 % of target) | 68.67 | 2024-07 | Rabi 2024 | 2025 | 2 |
| Koranahalli | 6,741 | 74.82 (10.3 % of target) | 24.05 | 2024-07 | Rabi 2024 | 2025 | 1 |
| Mallainupura | 5,486 | 108.78 (8.7 % of target) | 31.45 | 2024-07 | Rabi 2024 | 2025 | 2 |
| Chittharagi | 7,157 | 109.43 (7.6 % of target) | 41.25 | 2024-08 | Rabi 2024 | 2025 | 2 |
| Gummlapalli | 5,852 | 32.28 (4.9 % of target) | 15.74 | 2024-08 | Rabi 2024 | 2025 | 9 |
| Maidalakere | 5,253 | 96.41 (10.9 % of target) | 36.04 | 2024-08 | Rabi 2024 | 2025 | 0 |
| Beguru | 8,779 | 46.91 (4.8 % of target) | 32.69 | 2024-09 | Rabi 2024 | 2025 | 0 |
| Chhatrakodihalli | 7,369 | 16.95 (2.6 % of target) | 23.29 | 2024-10 | Zaid 2025 | 2025 | 2 |
| Kyatagondanahalli | 5,453 | 10.02 (0.9 % of target) | 36.21 | 2024-10 | Zaid 2025 | 2025 | 2 |
| Sirur | 6,446 | 1.63 (0.1 % of target) | 57.33 | 2024-10 | Zaid 2025 | 2025 | 1 |

Amounts in the workbook's own unit (its cumulative `Progress`); the start rule `FUND_START_RULE = "backcast"` (default).

Why it matters — a synthetic one-sub-watershed panel whose true effect (+0.05) starts in Rabi 2024 (as Artal's releases imply):

| Timing used by the model | Estimate (truth 0.0500) |
|---|---|
| `TREATMENT_TIMING = "fixed"`, `TREATMENT_YEAR = 2022` (every v20.56 run) | 0.0162 (SE 0.0110) |
| `"fixed"`, 2024 | 0.0335 (SE 0.0125) |
| `"fund"` (first treated season Rabi 2024) | **0.0499** (SE 0.0006) |

## 4. Biases found by the known-answer test and fixed (true effect +0.05)

| Model | v20.56 | v20.57 | Cause |
|---|---|---|---|
| M03 doubly robust | 0.016 | 0.049 / 0.050 | every row as a cross-section; now Sant'Anna & Zhao on one change per series (pixel × season) and cohort |
| M05 / M09 staggered | 0.122 | 0.050 / 0.050 | the unit was the whole sub-watershed, so its rings entered the treated pre-period mean; now the pixel series |
| M11 synthetic DiD, M36–M38 factor models, M45 | −0.002, no result, 0.002 | 0.050, 0.050, 0.050 | donors were the other (treated) sub-watersheds; now the core series against the ring series |
| M45 (staggered) | 0.064 (first v20.57 fix) | 0.050 | the penalty shrank the donors' common trend; now per season, net of the year effect |
| M04 changes-in-changes | 0.061 | 0.054 | one pooled 2 × 2 of every season and year; treated values beyond the control range; now comparable cells and the common support (share outside reported) |
| M35 quantile effects | 0.049 → 0.067 across quantiles | 0.048–0.051 | the same mixture; the headline is now the quantile DiD on comparable cells |
| M15 placebo (staggered) | 0.016–0.025 | ≈ 0 | the pre-period was one calendar cut for all cohorts; now each series' own untreated years |
| M21 (one sub-watershed) | no result | 0.049 | the site column was dropped in the aggregation |
| M24 spillover | pixel clusters; any decay called spillover | the design's clusters; significance required | — |
| M06 dose | the rings carried the core's district dose | fund dose, 0 on the rings | — |
| Every notebook | the per-site years of the saved scenario were ignored (JSON keys) | used | — |
| R | `COVARIATES <- "all"` reached no model; M27 didimputation failed on large ids | fixed; verified | — |
| M23 (Python) | pyfixest's wild bootstrap expands the fixed effects densely (1.3 GB for 20,000 rows × 2,000 units) | used only when it fits below 98 %; else the engine's exact bootstrap | — |

The full table (every model, both panels) is `docs/VALIDATION_KNOWN_ANSWERS_v20.57.csv`; the design-option checks
`docs/DESIGN_OPTIONS_VALIDATION_v20.57.csv` / `.md`.

## 5. Nothing missing

Every file, Python function / constant and R function / constant of v20.56 is in v20.57 (compared file by file, all three
projects; nothing removed). The three P00 timing switches `USE_SITE_YEARS`, `YEARS_FROM_REGISTRY`, `SWS_MODE` became the model option
`TREATMENT_TIMING` (`"registry"` = your registry years, `"fixed"` = one year) and the design resolved from the panel after the
fragment rule (= `SWS_MODE = "auto"`); `set_scenario(use_site_years=...)` still works. Your paths (`_paths.py`, `reward_paths.R`) are
unchanged.
