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
alpha = {k: 0.30 + 0.02 * ring + rng.normal(0, 0.03) for k, (_, _, ring) in enumerate(pts)}          # pixel effects (level differs by ring)
gamma = {(y, s): 0.012 * (y - 2016) + 0.02 * s + rng.normal(0, 0.004) for y in years for s in seasons}   # year-season effects
raw = []
for y in years:
    for s in seasons:
        rows = []
        for k, (la, lo, ring) in enumerate(pts):
            post = int(y >= T0); v = alpha[k] + gamma[(y, s)] + DELTA * (ring == 0) * post + rng.normal(0, 0.008)
            rows.append({"latitude": la, "longitude": lo, "SubwshedID": "U1", "SWSiD_All": 7, "buff_km": ring, "Year": y, "Season": s, "Treat": post,
                         "NDVI": round(v, 6), "LAI": round(1.0 + rng.normal(0, .05), 6), "Rain": round(600 + rng.normal(0, 30), 3), "Tmax": round(33 + rng.normal(0, .3), 3),
                         "Tmean": round(26 + rng.normal(0, .3), 3), "Tmin": round(19 + rng.normal(0, .3), 3), "LandUse": 2})
        pd.DataFrame(rows).to_csv(f"{ROOT}/data/Haligeri/CSV_{y}_{['Yearly','Kharif','Rabi','Zaid'][s]}_tile0.csv", index=False); raw += rows
raw = pd.DataFrame(raw); print(f"exports: {len(raw):,} rows, {len(pts)} pixels, {len(years)} years x {len(seasons)} seasons; true delta {DELTA}")
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
g = s.groupby([s["treatment"] == 1, s["post"] == 1])["NDVI"].mean()
did22 = (g[(True, True)] - g[(True, False)]) - (g[(False, True)] - g[(False, False)])
check("M01 beta = the 2x2 difference of means (balanced panel, one treatment date) to 1e-8", abs(b - did22) < 1e-8, f"2x2 {did22:.10f}")
check("M01 beta within 2 SE of the TRUE delta", abs(b - DELTA) < 2 * max(se, 1e-6), f"true {DELTA}, beta {b:.5f}, se {se:.5f}")
# CR1 closed form on the explicit-dummy regression, with fixest's "nested" convention (a FE nested in the clusters is not counted in K) and without
cl = s[clus_key].values; clusters = pd.unique(cl); Gc = len(clusters); n, K = X.shape
def cr1(k_count):
    XtX_inv = np.linalg.inv(X.T @ X); meat = np.zeros((K, K))
    for c in clusters:
        idx = cl == c; sc = X[idx].T @ resid[idx]; meat += np.outer(sc, sc)
    V = (Gc / (Gc - 1)) * ((n - 1) / (n - k_count)) * XtX_inv @ meat @ XtX_inv; return float(np.sqrt(V[0, 0]))
nested_unit = s.groupby(unit_key)[clus_key].nunique().max() == 1
K_nested = K - (U.shape[1] - 1) if nested_unit else K            # fixest fixef.K = "nested": the nested dimension counts as one
se_full, se_nested = cr1(K), cr1(K_nested)
check("M01 SE = cluster-robust CR1 (the conventional small-sample factor, every FE counted) within 1 % -- the exact factor is fixest's (checked below to 1e-9)",
      abs(se - se_full) <= 0.01 * se_full,
      f"engine {se:.10f} | CR1 (all FE counted) {se_full:.10f} | CR1 (nested unit FE) {se_nested:.10f} | clusters {Gc} ({clus_key}), unit nested in clusters: {nested_unit}")
check("no placeholder token / NaN in the estimate", np.isfinite(b) and np.isfinite(se) and se > 0)
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
pp <- panel_read(c("latitude", "longitude", "Year", "Season", "buff_km", "NDVI", "treat", "control", "pre", "post", "did"))
fwrite(pp, file.path(root, "r_panel_cols.csv"))
TREATMENT_TIMING <- "fixed"; TREATMENT_YEAR <- {T0}; CONTROL_RINGS <- 1:5; PRE_YEARS <- "all"; POST_YEARS <- "all"; SEASONS <- "all"; DESIGN_MODE <- "manual"
d <- model_design(verbose = FALSE, force = TRUE); x <- load_panel_R("NDVI", d)
f1 <- fe_fit(x, "NDVI", "did"); HAS_FIXEST <<- FALSE; f2 <- fe_fit(x, "NDVI", "did")
writeLines(jsonlite::toJSON(list(n = f1$n, G = f1$G, fixest_beta = unname(f1$coef["did"]), fixest_se = unname(f1$se["did"]), fixest_engine = f1$engine,
                                 builtin_beta = unname(f2$coef["did"]), builtin_se = unname(f2$se["did"]), builtin_engine = f2$engine,
                                 post_vs_panel = as.list(attr(x, "post_vs_panel"))), auto_unbox = TRUE, digits = NA), file.path(root, "r_m01.json"))
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
    check("R fixest SE = Python's M01 SE to 1e-8 relative (fixest's CR1 small-sample factor is the reference)", abs(rj["fixest_se"] - se) <= 1e-8 * se, f"R {rj['fixest_se']:.10f} vs Python {se:.10f}")
    check("R built-in SE = fixest SE to 1e-6 relative", abs(rj["builtin_se"] - rj["fixest_se"]) <= 1e-6 * max(1, rj["fixest_se"]), f"{rj['builtin_se']:.10f}")
    check("R DESIGN vs PANEL: 0 rows differ", rj.get("post_vs_panel", [None, None])[1] == 0, str(rj.get("post_vs_panel")))
print("=" * 90); print("DID SPEC AUDIT:", "CLEAN" if not FAIL else f"{len(FAIL)} FAIL -> {FAIL}")
print(f"work folder: {ROOT}")
sys.exit(1 if FAIL else 0)
