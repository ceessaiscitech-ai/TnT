# REWARD ground-data inputs for the DiD pipeline (v2, built 2026-09-14 -- season keys aligned to the GEE exporter)

Everything here was derived from the files in `PatchDPRAIRUn.rar` by the code in `pipeline_code/`.
No value was imputed, interpolated or invented: every row traces to a source sheet and row
(`source_sheet`, `source_row`), and every repair the code made (date swaps, year typos, header
fallbacks, coordinate outliers) is recorded in a flag column. Read `QC_REPORT.md` before using
any table in a model.

## 0. Season keys (read first)

`Year`/`Season` in every table follow **the GEE exporter's own rule** (`artal_exporter` `SEASONS`): Kharif = Jun–Sep, Rabi = Oct–Feb, Zaid = Mar–May, `Year` = calendar year of the season start (a January/February reading belongs to the Rabi that began the previous October). This is how the panel rows are keyed, so ground and satellite match. The DiD prep engine's `_prep_common.SEASON_MONTHS` (Kharif Jun–Oct, Rabi Nov–Mar, Zaid Apr–May, agri-year Jan–May) disagreed with the panel for October and March; pipeline v17.1 adds `SEASON_DEFINITION = 'export'` to align P05 dose timing (see its CHANGELOG).

Folders added in v2: `excel/` (the two structured workbooks), `gee_v111_inputs/` (survey-derived compositing-window tables read by exporter v111), `pipeline_code/` (builders + `_ground_common.py`).

## 1. What the raw material was

| Source | Content | Period | Rows produced |
|---|---|---|---|
| `Benchmark sites data/*.xlsx` (UAHS, UASB, UASD, UASR, UHSB; IISc = empty template) | Surface soil moisture (3 reps), TDR profile moisture/EC by depth, monthly manual groundwater depth, leaf-area index (3 reps) at benchmark sites in **saturation and control sub-watersheds** | Apr 2023 – Jun 2024 | SSM 3,879 · LAI 1,179 · GW 3,209 · TDR 5,946 |
| `99. All Field Survey Data - [03.12.2025 to 02.05.2026].xlsx` | 3,642 plots / 3,397 farmers in 7 districts: GPS, field polygon, crop, sowing date, variety, next-season crop | sowing Jul 2024 – Mar 2026; captured Dec 2025 – May 2026 | 3,642 plots |
| `REWARD MIS-Koppal New.xlsx` | 4,035 private parcels in 14 MWS of the Koppal SWS (code 4D4A2): proposed vs actual bunding/weirs/ponds/plantation; 175 common-land drainage-line structures | MIS snapshot (no dates) | 4,035 + 175 |
| `Hissa_parcel Counts.xlsx`, `DPR discriptions.docx` | 191 MWS / 125,620 parcels across 20 SWS; 70 %-of-parcels disbursement rule; IVA sampling note | – | context only |

All streamflow sheets are empty. The nested `Benchmark sites data-*.zip` is byte-identical to the loose workbooks.

## 2. Files

v2.1 adds to every long table: `unit_as_labelled` / `unit_used`, `*_clean` values (NaN where a value flag is set), `dup_key_flag` (identical copy-paste rows were dropped and counted in QC_SUMMARY.json; same-site-date rows with different readings are kept and flagged). See AUDIT_REPORT.md and DATA_USAGE_MAP.md.

### Benchmark hydrology (ground truth for satellite validation; treated + control)
| File | One row per | Key columns |
|---|---|---|
| `01_benchmark_sites_master.csv` | site × variable | `lat_median`, `lon_median` (median over visits), `share_visits_within_300m`, `sws_role`, `pixel_id_site_median` |
| `02_ground_ssm_long.csv` | site visit | `ssm1..3`, `ssm_mean` (% v/v, 0–10 cm), `crop`, `Year`, `Season`, `date_flag`, `coord_outlier_gt_300m` |
| `03_ground_lai_long.csv` | site visit | `lai1..3`, `lai_mean`, `crop_height_cm`, `days_after_sowing` where recorded |
| `04_ground_gw_long.csv` | well × month | `gw_depth_m` (depth to water below ground), `value_flag` (`Dry`, `No water`, `censored_deeper_than:40+`, …), `well_type`, `irrigation_method` |
| `05_ground_tdr_long.csv` | probe × visit × depth layer | `depth_top_cm`, `depth_bottom_cm`, `moisture_pct`, `moisture_pct_clean` (NaN if >100 or <0), `ec_ds_m` |
| `06_ground_tdr_rootzone_0_30cm_by_visit.csv` | probe × visit | mean of the 0–30 cm layers (comparator for SMDI / LSWI / NDMI) |
| `07_ground_site_season_means_treated_control.csv` | site × Year × Season × variable | `value_mean`, `n_obs`, `sws_role` ∈ {saturation, control, unlabelled} |
| `15_sws_parcel_counts_from_hissa.csv` | SWS / district (all 20) | parcels and MWS per SWS (denominators), IVA sample sizes, MIS/survey/benchmark coverage |
| `16_programme_rules_from_DPR.csv` | rule | 70 %-of-parcels eligibility, IVA sampling, programme scale, treatment grain |

### Field survey (crop / land-use truth, 2025–26)
| File | One row per | Notes |
|---|---|---|
| `08_field_survey_plots_deidentified.csv` | plot | `plot_uid`/`farmer_uid` are one-way hashes; **no names, phones or addresses**; `polygon_wkt`, `polygon_area_ha`, `link_lat/lon` (centroid, else GPS), `pixel_id_of_link_point`, `Year`/`Season` from the **sowing** date, `next_season_cropped` (Rabi double-cropping flag), `qc_flags` |
| `09_field_survey_crop_calendar.csv` | district × Year × Season × crop | sowing-date median / p10 / p90 – check the pipeline's fixed season windows against it |
| `10_field_survey_landuse_truth_polygons.csv` | QC-clean plot (3,251) | polygons + crop class for validating `LandUse` / `LandUseDW` and Rabi crop presence |

### Koppal MIS (physical dose at MWS / village grain)
| File | One row per | Notes |
|---|---|---|
| `11_mis_koppal_parcels_deidentified.csv` | parcel | `actual_rmt_source` ∈ {value, formula_80/81/82/83pct_of_proposed}; `actual_rmt_measured` is NaN for formula rows |
| `12_mis_koppal_dose_by_mws.csv` / `13_..._by_village.csv` | MWS / KGIS village | proposed vs actual works, `share_actual_rmt_formula_imputed`, `rmt_completion_pct_all_rows` **and** `rmt_completion_pct_measured_rows`, `parcels_treated_pct_*`, `bund_density_*_m_per_ha` |
| `14_mis_koppal_common_land_structures.csv` | DLT structure | proposal only (0 actuals recorded; 5 with GPS) |

### `pipeline_inputs/` (named for the slots in `_common.py`)
| File | Pipeline slot | What it is / is not |
|---|---|---|
| `intervention_detail.csv` | `INTERVENTION_DETAIL_PATH` (M06 dose; M05/M09/M27/M30 timing) | MWS-grain physical dose for Koppal. **`completion_date` is blank – the MIS has no dates**, so it upgrades dose, not timing. `subwshed_id` is blank: fill it from your `RWD_Sub_watershed_final_list.xlsx` (District = Koppal). |
| `household_characteristics.csv` | `HOUSEHOLD_CHARACTERISTICS_PATH` (M26) | village / MWS **aggregates** (female-owner share, small-farmer share, SC/ST share, mean holding). Linking them to pixels needs village or MWS polygons (KGIS codes are given); at SWS grain they have no variation and are useless for heterogeneity. |
| `ground_truth_outcomes_LAI_not_yield.csv` | `GROUND_TRUTH_OUTCOMES_PATH` (M07) | `measured_yield_or_income` = **seasonal mean of ground LAI**, labelled `measured_variable = ground_LAI_seasonal_mean_NOT_yield`. It validates the surrogate relationship (satellite LAI/NDVI → ground canopy); it is not an economic outcome. No file in the archive contains yield or income. |

### `pipeline_code/`
`_ground_common.py` (drop next to `_common.py`), `V06_Ground_Validation.py` (drop into `06_Validation/`),
and the builders (`build_all.py`, `ground_utils.py`, `ground_parsers.py`, `ground_tdr.py`, `field_survey.py`,
`mis_koppal.py`). Re-run: `python build_all.py <raw folder> <output folder>` (needs pandas ≥ 2, openpyxl, scipy).

## 3. How to use it in the DiD pipeline

1. **Read `pixel_id` columns as strings** (`dtype={"pixel_id_site_median": str}`) – the ids start with `0`.
2. **Never merge ground points on the formula `pixel_id`.** A GPS point almost never coincides with a
   10 m centroid (0 % match in testing). Use `_ground_common.snap_to_panel_pixels()` – nearest panel
   pixel within 12 m – or, for survey polygons, `pixels_within_polygon_bbox()`.
3. **Validation (paper, methods section)**: run `V06_Ground_Validation.py`. It pairs ground LAI with panel
   `LAI`, ground SSM and TDR root-zone with `SMDI`/`LSWI`/`NDMI`/`NDWI`, at the same pixel and
   `(Year, Season)`, and reports n, Pearson r, Spearman ρ, RMSE, bias and slope by institution and by
   SWS role. Because sites exist in both saturation and control SWS, agreement is not estimated on
   treated pixels only.
4. **Ground treated/control comparison**: `07_...treated_control.csv` gives site × season means with
   `sws_role`. Monitoring starts in 2023, so this is a post-period cross-section, not a DiD – use it to
   corroborate the sign of satellite effects (e.g. Rabi soil moisture and groundwater depth), not to
   replace them.
5. **Dose (M06)**: `12_mis_koppal_dose_by_mws.csv` is a within-district dose that the district fund file
   cannot give. Use `rmt_completion_pct_measured_rows` or `bund_density_actual_m_per_ha` and drop / weight
   MWS by `share_actual_rmt_formula_imputed`. To apply it to pixels you need the MWS boundaries
   (the MWS codes `4D4A2M1c …` are the join key).
6. **Land-use / crop-presence check**: `10_...landuse_truth_polygons.csv` → for each polygon take the panel
   pixels inside it for `Year=2025, Season=1` (Kharif) and `Season=2` (Rabi); compare `LandUse`/`LandUseDW`
   with `crop`, and Rabi NDVI/LSWI with `next_season_cropped`.
7. **Season windows**: `09_field_survey_crop_calendar.csv` shows late-Kharif sowing (e.g. Bidar pigeon pea
   median 1 Oct 2025). If your Kharif composites are built from the central months only, part of the
   Kharif signal for such crops falls in the edge months – worth a sensitivity run.

## 4. What these files cannot do

- No yield or income anywhere → M07 as a *long-term outcome* stays blocked.
- No completion dates → no within-district treatment timing; staggered modules keep district grain.
- No instrument → M08 stays blocked.
- Ground monitoring is post-period only; the satellite panel remains the only pre-period source.
- `sws_role` is filled only where a workbook itself says saturation/control (UASD, UASR-ITGI, UHSB) plus
  Koppal (from the MIS). Everything else is `unlabelled` until mapped with your crosswalk.
