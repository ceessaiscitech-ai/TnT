"""
field_survey.py -- restructure '99. All Field Survey Data - [03.12.2025 to 02.05.2026].xlsx'
=============================================================================================
Input : one plot per row (3,642 plots / 3,397 farmer profiles, 7 districts), with GPS point,
        field-boundary polygon (JSON list of {lng,lat}), crop, sowing date, variety, field size.
Output: de-identified plot table (no names, no phone numbers, no addresses) keyed by a stable
        plot_uid, with QC flags, harmonised crop, pipeline (Year, Season) key from the SOWING
        date, polygon as WKT, polygon centroid + area, and the pipeline pixel_id of the centroid.
Nothing is imputed: a plot with an unusable polygon keeps its GPS point; a plot with no sowing
date keeps season_code = NaN.
"""
import json, math, re, hashlib
import numpy as np
import pandas as pd
from ground_utils import harmonize_crop, pixel_id_from_latlon, panel_year_season, parse_coord

def _poly_from_json(s):
    try:
        pts = json.loads(s)
        ring = [(float(p["lng"]), float(p["lat"])) for p in pts]
    except Exception:
        return None
    ring = [p for p in ring if not (math.isnan(p[0]) or math.isnan(p[1]))]
    if len(ring) < 3:
        return None
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring

def _ring_area_ha_and_centroid(ring):
    """Planar area of a lon/lat ring using a local equirectangular projection (accurate for field-
    sized polygons). Returns (area_ha, centroid_lon, centroid_lat)."""
    lat0 = sum(p[1] for p in ring) / len(ring)
    kx = 111_320.0 * math.cos(math.radians(lat0)); ky = 110_574.0
    xy = [((p[0] - ring[0][0]) * kx, (p[1] - ring[0][1]) * ky) for p in ring]
    a = 0.0; cx = 0.0; cy = 0.0
    for (x1, y1), (x2, y2) in zip(xy[:-1], xy[1:]):
        cross = x1 * y2 - x2 * y1
        a += cross; cx += (x1 + x2) * cross; cy += (y1 + y2) * cross
    a *= 0.5
    if abs(a) < 1e-9:
        return 0.0, np.nan, np.nan
    cx /= (6 * a); cy /= (6 * a)
    return abs(a) / 10_000.0, ring[0][0] + cx / kx, ring[0][1] + cy / ky

def _area_to_ha(s):
    """'2 Acre' -> 0.809 ha; '20 Guntha' -> 0.202 ha (1 guntha = 1/40 acre). Blank number -> NaN."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return np.nan
    m = re.match(r"^\s*([\d.]+)?\s*(acre|guntha|gunta|ha|hectare)?", str(s), re.I)
    if not m or not m.group(1):
        return np.nan
    v = float(m.group(1)); u = (m.group(2) or "").lower()
    if u.startswith("acre"): return v * 0.404686
    if u.startswith("gun"): return v * 0.404686 / 40.0
    return v

def build_field_survey(path):
    fs = pd.read_excel(path).dropna(axis=1, how="all")
    fs.columns = [c.strip() for c in fs.columns]
    out = pd.DataFrame()
    # stable, non-identifying plot key: hash of (Profile ID, Plot_Crop_#, Captured Date)
    out["plot_uid"] = [hashlib.sha1(f"{a}|{b}|{c}".encode()).hexdigest()[:12]
                       for a, b, c in zip(fs["Profile ID"], fs["Plot_Crop_#"], fs["Captured Date"])]
    out["farmer_uid"] = [hashlib.sha1(f"profile|{a}".encode()).hexdigest()[:10] for a in fs["Profile ID"]]
    out["plot_index_within_farmer"] = fs["ID In Plots"].values
    for c in ("State", "District", "Taluka", "Gram Panchayat", "Village"):
        out[c.lower().replace(" ", "_")] = fs[c].fillna("").astype(str).str.strip().values
    out.loc[out["taluka"].str.lower().str.startswith("select"), "taluka"] = ""
    # survey number: keep the numeric survey/hissa part only (the Kannada suffix is an owner name -> dropped)
    out["survey_hissa"] = fs["Survey Number"].fillna("").astype(str).str.extract(r"^([\d/*A-Za-z\-]+)")[0].str.strip().values
    out["plot_name_raw"] = fs["Plot Name"].fillna("").astype(str).str.strip().str.lower().replace("nan", "").values
    out["crop_raw"] = fs["Crop Name"].fillna("").astype(str).str.strip().replace("nan", "").values
    out["crop"] = [harmonize_crop(c) for c in out["crop_raw"]]
    out["variety_duration"] = fs["Variety"].fillna("").astype(str).str.strip().replace({"Select Variety": "", "ಜಾತಿ ಆಯ್ಕೆಮಾಡಿ": "", "nan": ""}).values
    out["sowing_date"] = pd.to_datetime(fs["Sowing Date"], errors="coerce").dt.normalize().values
    out["next_season_crop_raw"] = fs["Next Season Crop"].fillna("").astype(str).str.strip().replace("nan", "").values
    out["next_season_crop"] = [harmonize_crop(c) for c in out["next_season_crop_raw"]]
    out["next_season_cropped"] = np.where(out["next_season_crop_raw"] == "", np.nan,
                                          np.where(out["next_season_crop"].isin(["no_crop", "unknown"]), 0, 1)).astype(float)
    out["cultivated_area_ha_stated"] = [_area_to_ha(v) for v in fs["Cultivated Area"]]
    # the app's 'Field Size' equals the polygon area in ACRES (corr 1.00, ratio 2.47) -> convert to ha
    out["field_size_acres_app"] = pd.to_numeric(fs["Field Size"], errors="coerce").values
    out["field_size_ha_app"] = out["field_size_acres_app"] * 0.404686
    out["gps_lat"] = [parse_coord(v, "lat") for v in fs["Field Worker Geo Latitude"]]
    out["gps_lon"] = [parse_coord(v, "lon") for v in fs["Field Worker Geo Longitude"]]
    out["captured_date"] = pd.to_datetime(fs["Captured Date"], errors="coerce").dt.normalize().values
    out["farmer_type"] = fs["Farmer Type"].fillna("").astype(str).values
    # polygons
    polys = [_poly_from_json(s) if isinstance(s, str) else None for s in fs["Field Boundaries"]]
    out["polygon_wkt"] = ["POLYGON((" + ", ".join(f"{x:.7f} {y:.7f}" for x, y in r) + "))" if r else "" for r in polys]
    out["polygon_n_vertices"] = [len(r) - 1 if r else 0 for r in polys]
    geo = [_ring_area_ha_and_centroid(r) if r else (np.nan, np.nan, np.nan) for r in polys]
    out["polygon_area_ha"] = [g[0] for g in geo]
    out["centroid_lon"] = [g[1] for g in geo]; out["centroid_lat"] = [g[2] for g in geo]
    # QC flags
    flags = []
    for i, r in out.iterrows():
        f = []
        if np.isnan(r.gps_lat) or np.isnan(r.gps_lon): f.append("gps_outside_karnataka_or_missing")
        if not r.polygon_wkt: f.append("no_polygon")
        elif r.polygon_area_ha < 0.005: f.append("polygon_degenerate_lt_50m2")
        elif r.polygon_area_ha > 50: f.append("polygon_gt_50ha")
        if r.polygon_wkt and not np.isnan(r.gps_lat) and not np.isnan(r.centroid_lat):
            dkm = math.hypot((r.centroid_lon - r.gps_lon) * 111.32 * math.cos(math.radians(r.gps_lat)),
                             (r.centroid_lat - r.gps_lat) * 110.57)
            if dkm > 1.0: f.append("centroid_gt_1km_from_gps")
        if pd.isna(r.sowing_date): f.append("no_sowing_date")
        if r.crop in ("unknown",) or r.crop.startswith("other:"): f.append("crop_unmapped")
        if not np.isnan(r.field_size_ha_app) and not np.isnan(r.polygon_area_ha) and r.polygon_area_ha > 0 \
                and abs(r.field_size_ha_app - r.polygon_area_ha) / max(r.polygon_area_ha, 1e-6) > 0.5:
            f.append("app_size_vs_polygon_gt_50pct")
        flags.append(";".join(f))
    out["qc_flags"] = flags
    # location used for pixel linkage: polygon centroid if the polygon is usable, else GPS point
    use_poly = out["polygon_wkt"].ne("") & ~out["qc_flags"].str.contains("degenerate|gt_50ha|gt_1km")
    out["link_lat"] = np.where(use_poly, out["centroid_lat"], out["gps_lat"])
    out["link_lon"] = np.where(use_poly, out["centroid_lon"], out["gps_lon"])
    out["link_source"] = np.where(use_poly, "polygon_centroid", "gps_point")
    out["pixel_id_of_link_point"] = pixel_id_from_latlon(out["link_lat"].values, out["link_lon"].values)
    # pipeline time keys from the SOWING date (the season the crop occupies the field)
    ys = [panel_year_season(d) if pd.notna(d) else (np.nan, np.nan) for d in out["sowing_date"]]
    out["Year"] = [y for y, _ in ys]; out["Season"] = [s for _, s in ys]
    out["Season"] = out["Season"].astype("float")
    return out

def crop_calendar(plots):
    """District x Season x crop: sowing-date distribution. Use it to check the pipeline's fixed
    season windows (Kharif Jun-Oct, Rabi Nov-Mar, Zaid Apr-May) against real sowing."""
    p = plots.dropna(subset=["sowing_date"]).copy()
    p["doy"] = p.sowing_date.dt.dayofyear
    g = p.groupby(["district", "Year", "Season", "crop"]).agg(
        n_plots=("plot_uid", "size"), sow_median=("sowing_date", "median"), sow_p10=("sowing_date", lambda s: s.quantile(0.1)),
        sow_p90=("sowing_date", lambda s: s.quantile(0.9)), area_ha_polygon=("polygon_area_ha", "sum")).reset_index()
    return g[g.n_plots >= 3].sort_values(["district", "Year", "Season", "n_plots"], ascending=[True, True, True, False])
