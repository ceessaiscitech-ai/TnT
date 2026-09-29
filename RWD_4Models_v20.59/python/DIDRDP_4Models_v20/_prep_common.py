"""_prep_common.py -- shared engine for the panel-preparation notebooks (P01-P06).
Split by TASK so each stage can be inspected and re-run independently.
EDIT THE PATHS BELOW, then run P01 -> P06 in order."""
import os, sys, re, json, gc, glob, hashlib, difflib, traceback

# ---- ENVIRONMENT CHECK (v15.3): refuse to run inside ArcGIS Pro's write-protected Python 3.7 ----


# ====================== ENGINE VERSION LOCK (v17.9) ======================
# The version lives in _version.py NEXT TO THIS FILE (single source of truth, read without touching sys.path,
# so the version always describes the engine you actually imported).
def _read_engine_version():
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_version.py")
    _ns = {}
    try:
        with open(_p, encoding="utf-8") as _fh: exec(compile(_fh.read(), _p, "exec"), _ns)
        return _ns.get("ENGINE_VERSION", "0")
    except Exception:
        return "0"
ENGINE_VERSION = _read_engine_version()
def _ver_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))) or (0,)
def require_engine(minimum):
    """Refuse to run on an engine OLDER than the notebook was written for, and refuse a split installation
    (the two engines coming from different folders). A newer engine is fine."""
    here = os.path.abspath(__file__)
    if _ver_tuple(ENGINE_VERSION) < _ver_tuple(minimum):
        raise RuntimeError(
            f"ENGINE TOO OLD: this notebook needs engine >= {minimum} but imported {os.path.basename(here)} "
            f"v{ENGINE_VERSION} from {here}. Either an older bundle is on the path, or this kernel imported the "
            f"engine BEFORE you updated it (a module imported once stays cached for the kernel's life). "
            f"Fix: Kernel > Restart, keep only one REWARD_FINAL_* folder, start Jupyter inside it, run from the top.")
    other = sys.modules.get("_prep_common" if os.path.basename(here).startswith("_common") else "_common")
    if other is not None and getattr(other, "__file__", None):
        if os.path.dirname(os.path.abspath(other.__file__)) != os.path.dirname(here):
            raise RuntimeError(
                f"SPLIT INSTALLATION: {os.path.basename(here)} loaded from {os.path.dirname(here)} but "
                f"{os.path.basename(other.__file__)} from {os.path.dirname(os.path.abspath(other.__file__))}. "
                f"Restart the kernel and keep a single bundle on the path.")
    print(f"[INFO]    engine {os.path.basename(here)} v{ENGINE_VERSION} from {here}")
    return here

# ====================== v17.3: LIBRARIES THIS ENGINE NEEDS (checked at import) ======================
# Every third-party package used anywhere in the pipeline, with the pip name. check_environment() is run
# once when the engine is imported: it prints what is missing and the exact install command, and it never
# stops a run for an OPTIONAL package (GPU / ML extras) -- those code paths fall back to CPU / are skipped.
REQUIRED_PACKAGES = {           # import name : pip name
    "numpy": "numpy", "pandas": "pandas", "pyarrow": "pyarrow", "scipy": "scipy", "sklearn": "scikit-learn",
    "psutil": "psutil", "tqdm": "tqdm", "joblib": "joblib", "openpyxl": "openpyxl",
}
OPTIONAL_PACKAGES = {
    "torch": "torch  (GPU fixed-effects demeaning; CPU numpy path is used without it)",
    "cupy": "cupy-cuda12x  (GPU k-NN / spatial weights; sklearn path without it)",
    "cuml": "cuml  (RAPIDS GPU ML; sklearn path without it)",
    "ipywidgets": "ipywidgets  (tqdm progress-bar widget in Jupyter; text bar without it)",
}
_ENV_CHECKED = {"done": False}
def check_environment(strict=False, verbose=True):
    """Import every package in REQUIRED_PACKAGES / OPTIONAL_PACKAGES, report versions, print the pip line for
    anything missing. strict=True raises ImportError when a REQUIRED package is absent."""
    import importlib as _il
    missing_req, rows = [], []
    for imp, pipn in REQUIRED_PACKAGES.items():
        try:
            m = _il.import_module(imp); rows.append((imp, getattr(m, "__version__", "?"), "ok"))
        except Exception:
            rows.append((imp, "-", "MISSING")); missing_req.append(pipn)
    for imp, note in OPTIONAL_PACKAGES.items():
        try:
            m = _il.import_module(imp); rows.append((imp, getattr(m, "__version__", "?"), "ok (optional)"))
        except Exception:
            rows.append((imp, "-", "absent (optional) -> " + note))
    if verbose and not _ENV_CHECKED["done"]:
        print("[INFO]    environment: " + ", ".join(f"{a} {b}" for a, b, c in rows if c.startswith("ok")))
        for a, b, c in rows:
            if not c.startswith("ok"): print(f"[INFO]      {a}: {c}")
        if missing_req:
            print(f"[WARNING] REQUIRED packages missing -> run:  pip install {' '.join(missing_req)}")
    _ENV_CHECKED["done"] = True
    if strict and missing_req:
        raise ImportError("missing required packages: pip install " + " ".join(missing_req))
    return {"missing_required": missing_req, "packages": rows}
try:
    check_environment(strict=False, verbose=True)
except Exception as _e:
    print(f"[INFO]    environment check skipped: {_e}")
if "arcgis" in sys.executable.lower() or sys.version_info < (3, 9):
    print(f"[FAILED]  wrong Python environment: {sys.executable}")
    print("[INFO]    Jupyter -> Kernel -> Change Kernel -> 'Python [conda env:anaconda3]', then restart.")
    raise ImportError("this pipeline must run in the Anaconda environment (Python >= 3.9), not ArcGIS Pro's")
from datetime import datetime
import numpy as np, pandas as pd
from scipy.spatial import cKDTree

def ok(m):   print(f"[OK]      {m}")
def info(m): print(f"[INFO]    {m}")
def warn(m): print(f"[WARNING] {m}")
def fail(m): print(f"[FAILED]  {m}")

# ====================== v17: TIMESTAMPS, PROGRESS BARS, NEXT-TASK POINTERS ======================
from datetime import datetime as _dt
import time as _time
_STEP_CLOCK = {}          # step label -> start time
_RUN_T0 = _time.time()

def _ts():
    return _dt.now().strftime("%Y-%m-%d %H:%M:%S")

def _fmt_secs(s):
    s = int(s); h, r = divmod(s, 3600); m, s = divmod(r, 60)
    return f"{h:d}h {m:02d}m {s:02d}s" if h else (f"{m:d}m {s:02d}s" if m else f"{s:d}s")

def step(n, msg):
    """Start of a task: prints a timestamped banner and starts its clock."""
    _STEP_CLOCK[str(n)] = _time.time()
    print(f"\n{'='*72}\nSTEP {n}: {msg}\n  started  {_ts()}   (run clock {_fmt_secs(_time.time()-_RUN_T0)})\n{'='*72}")

def done(n=None, next_task=None):
    """End of a task: prints finish timestamp, elapsed time, and what to run next."""
    key = str(n) if n is not None else (list(_STEP_CLOCK)[-1] if _STEP_CLOCK else None)
    t0 = _STEP_CLOCK.get(key, _RUN_T0)
    print(f"{'-'*72}\n  finished {_ts()}   elapsed {_fmt_secs(_time.time()-t0)}"
          + (f"\n  NEXT  -> {next_task}" if next_task else "") + f"\n{'-'*72}")

PROGRESS_STYLE = "text"      # v17.5: "text" (safe everywhere) | "widget" (needs matching ipywidgets)

def progress(iterable, total=None, desc="", unit="it"):
    """Progress bar over any iterable. v17.5: TEXT tqdm (sys.stdout) by default -- the notebook widget
    ('Error displaying widget' when ipywidgets is absent / a different version than the front-end) is never
    used unless PROGRESS_STYLE = "widget". Falls back to a plain counter without tqdm."""
    try:
        if PROGRESS_STYLE == "widget":
            from tqdm.auto import tqdm
            return tqdm(iterable, total=total, desc=desc, unit=unit, dynamic_ncols=True, leave=True)
        from tqdm import tqdm
        return tqdm(iterable, total=total, desc=desc, unit=unit, file=sys.stdout, ascii=True, ncols=100,
                    mininterval=0.5, leave=True)
    except Exception:
        def _plain():
            n = total if total is not None else (len(iterable) if hasattr(iterable, "__len__") else None)
            t0 = _time.time()
            for i, x in enumerate(iterable, 1):
                if n is None or i % max(1, n // 50) == 0 or i == n:
                    pct = f"{i/n*100:5.1f}%" if n else ""
                    el = _time.time() - t0; eta = (el / i * (n - i)) if (n and i) else 0
                    print(f"\r  {desc}: {i}{'/'+str(n) if n else ''} {pct}  elapsed {_fmt_secs(el)}  eta {_fmt_secs(eta)}   ", end="", flush=True)
                yield x
            print()
        return _plain()

# ======================= PATHS: edit INPUT_DIR in _paths.py (v20.14) =======================
# One path, one file. Output / temp / panel / results / estimator files derive from INPUT_DIR and are shared with
# _common.py so the models always read what the preparation wrote. These module defaults are only the fallback
# used if _paths.py is missing.
INPUT_DIR  = r"D:\LKT\TST_Artal"
OUTPUT_DIR = r"D:\LKT\TST_Artal\output"
TEMP_DIR   = os.path.join(OUTPUT_DIR, "_tmp_shards")
SUBWSHED_CROSSWALK_PATH = r"D:\LKT\RWD_Sub_watershed_final_list.xlsx"
FUND_RELEASE_PATH       = r"D:\LKT\Districtwise_Month_wise_Progress_with_DoseIntensity_and_SWS.xlsx"
FINAL_PANEL = os.path.join(OUTPUT_DIR, "did_panel_full.parquet")
ACTIVE_PATHS = {}

def _apply_paths(paths, verbose=False, _propagate=True):
    global INPUT_DIR, OUTPUT_DIR, TEMP_DIR, FINAL_PANEL, SUBWSHED_CROSSWALK_PATH, FUND_RELEASE_PATH
    INPUT_DIR = paths["INPUT_DIR"]; OUTPUT_DIR = paths["OUTPUT_DIR"]; TEMP_DIR = paths["TEMP_DIR"]
    FINAL_PANEL = paths["FINAL_PANEL"]
    SUBWSHED_CROSSWALK_PATH = paths["SUBWSHED_CROSSWALK_PATH"]; FUND_RELEASE_PATH = paths["FUND_RELEASE_PATH"]
    ACTIVE_PATHS.clear(); ACTIVE_PATHS.update(paths)
    # keep the model engine in step when it is loaded in the same kernel
    m = sys.modules.get("_common")
    if _propagate and m is not None and hasattr(m, "_apply_paths"):
        m._apply_paths(paths, verbose=False, _propagate=False)     # v20.14: one hop, never a ping-pong
    if verbose:
        import _paths as _PP
        print("[OK]      paths in force (edit INPUT_DIR in _paths.py, or call set_paths()):")
        print(_PP.describe(paths))

def set_paths(input_dir=None, output_dir=None, temp_dir=None, crosswalk=None, fund_release=None, verbose=True):
    """Point the WHOLE pipeline at an input folder for this session. Output, temp, the panel, results and the
    estimator files derive from it (see _paths.py); both engines are updated; the layout is recorded in
    OUTPUT_DIR/reward_paths.json."""
    import _paths as _PP
    paths = _PP.derive(input_dir, output_dir, temp_dir, crosswalk, fund_release)
    if not os.path.isdir(paths["INPUT_DIR"]):
        warn(f"INPUT_DIR does not exist (yet): {paths['INPUT_DIR']}")
    _apply_paths(paths, verbose=verbose)
    _PP.save(paths)
    return dict(paths)

try:                                     # import-time default: whatever _paths.py says
    import _paths as _PP0
    _sib = sys.modules.get("_common")                 # v20.14: if the other engine is already configured in this
    _live = getattr(_sib, "ACTIVE_PATHS", None)       # kernel, ADOPT its live layout; else the _paths.py default.
    _apply_paths(dict(_live) if _live else _PP0.derive(), _propagate=False)   # never override a configured sibling
    del _PP0
except Exception:
    pass
# ==========================================================

TREATMENT_YEAR=2022; PRE_CUTOFF=2022; POST_CUTOFF=2022   # v20.27: treatment start year 2022 -- pre = Year < 2022, post = Year >= 2022
EXCLUDE_TRANSITION_YEAR = False                           # True = hold 2022 out of both periods (robustness check)
POST_FROM_EXPORT_TREAT = True   # v20.59 (YOUR RULE): the panel's post / pre come from the exports' Treat flag (1 = post, 0 = pre -- the exporter's
                                # own timing, written for every pixel); a row without a usable flag takes the rule Year >= TREATMENT_YEAR (counted,
                                # said). False = the rule for every row (v20.58). Every model applies ITS OWN design when it runs (the fund
                                # timing, TREATMENT_YEAR, the transition year) and says on how many rows it differs from the panel's columns.
VALID_BUFFERS = (0, 1, 2, 3, 4, 5)                        # buffer 0 = treatment area; 1-5 km rings = control area
TREAT_CORE_BUFFKM=0; DEFAULT_CONTROL_ZONES=(1,2,3,4,5)
UID_MATCH_TOLERANCE_M=3.0; ROW_GROUP_SIZE=2_560_000   # v20.58: 5x (was 512,000)
# v14: pixel_id = rounded (lat,lon). 5 decimals ~ 1.1 m: sub-pixel for any satellite product yet
# tolerant of 1e-7 export noise (6 dp = 0.11 m flipped ~19% of ids under such noise in testing and
# is a likely cause of pixels failing to link across years). If P06 step 6c shows multi-year
# overlap rising sharply at 4, your export grids drift between years -- do NOT go below 5 on a 10 m grid: precision 4 (~11 m) MERGES adjacent pixels (6,160 pairs merged in a 40k-pixel test).
UID_PRECISION_DEC=5
SEASON_LABEL={0:"Yearly",1:"Kharif",2:"Rabi",3:"Zaid"}
SEASON_SORT_RANK={1:0,2:1,3:2,0:3}

try:
    import pyarrow as pa, pyarrow.parquet as pq
except ImportError:
    pa=pq=None

GPU_BACKEND="cpu"
try:
    import cupy as cp
    from cuml.neighbors import NearestNeighbors as cuNN
    GPU_BACKEND="cuml"
except Exception:
    try:
        import torch
        if torch.cuda.is_available(): GPU_BACKEND="torch"
    except Exception: pass
GPU_AVAILABLE = GPU_BACKEND!="cpu"

KNOWN_SUBWSHED_NAMES=[]

def autotune_prep(verbose=True):
    """v17: bigger Parquet row-groups on big-RAM machines (fewer, larger I/O ops)."""
    global ROW_GROUP_SIZE
    ram=None
    try:
        import psutil; ram=psutil.virtual_memory().total/1e9
    except Exception: pass
    # v20.58: every size 5x larger (your rule) -- and the v20.6 line "if ram >= 384: 4,000,000" that ran AFTER these and cut the >= 512 GB
    # value back to 4 M (your 549 GB machine never got its 32 M) is gone
    if ram and ram>=512: ROW_GROUP_SIZE=160_000_000     # v20.41: 4x again on >= 512 GB (yours: 549 GB); v20.58 x5
    elif ram and ram>=256: ROW_GROUP_SIZE=40_000_000    # v20.38: 4x on large-RAM machines; v20.58 x5
    elif ram and ram>=128: ROW_GROUP_SIZE=10_000_000    # v20.58 x5
    try:                                                    # v20.7: parent process gets every core for numpy/BLAS
        import _hardware as _H; prof = _H.use_full_machine(verbose=verbose)
        if verbose:
            ok(f"autotune_prep: ROW_GROUP_SIZE={ROW_GROUP_SIZE:,} | PASS A workers={_H.worker_cap()} "
               f"| PASS B workers autotuned per block (PASS_B_WORKERS to pin) | workers run 1 BLAS thread each")
    except Exception:
        if verbose: ok(f"autotune_prep: RAM={f'{ram:.0f} GB' if ram else 'unknown'} -> ROW_GROUP_SIZE={ROW_GROUP_SIZE:,}")
    return ROW_GROUP_SIZE

FNAME_RE = re.compile(
    r"CSV_(?:(?P<site>[A-Za-z][A-Za-z0-9\-]*)_)?"          # optional site name, e.g. "Artal_"
    r"(?P<year>\d{4})_(?P<season>[A-Za-z]+)_tile(?P<tile>\d+)"
    r"(?:_sub(?P<sub>\d+))?\.(?:csv|parquet|xlsx|xlsm|xls|feather|tsv|gz)$",
    re.IGNORECASE)
# v20.14: the LOOSE pattern -- a year and a season word ANYWHERE in the name, in any order, any separators,
# any extra words ("Artal 2022 rabi export (final v3).xlsx", "2023-Kharif tile 07 copy.csv.gz", "rabi_2024.parquet")
_YEAR_LOOSE = re.compile(r"(?<!\d)(20[1-3]\d)(?!\d)")
_SEASON_LOOSE = re.compile(r"(?<![A-Za-z])(kharif|rabi|zaid|yearly|annual|summer|monsoon|winter)(?![A-Za-z])", re.I)
_SEASON_ALIAS = {"kharif": "kharif", "monsoon": "kharif", "rabi": "rabi", "winter": "rabi",
                 "zaid": "zaid", "summer": "zaid", "yearly": "yearly", "annual": "yearly"}
_TILE_LOOSE = re.compile(r"tile[\s_\-]*(\d+)", re.I)
_SUB_LOOSE = re.compile(r"sub[\s_\-]*(\d+)", re.I)
SEASON_CODE = {"yearly": 0, "kharif": 1, "rabi": 2, "zaid": 3}

CANONICAL = ["UID","Year","Season","SubwshedID","SWSiD_All","SWS_Name","Treat","latitude","longitude","buff_km",
 "LandUse","NDVI","SAVI","EVI","LAI","LSWI","NDWI","NDMI","NDRE","AGB","RUSLE","Rain",
 "Tmax","Tmean","Tmin","ESI","WSSI","WSI","SMDI","VCI","TCI","VHI","DataYear","Coverage",
 "SrcOpt","SrcET","NObsV","NObsT","YrRel","LandUseDW","ESI_Anom",
 "GapFilled", "OptTier"]   # FIX v13: was only in NEW_ONLY_COLS; v20.37: OptTier = exporter v111 composite tier (QC)

ALIASES = {"lat":"latitude","lon":"longitude","long":"longitude","lng":"longitude",
 "swsid_all":"SWSiD_All","swsid":"SWSiD_All","sws_id":"SWSiD_All","site_id":"SWSiD_All","siteid":"SWSiD_All","sws":"SWSiD_All",
 "subwshed":"SWS_Name","sws_name":"SWS_Name","swsname":"SWS_Name","sub_watershed_name":"SWS_Name","subwatershed_name":"SWS_Name",
 "sws_nm":"SWS_Name","subwshed_name":"SWS_Name",   # v20.28: the SWS NAME (shapefile column SUBWSHED) -- never the numeric SubwshedID
 "sub_watershed_id":"SubwshedID","subwatershedid":"SubwshedID","sub_wshed_id":"SubwshedID",
 "watershedid":"SubwshedID","treatment":"Treat","is_treated":"Treat",
 "buffer_km":"buff_km","bufferkm":"buff_km","land_use":"LandUse","landuse_dw":"LandUseDW",
 "pixel_uid":"UID","point_id":"UID","rainfall_mm":"Rain","rainfallmm":"Rain",
 "soil_moisture_drought_idx":"SMDI","soilmoisturedroughtindex":"SMDI",
 "distance":"buff_km",
 "seasons":"Season","season_code":"Season","years":"Year","yr":"Year",
 "buff":"buff_km","buffer":"buff_km","buffkms":"buff_km","lat_dd":"latitude","lon_dd":"longitude"}   # found in your real pre-converted Parquet files (DuckDB schema)

def _norm(s): return re.sub(r"[^a-z0-9]", "", s.lower())
_NORM_CANON = {_norm(c): c for c in CANONICAL}
_NORM_ALIAS = {_norm(k): v for k, v in ALIASES.items()}

OLD_ARTIFACT_COLS = ["system:index", ".geo"]
NEW_ONLY_COLS = ["DataYear","Coverage","SrcOpt","SrcET","NObsV","NObsT","YrRel","LandUseDW","ESI_Anom",
                  "GapFilled", "OptTier"]   # FIX v9.0: GapFilled kept as a QC flag; v20.37: OptTier likewise (1..4 tier, 0 none)

# Only these cause a file to be REJECTED if missing -- needed for FE/treatment machinery.
ESSENTIAL_COLS = ["Year","Season","SubwshedID","Treat","latitude","longitude","buff_km"]   # v14: UID demoted -- pixel_id now comes from lat/lon, source UID is unreliable per your instruction
# These are filled NaN + flagged (not rejected) if a source file's schema lacks them --
# e.g. your 2 real uploaded Parquet files have every one of these EXCEPT RUSLE.
OUTCOME_VARS = ["NDVI","SAVI","EVI","LAI","LSWI","NDWI","NDMI","NDRE","AGB","RUSLE"]
# v20.16: MISSING-VALUE POLICY FOR THE PANEL. A cell that is NaN OR exactly 0.0 in an index or a weather variable
# is a masked / no-data cell in these exports (an exact 0.0 seasonal mean of NDVI, Rain or Tmax is not a
# measurement), so it is set to NaN BEFORE duplicates are resolved -- a second file's real value then fills it --
# and a row left with no usable outcome at all is dropped from the panel. Categorical / count columns (LandUse,
# NObsV, flags) are never touched by the zero rule.
ZERO_AS_MISSING = True
ZERO_RULE_VARS = OUTCOME_VARS + ["ESI","WSSI","WSI","SMDI","VCI","TCI","VHI","Rain","Tmax","Tmean","Tmin"]
ZERO_RULE_EXCEPT = ()          # variables where an exact 0 IS a valid value (none by default; e.g. ("Rain",))
# v20.30: NO NEGATIVE COVARIATES. Rainfall cannot be negative, and this region never sees sub-zero temperatures, so a
# negative value is an artefact (resampling, gap-fill arithmetic, or the exporter's -10 C clamp on a masked ERA5 cell).
# Applied during preparation, AFTER exact zeros became missing -- so the floored 0 is a real value that the models keep.
#   "zero" = floor at 0 (your rule, default) | "missing" = treat as no-data | "keep" = allow negatives
NEGATIVE_COVARIATE_RULE = {"Rain": "zero", "Tmax": "zero", "Tmean": "zero", "Tmin": "zero"}
NODATA_SENTINEL_BELOW = -100.0     # v20.30: -9999 / -3.4e38 style fill values are NO-DATA -> missing (never floored to 0)
TEMPERATURE_CLAMP_NODATA = -10.0   # v20.30: the exporter clamps temperature to [-10, 60] C; exactly -10.0 is that clamp on a
                                   # masked cell (never a real temperature here) -> missing. None = treat it like any negative
ALLOW_NEGATIVE_COVARIATES = False   # True = remove the barrier for every covariate (later processing); rebuild the panel
DROP_ROWS_WITHOUT_OUTCOME = True

def drop_rows_without_outcome(df, stats=None):
    """Rows with no usable outcome (every outcome missing) leave the panel. Returns (df, stats) with the counts by group
    (rows_dropped_no_outcome, _core, _rings; rows_core / rows_rings = the rows looked at).
    v20.58 (second pass): P00 calls it AFTER the cross-file de-duplication (PASS B; R: after resolve_duplicates) -- see apply_missing_policy."""
    stats = {} if stats is None else stats
    stats.setdefault("rows_dropped_no_outcome", 0)
    ocols = [c for c in OUTCOME_VARS + ["ESI","WSSI","WSI","SMDI","VCI","TCI","VHI"] if c in df.columns]
    if ocols:
        has_any = np.isfinite(df[ocols].apply(pd.to_numeric, errors="coerce").values.astype(np.float64)).any(axis=1)
        n_drop = int((~has_any).sum())
        # v20.18: by GROUP -- is the masking concentrated in the treated core (buff_km 0) or in the rings?
        if "buff_km" in df.columns:
            core = (pd.to_numeric(df["buff_km"], errors="coerce") == TREAT_CORE_BUFFKM).values
            stats["rows_core"] = int(core.sum()); stats["rows_rings"] = int((~core).sum())
            stats["rows_dropped_no_outcome_core"] = int((~has_any & core).sum())
            stats["rows_dropped_no_outcome_rings"] = int((~has_any & ~core).sum())
        if n_drop:
            stats["rows_dropped_no_outcome"] = n_drop
            df = df[has_any]
    return df, stats


def apply_missing_policy(df, log=None, stage="file", drop_empty=True):
    """Set NaN/0 cells to NaN (per ZERO_RULE_VARS) and drop rows with no usable outcome. Returns (df, stats).
    v20.30: stage="file" (PASS A, the raw export) turns original zeros into missing and THEN floors negative
    covariates at 0; stage="block" (PASS B, already prepared) must not touch those covariates' zeros again -- by then
    every 0 in them is a floored, real value.
    v20.58 (second pass, found by the poison test with cloud gaps): drop_empty=False keeps the rows with no usable outcome -- P00 drops
    them only AFTER the cross-file de-duplication. Dropped per file (before it), a newer export's row that a cloud left empty was gone
    before the duplicates were compared, and the OLDER repeated row of that pixel-year-season took its place -- a repeated row reached
    every model (+5 poison: M01 0.087 for the true 0.050). Now the newer row claims its pixel-year-season, the repeated row is dropped
    whole, and then the empty row leaves (drop_rows_without_outcome)."""
    stats = {"zero_cells_set_missing": 0, "rows_dropped_no_outcome": 0}
    cols = [c for c in ZERO_RULE_VARS if c in df.columns and c not in ZERO_RULE_EXCEPT]
    if stage == "block":                                   # v20.30: floored covariates keep their (real) zeros
        _fl = {k for k, r in NEGATIVE_COVARIATE_RULE.items() if r == "zero" and not ALLOW_NEGATIVE_COVARIATES}
        cols = [c for c in cols if c not in _fl]
    if ZERO_AS_MISSING and cols:
        for c in cols:
            v = pd.to_numeric(df[c], errors="coerce")
            z = (v == 0)
            if z.any():
                stats["zero_cells_set_missing"] += int(z.sum())
                df[c] = v.mask(z, np.nan)
    if DROP_ROWS_WITHOUT_OUTCOME and drop_empty:
        df, stats = drop_rows_without_outcome(df, stats)
    if log is not None and (stats["zero_cells_set_missing"] or stats["rows_dropped_no_outcome"]):
        log.append(stats)
    # v20.30: negative covariates -- after the zero rule, so a floored 0 stays a real value
    stats["negative_cells"] = {}; stats["negative_cells_at_minus10"] = {}
    for c_, rule in NEGATIVE_COVARIATE_RULE.items():
        if c_ not in df.columns: continue
        rule = "keep" if ALLOW_NEGATIVE_COVARIATES else rule
        v_ = pd.to_numeric(df[c_], errors="coerce")
        neg = (v_ < 0).values
        if not neg.any(): continue
        stats["negative_cells"][c_] = int(neg.sum())
        stats["negative_cells_at_minus10"][c_] = int((v_.values == -10.0).sum())
        # no-data first: fill values and the temperature clamp are MISSING -- flooring them would invent a real 0
        nod = neg & (v_.values <= NODATA_SENTINEL_BELOW)
        if TEMPERATURE_CLAMP_NODATA is not None and c_ in ("Tmax", "Tmean", "Tmin"):
            nod |= neg & (v_.values == TEMPERATURE_CLAMP_NODATA)
        if nod.any():
            df.loc[nod, c_] = np.nan; stats.setdefault("negative_nodata_to_missing", {})[c_] = int(nod.sum())
        if rule == "keep": continue       # v20.54: AFTER the no-data rule. With the barrier removed (ALLOW_NEGATIVE_COVARIATES)
                                          # a -9999 fill value or the -10 C clamp used to stay in the panel as a real value
        rest = neg & ~nod
        if rest.any():
            if rule == "zero":      df.loc[rest, c_] = 0.0; stats.setdefault("negative_floored_to_zero", {})[c_] = int(rest.sum())
            elif rule == "missing": df.loc[rest, c_] = np.nan; stats.setdefault("negative_blocked_to_missing", {})[c_] = int(rest.sum())
    return df, stats
OTHER_CORE_LENIENT = ["UID","LandUse","Rain","Tmax","Tmean","Tmin","ESI","WSSI","WSI","SMDI","VCI","TCI","VHI"]

# v17.1: the satellite panel's Season/Year come from the GEE exporter (artal_exporter SEASONS):
#   Kharif = Jun-Sep, Rabi = Oct-Feb, Zaid = Mar-May, Year = calendar year of the season START
#   (a January/February month belongs to the Rabi that began the previous October).
# The legacy prep definition (Kharif Jun-Oct, Rabi Nov-Mar, Zaid Apr-May, agri-year Jan-May) only
# ever drove the fund-release dose timing (P05) and disagreed with the panel for October and March.
# 'export' aligns P05 with the panel; set 'legacy' to reproduce earlier dose tables exactly.
SEASON_DEFINITION = "export"
if SEASON_DEFINITION == "export":
    SEASON_MONTHS = {1: [6,7,8,9], 2: [10,11,12,1,2], 3: [3,4,5]}       # Kharif, Rabi, Zaid (exporter)
    EXPECTED_MONTHS_PER_SEASON = {1: 4, 2: 5, 3: 3}
else:
    SEASON_MONTHS = {1: [6,7,8,9,10], 2: [11,12,1,2,3], 3: [4,5]}     # legacy prep definition
    EXPECTED_MONTHS_PER_SEASON = {1: 5, 2: 5, 3: 2}
SEASON_CYCLE = [1, 2, 3]

class InsufficientDataError(Exception):
    """Raised ONLY for known, explicitly-checked data-insufficiency conditions (empty
    groups, zero within-unit variation, too few clusters, no pre/post overlap, etc.) --
    NEVER for an actual bug. This is the ONLY exception type the orchestration loop
    (Step 17) catches gracefully and logs as 'blocked, needs more/different data'; any
    OTHER exception type is a potential BUG and is allowed to propagate loudly (full
    traceback, its own distinctly-named error file) rather than being silently absorbed --
    per your explicit instruction that no function may silently swallow a mistake."""
    pass


def parse_filename(path, strict=False):
    """What the FILE NAME says about the block it holds. Two layers:
      1. the exact export convention  CSV_[Site_]YYYY_Season_tileN[_subN].ext   (site name recognised);
      2. (v20.14) a LOOSE reading -- a year 2010-2039 and a season word anywhere in the name, any separators,
         any extra words. Site names are only taken from layer 1 (a loose name is not trusted for that).
    Returns None when the name carries no usable key; load_and_harmonize() then falls back to the Year / Season
    COLUMNS inside the file, so a file is never skipped for its name alone. A partial key (year but no season,
    or season but no year) is returned with the missing part as None and completed from the columns."""
    base = os.path.basename(path)
    m = FNAME_RE.search(base)
    if m and m.group("season").lower() in SEASON_CODE:
        return dict(Year=int(m.group("year")), Season=SEASON_CODE[m.group("season").lower()],
                    tile_raw=m.group("tile"), sub_raw=m.group("sub"), site_from_name=m.group("site"), how="strict")
    if strict:
        return None
    stem = base
    for ext in (".csv.gz", ".csv", ".tsv", ".txt", ".parquet", ".pq", ".feather", ".xlsx", ".xlsm", ".xls"):
        if stem.lower().endswith(ext): stem = stem[:-len(ext)]; break
    ym = _YEAR_LOOSE.findall(stem); sm = _SEASON_LOOSE.findall(stem)
    year = int(ym[0]) if len(set(ym)) == 1 else None            # two different years in one name = ambiguous
    season = SEASON_CODE[_SEASON_ALIAS[sm[0].lower()]] if len({x.lower() for x in sm}) == 1 else None
    if year is None and season is None:
        return None
    tm = _TILE_LOOSE.search(stem); sb = _SUB_LOOSE.search(stem)
    return dict(Year=year, Season=season, tile_raw=tm.group(1) if tm else None, sub_raw=sb.group(1) if sb else None,
                site_from_name=None, how="loose")

def validate_output_dir(create=True):
    """FIX v9.0: creates OUTPUT_DIR and fails EARLY with a readable message if the path is
    malformed. v8 had neither check, so a missing folder or a doubled drive letter surfaced
    as an opaque OSError from deep inside pandas."""
    p = OUTPUT_DIR
    problems = []
    if not isinstance(p, str) or not p.strip():
        problems.append("OUTPUT_DIR is empty")
    else:
        if re.match(r"^[A-Za-z]:[A-Za-z]:", p):
            problems.append(f"DOUBLED DRIVE LETTER -- '{p[:2]}' appears twice at the start")
        if p.count(":") > 1:
            problems.append("more than one ':' -- the drive letter is duplicated")
    if problems:
        fail(f"OUTPUT_DIR is malformed: {p!r}")
        for pr in problems:
            fail(f"   {pr}")
        info(r'   It should look like:  OUTPUT_DIR = r"D:\LKT\TST_Artal\output"')
        raise ValueError("fix OUTPUT_DIR in _prep_common.py")
    if create:
        os.makedirs(p, exist_ok=True)
    ok(f"OUTPUT_DIR valid and ready: {p}")
    return p

def harmonize_columns(cols, fname="", unresolved_log=None):
    mapping = {}
    for c in cols:
        if c in ("system:index", ".geo"):
            continue
        if c == "uid_final":
            # found in your real pre-converted files -- likely from an earlier pixel-matching
            # attempt. Kept as a DISTINCT passthrough column for QA cross-checking against our
            # own pixel_id, never merged into canonical 'UID' (which already exists separately
            # in the same files).
            mapping[c] = "external_uid_final"
            continue
        n = _norm(c)
        if n in _NORM_CANON: mapping[c] = _NORM_CANON[n]
        elif n in _NORM_ALIAS: mapping[c] = _NORM_ALIAS[n]
        else:
            close = difflib.get_close_matches(n, list(_NORM_CANON.keys()), n=1, cutoff=0.8)
            if close: mapping[c] = _NORM_CANON[close[0]]
            else:
                mapping[c] = c
                if unresolved_log is not None: unresolved_log.append((fname, c))
    return mapping


def dedupe_mapping(mapping, fname="", unresolved_log=None):
    """v20.53: ONE file with two columns that are aliases of the same canonical name (e.g. UID and pixel_uid) became two
    columns with one name -- df[name] was then a table and the numeric cast failed. The first keeps the name; a later one
    is kept as "<name>__dup_<its own name>" (nothing is lost) and reported. (harmonize_columns itself maps every spelling
    to its canonical name -- v20.52 had put this inside it, which broke the spelling test A3.)"""
    seen, out = set(), {}
    for c, t in mapping.items():
        if t in seen and t != c:
            out[c] = f"{t}__dup_{c}"
            if unresolved_log is not None: unresolved_log.append((fname, f"{c}: a second column for {t} (kept as {out[c]})"))
        else:
            out[c] = t; seen.add(t)
    return out


PIXEL_ID_AS_INT = True        # v17.6: int64 ids (v16 schema); False -> legacy 18-digit strings

def assign_pixel_ids(lat, lon, precision=UID_PRECISION_DEC, as_int=PIXEL_ID_AS_INT):
    """v14: pixel_id is a PURE FUNCTION of the rounded coordinate -- identical (lat,lon) in any
    file, any year, any season -> identical id. No nearest-neighbour registry, no tolerance,
    no order dependence, no GPU needed. Vectorised (numpy), so it is also far faster.
    precision=5 -> ~1.1 m; precision=4 -> ~11 m (use 4 if export grids drift between years)."""
    lat = np.asarray(lat, dtype=float); lon = np.asarray(lon, dtype=float)
    f = 10 ** precision
    # ONE rounding, applied to the already-scaled value. Rounding first and then multiplying in
    # float re-introduces representation error at the 1e-5 grid and flipped ~19% of ids under
    # 1e-7 noise in testing; this form flips only the ~1% genuinely sitting on a boundary.
    ls = np.rint((lat + 90.0) * f).astype(np.int64)
    lo = np.rint((lon + 180.0) * f).astype(np.int64)
    if as_int:
        # v17.6: the SAME 18-digit id as an int64 (ls * 1e9 + lo == int(zfill(ls,9)+zfill(lo,9))), computed with
        # integer arithmetic: ~50x faster than np.char string building and 8 B/row instead of ~60 B/row.
        return ls * np.int64(10 ** 9) + lo
    return np.char.add(np.char.zfill(ls.astype(str), 9), np.char.zfill(lo.astype(str), 9))


def numeric_pixel_id(lat, lon, precision=UID_PRECISION_DEC):
    """Pure function of the rounded coordinate -- 18-digit numeric string, <=20 chars,
    directly derived from lat/lon (not a hash), order-independent and reproducible."""
    lat_r = round(float(lat), precision)
    lon_r = round(float(lon), precision)
    lat_scaled = int(round((lat_r + 90) * 10**precision))    # 0 .. 180,000,000 -> 9 digits
    lon_scaled = int(round((lon_r + 180) * 10**precision))   # 0 .. 360,000,000 -> 9 digits
    uid = f"{lat_scaled:09d}{lon_scaled:09d}"
    assert len(uid) <= 20
    return uid


def _nn_match_torch_chunked(query_xy, registry_xy, query_chunk=20000, registry_chunk=20000):   # v20.58: blocks 5x larger (was 4000 x 20000)
    """Brute-force GPU nearest-neighbor via PyTorch -- works natively on Windows.
    Double-chunked (query AND registry) so GPU memory stays bounded as the registry grows into
    the millions of points at full 40k-file scale. Coordinates are CENTERED before the
    |q|^2+|r|^2-2q.r distance identity -- validated this against scipy cKDTree on real data:
    uncentered, worst-case distance error was 0.125m (close enough to the 3m tolerance to risk
    flipping a same/different-pixel decision); centered, the error drops to 3e-5m."""
    center = registry_xy.mean(axis=0)
    q_all = torch.as_tensor(query_xy - center, dtype=torch.float32, device="cuda")
    r_all = torch.as_tensor(registry_xy - center, dtype=torch.float32, device="cuda")
    n = q_all.shape[0]
    out_dist = torch.empty(n, device="cuda")
    out_idx = torch.empty(n, dtype=torch.int64, device="cuda")
    for qs in range(0, n, query_chunk):
        q = q_all[qs:qs+query_chunk]
        best_d2 = torch.full((q.shape[0],), float("inf"), device="cuda")
        best_idx = torch.zeros(q.shape[0], dtype=torch.int64, device="cuda")
        for rs in range(0, r_all.shape[0], registry_chunk):
            r = r_all[rs:rs+registry_chunk]
            d2 = torch.cdist(q, r, p=2, compute_mode="donot_use_mm_for_euclid_dist") ** 2   # v20.49: exact differences (float32 matrix identity erred by ~1.5 m)
            local_min, local_idx = d2.min(dim=1)
            improve = local_min < best_d2
            best_d2 = torch.where(improve, local_min, best_d2)
            best_idx = torch.where(improve, local_idx + rs, best_idx)
        out_dist[qs:qs+query_chunk] = best_d2.clamp(min=0).sqrt()
        out_idx[qs:qs+query_chunk] = best_idx
    return out_dist.cpu().numpy(), out_idx.cpu().numpy()


def _nn_match(query_xy, registry_xy):
    if GPU_BACKEND == "cuml" and len(registry_xy) > 50_000:
        model = cuNN(n_neighbors=1)
        model.fit(cp.asarray(registry_xy))
        dist, idx = model.kneighbors(cp.asarray(query_xy))
        return cp.asnumpy(dist).ravel(), cp.asnumpy(idx).ravel()
    if GPU_BACKEND == "torch" and len(registry_xy) > 50_000:
        return _nn_match_torch_chunked(query_xy, registry_xy)
    tree = cKDTree(registry_xy)
    return tree.query(query_xy, k=1)


class PixelRegistry:
    """Persistent lat/lon -> stable numeric UID registry. Call assign_batch() once per
    processing unit (Step 8 batches per file; batch per YEAR instead if profiling shows
    this as the bottleneck on the full 40k-file run)."""

    def __init__(self, tol_m=3.0):
        self.tol_m = tol_m
        self._reg_x = np.empty(0); self._reg_y = np.empty(0)
        self.uids = []
        self._mean_lat = None

    def _to_xy_m(self, lat, lon):
        R = 6371000.0
        lat0 = np.radians(self._mean_lat if self._mean_lat is not None else lat.mean())
        return np.radians(lon) * R * np.cos(lat0), np.radians(lat) * R

    def assign_batch(self, lat_arr, lon_arr):
        lat_arr = np.asarray(lat_arr, dtype="float64")
        lon_arr = np.asarray(lon_arr, dtype="float64")
        if self._mean_lat is None:
            self._mean_lat = lat_arr.mean()
        x, y = self._to_xy_m(lat_arr, lon_arr)
        out = np.empty(len(lat_arr), dtype=object)
        matched = np.zeros(len(lat_arr), dtype=bool)

        if len(self._reg_x) > 0:
            dist, idx = _nn_match(np.column_stack([x, y]), np.column_stack([self._reg_x, self._reg_y]))
            within = dist <= self.tol_m
            for i in np.where(within)[0]:
                out[i] = self.uids[idx[i]]
            matched |= within

        new_idx = np.where(~matched)[0]
        if len(new_idx):
            new_uids = [numeric_pixel_id(lat_arr[i], lon_arr[i]) for i in new_idx]
            for pos, i in enumerate(new_idx):
                out[i] = new_uids[pos]
            self.uids.extend(new_uids)
            self._reg_x = np.concatenate([self._reg_x, x[new_idx]])
            self._reg_y = np.concatenate([self._reg_y, y[new_idx]])
        return out


def extract_site_name(path, known_names):
    """Returns (name, strategy) or (None, None) -- never guesses.

    FIX v9.0: strategy 0 now reads the site name straight out of the FILENAME, e.g.
    CSV_Artal_2025_Rabi_tile11_sub1.csv -> "Artal". That is far more reliable than inferring
    it from folder names, and it keeps working if files are moved or re-organised.
    The original path-based strategies remain as fallbacks for the older un-named files.
    (Also fixes a real crash: this function referenced an undefined `_re` alias.)"""
    fm = parse_filename(path)
    if fm and fm.get("site_from_name"):
        cand = fm["site_from_name"].strip().lower()
        for name in known_names:
            if cand == name.strip().lower():
                return name, "site_embedded_in_filename"
        # a site name is present but unknown to the crosswalk -- report it verbatim so the
        # mismatch is visible rather than silently falling through to a weaker strategy
        return fm["site_from_name"], "filename_site_not_in_crosswalk"

    m = re.search(r"REWARD_(.+?)_Exports_final", path, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip().lower()
        for name in known_names:
            if candidate == name.strip().lower():
                return name, "reward_exports_final_pattern"
    parts = re.split(r"[\\/]", path)
    for part in parts:
        for name in known_names:
            if part.strip().lower() == name.strip().lower():
                return name, "exact_path_component"
    for part in parts:
        for name in known_names:
            if len(name) > 3 and name.lower() in part.lower():
                return name, "substring_match"
    return None, None



def _fast_read_csv(path):
    """v17.6: read a GEE CSV export with pyarrow.csv (multi-threaded C++, 5-10x pandas) and hand back the
    same pandas frame pandas.read_csv would produce for these files. Falls back to pandas on any error
    (e.g. an unusual quoting) so nothing changes in outputs -- only in speed."""
    try:
        import pyarrow.csv as _pacsv
        t = _pacsv.read_csv(path, read_options=_pacsv.ReadOptions(use_threads=True, block_size=64 << 20))
        return t.to_pandas()
    except Exception:
        return pd.read_csv(path)

# ====================== v20.10: WINDOWS-SAFE FILE HANDLING ======================
# Windows refuses to rename or delete a file while ANY handle points at it. pyarrow's ParquetFile keeps the file
# open until you close it, and several helpers here opened one just to read metadata and never closed it -- which
# is why publishing the finished panel failed with "[WinError 5] Access is denied". Every metadata-only read now
# goes through these helpers, which always close.
def pq_meta(path):
    """(num_rows, num_row_groups, column_names) -- opens, reads, CLOSES."""
    pf = pq.ParquetFile(path)
    try:
        return pf.metadata.num_rows, pf.num_row_groups, list(pf.schema_arrow.names)
    finally:
        try: pf.close()
        except Exception: pass

def pq_is_readable(path):
    try:
        pq_meta(path); return True
    except Exception:
        return False

def publish_atomic(build_path, final_path, retries=12, wait=1.0):
    """Rename the finished file over the real name, Windows-safely: collect garbage (so any ParquetFile that is
    still referenced is released), then retry the replace, and only then give up with a message that says exactly
    how to finish the job by hand."""
    import gc, time as _t
    gc.collect()
    last = None
    for attempt in range(1, retries + 1):
        try:
            os.replace(build_path, final_path)          # atomic; overwrites the destination on Windows too
            return final_path
        except PermissionError as e:
            last = e
            if attempt == 1:
                warn(f"the destination is locked by another handle ({e.__class__.__name__}); retrying for "
                     f"{retries} seconds -- close any viewer/notebook that has the panel open")
            gc.collect(); _t.sleep(wait)
            if attempt == retries // 2:                 # last resort: remove the old file, then rename
                try:
                    os.remove(final_path)
                except Exception:
                    pass
    raise PermissionError(
        f"could not publish the finished panel: {last}\n"
        f"    The DATA IS COMPLETE and sitting in:  {build_path}\n"
        f"    Something still holds a handle on {os.path.basename(final_path)} (usually this same kernel, or a "
        f"file explorer / Excel / another notebook).\n"
        f"    Fix without re-running PASS B:  restart the kernel, then\n"
        f"        import _prep_common as P; P.finalize_pending_panel()")

def finalize_pending_panel(output_dir=None, verbose=True):
    """Publish a finished-but-unpublished panel (a *.parquet.building left by a failed rename). Verifies the
    footer first, quarantines an unreadable file already sitting at the final name, then renames. No recompute."""
    output_dir = output_dir or OUTPUT_DIR
    final_path = os.path.join(output_dir, "did_panel_full.parquet")
    build_path = final_path + ".building"
    if not os.path.exists(build_path):
        if pq_is_readable(final_path):
            if verbose: ok(f"nothing pending: {final_path} is already a valid panel")
            return final_path
        raise FileNotFoundError(f"no {os.path.basename(build_path)} to publish in {output_dir}")
    rows, rgs, cols = pq_meta(build_path)               # raises if the footer is missing -> do not publish junk
    if verbose: ok(f"pending panel is complete: {rows:,} rows, {rgs} row groups, {len(cols)} columns")
    if os.path.exists(final_path) and not pq_is_readable(final_path):
        q = quarantine_file(final_path)
        if q and verbose: warn(f"unreadable file at the final name moved aside: {os.path.basename(q)}")
    publish_atomic(build_path, final_path)
    if verbose: ok(f"published -> {final_path}")
    return final_path

def quarantine_file(path, suffix=None):
    """v20.8: move an unreadable output aside instead of leaving it where a later step might read it."""
    if not os.path.exists(path): return None
    import time as _t
    q = f"{path}.corrupt_{suffix or _t.strftime('%Y%m%d_%H%M%S')}"
    try:
        os.replace(path, q); return q
    except Exception:
        return None

def panel_file_report(path=None):
    """Quick answer to 'is my panel file usable?' -- size, row count, columns, or the reason it cannot be read."""
    path = path or FINAL_PANEL
    if not os.path.exists(path): return {"path": path, "exists": False}
    size = os.path.getsize(path)
    try:
        nrows, rgs, names = pq_meta(path)              # v20.10: closes the handle
        return {"path": path, "exists": True, "readable": True, "gb": round(size / 1e9, 2),
                "rows": nrows, "row_groups": rgs, "columns": len(names)}
    except Exception as e:
        return {"path": path, "exists": True, "readable": False, "gb": round(size / 1e9, 2), "error": str(e)[:120]}

def final_panel_is_valid(path=None, required_cols=None, min_rows=1):
    """v17.6: True when the final panel exists, has every required column and at least min_rows rows --
    used by P00 to SKIP a rebuild unless FORCE_REBUILD = True."""
    path = path or FINAL_PANEL
    if not os.path.exists(path): return False
    try:
        nrows, _rg, names = pq_meta(path)              # v20.10: opens and CLOSES (Windows locks otherwise)
        cols = set(names)
        need = set(required_cols or FINAL_PANEL_COLUMNS)
        missing = need - cols
        if missing:
            warn(f"final panel exists but lacks {sorted(missing)} -> will rebuild"); return False
        if nrows < min_rows:
            warn("final panel exists but is empty -> will rebuild"); return False
        # v20.25: a panel built WITHOUT the near-duplicate pixel merge (or with other settings) is out of date
        _bs = os.path.join(os.path.dirname(path), "panel_build_settings.json")
        _want = {"enabled": bool(NEAR_DUPLICATE_PIXELS), "overlap_min": PIXEL_OVERLAP_MIN, "pixel_size_m": PIXEL_SIZE_M, "priority": DEDUP_PRIORITY}
        try:
            _got = json.load(open(_bs, encoding="utf-8")) if os.path.exists(_bs) else {}
        except Exception:
            _got = {}
        _nd = _got.get("near_duplicate_pixels", {}) or {}
        _have = {"enabled": bool(_nd.get("enabled", False)), "overlap_min": _nd.get("overlap_min"), "pixel_size_m": _nd.get("pixel_size_m"),
                 "priority": _got.get("dedup_priority")}
        # v20.30: the negative-covariate barrier is prepared at panel level -- another setting means another panel
        _nb_want = {"rule": dict(NEGATIVE_COVARIATE_RULE), "allow_negative": bool(ALLOW_NEGATIVE_COVARIATES),
                    "nodata_below": NODATA_SENTINEL_BELOW, "temperature_clamp_nodata": TEMPERATURE_CLAMP_NODATA}
        # v20.58 (your rule "repeated rows are dropped"): until v20.57 the kept row's gaps were FILLED from the repeated rows (no key in
        # panel_build_settings.json = that behaviour) -- such a panel holds values of dropped rows, so it is rebuilt unless you keep it
        _fill_got = bool(_got.get("dedup_fill_from_duplicates", True)) if _got else None
        if _fill_got is not None and _fill_got != bool(DEDUP_FILL_FROM_DUPLICATES) and not ACCEPT_PANEL_WITHOUT_PIXEL_MERGE:
            warn(f"final panel exists but was built with DEDUP_FILL_FROM_DUPLICATES = {_fill_got} "
                 + ("(every panel before v20.58: gaps of the kept rows were filled with values of the REPEATED rows) " if "dedup_fill_from_duplicates" not in _got else "")
                 + f"vs {bool(DEDUP_FILL_FROM_DUPLICATES)} now -> will rebuild so repeated rows are dropped whole "
                 f"(set ACCEPT_PANEL_WITHOUT_PIXEL_MERGE = True to keep it)")
            return False
        # v20.59: the panel's post / pre come from the exports' Treat flag (POST_FROM_EXPORT_TREAT) -- another setting means another panel
        _pf_want = bool(POST_FROM_EXPORT_TREAT and not EXCLUDE_TRANSITION_YEAR); _pf_got = _got.get("post_from_export_treat") if _got else None
        if _pf_got is not None and bool(_pf_got) != _pf_want and not ACCEPT_PANEL_WITHOUT_PIXEL_MERGE:
            warn(f"final panel exists but its post / pre columns were built {'from the exports Treat flag' if _pf_got else 'from the rule Year >= TREATMENT_YEAR'} "
                 f"(POST_FROM_EXPORT_TREAT = {bool(_pf_got)}) vs {_pf_want} now -> will rebuild (set ACCEPT_PANEL_WITHOUT_PIXEL_MERGE = True to keep it)")
            return False
        if _got.get("negative_barrier") != _nb_want and not ACCEPT_PANEL_WITHOUT_PIXEL_MERGE:
            warn(f"final panel exists but was built with other negative-covariate settings ({_got.get('negative_barrier')} vs {_nb_want}) "
                 f"-> will rebuild PASS B (set ACCEPT_PANEL_WITHOUT_PIXEL_MERGE = True to keep it)")
            return False
        if NEAR_DUPLICATE_PIXELS and (_have["enabled"] is False or any(_have[k] != _want[k] for k in ("overlap_min", "pixel_size_m", "priority"))):
            if ACCEPT_PANEL_WITHOUT_PIXEL_MERGE:
                warn("this panel was built without the current near-duplicate pixel settings -- ACCEPT_PANEL_WITHOUT_PIXEL_MERGE=True, keeping it")
            else:
                warn(f"final panel exists but was built WITHOUT the current near-duplicate pixel merge ({_have} vs {_want}) "
                     f"-> will rebuild PASS B so pixels overlapping >= {PIXEL_OVERLAP_MIN:.0%} become one pixel "
                     f"(set ACCEPT_PANEL_WITHOUT_PIXEL_MERGE = True to keep the old panel)")
                return False
        ok(f"final panel valid: {path} ({nrows:,} rows, {len(cols)} columns) -- rebuild skipped (FORCE_REBUILD=True to redo)")
        return True
    except Exception as e:
        # v20.8: the file exists but cannot be opened AT ALL -> it is unusable however it got that way.
        # Always move it aside so no later step can read a half-written panel, and say plainly what happened.
        size = os.path.getsize(path) if os.path.exists(path) else 0
        truncated = ("magic bytes" in str(e).lower()) or size == 0 or ("footer" in str(e).lower())
        if truncated:
            warn(f"the panel on disk is INCOMPLETE ({size/1e9:.2f} GB, no Parquet footer). A Parquet file only gets "
                 f"its footer when the writer closes, so this is what an interrupted PASS B leaves behind -- "
                 f"not a data problem. Rebuilding.")
        else:
            warn(f"the panel on disk cannot be read ({str(e)[:120]}) -- rebuilding.")
        q = quarantine_file(path)
        if q: warn(f"moved aside: {os.path.basename(q)} -- delete it once the rebuild succeeds")
        return False

INPUT_EXTENSIONS = (".csv", ".csv.gz", ".tsv", ".parquet", ".pq", ".feather", ".xlsx", ".xlsm", ".xls")   # v20.14

def _input_ext(path):
    low = path.lower()
    for e in sorted(INPUT_EXTENSIONS, key=len, reverse=True):      # ".csv.gz" before ".csv"
        if low.endswith(e): return e
    return None

def discover_input_files(input_dir, output_dir=None, temp_dir=None, verbose=True):
    """v20.14: EVERY readable export under INPUT_DIR, any depth, any name -- csv / csv.gz / tsv / parquet /
    feather / xlsx / xlsm / xls -- minus anything that lives under the output or temp folders (generated, never
    source), Excel lock files (~$...), hidden files, and the crosswalk / fund-release workbooks if they happen to
    sit inside INPUT_DIR. Returns (files, n_excluded_as_output, n_seen)."""
    input_dir = os.path.abspath(input_dir)
    excl = [os.path.abspath(x) for x in (output_dir, temp_dir) if x]
    side = {os.path.abspath(x) for x in (SUBWSHED_CROSSWALK_PATH, FUND_RELEASE_PATH) if x}
    files, n_excl, n_seen = [], 0, 0
    for root, dirs, names in os.walk(input_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]          # generated folders are walked, then counted out
        for n in names:
            p = os.path.join(root, n)
            if _input_ext(p) is None or n.startswith((".", "~$")): continue
            n_seen += 1
            ap = os.path.abspath(p)
            if any(ap == e or ap.startswith(e + os.sep) for e in excl): n_excl += 1; continue
            if ap in side: continue
            files.append(p)
    if verbose:
        by = {}
        for f in files: by[_input_ext(f)] = by.get(_input_ext(f), 0) + 1
        print(f"Found {n_seen:,} readable files under {input_dir} ({n_excl} excluded as living under OUTPUT_DIR/TEMP_DIR) "
              f"-- {len(files):,} to process: " + ", ".join(f"{v} {k}" for k, v in sorted(by.items())))
        named = sum(1 for f in files if parse_filename(f) is not None)
        if named < len(files):
            print(f"[INFO]    {len(files) - named} file name(s) carry no Year/Season -- those keys will be read from the "
                  f"columns inside each file")
    return files, n_excl, n_seen

def _read_delimited(path, ext):
    """csv (pyarrow fast path), csv.gz, tsv -- one pandas frame."""
    if ext == ".csv": return _fast_read_csv(path)
    if ext == ".csv.gz": return pd.read_csv(path, compression="gzip", low_memory=False)
    return pd.read_csv(path, sep="\t", low_memory=False)

def _read_feather_export(path):
    try:
        import pyarrow.feather as _pf; return _pf.read_table(path).to_pandas()
    except Exception:
        return pd.read_feather(path)

def _read_parquet_export(path):
    """A Parquet export, read with pyarrow directly (no pandas engine detour)."""
    try:
        return pq.read_table(path).to_pandas()
    except Exception:
        return pd.read_parquet(path)

def _sheet_is_data(cols):
    """A sheet is a DATA sheet when its columns resolve to the pixel coordinates (the harmoniser knows every
    alias). A crosswalk, a lookup table or a notes sheet does not qualify and is skipped, not failed."""
    try:
        cm = harmonize_columns(list(cols), fname="<sheet>", unresolved_log=[])
    except Exception:
        return False
    names = {cm.get(c, c) for c in cols}
    return {"latitude", "longitude"} <= names

def _read_excel_export(path, parse_errors_log=None):
    """v20.14: an Excel workbook is read like a CSV -- every sheet whose columns are pixel data is a table, and
    the tables are stacked. Year/Season come from the file name, else from the sheet name, else from columns.
    Workbooks without a data sheet (the crosswalk, the fund-release table, notes) are skipped with a message."""
    engine = "xlrd" if path.lower().endswith(".xls") else "openpyxl"
    sheets = pd.read_excel(path, sheet_name=None, engine=engine)
    frames = []
    for name, sh in sheets.items():
        if sh is None or sh.shape[0] == 0 or not _sheet_is_data(sh.columns):
            continue
        sh = sh.copy()
        if parse_filename(path) is None and not ({"Year", "Season"} <= set(sh.columns)):
            fm = parse_filename(f"CSV_{name}.csv")            # let a sheet named like an export carry its own key
            if fm is not None:
                sh["Year"], sh["Season"] = fm["Year"], fm["Season"]
        frames.append(sh)
    if not frames:
        if parse_errors_log is not None:
            parse_errors_log.append(f"{path} (skipped: no sheet with pixel latitude/longitude -- not a data export)")
        return None
    return pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

def read_export_raw(path, nrows=None):
    """v20.55: ONE export as the exporter wrote it (no renaming) -- every format the pipeline reads, for the dry runs and
    checks. nrows limits a CSV read; other formats are read whole and cut."""
    ext = _input_ext(path)
    if ext in (".csv", ".csv.gz", ".tsv"):
        if nrows is not None:
            return pd.read_csv(path, nrows=nrows, sep="\t" if ext == ".tsv" else ",", compression="gzip" if ext == ".csv.gz" else None, low_memory=False)
        return _read_delimited(path, ext)
    if ext in (".parquet", ".pq"): df = _read_parquet_export(path)
    elif ext == ".feather": df = _read_feather_export(path)
    elif ext in (".xlsx", ".xlsm", ".xls"): df = _read_excel_export(path, None)
    else: raise ValueError(f"unsupported export format: {path}")
    if df is None: raise ValueError(f"no data sheet in {path}")
    return df.head(nrows) if nrows is not None else df

def load_and_harmonize(path, unresolved_log=None, parse_errors_log=None):
    ext = _input_ext(path)
    try:
        if ext in (".csv", ".csv.gz", ".tsv"):
            df = _read_delimited(path, ext)
        elif ext in (".parquet", ".pq"):
            df = _read_parquet_export(path)                     # v20.14: pyarrow, same rows as a CSV export
        elif ext == ".feather":
            df = _read_feather_export(path)
        elif ext in (".xlsx", ".xlsm", ".xls"):
            df = _read_excel_export(path, parse_errors_log)    # v20.14: every data sheet of the workbook
            if df is None: return None
        else:
            if parse_errors_log is not None:
                parse_errors_log.append(f"{path} (unsupported extension, skipped)")
            return None
    except Exception as e:
        if parse_errors_log is not None:
            parse_errors_log.append(f"{path} (read error: {e})")
        return None

    colmap = dedupe_mapping(harmonize_columns(df.columns, fname=os.path.basename(path), unresolved_log=unresolved_log),
                            fname=os.path.basename(path), unresolved_log=unresolved_log)
    df = df.rename(columns=colmap)
    df = df.drop(columns=[c for c in OLD_ARTIFACT_COLS if c in df.columns])
    is_new_schema = "DataYear" in df.columns
    for c in NEW_ONLY_COLS:
        if c not in df.columns:
            df[c] = np.nan

    # v20.14: the block key. The file name is used for whatever it states (year, season, or both); anything it
    # does not state is read from the Year / Season columns inside the file. A file is rejected only when NEITHER
    # source gives a key. The name wins over the columns when both exist (an export's name is set by the
    # exporter; a stray column is not), and a disagreement is logged so it can be inspected.
    fmeta = parse_filename(path)
    have_cols = {"Year", "Season"} <= set(df.columns)
    for key in ("Year", "Season"):
        from_name = fmeta.get(key) if fmeta else None
        if from_name is not None:
            if key in df.columns:
                col = pd.to_numeric(df[key], errors="coerce")
                if key == "Season" and df[key].dtype == object:
                    col = df[key].astype(str).str.strip().str.lower().map(SEASON_CODE).where(col.isna(), col)
                vals = set(col.dropna().astype(int).unique().tolist())
                if vals and vals != {int(from_name)} and unresolved_log is not None:
                    unresolved_log.append(f"{os.path.basename(path)}: {key} in name = {from_name} but column holds "
                                          f"{sorted(vals)[:5]} -- name used")
            df[key] = int(from_name)
        elif key in df.columns:
            col = pd.to_numeric(df[key], errors="coerce")
            if key == "Season":
                lab = df[key].astype(str).str.strip().str.lower().map(SEASON_CODE)
                col = col.where(col.notna(), lab)
            if col.isna().any():
                if parse_errors_log is not None:
                    parse_errors_log.append(f"{path}: {key} missing in the name and not readable for "
                                            f"{int(col.isna().sum()):,} rows of the {key} column")
                return None
            df[key] = col.astype(int)
        else:
            if parse_errors_log is not None:
                parse_errors_log.append(f"{path}: cannot determine {key} -- not in the file name and no {key} column")
            return None

    # v20.27: Treat is a PERIOD flag the panel never relies on (post is computed from Year by the rule), so an export
    # without it is not rejected -- Treat is derived from the rule Treat = 1{Year >= TREATMENT_YEAR} and logged
    if "Treat" not in df.columns and "Year" in df.columns:
        df["Treat"] = (pd.to_numeric(df["Year"], errors="coerce") >= TREATMENT_YEAR).astype("float64")
        if unresolved_log is not None:
            unresolved_log.append((os.path.basename(path), f"Treat not in the source -> derived from the rule (1 for Year >= {TREATMENT_YEAR})"))
    missing_essential = [c for c in ESSENTIAL_COLS if c not in df.columns]
    if missing_essential:
        if parse_errors_log is not None:
            parse_errors_log.append(f"{path}: REJECTED, missing essential columns {missing_essential}")
        return None

    missing_lenient = [c for c in OUTCOME_VARS + OTHER_CORE_LENIENT if c not in df.columns]
    for c in missing_lenient:
        df[c] = np.nan
    df["missing_source_cols"] = ",".join(missing_lenient) if missing_lenient else ""
    if missing_lenient and parse_errors_log is not None:
        parse_errors_log.append(f"{path}: outcome columns filled NaN (not present in source): {missing_lenient}")

    # v20.27: buffer codes are RECODED (text like "1 km" / "Buffer_3" / "ring-4" keeps its ring number) before the
    # numeric cast -- a plain to_numeric turned them into blanks, silently dropping those rows from both groups
    if "buff_km" in df.columns:
        df["buff_km"], _bchg = recode_buff_km(df["buff_km"].values)
        if _bchg and unresolved_log is not None:
            unresolved_log.append((os.path.basename(path), "buff_km recoded: " + ", ".join(f"{k!r}->{v}" for k, v in list(_bchg.items())[:8])))
    for c in ESSENTIAL_COLS + OUTCOME_VARS + OTHER_CORE_LENIENT + NEW_ONLY_COLS:
        if c == "buff_km": continue
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["schema_vintage"] = "2026plus" if is_new_schema else "2015_2025"
    df["src_file"] = os.path.basename(path)
    try:
        df["file_mtime"] = os.path.getmtime(path)   # proxy for "date of download/generation" --
    except OSError:                                  # used to prioritize corrected/newer files
        df["file_mtime"] = np.nan                     # in resolve_duplicates (Step 6b)
    # v14: RETAIN only canonical columns (all variables/coefficients + DiD keys); DROP any
    # unmatched extras from newer exports -- logged, never silent.
    _INTERNAL = {"src_file","file_mtime","schema_vintage","external_uid_final","missing_source_cols",
                 "site_name","site_match_strategy","pixel_id","subwshed_id","time_fe_year",
                 "time_fe_yearseason","row_id","season_sort_rank","treat_legacy"}
    _extras = [c for c in df.columns if c not in CANONICAL and c not in _INTERNAL]
    if _extras:
        df = df.drop(columns=_extras)
        if unresolved_log is not None:
            for c in _extras: unresolved_log.append((os.path.basename(path), f"DROPPED:{c}"))
    site_name, site_match_strategy = extract_site_name(path, KNOWN_SUBWSHED_NAMES)
    df["site_name"] = site_name
    df["site_match_strategy"] = site_match_strategy
    if "external_uid_final" not in df.columns:
        df["external_uid_final"] = np.nan

    keep_cols = (ESSENTIAL_COLS + OUTCOME_VARS + OTHER_CORE_LENIENT + NEW_ONLY_COLS + [c_ for c_ in ("SWSiD_All", "SWS_Name") if c_ in df.columns] +
                 ["schema_vintage", "src_file", "file_mtime", "missing_source_cols", "external_uid_final",
                  "site_name", "site_match_strategy"])
    keep_cols = list(dict.fromkeys(keep_cols))   # v16.1: a name in two lists once produced DUPLICATE columns
    assert not df[keep_cols].columns.duplicated().any(), "duplicate columns in harmonised frame"
    return df[keep_cols]


def recode_buff_km(values):
    """v20.27: buffer codes -> exact integers 0..5 (VALID_BUFFERS). Accepts numbers (0, 1.0, 1.0000001 from sampling a
    float band -> nearest integer when within 0.01) and text carrying a number ("1 km", "Buffer_2", "ring 3").
    Anything else, or outside 0..5, becomes -1 (neither treatment nor control) and is counted. Returns
    (int8 array, {original value: recoded value} for every value that changed)."""
    raw = pd.Series(np.asarray(values))
    num = pd.to_numeric(raw, errors="coerce")
    txt = raw[num.isna() & raw.notna()].astype(str)
    if len(txt):   # the first number in the text; a leading '-' is a sign, a '-' after a word is a separator ("ring-2")
        _mag = pd.to_numeric(txt.str.extract(r"(\d+(?:\.\d+)?)")[0], errors="coerce")
        _neg = txt.str.strip().str.startswith("-")
        num.loc[txt.index] = np.where(_neg, -_mag, _mag)
    r = np.rint(num.values.astype(np.float64))
    okv = np.isfinite(r) & (np.abs(num.values.astype(np.float64) - r) <= 0.01) & np.isin(r, VALID_BUFFERS)
    out = np.where(okv, r, -1).astype("int8")
    changed = {}
    m = raw.astype(str).values != pd.Series(out).astype(str).values
    if m.any():
        vc = pd.DataFrame({"orig": raw[m].astype(str).values, "new": out[m]}).drop_duplicates()
        changed = dict(zip(vc["orig"], vc["new"].astype(int)))
    return out, changed

def data_qc(df):
    flat = {}
    for var in OUTCOME_VARS:
        nunique = df.groupby("src_file")[var].transform("nunique")
        flat[f"{var}_flat_flag"] = (nunique <= 1).astype("int8")
    for k, v in flat.items():
        df[k] = v
    df["any_outcome_flat_flag"] = (df[[f"{v}_flat_flag" for v in OUTCOME_VARS]].sum(axis=1) > 0).astype("int8")

    # v20.27: buffer codes recoded to exact integers (buffer 0 = treatment area, 1-5 km = control area)
    df["buff_km"], _chg = recode_buff_km(df["buff_km"].values)
    df.attrs["buff_km_recoded"] = {str(k): int(v) for k, v in _chg.items()}
    df["buffkm_out_of_range_flag"] = (df["buff_km"].values < 0).astype("int8")
    # v20.27: the export's Treat is a PERIOD flag (the exporter writes 1 for EVERY pixel from the treatment year on),
    # so it is checked against the rule Treat = 1{Year >= TREATMENT_YEAR}. (The old flag compared it with the treatment
    # AREA -- buffer 0 -- and marked every treated pixel before 2022 and every control pixel after it as a "mismatch".)
    # The panel never takes the period from Treat: post is always computed from Year.
    _rule = (pd.to_numeric(df["Year"], errors="coerce") >= TREATMENT_YEAR).astype("int8")
    _treat = pd.to_numeric(df["Treat"], errors="coerce") if "Treat" in df.columns else pd.Series(np.nan, index=df.index)
    df["treat_period_mismatch_flag"] = (_treat.notna() & (_treat.round() != _rule)).astype("int8")
    df["outcome_missing_flag"] = df[OUTCOME_VARS].isna().any(axis=1).astype("int8")
    return df


# ====================== v20.28: WHICH SUB-WATERSHED EVERY PIXEL IS IN (shapefile SWSs20_KarnatakaAll5k) ======================
SITE_GEOMETRY_CHECK = True     # verify / assign each row's SWS from its latitude-longitude and the 20-SWS shapefile
BUFF_FROM_GEOMETRY = False     # True = buff_km always from the polygon ring; False = only where the SWS was corrected /
                               # assigned (the exported ring is kept where the SWS is confirmed; disagreements reported)
_LOCATOR = {"obj": None, "err": None}

def _sws_locator():
    """The shapefile locator, built once per process (< 1 s); None when the shapefile is unavailable."""
    if _LOCATOR["obj"] is None and _LOCATOR["err"] is None:
        try:
            import _sws_geometry as _G
            _LOCATOR["obj"] = _G.SWSLocator.from_shapefile()
        except Exception as _e:
            _LOCATOR["err"] = f"{type(_e).__name__}: {_e}"
    return _LOCATOR["obj"]

def _relative_hint(path):
    """The part of a file path that can name its SWS (folders under INPUT_DIR + file name)."""
    try:
        base = globals().get("INPUT_DIR")
        rel = os.path.relpath(path, base) if base and os.path.abspath(path).startswith(os.path.abspath(base)) else path
    except Exception:
        rel = path
    return rel.replace("\\", "/")

def site_tagging_by_sws(st_):
    """v20.39: one row per shapefile sub-watershed: rows the overlay placed there, and how the id the files carried
    compared -- confirmed (same id), carried another id, or carried none."""
    from collections import Counter as _Ctr
    col = "id_pairs_all" if "id_pairs_all" in st_.columns else "id_pairs"
    tot, same, other = _Ctr(), _Ctr(), _Ctr()
    for _s in (st_[col].fillna("") if col in st_.columns else []):
        for _t in str(_s).split(";"):
            if ">" in _t and ":" in _t:
                _a, _r = _t.split(">"); _b, _k = _r.split(":"); a, b, k = int(_a), int(_b), int(_k)
                tot[b] += k; (same if a == b else other)[b] += k
    nm = _sites_names()
    rows = [{"site_id": b, "sws_name": nm.get(b, "?"), "rows": tot[b], "file_id_confirmed": same[b],
             "file_id_different": other[b], "share_confirmed": round(same[b] / tot[b], 4) if tot[b] else None} for b in sorted(tot)]
    return pd.DataFrame(rows)

def site_id_mapping(st_):
    """v20.37: which export id labels the points of which shapefile SWS, over EVERY tagged row, and whether that is a
    consistent RENUMBERING: each shapefile SWS carries ONE export id (>= 99 % of its rows) and each export id labels ONE
    SWS, with at least one id different. A SWS whose points carry two ids (e.g. 75 % correct, 25 % another id) is a
    labelling error, not a renumbering. Returns (mapping table, is_renumbering)."""
    from collections import Counter as _Ctr
    col = "id_pairs_all" if "id_pairs_all" in st_.columns else "id_pairs"
    _pc = _Ctr()
    for _s in (st_[col].fillna("") if col in st_.columns else []):
        for _t in str(_s).split(";"):
            if ">" in _t and ":" in _t:
                _a, _r = _t.split(">"); _b, _k = _r.split(":"); _pc[(int(_a), int(_b))] += int(_k)
    _mp = pd.DataFrame([(a, b, k) for (a, b), k in _pc.items()], columns=["export_id", "shapefile_id", "rows"])
    if not len(_mp): return _mp, False
    _mp["share_of_export_id"] = _mp["rows"] / _mp.groupby("export_id")["rows"].transform("sum")
    _mp["share_of_shapefile_sws"] = _mp["rows"] / _mp.groupby("shapefile_id")["rows"].transform("sum")
    _nm = _sites_names(); _mp["shapefile_name"] = _mp["shapefile_id"].map(lambda x: _nm.get(int(x), "?"))
    _mp["relation"] = np.where(_mp.export_id == _mp.shapefile_id, "same id", "different id")
    _mp["export_id_is_sws"] = _mp["export_id"].map(lambda x: _nm.get(int(x), "not a shapefile id"))   # v20.38
    _dom_e = _mp.groupby("export_id")["share_of_export_id"].max() >= 0.99
    _dom_s = _mp.groupby("shapefile_id")["share_of_shapefile_sws"].max() >= 0.99
    _one = bool(_dom_e.all() and _dom_s.all() and (_mp[_mp.share_of_export_id >= 0.99].relation == "different id").any())
    return _mp.sort_values(["shapefile_id", "rows"], ascending=[True, False]).reset_index(drop=True), _one

def _sites_names():
    """{shapefile id: sub-watershed name} for reports -- the same locator tag_sites uses (empty if unavailable)."""
    try:
        return {int(k): str(v) for k, v in (_sws_locator().names or {}).items()}
    except Exception:
        try:
            import _sites as _S_
            return {int(r): str(_S_.name(int(r))) for r in range(1, 21)}
        except Exception:
            return {}

def tag_fragments(df, stats=None):
    """v20.57 -- YOUR RULE: the major sub-watershed data are processed, smaller fragments of other sub-watersheds are dropped.
    Per export file: its OWN sub-watershed is the one holding more than half of its rows that lie inside a polygon; every
    row gets a code (0 its own / no majority, 1 inside another sub-watershed's polygon, 2 outside every polygon with another
    id -- _fragments.py). The panel keeps every row with its code: FRAGMENT_RULE ("drop" / "keep") is applied by the MODELS,
    so it can be changed without rebuilding the panel."""
    import _fragments as _FR
    stats = dict(stats or {})
    if not len(df) or "site_id" not in df.columns:
        df["fragment"] = np.zeros(len(df), dtype=np.int8); stats.update({"file_sws": 0, "fragment_rows_other_sws": 0, "fragment_rows_outside_other_id": 0})
        return df, stats
    chk = df["site_check"].values if "site_check" in df.columns else np.full(len(df), 4)
    codes, major = _FR.file_codes(df["site_id"].values, chk)
    df["fragment"] = codes
    stats.update({"file_sws": int(major) if major is not None else 0, "fragment_rows_other_sws": int((codes == 1).sum()),
                  "fragment_rows_outside_other_id": int((codes == 2).sum())})
    return df, stats

def tag_sites(df, path=None):
    """Adds site_id (SWSiD_All 1..20), sws_name and site_check to every row and returns (df, stats).
    The SWS the DATA indicates is read, in order, from a SWSiD_All column, a SWS name column (SUBWSHED / SWS_Name),
    the folder or file name (e.g. SWSs20Final/Artal/...), or the site name found earlier. Each row's latitude /
    longitude is then located in the shapefile:
      confirmed  the point lies in a polygon of the indicated SWS (overlapping rings of a neighbour are fine)
      corrected  the indicated SWS is wrong -> the SWS whose polygon holds the point (core first, then lower id)
      assigned   the data indicates no SWS -> the SWS whose polygon holds the point
      outside    in no polygon -> the indicated SWS is kept and the row flagged
    Where the SWS was corrected or assigned, buff_km is taken from that SWS's ring (the exported ring belonged to
    another SWS); where it was confirmed, a different exported ring is reported, not overwritten, unless
    BUFF_FROM_GEOMETRY = True."""
    import _sws_geometry as _G
    n = len(df)
    L = _sws_locator() if SITE_GEOMETRY_CHECK else None
    ind = np.zeros(n, dtype=np.int64); source = "none"
    if "SWSiD_All" in df.columns:
        v = pd.to_numeric(df["SWSiD_All"], errors="coerce").fillna(0).astype(np.int64).values
        if (v > 0).any(): ind = v; source = "SWSiD_All column"
    if not (ind > 0).any() and "SWS_Name" in df.columns:
        nm = df["SWS_Name"].astype(str)
        num = pd.to_numeric(nm, errors="coerce")
        if num.notna().mean() > 0.9:
            ind = num.fillna(0).astype(np.int64).values; source = "SWS_Name column (ids)"
        else:
            lookup = {}
            for u in nm.unique():
                sid = (L.site_id_for_name(u) if L is not None else None)
                if sid is None:
                    try:
                        import _sites as _S; sid = _S.site_id(u)
                    except Exception:
                        sid = None
                lookup[u] = int(sid or 0)
            ind = nm.map(lookup).fillna(0).astype(np.int64).values
            if (ind > 0).any(): source = "SWS_Name column"
    if not (ind > 0).any() and path is not None and L is not None:
        sid = L.site_id_for_name(_relative_hint(path))
        if sid: ind = np.full(n, int(sid), dtype=np.int64); source = "folder / file name"
    if not (ind > 0).any() and "site_name" in df.columns and len(df):
        try:
            import _sites as _S
            sid = (L.site_id_for_name(df["site_name"].iloc[0]) if L is not None else None) or _S.site_id(df["site_name"].iloc[0])
        except Exception:
            sid = None
        if sid: ind = np.full(n, int(sid), dtype=np.int64); source = "site name"
    stats = {"rows": int(n), "indicated_from": source}
    if L is None or not {"latitude", "longitude"} <= set(df.columns):
        df["site_id"] = ind.astype("int16")
        df["site_check"] = np.int8(_G.NO_GEOMETRY)
        names = {}
        try:
            import _sites as _S; names = {int(k): str(_S.name(k)) for k in np.unique(ind) if k > 0}
        except Exception:
            pass
        df["sws_name"] = pd.Series(ind).map(names).fillna("").values
        stats.update({"not_checked": int(n), "reason": _LOCATOR.get("err") or ("SITE_GEOMETRY_CHECK = False" if not SITE_GEOMETRY_CHECK else "no coordinates")})
        return df, stats
    site, buff, check = L.tag(pd.to_numeric(df["latitude"], errors="coerce").values,
                              pd.to_numeric(df["longitude"], errors="coerce").values, ind)
    bk = pd.to_numeric(df["buff_km"], errors="coerce").values if "buff_km" in df.columns else np.full(n, np.nan)
    moved = (check == _G.CORRECTED) | (check == _G.ASSIGNED)
    take = (moved | ((check == _G.CONFIRMED) & bool(BUFF_FROM_GEOMETRY))) & (buff >= 0)
    ring_disagree = (check == _G.CONFIRMED) & (buff >= 0) & (bk != buff)
    if "buff_km" in df.columns and take.any():
        newb = bk.copy(); newb[take] = buff[take]
        df["buff_km"] = pd.Series(newb).fillna(-1).astype("int8").values
    df["site_id"] = site.astype("int16")                      # the sub-watershed the shapefile OVERLAY puts the point in
    df["sws_id_export"] = np.asarray(ind).astype("int16")    # v20.39: the id the input file carried (0 = none) -- kept,
                                                             # so every row can be audited against the overlay
    df["sws_name"] = pd.Series(site).map({k: v for k, v in L.names.items()}).fillna("").values
    df["site_check"] = check.astype("int8")
    # v20.37: what the correction actually CHANGED -- the ring value, and treated <-> control -- and which export id
    # became which shapefile id (a consistent renumbering is a relabel, not an error)
    _fin = np.isfinite(bk) & (buff >= 0)
    stats["buff_km_changed_on_corrected"] = int((moved & _fin & (bk != buff)).sum())
    stats["treated_status_changed"] = int((moved & _fin & ((bk == 0) != (buff == 0))).sum())
    # every tagged row: (export id -> the SWS that holds the point); confirmed rows map to their own id
    _vm = (ind > 0) & (site > 0) & ((check == _G.CONFIRMED) | (check == _G.CORRECTED))
    if _vm.any():
        _to = np.where(check == _G.CONFIRMED, ind, site)
        _pa, _pk = np.unique(np.stack([ind[_vm].astype(np.int64), _to[_vm].astype(np.int64)]), axis=1, return_counts=True)
        stats["id_pairs_all"] = ";".join(f"{int(a)}>{int(b)}:{int(k)}" for (a, b), k in zip(_pa.T, _pk))
    _cm = check == _G.CORRECTED
    if _cm.any():
        _pr, _pn = np.unique(np.stack([ind[_cm].astype(np.int64), site[_cm].astype(np.int64)]), axis=1, return_counts=True)
        stats["id_pairs"] = ";".join(f"{int(a)}>{int(b)}:{int(k)}" for (a, b), k in zip(_pr.T, _pn))
    stats.update({"confirmed": int((check == _G.CONFIRMED).sum()), "corrected": int((check == _G.CORRECTED).sum()),
                  "assigned": int((check == _G.ASSIGNED).sum()), "outside_all_polygons": int((check == _G.OUTSIDE).sum()),
                  "buff_km_taken_from_polygon": int(take.sum()),
                  "buff_km_differs_from_polygon_ring": int(ring_disagree.sum()),
                  "sites": ";".join(f"{int(k)}:{L.names.get(int(k), '?')}" for k in np.unique(site) if k > 0),
                  "indicated_sites": ";".join(str(int(k)) for k in np.unique(ind) if k > 0)})
    return df, stats

def _audit_worker(args):
    """One file: read + harmonise, tag the SWS of every row, optionally write a tagged copy. Returns a report row."""
    import importlib
    m = importlib.import_module("_prep_common")
    path, copy_dir, input_dir = args
    u, e = [], []
    try:
        df = m.load_and_harmonize(path, unresolved_log=u, parse_errors_log=e)
        if df is None:
            return {"file": path, "status": "unreadable", "detail": "; ".join(e)[:300]}
        df, st = m.tag_sites(df, path)
        row = {"file": path, "status": "ok", **st}
        if copy_dir:
            rel = os.path.relpath(path, input_dir) if input_dir and os.path.abspath(path).startswith(os.path.abspath(input_dir)) else os.path.basename(path)
            dst = os.path.join(copy_dir, os.path.splitext(rel)[0] + ".parquet")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            out = df.copy()
            out["SWSiD_All"] = out["site_id"].astype("int16")          # the VERIFIED id, under the shapefile's column name
            out["SUBWSHED"] = out["sws_name"].astype(str)              # and the shapefile's name column
            pq.write_table(pa.Table.from_pandas(out.drop(columns=["site_id", "sws_name"]), preserve_index=False), dst)
            row["tagged_copy"] = dst
        return row
    except Exception as ex:
        return {"file": path, "status": f"failed: {type(ex).__name__}", "detail": str(ex)[:300]}

def audit_site_tags(input_dir=None, output_dir=None, write_copies=False, n_workers=None, verbose=True):
    """v20.28: scan EVERY data file under input_dir (any format, any depth -- the same discovery as PASS A), locate
    every row in the 20-SWS shapefile and report per file which rows were confirmed / corrected / assigned / outside.
    write_copies=True writes a tagged copy of each file (Parquet, same folder structure) under
    <output>/tagged_inputs/ with the verified SWSiD_All and SUBWSHED columns -- the originals are never modified.
    Returns the report DataFrame (also written to <output>/site_tagging_audit.csv)."""
    input_dir = input_dir or INPUT_DIR; output_dir = output_dir or OUTPUT_DIR
    files, _n_excl, _n_seen = discover_input_files(input_dir, output_dir, None, verbose=False)   # outputs never re-read
    copy_dir = os.path.join(output_dir, "tagged_inputs") if write_copies else None
    if verbose: info(f"SWS audit: {len(files):,} data files under {input_dir}" + (f"; tagged copies -> {copy_dir}" if copy_dir else ""))
    if _sws_locator() is None:
        raise RuntimeError(f"the 20-SWS shapefile could not be read: {_LOCATOR.get('err')}")
    try:
        import _hardware as _H; n_workers = n_workers or _H.worker_cap(n_tasks=len(files))
    except Exception:
        n_workers = n_workers or max(1, min(60, os.cpu_count() or 1))   # v20.57: every core (the fall-back too)
    tasks = [(f, copy_dir, input_dir) for f in files]
    rows = []
    if n_workers > 1 and len(files) > 1:
        import concurrent.futures as cf, multiprocessing as mp
        cfg = _settings_snapshot()                                   # v20.58: every setting (was: four of them)
        ctx = mp.get_context("spawn")
        with cf.ProcessPoolExecutor(max_workers=int(n_workers), mp_context=ctx, initializer=_pa_worker_init,
                                    initargs=(os.path.dirname(os.path.abspath(__file__)), list(KNOWN_SUBWSHED_NAMES), cfg)) as ex:
            for r in progress(ex.map(_audit_worker, tasks, chunksize=4), total=len(tasks), desc="SWS audit", unit="file"):
                rows.append(r)
    else:
        for t in progress(tasks, desc="SWS audit", unit="file"):
            rows.append(_audit_worker(t))
    rep = pd.DataFrame(rows)
    os.makedirs(output_dir, exist_ok=True); rep.to_csv(os.path.join(output_dir, "site_tagging_audit.csv"), index=False)
    if verbose and len(rep):
        cols = [c for c in ("rows", "confirmed", "corrected", "assigned", "outside_all_polygons", "buff_km_differs_from_polygon_ring") if c in rep.columns]
        tot = {c: int(pd.to_numeric(rep[c], errors="coerce").fillna(0).sum()) for c in cols}
        ok(f"SWS audit of {len(rep):,} files: " + ", ".join(f"{k} {v:,}" for k, v in tot.items()) + f" -> {os.path.join(output_dir, 'site_tagging_audit.csv')}")
        bad_ = rep[rep["status"] != "ok"]
        if len(bad_): warn(f"{len(bad_)} file(s) could not be audited: {bad_['file'].head(3).tolist()}")
        if "indicated_from" in rep.columns:
            info("where each file's SWS came from: " + str(rep["indicated_from"].value_counts().to_dict()))
    return rep

def build_fe_and_treatment(df):
    """FE/naming columns only (unit and time identifiers) -- these don't depend on any
    treatment-timing or control-zone CHOICE, so they're safe to compute once, globally.
    Treatment/control/period assignment itself now lives in build_treatment_columns()
    (next cell) and is computed FRESH, per call, by every estimator module -- see Step 6c."""
    def _sws(x):                                  # v20.5: SubwshedID may arrive numeric (3) or already as text ("SW3")
        if pd.isna(x): return "SW_NA"
        if isinstance(x, str):
            t = x.strip()
            if t.upper().startswith("SW"): return "SW" + t[2:].strip()
            try: return f"SW{float(t):.0f}"
            except ValueError: return t or "SW_NA"
        return f"SW{x:.0f}"
    df["subwshed_id"] = df["SubwshedID"].map(_sws)
    # v20.28: site identity is verified against the 20-SWS shapefile (tag_sites); PASS A tags BEFORE de-duplication,
    # so here an existing tag is kept and only untagged frames (direct callers) are tagged
    if "site_id" not in df.columns:
        df, _ = tag_sites(df)
    df["time_fe_year"] = df["Year"].astype(str)
    df["time_fe_yearseason"] = df["Year"].astype(str) + "_" + df["Season"].map(SEASON_LABEL)
    df["time_fe_season"] = df["Season"].map(SEASON_LABEL)          # v15.1: season-only FE for the additive spec
    # v20.5: pixel_id is int64 since v17.6 (8 bytes instead of a ~60-byte string), so row_id must CONVERT it.
    # Concatenating an int64 Series with "_" raised UFuncTypeError in PASS A -- the regression this fixes.
    df["row_id"] = (df["pixel_id"].astype("string") + "_" + df["Year"].astype("string") + "_"
                    + df["Season"].map(SEASON_LABEL).astype("string"))
    df["season_sort_rank"] = df["Season"].map(SEASON_SORT_RANK)
    df["treat_legacy"] = df["Treat"]   # original column, kept only for the legacy robustness check
    return df


def export_post_flag(df):
    """v20.59: the exports' Treat flag as the post indicator -- 1.0 (post) / 0.0 (pre) per row, NaN where a row has no usable flag (no Treat
    column, a blank, or a value other than 0 / 1). The exporter writes Treat = 1 for EVERY pixel from its treatment year on (1 = post,
    0 = pre); it says nothing about the treatment AREA (that is buff_km 0)."""
    if "Treat" not in df.columns: return None
    v = pd.to_numeric(df["Treat"], errors="coerce").values.astype("float64")
    ok_ = np.isfinite(v) & ((v == 0) | (v == 1))
    return np.where(ok_, v, np.nan)


PANEL_DESIGN_COLUMNS = ("treat", "control", "pre", "post", "did")   # v20.59: the DiD columns every model reads -- the same names in R's panel

def build_treatment_columns(df, control_zones=DEFAULT_CONTROL_ZONES, treatment_year=TREATMENT_YEAR,
                             pre_cutoff=None, post_cutoff=POST_CUTOFF, year_col="Year",
                             exclude_transition_year=None):
    """v14 -- YOUR SPECIFICATION, implemented literally:
        treatment  = 1 where buff_km == 0, else 0                          (alias treat -- v20.59)
        control    = 1 where buff_km in {1,2,3,4,5}, else 0
        post       = the exports' Treat flag: 1 = post, 0 = pre (v20.59, POST_FROM_EXPORT_TREAT); a row without a usable flag: Year >= 2022
        pre        = 1 - post
        did_term   = treatment * post                                      (alias did -- v20.59)
    The earlier names (treat_core, control_zone_selected, pre_period, post_period) are kept as
    exact aliases so every model notebook keeps working unchanged.
    exclude_transition_year=True restores the earlier design that drops 2022 from BOTH periods (the rule, not the flag: the flag
    cannot say 'neither period').
    These are the panel's DEFAULT design (the exporter's timing). Every model rebuilds them for ITS design when it runs
    (_common.build_treatment_columns) and reports on how many rows the two differ."""
    out = df.copy()
    bk = pd.to_numeric(out["buff_km"], errors="coerce")
    out["treatment"] = (bk == TREAT_CORE_BUFFKM).astype("int8")
    out["control"]   = bk.isin(list(control_zones)).astype("int8")
    # v20.26: the same transition-year rule as the model engine (informational columns in the panel; every model
    # recomputes them for its own scenario)
    if exclude_transition_year is None: exclude_transition_year = EXCLUDE_TRANSITION_YEAR
    _yr = pd.to_numeric(out[year_col], errors="coerce")
    if exclude_transition_year:
        _post_start = max(int(post_cutoff), int(treatment_year) + 1)
        rule_post = (_yr >= _post_start).astype("int8").values
        rule_pre = (_yr < int(treatment_year)).astype("int8").values
    else:
        rule_post = (_yr >= int(post_cutoff)).astype("int8").values
        rule_pre = (_yr < int(post_cutoff)).astype("int8").values
    # v20.59 -- YOUR RULE: post / pre from the exports' Treat flag (1 = post, 0 = pre) where a row has one; the rule where it has none
    flag = export_post_flag(out) if (POST_FROM_EXPORT_TREAT and not exclude_transition_year) else None
    if flag is not None:
        _ok = np.isfinite(flag)
        out["post"] = np.where(_ok, flag, rule_post).astype("int8")
        out["pre"] = (1 - out["post"].values).astype("int8")
        out.attrs["post_from_export_flag"] = int(_ok.sum()); out.attrs["post_from_rule"] = int((~_ok).sum())
        out.attrs["post_flag_vs_rule_differ"] = int((_ok & (np.nan_to_num(flag, nan=-1) != rule_post)).sum())
    else:
        out["post"] = rule_post.astype("int8"); out["pre"] = rule_pre.astype("int8")
        out.attrs["post_from_export_flag"] = 0; out.attrs["post_from_rule"] = int(len(out)); out.attrs["post_flag_vs_rule_differ"] = 0
    out["did_term"] = (out["treatment"] * out["post"]).astype("int8")
    out["treat"] = out["treatment"]; out["did"] = out["did_term"]     # v20.59: the DiD names every model (and R's panel) reads
    # aliases used by the 45 model notebooks
    out["treat_core"] = out["treatment"]; out["control_zone_selected"] = out["control"]
    out["pre_period"] = out["pre"];       out["post_period"] = out["post"]
    out["in_analysis_sample"] = ((out["treatment"] == 1) | (out["control"] == 1)).astype("int8")
    out["event_time"] = out[year_col] - treatment_year
    if "season_sort_rank" in out.columns:
        out["period_index"] = out[year_col].astype(int) * 10 + out["season_sort_rank"].astype(int)
    else:
        out["period_index"] = out[year_col].astype(int) * 10
    return out


DEDUP_KEYS = ("site_id", "pixel_id", "Year", "Season")   # v20.22: site-aware -- ring overlaps between sites are not duplicates

def resolve_duplicates(df, group_keys=None, conflict_log=None,
                       recency_col="file_mtime", recency_margin_seconds=1.0, fill_from_duplicates=None):
    """One row per (pixel_id, Year, Season). v20.12: VECTORISED -- the previous version looped in Python over
    every duplicate group (~7 ms each), which is why a block with 3.7 M duplicate groups took 9 hours.
    Same priority order as before, applied to all groups at once:
      1. exact duplicates -> any copy
      2. NEWER FILE WINS (mtime differs by more than `recency_margin_seconds`)
      3. fewer missing outcome values wins
      4. higher NObsV wins
      5. newer schema_vintage wins
      6. alphabetical src_file (logged AMBIGUOUS)
    v20.58 -- YOUR RULE "repeated rows are dropped": the kept row is taken AS IT IS; no value of a dropped (repeated) row
    enters the panel, not even into a gap of the kept row (DEDUP_FILL_FROM_DUPLICATES = False, the default). Until v20.57
    the kept row's missing outcome values were FILLED from the dropped rows -- a cloud gap of the newer export took the
    older export's value of that pixel-period, so a repeated row's number reached the models (the poison test found it).
    DEDUP_FILL_FROM_DUPLICATES = True (or fill_from_duplicates=True) restores that fill, in the same order (never
    overwriting a present value) -- for exports SPLIT by variable (one file NDVI, another LAI of the same cell).
    Every group is classified redundant / complementary (the dropped rows carried values the kept row lacks: merged
    when the fill is on, counted and reported as NOT used when it is off) / conflicting.
    The per-group log is written in aggregate form (counts by kind and resolution) plus the first 200 groups in
    full, because a JSON with 3.7 M entries is itself a 20-minute job nobody reads."""
    if conflict_log is None: conflict_log = []
    keys = [k for k in (group_keys or DEDUP_KEYS) if k in df.columns]      # site_id absent -> plain pixel key
    # v20.58: a pixel OUTSIDE every polygon (site_check 3) has no sub-watershed of its own -- its id is only what the file's NAME said, and a
    # named export and an unnamed tile of the same place disagree: its copies are ONE pixel-year-season (the newer file wins, as always)
    _sk = "site_id" in keys and "site_check" in df.columns
    if _sk:
        df["_site_key"] = np.where(pd.to_numeric(df["site_check"], errors="coerce").fillna(4).values == 3, -1,
                                   pd.to_numeric(df["site_id"], errors="coerce").fillna(0).astype(np.int64).values).astype(np.int64)
        keys = ["_site_key" if k == "site_id" else k for k in keys]
    dup_mask = df.duplicated(subset=keys, keep=False)
    if not dup_mask.any():
        if _sk: df.drop(columns=["_site_key"], inplace=True)
        df.attrs["duplicate_kinds"] = {}; df.attrs["values_filled_from_duplicates"] = 0
        df.attrs["values_in_dropped_rows_not_used"] = 0; df.attrs["values_not_used_by_variable"] = {}
        return df, conflict_log
    check_cols = [c for c in OUTCOME_VARS if c in df.columns]
    vintage_rank = {"2026plus": 2, "2015_2025": 1}
    g = df[dup_mask].copy()
    gid = g.groupby(keys, sort=False).ngroup().values
    g["_gid"] = gid
    # ---- ranking columns (all vectorised) ----
    if recency_col in g.columns and g[recency_col].notna().all():
        mt = g[recency_col].astype(float).values
        mmax = pd.Series(mt).groupby(gid).transform("max").values
        g["_newest"] = ((mmax - mt) <= recency_margin_seconds).astype(np.int8)
    else:
        g["_newest"] = np.int8(1)
    g["_n_missing"] = g[check_cols].isna().sum(axis=1).astype(np.int32) if check_cols else 0
    g["_nobs"] = pd.to_numeric(g["NObsV"], errors="coerce").fillna(-1).values if "NObsV" in g.columns else -1.0
    g["_vrank"] = g["schema_vintage"].map(vintage_rank).fillna(0).values if "schema_vintage" in g.columns else 0
    g["_src"] = g["src_file"].astype(str).values if "src_file" in g.columns else ""
    if DEDUP_PRIORITY == "complete":          # v20.25: the more complete row first, then the newer file
        order = g.sort_values(["_gid", "_n_missing", "_newest", "_nobs", "_vrank", "_src"],
                              ascending=[True, True, False, False, False, True], kind="mergesort")
    else:                                     # "newer" (default, unchanged): newer file first, then completeness
        order = g.sort_values(["_gid", "_newest", "_n_missing", "_nobs", "_vrank", "_src"],
                              ascending=[True, False, True, False, False, True], kind="mergesort")
    first = order.groupby("_gid", sort=False).head(1)
    # ---- the kept row's gaps that the dropped rows could fill (first non-null in priority order) ----
    # v20.58: filled ONLY when DEDUP_FILL_FROM_DUPLICATES is True; otherwise counted (per variable) and reported as NOT used
    _fill = bool(DEDUP_FILL_FROM_DUPLICATES if fill_from_duplicates is None else fill_from_duplicates)
    n_filled = 0; n_fillable = 0; per_var = {}
    if check_cols:
        donors = order.groupby("_gid", sort=False)[check_cols].first()        # first non-null per column per group
        kept = first.set_index("_gid")[check_cols]
        gaps = kept.isna()
        filled = kept.where(~gaps, donors.reindex(kept.index))
        _fillable = gaps & filled.notna()
        n_fillable = int(_fillable.values.sum())
        per_var = {c: int(v) for c, v in _fillable.sum(axis=0).items() if int(v)}
        if _fill:
            n_filled = n_fillable
            first = first.copy()
            first[check_cols] = filled.values
    # ---- classify each group ----
    kinds = pd.Series("redundant", index=first["_gid"].values)
    if check_cols:
        nun = order.groupby("_gid", sort=False)[check_cols].nunique(dropna=True)
        conflicting = (nun > 1).any(axis=1)
        gained = (first.set_index("_gid")[check_cols].notna().sum(axis=1)
                  > order.groupby("_gid", sort=False).head(1).set_index("_gid")[check_cols].notna().sum(axis=1)) if False else None
        # a group is complementary when the dropped rows carried at least one value the kept row lacks (merged only when the fill is on)
        per_group_gain = _fillable.sum(axis=1) if check_cols else pd.Series(0, index=kinds.index)
        kinds[conflicting.reindex(kinds.index).fillna(False).values] = "conflicting"
        kinds[(per_group_gain.reindex(kinds.index).fillna(0) > 0).values & (kinds.values == "redundant")] = "complementary"
    # ---- resolution reason (for the log) ----
    grp_sizes = order.groupby("_gid", sort=False).size()
    exact = order.groupby("_gid", sort=False)[check_cols].nunique(dropna=False).le(1).all(axis=1) if check_cols else pd.Series(True, index=grp_sizes.index)
    newest_n = order.groupby("_gid", sort=False)["_newest"].sum()
    reason = pd.Series("resolved_by_completeness", index=grp_sizes.index)
    reason[(newest_n < grp_sizes).values] = "resolved_by_file_recency"
    reason[exact.values] = "exact_duplicate_all_values_identical"
    kind_counts = kinds.value_counts().to_dict()
    # ---- log: aggregate + a sample of full entries ----
    conflict_log.append({"summary": True, "n_groups": int(len(grp_sizes)), "kinds": {k: int(v) for k, v in kind_counts.items()},
                         "resolutions": {k: int(v) for k, v in reason.value_counts().items()},
                         "values_filled_from_dropped_rows": n_filled, "fill_from_duplicates": _fill,
                         "values_in_dropped_rows_not_used": int(n_fillable - n_filled),
                         "values_not_used_by_variable": ({} if _fill else per_var)})
    for gi in first["_gid"].values[:200]:
        rows_ = order[order["_gid"] == gi]
        conflict_log.append({"group_key": {k: (v.item() if hasattr(v, "item") else v) for k, v in zip(keys, rows_.iloc[0][keys].values)},
                             "n_duplicates": int(len(rows_)), "resolution": str(reason.loc[gi]),
                             "duplicate_kind": str(kinds.loc[gi]), "kept_src_file": str(rows_.iloc[0]["_src"]),
                             "dropped_src_files": [str(x) for x in rows_["_src"].values[1:]]})
    if "fragment" in first.columns:                           # v20.57: a pixel-period that ANY file holds as its own
        first = first.copy()                                  # sub-watershed's data is major data (the lowest code wins)
        first["fragment"] = order.groupby("_gid", sort=False)["fragment"].min().reindex(first["_gid"].values).values
    resolved = first.drop(columns=["_gid", "_newest", "_n_missing", "_nobs", "_vrank", "_src", "_site_key"], errors="ignore")
    final = pd.concat([df[~dup_mask].drop(columns=["_site_key"], errors="ignore"), resolved], ignore_index=True)
    final.attrs["duplicate_kinds"] = {k: int(v) for k, v in kind_counts.items()}
    final.attrs["values_filled_from_duplicates"] = int(n_filled)
    final.attrs["values_in_dropped_rows_not_used"] = int(n_fillable - n_filled)       # v20.58
    final.attrs["values_not_used_by_variable"] = {} if _fill else per_var
    return final, conflict_log


# ============================ FINAL PANEL SCHEMA (v16) ============================
# ONLY these columns are written to did_panel_full.parquet, with the smallest safe dtype.
# Everything else (raw UID, source-file name, audit strings, alias duplicates, dose-table
# internals) is dropped at write time. Result: ~170 bytes/row instead of ~450+, so a
# 1B-row panel is ~170 GB in RAM / ~40-60 GB on disk instead of ~450 GB / ~150 GB.
PANEL_OUTCOME_VARS_21 = ["NDVI","SAVI","EVI","LAI","LSWI","NDWI","NDMI","NDRE","AGB","RUSLE",
                "Rain","Tmax","Tmean","Tmin","ESI","WSSI","WSI","SMDI","VCI","TCI","VHI"]
FINAL_PANEL_SCHEMA = {
    # ---- identity / keys ----
    "pixel_id": "int64",            # 18-digit numeric id fits int64: 8 bytes instead of a ~60-byte string
    "subwshed_id": "category", "site_name": "category", "District": "category",
    "site_id": "int16",             # v20.22/28: SWSiD_All (1..20), verified against the shapefile
    "sws_name": "category",         # v20.28: the SWS name (shapefile SUBWSHED)
    "site_check": "int8",           # v20.28: 0 confirmed, 1 corrected, 2 assigned, 3 outside every polygon, 4 not checked
    "sws_id_export": "int16",       # v20.39: the sub-watershed id the INPUT FILE carried (0 = none); site_id is the overlay's
    "fragment": "int8",             # v20.57: 0 the file's own sub-watershed | 1 inside ANOTHER one's polygon | 2 outside every polygon
                                    #   with another id (_fragments.py); FRAGMENT_RULE at the MODEL stage drops 1 / 2 (and minor sites)
    "latitude": "float64", "longitude": "float64",     # full precision kept for the spatial modules
    "Year": "int16", "Season": "int8", "season_sort_rank": "int8",
    # ---- fixed effects ----
    "time_fe_yearseason": "category", "time_fe_year": "category", "time_fe_season": "category",
    # ---- DiD design (your names; aliases are re-derived at model time, not stored) ----
    "buff_km": "int8", "treatment": "int8", "control": "int8", "pre": "int8", "post": "int8",
    "did_term": "int8", "in_analysis_sample": "int8",
    "treat": "int8", "did": "int8",     # v20.59 (your request): the DiD columns under the names every model and R's panel use --
                                        # treat = treatment, did = did_term (post / pre from the exports' Treat flag: POST_FROM_EXPORT_TREAT)
    # event_time and period_index are NOT stored: build_treatment_columns re-derives both from
    # Year/Season at model time (saves 5 bytes/row = 5 GB at 1B rows).
    # ---- treatment timing / dose (NaN-able -> float32) ----
    "dose_per_subwshed": "float32", "dose_amount_sws": "float32", "dose_intensity_per_ha": "float32",   # v20.38
    "first_treat_agri_year": "float32",
    "first_treat_season": "float32", "area_hectare": "float32",
    # ---- the 21 planned outcome variables ----
    **{v: "float32" for v in PANEL_OUTCOME_VARS_21},
    # ---- covariates ----
    "LandUse": "float32", "LandUseDW": "float32",
    # ---- QC needed for validation / filtering ----
    "GapFilled": "float32", "Coverage": "float32", "OptTier": "float32",   # v20.37: OptTier = composite tier (QC) "NObsV": "float32", "NObsT": "float32",
    "treat_period_mismatch_flag": "int8", "any_outcome_flat_flag": "int8",
    "outcome_missing_flag": "int8", "schema_vintage": "category",
}
# v20.58: a panel for a SUBSET of the models (_paths.PIPELINE_MODELS -- the four-model project carries M01, M02, M16, M34) holds only the
# columns those models read: the district / dose / area / first-treated columns serve the dose and staggered models (the fund timing is
# applied by every model from your workbook when it runs), the land use M10's third difference and the ML models' effect splits.
PANEL_COLUMNS_USED_BY = {"District": "M05 M06 M09 M22 M27 M28 M30 M31 M32", "dose_per_subwshed": "M06", "dose_amount_sws": "M06",
                         "dose_intensity_per_ha": "M06", "area_hectare": "M06",
                         "first_treat_agri_year": "M05 M06 M09 M22 M27 M28 M30 M31 M32", "first_treat_season": "M05 M06 M09 M22 M27 M28 M30 M31 M32",
                         "LandUse": "M10 M26 M39-M45", "LandUseDW": "M10 M39-M45"}
try:
    import _paths as _PPq
    PIPELINE_MODELS = tuple(getattr(_PPq, "PIPELINE_MODELS", None) or ()) or None
    del _PPq
except Exception:
    PIPELINE_MODELS = None

def _models_named(text):
    ids = set()
    for a, b in re.findall(r"M(\d{2})(?:\s*-\s*M(\d{2}))?", str(text)):
        ids |= {f"M{k:02d}" for k in range(int(a), int(b or a) + 1)}
    return ids

def panel_columns_left_out(models=None):
    """The model-specific columns a panel for `models` (default _paths.PIPELINE_MODELS; None = all 45 -> none) does not carry."""
    models = models if models is not None else PIPELINE_MODELS
    if not models: return []
    return [c for c, u in PANEL_COLUMNS_USED_BY.items() if not (_models_named(u) & set(models))]

for _c in panel_columns_left_out():
    FINAL_PANEL_SCHEMA.pop(_c, None)
FINAL_PANEL_COLUMNS = list(FINAL_PANEL_SCHEMA)          # single source of truth
DROPPED_FROM_PANEL = ["event_time","period_index","UID","external_uid_final","Treat","treat_legacy","SubwshedID","SWSiD_All","SWS_Name","Sub Watershed Name",
    "src_file","file_mtime","missing_source_cols","site_match_strategy","row_id","SrcOpt","SrcET","YrRel",
    "DataYear","ESI_Anom","treat_core","control_zone_selected","pre_period","post_period",
    "treatment_group","control_group","buffkm_out_of_range_flag"]

def finalize_panel_block(block):
    """Apply FINAL_PANEL_SCHEMA to one PASS-B shard: keep only listed columns (add as NaN if a
    vintage lacks one, so every shard has an identical schema), cast to the compact dtypes."""
    out = pd.DataFrame(index=block.index)
    for col, dt in FINAL_PANEL_SCHEMA.items():
        if col in block.columns:
            v = block[col]
        else:
            v = pd.Series(np.nan, index=block.index)
        try:
            if col == "pixel_id":
                out[col] = pd.to_numeric(v, errors="coerce").astype("int64")
            elif dt == "category":
                out[col] = v.astype(str).where(v.notna(), None).astype("category")
            elif dt.startswith("int"):
                out[col] = pd.to_numeric(v, errors="coerce").fillna(0).round().astype(dt)
            else:
                out[col] = pd.to_numeric(v, errors="coerce").astype(dt)
        except Exception as e:
            raise RuntimeError(f"finalize_panel_block: cannot cast {col} to {dt}: {e}")
    return out


_SNAP_TYPES = (type(None), bool, int, float, str)
def _plain_setting(v, depth=0):
    if depth > 6: return False
    if isinstance(v, _SNAP_TYPES) or isinstance(v, (np.integer, np.floating, np.bool_)): return True
    if isinstance(v, (list, tuple, set, frozenset)): return all(_plain_setting(x, depth + 1) for x in v)
    if isinstance(v, dict): return all(_plain_setting(k, depth + 1) and _plain_setting(x, depth + 1) for k, x in v.items())
    return False

def _settings_snapshot():
    """v20.58: EVERY setting of this module (its upper-case plain values -- whatever P00_Settings changed) for a worker process. The pools
    passed hand-picked lists until v20.57: a setting outside them (P.ALLOW_NEGATIVE_COVARIATES, P.NEGATIVE_COVARIATE_RULE) was ignored by
    the parallel PASS A / PASS B workers while the sequential path honoured it."""
    return {k: v for k, v in globals().items() if k.isupper() and not k.startswith("_") and _plain_setting(v)}

def _pa_worker_init(module_dir, known_names, cfg):
    """Runs once per worker process: make _prep_common importable, copy notebook-set globals,
    and pin BLAS to ONE thread (v20.7) so N workers do not start N x cores threads."""
    import sys as _sys, importlib
    if module_dir not in _sys.path: _sys.path.insert(0, module_dir)
    try:
        import _hardware as _H; _H.worker_init_threads()
    except Exception:
        import os as _os
        for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            _os.environ[_v] = "1"
    m = importlib.import_module("_prep_common")
    m.KNOWN_SUBWSHED_NAMES = list(known_names)
    for k, v in cfg.items(): setattr(m, k, v)

def _pa_worker(path):
    """Per-file work that is independent of every other file: read, harmonise, UID, dedup, QC, FE."""
    import importlib
    m = importlib.import_module("_prep_common")
    unresolved, errors, dedup = [], [], []
    df = m.load_and_harmonize(path, unresolved_log=unresolved, parse_errors_log=errors)
    if df is None:
        return None, unresolved, errors, dedup
    df["pixel_id"] = m.assign_pixel_ids(df["latitude"].values, df["longitude"].values)
    df, _st = m.tag_sites(df, path)                            # v20.28: SWS verified BEFORE de-duplication
    df, _st = m.tag_fragments(df, _st)                         # v20.57: the file's own sub-watershed; fragments of others coded
    unresolved.append(("__site_tagging__", os.path.basename(path), _st))
    df, _mp = m.apply_missing_policy(df, drop_empty=False)     # v20.16; v20.58: empty rows stay until the cross-file dedup (PASS B)
    df, dedup = m.resolve_duplicates(df, conflict_log=dedup)
    df = m.data_qc(df)
    df = m.build_fe_and_treatment(df)
    df = m._drop_source_ids(df)                                # v20.51
    return df, unresolved, errors, dedup


def _n_file_errors(parse_errors):
    """v20.55: entries of the PASS A log that are real file problems (rejected, unreadable, skipped, key missing) --
    a note that an absent outcome column was filled NaN is not an error and is counted separately."""
    return sum(1 for e in parse_errors if "outcome columns filled NaN (not present in source)" not in str(e))

def run_pass_a(input_dir, temp_dir, output_dir=None, n_workers=None, in_memory=None):
    """Ingest every CSV + Parquet file once, in ascending-Year order; write per-(Year,Season)
    temp shards. Returns (registry, unresolved_cols, parse_errors, dedup_conflicts, shard_paths).

    IMPORTANT: your OUTPUT_DIR is a subfolder of INPUT_DIR (D:/LKT/.../REWARD_Artal_Exports_final/output).
    Since files are searched recursively, a second run would otherwise try to re-ingest the
    FIRST run's own output (did_panel_full.parquet, temp shards) as if it were new source data.
    Fixed here defensively: anything under output_dir or temp_dir is excluded from discovery,
    regardless of where you point INPUT_DIR."""
    os.makedirs(temp_dir, exist_ok=True)
    files, n_excluded, all_n = discover_input_files(input_dir, output_dir, temp_dir, verbose=True)

    # order by Year for registry stability; files lacking a parseable Year go last with a warning
    def _year_key(f):
        m = parse_filename(f)
        return (m.get("Year") or 99999) if m else 99999
    files_sorted = sorted(files, key=_year_key)

    class _UIDs:      # v14: only tracks the set of ids seen (kept so the return signature is unchanged)
        def __init__(self): self.uids = set()
    registry = _UIDs()
    unresolved_cols, parse_errors, dedup_conflicts = [], [], []
    site_tag_rows = []                                          # v20.28: per-file SWS tagging
    shard_writers = {}   # (Year,Season) -> pq.ParquetWriter
    _mem_on = [bool(IN_MEMORY_BLOCKS if in_memory is None else in_memory)]; _mem_blocks = {}; _mem_bytes = [0]   # v20.30
    def _write_group(key, group):
        # v20.49: exports differ in their columns (e.g. SWSiD_All only in the newer ones). An open parquet file cannot
        # take a table with other columns -- real pyarrow raised "Target schema's field names are not matching" as soon
        # as a block spilled to disk. A group with FEWER columns is conformed to the open part (missing -> null);
        # a group with NEW columns starts a new part file of the same block (ShardParts); nothing is dropped.
        table_ = pa.Table.from_pandas(group, preserve_index=False)
        w_ = shard_writers.get(key)
        if w_ is not None:
            if set(table_.schema.names) - set(w_.schema.names):
                w_.close(); w_ = None
            else:
                try:
                    table_ = _conform_table(table_, w_.schema)
                except _TypeConflict as e_:                  # v20.51: another type in this export -> a new part file,
                    info(f"shard {key}: {e_} -- written to a new part (nothing converted)")   # exactly as for new columns
                    w_.close(); w_ = None
        if w_ is None:
            n_ = len(shard_parts.get(key, []))
            path_ = os.path.join(temp_dir, f"shard_{key[0]}_{SEASON_LABEL[key[1]]}" + (f"_part{n_ + 1}" if n_ else "") + ".parquet")
            w_ = shard_writers[key] = pq.ParquetWriter(path_, table_.schema, compression="zstd")
            shard_parts.setdefault(key, []).append(path_)
            shard_paths[key] = path_ if n_ == 0 else ShardParts(shard_parts[key])
        w_.write_table(table_)
    shard_paths = {}; shard_parts = {}
    t0 = datetime.now()

    # ---- v16: PARALLEL file processing (your box has 64 threads). Per-file work is
    # independent, so it runs in a process pool; only the shard WRITE is serialised here.
    # Falls back to sequential with a clear message if the pool cannot start (Windows/Jupyter
    # pickling issues are the usual cause).
    if n_workers is None:
        # v20.7: use the WHOLE machine. The old rule (min(32, cores//2)) left 32 of your 64 cores idle and
        # capped the pool at 32 however big the box was. _hardware.worker_cap() takes ALL logical cores (v20.57: no
        # reserve), never more than the number of files, and respects the 61-worker Windows pool limit.
        try:
            import _hardware as _H
            n_workers = _H.worker_cap(n_tasks=len(files_sorted))
        except Exception:
            n_workers = max(1, min(60, os.cpu_count() or 1))                  # v20.57: every core (the fall-back too)
    def _sequential(f):
        u, e, d = [], [], []
        df = load_and_harmonize(f, unresolved_log=u, parse_errors_log=e)
        if df is None: return None, u, e, d
        df["pixel_id"] = assign_pixel_ids(df["latitude"].values, df["longitude"].values)
        df, _st = tag_sites(df, f)                             # v20.28: SWS verified BEFORE de-duplication
        df, _st = tag_fragments(df, _st)                       # v20.57: the file's own sub-watershed; fragments of others coded
        u.append(("__site_tagging__", os.path.basename(f), _st))
        df, _mp = apply_missing_policy(df, drop_empty=False)   # v20.16: NaN/0 -> NaN BEFORE dedup; v20.58: empty rows stay until PASS B's dedup
        df, d = resolve_duplicates(df, conflict_log=d)
        df = data_qc(df); df = build_fe_and_treatment(df); df = _drop_source_ids(df)   # v20.51
        df.attrs["missing_policy"] = _mp
        return df, u, e, d
    pool = None
    if n_workers > 1:
        try:
            from concurrent.futures import ProcessPoolExecutor
            cfg = _settings_snapshot()                               # v20.58: every setting P00_Settings may have changed (was: a list of 11)
            # Windows/Jupyter use the 'spawn' start method: children start from a CLEAN interpreter
            # and do NOT inherit sys.path. They must be able to `import _prep_common` before they can
            # even unpickle the initializer, so the module directory is passed via PYTHONPATH,
            # which spawned children DO inherit. (Verified under an explicit spawn context.)
            _mdir = os.path.dirname(os.path.abspath(__file__))
            os.environ["PYTHONPATH"] = _mdir + os.pathsep + os.environ.get("PYTHONPATH", "")
            import multiprocessing as _mp
            pool = ProcessPoolExecutor(max_workers=n_workers, mp_context=_mp.get_context("spawn"),
                                       initializer=_pa_worker_init,
                                       initargs=(_mdir, KNOWN_SUBWSHED_NAMES, cfg))
            print(f"[INFO]    PASS A running on {n_workers} worker processes")
        except Exception as e:
            print(f"[WARNING] could not start the process pool ({type(e).__name__}: {e}) -- running sequentially")
            pool = None
    def _results():
        if pool is None:
            for f in files_sorted: yield _sequential(f)
        else:
            B = n_workers * 10                     # bounded in-flight batch keeps RAM flat -- v20.58: 5x larger (was n_workers x 2)
            for start in range(0, len(files_sorted), B):
                batch = files_sorted[start:start+B]
                try:
                    for r in pool.map(_pa_worker, batch): yield r
                except Exception as e:
                    print(f"[WARNING] pool batch failed ({type(e).__name__}: {e}) -- finishing this batch sequentially")
                    for f in batch: yield _sequential(f)

    for i, (df, u_, e_, d_) in enumerate(progress(_results(), total=len(files_sorted), desc="PASS A files", unit="file"), 1):
        for _x in u_:                                           # v20.28: per-file SWS tagging records
            if isinstance(_x, (list, tuple)) and len(_x) == 3 and _x[0] == "__site_tagging__":
                site_tag_rows.append({"file": _x[1], **(_x[2] or {})})
        u_ = [_x for _x in u_ if not (isinstance(_x, (list, tuple)) and len(_x) == 3 and _x[0] == "__site_tagging__")]
        unresolved_cols.extend(u_); parse_errors.extend(e_); dedup_conflicts.extend(d_)
        if df is None:
            continue
        registry.uids.update(df["pixel_id"].unique().tolist())

        for (yr, se), group in df.groupby(["Year", "Season"]):
            key = (int(yr), int(se))
            if _mem_on[0]:                                        # v20.30: keep the block in RAM while it fits
                import _hardware as _H
                _gb = int(group.memory_usage(deep=True).sum())
                if _H.fits((_mem_bytes[0] + _gb) * MEM_BLOCK_COPIES):
                    _mem_blocks.setdefault(key, MemBlock()).add(group.reset_index(drop=True)); _mem_bytes[0] += _gb
                    continue
                info(f"RAM ceiling ({int(_H.MEMORY_CEILING * 100)} %) reached after {_mem_bytes[0] / 1e9:.1f} GB of blocks -- "
                     f"spilling them to shard files and continuing on disk (the previous path). {_H.memory_report()}")
                _mem_on[0] = False
                for _k2 in sorted(_mem_blocks):
                    for _f2 in _mem_blocks[_k2].frames: _write_group(_k2, _f2)
                _mem_blocks.clear(); gc.collect()
            _write_group(key, group)
            continue
            if key not in shard_writers:
                path = os.path.join(temp_dir, f"shard_{yr}_{SEASON_LABEL[se]}.parquet")
                table = pa.Table.from_pandas(group, preserve_index=False)
                shard_writers[key] = pq.ParquetWriter(path, table.schema, compression="zstd")
                shard_paths[key] = path
            else:
                table = pa.Table.from_pandas(group, preserve_index=False).cast(shard_writers[key].schema)
            shard_writers[key].write_table(table)

        if i % 200 == 0 or i == len(files_sorted):
            print(f"[Pass A {i}/{len(files_sorted)}] registry_pixels={len(registry.uids)} "
                  f"shards={len(shard_writers)} elapsed={(datetime.now()-t0).total_seconds():.0f}s")

    for _k3, _mb in _mem_blocks.items(): shard_paths[_k3] = _mb        # v20.30: blocks handed to PASS B in RAM
    if _mem_blocks:
        info(f"PASS A kept {len(_mem_blocks)} blocks ({_mem_bytes[0] / 1e9:.1f} GB) in RAM for PASS B -- no shard files written")
    for w in shard_writers.values():
        w.close()
    if pool is not None:
        pool.shutdown(wait=True)

    with open(os.path.join(temp_dir, "unresolved_columns.json"), "w") as fh:
        json.dump(unresolved_cols, fh, indent=2)
    # v20.28: which SWS every file's rows were confirmed / corrected / assigned to (one row per file)
    if site_tag_rows:
        st_ = pd.DataFrame(site_tag_rows)
        _out = output_dir or os.path.dirname(os.path.abspath(temp_dir))
        os.makedirs(_out, exist_ok=True); st_.to_csv(os.path.join(_out, "site_tagging_report.csv"), index=False)
        tot = {k: int(st_[k].fillna(0).sum()) for k in ("rows", "confirmed", "corrected", "assigned", "outside_all_polygons",
                                               "buff_km_taken_from_polygon", "buff_km_differs_from_polygon_ring",
                                               "buff_km_changed_on_corrected", "treated_status_changed") if k in st_.columns}
        ok(f"SWS tagging (shapefile, {len(st_)} files): " + ", ".join(f"{k} {v:,}" for k, v in tot.items()) + " -> site_tagging_report.csv")
        try:                                                    # v20.39: the overlay's verdict per SUB-WATERSHED
            _bys = site_tagging_by_sws(st_)
            if len(_bys):
                _bys.to_csv(os.path.join(_out, "site_tagging_by_sws.csv"), index=False)
                info("rows per sub-watershed (shapefile overlay) and how the file's id compared -> site_tagging_by_sws.csv")
                print(_bys.to_string(index=False))
        except Exception as _e:
            info(f"per-sub-watershed tagging summary skipped ({_e})")
        if tot.get("corrected"):
            # v20.37: is it a RENUMBERING (every export id maps to one shapefile id) or genuinely wrong ids?
            _mp, _one = site_id_mapping(st_)
            if len(_mp): _mp.to_csv(os.path.join(_out, "site_id_mapping.csv"), index=False)
            _chg = tot.get("buff_km_changed_on_corrected", 0); _tsw = tot.get("treated_status_changed", 0)
            if _one:
                info(f"{tot['corrected']:,} rows: the export NUMBERS sub-watersheds differently from the shapefile ("
                     + ", ".join(f"{int(r.export_id)}->{int(r.shapefile_id)}" for r in _mp[_mp.share_of_export_id >= 0.99].itertuples())
                     + ") -- relabelled to the shapefile's ids; a renumbering, NOT wrong data (site_id_mapping.csv)")
            else:
                _named = _mp[(_mp.relation == "different id") & (_mp.export_id_is_sws != "not a shapefile id")]
                warn(f"{tot['corrected']:,} rows carried a sub-watershed id whose polygon does not hold the point, with NO consistent "
                     f"renumbering behind it -- corrected from the shapefile (site_id_mapping.csv, site_tagging_report.csv)"
                     + ("".join(f"; {int(r.rows):,} rows labelled {int(r.export_id)} ({r.export_id_is_sws}) lie in "
                                f"{int(r.shapefile_id)} ({r.shapefile_name})" for r in _named.itertuples()) if len(_named) else ""))
            (warn if _tsw else ok)(f"what the correction changed: the ring value on {_chg:,} rows, treated <-> control on {_tsw:,} rows"
                                   + (" -- these rows changed SIDES of the comparison; check them" if _tsw else " -- the DiD design is unaffected"))
        if tot.get("outside_all_polygons"): warn(f"{tot['outside_all_polygons']:,} rows lie in NO SWS polygon -- kept with the id from the data, flagged site_check = 3")
        if "not_checked" in st_.columns and st_["not_checked"].fillna(0).sum():
            warn(f"{int(st_['not_checked'].fillna(0).sum()):,} rows could not be checked against the shapefile: {st_['reason'].dropna().iloc[0] if 'reason' in st_ else ''}")
    with open(os.path.join(temp_dir, "file_errors.json"), "w") as fh:
        json.dump(parse_errors, fh, indent=2)
    with open(os.path.join(temp_dir, "dedup_conflicts.json"), "w") as fh:
        json.dump(dedup_conflicts, fh, indent=2, default=str)

    print(f"Pass A done. {len(registry.uids)} unique pixels, {len(shard_paths)} shards, "
          f"{len(unresolved_cols)} unresolved columns, {_n_file_errors(parse_errors)} file errors ({len(parse_errors) - _n_file_errors(parse_errors)} notes on outcome columns filled NaN), "
          f"{len(dedup_conflicts)} duplicate-pixel groups resolved (see dedup_conflicts.json).")
    if not len(registry.uids) and _n_file_errors(parse_errors):           # v20.39: stop HERE, with the reason
        raise RuntimeError(f"PASS A produced NO pixels: all {len(parse_errors)} file(s) were rejected -- e.g. "
                           f"{str(parse_errors[0])[-160:]} (full list: file_errors.json). Fix the exports or the column names, then re-run P00.")
    return registry, unresolved_cols, parse_errors, dedup_conflicts, shard_paths


# ====================== v20.6: PASS B WORKERS (one Year x Season block each) ======================
# PASS B used to run 44 blocks one after another on a single core while 63 sat idle, and it did the two most
# expensive steps TWICE per block (build_treatment_columns and finalize_panel_block were each called twice).
# Each block is independent -- read its shard, resolve cross-file duplicates, build the DiD columns, merge the
# dose, sort, finalize -- so the blocks now run in parallel worker processes, each writing its own part file.
# The parts are then streamed into the single did_panel_full.parquet IN THE REQUIRED ORDER, so the output is
# byte-for-byte the panel the sequential code produced.
PASS_B_WORKERS = None            # None = autotuned from cores and free RAM; set an int to pin it
PASS_B_BYTES_PER_ROW = 220.0     # measured working-set per row inside a worker (pandas block + copies)

def pass_b_worker_count(n_blocks, rows_per_block=2_000_000, verbose=True):
    """How many blocks to process at once: every core (v20.57: no reserve), never more than the number of blocks,
    never more than fit below 98 % of the RAM, never above the platform pool limit (61 on Windows)."""
    try:
        import _hardware as _H
        n = _H.worker_cap(n_tasks=n_blocks, bytes_per_worker=rows_per_block * PASS_B_BYTES_PER_ROW)
        p = _H.machine_profile()
        if verbose:
            print(f"[INFO]    PASS B: {p['logical_cores']} logical cores, "
                  f"{(p['ram_free'] or 0)/1e9:.0f} GB free -> {n} worker process(es), "
                  f"~{rows_per_block*PASS_B_BYTES_PER_ROW/1e9:.1f} GB each (1 BLAS thread per worker)")
        return n
    except Exception:
        import multiprocessing as _mp
        return max(1, min((_mp.cpu_count() or 1), n_blocks, 60))

def _pb_worker(args):
    """One (Year, Season) block, end to end, into its own part file. Returns (key, path, rows, dup_log)."""
    import importlib
    m = importlib.import_module("_prep_common")
    (yr, se), shard_path, part_path, dose_records, crosswalk_records = args
    import pandas as _pd
    dose_table = _pd.DataFrame(dose_records) if dose_records is not None else None
    crosswalk = _pd.DataFrame(crosswalk_records) if crosswalk_records is not None else None
    block, dup_log, removed, kinds, filled, n_pix, mp = m.prepare_pass_b_block(yr, se, shard_path, dose_table, crosswalk)
    table = m.pa.Table.from_pandas(block, preserve_index=False)
    w = m.pq.ParquetWriter(part_path, table.schema, compression="zstd")
    w.write_table(table, row_group_size=m.ROW_GROUP_SIZE); w.close()
    return (yr, se), part_path, len(block), dup_log, removed, kinds, filled, n_pix, mp

# ====================== v20.25: NEAR-DUPLICATE PIXELS (>= 80 % overlap = one pixel) ======================
# Two Earth Engine exports can sample the same physical 10 m pixel on grids a metre or two apart. pixel_id is a
# pure function of the coordinate rounded to 1e-5 degrees (~1.1 m), so such a pixel got TWO ids: it was counted
# twice in a block and, across years, looked like two different pixels (which breaks the within-pixel comparison a
# DiD rests on). PASS B now builds ONE registry of every pixel in every block, finds the pairs whose footprints
# overlap by at least PIXEL_OVERLAP_MIN, and maps each such pixel onto one canonical pixel -- chosen by the same
# rule used for duplicate rows (DEDUP_PRIORITY). After the remap the ordinary duplicate resolution keeps one row
# per (site, pixel, Year, Season) and fills its gaps from the dropped row. Exact coincidences already share an id.
NEAR_DUPLICATE_PIXELS = True     # False = the previous behaviour exactly (no spatial merging)
ACCEPT_PANEL_WITHOUT_PIXEL_MERGE = False   # True = reuse a panel built before v20.25 without rebuilding
PIXEL_OVERLAP_MIN = 0.65         # v20.38 (was 0.80): your 2025 exports sit on a grid shifted a median 3.0 m; at 0.80, 20 %
                                 # of the treated post-period rows had NO pre-period history (they identify nothing);
                                 # 0.70 links 95 %. Any value above 0.50 can match a pixel to ONE earlier pixel only.
PIXEL_SIZE_M = 10.0              # pixel side in metres (Sentinel-2 10 m); the report shows the grid spacing measured per export
DEDUP_PRIORITY = "newer"         # which row/pixel wins: "newer" = the newer export file (then the more complete row)
                                 #                        "complete" = the more complete row (then the newer file)
DEDUP_FILL_FROM_DUPLICATES = False   # v20.58 -- YOUR RULE "repeated rows are dropped": the kept row is taken AS IT IS, a value of a
                                     # dropped (repeated) row never enters the panel -- a cloud gap of the kept row stays a gap.
                                     # True = the v20.9-v20.57 behaviour: the kept row's gaps are filled from the dropped rows (use it
                                     # when your exports are SPLIT by variable: one file NDVI, another LAI of the same pixel-period)
PIXEL_OVERLAP_MAP_PATH = None    # set by run_pass_b; the PASS B workers read it
_PIXEL_MAP_CACHE = {}

def _metres(lat, lon, lat_ref):
    k = 111320.0 * np.cos(np.radians(lat_ref))
    return (np.asarray(lon, np.float64) * k, np.asarray(lat, np.float64) * 110574.0)

def _registry_one_shard(path):
    """Per-pixel aggregates of ONE block shard (threads: pyarrow I/O releases the GIL)."""
    if isinstance(path, (MemBlock, ShardParts)):                       # v20.30: block held in RAM (v20.49: or in parts)
        return _registry_aggregate(path.to_pandas([c_ for c_ in ("pixel_id", "latitude", "longitude", "file_mtime", "src_file")
                                                   + tuple(OUTCOME_VARS)]))
    pf = pq.ParquetFile(path)
    try:
        names = pf.schema_arrow.names
        cols = [c for c in ("pixel_id", "latitude", "longitude", "file_mtime", "src_file") if c in names]
        ocols = [c for c in OUTCOME_VARS if c in names]
        d = pd.concat([pf.read_row_group(i_, columns=cols + ocols).to_pandas() for i_ in range(pf.num_row_groups)],
                      ignore_index=True) if pf.num_row_groups else pd.DataFrame(columns=cols + ocols)
    finally:
        try: pf.close()
        except Exception: pass
    return _registry_aggregate(d)

def _registry_aggregate(d):
    if not len(d): return None
    ocols = [c_ for c_ in OUTCOME_VARS if c_ in d.columns]
    d = d.copy()
    d["_ok"] = np.isfinite(d[ocols].apply(pd.to_numeric, errors="coerce").values.astype(np.float64)).sum(axis=1) if ocols else 0
    if "file_mtime" not in d.columns: d["file_mtime"] = 0.0
    if "src_file" not in d.columns: d["src_file"] = ""
    d = d.sort_values("file_mtime", kind="mergesort")
    return d.groupby("pixel_id", sort=False).agg(lat=("latitude", "mean"), lon=("longitude", "mean"), mtime=("file_mtime", "max"),
                                                 n_rows=("_ok", "size"), n_ok=("_ok", "sum"), src=("src_file", "last"))

def pixel_registry(shard_paths, verbose=True, n_threads=None):
    """One row per pixel_id across ALL blocks: mean coordinates, newest file time, rows, usable outcome cells and the
    newest file's name. The shards are scanned in parallel threads (bounded by cores and free RAM)."""
    keys = sorted(shard_paths)
    try:
        import _hardware as _H
        n_threads = n_threads or _H.worker_cap(n_tasks=len(keys), bytes_per_worker=6e9)
    except Exception:
        n_threads = n_threads or min(8, len(keys))
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, int(n_threads))) as ex:
        it = ex.map(_registry_one_shard, [shard_paths[k] for k in keys])
        parts = [p_ for p_ in (progress(it, total=len(keys), desc="pixel registry", unit="block") if verbose else it) if p_ is not None]
    if not parts:
        return pd.DataFrame(columns=["lat", "lon", "mtime", "n_rows", "n_ok", "src", "completeness"])
    r = pd.concat(parts)
    r = r.sort_values("mtime", kind="mergesort")
    reg = r.groupby(level=0, sort=False).agg(lat=("lat", "mean"), lon=("lon", "mean"), mtime=("mtime", "max"),
                                             n_rows=("n_rows", "sum"), n_ok=("n_ok", "sum"), src=("src", "last"))
    reg["completeness"] = reg["n_ok"] / reg["n_rows"].clip(lower=1)
    return reg

def confirm_panel_duplicates(final_path, verbose=True):
    """v20.58 -- YOUR RULE: repeated rows and pixels are dropped AND CONFIRMED on the finished panel (checked, never assumed; as R's R_P00):
    every (sub-watershed, pixel, year, season) once, a pixel outside every polygon once per year-season, and the near-duplicate pixels that
    remain (footprints overlapping >= PIXEL_OVERLAP_MIN: the one-to-one merge cannot join a chain; the models leave the smaller one out)."""
    import pyarrow.parquet as pq, pyarrow as pa
    pf = pq.ParquetFile(final_path); names = pf.schema_arrow.names
    cols = [c for c in ("site_id", "pixel_id", "Year", "Season", "site_check", "latitude", "longitude") if c in names]
    t = pq.read_table(final_path, columns=cols)
    n = t.num_rows; keys = [c for c in ("site_id", "pixel_id", "Year", "Season") if c in cols]
    g = t.group_by(keys).aggregate([([], "count_all")]); rep = int(n - g.num_rows)
    if rep: raise RuntimeError(f"duplicate removal FAILED: {rep:,} rows repeat a (sub-watershed, pixel, year, season) in {final_path} -- please report this")
    rep_out = 0
    if "site_check" in cols:
        o = t.filter(pa.compute.equal(t["site_check"], 3)).select(["pixel_id", "Year", "Season"])
        if o.num_rows: rep_out = int(o.num_rows - o.group_by(["pixel_id", "Year", "Season"]).aggregate([([], "count_all")]).num_rows)
    if rep_out: raise RuntimeError(f"duplicate removal FAILED: a pixel outside every polygon is repeated in {rep_out:,} year-season(s) -- please report this")
    both = int(n - t.select(["pixel_id", "Year", "Season"]).group_by(["pixel_id", "Year", "Season"]).aggregate([([], "count_all")]).num_rows)
    left = 0
    if NEAR_DUPLICATE_PIXELS and {"latitude", "longitude"} <= set(cols):
        px = t.select(["pixel_id", "latitude", "longitude"]).group_by("pixel_id").aggregate([("latitude", "mean"), ("longitude", "mean")]).to_pandas()
        reg = pd.DataFrame({"lat": px["latitude_mean"].values, "lon": px["longitude_mean"].values}, index=px["pixel_id"].values)
        left = int(len(near_duplicate_pairs(reg)))
        (warn if left else ok)(f"near-duplicate pixels CONFIRMED: {left:,} pixel pair(s) remain whose footprints overlap >= {100 * PIXEL_OVERLAP_MIN:.0f} % among "
                               f"{len(reg):,} pixels" + (" (a chain the one-to-one merge cannot join) -- the models leave the smaller of each pair out (OVERLAP_ROWS)" if left else ""))
    if both: info(f"{both:,} pixel-year-season(s) lie in the polygons of TWO sub-watersheds (their zones overlap): kept once per sub-watershed -- "
                  f"the location rule of the models keeps each in its own sub-watershed only")
    ok(f"duplicates CONFIRMED removed: {n:,} rows, every (sub-watershed, pixel, year, season) exactly once; every pixel outside the polygons once per year-season")
    return {"rows": n, "repeated": rep, "outside_repeated": rep_out, "two_sub_watersheds": both, "near_duplicate_pairs_left": left}

def near_duplicate_pairs(reg, size_m=None, overlap_min=None):
    """Pairs of DIFFERENT pixel ids whose square footprints (side size_m) overlap by >= overlap_min.
    Overlap of two equal squares offset by (dx, dy) = (1-|dx|/s)(1-|dy|/s). Spatial hash on s-metre bins; only the
    3 x 3 neighbouring bins are compared, so this is linear in the number of pixels."""
    s_ = float(size_m or PIXEL_SIZE_M); thr = float(PIXEL_OVERLAP_MIN if overlap_min is None else overlap_min)
    if len(reg) < 2: return pd.DataFrame(columns=["i", "j", "overlap", "dx_m", "dy_m"])
    lat = reg["lat"].values.astype(np.float64); lon = reg["lon"].values.astype(np.float64)
    lat_ref = float(np.nanmedian(lat))
    x, y = _metres(lat, lon, lat_ref)
    bx = np.floor((x - np.nanmin(x)) / s_).astype(np.int64) + 1; by = np.floor((y - np.nanmin(y)) / s_).astype(np.int64) + 1
    BIG = np.int64(1) << np.int64(31)
    key = bx * BIG + by
    idx = np.arange(len(reg), dtype=np.int64)
    base = pd.DataFrame({"k": key, "i": idx})
    found = []
    for ox in (-1, 0, 1):
        for oy in (-1, 0, 1):
            sh = pd.DataFrame({"k": (bx + ox) * BIG + (by + oy), "j": idx})
            m = base.merge(sh, on="k", how="inner")
            m = m[m["i"] < m["j"]]
            if not len(m): continue
            i_ = m["i"].values; j_ = m["j"].values
            dx = (lon[i_] - lon[j_]) * 111320.0 * np.cos(np.radians(0.5 * (lat[i_] + lat[j_])))
            dy = (lat[i_] - lat[j_]) * 110574.0
            ov = np.clip(1 - np.abs(dx) / s_, 0, None) * np.clip(1 - np.abs(dy) / s_, 0, None)
            keep = ov >= thr - 1e-12
            if keep.any():
                found.append(pd.DataFrame({"i": i_[keep], "j": j_[keep], "overlap": ov[keep], "dx_m": dx[keep], "dy_m": dy[keep]}))
    if not found: return pd.DataFrame(columns=["i", "j", "overlap", "dx_m", "dy_m"])
    return pd.concat(found, ignore_index=True).drop_duplicates(["i", "j"])

def canonical_pixel_map(reg, pairs, priority=None):
    """Greedy, chain-free: pixels in priority order; an unassigned pixel becomes canonical and takes every unassigned
    pixel that overlaps IT by >= the threshold. A pixel is therefore merged only into a pixel it overlaps directly
    (A-B 85 % and B-C 85 % never pulls C onto A when A-C is 70 %). Returns DataFrame pixel_id -> canonical id/coords."""
    pr = (priority or DEDUP_PRIORITY)
    if len(pairs) == 0:
        return pd.DataFrame(columns=["pixel_id", "canonical_pixel_id", "canonical_lat", "canonical_lon", "overlap"])
    newer = -reg["mtime"].values.astype(np.float64); compl = -reg["completeness"].values.astype(np.float64)
    nrow = -reg["n_rows"].values.astype(np.float64); pid = reg.index.values
    order = np.lexsort((pid, nrow, newer, compl) if pr == "complete" else (pid, nrow, compl, newer))
    pos = np.empty(len(order), dtype=np.int64); pos[order] = np.arange(len(order))
    a = pairs["i"].values.astype(np.int64); b = pairs["j"].values.astype(np.int64); ov = pairs["overlap"].values
    hi = np.where(pos[a] < pos[b], a, b); lo = np.where(pos[a] < pos[b], b, a)
    srt = np.lexsort((pos[lo], pos[hi]))
    hi, lo, ov = hi[srt], lo[srt], ov[srt]
    # v20.55: the rows are sorted by PRIORITY of hi, not by its value, so equal hi are contiguous runs -- slice those runs.
    # (searchsorted on this order returned wrong slices: on a shifted export grid it merged 121 pixels onto ONE canonical
    #  pixel; the parity harness caught it. Every canonical now gets exactly the pixels that overlap IT.)
    change = np.flatnonzero(np.diff(hi)) + 1
    starts = np.concatenate([[0], change]).astype(np.int64); ends = np.concatenate([change, [len(hi)]]).astype(np.int64)
    adj = {int(hi[s0]): (lo[s0:s1], ov[s0:s1]) for s0, s1 in zip(starts, ends)}
    involved = np.unique(np.concatenate([hi, lo]))
    involved = involved[np.argsort(pos[involved], kind="mergesort")]
    assigned = {}; ovr = {}
    for p_ in involved:
        p_ = int(p_)
        if p_ in assigned: continue
        assigned[p_] = p_
        if p_ in adj:
            qs, os_ = adj[p_]
            for q, o in zip(qs.tolist(), os_.tolist()):
                if q not in assigned:
                    assigned[q] = p_; ovr[q] = o
    rows = [(q, r) for q, r in assigned.items() if q != r]
    if not rows:
        return pd.DataFrame(columns=["pixel_id", "canonical_pixel_id", "canonical_lat", "canonical_lon", "overlap"])
    q = np.array([r[0] for r in rows]); r_ = np.array([r[1] for r in rows])
    return pd.DataFrame({"pixel_id": pid[q].astype(np.int64), "canonical_pixel_id": pid[r_].astype(np.int64),
                         "canonical_lat": reg["lat"].values[r_], "canonical_lon": reg["lon"].values[r_],
                         "overlap": np.array([ovr[int(x)] for x in q]),
                         "merged_src": reg["src"].values[q], "canonical_src": reg["src"].values[r_]})

def grid_spacing_by_export(reg, max_exports=12, sample=None):   # v20.57: None = every pixel of the export (was a 20,000 sample)
    """Median nearest-neighbour distance among the pixels of each export (by the newest source file): the grid
    spacing actually in the data, printed next to PIXEL_SIZE_M so a wrong setting is visible."""
    out = []
    for src, sub in reg.groupby("src"):
        if len(out) >= max_exports: break
        if len(sub) < 50: continue
        sub = sub.sample(min(len(sub), sample), random_state=0) if (sample and len(sub) > sample) else sub
        x, y = _metres(sub["lat"].values, sub["lon"].values, float(np.nanmedian(sub["lat"].values)))
        o = np.lexsort((y, x)); xs, ys = x[o], y[o]
        d = np.hypot(np.diff(xs), np.diff(ys)); d = d[d > 0.5]
        if len(d): out.append({"export": str(src), "pixels": int(len(sub)), "grid_spacing_m": float(np.round(np.median(d), 2))})
    return pd.DataFrame(out)

def build_pixel_overlap_map(shard_paths, output_dir, verbose=True):
    """Registry -> pairs -> canonical map. Writes pixel_overlap_map.parquet (only the merged pixels) and
    pixel_overlap_report.csv; returns (map_path or None, stats)."""
    t0 = __import__("time").time()
    reg = pixel_registry(shard_paths, verbose=verbose)
    pairs = near_duplicate_pairs(reg)
    cmap = canonical_pixel_map(reg, pairs)
    stats = {"pixels_in_registry": int(len(reg)), "pairs_at_or_above_threshold": int(len(pairs)),
             "pixels_merged": int(len(cmap)), "canonical_pixels_receiving": int(cmap["canonical_pixel_id"].nunique()) if len(cmap) else 0,
             "overlap_min": PIXEL_OVERLAP_MIN, "pixel_size_m": PIXEL_SIZE_M, "priority": DEDUP_PRIORITY,
             "median_overlap_merged": float(cmap["overlap"].median()) if len(cmap) else None,
             "seconds": round(__import__("time").time() - t0, 1)}
    os.makedirs(output_dir, exist_ok=True)
    rep = pd.DataFrame([stats])
    gs = grid_spacing_by_export(reg)
    rep.to_csv(os.path.join(output_dir, "pixel_overlap_report.csv"), index=False)
    if len(gs): gs.to_csv(os.path.join(output_dir, "pixel_grid_spacing_by_export.csv"), index=False)
    path = None
    if len(cmap):
        path = os.path.join(output_dir, "pixel_overlap_map.parquet")
        pq.write_table(pa.Table.from_pandas(cmap, preserve_index=False), path)
        if "merged_src" in cmap.columns:
            pairs_by_export = cmap.groupby(["merged_src", "canonical_src"]).size().rename("pixels").reset_index().sort_values("pixels", ascending=False)
            pairs_by_export.to_csv(os.path.join(output_dir, "pixel_overlap_by_export_pair.csv"), index=False)
    if verbose:
        (warn if len(cmap) else ok)(
            f"near-duplicate pixels: {stats['pixels_in_registry']:,} pixels, {stats['pairs_at_or_above_threshold']:,} pairs overlapping "
            f">= {PIXEL_OVERLAP_MIN:.0%} -> {stats['pixels_merged']:,} pixels merged onto their "
            f"{'newer' if DEDUP_PRIORITY == 'newer' else 'more complete'} counterpart ({stats['seconds']} s)")
        if len(gs):
            off = gs[(gs.grid_spacing_m - PIXEL_SIZE_M).abs() > 0.2 * PIXEL_SIZE_M]
            info("grid spacing measured per export: " + ", ".join(f"{r.export[-40:]} {r.grid_spacing_m} m" for r in gs.head(4).itertuples()))
            if len(off): warn(f"measured grid spacing differs from PIXEL_SIZE_M={PIXEL_SIZE_M} m for {len(off)} export(s) -- check the setting")
    return path, stats

def _pixel_map(path):
    """Worker-side cache of the canonical map as a Series pixel_id -> (canonical id, lat, lon)."""
    if not path or not os.path.exists(path): return None
    if path not in _PIXEL_MAP_CACHE:
        m = pq.read_table(path).to_pandas()
        _PIXEL_MAP_CACHE.clear()
        _PIXEL_MAP_CACHE[path] = m.set_index("pixel_id")[["canonical_pixel_id", "canonical_lat", "canonical_lon"]]
    return _PIXEL_MAP_CACHE[path]

def apply_pixel_map(block, path=None):
    """Remap near-duplicate pixel ids (and their coordinates) onto the canonical pixel. Returns (block, n_rows_remapped)."""
    m = _pixel_map(path or PIXEL_OVERLAP_MAP_PATH)
    if m is None or not len(block) or "pixel_id" not in block.columns: return block, 0
    hit = block["pixel_id"].isin(m.index).values
    if not hit.any(): return block, 0
    tgt = m.reindex(block.loc[hit, "pixel_id"].values)
    block = block.copy()
    block.loc[hit, "pixel_id"] = tgt["canonical_pixel_id"].values.astype(np.int64)
    if "latitude" in block.columns: block.loc[hit, "latitude"] = tgt["canonical_lat"].values
    if "longitude" in block.columns: block.loc[hit, "longitude"] = tgt["canonical_lon"].values
    return block, int(hit.sum())

# ====================== v20.30: PASS A -> PASS B blocks kept in RAM (P00) ======================
PICKLE_SAFE_BYTES = 256 * 2**20   # v20.50: largest in-RAM block sent to a PASS B worker process by pickling (Windows pipes)
IN_MEMORY_BLOCKS = False     # P00 sets True: PASS A hands its Year x Season blocks to PASS B in RAM while they fit below
                             # the 98 % ceiling (x MEM_BLOCK_COPIES); beyond it they spill to shard files (the previous
                             # path). P03 -> P04 run in different kernels, so they always use shard files.
MEM_BLOCK_COPIES = 3.0       # parent's blocks + a worker's copy + processing

SOURCE_ID_COLS = ("UID", "external_uid_final")
def _drop_source_ids(df):
    """v20.51: the exports' own point ids (UID) are dropped as soon as a file is processed. They were never used (pixel_id
    comes from the coordinates, v14) and are dropped from the panel anyway -- but one export stored them as 64-bit hashes
    (int64) and another, with a gap, as float64: writing both into one shard crashed PASS A with "Integer value
    6234264803062266584 not in range: 0 to 9007199254740992" (a float64 cannot hold that integer exactly)."""
    return df.drop(columns=[c for c in SOURCE_ID_COLS if c in df.columns])

class _TypeConflict(Exception):
    """A column whose type in this export cannot be converted exactly to the type the open shard file has."""

def _conform_table(table, schema):
    """v20.49: `table` with exactly the columns / order / types of `schema` (a column it lacks becomes all-null)."""
    cols = []
    for f in schema:
        if f.name in table.schema.names:
            c = table.column(f.name)
            if c.type != f.type:
                try:
                    c = c.cast(f.type)                       # safe: an inexact conversion raises, nothing is rounded
                except (pa.ArrowInvalid, pa.ArrowNotImplementedError, pa.ArrowTypeError) as e_:
                    raise _TypeConflict(f"{f.name}: {c.type} -> {f.type} ({e_})")
            cols.append(c)
        else:
            cols.append(pa.nulls(table.num_rows, type=f.type))
    return pa.Table.from_arrays(cols, schema=schema)

def _union_schema(paths):
    """v20.49: None when every parquet file has the same columns and types; else ONE schema holding all of them (first
    file's order, new columns appended, types promoted -- int -> float, null -> the other type)."""
    sch = [pq.read_schema(p_) for p_ in paths if p_ and os.path.exists(p_)]
    if len(sch) < 2 or all(s_.equals(sch[0], check_metadata=False) for s_ in sch[1:]): return None
    try:
        uni = pa.unify_schemas(sch, promote_options="permissive")
    except TypeError:                                   # pyarrow < 14: no promotion options
        uni = pa.unify_schemas(sch)
    info(f"panel assembly: the blocks differ in their columns -> one schema of {len(uni)} columns (a column a block "
         f"lacks is missing there, nothing is dropped)")
    return uni

class ShardParts:
    """v20.49: one Year x Season block ON DISK in several part files (a later export brought new columns). Read as
    one frame: the union of the columns, a column a part lacks is missing (NaN) there -- as MemBlock does in RAM."""
    def __init__(self, paths): self.paths = list(paths)
    @property
    def num_rows(self): return int(sum(pq_meta(p_)[0] for p_ in self.paths))
    def to_pandas(self, columns=None):
        fr = []
        for p_ in self.paths:
            names_ = pq.ParquetFile(p_).schema_arrow.names
            fr.append(pq.read_table(p_, columns=[c_ for c_ in columns if c_ in names_]).to_pandas() if columns else pq.read_table(p_).to_pandas())
        return (pd.concat(fr, ignore_index=True) if len(fr) > 1 else fr[0]) if fr else pd.DataFrame()

class MemBlock:
    """One Year x Season block held in RAM: the per-file frames PASS A produced, in file order."""
    def __init__(self): self.frames = []; self.nbytes = 0
    def add(self, f): self.frames.append(f); self.nbytes += int(f.memory_usage(deep=True).sum())
    @property
    def num_rows(self): return int(sum(len(f) for f in self.frames))
    def to_pandas(self, columns=None):
        fr = [f[[c_ for c_ in columns if c_ in f.columns]] if columns else f for f in self.frames]
        return (pd.concat(fr, ignore_index=True) if len(fr) > 1 else fr[0].reset_index(drop=True)) if fr else pd.DataFrame()

def _block_frame(src, columns=None):
    """A PASS A block as a DataFrame, from RAM (MemBlock) or from its shard file."""
    if isinstance(src, (MemBlock, ShardParts)): return src.to_pandas(columns)
    return pq.read_table(src, columns=columns).to_pandas() if columns else pq.read_table(src).to_pandas()

def _block_rows(src):
    return src.num_rows if isinstance(src, (MemBlock, ShardParts)) else pq_meta(src)[0]

def prepare_pass_b_block(yr, se, shard_path, dose_table=None, crosswalk=None):
    """Everything PASS B does to ONE block -- shared by the parallel workers and the sequential fallback, so both
    paths produce identical output. v20.6: build_treatment_columns and finalize_panel_block run ONCE each.
    Returns (block, dup_log, removed, duplicate_kinds, values_filled, n_unique_pixels)."""
    block = _block_frame(shard_path)                          # v20.30: from RAM (MemBlock) or its shard file
    block, _n_remapped = apply_pixel_map(block) if NEAR_DUPLICATE_PIXELS else (block, 0)   # v20.25: >= 80 % overlap = one pixel
    block, mp_stats = apply_missing_policy(block, stage="block", drop_empty=False)   # v20.16/30: NaN/0 -> NaN, floored covariates keep 0
    mp_stats["rows_remapped_near_duplicate"] = int(_n_remapped)
    dup_log = []
    before = len(block)
    block, dup_log = resolve_duplicates(block, conflict_log=dup_log)
    removed = before - len(block)
    # v20.58 (second pass): the rows without any outcome leave only NOW -- after the newer export's (empty) row has claimed its pixel-year-
    # season and its repeated rows were dropped whole (dropped before the dedup, an older repeated row took the empty row's place)
    if DROP_ROWS_WITHOUT_OUTCOME:
        block, mp_stats = drop_rows_without_outcome(block, mp_stats)
    # v20.17: what is left, per variable -- written to panel_missingness_report.csv by the parent
    _vars = [c for c in ZERO_RULE_VARS if c in block.columns]
    _core = (pd.to_numeric(block["buff_km"], errors="coerce") == TREAT_CORE_BUFFKM).values if "buff_km" in block.columns else np.zeros(len(block), bool)
    mp_stats["per_variable"] = {}
    for c in _vars:
        _v = pd.to_numeric(block[c], errors="coerce").values.astype(np.float64); _f = np.isfinite(_v)
        # v20.59: the block's exact moments (mean, M2 about it; merged across out-of-core pieces by the parallel formula) -> panel_variation_by_block.csv:
        # does the panel carry PIXEL variation in this variable and year-season, or one value for every pixel (a fill value)?
        _mu = float(_v[_f].mean()) if _f.any() else float("nan"); _m2 = float(((_v[_f] - _mu) ** 2).sum()) if _f.any() else 0.0
        mp_stats["per_variable"][c] = {"finite": int(_f.sum()), "finite_core": int((_f & _core).sum()),
                                       "finite_rings": int((_f & ~_core).sum()),
                                       "zero_after_policy": int((pd.to_numeric(block[c], errors="coerce") == 0).sum()),
                                       "moments": [[int(_f.sum()), _mu, _m2, float(_v[_f].min()) if _f.any() else float("nan"), float(_v[_f].max()) if _f.any() else float("nan")]]}
    mp_stats["rows_after_policy"] = int(len(block)); mp_stats["rows_core_after"] = int(_core.sum())
    mp_stats["rows_rings_after"] = int((~_core).sum())
    kinds = block.attrs.get("duplicate_kinds", {}); filled = block.attrs.get("values_filled_from_duplicates", 0)
    mp_stats["dedup_values_not_used"] = int(block.attrs.get("values_in_dropped_rows_not_used", 0))          # v20.58
    mp_stats["dedup_not_used_by_variable"] = dict(block.attrs.get("values_not_used_by_variable", {}) or {})
    d_ = block.duplicated(subset=[k for k in DEDUP_KEYS if k in block.columns]).sum()
    if d_:
        raise RuntimeError(f"INTERNAL: {d_} duplicate pixel-Year-Season rows remain in shard "
                           f"{yr}/{SEASON_LABEL[se]} after dedup -- refusing to write a corrupt panel")
    if "site_check" in block.columns:                                       # v20.58: an outside pixel is one pixel, whatever id its files gave
        _o = pd.to_numeric(block["site_check"], errors="coerce").values == 3
        if _o.any() and block.loc[_o].duplicated(subset=["pixel_id", "Year", "Season"]).any():
            raise RuntimeError(f"INTERNAL: a pixel outside every polygon is still repeated in {yr}/{SEASON_LABEL[se]} after dedup -- refusing to write a corrupt panel")
    if dose_table is not None and crosswalk is not None:
        if "District" not in block.columns:
            block = block.merge(crosswalk, left_on="site_name", right_on="Sub Watershed Name", how="left")
        dsub = dose_table[(dose_table["target_agri_year"] == yr) & (dose_table["target_season"] == se)]
        dsub = dsub[[c_ for c_ in ("District", "dose_per_subwshed", "dose_amount_sws", "dose_intensity_per_ha",
                                   "first_treat_agri_year", "first_treat_season") if c_ in dsub.columns]].drop_duplicates("District")
        block = block.merge(dsub, on="District", how="left")
    else:
        for c_ in ("District", "Sub Watershed Name", "dose_per_subwshed", "dose_amount_sws", "dose_intensity_per_ha",
                   "first_treat_agri_year", "first_treat_season"):
            if c_ not in block.columns: block[c_] = np.nan
    block = block.sort_values(["subwshed_id", "pixel_id"], kind="stable").reset_index(drop=True)
    block = build_treatment_columns(block)          # ONCE (was twice)
    # v20.38: the dose belongs to the TREATMENT AREA -- control rings receive none, and before the programme it is 0
    for c_ in ("dose_amount_sws", "dose_intensity_per_ha"):
        if c_ not in block.columns: block[c_] = np.nan
        block[c_] = pd.to_numeric(block[c_], errors="coerce").astype("float32")
        block.loc[block["treatment"].values != 1, c_] = 0.0
        block.loc[(block["treatment"].values == 1) & (block["post"].values == 0), c_] = 0.0
    # v20.27: DESIGN CHECK -- every row placed and coded by the rules, before the block is written:
    #   buffer 0 -> treatment = 1, control = 0 | buffers 1-5 -> control = 1, treatment = 0 | anything else -> neither
    #   post = 1 for Year >= TREATMENT_YEAR (2022), pre = 1 for Year < 2022 | did_term = treatment x post
    _bk = pd.to_numeric(block["buff_km"], errors="coerce").values
    _yr = pd.to_numeric(block["Year"], errors="coerce").values
    _ps = max(int(POST_CUTOFF), int(TREATMENT_YEAR) + 1) if EXCLUDE_TRANSITION_YEAR else int(POST_CUTOFF)
    _exp_t = (_bk == TREAT_CORE_BUFFKM); _exp_c = np.isin(_bk, list(DEFAULT_CONTROL_ZONES))
    _exp_post = _yr >= _ps; _exp_pre = _yr < (int(TREATMENT_YEAR) if EXCLUDE_TRANSITION_YEAR else int(POST_CUTOFF))
    _flag = export_post_flag(block) if (POST_FROM_EXPORT_TREAT and not EXCLUDE_TRANSITION_YEAR) else None   # v20.59: the exports' flag where a row has one
    if _flag is not None:
        _fok = np.isfinite(_flag); _exp_post = np.where(_fok, _flag == 1, _exp_post); _exp_pre = ~_exp_post
    _t = block["treatment"].values.astype(int); _c = block["control"].values.astype(int)
    _po = block["post"].values.astype(int); _pr = block["pre"].values.astype(int); _dd = block["did_term"].values.astype(int)
    viol = {"treatment_not_buffer0": int((_t != _exp_t.astype(int)).sum()),
            "control_not_buffer1to5": int((_c != _exp_c.astype(int)).sum()),
            "treatment_and_control": int(((_t == 1) & (_c == 1)).sum()),
            "post_not_flag_or_rule": int((_po != _exp_post.astype(int)).sum()),
            "pre_not_flag_or_rule": int((_pr != _exp_pre.astype(int)).sum()),
            "did_not_treatment_x_post": int((_dd != _t * _po).sum()),
            "treat_not_treatment": int((block["treat"].values.astype(int) != _t).sum()),        # v20.59: the aliases every model reads
            "did_not_did_term": int((block["did"].values.astype(int) != _dd).sum())}
    _grp = np.where(_t == 1, "treatment (buffer 0)", np.where(_c == 1, "control (buffer 1-5)", "neither (invalid buffer)"))
    _per = np.where(_po == 1, "post", np.where(_pr == 1, "pre", "transition"))
    xt = pd.DataFrame({"buff_km": _bk, "group": _grp, "period": _per}).value_counts().rename("rows").reset_index()
    mp_stats["design"] = {"violations": viol, "xtab": xt.to_dict("records"),
                          "invalid_buffer_rows": int((_bk < 0).sum()),
                          "post_from_export_flag": int(block.attrs.get("post_from_export_flag", 0)),      # v20.59
                          "post_from_rule": int(block.attrs.get("post_from_rule", 0)),
                          "post_flag_vs_rule_differ": int(block.attrs.get("post_flag_vs_rule_differ", 0)),
                          "export_treat_mismatch_rows": int(pd.to_numeric(block.get("treat_period_mismatch_flag", pd.Series(0, index=block.index)), errors="coerce").fillna(0).sum()),
                          "buff_km_recoded": dict(block.attrs.get("buff_km_recoded", {}))}
    # v20.6: treatment_group / control_group / pre_period / post_period / row_id are in DROPPED_FROM_PANEL, so
    # assigning them here was dead work -- finalize_panel_block removes them. The file keeps the canonical
    # columns: treatment, control, pre, post, did_term (int8).
    block = finalize_panel_block(block)             # ONCE (was twice)
    return block, dup_log, removed, kinds, filled, int(block["pixel_id"].nunique()), mp_stats


# ====================== v20.58: PASS B OUT OF CORE -- a block beyond 98 % of the RAM (your rule: only there) ======================
# One Year x Season block is normally processed whole by one worker. A block whose working set would pass 98 % of the RAM (or every block,
# REWARD_FORCE_OUT_OF_CORE: the checks) is split into PIXEL-RANGE pieces -- every row of a pixel (after the near-duplicate map) in one piece,
# the pieces in pixel order -- each processed by the same prepare_pass_b_block on Dask, Spark or the built-in batches (OUT_OF_CORE in
# _paths.py). The block's rows are then written sub-watershed by sub-watershed, piece by piece: exactly the order of the whole block's
# stable sort by (subwshed_id, pixel_id) -- the same panel. Duplicates are resolved per (site, pixel, year, season): never split.
def _block_tables(src, columns=None):
    """The rows of a PASS A block, one table at a time, in the block's order (MemBlock frames, ShardParts part by part, row groups)."""
    if isinstance(src, MemBlock):
        for f in src.frames:
            yield pa.Table.from_pandas(f[[c for c in columns if c in f.columns]] if columns else f, preserve_index=False)
        return
    for p_ in (src.paths if isinstance(src, ShardParts) else [src]):
        pf = pq.ParquetFile(p_)
        try:
            names = pf.schema_arrow.names
            for i in range(pf.num_row_groups):
                yield pf.read_row_group(i, columns=[c for c in columns if c in names] if columns else None)
        finally:
            try: pf.close()
            except Exception: pass

def _mapped_ids(t, m):
    v = t["pixel_id"].to_numpy(zero_copy_only=False).astype(np.int64)
    if m is not None:
        hit = np.isin(v, m.index.values)
        if hit.any():
            v = v.copy(); v[hit] = m.reindex(v[hit])["canonical_pixel_id"].values.astype(np.int64)
    return v

def _merge_moments(parts):
    """v20.59: [n, mean, M2, min, max] pieces (one per out-of-core piece of a block) -> (n, mean, SD, min, max) of the whole block, exactly
    (the parallel-variance formula); None when nothing is finite."""
    n = 0; mu = 0.0; m2 = 0.0; lo = float("inf"); hi = float("-inf")
    for p in parts:
        k = int(p[0])
        if not k: continue
        d = float(p[1]) - mu; N = n + k
        mu = mu + d * k / N; m2 = m2 + float(p[2]) + d * d * n * k / N; n = N
        lo = min(lo, float(p[3])); hi = max(hi, float(p[4]))
    if not n: return None
    return (n, mu, (m2 / (n - 1)) ** 0.5 if n > 1 else 0.0, lo, hi)

def _merge_stats(dicts):
    out = {}
    for d in dicts:
        for k, v in (d or {}).items():
            if isinstance(v, (bool, np.bool_)): out[k] = bool(out.get(k, False)) or bool(v)
            elif isinstance(v, (int, float, np.integer, np.floating)): out[k] = out.get(k, 0) + v
            elif isinstance(v, dict): out[k] = _merge_stats([out.get(k, {}), v])
            elif isinstance(v, list): out.setdefault(k, []).extend(v)
            else: out.setdefault(k, v)
    return out

def _pass_b_ooc_keys(jobs, n_workers):
    """The blocks that go out of core: every one when forced (the checks); else a block whose working set passes 98 % of the RAM."""
    try:
        import _outofcore as _O, _hardware as _H
    except Exception:
        return set(), None
    if _O.forced(): return set(j[0] for j in jobs), _O.forced() if _O.forced() in _O.KNOWN_ENGINES else _O.choose_engine(verbose=True)
    b = _H.ram_budget_bytes()
    if b is None: return set(), None
    keys = set(j[0] for j in jobs if _block_rows(j[1]) * PASS_B_BYTES_PER_ROW > b)
    return keys, (_O.choose_engine(verbose=True) if keys else None)

def _pass_b_block_ooc(job, engine, parts_dir):
    """One block out of core -> the same result tuple as _pb_worker (its part file written in the panel's order)."""
    import _outofcore as _O
    (yr, se), src, part_path, dose_records, cw_records = job
    rows = _block_rows(src)
    env = os.environ.get("REWARD_OOC_PARTITIONS")
    try:
        import _hardware as _H
        b = _H.ram_budget_bytes() or 4e9
    except Exception:
        b = 4e9
    K = max(2, int(env)) if env else max(2, int(np.ceil(rows * PASS_B_BYTES_PER_ROW * 2.0 / max(b / max(_O._cores(), 1), 1.0))))
    m = _pixel_map(PIXEL_OVERLAP_MAP_PATH) if NEAR_DUPLICATE_PIXELS else None
    ids = np.concatenate([_mapped_ids(t, m) for t in _block_tables(src, ["pixel_id"])] or [np.zeros(0, np.int64)])
    u, cnt = np.unique(ids, return_counts=True); cum = np.cumsum(cnt); del ids
    bounds = sorted(set(int(u[min(len(u) - 1, int(np.searchsorted(cum, cum[-1] * j / K)))]) for j in range(1, K))) if len(u) else []
    bounds = [x for x in bounds if x > (int(u[0]) if len(u) else 0)]
    subdir = os.path.join(parts_dir, f"ooc_{yr}_{SEASON_LABEL[se]}"); os.makedirs(subdir, exist_ok=True)
    files = [[] for _ in range(len(bounds) + 1)]
    for ti, t in enumerate(_block_tables(src, None)):
        j = np.searchsorted(np.asarray(bounds, dtype=np.int64), _mapped_ids(t, m), side="right")
        for jj in np.unique(j):
            f = os.path.join(subdir, f"piece{int(jj):03d}_t{ti:05d}.parquet")
            pq.write_table(t.take(pa.array(np.flatnonzero(j == jj))), f, compression="zstd"); files[int(jj)].append(f)
    tasks = [{"key": [int(yr), int(se)], "files": fl, "out": os.path.join(subdir, f"out{jj:03d}"), "dose": dose_records, "cw": cw_records,
              "cfg": _settings_snapshot(), "known": list(KNOWN_SUBWSHED_NAMES)} for jj, fl in enumerate(files) if fl]
    info(f"PASS B block Year={yr} Season={SEASON_LABEL[se]}: {rows:,} rows OUT OF CORE -- {len(tasks)} pixel-range pieces on {_O.ENGINE_LABEL[engine]}"
         + (" (forced: a check)" if _O.forced() else " (the whole block would pass 98 % of the RAM)"))
    res = [g["result"] for g in _O.Pool(engine).map("pass_b_piece", tasks)]
    subs = sorted(set().union(*[set(r["outs"]) for r in res]))
    writer = None; buf, nbuf, total = [], 0, 0
    def _flush(final=False):
        nonlocal writer, buf, nbuf
        if not buf: return
        t_ = pa.concat_tables(buf) if len(buf) > 1 else buf[0]
        if writer is None: writer = pq.ParquetWriter(part_path, t_.schema, compression="zstd")
        elif t_.schema != writer.schema: t_ = _conform_table(t_, writer.schema)
        if final or t_.num_rows >= ROW_GROUP_SIZE:
            n_full = t_.num_rows if final else (t_.num_rows // ROW_GROUP_SIZE) * ROW_GROUP_SIZE
            writer.write_table(t_.slice(0, n_full), row_group_size=ROW_GROUP_SIZE)
            rest = t_.slice(n_full); buf, nbuf = ([rest], rest.num_rows) if rest.num_rows else ([], 0)
        else:
            buf, nbuf = [t_], t_.num_rows
    for s_ in subs:
        for r in res:
            if s_ in r["outs"]:
                t_ = pq.read_table(r["outs"][s_]); buf.append(t_); nbuf += t_.num_rows; total += t_.num_rows
                if nbuf >= ROW_GROUP_SIZE: _flush()
    _flush(final=True)
    if writer: writer.close()
    mp = _merge_stats([r["mp"] for r in res])
    xt = (mp.get("design") or {}).get("xtab")
    if xt:
        mp["design"]["xtab"] = (pd.DataFrame(xt).groupby(["buff_km", "group", "period"], as_index=False)["rows"].sum()
                                .sort_values("rows", ascending=False, kind="stable").to_dict("records"))
    kinds = _merge_stats([r["kinds"] for r in res])
    try:
        import shutil as _sh; _sh.rmtree(subdir, ignore_errors=True)
    except Exception:
        pass
    return ((yr, se), part_path, int(total), [x for r in res for x in (r["dup_log"] or [])], int(sum(r["removed"] for r in res)), kinds,
            int(sum(r["filled"] or 0 for r in res)), int(sum(r["n_pix"] for r in res)), mp)

def run_pass_b(shard_paths, output_dir, dose_table=None, crosswalk=None, n_workers=None):
    """Read shards back in the REQUIRED final order and stream them into one combined file.

    v20.6: the per-block work runs in parallel across processes (all cores, RAM-aware); the final file is then
    written by streaming the parts in order, so `did_panel_full.parquet` is identical to the sequential build.

    The final panel carries the DiD columns materialised with the ACTIVE scenario -- `treatment`, `control`,
    `pre`, `post`, `did_term` (int8) -- so you can open the Parquet file and read them without running any code.
    (The aliases treatment_group / control_group / pre_period / post_period are listed in DROPPED_FROM_PANEL and
    are NOT written; earlier versions claimed otherwise in this docstring and in the closing message.) Every estimator still calls build_treatment_columns() itself and
    recomputes them for whatever control rings / timing / year window that run uses."""
    os.makedirs(output_dir, exist_ok=True)
    ordered_keys = sorted(shard_paths.keys(), key=lambda k: (k[0], SEASON_SORT_RANK[k[1]]))
    final_path = os.path.join(output_dir, "did_panel_full.parquet")
    # v20.25: near-duplicate pixels -- one registry across ALL blocks, built before any block is processed, so the
    # same physical pixel carries the same canonical id in every year and season
    global PIXEL_OVERLAP_MAP_PATH
    PIXEL_OVERLAP_MAP_PATH = None; _overlap_stats = {"enabled": bool(NEAR_DUPLICATE_PIXELS)}
    if NEAR_DUPLICATE_PIXELS:
        PIXEL_OVERLAP_MAP_PATH, _st = build_pixel_overlap_map(shard_paths, output_dir, verbose=True)
        _overlap_stats.update(_st)
    else:
        info("near-duplicate pixel merging is OFF (NEAR_DUPLICATE_PIXELS = False) -- only identical coordinates are one pixel")
    # v20.8: write to a .building file and rename only after the footer is closed. A Parquet file gets its
    # footer (the "magic bytes") ONLY at close(), so a run that is interrupted mid-PASS-B used to leave a
    # truncated did_panel_full.parquet that nothing could open -- the "Parquet magic bytes not found" warning.
    build_path = final_path + ".building"
    for _stale in (build_path,):
        if os.path.exists(_stale):
            warn(f"removing an unfinished panel from a previous run: {os.path.basename(_stale)}")
            try: os.remove(_stale)
            except Exception: pass
    parts_dir = os.path.join(output_dir, "_pass_b_parts"); os.makedirs(parts_dir, exist_ok=True)
    shard_dup_log = []; total_rows = 0

    rows_guess = 2_000_000
    try:
        rows_guess = max(_block_rows(shard_paths[ordered_keys[0]]), 500_000)
    except Exception:
        pass
    n_workers = n_workers or PASS_B_WORKERS or pass_b_worker_count(len(ordered_keys), rows_guess)

    dose_records = dose_table.to_dict("records") if dose_table is not None else None
    cw_records = crosswalk.to_dict("records") if crosswalk is not None else None
    if n_workers > 1:
        # v20.50: a block held in RAM (MemBlock) is PICKLED into the worker process's pipe. On Windows a message of
        # several GB fails -- "OSError: [WinError 87] The parameter is incorrect" in multiprocessing's _feed, then
        # BrokenProcessPool and "handle is closed" (your run: block 32 of 43; the rest then ran sequentially). A block
        # above PICKLE_SAFE_BYTES is written to a shard file first and its worker reads the file: the same rows, the same
        # function, no multi-GB message. Blocks the parent processes itself (no pool) stay in RAM.
        _spilled, _gb = 0, 0.0
        for _k in ordered_keys:
            _src = shard_paths[_k]
            if isinstance(_src, MemBlock) and _src.nbytes > PICKLE_SAFE_BYTES:
                _p = os.path.join(parts_dir, f"spill_{_k[0]}_{SEASON_LABEL[_k[1]]}.parquet")
                _gb += _src.nbytes / 1e9
                _t = pa.Table.from_pandas(_src.to_pandas(), preserve_index=False)
                pq.write_table(_t, _p, compression="zstd"); del _t
                shard_paths[_k] = _p; _spilled += 1
        if _spilled:
            info(f"PASS B: {_spilled} in-RAM block(s) ({_gb:.1f} GB) handed to the worker processes as files "
                 f"(a pickled block above {PICKLE_SAFE_BYTES / 2**20:.0f} MB breaks the Windows process pool)")
    jobs = [((yr, se), shard_paths[(yr, se)], os.path.join(parts_dir, f"part_{yr}_{SEASON_LABEL[se]}.parquet"),
             dose_records, cw_records) for (yr, se) in ordered_keys]

    results = {}
    pool = None
    if n_workers > 1:
        try:
            from concurrent.futures import ProcessPoolExecutor
            import multiprocessing as _mp
            cfg = _settings_snapshot()                               # v20.58: every setting (was: a list of 14 -- the negative-covariate rule missing)
            _mdir = os.path.dirname(os.path.abspath(__file__))
            os.environ["PYTHONPATH"] = _mdir + os.pathsep + os.environ.get("PYTHONPATH", "")
            pool = ProcessPoolExecutor(max_workers=n_workers, mp_context=_mp.get_context("spawn"),
                                       initializer=_pa_worker_init, initargs=(_mdir, KNOWN_SUBWSHED_NAMES, cfg))
            print(f"[INFO]    PASS B running {len(jobs)} blocks on {n_workers} worker processes")
        except Exception as e:
            print(f"[WARNING] could not start the PASS B pool ({type(e).__name__}: {e}) -- running sequentially")
            pool = None

    policy_totals = {"zero_cells_set_missing": 0, "rows_dropped_no_outcome": 0, "rows_remapped_near_duplicate": 0}
    dedup_totals = {"values_filled": 0, "values_not_used": 0, "not_used_by_variable": {}}        # v20.58
    missing_rows = []                                        # v20.17: per block x variable
    variation_rows = []                                      # v20.59: per block x variable -- rows, mean, SD across pixels, min, max (pixel variation, or a fill value)
    design_rows, design_viol, design_notes = [], {}, {"invalid_buffer_rows": 0, "export_treat_mismatch_rows": 0,   # v20.27
                                                      "post_from_export_flag": 0, "post_from_rule": 0, "post_flag_vs_rule_differ": 0}   # v20.59
    neg_rows = []                                                                                                   # v20.30
    def _emit(r):
        key, path, nrows, dlog, removed, kinds, filled, n_pix, mp = r
        results[key] = (path, nrows, n_pix)
        for k_ in policy_totals: policy_totals[k_] += int(mp.get(k_, 0))
        for _kind in ("negative_floored_to_zero", "negative_nodata_to_missing", "negative_blocked_to_missing"):   # v20.30
            for _v, _n in (mp.get(_kind) or {}).items():
                neg_rows.append({"Year": key[0], "Season": SEASON_LABEL[key[1]], "variable": _v, "action": _kind, "cells": int(_n)})
        _dz = mp.get("design") or {}
        for k_, v_ in (_dz.get("violations") or {}).items(): design_viol[k_] = design_viol.get(k_, 0) + int(v_)
        for k_ in design_notes: design_notes[k_] += int(_dz.get(k_, 0))
        for r_ in (_dz.get("xtab") or []): design_rows.append({"Year": key[0], "Season": SEASON_LABEL[key[1]], **r_})
        if any(int(v_) for v_ in (_dz.get("violations") or {}).values()):
            raise RuntimeError(f"INTERNAL: block {key} breaks the DiD design rules {_dz['violations']} -- refusing to write the panel")
        for v_, st_ in (mp.get("per_variable") or {}).items():
            rc, rr = mp.get("rows_core_after", 0), mp.get("rows_rings_after", 0)
            missing_rows.append({"Year": key[0], "Season": SEASON_LABEL[key[1]], "variable": v_, "rows": nrows,
                                 "finite": st_["finite"], "missing": nrows - st_["finite"],
                                 "share_missing": round((nrows - st_["finite"]) / max(nrows, 1), 4),
                                 "rows_core_in_export": mp.get("rows_core", rc), "rows_core_dropped_no_outcome": mp.get("rows_dropped_no_outcome_core", 0),
                                 "finite_core": st_.get("finite_core", 0), "share_missing_core": round(1 - st_.get("finite_core", 0) / max(mp.get("rows_core", rc), 1), 4),
                                 "rows_rings_in_export": mp.get("rows_rings", rr), "finite_rings": st_.get("finite_rings", 0),
                                 "share_missing_rings": round(1 - st_.get("finite_rings", 0) / max(mp.get("rows_rings", rr), 1), 4),
                                 "zero_after_policy": st_["zero_after_policy"]})
            _mm = _merge_moments(st_.get("moments") or [])                       # v20.59
            if _mm is not None:
                variation_rows.append({"Year": key[0], "Season": SEASON_LABEL[key[1]], "variable": v_, "finite": _mm[0], "mean": _mm[1],
                                       "sd_across_pixels": _mm[2], "min": _mm[3], "max": _mm[4],
                                       "constant_across_pixels": bool(_mm[0] > 1 and _mm[2] <= 1e-9 * max(1.0, abs(_mm[1])))})
            _floored_ = {k for k, r in NEGATIVE_COVARIATE_RULE.items() if r == "zero" and not ALLOW_NEGATIVE_COVARIATES}
            if st_["zero_after_policy"] and ZERO_AS_MISSING and v_ not in ZERO_RULE_EXCEPT and v_ not in _floored_:   # v20.30
                raise RuntimeError(f"INTERNAL: {st_['zero_after_policy']} exact-zero {v_} cells survived the missing-value "
                                   f"policy in block {key} -- refusing to write a panel that violates it")
        if mp.get("zero_cells_set_missing") or mp.get("rows_dropped_no_outcome"):
            info(f"   Year={key[0]} {SEASON_LABEL[key[1]]}: missing-value policy -> {mp['zero_cells_set_missing']:,} "
                 f"zero cells set to missing, {mp['rows_dropped_no_outcome']:,} rows without any outcome dropped")
        if dlog: shard_dup_log.extend(dlog)
        _nu = int(mp.get("dedup_values_not_used", 0) or 0)
        dedup_totals["values_filled"] += int(filled or 0); dedup_totals["values_not_used"] += _nu
        for _v, _n in (mp.get("dedup_not_used_by_variable") or {}).items():
            dedup_totals["not_used_by_variable"][_v] = dedup_totals["not_used_by_variable"].get(_v, 0) + int(_n)
        if removed:
            detail = ", ".join(f"{v:,} {k}" for k, v in sorted(kinds.items())) or "kind unknown"
            warn(f"   Year={key[0]} {SEASON_LABEL[key[1]]}: {removed:,} duplicate pixel-rows resolved to one row "
                 f"per (pixel, Year, Season) [{detail}]"
                 + (f"; {filled:,} missing values FILLED from the dropped rows (DEDUP_FILL_FROM_DUPLICATES = True)" if filled else
                    f"; the dropped (repeated) rows carried {_nu:,} value(s) where the kept row has a gap -- NOT used, a repeated "
                    f"row is dropped whole (DEDUP_FILL_FROM_DUPLICATES = False)" if _nu else
                    "; the dropped rows carried no value the kept row lacks"))
        print(f"[Pass B] block Year={key[0]} Season={SEASON_LABEL[key[1]]} ready "
              f"({nrows:,} rows, {n_pix:,} unique pixels)")

    _ooc_keys, _ooc_eng = _pass_b_ooc_keys(jobs, n_workers)          # v20.58: beyond 98 % of the RAM -- out of core (exact, the same panel)
    for j in [j for j in jobs if j[0] in _ooc_keys]:
        _emit(_pass_b_block_ooc(j, _ooc_eng, parts_dir))
    jobs = [j for j in jobs if j[0] not in _ooc_keys]
    if pool is None:
        for j in progress(jobs, desc="PASS B blocks", unit="block"):
            _emit(_pb_worker(j))
    else:
        try:
            for r in progress(pool.map(_pb_worker, jobs), total=len(jobs), desc="PASS B blocks", unit="block"):
                _emit(r)
        except Exception as e:
            print(f"[WARNING] PASS B pool failed ({type(e).__name__}: {e}) -- finishing the remaining blocks sequentially")
            for j in jobs:
                if j[0] not in results: _emit(_pb_worker(j))
        finally:
            pool.shutdown(wait=True)

    # ---- assemble the single panel, in order, by streaming the parts (no recomputation) ----
    writer = None
    _uni = _union_schema([results[k][0] for k in ordered_keys])    # v20.49: None when every block has the same columns
    for (yr, se) in progress(ordered_keys, desc="PASS B assemble", unit="block"):
        path, nrows, _npix = results[(yr, se)]
        pf = pq.ParquetFile(path)
        try:
            n_rg = pf.num_row_groups
        except Exception:
            n_rg = 0
        for i in range(n_rg):
            table = pf.read_row_group(i)
            if writer is None:
                writer = pq.ParquetWriter(build_path, _uni if _uni is not None else table.schema, compression="zstd",
                                          use_dictionary=["Season", "schema_vintage", "src_file", "LandUse",
                                                          "time_fe_year", "time_fe_yearseason", "period"])
            if _uni is not None:
                table = _conform_table(table, writer.schema)       # v20.49: a column this block lacks -> null
            elif table.schema is not writer.schema:
                table = table.cast(writer.schema)
            writer.write_table(table, row_group_size=ROW_GROUP_SIZE)
        try: pf.close()                                   # v20.10: release the part file before it is deleted
        except Exception: pass
        total_rows += nrows
        print(f"[Pass B] wrote Year={yr} Season={SEASON_LABEL[se]} ({nrows:,} rows) -> running total {total_rows:,}")
    if writer: writer.close()
    # footer is on disk now -> the file is readable; publish it atomically
    if os.path.exists(build_path):
        try:
            nrows_built, _rg, _names = pq_meta(build_path)   # proof the footer is there; handle CLOSED afterwards
        except Exception as e:
            raise RuntimeError(f"PASS B produced an unreadable file ({e}); the previous panel (if any) was left "
                               f"untouched. The parts are kept in {parts_dir} for inspection.")
        if os.path.exists(final_path) and not pq_is_readable(final_path):
            q = quarantine_file(final_path)
            if q: warn(f"unreadable file at the final name moved aside: {os.path.basename(q)}")
        publish_atomic(build_path, final_path)               # v20.10: gc + retry, Windows-safe
    try:
        import shutil as _sh; _sh.rmtree(parts_dir, ignore_errors=True)
    except Exception:
        pass
    # v20.25: how this panel was built -- final_panel_is_valid() compares it with the current settings
    try:
        _rem = int(policy_totals.get("rows_remapped_near_duplicate", 0))
        with open(os.path.join(output_dir, "panel_build_settings.json"), "w", encoding="utf-8") as _fh:
            json.dump({"engine_policy": "v20.58", "near_duplicate_pixels": _overlap_stats,
                       "negative_barrier": {"rule": dict(NEGATIVE_COVARIATE_RULE), "allow_negative": bool(ALLOW_NEGATIVE_COVARIATES),
                                            "nodata_below": NODATA_SENTINEL_BELOW, "temperature_clamp_nodata": TEMPERATURE_CLAMP_NODATA},
                       "dedup_priority": DEDUP_PRIORITY, "zero_as_missing": bool(ZERO_AS_MISSING),
                       "dedup_fill_from_duplicates": bool(DEDUP_FILL_FROM_DUPLICATES),                        # v20.58
                       "post_from_export_treat": bool(POST_FROM_EXPORT_TREAT and not EXCLUDE_TRANSITION_YEAR),   # v20.59
                       "post_from_export_flag_rows": int(design_notes.get("post_from_export_flag", 0)), "post_from_rule_rows": int(design_notes.get("post_from_rule", 0)),
                       "post_flag_vs_rule_differ_rows": int(design_notes.get("post_flag_vs_rule_differ", 0)),
                       "dedup_values_filled": int(dedup_totals["values_filled"]), "dedup_values_not_used": int(dedup_totals["values_not_used"]),
                       "rows_remapped_near_duplicate": _rem, "written": _ts()}, _fh, indent=1, default=str)
    except Exception as _e:
        warn(f"panel_build_settings.json not written ({_e})")
    # v20.30: what the negative-covariate barrier did (floored to 0 / no-data -> missing / blocked), per block x variable
    try:
        _nr = pd.DataFrame(neg_rows, columns=["Year", "Season", "variable", "action", "cells"])
        _nr.to_csv(os.path.join(output_dir, "negative_covariates_report.csv"), index=False)
        if len(_nr):
            _tot = _nr.groupby(["variable", "action"])["cells"].sum()
            info("negative covariates (barrier " + ("OFF" if ALLOW_NEGATIVE_COVARIATES else "on") + "): "
                 + "; ".join(f"{v} {a.replace('negative_', '').replace('_', ' ')} {n:,}" for (v, a), n in _tot.items()) + " -> negative_covariates_report.csv")
        else:
            ok("no negative covariate values in the panel (negative_covariates_report.csv is empty)")
    except Exception as _e:
        warn(f"negative-covariate report skipped ({_e})")
    # v20.59: PIXEL VARIATION per block x variable -- a year-season with ONE value for every pixel is a fill value, not a measurement: the outcome
    # screen of every model leaves it out (OUTCOME_SCREEN); this table shows it right after P00, before any model runs
    try:
        if variation_rows:
            vt = pd.DataFrame(variation_rows).sort_values(["variable", "Year", "Season"])
            vt.to_csv(os.path.join(output_dir, "panel_variation_by_block.csv"), index=False)
            _k = vt[vt["constant_across_pixels"] & vt["variable"].isin(OUTCOME_VARS + ["ESI", "WSSI", "WSI", "SMDI", "VCI", "TCI", "VHI"])]
            if len(_k):
                warn(f"{len(_k)} of {int(vt['variable'].isin(OUTCOME_VARS + ['ESI', 'WSSI', 'WSI', 'SMDI', 'VCI', 'TCI', 'VHI']).sum())} outcome x year-season cells hold ONE value for "
                     f"every pixel (a fill value, not pixel data: the outcome screen of every model leaves them out unless OUTCOME_SCREEN = 'keep'): "
                     + "; ".join(f"{r.variable} {r.Year} {r.Season} = {r.mean:.6g}" for r in _k.head(8).itertuples()) + ("; ..." if len(_k) > 8 else "")
                     + " -> panel_variation_by_block.csv")
            else:
                ok(f"pixel variation CONFIRMED in every outcome x year-season cell ({len(vt):,} cells, no fill value) -> panel_variation_by_block.csv")
    except Exception as _e:
        warn(f"variation report skipped ({_e})")
    # v20.27: the DiD design, as built -- rows per buffer x group x period, with the rules it was checked against
    try:
        if design_rows:
            dz = pd.DataFrame(design_rows)
            dz.to_csv(os.path.join(output_dir, "panel_design_check.csv"), index=False)
            summ = dz.groupby(["group", "period"])["rows"].sum().unstack(fill_value=0)
            _ps_ = max(int(POST_CUTOFF), int(TREATMENT_YEAR) + 1) if EXCLUDE_TRANSITION_YEAR else int(POST_CUTOFF)
            if POST_FROM_EXPORT_TREAT and not EXCLUDE_TRANSITION_YEAR:      # v20.59: your rule -- the exports' flag is the panel's period
                info(f"DiD design columns in the panel -- treat / treatment (buffer 0), control (rings 1-5), post = the exports' Treat flag (1 = post, 0 = pre): "
                     f"{design_notes['post_from_export_flag']:,} rows from the flag, {design_notes['post_from_rule']:,} without a usable flag from the rule "
                     f"Year >= {_ps_}; pre = 1 - post; did / did_term = treat x post. The models apply THEIR design when they run and say where it differs:")
            else:
                info(f"DiD design (treatment year {TREATMENT_YEAR}: pre = Year < {TREATMENT_YEAR}, post = Year >= {_ps_}; buffer 0 = treatment, 1-5 = control"
                     + ("; POST_FROM_EXPORT_TREAT = False: the rule, not the exports' flag" if not POST_FROM_EXPORT_TREAT else "; the transition year is held out: the rule, not the flag") + "):")
            print(summ.to_string())
            ok(f"design rules hold on every row ({sum(design_viol.values())} violations) -> panel_design_check.csv")
            if design_notes["invalid_buffer_rows"]:
                warn(f"{design_notes['invalid_buffer_rows']:,} rows carry a buffer code outside 0-5 -- they are in NEITHER group (see panel_design_check.csv)")
            if design_notes["export_treat_mismatch_rows"]:
                warn(f"{design_notes['export_treat_mismatch_rows']:,} rows whose EXPORTED Treat flag disagrees with Treat = 1{{Year >= {TREATMENT_YEAR}}} "
                     f"(an export made with another treatment year or rule)"
                     + (" -- the panel's post / pre FOLLOW THE FLAG (POST_FROM_EXPORT_TREAT = True, your rule); every model applies its own design "
                        "when it runs and says on how many rows it differs from the panel's" if POST_FROM_EXPORT_TREAT and not EXCLUDE_TRANSITION_YEAR
                        else "; the panel uses the rule, not the flag"))
    except RuntimeError:
        raise
    except Exception as _e:
        warn(f"design report skipped ({_e})")
    # v20.17: the missing-value picture of the finished panel, per block and variable
    try:
        if missing_rows:
            mr = pd.DataFrame(missing_rows)
            mr.to_csv(os.path.join(output_dir, "panel_missingness_report.csv"), index=False)
            tot = mr.groupby("variable").agg(rows=("rows", "sum"), missing=("missing", "sum"))
            tot["share_missing"] = (tot["missing"] / tot["rows"].replace(0, np.nan)).round(4)
            worst = tot.sort_values("share_missing", ascending=False).head(6)
            info("missing after the policy (NaN or exact 0 = no-data), share of rows per variable: "
                 + ", ".join(f"{v} {r.share_missing:.1%}" for v, r in worst.iterrows()))
            if "rows_core_in_export" in mr.columns and mr.rows_core_in_export.sum() > 0:
                byg = mr.groupby("variable").agg(core=("rows_core_in_export", "sum"), fcore=("finite_core", "sum"),
                                                 rings=("rows_rings_in_export", "sum"), frings=("finite_rings", "sum"))
                byg["miss_core"] = 1 - byg.fcore / byg.core.replace(0, np.nan); byg["miss_rings"] = 1 - byg.frings / byg.rings.replace(0, np.nan)
                lead = byg.loc[[v for v in ("NDVI", "LAI", "SAVI") if v in byg.index][:1]] if any(v in byg.index for v in ("NDVI", "LAI", "SAVI")) else byg.head(1)
                for v, r in lead.iterrows():
                    info(f"{v}: no-data share in the TREATED CORE {r.miss_core:.1%} ({int(r.fcore):,} usable of {int(r.core):,} core rows) "
                         f"vs the CONTROL RINGS {r.miss_rings:.1%} ({int(r.frings):,} of {int(r.rings):,})")
                    if r.miss_core > 0.5 and r.miss_core > 2 * max(r.miss_rings, 1e-9):
                        warn(f"the treated core is MASKED far more than the rings ({r.miss_core:.0%} vs {r.miss_rings:.0%} of {v} rows). "
                             f"The DiD then rests on the few core pixels that carry data. This is an EXPORT problem (cloud/water/"
                             f"footprint mask over the core), not a modelling one: re-export those years for the core with the "
                             f"current exporter (v111) before relying on any estimate. See panel_missingness_report.csv "
                             f"(columns *_core / *_rings).")
            ok(f"panel_missingness_report.csv written ({len(mr):,} block x variable rows); "
               f"policy totals: {policy_totals['zero_cells_set_missing']:,} zero cells set to missing, "
               f"{policy_totals['rows_dropped_no_outcome']:,} rows without any outcome dropped")
            if "Rain" in tot.index and tot.loc["Rain", "share_missing"] > 0.01 and "Rain" not in ZERO_RULE_EXCEPT:
                warn(f"Rain is missing on {tot.loc['Rain','share_missing']:.1%} of rows after treating exact 0 as no-data. "
                     f"If some of those are GENUINE dry seasons, set P.ZERO_RULE_EXCEPT = ('Rain',) and rebuild -- a real "
                     f"zero-rainfall season is a valid covariate value, a masked cell is not.")
    except RuntimeError:
        raise
    except Exception as _e:
        warn(f"missingness report skipped ({_e})")
    # v20.9: is the panel BALANCED -- does every Year x Season block hold the same pixels?
    try:
        bal = pd.DataFrame([{"Year": yr, "Season": SEASON_LABEL[se], "rows": results[(yr, se)][1],
                             "unique_pixels": results[(yr, se)][2]} for (yr, se) in ordered_keys])
        bal.to_csv(os.path.join(output_dir, "panel_balance_by_block.csv"), index=False)
        for label, est in (("SEASONAL blocks (Kharif/Rabi/Zaid)", bal[bal.Season != "Yearly"]), ("ANNUAL blocks (Yearly, Season 0 -- the default estimation sample since v20.24)", bal[bal.Season == "Yearly"])):
            if not len(est): continue
            if est.unique_pixels.nunique() > 1:
                warn(f"{label} do NOT all contain the same pixels -- UNBALANCED:")
                for _, r_ in est[est.unique_pixels != est.unique_pixels.mode().iloc[0]].iterrows():
                    warn(f"   {int(r_.Year)} {r_.Season}: {int(r_.unique_pixels):,} pixels (most blocks have {int(est.unique_pixels.mode().iloc[0]):,})")
                warn("   -> the estimators keep every pixel (unbalanced panels are handled exactly) but coverage differs by period; see panel_balance_by_block.csv")
            else:
                ok(f"{label}: BALANCED, {int(est.unique_pixels.iloc[0]):,} pixels in each block")
    except Exception as _e:
        warn(f"balance report skipped ({_e})")
    if shard_dup_log:
        with open(os.path.join(output_dir, "cross_file_dedup_conflicts.json"), "w") as fh:
            json.dump(shard_dup_log, fh, indent=2, default=str)
        warn(f"{len(shard_dup_log):,} cross-file duplicate groups resolved -> cross_file_dedup_conflicts.json")
    else:
        ok("no cross-file duplicate pixel-rows found")
    if dedup_totals["values_filled"]:                                  # v20.58: what the repeated rows did (or did not) give the panel
        warn(f"DEDUP_FILL_FROM_DUPLICATES = True: {dedup_totals['values_filled']:,} gap(s) of the kept rows were FILLED with the values of "
             f"repeated rows (another export of the same pixel, year and season) -- set False to keep each kept row as it is")
    elif dedup_totals["values_not_used"]:
        _bv = ", ".join(f"{k} {v:,}" for k, v in sorted(dedup_totals["not_used_by_variable"].items(), key=lambda kv: -kv[1]))
        ok(f"repeated rows DROPPED WHOLE: their {dedup_totals['values_not_used']:,} value(s) where the kept row has a gap were NOT used ({_bv}) "
           f"-- DEDUP_FILL_FROM_DUPLICATES = False (your rule). If your exports are SPLIT by variable (one file NDVI, another LAI of "
           f"the same pixel-period), set P.DEDUP_FILL_FROM_DUPLICATES = True in P00_Settings and rebuild")
    else:
        ok("repeated rows dropped whole; they carried no value the kept rows lack")
    ok(f"missing-value policy over the panel: {policy_totals['zero_cells_set_missing']:,} NaN/zero cells set to missing "
       f"(zero = no-data in these exports), {policy_totals['rows_dropped_no_outcome']:,} rows with no usable outcome dropped")
    confirm_panel_duplicates(final_path)                          # v20.58: checked on the finished panel, never assumed
    print(f"Pass B done. Final file: {final_path} ({total_rows:,} rows)")
    print("Materialized columns for manual inspection: treatment, control, pre, post, did_term "
          f"(built with the scenario in force: control rings {tuple(DEFAULT_CONTROL_ZONES)}, "
          f"treatment year {TREATMENT_YEAR} -- every model recomputes them for whatever rings, timing and "
          "year window that run chooses).")
    return final_path


# registry, unresolved_cols, parse_errors, dedup_conflicts, shard_paths = run_pass_a(INPUT_DIR, TEMP_DIR, OUTPUT_DIR)
# final_path = run_pass_b(shard_paths, OUTPUT_DIR)
# shutil.rmtree(TEMP_DIR, ignore_errors=True)   # comment out to keep shards for debugging


def _pixel_sample_mod(path, fallback=100):
    """v20.57 -- YOUR 98 % RULE for the panel reports (P06 / P07 / the manifest): the pixel-persistence statistics use EVERY
    pixel when their per-pixel year sets (~120 B per row) fit below 98 % of the RAM (v20.31-v20.56: a 1 % pixel sample above
    2,000,000 rows); otherwise the smallest hash-bucket sample that fits. 1 = every pixel."""
    try:
        import pyarrow.parquet as _pq_, math as _m, _hardware as _H
        n = float(_pq_.ParquetFile(path).metadata.num_rows); b = _H.ram_budget_bytes()
        if b is None: return 1
        need = n * 120.0
        return 1 if need <= b else int(_m.ceil(need / max(b, 1.0)))
    except Exception:
        return fallback

def build_manifest(final_path, pixel_sample_mod=100):
    """v15.2 -- STREAMED. The earlier version did pq.read_table(final_path).to_pandas() on the
    whole panel, which is ~650 GB at 1 B rows and would have crashed production right after
    PASS B. Now reads one row-group at a time; pixel persistence is measured on a stable-hash 1 %
    pixel sample (unbiased for a percentage), everything else is an exact streaming aggregate."""
    import pyarrow.parquet as pq, hashlib
    from collections import defaultdict
    pixel_sample_mod = _pixel_sample_mod(final_path, pixel_sample_mod)   # v20.57: every pixel unless that would pass 98 % of the RAM
    pf = pq.ParquetFile(final_path)                        # v20.11: streamed below, CLOSED at the end
    have = set(pf.schema_arrow.names)
    cols = [c for c in ["pixel_id","Year","Season","subwshed_id","treat_period_mismatch_flag",
                        "any_outcome_flat_flag","season_sort_rank"] if c in have]
    n_rows = 0; subw = set(); years = set(); flag_sum = {"treat_period_mismatch_flag":0.0,"any_outcome_flat_flag":0.0}
    _pys = []; order_ok = True; last_key = None                             # v20.57: (pixel, Year, Season) triples
    for i in progress(range(pf.num_row_groups), desc="manifest row-groups", unit="rg"):
        d = pf.read_row_group(i, columns=cols).to_pandas(); n_rows += len(d)
        years.update(int(y) for y in d["Year"].unique())
        if "subwshed_id" in d: subw.update(d["subwshed_id"].dropna().unique().tolist())
        for f in flag_sum:
            if f in d: flag_sum[f] += float(pd.to_numeric(d[f], errors="coerce").fillna(0).sum())
        h = (d["pixel_id"].astype(str).map(lambda x: int(hashlib.blake2b(x.encode(), digest_size=4).hexdigest(), 16) % pixel_sample_mod == 0)
             if pixel_sample_mod > 1 else pd.Series(True, index=d.index))                  # v20.57: every pixel -- no hashing needed
        smp = d[h]
        _pys.append(smp[["pixel_id", "Year", "Season"]].drop_duplicates())     # v20.57: vectorised (every pixel, no Python loop)
        if "season_sort_rank" in d and len(d):
            keys = list(zip(d["Year"].astype(int), d["season_sort_rank"].astype(int)))
            if last_key is not None and keys[0] < last_key: order_ok = False
            if any(keys[k] < keys[k-1] for k in range(1, len(keys))): order_ok = False
            last_key = keys[-1]
    try: pf.close()                                     # v20.11: release the panel file
    except Exception: pass
    _t3 = pd.concat(_pys, ignore_index=True).drop_duplicates() if _pys else pd.DataFrame(columns=["pixel_id", "Year", "Season"])
    _nyy = _t3.groupby("pixel_id")["Year"].nunique() if len(_t3) else pd.Series(dtype="int64")       # years per pixel
    _nss = _t3.groupby("pixel_id")["Season"].nunique() if len(_t3) else pd.Series(dtype="int64")     # seasons per pixel
    manifest = {
        "generated_at": datetime.now().isoformat(),
        "n_rows": int(n_rows),
        "n_unique_pixels_est": int(len(_nyy) * pixel_sample_mod),
        "pixel_sample_size": int(len(_nyy)),
        "n_subwatersheds": int(len(subw)),
        "years": sorted(years),
        "pct_pixels_in_gt1_season": round(float((_nss > 1).mean() * 100), 2) if len(_nss) else 0.0,
        "pct_pixels_in_gt1_year": round(float((_nyy > 1).mean() * 100), 2) if len(_nyy) else 0.0,
        "pct_treat_period_mismatch": round(flag_sum["treat_period_mismatch_flag"] / n_rows * 100, 3) if n_rows else 0.0,
        "pct_any_outcome_flat": round(flag_sum["any_outcome_flat_flag"] / n_rows * 100, 3) if n_rows else 0.0,
        "row_order_check": "Kharif->Rabi->Zaid->Yearly per year, ascending" if order_ok else "ORDER VIOLATION -- inspect",
        "treatment_rule": f"treatment=(buff_km==0); control=(buff_km in {DEFAULT_CONTROL_ZONES}); pre=(Year<{POST_CUTOFF}); post=(Year>={POST_CUTOFF}); did_term=treatment*post",
    }
    with open(os.path.join(os.path.dirname(final_path), "run_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, default=str)
    print("Manifest:", json.dumps(manifest, indent=2, default=str))
    return manifest

def load_subwshed_crosswalk(path):
    """FIX v9.0: auto-detects which SHEET and which ROW hold the District / Sub Watershed Name
    table. v8 hard-coded sheet_name='Sheet2'; in your current file that sheet is EMPTY and the
    table has moved to Sheet1 -- hard-coding would have silently returned nothing.
    Verified against your real file: finds all 20 District->SWS pairs."""
    xl = pd.ExcelFile(path)
    for sheet in xl.sheet_names:
        raw = pd.read_excel(path, sheet_name=sheet, header=None)
        if raw.empty:
            continue
        for hr in range(min(6, len(raw))):
            vals = [str(v).strip().lower() for v in raw.iloc[hr].tolist()]
            if any("district" in v for v in vals) and any("sub" in v and "watershed" in v for v in vals):
                dc = next(i for i, v in enumerate(vals) if "district" in v)
                sc = next(i for i, v in enumerate(vals) if "sub" in v and "watershed" in v)
                df = raw.iloc[hr+1:, [dc, sc]].copy()
                df.columns = ["District", "Sub Watershed Name"]
                df = df.dropna(how="all")
                for c in df.columns:
                    df[c] = df[c].astype(str).str.strip()
                df = df[(df.District != "nan") & (df["Sub Watershed Name"] != "nan")]
                ok(f"crosswalk: {len(df)} District->SWS pairs from sheet '{sheet}'")
                return df.reset_index(drop=True)
    raise ValueError(f"no sheet in {path} has both 'District' and 'Sub Watershed Name' columns")

_SWS_IN_DIST = re.compile(r"^\s*(?P<sws>.+?)\s+SWS\s+in\s+(?P<dist>.+?)\s*$", re.I)

def load_fund_progress(path, sheet=0):
    """FIX v9.0: auto-detects THREE fund-file layouts seen across your exports --
      v1  row1=District, row2=metric, data row3+
      v2  row1=District, row2='SWS: name', row3=metric, data row4+
      v3  row0='<SWS> SWS in <District>', row1='Area in Hactare', row2=metric, data row3+  <-- CURRENT
    v3 also carries AREA IN HECTARES per sub-watershed, which v8 had no way to read.
    Verified on your real file: 440 rows (20 districts x 22 months), Dose/Intensity equals
    Progress/Target*100 to 1.4e-14, and the embedded SWS names match the standalone
    crosswalk with ZERO mismatches."""
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    def _row_text(r):
        return " ".join(str(v) for v in raw.iloc[r].tolist() if pd.notna(v))

    area_row = None
    if any(_SWS_IN_DIST.match(str(v)) for v in raw.iloc[0].tolist() if pd.notna(v)):
        layout, hdr_row, met_row, first_data = "v3_sws_in_district", 0, 2, 3
        if "area" in _row_text(1).lower():
            area_row = 1
    elif "SWS" in _row_text(2):
        layout, hdr_row, met_row, first_data = "v2_sws_row", 1, 3, 4
    else:
        layout, hdr_row, met_row, first_data = "v1_district_only", 1, 2, 3

    hdr  = raw.iloc[hdr_row].ffill()
    met  = raw.iloc[met_row]
    area = raw.iloc[area_row] if area_row is not None else None
    dates = pd.to_datetime(raw.iloc[first_data:, 0], errors="coerce")

    recs = []
    for c in range(1, raw.shape[1]):
        h, m = hdr[c], met[c]
        if pd.isna(h) or pd.isna(m):
            continue
        htxt = str(h).strip()
        mm = _SWS_IN_DIST.match(htxt)
        if mm:
            sws, dist = mm.group("sws").strip(), mm.group("dist").strip()
        else:
            sws, dist = np.nan, re.sub(r"^SWS:\s*", "", htxt).strip()
        a = area[c] if area is not None else np.nan
        for i, dt in enumerate(dates):
            if pd.isna(dt):
                continue
            recs.append({"District": dist, "SWS": sws, "Date": dt, "Metric": str(m).strip(),
                          "Value": raw.iloc[first_data + i, c], "area_hectare": a})

    long = pd.DataFrame(recs)
    area_map = long.dropna(subset=["area_hectare"]).groupby("District")["area_hectare"].first()
    wide = long.pivot_table(index=["District","SWS","Date"], columns="Metric",
                             values="Value", dropna=False).reset_index()
    wide.columns.name = None
    # pivot_table materializes the FULL District x SWS cross-product; each column belongs to
    # exactly one pair, so a row with no metric values at all is a phantom combination.
    metric_cols = [c for c in wide.columns if c not in ("District","SWS","Date")]
    wide = wide.dropna(subset=metric_cols, how="all").reset_index(drop=True)
    wide["area_hectare"] = wide["District"].map(area_map)
    wide = wide[~wide["District"].astype(str).str.lower().str.contains("total|toal", na=False)]
    wide.attrs["layout_version"] = layout
    ok(f"fund file layout detected: {layout}")
    return wide.sort_values(["District","Date"]).reset_index(drop=True)

def assign_agri_year(date):
    """Year key of a date, matching the satellite panel (v17.1, SEASON_DEFINITION='export'): the calendar
    year of the season start -- only Jan/Feb (the tail of Rabi) belong to the previous Year.
    Legacy ('legacy'): Indian agricultural-year convention, Jan-May belong to the previous year."""
    if SEASON_DEFINITION == "export":
        return date.year - 1 if date.month <= 2 else date.year
    return date.year if date.month >= 6 else date.year - 1


def current_season(date):
    for s, months in SEASON_MONTHS.items():
        if date.month in months:
            return s
    raise ValueError(date)


def next_season_after(date):
    """The season immediately AFTER the given date -- operationalizes your 'next nearest
    season' rule, and simultaneously the standard DiD no-anticipation assumption (outcomes
    can't respond to treatment before it's in effect -- Callaway & Sant'Anna 2021 sec 2;
    Abbring & van den Berg 2003 timing-of-events framework): a fund release recorded in
    month M shouldn't be treated as already affecting the season M sits inside, only the
    next one. See _validate_next_season_after() below for the actual persisted test (8
    boundary cases, including the agri-year rollover and the mid-Rabi calendar-year
    rollover that is NOT an agri-year change) -- an earlier version of this docstring
    claimed this was tested without the test actually existing in the notebook; fixed by
    writing the real test rather than trusting the old claim.
    Returns (agri_year, season_code)."""
    ay = assign_agri_year(date)
    cs = current_season(date)
    if SEASON_DEFINITION == "export":
        # v20.29: the panel labels seasons as the exporter does -- Zaid Y = Mar-May Y, Kharif Y = Jun-Sep Y,
        # Rabi Y = Oct Y - Feb Y+1 -- so time runs Zaid(Y) -> Kharif(Y) -> Rabi(Y) -> Zaid(Y+1). The legacy cycle below
        # (Kharif -> Rabi -> Zaid, +1 year) returned a PAST season for Oct-Feb releases (Nov 2021 -> Zaid 2021 =
        # Mar-May 2021) and a season a YEAR late for Mar-May releases (Apr 2022 -> Kharif 2023).
        return {3: (ay, 1), 1: (ay, 2), 2: (ay + 1, 3)}[cs]
    idx = SEASON_CYCLE.index(cs)
    if idx + 1 < len(SEASON_CYCLE):
        return ay, SEASON_CYCLE[idx + 1]
    return ay + 1, SEASON_CYCLE[0]


def build_district_season_dose(fund_df):
    """District-month -> max completion within each ORIGIN season -> SHIFTED to the next
    nearest season (your rule + no-anticipation lag).

    ENHANCEMENT (checked against your real file before adding this): your fund data spans
    Oct-2024 to Jul-2026 exactly -- confirmed by directly reading the file's date range,
    not assumed. That means the FIRST origin season (Kharif, Jun-Oct 2024) only has its
    LAST month (Oct) observed -- 1 of the normal 5 -- and the LAST origin season (Kharif
    2026) only has 2 of 5 (Jun-Jul). Both are genuine, correct consequences of the file's
    real start/end dates, not bugs -- but a dose value silently computed from 1 month of
    a 5-month season looks identical to one computed from all 5 unless you can SEE the
    difference. Added `n_months_observed` and `is_complete_origin_season` so this is
    visible rather than silently baked into the dose numbers."""
    df = fund_df.copy()
    df["completion_pct"] = df["Progress"] / df["Target"] * 100
    df = df.sort_values(["District", "Date"])
    df["completion_pct_smoothed"] = df.groupby("District")["completion_pct"].cummax()
    df["progress_amount_cum"] = pd.to_numeric(df["Progress"], errors="coerce").groupby(df["District"]).cummax()   # v20.38
    df["progress_decrease_flag"] = df.groupby("District")["Progress"].diff().lt(-1e-6).astype(int)
    df["origin_agri_year"] = df["Date"].apply(assign_agri_year)
    df["origin_season"] = df["Date"].apply(current_season)

    origin_agg = (df.groupby(["District", "origin_agri_year", "origin_season"])
                    .agg(dose_asof_season_end=("completion_pct_smoothed", "max"),
                         amount_asof_season_end=("progress_amount_cum", "max"),        # v20.38: the amount released
                         last_date=("Date", "max"),
                         n_months_observed=("Date", "nunique"))
                    .reset_index())
    if "area_hectare" in df.columns:                                                   # v20.38: for intensity
        origin_agg = origin_agg.merge(df.groupby("District")["area_hectare"].first().rename("area_hectare"), on="District", how="left")
    origin_agg["expected_months"] = origin_agg["origin_season"].map(EXPECTED_MONTHS_PER_SEASON)
    origin_agg["is_complete_origin_season"] = (
        origin_agg["n_months_observed"] >= origin_agg["expected_months"])
    target = origin_agg["last_date"].apply(next_season_after)
    origin_agg["target_agri_year"] = [t[0] for t in target]
    origin_agg["target_season"] = [t[1] for t in target]
    return origin_agg


def apply_subwshed_division(dose_df, crosswalk_df, threshold_pct=None):
    """Divides each district's dose EQUALLY across its named sub-watersheds (your rule --
    with the current 20:20 1:1 crosswalk this divisor is always 1, but the formula doesn't
    hardcode that, so it's correct if a future crosswalk lists multiple sub-watersheds per
    district). Also derives first_treat_year/season -- first (target_agri_year, target_season)
    where dose crosses threshold_pct, if given -- a candidate Template A input, at whatever
    grain the crosswalk supports (district here; sub-watershed once it's finer than 1:1)."""
    n_per_district = crosswalk_df.groupby("District").size().rename("n_subwsheds_in_district")
    merged = dose_df.merge(n_per_district, on="District", how="left")
    merged["dose_per_subwshed"] = merged["dose_asof_season_end"] / merged["n_subwsheds_in_district"]
    # v20.38: your rule -- the funds released to a sub-watershed are its dose from the NEXT season, applied to its whole
    # treatment area; intensity = that amount per hectare of the sub-watershed
    if "amount_asof_season_end" in merged.columns:
        merged["dose_amount_sws"] = merged["amount_asof_season_end"] / merged["n_subwsheds_in_district"]
        _ar = pd.to_numeric(merged["area_hectare"], errors="coerce") if "area_hectare" in merged.columns else np.nan
        merged["dose_intensity_per_ha"] = merged["dose_amount_sws"] / _ar
    full = merged.merge(crosswalk_df, on="District", how="left")

    if threshold_pct is not None:
        crossed = full[full["dose_per_subwshed"] >= threshold_pct]
        first = (crossed.sort_values(["District","target_agri_year","target_season"])
                         .groupby("District").first()
                         [["target_agri_year","target_season"]]
                         .rename(columns={"target_agri_year":"first_treat_agri_year",
                                           "target_season":"first_treat_season"}))
        full = full.merge(first, on="District", how="left")
    return full


# fund = load_fund_progress(FUND_RELEASE_PATH)
# dose = build_district_season_dose(fund)
# final_dose = apply_subwshed_division(dose, SUBWSHED_CROSSWALK, threshold_pct=50.0)
#
# seasonal_df = pd.read_parquet(final_path, filters=[("Season", "!=", 0)])
# seasonal_df = seasonal_df.merge(SUBWSHED_CROSSWALK, left_on="site_name", right_on="Sub Watershed Name", how="left")
# seasonal_df = seasonal_df.merge(
#     final_dose.rename(columns={"target_agri_year": "Year", "target_season": "Season"})
#               [["District","Year","Season","dose_per_subwshed","first_treat_agri_year","first_treat_season"]],
#     on=["District","Year","Season"], how="left"
# )
# # seasonal_df["dose_per_subwshed"] is now a continuous dose variable (Template B, DONE).
# # seasonal_df["first_treat_agri_year"] varies across District -> DONE at district grain
# # (Template A, partially -- see Step 15's module-by-module flagging for exactly how far this goes).


def diagnose_uid_match_distances(pre_latlon, new_latlon, registry_mean_lat=None):
    R = 6371000.0
    lat0 = np.radians(registry_mean_lat if registry_mean_lat is not None else pre_latlon[:,0].mean())
    def to_xy(latlon):
        return np.column_stack([np.radians(latlon[:,1]) * R * np.cos(lat0), np.radians(latlon[:,0]) * R])
    tree = cKDTree(to_xy(pre_latlon))
    dist, _ = tree.query(to_xy(new_latlon), k=1)
    return dist

# pre_pts = final_df[final_df.schema_vintage=="2015_2025"][["latitude","longitude"]].drop_duplicates().values
# new_pts = final_df[final_df.schema_vintage=="2026plus"][["latitude","longitude"]].drop_duplicates().values
# d = diagnose_uid_match_distances(pre_pts, new_pts)
# print(pd.Series(d).describe())


def log_pipeline_event(results_dir_root, event):
    """Every module call's outcome -- success, failure, or blocked -- gets a permanent,
    structured record here, not just a print() that scrolls off screen in a long batch run.
    Appends one JSON line per event; nothing is ever silently dropped. Review
    pipeline_run_log.jsonl after any run, especially a long unattended one, before trusting
    results -- 'ran without visible errors' is not the same as 'ran without any failures.'"""
    event["timestamp"] = datetime.now().isoformat()
    log_path = os.path.join(results_dir_root, "pipeline_run_log.jsonl")
    with open(log_path, "a") as f:
        f.write(json.dumps(event, default=str) + "\n")


def panel_validity_check(df):
    """Answers 'is this panel VALID for DiD?' with explicit reasons. Every DiD estimator in
    this pipeline assumes the conditions below; each is checked, none is assumed."""
    R={}; fails=[]; warns=[]
    need=["pixel_id","Year","Season","buff_km","treatment","control","pre","post","did_term"]
    miss=[c for c in need if c not in df.columns]
    if miss: fails.append(f"missing required columns: {miss}")
    else:
        R["n_rows"]=int(len(df)); R["n_pixels"]=int(df.pixel_id.nunique())
        R["n_treated_pixels"]=int(df.loc[df.treatment==1,"pixel_id"].nunique())
        R["n_control_pixels"]=int(df.loc[df.control==1,"pixel_id"].nunique())
        if R["n_treated_pixels"]==0: fails.append("NO treated pixels (buff_km==0)")
        if R["n_control_pixels"]==0: fails.append("NO control pixels (buff_km in 1..5)")
        # 2x2 cells: every DiD needs all four populated
        cells={(t,p):int(((df.treatment==t)&(df.post==p)).sum()) for t in (0,1) for p in (0,1)}
        R["cells_treat_x_post"]={f"treat={t},post={p}":n for (t,p),n in cells.items()}
        empty=[k for k,v in cells.items() if v==0]
        if empty: fails.append(f"EMPTY 2x2 cell(s): {empty} -- DiD cannot be computed")
        # both groups must be observed BOTH before and after (panel, not just cross-section)
        tp=df[df.treatment==1].groupby("pixel_id").post.nunique(); cp=df[df.control==1].groupby("pixel_id").post.nunique()
        R["pct_treated_pixels_in_both_periods"]=round(float((tp>1).mean()*100),1) if len(tp) else 0.0
        R["pct_control_pixels_in_both_periods"]=round(float((cp>1).mean()*100),1) if len(cp) else 0.0
        if R["pct_treated_pixels_in_both_periods"]<20: warns.append(
            f"only {R['pct_treated_pixels_in_both_periods']}% of treated pixels observed in BOTH pre and post "
            "-- pixel fixed effects will have little within-pixel variation; sub-watershed models are safer")
        # interaction validity
        if not ((df.did_term==df.treatment*df.post).all()): fails.append("did_term != treatment*post")
        if not ((df.treatment+df.control)<=1).all(): fails.append("a row is BOTH treatment and control")
        if not ((df.pre+df.post)==1).all(): fails.append("pre/post not complementary (each row must be exactly one)")
        if df.treatment.sum()==0 or df.post.sum()==0: fails.append("did_term has no variation")
        dup=int(df.duplicated(subset=["pixel_id","Year","Season"]).sum()); R["duplicates"]=dup
        if dup: fails.append(f"{dup:,} duplicate pixel-Year-Season rows")
        if "subwshed_id" in df.columns:
            R["n_clusters"]=int(df.subwshed_id.nunique())
            if R["n_clusters"]<6: warns.append(f"only {R['n_clusters']} clusters -- use wild bootstrap (M23) / permutation (M25), not asymptotic SEs")
        yrs=sorted(df.Year.unique()); R["years"]=[int(y) for y in yrs]
        if sum(1 for y in yrs if y<POST_CUTOFF)<2: warns.append("fewer than 2 pre-years: pre-trend tests (M15/M16) are weak")
    R["VERDICT"]="VALID for DiD" if not fails else "NOT VALID -- fix the failures below"
    R["failures"]=fails; R["warnings"]=warns
    return R



# ======================= v15: OUT-OF-CORE PANEL STATISTICS (for ~1B rows) =======================
def stream_row_groups(path, columns):
    """Yield one pandas frame per Parquet row-group, reading only `columns`."""
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    for i in progress(range(pf.num_row_groups), desc="row-groups", unit="rg"):
        yield pf.read_row_group(i, columns=columns).to_pandas()


def streaming_panel_stats(path, key_cols, outcome_cols, pixel_sample_mod=100, seed=0):
    """Everything P06/P07 need, computed in ONE streaming pass without holding the panel:
      - per-column null counts, exact unique-value counts for LOW-cardinality key columns
      - 2x2 treatment x post cell counts, treated/control pixel counts (via a 1% pixel sample)
      - multi-year / multi-season persistence on the SAME 1% pixel sample (hash-bucketed, so it
        is an unbiased sample of pixels, not of rows)
      - outcome min/max/mean/std via running sums
      - duplicate pixel-Year-Season check PER (Year,Season) partition (partitions are disjoint,
        so per-partition uniqueness == global uniqueness)"""
    from collections import Counter, defaultdict
    import hashlib
    cols = sorted(set(key_cols) | set(outcome_cols) | {"pixel_id","Year","Season","treatment","control","post"})
    nulls = Counter(); uniq = {k: Counter() for k in key_cols}; n_rows = 0
    cells = Counter(); sums = defaultdict(float); sq = defaultdict(float); cnt = Counter()
    mins = {}; maxs = {}
    _py_parts = []                                   # v20.57: (pixel, Year) pairs, counted at the end
    treated_ids, control_ids = set(), set()          # v20.31: EXACT treated / control pixel counts (not a 1 % sample)
    dup_by_part = Counter(); seen_by_part = {}
    pixel_sample_mod = _pixel_sample_mod(path, pixel_sample_mod)   # v20.57: EVERY pixel unless that would pass 98 % of the RAM
    for df in stream_row_groups(path, [c for c in cols]):
        n_rows += len(df)
        for c in df.columns:
            nulls[c] += int(df[c].isna().sum())
        for k in key_cols:
            if k in df.columns and df[k].nunique(dropna=True) <= 2000:
                uniq[k].update(df[k].dropna().value_counts().to_dict())
        for (t,p),n in df.groupby(["treatment","post"]).size().items(): cells[(int(t),int(p))] += int(n)
        for o in outcome_cols:
            if o in df.columns:
                v = pd.to_numeric(df[o], errors="coerce").dropna()
                if len(v):
                    sums[o] += float(v.sum()); sq[o] += float((v**2).sum()); cnt[o] += int(len(v))
                    mins[o] = min(mins.get(o, np.inf), float(v.min())); maxs[o] = max(maxs.get(o, -np.inf), float(v.max()))
        # 1% pixel sample by stable hash (same pixel always in/out of the sample)
        h = (df["pixel_id"].astype(str).map(lambda x: int(hashlib.blake2b(x.encode(), digest_size=4).hexdigest(), 16) % pixel_sample_mod == 0)
             if pixel_sample_mod > 1 else pd.Series(True, index=df.index))                 # v20.57: every pixel -- no hashing needed
        smp = df[h]
        _py_parts.append(smp[["pixel_id", "Year"]].drop_duplicates())           # v20.57: vectorised (every pixel, no Python loop)
        _tr = pd.to_numeric(df["treatment"], errors="coerce").values
        treated_ids.update(pd.unique(df["pixel_id"].values[_tr == 1]).tolist())
        if "control" in df.columns:
            control_ids.update(pd.unique(df["pixel_id"].values[pd.to_numeric(df["control"], errors="coerce").values == 1]).tolist())
        # duplicates within (Year,Season) partitions
        for (yr,se), g in df.groupby(["Year","Season"]):
            key = (int(yr), int(se)); ss = seen_by_part.setdefault(key, set())
            ids = g["pixel_id"].astype(str).values
            before = len(ss); ss.update(ids); dup_by_part[key] += len(ids) - (len(ss) - before)
    _ny = (pd.concat(_py_parts, ignore_index=True).drop_duplicates().groupby("pixel_id")["Year"].nunique()
           if _py_parts else pd.Series(dtype="int64"))                       # years per pixel
    stats = {"n_rows": n_rows, "nulls": dict(nulls), "unique_key_values": {k: dict(v) for k,v in uniq.items()},
             "cells_treat_x_post": {f"treat={t},post={p}": n for (t,p),n in sorted(cells.items())},
             "outcome_ranges": {o: {"count": cnt[o], "mean": sums[o]/cnt[o] if cnt[o] else np.nan,
                                    "std": float(np.sqrt(max(sq[o]/cnt[o]-(sums[o]/cnt[o])**2, 0))) if cnt[o] else np.nan,
                                    "min": mins.get(o), "max": maxs.get(o)} for o in outcome_cols if cnt[o]},
             "duplicates_total": int(sum(dup_by_part.values())),
             "duplicates_by_partition": {f"{y}/{SEASON_LABEL.get(s_,s_)}": n for (y,s_),n in dup_by_part.items() if n},
             "pixel_sample_size": int(len(_ny)),
             "pct_pixels_multi_year": round(float((_ny > 1).mean() * 100), 1) if len(_ny) else 0.0,
             "pct_pixels_6plus_years": round(float((_ny >= 6).mean() * 100), 1) if len(_ny) else 0.0,
             "n_treated_pixels_est": len(treated_ids),          # v20.31: exact (the key keeps its old name)
             "n_control_pixels_est": len(control_ids)}
    return stats


def panel_validity_from_stats(st, n_clusters=None, n_pre_years=None):
    """Same verdict logic as panel_validity_check, driven by streaming stats (1B-row safe)."""
    fails=[]; warns=[]
    cells = st["cells_treat_x_post"]
    for k in ("treat=1,post=1","treat=1,post=0","treat=0,post=1","treat=0,post=0"):
        if cells.get(k,0)==0: fails.append(f"EMPTY 2x2 cell {k} -- DiD cannot be computed")
    if st["n_treated_pixels_est"]==0: fails.append("no treated pixels (buff_km==0)")
    if st["n_control_pixels_est"]==0: fails.append("no control pixels (buff_km in 1..5)")
    if st["duplicates_total"]: fails.append(f"{st['duplicates_total']:,} duplicate pixel-Year-Season rows: {st['duplicates_by_partition']}")
    if st["pct_pixels_multi_year"]<20: warns.append(
        f"only {st['pct_pixels_multi_year']}% of pixels observed in >1 year -- pixel FE have little within-pixel variation")
    if n_clusters is not None and n_clusters<6: warns.append(f"only {n_clusters} clusters -- use wild bootstrap (M23) / permutation (M25)")
    if n_pre_years is not None and n_pre_years<2: warns.append("fewer than 2 pre-years: pre-trend tests are weak")
    return {"VERDICT": "VALID for DiD" if not fails else "NOT VALID -- fix the failures", "failures": fails, "warnings": warns}
