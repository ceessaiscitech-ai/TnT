# R/ — the R pipeline of the four-model project (M01, M02, M16, M34)

Open `RWD_4Models.Rproj` in RStudio.

1. `00_SETUP.R` — once (needs internet): installs this project's R packages only (data.table, arrow, sf, RANN, readxl, jsonlite, dplyr,
   fixest, HonestDiD, rmarkdown, knitr, ps, remotes) — pre-built binaries first — and registers the R kernel for Jupyter.
2. `rstudio/R_P00_Prepare_Panel.Rmd` — builds the panel once from `D:/LKT/RWDR/data` into `D:/LKT/RWDR/data/output_4Models`
   (only what the four models read; the same rules as the Python P00).
3. `rstudio/R_M01.Rmd`, `R_M02.Rmd`, `R_M16.Rmd`, `R_M34.Rmd` (or `R_RUN_ALL_MODELS.Rmd`) — the design of each run in its settings chunk.
4. `rstudio/R_V01_Results_Audit.Rmd` — every result audited.

The same notebooks for Jupyter (R kernel) are in `jupyter/`. `lib/` is the R library of the full R pipeline (RWDR) byte for byte, except
`reward_paths.R` / `reward_packages.R`, which set this project's models (`PIPELINE_MODELS`) and output folder (`OUTPUT_SUBDIR`); the Python
notebooks call the same `lib/` for M34's R route (HonestDiD on M02's event study). Tests: `Rscript tests/run_all_tests.R` (from this folder;
`quick` = the models only).

**Beyond 98 % of the RAM** the four models and R_P00 run OUT OF CORE (`lib/reward_outofcore.R`, `lib/reward_prep_ooc.R`): pixel partitions,
the same R code per partition, the two-way fixed effects solved exactly from their cross-products -- never sampled. The partition tasks run on
Dask, then Spark (through `lib/reward_ooc_engine.py`: set `PYTHON_EXE` in `lib/reward_paths.R` to the Python with dask / pyspark), then R
itself (always). `tests/run_all_tests.R` scenario H: in memory == out of core on every engine; R_P00 block by block == in memory, row for row.
