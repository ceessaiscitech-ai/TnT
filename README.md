# TnT — REWARD DiD pipelines, v20.59

| folder | what it is |
|---|---|
| `RWD_Artal_v20.59/` | the full Python pipeline (P00 + all 45 models), with the R library beside it |
| `RWDR_v20.59/` | the full R pipeline (R_P00 + all 45 models; RStudio and Jupyter) |
| `CHANGELOG_v20.59.md` | what changed in this version and why (also in each bundle's `docs/`) |

The engines (`python/DIDRDP_*/_common.py`, `_prep_common.py`, `_outofcore.py`, `_ooc_models.py`; `R/lib/*.R` / `lib/*.R`) are the same files in
both bundles, byte for byte; each bundle's `docs/VALIDATION_v20.59.md` says which gates ran on this code and where.
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
