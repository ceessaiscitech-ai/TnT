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

# v20.57 — every design option in the DiD models (R as Python); your fund workbook as the timing and the dose; fragments dropped; the 98 % rule; biases found and fixed

**The treatment timing pulled the v20.56 results toward zero.** Your fund workbook dates the releases to the 20 sub-watersheds
from late 2023 to late 2024 (table in 3), while every v20.56 model started all of them in `TREATMENT_YEAR = 2022`: if the works
followed the money, 2022–2023 (and part of 2024) were counted as treated although nothing had been released yet. On a synthetic
panel whose true effect starts in Rabi 2024 (+0.05), the v20.56 timing returns **0.016** (68 % lost), a fixed 2024 returns 0.034,
and the fund timing returns **0.0499**. The fund timing is now the default (3); the other biases the new known-answer test found
are fixed too (6).

1. **Every design option is set and applied in the DiD MODEL — R now as Python.** The panel is built once (R_P00 / P00) and is
   never rebuilt for a design choice; change an option in a model's settings and re-run that model only.
   - The options (both languages, the same names): `DESIGN_MODE`, `TREATMENT_TIMING` (`"fund"` | `"registry"` | `"fixed"`),
     `TREATMENT_YEAR`, `FUND_START_RULE`, `DOSE_VARIABLE`, `CONTROL_RINGS` (Python `CONTROL_ZONES`), `PRE_YEARS`, `POST_YEARS`,
     `SEASONS`, `EXCLUDE_TRANSITION_YEAR`, `UNIT_FE`, `OVERLAP_ROWS`, `FRAGMENT_RULE`, `POOLED_FE`, `EXCLUDE_GAPFILLED`,
     `COVARIATES`. R: in every `R_Mxx` notebook (RStudio `.Rmd` and Jupyter `.ipynb`), `R_RUN_ALL_MODELS`, `R_D01`; defaults in
     `lib/reward_paths.R`. Python: in every model's CELL 1 (and MS01); P00_Settings only saves the defaults a model adopts for an
     option its CELL 1 leaves unset.
   - **What you set is what runs.** In v20.56, `DESIGN_MODE = "recommended"` silently replaced your `CONTROL_RINGS <- 1:3` and
     `PRE_YEARS <- 4` by the data-driven values — that is the `control_rings 1 2 3 4 5` you saw. A value you set is now always used
     as set, in both modes; only an option set to `"data"` is chosen from the data (export breaks, fill years, spillover into inner
     rings — never the effect). `"manual"` makes `"data"` mean every ring / every year.
   - **DESIGN IN EFFECT:** every run prints each option — your setting, the value used, where it came from — and saves it as
     `DESIGN_IN_EFFECT.csv` beside the results. Each option has its own results folder tag, so runs never overwrite each other.
   - R: `model_design()`, `load_panel_R()`, `design_columns()`, `attach_dose_R()` (`lib/reward_design.R`); `run_prep()` no longer
     writes treat / post / did / cohort / event time / unit / period / dose into the panel. Python: `set_scenario()` takes every
     option, `resolve_design()` turns them into the design when the model runs, `build_treatment_columns()` rebuilds the cohorts.
   - Your v20.56 panels keep working (Python and R): nothing has to be rebuilt for v20.57.
   - Found by an independent review of this version and fixed: a model's `OVERLAP_ROWS` was replaced by P00's saved value when CELL 1
     loaded it (now every one of the 15 options set in CELL 1 survives P00's saved defaults — `validate_requests.py` rule 35 proves it);
     MS01 gained `UNIT_FE`, `POOLED_FE`, `EXCLUDE_GAPFILLED`, `COVARIATES`; P00_Settings gained `EXCLUDE_GAPFILLED`.
   - Proof: `validate_design_options.py` runs 27 option settings on 4 panels through BOTH pipelines — the same rows, the same
     treat / post / did / cohort / event time / dose, the same unit, period and cluster partitions, each option doing exactly what
     it says, the panel file byte-identical afterwards (1,545 checks, CLEAN). R test scenario E does the same in R alone.
2. **Fragments of other sub-watersheds are dropped (your rule), treated and control rows alike.** Every row is coded per export
   file: 0 = its file's own sub-watershed (the one holding more than half of the file's rows inside a polygon), 1 = inside another
   sub-watershed's polygon, 2 = outside every polygon with another sub-watershed's id; at the model stage 3 = a sub-watershed with
   fewer rows than `FRAGMENT_MIN_SHARE` (5 %) of the largest one. `FRAGMENT_RULE = "drop"` (default) estimates on code 0 only;
   `"keep"` keeps them (tag `_keepFragments`). Python PASS A (`_fragments.py`) and R `run_prep()` write the `fragment` column; a
   v20.56 panel without it gets the same rule from the export ids. `FRAGMENTS_TABLE.json` / the DESIGN IN EFFECT say what was left out.
3. **Your fund workbook = each sub-watershed's treatment timing and dose** (`_fund.py`, `lib/reward_fund.R`, identical results).
   - The cumulative progress per sub-watershed (80 % name rule against your crosswalk), downward revisions corrected (a later,
     lower report replaces the earlier ones), the start **back-cast** before the file's first month at the sub-watershed's own
     release rate (its first 12 months), and the first treated **season** = the season after the start month (no anticipation):
     | first treated season | sub-watersheds (start month) |
     |---|---|
     | Zaid 2024 | Murlapura (2023-10), Jantapur (2024-01), Kodihalli (2024-02) |
     | Kharif 2024 | Hunasehadagi (2024-03), Haligeri, Jammapur, Nilgund, Pashapur (2024-04) |
     | Rabi 2024 | Doddenahalli (2024-06), Artal, Honnutagi, Koranahalli, Mallainupura (2024-07), Chittharagi, Gummlapalli, Maidalakere (2024-08), Beguru (2024-09) |
     | Zaid 2025 | Chhatrakodihalli, Kyatagondanahalli, Sirur (2024-10) |
     Each row's cohort is the first Year its own series is treated: a Rabi start treats Rabi of that year and every other season
     (and the annual composite) from the next — staggered, season-level, per sub-watershed.
   - **Dose** of a season = the amount released by the end of the previous season ÷ the treatment area (the file's area = the
     core area) — `dose_intensity_per_ha`; also `dose_amount_sws`, `dose_share_of_target` (`DOSE_VARIABLE`). 0 on the rings and
     before the start; the back-cast seasons are flagged (`dose_estimated`; `FUND_DOSE_BEFORE_FILE = "missing"` leaves them out).
   - Options: `FUND_START_RULE = "backcast"` (default) | `"share"` (the month the amount reaches `FUND_START_SHARE` = 10 % of the
     target) | `"file_start"` (the file's first month: a lower bound). `TREATMENT_TIMING = "registry"` (sites.csv) or `"fixed"`
     (`TREATMENT_YEAR` for all) remain; a sub-watershed the file does not date falls back to its registry year (announced); a run
     without the workbook says so in its folder name (`_fundMissing`).
   - Reports: `FUND_TIMING.csv`, `FUND_SEASON_DOSE.csv`, `FUND_MONTHLY.csv`, `FUND_TIMING_AND_DOSE.md` (P00 STEP 4, R_P00).
   - M06 (dose response) now uses this dose; in v20.56 the rings got the core's district dose, so with one sub-watershed the dose
     effect could not be separated from the year effects. The v20.56 staggered models (M05, M09, M27 …) had also taken the fund
     file's 50 % milestone as the cohort instead of the treatment year — the cohorts now always come from the timing in force.
4. **The 98 % rule: no GPU / RAM / CPU cap anywhere until 98 % of the TOTAL; GPU or RAM first.**
   - Python: `_hardware.MEMORY_CEILING = 0.98` (RAM and GPU memory; was 0.95), `RESERVE_CORES = 0`, `MEMORY_HEADROOM = 1.0`
     (was 0.90 of the free RAM), the GPU capacity fall-back at 98 % (was 60 %), the VRAM estimate at 98 % (was 70 %), joblib on
     every core (was cores − 1), PASS A's fall-back on every core; the fixed sample sizes are gone — ML forests, k-NN spatial
     weights (every notebook's `MAX_SPATIAL_N = None`), the near-duplicate sample: every row that fits below 98 % of the RAM
     (`rows_that_fit`, `spatial_capacity`); a number set by hand still caps it.
   - R: `MEMORY_CEILING <- 0.98`, `units_that_fit()`; `N_MAX_UNITS`, `N_MAX_PIXELS_MIXED`, `N_MAX_ML`, `N_MAX_SPATIAL` are `NULL`
     (no fixed sample for the CiC bootstrap, lme4, quantile regression, ML, spatial weights); `00_SETUP.R` installs on every core.
   - Regressions were already never chunked (v20.56); the GPU is used first whenever the rows fit below 98 % of its memory.
   - The panel reports (P06 / P07, the manifest) count pixel persistence over EVERY pixel (was a 1 % sample above 2,000,000 rows;
     now vectorised), the grid-spacing check uses every pixel, the ML models save every pixel's CATE (was the first 50,000 rows),
     and the notebooks no longer suggest `MAX_ROWS = 2_000_000` (a number would thin the panel).
5. **R**: `COVARIATES <- "all"` reached no model (`covs_in()` looked for a column named "all") — fixed, the models use the design's
   covariates; the M27 R route (didimputation) never verified (ids of ~10^6 made its sparse design singular — in v20.56 too) —
   consecutive ids, verified (0.0498 for 0.05); the R test suite covers the model-stage design (scenarios A, B, D updated, E new).
6. **Biases found by the new known-answer test** (`validate_known_answers.py`: every Python model on a one-sub-watershed and an
   eight-sub-watershed staggered panel with a known +0.05; 82 PASS, 6 without an answer on such data, 2 right data gaps):
   - Fixed earlier in this version: M03 (0.016), M05 / M09 (0.122), M11 (−0.002), M15, M21, M36 / M37 / M38 (no result), M45
     (0.002) — all now within ±0.01–0.02 of the truth; the scenario's per-site years (JSON keys) were ignored by every notebook.
   - M04 changes-in-changes: 0.061 → 0.054 — one pooled 2×2 of every season and year (mixtures) replaced by comparable cells
     (sub-watershed × season × pre year × post year), and the counterfactual only where the treated value lies inside the control
     rings' range (CiC is not identified outside it; the share is reported). M35: the headline is the quantile DiD on the same
     cells (0.048–0.051 at every quantile) — the v20.56 CiC quantiles showed a spurious 0.049 → 0.067 "larger effect on greener
     pixels"; the CiC quantile effects stay beside it; heterogeneity is claimed only beyond the cell-to-cell noise.
   - M45: 0.064 → 0.050 on the staggered panel (each core series fitted on same-season rings net of their common year effect).
   - M24 spillover: clustered as every other model (v20.56: on pixels) and claimed only when significant (v20.56 called any decay
     a spillover).
   - M01: a **bad-control check** (Python and R) — each covariate as the outcome of the same DiD; a covariate that moves with the
     treatment (e.g. land-SURFACE temperature, MODIS LST, the exporter's fall-back when ERA5-Land air temperature is missing) is
     flagged with the estimate without covariates.
   - The design-based SE leaves out partly treated years; a single post year no longer breaks it (both languages).
   - M23: pyfixest's wild bootstrap expands the absorbed fixed effects into dense dummies (measured: 1.3 GB for 20,000 rows and
     2,000 units; for your millions of pixel × season units far beyond any RAM — the kernel is killed). The package is now used
     only when that fits below 98 % of the RAM; otherwise the engine's exact replicate-by-replicate bootstrap is the result.
7. Checks: `selfcheck.py` (`check_v20_57`; older checks moved to the model-stage design; 160 checks), `validate_requests.py` rules
   32–36 (and 2, 15, 17, 21, 24, 25, 30 updated), `validate_design_options.py` and `validate_known_answers.py` (new),
   `validate_r_parity.py` (compares the resolved windows), R `tests/run_all_tests.R` (A, B, C, D, E).
8. Bundles `RWD_Artal_v20.57`, `RWD_Artal1_v20.57`, `RWDR_v20.57`; engine 20.57; data rules 20.57 (the package input copies are
   rebuilt on their own). Your paths are unchanged.

# v20.56 — no chunking: every regression on ALL rows in RAM + GPU at once; R packages pre-built first, Rtools only when unavoidable

1. **Your rule: no chunking.** Every regression model loads **all** its rows into RAM — and the GPU demeaner takes the whole
   matrix at once below the 95 % VRAM ceiling (CPU RAM when it does not fit there) — and runs the regression once.
   Nothing is streamed, thinned or sampled for a regression:
   - `NO_CHUNKING = True`, `MEMORY_POLICY = "raise"` (`_common.py`): when the rows do not fit below the 95 % RAM ceiling the run
     stops with a readable message instead of thinning the panel.
   - M01: `M01_MODE = "memory"` (was `"auto"`, which could switch to the v17.2 two-pass "stream" estimator); `"auto"` now always
     resolves to `memory`; `"stream"` is refused with your rule named. The streaming estimator stays in the engine only as
     the validation scripts' independent cross-check of the in-RAM estimate; no model notebook uses it.
   - `MAX_ROWS = None` in every notebook is documented as your rule (an int would thin the panel).
   - Reading the parquet file row group by row group when the whole file does not fit is only how the rows are *read*; every
     kept row is in RAM before any estimate — the progress label and the message now say so.
   - Checks: self-check `check_v20_56`; `validate_requests.py` rule 30 runs a panel through loader and estimator and confirms
     180 of 180 rows estimated.
   - The R pipeline never chunked: `fixest` / the fall-back engine take the whole `data.table`.
   - Unchanged, as you set them last time: the ML / spatial / mixed-model **sampling** limits (10×) apply to the models that
     cannot take the whole pixel panel (forests, k-NN weights, lme4, quantile regression) — not to the DiD regressions.
2. **Your run: "Rtools is required to build R packages but is not currently installed" and "package 'upd' is not available".**
   - R chose a newer *source* version over the CRAN binary and asked to compile it. That choice is now switched off inside the
     install chain (`options(install.packages.compile.from.source = "never")`): on Windows / macOS the **pre-built binary is
     installed first, always**; a source build is attempted only when **no** binary exists for your R version **and** it can be
     built here — a pure-R package (HonestDiD, synthdid, ritest) needs no tools; a package with compiled code needs Rtools,
     which the chain names with its link (https://cran.r-project.org/bin/windows/Rtools/) — the models that use it fall back
     to the engine, nothing stops.
   - `00_SETUP.R` no longer updates already-installed packages by itself (`UPDATE_PACKAGES <- FALSE`; an update is what pulls a
     source build); it still installs missing dependencies (v20.51: MatchIt's `chk`). Every `install.packages()` call is
     `utils::install.packages(pkgs = <names>, ...)` — explicit, so a masked `install.packages` cannot read the variable name
     (`upd`) as a package name; the variable is gone as well.
   - The set-up and every `confirm_packages()` line now say whether Rtools is present.
3. Bundles `RWD_Artal_v20.56`, `RWD_Artal1_v20.56`, `RWDR_v20.56`; engine 20.56; data rules unchanged (20.55).

# v20.55 — seasons AND years in both pipelines; R structures the data exactly as Python; packages first, confirmed at every run; your options

**Why your results were small and insignificant (the code part of it).** Both pipelines' *recommended design* (v20.45)
replaced your `SEASONS = "all"` with `"yearly"` whenever one season was missing in some year — and your exports have
such gaps. So every model estimated on the annual composite alone: no Kharif / Rabi / Zaid variation entered any model,
only 10 annual cells per pixel, and the design-based inference had 10 year-draws to work with. That override is gone
(1 below). The parity harness (2) then found four further defects, in the code shared by both pipelines (5). What the
data themselves show (`docs/FINAL_EFFECT_REPORT_Artal.md`) is unchanged: the annual composite carries almost no
core-vs-ring difference; the Rabi divergence in 2025 is where the effect is visible.

1. **Yearly and seasonal data together — the setting is yours, in both languages.**
   - `SEASONS = "all"` (default, your rule) estimates on the annual composite **and** Kharif / Rabi / Zaid rows, with one fixed
     effect per pixel × season series and one per year × season (the year AND the season variation). Missing season-years
     are simply absent — the estimators handle an unbalanced panel exactly (4).
   - Your option: `"seasonal"` (the three seasons only), `"yearly"` (the annual composite only), one or several named seasons
     (`"Rabi"`, `"Kharif+Rabi"`; R: `c("Kharif", "Rabi")`), `"auto"` (the data decide, as until v20.54).
   - Where: Python `P00_Settings` → STEP 8; R `lib/reward_paths.R` / `R_P00`. The recommended design still chooses the years
     and the control rings from the data, and now **says** what it would have chosen for the seasons, without changing yours.
   - Inference: beside the year-level design-based SE, every result now carries the **year × season (period-level) draws**
     (`se_design_period`, `p_design_period`) — the seasonal variation you asked for is in the honest benchmark too.
2. **R structures the data exactly as Python** — `lib/reward_prep.R` rewritten as a step-by-step port of `_prep_common`:
   every export format (csv / csv.gz / parquet / xlsx / xlsm / xls), the strict-then-loose file-name parsing, column
   harmonisation (canonical names, aliases, ≥ 0.8 similarity), `buff_km` recoded from text ("1 km"), the zero rule, rows
   without any outcome dropped, negative covariates (fill values missing first, then floored, or kept with
   `ALLOW_NEGATIVE_COVARIATES`), the same pixel ids (lat / lon rounded to 1e-5), the shapefile overlay with the same
   codes, the near-duplicate pixel merge (3 × 3 spatial bins, footprint overlap, greedy chain-free canonical map, newer
   export wins), the cross-file duplicate rule (newer file, then fewer missing core outcomes, then more observations;
   gaps filled from the dropped rows), the annual composite's weather filled from the same pixel-year's seasonal mean,
   and — new in both — the pooled **sub-watershed × year × season** period fixed effect (`POOLED_FE`).
   - **Proof:** `validate_r_parity.py` (new, needs R). It writes synthetic exports with every awkward case (two sub-watersheds,
     one named only by its folder; yearly rows without weather; "N km" rings; Zaid only in some years, in .xlsx / .parquet /
     a file with the keys in its columns; a 2025 grid shifted 3 m; a year-season exported twice with a newer file; masked
     zeros; −9999 / −10 °C / −2.5 fill values; GapFilled / Coverage rows; NDVI missing in 2 % of cells), runs P00 as you
     do and R's `run_prep(); prepare_design()`, and compares: the design (pre / post years, control rings, seasons), the
     7,800-row panel value by value, the NDVI and EVI estimation samples row by row, the rows every season mode and
     `OVERLAP_ROWS` select, the unbalanced-panel rule, and M01 (Python engine 0.05109550 vs R fixest 0.05109549).
     **CLEAN: 14 checks.** Run it after any change to either pipeline; an R result and a Python result are comparable
     only while it prints CLEAN.
3. **Packages first — installed when missing, confirmed at every run.**
   - Python: a missing estimator package (pyfixest, wildboottest, diff-diff, econml, doubleml, esda, libpysal) is installed
     the moment a step needs it — **pre-built wheel** first (`pip --prefer-binary`), then the **source distribution** built
     locally, then a local wheel folder (`python_prebuilt/wheels` or `REWARD_WHEELS`, for an offline machine) — then
     verified on the known answer before it computes (`_use_prebuilt`). P00's P12 installs and confirms everything up front
     (`confirm_packages()` → `results/PACKAGE_STATUS.csv`: package, version, route, models it serves); every model notebook
     prints `Python packages: N of N installed` when the engine loads. `AUTO_INSTALL_PACKAGES` (P00_Settings
     `INSTALL_PACKAGES`) switches the installing off — reporting stays.
   - R: one chain for set-up time, run time and the Python bridge — `lib/reward_packages.R`: CRAN (a **pre-built binary**
     where the platform has one, else the **source**, compiled) → the author's r-universe → GitHub → the GitHub source
     archive (no API rate limit) → a mirror of the same code (synthdid). `need()` installs a missing package the first time a
     model calls it (`AUTO_INSTALL_PACKAGES` in `reward_paths.R`); `00_SETUP.R` uses the same functions; **every R notebook's
     setup chunk** now prints `R packages: 40 of 40 installed` (→ `results/PACKAGE_STATUS_R.csv`).
4. **Unbalanced panel.** A missing row / pixel-period leaves **only the estimation that needs it**: `load_panel` (Python) and
   `load_panel_R` (R) remove a row for one outcome's missing value or missing covariate only from that outcome's sample;
   the pixel's other periods, and the other outcomes' samples, keep it. Both now say how many rows leave *this*
   estimation. Nothing is balanced or dropped panel-wide (test: 115 NDVI cells missing → all 84 pixels concerned keep their
   other periods in the NDVI sample; the EVI sample keeps every cell — identical in Python and R). The estimators that
   need a balanced or two-period structure build it themselves and say so (M03 / M04 units seen before and after; M45).
5. **Defects the parity harness found — fixed in both pipelines:**
   - **Near-duplicate merge was many-to-one.** `canonical_pixel_map` sliced its adjacency with `searchsorted` on rows sorted
     by priority, not by value: on a shifted export grid 121 pixels were merged onto ONE canonical pixel (the merged rows
     then collided as duplicates and were thinned). Now every canonical pixel receives exactly the pixels that overlap
     it (one-to-one on a shifted grid). Re-run P00 if your panel has more than one export grid.
   - **Any common shock ended the post window.** A year in which both groups jumped > 3× the median year-to-year change was an
     "export break", and the post period stopped before it — a drought or a wet year does exactly that and the year × season
     fixed effects absorb it. Such a year is now reported as a **common shock** (kept); an export break is a lost pixel
     history (linkage < 0.9) or a jump that also **re-scales** the cross-pixel spread (> 50 %, both groups) and persists into
     the next year. Same rule in R.
   - **Pixel-history linkage** counted pixels with a finite NDVI (a cloudy year looked like a lost history) and was computed per
     parquet row group (`Season.min()` of each block — layout-dependent). It now counts pixels present, over the whole file.
   - **P00 PASS B overrode `PIXEL_OVERLAP_MIN`** (0.65 in P00_Settings → 0.80 in the cell): Python linked 0 pixel pairs where R
     linked 168. The setting decides (your open decision on the threshold stands).
   - R: the recommended design applied an **empty** post window (the outcome screen then stopped); like P00 it now keeps your
     windows when the data give no usable one, and says so. `scenario_tag` no longer fails on an empty window.
   - R read a "1 km" ring as missing, skipped an export whose keys are only inside the file, averaged duplicate rows instead of
     applying the newer-file rule, and linked shifted grids by nearest neighbour only — all replaced by the Python rules (2).
6. **Your options (both languages):** `OVERLAP_ROWS = "drop" | "keep"` — in a pooled panel the control rows of a pixel TREATED
   in another sub-watershed (and rows repeating a pixel already in the sample) are dropped by default (they pull every DiD
   toward zero); `"keep"` keeps them and tags the results `_keepOverlap`. `POOLED_FE = "site_period" | "period"` — the pooled
   period fixed effect (honoured; until v20.54 a pooled run always used site × period). Both in `P00_Settings` and
   `reward_paths.R` / `R_P00`.
7. **Data-volume limits × 10** (your rule): Python ML 400,000 → 4,000,000 rows, spatial weights 300,000 → 3,000,000, every
   notebook's k-NN cap 200,000 → 2,000,000, the near-duplicate diagnostic sample 200,000 → 2,000,000; R `N_MAX_UNITS`
   200,000 → 2,000,000, `N_MAX_PIXELS_MIXED` 40,000 → 400,000, `N_MAX_ML` 400,000 → 4,000,000, spatial 3,000,000. Your 95 %
   rule stays the only other limit.
8. **Small fixes:** P00's dry run read an .xlsx export as parquet ("Parquet magic bytes not found"); "66 file errors" in PASS A
   were notes that absent outcome columns were filled NaN — counted separately now; M02's headline SE by the delta method
   when the clusters are sub-watersheds; pandas 3 warnings in `recommend_design`.
9. **Tests:** self-check 148 (new `check_v20_55`: season modes, the overlap option on a pooled frame, the one-to-one merge, the
   common-shock rule, the period-level SE, the package chain, the 10× limits, the R mirrors); `validate_requests.py` 25 PASS
   (six new rules: seasons + years, R == Python, packages, overlap option, unbalanced panel, defects fixed); R
   `run_all_tests.R` scenario **D** (SEASONS kept against the data-driven choice, the common shock kept, the shifted grid
   merged one-to-one, season modes, the unbalanced panel, the annual fill, OVERLAP_ROWS, POOLED_FE, M01 on seasons + years,
   the package confirmation); `validate_r_parity.py` CLEAN.

## Your decisions (nothing changed)
- **PIXEL_OVERLAP_MIN = 0.65; your rule says > 80 %** (see v20.54). P00 now honours the setting; set 0.80 in `P00_Settings`
  and `reward_paths.R` to follow the rule exactly.
- **Optional runners** `MS01` / `R_RUN_ALL_MODELS` exist; your rule is to run each model yourself.
- **The p-values are what the data give.** With seasons and years in the models the samples are 3–4× larger and the
  design-based draws are year × season cells, so the inference has more to work with — but the effect itself is decided by
  your exports, not by the code (`docs/FINAL_EFFECT_REPORT_Artal.md`).

# v20.54 — regression audit against every earlier version: nothing lost; the defects it found, fixed

**How it was checked.** Your share link could not be opened here (the page loads its content only in a signed-in browser),
so the audit used everything else: the v20.47 bundle you uploaded, every later bundle (v20.50–v20.53), this changelog from
v17.11, your stated rules and your run logs.
- **Nothing is missing.** All 371 files of v20.47 exist in the three projects (213 identical, 158 changed as documented);
  Python functions 672 → 739, none removed, no parameter removed; settings 301 → 311, none removed; R functions 94 → 120,
  none removed. Each release v20.50 → v20.53 compared with the next: no file, function or parameter lost.
- **The old tests on the new code.** v20.47's own test files, run unchanged: self-check 132 pass and 6 expected differences
  (each one a change you asked for or a documented fix); validate_preprocessing, validate_inference, validate_all_models
  (37 estimate, 8 documented data gaps) and V00 (28/28) pass. On v20.54 the old preprocessing test differs in one place,
  by design (fix 6: the −10 °C clamp stays missing with the barrier off); the R test gives 50 PASS, 5 data gaps, 0 FAIL, and the R
  self-test PASS. Two v20.47 validation scripts (V00b's old copy, V00c) failed on v20.47 itself: they were outdated.
- **Your rules, one executable check each:** `validate_requests.py` (new). 20 PASS, 2 DECIDE (below), 1 NOT HERE (the A40
  check needs a GPU; on your machine it runs the GPU self-test), 0 FAIL.

## Defects found and fixed
1. **Pre-built package routes could estimate on the wrong rows.** The table each package reads (`estimator_files\package_input\`)
   was reused whenever a file of that name existed.
   - After P00 rebuilt the panel, the package routes kept the OLD panel's rows. The engine cross-check used the new panel.
   - In per-site runs (MS01 / `run_sites`), every site after the first with the same design read the FIRST site's rows.
   - Now the file name carries the sites, and the file records the panel it was cut from. It is rebuilt when the panel changed.
     If the rebuild cannot run (no panel), the model hands over to the engine; an old table is never used.
   - Test: site 2 now reads site 2's rows; a rebuilt panel (NDVI + 1) moves the input by exactly +1.000.
   - **Re-run the models whose result came from a package** (the `..._PACKAGE_...csv` files).
2. **Your 95 % rule did not cover package copies.** v20.52 had switched this check off. A package copy larger than the RAM left
   below 95 % was attempted and could kill the kernel. Such a copy now goes to the engine, with a [WARNING] line saying so;
   otherwise the package is used first.
3. **`DATA_RULES_VERSION`** was not raised when v20.52 changed a data rule (rows with Coverage ≤ 0 left out). Inputs cut under
   the older rules were reused. It is now 20.54.
4. **`MEMORY_SHARE` (Python `_paths.py`, R `reward_paths.R`) had no effect** since v20.52. It works again. The default 1.0 caps nothing
   (an unreadable value counts as 1.0 in both languages).
5. **M19's ICC was biased under pandas 2** when the sub-watershed column had categories not in the sample. The loader keeps every
   category of the file, so empty sub-watersheds were counted as groups. Test with 2 of 20: 0.281 instead of 0.317.
   - Fixed: `observed=True`, as pandas 3 does by default.
   - The same grouping made M11 return NaN and M45 stop with an error when a sub-watershed of the file was not in the sample
     (for example a per-site run clustered on sub-watersheds). Both now estimate: re-run M11 / M45 results that were NaN or failed.
   - The pandas warning is gone from M20, M36–M38, M43 and the BJS / Gardner helper (their values are unchanged; M43's table
     by sub-watershed loses its empty rows).
6. **The covariate rules in R now match Python:**
   - An exported exact 0 of Rain / Tmax / Tmean / Tmin is a masked cell (missing). R had kept it as a real 0.
   - R now has the switch `ALLOW_NEGATIVE_COVARIATES` to remove the negative barrier. Python already had it.
   - In both languages, with the barrier off, fill values (−9999) and the −10 °C clamp stay missing. Before, Python kept them
     as real values.
   - Re-run `R_P00`.
7. **Validation scripts:**
   - V00's path check D7 failed on Windows in every run since v20.50: it still expected `...\TST_Artal\output`. It now checks
     the paths set in `_paths.py`, on every system.
   - V00c was outdated (v17 folder name, DiD columns from PASS A). It now checks that the process pool gives the same result
     as a single process.
   - The self-check also tests that workers are sized by the 95 % rule.
   - Once P00's P12 had verified the routes, the self-check's M11 test ran diff-diff on your real panel, and then failed on the
     reason text. Its M13 test wrote into your results folder. Both now run in a scratch folder with an empty
     verification record.
8. **Warnings in your logs:**
   - pyfixest's raw "singleton fixed effects dropped" warning is now one explained line in `pf_pipeline.py` too (offered in
     v20.50, not done until now).
   - R: "NAs introduced by coercion" from M09 / M28 no longer appears.
   - M04: qte 2.0 printed "CiC() is deprecated" and "covariates appear to vary over time". Neither applies here, so both are
     silenced. If a later qte removes CiC(), its successor cic() is used.
   - M06: never-treated units now get dose 0 before diff-diff is called, as diff-diff did itself (with a warning on every
     call).
   - Results are unchanged.
9. **Paths off Windows:**
   - `D:\LKT\RWD_Artal\data` and `D:\LKT\RWD_Artal1\data` both mapped to `~/REWARD_data/data`. They now keep their project folder
     (`~/REWARD_data/RWD_Artal/data`; a test machine's data move there).
   - R created a folder literally named `D:` inside the project. Windows is unchanged.
10. **Documentation and setup:**
    - The requests ledger had lost its v20.48 table (and in RWDR the v20.49 one too). It is complete again, with the current
      status of every request.
    - The separate changelog copy lacked v20.53.
    - The R_P00 header and the RWDR README still described the old folder and the automatic split.
    - The machine plan said "reserve 1" core although none is reserved.
    - `00_SETUP.R`: synthdid's r-universe fallback pointed at a universe that does not exist. A last-resort source is added
      (it reproduces the paper's Proposition 99 estimate, −15.60). P12 still verifies it before use.
    - The R model line now also shows the model's own p-value. For M16 that is the pre-trend test; p(design) is the DiD effect's.
    - The package-input file name now reads the sites the way the loader does (an int, a list, a numpy array ...), so the same
      site written differently is the same file.
    - `validate_requests.py` and the self-check run the code for these rules instead of searching its text (per-site runs,
      package hand-over, the 95 % rule, no caps, history-filled rows).
    - `pf_pipeline.py`'s covariate defaults still listed LandUse. It is now your four weather covariates. No result changed: package
      inputs never carried LandUse.

## Your decisions (nothing changed)
- **PIXEL_OVERLAP_MIN = 0.65; your rule says > 80 %.** It was lowered in v20.38 because the 2025 exports sit on a grid shifted
  about 3 m: at 0.80, 20 % of the treated post-period pixels had no pre-period history. Set 0.80 in `_prep_common.py` and
  `reward_paths.R` to follow the rule exactly; P00 / R_P00 then rebuild the panel.
- **Optional runners.** `MS01` (one model per site, then pooled) and RWDR's `R_RUN_ALL_MODELS` (several models in a row) exist.
  Your rule is to run each model yourself. They do nothing unless opened; keep or delete them.

# v20.53 — the final effect report; single-season designs; the 95 % rule restored as the only limit

- **Your diagnostics, read** (`docs/FINAL_EFFECT_REPORT_Artal.md`):
  - The annual composite shows no core-vs-ring difference in any year: at most 0.0006 NDVI, raw DiD −0.0002. That is why the estimate is ~0.
  - The one strong divergence is Rabi 2025: core 0.354 vs ring 5 0.283, 22 pre-period SDs.
  - The Kharif composites (core mean 0.10, as low as 0.02) are cloud / haze contaminated.
- **Single-season designs (R):** `SEASONS <- "Rabi"` (or "Kharif", "Zaid", several). Before, only "all" or "yearly" was possible, and an effect that exists in one season was averaged away.
  - Test with a planted Rabi-only effect: 0.0056 with the Rabi design (truth 0.006), −0.0002 with the annual design.
- **R_D01:**
  - Flags an optical index whose sub-watershed mean falls below 0.10 in a season: clouds, haze or water, not crops.
  - Labels pixels without a ring "outside rings" (was NA).
- **Python, your 95 % rule is again the only limit on workers:**
  - Every core is used; workers are reduced only when that many would not fit below 95 % of the RAM.
  - v20.52 had removed this check as well, which could exhaust memory and kill the kernel with 64 workers holding a block each.
  - Without psutil there is no limit at all (before: one worker).
- **Python, one export with two alias columns of one name** (e.g. UID and pixel_uid) is resolved per file.
  - v20.52 did it inside the spelling map, which broke the case-insensitive spelling test (V00 A3).
  - V00 passes 28/28 again.
- **Stress test:** exports whose column types all differ (text land use, blank NDVI, 64-bit ids, "1 km" rings, integer rain, text sensor codes) give the identical panel on disk, in RAM and with a process pool.

# v20.52 — why the effects are small: two code causes fixed, the data causes measured on your panel; PASS A crash fixed; no caps

## Code causes that pulled R's estimates toward zero (fixed)
- **R estimated on rows the exporter FILLED from history.** For a recent window the exporter blends the unpublished tail
  with the 3-year historical mean (`GapFilled = 1`) and projects a window with no observation at all (`Coverage = 0`). In
  the post years those values are largely pre-treatment history: they pull the post period back toward the pre period and
  the DiD toward zero. Python has left them out since v20.35 — R kept them. R now leaves them out too (and says how many,
  and how many in the post years). Your NDVI / EVI / SAVI / LAI / NDRE results from R were affected: re-run them.
- **M34 (HonestDiD) was built on a covariance that is not valid with 1–5 sub-watersheds** (clustered on years: each
  coefficient rests on one year — the M16 problem of v20.49). It now uses the design covariance (independent years, the
  spread of the pre-period leads). "CI is open at one of the endpoints" is no longer repeated: an interval that reaches
  the grid is written as -Inf / Inf (the data cannot bound it), counted once, never as the grid edge.

## The data causes — measured on YOUR panel by the new `R_D01_Effect_Diagnostics` (RStudio and Jupyter)
Nine checks, every number from your panel, verdict in `results/DIAGNOSTICS/EFFECT_DIAGNOSTICS.md`: history-filled
rows by year and group; the optical source (the exporter falls back to MODIS 500 m where Sentinel-2 / Landsat have no
clear view — a 500 m value spans the core boundary and ring 1); the resolution of each outcome (distinct values per 100
pixels — MODIS LAI, LST-based TCI, ET-based ESI and the drought indices are 500–5000 m products); the ring gradient
(ring 1 moving with the core = spillover, a diluted estimate); the effect by season (works that store water act in Rabi /
Zaid — the annual composite your design uses dilutes them); the tails (an effect on the treated fields only, averaged
away over the whole sub-watershed); land use; the fund dose; the scale of each outcome by year. Tested on synthetic data
with each problem planted: all recovered (a Rabi-only effect on 12 % of the core, 26 % history-filled post rows, a 500 m
product, farm-only effect).

## PASS A: "Integer value 6234264803062266584 not in range: 0 to 9007199254740992" (your run, file 1,202 of 2,876)
One export stored its point ids (UID) as 64-bit integers, another — with a gap — as float64; writing both into one shard
failed (a float64 cannot hold that integer exactly). The exports' UIDs were never used (the pixel id comes from the
coordinates) and were dropped from the panel anyway: they are now dropped as soon as a file is processed, and a column
whose type cannot be converted EXACTLY opens a new part of the block (nothing is rounded). Two export columns that
are aliases of one name (UID and pixel_uid) no longer collide. Test: both UID types plus an alias duplicate, on disk and in RAM
-> identical panels.

## No caps (your instruction)
Every pipeline uses the whole machine even when several run: the automatic split is OFF (`AUTO_SPLIT = TRUE` restores
it); every logical core for PASS A / PASS B workers, the ML routes and permutation inference; a pre-built package is
always used first; R: all cores for data.table / fixest, fect / gsynth (were 8 of 64), ranger. The only switch left is your
own 95 % rule: above 95 % RAM the preparation streams through disk instead of crashing.

# v20.51 (RWDR) — your panel reads your data after a test; the fund file is read; M14's missing dependency

## "Only the sample files are read" (your log)
`tests/selftest.R` (and `run_all_tests.R`, when Sourced) point the R session at a synthetic folder through the environment
variable `REWARD_R_ROOT` — and left it set. Run afterwards in the same session, `R_P00` read the test's 10 sample files
(`data root: ...\Temp\...\reward_selftest`) instead of `D:\LKT\RWDR\data` (1,149 files). Both tests now restore the
session's variables and reload your paths when they end — also after an error — and say so:
`[INFO] test finished -- this R session points at your data again: D:/LKT/RWDR/data`. If the variable is ever set outside a
test, the notebook says `[WARNING] data root = ... -- taken from REWARD_R_ROOT ...` instead of silently using it.
Replayed exactly (notebook -> self-test -> notebook): the root is `D:/LKT/RWDR/data` again.

## The fund file was never read in R (the dose was empty in every R run)
Your workbook has the layout the Python pipeline reads ("<SWS> SWS in <District>" merged over Target / Progress /
Dose-Intensity columns, "Area in Hactare", dates in column 1). R expected a flat table, printed "New names ..." and
"SWS / date / progress columns not recognised -- dose left empty". R now reads the three layouts the Python loader knows;
on a workbook in your layout, R's seasonal dose equals Python's for every sub-watershed and season (18 of 18, difference 0),
misspelt names resolved by the 80 % rule.

## M14 "there is no package called 'chk'"
An older MatchIt already on your PC needs `chk`; `00_SETUP.R` only installed MISSING packages. It now also updates
out-of-date ones and installs every missing dependency (start it from a fresh session: Session -> Restart R).

## Smaller
An outcome that no export carries is reported as "NDVI is not in the panel: no export carries this variable" instead
of arrow's "Object ... not found". The self-test no longer reads your real fund file.

# v20.50 — three separate projects; the Windows PASS B pool failure fixed; the "crash" limits reverted and doubled; the A40 self-tested

## Three projects (was one bundle)
| project | what | its data (after `MIGRATE_DATA.bat`) | before |
|---|---|---|---|
| **RWD_Artal_v20.50** | Python pipeline + ground inputs + GEE exporter + the R bridge it calls | `D:\LKT\RWD_Artal\data` | `D:\LKT\TST_Artal` |
| **RWD_Artal1_v20.50** | the same Python pipeline for the second data set | `D:\LKT\RWD_Artal1\data` | `D:\LKT\TST_Artal1` |
| **RWDR_v20.50** | the R pipeline (RStudio `RWDR.Rproj` + Jupyter / IRkernel) | `D:\LKT\RWDR\data` | `D:\LKT\TST_ArtalR` |
Unzip each into its folder (`D:\LKT\RWD_Artal\RWD_Artal_v20.50`, …) — the code sits BESIDE its `data` folder, never inside it
(the export scan reads every sub-folder of `data`). `MIGRATE_DATA.bat` moves the data (a rename on drive D: — instant; the
`output` folder moves with it). Until you run it, each project finds and uses its old folder and says so. The fund file and
the crosswalk stay in `D:\LKT` (shared). The two Python projects still split the machine 50 / 50 when both run, with RWDR too.

## PASS B: "OSError: [WinError 87] The parameter is incorrect" -> BrokenProcessPool (your run, block 32 of 43)
PASS A keeps the Year x Season blocks in RAM (v20.30); PASS B then PICKLED each block into its worker process. On Windows a
multi-GB message through the process pipe fails (WinError 87 in multiprocessing's `_feed`); the pool broke, the "handle is
closed" tracebacks followed, and the remaining blocks ran sequentially (the panel was complete — the sequential path gives the
identical panel — only slower). Now a block above 256 MB is written to a shard file and its worker reads the file; nothing else
changes. Test (now in `validate_preprocessing.py`): blocks handed over as files == pickled blocks == sequential, row for row.

## Your correction: it was not a kernel crash (the status showed "Unknown" while busy) -> v20.45's limits reverted, doubled
- Permutation inference (M25): the pre-built package route first again (v20.45 had forced the engine path); its workers may
  use the WHOLE memory budget below the 95 % ceiling (was half).
- ML routes (M39-M43): 400,000 pixels (was 200,000) and up to 32 workers (was 16).
- A pre-built package is skipped only when its copy would exceed the whole budget (was half of it).
- R: N_MAX_UNITS 200,000 (was 100,000), N_MAX_PIXELS_MIXED 40,000 (was 20,000), N_MAX_ML 400,000 (was 200,000).
- Kept: the 95 % ceiling (your rule), the automatic 50 % split for two data folders (your request), the cell logs.

## Your NVIDIA A40
The engine now self-tests the GPU by itself the first time it finds a CUDA device: 2,000,000 rows demeaned on the GPU and on the
CPU, compared, the speed-up printed. If they disagree, or CUDA errors, the GPU paths are switched off for that session and the
CPU computes (every GPU result is also verified on ALL its rows, as before). `06_Validation/V00d_GPU_PATH_CHECK.py` now runs on
the REAL device when one is present (demeaning, matrix demeaning, a whole TWFE model, the k-NN matching vs scipy). torch must
be the CUDA build: `python -c "import torch; print(torch.cuda.get_device_name(0))"` must print `NVIDIA A40`.

# v20.49 — validated with real R, real packages and real Jupyter / IRkernel; the defects that surfaced, fixed

For the first time the bundle ran with R (4.6.1 + all 39 packages + polars), JupyterLab with the R kernel (IRkernel),
and the real Python packages (pyfixest 0.60, diff-diff 3.12, econml 0.17, DoubleML, esda, statsmodels, pyarrow 25,
pandas 2.3 and 3.0, torch). Every earlier "pass" had been measured against stand-ins; the real run found the following.

## Wrong numbers or wrong verdicts (fixed, each under test)
- **M16 pre-trend test with ONE sub-watershed (Python and R): "REJECT parallel trends" on data WITHOUT a pre-trend.**
  With fewer than 6 sub-watersheds the clusters are years and every lead is one year's dummy, so its cluster
  covariance is ~1e-30 and the Wald F exploded: F = 1e27–1e29 in 5 of 5 simulated panels (Python), F = 2.8e8 (R).
  The v20.34 conditioning checks did not catch it (a uniformly tiny matrix is well conditioned). Now, with year
  clusters, the test is the design-based one — the linear trend of the core-minus-control gap over the pre-period
  years (years as the draws). Measured on 40 panels: 2.5 % false rejections (nominal 5 %), 95 % power against a
  0.004/yr pre-trend. With >= 6 sub-watersheds the cluster-robust Wald test is unchanged. **Re-run M16 on Artal.**
- **Event study (M02) per-year SEs with year clusters** rest on one year each (not valid); every row now also carries
  `se_design` (the spread of the pre-period leads) and a note. The coefficients are unchanged.
- **BM (benchmark-site) means depended on the pandas version.** Under pandas 3 a site whose site number is blank was
  silently dropped. The R table shipped in v20.47 was built that way: Hunasehadagi root-zone moisture from 2 of its 24
  sites (up to 8.3 points off), Hanchinal SSM from 2 of 3 (6.2 points), ITGI missing. Now identical under pandas 2.3
  and 3.0 (275 rows, 19 programme + 13 control sub-watersheds; "ITGI (Control )" is now "ITGI"); the R tables are
  rebuilt and the self-check proves R reads exactly what Python computes.
- **R M35 quantile DiD: 0.030 for a true 0.050** (the whole-period pixel mean absorbed part of the effect). Now each
  series' PRE-period level is removed: 0.0500. Python used this R route once verified, and the ±0.025 tolerance
  would have let 0.030 through.
- **R M11 / M45 synthetic DiD with two cohorts: 0.042 for 0.050** (every treated unit dated from the earliest cohort).
  Now one fit per cohort, weighted by treated units (R and the diff-diff route alike).
- **R M26** reported the effect at Rain = 0 mm; rainfall is centred now (the effect at mean rainfall).
- **GPU k-NN pixel matching** (float32 matrix identity) chose another neighbour for 2 of 3,000 points with a 1.46 m
  error; distances are now computed from the coordinate differences (exact: 100 % agreement with scipy, 2e-4 m).

## Crashes and dead routes (fixed)
- **P00 PASS A / panel assembly with real pyarrow:** exports whose columns differ (e.g. `SWSiD_All` only in the newer
  ones) crashed as soon as a block spilled to disk ("Target schema's field names are not matching") — a real risk on
  the billion-row run. A later file with new columns now opens a new part of the block; the panel takes the union of
  the columns. Nothing is dropped.
- **Package routes that never verified with the installed diff-diff 3.12** (so the engine always computed them):
  M06 ContinuousDiD (new API: first_treat + dose; per unit dose = the linear dose-response slope), M11 SyntheticDiD
  (`post_periods`), M31 StackedDiD (cluster is a mode; covariates by entropy balancing), M34 / M05 base (a cluster
  must be constant within a unit — the year clusters of a one-sub-watershed run are not). **P12 now verifies all 4
  function routes and all 14 model routes** on the known answer. M06 on real inputs also merged its dose on the wrong
  key (pixel instead of pixel x season): fixed.
- **TWFE through pyfixest** (after P12) lost the MDE and the raw 2x2 that every result should carry: restored.
- **R, first real execution:** M03 / M30 (numeric id), M13 (needs `polars`, now installed by 00_SETUP.R), M19 (ICC from
  the variance components), M20 (across sub-watersheds), M22 (on sub-watershed x ring units — on pixels bacondecomp ran
  the test out of memory), M24 / M29 / M32 (headline estimates), M25 (Fisher permutation as the Python engine does it —
  ritest could not permute an interaction and ran out of memory), M36 / M37 (fect's output), M39 / M43 (grf clusters),
  M07 (one satellite predictor), M12 (no SE of 0 when the switch lies in one cluster), M34 (GLPK runtime on Linux).
- A Windows default path on Linux / Colab created a folder literally named `D:\LKT\TST_Artal` inside the bundle; it
  becomes `~/REWARD_data/TST_Artal` there (Windows unchanged).

## Your requests
- **80 % names in R, word by word, as in Python:** `REWARD_Artal_Exports_final`, `TST_Artal1`, `CSV_Sirur_v107_...`,
  misspellings (Hunsehadagli, Halligera, Mydalakere) resolve; Kohalli / Kandgula / Nagagondanahalli never become a
  programme name. The R test builds exports named ONLY by folder / file (no `SWSiD_All`) and checks every row is
  confirmed by its name.
- **The 50 % split is a real half of the machine** (share x 95 % of RAM / VRAM minus what the pipeline holds — v20.47 gave
  a share of what was FREE), shared by R and Python pipelines (one registry), immune to a re-used Windows process id.
  Live test: two folders 50 / 50, three 33 %, back to 100 % when the others end.
- **GPU first, proven without a GPU:** `06_Validation/V00d_GPU_PATH_CHECK.py` runs the engine's CUDA code on the CPU
  through a stand-in device: demeaning, matrix demeaning, the production entry point with its all-rows verification,
  a whole TWFE model (identical estimate and SE) and the k-NN — 5/5.
- **R in RStudio and Jupyter:** every notebook loads the library into its own environment (your settings apply when
  knitted, run with Run All, or in Jupyter). `00_SETUP.R` keeps a preset binary repository (the v20.48 fix), installs the
  GitHub-only packages through r-universe / the source archive when the GitHub API refuses, installs polars, and finds
  Anaconda's Jupyter from RStudio. `tests/run_all_tests.R` is strict now: two synthetic data sets (one sub-watershed;
  eight with two cohorts, a fund file and name-only folders), every model judged against its KNOWN answer, a data gap
  accepted only where the data lack what the model needs, then every notebook knitted as RStudio does and run in
  Jupyter through IRkernel.
- v20.48's Colab notebook is not needed any more: everything it was to check ran here, and `install_and_test_linux.sh`
  does it on any Linux machine.

# v20.48 — validation on web platforms (Colab / Posit Cloud) and a faster R setup on Linux

- **This sandbox still has no internet** (every host answers `host_not_allowed`, only api.anthropic.com is reachable), and
  web platforms need an interactive, logged-in browser session — so validation there is packaged for you to run:
  `VALIDATE_ON_COLAB.ipynb` (bundle root): real Python packages, every Python gate, the known-answer verification of each
  pre-built Python package route, R + all packages, `R/tests/run_all_tests.R` (RStudio engine + Jupyter through IRkernel),
  the Python -> R bridge verification -> one `VALIDATION_REPORT.txt`. Posit Cloud (RStudio in the browser): see README.
- **Fixed** `00_SETUP.R` overrode a repository chosen before it with plain CRAN — on Linux (Colab, Posit Cloud, the test
  script) every package would compile from source (arrow can take an hour and often fails). It now keeps a preset
  repository (Posit's pre-built Linux binaries) and installs in parallel.

# v20.47 — your 80 % name rule, an automatic 50 % machine split, R fall-backs and a complete R test

## Names: >= 80 % similar = the same sub-watershed (`_names.py`; R: `match_sws_name`), in every input file
similarity = 1 - Levenshtein distance / length of the longer normalised name (the same measure in R: adist). Applied to
the BM files, the fund file (`match_sws`) and export folder / file names (`site_id_for_name`, word by word). Two
safeguards, both found necessary in your BM files: the best match must be unambiguous (>= 5 points ahead of the next);
with coordinates, the sites must lie in that sub-watershed's core — "Nagagondanahalli" is 82 % similar to
"Kyatagondanahalli" but all 9 of its sites lie in Kyatagondanahalli's rings (a neighbouring control): kept apart.
"Kohalli" (control) is 78 % like "Kodihalli": never matched. Kandgul + Kandgula (88 %, within 10 km) now merge by the rule
(the hand-written alias is gone). The 13 non-programme names in your BM files are never matched to a programme name by
name alone. Result on your files: identical means (267 rows, largest difference 3.6e-15).

## Two pipelines at once: the machine is split AUTOMATICALLY (no setting to edit)
Every engine registers (process id + data folder) in a machine-wide folder; RAM, GPU memory and CPU are divided by the
number of DISTINCT data folders being processed now — 50 % each for TST_Artal + TST_Artal1 — and the whole machine
returns when one ends. Notebooks of the same pipeline do not split. Fixed on the way: the GPU budget ignored the share,
and worker counts / BLAS threads used every core regardless. Liveness via psutil (os.kill is never used on Windows,
where it terminates the process). `MEMORY_SHARE` in `_paths.py` stays an optional manual cap.

## R: package first, with fall-backs (the pipeline no longer stops when a package is missing)
`reward_models_core.R` began with `library(fixest)`: without fixest nothing could run. Now: fixest when installed, else a
built-in two-way fixed-effects engine (alternating projections, rank-revealing QR, cluster-robust SE, t with G-1 df) for
M01, M02, M06, M07, M16, M21, M23; arrow when installed, else a CSV panel. Validation (R cannot run in this sandbox —
every host is blocked, including the Ubuntu archive): a line-for-line NumPy mirror of the fall-back engine matches the
Python engine (beta 0.051184 both, difference 2e-17, SE ratio 1.000); no call to the pipeline's 91 R functions uses an
argument name the function lacks; all 106 R files / notebooks pass the structural check.

## The complete R test: `R/tests/run_all_tests.R` (RStudio: Source) and `install_and_test_linux.sh`
Synthetic export with a known +0.05 effect in the real Haligeri polygons -> preparation -> all 45 models with known-answer
checks -> the notebooks rendered as RStudio does and run in Jupyter through IRkernel -> one PASS / DATA GAP / FAIL table.

## Bundle names carry the version: REWARD_FINAL_v20.47.zip (root folder REWARD_FINAL_v20.47)

# v20.46 — BM sites as sub-watershed means, a deep validation loop, and the fixes it found

## Benchmark (BM) sites -> ONE mean per sub-watershed (your rule), `_bm_means.py`
- Variables declared explicitly with physical bounds (no ID / coordinate column is ever averaged): ssm_pct (02, clean,
  (0, 60]), lai (03, clean, (0, 10]), gw_depth_m (04, [0, 300]), tdr_rootzone_pct and tdr_rootzone_ec_ds_m (06, 0-30 cm —
  the TDR layer schemes differ between institutions, so 05's layers are not averaged), soil_temp_c (05, sparse).
- Two stages so every SITE counts once: site mean over visits and replicates, then the mean over the sub-watershed's sites
  (+ n_sites, spread between sites). Rows per site-season ranged 2-126, so a row mean let heavily sampled sites dominate.
- Names: 7 sub-watersheds were split over two spellings (e.g. "Kodihalli Sub-Watershed" / "Kodihalli sub-watershed") —
  unified; every site placed in the programme polygons: a name whose sites lie >= 80 % in one core IS that sub-watershed
  ("Koppal (4D4A2)" -> Murlapura, 20/22 sites; "Koranahalli and Haralahalli" -> Koranahalli, 6/6); blank names take the
  core they lie in, the TDR block name, or an exact micro-watershed match.
- Kept out and listed (BM_SITE_AUDIT.csv, BM_SWS_SUMMARY.md): sites whose location contradicts their name — all 16 "Artal
  Sub-Watershed" sites (Artal's only LAI / SSM sites; 14 outside every programme polygon), 10 "Shirur" sites, wells 4-5 km
  outside their named sub-watershed, 2 "Hanchinal" (control) sites inside the treated Sirur core; 47 root-zone sites with
  no resolvable name. Values dropped as not measurements: 55 SSM, 42 LAI (all three replicates exactly 0.0; the harmonised
  07 file omits them), 3 groundwater (< 0 m), 2 root-zone zeros.
- Result on your files: 19 programme + 12 control sub-watershed means (267 rows). Cross-check against the independent 07
  file: where both use the same sites the means agree EXACTLY (median difference 0; correlation 0.9995 gw, 0.998 SSM,
  0.999 root zone); they differ only where location checks keep sites out.
- M07 no longer falls back to single BM pixels (it runs on the GND_* outcomes built from the sub-watershed means, or stops
  with that reason); V06 validates BM sub-watershed means against satellite core means, not site by site. R reads the same
  validated table (R/data/ground/bm_sws_season_means.csv).

## Bugs the validation loop found (all fixed, all under test)
1. **Covariate folder tag**: v20.45 said new results go to `covAll4` folders — they did not: the default set had no tag,
   so new results shared folders with pre-v20.44 results (LandUse as a number). The four-weather set now always writes
   `_covAll4`; every result records `engine_version` and `data_rules`; the results audit flags untagged (old) folders.
2. **M01's streaming path** (large panels) read the files directly and skipped the fill-year screen — the very path that
   could reproduce beta ~ 0 / SE ~ 0. Screened now, with the same refusal rule (test: VCI 0.0298 vs truth 0.03; NDMI refused).
3. **Cached package inputs** were reused across rule changes (only rebuilt when missing): names now carry the data-rules
   version (`..._rules20.46`). Contract verified: did = treat x post, fill years absent, never-treated cohort = inf (as
   the R library reads it), cluster rule, unit = pixel x season, no LandUse.
4. **R-library resolver** could fall back to a stale engine/R folder (e.g. a new bundle unzipped over an old one): removed.
5. **P08b summary** read a column of the old name table (P00 cell 16 AttributeError) — fixed; a missing ground folder now
   yields empty tables and a one-line report instead of stopping P00.

## New gate: `validate_inference.py` (Monte Carlo on the engine, 200 panels per scenario)
| scenario | bias | true SD | model SE | design SE | coverage model / design | false positives model / design |
|---|---|---|---|---|---|---|
| one sub-watershed | -0.0003 | 0.0032 | 0.0028 | 0.0031 | 92.5 % / 96.0 % | — |
| eight sub-watersheds | 0.0000 | 0.0011 | 0.0011 | 0.0011 | 97.0 % / 97.0 % | — |
| one sub-watershed, no effect | -0.0003 | 0.0029 | 0.0029 | 0.0033 | 94.5 % / 95.5 % | 5.5 % / 4.5 % |

# v20.45 — fill years, four covariates, the design from the data, crash protection, the R pipeline, a clean layout

## Root cause of beta ~ 0.000014 with SE ~ 0 (from your yearly diagnostics)
NDMI in 2020, 2021, 2022, 2024; VCI in 2018, 2019; SMDI in 2020 and 2024 hold values for only 54 treated and 193,044 control
pixels (normally 619,271 / 1,248,914) and the treated and control means are IDENTICAL (NDMI 2020: 0.13102 = 0.13102): the
export wrote one constant for every pixel. After pixel and year fixed effects nothing varies, so every DiD is ~0 with an
SE of ~0. NDMI's only real year is 2025, whose pixels have no history (0.02 % linked). No standard-error formula fixes this.
- **Outcome screen** (`screen_outcome_frame`, applied inside `load_panel`, so every model and package route): a year-season
  constant across pixels, or with treated or control coverage below 5 % of the typical one, is left out and reported; an
  outcome left with < 2 valid pre-years or no post-year is refused with the reason. `screen_all_outcomes()` in P09 →
  `OUTCOME_SCREEN.csv/.md`. Test: an NDMI-like outcome is refused; a VCI-like one loses its fill years and recovers +0.03.
- **Zero-SE guard**: a result with SE ≤ 1e-9 (or < 1e-7·|beta|) carries `se_invalid` + the reason; `audit_results()` →
  `RESULTS_AUDIT.csv/.md` (new `06_Validation/V01_Results_Audit.ipynb`).

## Covariates
`"all"` = the four weather covariates (Rain, Tmax, Tmean, Tmin), folder tag `covAll4` (old `covAll` results entered
LandUse as a number). `all_with_landuse` removed; a LandUse request is dropped with the reason (a class code, and a bad
control). The R bridge (`run_one.R`) defaulted to LandUse too — fixed.

## The design from the data — never from the effect (`recommend_design`, P00 `DESIGN_MODE = "recommended"`)
Pre-years start after the last export break (both groups jump together); post-years end before the next break or a year
whose core pixels lose their history (< 90 % linked: 2025); fill years are not data; an inner ring (≤ 2) whose gap to the
farthest ring changes after implementation (|t| > 2) is spillover-contaminated and not a control (at least two control
rings kept); seasons enter only with coverage in every chosen year. `DESIGN_RECOMMENDATION.md` gives the evidence.
Test: breaks 2018 + 2025 and ring-1 spillover → pre 2018–2021, post 2022–2024, control rings 2–5.

## Crash protection and memory
- Permutation inference ran up to 999 fits in parallel threads through the package route — each copying the ~70 M-row
  panel: now the memory-light engine path (restored by `try/finally`), workers capped by free memory.
- ML routes (M39–M43) used `n_jobs=-1` on every pixel: now a 200,000-pixel sample and ≤ 16 workers.
- A package route is skipped when its copy of the frame would exceed half of the free memory.
- `MEMORY_SHARE` in `_paths.py` (or env `REWARD_MEMORY_SHARE`) scales the RAM and GPU budgets — 0.45 per copy when two run.

## Two Python pipelines at once
`python/DIDRDP_ALLRunDID_v20` (D:\LKT\TST_Artal) and `python/DIDRDP_ALLRunDID_v20_Artal1` (D:\LKT\TST_Artal1): identical
code except the data root, so notebooks, outputs and caches never collide (one code folder would have shared the notebook
files between two Jupyter servers).

## The R pipeline (`R/`, data root D:\LKT\TST_ArtalR)
`lib/reward_prep.R` (preparation with the Python rules; the BM sites AVERAGED PER SUB-WATERSHED and merged as `BM_*`),
`lib/reward_design.R` (screen, design SE, cluster rule, design from the data, zero-SE flag, audit),
`lib/reward_models_core.R` (M01 fixest, M02 event study, M05 did, M06 dose, M07 BM surrogate via glmnet, M08 data gap,
M11 synthdid, M16 rank-safe pre-trends, M21 annual, M23 wild cluster bootstrap with exact per-cluster sums, M34 HonestDiD
+ the 34 library models), 48 notebooks as `.Rmd` (RStudio) and `.ipynb` (Jupyter), `00_SETUP.R`, `tests/selftest.R`
(known answer +0.05). The Python bridge finds `R/lib/run_one.R` by relative path.

## Clean layout
`python/` and `R/` apart; removed: the engine's old R folder and `07_R_Canonical_Modules` (superseded by `R/`), `NDVI4/`
(unreferenced), ten v17 changelogs, v5–v17 guides nothing referenced, a stale Artal readiness file and gate outputs.

# v17.11 -> v20  (2026-09-16)  "choose the control rings and the treatment year at run time"

## What you set, in CELL 1 of whichever model you run
```python
CONTROL_ZONES  = "1-3"      # "1" | "1-2" | "1-3" | "1-4" | "1-5" | or an explicit set like (1, 3, 5)
TREATMENT_YEAR = 2022       # shift the intervention earlier or later; post = Year >= TREATMENT_YEAR
C.set_scenario(control_zones=CONTROL_ZONES, treatment_year=TREATMENT_YEAR)
```
Nothing else changes. Every column that depends on those two choices is rebuilt from `buff_km` and `Year` for
that run: `treatment`, `control`, `pre`, `post`, `did_term`, `in_analysis_sample`, `event_time`, `period_index`
and the aliases (`treat_core`, `control_zone_selected`, `pre_period`, `post_period`). The analysis sample changes
with the rings (fewer or more control pixels) and the pre/post split moves with the year, so the estimate, the
event-study window, the counterfactual and the coverage diagnostics all follow.
`set_scenario(post_cutoff=...)` is available when you want the pre/post split to differ from the event-time origin.

## Where results go
`RESULTS_ROOT/<MODEL_ID>/<scenario tag>/...`, e.g. `M01/ctrl1-3_treat2022/canonical_twfe_NDVI.csv`.
Scenarios therefore never overwrite each other and can be compared side by side. The tag also names the coverage
file (`TREATMENT_COVERAGE_<tag>.csv`) and is recorded in `OUTCOME_RUN_LOG.csv`.
The outcome loop (CELL 9) runs inside the scenario you chose, so one Run All gives every variable for that scenario.

## The correctness trap this closes
P09's per-variable files carry the treatment columns PRE-COMPUTED. A model run with different rings or a different
treatment year would otherwise have read columns built for the old choice. Each file now carries a
`<outcome>.scenario.json` sidecar; when the active scenario differs, `load_panel` rebuilds those columns on load and
says so. You do NOT need to rebuild the estimator files when you change scenario.
The streaming 2x2 estimator takes its rings and its post cutoff from the active scenario too.

## Verified (synthetic panel with a true effect of 0.05 and ring-specific drift)
| scenario | pixels in sample | post rows | beta |
|---|---|---|---|
| ctrl1_treat2023 | 388 | 4,656 | +0.0481 |
| ctrl1-2_treat2023 | 611 | 7,332 | +0.0467 |
| ctrl1-5_treat2023 | 1,200 | 14,400 | +0.0431 |
| ctrl1-5_treat2022 | 1,200 | 18,000 | +0.0325 |
| ctrl1-5_treat2024 | 1,200 | 10,800 | +0.0380 |
| ctrl1+3+5_treat2023 | 770 | 9,240 | +0.0428 |

A file built as `ctrl1-5_treat2023` and read under `ctrl1-2_treat2024` was rebuilt correctly; two M01 runs wrote to
`M01/ctrl1-5_treat2023` and `M01/ctrl1-2_treat2022` without touching each other. `selfcheck.py`: 11 checks clean
(engine 20.0, 287 cells parse, 1,769 engine calls signature-checked, 45 notebooks carry the scenario block).

## v20.1 (same day) -- one fix found by the final smoke test
The outcome loop (CELL 9) re-executes the notebook FROM DISK for each remaining variable, so it was reading CELL 1
as SAVED -- if you changed `CONTROL_ZONES` / `TREATMENT_YEAR` in the running cell without saving the notebook, the
first variable used your scenario and the rest silently used the saved defaults (NDVI landed in
`ctrl1-2_treat2023` while LAI went to `ctrl1-5_treat2023`). The scenario you set is now locked for the whole loop:
`set_scenario()` inside a loop pass keeps the parent's choice and says so, and every variable of a Run All lands in
the same scenario folder. `selfcheck.py` asserts the lock is present.

## v20.2 -- choose how many YEARS go into the estimation
Alongside the control rings and the treatment year, CELL 1 of every model now takes the year window:

```python
CONTROL_ZONES  = "1-3"
TREATMENT_YEAR = 2023
PRE_YEARS      = 4        # years kept BEFORE the cutoff   (None = every earlier year in the panel)
POST_YEARS     = 2        # years kept FROM the cutoff      (None = every later year; 1 = the cutoff year only)
C.set_scenario(control_zones=CONTROL_ZONES, treatment_year=TREATMENT_YEAR,
               pre_years=PRE_YEARS, post_years=POST_YEARS)
```
`C.set_scenario(year_min=2018, year_max=2025)` sets an explicit window instead; `all_years=True` clears it.
The counts are relative to the cutoff, so moving the treatment year moves the window with it (treat 2023 +
pre 4/post 2 -> 2019-2024; change to 2024 -> 2020-2025).

**Applied to every file that reaches an estimator, not just to one model:**
- `load_panel` drops out-of-window rows WHILE streaming each row group (so a narrow window also costs less RAM);
- `in_analysis_sample` is 0 outside the window, so any model that filters on it gets the same rows;
- the streaming 2x2 estimator filters identically (memory and stream agree to 1e-9 under a window -- tested);
- `apply_scenario()` trims a frame that arrives from anywhere else;
- per-variable estimator files keep EVERY year and the window is applied when a model reads them, so changing the
  window never means rebuilding them (verified: files built with all years, read back as 2022-2024);
- the window is in the scenario tag, so results land in e.g. `M01/ctrl1-5_treat2023_yr2019-2024/`;
- an empty or one-sided window (no pre or no post period) is refused or warned about before anything runs.

Verified on a synthetic panel with a true effect of 0.05: all years -> +0.0510 (28,800 rows), pre 4 -> +0.0516
(19,200), pre 4 / post 2 -> +0.0512 (14,400), 2018-2025 -> +0.0520 (19,200); memory and streaming identical; a real
M01 Run All with PRE_YEARS=3, POST_YEARS=2 wrote both variables to `M01/ctrl1-5_treat2023_yr2020-2024`.
`selfcheck.py`: 13 checks clean (engine 20.2).

## v20.3 / v20.4 -- every module equipped, and a production validation gate
### The scenario now reaches every model, and can be set once at panel preparation
- `P09` writes `did_scenario.json` next to the panel (`PERSIST = True`). Every model's CELL 1 has
  `SCENARIO_FROM_PANEL = True` and calls `C.load_scenario()`, so a choice made during preparation governs all 45
  modules with no notebook edits. Set it False to use that notebook's own four values.
- Added `cohort_offset`: staggered designs (M05, M27, M28, M29, M30, M31, M32) take their cohorts from the panel's
  `first_treat_agri_year`; the offset shifts every cohort, so "shift the timing" also works for them.
- `C.scenario_banner()` is printed by every model at STEP 1, so each run log states the rings, the treatment year
  and the year window in force.

### Leaks found and fixed by the deep check
- M11, M45 split pre/post on the module CONSTANT `C.TREATMENT_YEAR` (2022), ignoring the run's choice; M15's
  placebo used it as its base year. All three now read the ACTIVE scenario. `selfcheck.py` fails if any model ever
  reads `TREATMENT_YEAR`, `POST_CUTOFF` or `DEFAULT_CONTROL_ZONES` directly again.
- M40-M45 (the ML notebooks) had their one-line config mangled by an earlier edit: the `CONTROL_ZONES` assignment
  sat inside a comment and the import bootstrap ran after the config. Their configuration cells were rebuilt
  (bootstrap first, then config), and the assignments that edit had dropped (`COVARIATES`, `MAX_ROWS`) restored.
- **Real engine bug**: `_fit_untreated_two_way_fe` (used by M28 Gardner and M29) mapped unit/time means through a
  fixed-effect key that v17.2 stores as a pandas `category`; the mapped result is categorical and refuses
  arithmetic -> `TypeError: Object with dtype category cannot perform the numpy op subtract`. Added `_num_map()`
  and used it in all four places. M28 and M29 now run and respond to the scenario.

### `validate_all_models.py` -- the production gate
Runs EVERY model twice on a synthetic panel (A: rings 1-5, treatment 2023, all years; B: rings 1-2, treatment 2022,
pre 3 / post 2), checks each wrote to its scenario folder and that the two runs differ, and writes
`VALIDATION_ALL_MODELS.csv`. Current result: **45/45 execute without error; 38 demonstrably honour the scenario;
7 are blocked by documented data gaps** (M07 needs the ground-truth file, M08 an instrument, M13 switchers, M16
two pre periods, M31 clean cohorts, M37 treated cells, M38 a treated unit) -- none of them ignores the scenario.
`selfcheck.py` reads this report and FAILS if a model errors or ignores the scenario without a documented reason
(16 checks in total).

## v20.5 -- PASS A crash fixed, and the preparation path is now tested
### The bug you hit
`build_fe_and_treatment` built `row_id` by concatenating `pixel_id` with "_". Since v17.6 `pixel_id` is an **int64**
(8 bytes instead of a ~60-byte string, one of the speed-ups), and int64 + str raises
`UFuncTypeError: ufunc 'add' did not contain a loop ... (dtype('int64'), dtype('<U1'))`. Every PASS A worker failed
on it, in parallel and in sequential fallback. Fixed: `row_id` now converts explicitly
(`pixel_id.astype("string") + "_" + Year + "_" + season label`). The id itself, the shards and every downstream
column are unchanged -- only the text key is built correctly.
Also hardened `subwshed_id`: `SubwshedID` is accepted as a number (3), as text ("3") and as an already-formed
label ("SW3"); the previous code raised `ValueError: Unknown format code 'f'` on the last two.

### Why it slipped through
`validate_all_models.py` starts from a ready panel, so nothing in the test suite had ever executed PASS A.
**New: `validate_preprocessing.py`** writes synthetic Earth-Engine-style CSV exports and runs the REAL preparation
chain over them -- `load_and_harmonize -> assign_pixel_ids -> resolve_duplicates -> data_qc ->
build_fe_and_treatment`, then `run_pass_a` in BOTH the parallel and the sequential path -- and checks the dtypes,
that `row_id` is well formed, that duplicate (pixel, year, season) rows are resolved, that the same coordinate
always gets the same id across files, that the int64 id equals the legacy 18-digit string id, and that the
scenario columns come out right on the prepared shards. Current result: all checks clean, 0 file errors,
1 duplicate group resolved.
`selfcheck.py` (18 checks) additionally scans the engines and all notebooks for any bare string concatenation of
the int64 `pixel_id`, so this exact class of bug cannot return.

### Run order before a production rebuild
`python selfcheck.py` -> `python validate_preprocessing.py` -> `python validate_all_models.py` -> P00 ... P09 -> models.

## v20.6 -- PASS B uses every core and the RAM you have
### What was slow
PASS B walked the 44 Year x Season blocks **one at a time on a single core** (63 idle), and inside each block it
ran the two most expensive steps **twice**: `build_treatment_columns` and `finalize_panel_block` were each called
twice per block. At ~15-19 s per block that is ~13 minutes of mostly wasted, mostly single-threaded work.

### What changed
- The per-block work (read shard -> cross-file dedup -> DiD columns -> dose merge -> sort -> finalize) moved into
  `prepare_pass_b_block()`, called **once per step**. That alone roughly halves the work per block.
- Blocks now run in **parallel worker processes** (`_pb_worker`), each writing its own part file, using the same
  Windows/Jupyter-safe spawn setup PASS A uses. `pass_b_worker_count()` sizes the pool from the cores AND the RAM
  free at that moment (70 % of free RAM / ~220 B per row per block). On your machine -- 64 cores, 500 GB -- that is
  all 44 blocks at once, ~0.4 GB each. `PASS_B_WORKERS = <int>` pins it; a pool failure falls back to sequential.
- The single `did_panel_full.parquet` is then written by **streaming the parts in the required order**, so the file
  is identical to the sequential build: the gate checks shape, row order and every numeric column and reports
  "PASS B parallel output is IDENTICAL to sequential".
- `autotune_prep()` now also raises the Parquet row-group to 4,000,000 on >=384 GB machines and prints the core
  count and the worker plan for both passes.

### Two documentation errors corrected while doing this
`run_pass_b`'s docstring and closing message claimed the panel carries `treatment_group`, `control_group`,
`pre_period`, `post_period`. Those names are listed in `DROPPED_FROM_PANEL`, so they were never written -- the code
assigned them and `finalize_panel_block` immediately removed them. The dead assignment is gone and both messages
now name what the file really holds: `treatment`, `control`, `pre`, `post`, `did_term`.

### Gates
`validate_preprocessing.py` now runs PASS B **both ways** and compares the panels; `selfcheck.py` (18 checks) fails
if PASS B loses its `n_workers` parameter or if either expensive step is called more than once per block.

## v20.7 -- the whole machine (KSRSAC-GPU2: 2 x EPYC, 64 logical cores, 512 GB, Windows Server 2022)
### What was leaving the box idle
`run_pass_a` sized its pool as `min(32, cores // 2)` -- **32 of your 64 cores, and a hard 32 cap whatever the
machine**. Nothing set BLAS/OpenMP thread counts, so every worker process was free to start 64 numpy threads:
32 x 64 threads fighting over 64 cores, which is slower than one thread per worker.

### New: `_hardware.py`, one place that decides how much machine to use
- `machine_profile()` measures logical vs physical cores (your 64/32 = SMT on), total and free RAM, and the OS.
- `worker_cap()` = all logical cores minus a 1-core reserve, never more than the number of tasks, never more than
  free RAM allows, and **never above 61 on Windows** -- `ProcessPoolExecutor` raises above that limit, which would
  have crashed a naive "use all 64" change.
- `use_full_machine()` (parent process) gives numpy/BLAS every core; `worker_init_threads()` pins each worker to
  ONE BLAS thread. Both `OMP/OPENBLAS/MKL/NUMEXPR/VECLIB/BLIS` variables are set, plus `threadpoolctl` when present.
- Verified against a SIMULATED 64-core / 512 GB / Windows box (the self-check does this on every run, so the
  numbers are checked even on a small machine): **PASS A 60 workers, PASS B 44 workers (one per block), ~0.4 GB each**.

### Applied
- PASS A: pool from `worker_cap(n_tasks=n_files)` -- 60 processes for your 1,449 files instead of 32.
- PASS B: `pass_b_worker_count()` now goes through the same helper (all 44 blocks at once on your box).
- Every worker: 1 BLAS thread. Parent: all 64.
- `autotune()` / `autotune_prep()` print the machine, the thread plan and the worker plan before the long passes.
- Models: `TUNE["n_jobs"]` is now `cores - 1` (63), used by the wild-cluster bootstrap (M23), permutation
  inference (M25) and every sklearn learner in M39-M45 -- one of which (`causal_forest_style`) was still running
  single-threaded because its `RandomForestRegressor` had no `n_jobs`; it does now.
  The single-outcome estimators (M01-M38) are one process doing numpy work, so they get all 64 BLAS threads
  instead of process parallelism -- that is the right shape for them, not a missed opportunity.

### Gates (all green)
`selfcheck.py` 23 checks -- including the simulated-machine plan, "no 32-worker cap", and "workers pin BLAS to one
thread"; `validate_preprocessing.py` clean (PASS A both ways, PASS B parallel == sequential);
`validate_all_models.py` 45/45 run, 38 honour the scenario, 7 documented data gaps.

## v20.8 -- "Parquet magic bytes not found in footer"
### What that warning meant
A Parquet file gets its footer (the magic bytes) only when the writer CLOSES. Your earlier PASS B was interrupted,
so `did_panel_full.parquet` was left truncated -- real bytes on disk, no footer, unreadable by anything. The
validator did the right thing (refuse it, rebuild), but the message did not explain it and the corrupt file stayed
where a later step could pick it up. Nothing was wrong with your data.

### Fixes
- **Atomic publish**: PASS B now writes `did_panel_full.parquet.building` and renames it over the real name only
  after the footer is closed AND the file has been re-opened as a proof. An interrupted run can no longer leave a
  corrupt panel -- the previous good panel (if any) is left untouched, and a stale `.building` file from a killed
  run is removed at the start of the next one.
- **Quarantine**: `final_panel_is_valid()` now explains the cause in plain words ("no Parquet footer ... what an
  interrupted PASS B leaves behind, not a data problem") and moves the unreadable file to
  `did_panel_full.parquet.corrupt_<timestamp>` instead of leaving it in place. Delete those once a rebuild succeeds.
- **`P.panel_file_report()`**: one call that answers "is my panel usable?" -- size, rows, row groups, columns, or
  the reason it cannot be read.
- Gates: `validate_preprocessing.py` now truncates a good panel on purpose and checks that it is detected,
  quarantined, rebuilt readable, with no `.building` file left behind; `selfcheck.py` (25 checks) fails if PASS B
  ever stops writing atomically or the validator stops quarantining.

## v20.9 -- what the dedup warnings mean, and one real risk they were hiding
### Your question: is dedup only within a cell?
Yes. `resolve_duplicates(group_keys=("pixel_id", "Year", "Season"))` groups on exactly that key, so two rows are
only ever compared when they are the SAME pixel in the SAME year and the SAME season. A pixel in Kharif is never
compared with the same pixel in Rabi, or in another year. PASS B calls it per block, and the self-check now fails
if that key ever changes.

### The risk it was hiding (fixed)
The resolver kept ONE row per cell and discarded the rest. That is right when the duplicates are redundant copies,
but WRONG when an export is split by variable group -- file A holding NDVI/SAVI and file B holding SMDI/WSI for the
same pixel-year-season. The kept row would keep its own gaps and the other file's variables would be lost silently.
Now the kept row's missing values are FILLED from the rows being dropped, in the same priority order that chose it
(a value already present is never overwritten), and each duplicate group is classified:
  * `redundant`     - the dropped rows carried nothing the kept row lacks (safe, the usual case)
  * `complementary` - the dropped rows carried variables the kept row was missing -> now merged in
  * `conflicting`   - both rows have DIFFERENT values for the same variable -> newer file wins, both logged
The PASS B warning now states which, e.g. `1,663,078 duplicate pixel-rows resolved ... [1,663,078 redundant]; the
dropped rows carried no value the kept row lacks` -- so you can see at a glance whether anything was merged.
`cross_file_dedup_conflicts.json` records `duplicate_kind` and `values_filled_from_dropped_rows` per group.

### Your second question: does every block hold the same pixels?
PASS B now answers it explicitly. Each block prints its unique pixel count, and at the end
`panel_balance_by_block.csv` lists rows and unique pixels per Year x Season, with a warning naming any estimation
block that differs from the rest. Your log already shows it does NOT: the seasonal blocks hold 1,710,519 rows while
2025 Kharif holds 3,168,391 -- the 2025/2026 "Artal"-named export covers a different footprint from the earlier
unnamed one. (Season 0 "Yearly" is excluded from estimation, so its 3,757,288 rows do not affect any model.)
The estimators handle an unbalanced panel exactly (v17.7), but coverage differs by period, which is what the
M02 coverage diagnostics were pointing at.

## v20.10 -- "[WinError 5] Access is denied" when publishing the panel
### What happened (my bug, not your data)
v20.8 made PASS B write `did_panel_full.parquet.building` and rename it into place. On Windows a rename fails if
ANY handle still points at either file -- and this code left handles open: `final_panel_is_valid()` and
`panel_file_report()` created a `pyarrow.ParquetFile` just to read metadata and never closed it, and the footer
proof did the same on the `.building` file. So the kernel itself was holding the panel open, `os.remove` failed,
`os.replace` failed, and STEP 6/7 then read the OLD corrupt file -- hence "Parquet magic bytes not found".
**Your 20-hour PASS B was not wasted: the `.building` file is the complete, valid panel.**

### Fixes
- `pq_meta()` / `pq_is_readable()`: every metadata-only read opens, reads and **closes**. All such reads in
  `_prep_common.py` and `_common.py` now go through them; the PASS B assemble loop also closes each part file.
- `publish_atomic()`: garbage-collects, retries the rename for ~12 s, removes a stale destination mid-way, and if
  it still cannot publish it raises a message that names the finished file and the one-line recovery.
- `finalize_pending_panel()`: publishes a finished-but-unpublished `.building` panel **without re-running PASS B**.
  It verifies the footer first, quarantines an unreadable file sitting at the final name, then renames.
- Gates: the preprocessing gate now counts ParquetFile opens vs closes (3/3) and simulates exactly your failure --
  a complete `.building` plus a junk file at the final name -- then checks the recovery publishes it and
  quarantines the bad file. `selfcheck.py` (31 checks) fails if any metadata read stops closing its handle or if
  PASS B stops using `publish_atomic`.

### Recover your current run (no recompute)
Restart the kernel, then:
```python
import _prep_common as P
P.finalize_pending_panel(r"D:\LKT\TST_Artal\output")   # publishes did_panel_full.parquet.building
P.panel_file_report()                                   # confirm rows / columns
```
Then re-run STEP 6 and STEP 7 only. If the rename still fails, close anything holding the file (Explorer preview,
Excel, another notebook) -- the message will say so.

## v20.11 -- the 9.5-hour PASS B, the manifest crash, and empty coefficients
### 1. `NameError: name 'pf' is not defined` in build_manifest (my v20.10 regression)
The handle-closing edit replaced the `ParquetFile` that `build_manifest` streams from. Restored, with an explicit
close after the loop. Your panel was fully written before this crash (101,137,115 rows); only the manifest and
the steps after it need re-running.

### 2. PASS B took 9 h 33 min -- fixed by vectorising the duplicate resolver
`resolve_duplicates` looped in Python over EVERY duplicate group. Your 2025 blocks had 1-5 million groups each and
the run had 23,059,420 in total; the first Yearly block alone took ~3 hours, and 23 million log dicts were then
pickled back to the parent. The resolver now does ONE sort by the priority rules (newer file, then fewer gaps,
then NObsV, then vintage, then file name) and lets `groupby.first()` keep the top row while filling its gaps from
the next rows -- the same rules, the same result. Verified against the old loop on identical input: same rows,
same values, same kept file. Measured: 151x faster at 10k groups; the 3.76 M-group Yearly block goes from ~3.3 h
to ~1.3 min (single core). `cross_file_dedup_conflicts.json` is now one summary per block (counts by kind and by
rule) plus a 2,000-group sample instead of 23 million entries.

### 3. Empty coefficients -- make the cause print itself
Every model now prints a COVERAGE line right after the scenario is applied: rows, treated pixels, control pixels,
pre rows, post rows, treated x post rows, year span -- and a `COVERAGE PROBLEM` warning naming the specific cause
when any of those is zero (no treated pixels, no control ring present, no pre or no post period under the window).
`save_results` refuses to write empty numbers silently: a result whose coefficient/SE fields are all NaN is written
with `status=EMPTY_RESULT` and a `reason`, and a warning points at the coverage line.

### Gates
`selfcheck.py` (35 checks): dedup must stay vectorised, build_manifest must keep and close its handle, the
coverage/empty-result diagnostics must exist. `validate_preprocessing.py` clean; `validate_all_models.py` 45/45.

## v20.12 -- three things your PASS B log and your M01 results revealed
### 1. `build_manifest`: NameError 'pf' (my regression from v20.10)
When I routed metadata reads through `pq_meta()` I removed the `pf` reader that the streaming row-group loop of
`build_manifest` still used. Fixed (reader defined, closed at the end) and the preprocessing gate now executes
`build_manifest` on the finished panel so this cannot ship again. **Your panel was written correctly** -- the crash
came after "panel written", in the manifest step.

### 2. PASS B took 9.5 hours because of the duplicate resolver, not the machine
The 44 workers started at once (as designed), but three 2025 blocks had 1-3.7 MILLION duplicate groups each and
`resolve_duplicates` looped over them one group at a time in Python (~7 ms each -> hours). It is now vectorised:
the same priority rules (newer file > fewer missing > NObsV > vintage > name), the same coalescing of complementary
values, the same classification -- computed for all groups at once. **1,000,000 groups: 3.7 s** (gate: 200,000
groups in 0.7 s). The log no longer writes 23 million JSON entries either: a summary (counts by kind and reason)
plus the first 200 groups in full.
What the numbers themselves say: in 2025 Kharif/Rabi/Yearly the two exports (unnamed vs "Artal"-named) overlap on
roughly a million pixels each and carry DIFFERENT values for the same pixel-season ("conflicting"); the newer file
won, and 3.6 M missing values in 2025 Kharif were filled from the older one. That is a real data decision you
should be aware of when interpreting 2025.

### 3. Empty coefficients (WSI, WSSI, ESI, RUSLE = NaN; NDVI = 0.000 / 0.000)
`estimate_twfe_did` never excluded missing values. A NaN outcome poisons the fixed-effect means, so an outcome with
no seasonal values came out as beta = NaN, and one with a degenerate pattern came out through the pseudo-inverse
as a silent beta = 0.000 / se = 0.000 -- both written to the CSV as if they were estimates.
- **Missing-value policy, enforced**: rows whose outcome, treatment term or any covariate is not finite are excluded
  before demeaning, in the in-memory AND the streaming estimator (verified identical to 1e-9). The count is
  printed, and warned about above 25 %.
- **No degenerate numbers**: a non-finite estimate, or beta and se both exactly zero, now raises a DATA GAP with the
  reason instead of writing a number. `n_obs`, `n_dropped_missing`, `n_treated_post`, `n_clusters`, `status` are
  written into every result row.
- **`C.outcome_coverage('WSI')`**: one table -- finite values per Year x Season, split treated / control, every
  season including the annual composite. It is printed automatically whenever an estimate is refused.
- **Why those four were empty**: ESI, RUSLE, WSI and WSSI are annual-composite variables -- they have values only in
  the Season 0 "Yearly" rows, which every model excludes. New scenario switch: `SEASONS = "yearly"` in CELL 1
  (or `C.set_scenario(seasons="yearly")`) estimates on the annual rows with pixel + year fixed effects; results
  land in `<model>/ctrl..._yearly/`. The per-variable files now hold every season; the switch is applied on read.
  Verified: a yearly-only outcome refused under "seasonal" with a clear message, estimated under "yearly", memory and
  streaming identical.
- NDVI's 0.000 / 0.000 will now come back as an explicit refusal naming the cause; run
  `C.outcome_coverage('NDVI')` and `C.treatment_coverage()` for that scenario to see which periods lack treated or
  control pixels -- in your `ctrl2-3_treat2023_yr2020-end` run the control set was rings 2-3 only, with 2025-26 on a
  different footprint.

### Gates
selfcheck 37 checks (new: missing-value policy, degenerate-fit refusal, vectorised dedup, manifest reader, SEASONS
in all 45 notebooks); preprocessing gate runs build_manifest and times the dedup; 45/45 models run, 38 honour the
scenario, 7 documented data gaps.

## v20.13 -- missing values were reaching EVERY estimator, not just M01
### What your files showed
Your M01 run (v20.11) wrote NaN for all six outcomes, and its trace says why: "GPU demeaning cross-check passed
(relative drift nan)". The demeaned outcome contained NaN. One missing value in an outcome or a covariate makes
that pixel's fixed-effect mean NaN, the cross-products NaN, and every estimate NaN. M02 died on the same thing one
step later: `LinAlgError: SVD did not converge` is what numpy's least squares says when its input has NaN.
v20.12 fixed the 2x2 estimator only; the event study, Callaway-Sant'Anna, DDD, matching and the rest have their own
paths and were still exposed.

### The fix -- one choke point
Every model loads its data with `load_panel(columns=C.columns_for(OUTCOME, ...))`. `columns_for` now records the
outcome and the covariates, and `load_panel` excludes -- per row group, while streaming -- any row where one of
them is not finite, printing the count (warning above 25 %). No estimator can now receive a NaN in the columns it
regresses on, whichever model it is. `finite_only=False` opts out for a model that handles missing values itself.
Belt and braces: the event study also filters and no longer raises "SVD did not converge" (normal equations with a
pseudo-inverse if least squares fails); a NaN GPU drift is reported as a failure instead of "passed".

### Callaway-Sant'Anna event-time table
Cells (g,t) with no comparison group (every unit treated by t) are correctly NaN -- but averaging them into the
event-time mean blanked the whole table. The aggregate now uses identified cells only and reports `n_cells` /
`n_cells_identified` per event time, with a warning naming how many cells had no comparison group.

### Gates
`validate_all_models.py` now injects 8 % missing NDVI and 5 % missing Rain into its panel, runs all 45 models, and
FAILS if any result file has all-NaN coefficients: 45/45 run, 38 honour the scenario, 7 data gaps, no NaN files.
selfcheck 41 checks.

### What to do with the run you have
Unpack v20.13 and re-run M01 and M02 -- the panel from PASS B is fine. Expect a line like
`missing-value policy: excluded N of M rows (x%) where ['NDVI','Rain','Tmax','Tmean','Tmin','LandUse'] is not finite`
in the log: that percentage tells you how much of the panel the missing weather/index values were silently
destroying before. The M02 warning "event times [3] absorbed" is a genuine coverage limit at the edge of the
window, not an error -- the coefficient is flagged identified=False.

## v20.14 -- any format, any file name, one INPUT_DIR
### What you asked for
1. PASS A now ingests **csv, csv.gz, tsv, parquet (.parquet/.pq), feather, xlsx, xlsm and xls** from INPUT_DIR at
   any depth, exactly as it merged CSVs. An Excel workbook is read sheet by sheet: every sheet whose columns are
   pixel data is a table (stacked); a notes / lookup sheet is skipped; a workbook with no pixel sheet (the
   crosswalk, the fund-release table) is reported as skipped, not failed. Lock files (`~$...`), hidden files, and
   anything under the output or temp folders are never read.
2. **File names may take any form.** The exact export convention is still recognised (with its site name); beyond
   that, a year (2010-2039) and a season word anywhere in the name, in any order, with any separators or extra
   words, are enough: `Artal 2022 rabi export (final v3).xlsx`, `2023-Kharif tile 07 copy.csv.gz`,
   `rabi_2024.parquet`, `Annual composite 2021.feather`. Season synonyms: monsoon = Kharif, winter = Rabi,
   summer = Zaid, annual = Yearly. A name that states only the year, or only the season, is completed from the
   columns; a name with NO key (`export_no_key_in_name.csv`) falls back entirely to the file's own Year / Season
   columns -- which is the fallback you asked for: no file is skipped for its name. A name with two different
   years is treated as keyless (ambiguous) rather than guessed. In a workbook with a keyless file name, a
   sheet named like a block (`2024_Rabi`, `2024 zaid`) carries its own key. Name-vs-column disagreements are
   logged in `unresolved_columns.csv`, with the name winning.
3. **One path.** `_paths.py` has a single `INPUT_DIR`; OUTPUT_DIR (= INPUT_DIR/output), TEMP_DIR
   (= output/_tmp_shards), the panel, results and estimator files derive from it and BOTH engines follow it, so
   the preparation and the 45 models always look at the same folders. `P.set_paths(r"D:\\...")` or
   `C.set_paths(...)` redirects one session; the active layout is written to `output/reward_paths.json` and
   printed at the top of P00. Override OUTPUT_DIR / TEMP_DIR in `_paths.py` only if you want them elsewhere.

### What the deep check found in the half-built version of this feature
- `run_pass_a` called `discover_input_files`, which did not exist -> PASS A would have raised NameError on its
  first line. Written now (`discover_input_files`), used by run_pass_a and by P00 / P01 / P02, which still globbed
  only `*.csv` and `*.parquet`.
- The two engines' `_apply_paths` called each other without end -> `RecursionError` the moment both were imported
  in one kernel (P08, or a model notebook after P00). Fixed with a one-hop propagation flag.
- The file-name regex was the rigid `CSV_[Site_]YYYY_Season_tileN` -- the opposite of "versatile". Replaced by the
  two-layer parser above; the strict layer is kept for site-name recognition.

### Verified (validate_preprocessing.py, run three times)
A folder of nine files in seven formats at three depths -- strict-named csv, awkwardly-named xlsx with two data
sheets and a notes sheet, parquet, .pq, csv.gz, tsv, a keyless csv, a workbook keyed by sheet names -- plus a
README, a lock file, a crosswalk-like workbook and a generated file under output/: discovery finds exactly the
nine, PASS A ingests every block with rows exactly as written, PASS B's panel holds every row, and the same
coordinates receive the same pixel_id whichever format they came from. Self-check 44 checks; 45/45 models run,
38 honour the scenario, 7 documented data gaps, no NaN result files.
- (v20.14, found by the gate on the second pass) importing one engine used to re-apply the `_paths.py` default to
  BOTH engines, silently discarding a `set_paths(...)` override -- every model in the gate then looked for the
  panel under the default path. Now an engine imported into a kernel where the other is already configured ADOPTS
  the live layout, and an import never overrides one. Verified in all three import orders; guarded by the
  self-check (45 checks).

## v20.15 -- the M02 warnings, and what your event-study table is actually saying
### The warnings (all mine)
- **"GPU demeaning cross-check FAILED (relative drift 8.68)"** -- a design flaw in the check, not in the GPU. It
  re-demeaned a random ROW subsample of the GPU residual on the CPU; in a random subsample most pixels have one
  row, so the CPU "re-demeaning" zeroed every value and the "drift" was just the size of the residual divided
  by its spread (0.16 / 0.018 = 8.7 -- your number). The GPU was right and was switched off for nothing. The
  check now demeans the SAME rows with both implementations and compares them.
- **"RuntimeWarning: invalid value encountered in divide"** -- `_codes()` took a categorical's own `.codes`, which
  keep every category of the frame the column came from; after a row filter the code space had empty groups
  (0/0). Codes are now re-factorised on the rows given: no empty groups, no warning, and CPU and GPU use the same
  code space. The GPU path also now leaves rows with a missing key untouched, exactly as the CPU path does.
- **"event times [3] numerically absorbed"** -- 2026 has no rows in the window; it is now listed with the note
  "no rows in the panel for this period -- not estimated" instead of a NaN row and a warning.

### What the table says (the important part)
Read the coverage columns you attached: in every period before 2025 there are **4,438 treated pixels**; in 2025
there are **881,995**. The two exports do not label the same pixels as the saturation core -- the 2025/2026
"Artal"-named export has a different footprint (and, per your counterfactual file, a different NDVI level: 0.58
against 0.37-0.40 in every earlier year). So:
- the leads and lags at -3..1 are estimated from the 4,438 pixels seen throughout (their ~1e-13 betas mean those
  pixels moved exactly with the controls, relative to 2022);
- the 2025 coefficient (0.217) is that population change and level shift showing up as an "effect" -- it is not a
  watershed impact.
The event study now says this itself. New columns per event time: `n_treated_pixels_also_in_ref`,
`n_control_pixels_also_in_ref`, `share_treated_pixels_also_in_ref` and a plain-language `identification_note`
("identified from 4,438 treated pixels also seen in the reference period; the other 877,557 appear here but not
there (different population)"), plus a warning whenever the treated population changes by more than 5x across
periods or fewer than half of the treated pixels are seen in the reference period.
New `BALANCED_PIXELS = True` in M02's CELL 1 (engine: `C.common_pixel_mask`) restricts the window to pixels
observed in every period, so the coefficients compare the same pixels with themselves. Verified on a synthetic
replica of your pattern: a true +0.05 effect is recovered at 0, 1 and 2 with and without the balanced option,
and the notes name the 800 period-only pixels.

### What to do
1. Re-run M02 with v20.15: the warnings are gone and the notes explain each coefficient.
2. Until the 2025/2026 export is reconciled with the earlier one (same footprint, same `buff_km` labelling, same
   index scale), report the event study with `BALANCED_PIXELS = True` and/or `POST_YEARS = 2` (2023-2024) -- the
   2025 coefficient is an export artefact under either reading.
selfcheck 49 checks; preprocessing gate clean; 45/45 models run.

## v20.16 -- which models can give a complete result on THIS data
`_readiness.py` + `P10_Model_Readiness.ipynb`: measures the prepared panel -- treated pixels per year and how many
of them are observed in the reference year, clusters, treatment cohorts among treated pixels, never-treated units,
treated cluster-level units, land-use groups, dose variation, per-outcome seasonal vs annual coverage, the external
inputs -- and classifies all 45 models as READY / READY_SETTINGS / LIMITED / BLOCKED with the reason and the
settings to use. Writes `results/MODEL_READINESS.md` and `.csv`; re-run whenever the panel changes.
`MODEL_READINESS_Artal.md` is the assessment for the current extract, derived from your logs (one fact, the
land-use split among treated pixels, is assumed and flagged; P10 measures it).
selfcheck 51 checks.

## v20.16 -- NaN AND zero cells are missing, everywhere; and a readiness assessment of the 45 models
### The policy (your request)
An exact 0.0 in an index or a weather variable is a masked / no-data cell in these exports, not a measurement
(a seasonal mean NDVI or Tmax of exactly zero does not occur in Karnataka). It is now treated like NaN:
- **Preparation (PASS A, before duplicates are resolved, and again in PASS B)** -- `apply_missing_policy()` sets
  NaN/0 cells to missing in every outcome and weather variable (`ZERO_RULE_VARS`; categorical/count columns such
  as LandUse or NObsV are never touched), so a second file's real value can fill the gap through the dedup
  coalescing, and a row left with NO usable outcome at all is dropped from the panel. PASS B prints the totals:
  "N NaN/zero cells set to missing, M rows with no usable outcome dropped". `ZERO_RULE_EXCEPT = ("Rain",)` in
  `_prep_common.py` would keep zero rainfall as a value if you ever want that.
- **Every model** -- `load_panel()` (the one place all 45 models pass through) excludes rows where the outcome or
  any estimation covariate is NaN or exactly zero, and reports "excluded N of M rows (x%) ... (k of them
  zero-valued)". The 2x2 and streaming estimators, the event study and `outcome_coverage()` apply the same rule
  through `_usable()`.
- Found and fixed while doing this: the streaming estimator read only the columns it regressed on, so it could
  not apply the rule to covariates it did not use and its sample differed from the in-memory path once a covariate
  had zeros. It now reads the policy columns and the two paths agree to 1e-16 (gate-verified).

### `readiness.py` / `C.model_readiness()` -- which models can run to a complete result on YOUR panel
Streams the real panel once and measures every prerequisite the 45 models rely on: treated and control pixels
per year, the pixels present in every year, pre and post periods, cohorts (`first_treat_agri_year`), dose
variation, switchers, land-use classes, clusters and treated clusters, coordinates, the external files (M07,
M08), and per outcome how many usable values exist in the seasonal blocks vs the annual composite. Writes
`MODEL_READINESS.csv` + `MODEL_READINESS_facts.json` next to the panel and prints:
    RUN      every prerequisite met
    LIMITED  runs, read with the panel-wide caveats printed once above the table
    BLOCKED  a prerequisite is missing -- the model refuses by design, with the reason and what would unblock it
P09 now runs it as its last cell, so every panel build ends with this table. Gate: it classifies all 45 models
on the synthetic panel with 8 % NaN + 4 % zero NDVI and 3 % zero Tmax; 45/45 models still run, no NaN results.
selfcheck 54 checks, preprocessing gate clean, model gate clean -- looped twice, identical.

## v20.17 -- NaN AND exact-zero cells are no-data, everywhere, and it is proven end to end
### The rule (one place, both engines)
`ZERO_AS_MISSING = True`: an exact 0.0 in any outcome index or continuous weather covariate is a masked / no-data
cell, not a measurement. `ZERO_RULE_VARS` = the 17 outcome indices + Rain, Tmax, Tmean, Tmin; `ZERO_RULE_EXCEPT`
lists variables where 0 IS a value (empty by default -- see the Rain note). LandUse, counts and flags are never
touched. `DROP_ROWS_WITHOUT_OUTCOME = True`: a pixel-season with no usable outcome at all leaves the panel.

### Where it acts
- PASS A, per file, BEFORE duplicates are resolved -- so a zero in one export is filled by the real value of the
  other export during coalescing instead of being carried into the panel.
- PASS B, per block, once more after coalescing; then it MEASURES what is left per variable and writes
  `panel_missingness_report.csv` (Year x Season x variable: rows, finite, missing, share, zero_after_policy) and
  REFUSES to write a block in which a zero survived.
- Every model: `load_panel` (the one path all 45 models use) excludes rows where the outcome or a covariate is
  NaN or zero and reports both counts separately ("excluded 2,800 of 15,120 rows (18.5%) ... 945 of them
  zero-valued"); `_finite_rows` applies the same rule inside the 2x2, streaming and event-study estimators.
- Rain: a whole-season mean of exactly 0.0 from CHIRPS/ERA5 is almost always a mask, so it follows the rule; if
  your `panel_missingness_report.csv` shows Rain missing on more than 1 % of rows PASS B now warns and tells you to
  set `P.ZERO_RULE_EXCEPT = ("Rain",)` if those are genuine dry seasons.

### Proven, not assumed
`validate_preprocessing.py` now injects into the synthetic exports 10 % exact-zero NDVI, 5 % zero Tmax, 5 % NaN
LAI and rows with every outcome zero, runs the real PASS A + PASS B, and asserts on the FINAL panel: 0 exact zeros
across the 21 policy variables, 0 rows without an outcome, the report present with the counts. `validate_all_models.py`
injects 4 % zero NDVI and checks, after `load_panel`, that the estimation columns contain neither NaN nor zero and
that the zero count was reported -- then runs all 45 models (45/45 run, no NaN result files). Self-check 56 checks.

## v20.18 -- the M34 log: two fixes and one finding
### Fixes
- `RuntimeWarning: invalid value encountered in sqrt` (event-study SE inside HonestDiD): the cluster-robust
  sandwich is PSD in exact arithmetic, so a negative diagonal is cancellation on a coefficient whose regressor is
  (nearly) absorbed. It is now clipped to zero and that coefficient marked `identified = False`; no NaN, no warning.
- "breakdown M* = 0.00 -> FRAGILE": wrong reading. The sensitivity question only exists if the effect is
  significant with parallel trends assumed (M = 0). If it is not, there is no finding to erode. The engine now
  returns a verdict -- NOT SIGNIFICANT at M=0 / FRAGILE (lost below 1x the largest pre-trend violation) /
  ROBUST (survives up to M*) -- and M34 prints and saves it (`base_significant_at_M0`, `max_pre_violation`,
  `verdict`). Your run is the first case.

### The finding
Your log now reads "548 treated pixels in some periods vs 465,714 in others". Before the no-data rule the same
panel showed 4,438 core pixels in 2015-2024; after treating NaN and exact 0 as missing, only 548 of them carry a
usable NDVI. So roughly 88 % of the saturation core's rows in the 2015-2024 export are masked, while the 2025
export has 465,714 usable core pixels. Every pre-2025 estimate in every model currently rests on those 548
pixels -- an unmasked remnant of the core, not the core.
`panel_missingness_report.csv` now splits every variable by treated core vs control rings
(`finite_core`, `share_missing_core`, `finite_rings`, `share_missing_rings`, `rows_core_dropped_no_outcome`) and
PASS B prints "NDVI: no-data share in the TREATED CORE x% vs the CONTROL RINGS y%", warning when the core is the
masked side and naming the fix: re-export 2015-2024 for the core with the current exporter (v111). The readiness
assessment carries the same warning.
selfcheck 59 checks.

## v20.19 -- M16 `LinAlgError: Singular matrix`: a specification bug in the pre-trends test
The joint pre-trends F test restricted its sample to the lead years only (event times -4..-2) and then included a
dummy for EACH of them. Inside that sample the lead dummies add up to the treated indicator, which is constant
within a pixel and absorbed by the pixel fixed effect -- the columns were exactly collinear, the cluster-robust
covariance had no inverse, and `np.linalg.solve` raised. It only ran before through floating-point noise; the
548-pixel sample made the singularity exact. The test now keeps the REFERENCE period (event time -1) in its
sample, so each lead is identified as a change relative to it -- the event study's normalisation -- and it also:
- drops a lead whose regressor is absorbed (no treated pixel seen both at that lead and at the reference, or no
  within-pixel variation) and reports why;
- caps the number of restrictions at the rank of the cluster-robust covariance (at most G-1 with G clusters),
  using a pseudo-inverse and F(rank, G-1), with a warning when the window asks for more leads than the clusters
  can support;
- refuses cleanly when the reference period has no treated rows.
M16 now prints the leads tested and dropped, each lead's coefficient and SE, and saves them flat in
`pretrends_ftest_<outcome>.csv`. Verified: parallel trends -> F=1.42, p=0.34 (not rejected); a real 0.02/year
pre-trend -> p<0.0001 (rejected); 3 leads with 3 clusters -> 2 restrictions tested with a warning; no treated rows
in the reference -> refused with the reason. selfcheck 60 checks.

## v20.20 -- no placeholder values, anywhere
Until now an outcome that could not be estimated (e.g. ESI / RUSLE / WSI / WSSI under the seasonal scenario) still
produced `canonical_twfe_<X>.csv` -- a row of NaN with `status = EMPTY_RESULT`. That is a placeholder, and your
results folder shows 34 M01 files where only 13 outcomes were estimable. From now on:
- `save_results` REFUSES a row whose estimates are all NaN, any cell holding a placeholder token (TBD, N/A, dummy,
  null, '-', ...), or an empty table -- it raises a data-gap error, the notebook reports it, and nothing is written.
- the refused outcome is recorded once in `NOT_ESTIMATED.csv` in the model's scenario folder (model, scenario,
  outcome, reason, time) -- so the folder still tells you what was NOT estimated and why, without a fake result.
- the model gate scans every result file of the 45-model run for placeholder tokens, EMPTY_RESULT rows, empty
  files and NaN-only estimates: "no result file contains a placeholder value or an EMPTY_RESULT row".
Self-check 62 checks (adds a live test that a NaN-only and a 'TBD' result are refused and never written).

## v20.21 -- what your result files revealed: a FROZEN series, and the guard that now catches it
### The evidence (your M01 / M02 / M16 / M34 files, NDVI, NDRE, NDMI)
- Every lead and lag before 2025 is exactly zero: |beta| <= 2.6e-14 with SE ~8e-11, although the regressor has a
  normal spread (sd 0.021). A genuine null would have an SE of ~1e-3. The pre-trends F is exactly 0.0 (p = 1.0);
  HonestDiD's "largest pre-trend violation" is 7e-15. The same in all three indices.
- Only 2025 carries a real number (NDVI +0.0037, SE 0.0016) -- identified from 6,302 treated pixels also seen in
  the reference year, against 733,797 that appear in 2025 only; the treated-group NDVI level jumps 0.235 -> 0.404
  between 2024 and 2025.
- M01's pooled -0.0027 (t = -8.3) is therefore driven by the 2025 rows (752,413 of its 790,225 treated-post rows,
  95 %) and by the weather covariates; without covariates the sign flips (+0.0010).
Real data cannot produce 1e-14: it means the outcome does not change WITHIN a pixel between the pre-2025 years
at all -- the 2015-2024 export most likely wrote one composite under many dates. That is an export problem,
and it is the reason every pre-2025 estimate looks "perfectly null".

### What the pipeline now does about it
- `C.within_pixel_variation('NDVI')`: on a fixed 1-in-100 pixel sample, the share of pixel-years whose value is
  identical to the same pixel's previous year, per season, treated core vs control rings, plus the within-pixel SD
  across years; flags FROZEN at >= 50 %. P06 runs it for the selected outcomes and writes
  `within_pixel_variation_<outcome>.csv`.
- `_frozen_treated_guard`: the 2x2 (M01), the event study (M02 and everything built on it -- M34, M15, M12) and
  the pre-trends test (M16) now REFUSE a fit in which the treated pixels' pre-period rows carry no within-pixel
  change (median within-pixel SD < 1e-6 of the outcome's spread, or > 50 % of treated pixels constant), naming the
  cause and the diagnostic. Live post-period rows can no longer mask a frozen baseline (this is how M01 produced
  a "significant" number).
- Verified on a replica of your files' pattern (all pixels frozen 2018-2024, live 2025 with a level jump): all
  three estimators refuse; on normal data they return the true effect (+0.049 / +0.051, pre-trends p = 0.28).
  The model gate builds the frozen case from its own panel and requires all three refusals. selfcheck 63 checks.

## v20.22 -- both pipelines, both languages, and the 20-site structure
- `data/sites/` ships `SWSs20_KarnatakaAll5k` (120 polygons: 20 cores + 5 rings each) and `sites.csv` built from
  it by `_sites.py`: SWSiD_All, name, phase (Saturation Ph 1 = 11 sites, Ph 2 = 9 incl. Artal), treatment_year.
  Two phases = two cohorts once pooled: the staggered estimators become identified and clustering by site gives
  20 clusters. FILL Phase 1's treatment year before a pooled run.
- Engine: `SWSiD_All` (any spelling) is ingested and typed as `site_id`; the dedup key is (site_id, pixel_id, Year,
  Season) so overlapping rings of neighbouring sites are kept in both; every model loads site_id. Scenario gains
  `use_site_years` (each site on its own year -> post / did / event_time / cohort site-specific; rings = never
  treated), `cluster='site'`, `pooled_fe='site_period'`; `C.run_sites(model_fn)` runs one model per site then
  pooled (P11 notebook); `C.export_for_packages(outcome)` writes the tidy package-input table (schema in
  PIPELINES_GUIDE.md). Verified: 3 sites / 2 phases -- per-site and pooled recover the true effect, Callaway-
  Sant'Anna identified at every event time with the rings as never-treated; 45/45 models run with site_id present;
  a two-site export through PASS A/B keeps both sites and never merges a shared coordinate across sites.
- Pre-built pipelines, complete start to end: `R/RUN_ALL.R` (fixest 2x2 / event study / Wald pre-trends,
  fwildclusterboot with Webb weights, pooled site^period, did::att_gt on site cohorts, HonestDiD relative-
  magnitudes + smoothness + FLCI) and `python_prebuilt/pf_pipeline.py` (pyfixest + wildboottest, same models
  minus CS/HonestDiD). Same results layout under results/prebuilt_R and results/prebuilt_pyfixest; each has a
  `--smoke` mode that compares its 2x2 with the engine on identical rows and stops on disagreement. NOT executed
  here (no network / R) -- run the smoke test first.
- selfcheck 64 checks; preprocessing gate covers SWSiD_All and site-aware dedup; model gate runs 3 sites + pooled
  and checks the package-input invariants.

## v20.23 -- speed, accuracy, and every model in both pre-built pipelines
### Why it was slow on an A40 / 64 cores / 500 GB
The event study demeaned the outcome and EACH event-time dummy in a separate pass over the panel -- seven full
alternating-projection runs of 22.7 M rows on the GPU, each re-factorising the fixed-effect keys from their string
values. Now: (1) keys are factorised from their integer category codes (a 3 M-row categorical: 0.11 s, once);
(2) `demean_columns()` demeans a whole matrix -- outcome, treatment terms, covariates -- in ONE loop: on the GPU
one `index_add_` per fixed effect per sweep handles every column; on the CPU a sparse group-mean operator does
the same (the fixest approach). The event study and the 2x2 use it. Verified identical to column-by-column to
1e-12 (including rows with a missing key); memory and streaming 2x2 agree to 1e-9 for every covariate set.
Expect the event study at roughly the cost of one demeaning pass instead of seven.

### Accuracy (added to the engine)
- **Webb bootstrap weights** (auto below 12 clusters): with 6 clusters Rademacher weights allow only 64 distinct
  bootstrap samples, so p cannot resolve below ~0.016 and is biased upward; on the same data p = 0.005 (Webb)
  vs 0.035 (Rademacher). `wild_cluster_bootstrap_pvalue(weights="auto")`.
- **t(G-1) inference** in every 2x2 result: `p_t_G1`, `ci95_low_tG1`, `ci95_high_tG1` (normal-based p-values are
  too small with 7 clusters).
- **Absorbed-covariate rule**: a covariate whose within-(pixel x period) SD is below 1e-8 of its raw SD is dropped
  in BOTH estimators (a constant-within-pixel covariate such as LandUse used to survive an absolute 1e-12 test as
  a near-zero column that made the design ill-conditioned and shifted beta in the 5th digit).
- **Covariates x post** (`covariates_by_post=True` / `C.COVARIATES_BY_POST`): linear covariates in a TWFE impose
  one covariate effect before and after treatment, which does not respect conditional parallel trends
  (Sant'Anna & Zhao); the interaction lets each covariate carry its own trend across the cutoff.
- Package input now carries latitude, longitude and dose (spatial and dose-response models).

### Pre-built pipelines, all models (see PREBUILT_MODEL_MAP.md, sourced online)
- Python: `python_prebuilt/pf_pipeline.py` (pyfixest + wildboottest), `dd_pipeline.py` (diff-diff: 2x2, event
  study, Callaway-Sant'Anna, Sun-Abraham, stacked, BJS imputation, synthetic DiD, continuous DiD, Bacon,
  HonestDiD, pre-trend slope test), `ml_spatial_pipeline.py` (EconML LinearDML / DRLearner / CausalForestDML /
  S-T-X learners, DoubleML, esda Moran + LISA) and `run_prebuilt(outcome)` which runs everything that applies
  after the 2x2 smoke comparison with the engine.
- R: `R/models_prebuilt.R` registers DRDID, qte::CiC, fixest::sunab, DDD, DIDmultiplegtDYN, MatchIt, WeightIt ebal,
  spdep, lme4/performance ICC, metafor Q/I2, bacondecomp, ritest, didimputation, did2s, did::aggte(group), stacked,
  etwfe, quantreg, fect (ife / mc), gsynth, grf causal forest (clustered), DoubleML, bartCause, synthdid (site
  level); `run_models("NDVI", ids)` from RUN_ALL.R. M07/M08 need external files; M44 has no maintained Python
  implementation (R only); M45 is site-level only.
- Unit-period collapse (pixel-year means) for the staggered / factor packages, long differences for the ML
  packages -- both stated in PREBUILT_MODEL_MAP.md so the paper can say what was estimated on what.
NOT executed in the environment that produced the bundle (no network / R); each Python layer parses and the
orchestrator runs the smoke comparison first.
selfcheck 69 checks.

## v20.24 -- P08 ground linkage fixed; the ANNUAL composite leads every estimate
### The P08 error
`GROUND_INPUTS_DIR` was a fixed `D:\LKT\survey\REWARD_ground_inputs`, but the 16 harmonised ground inputs ship
INSIDE the bundle (`FINAL/REWARD_ground_inputs`). STEP 2 could not find them, STEP 3 neither, and STEP 4 then
crashed on the missing result (`'NoneType' object has no attribute 'copy'`). Now:
- `resolve_ground_inputs_dir()` finds the shipped folder from the engine's own location (it is two levels up in the
  bundle), then INPUT_DIR / OUTPUT_DIR, then the old path; `_paths.GROUND_INPUTS_DIR` overrides.
- P08 prints where the inputs are (16/16), and when they are genuinely absent it stops after CELL 1 saying where it
  looked and what is missing -- no cascade. STEP 4 refuses cleanly if STEP 2 produced nothing.
- The M07 ground-truth file was also hard-coded to `D:\LKT\survey\...`; it and the M08 instrument now follow
  INPUT_DIR (`<results>/P08/ground_truth_outcomes.csv`, `<INPUT_DIR>/rollout_instrument.csv`).
- P08 takes pixel coordinates from EVERY season of the link year (the annual composite has the fuller footprint)
  instead of Kharif alone.
Verified end to end on the shipped inputs: 768/768 benchmark site-variable rows snapped, 44 survey polygons
linked, ground_links.parquet and the M07 file written; and the missing case stops cleanly.

### Yearly-first (your request)
Your annual composite is complete for every year and the seasonal rows are not, so `SEASONS = "auto"` is now the
default in the engine and in all 46 notebooks: each outcome is estimated on the annual rows (pixel + year FE);
weather covariates the annual composite lacks are filled from the same pixel-year's seasonal mean (in load_panel
and in the streaming estimator); an outcome without annual values falls back to its seasonal rows; every result
carries `seasons_used`; results go to `..._yearly/` folders. P00 gains STEP 8 (`season_choice_report.csv` + the
yearly-first scenario saved for every model). An old `did_scenario.json` whose "seasonal" was only the previous
default no longer pins the models to seasonal rows.
Verified on a panel with treatment-correlated seasonal gaps and annual rows WITHOUT covariates: NDVI on annual
rows +0.0502 (true 0.05) with half the seasonal SE, streaming identical to 1e-9; LAI (no annual values) fell back to
seasonal; all 45 models ran through the covariate fill (20,014 values filled), no NaN or placeholder results.

### Found and fixed while doing it
- The frozen-series guard only examined treated pixels with >= 3 pre-period rows. Seasonal data always has 3 per
  year; on annual windows the event study and pre-trends test have 2, so the guard silently did nothing there
  (the model gate showed 1/3 refusals). Now >= 2 rows and the reference period is part of the test: 3/3 on
  annual and seasonal data.
- An earlier unfinished draft of this change resolved 'auto' once per session and cached it in the scenario (stale
  when the panel changed) and never touched the notebooks, which all still forced "seasonal" -- the request would
  not have reached a single model. Both fixed; the self-check now fails if any notebook defaults to seasonal.
selfcheck 75 checks; preprocessing gate adds P08 end-to-end and the season report; model gate asserts yearly-first.

## v20.25 -- pixels that overlap >= 80 % (or coincide) are ONE pixel
### Why
`pixel_id` is a pure function of the coordinate rounded to 1e-5 degrees (~1.1 m). Two Earth Engine exports that
sample the same physical 10 m pixel on grids a metre or two apart therefore gave it TWO ids: it was counted twice
in a block, and across years it looked like two different pixels -- which breaks the within-pixel comparison every
DiD rests on (and is one plausible reason the 2025 "Artal" export looked like a different treated population).

### What PASS B now does (before any block is processed)
1. `pixel_registry`: one row per pixel id across ALL blocks and years -- mean coordinates, newest file time,
   completeness (usable outcome cells per row), newest source file. Shards are scanned in parallel threads.
2. `near_duplicate_pairs`: every pair of different ids whose square footprints overlap by >= `PIXEL_OVERLAP_MIN`
   (0.80). Overlap of two squares offset by (dx, dy) = (1-|dx|/s)(1-|dy|/s), s = `PIXEL_SIZE_M` (10 m) -- so a
   2 m shift along one axis is exactly 80 %; pixels of one regular grid (10 m apart) never pair. Spatial hash on
   s-metre bins, linear in the number of pixels (2 M pixels / 1 M pairs: 4 s).
3. `canonical_pixel_map`: greedy and chain-free -- pixels in priority order; each unassigned pixel becomes canonical
   and takes the pixels that overlap IT directly (A-B 85 % and B-C 85 % never pull C onto A when A-C is 70 %).
4. Each block remaps those ids (and coordinates) onto the canonical pixel; the existing duplicate resolution then
   keeps ONE row per (site, pixel, Year, Season) and fills its gaps from the dropped row.
Which row / pixel wins is your choice: `DEDUP_PRIORITY = "newer"` (default -- the newer export, then the more
complete row; the rule used so far) or `"complete"` (the more complete row, then the newer export). Settings sit in
the PASS B cell of P00 / P04. Reports: `pixel_overlap_report.csv`, `pixel_overlap_map.parquet` (every merged pixel,
its canonical twin, the overlap), `pixel_overlap_by_export_pair.csv`, `pixel_grid_spacing_by_export.csv` (the grid
spacing actually measured per export, with a warning if it differs from PIXEL_SIZE_M).

### Consistency safeguards (so the change actually reaches the models)
- The panel records how it was built (`panel_build_settings.json`); a panel built without the merge -- your current
  one -- is rebuilt by P00 (`ACCEPT_PANEL_WITHOUT_PIXEL_MERGE = True` keeps it).
- Per-variable estimator files older than the panel are never read (models fall back to the panel and say so) and
  P09 rebuilds them. Before this, a model picked its per-variable file whenever it existed, so a rebuilt panel
  could be silently ignored.

### Verified
Two exports on grids 1.0 m / 0.6 m apart (overlap 0.846): 288 ids -> 144 physical pixels, every one continuous
2022-2024; one row per 2023 cell with the NEWER export's values and LAI filled from the older row; with
"complete" the complete older export wins; one coordinate per id. With merging off the old behaviour is unchanged
(288 ids, double rows). A 3 m offset (70 %) stays two pixels; a regular grid never merges; no chaining.
All earlier gates unchanged; selfcheck 77 checks.

## v20.26 -- treatment year 2022 (works started 2022, start month not known)
### The design
2022 is the year the works STARTED. Without the month, the 2022 annual composite is partly before and partly after
the works, so it belongs to neither period: **pre = 2015-2021, post = 2023 onwards, 2022 left out of every pooled
estimate**; the event study measures every year against 2021 (event time -1), with 2022 absent. This is the
default in the engine, in all 47 notebooks (`TREATMENT_YEAR = 2022`, `EXCLUDE_TRANSITION_YEAR = True`) and in P00
STEP 8, which records it for every model. `EXCLUDE_TRANSITION_YEAR = False` counts 2022 as post instead (a
robustness check -- results go to a separate `..._treat2022` folder; the default is `..._treat2022_noTransition`).
If the month becomes known, the transition rule can be narrowed to the seasons before it.

### Two real defects found on the way
- The default scenario was internally inconsistent: treatment year 2022 but post from 2023 (a leftover spec that
  counted 2022 as PRE), while the notebooks said 2023. Now one consistent default.
- `exclude_transition_year` did not exclude anything. It zeroed the pre/post flags but left the transition rows
  in the regression (where did = 0 made them act as untreated periods), started the post period AT the treatment
  year and ended the pre period two years early -- silently dropping 2021, the last clean baseline year. Fixed in
  both engines and in the streaming estimator (memory and streaming stay identical): the transition year leaves the
  sample (`transition_year = 1`), pre < treatment year, post >= treatment year + 1; per-site transition years
  under `use_site_years`.

### Verified (works started mid-2022: the 2022 value half-treated, true effect +0.050)
| design | mean over 40 simulated panels |
|---|---|
| 2022 excluded (new default) | **+0.0497** |
| 2022 counted as post | +0.0435 (13 % toward zero) |
| old default: 2022 counted as pre | +0.0468 |
Event study with 2022 excluded: leads -0.001..+0.001, lags +0.048..+0.053 against 2021.
Also: a `did_scenario.json` written before this version (treatment 2023, or post from 2023) no longer pins the old
timing -- its seasons are adopted, its timing is not, and it says so; re-run P00 STEP 8 or P09 to record 2022.
Sites registry: Phase 2 (Artal) = 2022; Phase 1 still to be filled if it differs. Readiness: clean pre 2015-2021,
clean post 2023-2024 (2025 still flagged). selfcheck 79 checks.

## v20.27 -- the DiD-ready panel follows your coding rules exactly, and proves it
### The rules (default in both engines, every notebook and P00 STEP 8)
- **Buffer 0 = treatment area; buffers 1-5 km = control area.** `treatment = 1{buff_km == 0}`,
  `control = 1{buff_km in 1..5}`; any other code is in neither group.
- **2022 is the treatment start year: pre = Year < 2022 (0), post = Year >= 2022 (1).** `did_term = treatment x post`.
  (v20.26 had made holding 2022 out the default; per your specification 2022 is now the first post year.
  `EXCLUDE_TRANSITION_YEAR = True` keeps that as a robustness check, into its own `_noTransition` folder.)
In the panel the period flag is the `post` column -- identical to your Treat definition; `treatment` / `control` are
the groups; `did_term` is their product. The panel never takes the period from the exported flag: it is computed
from Year by the rule.

### Defects found and fixed while enforcing them
- **The export's `Treat` was checked against the wrong thing.** The exporter writes Treat as a PERIOD flag (1 for
  every pixel from 2022), but the panel's QC flag compared it with the treatment AREA (buffer 0), marking every
  treated pixel before 2022 and every control pixel after it as a "mismatch". Now `treat_period_mismatch_flag`
  checks Treat against 1{Year >= 2022} (an export made with another year or rule shows up here); the misnamed
  `treat_buffkm_mismatch_flag` is gone from the schema and the manifest (`pct_treat_period_mismatch`).
- **Text buffer codes were silently dropped.** `load_and_harmonize` cast `buff_km` to a number before any check,
  so "1 km", "Buffer_3" or "ring-4" became blanks and fell out of both groups. `recode_buff_km` now runs at
  ingestion: numbers (1.0, 2.0000001 from sampling a float band) go to the nearest ring when within 0.01; text
  keeps its ring number (a hyphen after a word is a separator, a leading minus is a sign); anything else or outside
  0-5 becomes -1 = neither group. Every recode is logged per file.
- **An export without a Treat column was rejected outright** ("missing essential columns"), although the panel
  never needs it. It is now derived from the rule and logged.

### The proof, written with every panel
PASS B checks every block before writing it -- treatment == buffer 0, control == buffers 1-5, never both,
post == 1{Year >= 2022}, pre == 1{Year < 2022}, did == treatment x post -- and REFUSES to write a block that breaks
any of them. `panel_design_check.csv` holds rows per Year x Season x buffer x group x period, the run prints the
group x period table, and warns on invalid buffer codes and on exported Treat flags that disagree with the rule.
Verified on a messy export: "1 km" / 2.0000001 / "Buffer_3" / "ring-4" -> rings 1-4 (control), 0 -> treatment,
7 -> neither; 0 design violations; an export flagged with the wrong year caught on all 7 of its 2022 rows.
selfcheck 81 checks.

## v20.28 -- every pixel located in the 20-SWS shapefile
### What it does
PASS A now locates every row of every file in `SWSs20_KarnatakaAll5k` (20 SWS x core + five 1-km rings, shipped in
`data/sites/`) **before de-duplication**, so rows of neighbouring sites whose rings overlap stay separate:
| site_check | when |
|---|---|
| 0 confirmed | the SWS the data indicates (SWSiD_All column, SUBWSHED / SWS-name column, or folder name) holds the pixel |
| 1 corrected | the pixel lies in a different SWS -> that SWS's id, name and ring (buff_km) are assigned |
| 2 assigned | the data names no SWS -> the SWS whose polygon holds the pixel |
| 3 outside | the pixel lies in no polygon -> kept with the data's id, flagged |
The panel gains `sws_name` and `site_check` next to `site_id`; `site_tagging_report.csv` has one row per file.
`P02b_SWS_Tagging_Audit.ipynb` scans the whole directory (default `D:\LKT\MIDline_KSRSAC_DP\Data\SWSs20Final`, any
format, any depth, all cores) and can write tagged Parquet copies with verified `SWSiD_All` / `SUBWSHED` columns under
`tagged_inputs/` -- original files are never modified. `BUFF_FROM_GEOMETRY = True` takes buff_km from the polygon
ring everywhere (default: only where the SWS was corrected or assigned; other disagreements are reported).

### How (no GIS library needed)
`_sws_geometry.py`: a pure-Python shapefile reader; WGS 84 -> UTM 43N by the Krueger series (Karney 2011), read from
the .prj; even-odd point-in-polygon with edges indexed by horizontal band (holes and multi-part polygons handled).
Verified: the projection agrees with Snyder's independent formulas to 0.2 mm over 74-78.5 E, 11.5-18.5 N and
round-trips exactly; point-in-polygon matches matplotlib's C implementation on 240,000 points in six polygons
including 150-220-part ones, 6x faster; 0.9 M points/s per core (~0.17 s for a typical export file).
Real data: of 137 ground benchmark sites recorded in one of the 20 SWS, 121 fall in that SWS's polygons, 16 in no
polygon (the Artal soil-moisture / LAI stations 22-25 km outside the 5 km envelope -- the known coordinate error in
the ground data -- and two borewells just outside), and **none in a different SWS**.

### Defects found and fixed on the way
- A `SUBWSHED` (SWS name) column was fuzzy-matched to `SubwshedID` -- the numeric micro-watershed id used for
  fixed effects and clustering -- so its text would have blanked that id. Name columns now map to `SWS_Name`.
- Partial name matching let "Chhatrakodihalli ..." resolve to "Kodihalli"; the longest contained name now wins.
- In a pooled export (all SWS in one file) PASS A de-duplicated before the site was known, which would have merged a
  pixel shared by two sites' rings. The site is now tagged first.

### DiD
`C.site_design_table()` (printed by P11): per SWS -- name, phase, start year, treated / control pixels, rows before /
from the start year, and match quality. The 20 SWS are 20 clusters (`cluster='site'`) and strata (`pooled_fe=
'site_period'`, per-site runs via `C.run_sites`); **cohorts are distinct start years** -- with every SWS starting in
2022 the pooled panel is one cohort; fill per-site years in `data/sites/sites.csv` where they differ and the staggered
estimators (M05/M09/M27/M31) switch on. The package-input tables carry `sws_name`; descriptive columns (`sws_name`,
`site_check`, coordinates, dose) are read when present and never required, so panels built before this version
keep working (the model gate caught the export failing on an older panel before this was fixed). selfcheck 83 checks.

## v20.29 -- your P09 / P10 / P11 errors fixed at the root; all years + seasons with pixel x season FE; your covariates; packages verified before use
### The errors you hit
- **P09 "Table schema does not match"** -- the per-variable file writer decided each chunk's column type from that
  chunk: `first_treat_agri_year` became int16 in chunks without blanks and float in chunks with them, and the file
  (whose schema the first chunk fixed) refused chunk 38. Now always float32, and every later chunk is cast to the
  file's schema. Reproduced with the v20.27 code before the fix. My gates had missed it because the sandbox stand-in
  for pyarrow did not check column types; it now rejects mismatched chunks exactly like pyarrow 23.
- **P10 / P11 "name 'C' is not defined"** -- built from a bootstrap snippet cut just before the engine import. The
  same defect was in P02b and in M40-M45 (import after first use). Fixed in every notebook; a new gate,
  `validate_notebooks_cold.py`, starts every notebook in a fresh process from its own folder with nothing injected
  -- my other gates inject the engine, which is why they were blind to this. 62 notebooks also relied on Jupyter
  having pre-loaded `importlib.util`; they now import it themselves (plain Python / VS Code / papermill work).

### All years and all seasons, with year, season and pixel fixed effects
- `SEASONS = "all"` (default): the annual composite AND Kharif / Rabi / Zaid rows, every year.
- `UNIT_FE = "pixel_season"` (default): one fixed effect per pixel x season series (each pixel's annual, Kharif,
  Rabi and Zaid level) plus one per year x season (which contains the year and the season effects). Evidence: when
  cloud gaps fall on pixels with distinctive seasonal profiles, one FE per pixel was biased 22 % toward zero
  (+0.039 vs a true +0.050, 12 simulated panels); pixel x season stayed exact (+0.0499) and 4x more precise.
  Applied in the 18 estimators where the unit is a fixed effect / panel unit -- never in permutation inference,
  matching, weighting, ML or masks (treatment is assigned per pixel). Streaming == in-memory to 1e-9. Chained DiD
  (M12) links each season series year to year. `UNIT_FE = "pixel"` and `SEASONS = "auto" | "yearly" | "seasonal"`
  remain. An older saved scenario's seasons (the previous default) are not adopted; v20.29 files are honoured.
- R engine, R scripts, R notebooks, pyfixest / diff-diff / ML pipelines use the SAME unit (the package input
  carries `unit` as a compact int32 code: R cannot hold every 17-digit pixel id exactly as a double).

### Your covariates
`COVARIATES = [...]` in every notebook's CELL 1, P00 STEP 8 and P09 (saved with the scenario, so P09's choice reaches
every model). One shared list every estimator reads; only the chosen covariates drop rows for missing values; each
covariate set gets its own results folder (`_covRain-Tmax`, `_covNone`); outcome variables are refused as covariates
(the works can change them -- bad controls; `allow_outcome_covariates=True` overrides).

### Pre-built packages -- verified on YOUR machine before they compute
2x2 TWFE, the event study and the wild cluster bootstrap hand over to **pyfixest**, Callaway-Sant'Anna to
**diff-diff** -- inside the engine functions, so every notebook that calls them uses the package. A package computes
only after **P12** has run it against the validated engine on a known-answer panel (true +0.05, 2022 start, annual +
seasonal rows, pixel x season units) and they agreed (estimates to 1e-6, SE within 10 %, bootstrap p within 0.1);
the verdict is stored per package VERSION in `prebuilt_verified.json`. Unverified, missing or failing -> the engine
computes and says so; every result carries `engine`. `PREBUILT_MODE = "auto" | "require" | "off"`. The engine's
data checks always run first. None of these packages can be installed where this bundle was built (no network), so
the package code is exercised here only with stand-ins; P12 is where it is proven.

### Found and fixed on the way (the old validation suite, now running again)
- `V00_RUN_ALL_VALIDATIONS.py` could never start (hard-coded old folder name); fixed and updated to the current
  specification: 28/28 pass, 3 skipped (files from an earlier session, Windows-only paths).
- Two regressions in this version's own unit column, caught before shipping: a blank pixel id crashed it, and text
  ids collapsed every pixel into one unit (estimate 0.348 vs 0.5). Both fixed (0.501).
- **Fund-release -> first treated season** used the legacy calendar under the exporter's labels: releases in Oct-Feb
  mapped to a PAST season, Mar-May releases to a season a YEAR late (Nov 2021 -> Zaid 2021; Apr 2022 -> Kharif 2023).
  Now Zaid Y -> Kharif Y -> Rabi Y -> Zaid Y+1; every next season starts after its release. Affects P05 timing / dose.
- **R engine** still had post from 2023 (2022 as pre), an old transition rule, and event time from 2023; now
  identical to Python.
- The event-study cross-check revealed nothing wrong in the engine (exact to 1.8e-15 on its window) -- the first
  mismatch was my verification comparing different row sets, now fixed.
selfcheck 90 checks; cold-start gate 64/64 notebooks; validation suite 28/28.

## v20.30 -- covariates per model, no negative covariates, memory first
### Covariates are chosen in each MODEL, never at panel preparation
- Each model notebook's CELL 1: `COVARIATES = "all"` (Rain, Tmax, Tmean, Tmin, LandUse) | `"mean_temp_rain"` (Tmean + Rain)
  | `"weather"` (Rain, Tmax, Tmean, Tmin) | `"none"` | or your own list, e.g. `["Rain", "Tmean"]`.
- P00 STEP 8 and P09 no longer set covariates, and a saved panel scenario never carries or overrides them.
- The panel and every per-variable file keep ALL covariate columns and every row: only the model's choice decides
  which covariates enter its regression and which rows its missing-value rule drops (P09 used to write only the
  covariates chosen at that moment). Each covariate set still gets its own results folder (`_covMeanTempRain`, ...).

### No negative covariates -- prepared at panel level, with a switch
- Rain cannot be negative and this region never sees sub-zero temperatures, so during preparation (PASS A) negative
  Rain / Tmax / Tmean / Tmin become **0** -- AFTER exact zeros became missing, so a floored 0 is a real value that the
  models keep (dry season). Outcomes are never touched (a negative NDVI over water stays).
- `NEGATIVE_COVARIATE_RULE` per covariate: "zero" (default) | "missing" | "keep"; `ALLOW_NEGATIVE_COVARIATES = True`
  removes the barrier for later processing (rebuild the panel). The run logs how many cells were floored and how
  many sat exactly at -10 (the exporter's clamp on a masked ERA5 cell -- worth a look if many).
- Found by the end-to-end test: PASS B re-applied the zero rule and turned the floored zeros back into missing values,
  and its zero-survival guard refused them -- both now know a floored 0 is real; both model-level zero tests too.

### Memory first: RAM and GPU used up to 95 % of total, the previous paths only beyond that
- `_hardware.MEMORY_CEILING = 0.95` governs everything (`fits()`, `memory_report()`): worker pools (were 75 % of free
  RAM), the loaders' budget, GPU demeaning (was 60 % of FREE VRAM with a fixed 500 M-row cap).
- **Models:** `load_panel` reads the needed columns of the WHOLE file in one multi-threaded pass when that fits (it used to
  loop over row groups in Python), keeps the table in a session cache and serves the next outcome's load from RAM with
  no disk read; above the ceiling, row group by row group as before. Identical output, tested in three scenarios.
- **GPU:** matrix demeaning goes to the GPU whenever the whole matrix fits below 95 % VRAM, and never attempts a size that
  would fail (a failed attempt used to switch the GPU off for the rest of the session).
- **Preparation (P00):** PASS A hands its Year x Season blocks to PASS B in RAM -- no shard files -- while they fit;
  if the ceiling is reached mid-run the blocks spill to shard files and the run continues exactly as before. P03 -> P04
  run in different kernels, so they keep shard files. In-RAM, shards and a forced spill give the IDENTICAL panel.
selfcheck 93 checks; all gates green.

## v20.30 -- covariates per model; no negative covariates; memory first (95 % ceiling); every GPU result verified on ALL rows
### Read this first: what the v20.29 zip actually contained
An unfinished earlier draft of this request was already in my working copy when v20.29 was packaged, so the v20.29
zip carried its code (covariates per model, the negative floor, the 95 % memory ceiling -- all of which had passed the
gates) under the v20.29 label. It ALSO carried junk: folders literally named `D:\LKT\TST_Artal\output\results`
inside the notebook folders, created when my cold-start gate ran the notebooks on Linux (where your Windows default
path is relative). Windows cannot create such names, so parts of that zip may fail to extract. v20.30 removes them
and cannot produce them again (below). Use this zip, not v20.29.

### Covariates are chosen in each model -- never at panel preparation
`COVARIATES` in a model's CELL 1: a group -- `"all"` (Rain, Tmax, Tmean, Tmin, LandUse), `"mean_temp_rain"` (Tmean +
Rain), `"weather"` (the four weather variables), `"none"` -- or your own list. P00 / P09 no longer choose or filter
covariates; per-variable files carry every candidate covariate; a saved panel scenario never overrides a model's
choice; only the model's own covariates remove rows (a row missing Tmax is kept by a model that does not use Tmax).

### No negative covariates (prepared at panel level)
Negative Rain / Tmax / Tmean / Tmin -> 0 (your rule). Two refinements over the draft: no-data fill values (<= -100,
e.g. -9999) and the exporter's -10 C temperature clamp on a MASKED cell become MISSING -- flooring them would have put
an impossible 0 C into the covariates as if it were real. Outcomes (NDVI's legitimate negatives) are never touched.
Per variable: "zero" | "missing" (block) | "keep"; `ALLOW_NEGATIVE_COVARIATES = True` removes the barrier. The
settings are recorded with the panel; a different setting rebuilds PASS B. `negative_covariates_report.csv` counts
every floored / missing cell per block. Floored zeros survive PASS B and the models (a masked original 0 still becomes
missing first).

### Memory first, 95 % ceiling
Models read their columns from the WHOLE file in one pass into RAM (and a session cache serves the next outcome from
RAM) when the table plus working copies stays below 95 % of RAM; PASS A hands its blocks to PASS B in RAM, spilling to
shard files only if RAM would pass 95 %; the GPU demeaner takes a problem only if it fits below 95 % of VRAM.
Beyond a ceiling, the previous row-group / shard / CPU path runs. RAM == forced spill: identical panel.
Honest limit: panel preparation (dedup, structuring) is pandas on the CPU -- there is no GPU code for it; the GPU is
used where it exists, the fixed-effect demeaning of the estimators.

### Every GPU demeaning verified on ALL rows (your request)
The old check compared CPU and GPU ONCE per session on a 300,000-row SUBSAMPLE -- where most pixels have one row and
demeaning is trivially zero on both -- and, even when it failed, returned that call's GPU result; the matrix path
(2x2, event study) was not checked at all. Now, on every GPU call and on all rows and columns, every pixel-series and
every year x season mean of the result must be ~0 (the defining property of the projection), each column judged on its
own scale; the first GPU result of each kind in a session is also recomputed on the CPU on ALL rows and compared
element by element. A failure returns the CPU result for that call and uses the CPU for the rest of the session --
demeaning is never skipped (that would silently give wrong estimates). Tested on 1.35 M rows with stand-in GPU
functions (no GPU here): correct accepted; an error only beyond the first 300,000 rows rejected; an unconverged result
rejected; a 1e-4 error in one column rejected even after the GPU had been trusted.

### Also fixed
- The engine opened its trace / crash logs BEFORE your paths were applied, creating the default `D:\LKT\...` folders at
  import whatever INPUT_DIR you had set; logs now go to the temp folder until your layout is applied.
- Tests run with a temporary input folder (`REWARD_INPUT_DIR`, never set it yourself); the cold-start gate and the
  self-check fail if anything is written into the bundle; packaging refuses Windows-path names.
selfcheck 95 checks; preprocessing clean; 45/45 models; cold-start 65/65 notebooks; validation suite 28/28.

## v20.31 -- audit before the final build: nothing lost, five defects fixed, every preparation notebook run end to end
### Why the zip got smaller (and nothing real is missing)
v20.29's zip held ~2,300 entries; v20.30 holds 240 files (7.81 MB -- still LARGER than every earlier v20 zip, 5.99-6.10
MB, and the v17 bundles, ~5.7-6.0 MB). The difference was junk: trace / crash logs and scenario files the engine wrote
into folders literally named `D:\LKT\TST_Artal\output\results` whenever a test ran it on Linux (the default Windows path
is relative there). v17.11 already carried 52 such logs; v20.29's new cold-start gate multiplied them. File-by-file
comparison with the earlier bundles on disk: against v17.11 (this line's ancestor) the only files not present are two
`__pycache__` compiled caches (deliberately excluded). The separate v21 branch (18 Sep) had its own extras -- a
4-variable pipeline (REWARD_4VAR_DID), REWARD_PATHS / RESOURCES / BOOTSTRAP, RUN_FULL_v21 / RUN_4VAR -- which were never
part of the v20 line you run; its 11 MB size was also ~5 MB of junk (including a whole test panel).

### Defects found and fixed
- **False "NOT VALID" panel verdict**: P00's panel check ESTIMATED treated / control pixel counts from a 1 % hash sample;
  on a small panel (a single-SWS extract, a test run) the sample held no treated pixel and a correct panel was declared
  invalid. Now counted exactly; the balance sample covers every pixel on panels up to 2 M rows.
- **P01 crashed** ("cannot convert float NaN to integer") when any file carries no year / season in its NAME (allowed
  since v20.14 -- read from content); the inventory now reports those files instead.
- **P04 crashed** when the old sub-watershed crosswalk workbook is not at its hard-coded `D:\LKT\...` path; it is optional
  (the shapefile assigns sub-watersheds), as in P00.
- **Package tables**: `export_for_packages(outcome, covariates=...)` exported the given covariates but filtered missing
  values by the model's covariate list; rows are now filtered by the covariates actually exported.
- **Stale texts**: README_FINAL (said engine 20.24, 70 checks, P00-P11), PIPELINES_GUIDE (called the annual-first
  seasons "the default"), MODEL_READINESS_Artal.md and P00 STEP 8 comments -- all now describe the design in force.
- The retired subsample GPU check is marked as not called (kept only so old scripts still import).

### New gate: `validate_prep_notebooks.py`
Runs EVERY preparation notebook -- P00, P01, P02, P02b, P03 ... P12 -- completely, in a fresh process from its own
folder, on synthetic exports (pre and post years, annual + seasonal rows) in a temporary input folder; stops at the
first exception like Jupyter and fails on any "[FAILED]" line. No earlier gate ran these notebooks to the end, which is
where the P09 schema error, the P10 / P11 import error and the three defects above lived. Every static reference from
all 65 Python notebooks to the engine was also checked: all exist.

## v20.32 -- the non-negative switch (off by default), baselines saved, both specifications saved, models ranked
### Your negative-results concern -- what the switch does and does not do
A DiD coefficient is a DIFFERENCE (core minus rings, after minus before). It is negative whenever the core improves
LESS than the rings, with every value in the data positive -- your NDVI values run 0.2-0.6 and the coefficient is
-0.0009. Excluding negative values therefore cannot "remove a negative result"; in a test where 5.7 % of rows were
negative the estimate moved from +0.0489 to +0.0491. What it does do is select on the outcome: NDVI, NDWI, NDMI, LSWI,
NDRE and SMDI are negative over water, bare soil and moisture stress, so the dropped rows are the driest, most degraded
pixels -- the ones the works should change most.
- `NONNEGATIVE = False` in every model's CELL 1 (engine: `C.NONNEGATIVE_ESTIMATION`), `nonnegative_mode` "drop" or
  "zero", `nonnegative_scope` "outcome" / "covariates" / "outcome+covariates". Default OFF.
- ON: a warning states what it means, results go to their own `_nonneg` results folder (they can never be mixed with
  the clean ones), every saved file carries `nonnegative_filter`, and the loader reports how many rows it touched.
- Covariates keep the v20.30 barrier (negatives floored at 0 when the panel is built; no-data and the -10 C clamp
  become missing).

### Baselines saved for every variable
`C.baseline_means(outcome)` writes `baseline_means_<OUTCOME>.csv`: rows, mean, sd, min, max, share of negative and of
zero values, per group (treated core / control rings) x period (pre / post) x year. P09 writes one for every variable;
M01 attaches the summary to its result row together with `effect_pct_of_baseline` and `effect_in_baseline_sd`, so an
effect can be read against the level it started from.

### Canonical AND covariate-adjusted, everywhere it matters
M01 already saved both. The event study (M02) and the pre-trends test (M16) now accept covariates and save both:
`beta` / `se` (canonical) beside `beta_covariate_adjusted` / `se_covariate_adjusted`, and `f_stat` beside
`f_stat_covariate_adjusted`. Covariates absorbed by the fixed effects are dropped and named.

### RANKED_MODELS.md + `C.model_ranking()`
The 45 models ranked for THIS design (one cohort, 12 clusters, rings as controls): Tier 1 to report in order
M16 -> M02 -> M24 -> M23 -> M01 -> M34 -> M15 -> M25; Tier 2 robustness; Tier 3 heterogeneity only; and what each
blocked model needs to unlock. The ranking explains WHY: with 12 clusters only bootstrap / permutation inference holds,
with one cohort the staggered estimators have nothing to exploit, and because the controls are rings around the treated
cores, a spillover test (M24) decides whether any effect size is meaningful at all.
selfcheck 99 checks.

## v20.33 -- verified against your own run; three defects found in it
### Your changes ARE taking effect (verified from your notebook output, not from the archive)
Your `results.md` archive is from an EARLIER run (`ctrl1-5_treat2022_all_covMeanTempRain`). The notebooks you sent show
the current one: `[INFO] SCENARIO: treated = buff_km 0 | control rings (1, 2, 3) | treatment year 2022 | tag
ctrl1-3_treat2022_all_nonneg_cov...`. Control zones, the covariate group, the non-negative switch and the results
folder all follow CELL 1 correctly, and each design writes to its own folder.

### Defects found in that run and fixed here
- **M16 could never save.** Its pre-trends result carries `leads_dropped=''` -- meaning NO lead was dropped, the good
  case -- and the placeholder rule treated an empty string as a placeholder, so every outcome was refused with
  "placeholder value(s) in the result". "" is no longer a placeholder token and descriptive columns (note, reason,
  dropped, covariates, engine, status, ...) are exempt, where "none" is a value rather than a placeholder. A real
  placeholder ("TBD") is still refused.
- **Two switches for the same thing.** `BLOCK_NEGATIVES_IN_ESTIMATION` / `NEGATIVE_BLOCK_MODE` (an older draft) ran a
  second filter beside `NONNEGATIVE`, added a second folder suffix, and wrote `negatives_blocked = no` into files
  produced WITH the filter on. There is now one switch; the old names are aliases kept in sync, one suffix, one label.
- **A filter that empties an outcome now says so.** With NONNEGATIVE on, NDWI (negative over land almost everywhere)
  lost nearly every row and M02 / M34 then reported "no variation left after the fixed effects" as a data gap. The
  loader now warns with the share removed and names the outcome when it exceeds 30 %.

### What your run itself shows (read before reporting anything)
- Pre-trends are REJECTED, hard: F = 4748, p = 0.0000 for NDVI and SAVI. Parallel trends does not hold on this panel,
  so no DiD estimate from it is causal yet -- M34's bounds will be wide. Investigate the 2015-2024 vs 2025 export
  footprint first.
- With rings 1-3 the cluster count falls to 6: quote the wild bootstrap (M23), never the t-statistic.
- M01's NDVI effect changed sign between runs (-0.0009 with rings 1-5 and all covariates, +0.000075 with rings 1-3,
  mean-temp-rain and the non-negative filter). An effect whose sign depends on the specification is not an effect.
- M02 and M34 ran with SEASONS = "auto" (resolved to yearly) while M01 and M16 ran with "all": the four are not on the
  same rows. Set SEASONS identically across models before comparing them.

## v20.34 -- your CELL 1 changes now actually run; the filter can no longer run under a clean label; an honest M16
### Correction to v20.33's changelog
v20.33 said "your changes ARE taking effect". That was wrong, and it was read off the wrong line. CELL 1 printed
`control rings (1, 2, 3) ... tag ctrl1-3_..._nonneg`, but in the SAME pass the next lines were
`scenario adopted from panel preparation: ctrl1-5_treat2022_all_covMeanTempRain (file ...did_scenario.json)` and
`SCENARIO IN FORCE: rings (1, 2, 3, 4, 5)`: the scenario P00 saved replaced CELL 1 in every pass of M01, M02, M16 and
M34 -- control zones, and SEASONS "auto" in M02 / M34. Your NDVI file correctly records (1, 2, 3, 4, 5).

### Fixed
- **CELL 1 wins.** What a notebook's CELL 1 sets explicitly is what runs; the saved panel scenario fills only what CELL
  1 leaves unset, and a line names every setting where the two differ ("CELL 1 wins over panel preparation for:
  control_zones = (1, 2, 3) (panel preparation: (1, 2, 3, 4, 5)) ...").
- **The negative filter could run under a clean label.** The panel scenario reset the scenario's `nonnegative` flag
  but not the filter: your outcome loop dropped 100 % of NDWI, 6 % of LSWI / NDMI and 16 % of SMDI while the folder
  (`..._covMeanTempRain`, no `_nonneg`) and the labels said the filter was off. The scenario is now the single source of
  truth for the filter, its folder suffix and its labels; the outcome loop and the panel file set all three together.
- **The outcome loop** runs every outcome under the first outcome's design, filter and folder (it could not diverge
  once CELL 1 was overridden, but the filter could).
- **M16's F-test.** With 6 clusters the cluster covariance of the leads was near-singular (your log: rank 2 of 3) and a
  pseudo-inverse divided by an almost-zero variance: F = 4748.36 for NDVI, SAVI, EVI, LAI, NDRE and VHI alike, 4090.98
  for LSWI, NDMI and VCI -- a statistic that does not change with the data measures the covariance, not a pre-trend
  (your own NDVI event study shows leads of -0.000006 and +0.000027, both insignificant; HonestDiD breakdown M* = 3.8).
  Only well-conditioned directions are tested now; an ill-conditioned covariance returns INCONCLUSIVE, never REJECT;
  the result carries `test_reliable` and `vcov_condition_number`. v20.33's changelog called pre-trends "REJECTED,
  hard" on the strength of that F -- also wrong.
- M16 wrote nothing in your run because you ran v20.32; v20.33 already stopped `leads_dropped=''` being refused.

### Still in your data (not code)
The treated population doubles at event time +3 (632,938 -> 1,237,766 pixels): the 2025 export covers a different
footprint, so the 2025 coefficient compares different pixels. Re-exporting 2015-2024 on the 2025 footprint remains the
change that makes the post-2024 estimates interpretable.

## v20.35 -- why are beta and its SE so small? Measured, with the fix for each cause
### The arithmetic is not the cause
On a panel shaped like yours (6 sub-watersheds, core + rings, yearly NDVI swings of +/-0.05 shared by both) with a known
true effect of +0.020, the engine recovers 98.7 % of it. Inflating the coefficient by changing the arithmetic would make
it wrong; the task is to find what in the data makes the core and the rings move together. Your own numbers: the
treated core's NDVI swings between 0.25 and 0.35 across years, and its counterfactual differs from it by exactly the
estimate, 0.000048 -- the core moved in lockstep with the rings.

### What shrinks an estimate like yours (same panel, true effect +0.020)
| mechanism | estimate |
|---|---|
| clean data | 98.7 % |
| a later export codes 40 % of ring 1 as core | 78.5 % |
| the 2025-26 export on an OFFSET pixel grid, change visible in 2025-26 | -1.8 %  (tiny beta AND tiny SE -- your signature) |
| structures touch 3 % of the core | 6.5 %  (real, not an error: a local effect averaged over the whole core) |
| frozen pre-period composites | refused by the engine's guard |
Your event study shows the matching symptom: the treated pixels double at 2025 (632,938 -> 1,237,766).

### New
- `C.diagnose_effect_size(outcome)` and **P13** (every outcome): raw 2x2 of group means; share of treated post-period
  rows on pixels WITH a pre-period history; for the ones without, the distance to the nearest earlier pixel (decoded
  from pixel_id) -> "shifted grid" (names the `P.PIXEL_OVERLAP_MIN` that links 95 % of them) or "different ground"
  (re-export); pixels that were controls before 2022 and treated after (-> `P.BUFF_FROM_GEOMETRY = True`); frozen
  pre-period values; the core-vs-rings co-movement; the minimum detectable effect. Verdicts: STRUCTURING / DATA /
  SUBSTANTIVE, with the fix. Structuring fixes are made in P00 and fix EVERY model at once (all read one panel).
- Every TWFE result now carries `mde_80pct_tG1` (the smallest effect the design could detect) and `raw_did_means`.

## v20.35 -- why your effects are so small: the structural causes removed, the rest measured on your data
### What your records show
No crashes (all 7 crash logs empty). Every 23-Sep run used the overridden `ctrl1-5` design (fixed in v20.34). Your
NDVI event study: exactly 632,938 treated and 5,531,914 control units in EVERY year 2019-2024, then 1,237,767 treated at
2025 -- about half the 2025 treated units have no pre-period history. The core's yearly mean swings between 0.247 and
0.353, while the estimate is 0.00005: the core and the rings move together almost exactly.

### Causes that are STRUCTURAL (now removed by default -- every result records what was left out)
- **Gap-filled rows were used as observations.** The exporter fills the unpublished tail of an incomplete recent window
  with a day-weighted blend of the observed mean and the 3-YEAR HISTORICAL mean and stamps it `GapFilled = 1`; the
  engine never read that flag. In the post period such values are partly pre-treatment history: post is pulled back
  toward pre and the DiD shrinks. `EXCLUDE_GAPFILLED = True` (default) leaves them out, counted by group and period.
- **Multi-site overlap.** In a pooled panel the 1-5 km rings of one sub-watershed overlap the core of the next: the same
  pixel is then treated (core of B) AND a control (ring of A) in the same year, and one fixed effect per pixel merges
  the two rows -- identical values on both sides of the comparison. `CLEAN_CONTROLS = True` (default): a pixel treated
  anywhere is never a control; a pixel in several sites' rings enters once.
- Tested on a panel with both, true effect +0.0500: old behaviour +0.0407 (19 % too small); gap-filled out +0.0453;
  overlap cleaned +0.0449; both +0.0496.

### Causes that are in the DATA or the DESIGN (measured, not removable in code)
`C.diagnose_effect_size(outcome)` / **P13** (from the earlier v20.35 attempt, now extended) measures on your panel:
post rows with no pre-period history (2025 footprint), pixels switching treated/control across years, frozen series,
how tightly core and rings co-move (SD of their yearly means vs SD of their difference), gap-filled and contaminated
rows, the exporter's observed Coverage, and the minimum detectable effect -- each with a verdict and the fix. Every
TWFE fit also records the raw 2x2 of means and the MDE. What no code can change: an average over the WHOLE core dilutes
an effect confined to structure sites, and whatever the works do to the 1-5 km rings is differenced away (M24).

### Loading only what a model needs (your request)
Models never rebuild the panel: they read column-projected per-variable files (P09) through an in-RAM cache. Now they
also skip ROWS the scenario can never use: rings outside CONTROL_ZONES and invalid ring codes are not loaded
(`LOAD_SCENARIO_ROWS_ONLY`; M24 / M17 / M18 keep every ring). Pre-building one file per scenario is not done on
purpose: rings x seasons x years x filters x 17 outcomes is thousands of files, each a copy of the same rows, while
filtering the cached columns takes seconds. P09 files now carry `GapFilled` and `Coverage`; until P09 is re-run, models
read the flags from the panel (slower, with a note).

## v20.36 -- why your effects are so small, measured on every run; pixel counts; all baselines; cell logs
### About v20.35
An unfinished earlier attempt at this request was packaged into your outputs as v20.35 without ever being described
to you. Reviewed and verified here, it stays: it (1) excludes rows your exporter GAP-FILLED from a 3-year history
(`EXCLUDE_GAPFILLED = True`; imputed values are not observations and can only dilute an effect; counts are reported),
(2) loads only the scenario's rings (models that need every ring are exempt), (3) in pooled multi-site panels removes
control rows whose pixel is TREATED in another sub-watershed (`CLEAN_CONTROLS`; such a pixel sits on both sides of the
comparison and pulls the DiD to zero), and (4) adds `diagnose_effect_size` and notebook P13.

### Why beta and SE are so small -- what your own files show
The estimator is not the problem: the 2x2 matches a closed-form difference of means to 1e-9 in the validation suite.
Your NDVI event study shows (a) ONE row per pixel per year (n_rows = n_pixels = 632,938 in every year): for NDVI the
panel holds only the annual composite, so SEASONS = "all" adds nothing; and (b) standard errors of 5-26 millionths of an
NDVI unit, about 100x smaller than normal year-to-year NDVI variation allows with 6 sub-watersheds. That is the pattern
of values that barely change from year to year -- the 2015-2024 export we found writing one composite under many dates.
The frozen guard refuses only when more than HALF of the treated pre-period series are frozen; below that, a frozen share
shrinks the estimate silently (a 40 %-frozen test panel: true +0.020 -> +0.015, no refusal).

### What every run now tells you
- Every canonical 2x2 result (M01) carries the share of consecutive-year values that repeat EXACTLY, per group and
  period (`repeat_share_treated_pre` ...), the raw 2x2 of means, the MDE and the baseline; above 20 % a warning names
  the groups. Files beside it: `effect_size_diagnostics_<OUTCOME>.csv` (+ `_yearly`), `baseline_means_<OUTCOME>.csv`.
- Pixel counts on every result estimated with the 2x2 engine: `n_pixels_treated_pre / _post`, `n_pixels_control_pre /
  _post` and the matching row counts; `design_counts_<OUTCOME>.csv` beside it holds group x period, each ring x period
  and each Year x Season x group.
- P09 writes `BASELINE_MEANS_ALL_VARIABLES.csv` and `.txt` and `DESIGN_COUNTS_ALL_VARIABLES.csv` for all 17 variables
  (results\BASELINE\<scenario>\).
- Every Python notebook writes every message of every cell to `<OUTPUT_DIR>\cell_logs\<MODULE>_<date_time>.txt`, with a
  header per cell and its outcome (ok, or the full error); the screen output is unchanged.
- The M01 baseline block I added in v20.32 sat before the streaming branch's save only, so your in-memory runs never ran
  it -- that is why your NDVI result had no baseline columns. The engine now does it, whatever the cells say.

## v20.37 -- the cell-log error you hit, fixed and now tested; what P00's id corrections really changed; OptTier
### Fixed
- **"NameError: name 'time' is not defined" on every cell.** The v20.36 cell-log hooks called `time.time()`; the engine
  imports the module as `_time`. IPython reports a failing callback without stopping the cell, so P00 ran, but every cell
  printed two errors and the per-cell headers never reached the log. No test had executed the hooks (IPython is not
  installed where the bundle is built); the self-check now fires the same pre/post-cell events through a stand-in shell.
- **"68,790,887 rows carried a WRONG sub-watershed id".** The count is the rows whose export id is not the polygon that
  holds the point -- and it said nothing about what that changed. PASS A now reports the rows whose ring VALUE changed and
  the rows that switched between treated and control (what matters for the DiD), and works out whether the export simply
  NUMBERS sub-watersheds differently from the shapefile (every export id -> one shapefile id: a relabel, reported as such)
  or carries genuinely mixed ids. The mapping, with names, goes to `site_id_mapping.csv`. In your run only 14,619 of the
  confirmed rows disagreed on the ring, which points to a renumbering -- the next P00 run will say so, with numbers.
- **OptTier** (exporter v111: the composite tier per pixel, 1 = core months + strict masking ... 4 = full window +
  standard, 0 = no clear observation) was "unresolved". It is now a known QC column, carried in the panel like GapFilled.

### Worth checking in your data (from the same log)
PASS B measured 31-64 m between points in several 2025 exports, against the 10 m grid (exporter SCALE = 10; its own
comments mention SCALE = 30). If the 2025 exports sit on a different grid, their pixels have no 2015-2024 history and
the years that carry the change cannot identify anything -- the treated count doubling in 2025 in your event study fits
this. Masked pixels also widen the measured spacing, so check `treated_post_rows_with_pre_history` in
`effect_size_diagnostics_<OUTCOME>.csv` (M01) before concluding.

## v20.38 -- ONE preparation pipeline (P00); the sub-watershed is the cluster; dose = funds per sub-watershed
### P00 is the only preparation notebook
`01_Panel_Preparation` now holds P00 alone. Every module that folder held was merged in -- P01, P02, P02b, P03, P04,
P05, P06, P07, P08, P09, P10, P12, P13 -- and each section starts with a heading and a first code line naming the
notebook it replaces (`# ===== P09_Estimator_Variable_Files.ipynb (merged into P00) =====`); the table at the top maps
cell -> former notebook -> engine functions. All settings are in ONE cell (`P00_Settings`); no later step redefines
them (P09's cell used to re-save the scenario with its own values). Optional modules have switches there
(RUN_SWS_AUDIT, RUN_GROUND_LINKAGE, RUN_ESTIMATOR_FILES, RUN_READINESS, RUN_DIAGNOSTICS, VERIFY_PACKAGES,
INSTALL_PACKAGES). Per-site / pooled model runs (P11) moved to `08_Multisite_Runs/MS01_Multisite_Runs.ipynb`. The
self-check fails if the folder holds anything but P00, if P00 lacks a module's cell, or if a setting is defined twice;
the notebook gate runs P00 end to end and the cell log shows every module's output.

### What your diagnostics showed
- NOTHING is frozen (repeat share 0.0 everywhere) -- the one-composite-under-many-dates explanation is ruled out.
- Your "TST_Artal" data lie entirely inside the HALIGERI polygon (SWS 7): 68.8 M rows carry export id 1 (Artal's id),
  3.0 M carry 7. The shapefile labels them Haligeri; the ring coding is barely affected. Confirm which sub-watershed
  this extract is before reporting.
- The raw difference of means (+0.0177 NDVI) comes almost entirely from 2025: gap +0.0063 before 2022, +0.0096 in
  2022-2024 on the same pixels, +0.032 in 2025 -- a year exported differently (levels jump ~0.13 for BOTH groups; only
  2025 carries Coverage / OptTier) and on a grid shifted a median 3.0 m, so half its treated rows had no pre-period
  history and could not enter the within-pixel estimate. AGB, LAI, EVI, SAVI, VCI, VHI show the same 2025 jump.
- LSWI / NDMI: the core-ring gap is exactly 0 or missing in every year before 2025 -- not usable pre-2025.

### Design corrections (your points i-iii)
- (i) Treated = every pixel of the treatment area (buffer 0) of its sub-watershed from implementation (TREATMENT_YEAR,
  or per sub-watershed with USE_SITE_YEARS). The fund file's first season past 50 % completion is reported as a works
  milestone, no longer as a "treatment cohort".
- (ii) The SUB-WATERSHED is the cluster (`CLUSTER = "site"`, 20 clusters when pooled). One sub-watershed = one cluster,
  which cannot carry cluster-robust inference: such a run clusters on YEARS (each year's core-vs-ring contrast is one
  independent draw). Tested: with one sub-watershed and yearly core-vs-ring shocks, the old within-SWS pseudo-clusters
  understated the true spread of the estimate 6x; year clusters gave 1.4x (conservative). Your earlier SEs of ~1e-5
  came from those pseudo-clusters -- your own yearly gap varies by 0.0102, so the honest uncertainty is ~0.005-0.01.
  Every result records `cluster_used`.
- (ii) Dose = the AMOUNT released to each sub-watershed (cumulative, from the season after each release),
  `dose_amount_sws`, and its INTENSITY per hectare of the sub-watershed, `dose_intensity_per_ha`; both apply to the
  whole treatment area of that sub-watershed, are 0 on the control rings and before implementation, and are unknown
  (missing) for seasons before the fund file starts (Oct 2024). The completion-% dose is kept.
- (ii) Dose WITHIN a sub-watershed: `C.within_sws_dose(df, structures)` / `WITHIN_SWS_DOSE_PATH` -- when structure-level
  data arrive (site_id, latitude, longitude, amount, completion_date), each structure's amount is shared among the
  treated pixels within `radius_m`, from the season after completion; until then it equals the sub-watershed dose.
- (iii) Readiness labels: complete / limited / incomplete-need data (were RUN-READY / LIMITED / BLOCKED), in both
  readiness modules. Every PANEL-WIDE CAVEAT now states what is MISSING, WHY it matters and what FIXES it, including
  the one-sub-watershed case; every "incomplete-need data" row names the data that would complete it.
- Linkage: `PIXEL_OVERLAP_MIN` 0.80 -> 0.65 (your diagnostic: 0.70 links 95 % of the shifted 2025 pixels; any value
  above 0.50 can match a pixel to ONE earlier pixel only). The panel is rebuilt at the next P00 run.

### Speed and packages
Row groups 4x larger on machines with >= 256 GB RAM (8 M rows, was 2 M) for the panel and the per-variable files; the
95 % RAM / VRAM ceilings and the disk / CPU fallbacks are unchanged. P00's package step installs pyfixest,
wildboottest and diff-diff when missing (INSTALL_PACKAGES; needs internet, skipped cleanly without) and verifies them
against the engine, so the estimators use them from then on (`engine` column in every result).
- Resolved before packaging: (1) the dose check that failed at the end of the previous turn was the TEST's fault -- it
  compared seasons in label order and reported two checks joined by `and`. In time order the dose is 50 -> 80 -> 120
  (Rabi-24 -> Zaid-25, Zaid-25 -> Kharif-25, Kharif-25 -> Rabi-25) and intensity = amount / 5,000 ha exactly; the
  self-check now tests it in time order. (2) PASS A used 32 of your 64 threads because P00 hard-coded
  `N_WORKERS = 32`; it is now `N_WORKERS = None` in P00_Settings -> every logical core the platform allows (60 on
  Windows, whose process pools stop at 61). The self-check refuses the hard-coded value.

## v20.39 -- one folder, one or all 20 sub-watersheds: the overlay assigns, the file's id is validated, each sub-watershed its own cohort
You stage each sub-watershed's exports in one folder (TST_Artal holds Haligeri now) and will later put all 20 there.
- **The overlay assigns, the file's id is kept and validated.** PASS A overlays every row's latitude / longitude on the
  20-polygon shapefile: `site_id` = the sub-watershed that holds the point, `sws_name` its name. NEW: `sws_id_export` =
  the id the input file carried (0 = none), kept in the panel, so every row can be audited; `site_check` = 0 confirmed,
  1 corrected (the file said another sub-watershed), 2 assigned (the file said none), 3 outside every polygon. NEW:
  `site_tagging_by_sws.csv` -- per sub-watershed, the rows the overlay placed there and the share whose file id agreed.
  Rows labelled with another real sub-watershed are named ("7,680 rows labelled 1 (Artal) lie in 7 (Haligeri)").
  Put each sub-watershed's files in its own sub-folder under the input folder: exports of different sub-watersheds share
  file names (CSV_2021_yearly_tile5_sub1.csv) and would overwrite each other in one flat folder; PASS A reads every depth.
- **One or all 20, decided from the panel.** `SWS_MODE = "auto"` (P00_Settings): ONE sub-watershed -> single design (its
  own implementation year; inference on years); SEVERAL -> pooled design: each sub-watershed a cluster with its OWN
  implementation year (its cohort, from data/sites/sites.csv), sub-watershed x period fixed effects. P00 prints and saves
  `sws_implementation_years.csv` (year and where it came from). "single" / "pooled" force a design.
- **Implementation years are never silent.** Every year is marked registry / phase default / ASSUMED. The 11 Phase-1
  sub-watersheds -- Haligeri among them -- have NO year in data/sites/sites.csv, so 2022 was used for them without a
  word. If Phase 1 started earlier, Haligeri's "pre" years held treated years and every effect was pulled toward zero,
  and the pooled run would put all 20 in one cohort. Fill `treatment_year` for Phase 1 in data/sites/sites.csv.
- **Per-site runs cluster on the sub-watershed.** `run_sites` (MS01) still forced within-SWS pseudo-clusters for each site;
  it now uses the sub-watershed (one site -> years), like everything else since v20.38.
- **PASS A stops when nothing loads** -- with the reason (e.g. missing essential columns) -- instead of failing later in
  PASS B with a missing-file error.
- **The 20-sub-watershed path is a permanent gate** (`validate_prep_notebooks.py TWO_SWS`): the whole P00 on exports inside
  two real polygons, Haligeri's files carrying Artal's id; it must choose the pooled design, name the mislabelled rows,
  keep the file's id and warn about the assumed year.

## v20.40 -- the readiness report: complete / limited / incomplete-need data, built from your measured data
- **One readiness report, one set of labels.** P00 used to print two readiness tables (P09's and P10's) built by
  different rules. P10 is now the only one, and it applies the PANEL-WIDE CAVEATS: a model whose own requirements are met
  but which a panel-wide caveat bounds is **limited**, not complete.
- **Every caveat is stated in full**: what is MISSING, WHY it matters, what FIXES it and which models it AFFECTS
  (C1 one sub-watershed, C2 implementation year assumed, C3 2025 is a different export, C4 outcomes without a
  pre-period, C5 fund releases before the file, C6 no ground-truth panel, C7 no structure-level data, C8 results
  produced before v20.38). Every model row names its own gap and what completes it.
- **Measured facts, not the stale profile.** `FACTS_HALIGERI` (from your diagnostics: 2018-2025, 619,271 treated and
  1,248,914 control pixels, 50 % of 2025's treated rows linked, one sub-watershed, 2022 assumed) replaces the
  20-September Artal profile for the report; on your machine `measure_panel` now counts sub-watersheds (not
  within-SWS units) as clusters, and measures the implementation-year source, 2025-type level jumps, the fund file's
  first dose and outcomes without a usable pre-period.
- **The 20-sub-watershed projection** (`FACTS_POOLED_20`, labelled as a projection): P10 shows it automatically beside a
  single-sub-watershed panel.
- **Corrections found while building it:** M45 (ML synthetic control) needs >= 3 NEVER-treated sub-watersheds as donors
  -- all 20 of yours are programme areas -- so it stays incomplete-need data even pooled; the dose models (M06, M27, M30)
  are limited by the fund file starting in Oct 2024; the M01 note "weather covariates flip the raw sign" was measured on
  the old Artal extract and now appears only when that fact is measured.
- Result on your data: Haligeri now 0 complete / 32 limited / 13 incomplete-need data; all 20 sub-watersheds with
  Phase-1 years filled (and different from 2022) and 2025 handled: 38 / 3 / 4 (projected).

## v20.41 -- why your SEs were still tiny; the BM sites as sub-watershed means in every model; 4x again
### The small standard errors
Several estimators compute their SE from influence functions, pixel bootstraps or HC formulas that treat each of your
~1.8 million pixels as independent -- an SE of ~1e-5 whatever the clustering rule (v20.38 fixed the rule in the five
core inference functions; these never used it). Rewriting 45 SE formulas would risk what works, so every result now
carries a DESIGN-BASED SE: the data collapsed to the treated-minus-control gap per year (one sub-watershed, or fewer
than 6) or to one DiD per sub-watershed (6 or more) -- Bertrand-Duflo-Mullainathan -- in `se_design`, `p_design`,
`se_design_unit`; when the model's own SE is more than 3x smaller, the result says so in `se_warning` and the log
names the ratio. Tested on 30 simulated one-sub-watershed panels: true spread 0.0069, design SE 0.0058, M01's
year-clustered SE 0.0055, a pixel-level SE 0.0010 (7x too small here; hundreds of times on your 1.8 M pixels).
Also: the streaming estimator (M01's fallback) now follows the cluster rule; the per-variable estimator files now
carry `site_id` and the v20.38 dose columns (old files are rebuilt by P00, and models no longer reach back into the
full panel for them); and fewer than 6 sub-watersheds now cluster on YEARS -- two sub-watershed clusters gave an SE of
0.0000 in the test (it is 0.0024 now). Your beta itself is small for data reasons the readiness report names (C2: the
Phase-1 year is assumed 2022 -- if Haligeri started earlier its "pre" years hold treated years; C3: the 2025 export).
### The BM (benchmark) sites
Your rule is implemented: the BM sites of a sub-watershed are averaged per variable, year and season, and that mean
represents the sub-watershed (`ground_sws_season_means.csv`; names matched to the shapefile through an alias table --
Halligera -> Haligeri, Shirur -> Sirur ... -- in `ground_name_matching.csv`; the control sub-watersheds Gadag,
Hanchinal, Hosahalli, Kohalli and ITGI are kept apart). The BM data cover 2023-2024 only -- after implementation -- so
no DiD can run on ground values alone. They enter every model as SURROGATE OUTCOMES: P00's new cell P08b fits, per
ground variable (groundwater depth, surface soil moisture, root-zone soil moisture, LAI), ridge regressions of the
sub-watershed BM mean on the satellite indices of its treatment area (same year and season; leave-one-out R2 in
`ground_surrogate_fit.csv`; plain correlations in `ground_satellite_validation.csv`), and registers each usable fit as
`GND_<variable>` -- computed for EVERY pixel and year, written as an estimator file, and in the outcome list every model
loops over. M07 now runs the surrogate DiD on each GND_* outcome over the full panel (it used only the BM pixels).
A fit needs >= 6 sub-watershed x season means: with Haligeri alone there are too few, so it is refused with that
reason; the pooled run provides them. Readiness: M07 becomes "limited" in the 20-sub-watershed projection (new caveat
C9: the surrogate's first-stage error is not in its SE).
### Faster
Row groups 4x larger again on machines with >= 512 GB (32 M rows; yours: 549 GB), for the panel and the per-variable
files; a write that runs out of memory retries with row groups 4x smaller instead of failing. RAM/VRAM ceilings (95 %)
and the disk/CPU fallbacks are unchanged; PASS A/B already use every core Windows allows (60).

## v20.42 -- pre-built packages FIRST for every model that has one; the engine only as fallback
### What was true before
Only four estimators used a package inside the notebooks (pyfixest TWFE / event study / wild bootstrap, diff-diff
Callaway-Sant'Anna). Every other package counterpart lived in the stand-alone `python_prebuilt/` pipelines, which the
notebooks never called.
### Now
- **Every model notebook asks for its package first** (a hook right after CELL 1 in all 45): `C.prebuilt_first(MODEL_ID,
  OUTCOME)` and prints what computes the model and why.
  - *Function layer* (10 models: M01, M02, M05, M07, M20, M21, M23, M24, M25, M36): pyfixest / wildboottest / diff-diff
    compute inside the engine functions the model calls, as before.
  - *Model layer* (14 models): the verified package computes the model's PRIMARY result before the engine code --
    diff-diff ContinuousDiD (M06), SunAbraham (M09), SyntheticDiD (M11), BaconDecomposition (M22), ImputationDiD (M27),
    StackedDiD (M31), HonestDiD (M34); econml CausalForestDML (M39, M43), LinearDML / DoubleML PLR (M40), meta-learners
    (M41), DRLearner (M42); PySAL esda Moran (M17) and Moran_Local (M18) -> `<MODEL>_PACKAGE_<OUTCOME>.csv`, engine =
    package and version, with the design-based SE. The engine code then runs as the cross-check.
  - *Engine only* (21 models): no established Python package, or the engine is the safer implementation -- each with
    its reason (e.g. M16 keeps the rank-safe joint test; a package Wald test gave F = 4748 in v20.33).
- **Nothing is trusted unverified.** P00's P12 step installs every package a route uses (pyfixest, wildboottest,
  diff-diff, econml, doubleml, esda, libpysal), then checks every route on panels with a KNOWN answer (+0.05; per unit
  of dose for M06; Moran's I against the engine's own on the same neighbours), per installed version. A route that
  fails, a package that is missing, or a package that errors on your data hands the model back to the engine, with the
  reason recorded. Tested with stand-in packages: 14 of 14 model routes pass; a package biased by +0.03 is refused and
  its model goes to the engine; on a P00-built panel M11 / M40 / M17 give primary results and M27 (one cohort) falls
  back with the reason. The real packages could not be installed where the bundle was built -- their verification runs
  on your machine.
- **`C.prebuilt_readiness()` -> PREBUILT_READINESS.md / .csv**: all 45 models -- package route, installed version,
  verified, what computes it NOW, why, and whether the panel holds that route's inputs.
- **Fixed on the way:** the package input (`export_for_packages`, used by every package route and the R scripts)
  clustered on `subwshed_id` -- a single value with one sub-watershed, so every package SE collapsed to ~0; it now
  follows the cluster rule (sub-watersheds >= 6, else years). And `dd_pipeline`'s HonestDiD (M34) took its base from
  whichever estimator had run last instead of the Callaway-Sant'Anna result.

## v20.43 -- every model: a verified Python package, else a verified R package, else the existing implementation
- **R joins the pipeline.** The Python models now call R themselves: `R/run_one.R` runs ONE model from `models_prebuilt.R`
  on the package input and returns `result.json` (estimate, SE, table, R and package versions, or R's own error).
  `prebuilt_first` tries, in order, a verified Python package, a verified R package, then the existing implementation,
  and records why each step was skipped ("R not installed", "R route not verified for R 4.4 / fixest 0.12", "R: object
  'fit' not found", "no result -- needs >= 2 treatment cohorts" ...). A verified Python package takes precedence.
- **Coverage: 43 of 45 models** have a pre-built route -- 24 Python, 34 R; 19 models have R as their only package
  (M03 DRDID, M04 qte, M10/M12/M15/M26/M29 fixest, M13 DIDmultiplegtDYN, M14 MatchIt, M19 lme4, M28 did2s, M30 did,
  M32 etwfe, M33 WeightIt, M35 quantreg, M37 fect, M38 gsynth, M44 bartCause, M45 synthdid); for M20 (metafor), M24
  (fixest), M25 (ritest) and M36 (fect) the complete R model is primary over the Python engine function. The
  existing implementation alone: M08 (needs an instrument that does not exist) and M16 (the rank-safe joint test).
- **New R models:** M12 chained DiD (fixest first differences between consecutive observations), M15 placebo timing
  (fixest, fake treatment years inside the pre-period), M41 meta-learners (grf S / T), M42 doubly-robust (grf AIPW).
- **R library fixes found by line-by-line review** (the R code had never run): M03 duplicated its grouping column (would
  fail before DRDID ran); M04 treated the panel as repeated cross-sections; M17/M18 returned no LISA table; M19 fitted
  lme4 with a random effect per pixel on ~70 M rows (now a pixel sample); M24 hard-coded ring 5 as reference (your
  scenario used rings 1-3); M28 left never-treated units without an event time, so fixest dropped the comparison group;
  M36-M38 used ~600,000 pixel units (now sub-watershed x ring, as the engine); ML on 1.8 M pixels (now a sample); M41 /
  M42 were advertised but not registered; `run_model` swallowed every error (the bridge uses `run_model_strict`).
- **P00 P12** finds R (PATH, R_HOME, C:\Program Files\R\R-*, or `R_SCRIPT`), installs the R packages of every route
  (`INSTALL_R_PACKAGES`), and verifies every R route on the same known answers as the Python routes, per R and package
  version; `PREBUILT_READINESS.md` now has both languages.
- **Tested without R** (R cannot be installed where the bundle is built): a stand-in Rscript that speaks run_one.R's
  protocol -- 34 of 34 R routes pass the known-answer check; on a P00-built panel M03, M09, M15, M18 and M36 give
  primary results from R; an R error hands the model to the existing implementation with R's message; a verified
  Python package takes precedence over R; without R every model says so and runs. The real R code is verified on your
  machine by P00 -- a route that fails there is simply not used.
- **Your rule enforced first: incomplete data -> no package.** Before any Python or R package runs, the model's data
  requirements are checked against P00's readiness step (MODEL_READINESS.csv). A model marked "incomplete-need data"
  (e.g. M13 without switching units, M36/M45 without enough sub-watershed units) runs NO package -- the existing
  implementation runs and reports the gap and its reason. Found by testing: with packages available, 6 models whose
  data do not meet their requirements had produced package numbers the design cannot support.

## v20.44 -- from your run: LandUse was a number in every model; 2,031,153 singletons; diff-diff's new API
- **LandUse left the default covariates.** All 45 model notebooks use `COVARIATES = "all"`, which entered LandUse -- a
  land-use CLASS code -- as a NUMBER next to rainfall (your TRACE line: `covariates ['Rain', 'Tmax', 'Tmean', 'Tmin',
  'LandUse']`). A class code is not a quantity, and land use can change BECAUSE of the watershed works, so as a control
  it absorbs part of the effect. Measured on a simulated panel where the programme adds +0.05 directly and moves 40 % of
  treated pixels to a greener class (+0.03): true total effect 0.0540; weather-only 0.0539; with land-use classes as
  controls 0.0500 -- the channel removed. Now `"all"` = `"weather"` (Rain, Tmax, Tmean, Tmin) and its results go to a
  NEW folder tag `covWeather` (your earlier `covAll` results, with LandUse, stay separate). Land use only on explicit
  request, `"all_with_landuse"`, as one dummy per class (never as a number), with a warning. Found by testing on the
  way: the zero-as-missing rule would have deleted every row once land use became dummies (0 is their normal value);
  the exemption now covers LandUse and its class dummies.
- **Singletons, explained.** pyfixest's "2031153 singleton fixed effect(s) dropped" means 2.03 M pixel x season series
  are seen ONCE in the sample: they carry no within-series information, so the estimate is the same (pyfixest drops
  them, the engine keeps them with zero weight; both routes receive the same rows). The warning is now one explained
  line, and every TWFE result records `n_singleton_series` and WHERE they are (`singleton_rows_where`, by season and
  year) -- on your data this says whether they are sparse seasonal composites (e.g. Zaid) or the 2025 export.
- **diff-diff's new API.** `CallawaySantAnna.fit(aggregate=)` is deprecated (removed in diff-diff 4.0). The engine route
  and `dd_pipeline` (M05, and HonestDiD's base for M34) now fit once and call `results.aggregate("event_study")`;
  an older diff-diff still takes the old call. Your FutureWarning also confirms the real diff-diff route runs.
- Caught by the model gate while making this change: M10 (triple differences by land use) received its LandUse column
  only through the old default covariates, so removing LandUse from them silently removed M10's GROUP variable (no
  result). `columns_for` now always loads LandUse as a descriptor -- never required, never a covariate unless asked.
