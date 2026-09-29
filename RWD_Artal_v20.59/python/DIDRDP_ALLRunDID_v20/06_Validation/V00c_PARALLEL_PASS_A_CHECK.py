"""V00c -- PASS A in a SPAWN process pool (Windows semantics) gives exactly what the same per-file work gives in this
process (v20.54).

v20.47-v20.53 shipped an outdated copy of this check: it looked for the engine in a folder named DIDRDP_ALLRunDID_FINAL
(the v17 name) and expected the DiD columns (treatment / post / did_term) from PASS A. Since then those columns are built
per model by build_treatment_columns, so it printed "False" twice on every version. It now checks what PASS A is
responsible for, with the worker set up exactly as run_pass_a sets it up.

    python 06_Validation/V00c_PARALLEL_PASS_A_CHECK.py          (from the engine folder or anywhere)
"""
import sys, os, tempfile, numpy as np, pandas as pd, multiprocessing as mp
ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ENGINE_DIR)
import _prep_common as P
from concurrent.futures import ProcessPoolExecutor

PASS_A_COLUMNS = ["pixel_id", "site_id", "subwshed_id", "time_fe_year", "time_fe_yearseason", "time_fe_season", "row_id",
                  "season_sort_rank"]
SCENARIO_COLUMNS = ["treatment", "control", "pre", "post", "did_term"]


def _exports(td):
    rng = np.random.default_rng(2); paths = []
    for i, (yr, se, sn) in enumerate([(2021, 1, "Kharif"), (2021, 2, "Rabi"), (2023, 1, "Kharif"), (2023, 2, "Rabi"),
                                      (2025, 2, "Rabi"), (2025, 2, "Rabi")]):
        nm = f"CSV_{yr}_{sn}_tile0.csv" if i < 5 else f"CSV_Artal_{yr}_{sn}_tile0_sub0.csv"
        d = pd.DataFrame({"UID": range(800), "Year": yr, "Season": se, "SubwshedID": 1, "Treat": 0,
                          "latitude": 16.7 + np.arange(800) * 8.98e-5, "longitude": 75.3,
                          "buff_km": rng.choice([0, 1, 2, 3, 4, 5], 800), "LandUse": 1, "NDVI": rng.uniform(0.05, 1, 800),
                          "SAVI": .1, "EVI": .1, "LAI": 1, "LSWI": .1, "NDWI": .1, "NDMI": .1, "NDRE": .1, "AGB": 20, "RUSLE": 1,
                          "Rain": 100, "Tmax": 30, "Tmin": 20, "Tmean": 25, "ESI": .1, "WSSI": .1, "WSI": .1, "SMDI": .1,
                          "VCI": .1, "TCI": .1, "VHI": .1})
        p = os.path.join(td, nm); d.to_csv(p, index=False); paths.append(p)
    return paths


def main():
    td = tempfile.mkdtemp(prefix="v00c_"); paths = _exports(td)
    P.KNOWN_SUBWSHED_NAMES = ["Artal"]
    cfg = {k: getattr(P, k) for k in ("UID_PRECISION_DEC", "TREATMENT_YEAR", "POST_CUTOFF", "PRE_CUTOFF", "DEFAULT_CONTROL_ZONES",
                                      "TREAT_CORE_BUFFKM", "SITE_GEOMETRY_CHECK", "BUFF_FROM_GEOMETRY", "INPUT_DIR") if hasattr(P, k)}
    os.environ["PYTHONPATH"] = ENGINE_DIR + os.pathsep + os.environ.get("PYTHONPATH", "")     # as run_pass_a does
    with ProcessPoolExecutor(max_workers=2, mp_context=mp.get_context("spawn"), initializer=P._pa_worker_init,
                             initargs=(ENGINE_DIR, P.KNOWN_SUBWSHED_NAMES, cfg)) as pool:
        par = list(pool.map(P._pa_worker, paths))
    P._pa_worker_init(ENGINE_DIR, P.KNOWN_SUBWSHED_NAMES, cfg)                             # the same set-up here
    seq = [P._pa_worker(p) for p in paths]
    frames = [r[0] for r in par]
    checks = {}
    checks["SPAWN pool (Windows semantics): every file processed in a worker process"] = all(f is not None for f in frames)
    checks[f"PASS A columns present {PASS_A_COLUMNS}"] = all(all(c in f.columns for c in PASS_A_COLUMNS) for f in frames if f is not None)
    checks["no scenario columns from PASS A (built per model by build_treatment_columns)"] = not any(
        c in f.columns for f in frames if f is not None for c in SCENARIO_COLUMNS)
    checks["the exports' own point ids (UID) are dropped (v20.51: the pixel id comes from the coordinates)"] = all(
        "UID" not in f.columns for f in frames if f is not None)
    last = frames[-1]
    checks["the sub-watershed is resolved inside the worker from the file name (Artal)"] = (
        last is not None and "site_name" in last.columns and str(last["site_name"].iloc[0]) == "Artal")
    checks["same grid -> identical pixel ids in both 2025 Rabi files"] = (
        frames[4] is not None and frames[5] is not None and set(frames[4].pixel_id) == set(frames[5].pixel_id))
    checks["pool == in this process, file by file (every column, every value)"] = all(
        a[0] is not None and b[0] is not None and a[0].reset_index(drop=True).equals(b[0].reset_index(drop=True))
        for a, b in zip(par, seq))
    t = P.build_treatment_columns(frames[0])
    checks["the per-model DiD columns follow your rules on the pool's output (core = ring 0, post = Year >= 2022)"] = bool(
        (t["treatment"] == (pd.to_numeric(t["buff_km"]) == 0).astype(int)).all()
        and (t["post"] == (t["Year"] >= 2022).astype(int)).all() and (t["did_term"] == t["treatment"] * t["post"]).all())
    bad = [k for k, v in checks.items() if not v]
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print("CLEAN: PASS A in a process pool == in this process." if not bad else f"{len(bad)} FAILED")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
