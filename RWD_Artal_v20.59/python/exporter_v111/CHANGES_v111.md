# RWD_DP&D_FinalV111 -- ground-data cross-check and survey-based core months

**Base:** v110. Every edit is marked `# ⛑ v111`. Timestamps and progress bars from v110 are untouched.

## The attachments arrived -- what they can and cannot do for the export
| attachment | use in the export | verdict |
|---|---|---|
| Benchmark-site hydrology (UAHS/UASB/UASD/UASR/UHSB; Apr 2023-Jun 2024) | **validate** LAI (direct) and SMDI/LSWI/NDMI/NDWI (proxies) at benchmark points in saturation AND control sub-watersheds | yes -- `ground_crosscheck()` |
| Field survey 2025-26 (3,251 QC-clean cropped polygons with sowing dates) | **validate** the cropland class (`LandUse==2`, `LandUseDW==4`) and Rabi crop presence; **harmonise** the core (priority) months per district | yes -- `ground_crosscheck()`, `recommend_core_months()`, `CORE_MONTHS_OVERRIDE` |
| Groundwater levels | no satellite twin; ground outcome for the DiD side only | not used here |
| Koppal MIS, Hissa counts, DPR | dose / DiD inputs, nothing for the export | not used here |
| Rain / temperature / streamflow | no gauge data in the attachments (streamflow sheets empty) | v110 `reference_crosscheck` remains the only check |

## `ground_crosscheck(year, season)`  (section 12c)
Builds the window exactly as `main()` does, samples the stack at the benchmark-site points (`sampleRegions`, 10 m)
and inside each field polygon (`reduceRegions`), pairs them with the ground season means, prints n / r / bias / RMSE
per pair (LAI, NDVI vs ground LAI; SMDI, LSWI, NDMI, NDWI vs surface and root-zone soil moisture), LAI agreement by
saturation/control SWS, the share of cropped polygons classified `LandUse==2`, the `LandUseDW` class mix over
cropped fields, and Rabi NDVI/LSWI for double- vs single-cropped fields. Exports the paired tables to
`<DRIVE_FOLDER>_validation/GROUND_SITES_*.csv` and `GROUND_PLOTS_*.csv`. Nothing changes the exported panel.

Ground observations are keyed with **this pipeline's** `SEASONS` (`ground_season_key()` = inverse of
`season_window()`), so a January reading pairs with the Rabi window that began the previous October.
Reads the CSVs built by `build_all.py` from `GROUND_INPUTS_DIR` (copy `REWARD_ground_inputs` to Drive).

## `recommend_core_months(district)` and `CORE_MONTHS_OVERRIDE`
The survey's sowing dates, scored against the v110 core months (Kharif Jul-Aug, Rabi Nov-Jan, Zaid Apr):
- Raichur (99 % of Kharif plots) and Gadag (88 %) sow in **June**, the first window month -> peak canopy in
  September, an edge month -> suggestion `{'Kharif': (7, 9)}`.
- Bidar (Rabi pigeon pea, 264 plots) and Chamarajanagar (Rabi maize/horse gram) sow in **October** -> core
  Nov-Jan captures them; `(11, 2)` would add late growth.
- Chamarajanagar Kharif (91 %) and Bidar Kharif sow in **September**, the LAST Kharif month -> their canopy
  develops inside the Rabi window; no core change helps, interpret their Kharif indices as bare/early-field signal.
- Tumkur, Chitradurga: sowing inside the core -> no change.
`CORE_MONTHS_OVERRIDE` (configuration cell) is honoured by `_core_subwindow()` through `_core_months()`; it applies
to every year of the ROI alike (treated and control pixels), so it cannot create a treatment-correlated artefact.
Change it per ROI and re-download that ROI; the rest of the panel is unaffected.

## Verification (offline mock, same harness as v110)
`run_mock.py rabi`: Rabi 2025/2026 build and validate as in v110. `test_notebook.py`: 36 cells OK, 0 FAIL.
`test_v111_ground.py`: season keys match `season_window()`, override extends the Kharif core to Jul-Sep,
`recommend_core_months('Raichur')` returns `{'Kharif': (7, 9)}`, `ground_crosscheck` runs both the site and the
polygon branches and queues the two exports. The mock has no real pixel values, so the printed r/bias are
meaningless there; on Earth Engine they are the validation numbers.

## v111 audit fixes (2026-09-14, second pass)
- `ground_crosscheck`: `reduceRegions` output names forced to the band name when only one band is reduced (EE names a single-band output 'mode'/'mean', which broke the client-side join).
- `_ground_csv`: also looks in `gee_v111_inputs/` (where `gee_compositing_windows_by_district.csv` ships).
- Re-verified: `run_mock rabi`, `test_notebook` 36/36, `test_v111_ground` (site + polygon branches, 3 export tasks).
