# QC report — what was wrong in the source files and what the code did about it

Counts refer to the tables in this folder (`QC_SUMMARY.json` has the machine-readable version).
"Flagged" means the row is kept and marked; nothing was deleted.

## A. Benchmark hydrology workbooks

| # | Issue | Where | Handling | Flag / column |
|---|---|---|---|---|
| A1 | Five different sheet layouts per variable (long; wide-by-date; side-by-side SWS blocks; block-per-date; ceptometer raw log) | all institutions | headers located by column name, not position; per-layout parsers | `source_sheet`, `source_row`, `block` |
| A2 | Excel day/month swaps on real datetime cells (e.g. 6 Jan stored as 1 Jun) | UAHS, UASB, UASD, UHSB, UASR | per-site dynamic-programming resolver: chooses as-read vs swapped for each ambiguous visit jointly, minimising backward steps, bounded by the workbook save date and the April-2023 monitoring start; as-read is kept when both fit | `date_flag` = `ddmm_swapped_by_sequence` (SSM 903, LAI 262, GW 14, TDR 1,148) / `ddmm_kept_by_sequence` |
| A3 | Year typos in GW column headers (`2024-10-23 … 2024-12-23` inside a 2023 sequence) and in a few visit dates | UASD GW (402 readings), SSM (9), TDR (194) | year ±1 offered as a last-resort candidate in the same resolver | `year_corrected_by_sequence` |
| A4 | Month-name headers without a year (`July` … `December`, `Sept-2023`) | UHSB, UAHS, UASD GW | assigned to the year of the neighbouring dated headers | `month_marker` |
| A5 | Dates the parser could not read (219 TDR rows, 21 of them UAHS) | UHSB/UAHS TDR visit blocks with no date row | kept with `date = NaT` | `unparsed` |
| A6 | Whole visit blocks carrying another SWS's coordinates (copy-paste); first-visit GPS differing from later copied coordinates | UAHS SSM (Jammapura/Koranahalli/Haralahalli/Laxmisagara blocks at 14.257 N / 75.373 E), scattered elsewhere | site coordinate = **median over visits**; per-row distance to that median reported | `lat_site`, `lon_site`, `dist_to_site_median_m`, `coord_outlier_gt_300m` (129 SSM rows) |
| A7 | **Artal (UASD) SSM/LAI sites (≈16.44 N, 75.17 E) and Artal borewells (≈16.73–16.77 N, 75.28–75.36 E) are 35–40 km apart** | UASD | not resolved – one of the two sets is mislocated | check against your Artal shapefile before snapping |
| A8 | Section header mis-aligned with its data rows (two cells missing in the Artal section header) | UASD SSM row 13 | header-fit score: the previous header row was used because it explains the data row | `header_note` (117 rows) |
| A9 | Coordinates written as DMS strings (`16 07' 14"`) | UHSB | converted to decimal degrees | – |
| A10 | Continuation blocks with no site identifiers (2024 control-SWS rows listing only crop + dates) | UASD SSM rows 150–160 | kept, site fields blank, no coordinates | `latitude` NaN (336 SSM rows without coordinates in total, incl. all UASR SSM) |
| A11 | Replicate-number sub-header rows (`1 | 2 | 3`) inside data | UASR | skipped | – |
| A12 | Non-numeric readings (`No borewell`, `Dry`, `No water`, `40+`, `Stollen`, `Access tube damaged`, `-`) | GW, TDR | value NaN, text kept | `value_flag` (GW: 46 rows) |
| A13 | Physically impossible values (TDR moisture 1,463 %, 1,971 %, 4,013 %; GW depth −0.5 m) | UAHS/UASR TDR (5), UHSB GW (3) | kept in `moisture_pct`, NaN in `moisture_pct_clean`; GW flagged | `moisture_flag`, `value_flag = negative_depth` |
| A14 | Reported average ≠ mean of the three replicates | all | difference reported | `reported_avg_minus_mean3` |
| A15 | TDR block titles covering two SWS (`Jammapura and Laxmisagara 4U`) | UAHS | SWS re-assigned from the MWS→SWS map of the SSM sheet; block title kept | `sws_name_block` |
| A16 | Depth labels turned into dates by Excel (`10-20` → 2023-10-20) or given as the layer bottom only (`20.0`) | UAHS, UHSB TDR | decoded; single numbers treated as 10-cm layers | `depth_label`, `depth_top_cm`, `depth_bottom_cm` |
| A17 | UASR LAI is a raw AccuPAR log; site code in a preceding record, coordinates garbled (`17?`) | UASR | LAI taken from `SUM` records, annotation carried forward (`HUSWS71RGB` → survey 71, redgram, plot quality B); no coordinates | `remark` |
| A18 | Well depth unit inconsistent (`well_depth,ft` vs `well_depth (m)`); readings appear to be metres everywhere | UASD vs UHSB | unit carried as written, not converted | `well_depth_unit` |
| A19 | Empty template (IISc) and empty streamflow sheets | IISc, all | nothing produced | – |

## B. Field survey

| # | Issue | Count | Handling |
|---|---|---|---|
| B1 | GPS outside Karnataka (lat 23.6 N, lon 72.5 E) or missing | 24 plots | coordinates set to NaN; flagged `gps_outside_karnataka_or_missing` |
| B2 | Polygon centroid > 1 km from the enumerator GPS | 310 plots | flagged; polygon centroid still used for linkage (`link_source`) – inspect before use |
| B3 | Missing / degenerate polygons | 7 / 5 | flagged; GPS point used |
| B4 | ~70 spellings for the same crops (ragi/raagi/ರಾಗಿ; togari/toor/pigeon pea/thogre…; jola/jowar vs mekkejola/corn) | 3,642 | harmonised to 30 classes; 74 typo/test entries left as `other:<raw>` and flagged |
| B5 | `Field Size` from the app is the polygon area in **acres** (ratio 2.47, r = 1.00) | all | converted to ha (`field_size_ha_app`) |
| B6 | Free-text `Cultivated Area` unrelated to the polygon area (r = 0.02) | all | kept as `cultivated_area_ha_stated` only |
| B7 | Kannada owner names embedded in `Survey Number` | – | numeric survey/hissa part kept, name dropped |
| B8 | Personal data (names, phones, addresses) | – | removed; `plot_uid`/`farmer_uid` are SHA-1 hashes |

## C. Koppal MIS

| # | Issue | Count | Handling |
|---|---|---|---|
| C1 | `Actual RMT` is the spreadsheet formula `=Proposed×{80,81,82,83}/100`, not a measurement | 1,145 of 4,035 parcels (M3b 81 %, M4c 78 %, M3c 69 %, M1e 52 %, M1c 47 %) | `actual_rmt_source`; `actual_rmt_measured` NaN for those rows; both all-rows and measured-only completion figures reported (70.1 % vs 66.4 % overall) |
| C2 | Bunding cost formulas and totals depend on C1 | – | cost figures carried but labelled |
| C3 | Inconsistent categorical spellings (`MALE/Male/male/FEMAL`, `Other/OTHER/0THER`, `SMALL/sMALL/LF`) | – | normalised |
| C4 | One MWS name spelled three ways across sheets (`Muralapur-2` / `Murlapura 2` / `Murlapur`) | – | MWS **code** used as the key |
| C5 | Common-land sheet has proposals only (0 actuals; 5 of 175 with GPS) | 175 | delivered as proposal inventory |
| C6 | No dates of any kind | – | `completion_date` left blank in `intervention_detail.csv` |
| C7 | Personal data (owner names, phone numbers) | – | removed; social group and gender kept only as village/MWS shares |

## D. Things to verify on your side

1. The Artal coordinate discrepancy (A7).
2. Which SWS are saturation vs control for UAHS and UASB (no labels in their workbooks).
3. (resolved in v2) `Year`/`Season` keys follow the GEE exporter's `SEASONS` (Kharif Jun–Sep, Rabi Oct–Feb, Zaid Mar–May).
4. GW depth units (A18).
