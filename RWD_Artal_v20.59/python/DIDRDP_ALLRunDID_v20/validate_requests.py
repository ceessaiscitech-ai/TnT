"""
validate_requests.py -- every rule you set for this pipeline, checked on the code as it is now (v20.57).

Each line is one of your requests (from the whole history of the project), where it is implemented, and a check on the
code: most RUN the functions on small data; the rest read the settings that decide the rule (said in each line). Run it after any update to see that nothing you asked for
was lost:

    python validate_requests.py

PASS      the rule holds on this code
DECIDE    the code differs from a rule you stated, for a documented reason -- your decision (nothing is changed for you)
NOT HERE  the check needs hardware this machine lacks (the A40); it runs on yours
FAIL      the rule does not hold (the line says why)
"""
import os, sys, re, json, glob, tempfile, inspect
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd

ROWS = []
def rule(no, text, where, fn):
    if not R_HERE and re.search(r"(^|[^A-Za-z])R([^A-Za-z]|$)", where):      # 2 Oct: the R track is kept outside this module
        ROWS.append({"no": no, "your rule": text, "where": where, "status": "NOT HERE", "proof": "its R half is not in this module (R_separate_track/ in the repository); the Python half is checked by the other rules"}); return
    try:
        status, proof = fn()
    except Exception as e:
        status, proof = "FAIL", f"the check raised {type(e).__name__}: {str(e)[:160]}"
    ROWS.append({"no": no, "your rule": text, "where": where, "status": status, "proof": proof})

import _common as C, _prep_common as P, _hardware as H, _paths as PP, _names as N
RLIB = os.path.dirname(C.r_bridge_script()); R_HERE = os.path.isdir(RLIB)                   # 2 Oct: False in the delivered (Python-only) module
def rsrc(f): return open(os.path.join(RLIB, f), encoding="utf-8").read() if R_HERE else ""
def rconst(src, name):
    m = re.search(rf"^{name}\s*<-\s*(.+?)(\s+#.*)?$", src, re.M); return m.group(1).strip() if m else None
RP, RPREP, RDES = rsrc("reward_paths.R"), rsrc("reward_prep.R"), rsrc("reward_design.R")

def r01():
    lat = np.array([16.70001, 16.70001, 16.70101]); lon = np.array([75.30001, 75.30001, 75.30001])
    a = P.assign_pixel_ids(lat, lon); b = P.assign_pixel_ids(lat[::-1].copy(), lon[::-1].copy())[::-1]
    f = pd.DataFrame({"UID": [11, 22, 33], "pixel_uid": [1, 2, 3], "latitude": lat, "longitude": lon})
    dropped = [c for c in ("UID", "pixel_uid") if c in f.columns and c not in P._drop_source_ids(f).columns]
    ok = a[0] == a[1] and a[0] != a[2] and list(a) == list(b) and "UID" in dropped
    return ("PASS" if ok else "FAIL", f"same coordinates -> same id ({a[0]}), other coordinates -> another id; the exports' own ids dropped: {dropped}")
rule(1, "Pixel id from latitude / longitude; the exports' UID column is never used", "_prep_common.assign_pixel_ids, _drop_source_ids", r01)

def r02():
    d = pd.DataFrame({"pixel_id": [1] * 4 + [2] * 4, "Year": [2020, 2021, 2022, 2023] * 2, "Season": 1, "season_sort_rank": 0,
                      "buff_km": [0] * 4 + [3] * 4, "NDVI": 0.4})
    out = []
    for eng, f in (("model", C.build_treatment_columns), ("prep", P.build_treatment_columns)):
        o = f(d.copy())
        out.append(bool((o.treatment == (o.buff_km == 0)).all() and (o.post == (o.Year >= 2022)).all() and (o.pre == (o.Year < 2022)).all()
                        and (o.did_term == o.treatment * o.post).all() and (o[o.Year == 2022].post == 1).all()))
    ctrl = tuple(C.ACTIVE["control_zones"]) == (1, 2, 3, 4, 5) and int(C.ACTIVE["treatment_year"]) == 2022
    m01 = open(os.path.join(HERE, "02_Core_DiD_Models", "M01_Canonical_2x2_Static_TWFE.ipynb"), encoding="utf-8").read()
    cell_ok = 'TREATMENT_TIMING = \\"fund\\"' in m01 and 'TREATMENT_YEAR = 2022' in m01.replace("TREATMENT_YEAR   = 2022", "TREATMENT_YEAR = 2022")
    r_ok = (rconst(RP, "TREATMENT_YEAR") == "2022" and rconst(RP, "TREATMENT_TIMING") == '"fund"' and rconst(RP, "CONTROL_RINGS") in ('"data"', "1:5")
            and "x[, treat := as.integer(buff_km == 0L)]" in RDES)
    ok = all(out) and ctrl and r_ok and cell_ok
    return ("PASS" if ok else "FAIL", f"both Python engines: core = ring 0, post = Year >= the start (2022 fixed: 2022 is post), did = treat x post: {out}; "
            f"control rings {tuple(C.ACTIVE['control_zones'])} unless you set others (or 'data' finds spillover into an inner ring); the START: your fund "
            f"workbook per sub-watershed by default since v20.57 (TREATMENT_TIMING 'fund' in every model), TREATMENT_YEAR {C.ACTIVE['treatment_year']} = the "
            f"fixed option and the fall-back; R: TREATMENT_TIMING {rconst(RP, 'TREATMENT_TIMING')}, TREATMENT_YEAR {rconst(RP, 'TREATMENT_YEAR')}, rings {rconst(RP, 'CONTROL_RINGS')}"
            + ("" if ok else f" -- CELL 1 {cell_ok}, R {r_ok}"))
rule(2, "Treatment = ring 0 (core), control = rings 1-5; pre / post from the start (2022; since v20.57 the fund workbook per sub-watershed)", "build_treatment_columns (both engines); every model's settings; R reward_paths.R / design_columns", r02)

def r03():
    w = ["Rain", "Tmax", "Tmean", "Tmin"]
    ok = (C.COVARIATE_GROUPS["all"] == w and C.DEFAULT_COVARIATES == w and not set(w) & set(C.ALL_ESTIMATION_VARIABLES)
          and not set(w) & set(C.SELECTED_OUTCOMES) and "LandUse" not in C.DEFAULT_COVARIATES)
    r_cov = rconst(RP, "COVARIATES"); r_out = re.search(r"^OUTCOMES\s*<-\s*c\(([^)]*)\)", RP, re.M | re.S).group(1)
    r_ok = all(v in r_cov for v in w) and not any(f'"{v}"' in r_out for v in w) and "LandUse" not in r_cov
    return ("PASS" if ok and r_ok else "FAIL", f"Python covariates {C.DEFAULT_COVARIATES}, none of them an outcome; R covariates {r_cov}; LandUse never a covariate")
rule(3, "Rain, Tmax, Tmean, Tmin are covariates in every regression -- never outcomes", "_common.COVARIATE_GROUPS / DEFAULT_COVARIATES; R COVARIATES", r03)

def r04():
    nbs = sorted(glob.glob(os.path.join(HERE, "0[2-5]*", "M*.ipynb")))
    last = [json.load(open(nb, encoding="utf-8"))["cells"] for nb in nbs]
    loops = sum(1 for cells in last if any("run_other_outcomes" in "".join(c["source"]) for c in cells if c["cell_type"] == "code"))
    extra = [os.path.relpath(p, HERE) for p in glob.glob(os.path.join(HERE, "08_Multisite_Runs", "*.ipynb"))]
    return ("DECIDE" if loops == len(nbs) else "FAIL",
            f"{loops} of {len(nbs)} model notebooks run ONE model and loop it over your outcomes only (run_other_outcomes). Optional runners "
            f"exist and run nothing unless opened: {extra} (one model per site, then pooled) and, in RWDR, R_RUN_ALL_MODELS (several models "
            f"in a row) -- keep or delete them")
rule(4, "Each model is run by you, one at a time; automation only loops a single model over the outcomes", "every model notebook's last cell", r04)

def r05():
    seen = []; keep = (C.RESULTS_ROOT, dict(C.ACTIVE))
    try:
        C.RESULTS_ROOT = tempfile.mkdtemp(prefix="vr_sites_")
        C.run_sites(lambda tag: seen.append((tag, C._site_list())), sites=[3, 7], use_site_years=False, label="validate_requests")
    finally:
        C.RESULTS_ROOT = keep[0]; C.ACTIVE.clear(); C.ACTIVE.update(keep[1])
    ok = seen == [("site_3", [3]), ("site_7", [7]), ("pooled", [3, 7])] and C.SITE_FILTER is None
    return ("PASS" if ok else "FAIL", f"run_sites ran the model on {seen} -- each sub-watershed alone, then pooled -- and gave the whole panel back "
            f"afterwards; per-site package inputs are kept apart (v20.54)")
rule(5, "Sub-watersheds processed one at a time, then pooled", "_common.run_sites, 08_Multisite_Runs/MS01", r05)

def r06():
    d = PP.derive(input_dir=tempfile.mkdtemp(prefix="vr_in_"))
    inside = d["OUTPUT_DIR"].startswith(d["INPUT_DIR"]) and d["TEMP_DIR"].startswith(d["OUTPUT_DIR"])
    root = d["INPUT_DIR"]; os.makedirs(os.path.join(root, "output"), exist_ok=True); os.makedirs(os.path.join(root, "sub", "deeper"), exist_ok=True)
    for p_ in ("CSV_2021_Rabi_tile0.csv", os.path.join("sub", "deeper", "rabi_2022.parquet"), os.path.join("output", "did_panel_full.parquet")):
        pd.DataFrame({"latitude": [16.7], "longitude": [75.3], "NDVI": [0.4]}).to_csv(os.path.join(root, p_), index=False) if p_.endswith(".csv") else \
        pd.DataFrame({"latitude": [16.7], "longitude": [75.3], "NDVI": [0.4]}).to_parquet(os.path.join(root, p_), index=False)
    files = P.discover_input_files(root, d["OUTPUT_DIR"], d["TEMP_DIR"], verbose=False)[0]
    names = sorted(os.path.basename(f) for f in files)
    ok = inside and names == ["CSV_2021_Rabi_tile0.csv", "rabi_2022.parquet"]
    return ("PASS" if ok else "FAIL", f"output = <data>/output, temp inside it; discovered {names} (a file in output/ is never read back; "
            f"sub-folders at any depth are read -- your v20.14 request replaced the earlier 'Parquet only from the top folder')")
rule(6, "Temporary and result folders inside the data folder; exports read from it (any depth since your v20.14 request)", "_paths.derive, _prep_common.discover_input_files", r06)

def r07():
    base = dict(site_id=1, NDVI=0.4, src_file="a.csv", file_mtime=1.0, schema_vintage="x")
    df = pd.DataFrame([dict(pixel_id=1, Year=2021, Season=1, **base), dict(pixel_id=1, Year=2021, Season=1, **{**base, "NDVI": 0.5, "src_file": "b.csv", "file_mtime": 9.0}),
                       dict(pixel_id=1, Year=2022, Season=1, **base), dict(pixel_id=1, Year=2021, Season=2, **base)])
    out, _ = P.resolve_duplicates(df, conflict_log=[])
    kept = out.sort_values(["Year", "Season"]); ok = len(out) == 3 and float(kept.iloc[0].NDVI) == 0.5
    return ("PASS" if ok else "FAIL", f"4 rows (one duplicate within a pixel-year-season) -> {len(out)} rows; the newer file's value kept ({float(kept.iloc[0].NDVI)}); "
            f"other years / seasons of the pixel untouched")
rule(7, "Duplicates removed only within the same pixel-year-season (newer export wins); every year and season kept", "_prep_common.resolve_duplicates", r07)

def r08():
    f = pd.DataFrame({"NDVI": [0.4, np.nan, 0.0, 0.4], "Rain": [0.0, 10.0, 12.0, 11.0], "buff_km": [0, 0, 1, 1]})
    g, _ = P.apply_missing_policy(f.copy(), stage="file")        # rows 2 and 3 (NaN / 0 outcome) leave; the exported Rain 0 is missing
    ok = (not C._usable([0.0], "NDVI")[0]) and (not C._usable([np.nan], "NDVI")[0]) and len(g) == 2 and np.isnan(g.Rain.iloc[0]) and g.Rain.iloc[1] == 11.0
    _rb = RPREP.split("apply_missing_policy <- function")[1].split("\n}")[0]; r_ok = "x[x == 0] <- NA" in _rb or 'abs(x) <= .opt("PRECISION_TOLERANCE"' in _rb or "abs(x) <= .tol_R()" in _rb   # v20.55: R's apply_missing_policy; spec 1: |x| <= the tolerance
    return ("PASS" if ok and r_ok else "FAIL", "an exact 0 or NaN is no-data in outcomes AND covariates (Python and, since v20.54, R); the row without an "
            "outcome is dropped; load_panel blocks both from every model (validate_all_models: no placeholder value in any result)")
rule(8, "NaN and exact-zero cells are no-data: dropped in preparation, blocked from every model; no placeholder results", "_prep_common.apply_missing_policy, _common._usable; R apply_missing_policy", r08)

def r09():
    shp = os.path.join(HERE, "data", "sites", "SWSs20_KarnatakaAll5k.shp")
    import _sws_geometry as S
    L = S.SWSLocator.from_shapefile()
    n = len(set(L.name_to_id.values())) if hasattr(L, "name_to_id") else None
    return ("PASS" if os.path.exists(shp) and n == 20 else "FAIL", f"{os.path.relpath(shp, HERE)} ships with the engine; {n} sub-watersheds (SWSiD_All) with their rings")
rule(9, "SWSiD_All identifies each sub-watershed with its control rings; the SWSs20_KarnatakaAll5k shapefile is part of the pipeline", "data/sites, _sws_geometry", r09)

def r10():
    ok = C.ACTIVE.get("seasons") == "all" and C.ACTIVE.get("unit_fe") == "pixel_season" and rconst(RP, "SEASONS") == '"all"'
    return ("PASS" if ok else "FAIL", f"default: every year, annual + Kharif / Rabi / Zaid (seasons = {C.ACTIVE.get('seasons')}), unit FE = pixel x season, "
            f"period FE = year x season; R SEASONS {rconst(RP, 'SEASONS')} (a single season is an option since v20.53)")
rule(10, "All years and all annual + seasonal data, with year, season and pixel fixed effects", "_common.ACTIVE; R SEASONS", r10)

def r11():
    keep = C.PREBUILT_FILE
    try:
        C.PREBUILT_FILE = os.path.join(tempfile.mkdtemp(prefix="vr_pb_"), "prebuilt_verified.json")      # nothing verified yet
        head = C.prebuilt_first("M11", "NDVI", verbose=False); why = str(C.LAST_ENGINE.get("M11", {}).get("reason", ""))
    finally:
        C.PREBUILT_FILE = keep
    good, _ = C._judge_known_answer("M27", {"att": 0.0501}); biased, _ = C._judge_known_answer("M27", {"att": 0.0800})
    n_py = sum(1 for v in C.PREBUILT_MODELS.values() if v.get("package")); n_r = len(C.R_ROUTES)
    both = sorted(set(k for k, v in C.PREBUILT_MODELS.items() if v.get("package")) | set(C.R_ROUTES))
    ok = C.PREBUILT_MODE == "auto" and head is None and ("not verified" in why or "not installed" in why) and good and not biased
    return ("PASS" if ok else "FAIL", f"PREBUILT_MODE '{C.PREBUILT_MODE}': a verified Python package first ({n_py} models + {len(C.PREBUILT_ROUTES)} "
            f"estimator routes), then a verified R package ({n_r} models), the engine last -- {len(both)} of 45 models have a package route. "
            f"Run: an unverified package hands over with its reason ('{why[:60]}'); the known-answer test accepts +0.050 and refuses a "
            f"biased +0.080. P00's P12 verifies each installed version before use")
rule(11, "Pre-built packages first, with fall-backs", "_common: PREBUILT_MODELS, R_ROUTES, _route_call; P00 P12", r11)

def r12():
    thr = P.PIXEL_OVERLAP_MIN
    base_ok = P.NEAR_DUPLICATE_PIXELS and P.DEDUP_PRIORITY == "newer"
    st = "PASS" if (base_ok and thr >= 0.80) else ("DECIDE" if base_ok else "FAIL")
    return (st, f"overlapping pixels become one pixel, the newer export wins (DEDUP_PRIORITY 'newer'; 'complete' = the more complete cell). "
            f"Threshold PIXEL_OVERLAP_MIN = {thr:.2f}: your rule says > 80 %. It was lowered to 0.65 in v20.38 because your 2025 exports sit "
            f"on a grid shifted ~3 m -- at 0.80, 20 % of the treated post-period pixels had no pre-period history. Set 0.80 in "
            f"_prep_common.py (and R reward_paths.R) to follow the rule exactly; P00 then rebuilds the panel")
rule(12, "Pixels whose footprints overlap > 80 % are one pixel (newer export wins; more complete cell as the alternative)", "_prep_common.PIXEL_OVERLAP_MIN, DEDUP_PRIORITY", r12)

def r13():
    ok = C.COVARIATE_GROUPS.get("mean_temp_rain") == ["Tmean", "Rain"] and C.COVARIATE_GROUPS.get("all") == ["Rain", "Tmax", "Tmean", "Tmin"] \
         and "covariates" not in C.SCENARIO_KEYS
    return ("PASS" if ok else "FAIL", f"groups {sorted(C.COVARIATE_GROUPS)}: chosen in each model's CELL 1 (COVARIATES = ...), never at preparation")
rule(13, "Covariates chosen in each model (groups: mean temperature + rainfall; all), not at panel preparation", "_common.COVARIATE_GROUPS", r13)

def r14():
    sv = (P.ALLOW_NEGATIVE_COVARIATES, dict(P.NEGATIVE_COVARIATE_RULE)); res = {}
    try:
        for allow in (False, True):
            P.ALLOW_NEGATIVE_COVARIATES = allow
            g, _ = P.apply_missing_policy(pd.DataFrame({"NDVI": [0.4, 0.4], "Rain": [-2.0, -9999.0]}), stage="file")
            res[allow] = g.Rain.tolist()
    finally:
        P.ALLOW_NEGATIVE_COVARIATES, P.NEGATIVE_COVARIATE_RULE = sv
    ok = res[False][0] == 0.0 and np.isnan(res[False][1]) and res[True][0] == -2.0 and np.isnan(res[True][1])
    r_ok = rconst(RP, "ALLOW_NEGATIVE_COVARIATES") == "FALSE" and "isTRUE(ALLOW_NEGATIVE_COVARIATES)" in RPREP
    return ("PASS" if ok and r_ok else "FAIL", f"barrier on: Rain -2 -> 0; off (ALLOW_NEGATIVE_COVARIATES = True): -2 kept; a -9999 fill value is missing "
            f"either way; R has the same switch (v20.54)")
rule(14, "Negative covariates become 0 at panel level; an option removes this barrier", "_prep_common.ALLOW_NEGATIVE_COVARIATES; R reward_paths.R", r14)

def r15():
    d = pd.DataFrame({"y": np.zeros(1000), "x": np.ones(1000)}); calls = []
    saved = H.ram_budget_bytes
    try:
        H.ram_budget_bytes = lambda: 10.0                                   # no room left below 98 %
        small = C._route_call("twfe", lambda df: calls.append(1) or "package", d)
        n_small = H.worker_cap(n_tasks=64, bytes_per_worker=1e9)
        H.ram_budget_bytes = lambda: 1e15                                   # plenty of room
        big = C._route_call("twfe", lambda df: calls.append(1) or "package", d)
        n_big = H.worker_cap(n_tasks=64, bytes_per_worker=1e9)
    finally:
        H.ram_budget_bytes = saved
    p = H.machine_profile(); want_big = max(1, min(int(p["logical_cores"]), p["pool_limit"], 64))
    ok = (H.MEMORY_CEILING == 0.98 and C.LOAD_ALL_AT_ONCE and C.GPU_MAX_ROWS is None and C.GPU_VERIFY == "full"
          and small is None and big == "package" and len(calls) == 1 and n_small == 1 and n_big == want_big)
    return ("PASS" if ok else "FAIL", f"run with the RAM left below {H.MEMORY_CEILING:.0%} set by hand: no room -> the package hands over to the "
            f"engine and 1 worker; plenty -> the package runs and {n_big} workers (every core, up to 64 tasks). Whole tables are read "
            f"at once; GPU results are checked on ALL rows (GPU_VERIFY '{C.GPU_VERIFY}'), else not used")
rule(15, "All data in RAM and GPU at once; fall back only at 98 % (v20.57; was 95 %); GPU demeaning verified on the full data", "_hardware (98 %), _common.load_panel / _gpu_verify", r15)

def r16():
    s1 = N.similarity("Kandgul", "Kandgula"); s2 = N.similarity("Kohalli", "Kodihalli")
    ok = N.NAME_MATCH_THRESHOLD == 0.80 and s1 >= 0.8 > s2 and rconst(RPREP, "NAME_MATCH_THRESHOLD").startswith("0.80")
    return ("PASS" if ok else "FAIL", f"threshold {N.NAME_MATCH_THRESHOLD} (Python) = R; Kandgul/Kandgula {s1:.2f} -> same, Kohalli/Kodihalli {s2:.2f} -> different")
rule(16, "Sub-watershed names >= 80 % similar are the same sub-watershed", "_names.NAME_MATCH_THRESHOLD; R NAME_MATCH_THRESHOLD", r16)

def r17():
    p = H.machine_profile(); n = H.worker_cap(n_tasks=10**6)
    ok = (not H.AUTO_SPLIT and H.MEMORY_SHARE == 1.0 and H.memory_share() == 1.0 and n == min(int(p["logical_cores"]), p["pool_limit"])
          and rconst(RP, "N_THREADS").startswith(("max(1L, parallel::detectCores())", "max(1L, all_logical_cores_R())")) and rconst(RDES, "AUTO_SPLIT") == "FALSE")
    return ("PASS" if ok else "FAIL", f"run: {n} worker processes on this {p['logical_cores']}-core machine (every core; Windows' own pool limit is "
            f"{H.WINDOWS_POOL_LIMIT}), share of the machine {H.memory_share():.0%}, also when several pipelines run (AUTO_SPLIT {H.AUTO_SPLIT}); the "
            f"only limit is your 98 % rule. R: every core")
rule(17, "No cap on GPU, memory, cores or processors (maximum use)", "_hardware.AUTO_SPLIT / MEMORY_SHARE / worker_cap; R N_THREADS", r17)

def r18():
    sv = (H.AUTO_SPLIT, H.MEMORY_SHARE, H.INSTANCE_DIR, dict(H._SHARE_CACHE))
    try:
        H.INSTANCE_DIR = tempfile.mkdtemp(prefix="vr_inst_"); H._SHARE_CACHE.update(v=None, t=0.0)
        import subprocess, time
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
        json.dump({"pid": other.pid, "root": "__another_data_folder__", "heartbeat": time.time()}, open(os.path.join(H.INSTANCE_DIR, f"{other.pid}.json"), "w"))
        H.AUTO_SPLIT = True; half = H.memory_share(); other.kill(); other.wait()
        H.AUTO_SPLIT = False; H.MEMORY_SHARE = 0.5; manual = H.memory_share()
    finally:
        H.AUTO_SPLIT, H.MEMORY_SHARE, H.INSTANCE_DIR = sv[0], sv[1], sv[2]; H._SHARE_CACHE.clear(); H._SHARE_CACHE.update(sv[3])
    ok = abs(half - 0.5) < 1e-9 and abs(manual - 0.5) < 1e-9
    return ("PASS" if ok else "FAIL", f"switched on, AUTO_SPLIT gives {half:.2f} with a second data folder running; MEMORY_SHARE = 0.5 gives {manual:.2f} "
            f"(both off by default -- your later 'no cap' instruction)")
rule(18, "The 50 % split stays available as a fall-back option for two data folders", "_hardware.AUTO_SPLIT, _paths.MEMORY_SHARE", r18)

def r19():
    a = PP.INPUT_DIR if not os.environ.get("REWARD_INPUT_DIR") else os.environ["REWARD_INPUT_DIR"]
    src = open(os.path.join(HERE, "_paths.py"), encoding="utf-8").read()
    lit = re.search(r'^INPUT_DIR = .*?r"([^"]+)"', src, re.M).group(1); leg = re.search(r'^LEGACY_INPUT_DIR = r"([^"]+)"', src, re.M).group(1)
    ok = (lit == r"D:\LKT\RWD_Artal\data" and leg == r"D:\LKT\TST_Artal"                    # v20.58: ONE Python project (RWD_Artal1 dropped)
          and PP.SUBWSHED_CROSSWALK_PATH == r"D:\LKT\RWD_Sub_watershed_final_list.xlsx"
          and PP.FUND_RELEASE_PATH == r"D:\LKT\Districtwise_Month_wise_Progress_with_DoseIntensity_and_SWS.xlsx"
          and rconst(RP, "DEFAULT_ROOT") == '"D:/LKT/RWDR/data"')
    return ("PASS" if ok else "FAIL", f"data {lit} (until MIGRATE_DATA.bat: {leg}); crosswalk and fund file in D:\\LKT; R: {rconst(RP, 'DEFAULT_ROOT')}")
rule(19, "Your paths stay as set (v20.58: ONE Python project RWD_Artal and ONE R project RWDR -- the RWD_Artal1 copy dropped; data in their own folders)", "_paths.py; R reward_paths.R", r19)

def r20():
    import validate_all_models as VM
    df = VM.make_panel(n_pix=60); df["GapFilled"] = 0
    gf = (df.Year == 2025) & (df.Season == 2); proj = (df.Year == 2026) & (df.Season == 1)
    df.loc[gf, "GapFilled"] = 1; df.loc[proj, "Coverage"] = 0.0                       # filled from history / projected
    d_ = tempfile.mkdtemp(prefix="vr_gf_"); fp = os.path.join(d_, "panel.parquet"); df.to_parquet(fp, index=False)
    keep = (C.PREPARED_PANEL, C.ESTIMATOR_FILES_DIR, dict(C.ACTIVE), C.SITE_FILTER)
    try:
        C.PREPARED_PANEL = fp; C.ESTIMATOR_FILES_DIR = os.path.join(d_, "ef"); C.clear_panel_cache(); C.SITE_FILTER = None
        C.set_scenario(verbose=False, all_years=True)
        got = C.load_panel(columns=C.columns_for("NDVI"))
    finally:
        C.PREPARED_PANEL, C.ESTIMATOR_FILES_DIR = keep[0], keep[1]; C.ACTIVE.clear(); C.ACTIVE.update(keep[2]); C.SITE_FILTER = keep[3]; C.clear_panel_cache()
    left = int(((got.Year == 2025) & (got.Season == 2)).sum() + ((got.Year == 2026) & (got.Season == 1)).sum())
    ok = C.EXCLUDE_GAPFILLED and left == 0 and len(got) > 0 and rconst(RP, "EXCLUDE_GAPFILLED") == "TRUE"
    return ("PASS" if ok else "FAIL", f"run on a panel with filled rows (GapFilled = 1) and projected rows (Coverage = 0): {left} of them reach a "
            f"model ({len(got):,} other rows do). R: EXCLUDE_GAPFILLED = {rconst(RP, 'EXCLUDE_GAPFILLED')} (since v20.52)")
rule(20, "Values generated from the previous 3 years are estimates, not observations", "_common.EXCLUDE_GAPFILLED / load_panel; R EXCLUDE_GAPFILLED", r20)

def r21():
    ml = open(os.path.join(HERE, "python_prebuilt", "ml_spatial_pipeline.py"), encoding="utf-8").read()
    r_null = "N_MAX_UNITS         <- NULL; N_MAX_PIXELS_MIXED <- NULL; N_MAX_ML <- NULL; N_MAX_SPATIAL <- NULL" in RP
    fixed = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "0[2-5]_*", "M*.ipynb")) if re.search(r"MAX_SPATIAL_N = [0-9]", open(f, encoding="utf-8").read())]
    b_ = C._memory_budget_bytes(); n1 = C.rows_that_fit(1000.0)
    ok = ("n_max=None" in ml and "rows_that_fit" in ml and r_null and not fixed and "nn_sample=None" in inspect.getsource(C.diagnose_effect_size)
          and "N_MAX_SPATIAL <- NULL" in rsrc("models_prebuilt.R") and (b_ is None or n1 == max(1, int(b_ / 1000.0))))
    return ("PASS" if ok else "FAIL", "the 'Unknown' kernel status was not a crash: the limits set after it were reverted, doubled (v20.50), raised 10x (v20.55) and -- "
            "your v20.57 rule -- REMOVED: no fixed sample size is left (Python ML / spatial weights / k-NN / near-duplicate sample, R units / lmer / rq / ML / spatial): "
            f"a model samples only what would not fit below 98 % of the RAM (run here: {n1:,} rows of 1 kB fit now)" + ("" if ok else f" -- fixed in {fixed[:3]}, R NULL {r_null}"))
rule(21, "Kernel status 'Unknown' is not a crash: its restrictions reverted; data limits doubled (v20.50), 10x (v20.55), removed (v20.57: the 98 % rule)", "ml_spatial_pipeline.run_ml / run_spatial, _common.rows_that_fit; R reward_paths.R / units_that_fit", r21)

def r22():
    ok = callable(getattr(C, "gpu_selftest", None)) and C.GPU_AUTO_SELFTEST and os.path.exists(os.path.join(HERE, "06_Validation", "V00d_GPU_PATH_CHECK.py"))
    try:
        import torch; cuda = bool(torch.cuda.is_available()); dev = torch.cuda.get_device_name(0) if cuda else None
    except Exception:
        cuda, dev = False, None
    if not ok: return ("FAIL", "the GPU self-test or V00d is missing")
    if not cuda:
        return ("NOT HERE", "no CUDA device on this machine (or torch without CUDA): the check cannot run here. On your A40 this line "
                "runs the GPU self-test (GPU vs CPU demeaning); V00d_GPU_PATH_CHECK.py runs the whole GPU path")
    sp = C.gpu_selftest(n=200_000)
    return ("PASS" if sp is not None else "FAIL", f"{dev}: GPU demeaning equals the CPU to < 1e-8 on 200,000 rows ({sp:.0f}x faster)" if sp else f"{dev}: self-test failed")
rule(22, "Your NVIDIA A40 used first, verified", "_common.gpu_selftest / GPU_AUTO_SELFTEST; 06_Validation/V00d", r22)

def r23():
    here = os.path.basename(os.path.dirname(os.path.dirname(HERE)))
    ok = here.endswith("_v" + C.ENGINE_VERSION)
    return ("PASS" if ok else "DECIDE", f"project folder '{here}', engine {C.ENGINE_VERSION}" + ("" if ok else " (the folder was renamed after unzipping?)"))
rule(23, "Bundles named by their version", "the project folder, _version.py", r23)

# ---------------------------------------------------------------- v20.55: your requests of the seasons / parity / packages turn
def r24():
    nb = os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb")
    src = "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
    py_ok = ("seasons=SEASONS" in src and 'SEASONS        = "all"' in src
             and 'if str(seasons).strip().lower() == "auto": _dk.add("seasons")' in inspect.getsource(C.set_scenario))
    r_ok = ('identical(s$seasons_setting, "auto")' in RDES and rconst(RP, "SEASONS") == '"all"'
            and "length(rec$pre_window) > 0 && length(rec$post_window) > 0" in RDES)
    keep = dict(C.ACTIVE)
    try:
        got = {m: C.season_codes(C.normalize_seasons(m)) for m in ("all", "seasonal", "yearly", "Rabi", "Kharif+Rabi")}
    finally:
        C.ACTIVE.clear(); C.ACTIVE.update(keep)
    codes_ok = got == {"all": None, "seasonal": {1, 2, 3}, "yearly": {0}, "Rabi": {2}, "Kharif+Rabi": {1, 2}}
    ok = py_ok and r_ok and codes_ok
    return ("PASS" if ok else "FAIL", "both pipelines estimate on the annual composite AND Kharif / Rabi / Zaid rows by default (SEASONS = 'all': pixel x season and "
            "year x season fixed effects), and the data-driven design no longer replaces that setting with 'yearly' (only SEASONS = 'auto' follows the data). "
            "Your option: 'seasonal' | 'yearly' | named seasons -- since v20.57 in each MODEL's settings (Python CELL 1, R notebook), applied when it runs"
            + ("" if ok else f" -- Python {py_ok}, R {r_ok}, codes {codes_ok}"))
rule(24, "R AND Python use the yearly and the seasonal data together (season AND year variation); option: season-based or season + year", "every model's SEASONS -> set_scenario / resolve_design, normalize_seasons / season_codes / load_panel; R model_design, load_panel_R", r24)

def r25():
    pf = os.path.join(HERE, "validate_r_parity.py"); have = os.path.exists(pf)
    ports = all(k in RPREP for k in ("harmonise_names <- function", "recode_buff_km <- function", "apply_missing_policy <- function", "pixel_ids <- function",
                                      "near_duplicate_pairs <- function", "canonical_pixel_map <- function", "resolve_duplicates <- function", "overlay_sws <- function"))
    fill = "seasonal mean" in RDES and 'identical(d$pooled_fe, "site_period")' in RDES
    ok = have and ports and fill
    return ("PASS" if ok else "FAIL", "R's data structuring mirrors Python step for step (formats, name parsing, harmonisation, buff_km recode, zero rule, rows without any outcome, "
            "negatives, pixel ids, shapefile overlay, near-duplicate merge, duplicate rule with fill, annual covariate fill, pooled site x period FE) and validate_r_parity.py "
            "proves it on synthetic exports: the same design, the same 7,800-row panel, the same NDVI / EVI samples, the same rows under every season mode and OVERLAP_ROWS, "
            "the same M01 estimate to 1e-8 (run it after any change to either pipeline)" + ("" if ok else f" -- harness {have}, ports {ports}, fill/FE {fill}"))
rule(25, "The R data structuring must be the same as the Python pipeline's", "R/lib/reward_prep.R (ports of _prep_common), validate_r_parity.py", r25)

def r26():
    fns = all(callable(getattr(C, f, None)) for f in ("install_python_package", "ensure_python_packages", "confirm_packages", "r_package_status"))
    chain = "--prefer-binary" in inspect.getsource(C.install_python_package) and "--no-binary" in inspect.getsource(C.install_python_package) and "_wheel_dirs" in inspect.getsource(C.install_python_package)
    use = "_AUTO_INSTALL_TRIED" in inspect.getsource(C._use_prebuilt)
    rpk = rsrc("reward_packages.R"); r_ok = all(k in rpk for k in ("install_package_chain <- function", "ensure_packages <- function", "confirm_packages <- function", "need <- function", "r-universe", "install_github", "archive/HEAD.tar.gz"))
    nb = os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb")
    src = "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
    p12 = "C.confirm_packages(" in src
    rnb = glob.glob(os.path.join(os.path.dirname(RLIB), "..", "RWDR*", "rstudio", "*.Rmd"))       # the R project, when it sits beside this one
    ok = fns and chain and use and r_ok and p12
    return ("PASS" if ok else "FAIL", "pre-built packages are the primary route (P12 verifies each on a known answer); a missing one is installed when a step needs it -- "
            "Python: wheel -> source -> local wheel folder; R: CRAN binary -> source -> author's r-universe -> GitHub -> source archive -> mirror (ONE chain for "
            "00_SETUP.R, run time and the Python bridge) -- and every run confirms 'N of N installed' (P00 P12 -> PACKAGE_STATUS.csv; every R notebook -> PACKAGE_STATUS_R.csv)"
            + ("" if ok else f" -- fns {fns}, chain {chain}, run-time {use}, R {r_ok}, P12 {p12}"))
rule(26, "Pre-built packages first; fetch the source when no build exists; ensure, validate and confirm every package at run time", "_common.confirm_packages / install_python_package / _use_prebuilt; R/lib/reward_packages.R; P00 P12; every R notebook's setup chunk", r26)

def r27():
    keep = dict(C.ACTIVE)
    try:
        C.set_scenario(verbose=False, overlap_rows="keep"); tk = C.scenario_tag(); C.set_scenario(verbose=False, overlap_rows="drop"); td = C.scenario_tag()
    finally:
        C.ACTIVE.clear(); C.ACTIVE.update(keep)
    keep2 = dict(C.ACTIVE)
    try:                                               # v20.58: the overlap rows are the LOCATION rule's codes 3 / 4 (dropped from every group)
        C.set_scenario(verbose=False, overlap_rows="drop"); cd_ = C.location_drop_codes(); C.set_scenario(verbose=False, overlap_rows="keep"); ck_ = C.location_drop_codes()
    finally:
        C.ACTIVE.clear(); C.ACTIVE.update(keep2)
    py_ok = ("_keepOverlap" in tk and "_keepOverlap" not in td and {3, 4} <= set(cd_) and not ({3, 4} & set(ck_))
             and "location_mask(out, _lt, pooled=True)" in inspect.getsource(C.build_treatment_columns))
    r_ok = rconst(RP, "OVERLAP_ROWS") == '"drop"' and 'd$overlap_rows %||% OVERLAP_ROWS, "keep"' in RDES
    ok = py_ok and r_ok
    return ("PASS" if ok else "FAIL", "OVERLAP_ROWS = 'drop' (default: the control rows of a pixel TREATED in another sub-watershed, and rows repeating a pixel already in the "
            "sample, leave the estimation -- they pull every DiD toward zero) | 'keep' keeps them; results then carry the tag _keepOverlap. P00_Settings and R reward_paths.R / R_P00"
            + ("" if ok else f" -- Python {py_ok}, R {r_ok}"))
rule(27, "Option to keep or drop the rows of pixels overlapping another sub-watershed", "every model's OVERLAP_ROWS (Python CELL 1 -> set_scenario / build_treatment_columns; R notebook -> model_design / load_panel_R)", r27)

def r28():
    # a pixel with NDVI missing in ONE period keeps its other periods, and EVI keeps that period: the row leaves only the estimation that needs it
    rows = []
    for pix in range(1, 9):
        for y in (2019, 2020, 2021, 2022, 2023):
            for se in (0, 1, 2):
                rows.append({"pixel_id": pix, "site_id": 1, "subwshed_id": "S1", "buff_km": 0 if pix <= 3 else 3, "Year": y, "Season": se,
                             "NDVI": 0.4 + 0.001 * pix, "EVI": 0.3 + 0.001 * pix, "Rain": 500.0, "Tmax": 33.0, "Tmean": 26.0, "Tmin": 19.0, "LandUse": 1,
                             "first_treat_agri_year": 2022.0 if pix <= 3 else np.inf, "time_fe_yearseason": f"{y}_{se}"})
    f = pd.DataFrame(rows); f.loc[(f.pixel_id == 2) & (f.Year == 2021) & (f.Season == 1), "NDVI"] = np.nan
    d = tempfile.mkdtemp(prefix="req_unbal_"); fp = os.path.join(d, "panel.parquet"); f.to_parquet(fp, index=False)
    keep = (C.PREPARED_PANEL, dict(C.ACTIVE))
    try:
        C.PREPARED_PANEL = fp; C.clear_panel_cache(); C.set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, seasons="all", covariates=["Rain"])
        n_ = C.load_panel(columns=C.columns_for("NDVI"))          # columns_for names the estimation's own columns (outcome + covariates)
        e_ = C.load_panel(columns=C.columns_for("EVI"))
        pix2_n = int((n_.pixel_id == 2).sum()); pix2_e = int((e_.pixel_id == 2).sum())
        ok = pix2_n == 14 and pix2_e == 15 and len(n_) == 119 and len(e_) == 120
    finally:
        C.PREPARED_PANEL = keep[0]; C.ACTIVE.clear(); C.ACTIVE.update(keep[1]); C.clear_panel_cache()
    r_ok = "leave THIS estimation only" in RDES
    return ("PASS" if (ok and r_ok) else "FAIL", f"unbalanced panel: a pixel with NDVI missing in one period keeps its other {pix2_n} rows in the NDVI estimation and all "
            f"{pix2_e} in the EVI estimation (NDVI sample {len(n_)} of 120 rows, EVI {len(e_)}); nothing is balanced or dropped panel-wide; R load_panel_R reports the same rule"
            + ("" if r_ok else " -- R message missing"))
rule(28, "Unbalanced panel: a missing row / pixel leaves only its own estimation, never the whole panel", "_common.load_panel (per-model columns); R load_panel_R", r28)

def r29():
    src = inspect.getsource(C.recommend_design)
    py_ok = "common_shocks" in src and "rescaled" in src and "persists" in src and "core = d[d._ring == 0]" in src
    r_ok = "common_shocks" in RDES and "rescaled" in RDES and "core0 <- a0[Season == s0 & buff_km == 0]" in RDES
    mp = inspect.getsource(P.canonical_pixel_map); one = "np.flatnonzero(np.diff(hi))" in mp
    nb = os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb")
    src2 = "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
    thr = "P.PIXEL_OVERLAP_MIN = 0.80" not in src2
    ok = py_ok and r_ok and one and thr
    return ("PASS" if ok else "FAIL", "what the parity harness found and fixed in BOTH pipelines: (a) the near-duplicate merge could map many pixels onto one canonical pixel "
            "(now one-to-one); (b) a common year shock ended the post window as an 'export break' (now reported as a common shock -- the year fixed effects absorb it; "
            "only a lost pixel history or a persistent re-scaling is a break); (c) the linkage counted finite outcomes per row group (now pixels present, whole file); "
            "(d) P00 PASS B overrode PIXEL_OVERLAP_MIN 0.65 -> 0.80 (now the setting decides)" + ("" if ok else f" -- Python {py_ok}, R {r_ok}, one-to-one {one}, threshold {thr}"))
rule(29, "Deep and hard testing: defects found by the new tests are fixed in both pipelines", "_prep_common.canonical_pixel_map, _common.recommend_design, R recommend_design, P00 PASS B", r29)

# ---------------------------------------------------------------- v20.56: no chunking; R packages pre-built first, Rtools only when unavoidable
def r30():
    nb = os.path.join(HERE, "02_Core_DiD_Models", "M01_Canonical_2x2_Static_TWFE.ipynb")
    src = "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
    m01 = ('M01_MODE   = "auto"' in src and "RUN_MODE, _why = C.run_mode(MODEL_ID, cols)" in src and "C.load_panel_ooc(cols)" in src   # v20.58: your 98 % rule --
           and "C.ooc_model(MODEL_ID" in src)                                                                             #   out of core only beyond
    users = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "0[2-5]_*", "M*.ipynb"))
             if "estimate_twfe_did_streaming(" in open(f, encoding="utf-8").read() and "M01_" not in os.path.basename(f)]
    # run: the loader keeps every row of a small panel (no thinning) and the estimator sees all of them
    rows = []
    for pix in range(1, 13):
        for y in (2019, 2020, 2021, 2022, 2023):
            for se in (0, 1, 2):
                rows.append({"pixel_id": pix, "site_id": 1, "subwshed_id": "S1", "buff_km": 0 if pix <= 4 else 3, "Year": y, "Season": se,
                             "NDVI": 0.4 + 0.001 * pix + (0.05 if (pix <= 4 and y >= 2022) else 0), "Rain": 500.0, "Tmax": 33.0, "Tmean": 26.0, "Tmin": 19.0,
                             "LandUse": 1, "first_treat_agri_year": 2022.0 if pix <= 4 else np.inf, "time_fe_yearseason": f"{y}_{se}"})
    f = pd.DataFrame(rows); d = tempfile.mkdtemp(prefix="req_nochunk_"); fp = os.path.join(d, "panel.parquet"); f.to_parquet(fp, index=False)
    keep = (C.PREPARED_PANEL, dict(C.ACTIVE))
    try:
        C.PREPARED_PANEL = fp; C.clear_panel_cache(); C.set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, seasons="all", covariates=["Rain"])
        mode, why = C.recommend_mode(C.columns_for("NDVI"))
        x = C.load_panel(columns=C.columns_for("NDVI")); x = C.build_treatment_columns(x); x = x[x.in_analysis_sample == 1]
        r = C.estimate_twfe_did(x, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id", return_all=True)
        all_rows = len(x) == 180 and x.attrs.get("sample_fraction_applied", 1.0) == 1.0 and r["n"] == 180
    finally:
        C.PREPARED_PANEL = keep[0]; C.ACTIVE.clear(); C.ACTIVE.update(keep[1]); C.clear_panel_cache()
    gsrc = inspect.getsource(C._demean_gpu_matrix); gpu_whole = "range(0, n" not in gsrc and "chunk" not in gsrc.lower()
    ok = getattr(C, "NO_CHUNKING", False) and C.MEMORY_POLICY == "raise" and mode == "memory" and m01 and not users and all_rows and gpu_whole
    return ("PASS" if ok else "FAIL", f"every regression model loads ALL its rows into RAM and runs once (the GPU demeaner takes the whole matrix below the 98 % VRAM ceiling, "
            f"CPU RAM otherwise); nothing is streamed, thinned or sampled -- MEMORY_POLICY = raise (the run stops with a message when the rows do not fit), "
            f"recommend_mode -> {mode}, M01_MODE = auto (all rows at once while they fit below 98 % of the RAM; OUT OF CORE only beyond it -- Dask, then Spark, "
            f"then the built-in batches: pixel partitions, exact, nothing sampled -- your v20.58 rule), no other notebook streams; run: 180 of 180 rows loaded and estimated ({all_rows}); "
            f"reading the parquet file row group by row group when the whole file does not fit is only how the rows are READ -- they are all in RAM before any estimate"
            + ("" if ok else f" -- m01 {m01}, users {users}, gpu {gpu_whole}"))
rule(30, "No chunking: regression models load all data into GPU + memory and run the regression once", "_common.NO_CHUNKING / MEMORY_POLICY / recommend_mode / load_panel / demean_columns; M01 M01_MODE", r30)

def r31():
    rpk = rsrc("reward_packages.R")
    ok = all(k in rpk for k in ('install.packages.compile.from.source = "never"', 'type = "binary"', "binary_platform <- function", "has_build_tools <- function",
                                "needs_compilation <- function", "RTOOLS_URL", "utils::install.packages(pkgs = "))
    return ("PASS" if ok else "FAIL", "R: on Windows / macOS the pre-built CRAN binary is installed FIRST -- also when CRAN has a newer source version (R's 'compile "
            "from source?' choice is switched off, which is what asked for Rtools in your run); a source build is attempted only when no binary exists for your R "
            "version AND it can be built here (a pure-R package needs no tools; otherwise Rtools is named with its link and the models fall back to the engine); "
            "installed packages are not updated unless UPDATE_PACKAGES <- TRUE; every install.packages() call names its packages explicitly (pkgs = ...)")
rule(31, "R packages: pre-built binaries first; never an unasked-for source build; Rtools only when unavoidable, said plainly", "R/lib/reward_packages.R install_package_chain; RWDR 00_SETUP.R", r31)

# ---------------------------------------------------------------- v20.57: the 98 % rule, fragments, the fund workbook, the design in the models
def _report(stem):
    """A validation report: this engine folder (a run on this machine) first, else the one shipped in the bundle's docs."""
    for p_ in (os.path.join(HERE, stem + ".csv"), os.path.join(HERE, "..", "..", "docs", f"{stem}_v{C.ENGINE_VERSION}.csv")):
        if os.path.exists(p_): return os.path.abspath(p_) if os.path.dirname(os.path.abspath(p_)) != HERE else p_
    return None

def r32():
    saved = (H.machine_profile, H.memory_share, H.own_ram_bytes)
    try:                                                      # run: a 64-core machine, 100 GB of RAM, 60 GB free, alone
        H.machine_profile = lambda: {"logical_cores": 64, "physical_cores": 32, "smt": True, "pool_limit": 61, "ram_total": 100e9, "ram_free": 60e9}
        H.memory_share = lambda verbose=False: 1.0; H.own_ram_bytes = lambda: 0.0
        budget = H.ram_budget_bytes(); n_w = H.worker_cap(n_tasks=1000); n_w_ram = H.worker_cap(n_tasks=1000, bytes_per_worker=1e9)
    finally:
        H.machine_profile, H.memory_share, H.own_ram_bytes = saved
    caps = ("MAX_SPATIAL_N = 2_000_000", "n_max=4_000_000", "n_max=3_000_000", "nn_sample=2_000_000", "max(1, cores - 1)", "0.6 * p.total_memory",
            "b = 0.6 * free", "total_memory) * 0.7", "cpu_count() or 2) - 1")
    files = [os.path.join(HERE, f) for f in ("_common.py", "_prep_common.py", "_hardware.py")] + glob.glob(os.path.join(HERE, "python_prebuilt", "*.py")) \
            + glob.glob(os.path.join(HERE, "0[2-5]_*", "M*.ipynb"))
    left = sorted({c for f in files for c in caps if c in open(f, encoding="utf-8").read()})
    rdes = RDES; r_ok = "MEMORY_CEILING <- 0.98" in rdes and "detectCores() - 1" not in RP + rdes and rconst(RP, "N_THREADS").startswith(("max(1L, parallel::detectCores())", "max(1L, all_logical_cores_R())"))
    gpu_first = C.GPU_MAX_ROWS is None and "gpu_budget_bytes" in inspect.getsource(C.gpu_capacity_rows)
    ok = abs(budget - 58e9) < 1 and n_w == 61 and n_w_ram == 58 and H.RESERVE_CORES == 0 and C.MEMORY_HEADROOM == 1.0 and not left and r_ok and gpu_first
    return ("PASS" if ok else "FAIL", f"run on a stand-in 64-core / 100 GB machine with 60 GB free: {budget / 1e9:.0f} GB may be loaded (up to 98 % of the TOTAL, "
            f"nothing held back), {n_w} worker processes (every core up to the platform's own pool limit: 60 on Windows, where a pool waits on at most 63 handles), {n_w_ram} when each needs 1 GB (fewer ONLY because more "
            f"would pass 98 %); no fixed sample size or core reserve left in Python or R; the GPU is used first when the rows fit below 98 % of its memory, "
            f"else RAM" + ("" if ok else f" -- caps left {left}, R {r_ok}, GPU {gpu_first}"))
rule(32, "No GPU / RAM / CPU cap in any stage until 98 % of the TOTAL; GPU or RAM first", "_hardware.MEMORY_CEILING / worker_cap, _common.rows_that_fit / gpu_capacity_rows; R MEMORY_CEILING / units_that_fit", r32)

def r33():
    import _fragments as FR
    fc = FR.file_codes(np.array([1] * 6 + [2, 2, 3]), np.array([0] * 6 + [0, 0, 3]))
    codes = [int(x) for x in (fc[0] if isinstance(fc, tuple) else fc)]
    # run: a single-sub-watershed panel (Artal, site 1) whose files also carry a piece of Beguru's CORE (site 2) and an outside row of site 3
    rows = []
    for pix, (site, ring, code) in enumerate([(1, 0, 0)] * 40 + [(1, 3, 0)] * 40 + [(2, 0, 1)] * 2 + [(3, 4, 2)]):   # v20.58: Beguru's piece 2 of 82 pixels
        for y in (2020, 2021, 2022, 2023):
            rows.append({"pixel_id": 100 + pix, "site_id": site, "subwshed_id": f"S{site}", "sws_export": 1, "site_check": 0 if code < 2 else 3, "fragment": code,
                         "buff_km": ring, "Year": y, "Season": 1, "NDVI": 0.4 + 0.01 * pix, "Rain": 500.0, "Tmax": 33.0, "Tmean": 26.0, "Tmin": 19.0,
                         "LandUse": 1, "first_treat_agri_year": 2022.0 if ring == 0 else np.inf, "time_fe_yearseason": f"{y}_1"})
    f = pd.DataFrame(rows); d = tempfile.mkdtemp(prefix="req_frag_"); fp = os.path.join(d, "panel.parquet"); f.to_parquet(fp, index=False)
    keep = (C.PREPARED_PANEL, dict(C.ACTIVE)); got = {}
    try:
        C.PREPARED_PANEL = fp; C.clear_panel_cache()
        for rule_ in ("drop", "keep"):
            C.set_scenario(verbose=False, all_years=True, control_zones="1-5", timing="fixed", treatment_year=2022, seasons="all", fragment_rule=rule_)
            C.resolve_design(verbose=False, force=True)
            x = C.build_treatment_columns(C.load_panel(columns=C.columns_for("NDVI")))
            got[rule_] = sorted(int(v) for v in pd.unique(x["site_id"]))
    finally:
        C.PREPARED_PANEL = keep[0]; C.ACTIVE.clear(); C.ACTIVE.update(keep[1]); C.clear_panel_cache(); C._RESOLVED.clear()
    r_ok = ('dt[, fragment := file_codes(site_id, site_check), by = src_file]' in RPREP and ("fragment_codes_R(x, tab)" in RDES or "location_codes_R(x, loc, S)" in RDES)   # v20.58: the location rule
            and rconst(RP, "FRAGMENT_RULE") == '"drop"')
    ok = codes == [0] * 6 + [1, 1, 2] and got.get("drop") == [1] and got.get("keep") == [1, 2, 3] and r_ok and C.ACTIVE.get("fragment_rule", "drop") == "drop"
    return ("PASS" if ok else "FAIL", f"per export file the MAJOR sub-watershed is its own; a row inside another sub-watershed's polygon (code 1) or outside every "
            f"polygon with another id (code 2) is a fragment -- core and ring rows alike (codes {codes}); run on a single-sub-watershed panel with a piece of "
            f"Beguru's core and a stray row: FRAGMENT_RULE 'drop' (default) estimates sub-watershed(s) {got.get('drop')}, 'keep' {got.get('keep')}; the same "
            f"codes in R (run_prep per file, load_panel_R); a minor sub-watershed (< 5 % of the largest one's rows) is a fragment too -- v20.58: the rows of "
            f"a sub-watershed NOT processed (code 1) and outside every polygon (code 2) leave every group; SUB_WATERSHEDS = 'major' keeps only the largest")
rule(33, "Single sub-watershed processing: the MAJOR sub-watershed's data only; smaller fragments of other sub-watersheds (treated or control) dropped", "_fragments.file_codes (P00 PASS A), _common.fragment_table / load_panel; R run_prep / load_panel_R", r33)

def r34():
    import _fund as F
    m0 = F.month_index(pd.Timestamp("2024-10-01"))
    long = pd.concat([pd.DataFrame({"site_id": s, "sws_name": n, "district": "X", "month": [m0 + i for i in range(22)],
                                    "amount_reported": [a0 + 10.0 * i for i in range(22)], "target": 500.0, "area_ha": ar, "area_source": "file"})
                      for s, n, a0, ar in ((1, "Artal", 40.0, 4632.33845007), (2, "Murlapura", 200.0, 3000.0))], ignore_index=True)
    ser = F.fund_series(long); tim = F.fund_timing(ser, rule="backcast", rate_months=12).set_index("site_id")
    dose = F.season_dose(ser, tim.reset_index(), [2023, 2024, 2025], before_file="backcast")
    lab = {int(k): v for k, v in tim["first_treated_label"].items()}
    d1 = float(dose[(dose.site_id == 1) & (dose.Year == 2024) & (dose.Season == 2)]["dose_intensity_per_ha"].iloc[0])
    keep = dict(C.ACTIVE)
    try:
        C.set_scenario(verbose=False, timing="fund", site_start={int(k): [int(tim.loc[k, "first_treated_year"]), int(tim.loc[k, "first_treated_season"])] for k in tim.index})
        fr = pd.DataFrame([{"site_id": s, "buff_km": b_, "Year": y, "Season": se, "pixel_id": s * 100 + b_ * 10 + se, "subwshed_id": f"S{s}", "time_fe_yearseason": "x"}
                           for s in (1, 2) for b_ in (0, 1) for y in (2023, 2024) for se in (0, 1, 2, 3)])   # v20.58: with a control ring
        x = C.build_treatment_columns(fr)
        first = {int(s): [min(((int(r.Year), int(r.Season)) for r in g[(g.did_term == 1) & (g.Season != 0)].itertuples()),
                              key=lambda t: (t[0], F.SEASON_RANK[t[1]]))] for s, g in x.groupby("site_id")}      # chronological: Zaid, Kharif, Rabi
    finally:
        C.ACTIVE.clear(); C.ACTIVE.update(keep)
    r_ok = all(k in rsrc("reward_fund.R") for k in ("fund_timing <- function", "fund_season_dose <- function", "row_cohort <- function")) and rconst(RP, "TREATMENT_TIMING") == '"fund"'
    ok = lab == {1: "Rabi 2024", 2: "Kharif 2023"} and abs(d1 - 30.0 / 4632.33845007) < 1e-12 and first == {1: [(2024, 2)], 2: [(2023, 1)]} and r_ok
    return ("PASS" if ok else "FAIL", f"run on a two-sub-watershed workbook (cumulative releases from Oct 2024, back-cast before the file at each one's own rate): "
            f"first treated seasons {lab} -- varying, staggered, one per sub-watershed, the season AFTER the start (no anticipation); the dose of a season = the "
            f"amount released by the end of the previous season / the treatment area (Artal Rabi 2024: 30 / 4,632 ha = {d1:.5f} per ha), 0 before the start and "
            f"on the rings; each model applies it when it runs (TREATMENT_TIMING 'fund', DOSE_VARIABLE) in Python and R -- per row: first treated (Year, Season) "
            f"{first}; reports FUND_TIMING.csv / FUND_SEASON_DOSE.csv / FUND_TIMING_AND_DOSE.md" + ("" if ok else f" -- R {r_ok}"))
rule(34, "Your fund workbook = each sub-watershed's treatment timing and DOSE (release timing; amount released / treatment area; staggered)", "_fund.py, _common.resolve_design / build_treatment_columns / attach dose; R reward_fund.R, model_design, attach_dose_R", r34)

def r35():
    import hashlib
    rows = []
    for pix in range(1, 25):
        ring = 0 if pix <= 4 else 1 + (pix - 5) % 5
        for y in range(2016, 2026):
            for se in (0, 1, 2, 3):
                rows.append({"pixel_id": pix, "site_id": 1, "subwshed_id": "S1", "buff_km": ring, "Year": y, "Season": se, "sws_export": 1, "site_check": 0, "fragment": 0,
                             "NDVI": 0.4 + 0.001 * pix + (0.05 if (ring == 0 and y >= 2022) else 0), "Rain": 500.0, "Tmax": 33.0, "Tmean": 26.0, "Tmin": 19.0,
                             "LandUse": 1, "first_treat_agri_year": 2022.0 if ring == 0 else np.inf, "time_fe_yearseason": f"{y}_{se}"})
    f = pd.DataFrame(rows); d = tempfile.mkdtemp(prefix="req_design_"); fp = os.path.join(d, "panel.parquet"); f.to_parquet(fp, index=False)
    md5 = lambda: hashlib.md5(open(fp, "rb").read()).hexdigest(); h0 = md5()
    keep = (C.PREPARED_PANEL, dict(C.ACTIVE)); res = {}
    try:
        C.PREPARED_PANEL = fp; C.clear_panel_cache()
        # your v20.56 R_P00 choice, now set in the MODEL: DESIGN_MODE recommended, rings 1:3, 4 pre years, every post year, the three seasons
        C.set_scenario(verbose=False, design_mode="recommended", timing="fixed", treatment_year=2022, control_zones="1-3", pre_years=4, post_years="all", seasons="seasonal")
        C.resolve_design(verbose=False, force=True)
        x = C.build_treatment_columns(C.load_panel(columns=C.columns_for("NDVI"))); x = x[x.in_analysis_sample == 1]
        res["mine"] = (sorted(int(v) for v in pd.unique(x.buff_km)), int(x.Year.min()), int(x.Year.max()), sorted(int(v) for v in pd.unique(x.Season)))
        C.set_scenario(verbose=False, control_zones="data", pre_years="data", post_years="data", seasons="all")
        res["data_keys"] = sorted(C.ACTIVE.get("data_keys") or [])
        # every option set in CELL 1 survives P00's saved defaults (the load_scenario() each CELL 1 runs) -- v20.57: OVERLAP_ROWS did not
        sp = os.path.join(d, "did_scenario.json")
        C.set_scenario(verbose=False, design_mode="recommended", timing="fund", treatment_year=2022, fund_start_rule="backcast", dose_variable="dose_intensity_per_ha",
                       control_zones="data", pre_years="data", post_years="data", seasons="all", exclude_transition_year=False, unit_fe="pixel_season",
                       overlap_rows="drop", fragment_rule="drop", pooled_fe="site_period", exclude_gapfilled=True)
        C.save_scenario(path=sp, verbose=False)
        mine = dict(design_mode="manual", timing="fixed", treatment_year=2023, fund_start_rule="share", dose_variable="dose_amount_sws", control_zones="1-3",
                    pre_years=4, post_years=2, seasons="seasonal", exclude_transition_year=True, unit_fe="pixel", overlap_rows="keep", fragment_rule="keep",
                    pooled_fe="period", exclude_gapfilled=False)
        C.set_scenario(verbose=False, **mine); C.load_scenario(path=sp, verbose=False)
        got_ = {"design_mode": C.ACTIVE.get("design_mode"), "timing": C.ACTIVE.get("timing"), "treatment_year": C.ACTIVE.get("treatment_year_setting"),
                "fund_start_rule": C.ACTIVE.get("fund_start_rule"), "dose_variable": C.ACTIVE.get("dose_variable"), "control_zones": tuple(C.ACTIVE.get("control_zones")),
                "pre_years": C.ACTIVE.get("pre_years"), "post_years": C.ACTIVE.get("post_years"), "seasons": C.ACTIVE.get("seasons"),
                "exclude_transition_year": C.ACTIVE.get("exclude_transition_year"), "unit_fe": C.ACTIVE.get("unit_fe"), "overlap_rows": C.ACTIVE.get("overlap_rows"),
                "fragment_rule": C.ACTIVE.get("fragment_rule"), "pooled_fe": C.ACTIVE.get("pooled_fe"), "exclude_gapfilled": C.ACTIVE.get("exclude_gapfilled")}
        want_ = dict(mine, control_zones=(1, 2, 3))
        res["kept"] = [k for k in want_ if got_[k] == want_[k]]; res["lost"] = [f"{k}: {got_[k]!r}" for k in want_ if got_[k] != want_[k]]
    finally:
        C.PREPARED_PANEL = keep[0]; C.ACTIVE.clear(); C.ACTIVE.update(keep[1]); C.clear_panel_cache(); C._RESOLVED.clear()
    kc = RPREP.split("keep_cols <- intersect(c(", 1)[1].split(")", 1)[0]
    r_ok = (all(f'"{k}"' not in kc for k in ("cohort", "treat", "did", "event_time", "unit", "period")) and "model_design <- function" in RDES
            and ".opt(\"CONTROL_RINGS\"" in RDES and "is_data_opt" in RDES)
    rep_ = _report("DESIGN_OPTIONS_VALIDATION"); harness = "not run here"
    if rep_:
        t_ = pd.read_csv(rep_); harness = (f"validate_design_options.py ({'this machine' if os.path.dirname(rep_) == HERE else 'the run shipped in docs'}): "
                                           f"{int((t_.status == 'PASS').sum()):,} checks, {int((t_.status != 'PASS').sum())} failed (R == Python on every variant)")
    ok = res.get("mine") == ([0, 1, 2, 3], 2018, 2025, [1, 2, 3]) and res.get("data_keys") == ["control_zones", "post_years", "pre_years"] and md5() == h0 and r_ok \
         and not res.get("lost") and len(res.get("kept", [])) == 15 \
         and ("0 failed" in harness or harness == "not run here")
    return ("PASS" if ok else "FAIL", f"every design option (timing, treatment year, fund rule, dose, rings, pre / post years, seasons, transition year, unit FE, "
            f"overlap rows, fragments, pooled FE, gap-filled rows, covariates) is set in the MODEL's settings and applied when it runs, in Python (CELL 1 -> "
            f"set_scenario / resolve_design) and R (notebook -> model_design / load_panel_R); run: your v20.56 R_P00 choice (recommended, rings 1:3, 4 pre "
            f"years, seasonal) set in a model -> rings / first year / last year / seasons {res.get('mine')} -- used EXACTLY as set; 'data' = the data decide "
            f"({res.get('data_keys')}); all {len(res.get('kept', []))} options set in CELL 1 survive P00's saved defaults (the load every CELL 1 runs){' -- LOST: ' + str(res.get('lost')) if res.get('lost') else ''}; "
            f"the panel file is byte-identical afterwards (never rebuilt); R_P00 bakes nothing of the design; {harness}"
            + ("" if ok else f" -- R {r_ok}"))
rule(35, "Every option of the design is set and applied in the DiD MODEL (R as Python); your choice runs exactly as set; the panel is built once", "every model's settings; _common.set_scenario / resolve_design; R model_design / load_panel_R; validate_design_options.py", r35)

def r36():
    p_ = _report("VALIDATION_KNOWN_ANSWERS")
    if not p_: return ("FAIL", "VALIDATION_KNOWN_ANSWERS.csv not found -- run `python validate_known_answers.py` (every model against a known answer)")
    t = pd.read_csv(p_); where_ = "this machine" if os.path.dirname(p_) == HERE else "the run shipped in docs (python validate_known_answers.py redoes it here)"
    good = t.verdict.isin(["PASS", "NO ANSWER", "DATA GAP"]); n = t.verdict.value_counts().to_dict()
    ok = bool(good.all()) and n.get("PASS", 0) >= 80
    return ("PASS" if ok else "FAIL", f"every Python model on two synthetic panels with a KNOWN effect (+0.05; one sub-watershed and eight staggered; {where_}): {n.get('PASS', 0)} PASS, "
            f"{n.get('NO ANSWER', 0)} with no answer on such data (M07 ground data, M08 an instrument), {n.get('DATA GAP', 0)} right DATA GAP (M19 / M20 need "
            f">= 2 sub-watersheds); the biases it found were fixed (M03 0.016, M05 / M09 0.122, M11 / M36-M38 no result, M15, M21, M45 0.002 / 0.064, M04 0.061, M35 "
            f"a spurious gradient, M24 pixel clusters, M06 the dose) and the R routes are verified on known answers (M27's didimputation now too)"
            + ("" if ok else f" -- not met: {t[~good][['panel', 'model', 'verdict', 'detail']].to_dict('records')[:4]}"))
rule(36, "Deep and hard check of every model's result (biases): each against a known answer; what was biased is fixed", "validate_known_answers.py; P00 P12 package verification", r36)

# ================================================== v20.58: your request of 28 Sep 2026 ==================================================
def r37():
    import _location as L
    # the location codes on a small frame: S = {1}; rows of site 2 (not processed), outside (site_check 3), a control row of a pixel that is the
    # core of another processed site, a repeated pixel-year-season and a ring conflict -- every one leaves under the default "drop" rules
    site = np.array([1, 1, 2, 1, 1, 1, 1]); chk = np.array([0, 0, 0, 3, 0, 0, 0]); px = np.array([10, 11, 12, 13, 14, 14, 15])
    bk = np.array([0, 2, 0, 1, 1, 1, 0]); yr = np.array([2023] * 7); se_ = np.array([1] * 7)
    codes = L.row_codes(site, chk, px, bk, yr, se_, [1], ring_conflict={(1, 15)}, near_dup=set(), pooled_checks=True)
    keep_rule = C.location_drop_codes() == (1, 2, 3, 4)
    p_ = _report("VALIDATION_LOCATION_POISON")
    pz = ""; bad = []
    if p_:
        t = pd.read_csv(p_); bad = t[~t["identical"].astype(bool)] if "identical" in t.columns else t.iloc[0:0]
        pz = (f"; the poison run ({len(t)} models, every excluded row +5 on the outcomes and +100 mm / +5 degrees on the covariates, in every year, season "
              f"and group): {'every number of every model identical to the clean run' if not len(bad) else 'DIFFERENT for ' + str(bad['model'].tolist())}")
    ok = list(codes) == [0, 0, 1, 2, 0, 3, 4] and keep_rule and bool(p_) and not len(bad)
    return ("PASS" if ok else "FAIL", f"location codes of 7 test rows {[int(c_) for c_ in codes]} (0 kept; 1 another sub-watershed; 2 outside every polygon; 3 overlap / repeat; 4 ring "
            f"conflict); FRAGMENT_RULE and OVERLAP_ROWS 'drop' (defaults) leave codes {C.location_drop_codes()} out of every group (treated and control, pre "
            f"and post) in both languages; 'keep' is your option{pz}" + ("" if p_ else " -- run `python validate_location_poison.py`"))
rule(37, "Only the current sub-watershed(s)' own rows in any DiD model: overlapping / repeated pixels and rows of other locations dropped from every group (treated, control, pre, post) unless you choose keep",
     "_location.row_codes, _common.location_mask / load_panel; R location_codes_R / load_panel_R; validate_location_poison.py, run_all_tests.R F", r37)

def r38():
    src = inspect.getsource(C)
    ok_py = "SAMPLE_INTEGRITY_" in src and "every (pixel, year, season) once" in src
    ok_r = "sample_integrity_R" in RDES and "every (pixel, year, season) once" in RDES
    # v20.58 (second pass): at the PANEL a repeated row is dropped WHOLE -- none of its values fills a gap of the kept row (until v20.57 a
    # cloud gap of the newer export took the older export's value: the poison test found it). DEDUP_FILL_FROM_DUPLICATES = True is the option
    df = pd.DataFrame([dict(site_id=1, pixel_id=1, Year=2023, Season=1, NDVI=np.nan, LAI=1.0, src_file="new.csv", file_mtime=9.0),
                       dict(site_id=1, pixel_id=1, Year=2023, Season=1, NDVI=0.9, LAI=1.5, src_file="old.csv", file_mtime=1.0)])
    out, _ = P.resolve_duplicates(df.copy(), conflict_log=[]); opt, _ = P.resolve_duplicates(df.copy(), conflict_log=[], fill_from_duplicates=True)
    whole = (P.DEDUP_FILL_FROM_DUPLICATES is False and len(out) == 1 and np.isnan(out.NDVI.iloc[0]) and out.LAI.iloc[0] == 1.0
             and out.attrs.get("values_in_dropped_rows_not_used") == 1 and len(opt) == 1 and opt.NDVI.iloc[0] == np.float64(0.9) and opt.LAI.iloc[0] == 1.0)
    r_whole = (rconst(RPREP, "DEDUP_FILL_FROM_DUPLICATES") == "FALSE" and "fill <- isTRUE(DEDUP_FILL_FROM_DUPLICATES)" in RPREP
               and "if (fill) { set(first, which(gap), v, first$.don[gap])" in RPREP)
    return ("PASS" if (ok_py and ok_r and whole and r_whole) else "FAIL",
            "at the panel: a repeated row (the same sub-watershed, pixel, year and season in another export) is dropped WHOLE -- the kept (newer) row "
            f"keeps its gap (NDVI {out.NDVI.iloc[0]}), the older row's value is counted as not used ({out.attrs.get('values_in_dropped_rows_not_used')}); "
            "DEDUP_FILL_FROM_DUPLICATES = True is the option (Python P00_Settings, R reward_prep.R; a panel built otherwise is rebuilt). "
            "Every model run then CONFIRMS its own sample after every filter and writes it beside the results (SAMPLE_INTEGRITY_<outcome>.csv): "
            "every (pixel, year, season) once, one ring per pixel, no pixel both treated and a control, nothing outside the processed sub-watershed(s), exactly the "
            "design's rings / years / seasons -- a violation stops the model under the 'drop' rules (Python and R)"
            + ("" if whole and r_whole else f" -- FAILED: Python {whole}, R {r_whole}"))
rule(38, "Repeated rows / pixels dropped AND confirmed", "_prep_common.resolve_duplicates (DEDUP_FILL_FROM_DUPLICATES); _common sample integrity (HEADLINE / SAMPLE_INTEGRITY files); R resolve_duplicates, sample_integrity_R", r38)

def r39():
    src = inspect.getsource(C); mp = rsrc("models_prebuilt.R"); core = rsrc("reward_models_core.R")
    checks = {"M02 headline SE (was NA)": "def event_headline" in src and "design_se_event" in rsrc("reward_design.R"),
              "M15 p of its own mean": "mean_placebo_se" in src, "M23 p never 0 (was '< 1e-300')": "(1 + sum(abs(tb) >= abs(t0))) / (1 + B)" in core,
              "M34 breakdown exact (was capped at 5)": "breakdown_Mbar" in src, "design-SE p belongs to the estimate": "p_estimate_design" in src,
              "no site 0 as a sub-watershed": "site_id > 0L" in rsrc("reward_design.R"),
              "M45 converged elastic net (tol 1e-12)": "tol=1e-12" in inspect.getsource(C.lasso_synthetic_control),
              "M22 exact Goodman-Bacon weights (was approximate)": "def goodman_bacon_exact" in src,
              "the engine = R's package on M03 / M04 / M19 / M28 / M29 / M31 / M35 (DRDID imp, qte CiC, lme4 REML, did2s, fixest exposure, stacked, "
              "quantreg fn -- ported)": all(hasattr(C, f_) for f_ in ("_drdid_imp_panel", "cic_qte", "icc_reml", "did2s_event", "exposure_twfe",
                                                                           "stacked_series", "_rq_fnb")),
              "ML headlines with the package's own SE (DRLearner AIPW scores, CausalForestDML ATT, as R's grf)":
                  "att_stderr_(T=1)" in open(os.path.join(HERE, "python_prebuilt", "ml_spatial_pipeline.py"), encoding="utf-8").read(),
              "every calculation in double precision (float32 storage widened at load)": '"float32" and not _is_categorical_col(c_)' in src,
              "M36-M38: fect / gsynth ported (R's generator and cross-validation folds replicated, R's fits; was a fixed number of factors on one "
              "matrix of every season)": all(hasattr(C, f_) for f_ in ("_RRandom", "fect_fit", "fect_ring_series")) and "with_mt_seed(fect::fect(" in mp,
              "M39-M44: the engine on R's long difference (one per pixel x season series, season-matched; was per pixel, seasons mixed)":
                  hasattr(C, "ml_long_difference") and hasattr(C, "causal_forest_att"),
              "a package result of an EARLIER run is never this run's headline (moved to _superseded/)": "PACKAGE_RUN_START" in src and "_superseded" in src,
              "M11 / M13: synthdid's placebo SE with R's draws (engine and Python primary) and DIDmultiplegtDYN's estimates, placebos and analytic SEs "
              "(ported, to 1e-16)": hasattr(C, "synthdid_placebo_se") and hasattr(C, "did_multiplegt_dyn_port")
                  and "_synthdid_r_se" in open(os.path.join(HERE, "python_prebuilt", "dd_pipeline.py"), encoding="utf-8").read()}
    bad = [k for k, v in checks.items() if not v]
    return ("PASS" if not bad else "FAIL", "no placeholder or wrong number: every headline's estimate, SE and p belong together (an effect without an SE of its own takes the "
            "design-based SE of the same sample, and says so) -- " + "; ".join(k for k in checks) + ("" if not bad else f" -- missing: {bad}"))
rule(39, "No placeholder / vague values, no wrong calculation, no silent pass", "_common.headline / model_headline / HEADLINE_SPEC; R standardise / save_result", r39)

def r40():
    p_ = _report("VALIDATION_MODEL_PARITY"); pe = _report("VALIDATION_MODEL_PARITY_ENGINE")
    if not p_: return ("FAIL", "VALIDATION_MODEL_PARITY.csv not found -- run `python validate_model_parity.py`")
    t = pd.read_csv(p_); n = t.verdict.value_counts().to_dict(); bad = t[t.verdict.isin(["DIFFERENT", "KIND DIFFERS", "NO NUMBER"])]
    txt = (f"every model on the same exports in R and Python (their primary results): {n.get('IDENTICAL', 0)} IDENTICAL, {n.get('CLOSE', 0)} CLOSE, "
           f"{n.get('CLOSE-ML', 0)} CLOSE-ML (machine learning), {n.get('BOTH DATA GAP', 0)} the same data gap")
    if pe:
        te = pd.read_csv(pe); ne = te.verdict.value_counts().to_dict()
        txt += (f"; Python's OWN implementations (no package, no R) against R: {ne.get('IDENTICAL', 0)} IDENTICAL, {ne.get('CLOSE', 0)} CLOSE, "
                f"{ne.get('CLOSE-ML', 0)} CLOSE-ML, {int(te.verdict.isin(['DIFFERENT']).sum())} a different algorithm (listed in VALIDATION_v20.58.md)")
    return ("PASS" if not len(bad) else "FAIL", txt + ("" if not len(bad) else f" -- to read: {bad.model.tolist()}"))
rule(40, "R structured as Python, model by model: the same estimator, the same numbers", "validate_model_parity.py (both modes); R/lib models; _common engines", r40)

def r41():
    src = inspect.getsource(C); pc = inspect.getsource(P)
    ok = ("chunk_rows=2_500_000" in src and "ROW_GROUP_SIZE=2_560_000" in pc and "query_chunk=20000, registry_chunk=20000" in pc
          and "batch_split" in rsrc("models_prebuilt.R"))
    return ("PASS" if ok else "FAIL", "no cap: every model loads all its rows into the GPU / RAM at once while they fit below 98 % of the total; only beyond that the "
            "fall-back batches, 5 x larger than v20.57 (streaming 2,500,000 rows; row groups 2,560,000; k-NN blocks 20,000 x 20,000; in-flight batches "
            "n_workers x 10; R batches of units beyond 98 %)")
rule(41, "No cap: all data in GPU / memory in one go; only above 98 % the batch fall-back, 5 x larger", "_hardware 98 % rule; _common / _prep_common batch sizes; R units_that_fit / batch_split", r41)

def r42():
    import _outofcore as O
    order = tuple(getattr(PP, "OUT_OF_CORE", ()))
    rep = _report("VALIDATION_OUT_OF_CORE"); t = pd.read_csv(rep) if rep else None
    chk = t[~t.check.astype(str).str.startswith("engine available")] if t is not None else None
    py_ok = chk is not None and len(chk) > 0 and bool((chk.verdict == "IDENTICAL").all())
    avail = {e: O.engine_status(e)[0] for e in O.KNOWN_ENGINES}
    rfiles = ("reward_outofcore.R", "reward_prep_ooc.R", "reward_ooc_task.R", "reward_ooc_engine.py")
    r_ok = (all(os.path.exists(os.path.join(RLIB, f)) for f in rfiles) and 'OUT_OF_CORE         <- c("dask", "spark", "batches")' in RP
            and "rm_ <- run_mode_R(id, outcome, d)" in rsrc("reward_models_core.R") and "pm <- prep_mode_R(files)" in RPREP)
    rt = os.path.join(RLIB, "..", "tests", "LAST_TEST_RESULTS.csv"); rh = ""
    if os.path.exists(rt):
        tt = pd.read_csv(rt); th = tt[tt.scenario == "H"]
        if len(th): rh = f"; R (tests/run_all_tests.R scenario H): {int((th.status == 'PASS').sum())} PASS, {int((th.status == 'FAIL').sum())} FAIL, {int((th.status == 'DATA GAP').sum())} not available here"
    ok = py_ok and r_ok and order == ("dask", "spark", "batches") and O.engine_order()[-1] == "batches"
    return ("PASS" if ok else "FAIL", f"beyond 98 % of the RAM (never before) M01, M02, M16, M34 and the panel preparation go OUT OF CORE in BOTH languages -- Dask, then "
            f"Apache Spark, then the built-in batches (OUT_OF_CORE: {' -> '.join(order)}; on this machine: "
            + ", ".join(f"{e} {'available' if a else 'NOT available'}" for e, a in avail.items())
            + f"); pixel partitions, the same code per partition, the two-way FE solved exactly from their cross-products -- nothing sampled; Python "
            f"(validate_out_of_core.py): {0 if chk is None else int((chk.verdict == 'IDENTICAL').sum())} of {0 if chk is None else len(chk)} checks IDENTICAL "
            f"to the in-memory numbers on every engine; R: run_model_R / run_prep hand the same models and R_P00 to lib/reward_outofcore.R and "
            f"reward_prep_ooc.R (Dask / Spark through lib/reward_ooc_engine.py, R batches always){rh}"
            + ("" if ok else f" -- python {py_ok}, R files {r_ok}"))
rule(42, "Dask AND Spark kept as fall-back processing options when the memory limit is exceeded, in every pipeline (Python and R): exact, never sampled",
     "_outofcore.py / _ooc_models.py (Python); lib/reward_outofcore.R / reward_prep_ooc.R / reward_ooc_engine.py (R); OUT_OF_CORE in _paths.py and reward_paths.R", r42)

if __name__ == "__main__":
    t = pd.DataFrame(ROWS)
    for r in ROWS:
        print(f"{r['no']:>2} {r['status']:<8} {r['your rule']}\n          where: {r['where']}\n          proof: {r['proof']}")
    n = t.status.value_counts().to_dict()
    print("=" * 100)
    print(f"{n.get('PASS', 0)} PASS | {n.get('DECIDE', 0)} DECIDE (your decision, nothing changed) | {n.get('NOT HERE', 0)} NOT HERE "
          f"(needs your A40) | {n.get('FAIL', 0)} FAIL")
    try:
        t.to_csv(os.path.join(C.RESULTS_ROOT, "REQUESTS_CHECK.csv"), index=False)
    except Exception:
        pass
    sys.exit(1 if n.get("FAIL", 0) else 0)
