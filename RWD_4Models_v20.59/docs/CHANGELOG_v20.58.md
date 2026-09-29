# v20.58 — only the current sub-watershed's own rows in every model (proven by a poison test); your rings, years and seasons in every model; R = Python model by model; every number with its own SE and p; every calculation in double precision; beyond 98 % of the RAM out of core on Dask, Spark or the built-in batches (Python and R, exact); the four-model pipeline P00 + M01, M02, M16, M34

**What your v20.56 R log showed, and what was behind it.** (1) `CONTROL_RINGS <- 1:3` but rings 1–5 in some results: v20.56's
recommended mode replaced your rings (fixed in v20.57), and M17 / M18 / M24 still read every ring whatever the setting — now no model
does. (2) Numbers that looked like placeholders: effects without an SE (NA), p-values printed as `< 1e-300` (a normal p on 6 year
clusters, a bootstrap or permutation p of exactly 0), a HonestDiD breakdown capped at the grid's last value (5), a design-based p that
belonged to a different number than the estimate printed beside it, M15's p that did not belong to its mean placebo effect, M35's
cluster SE of 3.3e-05 against a design SE of 0.0012. Each is fixed (4). (3) LSWI gave exactly NDMI's result and WSSI exactly minus ESI's:
in your exports LSWI and NDMI are the same index and WSSI = 1 − ESI — not a copy; every run now says so (4).

1. **YOUR RULE — only the current sub-watershed's own rows in every model.** Every row gets a location code, in Python and in R,
   from one table per panel (`LOCATION_TABLE.json`): 0 = kept; 1 = another sub-watershed's data (not processed in this run); 2 = outside
   every sub-watershed polygon; 3 = an overlapping, repeated or near-duplicate pixel row, or a control row of a pixel TREATED in another
   processed sub-watershed; 4 = a pixel whose ring differs between its rows (all its rows). The processing set is
   `SUB_WATERSHEDS = "data"` (every sub-watershed with ≥ 5 % of the largest one's rows; one sub-watershed = its major one) | `"major"` |
   names / ids. `FRAGMENT_RULE = "drop"` leaves codes 1–2 out, `OVERLAP_ROWS = "drop"` codes 3–4 — from EVERY group: treated and control,
   pre and post; `"keep"` is your option (tagged, printed as KEPT). Applied where every model's data pass (`load_panel`, and
   `build_treatment_columns` for a frame that did not pass it; R `load_panel_R`). Every run prints the rows left out per code and group
   and writes `LOCATION_RULE_<outcome>.csv` beside the results.
   - **SAMPLE INTEGRITY, confirmed on every model's own estimation sample** (never assumed): every (pixel, year, season) once, one ring per
     pixel, no pixel both treated and a control, nothing outside the processed sub-watershed(s), exactly the design's rings / years /
     seasons — `SAMPLE_INTEGRITY_<outcome>.csv` beside the results; a violation under the "drop" rules stops the model (nothing is
     estimated on a leaking sample).
   - **Proof — the poison test** (`validate_location_poison.py`; R: `tests/run_all_tests.R` scenario F): your Koranahalli layout (named
     exports + repeating tiles, pixels outside every polygon, a piece of Kodihalli's core, three ring-1 pixels whose ring flips between
     exports, a grid shifted 3 m, a fund workbook with a Rabi 2024 start) written twice with the same random numbers — clean, and with
     EVERY row the design must leave out poisoned (+5 on the outcomes, +100 mm / +5 °C on the covariates) in every year, season and group
     (rings 4–5 with `CONTROL_ZONES = 1-3`, every ring before the window, the annual composite, the flipping pixels in all their rows,
     the repeated tiles, the outside pixels, Kodihalli). Every number every model writes must be identical in the two runs.
2. **Your rings, years and seasons in every model.** `MODELS_NEEDING_ALL_RINGS` is empty (was M17, M18, M24): M24's spillover gradient
   runs over YOUR rings; M17 / M18 take one point per pixel of the estimation sample (its change post minus pre; v20.57 took every row, so
   a pixel's 8 "nearest neighbours" were its own other years at distance 0), exact k-NN on metres, spdep's formulas (identical in R).
3. **Repeated rows and pixels: dropped and confirmed** — near-duplicate pixels that P00's merge left (footprints overlapping ≥
   `PIXEL_OVERLAP_MIN`), repeated pixel-year-seasons, ring conflicts: code 3 / 4 above, confirmed by SAMPLE INTEGRITY. R's preparation
   drops and confirms the same (`reward_prep.R`).
   **A leak the poison test found in P00 (fourth pass, with cloud gaps): a repeated row's VALUES reached the panel.** When two exports
   hold the same sub-watershed, pixel, year and season, P00 kept the newer row — and then FILLED its missing values from the repeated
   (older) rows it dropped: wherever the newer export had a cloud gap, the older tile's value took its place (on your data: millions of
   values in 2025, "3.6 M missing values filled from the older one" in the v20.12 log). The dropped row was not dropped. Now a repeated
   row is dropped WHOLE — the kept row is taken as it is, its gap stays a gap (Python `_prep_common.resolve_duplicates`, R
   `reward_prep.R`: `DEDUP_FILL_FROM_DUPLICATES = False`); the values not used are counted per variable and reported
   (`cross_file_dedup_conflicts.json`, the PASS B log). `True` is your option (the old fill — for exports SPLIT by variable, one file
   NDVI, another LAI of the same pixel-period). The setting is recorded in `panel_build_settings.json` (R: `panel_build_settings_R.csv`);
   **P00 rebuilds a panel built before v20.58 by itself** (`ACCEPT_PANEL_WITHOUT_PIXEL_MERGE = True` keeps it), and until then every model
   says once that its panel holds values of dropped rows. Also fixed in P00: `NEAR_DUPLICATE_PIXELS`, `PIXEL_SIZE_M`, `DEDUP_PRIORITY`
   and the negative-covariate barrier were set in the PASS B cell — AFTER `P00_Validate_or_Skip` had compared the panel on disk with the
   defaults, so a change there was silently ignored while the old panel was kept (as `PIXEL_OVERLAP_MIN` until v20.55); every panel
   setting now lives in `P00_Settings`.
4. **Every number with its own SE and p — no placeholder, no silent pass.** Each model's headline (`HEADLINE_<outcome>.csv`, the same
   columns in R) says what it is: an EFFECT (estimate, SE, p — never NA: a model without an SE of its own takes the design-based SE of
   the same sample and says so), a TEST (statistic, p), a STATISTIC (Moran's I, its SE, p) or a DIAGNOSTIC (the ICC: descriptive). Each
   SE and p is printed with how it was computed (`se_how`, `p_how`). The p of an effect uses t with (the design's clusters − 1) — the
   same count in R and Python — unless the package gives its own. Fixed: M23's wild bootstrap p and M25's permutation p are never 0
   ((1 + #) / (1 + B)); M32 (etwfe) p from t with G − 1 (etwfe's normal p printed `< 1e-300` on 6 year clusters); M15's headline is the
   MEAN placebo effect with its own SE and p (+ the Bonferroni p of any placebo); M34's breakdown value is exact (was capped at 5) and
   assesses the same effect as M02's headline; M35's cluster SE with the years as clusters (degenerate: the pre years' scores are 0) is
   left out and the design-based SE used, said as such; M20's headline is the TEST (Cochran's Q) with the pooled effect, I², τ² beside it;
   the design-based p is the p of THIS estimate against that SE (`p_estimate_design`). A data gap is written as
   `<model>_<outcome>_DATA_GAP.csv` with its reason (as R). Outcomes that are the same variable in your exports (LSWI = NDMI,
   WSSI = 1 − ESI) are found once per panel and announced at every run (`OUTCOME_IDENTITIES.csv`).
5. **R structured as Python, model by model — the same estimator, the same numbers** (`validate_model_parity.py`: the poison test's
   exports through both pipelines, every model's headline compared). Aligned in this version: M02 (the event study's headline = the
   equal-weight mean of the post-period effects with its SE), M05 (the simple aggregation; analytical SE unless ≥ 6 sub-watersheds),
   M06 (the two-way FE slope on the fund dose), M09 (fixest::sunab's interaction weights), M10 (the triple difference as one
   regression), M11 (synthdid on season series, one fit per cohort × season), M12 (chained first differences), M13 (DIDmultiplegtDYN's
   switchers — v20.57 Python reported a false data gap), M14 (MatchIt's nearest-neighbour rule: logit PS, largest first, caliper 0.2 SD),
   M15, M16 (the design-based pre-trend test with year clusters), M19 (lme4's REML variance components), M20, M21 (a partly treated
   year counted with the share of its treated seasons), M22 (Goodman-Bacon's EXACT weights — they add up to the two-way FE), M23 (Webb
   weights below 12 clusters), M24, M26 (the effect at the covariate's mean), M27 (the design's covariates in the first stage), M30 (the
   group aggregation), M33 (WeightIt's entropy balancing), M34 (HonestDiD on M02's event study — Python's primary is R's own code
   through the bridge), M35, M36–M38 (season series, cross-validated factors), M39–M44 (below), M45 (the elastic-net synthetic control
   on the core-vs-ring series of one season: scikit-learn in Python, glmnet in R with the same penalty path — equal to 1e-9). The
   cluster-robust SE counts the fixed effects not nested in the clusters in its small-sample factor, as fixest and pyfixest do (the
   engine's SE was ~9 % below R's with year clusters).
6. **Python's own implementations (the fall-back when no verified package or R route can run) compute what R's package computes** —
   ported from the package sources and checked number by number (`validate_model_parity.py --engine`): synthdid's Frank-Wolfe weights
   (M11), the exact Goodman-Bacon decomposition (M22), BJS imputation (M27), fixest::sunab (M09), MatchIt (M14), WeightIt ebal (M33),
   the CS group aggregation (M30), and in this pass DRDID's improved doubly robust DiD (M03), qte's changes-in-changes (M04, with R's
   type-1 quantile arithmetic), lme4's REML ICC (M19, exact for two crossed random intercepts), did2s (M28), fixest's exposure model (M29),
   the stacked design (M31) and quantreg's Frisch-Newton quantile regression (M35: when the median regression has several optima —
   a discrete design — the simplex returns a corner and "fn" an interior point; R's route uses "fn", so does the engine now).
   In the third pass: **M36–M38 — fect / gsynth ported**: the initial two-way fit on the untreated cells, fect's EM (interactive fixed
   effects) and soft-impute (matrix completion) with its stopping rule, gsynth's factors from the ring series with each core series'
   loadings from its own pre years, fect's rolling-window cross-validation (its folds drawn by R's OWN generator, replicated: Mersenne-
   Twister, set.seed's scrambling, R's rejection sampling in sample.int), its pooled MSPE, fold SE and 1-SE rule, the matrix-completion
   penalty grid and early stop — one fit per cohort × season as R's route. Checked against fect 2.4.5 / gsynth 1.4.0 on six panels: the
   masks identical, the CV tables to 1e-10, the same r / lambda chosen (r = 0, 1 and 2 among them), the effect to 1e-13. **M39–M44**: the
   engine's learners now estimate on R's long difference (one per pixel × season series, the season-matched outcome, the covariates'
   pre-period means); v20.57's engine differenced each PIXEL's raw outcome with every season mixed (M40 was 2.2 SE from R's). The M43 / M39
   engine forest gives grf's doubly robust ATT (out-of-sample effects) with its SE.
   The v20.57 engines stay beside them as cross-checks (`*_cells`, `*_static`, `*_rows`, `*_anova`, `*_imputation`, `interactive_fe_*`,
   `matrix_completion_*`, `gsc_*`, `ml_cate_*` files).
   In the fourth pass the engine's **standard errors** became R's too, each checked against the R package on the same data (the numbers
   are in `selfcheck.py`): **M36 / M37** fect's bootstrap with R's OWN draws (R's route runs fect with `seed`: doRNG's L'Ecuyer-CMRG streams,
   one per draw; matrix completion refits the FE model in every draw when the real fit kept no factor, fect's `validF`) — every draw to
   1e-14 on six panels; **M38** gsynth's PARAMETRIC bootstrap (simulated prediction errors of a ring series fitted as if treated), not
   fect's nonparametric one — the engine's SE was 2.6 × below R's on the parity panel; **M25** the permutations of R's route (the design's
   unit — the engine permuted whole pixels while its fit's unit was the series: an SD 57 % above R's — and R's `set.seed(12345)` draws);
   **M04** qte's bootstrap draws; **M11** synthdid's placebo SE (each replication re-fits the weights from the given ones with the
   original fit's options, as `synthdid:::placebo_se`; R's draws) — and the Python PRIMARY (diff-diff's SyntheticDiD: its estimate)
   takes the same R-draw SE for each fit (diff-diff's own placebo SE, numpy's draws, stays in `se_diffdiff`: 200 random permutations
   of two generators differ by ~5 %, so R and Python gave different SEs for one estimate); **M13** DIDmultiplegtDYN 2.4.0 ported whole
   (`did_multiplegt_dyn_port`): its panel preparation (a switcher whose last pre-switch year is missing becomes a truncated control), the
   effects, the PLACEBOS (the engine's had the opposite sign and every switcher instead of those whose effect is computed), the average
   total effect and their analytic SEs (the cohort-demeaned influence functions with the package's small-sample factors; clustered on the
   sub-watersheds as R) — checked on ten panels (balanced, up to 20 % missing, 1–3 cohorts, a missing year, clusters) to 1.4e-16; the
   engine had the design-based SE (0.00035 against the package's 0.00115 on the parity panel); **M05 / M30** did's analytical influence function (DRDID's panel estimator, or its repeated-cross-section
   estimator when the series have gaps, and the weights' own influence) — the engine had the design-based SE; **M27** didimputation's
   conservative SE (BJS Theorem 3), its cells by the design's cohort; **M32** etwfe's own specification — the COHORT's effects (the engine
   used the series' effects: the same coefficients on complete series, not on gappy ones: 0.0495 against R's 0.0488 on a test panel with
   2 % gaps) — and emfx's delta-method SE on fixest's clustered covariance.
7. **Machine-learning models (M39–M44): the same estimand and SE rule in R and Python.** One long difference per series (the design's
   unit: pixel × season), the season-matched outcome, pre / post by the design's own split; the headline is the package's own estimate
   and SE — M39 / M43 the causal forest's doubly robust ATT (grf / econml CausalForestDML), M42 the AIPW ATE (grf / econml DRLearner's
   doubly robust scores), M40 DoubleML / LinearDML, M44 bartCause's posterior; M41 the mean of the S, T and X learners' ATEs (R gained the
   X-learner); p normal from the package's asymptotic SE; each unit one draw (said). Forests are different random objects in the two
   languages: they agree within 2 SE and each is held to the known answer. Two alignments in this pass: the Python primary's causal
   forest ATT takes every series' effect cross-fitted out of sample (econml's own out-of-bag effects were ~25 × as dispersed as grf's on
   the parity panel — unchanged with 4,000 trees — and made the SE 4.3 × R's; now 0.000885 against R's 0.000857); R's DoubleML uses the
   Python primary's forests (300 trees, leaves of ≥ 20 series; ranger's defaults put R 1.5–1.8 SE above Python). Fourth pass: the Python
   primary of M40 is the PARTIALLY LINEAR model of R's DoubleML (econml LinearDML with the covariates as controls and DoubleML's score SE);
   it had fitted a linear effect θ(X) and averaged it — another estimator (1.2 SE from R's, its SE 15 % below); on the same folds and forests
   the two packages now give the same estimate and SE to 16 digits.
8. **Every calculation in double precision.** The panel keeps outcomes, covariates and doses as float32 (7 significant digits — your
   exporter writes float32: `harmonise()` = `toFloat()`, so this storage is exact for your exports); they are widened to float64 once
   at load, so no mean, sum or solve runs in float32 (M16's pre-trend F differed from R's by 1.4e-5 from float32 group means alone).
9. **YOUR 98 % RULE — no cap anywhere; the fall-back only beyond 98 %, 5× larger.** Every model loads all its rows into RAM (and the GPU)
   at once while they fit below 98 % of the TOTAL; nothing is ever sampled. Beyond 98 %: M01, M02, M16, M34 and the panel preparation go
   OUT OF CORE (16 below: Dask, Spark or the built-in batches — exact); the ML models, CiC, the quantile regression, lmer and the spatial
   statistics run in batches of units (every unit used once); k-NN blocks 20,000 × 20,000; row groups 2,560,000; the other models stop with
   a readable message naming the per-sub-watershed route (MS01). R the same (`units_that_fit`, `batch_split`, `lib/reward_outofcore.R`).
10. **The known-answer check panels carry YOUR season timing** (three season series per pixel with their own shocks, a Rabi start a
    year before the other seasons): a pre-built route that cannot handle it fails verification and is never used; the verification runs
    on a fixed timing (P00's fund timing made the TWFE route verify at 0.0372 for the true 0.05).
11. **Also fixed:** M07's ground surrogate used rows of another sub-watershed (now the processing set); M25's permutation fits
    overwrote the actual fit's diagnostics (993 messages); the design-counts table and fit info belong to their own estimate only;
    the scenario line printed a placeholder year / folder tag before the fund timing was resolved; R M09 crashed with several cohorts;
    a Windows file path was rewritten on Linux / macOS (`_paths._file_path`); a package result of an EARLIER run was read as this run's
    headline when no package computed it this time (PREBUILT_MODE "off", a failing package) — such a file is now moved to `_superseded/`
    and the headline is this run's; R: fect's / gsynth's cross-validation was unseeded (the chosen number of factors could change from one
    run to the next) — seeded (the Python engine replicates it); fect's series were ordered by the locale's collation and its bootstrap's
    `sample(tr, Ntr, TRUE)` drew ANY series when one treated series was not the first — integer ids, treated first; "fect's default lambda"
    said for what is fect's FE model; R's location rule stopped ("table is type 'integer'") whenever near-duplicate pixels were present;
    Python's data-driven design stopped when the rings lacked a year the core had; P00's ground surrogate stopped with a KeyError when
    no core row of the processed sub-watershed was left; the stacked DiD's cluster rule stopped on a frame without sub-watersheds (V03's
    simulation); an empty sample now names the location rule among its possible causes. Fourth pass: **the R bridge left a copy of the
    model's input frame in the system's temp folder at every call** (and the package checks their results): 6,000 folders / 2.2 GB after the
    validation runs here — on your machine a frame per model and outcome at every run; they are now removed after each call
    (`REWARD_KEEP_TEMP=1` keeps them). **R M04:** qte's bootstrap used the cores only on Linux / macOS, where its draws depend on the NUMBER
    of cores (another machine, another SE; Windows runs it sequentially whatever `cores` says) — sequential everywhere now, with integer
    series ids in (pixel, season) order (the character ids came in the data's order). **R M25:** the units in (pixel, season) order and the
    draws from `set.seed(12345)` in R's default generator, set explicitly. **R M11:** synthdid's series ids are integers (treated first, then
    the rings by sub-watershed and ring) — character ids were sorted by the locale's collation, so the placebo draws picked other series on
    another machine.
12. **Checks:** `validate_location_poison.py`, `validate_model_parity.py` (primary and `--engine`), `validate_requests.py` rules 37–41,
    `selfcheck.py` (`check_v20_58`: + the fect port against R's own numbers, R's generator, the stale-package rule),
    `tests/run_all_tests.R` scenarios F (poison) and G (the batch paths give the all-at-once answer). `validate_design_options.py`'s
    synthetic pixels now sit on a 30 m grid (they were 0.1 m apart: the near-duplicate rule rightly left 97 % of the rows out);
    `validate_prep_notebooks.py` writes its exports inside Artal's real polygons (they lay outside every polygon, which v20.58 leaves out);
    `validate_preprocessing.py` checks both dedup cases (the same pixel in two sub-watersheds' rings kept in both; outside every polygon one).
    Fourth pass: the poison test's exports have CLOUD GAPS (3 % of the own pixels' rows without a value, as real scenes) — the R-vs-Python
    comparison had run on complete series only, where e.g. a series' effect and a cohort's effect give the same ETWFE coefficients;
    `validate_design_options.py` expects Beguru's piece of Artal's files to be Beguru's own data in the POOLED panel (both processed; the
    location decides, not the file) and out in the single panel; `validate_preprocessing.py`, `validate_requests.py` rule 38,
    `selfcheck.py` (`check_v20_58_repeated_rows`) and `tests/run_all_tests.R` C prove a repeated row is dropped whole (and filled only
    with the option); R's poison scenario F has the same cloud gaps.
12b. **Fifth pass — what the R-vs-Python run found on series WITH GAPS (the cloud gaps of the poison test's exports), fixed:**
    - **M05 (Callaway-Sant'Anna), Python's primary:** diff-diff's CallawaySantAnna is `did::att_gt` only on BALANCED series; on series with
      gaps R runs `did::att_gt(allow_unbalanced_panel = TRUE)` (DRDID's repeated-cross-section estimator), which neither of diff-diff's
      options reproduces (0.0505 in Python against R's 0.0488 on the parity exports). The engine IS did's estimator (ported: R's numbers to
      1e-12), so on series with gaps it computes (and says why); on balanced series the verified package, as before. Now IDENTICAL.
    - **M24 (spillover gradient), Python's engine and pyfixest route:** R fits ONE regression — every ring (the core too) × post against the
      farthest ring, `fixest: y ~ i(ring, post, ref = farthest) | unit + period`; Python fitted ring by ring (each ring with the farthest
      only). The two are the same numbers on balanced series only: with gaps the period effects differ (0.000158 against R's 0.000152). Now
      one fit, as R (engine = R to 1e-15; pyfixest's route the same fit), checked against an explicit dummy-variable regression.
    - **The gates themselves:** `validate_all_models.py` printed a failing model and returned 0 — it now fails; `validate_preprocessing.py`
      expected 100 unused values where the test's two exports overlap in TWO seasons (200); `V00`'s schema check and the readiness check
      follow the project's models (below).
13. **YOUR REQUEST — a separate pipeline for the panel and M01, M02, M16, M34, in both languages: `RWD_4Models_v20.58`** (its own bundle:
    `python/` + `R/`; your latest message: M34 — HonestDiD on M02's event study — in place of M04). Filtered from this version: the engines
    are these files byte for byte, the four-model scope is configuration they
    honour — `PIPELINE_MODELS = ("M01", "M02", "M16", "M34")` and `OUTPUT_SUBDIR = "output_4Models"` (`_paths.py`; R: `lib/reward_paths.R`,
    `lib/reward_packages.R`, `00_SETUP.R`). Its P00 / R_P00 prepare the panel for these four only (no `District`, dose, `area_hectare`,
    `first_treat_*`, `LandUse*` columns; no ground linkage, surrogates, dose table, preview, diagnostics, SWS audit; no benchmark means in
    R); packages (Python pyfixest; R fixest, HonestDiD), pre-built route checks, readiness and R's `MODEL_FUN` cover the four; the out-of-core
    layer is there too (16: Dask, Spark, batches — a gate of `validate_4models.py`); everything is written to `<data>\output_4Models`,
    your data paths unchanged. Its own `selfcheck_4models.py` (the project + the engine checks of `selfcheck.py`) and `validate_4models.py`
    (every validator on it). What changed in this bundle for it (a no-op here, where all 45 models are the project): `readiness.py` and
    the gates follow `PIPELINE_MODELS`; the validators find the output folder from `OUTPUT_SUBDIR`; `validate_all_models.py` FAILS when
    a model does not honour a scenario or writes a placeholder / all-NaN / stray file (it printed these and returned 0 — a silent pass);
    `validate_preprocessing.py` says when a project has no P08; R's `00_SETUP.R` installs the project's CRAN packages' dependencies only;
    R's tests guard the checks of models outside the project; R_P00's text says repeated rows are dropped whole (it said "merged").
14. **YOUR REQUEST — RWD_Artal1 dropped**: no code, notebook or path of this version refers to the second Python copy; from now on one
    Python pipeline (RWD_Artal) and one R pipeline (RWDR) — plus the four-model bundle above, filtered from them.
15. **Nothing removed** (every v20.57 function, file and option is here — M01's exact two-pass streaming estimator too, kept as a cross-check; the v20.57 names `fragment_table` / `fragment_mask` return the
    location rule's table and mask). Your paths are unchanged. **Re-run P00 / R_P00 first** (they rebuild the panel: repeated rows are
    now dropped whole — P00 does it by itself because the panel records how it was built), **then the models** (the location rule and the
    aligned estimators change results).
16. **YOUR REQUEST — Dask AND Spark kept as fall-back processing options when the memory limit is exceeded, across all the code and
    pipelines.** Beyond 98 % of the RAM (never before) the run does not stop and is never sampled: it goes OUT OF CORE on the first engine of
    `OUT_OF_CORE` that this machine has — **Dask** (the PyData stack, no Java/Scala; the default), then **Apache Spark** (pyspark,
    local[all cores]; the enterprise engine for heavy SQL-like pipelines; Java 17+), then the **built-in batches** (always there). An engine
    that is not installed is named with the reason; `_paths.OUT_OF_CORE` / R `OUT_OF_CORE` (`lib/reward_paths.R`) set the order.
    - **How it stays exact:** the rows are split into PIXEL PARTITIONS (every row of a pixel — all its years, seasons, rings — in one
      partition, by a hash of the pixel id, streamed from the parquet file). Each partition runs the SAME code as the in-memory path (the
      location rule, gap-filled rows, the window, the seasons, the annual covariate fill, the design columns); only additive facts cross
      partitions (counts, sums, the outcome screen's moments, the integrity facts, the design SE's cells). The two-way fixed-effects
      regressions are solved EXACTLY from the partitions' cross-products — the unit effects removed inside each partition, the period
      effects jointly (Frisch-Waugh-Lovell and the Schur complement of the period block, one reference period per connected component),
      the CR1 sandwich from per-cluster score sums, with the in-memory estimator's own small-sample rule (fixest's in R).
    - **Python** (`_outofcore.py`, `_ooc_models.py`): M01, M02, M16 and M34 (each notebook's CELL 2: `C.run_mode` — in memory below 98 %,
      `C.load_panel_ooc` + `C.ooc_model` beyond; `M01_MODE = "stream"` / `"out_of_core"` forces it); P00's PASS B block by block in pixel
      pieces; the location table and the outcome identities row group by row group. `P12` lists the engines; `dask[distributed]` and
      `pyspark` are in the package list (installed and confirmed like every package). Proof: `validate_out_of_core.py` — known answers
      (one sub-watershed, staggered), your layout, the poisoned layout, P00, the automatic switch, the streaming reports: every file of
      every model IDENTICAL to the in-memory run on Dask, Spark and the batches (15 checks).
    - **R** (`lib/reward_outofcore.R`, `lib/reward_prep_ooc.R`): `run_model_R` hands M01, M02, M16 and M34 to the out-of-core path when
      the sample would not fit (or when the in-memory load runs out of memory); `run_prep` builds the panel BLOCK BY BLOCK (year × season:
      PASS 1 one task per export file, PASS 2 one task per block, a block too large for one task in pixel groups) — the same panel row for
      row; the design from the data and the outcome identities out of core too. The partition tasks run on Dask or Spark through
      `lib/reward_ooc_engine.py` (each task its own R process, `lib/reward_ooc_task.R`; `PYTHON_EXE` names the Python with dask / pyspark),
      or in R itself. `00_SETUP.R` lists the engines. Proof: `tests/run_all_tests.R` scenario H — M01, M02, M16, M34 on Dask, Spark and
      R batches == in memory (487 numbers; the largest difference 2.7e-11, fixest's own convergence), every engine the same numbers, the
      automatic switch, the design from the data, the identities, R_P00 block by block == in memory (the panel row for row, its schema,
      every report) on every engine. (The refactoring of R's in-memory path behind this changed no number: all 45 models on the poison
      layout, 5,171 numbers, identical before and after.)
17. **Found by this pass's checks and fixed:** `_common.treatment_coverage` was defined twice — the second definition (the scenario
    coverage) replaced the first, which `apply_scenario` then called recursively (328 levels deep on a pooled panel): now
    `scenario_coverage`, and the self-check fails on any function defined twice in the engine files; M01's bad-control fits and its
    by-season fits overwrote the canonical fit's diagnostics (`design_counts_<outcome>.csv` held the last season only, the fit info was
    lost) — they now run in their own scope; P00's parallel PASS A / PASS B workers did not receive `ALLOW_NEGATIVE_COVARIATES` /
    `NEGATIVE_COVARIATE_RULE` (a worker applied the default barrier whatever you set) — every setting now travels with the task; M34's
    grid marked the breakdown row "significant" when its lower bound was −2e-18 (the bound is exactly 0 there); the location report's rows
    are in a fixed order (code, group), as the site tagging per file (file name), so the in-memory and out-of-core reports are the same
    files; `diff-diff` is no longer listed as used by M34 (its HonestDiD is the supplementary check of `dd_pipeline.py`; M34's route is R's).
    **YOUR 98 % RULE, M25 (randomisation inference): its batches passed 98 %.** The batch of permutations was sized for 3 n-vectors per
    permutation while the peak was 5 — the demeaning's convergence test made two more n × k temporaries — so a validation run here was
    killed by the system for memory (on your data: millions of rows, the same). The demeaning now tests its convergence in place (the
    same numbers, bit for bit: checked on six panels) and M25 counts 6 n-vectors per permutation, in Python and R (R frees the permuted
    matrix before its products); the permuted estimates do not depend on the batch size (the same draws in the same order: checked, both
    languages).
    **The same rows, the same numbers — in every process (found by the poison test).** Two runs of M31 on identical rows gave SEs 4.5e-8
    apart: pyfixest's demeaning stops at its default tolerance (1e-6), about four passes before convergence, and the order in which
    it visits the fixed effects follows Python's string hashing, which changes from one process to the next (reproduced on one frame
    with PYTHONHASHSEED 0 and 1). Every pyfixest fit of the pipeline now converges to 1e-12 (`PYFIXEST_FIXEF_TOL`, as tight as the
    engine's own 1e-10): the same numbers in every process to ~1e-14, closer to the exact solution, a few more passes only.
    **The engine's demeaning never stops silently short of its tolerance.** It ended after 100 / 200 passes without a word; on a
    design where 3 % of the rows lack a unit key the change was still 1e-5 there. Wherever v20.57 converged nothing changes (the
    same passes, the same numbers, bit for bit); otherwise the passes are extended (up to 10,000) to the tolerance or the column's
    floating-point noise floor, and a demeaning that still does not converge is reported with its last change (CPU and GPU paths).
    **R_P00 in memory and out of core write the same FILE** (found by the four-model bundle's gate): in a project without M07 (no
    benchmark means, so no merge dropped them) the in-memory panel carried R attributes of its build (the dedup counts, the rows
    dropped without an outcome) into the parquet metadata, and the out-of-core blocks carried their own — the data were identical,
    the schema metadata was not. The panel is now written without them in both paths (the counts are in
    `panel_build_settings_R.csv` and the log). The R tests: scenario G's batch checks are skipped with a message where the project
    has no batch model (the four-model bundle stopped with "object 'model' not found"), and the forced batch size is reset after G.
    **R M01 stopped when a covariate cannot be fitted** (found by `tests/selftest.R` from the delivered zip: its Tmax and Tmin are
    constant): the bad-control table's row for that covariate carries a note ("not fitted: ...") and the table could not be bound
    with the others, so M01 — in memory and out of core — gave no result. The table now takes the note (as Python always did); the
    covariate is reported as not fitted, and M01 runs. `tests/selftest.R` says FAIL with the reason when a model gives no estimate.

