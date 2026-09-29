# DATA USAGE MAP -- every attached dataset: structure produced, and where it is used (DiD / synchronisation / validation)

Legend: **DiD** = estimator input in DIDRDP_ALLRunDID v17.1 · **SYNC** = harmonisation of the GEE export (v111) or of the panel keys · **VAL** = accuracy validation of the satellite panel.

| # | Attached dataset (raw) | Structured table(s) produced | Structure (one row per) | Used in | Section / module that consumes it | Role |
|---|---|---|---|---|---|---|
| 1 | Benchmark SSM sheets (UAHS, UASB, UASD, UASR, UHSB) | `02_ground_ssm_long.csv`; `site_season_means` (xlsx B); `07_...treated_control.csv` | site visit; site x Year x Season | VAL, DiD-support | GEE v111 §12c `ground_crosscheck` (SMDI/LSWI/NDMI/NDWI vs SSM); pipeline V06 cell 2; xlsx B `VARIABLE_CROSSWALK` | validates soil-moisture proxies; ground treated/control post-period comparison |
| 2 | Benchmark LAI sheets (incl. UASR ceptometer log) | `03_ground_lai_long.csv`; `pipeline_inputs/ground_truth_outcomes_LAI_not_yield.csv`; P08 rewrites `GROUND_TRUTH_OUTCOMES_PATH` | site visit; pixel x Year | VAL, DiD | V06 cell 2 (LAI/NDVI/SAVI/EVI vs ground LAI); **M07 Surrogate-Index DiD** (via P08 file, merge on pixel_id+Year); v111 `ground_crosscheck` | direct LAI validation; surrogate-relationship check (NOT yield) |
| 3 | Benchmark Manual GW sheets | `04_ground_gw_long.csv`; `07_...treated_control.csv` (gw_depth_m_bgl) | well x month; well x Year x Season | DiD-support | xlsx B `site_season_means`; paper's ground-outcome table | watershed outcome with no satellite twin (saturation vs control, post-period only) |
| 4 | Benchmark TDR sheets | `05_ground_tdr_long.csv` (layers); `06_..._rootzone_0_30cm_by_visit.csv` | probe x visit x depth; probe x visit | VAL | V06 cell 2; v111 `ground_crosscheck` (SMDI vs root-zone) | validates SMDI with the quantity it is meant to track |
| 5 | Site coordinates in all sheets | `01_benchmark_sites_master.csv` | site x variable (median coordinate, role) | SYNC | pipeline **P08** (nearest-pixel snap, writes `ground_links.parquet`); v111 `ground_site_collection` | pixel linkage (GPS never equals a 10 m centroid) |
| 6 | Field survey 2025-26 (plots, GPS, polygons, crops, sowing dates) | `08_field_survey_plots_deidentified.csv`; `10_..._landuse_truth_polygons.csv`; `09_..._crop_calendar.csv`; `gee_v111_inputs/gee_compositing_windows_by_district.csv`, `gee_district_season_edge_sowing.csv` | plot; QC-clean plot; district x Year x Season x crop | VAL, SYNC | V06 cell 3 (`LandUse==2` used by **M10 DDD**; `LandUseDW`; Rabi NDVI/LSWI vs double cropping); v111 `ground_crosscheck` polygons; v111 `recommend_core_months` -> `CORE_MONTHS_OVERRIDE` | cropland-class truth; Rabi crop-presence truth; district-aware compositing months |
| 7 | Koppal MIS -- private land | `11_mis_koppal_parcels_deidentified.csv`; `12_..._dose_by_mws.csv`; `13_..._dose_by_village.csv`; `pipeline_inputs/intervention_detail.csv`; `pipeline_inputs/household_characteristics.csv` | parcel; MWS; KGIS village; MWS x intervention; SWS/MWS/village aggregates | DiD | **M06** continuous dose (physical, MWS grain; needs MWS polygons); **M26 / M39** heterogeneity (`HET_COVARIATE`, `CATE_COVARIATES`, one row per subwshed_id); P05 alternative dose (no dates) | dose and household covariates; IVA data-quality flags (`actual_rmt_source`) |
| 8 | Koppal MIS -- common land | `14_mis_koppal_common_land_structures.csv` | drainage-line structure | DiD-support | inventory only (no actuals, 5 GPS) | proposal inventory; direction-of-change expectation for RUSLE/NDWI |
| 9 | Hissa_parcel Counts.xlsx | `15_sws_parcel_counts_from_hissa.csv` (xlsx A sheet `SWS_parcel_counts_hissa`) | SWS/district | DiD-support | denominators for `parcels_treated_pct` (all 20 SWS); IVA sampling sizes; coverage map (MIS / survey / benchmark institution per SWS) | saturation denominators; which SWS still lack MIS |
| 10 | DPR discriptions.docx | `16_programme_rules_from_DPR.csv` (xlsx A sheet `programme_rules_DPR`) | rule | DiD-support | eligibility rule (70 % parcels) applied in `12_..._dose_by_mws.csv`; grain statement (parcel -> MWS -> SWS) | programme rules made machine-readable |
| 11 | artal_exporter v109/v110 + notebook | `Rwd_dp_d_AdvancefinalCodev111` (exporter + notebook + tests) | code | SYNC, VAL | §12c ground cross-check; `CORE_MONTHS_OVERRIDE`; `ground_season_key` | export-side validation and harmonisation |
| 12 | DIDRDP_ALLRunDID_FINAL v17 | `DIDRDP_ALLRunDID_v17_1` | code | DiD, SYNC, VAL | `SEASON_DEFINITION='export'` (P05 timing aligned to the panel); P08; V06; `_ground_common.py` | season-key alignment; ground linkage; validation |
| -- | Streamflow sheets, IISc workbook | nothing (empty) | -- | -- | -- | recorded in QC_REPORT A19 |

## Where each pipeline module gets what
| Module | Ground-derived input | File | Merge key in code |
|---|---|---|---|
| P05 | none (but season definition aligned) | `_prep_common.SEASON_DEFINITION` | -- |
| P08 (new) | sites master, LAI long, survey polygons | `01_`, `03_`, `10_` | nearest pixel (<= 12 m); polygon containment |
| M06 | physical dose by MWS | `12_` / xlsx A `dose_by_mws` | MWS polygons (yours) -> pixels |
| M07 | ground LAI per pixel-year | `GROUND_TRUTH_OUTCOMES_PATH` written by P08 | `[pixel_id, Year]` |
| M10 | cropland-class check of `LandUse==2` | V06 cell 3 output | -- (validation) |
| M26 / M39 | household aggregates | `pipeline_inputs/household_characteristics.csv` (1 row per subwshed_id) | `subwshed_id` |
| V06 (new) | all long tables + links | `02_`, `03_`, `06_`, `10_`, `ground_links.parquet` | `[pixel_id, Year, Season]` |
| GEE v111 §12c | sites, obs, polygons, windows | `01_`, `02_`, `03_`, `06_`, `10_`, `gee_v111_inputs/` | `sampleRegions` / `reduceRegions`; `ground_season_key` |

## Not usable, and why (unchanged)
No yield or income in any attachment (M07 stays a validation check); no completion dates (timing modules keep district grain); no instrument (M08); no rain/temperature/streamflow gauges.
