# Data dictionary (generated from the delivered CSVs, v2.1)

Units: SSM/TDR moisture in % volumetric, LAI dimensionless, groundwater depth in m below ground level, areas ha, lengths RMT (running metres), costs Rs, coordinates WGS84. Year/Season keys follow the GEE exporter's SEASONS (Kharif Jun-Sep, Rabi Oct-Feb, Zaid Mar-May).


## 01_benchmark_sites_master.csv  (768 rows)

| column | non-null | example |
|---|---|---|
| `site_key` | 100% | UAHS/Beguru/Dabbanabairanahalli/ssm/37.0 |
| `institution` | 100% | UAHS |
| `sws_name` | 100% | Beguru |
| `mws_name` | 97% | Dabbanabairanahalli |
| `variable` | 100% | ssm |
| `site_no` | 93% | 37.0 |
| `lat_median` | 100% | 14.2778 |
| `lon_median` | 100% | 75.408387 |
| `n_obs_with_coords` | 100% | 17 |
| `n_dates` | 100% | 17 |
| `share_visits_within_300m` | 100% | 0.9411764705882353 |
| `max_visit_dist_from_median_m` | 100% | 4479.120219843208 |
| `sws_role` | 100% | unlabelled |
| `pixel_id_site_median` | 100% | 010427780025540839 |

## 02_ground_ssm_long.csv  (3,845 rows)

| column | non-null | example |
|---|---|---|
| `institution` | 100% | UAHS |
| `sws_name` | 93% | Jammapura |
| `sws_role` | 100% | unlabelled |
| `mws_name` | 92% | Pandavamatti1 |
| `district` | 7% | Belagavi |
| `bm_site_no` | 91% | 1.0 |
| `survey_no` | 93% | 1.0 |
| `soil_phase` | 92% | VITmA1 |
| `latitude` | 91% | 14.2573 |
| `longitude` | 91% | 75.372552 |
| `lat_site` | 91% | 13.967576000000001 |
| `lon_site` | 91% | 75.971994 |
| `dist_to_site_median_m` | 91% | 72128.58928999412 |
| `coord_outlier_gt_300m` | 100% | True |
| `pixel_id_site_median` | 91% | 010396758025597199 |
| `date` | 100% | 2024-05-30 |
| `date_flag` | 55% | ddmm_kept_by_sequence |
| `Year` | 100% | 2024 |
| `Season` | 100% | 3 |
| `crop_raw` | 74% | Maize |
| `crop` | 100% | unknown |
| `ssm1` | 99% | 27.2 |
| `ssm2` | 98% | 21.4 |
| `ssm3` | 99% | 23.2 |
| `ssm_mean` | 100% | 23.93333333 |
| `ssm_mean_clean` | 100% | 23.93333333 |
| `ssm_flag` | 0% | negative |
| `n_replicates` | 100% | 3 |
| `reported_avg_minus_mean3` | 98% | -3.33333360913457e-09 |
| `soil_temp_mean_c` | 1% | 2.0 |
| `remark` | 1% | multi_date_header |
| `unit_as_labelled` | 100% | avg Soil moisture in mm (template label) |
| `unit_used` | 100% | % (v/v, 0-10 cm probe): the 0-60 range r |
| `dup_key_flag` | 9% | same_site_date_different_values |
| `site_cols_inherited` | 100% | False |
| `source_sheet` | 100% | SSM |
| `source_row` | 100% | 863 |

## 03_ground_lai_long.csv  (1,107 rows)

| column | non-null | example |
|---|---|---|
| `institution` | 100% | UAHS |
| `sws_name` | 97% | Beguru |
| `sws_role` | 100% | unlabelled |
| `mws_name` | 93% | Dabbanabairanahalli |
| `district` | 0% |  |
| `bm_site_no` | 36% | LW |
| `survey_no` | 97% | 118.0 |
| `soil_phase` | 0% |  |
| `latitude` | 95% | 14.292298 |
| `longitude` | 95% | 75.417259 |
| `lat_site` | 95% | 14.291134 |
| `lon_site` | 95% | 75.412213 |
| `dist_to_site_median_m` | 95% | 556.2288712468727 |
| `coord_outlier_gt_300m` | 100% | True |
| `pixel_id_site_median` | 95% | 010429113025541221 |
| `date` | 100% | 2023-04-10 |
| `date_flag` | 33% | ddmm_kept_by_sequence |
| `Year` | 100% | 2023 |
| `Season` | 100% | 3 |
| `crop_raw` | 100% | Maize |
| `crop` | 100% | maize |
| `crop_source` | 22% | first_block_of_row |
| `lai1` | 62% | 5.05 |
| `lai2` | 60% | 4.52 |
| `lai3` | 59% | 4.61 |
| `lai_mean` | 62% | 4.73 |
| `lai_mean_clean` | 62% | 4.73 |
| `lai_flag` | 0% |  |
| `n_replicates` | 100% | 3 |
| `reported_avg_minus_mean3` | 58% | 0.0033333333333338544 |
| `crop_height_cm` | 3% | 17.0 |
| `days_after_sowing` | 3% | 20.0 |
| `remark` | 50% | - |
| `dup_key_flag` | 7% | same_site_date_different_values |
| `site_cols_inherited` | 100% | False |
| `source_sheet` | 100% | LAI |
| `source_row` | 100% | 50 |

## 04_ground_gw_long.csv  (3,209 rows)

| column | non-null | example |
|---|---|---|
| `institution` | 100% | UAHS |
| `sws_name` | 100% | Jammapura |
| `sws_role` | 100% | unlabelled |
| `mws_name` | 99% | Pandavamatti1 |
| `district` | 43% | Gadag |
| `soil_phase` | 84% | KLKiB2 |
| `latitude` | 99% | 13.967596 |
| `longitude` | 99% | 75.972083 |
| `lat_site` | 99% | 13.967596 |
| `lon_site` | 99% | 75.972083 |
| `dist_to_site_median_m` | 99% | 0.0 |
| `coord_outlier_gt_300m` | 100% | False |
| `pixel_id_site_median` | 99% | 010396760025597208 |
| `date` | 100% | 2023-09-01 |
| `date_flag` | 88% | month_marker |
| `Year` | 100% | 2023 |
| `Season` | 100% | 1 |
| `bm_site_no` | 72% | 1.0 |
| `borewell_no` | 99% | 1.0 |
| `survey_no` | 76% | 111.0 |
| `village` | 6% | Ashinala |
| `well_type` | 6% | Bore well |
| `ground_level_m` | 67% | 717.0 |
| `well_depth` | 54% | 220.0 |
| `well_depth_unit` | 68% | ft |
| `geomorphology` | 18% | Pediplain |
| `irrigation_method` | 80% | Drip |
| `gw_depth_m` | 99% | 10.12 |
| `value_flag` | 1% | No borewell |
| `unit_as_labelled` | 100% | unlabelled |
| `unit_used` | 100% | m below ground level (readings 0-104 m a |
| `crop_remark` | 29% | Chickpea |
| `dup_key_flag` | 0% |  |
| `source_sheet` | 100% | Manual GW |
| `source_row` | 100% | 8 |

## 05_ground_tdr_long.csv  (5,927 rows)

| column | non-null | example |
|---|---|---|
| `institution` | 100% | UAHS |
| `sws_name` | 82% | Jammapura |
| `sws_name_block` | 100% | Jammapura and Laxmisagara 4U |
| `sws_role` | 100% | unlabelled |
| `mws_name` | 100% | Jammapur2 |
| `bm_site_no` | 82% | 9.0 |
| `probe_or_survey_no` | 100% | 9.0 |
| `latitude` | 82% | 13.89344 |
| `longitude` | 82% | 75.978869 |
| `lat_site` | 82% | 13.89344 |
| `lon_site` | 82% | 75.978869 |
| `dist_to_site_median_m` | 82% | 0.0 |
| `coord_outlier_gt_300m` | 100% | False |
| `pixel_id_site_median` | 82% | 010389344025597887 |
| `date` | 97% | 2023-09-11 |
| `date_flag` | 42% | ddmm_swapped_by_sequence |
| `Year` | 97% | 2023.0 |
| `Season` | 97% | 1.0 |
| `visit_id` | 100% | 1 |
| `irrigation_type` | 75% | Rainfed |
| `crop_raw` | 81% | Ragi+Maize |
| `crop` | 100% | finger_millet_mixed |
| `depth_label` | 100% | 0-10 |
| `depth_top_cm` | 100% | 0.0 |
| `depth_bottom_cm` | 100% | 10.0 |
| `moisture_pct` | 99% | 6.84 |
| `moisture_pct_clean` | 99% | 6.84 |
| `moisture_flag` | 0% | implausible_gt_100pct |
| `ec_ds_m` | 89% | 1.18 |
| `soil_temp_c` | 5% | 28.6 |
| `unit_used` | 100% | % volumetric (TDR probe); EC in dS/m |
| `value_flag` | 1% | Stollen |
| `dup_key_flag` | 16% | same_site_date_different_values |
| `source_sheet` | 100% | TDR |
| `source_row` | 100% | 13 |

## 06_ground_tdr_rootzone_0_30cm_by_visit.csv  (927 rows)

| column | non-null | example |
|---|---|---|
| `institution` | 100% | UAHS |
| `sws_name` | 90% | Begur SWS |
| `sws_role` | 100% | unlabelled |
| `mws_name` | 100% | LP2 |
| `probe_or_survey_no` | 100% | 820.0 |
| `date` | 99% | 2023-05-11 |
| `date_flag` | 42% | ddmm_kept_by_sequence |
| `lat_site` | 89% | 14.291116 |
| `lon_site` | 89% | 75.412237 |
| `crop` | 100% | maize |
| `Year` | 99% | 2023.0 |
| `Season` | 99% | 3.0 |
| `moisture_pct` | 100% | 9.783333333333333 |
| `n_layers` | 100% | 3 |
| `ec_ds_m` | 96% | 1.4666666666666668 |
| `pixel_id_site_median` | 89% | 010429112025541224 |

## 07_ground_site_season_means_treated_control.csv  (2,179 rows)

| column | non-null | example |
|---|---|---|
| `variable` | 100% | ssm_pct |
| `institution` | 100% | UAHS |
| `sws_name` | 97% | Beguru |
| `sws_role` | 100% | unlabelled |
| `mws_name` | 99% | Dabbanabairanahalli |
| `site_no` | 94% | 37.0 |
| `Year` | 100% | 2023 |
| `Season` | 100% | 1 |
| `value_mean` | 100% | 15.37 |
| `value_median` | 100% | 15.37 |
| `n_obs` | 100% | 1 |

## 08_field_survey_plots_deidentified.csv  (3,642 rows)

| column | non-null | example |
|---|---|---|
| `plot_uid` | 100% | 6e55de33ae98 |
| `farmer_uid` | 100% | 8ae01f80d6 |
| `plot_index_within_farmer` | 100% | 1 |
| `state` | 100% | Karnataka |
| `district` | 100% | Chitradurga |
| `taluka` | 100% | Holalkere |
| `gram_panchayat` | 100% | TUPPADAHALLI |
| `village` | 100% | Singenahalli |
| `survey_hissa` | 100% | 72/*/*/ |
| `plot_name_raw` | 100% | kalu hola |
| `crop_raw` | 100% | raagi |
| `crop` | 100% | finger_millet |
| `variety_duration` | 98% | Medium |
| `sowing_date` | 98% | 2025-08-30 |
| `next_season_crop_raw` | 93% | no crop |
| `next_season_crop` | 100% | no_crop |
| `next_season_cropped` | 93% | 0.0 |
| `cultivated_area_ha_stated` | 93% | 0.607029 |
| `field_size_acres_app` | 100% | 0.76 |
| `field_size_ha_app` | 100% | 0.30756136 |
| `gps_lat` | 99% | 13.9048487 |
| `gps_lon` | 99% | 76.0798916 |
| `captured_date` | 100% | 2026-05-02 |
| `farmer_type` | 100% | new |
| `polygon_wkt` | 100% | POLYGON((76.0791263 13.9046173, 76.07893 |
| `polygon_n_vertices` | 100% | 4 |
| `polygon_area_ha` | 100% | 0.30443612048419116 |
| `centroid_lon` | 100% | 76.07941883601634 |
| `centroid_lat` | 100% | 13.904888751178692 |
| `qc_flags` | 12% | centroid_gt_1km_from_gps |
| `link_lat` | 100% | 13.904888751178692 |
| `link_lon` | 100% | 76.07941883601634 |
| `link_source` | 100% | polygon_centroid |
| `pixel_id_of_link_point` | 100% | 010390489025607942 |
| `Year` | 98% | 2025.0 |
| `Season` | 98% | 1.0 |

## 09_field_survey_crop_calendar.csv  (47 rows)

| column | non-null | example |
|---|---|---|
| `district` | 100% | Bidar |
| `Year` | 100% | 2025.0 |
| `Season` | 100% | 1.0 |
| `crop` | 100% | pigeon_pea |
| `n_plots` | 100% | 41 |
| `sow_median` | 100% | 2025-09-11 00:00:00 |
| `sow_p10` | 100% | 2025-09-03 00:00:00 |
| `sow_p90` | 100% | 2025-09-26 00:00:00 |
| `area_ha_polygon` | 100% | 45.84572263570289 |

## 10_field_survey_landuse_truth_polygons.csv  (3,251 rows)

| column | non-null | example |
|---|---|---|
| `plot_uid` | 100% | 6e55de33ae98 |
| `district` | 100% | Chitradurga |
| `village` | 100% | Singenahalli |
| `Year` | 100% | 2025.0 |
| `Season` | 100% | 1.0 |
| `crop` | 100% | finger_millet |
| `sowing_date` | 100% | 2025-08-30 |
| `next_season_cropped` | 97% | 0.0 |
| `polygon_wkt` | 100% | POLYGON((76.0791263 13.9046173, 76.07893 |
| `polygon_area_ha` | 100% | 0.30443612048419116 |
| `link_lat` | 100% | 13.904888751178692 |
| `link_lon` | 100% | 76.07941883601634 |
| `pixel_id_of_link_point` | 100% | 010390489025607942 |

## 11_mis_koppal_parcels_deidentified.csv  (4,035 rows)

| column | non-null | example |
|---|---|---|
| `parcel_uid` | 100% | def464b24579 |
| `district` | 100% | Koppal |
| `sws_code` | 100% | 4D4A2 |
| `mws_code` | 100% | 4D4A2M1c |
| `mws_name` | 100% | Muralapur-2 |
| `kgis_village_code` | 100% | 0805020010 |
| `survey_hissa` | 100% | 133/*/1 |
| `area_ha` | 100% | 1.37 |
| `owner_female` | 100% | 0.0 |
| `social_group` | 100% | OTHER |
| `farmer_category` | 100% | small |
| `has_fruits_id` | 100% | 1 |
| `ag_code` | 100% | AG3 |
| `soil_phase` | 100% | AWDmA1 |
| `bunding_type` | 100% | TCB |
| `proposed_rmt` | 100% | 276.18 |
| `actual_rmt` | 100% | 226.46760000000003 |
| `actual_rmt_source` | 100% | formula_82pct_of_proposed |
| `actual_rmt_measured` | 72% | 0.0 |
| `proposed_waste_weirs` | 100% | 1.0 |
| `actual_waste_weirs` | 59% | 0.0 |
| `proposed_spillways` | 100% | 0.0 |
| `actual_spillways` | 2% | 28686.02 |
| `proposed_farm_pond` | 100% | 0 |
| `actual_farm_pond` | 100% | 0 |
| `proposed_horti_plants` | 100% | 0.0 |
| `actual_horti_plants` | 100% | 0.0 |
| `proposed_forestry_plants` | 100% | 0.0 |
| `actual_forestry_plants` | 100% | 0.0 |
| `proposed_total_cost_rs` | 100% | 28686.02 |
| `actual_total_cost_rs` | 100% | 11640.434640000001 |
| `parcel_any_actual_work` | 100% | 1 |
| `parcel_any_measured_work` | 100% | 0 |

## 12_mis_koppal_dose_by_mws.csv  (14 rows)

| column | non-null | example |
|---|---|---|
| `district` | 100% | Koppal |
| `sws_code` | 100% | 4D4A2 |
| `mws_code` | 100% | 4D4A2M1c |
| `mws_name` | 100% | Muralapur-2 |
| `n_parcels` | 100% | 271 |
| `area_ha` | 100% | 444.11 |
| `proposed_rmt` | 100% | 88208.18 |
| `actual_rmt_all_rows` | 100% | 56482.5176 |
| `actual_rmt_measured_only` | 100% | 21256.81 |
| `n_parcels_actual_rmt_formula` | 100% | 128 |
| `proposed_waste_weirs` | 100% | 274.0 |
| `actual_waste_weirs` | 100% | 71.0 |
| `proposed_spillways` | 100% | 6.0 |
| `actual_spillways` | 100% | 28692.02 |
| `proposed_farm_ponds` | 100% | 2 |
| `actual_farm_ponds` | 100% | 6 |
| `proposed_horti_plants` | 100% | 0.0 |
| `actual_horti_plants` | 100% | 0.0 |
| `proposed_forestry_plants` | 100% | 0.0 |
| `actual_forestry_plants` | 100% | 0.0 |
| `proposed_cost_rs` | 100% | 9631432.02 |
| `actual_cost_rs` | 100% | 4385527.40464 |
| `n_parcels_any_actual_work` | 100% | 219 |
| `n_parcels_any_measured_work` | 100% | 93 |
| `share_actual_rmt_formula_imputed` | 100% | 0.47232472324723246 |
| `rmt_completion_pct_all_rows` | 100% | 64.03319692119257 |
| `proposed_rmt_measured_rows` | 100% | 45250.0 |
| `rmt_completion_pct_measured_rows` | 100% | 46.97637569060773 |
| `parcels_treated_pct_all` | 100% | 80.81180811808117 |
| `parcels_treated_pct_measured` | 100% | 34.31734317343174 |
| `bund_density_actual_m_per_ha` | 100% | 127.18136857985634 |
| `bund_density_proposed_m_per_ha` | 100% | 198.61786494336985 |
| `cost_completion_pct` | 100% | 45.53349279248716 |

## 13_mis_koppal_dose_by_village.csv  (43 rows)

| column | non-null | example |
|---|---|---|
| `district` | 100% | Koppal |
| `sws_code` | 100% | 4D4A2 |
| `mws_code` | 100% | 4D4A2M1c |
| `kgis_village_code` | 98% | 0704020014 |
| `n_parcels` | 100% | 165 |
| `area_ha` | 100% | 254.58 |
| `proposed_rmt` | 100% | 50300.0 |
| `actual_rmt_all_rows` | 100% | 32886.05 |
| `actual_rmt_measured_only` | 100% | 19495.45 |
| `n_parcels_actual_rmt_formula` | 100% | 53 |
| `proposed_waste_weirs` | 100% | 165.0 |
| `actual_waste_weirs` | 100% | 68.0 |
| `proposed_spillways` | 100% | 4.0 |
| `actual_spillways` | 100% | 4.0 |
| `proposed_farm_ponds` | 100% | 0 |
| `actual_farm_ponds` | 100% | 2 |
| `proposed_horti_plants` | 100% | 0.0 |
| `actual_horti_plants` | 100% | 0.0 |
| `proposed_forestry_plants` | 100% | 0.0 |
| `actual_forestry_plants` | 100% | 0.0 |
| `proposed_cost_rs` | 100% | 5315670.0 |
| `actual_cost_rs` | 100% | 2699523.9699999997 |
| `n_parcels_any_actual_work` | 100% | 134 |
| `n_parcels_any_measured_work` | 100% | 81 |
| `share_actual_rmt_formula_imputed` | 100% | 0.3212121212121212 |
| `rmt_completion_pct_all_rows` | 100% | 65.37982107355866 |
| `proposed_rmt_measured_rows` | 100% | 33970.0 |
| `rmt_completion_pct_measured_rows` | 100% | 57.390197232852515 |
| `parcels_treated_pct_all` | 100% | 81.21212121212122 |
| `parcels_treated_pct_measured` | 100% | 49.09090909090909 |
| `bund_density_actual_m_per_ha` | 100% | 129.1776651740121 |
| `bund_density_proposed_m_per_ha` | 100% | 197.580328384005 |
| `cost_completion_pct` | 100% | 50.78426557705802 |

## 14_mis_koppal_common_land_structures.csv  (175 rows)

| column | non-null | example |
|---|---|---|
| `district` | 100% | Koppal |
| `sws_code` | 100% | 4D4A2 |
| `mws_name` | 100% | Murlapura 2 |
| `village` | 100% | Baradhura |
| `kgis_village_code` | 98% | 0805020010 |
| `proposed_survey_no` | 100% | 147 |
| `activity_type` | 100% | DLT |
| `proposed_sub_activity` | 100% | Boulder Check |
| `proposed_gps_raw` | 3% | N-15'25951  E- 75'9257 |
| `proposed_dimension_section` | 91% | 5.0 |
| `proposed_total_cost_lakh` | 100% | 0.27311 |
| `actual_total_cost_lakh` | 3% | 4.43967 |
| `actual_recorded` | 100% | 0 |

## 15_sws_parcel_counts_from_hissa.csv  (20 rows)

| column | non-null | example |
|---|---|---|
| `sl_no` | 100% | 1 |
| `district_as_written` | 100% | Kalburgi |
| `district_std` | 100% | Kalaburagi |
| `sws_code` | 5% | 4D4A2 |
| `n_mws` | 100% | 12 |
| `n_parcels_private` | 100% | 3634 |
| `n_parcels_common` | 100% | 170 |
| `n_parcels_total` | 100% | 3804 |
| `avg_parcels_per_mws` | 100% | 317 |
| `iva_parcels_in_3_mws` | 100% | 951 |
| `iva_10pct_sample` | 100% | 95.10000000000001 |
| `iva_sample_per_mws` | 100% | 31.700000000000003 |
| `mws_30pct` | 100% | 3.5999999999999996 |
| `mis_received` | 100% | 0 |
| `in_field_survey_2025_26` | 100% | 0 |
| `benchmark_sites_institution` | 95% | UASR |
| `benchmark_sites_institution_note` | 100% | institution assignment inferred from the |

## 16_programme_rules_from_DPR.csv  (5 rows)

| column | non-null | example |
|---|---|---|
| `rule_id` | 100% | disbursement_eligibility |
| `rule` | 100% | MWS eligible for disbursement when >= 70 |
| `source_document` | 100% | DPR discriptions.docx |
| `where_it_is_used` | 100% | parcels_treated_pct_measured in 12_mis_k |

## gee_compositing_windows_by_district.csv  (31 rows)

| column | non-null | example |
|---|---|---|
| `district` | 100% | Bidar |
| `Year` | 100% | 2025 |
| `Season` | 100% | 1 |
| `season_name` | 100% | Kharif |
| `crop` | 100% | pigeon_pea |
| `n_plots` | 100% | 41 |
| `sowing_p10` | 100% | 2025-09-03 |
| `sowing_median` | 100% | 2025-09-11 |
| `sowing_p90` | 100% | 2025-09-26 |
| `sowing_month_mode` | 100% | 9 |
| `share_sown_in_core_months` | 100% | 0.0 |
| `share_sown_in_edge_months` | 100% | 1.0 |
| `duration_class_share_short` | 100% | 0.0 |
| `duration_class_share_medium` | 100% | 1.0 |
| `duration_class_share_long` | 100% | 0.0 |
| `export_window_months` | 100% | [6, 7, 8, 9] |
| `export_core_months` | 100% | [7, 8] |
| `recommendation` | 100% | sown in 9 = late in the Kharif window ([ |
| `duration_days_FILL_IN` | 0% |  |
| `peak_canopy_rule` | 100% | peak_start = sowing_median + 0.45*durati |

## pipeline_inputs/ground_truth_outcomes_LAI_not_yield.csv  (165 rows)

| column | non-null | example |
|---|---|---|
| `institution` | 100% | UAHS |
| `sws_name` | 99% | Beguru |
| `sws_role` | 100% | unlabelled |
| `mws_name` | 99% | Dabbanabairanahalli |
| `bm_site_no` | 39% | UP |
| `latitude` | 100% | 14.291134 |
| `longitude` | 100% | 75.412213 |
| `pixel_id` | 100% | 010429113025541221 |
| `Year` | 100% | 2023 |
| `Season` | 100% | 2 |
| `measured_yield_or_income` | 100% | 3.8336111110833335 |
| `n_visits` | 100% | 12 |
| `crop` | 100% | maize |
| `measured_variable` | 100% | ground_LAI_seasonal_mean_NOT_yield |
| `survey_source` | 100% | benchmark_sites_UAHS |
| `pixel_id_note` | 100% | formula id of the site median coordinate |

## pipeline_inputs/household_characteristics.csv  (57 rows)

| column | non-null | example |
|---|---|---|
| `district` | 100% | Koppal |
| `sws_code` | 100% | 4D4A2 |
| `subwshed_id` | 0% |  |
| `mws_code` | 100% | 4D4A2M1c |
| `mws_name` | 25% | Muralapur-2 |
| `n_parcels` | 100% | 271 |
| `share_owner_female` | 100% | 0.13653136531365315 |
| `share_small_farmer` | 100% | 0.7822878228782287 |
| `share_large_farmer` | 100% | 0.04059040590405904 |
| `mean_parcel_ha` | 100% | 1.6387822878228784 |
| `median_parcel_ha` | 100% | 1.42 |
| `share_sc_st` | 100% | 0.1033210332103321 |
| `share_fruits_id` | 100% | 0.7933579335793358 |
| `grain` | 100% | mws |
| `kgis_village_code` | 74% | 0704020014 |

## pipeline_inputs/intervention_detail.csv  (70 rows)

| column | non-null | example |
|---|---|---|
| `district` | 100% | Koppal |
| `sws_code` | 100% | 4D4A2 |
| `subwshed_id` | 0% |  |
| `mws_code` | 100% | 4D4A2M1c |
| `mws_name` | 100% | Muralapur-2 |
| `completion_date` | 0% |  |
| `completion_date_note` | 100% | not recorded in MIS |
| `intervention_type` | 100% | bunding |
| `works_count` | 100% | 56482.5176 |
| `works_unit` | 100% | running_metres (all rows; see measured c |
| `works_count_measured_only` | 100% | 21256.810000000005 |
| `proposed` | 100% | 88208.18 |
| `area_treated_ha` | 100% | 354.58 |
| `beneficiary_hh_count` | 100% | 218 |

## gee_v111_inputs/gee_compositing_windows_by_district.csv  (31 rows)

| column | non-null | example |
|---|---|---|
| `district` | 100% | Bidar |
| `Year` | 100% | 2025 |
| `Season` | 100% | 1 |
| `season_name` | 100% | Kharif |
| `crop` | 100% | pigeon_pea |
| `n_plots` | 100% | 41 |
| `sowing_p10` | 100% | 2025-09-03 |
| `sowing_median` | 100% | 2025-09-11 |
| `sowing_p90` | 100% | 2025-09-26 |
| `sowing_month_mode` | 100% | 9 |
| `share_sown_in_core_months` | 100% | 0.0 |
| `share_sown_in_edge_months` | 100% | 1.0 |
| `duration_class_share_short` | 100% | 0.0 |
| `duration_class_share_medium` | 100% | 1.0 |
| `duration_class_share_long` | 100% | 0.0 |
| `export_window_months` | 100% | [6, 7, 8, 9] |
| `export_core_months` | 100% | [7, 8] |
| `recommendation` | 100% | sown in 9 = late in the Kharif window ([ |
| `duration_days_FILL_IN` | 0% |  |
| `peak_canopy_rule` | 100% | peak_start = sowing_median + 0.45*durati |

## gee_v111_inputs/gee_district_season_edge_sowing.csv  (19 rows)

| column | non-null | example |
|---|---|---|
| `district` | 100% | Bidar |
| `Season` | 100% | 1 |
| `n_plots` | 100% | 59 |
| `share_sown_in_core` | 100% | 0.0 |
| `share_sown_in_last_window_month` | 100% | 1.0 |
| `season_name` | 100% | Kharif |