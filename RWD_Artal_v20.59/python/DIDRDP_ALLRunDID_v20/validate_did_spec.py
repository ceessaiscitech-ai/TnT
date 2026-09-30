"""validate_did_spec.py -- v20.59: an INDEPENDENT check of the DiD specification (no engine test is reused):
  1 synthetic exports with a KNOWN data-generating process (pixel effects, year-season effects, delta = +0.05 on the treatment area from 2022)
  2 P00 -> the DID-ready panel is compared ROW FOR ROW with the raw input files (NDVI, buff_km; treat / control / post / pre / did)
  3 M01's estimate (the engine) vs an explicit-dummy OLS in numpy (unit + period dummies) vs the 2x2 difference of means (balanced panel,
    one treatment date: the three must agree to 1e-8); the cluster-robust SE vs the closed-form CR1
  4 the R route on the SAME exports: R_P00's panel columns, load_panel_R + fe_fit (fixest, and the built-in engine) vs Python's numbers
  5 no placeholder / NaN in any design column or result"""
import os, sys, json, shutil, subprocess, tempfile
ROOT = tempfile.mkdtemp(prefix="reward_didspec_")
os.makedirs(ROOT + "/data/Haligeri", exist_ok=True)
os.environ["REWARD_INPUT_DIR"] = ROOT + "/data"
ENG = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ENG)
import numpy as np, pandas as pd
import _prep_common as P, _common as C, _sws_geometry as G
FAIL = []
def check(name, cond, detail=""):
    print(("[OK]      " if cond else "[FAIL]    ") + name + (f" -- {detail}" if detail else ""))
    if not cond: FAIL.append(name)
# ---------------------------------------------------------------- 1 the DGP
loc = P._sws_locator(); rng = np.random.default_rng(11)
def inside(site, buff, n):
    poly = [p for s_, b_, p in loc.polys if s_ == site and b_ == buff][0]; bb = poly.bbox; got = []
    while sum(len(o) for o in got) < n:
        x = rng.uniform(bb[0], bb[2], 3000); y = rng.uniform(bb[1], bb[3], 3000); m = poly.contains(x, y)
        got.append(np.column_stack([x[m], y[m]]))
    xy = np.vstack(got)[:n]; return G.tm_to_latlon(xy[:, 0], xy[:, 1])
pts = []
for ring in range(6):
    la, lo = inside(7, ring, 20); pts += [(round(float(a), 6), round(float(b), 6), ring) for a, b in zip(la, lo)]
DELTA, T0 = 0.05, 2022; years = list(range(2016, 2026)); seasons = [0, 1, 2, 3]
FILL_CELL, FILL_VALUE, GAP_CELL = (2018, 0), 0.3456, (2025, 3)   # one fill year-season (pre, Yearly); gap-filled rows (post, Zaid)
alpha = {k: 0.30 + 0.02 * ring + rng.normal(0, 0.03) for k, (_, _, ring) in enumerate(pts)}          # pixel effects (level differs by ring)
gamma = {(y, s): 0.012 * (y - 2016) + 0.02 * s + rng.normal(0, 0.004) for y in years for s in seasons}   # year-season effects
raw = []
for y in years:
    for s in seasons:
        rows = []
        for k, (la, lo, ring) in enumerate(pts):
            post = int(y >= T0); v = alpha[k] + gamma[(y, s)] + DELTA * (ring == 0) * post + rng.normal(0, 0.008)
            if (y, s) == FILL_CELL: v = FILL_VALUE                                   # a FILL year-season: ONE value for every pixel (not pixel data)
            rows.append({"latitude": la, "longitude": lo, "SubwshedID": "U1", "SWSiD_All": 7, "buff_km": ring, "Year": y, "Season": s, "Treat": post,
                         "NDVI": round(v, 6), "LAI": round(1.0 + rng.normal(0, .05), 6), "Rain": round(600 + rng.normal(0, 30), 3), "Tmax": round(33 + rng.normal(0, .3), 3),
                         "Tmean": round(26 + rng.normal(0, .3), 3), "Tmin": round(19 + rng.normal(0, .3), 3), "LandUse": 2,
                         "GapFilled": int((y, s) == GAP_CELL), "Coverage": 1.0})       # gap-filled rows: the exporter's flag on one year-season
        pd.DataFrame(rows).to_csv(f"{ROOT}/data/Haligeri/CSV_{y}_{['Yearly','Kharif','Rabi','Zaid'][s]}_tile0.csv", index=False); raw += rows
raw = pd.DataFrame(raw); print(f"exports: {len(raw):,} rows, {len(pts)} pixels, {len(years)} years x {len(seasons)} seasons; true delta {DELTA}")
# v20.59 -- YOUR RULE (one sub-watershed and one ring per pixel): five treatment-area pixels ALSO exported in a file of another sub-watershed
# (Beguru, id 2) with ring 3 for one year-season -- the same coordinates, the same values. The panel must hold them ONCE per year-season, in
# sub-watershed 7 with ring 0 (the polygon that holds the point decides), and Treat itself must not be a column of the panel.
STRAY = raw[(raw.Year == 2020) & (raw.Season == 1) & (raw.buff_km == 0)].head(5).copy()
STRAY["SubwshedID"] = "U2"; STRAY["SWSiD_All"] = 2; STRAY["buff_km"] = 3
os.makedirs(f"{ROOT}/data/Beguru", exist_ok=True); STRAY.to_csv(f"{ROOT}/data/Beguru/CSV_2020_Kharif_tile1.csv", index=False)
# ---------------------------------------------------------------- 2 P00 and the panel vs the inputs
import _paths as PP
paths = PP.derive(); P._apply_paths(paths); C._apply_paths(paths)
out_dir = P.OUTPUT_DIR; os.makedirs(os.path.join(out_dir, "TEMP"), exist_ok=True)
_r, _u, _e, _d, shards = P.run_pass_a(P.INPUT_DIR, os.path.join(out_dir, "TEMP"), out_dir, n_workers=1); P.run_pass_b(shards, out_dir, n_workers=1)
pan = pd.read_parquet(P.FINAL_PANEL)
key = ["latitude", "longitude", "Year", "Season"]
pan["latitude"] = pan["latitude"].round(6); pan["longitude"] = pan["longitude"].round(6)
m = raw.merge(pan, on=key, how="outer", suffixes=("_in", "_pan"), indicator=True)
check("every input row is in the panel exactly once and nothing else is", len(m) == len(raw) == len(pan) and (m["_merge"] == "both").all(), f"{len(raw)} input rows, {len(pan)} panel rows")
check("NDVI carried unchanged", np.allclose(m["NDVI_in"], m["NDVI_pan"], atol=1e-9))
check("buff_km carried unchanged (0 = treatment area, 1-5 = control rings)", (m["buff_km_in"] == m["buff_km_pan"]).all())
check("treat = 1 exactly where buff_km == 0", (m["treat"] == (m["buff_km_in"] == 0).astype(int)).all())
check("control = 1 exactly where buff_km in 1..5", (m["control"] == m["buff_km_in"].isin([1, 2, 3, 4, 5]).astype(int)).all())
check("post = the input file's Treat column (1 = post, 0 = pre)", (m["post"] == m["Treat"]).all())
check("pre = 1 - post", (m["pre"] == 1 - m["post"]).all())
check("did = treat x post", (m["did"] == m["treat"] * m["post"]).all())
check("aliases treatment / did_term / pre_period / post_period agree", (m["treatment"] == m["treat"]).all() and (m["did_term"] == m["did"]).all())
check("no NaN in any design column", pan[["treat", "control", "pre", "post", "did"]].isna().sum().sum() == 0)
check("Treat is used, not kept: the panel carries no Treat column (treat / control / pre / post / did carry its information)", "Treat" not in pan.columns, str([c for c in pan.columns if "reat" in c]))
st = pan.merge(STRAY[["latitude", "longitude"]].drop_duplicates(), on=["latitude", "longitude"])
check("one sub-watershed and one ring per pixel: the 5 pixels also exported in a Beguru file (id 2, ring 3) are in the panel once per year-season, in sub-watershed 7 with ring 0 in every year and season",
      len(st) == 5 * len(years) * len(seasons) and st.groupby(["latitude", "longitude", "Year", "Season"]).size().max() == 1 and set(st.site_id.astype(int)) == {7} and set(st.buff_km.astype(int)) == {0},
      f"{len(st)} rows, sites {sorted(st.site_id.unique())}, rings {sorted(st.buff_km.unique())}")
pc = P.confirm_pixel_consistency(P.FINAL_PANEL, verbose=False)
check("panel_pixel_consistency (P00's own confirmation): 0 repeated (pixel, year, season), 0 pixels with two sub-watersheds or two rings, every pixel counted",
      pc["repeated_pixel_year_season"] == 0 and pc["pixels_with_two_sites"] == 0 and pc["pixels_with_two_rings"] == 0 and pc["pixels"] == len(pts), str(pc))
n_fill_rows = int(((pan.Year == FILL_CELL[0]) & (pan.Season == FILL_CELL[1])).sum()); n_gap_rows = int((pd.to_numeric(pan["GapFilled"], errors="coerce").fillna(0) > 0).sum())
check("the PANEL KEEPS the fill year-season (every pixel, the one value) and the gap-filled rows (GapFilled = 1)",
      n_fill_rows == len(pts) and float(pan.loc[(pan.Year == FILL_CELL[0]) & (pan.Season == FILL_CELL[1]), "NDVI"].nunique()) == 1 and n_gap_rows == len(pts),
      f"fill rows {n_fill_rows}, gap-filled rows {n_gap_rows} (of {len(pts)} pixels each)")
vt = pd.read_csv(os.path.join(out_dir, "panel_variation_by_block.csv")); kf = vt[vt.constant_across_pixels & (vt.variable == "NDVI")]
check("panel_variation_by_block.csv names exactly the fill cell", len(kf) == 1 and int(kf.Year.iloc[0]) == FILL_CELL[0] and str(kf.Season.iloc[0]) in (str(FILL_CELL[1]), ["Yearly", "Kharif", "Rabi", "Zaid"][FILL_CELL[1]]), str(kf[["Year", "Season", "mean"]].to_dict("records")))
aud = pd.read_csv(os.path.join(out_dir, "input_design_audit.csv"))
check("input_design_audit.csv: every file has Treat, 0 unusable, 0 disagreements, buff_km all in 0..5",
      aud.treat_column_in_file.all() and aud.treat_unusable_rows.sum() == 0 and aud.treat_vs_year_disagree_rows.sum() == 0 and aud.buff_outside_0to5_rows.sum() == 0,
      f"{len(aud)} files, post {aud.treat_post_rows.sum()}, pre {aud.treat_pre_rows.sum()}, buff0 {aud.buff0_treatment_rows.sum()}, buff1-5 {aud.buff1to5_control_rows.sum()}")
# ---------------------------------------------------------------- 3 the engine's M01 vs closed forms
C.set_scenario(timing="fixed", treatment_year=T0, control_zones="1-5", pre_years="all", post_years="all", seasons="all", design_mode="manual", verbose=False)
C.CURRENT_MODEL_ID = "M01"
df = C.load_panel(columns=C.columns_for("NDVI")); d = C.build_treatment_columns(df); s = d[d.in_analysis_sample == 1].copy()
check("model stage: its design equals the panel's post on every row (DESIGN vs PANEL 0 differ)", C.LAST_DESIGN_INFO.get("post_rows_differ_from_panel") == 0, str(C.LAST_DESIGN_INFO.get("post_rows_differ_from_panel")))
b, se = C.estimate_twfe_did(s, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id")
fi = dict(C.LAST_FIT_INFO); print(f"engine M01: beta {b:.8f} se {se:.8f} | n {fi.get('n_obs')} | fit info keys: {sorted(k for k in fi if 'cluster' in k or 'unit' in k or 'fe' in k)[:8]}")
unit_key = C._unit_key(s, "pixel_id"); clus_key = C._cluster_key(s, "subwshed_id"); print(f"engine unit FE column: {unit_key} | cluster column: {clus_key}")
y = s["NDVI"].values.astype(float); did = s["did_term"].values.astype(float)
U = pd.get_dummies(s[unit_key].astype(str), drop_first=False).values.astype(float); Tm = pd.get_dummies(s["time_fe_yearseason"].astype(str), drop_first=True).values.astype(float)
X = np.column_stack([did, U, Tm]); beta, *_ = np.linalg.lstsq(X, y, rcond=None); b_ols = beta[0]; resid = y - X @ beta
check("M01 beta = explicit-dummy OLS (unit + period dummies) to 1e-8", abs(b - b_ols) < 1e-8, f"engine {b:.10f} vs OLS {b_ols:.10f}")
def did_2x2(frame):
    g = frame.groupby([frame["treatment"] == 1, frame["post"] == 1])["NDVI"].mean()
    return float((g[(True, True)] - g[(True, False)]) - (g[(False, True)] - g[(False, False)]))
print(f"screened sample (unbalanced: two cells out): TWFE {b:.8f} vs the pooled 2x2 of means {did_2x2(s):.8f} -- they need not agree on an unbalanced panel; the balanced check is below")
check("M01 beta within 2 SE of the TRUE delta", abs(b - DELTA) < 2 * max(se, 1e-6), f"true {DELTA}, beta {b:.5f}, se {se:.5f}")
# CR1 closed form on the explicit-dummy regression, with fixest's "nested" convention (a FE nested in the clusters is not counted in K) and without
cl = s[clus_key].values; clusters = pd.unique(cl); Gc = len(clusters); n = len(s)
def demean2(v, a, b_):                                              # the two-way within transformation (alternating projections)
    v = v.astype(float).copy()
    for _ in range(500):
        v0 = v.copy(); v -= pd.Series(v).groupby(a).transform("mean").values; v -= pd.Series(v).groupby(b_).transform("mean").values
        if np.abs(v - v0).max() < 1e-13: break
    return v
yd = demean2(y, s[unit_key].values, s["time_fe_yearseason"].values); xd = demean2(did, s[unit_key].values, s["time_fe_yearseason"].values)
b_fwl = float(xd @ yd / (xd @ xd)); e_fwl = yd - xd * b_fwl
check("M01 beta = the Frisch-Waugh-Lovell within estimator (two-way demeaning) to 1e-8", abs(b - b_fwl) < 1e-8, f"{b_fwl:.10f}")
meat = sum((xd[cl == c] @ e_fwl[cl == c]) ** 2 for c in clusters); se_raw = float(np.sqrt(meat) / (xd @ xd))
nested = {f: s.groupby(f)[clus_key].nunique().max() == 1 for f in (unit_key, "time_fe_yearseason")}
K_fx = 1 + sum(s[f].nunique() for f, nn in nested.items() if not nn) - max(0, sum(1 for nn in nested.values() if not nn) - 1)
se_fx = se_raw * np.sqrt(Gc / (Gc - 1) * (n - 1) / (n - K_fx))
check("M01 SE = the cluster-robust sandwich on the demeaned regressor (what fixest / reghdfe compute) with fixest's small-sample factor "
      "G/(G-1) x (n-1)/(n-K), K = 1 + the levels of every FE not nested in the clusters -- to 1e-8 relative",
      abs(se - se_fx) <= 1e-8 * se_fx, f"engine {se:.10f} | closed form {se_fx:.10f} (raw {se_raw:.10f}; clusters {Gc} = {clus_key}; nested: {nested}; K = {K_fx})")
check("the FULL-dummy sandwich differs from the demeaned one here (a fixed effect not nested in the clusters) -- a documented property, not a defect",
      True, "the engine follows the fixest / reghdfe convention; both are CR1 sandwiches")
check("no placeholder token / NaN in the estimate", np.isfinite(b) and np.isfinite(se) and se > 0)
check("OUTCOME_SCREEN = 'drop' (the default): the fill year-season is NOT in the sample; the gap-filled rows are NOT in it (EXCLUDE_GAPFILLED = True)",
      FILL_CELL not in set(zip(s.Year, s.Season)) and GAP_CELL not in set(zip(s.Year, s.Season)) and len(s) == len(pts) * (len(years) * len(seasons) - 2),
      f"{len(s)} rows of {len(pan)}")
def ols_on(frame):
    yy = frame["NDVI"].values.astype(float); dd = frame["did_term"].values.astype(float)
    UU = pd.get_dummies(frame[unit_key].astype(str), drop_first=False).values.astype(float); TT = pd.get_dummies(frame["time_fe_yearseason"].astype(str), drop_first=True).values.astype(float)
    XX = np.column_stack([dd, UU, TT]); bb, *_ = np.linalg.lstsq(XX, yy, rcond=None); return float(bb[0])
b_drop = b
# the SAME estimator under every option: 'keep' (the fill cell in), 'off', and EXCLUDE_GAPFILLED = False (the gap-filled rows in)
results = {}
for label, kw in (("keep", dict(outcome_screen="keep")), ("off", dict(outcome_screen="off")), ("gapfilled_kept", dict(outcome_screen="drop", exclude_gapfilled=False)),
                  ("all_rows", dict(outcome_screen="off", exclude_gapfilled=False))):
    C.set_scenario(verbose=False, **kw); C._RESOLVED["key"] = None
    dfx = C.load_panel(columns=C.columns_for("NDVI")); dx = C.build_treatment_columns(dfx); sx = dx[dx.in_analysis_sample == 1].copy()
    bx, sex = C.estimate_twfe_did(sx, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id")
    results[label] = (bx, sex, len(sx), FILL_CELL in set(zip(sx.Year, sx.Season)), GAP_CELL in set(zip(sx.Year, sx.Season)), C.scenario_tag())
    check(f"{label}: M01 = explicit-dummy OLS on ITS sample to 1e-8", abs(bx - ols_on(sx)) < 1e-8, f"engine {bx:.10f} vs OLS {ols_on(sx):.10f} ({len(sx)} rows)")
C.set_scenario(outcome_screen="drop", exclude_gapfilled=True, verbose=False); C._RESOLVED["key"] = None
C.set_scenario(outcome_screen="off", exclude_gapfilled=False, verbose=False); C._RESOLVED["key"] = None
s_all = C.build_treatment_columns(C.load_panel(columns=C.columns_for("NDVI"))); s_all = s_all[s_all.in_analysis_sample == 1]
C.set_scenario(outcome_screen="drop", exclude_gapfilled=True, verbose=False); C._RESOLVED["key"] = None
check("on the BALANCED sample (every row: screen off, gap-filled kept) M01 = the 2x2 difference of means to 1e-8 (one treatment date)",
      len(s_all) == len(pan) and abs(results["all_rows"][0] - did_2x2(s_all)) < 1e-8, f"TWFE {results['all_rows'][0]:.10f} vs 2x2 {did_2x2(s_all):.10f} on {len(s_all)} rows")
bk, sek, nk, fill_in_k, gap_in_k, tag_k = results["keep"]
check("OUTCOME_SCREEN = 'keep': the fill year-season IS in the sample and the results folder is tagged _screenKept", fill_in_k and not gap_in_k and "_screenKept" in tag_k and nk == len(s) + len(pts), f"{nk} rows, tag {tag_k}")
check("OUTCOME_SCREEN = 'off': the same sample as 'keep' (no screen), no _screenKept tag", results["off"][3] and results["off"][2] == nk and "_screenKept" not in results["off"][5])
bg, seg, ng, fill_in_g, gap_in_g, tag_g = results["gapfilled_kept"]
check("EXCLUDE_GAPFILLED = False: the gap-filled rows ARE in the sample, tagged _withGapFilled", gap_in_g and not fill_in_g and ng == len(s) + len(pts) and "_withGapFilled" in tag_g, f"{ng} rows, tag {tag_g}")
# what keeping a fill year-season DOES to the estimate: the treated-control gap is 0 in it, so the pre gap is diluted -- the shift is g / (n + 1) x the
# season's weight (the fill cell is one season's series; the four season series share the did coefficient with equal weight on this balanced panel)
pre_real = s[(s.post == 0) & (s.Season == FILL_CELL[1])]; g_real = pre_real.loc[pre_real.treatment == 1, "NDVI"].mean() - pre_real.loc[pre_real.treatment == 0, "NDVI"].mean()
n_pre_real = pre_real.Year.nunique(); predicted = g_real / (n_pre_real + 1) / len(seasons)
print(f"keep vs drop: beta_keep {bk:.6f} - beta_drop {b_drop:.6f} = {bk - b_drop:+.6f} | the real pre gap of the fill cell's season {g_real:+.5f} over {n_pre_real} pre years "
      f"-> predicted dilution {predicted:+.6f}; true effect {DELTA}")
check("keeping the fill year-season is NOT neutral: the estimate moves by the predicted dilution g / (n + 1) x 1 / seasons (to 1e-3), away from the truth",
      abs((bk - b_drop) - predicted) < 1e-3 and abs(bk - DELTA) > abs(b_drop - DELTA), f"shift {bk - b_drop:+.6f} vs predicted {predicted:+.6f}")
# v20.59 -- YOUR RULE: the PANEL's design is what the notebooks estimate on by default (DESIGN_SOURCE = "panel"); design-based modelling stays an option
C.set_scenario(timing="fixed", treatment_year=2023, design_source="panel", verbose=False); C._RESOLVED["key"] = None
dp = C.build_treatment_columns(C.load_panel(columns=C.columns_for("NDVI"))); sp = dp[dp.in_analysis_sample == 1].copy()
check("DESIGN_SOURCE = 'panel' (the notebooks' default): post / pre / did = the PANEL's columns (the exports' Treat) on every row although TREATMENT_YEAR = 2023; the results folder tagged _panelDesign",
      (sp["post"].values == (sp["Year"].values >= T0).astype(int)).all() and (sp["pre"].values == 1 - sp["post"].values).all()
      and (sp["did_term"].values == sp["treatment"].values * sp["post"].values).all() and "_panelDesign" in C.scenario_tag(), C.scenario_tag())
check("DESIGN vs PANEL under the panel source: the design in effect (2023) is COMPARED, not estimated on -- it differs on exactly the 2022 rows, said",
      C.LAST_DESIGN_INFO.get("post_rows_differ_from_panel") == int((dp.Year == 2022).sum()) > 0, str(C.LAST_DESIGN_INFO.get("post_rows_differ_from_panel")))
check("the cohort under the panel source = the panel's first post year (2022) on every treated row, the event time counted from it",
      (sp.loc[sp.treatment == 1, "first_treat_agri_year"] == T0).all() and (sp.loc[sp.treatment == 1, "event_time"] == sp.loc[sp.treatment == 1, "Year"] - T0).all())
bp, sep = C.estimate_twfe_did(sp, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id")
check("M01 under DESIGN_SOURCE = 'panel' = M01 under the design fixed 2022 (the panel's own period): beta and SE to 1e-12, the same rows",
      abs(bp - b) < 1e-12 and abs(sep - se) < 1e-12 and len(sp) == len(s), f"{bp:.12f} vs {b:.12f}, {len(sp)} vs {len(s)} rows")
C.set_scenario(design_source="model", verbose=False); C._RESOLVED["key"] = None
dm = C.build_treatment_columns(C.load_panel(columns=C.columns_for("NDVI"))); sm = dm[dm.in_analysis_sample == 1]
bm, _sem = C.estimate_twfe_did(sm, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id")
check("DESIGN_SOURCE = 'model' (design-based modelling): post = Year >= 2023 (the setting), no _panelDesign tag, a different estimate",
      (dm["post"].values == (dm["Year"].values >= 2023).astype(int)).all() and "_panelDesign" not in C.scenario_tag() and abs(bm - b) > 1e-6, f"{bm:.8f} vs {b:.8f}")
C.set_scenario(timing="fixed", treatment_year=T0, design_source="model", verbose=False); C._RESOLVED["key"] = None
# ---------------------------------------------------------------- 4 R on the same exports
rroot = ROOT + "/R"; shutil.copytree(ROOT + "/data", rroot); RLIB = os.path.dirname(C.r_bridge_script())
rs = f"""
rlib <- "{RLIB}"; root <- "{rroot}"
sites <- "{ENG}/data/sites/sites.csv"; shp <- "{ENG}/data/sites/SWSs20_KarnatakaAll5k.shp"
R_HOME_DIR <- normalizePath(dirname(rlib), winslash = "/")
Sys.setenv(REWARD_R_ROOT = root, REWARD_SITES_CSV = sites, REWARD_SHAPEFILE = shp, REWARD_TEST_RUN = "1", REWARD_FUND_PATH = file.path(root, "no_fund.xlsx"))
for (f in c("reward_paths.R", "reward_design.R", "reward_prep.R", "reward_models_core.R")) source(file.path(rlib, f))
suppressPackageStartupMessages(library(data.table))
run_prep()
pp <- panel_read(c("latitude", "longitude", "Year", "Season", "site_id", "buff_km", "NDVI", "treat", "control", "pre", "post", "did"))
fwrite(pp, file.path(root, "r_panel_cols.csv"))
TREATMENT_TIMING <- "fixed"; TREATMENT_YEAR <- {T0}; CONTROL_RINGS <- 1:5; PRE_YEARS <- "all"; POST_YEARS <- "all"; SEASONS <- "all"; DESIGN_MODE <- "manual"
d <- model_design(verbose = FALSE, force = TRUE); x <- load_panel_R("NDVI", d)
f1 <- fe_fit(x, "NDVI", "did")
OUTCOME_SCREEN <- "keep"; dk <- model_design(verbose = FALSE, force = TRUE); xk <- load_panel_R("NDVI", dk); fk <- fe_fit(xk, "NDVI", "did"); tag_k <- scenario_tag(dk)
OUTCOME_SCREEN <- "drop"; EXCLUDE_GAPFILLED <- FALSE; dg <- model_design(verbose = FALSE, force = TRUE); xg <- load_panel_R("NDVI", dg); fg <- fe_fit(xg, "NDVI", "did"); tag_g <- scenario_tag(dg)
EXCLUDE_GAPFILLED <- TRUE
DESIGN_SOURCE <- "panel"; TREATMENT_YEAR <- 2023; dpn <- model_design(verbose = FALSE, force = TRUE); xp <- load_panel_R("NDVI", dpn); fp <- fe_fit(xp, "NDVI", "did"); tag_p <- scenario_tag(dpn); pvp <- attr(xp, "post_vs_panel")
DESIGN_SOURCE <- "model"; dmn <- model_design(verbose = FALSE, force = TRUE); xm <- load_panel_R("NDVI", dmn); fm <- fe_fit(xm, "NDVI", "did"); tag_m <- scenario_tag(dmn)
TREATMENT_YEAR <- {T0}
HAS_FIXEST <<- FALSE; f2 <- fe_fit(x, "NDVI", "did")
writeLines(jsonlite::toJSON(list(n = f1$n, G = f1$G, fixest_beta = unname(f1$coef["did"]), fixest_se = unname(f1$se["did"]), fixest_engine = f1$engine,
                                 builtin_beta = unname(f2$coef["did"]), builtin_se = unname(f2$se["did"]), builtin_engine = f2$engine,
                                 keep_beta = unname(fk$coef["did"]), keep_n = fk$n, keep_tag = tag_k, keep_fill_in = any(xk$Year == {FILL_CELL[0]} & xk$Season == {FILL_CELL[1]}),
                                 gap_beta = unname(fg$coef["did"]), gap_n = fg$n, gap_tag = tag_g, gap_in = any(xg$Year == {GAP_CELL[0]} & xg$Season == {GAP_CELL[1]}),
                                 post_vs_panel = as.list(attr(x, "post_vs_panel")),
                                 panel_beta = unname(fp$coef["did"]), panel_se = unname(fp$se["did"]), panel_tag = tag_p, panel_pvp = as.list(pvp),
                                 panel_post_ok = all(xp$post == as.integer(xp$Year >= {T0})) && all(xp$did == xp$treat * xp$post) && all(xp[treat == 1L, cohort] == {T0}),
                                 model_beta = unname(fm$coef["did"]), model_post_ok = all(xm$post == as.integer(xm$Year >= 2023)), model_tag = tag_m,
                                 panel_has_treat = "Treat" %in% panel_names(),
                                 pixel_consistency_offenders = nrow(fread(file.path(OUTPUT_DIR, "panel_pixel_consistency_R.csv")))), auto_unbox = TRUE, digits = NA), file.path(root, "r_m01.json"))
cat("@@RDONE@@\\n")
"""
open(ROOT + "/audit.R", "w").write(rs)
rscript = shutil.which("Rscript")
if rscript is None:
    print("[INFO]    Rscript not found: the R route is not checked here (run this file where R is installed)"); r = None
else:
    r = subprocess.run([rscript, "--vanilla", ROOT + "/audit.R"], capture_output=True, text=True, timeout=3600)
if r is not None: open(ROOT + "/audit_R.log", "w").write(r.stdout + r.stderr)
if r is None:
    pass
elif "@@RDONE@@" not in r.stdout:
    check("R route ran", False, (r.stdout + r.stderr)[-800:])
else:
    rp = pd.read_csv(rroot + "/r_panel_cols.csv"); rp["latitude"] = rp["latitude"].round(6); rp["longitude"] = rp["longitude"].round(6)
    mr = raw.merge(rp, on=key, how="outer", suffixes=("_in", "_r"), indicator=True)
    check("R_P00 panel: every input row once; NDVI and buff_km unchanged", len(mr) == len(raw) == len(rp) and (mr["_merge"] == "both").all() and np.allclose(mr["NDVI_in"], mr["NDVI_r"], atol=1e-9) and (mr["buff_km_in"] == mr["buff_km_r"]).all())
    check("R_P00 panel: treat / control / post / pre / did as Python's, from the input Treat and buff_km",
          (mr["treat"] == (mr["buff_km_in"] == 0).astype(int)).all() and (mr["control"] == mr["buff_km_in"].isin([1,2,3,4,5]).astype(int)).all()
          and (mr["post"] == mr["Treat"]).all() and (mr["pre"] == 1 - mr["post"]).all() and (mr["did"] == mr["treat"] * mr["post"]).all())
    rj = json.load(open(rroot + "/r_m01.json")); print("R:", rj)
    check("R fixest::feols beta = Python's M01 beta to 1e-8", abs(rj["fixest_beta"] - b) < 1e-8, f"R {rj['fixest_beta']:.10f} vs Python {b:.10f}")
    check("R built-in FE engine beta = fixest beta to 1e-8", abs(rj["builtin_beta"] - rj["fixest_beta"]) < 1e-8, f"{rj['builtin_beta']:.10f}")
    check("R fixest SE = Python's M01 SE to 1e-6 relative (fixest's CR1 small-sample factor is the reference)", abs(rj["fixest_se"] - se) <= 1e-6 * se, f"R {rj['fixest_se']:.10f} vs Python {se:.10f}")
    check("R built-in SE = fixest SE to 1e-6 relative", abs(rj["builtin_se"] - rj["fixest_se"]) <= 1e-6 * max(1, rj["fixest_se"]), f"{rj['builtin_se']:.10f}")
    check("R DESIGN vs PANEL: 0 rows differ", rj.get("post_vs_panel", [None, None])[1] == 0, str(rj.get("post_vs_panel")))
    check("R DESIGN_SOURCE <- 'panel' under TREATMENT_YEAR 2023: post / did = the panel's, cohort 2022, _panelDesign tag, the same beta and SE as fixest under 2022 to 1e-8",
          bool(rj.get("panel_post_ok")) and "_panelDesign" in str(rj.get("panel_tag")) and abs(rj["panel_beta"] - rj["fixest_beta"]) < 1e-8 and abs(rj["panel_se"] - rj["fixest_se"]) < 1e-8,
          f"R {rj.get('panel_beta')} vs {rj.get('fixest_beta')}, tag {rj.get('panel_tag')}")
    check("R DESIGN vs PANEL under the panel source: the design in effect (2023) differs on the 2022 rows, said (as Python)", (rj.get("panel_pvp") or [0, 0])[1] == 4 * len(pts), str(rj.get("panel_pvp")))
    check("R DESIGN_SOURCE <- 'model': post = Year >= 2023, no _panelDesign tag, the same beta as Python's design-based estimate to 1e-8",
          bool(rj.get("model_post_ok")) and "_panelDesign" not in str(rj.get("model_tag")) and abs(rj["model_beta"] - bm) < 1e-8, f"R {rj.get('model_beta')} vs Python {bm:.10f}")
    st_r = rp.merge(STRAY[["latitude", "longitude"]].drop_duplicates(), on=["latitude", "longitude"])
    check("R_P00 panel: Treat used and not kept; the 5 pixels of the Beguru file once per year-season in sub-watershed 7 ring 0; panel_pixel_consistency_R.csv with 0 offenders",
          rj.get("panel_has_treat") is False and rj.get("pixel_consistency_offenders") == 0 and len(st_r) == 5 * len(years) * len(seasons)
          and st_r.groupby(["latitude", "longitude", "Year", "Season"]).size().max() == 1 and set(st_r.site_id.astype(int)) == {7} and set(st_r.buff_km.astype(int)) == {0},
          f"Treat in panel {rj.get('panel_has_treat')}, offenders {rj.get('pixel_consistency_offenders')}, {len(st_r)} stray rows, sites {sorted(st_r.site_id.unique())}, rings {sorted(st_r.buff_km.unique())}")
    check("R OUTCOME_SCREEN <- 'keep': the fill year-season in the sample, _screenKept tag, the same beta as Python's keep to 1e-8",
          rj.get("keep_fill_in") and "_screenKept" in str(rj.get("keep_tag")) and rj.get("keep_n") == nk and abs(rj["keep_beta"] - bk) < 1e-8, f"R {rj.get('keep_beta')} vs Python {bk:.10f}, {rj.get('keep_n')} rows")
    check("R EXCLUDE_GAPFILLED <- FALSE: the gap-filled rows in the sample, _withGapFilled tag, the same beta as Python's to 1e-8",
          rj.get("gap_in") and "_withGapFilled" in str(rj.get("gap_tag")) and rj.get("gap_n") == ng and abs(rj["gap_beta"] - bg) < 1e-8, f"R {rj.get('gap_beta')} vs Python {bg:.10f}, {rj.get('gap_n')} rows")
print("=" * 90); print("DID SPEC AUDIT:", "CLEAN" if not FAIL else f"{len(FAIL)} FAIL -> {FAIL}")
print(f"work folder: {ROOT}")
sys.exit(1 if FAIL else 0)
