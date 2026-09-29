"""
validate_design_options.py -- v20.57, YOUR REQUEST: every option of the design is applied at the MODEL stage, on a panel that is
built once and never rebuilt, and "the choice which I have chosen, exactly the same function is working" -- proven option by option,
in the Python engine AND in the R pipeline, on the same panel file.

One synthetic PREPARED PANEL with every feature the options act on (as P00 / R_P00 write it):
  * two sub-watersheds with their own exports (Artal = 1, Beguru = 2), core + rings 1-5, 2015-2025, the annual composite and
    Kharif / Rabi / Zaid, the annual rows without weather (filled from the seasons), 2 % missing NDVI, a fill year (2017 annual)
  * FRAGMENTS inside Artal's files: a piece of Beguru's core (inside Beguru's polygon: code 1 in the SINGLE panel, where Beguru is not
    processed; in the POOLED panel Beguru is processed and its piece is Beguru's own data, code 0 -- v20.58: the location decides, not
    the file) and points outside every polygon that kept another id (code 2); a stray file of a third sub-watershed (code 1)
  * OVERLAP: four pixels TREATED in Beguru's core that also sit in Artal's ring 5
  * history-filled rows (GapFilled = 1 / Coverage = 0)
  * a fund workbook (flat table) whose releases put Artal's first treated season in Rabi 2024 (back-cast start 2024-07) and Beguru's
    in Kharif 2023 (start 2023-04); the true effect +0.05 NDVI from those seasons on
A SINGLE panel (Artal + its fragments + the stray file: your single-sub-watershed processing) and a POOLED one (Artal + Beguru), each
also written WITHOUT the `fragment` column (a panel R_P00 / P00 wrote before v20.57: the fallback rule).

Every VARIANT sets one option (or a few) and runs the model stage of BOTH pipelines: Python set_scenario + resolve_design +
load_panel + build_treatment_columns, R model_design + load_panel_R (lib/reward_design.R design_variant_samples). Checked:
  1 R == Python: the same rows (pixel, year, season), the same treat / post / did / cohort / event time / dose, the same unit, period
    and cluster partitions
  2 the choice is what runs: the rings, years, seasons, sub-watersheds, timing (first treated season per sub-watershed), dose,
    fragments, overlap rows, gap-filled rows each match what the option says -- from the panel itself and hand-derived fund dates
  3 the panel file is byte-identical before and after all variants (no option rebuilds or changes it)
Report: DESIGN_OPTIONS_VALIDATION.csv / .md next to this file.

    python validate_design_options.py            (needs R + the lib's packages for part 1; without R, parts 2-3 run and it says so)
"""
import os, sys, json, glob, shutil, subprocess, tempfile, hashlib, time
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

def _out_sub():
    """v20.58: the output folder's name inside a data root (_paths.OUTPUT_SUBDIR -- "output"; the four-model project: "output_4Models")."""
    try:
        import _paths as _PPo
        return getattr(_PPo, "OUTPUT_SUBDIR", "output")
    except Exception:
        return "output"

sys.path.insert(0, HERE)
RHOME = os.environ.get("REWARD_R_HOME") or os.path.join(os.path.dirname(os.path.dirname(HERE)), "R")
ROWS = []
def rec(panel, variant, check, ok, detail=""):
    ROWS.append({"panel": panel, "variant": variant, "check": check, "status": "PASS" if ok else "FAIL", "detail": str(detail)[:300]})
    print(f"{'[OK]     ' if ok else '[FAILED] '} {panel:14s} {variant:26s} {check}: {str(detail)[:150]}", flush=True)

YEARS = list(range(2015, 2026)); SEASONS = (0, 1, 2, 3)
START = {1: (2024, 2), 2: (2023, 1)}          # first treated (Year, Season) by the fund file: Artal Rabi 2024, Beguru Kharif 2023
RANK = {3: 0, 1: 1, 2: 2}

def cohort_of(site, season, start):
    y, s = start
    if season == 0: return y + (1 if s == 2 else 0)
    return y + (1 if RANK[season] < RANK[s] else 0)

def make_panel(kind, seed=11, n=24):
    rng = np.random.default_rng(seed + (0 if kind == "single" else 1))
    rows = []
    def add(pid, site, buff, sws_export, check, frag, lvl_site):
        a = rng.normal(0, 0.03)
        for y in YEARS:
            for se in SEASONS:
                eff = 0.05 if (buff == 0 and site in START and y >= cohort_of(site, se, START[site])) else 0.0
                v = 0.30 + lvl_site + a + {0: 0.0, 1: 0.06, 2: 0.01, 3: -0.05}[se] + 0.006 * (y - 2015) + eff + rng.normal(0, 0.008)
                if y == 2017 and se == 0: v = 0.31                                   # a FILL year of the annual composite
                cov = (np.nan, np.nan, np.nan, np.nan) if se == 0 else (600 + rng.normal(0, 30), 33 + rng.normal(0, .3), 26 + rng.normal(0, .3), 19 + rng.normal(0, .3))
                rows.append((pid, site, buff, sws_export, check, frag, y, se, v, *cov))
    pid = 0
    sites = [1] if kind == "single" else [1, 2]
    for s in sites:
        for b in range(6):
            for i in range(n):
                pid += 1; add(s * 10000 + pid, s, b, s, 0, 0, 0.0 if s == 1 else 0.02)
    for i in range(6): add(500 + i, 2, 0, 1, 1, 1, 0.02)                           # Beguru's core inside ARTAL's files -> code 1
    for i in range(4): add(600 + i, 7, 3, 1, 3, 2, 0.0)                            # outside every polygon, another id -> code 2
    for i in range(2): add(700 + i, 9, 1, 9, 0, 0, 0.0)                            # a stray file of sub-watershed 9 -> minor site
    if kind == "pooled":                                                             # OVERLAP: Beguru's treated core in Artal's ring 5
        core2 = sorted({r[0] for r in rows if r[1] == 2 and r[2] == 0 and r[3] == 2})[:4]
        for p_ in core2:
            base = [r for r in rows if r[0] == p_]
            for r in base: rows.append((p_, 1, 5, 1, 0, 0) + r[6:])
    df = pd.DataFrame(rows, columns=["pixel_id", "site_id", "buff_km", "sws_id_export", "site_check", "fragment", "Year", "Season", "NDVI",
                                     "Rain", "Tmax", "Tmean", "Tmin"])
    df["sws_export"] = df["sws_id_export"]                                           # the R panel's name for the same column
    df.loc[rng.random(len(df)) < 0.02, "NDVI"] = np.nan                              # an unbalanced panel
    df["GapFilled"] = 0.0; df["Coverage"] = 1.0
    m = (df.Year == 2025) & (df.Season == 1) & (df.site_id == 1); idx = df.index[m]
    df.loc[idx[rng.random(len(idx)) < 0.2], "GapFilled"] = 1.0                        # history-filled rows
    m = (df.Year == 2025) & (df.Season == 2) & (df.site_id == 1); idx = df.index[m]
    df.loc[idx[rng.random(len(idx)) < 0.1], "Coverage"] = 0.0
    lab = {0: "Yearly", 1: "Kharif", 2: "Rabi", 3: "Zaid"}
    df["subwshed_id"] = "S" + df.site_id.astype(str)
    df["time_fe_yearseason"] = df.Year.astype(str) + "_" + df.Season.map(lab); df["time_fe_year"] = df.Year.astype(str)
    df["time_fe_season"] = df.Season.map(lab); df["season_sort_rank"] = df.Season.map({1: 0, 2: 1, 3: 2, 0: 3})
    df["first_treat_agri_year"] = 2026.0                                             # the v20.56 panel's milestone: must NOT be used
    df["dose_per_subwshed"] = 55.0                                                   # the v20.56 district percent: must NOT be used
    df["LandUse"] = 1.0; df["sws_name"] = df.site_id.map({1: "Artal", 2: "Beguru", 7: "Haligeri", 9: "Hunasehadagi"})
    # v20.58: pixels on a 30 m grid (3e-4 degrees apart) -- 1e-6 degrees (0.1 m) put every pixel's 30 m footprint on its neighbours', and the
    # location rule (near-duplicate pixels: footprints overlapping >= PIXEL_OVERLAP_MIN) rightly left 97 % of the rows out
    df["latitude"] = 15.0 + (df.pixel_id // 100) * 3e-4; df["longitude"] = 75.0 + (df.pixel_id % 100) * 3e-4
    for c in ("Year", "Season", "buff_km", "site_id", "sws_id_export", "sws_export", "site_check", "fragment"): df[c] = df[c].astype("int32")
    df["pixel_id"] = df["pixel_id"].astype("int64")
    return df

def write_fund(path):
    """A flat fund table: Artal a0 = 40 at 2024-10, +10 a month -> back-cast start 2024-07 (Rabi 2024 first treated); Beguru a0 = 95,
    +5 a month -> start 2023-04 (Kharif 2023). Share 10 %: Artal 2024-11 (-> Zaid 2025), Beguru on the back-cast line 2024-03 (-> Kharif
    2024). File start: both 2024-10 (-> Zaid 2025)."""
    months = pd.date_range("2024-10-01", "2026-07-01", freq="MS")
    rows = []
    for nm, a0, r, tgt, area in (("Artal", 40.0, 10.0, 500.0, 4632.33845007), ("Beguru", 95.0, 5.0, 600.0, 8779.04187878)):
        for i, m in enumerate(months): rows.append({"SWS Name": nm, "Date": m, "Progress": a0 + r * i, "Target": tgt, "Area": area})
    pd.DataFrame(rows).to_excel(path, index=False)

EXPECT_START = {"backcast": {1: (2024, 2), 2: (2023, 1)}, "share": {1: (2025, 3), 2: (2024, 1)}, "file_start": {1: (2025, 3), 2: (2025, 3)}}
EXPECT_DOSE = {("backcast", 1, 2024, 2): 30.0 / 4632.33845007,        # Rabi 2024: released by the end of Sep 2024 on the back-cast line (3 of 4 months x 40 / 4)
               ("backcast", 1, 2025, 1): 110.0 / 4632.33845007,       # Kharif 2025: by the end of May 2025 (Oct 2024 + 7 months: 40 + 70)
               ("backcast", 2, 2023, 1): 5.0 * 2 / 8779.04187878}     # Beguru Kharif 2023: by the end of May 2023 (Apr, May: 2 x 5)

BASE = {"DESIGN_MODE": "recommended", "TREATMENT_TIMING": "fund", "TREATMENT_YEAR": 2022, "FUND_START_RULE": "backcast", "FUND_DOSE_BEFORE_FILE": "backcast",
        "DOSE_VARIABLE": "dose_intensity_per_ha", "CONTROL_RINGS": "data", "PRE_YEARS": "data", "POST_YEARS": "data", "SEASONS": "all",
        "EXCLUDE_TRANSITION_YEAR": False, "UNIT_FE": "pixel_season", "OVERLAP_ROWS": "drop", "FRAGMENT_RULE": "drop", "POOLED_FE": "site_period",
        "EXCLUDE_GAPFILLED": True, "COVARIATES": ["Rain", "Tmax", "Tmean", "Tmin"]}
VARIANTS = {
    "base":                   {},
    "timing_registry":        {"TREATMENT_TIMING": "registry"},
    "timing_fixed_2022":      {"TREATMENT_TIMING": "fixed", "TREATMENT_YEAR": 2022},
    "timing_fixed_2023":      {"TREATMENT_TIMING": "fixed", "TREATMENT_YEAR": 2023},
    "fund_rule_share":        {"FUND_START_RULE": "share"},
    "fund_rule_file_start":   {"FUND_START_RULE": "file_start"},
    "dose_amount":            {"DOSE_VARIABLE": "dose_amount_sws"},
    "dose_share":             {"DOSE_VARIABLE": "dose_share_of_target"},
    "dose_before_missing":    {"FUND_DOSE_BEFORE_FILE": "missing"},
    "rings_1_3":              {"CONTROL_RINGS": [1, 2, 3]},
    "rings_2_4":              {"CONTROL_RINGS": [2, 4]},
    "pre4_post2":             {"PRE_YEARS": 4, "POST_YEARS": 2},
    "pre_all_post_all":       {"PRE_YEARS": None, "POST_YEARS": None},
    "manual_mode":            {"DESIGN_MODE": "manual"},
    "manual_rings_1_3_pre4":  {"DESIGN_MODE": "recommended", "CONTROL_RINGS": [1, 2, 3], "PRE_YEARS": 4},
    "seasons_seasonal":       {"SEASONS": "seasonal"},
    "seasons_yearly":         {"SEASONS": "yearly"},
    "seasons_rabi":           {"SEASONS": "Rabi"},
    "seasons_kharif_rabi":    {"SEASONS": ["Kharif", "Rabi"]},
    "seasons_auto":           {"SEASONS": "auto"},
    "exclude_transition":     {"EXCLUDE_TRANSITION_YEAR": True},
    "unit_fe_pixel":          {"UNIT_FE": "pixel"},
    "overlap_keep":           {"OVERLAP_ROWS": "keep"},
    "fragments_keep":         {"FRAGMENT_RULE": "keep"},
    "pooled_fe_period":       {"POOLED_FE": "period"},
    "gapfilled_kept":         {"EXCLUDE_GAPFILLED": False},
    "covariates_none":        {"COVARIATES": []},
}

def py_kwargs(o):
    cr = o["CONTROL_RINGS"]; sea = o["SEASONS"]
    return dict(design_mode=o["DESIGN_MODE"], timing=o["TREATMENT_TIMING"], treatment_year=int(o["TREATMENT_YEAR"]), fund_start_rule=o["FUND_START_RULE"],
                fund_dose_before_file=o["FUND_DOSE_BEFORE_FILE"], dose_variable=o["DOSE_VARIABLE"],
                control_zones=(cr if isinstance(cr, str) else tuple(int(x) for x in cr)),
                pre_years=("all" if o["PRE_YEARS"] is None else o["PRE_YEARS"]), post_years=("all" if o["POST_YEARS"] is None else o["POST_YEARS"]),
                seasons=("+".join(sea) if isinstance(sea, list) else sea), exclude_transition_year=bool(o["EXCLUDE_TRANSITION_YEAR"]),
                unit_fe=o["UNIT_FE"], overlap_rows=o["OVERLAP_ROWS"], fragment_rule=o["FRAGMENT_RULE"], pooled_fe=o["POOLED_FE"],
                exclude_gapfilled=bool(o["EXCLUDE_GAPFILLED"]), covariates=(list(o["COVARIATES"]) if o["COVARIATES"] else "none"),
                cluster="site", cohort_offset=0, nonnegative=False)

def py_sample(C, o):
    C.set_scenario(verbose=False, all_years=True)
    C.set_scenario(verbose=False, **py_kwargs(o))
    C.resolve_design(verbose=False, force=True)
    d = C.load_panel(columns=C.columns_for("NDVI"))
    d = C.build_treatment_columns(d)
    d = d[d["in_analysis_sample"] == 1]
    ck = C._cluster_key(d, "subwshed_id")
    tr = d["treatment"].values.astype(int)
    out = pd.DataFrame({"pixel_id": d["pixel_id"].astype("int64").values, "site_id": d["site_id"].astype(int).values, "Year": d["Year"].astype(int).values,
                        "Season": d["Season"].astype(int).values, "buff_km": d["buff_km"].astype(int).values, "treat": tr,
                        "post": d["post"].astype(int).values, "did": d["did_term"].astype(int).values,
                        "cohort": pd.to_numeric(d["first_treat_agri_year"], errors="coerce").values,
                        "event_time": np.where(tr == 1, pd.to_numeric(d["event_time"], errors="coerce").values, np.nan),
                        "dose": pd.to_numeric(d["dose"], errors="coerce").values, "unit": d["unit_id"].astype(str).values,
                        "period": d["time_fe_yearseason"].astype(str).values, "cluster_id": d[ck].astype(str).values})
    meta = {"tag": C.scenario_tag(), "control_rings": list(C.ACTIVE["control_zones"]), "window": C.scenario_years(), "drop_years": list(C.ACTIVE.get("drop_years") or []),
            "seasons": C.seasons_mode(verbose=False), "treatment_year": C.ACTIVE["treatment_year"], "site_start": dict(C.ACTIVE.get("site_start") or {}),
            "site_years": dict(C.ACTIVE.get("site_years") or {}), "choices": C.design_in_effect()}
    return out, meta

def run_r(variants, root, fund, sites_csv, out_dir):
    rs = shutil.which("Rscript")
    try:
        import _common as C
        rs = rs or C.find_rscript()
    except Exception:
        pass
    if not rs or not os.path.isdir(os.path.join(RHOME, "lib")): return None, "Rscript or the R lib not found"
    os.makedirs(out_dir, exist_ok=True)
    vf = os.path.join(out_dir, "variants.json"); json.dump(variants, open(vf, "w"))
    code = (f'R_HOME_DIR <- "{RHOME.replace(os.sep, "/")}"; for (f in c("reward_paths.R", "reward_design.R", "reward_prep.R", "reward_models_core.R")) '
            f'source(file.path(R_HOME_DIR, "lib", f)); v <- jsonlite::fromJSON("{vf.replace(os.sep, "/")}", simplifyVector = TRUE, simplifyDataFrame = FALSE); '
            f'design_variant_samples(v, "{out_dir.replace(os.sep, "/")}")')
    env = dict(os.environ, REWARD_R_ROOT=root, REWARD_FUND_PATH=fund, REWARD_SITES_CSV=sites_csv, REWARD_TEST_RUN="1", AUTO_INSTALL_PACKAGES="FALSE")
    p = subprocess.run([rs, "-e", code], capture_output=True, text=True, env=env, timeout=3600)
    return p, (p.stdout[-3000:] + p.stderr[-3000:])

def partition_equal(a, b):
    """Two labelings of the same rows define the same grouping."""
    a = pd.factorize(pd.Series(a).astype(str))[0]; b = pd.factorize(pd.Series(b).astype(str))[0]
    t = pd.DataFrame({"a": a, "b": b}).drop_duplicates()
    return t["a"].is_unique and t["b"].is_unique

def compare(panel, name, py, r):
    k = ["pixel_id", "Year", "Season", "site_id"]
    py = py.sort_values(k).reset_index(drop=True); r = r.sort_values(k).reset_index(drop=True)
    same_rows = len(py) == len(r) and (py[k].values == r[k].values).all()
    rec(panel, name, "R == Python: the same rows", same_rows, f"Python {len(py):,} rows, R {len(r):,}")
    if not same_rows:
        m = py.merge(r, on=k, how="outer", indicator=True)
        rec(panel, name, "  rows only in one", False, m["_merge"].value_counts().to_dict()); return
    for c in ("treat", "post", "did"):
        rec(panel, name, f"R == Python: {c}", bool((py[c].values == r[c].values).all()), f"{int((py[c].values != r[c].values).sum())} differ")
    rc = pd.to_numeric(r["cohort"].replace({"Inf": np.inf, "inf": np.inf}), errors="coerce").values
    pc = py["cohort"].values
    rec(panel, name, "R == Python: cohort", bool(np.all((pc == rc) | (np.isinf(pc) & np.isinf(rc)))), f"{int((~((pc == rc) | (np.isinf(pc) & np.isinf(rc)))).sum())} differ")
    re_ = pd.to_numeric(r["event_time"], errors="coerce").values; pe = py["event_time"].values; t1 = py["treat"].values == 1
    rec(panel, name, "R == Python: event time (treated)", bool(np.all(pe[t1] == re_[t1])), f"{int((pe[t1] != re_[t1]).sum())} differ")
    rd = pd.to_numeric(r["dose"], errors="coerce").values; pd_ = py["dose"].values
    okd = np.all((np.isnan(rd) & np.isnan(pd_)) | (np.abs(rd - pd_) <= 1e-9 * np.maximum(1, np.abs(pd_))))
    rec(panel, name, "R == Python: dose", bool(okd), f"max |diff| {np.nanmax(np.abs(rd - pd_)) if len(rd) else 0:.3g}")
    for c in ("unit", "period", "cluster_id"):
        rec(panel, name, f"R == Python: the {c} partition", partition_equal(py[c], r[c]), f"{py[c].nunique()} vs {r[c].nunique()} groups")

def expect(panel, name, o, py, meta, full):
    """The choice is what runs -- from the panel itself and the hand-derived fund dates."""
    s = set(py.site_id.unique()); pids = set(py.pixel_id.unique())
    # v20.58 -- the location rule judges a row by WHERE its pixel lies, not by the file it came from: 600-603 lie outside every polygon
    # (code 2) and 700-701 are a stray file of sub-watershed 9 (not processed: code 1) in every panel; 500-505 lie in Beguru's core --
    # another sub-watershed's data in the SINGLE panel (Beguru is not processed: code 1), Beguru's OWN rows in the POOLED panel (Beguru is
    # processed: code 0, kept in every group like every row inside a processed sub-watershed's polygons)
    beguru_piece = {500, 501, 502, 503, 504, 505}
    planted = {600, 601, 602, 603, 700, 701} | (beguru_piece if panel.startswith("single") else set())
    has_frag = bool(pids & planted)
    if o["FRAGMENT_RULE"] == "drop":
        rec(panel, name, "fragments left out (FRAGMENT_RULE drop)", not has_frag,
            f"planted pixels left in: {sorted(pids & planted) or 'none'}; sites in the sample {sorted(s)}")
        rec(panel, name, "only the major sub-watershed(s)", s == ({1} if panel.startswith("single") else {1, 2}), sorted(s))
        if panel.startswith("pooled"):
            rec(panel, name, "a processed sub-watershed's rows kept whatever file they came from (Beguru's piece of Artal's files)",
                beguru_piece <= pids, f"kept {sorted(beguru_piece & pids)} of {sorted(beguru_piece)}")
    else:
        rec(panel, name, "fragments kept (FRAGMENT_RULE keep)", has_frag, f"planted pixels in the sample: {sorted(pids & planted)}; sites {sorted(s)}")
    rings = set(py.loc[py.buff_km > 0, "buff_km"].unique())
    want_r = set(range(1, 6)) if o["CONTROL_RINGS"] == "data" else set(int(x) for x in o["CONTROL_RINGS"])
    rec(panel, name, "control rings = the choice", rings <= want_r and (len(rings) == len(want_r) or o["CONTROL_RINGS"] == "data"), f"used {sorted(rings)}, setting {o['CONTROL_RINGS']}")
    sea = set(py.Season.unique())
    want_s = {"all": {0, 1, 2, 3}, "seasonal": {1, 2, 3}, "yearly": {0}, "Rabi": {2}, "auto": {0, 1, 2, 3}}.get(o["SEASONS"] if isinstance(o["SEASONS"], str) else "", None)
    if isinstance(o["SEASONS"], list): want_s = {{"Kharif": 1, "Rabi": 2, "Zaid": 3}[x] for x in o["SEASONS"]}
    rec(panel, name, "seasons = the choice", sea == want_s, f"used {sorted(sea)}, setting {o['SEASONS']}")
    yrs = sorted(py.Year.unique())
    base_y = min(v[0] for v in meta["site_start"].values()) if meta["site_start"] else (min(meta["site_years"].values()) if meta["site_years"] else int(o["TREATMENT_YEAR"]))
    if o["PRE_YEARS"] == "data" and o["DESIGN_MODE"] == "recommended":
        rec(panel, name, "years: the data window without the fill year", 2017 not in yrs and yrs[0] == 2015 and yrs[-1] == 2025, f"{yrs}")
    elif isinstance(o["PRE_YEARS"], int):
        lo = base_y - o["PRE_YEARS"]; hi = (base_y + o["POST_YEARS"] - 1) if isinstance(o["POST_YEARS"], int) else 2025
        rec(panel, name, "years = PRE_YEARS / POST_YEARS from the first treated year", yrs[0] == lo and yrs[-1] == min(hi, 2025), f"{yrs[0]}..{yrs[-1]} (want {lo}..{min(hi, 2025)}; base {base_y})")
    else:
        rec(panel, name, "years: every year (the fill year's annual rows out by the screen)", yrs[0] == 2015 and yrs[-1] == 2025 and not ((py.Year == 2017) & (py.Season == 0)).any(), f"{yrs}")
    # timing: the cohort of every treated row = the hand-derived first treated season (fund) / the registry / the fixed year
    t = py[py.treat == 1]
    if o["TREATMENT_TIMING"] == "fund":
        st = EXPECT_START[o["FUND_START_RULE"]]
        exp = np.array([cohort_of(si, se, st[si]) for si, se in zip(t.site_id, t.Season)], float)
    elif o["TREATMENT_TIMING"] == "registry":
        exp = np.full(len(t), 2022.0)                                                   # data/sites/sites.csv: Artal, Beguru 2022
    else:
        exp = np.full(len(t), float(o["TREATMENT_YEAR"]))
    rec(panel, name, "timing: cohort of every treated row = the choice", bool(np.all(t.cohort.values == exp)), f"{int((t.cohort.values != exp).sum())} of {len(t):,} differ")
    post_ok = np.all(py.post.values == (py.Year.values >= np.where(py.treat.values == 1, py.cohort.values, 0)).astype(int)) if o["TREATMENT_TIMING"] != "fixed" \
        else np.all(py.post.values == (py.Year.values >= int(o["TREATMENT_YEAR"])).astype(int))
    if o["EXCLUDE_TRANSITION_YEAR"]:
        rec(panel, name, "no first treated year of a treated series", not (t.Year.values == t.cohort.values).any(), "")
    else:
        rec(panel, name, "post = Year >= the row's cohort (treated rows)", bool(np.all(t.post.values == (t.Year.values >= t.cohort.values).astype(int))), "")
    rec(panel, name, "the v20.56 milestone cohort (2026) is never used", not (t.cohort == 2026).all() or o["TREATMENT_TIMING"] == "fixed" and int(o["TREATMENT_YEAR"]) == 2026, "")
    # dose: 0 on the rings and untreated periods; the hand-derived values; the variable chosen
    ctrl0 = bool((py.loc[(py.treat == 0) | (py.post == 0), "dose"].fillna(0) == 0).all())
    rec(panel, name, "dose 0 on the control rings and untreated periods", ctrl0, "")
    if o["DOSE_VARIABLE"] != "dose_amount_sws":                                       # (an AMOUNT of 55 is a real value)
        rec(panel, name, "the v20.56 district percent (55) is never the dose", not (py.dose == 55.0).any(), "")
    if o["DOSE_VARIABLE"] == "dose_intensity_per_ha" and o["FUND_START_RULE"] == "backcast" and o["TREATMENT_TIMING"] == "fund":
        for (rule, si, y, se), v in EXPECT_DOSE.items():
            if o["FUND_DOSE_BEFORE_FILE"] == "missing" and y <= 2024 and not (y == 2024 and se == 2 and False): continue
            m = (py.site_id == si) & (py.Year == y) & (py.Season == se) & (py.treat == 1)
            if m.any(): rec(panel, name, f"dose of site {si} {y} season {se} = hand-derived", bool(np.allclose(py.loc[m, "dose"], v, rtol=1e-9)), f"{py.loc[m, 'dose'].iloc[0]:.6g} vs {v:.6g}")
    if o["DOSE_VARIABLE"] == "dose_amount_sws" and o["TREATMENT_TIMING"] == "fund":
        m = (py.site_id == 1) & (py.Year == 2025) & (py.Season == 1) & (py.treat == 1)
        if m.any(): rec(panel, name, "dose = the AMOUNT (Kharif 2025 = 110)", bool(np.allclose(py.loc[m, "dose"], 110.0)), f"{py.loc[m, 'dose'].iloc[0]:.6g}")
    if o["FUND_DOSE_BEFORE_FILE"] == "missing" and o["TREATMENT_TIMING"] == "fund":
        m = (py.site_id == 1) & (py.Year == 2024) & (py.Season == 2) & (py.treat == 1)
        rec(panel, name, "dose before the file = missing (Rabi 2024)", bool(py.loc[m, "dose"].isna().all()) if m.any() else True, "")
    # overlap (pooled): the four pixels treated in Beguru never a control in Artal's ring 5
    if panel.startswith("pooled"):
        ov = py[(py.site_id == 1) & (py.buff_km == 5) & py.pixel_id.isin(list(full.loc[(full.site_id == 2) & (full.buff_km == 0), "pixel_id"].unique()))]
        if o["OVERLAP_ROWS"] == "drop": rec(panel, name, "overlap rows left out (OVERLAP_ROWS drop)", len(ov) == 0, f"{len(ov)} rows")
        else: rec(panel, name, "overlap rows kept (OVERLAP_ROWS keep)", len(ov) > 0, f"{len(ov)} rows")
        periods = py.groupby("period").site_id.nunique().max()
        if o["POOLED_FE"] == "site_period": rec(panel, name, "period effect = sub-watershed x year x season", periods == 1, f"max sites per period {periods}")
        else: rec(panel, name, "period effect = year x season (shared)", periods == 2, f"max sites per period {periods}")
    gf = full[(full.GapFilled > 0) | (full.Coverage <= 0)][["pixel_id", "Year", "Season", "site_id"]]
    n_gf = len(py.merge(gf, on=["pixel_id", "Year", "Season", "site_id"]))
    if o["EXCLUDE_GAPFILLED"]: rec(panel, name, "history-filled rows left out", n_gf == 0, f"{n_gf}")
    else: rec(panel, name, "history-filled rows kept (EXCLUDE_GAPFILLED False)", n_gf > 0, f"{n_gf}")
    units = py.groupby("unit").Season.nunique().max()
    rec(panel, name, f"unit = {'pixel' if o['UNIT_FE'] == 'pixel' else 'pixel x season'}", (units > 1) if o["UNIT_FE"] == "pixel" and len(sea) > 1 else units == 1, f"max seasons per unit {units}")
    ch = meta["choices"]
    if len(ch):
        used = dict(zip(ch.option, ch.used))
        if o["CONTROL_RINGS"] != "data":
            rec(panel, name, "DESIGN IN EFFECT: CONTROL_ZONES used = your setting", used.get("CONTROL_ZONES") == str(sorted(int(x) for x in o["CONTROL_RINGS"])), used.get("CONTROL_ZONES"))
        rec(panel, name, "DESIGN IN EFFECT: FRAGMENT_RULE used = your setting", used.get("FRAGMENT_RULE") == o["FRAGMENT_RULE"], used.get("FRAGMENT_RULE"))

def sha(p):
    h = hashlib.sha256(); h.update(open(p, "rb").read()); return h.hexdigest()

def main():
    import _common as C
    import pyarrow as pa, pyarrow.parquet as pq
    work = tempfile.mkdtemp(prefix="design_options_")
    fund = os.path.join(work, "fund_flat.xlsx"); write_fund(fund)
    sites_csv = os.path.join(HERE, "data", "sites", "sites.csv")
    r_ok = True
    for kind, with_frag in (("single", True), ("single_v2056", False), ("pooled", True), ("pooled_v2056", False)):
        root = os.path.join(work, kind, "data"); os.makedirs(os.path.join(root, _out_sub()), exist_ok=True)
        full = make_panel("single" if kind.startswith("single") else "pooled")
        if not with_frag: full = full.drop(columns=["fragment"])
        panel = os.path.join(root, _out_sub(), "did_panel_full.parquet")
        pq.write_table(pa.Table.from_pandas(full, preserve_index=False), panel, row_group_size=50000)
        h0 = sha(panel)
        C.set_paths(input_dir=root, fund_release=fund, verbose=False); C.clear_panel_cache()
        C.SELECTED_OUTCOMES = ["NDVI"]
        names = list(VARIANTS) if kind in ("single", "pooled") else ["base", "fragments_keep", "timing_fixed_2022"]
        variants = {n: {**BASE, **VARIANTS[n]} for n in names}
        py = {}
        for n, o in variants.items():
            try:
                out, meta = py_sample(C, o); py[n] = out
                expect(kind, n, o, out, meta, full)
            except Exception as e:
                rec(kind, n, "Python model stage ran", False, f"{type(e).__name__}: {e}")
        rdir = os.path.join(work, kind, "r_out")
        p, log = run_r(variants, root, fund, sites_csv, rdir)
        if p is None:
            r_ok = False; rec(kind, "-", "R model stage available", False, log)
        else:
            for n in variants:
                j = os.path.join(rdir, n + ".json"); f = os.path.join(rdir, n + ".csv")
                if not os.path.exists(f):
                    err = json.load(open(j)).get("error") if os.path.exists(j) else log[-400:]
                    rec(kind, n, "R model stage ran", False, err); continue
                if n in py: compare(kind, n, py[n], pd.read_csv(f))
        rec(kind, "-", "the panel file is unchanged by every option (byte-identical)", sha(panel) == h0, panel)
        if not with_frag and "base" in py:
            ref = os.path.join(work, kind.replace("_v2056", ""), "py_base.csv")
            if os.path.exists(ref):
                a = pd.read_csv(ref).sort_values(["pixel_id", "Year", "Season", "site_id"]).reset_index(drop=True)
                b = py["base"].sort_values(["pixel_id", "Year", "Season", "site_id"]).reset_index(drop=True)
                rec(kind, "base", "a panel WITHOUT the fragment column (v20.56) gives the same sample", len(a) == len(b) and (a[["pixel_id", "Year", "Season", "site_id", "post", "did"]].values == b[["pixel_id", "Year", "Season", "site_id", "post", "did"]].values).all(), f"{len(a)} vs {len(b)} rows")
        if with_frag and "base" in py: py["base"].to_csv(os.path.join(work, kind, "py_base.csv"), index=False)
    t = pd.DataFrame(ROWS)
    t.to_csv(os.path.join(HERE, "DESIGN_OPTIONS_VALIDATION.csv"), index=False)
    bad = t[t.status == "FAIL"]
    md = ["# Design options at the model stage -- validation (v20.57)", "",
          f"{len(t)} checks on {t.variant.nunique() - 1} variants x 4 panels (single, pooled; each also without the fragment column): "
          f"**{(t.status == 'PASS').sum()} PASS, {len(bad)} FAIL**. R compared: {'yes' if r_ok else 'NO (R not available)'}.", "",
          "| panel | variant | check | status | detail |", "|---|---|---|---|---|"]
    md += [f"| {r.panel} | {r.variant} | {r.check} | {r.status} | {str(r.detail).replace('|', '/')[:120]} |" for r in t.itertuples()]
    open(os.path.join(HERE, "DESIGN_OPTIONS_VALIDATION.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("=" * 100); print(t.groupby(["panel", "status"]).size().to_string())
    print("CLEAN: every option does exactly what it says, in Python and R, and the panel is never rebuilt." if not len(bad)
          else f"{len(bad)} PROBLEM(S):\n" + bad.head(40).to_string(index=False))
    shutil.rmtree(work, ignore_errors=True)
    return 1 if len(bad) else 0

if __name__ == "__main__":
    sys.exit(main())
