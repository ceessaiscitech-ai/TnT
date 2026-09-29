"""
build_all.py -- build every ground-data input for the REWARD DiD pipeline from the raw files
=============================================================================================
Usage:  python build_all.py <folder with the raw files> <output folder>
Raw files expected (as delivered in PatchDPRAIRUn):
    Benchmark sites data/<INST> Bench marks sites hydrology data*.xlsx   (UAHS, UASB, UASD, UASR, UHSB; IISc is an empty template)
    99. All Field Survey Data - [03.12.2025 to 02.05.2026].xlsx
    REWARD MIS-Koppal New.xlsx
"""
import os, sys, glob, json, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from ground_utils import pixel_id_from_latlon, panel_year_season, sws_role
from ground_parsers import parse_ssm, parse_lai, parse_gw
from ground_tdr import parse_tdr
from field_survey import build_field_survey, crop_calendar
from mis_koppal import load_pvt, parcel_table, dose_table, intervention_detail, household_characteristics, common_land, SWS_CODE as SWS_CODE_KOPPAL
from _ground_common import site_master, attach_site_median_coords, ground_treated_control_table

INST_FILES = {"UAHS": "UAHS Bench marks*", "UASB": "UASB Bench marks*", "UASD": "UASD Bench marks*",
              "UASR": "UASR Bench marks*", "UHSB": "UHSB Bench marks*"}

def _find(folder, pattern):
    hits = glob.glob(os.path.join(folder, "**", pattern), recursive=True)
    hits = [h for h in hits if "zipcheck" not in h]
    return hits[0] if hits else None

def add_keys(df, key):
    """Pipeline (Year, Season) keys from the observation date + pixel_id of the SITE median coordinate."""
    d = df.copy()
    ys = [panel_year_season(x) if pd.notna(x) else (np.nan, np.nan) for x in d["date"]]
    d["Year"] = [a for a, _ in ys]; d["Season"] = [b for _, b in ys]
    d["pixel_id_site_median"] = pixel_id_from_latlon(d["lat_site"].values, d["lon_site"].values)
    return d

def main(raw, out):
    os.makedirs(out, exist_ok=True); os.makedirs(os.path.join(out, "pipeline_inputs"), exist_ok=True)
    qc = {}
    # ---------------------------------------------------------------- benchmark hydrology
    ssm, lai, gw, tdr = [], [], [], []
    for inst, pat in INST_FILES.items():
        f = _find(raw, pat)
        if f is None:
            print(f"[WARNING] {inst} workbook not found"); continue
        for name, fn, acc in (("SSM", parse_ssm, ssm), ("LAI", parse_lai, lai), ("Manual GW", parse_gw, gw), ("TDR", parse_tdr, tdr)):
            try:
                d = fn(f, inst); acc.append(d); print(f"[OK]      {inst} {name}: {len(d):,} rows")
            except Exception as e:
                print(f"[FAILED]  {inst} {name}: {e}")
    ssm = pd.concat(ssm, ignore_index=True); lai = pd.concat(lai, ignore_index=True)
    gw = pd.concat(gw, ignore_index=True); tdr = pd.concat(tdr, ignore_index=True)
    # TDR: UAHS block titles cover two SWS ('Jammapura and Laxmisagara 4U'); resolve via MWS -> SWS from SSM
    m2s = ssm.dropna(subset=["mws_name"]).groupby("mws_name")["sws_name"].agg(lambda s: s.mode().iloc[0])
    tdr["sws_name_block"] = tdr["sws_name"]
    tdr["sws_name"] = tdr["mws_name"].map(m2s).fillna(tdr["sws_name"])
    # single-number depth labels = layer bottom in 10-cm steps
    tdr["depth_top_cm"] = np.where(tdr["depth_top_cm"].isna() & tdr["depth_bottom_cm"].notna(), tdr["depth_bottom_cm"] - 10, tdr["depth_top_cm"])
    tdr["moisture_flag"] = np.where(tdr["moisture_pct"] > 100, "implausible_gt_100pct", np.where(tdr["moisture_pct"] < 0, "negative", ""))
    tdr["moisture_pct_clean"] = np.where(tdr["moisture_flag"] == "", tdr["moisture_pct"], np.nan)
    # ---- value flags (nothing deleted: *_clean columns are NaN where the flag is set)
    ssm["ssm_flag"] = np.where(ssm["ssm_mean"] < 0, "negative", np.where(ssm["ssm_mean"] > 100, "gt_100pct", ""))
    ssm["ssm_mean_clean"] = np.where(ssm["ssm_flag"] == "", ssm["ssm_mean"], np.nan)
    lai["lai_flag"] = np.where(lai["lai_mean"] < 0, "negative", np.where(lai["lai_mean"] > 10, "gt_10", ""))
    lai["lai_mean_clean"] = np.where(lai["lai_flag"] == "", lai["lai_mean"], np.nan)
    # ---- units as labelled in each workbook header vs the unit the values support
    SSM_UNIT_LABEL = {"UAHS": "avg Soil moisture in mm (template label)", "UASB": "Avg SSM%", "UASD": "Avg. Soil moisture in mm (template label)",
                      "UASR": "soil moisture (no unit given)", "UHSB": "no unit given"}
    ssm["unit_as_labelled"] = ssm["institution"].map(SSM_UNIT_LABEL)
    ssm["unit_used"] = "% (v/v, 0-10 cm probe): the 0-60 range rules out mm of water in a 10 cm layer"
    gw["unit_as_labelled"] = gw["institution"].map({"UASD": "well_depth column labelled ft; readings unlabelled", "UHSB": "well_depth (m)", "UASR": "m ('11.30 m' strings)", "UAHS": "unlabelled", "UASB": "unlabelled"})
    gw["unit_used"] = "m below ground level (readings 0-104 m are consistent with metres at every institution)"
    tdr["unit_used"] = "% volumetric (TDR probe); EC in dS/m"
    # ---- duplicate observations (copy-paste blocks): same site (incl. coordinates) + same date
    def dedupe(df, key_extra, valcols, name):
        d = df.copy()
        d["_lat5"] = d["latitude"].round(5); d["_lon5"] = d["longitude"].round(5)
        key = ["institution", "sws_name", "mws_name"] + key_extra + ["_lat5", "_lon5", "date"]
        same_key = d.duplicated(key, keep=False)
        identical = d.duplicated(key + valcols, keep="first")
        d["dup_key_flag"] = np.where(identical, "identical_duplicate_dropped", np.where(same_key, "same_site_date_different_values", ""))
        n_ident = int(identical.sum())
        qc.setdefault("duplicates", {})[name] = {"same_site_date_rows": int(same_key.sum()), "identical_rows_dropped": n_ident}
        return d[~identical].drop(columns=["_lat5", "_lon5"])
    ssm = dedupe(ssm, ["bm_site_no", "survey_no"], ["ssm1", "ssm2", "ssm3"], "ssm")
    lai = dedupe(lai, ["bm_site_no", "survey_no"], ["lai1", "lai2", "lai3"], "lai")
    gw = dedupe(gw, ["borewell_no"], ["gw_depth_m"], "gw")
    tdr = dedupe(tdr, ["probe_or_survey_no", "depth_label"], ["moisture_pct", "ec_ds_m"], "tdr")
    # site master (median coordinates) + roles
    ms = site_master(ssm, lai, gw, tdr)
    ssm = attach_site_median_coords(ssm, ms, "ssm", "bm_site_no"); lai = attach_site_median_coords(lai, ms, "lai", "bm_site_no")
    gw = attach_site_median_coords(gw, ms, "gw", "borewell_no"); tdr = attach_site_median_coords(tdr, ms, "tdr", "probe_or_survey_no")
    for d in (ssm, lai, gw, tdr):
        d["sws_role"] = d["sws_name"].map(sws_role)
    ssm, lai, gw, tdr = add_keys(ssm, "bm_site_no"), add_keys(lai, "bm_site_no"), add_keys(gw, "borewell_no"), add_keys(tdr, "probe_or_survey_no")
    ms["pixel_id_site_median"] = pixel_id_from_latlon(ms["lat_median"].values, ms["lon_median"].values)
    # TDR root zone (0-30 cm) per probe-visit
    rz = tdr[(tdr["depth_bottom_cm"] <= 30) & tdr["moisture_pct_clean"].notna()]
    rz = rz.groupby(["institution", "sws_name", "sws_role", "mws_name", "probe_or_survey_no", "date", "date_flag", "lat_site", "lon_site", "crop", "Year", "Season"], dropna=False) \
           .agg(moisture_pct=("moisture_pct_clean", "mean"), n_layers=("moisture_pct_clean", "size"), ec_ds_m=("ec_ds_m", "mean")).reset_index()
    rz["pixel_id_site_median"] = pixel_id_from_latlon(rz["lat_site"].values, rz["lon_site"].values)
    # ordered columns
    site_cols = ["institution", "sws_name", "sws_role", "mws_name", "district", "bm_site_no", "survey_no", "soil_phase",
                 "latitude", "longitude", "lat_site", "lon_site", "dist_to_site_median_m", "coord_outlier_gt_300m", "pixel_id_site_median",
                 "date", "date_flag", "Year", "Season"]
    ssm_out = ssm[site_cols + ["crop_raw", "crop", "ssm1", "ssm2", "ssm3", "ssm_mean", "ssm_mean_clean", "ssm_flag", "n_replicates", "reported_avg_minus_mean3",
                               "soil_temp_mean_c" if "soil_temp_mean_c" in ssm else "remark", "remark", "unit_as_labelled", "unit_used", "dup_key_flag", "site_cols_inherited", "source_sheet", "source_row"]]
    lai_out = lai[site_cols + ["crop_raw", "crop", "crop_source", "lai1", "lai2", "lai3", "lai_mean", "lai_mean_clean", "lai_flag", "n_replicates", "reported_avg_minus_mean3",
                               "crop_height_cm", "days_after_sowing", "remark", "dup_key_flag", "site_cols_inherited", "source_sheet", "source_row"]]
    gw_cols = [c for c in site_cols if c not in ("bm_site_no", "survey_no")] + ["bm_site_no", "borewell_no", "survey_no", "village", "well_type",
               "ground_level_m", "well_depth", "well_depth_unit", "geomorphology", "irrigation_method", "gw_depth_m", "value_flag", "unit_as_labelled", "unit_used", "crop_remark", "dup_key_flag", "source_sheet", "source_row"]
    for c in ("village", "well_type"):
        if c not in gw: gw[c] = ""
    gw_out = gw[gw_cols]
    tdr_out = tdr[["institution", "sws_name", "sws_name_block", "sws_role", "mws_name", "bm_site_no", "probe_or_survey_no", "latitude", "longitude",
                   "lat_site", "lon_site", "dist_to_site_median_m", "coord_outlier_gt_300m", "pixel_id_site_median", "date", "date_flag", "Year", "Season",
                   "visit_id", "irrigation_type", "crop_raw", "crop", "depth_label", "depth_top_cm", "depth_bottom_cm", "moisture_pct", "moisture_pct_clean",
                   "moisture_flag", "ec_ds_m"] + (["soil_temp_c"] if "soil_temp_c" in tdr else []) + ["unit_used", "value_flag", "dup_key_flag", "source_sheet", "source_row"]]
    tc = ground_treated_control_table(ssm.assign(ssm_mean=ssm["ssm_mean_clean"]), lai.assign(lai_mean=lai["lai_mean_clean"]), gw, rz)
    # write
    ms.to_csv(os.path.join(out, "01_benchmark_sites_master.csv"), index=False)
    ssm_out.to_csv(os.path.join(out, "02_ground_ssm_long.csv"), index=False)
    lai_out.to_csv(os.path.join(out, "03_ground_lai_long.csv"), index=False)
    gw_out.to_csv(os.path.join(out, "04_ground_gw_long.csv"), index=False)
    tdr_out.to_csv(os.path.join(out, "05_ground_tdr_long.csv"), index=False)
    rz.to_csv(os.path.join(out, "06_ground_tdr_rootzone_0_30cm_by_visit.csv"), index=False)
    tc.to_csv(os.path.join(out, "07_ground_site_season_means_treated_control.csv"), index=False)
    qc["benchmark"] = {
        "ssm_rows": int(len(ssm)), "lai_rows": int(len(lai)), "gw_rows": int(len(gw)), "tdr_rows": int(len(tdr)), "tdr_rootzone_visits": int(len(rz)),
        "sites_in_master": int(len(ms)), "sites_by_role": {f"{a}|{b}": int(n) for (a, b), n in ms.groupby("variable")["sws_role"].value_counts().items()},
        "date_flags_ssm": ssm.date_flag.value_counts().to_dict(), "date_flags_lai": lai.date_flag.value_counts().to_dict(),
        "date_flags_gw": gw.date_flag.value_counts().to_dict(), "date_flags_tdr": tdr.date_flag.value_counts().to_dict(),
        "ssm_coord_outliers": int(ssm.coord_outlier_gt_300m.sum()), "ssm_no_coords": int(ssm.latitude.isna().sum()),
        "lai_no_coords": int(lai.latitude.isna().sum()), "gw_value_flags": gw.value_flag.value_counts().to_dict(),
        "tdr_moisture_flags": tdr.moisture_flag.value_counts().to_dict(),
        "date_range": {k: [str(d.date.min().date()), str(d.date.max().date())] for k, d in (("ssm", ssm), ("lai", lai), ("gw", gw), ("tdr", tdr))},
        "year_season_counts": {k: {f"{int(a)}-S{int(b)}": int(n) for (a, b), n in d.dropna(subset=["Year"]).groupby(["Year", "Season"]).size().items()}
                               for k, d in (("ssm", ssm), ("lai", lai), ("gw", gw))},
    }
    # ---------------------------------------------------------------- field survey
    f = _find(raw, "99. All Field Survey Data*.xlsx")
    plots = build_field_survey(f)
    plots.to_csv(os.path.join(out, "08_field_survey_plots_deidentified.csv"), index=False)
    cc = crop_calendar(plots); cc.to_csv(os.path.join(out, "09_field_survey_crop_calendar.csv"), index=False)
    lu = plots[plots.qc_flags.eq("") | plots.qc_flags.eq("crop_unmapped")][["plot_uid", "district", "village", "Year", "Season", "crop", "sowing_date",
                                                                            "next_season_cropped", "polygon_wkt", "polygon_area_ha", "link_lat", "link_lon", "pixel_id_of_link_point"]]
    lu.to_csv(os.path.join(out, "10_field_survey_landuse_truth_polygons.csv"), index=False)
    qc["field_survey"] = {"plots": int(len(plots)), "farmers": int(plots.farmer_uid.nunique()), "districts": plots.district.value_counts().to_dict(),
                          "qc_flags": plots.qc_flags.str.split(";").explode().value_counts().to_dict(),
                          "year_season": {f"{int(a)}-S{int(b)}": int(n) for (a, b), n in plots.dropna(subset=["Year"]).groupby(["Year", "Season"]).size().items()},
                          "crops_top": plots.crop.value_counts().head(15).to_dict(), "usable_for_landuse_truth": int(len(lu)),
                          "next_season_cropped_share": float(plots.next_season_cropped.mean())}
    # ---------------------------------------------------------------- MIS Koppal
    f = _find(raw, "REWARD MIS-Koppal*.xlsx")
    pv = load_pvt(f); t = parcel_table(pv)
    t.to_csv(os.path.join(out, "11_mis_koppal_parcels_deidentified.csv"), index=False)
    dm = dose_table(t, ["mws_code", "mws_name"]); dm.to_csv(os.path.join(out, "12_mis_koppal_dose_by_mws.csv"), index=False)
    dv = dose_table(t, ["mws_code", "kgis_village_code"]); dv.to_csv(os.path.join(out, "13_mis_koppal_dose_by_village.csv"), index=False)
    cl = common_land(f); cl.to_csv(os.path.join(out, "14_mis_koppal_common_land_structures.csv"), index=False)
    idt = intervention_detail(t); idt.to_csv(os.path.join(out, "pipeline_inputs", "intervention_detail.csv"), index=False)
    hh_m = household_characteristics(t, ["mws_code", "mws_name"]); hh_v = household_characteristics(t, ["mws_code", "kgis_village_code"])
    hh = pd.concat([hh_m.assign(grain="mws"), hh_v.assign(grain="kgis_village")], ignore_index=True)
    hh.insert(2, "subwshed_id", "")
    hh.to_csv(os.path.join(out, "pipeline_inputs", "household_characteristics.csv"), index=False)
    qc["mis_koppal"] = {"parcels": int(len(t)), "mws": int(t.mws_code.nunique()), "villages": int(t.kgis_village_code.nunique()),
                        "actual_rmt_source": t.actual_rmt_source.value_counts().to_dict(),
                        "rmt_completion_pct_all_rows_total": float(100 * t.actual_rmt.sum() / t.proposed_rmt.sum()),
                        "rmt_completion_pct_measured_rows_total": float(100 * t.actual_rmt_measured.sum() / t.loc[t.actual_rmt_source == "value", "proposed_rmt"].sum()),
                        "common_land_structures": int(len(cl)), "common_land_with_actuals": int(cl.actual_recorded.sum())}
    # ---------------------------------------------------------------- Hissa parcel counts (all 20 SWS) + DPR programme rules
    f = _find(raw, "Hissa_parcel Counts*.xlsx")
    if f:
        h = pd.read_excel(f, header=None)
        h = h.iloc[1:21, :11]; h.columns = ["sl_no", "district_as_written", "n_parcels_private", "n_parcels_common", "n_parcels_total", "n_mws", "avg_parcels_per_mws",
                                            "iva_parcels_in_3_mws", "iva_10pct_sample", "iva_sample_per_mws", "mws_30pct"]
        STD = {"Kalburgi": "Kalaburagi", "Chamarajnagar": "Chamarajanagar", "Dhawad": "Dharwad", "Belgaum": "Belagavi", "Hasan": "Hassan", "Chikkamagalur": "Chikkamagaluru"}
        h["district_std"] = h["district_as_written"].map(lambda x: STD.get(str(x).strip(), str(x).strip()))
        h["sws_code"] = np.where(h["district_std"] == "Koppal", SWS_CODE_KOPPAL, "")
        h["mis_received"] = np.where(h["district_std"] == "Koppal", 1, 0)
        h["in_field_survey_2025_26"] = h["district_std"].isin(plots.district.unique()).astype(int)
        h["benchmark_sites_institution"] = h["district_std"].map({"Koppal": "UASR", "Raichur": "UASR", "Kalaburagi": "UASR", "Gadag": "UASD", "Belagavi": "UASD", "Haveri": "UASD", "Dharwad": "UASD",
                                                                  "Bagalkot": "UHSB", "Vijayapura": "UHSB", "Bidar": "UHSB", "Shivamogga": "UAHS", "Davanagere": "UAHS", "Chikkamagaluru": "UAHS",
                                                                  "Chitradurga": "UAHS/UASB", "Tumkur": "UASB", "Kolar": "UASB", "Chikkaballapura": "UASB", "Hassan": "UASB", "Chamarajanagar": "UASB"}).fillna("")
        h["benchmark_sites_institution_note"] = "institution assignment inferred from the SWS names in the workbooks; confirm against your monitoring contracts"
        h = h[["sl_no", "district_as_written", "district_std", "sws_code", "n_mws", "n_parcels_private", "n_parcels_common", "n_parcels_total", "avg_parcels_per_mws",
               "iva_parcels_in_3_mws", "iva_10pct_sample", "iva_sample_per_mws", "mws_30pct", "mis_received", "in_field_survey_2025_26", "benchmark_sites_institution", "benchmark_sites_institution_note"]]
        h.to_csv(os.path.join(out, "15_sws_parcel_counts_from_hissa.csv"), index=False)
        qc["hissa"] = {"districts": int(len(h)), "total_parcels": int(pd.to_numeric(h.n_parcels_total).sum()), "total_mws": int(pd.to_numeric(h.n_mws).sum()),
                       "koppal_pvt_matches_mis": bool(int(h.loc[h.district_std == "Koppal", "n_parcels_private"].iloc[0]) == len(t))}
    rules = pd.DataFrame([
        ["disbursement_eligibility", "MWS eligible for disbursement when >= 70% of its parcels (hissas) are treated", "DPR discriptions.docx", "parcels_treated_pct_measured in 12_mis_koppal_dose_by_mws.csv is the MWS-level test of this rule"],
        ["iva_sampling_mws", "IVA verifies 3 MWS per district (upper, middle, lower reach; ~30% of MWS)", "DPR discriptions.docx / Hissa_parcel Counts.xlsx", "15_sws_parcel_counts_from_hissa.csv columns iva_*"],
        ["iva_sampling_parcels", "10% of parcels sampled per MWS, across activity types", "Hissa_parcel Counts.xlsx note b/c", "-"],
        ["programme_scale", "191 MWS in 20 SWS (one per district); 125,620 parcels (122,721 private + 2,899 common)", "Hissa_parcel Counts.xlsx", "denominators for saturation shares"],
        ["treatment_unit", "the parcel (hissa) is the unit of physical treatment; MWS is the unit of eligibility; SWS is the unit of the DiD treatment indicator (buff_km = 0)", "DPR discriptions.docx", "grain mismatch: dose can be MWS-level, treatment is SWS-level"],
    ], columns=["rule_id", "rule", "source_document", "where_it_is_used"])
    rules.to_csv(os.path.join(out, "16_programme_rules_from_DPR.csv"), index=False)
    # ---------------------------------------------------------------- M07-style ground outcome file (LAI, not yield)
    g7 = lai.dropna(subset=["lai_mean_clean", "Year", "lat_site"]).copy(); g7["lai_mean"] = g7["lai_mean_clean"]
    g7 = g7.groupby(["institution", "sws_name", "sws_role", "mws_name", "bm_site_no", "lat_site", "lon_site", "pixel_id_site_median", "Year", "Season"], dropna=False) \
           .agg(measured_yield_or_income=("lai_mean", "mean"), n_visits=("lai_mean", "size"), crop=("crop", lambda s: s.mode().iloc[0] if len(s.mode()) else "")).reset_index()
    g7["measured_variable"] = "ground_LAI_seasonal_mean_NOT_yield"; g7["survey_source"] = "benchmark_sites_" + g7["institution"]
    g7 = g7.rename(columns={"pixel_id_site_median": "pixel_id", "lat_site": "latitude", "lon_site": "longitude"})
    g7["pixel_id_note"] = "formula id of the site median coordinate; replace with pixel_id_nearest from _ground_common.snap_to_panel_pixels before merging"
    g7.to_csv(os.path.join(out, "pipeline_inputs", "ground_truth_outcomes_LAI_not_yield.csv"), index=False)
    with open(os.path.join(out, "QC_SUMMARY.json"), "w") as fh:
        json.dump(qc, fh, indent=2, default=str)
    print(json.dumps(qc, indent=1, default=str)[:6000])
    return qc

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
