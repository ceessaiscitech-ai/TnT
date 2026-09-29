"""
validate_prep_notebooks.py -- run the PREPARATION notebooks end to end, as you do (v20.31).

The cold-start gate only runs each notebook up to its first engine cell, and the model gate runs the 45 models; no
gate ran P00 / P09 / P10 / P11 / P12 to the end -- which is where the P09 schema error and the P10 / P11 import error
lived. This gate writes synthetic exports (pre AND post years, annual + seasonal rows) into a temporary input folder,
then executes EVERY code cell of each notebook in a fresh Python process started from the notebook's own folder
(nothing injected; the notebook's own bootstrap must find the engine). It stops at the first exception, exactly like
Jupyter, and also fails on any "[FAILED]" line a notebook prints.

    python validate_prep_notebooks.py P00        # then any of P01 ... P12 (P02b too) -- or: all
"""
import os, sys, json, glob, subprocess, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))

def _out_sub():
    """v20.58: the output folder's name inside a data root (_paths.OUTPUT_SUBDIR -- "output"; the four-model project: "output_4Models")."""
    try:
        import _paths as _PPo
        return getattr(_PPo, "OUTPUT_SUBDIR", "output")
    except Exception:
        return "output"

PREP = os.path.join(HERE, "01_Panel_Preparation")
ROOT = os.path.join(tempfile.gettempdir(), "reward_prep_notebook_gate")      # shared by the steps, rebuilt by P00
ORDER = ["P00", "MS01", "TWO_SWS"]

RUNNER = r'''
import sys, os, json, traceback
nb = sys.argv[1]
cells = ["".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code"]
ns = {"__name__": "__main__"}
try:   # TEST SANDBOX ONLY: with the pyarrow stand-in (version 0.0.0) pandas cannot read parquet -- route it through the
    import pyarrow as _pa_, pandas as _pd_     # stand-in. With real pyarrow (your machine) nothing is changed.
    if getattr(_pa_, "__version__", "") == "0.0.0":
        import pyarrow.parquet as _pq_
        _pd_.read_parquet = lambda path, columns=None, **kw: _pq_.read_table(path, columns=columns).to_pandas()
        _pd_.DataFrame.to_parquet = lambda self, path, *a, **kw: _pq_.write_table(_pa_.Table.from_pandas(self, preserve_index=False), path)
except Exception:
    pass
for i, src in enumerate(cells):
    src = "\n".join(l for l in src.split("\n") if not l.lstrip().startswith(("%", "!")))
    try:
        exec(compile(src, f"{os.path.basename(nb)} cell {i}", "exec"), ns)
    except SystemExit:
        pass
    except Exception as e:
        print("@@EXCEPTION@@" + json.dumps({"cell": i, "error": type(e).__name__, "msg": str(e)[:400],
                                           "tb": traceback.format_exc()[-1500:]}))
        sys.exit(3)
print("@@DONE@@" + json.dumps({"cells": len(cells)}))
'''


def prepare_inputs():
    sys.path.insert(0, HERE)
    import validate_preprocessing as VP
    if os.path.isdir(ROOT): shutil.rmtree(ROOT, ignore_errors=True)
    os.makedirs(ROOT, exist_ok=True)
    files = VP.write_synthetic_exports(ROOT, n_files=6, n_pix=40, years=(2019, 2020, 2021, 2022, 2023, 2024), seasons=(0, 1, 2, 3))
    # v20.58: every pixel INSIDE Artal's real polygon of its ring (the same point in every file) -- the synthetic coordinates lay outside
    # every polygon, and v20.58's location rule leaves such rows out of every model (code 2): P00 kept no core row, MS01 had nothing to export
    import numpy as np, pandas as pd, _sws_geometry as G_
    L = G_.SWSLocator.from_shapefile(); rg = np.random.default_rng(58); pts = {}
    def inside(buff):
        poly = [p_ for s_, b_, p_ in L.polys if s_ == 1 and b_ == buff][0]; bb = poly.bbox
        while True:
            x = rg.uniform(bb[0], bb[2], 200); y = rg.uniform(bb[1], bb[3], 200); m = poly.contains(x, y)
            if m.any():
                la, lo = G_.tm_to_latlon(x[m][:1], y[m][:1]); return float(la[0]), float(lo[0])
    for f in files:
        d = pd.read_csv(f)
        for u_, b_ in d[["UID", "buff_km"]].drop_duplicates("UID").itertuples(index=False):
            if u_ not in pts: pts[u_] = inside(int(b_))
        d["latitude"] = d["UID"].map(lambda u_: pts[u_][0]); d["longitude"] = d["UID"].map(lambda u_: pts[u_][1]); d["SWSiD_All"] = 1
        d.to_csv(f, index=False)
    return ROOT


def two_sws_scenario():
    """v20.39: the 20-sub-watershed path. Exports inside two REAL polygons (Artal = 1, Phase 2, year in the registry;
    Haligeri = 7, Phase 1, year blank), Haligeri's files carrying Artal's id as the real exports do. P00 must pick the
    POOLED design, name the mislabelled rows, keep the file's id beside the overlay's, and warn about the assumed year."""
    import numpy as np, pandas as pd, shutil, tempfile
    ROOT = os.path.join(tempfile.gettempdir(), "reward_two_sws_gate")
    if os.path.isdir(ROOT): shutil.rmtree(ROOT)
    import _sws_geometry as G_
    L = G_.SWSLocator.from_shapefile(); rg = np.random.default_rng(11)
    def inside(site, buff, n):
        poly = [p for s_, b_, p in L.polys if s_ == site and b_ == buff][0]; bb = poly.bbox; got = []
        while sum(len(o) for o in got) < n:
            x = rg.uniform(bb[0], bb[2], 3000); y = rg.uniform(bb[1], bb[3], 3000); m = poly.contains(x, y)
            got.append(np.column_stack([x[m], y[m]]))
        xy = np.vstack(got)[:n]; return G_.tm_to_latlon(xy[:, 0], xy[:, 1])
    for site, folder, file_id in ((1, "Artal", 1), (7, "Haligeri", 1)):          # Haligeri's files carry id 1, like yours
        pts = []
        for b in range(0, 6):
            lat, lon = inside(site, b, 40); pts += [(la, lo, b) for la, lo in zip(lat, lon)]
        os.makedirs(os.path.join(ROOT, folder), exist_ok=True)
        for y in range(2018, 2026):
            for s, lab in ((0, "yearly"), (1, "Kharif"), (2, "Rabi"), (3, "Zaid")):
                rows = []
                for i, (la, lo, b) in enumerate(pts):
                    v = 0.3 + 0.05 * (s == 1) + rng if (rng := 0) else 0.3 + 0.05 * (s == 1)
                    v += (0.02 if (b == 0 and y >= 2022) else 0.0) + np.random.default_rng(1000 * y + 10 * s + i).normal(0, 0.02)
                    rows.append({"latitude": la, "longitude": lo, "buff_km": b, "Year": y, "SWSiD_All": file_id, "SubwshedID": f"{folder[:3]}{i % 3}", "Treat": int(y >= 2022),
                                 "NDVI": v, "SAVI": v * 0.8, "Rain": 600.0, "Tmax": 33.0, "Tmean": 26.0, "Tmin": 19.0, "LandUse": 2})
                pd.DataFrame(rows).to_csv(os.path.join(ROOT, folder, f"CSV_{y}_{lab}_tile0.csv"), index=False)
    return ROOT


def run(tag, timeout=900):              # v20.57: 280 s timed out on a loaded 2-core machine
    env_root = None
    if tag == "TWO_SWS":                                   # v20.39: P00 on two real sub-watersheds (the pooled path)
        env_root = two_sws_scenario(); nb = sorted(glob.glob(os.path.join(PREP, "P00_*.ipynb")))
    else:
        nb = sorted(glob.glob(os.path.join(PREP, f"{tag}_*.ipynb")) + glob.glob(os.path.join(HERE, "08_Multisite_Runs", f"{tag}_*.ipynb")))
    if not nb: return tag, 2, {"error": "notebook not found"}, ""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p and os.path.abspath(p) != HERE)
    env["REWARD_INPUT_DIR"] = env_root or ROOT
    r = subprocess.run([sys.executable, "-c", RUNNER, nb[0]], cwd=os.path.dirname(nb[0]), capture_output=True, text=True, timeout=timeout, env=env)
    out = r.stdout + r.stderr
    exc = [l for l in out.splitlines() if l.startswith("@@EXCEPTION@@")]
    failed = [l for l in out.splitlines() if l.startswith("[FAILED]")]
    info = json.loads(exc[-1][13:]) if exc else {}
    code = 1 if (exc or failed or "@@DONE@@" not in out) else 0
    if failed and not exc: info = {"error": "[FAILED] printed", "msg": " | ".join(f[:200] for f in failed[:3])}
    if tag == "TWO_SWS" and code == 0:
        import pyarrow.parquet as _pq
        _log = open(sorted(glob.glob(os.path.join(env_root, _out_sub(), "cell_logs", "P00_*")))[-1], encoding="utf-8").read()
        _d = _pq.read_table(os.path.join(env_root, _out_sub(), "did_panel_full.parquet"), columns=["site_id", "sws_id_export", "site_check"]).to_pandas()
        _ok = ("POOLED design" in _log and "lie in 7 (Haligeri)" in _log and "ASSUMED" in _log
               and "Sub-watersheds 2 | inference clusters 8 = years" in _log                  # v20.41: 2 < 6 -> years
               and set(int(x) for x in _d.site_id.unique()) == {1, 7} and (_d.loc[_d.site_id == 7, "sws_id_export"] == 1).all()
               and (_d.loc[_d.site_id == 7, "site_check"] == 1).all() and (_d.loc[_d.site_id == 1, "site_check"] == 0).all())
        if not _ok:
            code, info = 1, {"error": "TWO_SWS", "msg": "pooled design / overlay audit / assumed-year warning not as expected"}
    return tag, code, info, out


def main():
    tags = ORDER if (len(sys.argv) < 2 or sys.argv[1] == "all") else sys.argv[1:]
    if "P00" in tags or not os.path.isdir(ROOT): prepare_inputs()
    bad = 0
    for t in tags:
        tag, code, info, out = run(t)
        if code == 0:
            n = [l for l in out.splitlines() if l.startswith("@@DONE@@")]
            print(f"[OK]      {tag}: every code cell ran ({json.loads(n[-1][8:])['cells']} cells), no exception, no [FAILED] line")
        else:
            bad += 1
            print(f"[FAILED]  {tag}: cell {info.get('cell')} {info.get('error')}: {info.get('msg', '')[:300]}")
            if info.get("tb"): print(info["tb"][-900:])
    junk = [p for p in glob.glob(os.path.join(HERE, "**", "*"), recursive=True) if ":" in os.path.basename(p) or "\\" in os.path.basename(p)]
    if junk: bad += 1; print(f"[FAILED]  a notebook wrote into the bundle: {junk[:3]}")
    print("CLEAN: the preparation notebooks run end to end." if not bad else f"{bad} PROBLEM(S)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
