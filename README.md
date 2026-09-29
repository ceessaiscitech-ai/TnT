# TnT — REWARD DiD pipelines, v20.59

| folder | what it is |
|---|---|
| `RWD_4Models_v20.59/` | the four-model pipeline (P00 + M01, M02, M16, M34) in Python **and** R — the bundle behind the v20.58 run this version fixes |
| `RWD_Artal_v20.59/` | the full Python pipeline (P00 + all 45 models), with the R library beside it |
| `RWDR_v20.59/` | the full R pipeline (R_P00 + all 45 models; RStudio and Jupyter) |
| `CHANGELOG_v20.59.md` | what changed in this version and why (also in each bundle's `docs/`) |

The engines (`python/DIDRDP_*/_common.py`, `_prep_common.py`, `_outofcore.py`, `_ooc_models.py`; `R/lib/*.R` / `lib/*.R`) are the same files in
all three bundles, byte for byte; each bundle's `docs/VALIDATION_v20.59.md` says which gates ran on this code and where.
