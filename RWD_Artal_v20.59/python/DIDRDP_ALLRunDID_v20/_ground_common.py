import re
"""
_ground_common.py -- ground <-> satellite linkage for the REWARD DiD pipeline
============================================================================
Drop this file next to _common.py. It contains no estimator maths; it only links, aggregates
and scores. Three jobs:

1. snap_to_panel_pixels(points, panel_xy)  -- a GPS point never coincides with a 10 m pixel
   centroid, so the pipeline's exact merge on pixel_id (M07) cannot be used directly. This
   finds the NEAREST panel pixel (KD-tree on local metres) and reports the distance; anything
   beyond `max_dist_m` (default 12 m, i.e. more than one pixel away) is left unlinked.
2. validate_variable(...)  -- agreement statistics between a ground variable and the matching
   satellite variable at the same (pixel, Year, Season): n, Pearson r, Spearman rho, RMSE, bias,
   slope/intercept of satellite-on-ground, by institution and by SWS role (saturation/control).
3. ground_treated_control_table(...) -- site x (Year, Season) means of each ground variable with
   the saturation/control label, for a ground-only post-period comparison and as the
   'measured outcome' side of a surrogate-index check.

All coordinates are WGS84 lat/lon. Distances use a local equirectangular projection (exact to
<0.1% at field scale).
"""
import math
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy import stats

def _to_xy_m(lat, lon, lat0=None):
    lat = np.asarray(lat, float); lon = np.asarray(lon, float)
    lat0 = np.nanmean(lat) if lat0 is None else lat0
    kx = 111_320.0 * math.cos(math.radians(lat0)); ky = 110_574.0
    return np.column_stack([lon * kx, lat * ky]), lat0

def snap_to_panel_pixels(points, panel_xy, max_dist_m=12.0):
    """points: DataFrame with 'latitude','longitude' (any extra columns kept).
    panel_xy: DataFrame with 'pixel_id','latitude','longitude' -- ONE row per pixel (e.g. the
    coordinates of one Year/Season shard of the prepared panel, restricted to the sub-watershed).
    Returns points + ['pixel_id_nearest','snap_dist_m','snap_ok']."""
    out = points.copy()
    ok = out["latitude"].notna() & out["longitude"].notna()
    # keep the panel's own pixel_id dtype (int64 in the v16 schema, 18-digit string in older panels)
    out["pixel_id_nearest"] = pd.Series([None] * len(out), index=out.index, dtype=object)
    out["snap_dist_m"] = np.nan; out["snap_ok"] = False
    if ok.sum() == 0 or len(panel_xy) == 0:
        return out
    pxy, lat0 = _to_xy_m(panel_xy["latitude"].values, panel_xy["longitude"].values)
    tree = cKDTree(pxy)
    qxy, _ = _to_xy_m(out.loc[ok, "latitude"].values, out.loc[ok, "longitude"].values, lat0)
    d, j = tree.query(qxy, k=1)
    out.loc[ok, "pixel_id_nearest"] = list(panel_xy["pixel_id"].values[j])
    out.loc[ok, "snap_dist_m"] = d
    out.loc[ok, "snap_ok"] = d <= max_dist_m
    return out

_POLY_TREE = {}
def _panel_tree(panel_xy):
    """KD-tree over the panel pixels (built once per panel_xy object and cached)."""
    key = id(panel_xy)
    if key not in _POLY_TREE:
        xy, lat0 = _to_xy_m(panel_xy["latitude"].values, panel_xy["longitude"].values)
        _POLY_TREE.clear(); _POLY_TREE[key] = (cKDTree(xy), lat0)
    return _POLY_TREE[key]

def pixels_within_polygon_bbox(panel_xy, polygon_wkt):
    """Panel pixels whose centroid lies inside a POLYGON WKT. Candidates come from a KD-tree ball
    query around the polygon's bounding-box centre (radius = half-diagonal + one pixel), then an exact
    point-in-polygon test (ray casting). O(log n) per polygon instead of a scan of the whole panel."""
    coords = polygon_wkt.strip()[len("POLYGON(("):-2].split(",")
    ring = [(float(a), float(b)) for a, b in (c.strip().split() for c in coords)]
    xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
    tree, lat0 = _panel_tree(panel_xy)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    kx = 111_320.0 * math.cos(math.radians(lat0)); ky = 110_574.0
    half_diag = math.hypot((max(xs) - min(xs)) * kx, (max(ys) - min(ys)) * ky) / 2
    idx = tree.query_ball_point([cx * kx, cy * ky], r=half_diag + 15.0)
    if not idx:
        return panel_xy.iloc[0:0]
    sub = panel_xy.iloc[idx]
    inside = []
    for x, y in zip(sub.longitude.values, sub.latitude.values):
        c = False
        for (x1, y1), (x2, y2) in zip(ring[:-1], ring[1:]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-15) + x1:
                c = not c
        inside.append(c)
    return sub[np.array(inside, dtype=bool)]

def site_master(ssm, lai, gw, tdr, min_visits_for_median=2):
    """One row per benchmark site (institution, sws, mws, bm_site_no / borewell / probe) with the
    MEDIAN coordinate across visits (the workbooks contain copy-paste coordinate errors on some
    visit blocks), the share of visits within 300 m of that median, and the SWS role label."""
    from ground_utils import sws_role
    frames = []
    for name, df, key in (("ssm", ssm, "bm_site_no"), ("lai", lai, "bm_site_no"), ("gw", gw, "borewell_no"), ("tdr", tdr, "probe_or_survey_no")):
        if df is None or not len(df):
            continue
        d = df.dropna(subset=["latitude", "longitude"]).copy()
        d["site_key"] = d["institution"] + "|" + d["sws_name"].fillna("") + "|" + d["mws_name"].fillna("") + "|" + name + "|" + d[key].fillna("").astype(str)
        g = d.groupby("site_key")
        m = pd.DataFrame({"institution": g["institution"].first(), "sws_name": g["sws_name"].first(), "mws_name": g["mws_name"].first(),
                          "variable": name, "site_no": g[key].first(), "lat_median": g["latitude"].median(), "lon_median": g["longitude"].median(),
                          "n_obs_with_coords": g.size(), "n_dates": g["date"].nunique()})
        xy, _ = _to_xy_m(d["latitude"].values, d["longitude"].values)
        d["_x"], d["_y"] = xy[:, 0], xy[:, 1]
        med = d.groupby("site_key")[["_x", "_y"]].transform("median")
        d["_dist"] = np.hypot(d["_x"] - med["_x"], d["_y"] - med["_y"])
        m["share_visits_within_300m"] = d.groupby("site_key")["_dist"].apply(lambda s: (s <= 300).mean())
        m["max_visit_dist_from_median_m"] = d.groupby("site_key")["_dist"].max()
        frames.append(m.reset_index())
    ms = pd.concat(frames, ignore_index=True)
    ms["sws_role"] = ms["sws_name"].map(sws_role)
    return ms

def attach_site_median_coords(df, ms, variable, key):
    """Add lat_site/lon_site (site median) and coord_outlier flag (>300 m from site median) to a long table."""
    d = df.copy()
    d["site_key"] = d["institution"] + "|" + d["sws_name"].fillna("") + "|" + d["mws_name"].fillna("") + "|" + variable + "|" + d[key].fillna("").astype(str)
    m = ms[ms.variable == variable].set_index("site_key")[["lat_median", "lon_median", "sws_role"]]
    d = d.join(m, on="site_key")
    d = d.rename(columns={"lat_median": "lat_site", "lon_median": "lon_site"})
    has = d["latitude"].notna() & d["lat_site"].notna()
    dist = np.full(len(d), np.nan)
    if has.any():
        kx = 111_320.0 * math.cos(math.radians(np.nanmean(d.loc[has, "lat_site"]))); ky = 110_574.0
        dist[has.values] = np.hypot((d.loc[has, "longitude"] - d.loc[has, "lon_site"]) * kx, (d.loc[has, "latitude"] - d.loc[has, "lat_site"]) * ky)
    d["dist_to_site_median_m"] = dist
    d["coord_outlier_gt_300m"] = d["dist_to_site_median_m"] > 300
    return d

def validate_variable(pairs, ground_col, sat_col, by=("institution",)):
    """pairs: rows already joined on (pixel/site, Year, Season) with both columns present."""
    rows = []
    groups = [((), pairs)] + [(k if isinstance(k, tuple) else (k,), g) for k, g in pairs.groupby(list(by))] if by else [((), pairs)]
    for k, g in groups:
        g = g.dropna(subset=[ground_col, sat_col])
        n = len(g)
        rec = {"group": "|".join(map(str, k)) if k else "ALL", "n": n}
        if n >= 3:
            x = g[ground_col].values.astype(float); y = g[sat_col].values.astype(float)
            rec["pearson_r"] = float(np.corrcoef(x, y)[0, 1]); rec["spearman_rho"] = float(stats.spearmanr(x, y)[0])
            rec["rmse"] = float(np.sqrt(np.mean((y - x) ** 2))); rec["bias_sat_minus_ground"] = float(np.mean(y - x))
            sl, ic = np.polyfit(x, y, 1); rec["slope_sat_on_ground"] = float(sl); rec["intercept"] = float(ic)
            rec["ground_mean"] = float(x.mean()); rec["sat_mean"] = float(y.mean())
        rows.append(rec)
    return pd.DataFrame(rows)

def ground_treated_control_table(ssm, lai, gw, tdr_rootzone):
    """Site x (Year, Season) means with the saturation/control role. Only sites whose SWS carries a
    role label in the workbooks are labelled; everything else is 'unlabelled'."""
    from ground_utils import panel_year_season
    out = []
    for name, df, col, key in (("ssm_pct", ssm, "ssm_mean", "bm_site_no"), ("lai", lai, "lai_mean", "bm_site_no"),
                               ("gw_depth_m", gw, "gw_depth_m", "borewell_no"), ("tdr_rootzone_pct", tdr_rootzone, "moisture_pct", "probe_or_survey_no")):
        if df is None or not len(df):
            continue
        d = df.dropna(subset=["date", col]).copy()
        ys = [panel_year_season(x) for x in d["date"]]
        d["Year"] = [a for a, _ in ys]; d["Season"] = [b for _, b in ys]
        g = d.groupby(["institution", "sws_name", "sws_role", "mws_name", key, "Year", "Season"])
        a = g[col].agg(["mean", "median", "count"]).reset_index().rename(columns={key: "site_no", "mean": "value_mean", "median": "value_median", "count": "n_obs"})
        a.insert(0, "variable", name)
        out.append(a)
    return pd.concat(out, ignore_index=True)


# ====================== v20.41: BENCHMARK SITES -> SUB-WATERSHED MEANS -> SURROGATE OUTCOMES ======================
# Your rule: the BM sites of a sub-watershed (three points) are averaged, and that average represents the
# sub-watershed. The ground data cover 2023-2024 only -- after implementation -- so no DiD can run on ground values
# alone (no baseline). They enter the DiD as SURROGATE OUTCOMES: over the programme sub-watersheds, learn how the
# satellite indices of a sub-watershed's treatment area map to its ground mean (per variable, season by season),
# then compute that ground-scale value for EVERY pixel in EVERY year -- a new outcome (GND_<variable>) that every
# model runs on like NDVI.
SWS_NAME_ALIASES = {
    "artal": "Artal", "begur": "Beguru", "beguru": "Beguru", "chatrakodihalli": "Chhatrakodihalli",
    "chhatrakodihalli": "Chhatrakodihalli", "chittaragi": "Chittharagi", "chittharagi": "Chittharagi",
    "doddenahalli": "Doddenahalli", "gummalapalli": "Gummlapalli", "gummlapalli": "Gummlapalli",
    "halligera": "Haligeri", "haligeri": "Haligeri", "honnutagi": "Honnutagi", "hunsehadagli": "Hunasehadagi",
    "hunasehadagi": "Hunasehadagi", "jammapura": "Jammapur", "jammapur": "Jammapur", "jantapur": "Jantapur",
    "kodihalli": "Kodihalli", "koranahalli": "Koranahalli", "kytagondanahalli": "Kyatagondanahalli",
    "kyatagondanahalli": "Kyatagondanahalli", "maidalakere": "Maidalakere", "mydalakere": "Maidalakere",
    "mallainupura": "Mallainupura", "murlapura": "Murlapura", "nilagunda": "Nilgund", "nilgunda": "Nilgund",
    "nilgund": "Nilgund", "pashapur": "Pashapur", "shirur": "Sirur", "sirur": "Sirur",
}
GROUND_CONTROL_SWS = ("gadag", "hanchinal", "hosahalli", "kohalli", "itgi",          # v20.47: every non-programme sub-watershed
                      "haralahalli", "holali", "kandgul", "laxmisagara", "mattikote",   # in your BM files -- a name-only match must
                      "nagagondanahalli", "narayanghatta", "virupasandra")              # never turn one into a programme name
GROUND_PREDICTOR_CANDIDATES = ["NDVI", "EVI", "SAVI", "LAI", "NDRE", "SMDI", "VCI", "TCI", "VHI", "NDMI", "LSWI", "NDWI"]

def _norm_sws(name):
    s = re.sub(r"\(.*?\)", " ", str(name).lower())
    s = re.sub(r"sub[\s\-_]*watershed|\bsws\b|control", " ", s)
    return re.sub(r"[^a-z]", "", s)

def match_sws(name, registry_names=None):
    """(shapefile name or None, how): v20.47 -- the shared rule (_names.py): a known spelling, else >= 80 % similar and
    unambiguous. A control sub-watershed never matches a programme name it is not >= 80 % similar to."""
    import _names as _N
    reg = registry_names or sorted(set(SWS_NAME_ALIASES.values()))
    n = _norm_sws(name)
    if any(n.startswith(c) for c in GROUND_CONTROL_SWS): return None, "control sub-watershed (outside the programme)"
    canon, sc, how = _N.best_match(name, _N.programme_candidates(reg))
    return canon, ("alias" if sc >= 1.0 else how) if canon else how

def ground_sws_season_means(path=None, name_to_id=None):
    """v20.46: one row per sub-watershed x variable x Year x Season = THE MEAN OF ITS BM SITES (your rule), computed by
    _bm_means: declared variables with physical bounds, every site counted once (site mean over visits and
    replicates, then the mean over sites), names unified, blank / combined / code names resolved by where the sites
    lie, and sites whose location contradicts their name kept out and listed. `path` = the ground-inputs folder
    (a file path inside it also works). Returns (means, name_table); means.attrs carries the site audit."""
    import os
    import _bm_means as _B
    gdir = path if (path and os.path.isdir(path)) else (os.path.dirname(path) if path else _ground_dir())
    means, sites, bounds = _B.bm_sws_means(gdir, name_to_id=name_to_id)
    means.attrs["sites"] = sites; means.attrs["bounds"] = bounds
    return means, means.attrs.get("name_table")

def _ground_dir():
    import os
    try:
        import _common as _C
        return getattr(_C, "GROUND_INPUTS_DIR", None) or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "REWARD_ground_inputs")
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "REWARD_ground_inputs")

def fit_ground_surrogates(C, variables=None, predictors=None, min_rows=6, write=True, verbose=True, register=True):
    """Fit, per ground variable, ground mean of a sub-watershed ~ satellite means of its treatment area (same Year and
    Season), by ridge regression with leave-one-out validation. Registers each usable fit as GND_<variable> (a new
    outcome every model can run on) and writes ground_sws_season_means.csv, ground_surrogate_fit.csv,
    ground_satellite_validation.csv and ground_name_matching.csv next to the panel."""
    import os, numpy as np, pandas as pd, pyarrow.parquet as pq
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import LeaveOneOut, cross_val_predict
    from sklearn.preprocessing import StandardScaler
    import _sites as _S
    reg = _S.registry(); name_to_id = {str(n): int(i) for n, i in zip(reg["name"], reg["SWSiD_All"])}
    gm, matching = ground_sws_season_means(name_to_id=name_to_id)
    out_dir = os.path.dirname(C.PREPARED_PANEL)
    pf = pq.ParquetFile(C.PREPARED_PANEL); names = pf.schema_arrow.names
    cand = [p for p in (predictors or GROUND_PREDICTOR_CANDIDATES) if p in names]
    acc = {}
    # v20.58 -- YOUR LOCATION RULE here too: a sub-watershed's treatment-area mean is taken over ITS OWN core pixels only -- never a pixel
    # outside every polygon (an export's id alone), a repeated pixel-year-season, a pixel whose ring the exports disagree on, or the smaller
    # of two overlapping pixels (v20.57 averaged them in: the ground fit, and every GND_ outcome, moved with them)
    # v20.58 (found by the poison test): the fit is trained on the PROCESSED sub-watershed(s) only -- as R's m07_surrogate. It took every
    # sub-watershed with own rows (a 2.5 % fragment of a neighbour included), so rows your rule leaves out moved the mapping, and with it
    # whether GND_ outcomes exist at all. A single-sub-watershed run now reports the gap (< 6 means) exactly as R does; the pooled run fits it.
    try:
        _lt = C.location_table(); _S_run = C.processing_sites(_lt)[0] if _lt.get("mode") != "none" else []
    except Exception as _e:
        raise RuntimeError(f"the ground surrogate needs the location rule (processing set) and could not get it: {type(_e).__name__}: {_e}")
    _lc = [c for c in ("site_check", "pixel_id") if c in names]
    for i in range(pf.num_row_groups):                  # treatment-area means per sub-watershed x Year x Season, streamed
        d = pf.read_row_group(i, columns=["site_id", "Year", "Season", "buff_km"] + _lc + cand).to_pandas()
        if _lt.get("mode") != "none" and len(d):
            d = d[C.location_mask(d, _lt, S=_S_run, pooled=True)[0]]
        d = d[(pd.to_numeric(d["buff_km"], errors="coerce") == C.TREAT_CORE_BUFFKM) & (pd.to_numeric(d["site_id"], errors="coerce") > 0)]
        if not len(d): continue
        s = d.groupby(["site_id", "Year", "Season"])[cand].agg(["sum", "count"])
        for k, row in s.iterrows():
            a = acc.setdefault(k, {p: [0.0, 0] for p in cand})
            for p in cand: a[p][0] += float(row[(p, "sum")]); a[p][1] += int(row[(p, "count")])
    sat = pd.DataFrame([{"site_id": int(k[0]), "Year": int(k[1]), "Season": int(k[2]),
                         **{p: (v[p][0] / v[p][1] if v[p][1] else np.nan) for p in cand}} for k, v in acc.items()],
                       columns=["site_id", "Year", "Season"] + cand)      # v20.58: the columns even when no core row is left (was a KeyError)
    fits, valid = [], []
    if len(sat):
        # predictors must exist in EVERY year of the panel, or the new outcome would be missing there
        yrs = sorted(sat["Year"].unique())
        full = [p for p in cand if sat.groupby("Year")[p].apply(lambda s: s.notna().mean()).reindex(yrs).fillna(0).min() >= 0.9]
    else:
        full = []
    prog = gm[gm["group"] == "programme"]
    for var in (variables or sorted(prog["variable"].unique())):
        tr = prog[prog["variable"] == var].merge(sat, on=["site_id", "Year", "Season"], how="inner").dropna(subset=["value"] + full)
        row = {"ground_variable": var, "outcome_name": f"GND_{var}", "n_rows": len(tr),
               "n_sub_watersheds": tr["site_id"].nunique() if len(tr) else 0, "predictors": ";".join(full)}
        for p in full:
            if len(tr) >= 3 and tr[p].std() > 0:
                valid.append({"ground_variable": var, "satellite": p, "r": float(np.corrcoef(tr["value"], tr[p])[0, 1]), "n": len(tr)})
        if len(tr) < min_rows or not full:
            row["status"] = (f"not fitted: {len(tr)} sub-watershed x season means (need >= {min_rows}) -- the pooled run over the "
                             f"sub-watersheds provides them" if full else
                             ("not fitted: no core row of the processed sub-watershed(s) is left by the location rule (inside its own polygon)"
                              if not len(sat) else "not fitted: no satellite index covers every year"))
            fits.append(row); continue
        X = tr[full].values.astype(float); y = tr["value"].values.astype(float)
        best = None
        for a in (0.1, 1.0, 10.0, 100.0):
            sc = StandardScaler().fit(X); pr = cross_val_predict(Ridge(alpha=a), sc.transform(X), y, cv=LeaveOneOut())
            mse = float(np.mean((pr - y) ** 2))
            if best is None or mse < best[0]: best = (mse, a, pr)
        mse, alpha, pr = best
        sc = StandardScaler().fit(X); mdl = Ridge(alpha=alpha).fit(sc.transform(X), y)
        coef = mdl.coef_ / sc.scale_; icpt = float(mdl.intercept_ - np.sum(mdl.coef_ * sc.mean_ / sc.scale_))
        r2cv = float(1 - mse / np.var(y)) if np.var(y) > 0 else np.nan
        row.update({"status": "fitted" if r2cv > 0 else "fitted, but predicts no better than the mean (r2_cv <= 0) -- not registered",
                    "alpha": alpha, "r2_in_sample": float(mdl.score(sc.transform(X), y)), "r2_cv_leave_one_out": r2cv,
                    "intercept": icpt, **{f"coef_{p}": float(b) for p, b in zip(full, coef)}})
        fits.append(row)
        if r2cv > 0 and register:
            C.register_derived_variable(f"GND_{var}", {"predictors": full, "coef": [float(b) for b in coef], "intercept": icpt,
                                                       "ground_variable": var, "r2_cv": r2cv, "n_rows": len(tr),
                                                       "n_sub_watersheds": int(tr["site_id"].nunique())})
    fit_df, val_df = pd.DataFrame(fits), pd.DataFrame(valid)
    if write:
        gm.to_csv(os.path.join(out_dir, "ground_sws_season_means.csv"), index=False)
        import _bm_means as _B                                   # v20.46: every site's decision + the per-sub-watershed summary
        _B.write_bm_reports(gm, gm.attrs.get("sites"), gm.attrs.get("bounds"), out_dir)
        fit_df.to_csv(os.path.join(out_dir, "ground_surrogate_fit.csv"), index=False)
        val_df.to_csv(os.path.join(out_dir, "ground_satellite_validation.csv"), index=False)
    if verbose:
        _s = gm.attrs.get("sites")
        _nc = int((_s.decision == "counted").sum()) if _s is not None and len(_s) else 0
        _nx = int((_s.decision == "excluded").sum()) if _s is not None and len(_s) else 0
        _none = (sorted(matching.loc[matching["counted"] == 0, "sws_name"].replace("", "(blank)").astype(str))
                 if matching is not None and len(matching) and "counted" in matching.columns else [])
        C.info(f"ground: BM sub-watershed means (the mean of each sub-watershed's sites) for {prog['site_id'].nunique()} programme and "
               f"{gm.loc[gm.group == 'control', 'sws'].nunique()} control sub-watersheds ({len(prog):,} programme rows); "
               f"{_nc} site x variable entries counted, {_nx} kept out (location contradicts the name, or no name) -> BM_SWS_SUMMARY.md"
               + (f"; names with no site counted: {_none}" if _none else ""))
        for r in fits:
            (C.ok if str(r.get("status", "")).startswith("fitted") and r.get("r2_cv_leave_one_out", 0) > 0 else C.warn)(
                f"GND_{r['ground_variable']}: {r['status']}" + (f" | leave-one-out R2 {r['r2_cv_leave_one_out']:.2f}, "
                f"{r['n_rows']} means from {r['n_sub_watersheds']} sub-watershed(s)" if "r2_cv_leave_one_out" in r else ""))
    return fit_df, val_df
