# Customisation guide — every option, what it does, and its USE_ switch (v20.59, 1 Oct)

Every model notebook (Python: CELL 1; R: the first chunk of `R_Mxx`) and the panel notebooks (P00_Settings, R_P00) carry the same options with
the same names. They come in three sections. **Section A is the standard DiD design and is always in force. Sections B and C are optional
customisations: every one has a `USE_...` switch, and every switch is OFF (`False` / `FALSE`) by default.** With a switch OFF the option is not
applied at all, whatever the value written beside it says; the notebook runs the standard design of section A. With a switch ON the option is
applied exactly as set. `DESIGN IN EFFECT` (printed by every run, saved as `DESIGN_IN_EFFECT.csv` beside the results) shows each option with
its setting, `-- switch OFF` when it is not applied, and the value actually used. A rule in force also tags the results folder (the tags are
named below), so two runs never overwrite each other.

How to switch something on: set its `USE_...` line to `True` (R: `TRUE`), set the value(s) beside it, and run the notebook. Nothing else
changes; P00 / R_P00 is never re-run for a design choice.

## Section A — the standard DiD design (always in force)

| Option | Values | Meaning |
|---|---|---|
| `DESIGN_MODE` | `"recommended"` (default) / `"manual"` | how an option set to `"data"` is resolved: from the data (`DESIGN_RECOMMENDATION.md`) or as "everything" |
| `TREATMENT_TIMING` | `"fund"` / `"registry"` / `"fixed"` | when treatment starts: the fund workbook's first treated season per sub-watershed, the registry year, or `TREATMENT_YEAR` |
| `TREATMENT_YEAR` | a year | the fixed start, and the fall-back for an undated sub-watershed |
| `FUND_START_RULE`, `DOSE_VARIABLE` | see the notebook | the fund timing rule and the dose variable of the dose models |
| `CONTROL_ZONES` (R `CONTROL_RINGS`) | `"data"` / `"1-5"` / `"2-5"` / a tuple | which buffer rings are the control pool (ring 0 is always the treatment area) |
| `PRE_YEARS`, `POST_YEARS` | `"data"` / `"all"` / a count / a calendar year | the years before and from the start |
| `SEASONS` | `"all"` / `"seasonal"` / `"yearly"` / `"Rabi"` / `"Kharif+Rabi"` / `"auto"` | which season rows are estimated on. **`"Rabi"` is the dry-season run of the specifications** |
| `EXCLUDE_TRANSITION_YEAR` | `False` / `True` | drop the first treated year of each series |
| `UNIT_FE`, `POOLED_FE`, `CLUSTER` | see the notebook | the fixed effects and the clusters of the SE. **`CLUSTER = "block"` = ~1 km spatial blocks as clusters** (many clusters, spatial correlation absorbed) |
| `SUB_WATERSHEDS`, `FRAGMENT_RULE`, `OVERLAP_ROWS` | see the notebook | your location rules: only the processed sub-watershed's own rows, no repeated or overlapping pixel |
| `EXCLUDE_GAPFILLED`, `OUTCOME_SCREEN` | `True` / `"drop"` (defaults) | history-filled rows out; a fill year-season or a collapsed-coverage year-season out (evidence file beside the results) |
| `DESIGN_SOURCE` | `"panel"` (default) / `"model"` | estimate on the panel's `treat / post / did` (the exports' Treat flag) or on the design built from the timing settings |
| `COVARIATES`, `NONNEGATIVE` | see the notebook | the weather covariates; the no-negative-values option |

## Section B — the control group chosen on the PRE period (your request of 30 Sep) — OFF by default

What it is for: when the estimate is not significant, the usual culprit is a control group that does not move like the treatment area before
treatment. This section lets you choose, per outcome, the buffers (or clusters of pixels inside the buffers) that are closest to the treatment
area **on the pre period only**, and then keeps that control set fixed for the whole panel, as the DiD rule requires.

| Switch / option | Default | Meaning |
|---|---|---|
| `USE_CONTROL_SELECTION` | `False` | OFF = every ring of `CONTROL_ZONES` is the control group. ON = `CONTROL_SELECTION` decides |
| `CONTROL_SELECTION` | `"pre_rings"` | `"pre_rings"`: the `CONTROL_SELECT_K` buffers whose pre-period series is closest to the treatment area's (your "most close 1 or 2 buffers"). `"pre_blocks"`: control clusters (~1 km blocks of pixels) from any part of the buffers, the closest first, until `CONTROL_SELECT_RATIO` x the treated pixels (your "clusters from any part of the buffers") |
| `CONTROL_SELECT_K` | `2` | pre_rings: 1 or 2 buffers (up to 5) |
| `CONTROL_SELECT_RATIO` | `3.0` | pre_blocks: control pixels >= this x the treated pixels |
| `CONTROL_SELECT_ON` | `"trend"` | what "closest" means. `"trend"` = the demeaned pre series' distance (what the parallel-trends assumption asks; recommended). `"level"` = the nearest pre-period mean (your "mean of the treatment area vs the buffer's mean"). `"rmse"` = the RMSE of the cell-wise pre differences. `"both"` = trend + level |
| `USE_SAME_PIXELS` | `False` | OFF = a pixel may contribute to one side only (the v20.58 sample). ON = the treated and control groups are the same pixels across the panel |
| `SAME_PIXELS` | `"pre_post"` | `"pre_post"`: every pixel must be observed before and after treatment, else it leaves. `"all"`: in every year-season (a balanced pixel set) |

Rules that always hold when the section is ON: the decision uses the pre period only (a rule named after the post period or the outcome's mean
is refused, because it would select on the result); it is made once per outcome and applied to every year and season; the treated pixels are
never touched. Evidence: `CONTROL_SELECTION_<outcome>.csv` (R: `_R.csv`) beside the results lists every candidate with its pre-period rows,
pixels, level gap, trend distance, RMSE gap, score, rank and whether it was chosen. Tags: `_ctrlPre2r` / `_ctrlPreBlk3x` (+ `L` / `R` / `B`
for level / rmse / both), `_pixPP` / `_pixAll`. Out of core the parent decides once on the merged pre-period facts and every worker applies
the same set. `select_optimal_control_rings(df, outcome_var, treat_ring=0, candidate_rings=[2,3,4,5], pre_years=range(2015,2022), top_k=2)`
(R `select_optimal_control_rings_R`) is the same decision as a function you can call on a frame.

## Section C — panel-preparation enhancements (the three specifications of 30 Sep) — OFF by default

| Switch / option | Default | Meaning |
|---|---|---|
| `USE_DONUT` / `DONUT_RINGS` | `False` / `[1]` | ON = the named ring(s) leave the control pool before any control choice: the ring next to the core shares the works' hydrology (spillover), so keeping it as a control subtracts part of the effect from itself. Tag `_donut1` |
| `USE_LANDUSE_MASK` / `LANDUSE_KEEP` | `False` / `[2]` | ON = only pixels whose pre-period (baseline) `LandUse` class is in the list stay (your exporter's codes for agriculture). The class is read on the pre period, so the works cannot move a pixel between groups. Tag `_lu2` |
| `USE_BASELINE_NDVI_MASK` / `BASELINE_NDVI_MIN` | `False` / `0.25` | ON = only pixels whose pre-period mean NDVI exceeds the threshold stay (an agricultural mask on the baseline). Tag `_ndviPre0.25` |
| `USE_COVERAGE_THRESHOLD` / `MIN_PIXEL_COVERAGE_PCT` | `False` / `0.70` | OFF = the standard screen (a year-season below 5 % of the typical coverage leaves). ON = a year-season whose treated or control coverage is below this share of the typical one leaves (your log: 2023 Zaid, 2025 Kharif / Zaid). Tag `_cov70` |
| `USE_DROP_SINGLETONS` | `False` | ON = series seen once leave before the demeaning (the pre-flight; pyfixest drops them itself). Tag `_noSingle` |
| `USE_PRECISION_TOLERANCE` / `PRECISION_TOLERANCE` | `False` / `1e-6` | OFF = the no-data zero is an exact 0 (the v20.58 rule). ON = \|value\| <= the tolerance is the no-data zero (at panel build and at the model stage), and a year-season is "constant across pixels" within it — indices in [-1, 1] are never compared with exact equality |

The seasonal isolation of the specifications is `SEASONS = "Rabi"` (section A); the block clusters are `CLUSTER = "block"` (section A).
The range-safety check (the outcome within its physical bounds, no no-data code) always runs and is reported; it is not a customisation.

## The orchestrator's configuration file (`config/analysis_config.yaml`)

The same switches, all `false`, with `CONTROL_SELECTION_METHOD: all` (= the selection OFF; `pre_bias_min` / `closest_1` / `closest_2` turn
it on) and `SEASON_FILTER: All`. The comparison report's own specs set what they need (the donut spec turns the donut on, the matched spec
the control selection, both for that spec only); every other spec follows the file's switches.

## Where a switch is checked in the code

Python: `_common.opt(key)` returns the value in force (the setting when its switch is on, else the "do not use" value); every rule
(`donut_rule`, `landuse_rule`, `baseline_ndvi_rule`, `select_controls`, `same_pixels_rule`, the screen, `_usable`, the tag, the design report)
reads through it; `_prep_common.USE_PRECISION_TOLERANCE` at panel build. R: `design_settings()` holds both the setting (`*_set`) and the value
in force; `.tol_R()`, `.cov_R()`, `.same_pixels_opt_R()` in `reward_paths.R`. `selfcheck.py` confirms that a rule with its switch off changes
nothing and that every notebook carries every switch set to False / FALSE.
