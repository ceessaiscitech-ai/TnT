# v20.59 — the panel carries the DiD design columns from the exports' Treat flag (1 = post, 0 = pre); the outcome screen explains itself and can be kept; PRE_YEARS / POST_YEARS take calendar years; every model says where its design differs from the panel's

Two bundles: `RWD_Artal_v20.59` (the full Python pipeline, all 45 models, with the R library beside it) and `RWDR_v20.59` (the full R
pipeline). The engines are the same files in both (byte for byte); what differs is configuration and notebooks, as in v20.58. The
four-model bundle (`RWD_4Models`, P00 + M01, M02, M16, M34) is discontinued at your request: its models are part of both pipelines.
Nothing of v20.58 is removed from the two: every function, file, option and default is still there and still means what it meant.
Your paths are unchanged.

## Your second request — the period from the `Treat` column, the groups from `buff_km`, confirmed on every input file

- **The input files' `Treat` column is the period flag: 1 = post-treatment, 0 = pre-period.** It is never the treatment AREA: that is the
  `buff_km` / `distance` column — 0 = the treatment area, 1–5 = the control rings. Both engines now say this in one setting and confirm it
  on every file before the panel is built.
- **`PERIOD_RULE`** (`P.PERIOD_RULE` in P00_Settings; `PERIOD_RULE` in `lib/reward_paths.R`) — how the DID-ready panel's `post` / `pre`
  are set: `"treat"` (default) = the exports' `Treat` column (a row without a usable flag takes the Year rule, counted and said);
  `"year"` = the rule `Year >= TREATMENT_YEAR` for every row (v20.58); `"both"` = the `Treat` column AND the Year rule, which must
  AGREE — a row where they disagree (or whose flag is not 0 / 1) leaves the panel in PASS A / `read_export`, before the duplicates are
  resolved (another export's consistent row of the same pixel-period can then stand in), counted per file and in the panel's settings
  (`period_rows_dropped`). `POST_FROM_EXPORT_TREAT` is kept as the older name (`False` = `"year"`). An unknown value is refused with the
  three choices named. A panel built under another rule is rebuilt (`panel_build_settings.json` / `panel_build_settings_R.csv` record
  `period_rule`).
- **The input audit — `input_design_audit.csv` (P00) / `input_design_audit_R.csv` (R_P00)**, one row per input file: whether the file
  carries `Treat`, rows with 1 (post) / 0 (pre) / another value, the years, rows the Year rule calls post, rows where the flag and the rule
  disagree, rows with `buff_km` 0 (treatment) / 1–5 (control) / outside 0–5, the rule in effect and the rows it dropped. Printed once:
  `input files CONFIRMED (N files, R rows): Treat column 1 = post on ... rows, 0 = pre on ...; buff_km 0 = the treatment area on ...
  rows, 1-5 = the control rings on ...; PERIOD_RULE = 'treat': ...`, with a WARNING for files without `Treat`, for flag-vs-year
  disagreements (and what the rule in effect does with them) and for buffer codes outside 0–5. The same in memory and out of core
  (Python's PASS A workers; R's `read_export` -> `run_prep` / `ooc_task_p00_read` -> `run_prep_ooc`).
- **The DID-ready panel** therefore carries, for every row: `treat` (buff_km 0), `control` (rings 1–5), `post` / `pre` under the rule
  in effect, `did` = treat x post — and every model still applies ITS OWN design when it runs and reports `DESIGN vs PANEL`.
- **The Python error you saw** (the same refusal as R's: `'NDVI' is not usable ... Re-export it`) had the same cause and takes the same
  fixes: the outcome screen now writes its evidence (`OUTCOME_SCREEN_<outcome>.csv`, min / max per year-season), `OUTCOME_SCREEN = "keep"`
  runs the model regardless, and P00's `panel_variation_by_block.csv` shows the pixel spread per year-season right after the panel is
  built — `screen_outcome_frame` / `screen_all_outcomes` in `_common.py`, the same texts as `reward_design.R`.

## What your v20.58 R log showed, and what was behind it

Your run (`R_M01`, NDVI, Jantapur, `TREATMENT_TIMING <- "fixed"`, `PRE_YEARS <- 2022`, `EXCLUDE_GAPFILLED <- FALSE`) did not estimate
anything. Three things in it, and what each was:

1. **`PRE_YEARS  your setting: 2022  USED: from 0`.** v20.58 read every number in PRE_YEARS / POST_YEARS as a COUNT of years
   (PRE_YEARS 4 = the four years before the start), so 2022 became `year_min = 2022 - 2022 = 0` — a window "from year 0", applied
   without a word (it happened to keep every year). Python did the same. **Fixed (both engines):** a number below 1900 is a count, a number
   from 1900 on is a CALENDAR YEAR — `PRE_YEARS <- 2015` = the first pre year, `POST_YEARS <- 2025` = the last post year. A calendar year
   that leaves no year on its side of the start (`PRE_YEARS <- 2022` with the start in 2022) is not a window: DESIGN IN EFFECT says
   `PRE_YEARS 2022 is not before the start 2022 -> every year before it`, a warning names the two valid forms, and every year before the
   start is used. Anything else (0, 500, 2500, text) is refused with the same message.
2. **`41 year-season(s) are NOT pixel data and are left out -- 2015 Yearly: constant across pixels (a fill value); ...`, then
   `'NDVI' is not usable: ... 1 valid pre-period year(s) [2015] and 1 post-period year(s) [2025] ... Re-export it.`** The outcome screen
   (v20.45) leaves out a year-season whose value is the SAME for every pixel: that is a fill value, not a measurement, and a DiD on it has
   no cross-sectional variation. On your panel it flagged 41 of the 44 year-seasons of NDVI, EVI and SAVI — and then stopped with
   "Re-export it", showing nothing of what it had measured and offering no way to run. **Fixed (both engines, in memory and out of core):**
   - every decision now comes with its EVIDENCE: `OUTCOME_SCREEN_<outcome>.csv` beside the results — per year-season the rows, the pixels,
     the mean, the SD across pixels, the min and the max, the treated / control rows, the verdict and the rule — and the message names the
     numbers (`2016 Yearly: constant across pixels (a fill value: 1,612,000 rows of 1,612,000 pixels, every value 0.3456)`);
   - a new option in every model's settings, `OUTCOME_SCREEN` — `"drop"` (the default, as before), `"keep"` (the flagged year-seasons are
     reported and KEPT: the model runs on every year-season, its results go to a folder tagged `_screenKept`) or `"off"`; with `"keep"` /
     `"off"` the data-driven design (`PRE_YEARS / POST_YEARS = "data"`) keeps its fill years too;
   - the refusal names the evidence file and the option: `... The evidence -- rows, pixels, mean, SD, min and max per year-season -- is in
     <results>/OUTCOME_SCREEN_NDVI.csv. If those year-seasons ARE pixel data, set OUTCOME_SCREEN <- "keep" ... -- or re-export the variable
     if they are not`;
   - P00 / R_P00 now write `panel_variation_by_block.csv` (per outcome x year x season: finite rows, mean, SD across pixels, min, max,
     `constant_across_pixels`) and say at once which cells hold one value for every pixel — so you see it right after the panel is built,
     before any model runs, and can tell an export problem from a code problem;
   - the design from the data prints the SD across pixels of every year beside its fill years (DESIGN_RECOMMENDATION.md too).
   **What the evidence will tell you on your data.** The screen's test is exact: SD across 1.6 million pixels below 1e-9 means every pixel
   carries the same number. If `OUTCOME_SCREEN_NDVI.csv` shows `min == max` on those 41 cells, the exports hold one value per year-season
   (a fill / projection of the exporter, not a measurement) and no pixel-level DiD can be estimated on them — `"keep"` will run, but its
   SE will be ~0 and flagged. If it shows a spread, the screen was wrong and the file shows why; either way the run no longer stops blind.
3. **The panel had no design columns.** R_P00's panel carried the exports' `Treat` flag but nothing a DiD reads; every model built its
   own `treat / post / did` when it ran, and nothing said whether that matched the exports. **Your request, implemented (both engines):**
   - the panel carries **`treat`** (1 = the treatment area, buff_km 0), **`control`** (1 = a control ring 1–5), **`post`** = the exports'
     `Treat` flag (1 = post, 0 = pre — the exporter's own timing, written for every pixel; a row without a usable flag takes the rule
     `Year >= TREATMENT_YEAR`, counted and said), **`pre`** = 1 − post and **`did`** = treat x post. Python's panel keeps its names
     `treatment` / `did_term` and adds `treat` / `did` beside them, so both panels carry the same five columns.
     `P.POST_FROM_EXPORT_TREAT` (P00_Settings) / `POST_FROM_EXPORT_TREAT` (`lib/reward_prep.R`) = `True`; `False` gives v20.58's rule. The
     setting is recorded with the panel (`panel_build_settings.json` / `panel_build_settings_R.csv`) and P00 rebuilds a panel built under the
     other one. `panel_design_check.csv` / `panel_design_check_R.csv` list the rows per year x season x group x period and how many rows'
     exported flag differs from the rule.
   - **the customisation question — which columns a model estimates on.** Every model still applies ITS OWN design when it runs (the fund
     timing, `TREATMENT_YEAR`, the transition year, the rings, the years, the seasons — your settings) and rebuilds `treat / post / did`
     for it; the panel's columns are the exporter's default, never the input of an estimate. New at every run, in memory and out of core:
     **`DESIGN vs PANEL`** — `the design in effect (fixed: post = Year >= 2022) gives the same post period as the panel's post column (the
     exports' Treat flag) on every one of 70,425,719 rows`, or `... (fund timing ...) differs from the panel's post column on 12,345,678 of
     70,425,719 rows (17.5 %) -- the DESIGN's columns are what this model estimates on (your settings ...); the panel's are the exporter's
     default`. The count is in every result row (`post_rows_differ_from_panel`). A panel built before v20.59 (no `post` column) is said
     once; the models run on their own design as before.

## Your fill-value question — keep or drop, at both levels, in both languages

Your R_P00 run (71,141,565 rows, 68 min) built the panel and said `410 of 731 outcome x year-season cells hold ONE value for every pixel`;
the screen then left 41 of 44 year-seasons out of every model. Two things were missing and are now in place:

- **The panel keeps everything, and says so.** P00 and R_P00 never drop a fill value or a gap-filled row; both now print
  `the panel KEEPS every row and value: N outcome x year-season fill cell(s) and G gap-filled row(s) (GapFilled = 1) are IN the panel -- each
  model decides with OUTCOME_SCREEN ('drop' | 'keep' | 'off') and EXCLUDE_GAPFILLED (True | False) in its own CELL 1`. In memory and out of core.
- **The two options at the panel level in R too.** R_P00 (`R_P00_Prepare_Panel.Rmd` / `.ipynb`) now carries `OUTCOME_SCREEN <- "drop"` and
  `EXCLUDE_GAPFILLED <- TRUE` beside the design defaults, exactly as Python's P00_Settings does; they are the defaults of the design report and
  the screen table of that notebook. Python's P00 now also passes `outcome_screen=OUTCOME_SCREEN` to its own design report (it passed
  `exclude_gapfilled` only). Every model notebook, Python and R, has had both options in its first cell since v20.59; each model overrides
  the panel-level default for itself.
- **What "keep" does to the estimate — said in the log, proved in `validate_did_spec.py`.** A fill year-season holds one value for every
  pixel, so the treated-control difference in it is exactly 0. Kept, it dilutes the gap the DiD compares: a pre gap g over n real pre periods
  becomes g x n / (n + 1), and the estimate moves by g / (n + 1) (per season series). On the audit's synthetic panel (true effect +0.05) the
  estimate under "drop" is 0.05029 and under "keep" 0.04825; the shift equals the predicted dilution. The screen's warning under "keep" now
  says this in both languages. With 41 of 44 year-seasons being fill values in your NDVI / EVI / SAVI exports, "keep" would compute a DiD
  dominated by artificial zero gaps: the estimate on the 3 real year-seasons ("drop") is the honest one, and the real fix is an export that
  carries pixel values in every year-season. Both options remain yours; the run never stops blind either way.

## Your machine (2 x AMD EPYC, 512 GB, NVIDIA A40, Windows Server 2022) — what was idle and why, and what changed

- **Half the cores were idle on Windows.** Windows splits a box with more than 64 logical processors into PROCESSOR GROUPS;
  `os.cpu_count()` and R's `detectCores()` report one group (64), and `concurrent.futures` refuses more than 61 worker processes. Now
  `_hardware.logical_cores_all()` (GetActiveProcessorCount over ALL groups) and R's `all_logical_cores_R()` (the CIM count) give every
  logical processor, and PASS A / PASS B run on `multiprocessing.Pool` (`_hardware.make_pool`), which has no 61-worker limit: one worker
  per logical core of every group. `N_THREADS` in R follows the same count.
- **"RAM ceiling (98 %) reached after 97.6 GB" with 292 GB usable.** PASS B processes every Year x Season block at once and holds up to
  `MEM_BLOCK_COPIES` (3) copies of each, so the in-RAM hand-over needs that multiple of the panel's size; and a block above 256 MB is handed
  to a worker as a FILE in any case (a pickled block that size breaks the Windows process pool). Your blocks are ~2 GB each, so the in-RAM
  path could never have been used for them: PASS A now switches to shard files as soon as a block passes 256 MB, says why, and stops
  holding ~100 GB for nothing. Nothing is slower: PASS B read those blocks from files before as well. The message now explains the rule and
  names `P.MEM_BLOCK_COPIES` (P00_Settings) for a machine where it should be lowered.
- **The GPU during P00.** P00 parses files and builds the panel on the CPU cores; the A40 serves the MODEL stage (fixed-effects demeaning
  with `torch`, k-NN / spatial weights with `cupy`). P00 now prints the GPU line at the start of PASS A: the device and its memory when
  `torch` with CUDA is installed, else the pip command that enables it (`pip install torch --index-url https://download.pytorch.org/whl/cu124`).
- **The working sub-watershed rule, made explicit at both levels.** The sub-watershed of every row is where its latitude / longitude falls in
  the shapefile (the core or a control ring): the file's id only labels (confirmed / corrected / assigned; your run: 3,286,494 confirmed,
  3,287,173 assigned, 102 outside). ONE sub-watershed processed = the one holding the majority of the rows (`SUB_WATERSHEDS = "data"`: every
  sub-watershed with >= 5 % of the largest one's own rows; the rest are fragments, `FRAGMENT_RULE`); SEVERAL = every row in the
  sub-watershed its coordinates put it in. P00_Settings now carries `SUB_WATERSHEDS`, `P.SITE_GEOMETRY_CHECK` and `P.BUFF_FROM_GEOMETRY`
  (the overlay comparison options: verify every row, or trust the file's id; the ring from the polygon on corrected / assigned rows, or on
  every row), R_P00 and `lib/reward_paths.R` carry `SITE_GEOMETRY_CHECK` / `BUFF_FROM_GEOMETRY` for the first time (R always overlaid; now
  the same two switches as Python, in memory and out of core), and both P00s print the rule with the numbers of the run.
- **Every customisation at the panel level in R too.** R_P00 now carries the full design-defaults block Python's P00_Settings has
  (DESIGN_MODE, TREATMENT_TIMING, TREATMENT_YEAR, FUND_START_RULE, DOSE_VARIABLE, CONTROL_RINGS, PRE_YEARS, POST_YEARS, SEASONS,
  EXCLUDE_TRANSITION_YEAR, UNIT_FE, COHORT_OFFSET, POOLED_FE, OVERLAP_ROWS, FRAGMENT_RULE, COVARIATES, SUB_WATERSHEDS, OUTCOME_SCREEN,
  EXCLUDE_GAPFILLED, PERIOD_RULE) -- the defaults of the design report and the screen table; every model notebook keeps its own first cell,
  which wins for that model. `validate_design_options.py` (1,728 checks, R == Python) is the proof that each option does what it says at the
  model stage; the R suite's scenario E checks the panel-level ones.

## Your fourth request — the panel's design as the default, `Treat` used and not kept, one sub-watershed and one ring per pixel

**The panel's design is what every model estimates on by default.** Every model notebook (Python `CELL 1`, R `R_Mxx`) now carries
`DESIGN_SOURCE = "panel"`: the model's `post` / `pre` / `did` ARE the panel's columns (built by P00 / R_P00 from the exports' `Treat`
flag under `PERIOD_RULE`), each series' cohort is the panel's first post year of its sub-watershed, and the event time counts from it.
The design in effect (`TREATMENT_TIMING`, `TREATMENT_YEAR`, `EXCLUDE_TRANSITION_YEAR`, the fund / registry dates) is still computed
and COMPARED with the panel (the `DESIGN vs PANEL` line says on how many rows it would differ) but is not estimated on. Results are
tagged `_panelDesign`. `DESIGN_SOURCE = "model"` is design-based modelling: the design in effect builds the columns, as before. P00 /
R_P00 carry the same default at the panel level; the engine's own default (the validators, the R bridge) stays `"model"` so that every
timing test keeps its meaning. Python `set_scenario(design_source=...)`, `resolve_design` row `DESIGN_SOURCE`; R `design_settings`
(`.one_of`), `design_columns`. Out of core the workers receive it (`SCENARIO_KEYS`).

**`Treat` is used, not kept.** The exports' `Treat` column populates `pre` / `post` (and `did`) under `PERIOD_RULE` and is then dropped
from the final panel in BOTH languages (Python had `Treat` in `DROPPED_FROM_PANEL` already; R_P00's `keep_cols` / the out-of-core
`all_cols` no longer list it). A panel that still carries it is rebuilt.

**Every row belongs to the sub-watershed whose polygon holds its latitude / longitude, and ONE ring.** `PIXEL_ONE_SITE = True` (P00
`P.PIXEL_ONE_SITE`, R `reward_paths.R` / R_P00): the location of every row decides its sub-watershed (core first, then the lower id when
a point lies in the zones of two sub-watersheds) and its ring, whatever id or ring the file carried -- a pure function of the
coordinates, so the same pixel has the same `site_id` / `buff_km` in every year and season and appears once per year-season. A row in
no polygon keeps the file's id, flagged (`site_check` 3), and leaves every estimate (the location rule). Python `tag_sites`
(`site_unified_by_one_site_rule` in `site_tagging_report.csv`), R `overlay_sws` + `ring_from_polygon_codes`. `False` = the v20.58 rule
(a point in the zones of two sub-watersheds kept once per sub-watershed).

**Confirmed on the finished panel, never assumed.** P00 (`confirm_pixel_consistency`) and R_P00 (`panel_pixel_consistency_R`, in
memory and out of core) count, per pixel, the distinct `site_id`, `buff_km` and coordinates and the repeated (pixel, year, season)
rows; the verdict is one line of the log (`pixel consistency CONFIRMED: N pixels ...`) and the offenders, if any, are in
`panel_pixel_consistency.csv` / `panel_pixel_consistency_R.csv`.

## Your fifth request — the control group chosen on the PRE period (per outcome, fixed across the panel); what to change for a credible estimate

`ECONOMETRIC_ADVICE_v20.59.md` (root and both `docs/`) answers the question behind the request — which customisations are legitimate
when the estimate is not significant, and which are not (a rule that picks controls, years or rings because the estimate then becomes
significant selects on the result). The code side:

**`CONTROL_SELECTION`** (CELL 1 of every model notebook and `R_Mxx`; the panel-level default in `P00_Settings` / `R_P00`):
`"rings"` (as before: every ring of `CONTROL_RINGS`) | `"pre_rings"` (per outcome, the `CONTROL_SELECT_K` = 1 or 2 buffers whose
PRE-period series is closest to the treatment area's -- your "perfect buffer") | `"pre_blocks"` (control CLUSTERS -- ~1 km blocks of
pixels -- from any part of the buffers, the closest first, until `CONTROL_SELECT_RATIO` x the treated pixels -- your "cluster
controls"). `CONTROL_SELECT_ON`: `"trend"` (the demeaned pre series' distance -- the parallel-trends distance, recommended) |
`"level"` (nearest to the pre mean) | `"both"`. The decision is a function of the PRE period alone, made once per outcome and applied
to every year and season, so the control pixels are the same across the whole panel (your rule); unselected control rows leave the
sample, treated rows never do. Evidence: `CONTROL_SELECTION_<outcome>.csv` (R: `_R.csv`) beside the results -- every candidate's
pre-period rows, pixels, level gap, trend distance, slope difference, score, rank, selected. Results tagged `_ctrlPre2r` /
`_ctrlPreBlk3x` (`L` / `B` for the level / both rules); the design report carries the row `CONTROL_SELECTION`. A rule named after the
post period, the outcome's mean or the result is refused with the reason. Out of core the parent decides once on the merged
pre-period facts of every partition (`_ooc_models.decide_controls_ooc`, R `ooc_task_presel`) and every worker applies the same set.

**`CLUSTER = "block"`** (both languages): ~1 km spatial blocks of pixels (`CONTROL_BLOCK_DEG`, 0.01 deg) as the clusters of the
cluster-robust SE -- hundreds to thousands of clusters instead of 2 sub-watersheds or 10 years; tag `_clBlock`. The block of a pixel
comes from its id (a pure function of the rounded coordinate since v14), or from the frame's latitude / longitude when the ids are
plain numbers (a synthetic panel); the same rule in R (`block_ids_R`).

Where: Python `_common.select_controls`, `control_selection_aggregates` / `control_selection_decide` / `record_control_selection`,
`block_ids`, `_cluster_key`, `columns_for` (latitude / longitude read when a block rule is set), `_ooc_models._t_presel` /
`decide_controls_ooc`; R `reward_design.R` `control_selection_R`, `block_ids_R`, `control_selection_facts_R` /
`control_selection_decide_R` / `record_control_selection_R`, `select_controls_R` (in `load_panel_R`), `reward_outofcore.R`
`ooc_task_presel`, `ctx$ctrl_sel`; `reward_paths.R` defaults.

## Found by running R here (v20.59, after the first delivery)

- **R_P00 stopped before writing the panel** when an outcome column had no finite value at all (`panel_variation_R`: the empty part
  lacked the `variable` column, so `rbindlist` refused it and `run_prep` ended before `panel_write`). Fixed: every part carries the
  same columns; `rbindlist(fill = TRUE)`. In memory and out of core (`reward_prep_ooc.R` calls the same function).
- `tests/run_all_tests.R`: the scenario-E audit check accepts exports without a `Treat` column (the Year rule, said); a batch model
  without its package fails its own row, not scenario G.
- An independent DiD-specification audit (`docs/VALIDATION_v20.59.md`, section 5) ran on both engines with R installed.
- **Found by the self-check of the fourth request (Python):** the resolved-design cache (`resolve_design`, v20.58) restores its
  snapshot of the whole scenario on a cache hit, and its key held only the design settings -- so CELL 1 re-run in the SAME kernel with
  another `OUTCOME_SCREEN`, `EXCLUDE_GAPFILLED`, `COVARIATES`, `CLUSTER`, `POOLED_FE`, `UNIT_FE`, `COHORT_OFFSET`, `NONNEGATIVE` (or now
  `DESIGN_SOURCE`) kept the OLD value silently (a fresh kernel, and every notebook run from the top, was unaffected). Fixed: every raw
  model-level setting is part of the key (`_design_key`); the self-check toggles them with a resolve in between and confirms the cache
  still hits when nothing changed.

## Where each change lives

| what | Python | R |
|---|---|---|
| calendar years in PRE_YEARS / POST_YEARS; a bound at the start said and set aside | `_common.set_scenario` (`_year_option`), `scenario_years`, `year_window_dropped`, `resolve_design` | `reward_design.R` `design_settings`, `year_bounds_R`, `model_design` |
| the period rule and the input audit | `_prep_common.PERIOD_RULE`, `period_rule`, `input_design_audit`, `audit_and_apply_period_rule` (PASS A, `_pa_worker`), `input_audit_report` (`run_pass_a` -> `input_design_audit.csv`), `run_pass_b` (`panel_build_settings.json`: `period_rule`, `period_rows_dropped`), `final_panel_is_valid` | `reward_paths.R` `PERIOD_RULE`; `reward_prep.R` `period_rule_R`, `input_audit_R`, `input_audit_report_R` (`read_export` -> `run_prep` -> `input_design_audit_R.csv`), `panel_design_columns_R`; `reward_prep_ooc.R` `ooc_task_p00_read` (`audit`), `run_prep_ooc`; `panel_build_settings_R.csv` |
| the panel's design columns from the exports' flag | `_prep_common.build_treatment_columns` (`export_post_flag`, `POST_FROM_EXPORT_TREAT`), `FINAL_PANEL_SCHEMA` (+ `treat`, `did`), `prepare_pass_b_block` (the design check), `run_pass_b`, `final_panel_is_valid` | `reward_prep.R` `panel_design_columns_R` / `panel_design_report_R` (run_prep), `reward_prep_ooc.R` (block by block, merged) |
| DESIGN vs PANEL at the model stage | `_common.build_treatment_columns` -> `design_vs_panel` / `say_design_vs_panel`; `_ooc_models._t_prep` + `prepare_sample` (out of core, summed) | `reward_design.R` `design_columns` -> `design_vs_panel_say_R`, `sample_facts`, `save_result` (`post_rows_differ_from_panel`); `reward_outofcore.R` `ooc_task_sample` / `ooc_load_R` |
| the outcome screen: evidence, rule, refusal | `_common.screen_decide_table`, `screen_report`, `screen_refuse_years`, `screen_outcome_frame`, `screen_all_outcomes` (P09), `screen_rule`, `set_scenario(outcome_screen=)`, `scenario_tag` (`_screenKept`); `_outofcore.screen_decision` / `_screen_stats` (min, max) | `reward_design.R` `screen_rule_R`, `screen_outcome`, `screen_decide`, `screen_refuse`, `design_settings`, `scenario_tag`; `reward_outofcore.R` (`ooc_task_prep` moments + min / max, `ooc_merge_moments`, `ooc_load_R`); `reward_paths.R` `OUTCOME_SCREEN` |
| the pixel-variation report of P00 | `_prep_common.prepare_pass_b_block` (exact moments per block, merged out of core by `_merge_moments`), `run_pass_b` -> `panel_variation_by_block.csv` | `reward_prep.R` `panel_variation_R` / `panel_variation_report_R` (in memory and block by block) |
| the panel's design as the default, `Treat` dropped, one site and ring per pixel | `_common.ACTIVE["design_source"]`, `_design_source_of`, `set_scenario(design_source=)`, `build_treatment_columns` (the override, `_post_design`), `design_vs_panel` / `say_design_vs_panel`, tag `_panelDesign`; `_prep_common.PIXEL_ONE_SITE`, `tag_sites`, `confirm_pixel_consistency` (`run_pass_b`) | `reward_design.R` `design_settings` (`design_source`), `design_columns`, `design_vs_panel_say_R`, `DESIGN_DEFAULTS`; `reward_paths.R` `PIXEL_ONE_SITE`, `DESIGN_SOURCE`; `reward_prep.R` `overlay_sws`, `ring_from_polygon_codes`, `panel_pixel_consistency_R`, `keep_cols` without `Treat`; `reward_prep_ooc.R` (`pix`, `n_rep_in`, `all_cols` without `Treat`) |
| the notebooks | every model's CELL 1: `OUTCOME_SCREEN`, passed to `set_scenario`; PRE_YEARS / POST_YEARS document the calendar-year form; P00_Settings: `P.POST_FROM_EXPORT_TREAT` | every `R_Mxx` (Rmd and Jupyter): `OUTCOME_SCREEN <- "drop"`, the calendar-year form documented |

## Checks

- `selfcheck.py`: `check_v20_59` — the year window (calendar years, counts, the bound at the start, refused values), the panel's
  columns from the flag, `PERIOD_RULE` `"treat"` / `"year"` / `"both"` on a small frame (the disagreeing row leaves under `"both"`; an
  unknown value refused; `POST_FROM_EXPORT_TREAT = False` = `"year"`), the PASS A audit's counts, the model-stage comparison and its
  count, the screen's evidence / rule / refusal text (in memory and out of core), the notebooks' options, the R library's functions.
- `validate_preprocessing.py`: the design case expects the panel to FOLLOW the exports' flag (post = 1 from 2023 where the export says
  so), `input_design_audit.csv` with the file's counts (7 post / 21 pre rows, 4 treatment / 20 control / 4 outside, 7 disagreements),
  then the same exports under `PERIOD_RULE = "both"` (the 7 disagreeing rows leave in PASS A, counted per file and in
  `panel_build_settings.json`, the panel rebuilt) and under `"year"` (the v20.58 panel).
- `validate_design_options.py`: variants `pre2018_post2024` (calendar years), `pre_at_start_2022` (every year before the start, said)
  and `screen_keep` (the fill year kept, folder `_screenKept`), R == Python where R runs.
- `tests/run_all_tests.R` scenario E: `pre_cal`, `pre_at_start`, `screen_keep`; the panel's five columns and the two P00 reports;
  `input_design_audit_R.csv` (every file confirmed, `period_rule` in `panel_build_settings_R.csv`); `PERIOD_RULE` `"treat"` / `"year"` /
  `"both"` on a small frame; DESIGN vs PANEL under the fund timing (differs, said) and under fixed 2022 (0 rows differ); the screen's
  evidence file.

- The fifth request: `selfcheck.py` (the rule parsed and the post- / outcome-based names refused; a synthetic frame where rings 1 and 3
  share the treated pre-trend and rings 1 and 2 the closest level -- `"trend"` picks 1 and 3, `"level"` picks 1 and 2, the same
  pixels in every year and season, the evidence file written, `pre_blocks` stops at the ratio, `CLUSTER = "block"` clusters on the
  blocks; block ids from int / 18-digit / R ids and from coordinates; every notebook and P00 / R_P00 carry and pass the settings; the
  out-of-core parent decides once); `validate_did_spec.py` (`"level"` K = 2 -> rings 1 and 2 by the DGP's ring levels; `"trend"` = the
  two smallest pre-trend distances recomputed independently from every loaded row; the evidence file's numbers; the same control
  pixels in every year-season; M01 on the chosen rings = explicit-dummy OLS; the post-based rule refused; R the same rings, the same
  beta to 1e-8); `validate_design_options.py` (`ctrl_pre_rings2`, `ctrl_pre_ring1_level`, `ctrl_pre_blocks`, `cluster_block` on every
  panel, R == Python); `validate_out_of_core.py --only ctrl` (the three rules out of core = in memory on every engine, the same
  decision); `tests/run_all_tests.R` E (`ctrl_pre2`, `cluster_block`).
- The fourth request: `selfcheck.py` (`DESIGN_SOURCE` parsed and refused, the tag, a six-row frame under `"panel"` -- post / pre / did
  = the panel's, the design's differing rows counted, cohort and event time from the panel's first post year -- and back under
  `"model"`; every notebook carries and passes `DESIGN_SOURCE`; P00 / R_P00 carry `PIXEL_ONE_SITE`; the R library's functions;
  `Treat` in no panel schema); `validate_did_spec.py` (five pixels also exported in a Beguru file with ring 3: in the panel once per
  year-season, sub-watershed 7, ring 0; `Treat` absent; the consistency count 0 / 0 / 0; `DESIGN_SOURCE = "panel"` under
  `TREATMENT_YEAR = 2023` = the fixed-2022 estimate to 1e-12 with the 2022 rows counted as differing; `"model"` = 2023; the same in R);
  `validate_design_options.py` (`design_panel`, `design_panel_fixed_2023`, R == Python); `validate_preprocessing.py` (the shapefile case's
  consistency); `tests/run_all_tests.R` E (`Treat` absent, `design_panel`, `panel_pixel_consistency_R.csv` with 0 offenders).

What ran on the delivered code, and what could not run here, is in `VALIDATION_v20.59.md`.

## Re-run order

1. **P00 / R_P00** (the panel gains `treat / control / pre / post / did`; Python's P00 rebuilds by itself because the panel lacks the new
   columns; R_P00 always rebuilds). Read `panel_variation_by_block.csv` and the `pixel variation` line: it says at once whether your
   exports carry one value per year-season.
2. **The models.** With your settings as they were, `PRE_YEARS <- 2022` now warns and uses every year before 2022 (set `PRE_YEARS <- 2015`
   or `7` to say it exactly). If the screen still flags the year-seasons, open `OUTCOME_SCREEN_NDVI.csv`: `min == max` on a cell means the
   export holds one value there; `OUTCOME_SCREEN <- "keep"` runs the model on them regardless (results tagged `_screenKept`).
