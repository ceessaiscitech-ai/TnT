"""
validate_location_poison.py -- v20.58: PROOF that no excluded row reaches any model (your rule: only the current sub-watershed's own rows,
your rings, your years, your seasons -- never an overlapping, repeated or other-location pixel, in any group: treated or control, pre or post).

Your Koranahalli layout is rebuilt from the shapefile (as R's tests/run_all_tests.R scenario F): NAMED full exports
(CSV_Koranahalli_<year>_<season>) and UNNAMED tiles that repeat the same pixels (older files), pixels OUTSIDE every polygon in both, a piece of
Kodihalli's CORE in the tiles, three ring-1 pixels the named files call "core" from 2023 (their ring flips between exports), a 2025 grid
shifted 3 m, LSWI = NDMI and WSSI = 1 - ESI (as in your exports), the four seasons, a fund workbook (the treatment timing: Rabi 2024).
The design is yours: CONTROL_ZONES 1-3, PRE_YEARS 4, SEASONS "seasonal", the location rule "drop".

The data are written TWICE with the same random numbers: CLEAN, and POISONED -- every row the design must leave out carries +5 on the
outcomes and +100 mm / +5 degrees on the covariates, in every year, season and group (rings 4-5, every ring before the window, the annual
composite of every ring, the flipping pixels in all their rows, the repeated tiles, the outside pixels, Kodihalli). P00 builds each panel, then EVERY model notebook runs on both. Every number every model writes must be IDENTICAL in the
two runs (a single excluded row that reaches an estimator moves it by up to +5), and the effect models must find the truth (+0.05).

    python validate_location_poison.py            (all 45 models; ~30-60 min)
    python validate_location_poison.py M01 M17    (a subset)
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
TRUE = 0.05
LOOSE = {"M04", "M13", "M35", "M36", "M37", "M38", "M39", "M40", "M41", "M42", "M43", "M44", "M45"}   # distributional / ML: +-0.02
SETTINGS = dict(design_mode="recommended", timing="fund", control_zones="1-3", pre_years=4, post_years="all", seasons="seasonal",
                overlap_rows="drop", fragment_rule="drop", pooled_fe="site_period", sub_watersheds="data", unit_fe="pixel_season", covariates="all")


# ----------------------------------------------------------------------------------------------- the exports
def _points_in(L, site, buff, n, rng):
    poly = [p for s_, b_, p in L.polys if s_ == site and b_ == buff][0]; bb = poly.bbox; out = []
    while sum(len(o) for o in out) < n:
        x = rng.uniform(bb[0], bb[2], 4 * n); y = rng.uniform(bb[1], bb[3], 4 * n); m = poly.contains(x, y)
        out.append(np.column_stack([x[m], y[m]]))
    return np.vstack(out)[:n]

def _points_outside(L, site, n, rng, margin=1500.0):
    bx0, by0, bx1, by1 = L.site_bbox[site]; out = []
    while sum(len(o) for o in out) < n:
        x = rng.uniform(bx0 - margin, bx1 + margin, 20 * n); y = rng.uniform(by0 - margin, by1 + margin, 20 * n)
        near = (x < bx0) | (x > bx1) | (y < by0) | (y > by1)                         # beyond the zone's box, within 1.5 km of it
        inside_any = np.zeros(len(x), bool)
        for _, _, p in L.polys: inside_any |= p.contains(x, y)
        m = near & ~inside_any
        out.append(np.column_stack([x[m], y[m]]))
    return np.vstack(out)[:n]

def make_exports(root, poison, seed=58):
    """The layout of scenario F. Returns the fund workbook's path."""
    import _sws_geometry as G
    shutil.rmtree(root, ignore_errors=True); os.makedirs(root)
    L = G.SWSLocator.from_shapefile(); rng = np.random.default_rng(seed); P5 = 5.0 if poison else 0.0
    def pix(site, n, rings, kind):
        rows = []
        for r in rings:
            xy = _points_in(L, site, r, n, rng); la, lo = G.tm_to_latlon(xy[:, 0], xy[:, 1])
            rows.append(pd.DataFrame({"buff_km": r, "latitude": la, "longitude": lo, "a": rng.normal(0, 0.03, n), "kind": kind}))
        return pd.concat(rows, ignore_index=True)
    K = pix(13, 40, range(6), "own")                                           # Koranahalli: core + rings 1-5
    K.loc[K.index[K.buff_km == 1][:3], "kind"] = "flip"                        # three ring-1 pixels the named files call core from 2023
    K.loc[K.index[K.buff_km == 0][:2], "kind"] = "shift"                       # two core pixels on a grid shifted 3 m in 2025
    N = pix(12, 6, [0], "neighbour")                                           # Kodihalli's core in the (unnamed) tiles
    xy = _points_outside(L, 13, 6, rng); la, lo = G.tm_to_latlon(xy[:, 0], xy[:, 1])
    O = pd.DataFrame({"buff_km": [0, 0, 5, 5, 5, 5], "latitude": la, "longitude": lo, "a": rng.normal(0, 0.03, 6), "kind": "outside"})
    yrs = range(2016, 2026); sea = {"yearly": 0, "Kharif": 1, "Rabi": 2, "Zaid": 3}
    shock = {(y, s): rng.normal(0, 0.01) for y in yrs for s in range(4)}
    fn = os.path.join(root, "REWARD_Koranahalli_Exports_final"); ft = os.path.join(root, "tiles"); os.makedirs(fn); os.makedirs(ft)
    def val(P, b, site, y, sc):
        eff = np.where((site == 13) & (b == 0) & (((sc == 2) & (y >= 2024)) | ((sc != 2) & (y >= 2025))), 0.05, 0.0)
        return 0.35 + P["a"].values + 0.005 * (y - 2016) + (0.0, 0.06, 0.01, -0.05)[sc] + shock[(y, sc)] + eff + rng.normal(0, 0.008, len(P))
    def write(d, path, sc, mtime=None):
        # v20.58 (hard check): the COVARIATES of an excluded row are poisoned too (x = 1: Rain +100, temperatures +5) -- a model that took the
        # baseline covariates of a row outside the design (matching, weighting, the ML models) would move with them
        n = len(d); v = d["v"].values; x = d["x"].values.astype(float) * (P5 / 5.0); esi = 0.5 + 0.2 * (v - 0.35) + rng.normal(0, 0.002, n)
        out = pd.DataFrame({"latitude": d["latitude"].values, "longitude": d["longitude"].values, "buff_km": d["buff_km"].values, "SubwshedID": "U1",
                            "NDVI": v, "EVI": 0.8 * v + rng.normal(0, 0.003, n), "NDMI": 0.6 * v - 0.1, "ESI": esi,
                            "Rain": np.nan if sc == 0 else 600 + rng.normal(0, 30, n) + 100 * x, "Tmax": np.nan if sc == 0 else 33 + rng.normal(0, .3, n) + 5 * x,
                            "Tmean": np.nan if sc == 0 else 26 + rng.normal(0, .3, n) + 5 * x, "Tmin": np.nan if sc == 0 else 19 + rng.normal(0, .3, n) + 5 * x,
                            "LandUse": 1 + (np.arange(1, n + 1) % 2)})
        out["LSWI"] = out["NDMI"]; out["WSSI"] = 1 - out["ESI"]                   # as in your exports: the same index / a mirror
        # v20.58: every band is a FLOAT32 value, as the exporter writes it (artal_exporter_v111.harmonise: img.toFloat(), "float32 everywhere");
        # the coordinates stay double. Values with more digits than the exporter can produce made R (double) and the Python panel (float32,
        # exact for real exports) start from different inputs -- a 1e-6 difference that is not a model's
        for c_ in out.columns:
            if c_ not in ("latitude", "longitude", "SubwshedID", "buff_km") and pd.api.types.is_float_dtype(out[c_]):
                out[c_] = out[c_].astype(np.float32).astype(np.float64)
        out.to_csv(path, index=False)
        if mtime is not None: os.utime(path, (mtime, mtime))
    t_old = time.mktime((2025, 1, 1, 0, 0, 0, 0, 0, 0))
    for y in yrs:
        for sn, sc in sea.items():
            bk = K["buff_km"].values.copy(); bk[(K["kind"].values == "flip") & (y >= 2023)] = 0
            lat = K["latitude"].values + np.where((K["kind"].values == "shift") & (y == 2025), 3 / 110574.0, 0.0)
            v = val(K, bk, 13, y, sc)
            # v20.58 (second pass): CLOUD GAPS -- 3 % of the own pixels' rows have no value (every band), as your exports where a scene is
            # missing: the panel is UNBALANCED, as real data are (the R-vs-Python comparison ran on complete series only until now, where
            # e.g. a series' effect and a cohort's effect give the same ETWFE coefficients -- on gaps they do not). Same draws in both runs.
            v = np.where(rng.random(len(K)) < 0.03, np.nan, v)
            # v20.58 (hard check): EVERY row the design leaves out, in EVERY year and season and group -- rings 4-5 (CONTROL_ZONES 1-3) in all
            # years, every ring before the window (2020 = the Rabi 2024 start - PRE_YEARS 4), the annual composite of every ring (SEASONS
            # "seasonal"), and the flipping pixels in ALL their rows (a pixel whose ring differs between exports leaves whole). v20.57's test
            # poisoned only the post-period rings 4-5, the core's early years / composite and the flipped "core" rows -- a leak of a
            # pre-period ring 4-5 row, an early control row or a flipping pixel's ring-1 years would have passed it
            excl = np.isin(bk, [4, 5]) | (y < 2020) | (sc == 0) | (K["kind"].values == "flip")
            v = v + P5 * excl
            ov = val(O, O["buff_km"].values, 0, y, sc) + P5
            named = pd.concat([pd.DataFrame({"latitude": lat, "longitude": K["longitude"].values, "buff_km": bk, "v": v, "x": excl.astype(int)}),
                               pd.DataFrame({"latitude": O["latitude"].values, "longitude": O["longitude"].values, "buff_km": O["buff_km"].values, "v": ov,
                                             "x": 1})], ignore_index=True)
            tiles = pd.concat([pd.DataFrame({"latitude": K["latitude"].values, "longitude": K["longitude"].values, "buff_km": K["buff_km"].values,
                                             "v": val(K, K["buff_km"].values, 13, y, sc) + P5, "x": 1}),                # repeats: older, poisoned
                               pd.DataFrame({"latitude": N["latitude"].values, "longitude": N["longitude"].values, "buff_km": N["buff_km"].values,
                                             "v": val(N, N["buff_km"].values, 12, y, sc) + P5, "x": 1}),                # another sub-watershed: always out
                               pd.DataFrame({"latitude": O["latitude"].values, "longitude": O["longitude"].values, "buff_km": O["buff_km"].values,
                                             "v": val(O, O["buff_km"].values, 0, y, sc) + P5, "x": 1})], ignore_index=True)
            write(named, os.path.join(fn, f"CSV_Koranahalli_{y}_{sn}_tile0.csv"), sc)
            half = np.arange(1, len(tiles) + 1) % 2
            for k in (0, 1):
                write(tiles[half == k].reset_index(drop=True), os.path.join(ft, f"CSV_{y}_{sn}_tile{k + 1}.csv"), sc, mtime=t_old)
    dates = pd.date_range("2024-10-01", "2026-07-01", freq="MS")
    fund = pd.DataFrame({"SWS": "Koranahalli", "Date": dates, "Progress": 40 + 10 * np.arange(len(dates)), "Target": 500, "Area": 6741})
    fp = os.path.join(os.path.dirname(root), os.path.basename(root) + "_fund.xlsx"); fund.to_excel(fp, index=False)
    return fp


# ----------------------------------------------------------------------------------------------- the runs
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
MODELS_RUNNER = r'''
import sys, os, json, glob, time
eng, out, models = sys.argv[1], sys.argv[2], json.loads(sys.argv[3]); settings = json.loads(sys.argv[4])
sys.path.insert(0, eng); os.chdir(eng)
import _common as C, validate_all_models as VM
C.SELECTED_OUTCOMES = ["NDVI"]; C.clear_panel_cache()
C.set_scenario(verbose=False, **settings); C.save_scenario(verbose=False); C.PANEL_SCENARIO_OVERRIDES_CELL1 = True
for nb in sorted(glob.glob(os.path.join(eng, "0[2-5]*", "M*.ipynb"))):
    mid = os.path.basename(nb).split("_")[0]
    if models and mid not in models: continue
    t0 = time.time(); st, err, log = VM.run_notebook(nb)
    open(os.path.join(out, f"{mid}.log"), "w", encoding="utf-8").write(log)
    print(json.dumps({"model": mid, "status": st, "error": err[:200], "secs": round(time.time() - t0, 1)}), flush=True)
print("@@MODELS_DONE@@")
'''

def run_variant(key, poison, models, base):
    root = os.path.join(base, key); fund = make_exports(root, poison)
    env = dict(os.environ); env["REWARD_INPUT_DIR"] = root; env["REWARD_FUND_PATH"] = fund; env["REWARD_OUTCOME"] = "NDVI"
    env["PYTHONPATH"] = os.pathsep.join(p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p and os.path.abspath(p) != HERE)
    nb = sorted(glob.glob(os.path.join(HERE, "01_Panel_Preparation", "P00_*.ipynb")))[0]
    r = subprocess.run([sys.executable, "-c", NB_RUNNER, nb], cwd=os.path.dirname(nb), capture_output=True, text=True, timeout=3600, env=env)
    open(os.path.join(base, f"{key}_P00.log"), "w", encoding="utf-8").write(r.stdout + r.stderr)
    if "@@DONE@@" not in r.stdout: raise RuntimeError(f"{key}: P00 did not finish -- {(r.stdout + r.stderr)[-1500:]}")
    logs = os.path.join(base, f"{key}_logs"); os.makedirs(logs, exist_ok=True)
    r = subprocess.run([sys.executable, "-c", MODELS_RUNNER, HERE, logs, json.dumps(models or []), json.dumps(SETTINGS)], cwd=HERE,
                       capture_output=True, text=True, timeout=6 * 3600, env=env)
    open(os.path.join(base, f"{key}_models.log"), "w", encoding="utf-8").write(r.stdout + r.stderr)
    if "@@MODELS_DONE@@" not in r.stdout: raise RuntimeError(f"{key}: the model runs did not finish -- {(r.stdout + r.stderr)[-1500:]}")
    status = [json.loads(l) for l in r.stdout.splitlines() if l.startswith('{"model"')]
    return os.path.join(root, _out_sub(), "results"), {s["model"]: s for s in status}

def numbers(folder):
    """{(model, relative file, column, row): value} of every numeric cell a model wrote."""
    out = {}
    for f in sorted(glob.glob(os.path.join(folder, "M*", "**", "*.csv"), recursive=True)):
        rel = os.path.relpath(f, folder)
        try: t = pd.read_csv(f)
        except Exception: continue
        for c in t.columns:
            v = pd.to_numeric(t[c], errors="coerce")
            if v.notna().sum() == 0 or c in ("secs", "seconds", "n_jobs_used", "elapsed_s"): continue
            for i, x in enumerate(v.values.astype(float)): out[(rel.split(os.sep)[0], rel, c, i)] = float(x)
    return out

def _same(x, y):
    if x is None or y is None: return False
    if np.isnan(x) and np.isnan(y): return True
    if np.isinf(x) or np.isinf(y): return x == y
    return abs(x - y) <= 1e-9 * max(1.0, abs(x))

def main(only=None):
    base = tempfile.mkdtemp(prefix="reward_poison_"); print(f"[INFO]    working in {base}")
    rc, sc = run_variant("clean", False, only, base)
    rp, sp = run_variant("poison", True, only, base)
    a, b = numbers(rc), numbers(rp)
    keys = sorted(set(a) | set(b)); diff = {}
    for k in keys:
        x, y = a.get(k), b.get(k)
        if not _same(x, y): diff.setdefault(k[0], []).append((k[1], k[2], k[3], x, y))
    rows = []
    for m in sorted(set(sc) | set(sp)):
        h = glob.glob(os.path.join(rc, m, "**", "HEADLINE_NDVI.csv"), recursive=True)
        hd = pd.read_csv(h[0]).iloc[0].to_dict() if h else {}
        est = float(hd.get("estimate", np.nan)); kind = hd.get("kind", ""); eng = float(hd.get("engine_estimate", np.nan))
        tol = 0.02 if m in LOOSE else 0.01
        if kind == "effect" and m in ("M15", "M24", "M10"): near = abs(est) <= 0.01                    # placebo / spillover / DDD: truth 0
        elif kind == "effect" and m not in ("M06", "M26"): near = abs(est - TRUE) <= tol
        else: near = None
        se_ok = (kind != "effect") or (np.isfinite(float(hd.get("se", np.nan))) and np.isfinite(float(hd.get("p_value", np.nan))))
        rows.append({"model": m, "clean": sc.get(m, {}).get("status"), "poison": sp.get(m, {}).get("status"), "identical": m not in diff,
                     "cells_differing": len(diff.get(m, [])), "kind": kind, "primary": hd.get("primary", ""), "estimate": est, "engine_estimate": eng,
                     "se": hd.get("se", np.nan), "p": hd.get("p_value", np.nan), "se_and_p": se_ok, "near_truth": near, "se_how": str(hd.get("se_how", ""))[:90]})
    t = pd.DataFrame(rows); out = os.path.join(HERE, "VALIDATION_LOCATION_POISON.csv" if not only else "VALIDATION_LOCATION_POISON_SUBSET.csv")
    t.to_csv(out, index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 90)
    print(t.to_string(index=False))
    for m, d in diff.items():
        print(f"[FAILED]  {m}: {len(d)} numbers differ between the clean and the poisoned run, e.g. " + "; ".join(f"{f} {c}[{i}] {x} vs {y}" for f, c, i, x, y in d[:3]))
    bad = t[(~t.identical) | (t.near_truth == False) | (~t.se_and_p)]
    print(f"report -> {out}")
    print("CLEAN: no excluded row reaches any model, and every effect model finds the truth." if not len(bad) else
          f"{len(bad)} PROBLEM(S): " + ", ".join(bad.model))
    return 1 if len(bad) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
