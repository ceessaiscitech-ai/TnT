# RWDR v20.59 — the R track, 3 Oct: your R_P00 run that hung for hours, and the 1–2 Oct corrections ported from Python

This bundle is the R pipeline only (`RWDR_v20.59/`). The Python module is delivered apart (`DIDVALIDATION_v20.59.zip`); the two no longer
share a zip. Everything below is in `RWDR_v20.59/lib/` and is proved by `tests/test_3oct_additions.R` (27 checks) and `tests/run_all_tests.R`.

## 1. Your R_P00 run: hours without a line after the duplicate step — what it was, what changed

Your log ended at `[OK] 30,875,154 rows shared a (sub-watershed, pixel, year, season) with another file -> 15,437,454 kept ...` and then
nothing for hours (86,579,265 rows, 3.29 M pixels, 1,253 files). The cause was found by reading the code and timing every step on synthetic
exports in your layout (`tests/benchmark_prep_scale.R`, new):

- **THE hang: `panel_variation_R`** (the pixel-variation report, right after the design columns). Its grouping used `get(v)` inside `j`
  with an `i` subset: data.table then gathers EVERY column of every row into `.SD`, group by group, single-threaded, once per outcome —
  measured here at 36 s per outcome on 6 M rows × 63 columns. At your 71 M rows × ~60 columns that is 7–30 min per outcome, 2–8 hours for
  the 17 outcomes, with no line printed until all of them were done. The function now takes only the three columns the moments need; the
  numbers are bit-identical (checked against the old body on a synthetic panel), about 6 s per outcome at your size, and **each outcome is
  said when it is done**.
- **The de-duplication** (the step BEFORE the line you saw — ~50 minutes of it was the donor loop, `get(v)[1L]` per group over 15.4 M
  groups × 10 outcomes, plus two `duplicated()` sorts of 86 M rows and an N × 10 matrix). Now: one radix pass for the repeated keys, the
  missing-value rank column by column, the kept row by `unique()` on the sorted groups (version-independent; without data.table's GForce
  rewrite the old `.SD[1L]` was 15 M `[` calls), the donor values by `unique()` on a keyed table. The rows, values and counts are the same
  (checked with the fill rule on and off). Progress lines inside the step.
- **The pixel registry** (before the dedup and in the confirmation after it) copied 15 columns of the whole frame and built an N × 10
  outcome matrix (~20 GB at your size). Now the usable cells are counted column by column and six columns are grouped; the confirmation
  after the dedup needs only latitude / longitude per pixel. When even the lean pass cannot be allocated, the registry is built one
  year-season block at a time and the parts are combined exactly (the twin of Python's memory fall-back), said when it happens.
- **Memory**: the per-file list was kept alive after the files were bound into one table (+33 GB at your size for the whole run); it is
  freed now. A no-op "rows without outcome" step no longer copies the table. Peak RSS on the benchmark: 9.7 GB → 7.5 GB at 4.7 M rows.
- **Every step is said before it starts (`...`) and when it ends (`N s; M min since the start`)**: the file reads (every 50 files), the
  pixel ids, the overlay, the join to the sub-watersheds, the fragment codes, the near-duplicate pixels, the duplicates (three lines inside),
  the rows without an outcome (also when 0), the confirmation checks, the pixel consistency, the design columns, the variation (one line per
  outcome), the columns kept, the benchmark-site join, the sort, the write, the precision report, the balance. A long silent step is one
  that is still running, never one that is stuck.
- **The panel is written beside its name and renamed into place.** On Windows a `did_panel_full.parquet` still open in another R or Python
  session made the write fail after hours of work; now the finished file is there under `.writing` and the message says what to close.
- **A valid panel on disk is kept.** `FORCE_REBUILD <- FALSE` (R_P00's build chunk, `lib/reward_paths.R`): when `panel_is_valid_R()` is TRUE
  (every required column, rows, Parquet DOUBLE, `panel_build_settings_R.csv` beside it) R_P00 and `build_panel.R` skip the build and print
  the precision report; `TRUE` builds again. `build_panel.R force=TRUE` now has an effect (the validity rule did not exist before).
- **Benchmark** (`tests/benchmark_prep_scale.R pixels=200000 threads=4`, 352 files, 4.7 M rows, 200 k pixels, this 4-core machine): the
  whole `run_prep()` 198 s → 143 s even though the baseline already had the fast variation step substituted; the 17-outcome variation 5 s;
  the de-duplication 26 s for 1.68 M repeated rows. The script is in the bundle so you can time your own machine (`pixels=1000000` fits
  in ~40 GB).

What you will see on your machine: the read loop prints every 50 files; the dedup prints its three phases; after the `[OK] ... rows
shared` line every later step prints within minutes; the variation step prints 17 lines. If the overlay or the dedup still takes long,
the line before it names the step and its size.

## 2. The 1–2 Oct Python corrections, now in R

- **A p-value beside every beta and SE in every result file.** The headline row had one since v20.58 (`save_result`); now every row of the
  models' tables (`<model>_<outcome>_table.csv`: event studies, placebo rows, quantiles, dose terms) and of the package tables
  (`results/package_tables/`) gets `p_value` and `p_how` when it carries an estimate and an SE and no p: t with clusters − 1 df when the
  sample's clusters are known (G ≥ 2), else normal (`ensure_p_value_R`, the twin of Python's `_ensure_p_value`). A p that is there is
  never touched; a character `estimate` column is skipped. The headline's own fall-back is aligned with Python (normal below 2 clusters).
- **`results/HEADLINES_ALL_VARIABLES_R.csv`** — one table across variables and models (model, outcome, scenario, kind, estimate, se,
  p_value, p_how, se_how, engine, engine_version, n_clusters, n_obs, written), the row of the same model × outcome × scenario replaced at
  every run (`headlines_all_R`, called by `save_result`; no notebook change needed).
- **Precision.** R stores doubles end to end (`arrow::write_parquet` → Parquet DOUBLE; there is no float32 option), so the panel never lost
  the 8th–10th decimals in R. To PROVE it and to catch a loss upstream: `output/panel_precision_report_R.csv` (`panel_precision_report_R`,
  written by R_P00 / `build_panel.R` / the out-of-core path) — per variable the stored type, rows, finite values, distinct values, the
  smallest difference present, the decimals needed, one float32 step at the largest magnitude, `float32_would_merge_values`,
  `full_precision_kept`, `all_values_float32_representable` (TRUE = the values were rounded to 7 digits BEFORE the panel: in the export or
  in an older float32 panel read as an input). `panel_is_valid_R` rejects a float32 panel (another writer's) and `load_panel_R` says once
  per session when it reads one.
- **The pipeline's own products are never read as exports** (`is_pipeline_product_R`, `discover_exports`): a folder holding a
  `did_panel_full.parquet` (an earlier run's output, skipped whole), `shard_*` / `part_*` files, any Parquet / Feather carrying the panel's
  own columns (R's `pixel_id + did + site_check`, Python's `pixel_id + did_term + schema_vintage`). The discovery line counts them. Found
  in Python on 2 Oct, where an older float32 panel inside the exports folder won the de-duplication; the R discovery had the same hole,
  and one more: a sibling folder whose name begins with `output` was silently treated as the current output folder (fixed).
- **Worker processes capped at 60 on Windows** (`pool_cap_R`, the twin of Python's `WINDOWS_POOL_LIMIT`): `fect`'s and `did`'s `cores`, the
  Dask / Spark workers of the out-of-core path. Threads (data.table, fixest) stay at `N_THREADS`.
- Already in R before this bundle: the USE_ switches (every optional customisation OFF, sections B / C in every notebook), R_P00's
  progress lines of 1 Oct, `build_panel.R`, `orchestrator.R`, the surrogate / synthetic DiD module.

## 3. Checks

`tests/test_3oct_additions.R` (scenario I of `run_all_tests.R`): the three rewritten functions against their old bodies (same numbers, fill
rule on and off, the registry's block fall-back forced), the no-copy path keeps the table usable, `ensure_p_value_R` (t, normal, an existing
p kept, a character estimate skipped, a table without estimates untouched), `headlines_all_R` (one row per key, replaced), the precision
report on a double column with values 1e-10 apart and on its float32 copy, `panel_is_valid_R` on both, the float32 note said once,
`discover_exports` with an earlier run's output folder, a stray panel copy, an out-of-core partition and a real Parquet export inside the
exports folder, `is_pipeline_product_R` by name, `pool_cap_R`, `FORCE_REBUILD`, and `build_panel.R` run twice on that folder (the products
counted, the panel built with its precision report, the second run keeps it; at least 12 start and 12 end progress lines).
`tests/run_all_tests.R quick`: every model and scenario as before. `tests/benchmark_prep_scale.R`: the timings above.

## 3a. `tests/run_all_tests.R` on this code: three expectations were stale since 1 Oct

The full suite had not been re-run after the 1 Oct commits (the USE_ switches, the R_P00 speed-up, and PIXEL_ONE_SITE letting the polygon
decide a pixel's ring for confirmed rows too). Run on 3 Oct it failed three groups of checks that encode the OLD ring rule, not the library:
scenario D's OVERLAP_ROWS case (the pixel Haligeri's export calls "core" from 2023 is ring 1 in every year of the panel now -- no ring
conflict is left for OVERLAP_ROWS to act on; the check now asserts one ring in the panel, drop == keep, no two-ring pixel in
`panel_pixel_consistency_R.csv`), scenario F's poison test (the three "flipping" pixels are ring-1 CONTROL rows of the panel under that rule,
so they are data and are no longer poisoned; with PIXEL_ONE_SITE FALSE they leave whole, as before), and scenario E's `pix_switch_off`
check, added on 1 Oct and never run (a fixed-2022 design was compared with the fund-timing base; it is now compared with the same design
without the pixel rule, `cluster_block`, and must have more rows than `pix_all`). The de-duplication and the registry were proved
unchanged against their old bodies before any test was touched (section 3). The known M13 gap (`polars` not installable here) stays.

## 3b. The adversarial review of the diff (3 Oct) and what it changed

A second reading, set to refute every claim above, held on the numbers (the three rewrites against their old bodies on 16 variants with NA
keys, mtime ties, all-NA donors, fill rule and priority both ways; the no-copy path; the discovery rules; the Windows rename) and found six
things, all fixed and covered by `test_3oct_additions.R`: the precision report after the write is wrapped so an error in it can never cost the
panel's valid status (and it no longer needs dplyr); `ensure_p_value_R` coerces a logical-NA `p_value` column and a factor `p_how` before
filling (a bare `p_value = NA` column would have taken TRUE); `headlines_all_R` re-reads its file as text so `20.60` and the ISO timestamp
survive; the registry's block fall-back breaks file-time ties by the original row order, exactly as the one pass; `FORCE_REBUILD` is
documented as the notebook's own setting (the library value is the default); the package tables written by `wr()` get a normal p (they do
not know the clusters) and say so in `p_how`.

## 4. Where each change lives

`lib/reward_prep.R` (panel_variation_R, resolve_duplicates, pixel_registry + `.pixel_registry_pass` + `n_finite_R`, drop_rows_without_outcome,
discover_exports + is_pipeline_product_R, panel_precision_report_R, run_prep's progress lines), `lib/reward_design.R` (panel_write,
panel_is_valid_R, panel_precision_note_R, ensure_p_value_R, headlines_all_R, save_result), `lib/models_prebuilt.R` (`wr()`, the `cores`
caps), `lib/reward_outofcore.R` (ooc_cores), `lib/reward_prep_ooc.R` (the precision report after the out-of-core write), `lib/reward_paths.R`
(`FORCE_REBUILD`, `pool_cap_R`, `WINDOWS_POOL_LIMIT_R`), `build_panel.R`, `rstudio/R_P00_Prepare_Panel.Rmd` and `jupyter/R_P00_Prepare_Panel.ipynb`
(the build chunk), `tests/test_3oct_additions.R`, `tests/benchmark_prep_scale.R`.
