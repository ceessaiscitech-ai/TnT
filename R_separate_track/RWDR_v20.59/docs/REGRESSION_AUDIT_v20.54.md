# Regression audit: v20.54 against every earlier version

You asked whether the current code has lost anything, or been downgraded, compared with the earlier versions and with
everything you have requested and reported.

**Answer: nothing is missing and nothing was downgraded.**
- Every file, function, parameter and setting of v20.47 is still present in the three projects.
- Each later release (v20.50 → v20.54) contains everything of the one before.
- v20.47's own tests pass on the new code, apart from differences that you asked for or that are documented fixes.

The audit also found defects that no earlier test had caught. None of them is a removed feature. All are fixed in v20.54,
and each has a test.

**Your link** (claude.ai/share/a914f4fd-…) could not be opened here: the page loads its content only in a signed-in browser,
so no tool here can read it. The audit therefore used every other record:
- the v20.47 bundle you uploaded;
- every later bundle: v20.50, v20.52 and v20.53 of the three projects, and RWDR v20.51;
- the complete changelog from v17.11;
- your stated rules;
- the run logs you pasted: v20.39 PASS B, the pyfixest singleton warning, the R M34 / M02 runs, the PASS A crash and the
  NDVI diagnostics.

If that conversation holds a request that appears in none of these, send it and it will be checked the same way.

## 1. Files — v20.47 (one bundle) → v20.54 (three projects)

| | count |
|---|---|
| files in v20.47 | 371 |
| missing in v20.54 | **0** |
| identical | 213 |
| changed | 158 |

Where the changes are:
- **96 R notebooks.** One line in each: the library loads into the notebook's own environment (v20.49), so your settings
  apply in RStudio and in Jupyter alike. The two R_P00 copies also name the new default data folder in their header (v20.54).
- **14 Python notebooks, 7 in each Python project.** One grouping line in each now states `observed=True` (v20.54, defect 5).
- **31 other Python files and 14 other R files** (engine, tests, setup and the BM tables). Each change is a changelog entry.
- **The BM tables R reads.** They now equal what Python computes. The v20.47 tables had been generated under pandas 3,
  which dropped sites whose site number was blank: Hunasehadagi's root zone had 2 sites instead of 24, and ITGI was lost.

Also:
- The v20.48 Colab notebook was retired in v20.49, as documented: everything it was to check runs in
  `tests/install_and_test_linux.sh`.
- RWD_Artal1 is RWD_Artal with its own data root. The one file that differs is `_paths.py`, in two lines.

## 2. Functions, parameters and settings

| | v20.47 | v20.54 | removed |
|---|---|---|---|
| Python functions and classes (engine) | 672 | 739 | **0** |
| Python functions (ground inputs / exporter) | 64 / 350 | 64 / 350 | **0** (both unchanged) |
| Python module settings | 301 | 311 | **0** |
| R functions | 94 | 120 | **0** |
| R settings | 38 | 47 | **0** |

**Python: signatures that changed.** No parameter was removed. There are five changes:
- `_alive` gained `created`. This is the v20.49 fix for re-used Windows process ids.
- `run_ml`'s default sample went from 200,000 to 400,000. That is your "2x" (v20.50).
- The covariate defaults of three `pf_pipeline` functions no longer list LandUse (v20.54, defect 11).

**Python: settings whose value changed.** Three:
- `ENGINE_VERSION` and `DATA_RULES_VERSION`;
- `INPUT_DIR`, which is your migration to `D:\LKT\RWD_Artal\data`. The old folder stays as `LEGACY_INPUT_DIR`.

**R: signatures that changed.** There are three, and each one only adds a parameter with a default: `m25_ritest` (`batch`),
`m16_pretrends` (`pre_window`, `ref`) and `read_export` (`sws_file`).

**R: settings whose value changed.** Each is either your instruction or a test hook:
- limits doubled (v20.50);
- every core (v20.52);
- the new data root (v20.50);
- the environment overrides the tests use (v20.49–v20.51).

## 3. Each release against the next

| from → to | files lost | functions lost | parameters lost |
|---|---|---|---|
| RWD_Artal v20.50 → v20.52 → v20.53 → v20.54 | 0 | 0 | 0 |
| RWD_Artal1 v20.50 → v20.52 → v20.53 → v20.54 | 0 | 0 | 0 |
| RWDR v20.50 → v20.51 → v20.52 → v20.53 → v20.54 | 0 (VALIDATION_v20.50.md replaced by v20.51's) | 0 | 0 |

## 4. v20.47's own tests, run unchanged on v20.53 and on v20.54

| test (v20.47 copy) | on v20.53 | on v20.54 | explanation of every difference |
|---|---|---|---|
| `selfcheck.py` | 132 pass, 6 differ | the same 132 pass and the same 6 differ | see the list below this table |
| `validate_preprocessing.py` | CLEAN | 1 differs | v20.54 fix 6: with the negative barrier OFF, the −10 °C clamp now stays missing; v20.47 expected it kept as −10 |
| `validate_inference.py` | CLEAN: unbiased; design-based 95 % intervals cover 96–97 %; false positives 4.5 % | the same | identical to v20.48 |
| `validate_all_models.py` | 45 run in both scenarios: 37 estimate, 8 documented data gaps, no placeholder values | the same | identical to v20.48 |
| `V00_RUN_ALL_VALIDATIONS.py` | 28/28 | 28/28 | — |
| `V00b` / `V00c` (old copies) | fail | — | they fail identically on v20.47 itself: outdated scripts. V00b was renewed in v20.49, V00c in v20.54 (both pass) |
| R `tests/run_all_tests.R` (v20.47) | 50 PASS, 5 data gaps, 0 FAIL | 50 PASS, 5 data gaps, 0 FAIL | the gaps are real: one sub-watershed has no dose, instrument, ground truth or second site |
| R `tests/selftest.R` (v20.47) | PASS: 0.0504 against a truth of 0.0500 | PASS: 0.0504 | — |

The six self-check differences:
1. The R units of M36–M38 now include the cohort. This is the v20.49 fix: a unit never mixes cohorts.
2. ML samples 400,000 pixels on every core. This is your "2x" (v20.50) and your "no cap" instruction (v20.52).
3. The BM means have 13 control sub-watersheds, not 12. The v20.47 code gives 13 too under pandas 2.3, with identical
   values; 12 came from pandas 3 dropping ITGI.
4. and 5. The machine is no longer split automatically, per your "no cap" instruction (v20.52). The split is still
   available as an option.
6. The R tests now live in RWDR, since your three-project split (v20.50).

## 5. Your rules — one executable check each

The new check `validate_requests.py` runs these on the code: most checks run the functions on small data, the rest read the
settings that decide the rule. It gives **20 PASS, 2 DECIDE, 1 NOT HERE (the A40 check needs a GPU; on your machine it runs
the GPU self-test), 0 FAIL**; the full table is in `REQUESTS_VERIFIED.md`. The rules it covers:
- the pixel id from the coordinates;
- the treatment timing, and ring 0 against rings 1–5;
- the four weather covariates, which are never outcomes;
- one model at a time;
- sites processed alone, then pooled;
- the output folder inside the data folder;
- de-duplication only within a pixel-year-season;
- NaN and exact 0 treated as no-data;
- SWSiD_All and the shapefile;
- all years and seasons, with the fixed effects;
- packages first;
- pixel overlap;
- covariate groups;
- the negative barrier and its switch;
- everything in RAM and GPU up to 95 %, with GPU results verified on all rows;
- the 80 % name rule;
- no caps;
- the optional 50 % split;
- your paths;
- values filled from history are not observations;
- the doubled limits;
- the A40;
- versioned bundle names.

The R pipeline's own rules are checked by `tests/run_all_tests.R`. v20.54 adds its scenario C.

## 6. Defects the audit found (all fixed in v20.54, each under a test)

| # | defect | since | effect | test |
|---|---|---|---|---|
| 1 | Package routes reused the table they read (`estimator_files\package_input\`) whenever a file of that name existed | v20.23 / v20.46 | After P00 rebuilt the panel, the PRIMARY package results came from the old panel. In per-site runs, every site after the first read the first site's rows | site 2 → site 2's rows; rebuilt panel (NDVI + 1) → input + 1.000 exactly (v20.53: site 1's rows; +0.000); the same site written as 1, [1] or an array → the same file; a rebuild that cannot run hands the model to the engine |
| 2 | Your 95 % rule was switched off for package copies | v20.52 | a copy larger than the RAM left below 95 % was attempted and could kill the kernel | self-check; validate_requests (no room → engine, with a [WARNING] line; room → package) |
| 3 | `DATA_RULES_VERSION` not raised when v20.52 changed a rule (Coverage ≤ 0 rows left out) | v20.52 | inputs cut under the older rules were reused | self-check |
| 4 | `MEMORY_SHARE` (Python and R) had no effect | v20.52 | your documented manual setting did nothing (the default, 1.0, was unaffected) | self-check; R test C |
| 5 | Grouping by the sub-watershed under pandas 2 when the column is a categorical holding sub-watersheds not in the sample | long-standing | M19: empty sub-watersheds counted as groups, ICC 0.281 instead of 0.317 in a test with 2 of 20. M11 returned NaN and M45 stopped with an error (e.g. a per-site run clustered on sub-watersheds) | self-check; the independent review reproduced M11: NaN (v20.53) → 0.0101 (v20.54) |
| 6 | R kept an exported exact 0 of Rain / temperature as a real value; R had no switch for the negative barrier; with the barrier off, Python kept −9999 and the −10 °C clamp | long-standing | R's sample differed from Python's; fill values could enter a barrier-off panel | self-check; R test C; validate_preprocessing |
| 7 | V00 check D7 failed on Windows (it expected `…\TST_Artal\output`); V00c was outdated | v20.50 / v17 | a false FAIL on your machine; a check that could not pass | both pass; D7 now runs on every system |
| 8 | Warnings: pyfixest's raw singleton warning in `pf_pipeline.py`; R "NAs introduced by coercion" (M09 / M28); qte 2.0's two inapplicable notes (M04); pandas' `observed` warning (M11, M20, M36–M38, M43, M45) | long-standing | noise in your logs; where the grouping changed a result (M19, M11, M45) it is defect 5 | self-check; results unchanged |
| 9 | Off Windows, both Python projects mapped to one data folder; R created a folder named `D:` inside the project | v20.50 | test machines only | self-check; R test C |
| 10 | Self-check: its M11 hand-over test ran diff-diff on your real panel once P12 had verified the route, and failed on the reason text; its M13 test wrote into your results folder | v20.42 / v20.43 | a slow, false FAIL on your machine after P00 | isolated verification record and scratch folder |
| 11 | Documentation and setup: see the list below this table | v20.49–v20.53 | wrong or missing information | — |

The documentation and setup defects (row 11):
- The requests ledger had lost its v20.48 table, and in RWDR the v20.49 one as well.
- The separate changelog copy lacked v20.53.
- The R_P00 header and the RWDR README described the old folder and the automatic split.
- The machine plan said "reserve 1" core although none is reserved.
- `00_SETUP.R` sent synthdid to an r-universe that does not exist.
- `pf_pipeline`'s covariate defaults still listed LandUse. No result was affected: package inputs never carry it.

## 7. Your decisions (nothing was changed for you)

1. **Pixel linkage threshold: 0.65; your rule says > 80 %.**
   - It was lowered in v20.38, from your own diagnostic: the 2025 exports sit on a grid shifted about 3 m, and at 0.80,
     20 % of the treated post-period pixels had no pre-period history.
   - To follow the rule exactly, set `PIXEL_OVERLAP_MIN = 0.80` in `_prep_common.py` and `reward_paths.R`, then rebuild
     with P00 / R_P00.
2. **Optional runners.** `MS01` runs one model per site, then pooled. RWDR's `R_RUN_ALL_MODELS` runs several models in a
   row.
   - Your rule is that you run each model yourself.
   - These runners do nothing unless you open them. Keep them or delete them.

## 8. The independent review

A separate reviewer, which had not seen the work, went through every code change of v20.54 and re-ran the tests on copies.
- It confirmed the fixes and found nothing that changes a default estimate silently.
- It found four edge cases, all fixed before delivery:
  - a site list given as an array broke the package-input name;
  - a stale input was deleted before its rebuild;
  - the same site written as 1 or [1] was rebuilt twice;
  - V00's D7 failed when the test variable REWARD_INPUT_DIR was set.
- It also found two gaps in the reporting, both corrected:
  - the M11 / M45 effect of defect 5;
  - four request checks that only searched the code's text. They now run the functions.

## 9. What to do now

1. Unzip the three v20.54 projects beside the old ones. Your paths are unchanged.
2. Python: re-run P00 (its P12 cell re-verifies the packages), then the models.
   - Results that came from a package — the `…_PACKAGE_…csv` files — may have used an older panel, or, in MS01 per-site
     runs, the first site's rows. Re-run them, and any M11 / M45 result that was NaN or failed.
   - The old package-input tables are rebuilt automatically.
3. R: run `R_P00` (the covariate zero rule), then the models.
4. Run `python validate_requests.py` whenever you update. It shows at a glance that every rule you set still holds.
