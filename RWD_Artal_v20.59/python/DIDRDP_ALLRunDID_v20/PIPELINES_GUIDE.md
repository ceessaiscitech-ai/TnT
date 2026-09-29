# Two pipelines, one data layer  (v20.22)

```
 INPUT_DIR (any format, any name; single site or the 20-site pooled export with SWSiD_All)
    │  P00-P09  custom Python preparation: harmonise -> pixel ids -> site-aware dedup + coalescing
    │           -> NaN/zero policy -> panel (did_panel_full.parquet, site_id) -> per-variable files
    ├── P10  which models the data can support  ── P06 frozen-series / missingness / balance reports
    ├── P11  one model per site, then all sites pooled  (custom engine, 45 models, scenario machinery)
    │
    └── C.export_for_packages(outcome)  ->  estimator_files/package_input/<outcome>_<scenario>.{parquet,csv,json}
           ├── (bundle) R/                 the R pipeline: preparation + all 45 models — see R/README_R.md
           └── python_prebuilt/pf_pipeline.py   pyfixest · wildboottest                  (results/prebuilt_pyfixest/)
```

## Which to use for what
| need | custom engine (Python) | pre-built (R / pyfixest) |
|---|---|---|
| preparation, scenarios, coverage & identification diagnostics, frozen-series and no-data guards | **yes** | reads its output |
| point estimates (2x2, event study) | identical | identical |
| inference with few clusters (7 sub-watersheds; 20 sites pooled) | CR1 t / Rademacher bootstrap | **Webb-weight wild bootstrap, HonestDiD FLCI** |
| staggered / specialised estimators (CS, Sun-Abraham, BJS, synthdid) | custom implementations | **peer-reviewed packages** |
| a billion-row panel that does not fit in memory | **streaming estimator** | not possible |

Run both on every headline number; where they disagree, the package is right until proven otherwise.

## The package-input table (`PACKAGE_INPUT_SCHEMA`)
| column | meaning |
|---|---|
| pixel_id | unit id, int64, a pure function of the coordinate |
| site_id | SWSiD_All 1..20 (0 = single-site export without the column) |
| subwshed_id / cluster_id | the sub-watershed; cluster_id is what the scenario clusters on (site when `cluster='site'`) |
| Year, Season, period | Season 1-3 (0 = annual composite); period = Year_Season fixed effect (`site|period` when `pooled_fe='site_period'`) |
| treat, post, did, event_time | core (buff_km 0) = 1; post = Year >= the row's cohort (v20.57: the timing in force -- your fund workbook's first treated season per sub-watershed by default); did = treat x post; event_time = Year - cohort |
| cohort | the first Year the row's own series (sub-watershed x season) is treated, `Inf` for never-treated rings (did:: / csdid convention) |
| dose | v20.57: the fund workbook's amount released by the end of the previous season / the treatment area (`DOSE_VARIABLE`); 0 on the rings and before the start |
| buff_km, outcome, covariates | values with the missing-value policy applied -- no NaN, no exact zero |

## Multi-site (20 sub-watersheds)
- `data/sites/sites.csv` (built from `SWSs20_KarnatakaAll5k`): SWSiD_All, name, phase (Ph 1 = 11 sites, Ph 2 = 9),
  treatment_year. **Fill the treatment year of Phase 1** (`_sites.PHASE_TREATMENT_YEAR` or the CSV) before a pooled run with
  `TREATMENT_TIMING = "registry"`; the default since v20.57 (`"fund"`) dates every sub-watershed from your fund workbook (the registry
  year only for one the workbook does not date).
- Per site: the site's own treatment year, clusters by sub-watershed. Pooled: site x period fixed effects, clusters by
  site (20), two cohorts -> Callaway-Sant'Anna, Sun-Abraham, stacked DiD and Goodman-Bacon become identified.
- Overlapping rings of neighbouring sites are NOT duplicates: the dedup key is (site_id, pixel_id, Year, Season).
- P11 runs one model per site + pooled; `C.run_sites(model_fn)` does the same from any notebook.

## Status of the pre-built pipelines in this bundle
Written against the current public APIs (pyfixest >= 0.25; fixest, did, HonestDiD, fwildclusterboot from CRAN /
GitHub) but **not executed in the environment that produced this bundle** (no network, no R). Each starts with a
smoke test that compares its 2x2 with the custom engine on the same rows and stops on disagreement:
`python python_prebuilt/pf_pipeline.py NDVI --smoke` · R: `tests/selftest.R` in RStudio (see R/README_R.md).

## Yearly-first (v20.24): which rows every model estimates on
Your annual composite (Season 0) is complete for every year; the seasonal rows (Kharif / Rabi / Zaid) have gaps --
cloud, masks, a changing export footprint. A DiD on gappy seasonal rows is biased whenever the gaps differ
between the treated core and the rings, or change at treatment. `SEASONS = "auto"` (the default in v20.24-v20.28; since v20.29 the default is "all" -- see the v20.29 section; "auto" remains an option in every notebook and
in the engine) therefore:
1. estimates each outcome on the **annual rows** with pixel + year fixed effects;
2. fills any weather covariate the annual composite does not carry with the **same pixel-year's seasonal mean**
   (so the weather adjustment is kept, never dropped);
3. uses the **seasonal rows only for an outcome that has no annual values**, and says so in the log;
4. stamps `seasons_used` on every result row, and puts results in `<model>/<scenario>_yearly/` so they never mix
   with earlier seasonal results.
`P00` STEP 8 writes `season_choice_report.csv` (annual vs seasonal completeness per outcome, treated core vs
rings) and saves the DEFAULTS a model adopts for an option its CELL 1 leaves unset (v20.57: each model sets its own design in CELL 1).
`SEASONS = "all" | "seasonal" | "yearly" | named seasons | "auto"` in each model's CELL 1; a scenario file written before v20.24 (whose "seasonal" was only the old default) is upgraded to "auto",
a file written from v20.24 on is honoured exactly. The pre-built R / pyfixest / diff-diff pipelines read the
package-input table, which carries the same rows.

## Near-duplicate pixels (v20.25)
Pixels whose 10 m footprints overlap by >= 80 % -- or coincide -- are one pixel. PASS B builds a registry of every
pixel across all years and seasons, maps each near-duplicate onto one canonical pixel (the newer export's by default,
or the more complete one with `DEDUP_PRIORITY = "complete"`), keeps one row per cell and fills its gaps from the
dropped row. Settings: PASS B cell of P00 / P04. Audit: `pixel_overlap_report.csv`, `pixel_overlap_map.parquet`.
A panel built without the merge, and per-variable files older than the panel, are rebuilt automatically.

## Which sub-watershed every pixel is in (v20.28)
PASS A locates every row in the 20-SWS shapefile (`data/sites/SWSs20_KarnatakaAll5k`, UTM 43N) before de-duplication.
The SWS the data indicates -- a `SWSiD_All` column, a `SUBWSHED` / SWS-name column, or the folder name
(`SWSs20Final/<SWS>/...`) -- is **confirmed** when the pixel lies in that SWS's core or rings, **corrected** (id and ring)
when it lies in another SWS, **assigned** when the data names none, and kept but **flagged** when the pixel lies in no
polygon. The panel carries `site_id` (SWSiD_All), `sws_name` and `site_check` (0-4); `site_tagging_report.csv` lists
every file. `P02b_SWS_Tagging_Audit` runs the same check over the whole directory before any panel is built and can
write tagged Parquet copies (`tagged_inputs/`); the originals are never modified.
In the DiD the 20 SWS are clusters and strata; **cohorts are distinct start years** (per site in `sites.csv`).
`C.site_design_table()` (P11) shows per site: name, phase, start year, treated and control pixels, and match quality.

## v20.29 -- design defaults and pre-built packages
- Rows: all years, the annual composite AND Kharif / Rabi / Zaid (`SEASONS = "all"`).
- Fixed effects: pixel x season series + year x season (`UNIT_FE = "pixel_season"`; "pixel" = one per pixel).
- Covariates: `COVARIATES = [...]` in each model's CELL 1 (v20.57: with every other design option); outcomes refused as covariates.
- Pre-built packages: run **P12** once (installs pyfixest, wildboottest, diff-diff; verifies each against the engine);
  from then on the 2x2, event study, wild bootstrap and Callaway-Sant'Anna are computed by the verified package,
  labelled in every result (`engine` column). `C.prebuilt_status()` shows what computes what.

## v20.30 -- covariates per model, negative covariates, memory
- **Covariates**: chosen in each MODEL notebook (`COVARIATES = "all" | "mean_temp_rain" | "weather" | "none" | [list]`);
  preparation keeps every covariate column and row.
- **Negative covariates**: floored at 0 during preparation (Rain, Tmax, Tmean, Tmin); `ALLOW_NEGATIVE_COVARIATES = True`
  (in P00, before PASS A) removes the barrier; `NEGATIVE_COVARIATE_RULE` sets "zero" / "missing" / "keep" per variable.
- **Memory**: everything uses RAM / GPU up to 98 % of the total (v20.57, your rule; `_hardware.MEMORY_CEILING`), every core, no fixed
  sample size; the GPU first when the rows fit there, else RAM; regressions are never chunked (v20.56). `import _hardware as H;
  print(H.memory_report())` shows the headroom.
- **The design** (v20.57): set in each model's CELL 1 and applied when the model runs (timing, dose, rings, years, seasons, fragments,
  overlap rows, fixed effects, covariates); P00 only saves the defaults. DESIGN IN EFFECT is printed and saved beside the results.
