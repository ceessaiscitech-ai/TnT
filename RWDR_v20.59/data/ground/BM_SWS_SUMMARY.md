# Benchmark sites -> one mean per sub-watershed

797 physical sites x variables; 821 counted, 50 excluded (location contradicts the name, or no name and no programme core). Each sub-watershed's value = the mean over its sites of each site's mean over visits and replicates (every site counts once).

## Values outside physical bounds (not measurements)

| variable | file | column | bounds | rows | dropped |
|---|---|---|---|---|---|
| ssm_pct | 02_ground_ssm_long.csv | ssm_mean_clean | (0.0, 60.0] | 3,829 | 55 |
| lai | 03_ground_lai_long.csv | lai_mean_clean | (0.0, 10.0] | 687 | 42 |
| gw_depth_m | 04_ground_gw_long.csv | gw_depth_m | [0.0, 300.0] | 3,168 | 3 |
| tdr_rootzone_pct | 06_ground_tdr_rootzone_0_30cm_by_visit.csv | moisture_pct | (0.0, 60.0] | 927 | 2 |
| tdr_rootzone_ec_ds_m | 06_ground_tdr_rootzone_0_30cm_by_visit.csv | ec_ds_m | (0.0, 20.0] | 891 | 0 |
| soil_temp_c | 05_ground_tdr_long.csv | soil_temp_c | (0.0, 60.0] | 291 | 0 |

## Sites per sub-watershed (counted)

| sub-watershed | group | gw_depth_m | lai | soil_temp_c | ssm_pct | tdr_rootzone_ec_ds_m | tdr_rootzone_pct |
|---|---|---|---|---|---|---|---|
| Artal | programme | 38 | 0 | 0 | 0 | 0 | 0 |
| Beguru | programme | 8 | 4 | 0 | 9 | 8 | 8 |
| Chhatrakodihalli | programme | 9 | 0 | 0 | 9 | 0 | 0 |
| Chittharagi | programme | 0 | 0 | 0 | 6 | 1 | 1 |
| Doddenahalli | programme | 9 | 0 | 0 | 9 | 0 | 0 |
| Gadag | control | 9 | 3 | 0 | 3 | 0 | 0 |
| Gummlapalli | programme | 9 | 1 | 0 | 9 | 1 | 1 |
| Haligeri | programme | 14 | 0 | 0 | 0 | 0 | 0 |
| Hanchinal | control | 0 | 2 | 0 | 3 | 0 | 0 |
| Haralahalli | control | 3 | 3 | 0 | 3 | 3 | 3 |
| Holali (Kembodi) | control | 3 | 0 | 0 | 3 | 0 | 0 |
| Honnutagi | programme | 0 | 0 | 0 | 3 | 1 | 1 |
| Hosahalli | control | 12 | 3 | 0 | 3 | 0 | 0 |
| Hunasehadagi | programme | 83 | 1 | 7 | 12 | 24 | 27 |
| ITGI | control | 0 | 0 | 0 | 1 | 0 | 0 |
| Jammapur | programme | 8 | 4 | 0 | 9 | 9 | 9 |
| Jantapur | programme | 11 | 0 | 0 | 1 | 0 | 0 |
| Kandgula | control | 16 | 3 | 0 | 3 | 0 | 0 |
| Kodihalli | programme | 39 | 5 | 0 | 9 | 0 | 0 |
| Kohalli | control | 14 | 3 | 0 | 3 | 0 | 0 |
| Koranahalli | programme | 9 | 5 | 0 | 9 | 9 | 9 |
| Kyatagondanahalli | programme | 9 | 6 | 0 | 9 | 0 | 0 |
| Laxmisagara 4U | control | 3 | 1 | 0 | 3 | 3 | 3 |
| Maidalakere | programme | 9 | 0 | 0 | 9 | 3 | 3 |
| Mattikote | control | 3 | 3 | 0 | 3 | 0 | 0 |
| Murlapura | programme | 22 | 0 | 0 | 0 | 0 | 0 |
| Nagagondanahalli | control | 3 | 3 | 0 | 3 | 0 | 0 |
| Narayanghatta (Annapura) | control | 3 | 0 | 0 | 0 | 0 | 0 |
| Nilgund | programme | 21 | 6 | 0 | 9 | 0 | 0 |
| Pashapur | programme | 50 | 7 | 0 | 9 | 9 | 9 |
| Sirur | programme | 16 | 6 | 0 | 9 | 0 | 0 |
| Virupasandra | control | 3 | 0 | 0 | 3 | 0 | 0 |

## Excluded sites (fix at source if the location or the name is wrong)

| variable | name in file | site | reason |
|---|---|---|---|
| lai | Laxmisagara 4U | 13.96758, 75.97189 | a non-programme site inside the Jammapur core (treated land) |
| lai | Hanchinal sub-watershed | 15.22694, 75.22889 | a non-programme site inside the Sirur core (treated land) |
| ssm_pct | Hanchinal sub-watershed | 15.22694, 75.22889 | a non-programme site inside the Sirur core (treated land) |
| lai | Artal Sub-Watershed | 16.78810, 75.35060 | named Artal but lies in Artal ring 2 |
| ssm_pct | Artal Sub-Watershed | 16.78810, 75.35060 | named Artal but lies in Artal ring 2 |
| lai | Artal Sub-Watershed | 16.44480, 75.17470 | named Artal but lies in outside every programme sub-watershed |
| lai | Artal Sub-Watershed | 16.45190, 75.21220 | named Artal but lies in outside every programme sub-watershed |
| lai | Artal Sub-Watershed | 16.45210, 75.20090 | named Artal but lies in outside every programme sub-watershed |
| lai | Artal Sub-Watershed | 16.46120, 75.20370 | named Artal but lies in outside every programme sub-watershed |
| ssm_pct | Artal Sub-Watershed | 16.43490, 75.17520 | named Artal but lies in outside every programme sub-watershed |
| ssm_pct | Artal Sub-Watershed | 16.44000, 75.17240 | named Artal but lies in outside every programme sub-watershed |
| ssm_pct | Artal Sub-Watershed | 16.44320, 75.17180 | named Artal but lies in outside every programme sub-watershed |
| ssm_pct | Artal Sub-Watershed | 16.44480, 75.17470 | named Artal but lies in outside every programme sub-watershed |
| ssm_pct | Artal Sub-Watershed | 16.45110, 75.18160 | named Artal but lies in outside every programme sub-watershed |
| ssm_pct | Artal Sub-Watershed | 16.45190, 75.21220 | named Artal but lies in outside every programme sub-watershed |
| ssm_pct | Artal Sub-Watershed | 16.45210, 75.20090 | named Artal but lies in outside every programme sub-watershed |
| ssm_pct | Artal Sub-Watershed | 16.46120, 75.20370 | named Artal but lies in outside every programme sub-watershed |
| gw_depth_m | Beguru | 14.26399, 75.74142 | named Beguru but lies in outside every programme sub-watershed |
| gw_depth_m | Halligera | 16.74527, 77.13634 | named Haligeri but lies in Haligeri ring 4 |
| gw_depth_m | Halligera | 16.80700, 77.22030 | named Haligeri but lies in Haligeri ring 5 |
| gw_depth_m | Halligera | 16.80746, 77.23174 | named Haligeri but lies in Haligeri ring 5 |
| gw_depth_m | Halligera | 16.80860, 77.22570 | named Haligeri but lies in Haligeri ring 5 |
| gw_depth_m | Hunsehadagli | 17.32506, 76.70786 | named Hunasehadagi but lies in Hunasehadagi ring 2 |
| gw_depth_m | Hunsehadagli | 17.28497, 76.00000 | named Hunasehadagi but lies in outside every programme sub-watershed |
| gw_depth_m | Hunsehadagli | 17.28784, 76.86651 | named Hunasehadagi but lies in outside every programme sub-watershed |
| gw_depth_m | Kodihalli sub-watershed | 14.42652, 75.51762 | named Kodihalli but lies in outside every programme sub-watershed |
| lai | Koranahalli | 13.67343, 75.97357 | named Koranahalli but lies in Koranahalli ring 3 |
| gw_depth_m | Nilgunda sub-watershed | 15.39827, 75.52067 | named Nilgund but lies in outside every programme sub-watershed |
| tdr_rootzone_ec_ds_m | Pashapur | 18.09167, 77.52663 | named Pashapur but lies in Pashapur ring 4 |
| tdr_rootzone_pct | Pashapur | 18.09167, 77.52663 | named Pashapur but lies in Pashapur ring 4 |
| tdr_rootzone_ec_ds_m | Pashapur | 18.09009, 77.53695 | named Pashapur but lies in Pashapur ring 5 |
| tdr_rootzone_pct | Pashapur | 18.09009, 77.53695 | named Pashapur but lies in Pashapur ring 5 |
| tdr_rootzone_ec_ds_m | Pashapur | 18.09857, 77.54651 | named Pashapur but lies in outside every programme sub-watershed |
| tdr_rootzone_pct | Pashapur | 18.09857, 77.54651 | named Pashapur but lies in outside every programme sub-watershed |
| gw_depth_m | Shirur sub-watershed | 15.12048, 75.25633 | named Sirur but lies in Sirur ring 4 |
| gw_depth_m | Shirur sub-watershed | 15.18641, 75.19694 | named Sirur but lies in Sirur ring 4 |
| gw_depth_m | Shirur sub-watershed | 15.15245, 75.15236 | named Sirur but lies in outside every programme sub-watershed |
| gw_depth_m | Shirur sub-watershed | 15.15376, 75.15384 | named Sirur but lies in outside every programme sub-watershed |
| gw_depth_m | Shirur sub-watershed | 15.15493, 75.15046 | named Sirur but lies in outside every programme sub-watershed |
| gw_depth_m | Shirur sub-watershed | 15.15537, 75.15778 | named Sirur but lies in outside every programme sub-watershed |
| gw_depth_m | Shirur sub-watershed | 15.15683, 75.15666 | named Sirur but lies in outside every programme sub-watershed |
| gw_depth_m | Shirur sub-watershed | 15.16001, 75.17261 | named Sirur but lies in outside every programme sub-watershed |
| gw_depth_m | Shirur sub-watershed | 15.16018, 75.16962 | named Sirur but lies in outside every programme sub-watershed |
| gw_depth_m | Shirur sub-watershed | 15.16079, 75.16715 | named Sirur but lies in outside every programme sub-watershed |
| gw_depth_m | Shirur sub-watershed | 15.16683, 75.17879 | named Sirur but lies in outside every programme sub-watershed |
| gw_depth_m | Shirur sub-watershed | 15.16904, 75.18405 | named Sirur but lies in outside every programme sub-watershed |
| lai | (blank) | (no coordinates) | no name, and the site lies in no programme core |
| ssm_pct | (blank) | (no coordinates) | no name, and the site lies in no programme core |
| ssm_pct | (blank) | (no coordinates) | no name, and the site lies in no programme core |
| ssm_pct | (blank) | (no coordinates) | no name, and the site lies in no programme core |
