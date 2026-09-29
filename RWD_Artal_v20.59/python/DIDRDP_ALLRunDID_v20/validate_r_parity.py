"""
validate_r_parity.py -- the R pipeline structures the data EXACTLY as the Python pipeline does (v20.55, your rule).

One set of synthetic exports with every feature of your real exports is written once. The Python P00 notebook runs on it
(as you run it), then the R preparation (lib/reward_prep.R: run_prep + prepare_design) on the same folder, with the same
shapefile and sites registry. Then row for row:
  * the panel: the same pixels in the same year-seasons, the same values (outcome, covariates after your rules, ring, site)
  * the design chosen from the data: pre / post years, control rings, seasons
  * the estimation sample of NDVI and EVI: the same rows, the same treat / post / did, the same values
  * the M01 estimate on that sample (R fixest vs the Python engine)

Features planted (each one is a rule of yours): two sub-watersheds (one named only by its folder), a 2025 export on a grid
shifted 3 m (pixels linked at >= PIXEL_OVERLAP_MIN), a second file for one year-season written later (the newer file
wins; its gaps filled from the older one), exact-zero outcomes and covariates (masked cells), negative rain, -9999 and the
-10 C clamp, real negative temperature (floored), history-filled and projected rows (GapFilled / Coverage), a buffer written
as "1 km", annual composites without weather (site 1), a season without a file name (columns inside the file), an .xlsx
and a .parquet export, a season present in some years only (an unbalanced panel), an outcome missing in some cells.

    python validate_r_parity.py           (needs R with the lib's packages; without R it says so and stops)
"""
import os, sys, json, glob, shutil, subprocess, tempfile, time
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
RLIB = os.path.join(os.path.dirname(os.path.dirname(HERE)), "R", "lib")
PROBLEMS, NOTES = [], []
def ok(m): NOTES.append(m); print(f"[OK]      {m}")
def bad(m): PROBLEMS.append(m); print(f"[FAILED]  {m}")


# ----------------------------------------------------------------------------------------------- the exports
def write_parity_exports(root, n_ring=20, seed=5):
    import _sws_geometry as G
    L = G.SWSLocator.from_shapefile(); rng = np.random.default_rng(seed)
    def grid_inside(site, buff, n):
        poly = [p for s_, b_, p in L.polys if s_ == site and b_ == buff][0]; bb = poly.bbox
        xs = np.arange(bb[0], bb[2], 10.0); ys = np.arange(bb[1], bb[3], 10.0)        # a 10 m grid (the export's own spacing)
        X, Y = np.meshgrid(xs, ys); X = X.ravel(); Y = Y.ravel(); m = poly.contains(X, Y)
        X, Y = X[m], Y[m]; step = max(1, len(X) // n); X, Y = X[::step][:n], Y[::step][:n]
        return G.tm_to_latlon(X, Y)
    sites = {1: ("REWARD_Artal_Exports_final", False), 7: ("REWARD_Haligeri_Exports_final", True)}   # (folder, files carry SWSiD_All)
    pix = {}
    for s in sites:
        rows = []
        for b in range(6):
            lat, lon = grid_inside(s, b, n_ring); rows += [(la, lo, b) for la, lo in zip(lat, lon)]
        pix[s] = rows
    a_pix = {s: rng.normal(0, 0.03, len(pix[s])) for s in sites}
    ty = {1: 2022, 7: 2022}
    ys = list(range(2016, 2026)); shock = {y: rng.normal(0, 0.01, 1)[0] for y in ys}
    def frame(s, y, se, shift_m=0.0, text_buff=False, cov=True, gap=None):
        P = pix[s]; n = len(P); i = np.arange(n)
        lat = np.array([p[0] for p in P]) + shift_m / 110574.0; lon = np.array([p[1] for p in P]); b = np.array([p[2] for p in P])
        eff = np.where((b == 0) & (y >= ty[s]), 0.05, 0.0)
        base = 0.30 + a_pix[s] + 0.01 * (y - 2016) + shock[y] + eff + {0: 0.0, 1: 0.05, 2: -0.02, 3: -0.06}[se] + rng.normal(0, 0.01, n)
        d = pd.DataFrame({"UID": 1000 * i + y, "latitude": lat, "longitude": lon, "buff_km": b, "Year": y, "Season": se,
                          "SubwshedID": "U1", "Treat": int(y >= ty[s]), "LandUse": 1 + (i % 3),
                          "NDVI": base, "EVI": 0.8 * base + rng.normal(0, 0.005, n), "SAVI": 0.9 * base, "LAI": 3 * base,
                          "Rain": 600 + rng.normal(0, 30, n), "Tmax": 33 + rng.normal(0, .3, n), "Tmean": 26 + rng.normal(0, .5, n), "Tmin": 19 + rng.normal(0, .3, n),
                          "GapFilled": 0, "Coverage": 1.0})
        if sites[s][1]: d["SWSiD_All"] = s
        if not cov: d[["Rain", "Tmax", "Tmean", "Tmin"]] = np.nan                                  # annual composite without weather
        if text_buff: d["buff_km"] = [f"{x} km" for x in b]
        d.loc[rng.random(n) < 0.02, "NDVI"] = np.nan                                                # an outcome missing in some cells
        if gap == "filled": d.loc[rng.random(n) < 0.3, "GapFilled"] = 1
        if gap == "projected": d.loc[rng.random(n) < 0.1, "Coverage"] = 0.0
        return d
    files = []
    for s, (folder, _) in sites.items():
        fd = os.path.join(root, folder); os.makedirs(fd, exist_ok=True)
        for y in ys:
            for se, lab in ((0, "yearly"), (1, "Kharif"), (2, "Rabi")):
                d = frame(s, y, se, shift_m=3.0 if y == 2025 else 0.0, text_buff=(s == 1 and y == 2019), cov=not (s == 1 and se == 0),
                          gap="filled" if (y == 2025 and se == 1) else ("projected" if (y == 2025 and se == 2) else None))
                if y == 2017 and se == 1: d.loc[d.index[:5], "NDVI"] = 0.0                          # masked cells written as 0
                if y == 2018 and se == 2: d.loc[d.index[:4], "Rain"] = 0.0
                if s == 7 and y == 2019 and se == 1: d.loc[d.index[:10], "Rain"] = -2.5; d.loc[d.index[10:15], "Tmin"] = -9999.0
                if s == 7 and y == 2019 and se == 2: d.loc[d.index[:5], "Tmax"] = -10.0
                if s == 7 and y == 2020 and se == 1: d.loc[d.index[:5], "Tmin"] = -3.0
                p = os.path.join(fd, f"CSV_{y}_{lab}_tile0.csv"); d.to_csv(p, index=False); files.append(p)
        # Zaid: present in some years only (an unbalanced panel), in other formats / without a key in the file name
        z = frame(s, 2019, 3); p = os.path.join(fd, "CSV_2019_Zaid_tile0.csv"); z.to_csv(p, index=False); files.append(p)
        if s == 7:
            frame(s, 2017, 3).to_excel(os.path.join(fd, "CSV_2017_Zaid_tile0.xlsx"), index=False)
            frame(s, 2018, 3).to_parquet(os.path.join(fd, "CSV_2018_Zaid_tile0.parquet"), index=False)
            frame(s, 2020, 3).to_csv(os.path.join(fd, "export_extra.csv"), index=False)              # Year / Season inside the file
    t0 = time.time() - 600
    for p in files: os.utime(p, (t0, t0))
    # the SAME year-season exported twice: the newer file (written later) wins, its gaps are filled from the older one
    fd = os.path.join(root, sites[7][0]); d2 = pd.read_csv(os.path.join(fd, "CSV_2021_Rabi_tile0.csv"))
    d2.loc[d2.index % 2 == 1, "NDVI"] = d2.loc[d2.index % 2 == 1, "NDVI"] + 0.01; d2.loc[d2.index[:20], "NDVI"] = np.nan; d2["Rain"] = d2["Rain"] + 5
    p2 = os.path.join(fd, "CSV_2021_Rabi_tile1.csv"); d2.to_csv(p2, index=False); os.utime(p2, (t0 + 100, t0 + 100))
    return root


# ----------------------------------------------------------------------------------------------- Python side
NB_RUNNER = r'''
import sys, os, json, traceback
nb = sys.argv[1]
cells = ["".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code"]
ns = {"__name__": "__main__"}
for i, src in enumerate(cells):
    src = "\n".join(l for l in src.split("\n") if not l.lstrip().startswith(("%", "!")))
    try:
        exec(compile(src, f"{os.path.basename(nb)} cell {i}", "exec"), ns)
    except SystemExit:
        pass
    except Exception as e:
        print("@@EXCEPTION@@" + json.dumps({"cell": i, "error": type(e).__name__, "msg": str(e)[:400], "tb": traceback.format_exc()[-1500:]})); sys.exit(3)
print("@@DONE@@")
'''
PY_SAMPLE = r'''
import sys, os, json, numpy as np, pandas as pd
sys.path.insert(0, sys.argv[1]); out = sys.argv[2]
import _common as C
C.load_scenario(verbose=False)
d = dict(C.ACTIVE); d["scenario_tag"] = C.scenario_tag()
json.dump({k: (list(v) if isinstance(v, (tuple, set)) else v) for k, v in d.items()}, open(os.path.join(out, "py_design.json"), "w"), default=str, indent=1)
import pyarrow.parquet as pq
pan = pq.read_table(C.PREPARED_PANEL, columns=[c for c in ["pixel_id", "latitude", "longitude", "site_id", "buff_km", "Year", "Season", "NDVI", "EVI", "Rain", "Tmax", "Tmean", "Tmin", "GapFilled", "Coverage", "LandUse"] if c in pq.ParquetFile(C.PREPARED_PANEL).schema_arrow.names]).to_pandas()
pan.to_parquet(os.path.join(out, "py_panel.parquet"), index=False)
for o in ("NDVI", "EVI"):
    x = C.load_panel(columns=C.columns_for(o)); x = C.build_treatment_columns(x); x = x[x["in_analysis_sample"] == 1]
    cols = [c for c in ["pixel_id", "latitude", "longitude", "site_id", "buff_km", "Year", "Season", "treatment", "post", "did_term", o, "Rain", "Tmax", "Tmean", "Tmin"] if c in x.columns]
    x[cols].to_parquet(os.path.join(out, f"py_sample_{o}.parquet"), index=False)
    if o == "NDVI":
        r = C.estimate_twfe_did(x, o, "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id", covariates=list(C.DEFAULT_COVARIATES), return_all=True)
        b = r[0] if isinstance(r, tuple) else r.get("beta", r.get("estimate"))
        json.dump({"beta": float(b)}, open(os.path.join(out, "py_m01.json"), "w"))
# v20.55: the season modes and the overlap option must select the SAME rows in both languages
base = dict(C.ACTIVE)
for mode in ("all", "seasonal", "yearly", "rabi", "kharif+rabi"):
    C.set_scenario(seasons=mode, verbose=False)
    x = C.load_panel(columns=C.columns_for("NDVI")); x = C.build_treatment_columns(x); x = x[x["in_analysis_sample"] == 1]
    x[["pixel_id", "Year", "Season", "treatment", "post", "did_term"]].to_parquet(os.path.join(out, f"py_mode_{mode.replace('+', '_')}.parquet"), index=False)
C.set_scenario(seasons=base["seasons"], overlap_rows="keep", verbose=False)
x = C.load_panel(columns=C.columns_for("NDVI")); x = C.build_treatment_columns(x); x = x[x["in_analysis_sample"] == 1]
x[["pixel_id", "Year", "Season", "treatment", "post", "did_term"]].to_parquet(os.path.join(out, "py_keepoverlap.parquet"), index=False)
C.set_scenario(seasons=base["seasons"], overlap_rows="drop", verbose=False)
print("@@PYDONE@@")
'''
R_SCRIPT = r'''
args <- commandArgs(trailingOnly = TRUE); rlib <- args[1]; root <- args[2]; out <- args[3]; sites <- args[4]; shp <- args[5]
R_HOME_DIR <- normalizePath(dirname(rlib), winslash = "/")
Sys.setenv(REWARD_R_ROOT = root, REWARD_SITES_CSV = sites, REWARD_SHAPEFILE = shp, REWARD_TEST_RUN = "1", REWARD_FUND_PATH = file.path(root, "no_fund.xlsx"))
for (f in c("reward_paths.R", "reward_design.R", "reward_prep.R", "reward_models_core.R")) source(file.path(rlib, f))
suppressPackageStartupMessages(library(data.table))
run_prep(); d <- prepare_design()
writeLines(jsonlite::toJSON(d, auto_unbox = TRUE, digits = NA), file.path(out, "r_design.json"))
pan <- panel_read(intersect(c("pixel_id", "latitude", "longitude", "site_id", "buff_km", "Year", "Season", "NDVI", "EVI", "Rain", "Tmax", "Tmean", "Tmin", "GapFilled", "Coverage", "LandUse"), panel_names()))
fwrite(pan, file.path(out, "r_panel.csv"))
for (o in c("NDVI", "EVI")) {
  x <- load_panel_R(o, d)
  fwrite(x[, intersect(c("pixel_id", "latitude", "longitude", "site_id", "buff_km", "Year", "Season", "treat", "post", "did", o, "Rain", "Tmax", "Tmean", "Tmin"), names(x)), with = FALSE], file.path(out, sprintf("r_sample_%s.csv", o)))
  if (o == "NDVI") { f <- fe_fit(x, o, c("did", covs_in(x))); writeLines(jsonlite::toJSON(list(beta = unname(f$coef["did"]), engine = f$engine), auto_unbox = TRUE, digits = NA), file.path(out, "r_m01.json")) }
}
for (mode in c("all", "seasonal", "yearly", "rabi", "kharif+rabi")) {                 # v20.55: the season modes select the same rows
  dm <- d; dm$seasons <- normalize_seasons(mode)
  x <- load_panel_R("NDVI", dm)
  fwrite(x[, .(pixel_id, Year, Season, treat, post, did)], file.path(out, sprintf("r_mode_%s.csv", gsub("+", "_", mode, fixed = TRUE))))
}
dk <- d; dk$overlap_rows <- "keep"; x <- load_panel_R("NDVI", dk)
fwrite(x[, .(pixel_id, Year, Season, treat, post, did)], file.path(out, "r_keepoverlap.csv"))
cat("@@RDONE@@\n")
'''


def r_pixel_to_int(s):
    """R's pixel_id 'lat5_lon5' -> Python's int64 (lat5 * 1e9 + lon5); an int already -> itself."""
    s = pd.Series(s).astype(str)
    if s.str.contains("_").any():
        a = s.str.split("_", expand=True); return a[0].astype("int64") * np.int64(10 ** 9) + a[1].astype("int64")
    return pd.to_numeric(s, errors="coerce").astype("int64")


def compare_frames(py, r, keys, vals, label, tol=1e-6):
    """Same rows (by keys) and the same values (finite where finite, equal within tol -- relative AND absolute, because the
    Python panel stores covariates as float32 (its memory rule) while R keeps double; missing where missing)."""
    m = py.merge(r, on=keys, how="outer", suffixes=("_py", "_r"), indicator=True)
    only_py = int((m["_merge"] == "left_only").sum()); only_r = int((m["_merge"] == "right_only").sum())
    both = m[m["_merge"] == "both"]
    diffs = {}
    for v in vals:
        a = pd.to_numeric(both.get(v + "_py"), errors="coerce"); b = pd.to_numeric(both.get(v + "_r"), errors="coerce")
        if a is None or b is None: continue
        fa, fb = np.isfinite(a.values.astype(float)), np.isfinite(b.values.astype(float))
        av, bv = a.values.astype(float), b.values.astype(float)
        n_pat = int((fa != fb).sum()); n_val = int((fa & fb & ~np.isclose(av, bv, rtol=tol, atol=tol, equal_nan=True)).sum())
        if n_pat or n_val: diffs[v] = f"{n_pat} missing-pattern, {n_val} value"
    if only_py or only_r or diffs:
        bad(f"{label}: rows only in Python {only_py:,}, only in R {only_r:,}, both {len(both):,}; value differences {diffs or 'none'}")
        return m
    ok(f"{label}: {len(both):,} rows identical (keys {keys}; values {vals})")
    return m


def main():
    rscript = shutil.which("Rscript")
    if not rscript:
        import _common as C
        rscript = C.find_rscript()
    if not rscript:
        print("[INFO]    R is not installed here: the parity check runs on a machine with R (RWDR's packages)"); return 0
    root = tempfile.mkdtemp(prefix="reward_parity_in_"); out = tempfile.mkdtemp(prefix="reward_parity_out_")
    write_parity_exports(root); print(f"[INFO]    exports written to {root}")
    # ---- Python: the P00 notebook as you run it, then the estimation samples
    nb = sorted(glob.glob(os.path.join(HERE, "01_Panel_Preparation", "P00_*.ipynb")))[0]
    env = dict(os.environ); env["REWARD_INPUT_DIR"] = root
    env["PYTHONPATH"] = os.pathsep.join(p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p and os.path.abspath(p) != HERE)
    r = subprocess.run([sys.executable, "-c", NB_RUNNER, nb], cwd=os.path.dirname(nb), capture_output=True, text=True, timeout=1800, env=env)
    if "@@DONE@@" not in r.stdout:
        bad("Python P00 did not finish: " + (r.stdout + r.stderr)[-1200:]); return finish(root, out)
    open(os.path.join(out, "py_p00.log"), "w").write(r.stdout + r.stderr)
    r = subprocess.run([sys.executable, "-c", PY_SAMPLE, HERE, out], cwd=HERE, capture_output=True, text=True, timeout=1800, env=env)
    if "@@PYDONE@@" not in r.stdout:
        bad("Python sample export failed: " + (r.stdout + r.stderr)[-1500:]); return finish(root, out)
    # ---- R: run_prep + the design + the samples, on a COPY of the same exports (file times kept), the same shapefile and registry
    root_r = tempfile.mkdtemp(prefix="reward_parity_in_R_"); shutil.rmtree(root_r)
    shutil.copytree(root, root_r, ignore=shutil.ignore_patterns("output", _out_sub()))          # copy2 keeps the modification times the rules use
    sites = os.path.join(HERE, "data", "sites", "sites.csv"); shp = os.path.join(HERE, "data", "sites", "SWSs20_KarnatakaAll5k.shp")
    rs = os.path.join(out, "parity.R"); open(rs, "w").write(R_SCRIPT)
    r = subprocess.run([rscript, "--vanilla", rs, RLIB, root_r, out, sites, shp], capture_output=True, text=True, timeout=3600)
    open(os.path.join(out, "r_prep.log"), "w").write(r.stdout + r.stderr)
    if "@@RDONE@@" not in r.stdout:
        bad("R preparation failed: " + (r.stdout + r.stderr)[-1500:]); return finish(root, out)
    # ---- the design
    pyd = json.load(open(os.path.join(out, "py_design.json"))); rd = json.load(open(os.path.join(out, "r_design.json")))
    T_ = int(pyd.get("treatment_year") or 2022)
    # v20.57: both keep the window the design RESOLVED -- the first and last year used (Python: year_min / year_max, or counts from the
    # start; R: year_min / year_max) and the fill years left out -- compared as years, whichever way each pipeline stores them
    def _y(v):
        try: return None if v is None or (isinstance(v, float) and np.isnan(v)) or str(v) in ("NA", "null", "") else int(v)
        except Exception: return None
    py_lo = _y(pyd.get("year_min")) if _y(pyd.get("year_min")) is not None else (T_ - int(pyd["pre_years"]) if pyd.get("pre_years") else None)
    py_hi = _y(pyd.get("year_max")) if _y(pyd.get("year_max")) is not None else (T_ + int(pyd["post_years"]) - 1 if pyd.get("post_years") else None)
    r_lo, r_hi = _y(rd.get("year_min")), _y(rd.get("year_max"))
    py_drop = sorted(int(x) for x in (pyd.get("drop_years") or [])); r_drop = rd.get("drop_years") or []
    r_drop = sorted(int(x) for x in (r_drop if isinstance(r_drop, list) else [r_drop]))
    py_rings = list(pyd.get("control_zones", [])); r_rings = rd.get("control_rings", [])
    r_rings = r_rings if isinstance(r_rings, list) else [r_rings]
    same = ((py_lo, py_hi) == (r_lo, r_hi) and py_drop == r_drop and int(pyd.get("treatment_year") or 0) == int(rd.get("treatment_year") or 0)
            and list(map(int, py_rings)) == list(map(int, r_rings)) and str(pyd.get("seasons")) == str(rd.get("seasons")))
    (ok if same else bad)(f"design from the data: Python years {py_lo}-{py_hi} (fill years out {py_drop}) rings {py_rings} seasons {pyd.get('seasons')} start {pyd.get('treatment_year')} | "
                          f"R years {r_lo}-{r_hi} (fill years out {r_drop}) rings {r_rings} seasons {rd.get('seasons')} start {rd.get('treatment_year')}")
    # ---- the panel
    pp = pd.read_parquet(os.path.join(out, "py_panel.parquet")); rp = pd.read_csv(os.path.join(out, "r_panel.csv"))
    rp["pixel_id"] = r_pixel_to_int(rp["pixel_id"]); pp["pixel_id"] = pp["pixel_id"].astype("int64")
    for f_ in (pp, rp):
        f_["Year"] = f_["Year"].astype(int); f_["Season"] = f_["Season"].astype(int)
    keys = ["pixel_id", "Year", "Season"]
    vals = [c for c in ["NDVI", "EVI", "Rain", "Tmax", "Tmean", "Tmin", "buff_km", "site_id", "LandUse"] if c in pp.columns and c in rp.columns]
    compare_frames(pp, rp, keys, vals, "panel (every pixel x year x season)")
    ps = pp.groupby(["Year", "Season"]).pixel_id.nunique(); rs_ = rp.groupby(["Year", "Season"]).pixel_id.nunique()
    if not ps.equals(rs_): bad("pixels per year-season differ: " + str(pd.concat([ps.rename("py"), rs_.rename("r")], axis=1).query("py != r").head(12).to_dict()))
    else: ok(f"pixels per year-season identical over {len(ps)} year-seasons ({int(pp.pixel_id.nunique()):,} pixels)")
    # ---- the estimation samples
    for o in ("NDVI", "EVI"):
        a = pd.read_parquet(os.path.join(out, f"py_sample_{o}.parquet")); b = pd.read_csv(os.path.join(out, f"r_sample_{o}.csv"))
        b["pixel_id"] = r_pixel_to_int(b["pixel_id"]); a["pixel_id"] = a["pixel_id"].astype("int64")
        a = a.rename(columns={"treatment": "treat", "did_term": "did"})
        for f_ in (a, b):
            f_["Year"] = f_["Year"].astype(int); f_["Season"] = f_["Season"].astype(int)
        compare_frames(a, b, keys, [c for c in ["treat", "post", "did", o, "Rain", "Tmax", "Tmean", "Tmin", "site_id"] if c in a.columns and c in b.columns],
                       f"estimation sample of {o}")
    # ---- the unbalanced panel (v20.55): a missing outcome cell leaves ONLY that estimation -- the pixel's other periods stay,
    #      and the other outcome (EVI, complete) keeps the cell. Checked on both languages' samples.
    try:
        pyN = pd.read_parquet(os.path.join(out, "py_sample_NDVI.parquet")); pyE = pd.read_parquet(os.path.join(out, "py_sample_EVI.parquet"))
        rN = pd.read_csv(os.path.join(out, "r_sample_NDVI.csv")); rE = pd.read_csv(os.path.join(out, "r_sample_EVI.csv"))
        for nm, aN, aE in (("Python", pyN, pyE), ("R", rN, rE)):
            kN = set(zip(aN.pixel_id.astype(str), aN.Year.astype(int), aN.Season.astype(int))); kE = set(zip(aE.pixel_id.astype(str), aE.Year.astype(int), aE.Season.astype(int)))
            only_e = kE - kN                                                    # cells EVI has and NDVI lacks = NDVI missing there
            pix_gap = {k[0] for k in only_e}; pix_in_n = set(aN.pixel_id.astype(str))
            kept = len(pix_gap & pix_in_n); ncell = len(only_e)
            (ok if (ncell > 0 and kept == len(pix_gap) and not (kN - kE)) else bad)(
                f"{nm}: unbalanced panel -- {ncell:,} cells with NDVI missing leave the NDVI estimation only; all {len(pix_gap):,} pixels concerned keep their "
                f"other periods ({kept:,} present in the NDVI sample); the EVI sample keeps every cell (cells only in NDVI: {len(kN - kE)})")
    except Exception as e:
        bad(f"unbalanced-panel check failed: {e}")
    # ---- the season modes and the overlap option (v20.55): the same rows in both languages
    for mode in ("all", "seasonal", "yearly", "rabi", "kharif_rabi", "keepoverlap"):
        fa = os.path.join(out, f"py_mode_{mode}.parquet" if mode != "keepoverlap" else "py_keepoverlap.parquet")
        fb = os.path.join(out, f"r_mode_{mode}.csv" if mode != "keepoverlap" else "r_keepoverlap.csv")
        if not (os.path.exists(fa) and os.path.exists(fb)):
            bad(f"season mode / overlap option '{mode}': a side did not write its rows"); continue
        a = pd.read_parquet(fa).rename(columns={"treatment": "treat", "did_term": "did"}); b = pd.read_csv(fb)
        b["pixel_id"] = r_pixel_to_int(b["pixel_id"]); a["pixel_id"] = a["pixel_id"].astype("int64")
        for f_ in (a, b):
            f_["Year"] = f_["Year"].astype(int); f_["Season"] = f_["Season"].astype(int)
        seas = sorted(a.Season.unique().tolist())
        compare_frames(a, b, keys, ["treat", "post", "did"], f"rows selected with {'OVERLAP_ROWS = keep' if mode == 'keepoverlap' else 'SEASONS = ' + mode} (seasons in the sample: {seas})")
    # ---- M01 on the sample
    try:
        pb = json.load(open(os.path.join(out, "py_m01.json")))["beta"]; rb = json.load(open(os.path.join(out, "r_m01.json")))["beta"]
        (ok if abs(pb - rb) < 1e-6 else bad)(f"M01 (TWFE, four covariates) on the NDVI sample: Python engine {pb:.8f}, R fixest {rb:.8f}")
    except Exception as e:
        bad(f"M01 comparison failed: {e}")
    return finish(root, out)


def finish(root, out):
    print("=" * 100)
    print(f"logs and samples: {out}")
    if PROBLEMS:
        print(f"{len(PROBLEMS)} DIFFERENCE(S) between the Python and the R data structuring:")
        for p in PROBLEMS: print("  -", p)
        return 1
    print(f"CLEAN: the R pipeline structures the data exactly as the Python pipeline does ({len(NOTES)} checks)."); return 0


if __name__ == "__main__":
    sys.exit(main())
