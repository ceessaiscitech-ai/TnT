"""
validate_column_styles.py -- 4 Oct (your deep check): NO column is mis-joined or left out because of its WRITING STYLE, every DiD column is
there on every row, and the panel's rows follow the natural year / season / pixel sequence.

The same export rows are written FIVE times, each file in another header style -- lower case with spaces, UPPER CASE with units in brackets,
"_mean" suffixes, the aliases other exporters use (lat / lon / dist_km / rainfall / temp_max ...), a BOM and a mixed style with an extra
unknown column, a statistic column (NDVI_sd) and a second NDVI column -- as five year-seasons of one folder. The panel is built from them
(build_panel.PanelBuild, the engine as P00 runs it) and checked: every value of every variable equals the source value of that pixel-year-
season (joined on the rounded coordinates, never on a column name); the unresolved-columns report says what was read under another name,
what was kept apart and what was left out; confirm_panel_columns is CLEAN (treatment / control / pre / post / did_term / treat / did / the time
columns on every row, the rows in order); the dose join on district names in different spellings matches; the name key unifies spellings.
    python validate_column_styles.py          -> CLEAN or the failing checks (exit 1)
"""
import os, sys, glob, json, shutil, tempfile, traceback
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
FAILS, OKS = [], []
def ok(m): OKS.append(m); print("[OK]      " + m)
def bad(m): FAILS.append(m); print("[FAILED]  " + m)

def write_styled_exports(root):
    """Five files, one per year-season, the same 60 pixels (inside Haligeri's polygons: the coordinates of the DiD-spec audit's synthetic
    exports when they exist, else a grid), each in another header style. Returns (files, the source frame per file in canonical names)."""
    src = sorted(glob.glob("/tmp/reward_didspec_*/data/Haligeri/CSV_2016_Yearly_tile0.csv"))
    rng = np.random.default_rng(4)
    if src:
        base = pd.read_csv(src[0]).iloc[:60][["latitude", "longitude", "buff_km"]].reset_index(drop=True)
    else:
        base = pd.DataFrame({"latitude": 16.66 + rng.random(60) / 100, "longitude": 77.23 + rng.random(60) / 100, "buff_km": np.tile([0, 1, 2, 3, 4, 5], 10)})
    out_dir = os.path.join(root, "REWARD_Haligeri_Exports_final"); os.makedirs(out_dir, exist_ok=True)
    OUT = ["NDVI", "SAVI", "EVI", "LAI", "LSWI", "NDWI", "NDMI", "NDRE", "AGB", "RUSLE", "ESI", "WSSI", "WSI", "SMDI", "VCI", "TCI", "VHI"]
    def frame(y, s):
        d = base.copy(); d["Year"] = y; d["Season"] = s; d["Treat"] = int(y >= 2022); d["SubwshedID"] = "U1"; d["SWSiD_All"] = 7
        for v in OUT: d[v] = np.round(rng.uniform(0.1, 0.9, len(d)), 6)
        d["Rain"] = np.round(rng.uniform(300, 900, len(d)), 3); d["Tmax"] = np.round(rng.uniform(30, 36, len(d)), 3); d["Tmean"] = np.round(rng.uniform(24, 28, len(d)), 3); d["Tmin"] = np.round(rng.uniform(17, 21, len(d)), 3)
        d["LandUse"] = 2; d["GapFilled"] = 0; d["Coverage"] = 1.0
        return d
    styles = {
        (2016, 0): ("lower case with spaces",   lambda c: {"latitude": "latitude", "longitude": "longitude", "buff_km": "buff km", "Year": "year", "Season": "season", "Treat": "treat", "SubwshedID": "subwshed id", "SWSiD_All": "swsid all", "Rain": "rain", "Tmax": "t max", "Tmean": "t mean", "Tmin": "t min", "LandUse": "land use", "GapFilled": "gap filled", "Coverage": "coverage"}.get(c, c.lower())),
        (2018, 1): ("UPPER CASE with units",     lambda c: {"latitude": "LATITUDE (deg)", "longitude": "LONGITUDE (deg)", "buff_km": "BUFFER (km)", "Year": "YEAR", "Season": "SEASON", "Treat": "TREAT", "SubwshedID": "SUBWSHEDID", "SWSiD_All": "SWSID_ALL", "Rain": "RAIN (mm)", "Tmax": "TMAX (C)", "Tmean": "TMEAN (C)", "Tmin": "TMIN (C)", "LandUse": "LAND_USE", "GapFilled": "GAPFILLED", "Coverage": "COVERAGE (%)"}.get(c, c.upper())),
        (2020, 2): ("_mean suffixes",            lambda c: {"latitude": "Latitude", "longitude": "Longitude", "buff_km": "Buff_Km", "Year": "Year", "Season": "Season", "Treat": "Treat", "SubwshedID": "SubwshedID", "SWSiD_All": "SWSiD_All", "Rain": "Rain_mean", "Tmax": "Tmax_mean", "Tmean": "Tmean_mean", "Tmin": "Tmin_mean", "LandUse": "LandUse", "GapFilled": "GapFilled", "Coverage": "Coverage"}.get(c, c + "_mean")),
        (2023, 1): ("other exporters' aliases",  lambda c: {"latitude": "lat", "longitude": "lon", "buff_km": "dist_km", "Year": "yr", "Season": "season_code", "Treat": "treatment", "SubwshedID": "sub_watershed_id", "SWSiD_All": "site_id", "Rain": "rainfall", "Tmax": "temp_max", "Tmean": "temp_mean", "Tmin": "temp_min", "LandUse": "landcover", "GapFilled": "gap_filled", "Coverage": "coverage_pct", "SMDI": "soil_moisture_drought_idx"}.get(c, c)),
        (2025, 3): ("BOM, mixed, extra columns", lambda c: {"latitude": "﻿Latitude", "longitude": "longitude ", "buff_km": " buff_km", "Year": "Year ", "Season": "Season", "Treat": "Treat", "SubwshedID": "SubwshedID", "SWSiD_All": "SWSiD_All", "NDVI": "ndvi"}.get(c, c)),
    }
    files, sources = [], {}
    for (y, s), (label, ren) in styles.items():
        d = frame(y, s); sources[(y, s)] = d.copy()
        w = d.rename(columns={c: ren(c) for c in d.columns})
        if (y, s) == (2025, 3):
            w["notes"] = "x"; w["NDVI_sd"] = 0.01; w["NDVI2"] = d["NDVI"] + 0.5        # unknown, a statistic, a second column of NDVI
        f = os.path.join(out_dir, f"CSV_Haligeri_{y}_{ {0: 'Yearly', 1: 'Kharif', 2: 'Rabi', 3: 'Zaid'}[s] }_tile0.csv"); w.to_csv(f, index=False, encoding="utf-8"); files.append(f)
        print(f"[INFO]    {os.path.basename(f)}: {label}")
    return files, sources

def main():
    import _prep_common as P
    tmp = tempfile.mkdtemp(prefix="reward_styles_"); root = os.path.join(tmp, "exports"); out = os.path.join(tmp, "output"); os.makedirs(root)
    files, sources = write_styled_exports(root)
    # ---- 1 the harmoniser on each file's header: every canonical column recognised, the extras handled as said
    try:
        for f in files:
            log = []; m = P.dedupe_mapping(P.harmonize_columns(pd.read_csv(f, nrows=0).columns, fname=os.path.basename(f), unresolved_log=log), fname=os.path.basename(f), unresolved_log=log)
            got = set(m.values()); need = {"latitude", "longitude", "buff_km", "Year", "Season", "Treat", "NDVI", "LAI", "Rain", "Tmax", "Tmean", "Tmin", "LandUse", "Coverage", "GapFilled", "SWSiD_All", "SubwshedID", "SMDI", "VHI"}
            miss = need - got
            if miss: bad(f"{os.path.basename(f)}: not recognised {sorted(miss)} -- mapping {m}")
            else: ok(f"{os.path.basename(f)}: every column recognised whatever its style")
            if "2025" in f:
                if m.get("NDVI_sd") != "NDVI_sd" or m.get("notes") != "notes": bad(f"the statistic / unknown column was folded into a variable: {m.get('NDVI_sd')}, {m.get('notes')}")
                elif m.get("NDVI2") != "NDVI__dup_NDVI2" and m.get("ndvi") != "NDVI": bad(f"the second NDVI column: {m.get('NDVI2')} / {m.get('ndvi')}")
                else: ok("NDVI_sd kept apart (a statistic), 'notes' left as unknown, the second NDVI column kept as NDVI__dup_NDVI2")
    except Exception as e: bad(f"harmoniser check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)
    # ---- 2 the panel from the five styles
    try:
        import build_panel; B = build_panel.PanelBuild(root, output_dir=out, workers=1, force=True, readiness=False, verbose=True)
        B.audit(); B.pass_a(); B.dose(); B.pass_b(); B.integrity(); B.precision()
        pan = pd.read_parquet(B.final_path)
        ur = pd.read_csv(os.path.join(out, "unresolved_columns.csv"))
        kinds = dict(zip(ur.column, ur.kind))
        if not (kinds.get("notes", "").startswith("LEFT OUT") and kinds.get("NDVI_sd", "").startswith("A STATISTIC") and kinds.get("NDVI2", "").startswith("SECOND COLUMN") and any(k.startswith("READ UNDER") for k in ur.kind)
                and (ur.column.value_counts() == 1).all()):
            bad(f"unresolved_columns.csv does not say what happened (one row per column): {kinds}")
        else: ok(f"unresolved_columns.csv: 'notes' LEFT OUT, NDVI_sd kept APART (a statistic), NDVI2 a SECOND column, {int((ur.kind == 'READ UNDER ITS CANONICAL NAME').sum())} column(s) read under their canonical name -- one row per column")
        # every value equals the source value of that pixel-year-season (joined on the ROUNDED coordinates, not on a name)
        vars_ = ["NDVI", "SAVI", "EVI", "LAI", "LSWI", "NDWI", "NDMI", "NDRE", "AGB", "RUSLE", "ESI", "WSSI", "WSI", "SMDI", "VCI", "TCI", "VHI", "Rain", "Tmax", "Tmean", "Tmin"]
        n_bad, n_cmp, worst = 0, 0, ""
        for (y, s), d in sources.items():
            sub = pan[(pan.Year == y) & (pan.Season == s)].copy()
            if len(sub) != len(d): bad(f"{y}/{s}: {len(sub)} panel rows for {len(d)} source rows"); continue
            k = lambda t: list(zip(np.round(t.latitude.astype(float), 5), np.round(t.longitude.astype(float), 5)))
            sub.index = k(sub); d2 = d.copy(); d2.index = k(d2)
            common = sub.index.intersection(d2.index)
            if len(common) != len(d2): bad(f"{y}/{s}: {len(d2) - len(common)} source pixels not found in the panel by coordinates"); continue
            for v in vars_:
                a = sub.loc[common, v].astype(float).values; b = d2.loc[common, v].astype(float).values; n_cmp += len(a)
                db = ~np.isclose(a, b, rtol=0, atol=1e-12, equal_nan=True)
                if db.any(): n_bad += int(db.sum()); worst = worst or f"{y}/{s} {v}: panel {a[db][0]!r} vs source {b[db][0]!r}"
            bk_ok = (sub.loc[common, "buff_km"].astype(int).values == d2.loc[common, "buff_km"].astype(int).values).all()
            if not bk_ok: bad(f"{y}/{s}: buff_km differs from the source (a mis-joined ring column)")
        if n_bad: bad(f"{n_bad:,} of {n_cmp:,} values differ from the source ({worst})")
        else: ok(f"{n_cmp:,} values of {len(vars_)} variables x 5 header styles equal the source value of their pixel-year-season exactly")
        ca = B.column_audit
        if not ca.ok.all(): bad(f"column audit: {ca[~ca.ok][['check', 'detail']].to_dict('records')}")
        else: ok(f"column audit CLEAN on the built panel ({len(ca)} checks: every DiD / time column on every row, the rows in the natural order)")
        # post from the exports' flag on every row
        want_post = pan.Year.ge(2022).astype(int).values
        if not (pan.post.values == want_post).all() or not (pan.pre.values == 1 - want_post).all(): bad("post / pre do not follow the exports' Treat flag (1 from 2022)")
        else: ok("post / pre follow the exports' Treat flag (1 = post from 2022) on every row; did_term = treat x post")
    except Exception as e: bad(f"panel from the five styles raised {type(e).__name__}: {e}"); traceback.print_exc(limit=3)
    # ---- 3 name-keyed joins
    try:
        if P._name_key("Haligeri SWS") == P._name_key(" haligeri ") == P._name_key("HALIGERI (sub-watershed)") and P._name_key("Vijayapura District") == P._name_key("vijayapura"):
            ok("the name key unifies 'Haligeri SWS', ' haligeri ', 'HALIGERI (sub-watershed)'; 'Vijayapura District' and 'vijayapura'")
        else: bad(f"the name key does not unify the spellings: {P._name_key('Haligeri SWS')} / {P._name_key(' haligeri ')} / {P._name_key('HALIGERI (sub-watershed)')}")
        dose = pd.DataFrame({"District": ["Vijayapura ", "BAGALKOT"], "target_agri_year": [2024, 2024], "target_season": [2, 2], "dose_asof_season_end": [40.0, 60.0], "amount_asof_season_end": [100.0, 200.0], "area_hectare": [4000.0, 5000.0]})
        xw = pd.DataFrame({"District": ["vijayapura", "Bagalkot"], "Sub Watershed Name": ["Artal", "Haligeri"]})
        full = P.apply_subwshed_division(dose, xw, threshold_pct=50.0)
        if len(full) == 2 and full["Sub Watershed Name"].notna().all() and np.isfinite(full["dose_per_subwshed"]).all(): ok("the dose join matches districts written differently in the fund file and the crosswalk ('Vijayapura ' = 'vijayapura', 'BAGALKOT' = 'Bagalkot')")
        else: bad(f"the dose join lost a district written differently: {full[['District', 'Sub Watershed Name', 'dose_per_subwshed']].to_dict('records')}")
    except Exception as e: bad(f"name-key check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)
    # ---- 4 a planted fault is caught by the audit
    try:
        import pyarrow.parquet as pq
        pan = pd.read_parquet(os.path.join(out, "did_panel_full.parquet")); bad_p = pan.copy(); bad_p.loc[bad_p.index[3], "did_term"] = 1 - bad_p.loc[bad_p.index[3], "did_term"]
        bad_p = pd.concat([bad_p.iloc[10:], bad_p.iloc[:10]], ignore_index=True)                 # the order broken too
        fp = os.path.join(tmp, "planted.parquet"); bad_p.to_parquet(fp, index=False)
        t = P.confirm_panel_columns(fp, tmp, verbose=False); flagged = set(t[~t.ok].check)
        if any("did_term" in c for c in flagged) and any("natural order" in c for c in flagged): ok("a wrong did_term on one row and a broken row order are both caught by the audit")
        else: bad(f"the audit missed a planted fault: {sorted(flagged)}")
    except Exception as e: bad(f"planted-fault check raised {type(e).__name__}: {e}"); traceback.print_exc(limit=2)
    shutil.rmtree(tmp, ignore_errors=True)
    print(); print("CLEAN: no column is mis-joined or left out for its writing style; every DiD column on every row; the rows in the natural order" if not FAILS else f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS: print("  - " + f)
    return 1 if FAILS else 0

if __name__ == "__main__":
    sys.exit(main())
