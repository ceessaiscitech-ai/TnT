# The R track — kept here, outside the delivered module

On 1 Oct you asked for the R code to be dropped from this module and continued in its own chat. Nothing is lost: the whole R pipeline as
it stood (the `RWDR_v20.59` bundle and the R library + orchestrator that lived beside the Python engine) is in this folder, with every
change up to that point (the USE_ switches, the R_P00 speed-up, `build_panel.R`, `orchestrator.R`, `surrogate_did_estimator.R`, the
scenario-E tests). The delivered module (`RWD_Artal_v20.59`, the zip) is Python only; its validators report "R not part of this module"
where they used to compare with R.

- `RWDR_v20.59/` -- the R pipeline (R_P00 + 45 models, RStudio and Jupyter notebooks, `lib/`, `tests/run_all_tests.R`, `build_panel.R`, `orchestrator.R`, `config/`).
- `RWD_Artal_R/` -- the copy of `lib/` that sat at `RWD_Artal_v20.59/R/` (byte-identical to `RWDR_v20.59/lib/`), with `orchestrator.R`, `build_panel.R`, `config/` and `tests/`.

Start the R chat from `RWDR_v20.59/`; `R_separate_track/RWD_Artal_R` is the same library.

**3 Oct:** the R track received the 1–2 Oct Python corrections (a p beside every beta / SE, `HEADLINES_ALL_VARIABLES_R.csv`, the precision
report and float32 guard, the own-products rule of the file discovery, the Windows worker cap) and the fix of the R_P00 run that hung for
hours after the duplicate step (`CHANGELOG_R_v20.59.md`, `VALIDATION_R_v20.59.md`). The R-only zip is `DIDVALIDATION_R_v20.59.zip`.
