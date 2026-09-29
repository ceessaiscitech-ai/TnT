# Why the Artal DiD shows no effect — final report (v20.53)

Source: your `DIAG_raw_means_NDVI.csv` / `.png` (R_D01, R panel `D:/LKT/RWDR/data`, design `ctrl1-5_treat2022_yearly_covAll4_yr2016-2025`),
the code of all three projects, the 20 sub-watershed polygons and the Earth Engine exporter. Numbers are NDVI; "gap" = core
mean minus ring-5 mean; pre = 2015–2021, post = 2022–2025.

## 1. Bottom line

1. **The estimate is correct for the data it was given.** Your design uses the annual composite only (`yearly`). In that
   series the core and every ring moved together in every year: the largest difference between any two of them in any year
   is 0.0006 NDVI, and the raw DiD is −0.0002. M02 / M34 returned 0.000025 because there is nothing else in that series. No
   code path produced the zero.
2. **The only clear divergence is in Rabi 2025.** Core 0.354, ring 1 0.308, rings 2–4 0.313–0.320, ring 5 0.283, outside the
   rings 0.232. Across 2015–2024 the Rabi gap stayed between −0.003 and +0.007 (pre-period SD 0.0032). The 2025 gap (+0.071) is
   22 pre-period SDs away. Without 2025 the Rabi DiD is −0.004. If this signal is real, the programme's effect shows in the
   Rabi season from 2025. An annual-only design cannot see it (tested: a Rabi-only effect gives 0.0056 with a Rabi design and
   −0.0002 with the annual design).
3. **The Kharif composites are not usable vegetation data.** The core's Kharif NDVI is 0.02–0.19 (mean 0.10). That is the lowest
   of the four series, below Rabi (0.25) and Zaid (0.18). During the monsoon it should be the highest. Values of 0.02–0.06
   (2019, 2022, 2025) are what clouds, haze or standing water give. This breaks your cloud-free rule, and those seasons cannot
   show an effect.

## 2. Evidence by season (from your file)

| season | core level | raw DiD vs ring 5 | largest core–ring spread in any year | 2025 gap in pre-period SDs |
|---|---|---|---|---|
| Annual (S0) — the design uses only this | 0.206 | −0.0002 | 0.0006 | −0.6 |
| Kharif (S1) | 0.102 (implausibly low) | −0.0008 | 0.0072 | 1.7 |
| Rabi (S2) | 0.250 | **+0.0144** (all from 2025; −0.0038 without it) | 0.0710 (2025) | **22.0** |
| Zaid (S3) | 0.182 | −0.0004 | 0.0033 | 1.2 |

## 3. What was ruled out in the code and the design (deep check)

- **Formulas:** every estimator recovers a planted effect. The strict R test passes: 89 checks, 0 failures, each model within ±0.01 of 0.05 (±0.02 for ML / factor models). Python V00 passes 28/28, including:
  - TWFE equals the closed-form 2x2 to 1e-9;
  - cluster SEs equal CGM 2011 CR1;
  - Callaway–Sant'Anna collapses exactly to the 2x2;
  - the pre period is Year < 2022, identically in Python and R.
- **Pre-built packages first, verified before use (P12):** P12 re-checks every package against a known answer, on your installed versions, each time P00 runs. The engine is only the fallback. Here:
  - all 4 estimator routes and all 14 model routes pass (pyfixest 0.60, diff-diff 3.12, econml 0.17, esda 2.10);
  - 33 of 34 R routes pass. M27's R package fails inside the package, so M27 uses the verified diff-diff route.
- **Controls:** the rings are exclusive (core ∩ ring 1 = 0 ha), and no control ring of any sub-watershed lies in another programme core (all 20 polygons checked).
- **History-filled rows:** R used them before v20.52. They are now excluded in both languages.
- **Spillover:** in 2025 Rabi, ring 1 (0.308) sits between the core (0.354) and ring 5 (0.283), and so do rings 2–4. That is consistent with a real effect fading with distance, and with an artefact that varies across space. §4.2 decides which.

## 4. What to do, in this order

1. **Run the Rabi design** (new in v20.53). Since v20.57 the design is set in each model notebook: set `SEASONS <- "Rabi"` (R) /
   `SEASONS = "Rabi"` (Python CELL 1) in M01, M02 (event study by year), M16 and M24, and run them — the panel is not rebuilt.
   - If the effect is only in 2025, the event study shows it.
   - Also run it with post years 2022–2024 only (`TREATMENT_TIMING <- "fixed"`, `TREATMENT_YEAR <- 2022`, `POST_YEARS <- 3`); this estimate must stay near zero for the 2025 signal to be taken as programme-driven. (v20.57: your fund workbook dates Artal's first treated season to Rabi 2024 — the default timing now.)
2. **Verify Rabi 2025 before believing it.** It is the most recent season, the year of the shifted export grid, and possibly a newer exporter version: exactly where artefacts appear. `R_D01` writes three files; compare core against rings for 2025 / Season 2 in each:
   - `DIAG_src.csv`: the sensor (1 = S2 SR, 3 = Landsat, 4 = MODIS 500 m, 5 = projected);
   - `DIAG_gap.csv`: the history-filled share;
   - `DIAG_res.csv`: the resolution.
   - If the core came from other tiles, dates or sensors than the rings, the jump is an artefact. If they share the same sources, it is evidence of an effect.
3. **Re-export Kharif under your cloud-free rule.**
   - Use only the strict tier, or a cloud-free substitute at native resolution. The current last tier accepts scenes up to 80 % cloud with a per-pixel clear score of 0.60.
   - Until then, do not interpret Kharif results.
4. **Sensitivity:** controls = rings 2–5 (`CONTROL_RINGS <- 2:5`). If ring 1 carries part of the effect, the core-vs-ring-5 contrast is the cleaner one.

## 5. Status

v20.53 contains everything above. The R project adds single-season designs, the Kharif plausibility check in R_D01 and an
"outside rings" label. The Python projects keep every core, with one limit: workers are reduced only when they would not fit
below 95 % RAM (your rule); v20.52 had dropped that check, which risked killing the kernel. Your paths are unchanged.
