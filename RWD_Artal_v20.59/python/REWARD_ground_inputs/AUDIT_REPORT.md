# AUDIT REPORT (deep check, 2026-09-14) -- what was checked, what was wrong, what was fixed

## Checks run (all automated, re-runnable with pipeline_code/build_all.py + the test scripts)
1. Value ranges per institution and per variable (unit suspicion) -- SSM/LAI/GW/TDR.
2. Duplicate observations (same site incl. coordinates, same date) -- identical copy-paste rows vs different readings.
3. Every date inside Apr-2023..Jun-2024 for benchmark data; (Year, Season) recomputed independently from the date and compared with the stored key -> 0 mismatches for SSM/LAI/GW/TDR.
4. Season keys against the GEE exporter's `SEASONS` (Kharif Jun-Sep, Rabi Oct-Feb, Zaid Mar-May) -- and against the DiD prep engine's definition.
5. MIS totals against the Hissa parcel counts (Koppal private parcels 4,035 = 4,035; common 175 rows vs 176 in Hissa).
6. Field survey: polygons present (3,635/3,642), season assignment (60 plots without sowing date), 69 unmapped crop spellings kept as `other:`.
7. Pipeline notebooks P08/V06 executed end-to-end on a synthetic v16-schema panel (int64 pixel_id); exporter v111 through the authors' mock harness (`run_mock rabi`, `test_notebook` 36/36 cells, new `test_v111_ground`).

## Errors found and fixed in this pass
| # | Finding | Fix |
|---|---|---|
| 1 | **Season definition mismatch** between the GEE export and `_prep_common.py` (October: Rabi vs Kharif; March: Zaid vs Rabi) -- affected P05 fund-release dose timing and the earlier ground keys | ground tables re-keyed with the exporter's rule; pipeline v17.1 `SEASON_DEFINITION='export'` |
| 2 | UASR LAI: each ceptometer SUM record was one row (repeat readings of the same plot-day) -> 78 duplicate site-days | aggregated per (plot annotation, date): `lai_mean` = mean of records, `n_replicates` = count (LAI rows 1,179 -> 1,107) |
| 3 | Copy-paste duplicate rows in the source sheets (UASB SSM whole day-blocks entered twice; UAHS LAI; TDR) | identical rows dropped (SSM 34, LAI 36, TDR 19) and counted in QC_SUMMARY; same-site-date rows with different values kept and flagged `dup_key_flag` (SSM 362, LAI 113, TDR 942) |
| 4 | SSM template header says "mm" while values are 0-60 -> percent | `unit_as_labelled` / `unit_used` columns; negative SSM (UASR) flagged, `ssm_mean_clean` |
| 5 | Polygon-to-pixel lookup scanned the whole panel slice per polygon (3,251 x ~30 M rows on a real panel) | KD-tree ball query around each polygon (cached tree), exact point-in-polygon on candidates |
| 6 | `snap_to_panel_pixels` broke on the v16 int64 `pixel_id` (pandas 3 str dtype) | keeps the panel's native dtype |
| 7 | V06 cast pixel ids to str on one side only -> 0 pairs on an int64 panel | dtype aligned to the panel |
| 8 | Exporter v111: `reduceRegions` over a single band names its output after the reducer ('mode'/'mean'), breaking the client-side join | `setOutputs([band])` when one band |
| 9 | Exporter v111: windows table looked up only in the folder root | fallback to `gee_v111_inputs/` |
| 10 | `_ground_common.site_master` imported `ground_utils`, which was not shipped with the pipeline | `ground_utils.py` bundled in v17.1 |
| 11 | Hissa parcel counts and DPR rules were attached but not structured | `15_sws_parcel_counts_from_hissa.csv`, `16_programme_rules_from_DPR.csv` (+ xlsx A sheets) |

## Open items that only you can settle (unchanged from QC_REPORT.md section D)
Artal coordinate discrepancy (35-40 km between SSM/LAI sites and borewells); saturation/control labels for UAHS/UASB sub-watersheds; groundwater units at UASD (well_depth labelled ft, readings consistent with m); which SWS is which `SW<n>` (crosswalk).

## Current QC counts
duplicates: {"ssm": {"same_site_date_rows": 362, "identical_rows_dropped": 34}, "lai": {"same_site_date_rows": 113, "identical_rows_dropped": 36}, "gw": {"same_site_date_rows": 0, "identical_rows_dropped": 0}, "tdr": {"same_site_date_rows": 942, "identical_rows_dropped": 19}}
hissa: {"districts": 20, "total_parcels": 125620, "total_mws": 191, "koppal_pvt_matches_mis": true}
rows: ssm 3845, lai 1107, gw 3209, tdr 5927, tdr root-zone visits 927; survey plots 3642; MIS parcels 4035
