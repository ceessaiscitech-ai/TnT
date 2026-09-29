"""
mis_koppal.py -- restructure 'REWARD MIS-Koppal New.xlsx' into pipeline inputs
==============================================================================
The MIS is parcel (hissa) level: 4,035 private parcels in 14 micro-watersheds (MWS) of the Koppal
saturation sub-watershed (SWS code 4D4A2), plus 175 proposed common-land drainage-line structures.

What this produces
------------------
1. parcel-level table WITHOUT names / phone numbers, with a `actual_rmt_source` column that says
   whether the 'Actual RMT' cell was a typed value or the spreadsheet formula =Proposed*82/100.
   (1,145 of 4,035 'actual' bunding lengths are that formula -- they are NOT measurements.)
2. MWS-level and KGIS-village-level physical-works dose tables (proposed vs actual, measured-only
   and all-rows variants, parcel-treated shares), i.e. the 'intervention_detail.csv' the pipeline's
   HOUSEHOLD_SURVEY_DATA_SPEC asks for -- minus completion dates, which the MIS does not record.
3. village/MWS aggregate household characteristics (female-owner share, small-farmer share, mean
   holding, SC/ST share) for M26 heterogeneity -- aggregates only.
"""
import re, hashlib
import numpy as np
import pandas as pd
from openpyxl import load_workbook

SWS_CODE = "4D4A2"; DISTRICT = "Koppal"

def _num(s):
    return pd.to_numeric(s, errors="coerce")

def load_pvt(path):
    """Read with cached values AND detect formula cells in the 'Actual' columns."""
    df = pd.read_excel(path, sheet_name="PVT Land MIS (2)")
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    wb = load_workbook(path, read_only=True)
    ws = wb["PVT Land MIS (2)"]
    rows = list(ws.iter_rows(values_only=True))
    hdr = [re.sub(r"\s+", " ", str(c)).strip() if c else "" for c in rows[0]]
    idx = {h: i for i, h in enumerate(hdr) if h}
    def kind(col):
        i = idx[col]
        out = []
        for r in rows[1:]:
            v = r[i] if i < len(r) else None
            if v is None or v == "": out.append("blank")
            elif isinstance(v, str) and v.startswith("="):
                m = re.match(r"^=Z\d+\*(\d+)/100$", v)
                out.append(f"formula_{m.group(1)}pct_of_proposed" if m else "formula:" + re.sub(r"\d+", "#", v)[:25])
            else: out.append("value")
        return out
    df["actual_rmt_source"] = kind("Actual RMT")[:len(df)]
    df["actual_ww_source"] = kind("Actual Waste Weirs (Nos)")[:len(df)]
    return df

def parcel_table(df):
    """De-identified parcel table."""
    t = pd.DataFrame()
    t["parcel_uid"] = [hashlib.sha1(f"{a}|{b}|{c}".encode()).hexdigest()[:12]
                       for a, b, c in zip(df["MWS CODE"], df["KGISvillage_Code"], df["Survey hissa"])]
    t["district"] = DISTRICT; t["sws_code"] = SWS_CODE
    t["mws_code"] = df["MWS CODE"].fillna("").astype(str).str.strip()
    t["mws_name"] = df["MWS Name"].fillna("").astype(str).str.strip()
    t["kgis_village_code"] = df["KGISvillage_Code"].apply(lambda v: f"{int(v):010d}" if pd.notna(v) else "")
    t["survey_hissa"] = df["Survey hissa"].fillna("").astype(str).str.strip()
    t["area_ha"] = _num(df["Area (ha)"])
    g = df["Gender (M/F)"].fillna("").astype(str).str.strip().str.lower()
    t["owner_female"] = np.where(g.str.startswith("f"), 1, np.where(g.str.startswith("m"), 0, np.nan))
    c = df["Caste (SC/ST/OBC/MIN/ GEN)"].fillna("").astype(str).str.strip().str.upper().replace({"0THER": "OTHER", "0BC": "OBC"})
    t["social_group"] = c.where(c.isin(["SC", "ST", "OBC", "OTHER", "MIN", "GEN"]), "")
    cat = df["Category (MF/SF/ MEF/LF)"].fillna("").astype(str).str.strip().str.upper()
    t["farmer_category"] = cat.replace({"SMALL": "small", "MEDIUM": "medium", "LARGE": "large", "LF": "large", "SMALL ": "small"})
    t.loc[~t["farmer_category"].isin(["small", "medium", "large"]), "farmer_category"] = ""
    t["has_fruits_id"] = df["Fruit ID"].fillna("").astype(str).str.startswith("FID").astype(int)
    t["ag_code"] = df["AG Code"].fillna("").astype(str).str.strip().replace("nan", "")
    t["soil_phase"] = df["Soil Phase"].fillna("").astype(str).str.strip().replace("nan", "")
    t["bunding_type"] = df["Bunding"].fillna("").astype(str).str.strip().replace("nan", "")
    # physical works: proposed vs actual
    t["proposed_rmt"] = _num(df["Proposed RMT"]); t["actual_rmt"] = _num(df["Actual RMT"])
    t["actual_rmt_source"] = df["actual_rmt_source"]
    t["actual_rmt_measured"] = np.where(t["actual_rmt_source"] == "value", t["actual_rmt"], np.nan)
    t["proposed_waste_weirs"] = _num(df["Proposed Waste Weirs (Nos)"]); t["actual_waste_weirs"] = _num(df["Actual Waste Weirs (Nos)"])
    t["proposed_spillways"] = _num(df["Proposed Spilway (No.)"]); t["actual_spillways"] = _num(df["Actual Spilway (No.)"])
    fp_p = df["Proposed Farm Pond size"].fillna("").astype(str).str.strip(); fp_a = df["Actual Farm Pond size"].fillna("").astype(str).str.strip()
    t["proposed_farm_pond"] = (~fp_p.isin(["0", "0.0", "", "nan", "None"])).astype(int)
    t["actual_farm_pond"] = (~fp_a.isin(["0", "0.0", "", "nan", "None"])).astype(int)
    hp = sum(_num(df[f"Proposed No of Plants {k}"]).fillna(0) for k in (1, 2, 3, 4))
    ha = sum(_num(df[f"Actual No of Plants {k}"]).fillna(0) for k in (1, 2, 3, 4))
    t["proposed_horti_plants"] = hp; t["actual_horti_plants"] = ha
    t["proposed_forestry_plants"] = _num(df["Proposed No of Plants"]).fillna(0); t["actual_forestry_plants"] = _num(df["Actual No of Plants"]).fillna(0)
    t["proposed_total_cost_rs"] = _num(df["Proposed Total Beneficiary Cost"]); t["actual_total_cost_rs"] = _num(df["Actual Total Beneficiary Cost"])
    t["parcel_any_actual_work"] = ((t["actual_rmt"].fillna(0) > 0) | (t["actual_waste_weirs"].fillna(0) > 0) |
                                   (t["actual_farm_pond"] > 0) | (ha > 0) | (t["actual_forestry_plants"] > 0)).astype(int)
    t["parcel_any_measured_work"] = ((t["actual_rmt_measured"].fillna(0) > 0) | (t["actual_waste_weirs"].fillna(0) > 0) |
                                     (t["actual_farm_pond"] > 0) | (ha > 0) | (t["actual_forestry_plants"] > 0)).astype(int)
    return t[t["mws_code"].ne("nan") & t["mws_code"].ne("")]

def dose_table(t, by):
    """Aggregate physical works by MWS or by KGIS village. `by` = ['mws_code','mws_name'] or ['mws_code','kgis_village_code']."""
    g = t.groupby(by)
    d = pd.DataFrame({
        "n_parcels": g.size(), "area_ha": g["area_ha"].sum(),
        "proposed_rmt": g["proposed_rmt"].sum(), "actual_rmt_all_rows": g["actual_rmt"].sum(),
        "actual_rmt_measured_only": g["actual_rmt_measured"].sum(),
        "n_parcels_actual_rmt_formula": g["actual_rmt_source"].apply(lambda s: s.str.startswith("formula").sum()),
        "proposed_waste_weirs": g["proposed_waste_weirs"].sum(), "actual_waste_weirs": g["actual_waste_weirs"].sum(),
        "proposed_spillways": g["proposed_spillways"].sum(), "actual_spillways": g["actual_spillways"].sum(),
        "proposed_farm_ponds": g["proposed_farm_pond"].sum(), "actual_farm_ponds": g["actual_farm_pond"].sum(),
        "proposed_horti_plants": g["proposed_horti_plants"].sum(), "actual_horti_plants": g["actual_horti_plants"].sum(),
        "proposed_forestry_plants": g["proposed_forestry_plants"].sum(), "actual_forestry_plants": g["actual_forestry_plants"].sum(),
        "proposed_cost_rs": g["proposed_total_cost_rs"].sum(), "actual_cost_rs": g["actual_total_cost_rs"].sum(),
        "n_parcels_any_actual_work": g["parcel_any_actual_work"].sum(),
        "n_parcels_any_measured_work": g["parcel_any_measured_work"].sum(),
    }).reset_index()
    d["share_actual_rmt_formula_imputed"] = d["n_parcels_actual_rmt_formula"] / d["n_parcels"]
    d["rmt_completion_pct_all_rows"] = 100 * d["actual_rmt_all_rows"] / d["proposed_rmt"]
    meas_prop = t[t["actual_rmt_source"] == "value"].groupby(by)["proposed_rmt"].sum()
    d = d.merge(meas_prop.rename("proposed_rmt_measured_rows").reset_index(), on=by, how="left")
    d["rmt_completion_pct_measured_rows"] = 100 * d["actual_rmt_measured_only"] / d["proposed_rmt_measured_rows"]
    d["parcels_treated_pct_all"] = 100 * d["n_parcels_any_actual_work"] / d["n_parcels"]
    d["parcels_treated_pct_measured"] = 100 * d["n_parcels_any_measured_work"] / d["n_parcels"]
    d["bund_density_actual_m_per_ha"] = d["actual_rmt_all_rows"] / d["area_ha"]
    d["bund_density_proposed_m_per_ha"] = d["proposed_rmt"] / d["area_ha"]
    d["cost_completion_pct"] = 100 * d["actual_cost_rs"] / d["proposed_cost_rs"]
    d.insert(0, "district", DISTRICT); d.insert(1, "sws_code", SWS_CODE)
    return d

def intervention_detail(t):
    """Long format per pipeline spec: subwshed_id | intervention_type | completion_date | works_count | area_treated_ha | beneficiary_hh_count.
    completion_date is NOT in the MIS -> left blank on purpose. Grain = MWS (finer than the district fund file)."""
    recs = []
    for (mc, mn), g in t.groupby(["mws_code", "mws_name"]):
        base = {"district": DISTRICT, "sws_code": SWS_CODE, "subwshed_id": "", "mws_code": mc, "mws_name": mn,
                "completion_date": "", "completion_date_note": "not recorded in MIS"}
        recs.append({**base, "intervention_type": "bunding", "works_count": float(g["actual_rmt"].sum()), "works_unit": "running_metres (all rows; see measured column)",
                     "works_count_measured_only": float(g["actual_rmt_measured"].sum()), "proposed": float(g["proposed_rmt"].sum()),
                     "area_treated_ha": float(g.loc[g["actual_rmt"].fillna(0) > 0, "area_ha"].sum()),
                     "beneficiary_hh_count": int((g["actual_rmt"].fillna(0) > 0).sum())})
        recs.append({**base, "intervention_type": "waste_weir", "works_count": float(g["actual_waste_weirs"].sum()), "works_unit": "number",
                     "works_count_measured_only": float(g["actual_waste_weirs"].sum()), "proposed": float(g["proposed_waste_weirs"].sum()),
                     "area_treated_ha": float(g.loc[g["actual_waste_weirs"].fillna(0) > 0, "area_ha"].sum()),
                     "beneficiary_hh_count": int((g["actual_waste_weirs"].fillna(0) > 0).sum())})
        recs.append({**base, "intervention_type": "farm_pond", "works_count": float(g["actual_farm_pond"].sum()), "works_unit": "number",
                     "works_count_measured_only": float(g["actual_farm_pond"].sum()), "proposed": float(g["proposed_farm_pond"].sum()),
                     "area_treated_ha": float(g.loc[g["actual_farm_pond"] > 0, "area_ha"].sum()), "beneficiary_hh_count": int((g["actual_farm_pond"] > 0).sum())})
        recs.append({**base, "intervention_type": "plantation_horticulture", "works_count": float(g["actual_horti_plants"].sum()), "works_unit": "plants",
                     "works_count_measured_only": float(g["actual_horti_plants"].sum()), "proposed": float(g["proposed_horti_plants"].sum()),
                     "area_treated_ha": float(g.loc[g["actual_horti_plants"] > 0, "area_ha"].sum()), "beneficiary_hh_count": int((g["actual_horti_plants"] > 0).sum())})
        recs.append({**base, "intervention_type": "plantation_forestry", "works_count": float(g["actual_forestry_plants"].sum()), "works_unit": "plants",
                     "works_count_measured_only": float(g["actual_forestry_plants"].sum()), "proposed": float(g["proposed_forestry_plants"].sum()),
                     "area_treated_ha": float(g.loc[g["actual_forestry_plants"] > 0, "area_ha"].sum()), "beneficiary_hh_count": int((g["actual_forestry_plants"] > 0).sum())})
    return pd.DataFrame(recs)

def household_characteristics(t, by):
    g = t.groupby(by)
    h = pd.DataFrame({
        "n_parcels": g.size(),
        "share_owner_female": g["owner_female"].mean(),
        "share_small_farmer": g["farmer_category"].apply(lambda s: (s == "small").mean()),
        "share_large_farmer": g["farmer_category"].apply(lambda s: (s == "large").mean()),
        "mean_parcel_ha": g["area_ha"].mean(), "median_parcel_ha": g["area_ha"].median(),
        "share_sc_st": g["social_group"].apply(lambda s: s.isin(["SC", "ST"]).mean()),
        "share_fruits_id": g["has_fruits_id"].mean(),
    }).reset_index()
    h.insert(0, "district", DISTRICT); h.insert(1, "sws_code", SWS_CODE)
    return h

def common_land(path):
    cm = pd.read_excel(path, sheet_name="Comn Land")
    cm.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in cm.columns]
    out = pd.DataFrame({
        "district": DISTRICT, "sws_code": SWS_CODE, "mws_name": cm["MWS Name"].fillna("").astype(str).str.strip(),
        "village": cm["Village"].fillna("").astype(str).str.strip(),
        "kgis_village_code": cm["KGIS Village Code"].apply(lambda v: f"{int(v):010d}" if pd.notna(v) else ""),
        "proposed_survey_no": cm["Proposed Survey No"].fillna("").astype(str).str.strip(),
        "activity_type": cm["Activity Type"].fillna("").astype(str).str.strip(), "proposed_sub_activity": cm["Proposed Sub Activity"].fillna("").astype(str).str.strip(),
        "proposed_gps_raw": cm["Proposed Location GPS"], "proposed_dimension_section": _num(cm["Proposed Dimension_Section Ha"]),
        "proposed_total_cost_lakh": _num(cm["Proposed Total Cost"]), "actual_total_cost_lakh": _num(cm["Actual Total Cost"]),
        "actual_recorded": cm["Actual Sub Activity"].notna().astype(int),
    })
    return out
