# TnT — REWARD DiD pipelines, v20.59

| folder | what it is |
|---|---|
| `RWD_Artal_v20.59/` | the full Python pipeline (P00 + all 45 models) -- THE delivered module (Python only since 2 Oct) |
| `R_separate_track/` | the R pipeline (`RWDR_v20.59`) and the R library, kept outside the delivered module since 2 Oct (continued in its own chat); not in the zip |
| `CHANGELOG_v20.59.md` | what changed in this version and why (also in each bundle's `docs/`) |

The engine (`python/DIDRDP_*/_common.py`, `_prep_common.py`, `_outofcore.py`, `_ooc_models.py`); `docs/VALIDATION_v20.59.md` says which gates
ran on this code and where. **2 Oct:** every result row carries a p-value beside its beta and SE and `results/HEADLINES_ALL_VARIABLES.csv`
collects them across variables; the panel stores the outcomes at full precision (`P.PANEL_FLOAT_DTYPE = "float64"`, the 8th-10th decimals
survive; `panel_precision_report.csv`, with `all_values_float32_representable` showing a rounding that happened before the panel); an
earlier run's output inside the exports folder is recognised as the pipeline's own product and never read as an export; PASS B's pixel
registry has a memory fall-back.
The four-model bundle (`RWD_4Models`) is discontinued at your request: its four models (M01, M02, M16, M34) are part of both
remaining pipelines, and the validators that ran on it (`selfcheck.py`, `validate_preprocessing.py`, `validate_known_answers.py`,
`validate_design_options.py`) are the same scripts in `RWD_Artal_v20.59/python/DIDRDP_ALLRunDID_v20/`.

**The period and the groups in the DID-ready panel (v20.59, your rule):** every input file's `Treat` column is 1 = post-treatment,
0 = pre-period; `PERIOD_RULE` (`P00_Settings` / `lib/reward_paths.R`) says whether the panel's `post` / `pre` come from that column
(`"treat"`, the default), from `Year >= TREATMENT_YEAR` (`"year"`) or from both, which must agree (`"both"`: a disagreeing row
leaves, counted). `buff_km` / `distance` 0 = the treatment area (`treat` = 1), 1–5 = the control rings (`control` = 1); `did` = treat x post.
P00 / R_P00 confirm this on every input file (`input_design_audit.csv` / `input_design_audit_R.csv`) before the panel is built.
`Treat` itself is then dropped from the panel (both languages). **Every model estimates on the panel's design by default**
(`DESIGN_SOURCE = "panel"` in every notebook; results tagged `_panelDesign`; the design in effect is compared with it, not estimated
on) -- `"model"` is design-based modelling (the timing / `TREATMENT_YEAR` settings build `post` / `pre` / `did`). **One sub-watershed
and one ring per pixel** (`PIXEL_ONE_SITE`, both languages): the polygon that holds a row's latitude / longitude decides its
sub-watershed and ring, so the same pixel has the same `site_id` / `buff_km` in every year and season and appears once per
year-season -- confirmed on the finished panel (`panel_pixel_consistency.csv` / `panel_pixel_consistency_R.csv`).
**The control group chosen on the PRE period** (`CONTROL_SELECTION`, both languages, panel level and every model): `"pre_rings"` =
the 1 or 2 buffers whose pre-period series is closest to the treatment area's; `"pre_blocks"` = control clusters (~1 km blocks) from
any part of the buffers; `"trend"` / `"level"` / `"both"` as the closeness; the same control pixels in every year and season; the
evidence in `CONTROL_SELECTION_<outcome>.csv`; a post- or outcome-based rule is refused. `CLUSTER = "block"` clusters the SE on ~1 km
blocks. `SAME_PIXELS` (`"pre_post"` default | `"all"` | `"off"`) keeps the treated and control groups the same pixels in pre and post
(or in every year-season), confirmed on every sample. What to change when the estimate is not significant, and what never to change:
`ECONOMETRIC_ADVICE_v20.59.md`.
**Every optional customisation has a USE_ switch and is OFF by default (1 Oct):** `CUSTOMISATION_GUIDE_v20.59.md` explains each option of
SECTION A (the standard design), SECTION B (the pre-period control group, the same pixels) and SECTION C (the panel-preparation enhancements).
**4 Oct:** headers are read for what they are whatever their writing style (units, suffixes, aliases, a BOM; a statistic such as `NDVI_sd`
stays apart), `unresolved_columns.csv` says what PASS A did with every header, name-keyed joins for the crosswalk and the dose, and
`panel_column_audit.csv` confirms every DiD / time column on every row and the natural row order (Year > Kharif, Rabi, Zaid, Yearly >
sub-watershed > pixel) on the finished panel. **The two bundles are kept separately:** `DIDVALIDATION_v20.59.zip` (Python, this module) and
`DIDVALIDATION_R_v20.59.zip` (R, `R_separate_track/RWDR_v20.59`).
`build_panel.py --input <exports>` / `Rscript build_panel.R input=<exports>` build the panel from a path without a notebook; **3 Oct:**
`01_Panel_Preparation/P00b_Build_Panel_From_Path.ipynb` does the same from a notebook whose FIRST cell names the folder, one cell per step,
every step's result kept on `B` (`B.summary()`); and `PRE_YEARS` / `POST_YEARS` take a list of calendar years (`[2015, 2017, 2018]`,
`"2015, 2017-2021"`) = exactly these years.
**The three specifications** (panel preparation, the surrogate / synthetic DiD engine, the configuration and orchestrator) are integrated in both
languages: `DONUT_RINGS`, `CONTROL_SELECT_ON = "rmse"` + `select_optimal_control_rings`, `PRECISION_TOLERANCE`, `LANDUSE_KEEP`, `BASELINE_NDVI_MIN`,
`MIN_PIXEL_COVERAGE_PCT`, `DROP_SINGLETONS`, the range-safety check; `surrogate_did_estimator.py` / `lib/surrogate_did_estimator.R` (the
two-level synthetic DiD and the surrogate index, the same numbers to 1e-8); `config/analysis_config.yaml` read by `orchestrator.py` and
`orchestrator.R`, which run the pre-execution checks and write `SPEC_COMPARISON_<outcome>.csv` (canonical, donut, matched, synthetic DiD,
surrogate index -- beta, SE, p, pre-trend p, N). Section "Your validation request" of the changelog says what was already there and what was added.
