import re
"""
_common.py -- shared engine for the REWARD DiD pipeline (v6.0)
==============================================================
Imported by EVERY model notebook in All_DIDsCodes/ so each notebook stays small,
fast to open, and independent -- which is also the fix for the kernel crashes:
nothing heavy runs at import, and each notebook loads ONLY the columns it needs.

Do not edit estimator maths here without re-running validate_all() at the bottom.
"""
import os, sys, json, gc, warnings, math

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
def require_engine(minimum, module=None):
    """Refuse to run on an engine OLDER than the notebook was written for, and refuse a split installation
    (the two engines coming from different folders). A newer engine is fine. v20.36: starts the text log of every
    cell's messages when the notebook names itself (module) or Jupyter / VS Code tells us its file."""
    try:
        _m = module or os.path.splitext(os.path.basename(os.environ.get("JPY_SESSION_NAME", "") or ""))[0] or None
        if not _m:
            try:
                from IPython import get_ipython as _gi
                _m = os.path.splitext(os.path.basename(str((_gi().user_ns or {}).get("__vsc_ipynb_file__", ""))))[0] or None
            except Exception:
                _m = None
        if _m and "start_cell_log" in globals(): start_cell_log(_m.split("_")[0])
    except Exception:
        pass
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
        try:                                              # v20.55: the estimator packages, counted at every run (installed when a model needs one)
            import importlib.util as _iu
            _est = {k: v for k, v in PYTHON_PACKAGES.items() if v[1] != "optional"}
            _miss = [v[0] for k, v in _est.items() if _iu.find_spec(k) is None]
            print(f"[{'OK' if not _miss else 'INFO'}]{'      ' if not _miss else '    '}Python packages: {len(_est) - len(_miss)} of {len(_est)} installed"
                  + ("" if not _miss else f" -- missing {_miss}: installed automatically when a step needs them (AUTO_INSTALL_PACKAGES), else the engine computes"))
        except Exception:
            pass
    _ENV_CHECKED["done"] = True
    if strict and missing_req:
        raise ImportError("missing required packages: pip install " + " ".join(missing_req))
    return {"missing_required": missing_req, "packages": rows}

# ====================== v20.55: PACKAGES FIRST -- installed when missing, confirmed at every run ======================
# The pre-built packages are the primary route of every estimator (P12 verifies them on a known answer before they are
# trusted). A package that is missing is installed the moment a step needs it -- pip WHEEL first (pre-built), then the
# SOURCE distribution (built here), then a local wheel folder (offline: python_prebuilt/wheels or REWARD_WHEELS) -- and
# every run confirms "N of N packages installed" (results/PACKAGE_STATUS.csv). R: lib/reward_packages.R, the same rule.
AUTO_INSTALL_PACKAGES = True          # False: never install, only report (P00_Settings INSTALL_PACKAGES sets it)
# ---- v20.58: the models THIS project carries (_paths.PIPELINE_MODELS; None = all 45). The four-model project (RWD_4Models) carries
# M01, M02, M16 and M34 only: its package checks, verifications, readiness report and validators cover those, nothing else.
ALL_MODEL_IDS = tuple(f"M{i:02d}" for i in range(1, 46))
try:
    import _paths as _PPm
    PIPELINE_MODELS = tuple(getattr(_PPm, "PIPELINE_MODELS", None) or ()) or None
    del _PPm
except Exception:
    PIPELINE_MODELS = None

def pipeline_models():
    """The model ids this project carries (all 45 unless _paths.PIPELINE_MODELS names a subset)."""
    return list(PIPELINE_MODELS) if PIPELINE_MODELS else list(ALL_MODEL_IDS)

def in_pipeline(model):
    return PIPELINE_MODELS is None or str(model) in PIPELINE_MODELS

def _model_ids_in(text):
    """The model ids a 'used by' text names: 'M01 M02 M24-M26' -> {'M01', 'M02', 'M24', 'M25', 'M26'}."""
    ids = set()
    for a, b in re.findall(r"M(\d{2})(?:\s*-\s*M(\d{2}))?", str(text)):
        lo = int(a); hi = int(b) if b else lo
        ids |= {f"M{k:02d}" for k in range(lo, hi + 1)}
    return ids

def serves_pipeline(used_by):
    """A package / column serves this project when its 'used by' names no model (infrastructure) or one of the project's models."""
    ids = _model_ids_in(used_by)
    return PIPELINE_MODELS is None or not ids or bool(ids & set(PIPELINE_MODELS))
PYTHON_PACKAGES = {                   # import name: (pip name, kind, used by)
    "numpy": ("numpy", "required", "every step"), "pandas": ("pandas", "required", "every step"),
    "pyarrow": ("pyarrow", "required", "the panel (parquet)"), "scipy": ("scipy", "required", "inference"),
    "sklearn": ("scikit-learn", "required", "M39-M44, matching"), "psutil": ("psutil", "required", "RAM rule"),
    "tqdm": ("tqdm", "required", "progress"), "joblib": ("joblib", "required", "parallel steps"),
    "openpyxl": ("openpyxl", "required", "Excel exports, fund file"),
    "pyfixest": ("pyfixest", "estimator", "M01 M02 M09 M10 M12 M14 M15 M23 M24 M26 M29 M31 (TWFE, event study, wild bootstrap)"),
    "wildboottest": ("wildboottest", "estimator", "M23 (wild cluster bootstrap)"),
    "diff_diff": ("diff-diff", "estimator", "M05 M09 M11 M22 M27 M30 M31 (Callaway-Sant'Anna, Sun-Abraham, synthetic DiD, Bacon, imputation, stacked; "
                                            "its HonestDiD is the supplementary check of python_prebuilt/dd_pipeline.py -- the HonestDiD route is R's)"),
    "econml": ("econml", "estimator", "M39 M41 M42 M43 (causal forests, meta-learners)"), "doubleml": ("doubleml", "estimator", "M40 (double ML)"),
    "esda": ("esda", "estimator", "M17 M18 (spatial autocorrelation)"), "libpysal": ("libpysal", "estimator", "M17 M18 (spatial weights)"),
    "dask": ("dask[distributed]", "out-of-core", "M01 M02 M16 M34 and P00 beyond 98 % of the RAM: the first engine (Dask; also the R pipeline's)"),
    "distributed": ("distributed", "out-of-core", "M01 M02 M16 M34 and P00 beyond 98 % of the RAM: Dask's local cluster"),
    "pyspark": ("pyspark", "out-of-core", "M01 M02 M16 M34 and P00 beyond 98 % of the RAM: the second engine (Apache Spark; needs Java 17+)"),
    "torch": ("torch", "optional", "GPU demeaning (CPU path without it)"), "ipywidgets": ("ipywidgets", "optional", "progress widget"),
}
_PKG_STATUS_DONE = {"printed": False}

def _wheel_dirs():
    """Local wheel folders for an offline install: REWARD_WHEELS, python_prebuilt/wheels, ./wheels."""
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [os.environ.get("REWARD_WHEELS", ""), os.path.join(here, "python_prebuilt", "wheels"), os.path.join(here, "wheels")]
    return [c for c in cands if c and os.path.isdir(c)]

def install_python_package(pip_name, verbose=True, timeout=1800):
    """Install ONE package: pre-built wheel -> source distribution -> local wheel folder. Returns the route that worked,
    or 'NOT installed'. Never raises."""
    import subprocess as _sp, importlib as _il
    base = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--timeout", "60", "--retries", "2"]
    routes = [("pre-built wheel (pip --prefer-binary)", base + ["--prefer-binary", pip_name]),
              ("source distribution, built here (pip --no-binary)", base + ["--no-binary", pip_name, pip_name])]
    for d in _wheel_dirs():
        routes.append((f"local wheel folder {d}", base + ["--no-index", "--find-links", d, pip_name]))
    imp = next((k for k, v in PYTHON_PACKAGES.items() if v[0] == pip_name), pip_name.replace("-", "_"))
    for label, cmd in routes:
        if verbose: info(f"installing '{pip_name}': {label} ...")
        try:
            r = _sp.run(cmd, capture_output=True, text=True, timeout=timeout)
        except Exception as e:
            r = None; err = str(e)
        else:
            err = " ".join((r.stderr or r.stdout).strip().split())[-300:]
        _il.invalidate_caches()
        if r is not None and r.returncode == 0 and _il.util.find_spec(imp) is not None:
            if verbose: ok(f"'{pip_name}' {_pkg_version(pip_name) or ''} installed -- {label}")
            return label
        if verbose: info(f"  {label}: not available ({err[-160:] if err else 'no output'})")
    if verbose: warn(f"'{pip_name}' could not be installed from any route (wheel, source, local wheels) -- the estimators that use it fall back to the engine")
    return "NOT installed"

def ensure_python_packages(packages=None, install=None, verbose=True):
    """One row per package: installed?, version, how it got here. Missing ones are installed (chain) when allowed."""
    import importlib.util as _iu
    install = AUTO_INSTALL_PACKAGES if install is None else install
    rows = []
    for imp, (pipn, kind, used) in PYTHON_PACKAGES.items():
        if packages and imp not in packages and pipn not in packages: continue
        if not packages and kind == "estimator" and not serves_pipeline(used): continue     # v20.58: only the project's models' packages
        have = _iu.find_spec(imp) is not None; how = "installed" if have else "NOT installed"
        if not have and install and kind != "optional":
            how = install_python_package(pipn, verbose=verbose); have = _iu.find_spec(imp) is not None
        rows.append({"language": "Python", "package": pipn, "import_name": imp, "kind": kind, "installed": bool(have),
                     "version": _pkg_version(pipn) or "", "how": how, "used_by": used})
    return pd.DataFrame(rows)

def confirm_packages(install=None, r=True, write=True, verbose=True):
    """The run-time confirmation both pipelines print: Python packages (and the R packages when R is found) -- installed
    when missing (AUTO_INSTALL_PACKAGES), counted, the missing ones named with the models they serve; -> PACKAGE_STATUS.csv."""
    py = ensure_python_packages(install=install, verbose=verbose)
    core = py[py.kind != "optional"]; n, N = int(core.installed.sum()), len(core)
    if verbose:
        now = core[core.how.str.startswith(("pre-built", "source", "local"))]
        (ok if n == N else warn)(f"Python packages: {n} of {N} installed (pre-built wheels first, source where no wheel exists)"
                                 + (f"; installed now: {', '.join(now.package)}" if len(now) else "")
                                 + ("" if n == N else " -- MISSING: " + "; ".join(f"{a} ({b})" for a, b in zip(core[~core.installed].package, core[~core.installed].used_by))))
        opt = py[(py.kind == "optional") & ~py.installed]
        if len(opt): info("optional, absent: " + ", ".join(f"{a} ({b})" for a, b in zip(opt.package, opt.used_by)))
    out = [py]
    if r and find_rscript():
        rr = r_package_status(install=install, verbose=verbose)
        if rr is not None and len(rr): out.append(rr)
    st = pd.concat(out, ignore_index=True)
    if write:
        try:
            os.makedirs(RESULTS_ROOT, exist_ok=True)
            st.assign(python=sys.version.split()[0], checked=pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")).to_csv(os.path.join(RESULTS_ROOT, "PACKAGE_STATUS.csv"), index=False)
        except Exception:
            pass
    return st

def r_package_status(install=None, verbose=True):
    """The R packages through the SAME chain R uses (lib/reward_packages.R: CRAN binary -> source -> r-universe -> GitHub ->
    archive -> mirror): install the missing ones when allowed, then one row per package."""
    import subprocess as _sp, tempfile as _tf
    rs = find_rscript()
    if not rs: return None
    install = AUTO_INSTALL_PACKAGES if install is None else install
    lib = os.path.join(os.path.dirname(r_bridge_script()), "reward_packages.R")
    if not os.path.exists(lib):
        v = r_versions(refresh=True); rows = [{"language": "R", "package": p, "import_name": p, "kind": "estimator", "installed": bool(v.get(p)),
                                              "version": v.get(p) or "", "how": "installed" if v.get(p) else "NOT installed", "used_by": ""} for p in v if p != "R"]
        return pd.DataFrame(rows)
    outf = os.path.join(_tf.mkdtemp(prefix="reward_rpk_"), "status.csv")
    code = (f"AUTO_INSTALL_PACKAGES <- {'TRUE' if install else 'FALSE'}; "
            + (f"PIPELINE_MODELS <- c({', '.join(repr(m) for m in PIPELINE_MODELS)}); " if PIPELINE_MODELS else "")   # v20.58: the project's models
            + f"source('{lib.replace(os.sep, '/')}'); "
            f"st <- ensure_packages(install = AUTO_INSTALL_PACKAGES, verbose = TRUE); write.csv(st, '{outf.replace(os.sep, '/')}', row.names = FALSE)")
    try:
        r = _sp.run([rs, "--vanilla", "-e", code], capture_output=True, text=True, timeout=7200)
        st = pd.read_csv(outf)
    except Exception as e:
        warn(f"R package status unavailable: {e}"); return None
    finally:
        _rm_temp(os.path.dirname(outf))                                 # v20.58: the temporary folder is removed (was left in %TEMP%)
    st["installed"] = st["installed"].astype(str).str.upper().eq("TRUE")
    st = st.assign(language="R", import_name=st["package"], kind="estimator")[["language", "package", "import_name", "kind", "installed", "version", "how", "used_by"]]
    n, N = int(st.installed.sum()), len(st)
    if verbose:
        now = st[~st.how.isin(["installed", "NOT installed"])]
        (ok if n == N else warn)(f"R packages: {n} of {N} installed (R {r_versions().get('R')}; CRAN binary first, source where no binary exists, r-universe / GitHub / mirror for the rest)"
                                 + (f"; installed now: {', '.join(now.package)}" if len(now) else "")
                                 + ("" if n == N else " -- MISSING: " + "; ".join(f"{a} ({b})" for a, b in zip(st[~st.installed].package, st[~st.installed].used_by.fillna("")))))
    _R_CACHE.clear()
    return st

try:
    check_environment(strict=False, verbose=True)
except Exception as _e:
    print(f"[INFO]    environment check skipped: {_e}")
if "arcgis" in sys.executable.lower() or sys.version_info < (3, 9):
    print(f"[FAILED]  wrong Python environment: {sys.executable}")
    print("[INFO]    Jupyter -> Kernel -> Change Kernel -> 'Python [conda env:anaconda3]', then restart.")
    raise ImportError("this pipeline must run in the Anaconda environment (Python >= 3.9), not ArcGIS Pro's")
from itertools import combinations   # FIX: needed by goodman_bacon_diagnostic
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.optimize import minimize, nnls


# ---- GPU backend detection (used by _nn_match; spatial modules M17/M18 need this) ----
GPU_BACKEND = "cpu"
try:
    import cupy as cp
    from cuml.neighbors import NearestNeighbors as cuNN
    GPU_BACKEND = "cuml"
except Exception:
    try:
        import torch
        if torch.cuda.is_available():
            GPU_BACKEND = "torch"
    except Exception:
        pass
GPU_AVAILABLE = GPU_BACKEND != "cpu"

# ============================== CONFIG ==============================
# EDIT THESE to match your machine, then every model notebook picks them up.
PREPARED_PANEL = r"D:\LKT\TST_Artal\output\did_panel_full.parquet"          # fallback; _paths.py decides (v20.14)
RESULTS_ROOT   = r"D:\LKT\TST_Artal\output\results"
ACTIVE_PATHS = {}

def _apply_paths(paths, verbose=False, _propagate=True):
    """v20.14: adopt the layout derived from _paths.INPUT_DIR (shared with _prep_common)."""
    global PREPARED_PANEL, RESULTS_ROOT, ESTIMATOR_FILES_DIR, GROUND_LINKS_PATH, GROUND_TRUTH_OUTCOMES_PATH, ROLLOUT_INSTRUMENT_PATH
    _PATHS_APPLIED[0] = True                                  # v20.30: logs may now use RESULTS_ROOT
    PREPARED_PANEL = paths["FINAL_PANEL"]; RESULTS_ROOT = paths["RESULTS_ROOT"]
    ESTIMATOR_FILES_DIR = paths["ESTIMATOR_FILES_DIR"]; GROUND_LINKS_PATH = paths["GROUND_LINKS_PATH"]
    if paths.get("GROUND_TRUTH_OUTCOMES_PATH"): GROUND_TRUTH_OUTCOMES_PATH = paths["GROUND_TRUTH_OUTCOMES_PATH"]   # v20.24
    if paths.get("ROLLOUT_INSTRUMENT_PATH"): ROLLOUT_INSTRUMENT_PATH = paths["ROLLOUT_INSTRUMENT_PATH"]
    ACTIVE_PATHS.clear(); ACTIVE_PATHS.update(paths)
    m = sys.modules.get("_prep_common")
    if _propagate and m is not None and hasattr(m, "_apply_paths"):
        m._apply_paths(paths, verbose=False, _propagate=False)     # v20.14: one hop, never a ping-pong
    if verbose:
        import _paths as _PP
        print("[OK]      paths in force (edit INPUT_DIR in _paths.py, or call set_paths()):"); print(_PP.describe(paths))

def set_paths(input_dir=None, output_dir=None, temp_dir=None, crosswalk=None, fund_release=None, verbose=True):
    """Point the models at an input folder for this session: the panel, results and estimator files derive from
    it exactly as the preparation notebooks derive theirs. Records the layout in OUTPUT_DIR/reward_paths.json."""
    import _paths as _PP
    paths = _PP.derive(input_dir, output_dir, temp_dir, crosswalk, fund_release)
    _apply_paths(paths, verbose=verbose); _PP.save(paths)
    return dict(paths)

TREATMENT_YEAR = 2022       # treatment START year
PRE_CUTOFF     = 2022       # kept for backward compatibility (not used: pre = Year < treatment year)
POST_CUTOFF    = 2022       # v20.27: post = Year >= 2022 (0 before 2022, 1 from 2022) -- your specification
EXCLUDE_TRANSITION_YEAR = False  # True = hold 2022 out of both periods (robustness check; post then starts 2023)
TREAT_CORE_BUFFKM = 0
DEFAULT_CONTROL_ZONES = (1, 2, 3, 4, 5)
DESIGN_OUTCOME = "NDVI"          # v20.57: the outcome whose DATA decide the "data" options (export breaks, fill years, spillover)
DATA_OPTION_WORDS = ("data", "recommended")   # v20.57: CONTROL_ZONES / PRE_YEARS / POST_YEARS = "data" -> chosen from the data
DOSE_VARIABLES = ("dose_intensity_per_ha", "dose_amount_sws", "dose_share_of_target")   # v20.57: the dose models' dose (fund file)

SEASON_LABEL = {0: "Yearly", 1: "Kharif", 2: "Rabi", 3: "Zaid"}
SEASON_SORT_RANK = {1: 0, 2: 1, 3: 2, 0: 3}

# ---- FUTURE DATA SLOTS: fill these in when your household survey is ready ----
# Each is consumed by exactly one blocked module; see that notebook's DATA REQUIREMENTS cell.
GROUND_TRUTH_OUTCOMES_PATH = r"D:\LKT\survey\ground_truth_outcomes.csv"      # -> M07 Surrogate Index
HOUSEHOLD_CHARACTERISTICS_PATH = r"D:\LKT\survey\household_characteristics.csv"  # -> M26/M37 heterogeneity
INTERVENTION_DETAIL_PATH = r"D:\LKT\survey\intervention_detail.csv"          # -> finer treatment grain
ROLLOUT_INSTRUMENT_PATH = r"D:\LKT\survey\rollout_instrument.csv"            # -> M08 Instrumented DiD
# v17.1 ground data (benchmark hydrology + field survey + MIS), built by build_all.py
GROUND_INPUTS_DIR = r"D:\LKT\survey\REWARD_ground_inputs"                     # -> P08 / V06 (overridden below)
GROUND_INPUT_FILES = ["01_benchmark_sites_master.csv", "02_ground_ssm_long.csv", "03_ground_lai_long.csv",
                      "04_ground_gw_long.csv", "05_ground_tdr_long.csv", "06_ground_tdr_rootzone_0_30cm_by_visit.csv",
                      "07_ground_site_season_means_treated_control.csv", "08_field_survey_plots_deidentified.csv",
                      "09_field_survey_crop_calendar.csv", "10_field_survey_landuse_truth_polygons.csv",
                      "11_mis_koppal_parcels_deidentified.csv", "12_mis_koppal_dose_by_mws.csv",
                      "13_mis_koppal_dose_by_village.csv", "14_mis_koppal_common_land_structures.csv",
                      "15_sws_parcel_counts_from_hissa.csv", "16_programme_rules_from_DPR.csv"]

def resolve_ground_inputs_dir(explicit=None, verbose=False):
    """v20.24: the harmonised ground inputs (REWARD_ground_inputs/, 16 CSVs) SHIP WITH THE BUNDLE. Look, in order:
    an explicit path / _paths.GROUND_INPUTS_DIR; the bundle (this engine's folder and up to 4 parents);
    INPUT_DIR and OUTPUT_DIR; the historical D:/LKT/survey location. The first folder holding
    01_benchmark_sites_master.csv wins; otherwise the historical default is kept and P08/V06 say what is missing."""
    here = os.path.dirname(os.path.abspath(__file__))
    cands = []
    if explicit: cands.append(explicit)
    try:
        import _paths as _PP
        if getattr(_PP, "GROUND_INPUTS_DIR", None): cands.append(_PP.GROUND_INPUTS_DIR)
    except Exception:
        pass
    p = here
    for _ in range(5):
        cands += [os.path.join(p, "REWARD_ground_inputs"), os.path.join(p, "ground_inputs")]
        p = os.path.dirname(p)
    for base in (globals().get("INPUT_DIR"), globals().get("OUTPUT_DIR"), os.path.dirname(PREPARED_PANEL) if "PREPARED_PANEL" in globals() else None):
        if base: cands.append(os.path.join(base, "REWARD_ground_inputs"))
    cands.append(GROUND_INPUTS_DIR)
    for d in cands:
        if d and os.path.exists(os.path.join(d, "01_benchmark_sites_master.csv")):
            if verbose: info(f"ground inputs: {d}")
            return os.path.abspath(d)
    if verbose: warn(f"ground inputs not found; looked in {len(cands)} places (first: {cands[0] if cands else '-'})")
    return GROUND_INPUTS_DIR

def ground_inputs_status(verbose=True):
    """Which of the 16 ground-input files are present where GROUND_INPUTS_DIR points."""
    d = GROUND_INPUTS_DIR
    present = [f for f in GROUND_INPUT_FILES if os.path.exists(os.path.join(d, f))]
    missing = [f for f in GROUND_INPUT_FILES if f not in present]
    if verbose:
        (ok if not missing else warn)(f"ground inputs at {d}: {len(present)}/{len(GROUND_INPUT_FILES)} files present"
                                      + (f"; missing {missing[:4]}{'...' if len(missing) > 4 else ''}" if missing else ""))
        if missing:
            warn("P08 (ground links), M07 (surrogate index) and V06 (ground validation) need these files. The bundle ships "
                 "them in REWARD_ground_inputs/ next to the python/ folder; set GROUND_INPUTS_DIR in _paths.py if they "
                 "live elsewhere.")
    return {"dir": d, "present": present, "missing": missing}

try:
    GROUND_INPUTS_DIR = resolve_ground_inputs_dir()
except Exception:
    pass
GROUND_LINKS_PATH = os.path.join(RESULTS_ROOT, "P08", "ground_links.parquet")  # written by P08, read by V06
GROUND_SNAP_MAX_M = 12.0                                                      # nearest-pixel tolerance (one 10 m pixel)
GROUND_LINK_YEAR, GROUND_LINK_SEASON = 2023, None                              # v20.24: None = EVERY season of that year (annual
                                                                               # composite included) -> the fullest pixel footprint

# v17.5: Rain / Tmax / Tmean / Tmin are WEATHER COVARIATES of the DiD regressions -- never outcomes.
# They were listed as outcomes up to v17.4 (and only Rain/Tmean entered as controls). Any request to
# estimate a weather variable as an outcome now raises a readable error (see columns_for / load_panel).
class InsufficientDataError(Exception):
    """raised when a model cannot run on the available data (defined early for assert_is_outcome)"""
    pass

class OutOfCoreNeeded(InsufficientDataError):
    """v20.58: every row of this model's sample would pass 98 % of the RAM -- the model notebook switches to the out-of-core path
    (Dask / Spark / the built-in batches, exact) when it has one (_outofcore.OOC_MODELS); any other caller sees a data gap with the reason."""
    pass
WEATHER_COVARIATES = ["Rain", "Tmax", "Tmean", "Tmin"]
ALL_ESTIMATION_VARIABLES = [
    "NDVI","SAVI","EVI","LAI","LSWI","NDWI","NDMI","NDRE","AGB","RUSLE",
    "ESI","WSSI","WSI","SMDI","VCI","TCI","VHI",
]
DEFAULT_COVARIATES = list(WEATHER_COVARIATES)      # v20.44: weather only -- LandUse was entered as a NUMBER in every model
STANDARD_COVARIATES = list(DEFAULT_COVARIATES)     # v20.29: the default set; set_scenario(covariates=...) changes
                                                   # DEFAULT_COVARIATES IN PLACE, so every model sees the choice
# v20.30: covariates are chosen IN EACH MODEL (CELL 1: COVARIATES = a group name or a list) -- never at panel
# preparation and never inherited from the saved panel scenario. The panel and the per-variable files keep EVERY
# covariate column and every row; only the model's own choice decides which covariates enter its regression and
# which rows its missing-value rule drops.
COVARIATE_GROUPS = {
    "all":            ["Rain", "Tmax", "Tmean", "Tmin"],               # v20.45: the FOUR weather covariates (tag covAll4)
    "mean_temp_rain": ["Tmean", "Rain"],                               # mean temperature + rainfall
    "weather":        ["Rain", "Tmax", "Tmean", "Tmin"],               # all weather, no land use
    "none":           [],
}
ALL_COVARIATE_COLUMNS = ["Rain", "Tmax", "Tmean", "Tmin", "LandUse"]   # what the per-variable files always carry
DOUBLE_PRECISION_EXTRA = ("dose_per_subwshed", "dose_amount_sws", "dose_intensity_per_ha")   # v20.58: widened to float64 at load (load_panel)

_LANDUSE_SAID = {}
CATEGORICAL_COVARIATES = ("LandUse",)                   # v20.44: class codes -- entered as dummies, never as numbers

def _is_categorical_col(c):
    """v20.44: LandUse and its class dummies (LandUse_class2 ...): 0 is a real value there, never 'missing'."""
    c = str(c); return c in CATEGORICAL_COVARIATES or any(c.startswith(x + "_class") for x in CATEGORICAL_COVARIATES)

def _expand_categorical_covariates(df, covariates):
    """v20.45: LandUse is NEVER a covariate -- a class code is not a quantity, and land use can change BECAUSE of the
    programme (a bad control that absorbs part of the effect). It stays a descriptor (M10's land-use groups)."""
    covs = list(covariates or [])
    drop = [x for x in covs if _is_categorical_col(x)]
    if not drop: return df, covariates
    if not _LANDUSE_SAID.get("refused"):
        warn(f"{drop} left out of the covariates: land use is a class code and can itself change because of the programme "
             f"(a bad control). Covariates are the four weather variables; land use stays available to M10 as its group.")
        _LANDUSE_SAID["refused"] = True
    return df, [x for x in covs if not _is_categorical_col(x)]

def resolve_covariates(spec):
    """A group name ("all", "mean_temp_rain", "weather", "none") or a list -> (list, label)."""
    if spec is None: return list(DEFAULT_COVARIATES), "current"
    if isinstance(spec, str):
        key = spec.strip().lower()
        if key not in COVARIATE_GROUPS:
            raise InsufficientDataError(f"unknown covariate group {spec!r}; use one of {sorted(COVARIATE_GROUPS)} or a list")
        if key == "all":                               # v20.45: the four weather covariates; results get their own tag
            if not _LANDUSE_SAID.get("all"):
                info("COVARIATES = 'all' = the four weather covariates (Rain, Tmax, Tmean, Tmin) -- results folder tag 'covAll4' "
                     "(earlier 'covAll' results entered LandUse as a number and are not comparable)")
                _LANDUSE_SAID["all"] = True
            return list(COVARIATE_GROUPS["all"]), "all4"
        return list(COVARIATE_GROUPS[key]), key
    covs = [str(x) for x in dict.fromkeys(spec)]
    for name, members in COVARIATE_GROUPS.items():
        if covs == members: return covs, name
    return covs, "custom"
def assert_is_outcome(outcome):
    if outcome in WEATHER_COVARIATES:
        raise InsufficientDataError(f"'{outcome}' is a weather COVARIATE (Rain/Tmax/Tmean/Tmin), not an outcome -- "
                                    f"it enters the regressions as a control; choose an outcome from ALL_ESTIMATION_VARIABLES")
    return outcome
ID_FE_COLS = ["pixel_id","subwshed_id","site_id","Year","Season","buff_km","time_fe_yearseason",
              "time_fe_year","time_fe_season","season_sort_rank","first_treat_agri_year","dose_per_subwshed"]
# NOTE: treatment/control/pre/post/did_term are DERIVED from buff_km + Year by
# build_treatment_columns() at model time, so they need not be loaded from disk.

# ====================== v17: RUNTIME AUTO-TUNING ======================
# Detects CPU cores, RAM, GPU VRAM and disk on THIS machine and sets every performance knob
# from measurements, not assumptions. Call C.autotune() once per session (M01 cell 1 does).
TUNE = {"n_jobs": 1, "ram_gb": None, "vram_gb": None, "gpu": "CPU", "disk_free_gb": None,
        "load_mode": "stream", "bootstrap_parallel": False, "row_group_size": 512_000}

def autotune(verbose=True):
    global GPU_MAX_ROWS, TUNE
    try: enable_crash_diagnostics()          # v17.4: (re)open the trace/crash logs under the configured RESULTS_ROOT
    except Exception: pass
    import os as _os, shutil as _sh, multiprocessing as _mp
    # ---- CPU ----
    cores = _mp.cpu_count() or 1
    try:                                            # v20.7: give numpy/BLAS the whole machine in THIS process
        import _hardware as _H; _H.use_full_machine(verbose=False); TUNE["machine"] = _H.machine_profile()
    except Exception:
        pass
    TUNE["n_jobs"] = max(1, cores)                 # joblib workers for bootstrap / permutation / sklearn (v20.57: every core)
    # ---- RAM ----
    ram = None
    try:
        import psutil; ram = psutil.virtual_memory().total / 1e9
    except Exception:
        try:                                          # Windows fallback without psutil
            import ctypes
            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS(); m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)); ram = m.ullTotalPhys / 1e9
        except Exception:
            pass
    TUNE["ram_gb"] = ram
    # a 1 B-row x ~15-col DiD frame is ~90-120 GB; hold it in RAM only if there is 2x headroom
    TUNE["load_mode"] = "in_memory" if (ram and ram >= 256) else "stream"
    TUNE["row_group_size"] = (32_000_000 if (ram and ram >= 512) else 8_000_000 if (ram and ram >= 256)
                              else 2_000_000 if (ram and ram >= 128) else 512_000)   # v20.41: 4x again on >= 512 GB
    # ---- GPU ----
    T = _torch_cuda()
    if T:
        p = T.cuda.get_device_properties(0); vram = p.total_memory / 1e9
        TUNE["gpu"] = p.name; TUNE["vram_gb"] = vram
        # working set of the demeaner ~ 8 B x rows x (3 + n_FE); v17.3: measured against FREE VRAM at run time
        GPU_MAX_ROWS = gpu_capacity_rows(n_fe=2) or int(0.98 * p.total_memory / (8 * 5))   # v20.57: the 98 % rule
    else:
        TUNE["gpu"] = "CPU (torch/CUDA not available)"
    # ---- disk ----
    try:
        d = _sh.disk_usage(_os.path.dirname(PREPARED_PANEL) or "."); TUNE["disk_free_gb"] = d.free / 1e9
    except Exception:
        pass
    TUNE["bootstrap_parallel"] = TUNE["n_jobs"] > 1
    TUNE["max_rows_in_memory"] = host_capacity_rows()        # v17.3: rows the in-RAM estimators can take NOW
    if verbose:
        print("="*70); print("AUTO-TUNE (measured on this machine)"); print("="*70)
        _m = TUNE.get("machine") or {}
        print(f"  CPU threads        : {cores}" + (f" ({_m.get('physical_cores')} physical, SMT on)" if _m.get("smt") else "")
              + f"  -> n_jobs={TUNE['n_jobs']} for sklearn / bootstrap / permutation; BLAS uses all {cores}")
        print(f"  RAM                : {f'{ram:.0f} GB' if ram else 'unknown'}  -> load_mode={TUNE['load_mode']}, row_group={TUNE['row_group_size']:,}")
        print(f"  GPU                : {TUNE['gpu']}" + (f", {TUNE['vram_gb']:.0f} GB VRAM -> GPU_MAX_ROWS={GPU_MAX_ROWS:,} (from free VRAM)" if TUNE['vram_gb'] else ""))
        _hf = host_free_bytes()
        if _hf: print(f"  RAM free now       : {_hf/1e9:.1f} GB -> in-RAM estimators can hold ~{TUNE['max_rows_in_memory']:,} rows "
                      f"(set MAX_ROWS below this, or use M01_MODE='stream')")
        if TUNE['vram_gb'] and _hf and TUNE['vram_gb'] * 1e9 > _hf:
            print("  NOTE               : GPU VRAM exceeds free host RAM -- the host, not the GPU, is the binding constraint: "
                  "every GPU estimator still needs the rows in host RAM first")
        if TUNE["disk_free_gb"] is not None:
            print(f"  Disk free (panel)  : {TUNE['disk_free_gb']:.0f} GB" + ("   <-- WARNING: <300 GB, tight for a 1B-row run" if TUNE["disk_free_gb"] < 300 else ""))
        print("="*70)
    return dict(TUNE)


def system_report():
    """Print what this run will actually use: CPU threads, RAM, GPU."""
    import platform
    try:
        import psutil; ram = f"{psutil.virtual_memory().total/1e9:.0f} GB RAM, {psutil.virtual_memory().available/1e9:.0f} GB free"
    except Exception: ram = "RAM: (install psutil to report)"
    gpu = "GPU: none usable (numpy path)"
    if _gpu_available():
        t=_TORCH; p=t.cuda.get_device_properties(0)
        gpu = f"GPU: {p.name}, {p.total_memory/1e9:.0f} GB VRAM (demeaning will run here)"
    print(f"[INFO]    {platform.node()} | {os.cpu_count()} logical CPUs | {ram} | {gpu}")

# ====================== VISIBLE STATUS HELPERS ======================
# Every notebook cell ends with one of these, so you ALWAYS see whether it worked.
def ok(msg):
    print(f"[OK]      {msg}")
def info(msg):
    print(f"[INFO]    {msg}")
def warn(msg):
    print(f"[WARNING] {msg}")
def fail(msg):
    print(f"[FAILED]  {msg}")
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
    """Start of a task: prints a timestamped banner and starts its clock. v17.4: also a heartbeat in the trace log."""
    _STEP_CLOCK[str(n)] = _time.time()
    try: trace(f"STEP {n}: {msg}")
    except Exception: pass
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


def cell_guard(fn):
    """Wrap a cell body so it ALWAYS reports something -- success or a readable error --
    instead of dying silently or killing the kernel."""
    def wrapper(*a, **kw):
        LAST_FIT_INFO.clear(); LAST_CLUSTER_USED["value"] = None                       # v20.58: nothing of an earlier model travels into this one
        LAST_DESIGN_COUNTS.update({"table": None, "outcome": None}); LAST_GAP.clear()
        try:
            out = fn(*a, **kw)
            ok(f"{fn.__name__} completed")
            return out
        except InsufficientDataError as e:
            LAST_GAP.update({"status": "data gap", "reason": " ".join(str(e).split())})     # v20.58: written as <model>_<outcome>_DATA_GAP.csv (as R)
            if "outcome_coverage(" in str(e):                      # v20.12: show WHERE the outcome has values
                try:
                    _o = re.search(r"outcome_coverage\('([A-Za-z0-9_]+)'\)", str(e)).group(1)
                    outcome_coverage(_o, verbose=True)
                except Exception:
                    pass
            warn(f"{fn.__name__} blocked by a DATA GAP (not a bug): {e}")
            return None
        except Exception as e:
            LAST_GAP.update({"status": "failed", "reason": f"{type(e).__name__}: {' '.join(str(e).split())}"})
            fail(f"{fn.__name__} raised {type(e).__name__}: {e}")
            import traceback; traceback.print_exc()
            return None
    return wrapper
LAST_GAP = {}      # v20.58: why the last guarded cell wrote no result (a data gap or an error) -- report_model_outcome writes it down

# ====================== MEMORY RELEASE ======================
def release(*objs):
    """Free DataFrames explicitly between models. Call at the END of every model notebook:
        C.release(panel, df)
    v17.2: also unbinds every variable in the CALLER's namespace (the notebook) that points at these
    objects -- deleting a local alias alone (the v14 behaviour) never freed the notebook's memory."""
    import gc, inspect
    n = 0
    try:
        fr = inspect.currentframe().f_back
        for ns in (fr.f_locals, fr.f_globals):
            for name, val in list(ns.items()):
                if name.startswith("__"): continue
                if any(val is o for o in objs):
                    try: del ns[name]; n += 1
                    except Exception: pass
    except Exception:
        pass
    objs = None
    gc.collect()
    ok(f"released {n} notebook variable(s); garbage collected")


# ====================== v17.4: CRASH DIAGNOSTICS ======================
# A dead kernel leaves no Python traceback. Two things now survive it:
#   1. faulthandler: on a segfault / abort (CUDA device assert, BLAS int overflow, driver reset) Python writes the
#      native traceback to RESULTS_ROOT/_crash_<pid>.log BEFORE the process dies.
#   2. trace(): a heartbeat line (wall clock, step name, host RSS, host free, GPU used/free) appended to
#      RESULTS_ROOT/_trace_<pid>.log at every estimator sub-step. After a death, the LAST line names the step.
# Both are plain text: attach them when reporting a crash.
import faulthandler as _fh
_DIAG = {"trace": None, "crash": None}
_PATHS_APPLIED = [False]   # v20.30: set by _apply_paths -- until then the logs go to the system temp folder

def _foreign_path(p):
    """A Windows drive path (D:\\...) on a non-Windows system is RELATIVE there -- it would create junk folders. v20.37:
    detected ANYWHERE in the path, because once made absolute it sits inside it (/home/.../D:\\LKT\\...)."""
    import re as _re
    return os.name != "nt" and bool(_re.search(r"(^|[\\/])[A-Za-z]:[\\/]", str(p)))

def _diag_paths():
    # v20.30: never before the path layout is applied (it used to create the DEFAULT D:\\LKT\\... folders at import,
    # whatever INPUT_DIR you had set), and never a Windows drive path on another OS
    import tempfile as _tf
    d = RESULTS_ROOT if (_PATHS_APPLIED[0] and "RESULTS_ROOT" in globals() and not _foreign_path(RESULTS_ROOT)) else _tf.gettempdir()
    try: os.makedirs(d, exist_ok=True)
    except Exception: d = _tf.gettempdir()
    return os.path.join(d, f"_trace_{os.getpid()}.log"), os.path.join(d, f"_crash_{os.getpid()}.log")
def enable_crash_diagnostics():
    t, c = _diag_paths()
    try:
        fh = open(c, "a"); _fh.enable(file=fh, all_threads=True); _DIAG["crash"] = c
    except Exception as e:
        print(f"[INFO]    faulthandler not enabled: {e}")
    _DIAG["trace"] = t
    trace("diagnostics enabled")
    return t, c
def _mem_line():
    parts = []
    try:
        import psutil; p = psutil.Process(); vm = psutil.virtual_memory()
        parts.append(f"rss {p.memory_info().rss/1e9:.1f} GB free {vm.available/1e9:.1f} GB")
    except Exception:
        pass
    T = _torch_cuda() if "_torch_cuda" in globals() else None
    if T:
        try:
            free, total = T.cuda.mem_get_info(); parts.append(f"gpu used {(total-free)/1e9:.1f}/{total/1e9:.0f} GB")
        except Exception:
            pass
    return " | ".join(parts)
def trace(msg):
    """Heartbeat: printed AND appended to the trace log (flushed, so it survives a kernel death)."""
    line = f"[{_ts()}] {msg} | {_mem_line()}"
    print(f"[TRACE]   {line}")
    p = _DIAG.get("trace")
    if p:
        try:
            with open(p, "a") as fh: fh.write(line + "\n"); fh.flush(); os.fsync(fh.fileno())
        except Exception:
            pass
try:
    enable_crash_diagnostics()
except Exception as _e:
    print(f"[INFO]    crash diagnostics skipped: {_e}")

# ====================== v17.2: MEMORY HELPERS ======================
# v20.56 -- YOUR RULE: NO CHUNKING. Every regression model loads ALL its rows into RAM (and the GPU demeaner takes the
# whole matrix at once, below the 98 % VRAM ceiling; CPU RAM when it does not fit there) and runs on all of them at once.
# The panel is read from the parquet file in one pass when it fits (LOAD_ALL_AT_ONCE), else row group by row group --
# that is only how the rows are READ: every kept row is in RAM before any estimate is computed. Nothing is streamed,
# thinned or sampled for a regression: when the rows do not fit below the 98 % RAM ceiling the run stops with a readable
# message (MEMORY_POLICY = "raise"). The v17.2 two-pass "stream" estimator is kept ONLY as a cross-check of the in-RAM
# result in the validation scripts; no model notebook uses it (M01_MODE = "memory"; "auto" resolves to "memory").
NO_CHUNKING = True
MEMORY_POLICY = "raise"      # v20.58 YOUR RULE: every row -- when a frame cannot fit below 98 % of the RAM the loader stops with a readable
                             #        message naming the batch route (M01's exact streaming estimator; one sub-watershed per pass). The
                             #        v20.57 option "sample" (thin the rows to fit) is gone: nothing is ever sampled
                             # v20.56: "raise" is the rule (no chunking, no thinning); "sample" is not used by any model
MEMORY_COPIES = 6.0          # v17.3: measured peak of the in-RAM 2x2 path = panel + filtered copy + 2 demeaned float64 arrays
                             # + factorised codes + demeaner temporaries + counterfactual columns ~ 6x the compact frame
MEMORY_HEADROOM = 1.0        # v20.57 (your 98 % rule): no headroom below the free RAM -- the only limit is 98 % of the TOTAL
                             # (_hardware.MEMORY_CEILING); v17.4-v20.56 kept 10 % of the free RAM unused
STRING_COLS_TO_CATEGORY = ("subwshed_id", "site_name", "District", "time_fe_year", "time_fe_season", "time_fe_yearseason")
def _memory_budget_bytes():
    """v20.57: what the 98 % RAM ceiling still allows (v20.30: 95 %; before: 90 % of the RAM free when the loader started)."""
    try:
        import _hardware as _H
        b = _H.ram_budget_bytes()
        if b is not None: return b
    except Exception:
        pass
    try:
        import psutil; vm = psutil.virtual_memory(); return max(0.0, vm.available - 0.02 * vm.total)   # v20.57: 98 % of the total
    except Exception:
        return None

def rows_that_fit(bytes_per_row):
    """v20.57 -- YOUR 98 % RULE: how many rows (pixels, points, units) of `bytes_per_row` fit below 98 % of the RAM right now.
    Every former fixed sample size (k-NN weights, forests, nearest neighbours) is this, not a constant. None = unknown (no limit)."""
    b = _memory_budget_bytes()
    return None if b is None else max(1, int(b / float(bytes_per_row)))

def spatial_capacity(k=8):
    """Points whose k-nearest-neighbour weights fit below the 98 % ceiling (coordinates, the tree, k x (row, col, value), temporaries)."""
    return rows_that_fit(2.0 * (64 + 24 * int(k)))

def _compact_frame(d):
    """Strings -> category (a 'SW3' object cell costs ~60 B, a category code 1-2 B); Year/Season/buff_km -> small ints.
    Nothing is rounded: outcomes keep their stored float32/float64."""
    for c in d.columns:
        _is_str = (d[c].dtype == object) or pd.api.types.is_string_dtype(d[c])
        if _is_str and not isinstance(d[c].dtype, pd.CategoricalDtype):
            _head = d[c].head(2000)                      # v17.3: decide from a sample, not a full n-length type scan
            if c in STRING_COLS_TO_CATEGORY or (len(_head) and _head.map(type).eq(str).all()):
                d[c] = d[c].astype("category")
    for c, dt in (("Year", "int16"), ("Season", "int8"), ("buff_km", "int8")):
        if c in d.columns and str(d[c].dtype).startswith(("int", "float")) and d[c].notna().all():
            try: d[c] = d[c].astype(dt)
            except Exception: pass
    return d


# ====================== v17.4: PER-VARIABLE ESTIMATOR FILES ======================
# One Parquet file per outcome variable holding ONLY what the estimators read for that variable:
#   ids/FE (pixel_id int64, subwshed_id dictionary-encoded, Year int16, Season int8, buff_km int8,
#   time_fe_yearseason/time_fe_year/time_fe_season dictionary-encoded, season_sort_rank int8,
#   first_treat_agri_year int16, dose_per_subwshed float32), the outcome (float32), the covariates
#   (Rain, Tmean float32, LandUse int8), latitude/longitude (float64, spatial models) and the treatment
#   columns PRE-COMPUTED as int8 (treatment, control, pre, post, did_term, in_analysis_sample, event_time,
#   period_index). Season == 0 rows are already dropped. ~45 B/row vs ~120+ B/row when the same columns
#   are read from the full panel with Python strings -- and no string handling at model time.
# load_panel(columns=...) uses the variable file automatically when every requested column is in it.
ESTIMATOR_FILES_DIR = os.path.join(os.path.dirname(PREPARED_PANEL), "estimator_files")
try:                                     # v20.14 import-time default from _paths.py (both engines agree)
    import _paths as _PP0
    _sib = sys.modules.get("_prep_common")             # v20.14: adopt a sibling's live layout if it has one
    _live = getattr(_sib, "ACTIVE_PATHS", None)
    _apply_paths(dict(_live) if _live else _PP0.derive(), _propagate=False); del _PP0
except Exception:
    pass
ESTIMATOR_FILE_EXTRA = ["latitude", "longitude", "GapFilled", "Coverage",   # spatial models; v20.35 QC flags
                        "fragment", "site_check", "sws_id_export"]           # v20.57: the fragment rule travels with every file

def _pixel_keep_mask(pixel_ids, fraction, seed=0):
    """Deterministic pixel-level sample: keep a pixel iff hash(pixel_id, seed) mod 1e6 < fraction*1e6.
    Same pixels are kept in every row-group, every column set and every model."""
    ids = np.asarray(pixel_ids)
    if np.issubdtype(ids.dtype, np.integer):
        h = (ids.astype(np.uint64) * np.uint64(11400714819323198485) + np.uint64(seed * 2654435761 + 1)) % np.uint64(1_000_000)
    else:
        h = pd.util.hash_array(pd.Series(ids).astype(str).values, hash_key=f"{seed:016d}") % np.uint64(1_000_000)
    return h < np.uint64(int(fraction * 1_000_000))

_STALE_WARNED = set()

def estimator_file_is_fresh(path, panel=None):
    """v20.25: a per-variable file is only usable if it was written AFTER the panel it was cut from. A rebuilt panel
    (new pixel ids after the near-duplicate merge, new rows, new policy) makes every older per-variable file stale."""
    panel = panel or PREPARED_PANEL
    try:
        if not os.path.exists(panel): return True
        return os.path.getmtime(path) >= os.path.getmtime(panel) - 1.0
    except Exception:
        return False

def estimator_file_is_valid(outcome):
    """v17.6: an existing per-variable file is accepted when it has the treatment columns and the outcome; used by
    P09 to skip (OVERWRITE=False) or rebuild (OVERWRITE=True)."""
    pth = estimator_file_path(outcome)
    if not os.path.exists(pth): return False
    if not estimator_file_is_fresh(pth):                     # v20.25: older than the panel -> rebuild it
        warn(f"{os.path.basename(pth)} is older than the panel -> it will be rebuilt"); return False
    try:
        import pyarrow.parquet as pq
        pf = pq.ParquetFile(pth)
        try:
            cols = set(pf.schema_arrow.names); nrows = pf.metadata.num_rows
        finally:
            try: pf.close()                                  # v20.10: Windows locks an open handle
            except Exception: pass
        need = {"pixel_id", "Year", "Season", "buff_km", "subwshed_id", "site_id", outcome, "did_term", "in_analysis_sample", "post",
                "treatment"}                                              # v20.41: site_id -- files without it are rebuilt
        return need <= cols and nrows > 0
    except Exception:
        return False


def _estimator_meta_path(path):
    return os.path.splitext(path)[0] + ".scenario.json"

def estimator_file_scenario(path):
    """The scenario a per-variable file was built with (None when unknown)."""
    mp = _estimator_meta_path(path)
    if not os.path.exists(mp): return None
    try:
        with open(mp, encoding="utf-8") as fh: m = json.load(fh)
        m["control_zones"] = tuple(m.get("control_zones", ()))
        return m
    except Exception:
        return None

def estimator_file_path(outcome):
    return os.path.join(ESTIMATOR_FILES_DIR, f"{outcome}.parquet")
_EF_NOTICE = {}

def estimator_file_for(columns):
    """The variable file that covers `columns` (exactly one outcome among them), or None."""
    if not columns: return None
    outs = [c for c in columns if c in ALL_ESTIMATION_VARIABLES and c not in DEFAULT_COVARIATES]
    outs = outs or [c for c in columns if c in ALL_ESTIMATION_VARIABLES]
    if len(outs) != 1: return None
    p = estimator_file_path(outs[0])
    if not os.path.exists(p): return None
    if not estimator_file_is_fresh(p):                        # v20.25: never read a file cut from an older panel
        if p not in _STALE_WARNED:
            warn(f"{os.path.basename(p)} is OLDER than the panel (the panel was rebuilt) -- reading the panel instead; "
                 f"re-run P09 to refresh the per-variable files (faster)")
            _STALE_WARNED.add(p)
        return None
    try:
        import pyarrow.parquet as pq
        _pf = pq.ParquetFile(p)
        try: have = set(_pf.schema_arrow.names)
        finally:
            try: _pf.close()
            except Exception: pass
    except Exception:
        return None
    need_ = set(columns) - OPTIONAL_READ_COLUMNS
    if not need_ <= have: return None
    if EXCLUDE_GAPFILLED and "GapFilled" in set(columns) and "GapFilled" not in have:   # v20.35: an older P09 file
        if not _EF_NOTICE.get(p):
            info(f"{os.path.basename(p)} predates v20.35 (no GapFilled column) -> reading the panel instead so gap-filled rows "
                 f"can be excluded; re-run P09 to get the fast per-variable file back")
            _EF_NOTICE[p] = True
        return None
    try:                                                      # v20.57: the fragment rule needs the same columns as in the panel
        _ft = location_table()                                  # v20.58: the location rule's columns
        _need_f = {"site_id", "site_check", "pixel_id", "buff_km"} if _ft.get("mode") == "overlay" else ({"site_id", "pixel_id", "buff_km"} if _ft.get("mode") != "none" else set())
        if _need_f and not _need_f <= have:
            if not _EF_NOTICE.get(p + "#frag"):
                info(f"{os.path.basename(p)} lacks {sorted(_need_f - have)} (written before v20.58) -> reading the panel instead so the "
                     f"location rule applies; re-run P09 to get the fast per-variable file back")
                _EF_NOTICE[p + "#frag"] = True
            return None
    except Exception:
        return None
    return p

# ====================== v20.41: DERIVED OUTCOMES (ground-scale surrogates) ======================
DERIVED_VARIABLES = {}

def _derived_path():
    return os.path.join(os.path.dirname(PREPARED_PANEL), "derived_variables.json")

def register_derived_variable(name, spec, persist=True):
    """A new outcome computed from panel columns (a linear surrogate): every model can run on it once P00 has
    written its estimator file."""
    DERIVED_VARIABLES[name] = spec
    if name not in ALL_ESTIMATION_VARIABLES: ALL_ESTIMATION_VARIABLES.append(name)
    if persist:
        try:
            with open(_derived_path(), "w", encoding="utf-8") as fh: json.dump(DERIVED_VARIABLES, fh, indent=1)
        except Exception as e:
            warn(f"derived variables not saved ({e})")

def load_derived_variables():
    try:
        p = _derived_path()
        if os.path.exists(p):
            for k, v in json.load(open(p, encoding="utf-8")).items():
                register_derived_variable(k, v, persist=False)
    except Exception:
        pass

def build_estimator_files(outcomes=None, path=None, out_dir=None, row_group_size=None, overwrite=False):
    """Stream the prepared panel ONCE per outcome and write <ESTIMATOR_FILES_DIR>/<outcome>.parquet.
    Memory: one row-group at a time. Writes a manifest (rows, bytes, columns) next to the files."""
    if row_group_size is None:                                      # v20.38: 4x larger on big-RAM machines
        row_group_size = int(TUNE.get("row_group_size") or 2_000_000) if "TUNE" in globals() else 2_000_000
    import pyarrow as pa, pyarrow.parquet as pq, pyarrow.compute as pc
    p = path or PREPARED_PANEL; out_dir = out_dir or ESTIMATOR_FILES_DIR
    os.makedirs(out_dir, exist_ok=True)
    pf = pq.ParquetFile(p); avail = set(pf.schema_arrow.names)
    load_derived_variables()
    outcomes = [o for o in (outcomes or ALL_ESTIMATION_VARIABLES)
                if o in avail or (o in DERIVED_VARIABLES and set(DERIVED_VARIABLES[o]["predictors"]) <= avail)]   # v20.41
    _win = (ACTIVE["pre_years"], ACTIVE["post_years"], ACTIVE["year_min"], ACTIVE["year_max"])   # v20.2: files hold
    ACTIVE.update({"pre_years": None, "post_years": None, "year_min": None, "year_max": None})   # EVERY year; the
    info("per-variable files are written with every year in the panel; the year window is applied when a model reads them")
    base = [c for c in ["pixel_id", "subwshed_id", "site_id", "Year", "Season", "buff_km", "time_fe_yearseason", "time_fe_year",
                        "time_fe_season", "season_sort_rank", "first_treat_agri_year", "dose_per_subwshed",
                        "dose_amount_sws", "dose_intensity_per_ha"]           # v20.41: the cluster and the dose travel with every file
            + ALL_COVARIATE_COLUMNS + ESTIMATOR_FILE_EXTRA if c in avail]   # v20.30: every covariate
    manifest = []
    for o in outcomes:
        dst = os.path.join(out_dir, f"{o}.parquet")
        if not overwrite and estimator_file_is_valid(o):
            info(f"{o}: valid file exists ({dst}) -- skipped; set OVERWRITE=True to rebuild"); continue
        if os.path.exists(dst) and not overwrite:
            warn(f"{o}: existing file is incomplete -> rebuilding"); 
        spec = DERIVED_VARIABLES.get(o) if o not in avail else None          # v20.41: a ground-scale surrogate
        _rg_try = int(row_group_size)
        cols = sorted(set(base) | ({o} if spec is None else set(spec["predictors"]))); writer = None; n_rows = 0
        for i in progress(range(pf.num_row_groups), desc=f"estimator file {o}", unit="rg"):
            t = pf.read_row_group(i, columns=cols)              # v20.12: every season is written; the scenario's
            if t.num_rows == 0: continue                         # seasons switch is applied when a model reads
            d = t.to_pandas()
            if spec is not None:                                  # computed row group by row group: no extra memory
                _v = float(spec["intercept"]) + sum(float(b) * pd.to_numeric(d[p], errors="coerce").astype("float64")
                                                    for p, b in zip(spec["predictors"], spec["coef"]))
                d[o] = _v.astype("float32")
                d = d.drop(columns=[p for p in spec["predictors"] if p not in base])
            # derived time FE if the panel lacks them
            if "time_fe_yearseason" not in d: d["time_fe_yearseason"] = d["Year"].astype(str) + "_" + d["Season"].map(SEASON_LABEL)
            if "time_fe_year" not in d: d["time_fe_year"] = d["Year"].astype(str)
            if "time_fe_season" not in d: d["time_fe_season"] = d["Season"].map(SEASON_LABEL)
            if "season_sort_rank" not in d: d["season_sort_rank"] = d["Season"].map(SEASON_SORT_RANK)
            d = build_treatment_columns(d)                         # in place: int8 treatment/control/pre/post/did_term/...
            d = _compact_frame(d)
            for c in (o,) + tuple(x for x in ALL_COVARIATE_COLUMNS if not _is_categorical_col(x)):
                if c in d and str(d[c].dtype) == "float64": d[c] = d[c].astype("float32")
            for c in ("LandUse", "event_time"):
                if c in d and d[c].notna().all():
                    try: d[c] = d[c].astype("int16" if c == "event_time" else "int8")
                    except Exception: pass
            if "period_index" in d: d["period_index"] = d["period_index"].astype("int32")
            if "first_treat_agri_year" in d:            # v20.29: ALWAYS float32 -- the old "int16 when this chunk has no
                d["first_treat_agri_year"] = pd.to_numeric(d["first_treat_agri_year"], errors="coerce").astype("float32")   # blank" rule
                                                        # made row groups disagree (P09 failed at row group 38 of NDVI)
            tbl = pa.Table.from_pandas(d, preserve_index=False)
            if writer is None: writer = pq.ParquetWriter(dst, tbl.schema, compression="zstd")
            elif tbl.schema != writer.schema:                     # v20.29: every chunk takes the file's schema
                try:
                    tbl = tbl.select(writer.schema.names).cast(writer.schema)
                except Exception as _e:
                    raise RuntimeError(f"{os.path.basename(dst)}: a row group's columns cannot take the file's types "
                                       f"({_e}); columns {[f.name for f in tbl.schema if f.name in writer.schema.names and f.type != writer.schema.field(f.name).type]}")
            while True:                                       # v20.41: out of memory -> 4x smaller row groups, same file
                try:
                    writer.write_table(tbl, row_group_size=_rg_try); break
                except MemoryError:
                    if _rg_try <= 512_000: raise
                    _rg_try = max(512_000, _rg_try // 4); warn(f"{o}: out of memory -> row groups of {_rg_try:,} rows")
            n_rows += len(d)
        if writer is not None: writer.close()
        with open(_estimator_meta_path(dst), "w", encoding="utf-8") as fh:
            json.dump({"control_zones": list(ACTIVE["control_zones"]), "treatment_year": ACTIVE["treatment_year"],
                       "post_cutoff": ACTIVE["post_cutoff"], "exclude_transition_year": ACTIVE["exclude_transition_year"],
                       "year_min": ACTIVE["year_min"], "year_max": ACTIVE["year_max"],
                       "pre_years": ACTIVE["pre_years"], "post_years": ACTIVE["post_years"],
                       "scenario_tag": scenario_tag()}, fh, indent=1)
        sz = os.path.getsize(dst) if os.path.exists(dst) else 0
        manifest.append({"outcome": o, "file": dst, "rows": n_rows, "bytes_on_disk": sz, "columns": ",".join(cols + ["treatment", "control", "pre", "post", "did_term", "in_analysis_sample", "event_time", "period_index"])})
        ok(f"{o}: {n_rows:,} rows -> {dst} ({sz/1e9:.2f} GB on disk)")
    ACTIVE["pre_years"], ACTIVE["post_years"], ACTIVE["year_min"], ACTIVE["year_max"] = _win
    mf = os.path.join(out_dir, "estimator_files_manifest.csv")
    pd.DataFrame(manifest).to_csv(mf, index=False, mode="a" if os.path.exists(mf) else "w", header=not os.path.exists(mf))
    ok(f"manifest -> {mf}")
    return manifest

# ====================== MEMORY-SAFE PANEL LOADER ======================
LOAD_ALL_AT_ONCE = True      # v20.30: read the columns a model needs from the WHOLE file in one multi-threaded pass when
                             # that fits below the 98 % RAM ceiling; else row group by row group (the previous path)
PANEL_CACHE = {}             # (file, mtime) -> {"cols": set, "table": pyarrow table, "bytes": int} -- reused by later loads
PANEL_CACHE_SHARE = 0.5      # the cache may hold at most this share of what the RAM ceiling allows
_BYTES = {"double": 8, "float64": 8, "int64": 8, "float": 4, "float32": 4, "int32": 4, "int16": 2, "int8": 1, "bool": 1}

def clear_panel_cache():
    PANEL_CACHE.clear(); gc.collect()

def _table_bytes(t):
    try:
        return int(t.nbytes)
    except Exception:
        try: return int(t.to_pandas().memory_usage(deep=True).sum())
        except Exception: return 0

def _estimate_read_bytes(pf, cols, n_rows):
    """Bytes of `cols` x `n_rows` once in memory, from the file's column types (text / dictionary: 16 B)."""
    per = 0
    try:
        sch = pf.schema_arrow
        for c_ in cols:
            try:
                _t = str(sch.field(c_).type)
                _wid = _t in ("float", "float32") and not _is_categorical_col(c_) and (c_ in ALL_ESTIMATION_VARIABLES or c_ in ALL_COVARIATE_COLUMNS
                                                                                      or c_ in DOUBLE_PRECISION_EXTRA)
                per += 8 if _wid else _BYTES.get(_t, 16)          # v20.58: widened to float64 at load (every calculation in double)
            except Exception: per += 8
    except Exception:
        per = 8 * len(cols)
    return float(per) * float(n_rows)

def _read_whole(p, cols):
    import pyarrow.parquet as pq
    try:
        return pq.read_table(p, columns=list(cols), use_threads=True, memory_map=True)
    except TypeError:                                             # minimal readers without those options
        return pq.read_table(p, columns=list(cols))

def _cached_or_read(p, pf, read_cols):
    """The table for read_cols from the session cache, else ONE multi-threaded read (for the prepared panel the
    superset of every model column is read when it also fits, so the next outcome's load is served from RAM)."""
    import _hardware as _H
    try: key = (os.path.abspath(p), os.path.getmtime(p))
    except Exception: key = (os.path.abspath(p), 0)
    ent = PANEL_CACHE.get(key)
    if ent and set(read_cols) <= ent["cols"]:
        info(f"served from the in-RAM panel cache ({len(read_cols)} columns, no disk read)")
        return ent["table"].select(list(read_cols))
    want = list(read_cols)
    try:
        if os.path.abspath(p) == os.path.abspath(PREPARED_PANEL):
            sup = set(ID_FE_COLS) | set(ALL_ESTIMATION_VARIABLES) | set(ALL_COVARIATE_COLUMNS) | {
                "latitude", "longitude", "sws_name", "site_check", "site_id", "dose_per_subwshed", "first_treat_agri_year", "LandUse"}
            cand = [c_ for c_ in pf.schema_arrow.names if c_ in sup or c_ in read_cols]
            if _H.fits(_estimate_read_bytes(pf, cand, pf.metadata.num_rows) * (2 + MEMORY_COPIES)):
                want = cand
    except Exception:
        pass
    t = _read_whole(p, want)
    tb = _table_bytes(t); bud = _H.ram_budget_bytes() or 0
    while PANEL_CACHE and sum(e["bytes"] for e in PANEL_CACHE.values()) + tb > PANEL_CACHE_SHARE * bud:
        PANEL_CACHE.pop(next(iter(PANEL_CACHE)))
    if tb <= PANEL_CACHE_SHARE * bud:
        PANEL_CACHE[key] = {"cols": set(want), "table": t, "bytes": tb}
    return t.select(list(read_cols)) if set(want) != set(read_cols) else t

# ====================== v20.32: NEGATIVE VALUES IN ESTIMATION (your switch) ======================
# Negative values of the INDICES are real measurements: NDVI < 0 over water and wet bare soil, NDWI > 0 over water and
# < 0 over vegetation, NDMI / LSWI < 0 over dry soil, SMDI is a deficit index centred on 0. Removing them truncates one
# tail of the outcome -- a non-linear transformation -- so the estimate is no longer the effect on the index itself, and
# the bias goes whichever way the negative share happens to differ between core and rings, before and after. It does NOT
# turn a negative result into a positive one: a DiD coefficient is negative when the rings improved MORE than the core,
# which has nothing to do with the sign of any single value. Default False. True is available for exploration; those runs
# land in their own results folder (tag ..._noNegDrop / ..._noNegZero) and every result file records it.
BLOCK_NEGATIVES_IN_ESTIMATION = False   # True = no negative value of any estimation variable enters the models
NEGATIVE_BLOCK_MODE = "drop"            # "drop" = the whole row leaves the sample | "zero" = the value is floored at 0

def negative_value_report(outcome, columns=None, path=None, save=True, verbose=True):
    """What blocking negatives would remove: the share of negative values by group (core / rings) and period
    (pre / post), per estimation column. A share that differs across those four cells is exactly what biases a
    truncated estimate -- read this before switching BLOCK_NEGATIVES_IN_ESTIMATION on."""
    cols = list(columns or ([outcome] + list(DEFAULT_COVARIATES)))
    d = build_treatment_columns(load_panel(columns=columns_for(outcome), path=path))
    d = d[d.in_analysis_sample == 1]
    rows = []
    for c_ in [x for x in cols if x in d.columns]:
        v = pd.to_numeric(d[c_], errors="coerce")
        for (t_, p_), g in v.groupby([d.treatment, d.post]):
            rows.append({"variable": c_, "group": "core" if t_ == 1 else "rings", "period": "post" if p_ == 1 else "pre",
                         "rows": int(len(g)), "negative": int((g < 0).sum()), "share_negative": float((g < 0).mean())})
    out = pd.DataFrame(rows)
    if verbose and len(out):
        info(f"negative values in the estimation sample for '{outcome}' (what blocking would remove):")
        print(out.pivot_table(index="variable", columns=["group", "period"], values="share_negative")
                 .applymap(lambda x: f"{x:.2%}").to_string())
    if save and len(out):
        p_ = os.path.join(results_dir("M00_Diagnostics"), f"negative_values_{outcome}.csv")
        out.to_csv(p_, index=False); info(f"-> {p_}")
    return out

# ====================== v20.32: NEGATIVE VALUES IN ESTIMATION -- one switch, default OFF ======================
# Covariates are already floored at 0 when the panel is built (v20.30). This switch is about the OUTCOME, and it is
# OFF by default because excluding negative outcome values is SELECTION ON THE DEPENDENT VARIABLE: NDVI, NDWI, NDMI,
# LSWI, NDRE and SMDI are designed to go negative over water, bare soil and moisture stress, so the dropped rows are
# the driest and most degraded pixels -- exactly the ones the works should change. The DiD coefficient is a
# DIFFERENCE (core minus rings, after minus before); it can be negative with every value positive, so this switch
# does not "remove negative results". Every result produced with it ON is labelled in the saved file.
NONNEGATIVE_ESTIMATION = False      # True = no negative values from any estimation variable enter the DiD
NONNEGATIVE_MODE = "drop"           # "drop" = leave those rows out | "zero" = floor the negative values at 0
NONNEGATIVE_SCOPE = "outcome+covariates"    # or "outcome" / "covariates"

_NN_SHADOW = {"v": False}

def _force_negative_from_active():
    """v20.34: the outcome-loop lock and the scenario file are AUTHORITATIVE -- the filter takes ACTIVE's value, and a
    stale direct assignment cannot override the design the first outcome ran with."""
    global NONNEGATIVE_ESTIMATION
    NONNEGATIVE_ESTIMATION = bool(ACTIVE.get("nonnegative", False)); _NN_SHADOW["v"] = NONNEGATIVE_ESTIMATION
    _sync_negative_switch()

def _sync_negative_switch():
    """v20.34: the SCENARIO (ACTIVE["nonnegative"]) is the single source of truth for the negative filter -- the
    results folder, the saved labels and the filter itself all read it. A direct assignment to C.NONNEGATIVE_ESTIMATION
    or the older alias C.BLOCK_NEGATIVES_IN_ESTIMATION is still honoured (pushed into the scenario). Before this, the
    panel scenario could reset the flag while the filter kept running: your loop dropped 100 % of NDWI under a folder
    and labels that said the filter was OFF."""
    global NONNEGATIVE_ESTIMATION, NONNEGATIVE_MODE, BLOCK_NEGATIVES_IN_ESTIMATION, NEGATIVE_BLOCK_MODE
    if bool(NONNEGATIVE_ESTIMATION) != _NN_SHADOW["v"]:
        ACTIVE["nonnegative"] = bool(NONNEGATIVE_ESTIMATION)
    elif bool(BLOCK_NEGATIVES_IN_ESTIMATION) != _NN_SHADOW["v"]:
        ACTIVE["nonnegative"] = bool(BLOCK_NEGATIVES_IN_ESTIMATION); ACTIVE["nonnegative_mode"] = str(NEGATIVE_BLOCK_MODE)
    NONNEGATIVE_ESTIMATION = bool(ACTIVE.get("nonnegative", False))
    NONNEGATIVE_MODE = str(ACTIVE.get("nonnegative_mode", NONNEGATIVE_MODE))
    BLOCK_NEGATIVES_IN_ESTIMATION = NONNEGATIVE_ESTIMATION; NEGATIVE_BLOCK_MODE = NONNEGATIVE_MODE
    globals()["NONNEGATIVE_SCOPE"] = str(ACTIVE.get("nonnegative_scope", globals().get("NONNEGATIVE_SCOPE", "outcome+covariates")))
    _NN_SHADOW["v"] = NONNEGATIVE_ESTIMATION

def nonnegative_columns(est_cols, outcome):
    """Which estimation columns the switch applies to."""
    if NONNEGATIVE_SCOPE == "outcome": return [c_ for c_ in est_cols if c_ == outcome]
    if NONNEGATIVE_SCOPE == "covariates": return [c_ for c_ in est_cols if c_ != outcome]
    return list(est_cols)

# ====================== v20.45: THE OUTCOME SCREEN -- a year the export filled is not data ======================
# Your diagnostics: NDMI in 2020-2024, VCI in 2018-2019, SMDI in 2020 and 2024 carry values for ~54 treated and
# ~193,000 control pixels (of 619,271 / 1,248,914), and the treated and control means are IDENTICAL -- one constant
# written for every pixel. Such a year has no variation left after the fixed effects: every DiD on it is ~0 with an SE
# of ~0 (your beta 0.000014, SE 0.00000000). A year-season is screened out when the outcome is CONSTANT across pixels,
# or when its coverage (treated or control) collapses below 5 % of the typical year-season. An outcome left without
# two valid pre-period years (or any valid post year) is refused with that reason -- never estimated on fill values.
OUTCOME_SCREEN = "drop"          # v20.59: the outcome screen's RULE -- "drop" (True): a year-season whose values are constant across pixels (a fill
                                 #   value) or whose coverage collapsed leaves every model, as before | "keep": it is reported, its evidence written
                                 #   and KEPT (the model runs; results tagged _screenKept) | "off" (False): no screen. Set in each model's CELL 1
                                 #   (OUTCOME_SCREEN -> set_scenario(outcome_screen=...)). The evidence of every decision -- rows, pixels, mean, SD,
                                 #   min and max per year-season -- is OUTCOME_SCREEN_<outcome>.csv beside the results (every run, every rule).
SCREEN_MIN_COVERAGE = 0.05
SCREEN_REPORT = {}
SCREEN_EVIDENCE = {}             # v20.59: outcome -> the per-cell evidence table of the last screen (what OUTCOME_SCREEN_<outcome>.csv holds)

def _screen_rule_of(v):
    if v is True: return "drop"
    if v is False or v is None: return "off"
    v = str(v).strip().lower()
    if v in ("drop", "true", "on", "1"): return "drop"
    if v in ("keep", "report", "warn"): return "keep"
    if v in ("off", "false", "none", "0", "no"): return "off"
    raise InsufficientDataError(f"OUTCOME_SCREEN must be 'drop', 'keep' or 'off' (got {v!r})")

DESIGN_SOURCES = ("panel", "model")
def _design_source_of(v):
    """v20.59: DESIGN_SOURCE -- 'panel' (the panel's design columns are estimated on) | 'model' (the design in effect is)."""
    s = str(v).strip().lower()
    if s not in DESIGN_SOURCES: raise InsufficientDataError(f"DESIGN_SOURCE must be 'panel' or 'model' (got {v!r})")
    return s

def screen_rule(scn=None):
    """v20.59: the screen's rule in force -- 'drop' | 'keep' | 'off' (the design's outcome_screen, else the constant OUTCOME_SCREEN)."""
    a = scn if scn is not None else globals().get("ACTIVE")
    v = a.get("outcome_screen") if isinstance(a, dict) else None
    return _screen_rule_of(OUTCOME_SCREEN if v is None else v)

def _screen_table(t, pixel_ids=None):
    """v20.59: the screen's evidence per (Year, Season) from t (Year, Season, tr, y; finite y only): rows, pixels, mean, SD across the rows,
    min, max, treated / control rows."""
    g = t.groupby(["Year", "Season"]).agg(n=("y", "size"), mean=("y", "mean"), sd=("y", "std"), vmin=("y", "min"), vmax=("y", "max"))
    g["n_treated"] = t[t.tr].groupby(["Year", "Season"]).size().reindex(g.index).fillna(0).astype(int)
    g["n_control"] = t[~t.tr].groupby(["Year", "Season"]).size().reindex(g.index).fillna(0).astype(int)
    g["n_pixels"] = (t.assign(_p=np.asarray(pixel_ids)).groupby(["Year", "Season"])["_p"].nunique().reindex(g.index).fillna(0).astype(float)
                     if pixel_ids is not None else np.nan)
    return g

def screen_decide_table(g, outcome):
    """v20.59: the screen's two decisions on its (Year, Season) table -- constant across pixels (a fill value), coverage collapsed -- added as
    the columns usable / why, each with its numbers. Shared by the in-memory screen, the per-variable report (P09) and the out-of-core path."""
    g = g.copy()
    g["sd"] = g["sd"].fillna(0.0)
    const = g["sd"] <= 1e-9 * np.maximum(1.0, g["mean"].abs())
    med_t, med_c = float(g["n_treated"].median()), float(g["n_control"].median())
    collapse = (g["n_treated"] < SCREEN_MIN_COVERAGE * med_t) | (g["n_control"] < SCREEN_MIN_COVERAGE * med_c)
    why = []
    for (yy, ss), r in g.iterrows():
        w = []
        if const.loc[(yy, ss)]:
            npx = r.get("n_pixels", np.nan)
            w.append(f"constant across pixels (a fill value: {int(r.n):,} rows" + (f" of {int(npx):,} pixels" if np.isfinite(npx) else "")
                     + f", every value {r.vmin:.6g}" + (f"..{r.vmax:.6g}" if r.vmax != r.vmin else "") + ")")
        if collapse.loc[(yy, ss)]:
            w.append(f"coverage collapsed ({int(r.n_treated):,} treated / {int(r.n_control):,} control rows against typical {med_t:,.0f} / {med_c:,.0f})")
        why.append("; ".join(w))
    g["usable"] = ~(const | collapse); g["why"] = why; g["outcome"] = outcome
    return g

def screen_evidence_path(outcome):
    try: os.makedirs(RESULTS_ROOT, exist_ok=True)
    except Exception: pass
    return os.path.join(RESULTS_ROOT, f"OUTCOME_SCREEN_{outcome}.csv")

def screen_report(g, outcome, rule=None, verbose=True):
    """v20.59: the screen's report from its decided table -- the evidence file (every cell, every rule), the message with the numbers, and
    what to leave out: (the (Year, Season) cells to DROP -- none under 'keep', the report rows, the evidence path)."""
    rule = rule or screen_rule()
    bad = g[~g["usable"]]
    rep_rows = [{"outcome": outcome, "Year": int(yy), "Season": SEASON_LABEL.get(int(ss), ss), "why": r.why} for (yy, ss), r in bad.iterrows()]
    SCREEN_REPORT[outcome] = rep_rows
    ev = g.reset_index()
    ev["season"] = ev["Season"].map(lambda s: SEASON_LABEL.get(int(s), s)); ev["rule"] = rule; ev["left_out"] = (~ev["usable"]) & (rule == "drop")
    ev = ev.rename(columns={"n": "rows", "n_pixels": "pixels", "sd": "sd_across_pixels", "vmin": "min", "vmax": "max", "n_treated": "treated_rows", "n_control": "control_rows"})
    ev = ev[[c for c in ("outcome", "Year", "Season", "season", "rows", "pixels", "mean", "sd_across_pixels", "min", "max", "treated_rows", "control_rows", "usable", "rule", "left_out", "why") if c in ev.columns]]
    SCREEN_EVIDENCE[outcome] = ev
    path = screen_evidence_path(outcome)
    try: ev.to_csv(path, index=False)
    except Exception: path = "(the evidence file could not be written)"
    if rep_rows and verbose:
        warn(f"{outcome}: {len(rep_rows)} of {len(g)} year-season(s) are NOT pixel data"
             + (" and are left out" if rule == "drop" else " -- KEPT (OUTCOME_SCREEN = 'keep': the model runs on them" + " -- NOTE: in a fill year-season every pixel holds ONE value, so the treated-control difference there is exactly 0; kept, it dilutes the gap the DiD compares (a pre gap g over n real pre periods becomes g x n / (n + 1)) and the estimate moves by that dilution. Use 'keep' only if these ARE pixel data)")
             + " -- " + "; ".join(f"{r['Year']} {r['Season']}: {r['why']}" for r in rep_rows[:6]) + ("; ..." if len(rep_rows) > 6 else "")
             + f" -> the evidence of every year-season (rows, pixels, mean, SD, min, max): {path}")
    drop = set((int(a), int(b)) for a, b in bad.index) if rule == "drop" else set()
    return drop, rep_rows, path

def screen_refusal_text(outcome, pre, post, n_bad, n_cells, path):
    return (f"'{outcome}' is not usable: after the screen ({n_bad} of {n_cells} year-seasons left out as fill values / collapsed coverage) it has "
            f"{len(pre)} valid pre-period year(s) {pre} and {len(post)} post-period year(s) {post} (need >= 2 and >= 1). The evidence -- rows, "
            f"pixels, mean, SD, min and max per year-season -- is in {path}. If those year-seasons ARE pixel data, set OUTCOME_SCREEN = 'keep' in "
            f"this model's settings (the model then runs on every year-season, tagged _screenKept) -- or re-export the variable if they are not.")

def screen_refuse_years(outcome, yrs, n_bad, n_cells, path, refuse=True):
    """v20.59: fewer than 2 pre / 1 post years left after the screen -> the refusal names the evidence and the way out."""
    T = int(ACTIVE.get("treatment_year") or 2022)
    pre, post = [v for v in yrs if v < T], [v for v in yrs if v >= T]
    if refuse and (len(pre) < 2 or not post):
        raise InsufficientDataError(screen_refusal_text(outcome, pre, post, n_bad, n_cells, path))

DATA_RULES_VERSION = "20.58"    # bump when a data rule changes (screen, zeros, ...): cached package inputs are rebuilt
                                # v20.57: the fund timing and dose, the fragment rule and the always-rebuilt cohorts
                                # v20.54: v20.52 added a rule (rows with Coverage <= 0 left out) without bumping this, so
                                # inputs written under the v20.49 rules were still reused; v20.54 keeps fill values missing
                                # when the negative-covariate barrier is off

def _site_list():
    """The sites SITE_FILTER selects, as a sorted list of ints (None = every site) -- read the way site_rows reads it
    (an int, or any list-like: list, tuple, set, numpy array, range, pandas Series)."""
    if SITE_FILTER is None: return None
    vals = [SITE_FILTER] if np.isscalar(SITE_FILTER) else list(SITE_FILTER)
    return sorted({int(x) for x in vals})

def _site_suffix():
    """v20.54: the sites a package input holds. Without it, a per-site run (run_sites / MS01) wrote site 1's input and
    every later site with the same scenario tag READ SITE 1's ROWS."""
    s = _site_list()
    if s is None: return ""
    if len(s) <= 6: return "_site" + "-".join(str(x) for x in s)
    import hashlib                                           # 20 sites would make the Windows path too long
    return f"_sites{len(s)}_" + hashlib.sha1(",".join(map(str, s)).encode()).hexdigest()[:8]

def package_input_stem(outcome, out_dir=None):
    """v20.46: the package-input file name carries the data-rules version -- an input written under older rules (e.g.
    before the fill-year screen) is never reused. v20.54: and the sites it holds (per-site runs)."""
    return os.path.join(out_dir or os.path.join(ESTIMATOR_FILES_DIR, "package_input"),
                        f"{outcome}_{scenario_tag()}{_site_suffix()}_rules{DATA_RULES_VERSION}")

def _panel_identity(path=None):
    p = os.path.abspath(path or PREPARED_PANEL)
    try: return {"panel": p, "panel_mtime": round(os.path.getmtime(p), 3), "panel_bytes": int(os.path.getsize(p))}
    except Exception: return {"panel": p, "panel_mtime": None, "panel_bytes": None}

def package_input_is_fresh(stem, path=None):
    """v20.54: a package input is reused only when it was cut from THIS panel as it is now. Before, an existing file was
    always reused: after P00 rebuilt the panel (new exports, the full file set instead of a sample, new rules) every
    pre-built package route kept estimating on the OLD panel's rows while the engine cross-check used the new one."""
    if not (os.path.exists(stem + ".parquet") or os.path.exists(stem + ".csv")): return False
    try:
        with open(stem + ".json", encoding="utf-8") as fh: meta = json.load(fh)
    except Exception:
        return False                                        # written before v20.54: its panel is unknown -> rebuild once
    now = _panel_identity(path)
    return (meta.get("panel") == now["panel"] and meta.get("panel_mtime") == now["panel_mtime"]
            and meta.get("panel_bytes") == now["panel_bytes"] and meta.get("site_filter") == str(_site_list())
            and meta.get("fund") == _fund_identity_text())                  # v20.57: a revised fund workbook changes timing and dose

def _fund_identity_text():
    """The fund workbook's version (path, modified time, size) as text -- '' when there is none."""
    try:
        import _fund as _F
        p_ = _fund_path()
        return str(_F.file_identity(p_)) if p_ and os.path.exists(p_) else ""
    except Exception:
        return ""

def package_input_ready(outcome, path=None):
    """The stem of a package input for the scenario in force that is FRESH for the current panel and sites -- written
    (or re-written) by export_for_packages when missing or stale. Every pre-built package route reads through this."""
    stem = package_input_stem(outcome)
    if not package_input_is_fresh(stem, path):
        if os.path.exists(stem + ".json") or os.path.exists(stem + ".parquet") or os.path.exists(stem + ".csv"):
            info(f"package input for {outcome} was cut from an older panel (or other sites) -> rebuilt from the current panel")
        export_for_packages(outcome, path=path)     # overwrites the files (the .json last); if it fails, the old files stay
    return stem                                     # stale and are not used -- the model hands over to the engine

def screened_year_seasons(outcome, with_years=False):
    """v20.46: the (Year, Season) cells the outcome screen removes -- for the paths that stream files instead of load_panel.
    with_years=True also returns the years that keep at least one EXISTING usable year-season."""
    t = screen_all_outcomes([outcome], write=False, verbose=False)
    if t is None or not len(t) or "usable" not in t.columns: return (set(), None) if with_years else set()
    inv = {v: k for k, v in SEASON_LABEL.items()}
    bad = {(int(r.Year), int(inv.get(r.Season, r.Season))) for r in t.itertuples() if not bool(r.usable)}
    good = {int(r.Year) for r in t.itertuples() if bool(r.usable)}
    return (bad, good) if with_years else bad

def screen_outcome_frame(df, outcome, verbose=True, refuse=True):
    """The outcome screen on a loaded frame (v20.45; v20.59: the evidence of every decision, the rule OUTCOME_SCREEN drop / keep / off, and a
    refusal that names the evidence file and the way out)."""
    rule = screen_rule()
    if rule == "off" or outcome not in getattr(df, "columns", ()) or "Year" not in df.columns or not len(df):
        return df
    y = pd.to_numeric(df[outcome], errors="coerce").values.astype("float64")
    fin = np.isfinite(y)
    season = df["Season"].values if "Season" in df.columns else np.zeros(len(df), int)
    tr = (pd.to_numeric(df["buff_km"], errors="coerce").values == TREAT_CORE_BUFFKM) if "buff_km" in df.columns else np.zeros(len(df), bool)
    t = pd.DataFrame({"Year": pd.to_numeric(df["Year"], errors="coerce").values, "Season": season, "tr": tr, "y": y})[fin]
    if not len(t): return df
    g = screen_decide_table(_screen_table(t, df["pixel_id"].values[fin] if "pixel_id" in df.columns else None), outcome)
    drop, rep_rows, path = screen_report(g, outcome, rule, verbose=verbose)
    if drop:
        m = pd.MultiIndex.from_arrays([pd.to_numeric(df["Year"], errors="coerce").values, season]).isin(sorted(drop))
        df = df[~m]
    yrs = sorted(set(int(v) for v in pd.to_numeric(df["Year"], errors="coerce").dropna().unique())) if len(df) else []
    screen_refuse_years(outcome, yrs, len(rep_rows), len(g), path, refuse=refuse)
    return df

def screen_all_outcomes(outcomes=None, write=True, verbose=True):
    """The screen for every variable, streamed from its per-variable file -> OUTCOME_SCREEN.csv / .md."""
    import pyarrow.parquet as _pq
    rows = []
    for o in (outcomes or ALL_ESTIMATION_VARIABLES):
        p = estimator_file_path(o) if "estimator_file_path" in globals() else None
        if not p or not os.path.exists(p): continue
        try:
            pf = _pq.ParquetFile(p); acc = {}
            for i in range(pf.num_row_groups):        # v20.59: exact moments row group by row group (mean / M2 combined, as the out-of-core screen), min, max
                d = pf.read_row_group(i, columns=[x for x in ("Year", "Season", "buff_km", o) if x in pf.schema_arrow.names]).to_pandas()
                v = pd.to_numeric(d[o], errors="coerce"); f = np.isfinite(v.values)
                d = d[f].assign(_v=v[f].astype("float64"), _tr=(pd.to_numeric(d.loc[f, "buff_km"], errors="coerce") == TREAT_CORE_BUFFKM))
                for k, gg in d.groupby(["Year", "Season"]):
                    n, mu = len(gg), float(gg._v.mean()); m2 = float(((gg._v - mu) ** 2).sum())
                    a = acc.get(k)
                    if a is None: acc[k] = [n, mu, m2, int(gg._tr.sum()), int((~gg._tr).sum()), float(gg._v.min()), float(gg._v.max())]; continue
                    N = a[0] + n; dlt = mu - a[1]
                    a[1] = a[1] + dlt * n / N; a[2] = a[2] + m2 + dlt * dlt * a[0] * n / N; a[0] = N
                    a[3] += int(gg._tr.sum()); a[4] += int((~gg._tr).sum()); a[5] = min(a[5], float(gg._v.min())); a[6] = max(a[6], float(gg._v.max()))
            if not acc: continue
            g = pd.DataFrame([{"Year": int(k[0]), "Season": int(k[1]), "n": a[0], "mean": a[1], "sd": (math.sqrt(a[2] / (a[0] - 1)) if a[0] > 1 else 0.0),
                               "vmin": a[5], "vmax": a[6], "n_treated": a[3], "n_control": a[4], "n_pixels": np.nan} for k, a in acc.items()]).set_index(["Year", "Season"])
            g = screen_decide_table(g, o)                       # v20.59: the same two decisions, the same numbers, as the models' screen
            for (yy, ss), r in g.iterrows():
                rows.append({"outcome": o, "Year": int(yy), "Season": SEASON_LABEL.get(int(ss), ss), "treated_pixels": int(r.n_treated),
                             "control_pixels": int(r.n_control), "rows": int(r.n), "mean": float(r["mean"]), "sd_across_pixels": float(r.sd),
                             "min": float(r.vmin), "max": float(r.vmax), "usable": bool(r.usable), "why": r.why})
        except Exception as e:
            rows.append({"outcome": o, "why": f"screen failed: {e}"})
    out = pd.DataFrame(rows)
    if write and len(out):
        os.makedirs(RESULTS_ROOT, exist_ok=True); out.to_csv(os.path.join(RESULTS_ROOT, "OUTCOME_SCREEN.csv"), index=False)
        bad = out[out.get("usable", True) == False]
        md = ["# Outcome screen -- year-seasons that are not pixel data", "",
              f"{len(bad)} of {len(out)} outcome x year-season cells are left out of every model (constant fill values or collapsed coverage).", "",
              "| outcome | year | season | treated px | control px | mean | SD across pixels | min | max | why |", "|---|---|---|---|---|---|---|---|---|---|"]
        md += [f"| {r.outcome} | {r.Year} | {r.Season} | {r.treated_pixels:,} | {r.control_pixels:,} | {r.mean:.6g} | {r.sd_across_pixels:.3g} | {r.min:.6g} | {r.max:.6g} | {r.why} |" for r in bad.itertuples()]
        md += ["", f"Rule in force: OUTCOME_SCREEN = {screen_rule()!r} ('drop' leaves these cells out of every model; 'keep' keeps them, said; 'off' runs no screen)."]
        open(os.path.join(RESULTS_ROOT, "OUTCOME_SCREEN.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
        if verbose: info(f"outcome screen: {len(bad)} outcome x year-season cells are fill / collapsed -> OUTCOME_SCREEN.md")
    return out

_PANEL_DEDUP_NOTED = set()

def panel_dedup_note(panel_path=None, verbose=True):
    """v20.58 (your rule "repeated rows are dropped"): how the panel on disk treated REPEATED rows (the same sub-watershed, pixel, year and
    season in two exports). Until v20.57 P00 filled the kept row's gaps with the repeated rows' values; a panel built so (no
    'dedup_fill_from_duplicates' in panel_build_settings.json, or True) holds values of dropped rows -- every model says so once per
    session until P00 has rebuilt it (P00 rebuilds it by itself). Returns 'dropped whole' / 'filled' / 'unknown'."""
    pp = panel_path or PREPARED_PANEL
    bs = os.path.join(os.path.dirname(os.path.abspath(pp)), "panel_build_settings.json")
    try:
        got = json.load(open(bs, encoding="utf-8")) if os.path.exists(bs) else None
    except Exception:
        got = None
    if got is None: state = "unknown"
    elif "dedup_fill_from_duplicates" not in got or bool(got.get("dedup_fill_from_duplicates")): state = "filled"
    else: state = "dropped whole"
    if verbose and pp not in _PANEL_DEDUP_NOTED:
        _PANEL_DEDUP_NOTED.add(pp)
        if state == "filled":
            warn("this panel was built with the gaps of the kept rows FILLED from REPEATED rows (another export of the same pixel, year and season"
                 + ("; every panel before v20.58" if got is not None and "dedup_fill_from_duplicates" not in got else "; DEDUP_FILL_FROM_DUPLICATES = True")
                 + ") -- values of dropped rows are in it. Your rule drops a repeated row whole: re-run P00 (it rebuilds the panel by itself)")
        elif state == "unknown" and os.path.exists(pp):
            warn(f"no panel_build_settings.json beside {os.path.basename(pp)}: how its repeated rows were resolved is not recorded -- re-run P00 "
                 f"(a v20.58 panel drops a repeated row whole)")
    return state


def load_panel(columns=None, season_not_equal=0, path=None, max_rows=None, finite_only=True,
               subwshed_filter=None, sample_fraction=None, seed=0, batch_rows=None, screen=True):
    """v15 -- OUT-OF-CORE loader for a ~1-billion-row panel.
    Reads ONE Parquet row-group at a time (each ~512k rows), applies the filters to that
    row-group, keeps only what survives, and moves on. Peak RAM ~ one row-group + kept rows.
      columns          : ONLY these are read from disk (Parquet column projection)
      season_not_equal : Season!=0 rule applied per row-group (drops the composited 'Yearly' rows)
      subwshed_filter  : list of subwshed_id values -> run a model on a subset of sites
      sample_fraction  : e.g. 0.05 keeps a random 5% of rows of EVERY row-group (unbiased)
      max_rows         : stop reading once this many rows are kept
    For the FULL 1B-row pixel regression, prefer R06 (fixest) -- see SCALE_STRATEGY.md."""
    import pyarrow.parquet as pq, pyarrow as pa, pyarrow.compute as pc
    _ensure_resolved()                                                  # v20.57: the design of THIS run (CELL 1), resolved once
    p = path or PREPARED_PANEL
    _ef = estimator_file_for(columns) if path is None else None       # v17.4: per-variable file fast path
    if _ef:
        p = _ef; info(f"reading the per-variable estimator file {os.path.basename(_ef)} (Season!=0 rows, compact dtypes, treatment columns pre-computed)")
        _meta = estimator_file_scenario(_ef)
        if _meta and scenario_tag(_meta) != scenario_tag():
            info(f"that file was built for scenario {scenario_tag(_meta)}; the columns will be rebuilt for {scenario_tag()}")
    if not os.path.exists(p):
        raise InsufficientDataError(
            f"Prepared panel not found at {p}. Run 01_Panel_Preparation/P00_RUN_ALL first, "
            f"then set PREPARED_PANEL in _common.py to the file it produced.")
    pf = pq.ParquetFile(p)
    if path is None or os.path.abspath(p) == os.path.abspath(PREPARED_PANEL) or _ef:
        panel_dedup_note()                                          # v20.58: a panel whose repeated rows filled gaps is announced
    avail = set(pf.schema_arrow.names)
    need = set(columns) if columns else avail
    for f_ in (["Season"] if season_not_equal is not None else []) + (["subwshed_id"] if subwshed_filter else []):
        need.add(f_)
    # v15.1: the time-FE columns are pure functions of Year/Season, so a panel written by an
    # earlier P00 that lacks them is still usable -- derive them after reading instead of failing.
    DERIVABLE = {"time_fe_year", "time_fe_season", "time_fe_yearseason", "season_sort_rank"}
    derive = sorted((need & DERIVABLE) - avail)
    if derive:
        need = (need - set(derive)) | {"Year", "Season"}
        info(f"deriving {derive} from Year/Season (not stored in this panel)")
    # v20.28: descriptive columns added in later versions are read when present, never required -- a panel (or a
    # per-variable file) written before them stays fully usable
    OPTIONAL = set(OPTIONAL_READ_COLUMNS)                                   # v20.35: one definition
    need = need - ((need & OPTIONAL) - avail)
    # v20.58: YOUR RULE -- only the CURRENT sub-watershed's own data (the location rule): the columns it reads come along (when present)
    _frag_tab = location_table(PREPARED_PANEL) if os.path.exists(PREPARED_PANEL) else location_table(p)
    _loc_S = processing_sites(_frag_tab)[0] if _frag_tab.get("mode") != "none" else []
    if _frag_tab.get("mode") != "none":
        need |= {c_ for c_ in LOCATION_COLUMNS if c_ in avail}
    _frag_n = {}
    missing = sorted(need - avail)
    if missing:
        raise InsufficientDataError(f"panel lacks required columns {missing}; present: {sorted(avail)[:12]}...")
    read_cols = sorted(need)
    rng = np.random.default_rng(seed); parts = []; kept = 0; scanned = 0
    info(f"streaming {pf.metadata.num_rows:,} rows in {pf.num_row_groups} row-groups; "
         f"reading {len(read_cols)} columns")
    # ---- v17.2 memory guard ----------------------------------------------------------
    # The frame is copied ~MEMORY_COPIES times downstream (treatment columns, sample filter,
    # demeaned float64 arrays). If the projected peak exceeds the RAM that is free right now,
    # the loader THINS every row-group by the same fraction (unbiased) instead of letting the
    # kernel die, and says so loudly. MEMORY_POLICY = "raise" makes it stop instead.
    _budget = _memory_budget_bytes()
    _auto_frac = None
    _est_cols = sorted(CURRENT_ESTIMATION_COLUMNS) if finite_only else []
    _sync_negative_switch()                                        # v20.33: ONE switch (either name works)
    _blk = bool(NONNEGATIVE_ESTIMATION); _blk_mode = str(NONNEGATIVE_MODE); _n_neg = 0
    _n_missing_dropped = 0; _n_seen = 0; _n_zero_dropped = 0; _n_yearly_filled = 0
    _n_ring_skip = 0; _n_gapfilled = 0; _gf_by = {}                          # v20.35
    # v20.30: the whole table at once when it fits below the 98 % RAM ceiling (v20.57) -- one multi-threaded read (or the
    # in-RAM cache), then the SAME filters as the row-group path, applied once. Otherwise row group by row group.
    _whole = None
    if LOAD_ALL_AT_ONCE and not max_rows and not sample_fraction:
        try:
            import _hardware as _H
            _raw = _estimate_read_bytes(pf, read_cols, pf.metadata.num_rows)
            if _H.fits(_raw * (2 + MEMORY_COPIES)):
                _whole = _cached_or_read(p, pf, read_cols)
                info(f"all at once: {len(read_cols)} columns x {pf.metadata.num_rows:,} rows in RAM ({_raw / 1e9:.1f} GB) -- "
                     f"{_H.memory_report()}")
            else:
                info(f"read row group by row group (the whole unfiltered table, ~{_raw * (2 + MEMORY_COPIES) / 1e9:.0f} GB with working copies, "
                     f"would pass the {int(_H.MEMORY_CEILING * 100)} % RAM ceiling); every row this model keeps stays in RAM and the "
                     f"regression runs on all of them at once -- {_H.memory_report()}")
        except Exception as _e:
            warn(f"whole-table read unavailable ({type(_e).__name__}: {str(_e)[:80]}) -- row group by row group"); _whole = None
    _chunks = [(0, _whole)] if _whole is not None else ((i_, None) for i_ in range(pf.num_row_groups))
    for i, t in progress(_chunks, total=(1 if _whole is not None else pf.num_row_groups), desc="reading the panel (every kept row stays in RAM)", unit="rg"):
        if t is None: t = pf.read_row_group(i, columns=read_cols)
        scanned += t.num_rows
        mask = None
        if season_not_equal is not None:
            import pyarrow.compute as pc
            mode = seasons_mode(path=p, verbose=False)                     # v20.12 / v20.24 auto; v20.55: named seasons too
            _codes = season_codes(mode)
            mask = (pc.not_equal(t["Season"], -1) if _codes is None else
                    pc.is_in(t["Season"], value_set=pa.array(sorted(_codes), type=t["Season"].type)))
        if subwshed_filter:
            m2 = pc.is_in(t["subwshed_id"], value_set=pa.array(list(subwshed_filter)))
            mask = m2 if mask is None else pc.and_(mask, m2)
        if mask is not None:
            t = t.filter(mask)
        if t.num_rows == 0:
            continue
        d = _compact_frame(t.to_pandas())
        if has_year_window() and "Year" in d.columns:            # v20.2: window applied while streaming
            d = d[year_mask(d["Year"].values)]
            if not len(d): continue
        if SITE_FILTER is not None and "site_id" in d.columns:   # v20.22: one site, a list of sites, or all
            d = site_rows(d)
            if not len(d): continue
        if _frag_tab.get("mode") != "none":                       # v20.58: the location rule, row by row (the whole-frame checks below)
            _kf, _cf = location_mask(d, _frag_tab, _loc_S, pooled=False)
            if (_cf > 0).any(): _count_location(_frag_n, d, _cf)
            if not _kf.all():
                d = d[_kf]
                if not len(d): continue
        if LOAD_SCENARIO_ROWS_ONLY and "buff_km" in d.columns and CURRENT_MODEL_ID not in MODELS_NEEDING_ALL_RINGS:
            _b = pd.to_numeric(d["buff_km"], errors="coerce").values         # v20.35: only this scenario's rings
            _kb = (_b == TREAT_CORE_BUFFKM) | np.isin(_b, list(ACTIVE["control_zones"]))
            if not _kb.all():
                _n_ring_skip += int((~_kb).sum()); d = d[_kb]
                if not len(d): continue
        if EXCLUDE_GAPFILLED and "GapFilled" in d.columns:                   # v20.35: imputed from 3-year history
            _gf = pd.to_numeric(d["GapFilled"], errors="coerce").fillna(0).values > 0
            if "Coverage" in d.columns:                                    # v20.52: a window with NO real observation
                _gf |= pd.to_numeric(d["Coverage"], errors="coerce").fillna(1).values <= 0   # (fully projected) as well
            if _gf.any():
                if "buff_km" in d.columns and "Year" in d.columns:
                    _tr = pd.to_numeric(d["buff_km"], errors="coerce").values[_gf] == TREAT_CORE_BUFFKM
                    _po = pd.to_numeric(d["Year"], errors="coerce").values[_gf] >= int(ACTIVE["treatment_year"])
                    for _k, _mm in (("treated_post", _tr & _po), ("treated_pre", _tr & ~_po),
                                    ("control_post", ~_tr & _po), ("control_pre", ~_tr & ~_po)):
                        _gf_by[_k] = _gf_by.get(_k, 0) + int(_mm.sum())
                _n_gapfilled += int(_gf.sum()); d = d[~_gf]
                if not len(d): continue
        if _est_cols and "Season" in d.columns and (pd.to_numeric(d["Season"], errors="coerce") == 0).any():
            _covs_ = [c_ for c_ in _est_cols if c_ != CURRENT_OUTCOME and not _is_categorical_col(c_)]
            d, _nf = fill_yearly_covariates(d, _covs_, path=p)      # v20.24: annual rows keep their covariates
            _n_yearly_filled += _nf
        # v20.13: MISSING-VALUE POLICY, applied where every model's data passes. A row whose outcome or any
        # covariate is not finite cannot enter a regression; left in, a single NaN poisons the fixed-effect
        # means and every estimate comes out NaN (M01) or the solver fails (M02 "SVD did not converge").
        if finite_only and _est_cols and set(_est_cols) <= set(d.columns):
            _m = np.ones(len(d), dtype=bool); _mz = np.ones(len(d), dtype=bool)
            for _c in _est_cols:
                _v = pd.to_numeric(d[_c], errors="coerce").values.astype(np.float64)
                _m &= np.isfinite(_v)
                if ZERO_AS_MISSING and _c not in ZERO_RULE_EXCEPT and not _is_categorical_col(_c) and _c not in FLOORED_COVARIATES: _mz &= (_v != 0)   # v20.30
            _n_zero_dropped += int((_m & ~_mz).sum())
            _m &= _mz
            if _blk:                                            # v20.32: your switch -- no negative value in estimation
                _neg = np.zeros(len(d), dtype=bool)
                for _c in _est_cols:
                    if _c in d.columns and not _is_categorical_col(_c):
                        _neg |= (pd.to_numeric(d[_c], errors="coerce").values < 0)
                _n_neg += int((_m & _neg).sum())
                if _blk_mode == "zero":
                    for _c in _est_cols:
                        if _c in d.columns and not _is_categorical_col(_c):
                            d[_c] = pd.to_numeric(d[_c], errors="coerce").clip(lower=0)
                else:
                    _m &= ~_neg
            _n_missing_dropped += int((~_m).sum()); _n_seen += len(d)
            if not _m.all():
                d = d[_m]
                if not len(d): continue
        # v17.6: sampling is by PIXEL (deterministic hash of pixel_id), never by row: every kept pixel keeps
        # all its periods, so the panel stays balanced and the two-way demeaning stays exact. Row-wise
        # thinning (v17.2-v17.5) broke the balance and inflated the SE more than necessary.
        if sample_fraction:
            d = d[_pixel_keep_mask(d["pixel_id"].values, sample_fraction, seed)]
        elif _budget and i == 0 and len(d) and not _OOC_WORKER:   # v20.58: a pixel partition was sized by the out-of-core planner
            _per_row = d.memory_usage(deep=True).sum() / max(len(d), 1)
            _rows_total = pf.metadata.num_rows if season_not_equal is None else pf.metadata.num_rows * (1 - 1.0 / 34)
            _proj = _per_row * _rows_total * MEMORY_COPIES
            if _proj > _budget:
                # v20.58 YOUR RULE: never a sample. v20.57 could THIN the rows here (MEMORY_POLICY = "sample") -- removed: every row or a
                # readable stop that names the batch route (the exact two-pass streaming estimator of M01, or one sub-watershed per run)
                import _outofcore as _O
                _msg = (f"every row of this outcome needs ~{_proj/1e9:.1f} GB ({MEMORY_COPIES} copies of {_per_row:.0f} B/row x {_rows_total:,.0f} rows) -- "
                        f"above 98 % of the RAM ({_budget/1e9:.1f} GB left). Nothing is sampled (your rule): ")
                if CURRENT_MODEL_ID in _O.OOC_MODELS:           # v20.58: Dask / Spark / the built-in batches take over (exact)
                    raise OutOfCoreNeeded(_msg + f"{CURRENT_MODEL_ID} runs OUT OF CORE ({' -> '.join(_O.engine_order())}; exact, every row)")
                raise InsufficientDataError(_msg + f"{', '.join(_O.OOC_MODELS)} run out of core (Dask / Spark / the built-in batches); "
                                            f"{CURRENT_MODEL_ID or 'this model'} needs every row in one place -- run it one sub-watershed per pass (MS01).")
        parts.append(d); kept += len(d)
        if max_rows and kept >= max_rows:
            break
    if not parts:
        raise InsufficientDataError("no rows survived the filters -- the location rule (every row of the processed sub-watershed(s) must lie "
                                    "inside its own polygon: FRAGMENT_RULE / OVERLAP_ROWS, see the LOCATION lines above), SUB_WATERSHEDS / the "
                                    "sub-watershed filter, or the Season rule")
    df = pd.concat(parts, ignore_index=True)
    if _frag_tab.get("mode") != "none" and len(df):              # v20.58: the whole-frame location checks -- a control row of a pixel TREATED
        _kf2, _cf2 = location_mask(df, _frag_tab, _loc_S, pooled=True)   # in another processed sub-watershed, a repeated pixel-year-season
        _new = (_cf2 == 3)
        if _new.any(): _count_location(_frag_n, df, np.where(_new, 3, 0).astype(np.int8))
        if not _kf2.all(): df = df[_kf2].reset_index(drop=True)
    if _n_yearly_filled:
        info(f"annual rows: {_n_yearly_filled:,} covariate values the annual composite lacks were filled with the same "
             f"pixel-year's seasonal mean (yearly-first keeps its weather adjustment)")
    if _blk and _n_neg:
        _share = _n_neg / max(_n_seen, 1)
        if _share > 0.30:
            warn(f"the non-negative filter removed {_share:.0%} of the rows of '{CURRENT_OUTCOME}' ({_n_neg:,} of {_n_seen:,}). "
                 f"An index that is mostly negative over land (NDWI, and often NDMI / LSWI / NDRE / SMDI) is left with "
                 f"almost nothing, so the model will report 'no variation' or an effect estimated on a different "
                 f"population. Switch NONNEGATIVE off for this outcome.")
        warn(f"NONNEGATIVE is ON ({_blk_mode}): {_n_neg:,} rows with a negative value were "
             f"{'floored at 0' if _blk_mode == 'zero' else 'removed'}. This truncates one tail of the outcome, so the "
             f"estimate is no longer the effect on the index itself -- C.negative_value_report(outcome) shows how "
             f"unevenly the negatives sit across core / rings and pre / post. Report such runs as exploration only.")
    LAST_LOAD_INFO.clear(); LAST_LOAD_INFO.update({"negatives_blocked": (_blk_mode if _blk else "no"),
                                                   "rows_with_negative_value": int(_n_neg),
                                                   "rows_seen": _n_seen, "rows_dropped_missing": _n_missing_dropped,
                                                   "yearly_covariates_filled": _n_yearly_filled,
                                                   "seasons_used": seasons_mode(path=p, verbose=False) if "p" in dir() else None,
                                                   "rows_dropped_zero": _n_zero_dropped, "estimation_columns": list(_est_cols),
                                                   "nonnegative_filter": (f"{_blk_mode} ({NONNEGATIVE_SCOPE})" if _blk else "off"),
                                                   "rows_with_negative_values": _n_neg,
                                                   "gapfilled_rows_excluded": _n_gapfilled, "gapfilled_by_group": dict(_gf_by),
                                                   "ring_rows_not_loaded": _n_ring_skip,
                                                   "fragment_rule": ACTIVE.get("fragment_rule", "drop"),          # v20.57
                                                   "overlap_rows": ACTIVE.get("overlap_rows", "drop"),            # v20.58: the location rule
                                                   "location_rows": {f"{k[0]}|{int(k[1])}|{int(k[2])}": int(v) for k, v in _frag_n.items()},
                                                   "processed_sites": list(_loc_S),
                                                   "fragment_rows_dropped": int(sum(v for k, v in _frag_n.items() if k[0] in location_drop_codes()))})
    if _frag_n:
        location_report_lines(_frag_n, label=f"{CURRENT_OUTCOME or 'panel'}: ")
    if _n_gapfilled:
        info(f"gap-filled rows left out: {_n_gapfilled:,} (" + ", ".join(f"{k} {v:,}" for k, v in _gf_by.items() if v)
             + ") -- the exporter blended their unpublished days with the 3-year historical mean (EXCLUDE_GAPFILLED)")
    if _n_ring_skip:
        info(f"{_n_ring_skip:,} rows outside this scenario's rings were not loaded (control rings {tuple(ACTIVE['control_zones'])})")
    if _n_missing_dropped:
        _share = _n_missing_dropped / max(_n_seen, 1)
        (warn if _share > 0.25 else info)(f"missing-value policy: excluded {_n_missing_dropped:,} of {_n_seen:,} rows "
                                           f"({_share:.1%}) where {_est_cols} is NaN or exactly zero "
                                           f"({_n_zero_dropped:,} of them zero-valued) -- they cannot enter a regression"); del parts
    df = _compact_frame(df)                      # categoricals survive concat only if categories match; re-compact
    # v20.58: EVERY CALCULATION IN DOUBLE PRECISION (as R). The panel stores the outcomes, covariates and doses as float32 (7 significant
    # digits -- more than the sensors resolve -- at half the disk and RAM); here, once, they are widened to float64, so no group mean, sum
    # or solve downstream runs in float32. v20.57 averaged float32 columns in float32: the M16 pre-trend F differed from R's by 1.4e-5
    # (relative) from that alone; widened, what is left (1e-6) is the float32 STORAGE of the raw values, identical in both engines' inputs.
    _wide = [c_ for c_ in df.columns if str(df[c_].dtype) == "float32" and not _is_categorical_col(c_)
             and (c_ in ALL_ESTIMATION_VARIABLES or c_ in ALL_COVARIATE_COLUMNS or c_ in DOUBLE_PRECISION_EXTRA or c_ in DERIVED_VARIABLES)]
    for c_ in _wide: df[c_] = df[c_].astype("float64")
    # v20: any frame that carries pre-computed treatment columns (from a per-variable estimator file) is made
    # consistent with the ACTIVE scenario here, so a model can never read columns baked for a different choice.
    if {"buff_km", "Year"} <= set(df.columns) and ({"treatment", "did_term", "control", "in_analysis_sample"} & set(df.columns)):
        df = apply_scenario(df)
    df.attrs["sample_fraction_applied"] = sample_fraction or _auto_frac or 1.0
    if max_rows and len(df) > max_rows:
        df = df.iloc[:max_rows].copy()
    if derive:
        if "time_fe_year" in derive:       df["time_fe_year"] = df["Year"].astype(str)
        if "time_fe_season" in derive:     df["time_fe_season"] = df["Season"].map(SEASON_LABEL)
        if "time_fe_yearseason" in derive: df["time_fe_yearseason"] = df["Year"].astype(str) + "_" + df["Season"].map(SEASON_LABEL)
        if "season_sort_rank" in derive:   df["season_sort_rank"] = df["Season"].map(SEASON_SORT_RANK)
    if columns:                                                  # v20.58: site_check stays -- SAMPLE INTEGRITY confirms nothing outside
        df = df[[c for c in list(columns) + [x for x in ("site_check",) if x not in columns] if c in df.columns]]
    mb = df.memory_usage(deep=True).sum() / 1e6
    ok(f"kept {len(df):,} of {scanned:,} scanned rows x {df.shape[1]} cols ({mb:.1f} MB)")
    if mb > 8000:
        info(f"this frame holds {mb / 1000:.1f} GB -- it fits below 98 % of the RAM, every row stays (your rule)")
    if screen and CURRENT_OUTCOME and CURRENT_OUTCOME in df.columns:   # v20.45: fill years are not data (v20.58: screen=False -- one pixel
        df = screen_outcome_frame(df, CURRENT_OUTCOME)                 #   partition of the out-of-core path; the screen is the WHOLE panel's)
    df.attrs["location_rule_applied"] = _frag_tab.get("mode") != "none"   # v20.58: build_treatment_columns need not repeat it
    return df


# ====================== v20.58: BEYOND 98 % OF THE RAM -- OUT OF CORE (Dask, then Spark, then the built-in batches; _outofcore.py) ======================
def run_mode(model_id=None, columns=None, verbose=False):
    """'memory' -- every row in RAM (and on the GPU) at once, ONE regression: YOUR RULE whenever the model's sample fits below 98 % of the
    RAM -- or 'out_of_core' beyond it, for the models with an exact out-of-core path (_outofcore.OOC_MODELS: M01, M02, M16, M34): Dask,
    then Spark, then the built-in batches (OUT_OF_CORE in _paths.py). Returns (mode, why). REWARD_FORCE_OUT_OF_CORE (the checks) forces it."""
    import _outofcore as _O
    model_id = model_id or CURRENT_MODEL_ID
    f = _O.forced()
    if f and model_id in _O.OOC_MODELS:
        return "out_of_core", f"REWARD_FORCE_OUT_OF_CORE = {os.environ.get('REWARD_FORCE_OUT_OF_CORE')} (a check: the out-of-core path on data that fit)"
    p = (estimator_file_for(columns) if columns else None) or PREPARED_PANEL
    if not os.path.exists(p):
        return "memory", "no panel file yet (the loader says what to run)"
    try:
        cols = _O._read_columns(columns, p)
        bpr, n = _O._bytes_per_row(p, cols)
    except Exception as e:
        return "memory", f"the memory need could not be measured ({type(e).__name__}); the loader decides"
    n = n * (1.0 if p != PREPARED_PANEL else (1 - 1.0 / 34))
    need = bpr * n * float(MEMORY_COPIES); budget = _memory_budget_bytes()
    if budget is None or need <= budget:
        return "memory", (f"every row fits below 98 % of the RAM (~{need / 1e9:.2f} GB" + (f" of {budget / 1e9:.1f} GB" if budget else "")
                          + "): all rows in RAM (and on the GPU) at once, one regression -- your rule")
    if model_id in _O.OOC_MODELS:
        return "out_of_core", (f"all {n:,.0f} rows need ~{need / 1e9:.1f} GB, above 98 % of the RAM ({budget / 1e9:.1f} GB left): OUT OF CORE on "
                               f"{' -> '.join(_O.engine_order())} -- exact, every row, nothing sampled")
    return "memory", (f"all rows need ~{need / 1e9:.1f} GB, above 98 % of the RAM; {model_id} has no out-of-core path -- the loader stops with the "
                      f"per-sub-watershed route (MS01)")

def load_panel_ooc(columns, finite_only=True):
    """load_panel beyond 98 % of the RAM: the same rows in pixel partitions (every row of a pixel in one), on Dask / Spark / batches."""
    import _outofcore as _O
    return _O.load_panel_ooc(columns, finite_only=finite_only)

def ooc_model(model_id, outcome, panel, results_dir_, control_zones=None, covariates=None, use_covariates=True, balanced=False):
    """A model's CELL 3 out of core (M01, M02, M16, M34): the same estimator, numbers and files as in memory (validate_out_of_core.py)."""
    import _ooc_models as _OM
    return _OM.ooc_model(model_id, outcome, panel, results_dir_, control_zones=control_zones, covariates=covariates,
                         use_covariates=use_covariates, balanced=balanced)

# ====================== OUTCOME LOOP INSIDE ONE MODEL NOTEBOOK (v17.11) ======================
# You run ONE model notebook at a time, by hand. Its last cell then repeats THAT SAME notebook for every remaining
# variable in SELECTED_OUTCOMES, so a single Run All gives you every outcome of that model with no manual edits.
# There is no across-models runner: each module is started by you, deliberately.
SELECTED_OUTCOMES = ["NDVI", "SAVI", "EVI", "LAI", "LSWI", "NDWI", "NDMI", "NDRE", "AGB", "RUSLE",
                     "ESI", "WSSI", "WSI", "SMDI", "VCI", "TCI", "VHI"]     # edit here, once, for the whole pipeline
OUTCOME_LOOP_STATE = {"outcome": None, "model": None, "scenario": None}
def current_outcome(default="NDVI"):
    """The outcome this pass is estimating: the one injected by the notebook's own outcome loop, else `default`
    (the variable you set in CELL 1). Weather variables are refused -- they are covariates."""
    o = OUTCOME_LOOP_STATE.get("outcome") or os.environ.get("REWARD_OUTCOME") or default
    return assert_is_outcome(o)

def outcomes_available(outcomes=None, path=None):
    """The selected outcomes that actually exist in the panel (or have a per-variable estimator file)."""
    import pyarrow.parquet as pq
    outs = list(outcomes or SELECTED_OUTCOMES)
    try:
        _pf = pq.ParquetFile(path or PREPARED_PANEL)
        try: have = set(_pf.schema_arrow.names)
        finally:
            try: _pf.close()
            except Exception: pass
    except Exception:
        have = set()
    keep = [o for o in outs if o in have or os.path.exists(estimator_file_path(o))]
    missing = [o for o in outs if o not in keep]
    if missing: warn(f"not in the panel, skipped: {missing}")
    return keep

def _result_files(model_id, outcome):
    d = results_dir(model_id, make=False)
    if not os.path.isdir(d): return []
    return [x for x in os.listdir(d) if x.endswith(f"_{outcome}.csv") or x.endswith(f"_{outcome}.parquet")]

def run_model_notebook(nb_path, outcome, overwrite=False, skip_cells=("CELL 0", "gpu_selftest", "run_other_outcomes"), verbose=True):
    """Re-execute THIS model notebook for ONE outcome in a fresh namespace (nothing leaks between outcomes).
    Used only by run_other_outcomes(); it never touches another model. Existing results are skipped unless
    overwrite=True, and a failure is caught and reported so the remaining outcomes still run."""
    import time as _t, traceback, gc
    nb = json.load(open(nb_path, encoding="utf-8"))
    model_id = os.path.basename(nb_path).split("_")[0]
    if not overwrite and _result_files(model_id, outcome):
        info(f"{model_id} x {outcome}: results exist ({_result_files(model_id, outcome)[0]}) -- skipped (OVERWRITE=True to redo)")
        return {"model": model_id, "outcome": outcome, "status": "skipped", "seconds": 0.0, "files": _result_files(model_id, outcome)}
    OUTCOME_LOOP_STATE.update({"outcome": outcome, "model": model_id, "scenario": dict(ACTIVE)})
    ns = {"__name__": "__main__", "os": os, "json": json}
    t0 = _t.time(); status = "ok"; err = ""
    trace(f"{model_id} x {outcome}: start")
    try:
        for c in nb["cells"]:
            if c["cell_type"] != "code": continue
            src = "".join(c["source"])
            if any(k in src for k in skip_cells) and "ROBUST IMPORT BOOTSTRAP" not in src: continue
            src = "\n".join(l for l in src.split("\n") if not l.lstrip().startswith(("%", "!")))
            exec(compile(src, nb_path, "exec"), ns)
    except SystemExit:
        pass
    except Exception as e:
        status = "failed"; err = f"{type(e).__name__}: {e}"
        fail(f"{model_id} x {outcome}: {err}")
        if verbose: traceback.print_exc(limit=3)
    finally:
        for k in ("panel", "df", "d", "data"):
            ns.pop(k, None)
        ns.clear(); gc.collect()
        OUTCOME_LOOP_STATE.update({"outcome": None, "model": None, "scenario": None})
    el = _t.time() - t0
    files = _result_files(model_id, outcome)
    if status == "ok" and not files:
        status = "no_result"     # the notebook ran but wrote nothing for this outcome (e.g. a documented DATA GAP)
    (ok if status == "ok" else warn)(f"{model_id} x {outcome}: {status} in {_fmt_secs(el)}" + (f" -> {files}" if files else ""))
    trace(f"{model_id} x {outcome}: {status} ({el:.0f}s)")
    return {"model": model_id, "outcome": outcome, "status": status, "seconds": round(el, 1), "files": ";".join(files), "error": err}

def find_model_notebook(model_id, root=None):
    """Locate a model notebook by its MODEL_ID (M01 ... M45) inside the bundle."""
    import glob
    root = root or os.path.dirname(os.path.abspath(__file__))
    hits = sorted(glob.glob(os.path.join(root, "0*", f"{model_id}_*.ipynb")))
    return hits[0] if hits else None

# ====================== v20.22: INPUT FOR THE PRE-BUILT MODELS (fixest / pyfixest / did / HonestDiD) ======================
PACKAGE_INPUT_COLUMNS = ["pixel_id", "unit", "site_id", "subwshed_id", "cluster_id", "Year", "Season", "period",
                         "treat", "post", "did", "event_time", "cohort", "buff_km"]

def export_for_packages(outcome, covariates=None, path=None, out_dir=None, fmt=("parquet", "csv"), max_rows=None):
    """Write ONE tidy table per outcome, in the shape every pre-built estimator expects and nothing else:
        pixel_id   unit id (int64)             site_id    SWSiD_All (0 if single-site export)
        cluster_id the cluster the scenario chose (sub-watershed, or site when cluster='site')
        Year, Season, period ("2023_Kharif" -- the Year x Season fixed effect; site|period under pooled_fe='site_period')
        treat      1 = saturation core         post 1 = Year >= the (site's) treatment year
        did        treat x post                event_time  Year - (site's) treatment year
        cohort     first treated year for treated units, Inf for never-treated controls (did:: / csdid convention)
        <outcome>, <covariates>                the values, missing-value policy already applied
    Rows: the scenario's analysis sample only (rings chosen, year window, seasons, sites). Written to
    estimator_files/package_input/<outcome>_<scenario>.parquet and .csv. The R and pyfixest pipelines read these."""
    import pyarrow as pa, pyarrow.parquet as pq
    covs = list(resolve_covariates(covariates) if covariates is not None else DEFAULT_COVARIATES)
    _cols = columns_for(outcome, list(covs) + ["latitude", "longitude", "dose_per_subwshed", "sws_name"])
    CURRENT_ESTIMATION_COLUMNS.clear(); CURRENT_ESTIMATION_COLUMNS.update({outcome} | set(covs))   # v20.31: rows filtered
    d = load_panel(columns=_cols, path=path)                                                      # by the EXPORTED covariates
    d = build_treatment_columns(d); d = d[d["in_analysis_sample"] == 1].copy()
    ty = int(ACTIVE["treatment_year"])
    site_years = ACTIVE.get("site_years") if ACTIVE.get("use_site_years") else {}
    out = pd.DataFrame({
        "pixel_id": d["pixel_id"].astype("int64").values,
        # v20.29: the unit fixed effect of the scenario (pixel x season series by default) as a compact int32 code --
        # R reads 64-bit integers as doubles, which cannot hold every 17-digit pixel id exactly
        "unit": pd.factorize(d["unit_id"] if "unit_id" in d.columns else d["pixel_id"])[0].astype("int32"),
        "site_id": pd.to_numeric(d["site_id"], errors="coerce").fillna(0).astype(int).values if "site_id" in d.columns else 0,
        "subwshed_id": d["subwshed_id_orig"].astype(str).values if "subwshed_id_orig" in d.columns else d["subwshed_id"].astype(str).values,
        "cluster_id": d[_cluster_key(d, "subwshed_id")].astype(str).values,     # v20.42: sub-watersheds (>= 6) or years
        "Year": d["Year"].astype(int).values, "Season": d["Season"].astype(int).values,
        "period": d["time_fe_yearseason"].astype(str).values,
        "treat": d["treatment"].astype(int).values, "post": d["post"].astype(int).values, "did": d["did_term"].astype(int).values,
        "event_time": np.where(d["treatment"].values == 1, d["event_time"].astype(float).values, np.nan),   # v20.58: never-treated -> missing (as R)
        "cohort": (pd.to_numeric(d["first_treat_agri_year"], errors="coerce").values if "first_treat_agri_year" in d.columns   # v20.57: always
                   else np.where(d["treatment"].values == 1, float(ty), np.inf)),                                               # the timing in force
        "buff_km": pd.to_numeric(d["buff_km"], errors="coerce").values,
        outcome: pd.to_numeric(d[outcome], errors="coerce").values,
    })
    for cv in covs:
        if cv in d.columns: out[cv] = pd.to_numeric(d[cv], errors="coerce").values
    if "sws_name" in d.columns: out["sws_name"] = d["sws_name"].astype(str).values     # v20.28
    for extra in ("latitude", "longitude"):                               # v20.23: spatial and dose models need these
        if extra in d.columns: out[extra] = pd.to_numeric(d[extra], errors="coerce").values
    if "dose" in d.columns: out["dose"] = pd.to_numeric(d["dose"], errors="coerce").values   # v20.57: DOSE_VARIABLE from the fund file
    if max_rows and len(out) > max_rows: out = out.iloc[:max_rows]
    out_dir = out_dir or os.path.join(ESTIMATOR_FILES_DIR, "package_input"); os.makedirs(out_dir, exist_ok=True)
    stem = package_input_stem(outcome, out_dir)
    written = []
    if "parquet" in fmt:
        pq.write_table(pa.Table.from_pandas(out, preserve_index=False), stem + ".parquet", compression="zstd"); written.append(stem + ".parquet")
    if "csv" in fmt:
        out.to_csv(stem + ".csv", index=False); written.append(stem + ".csv")
    meta = {"outcome": outcome, "covariates": covs, "scenario": dict((k, (list(v) if isinstance(v, tuple) else v)) for k, v in ACTIVE.items()),
            "scenario_tag": scenario_tag(), "rows": int(len(out)), "n_treated_pixels": int(out.loc[out.treat == 1, "pixel_id"].nunique()),
            "n_clusters": int(out.cluster_id.nunique()), "cohorts": sorted(set(float(x) for x in out.cohort.unique() if np.isfinite(x))),
            "columns": list(out.columns), "written": _ts(),
            **_panel_identity(path), "site_filter": str(_site_list()), "data_rules": DATA_RULES_VERSION,   # v20.54: freshness
            "fund": _fund_identity_text()}                                                                   # v20.57: and the fund file
    with open(stem + ".json", "w", encoding="utf-8") as fh: json.dump(meta, fh, indent=1, default=str)
    ok(f"package input for {outcome}: {len(out):,} rows, {meta['n_treated_pixels']:,} treated pixels, {meta['n_clusters']} clusters, "
       f"cohorts {meta['cohorts']} -> {stem}.[parquet|csv|json]")
    return written, meta

# ====================== v20.22: MULTI-SITE RUNNER ======================
SITE_FILTER = None      # None = every row; an int or list of SWSiD_All = only those sites (set by run_sites)

# ====================== v20.58: SAMPLE INTEGRITY -- what enters the estimate, CONFIRMED (never assumed) ======================
# On the rows a model estimates on (in_analysis_sample): only the processed sub-watersheds, nothing outside their polygons, every
# (pixel, year, season) once, one ring per pixel, no pixel both treated and a control, exactly the rings / years / seasons of the design.
# Under the default rules (FRAGMENT_RULE / OVERLAP_ROWS "drop") a violation STOPS the model -- a leak is a bug, never a silent pass.
_INTEGRITY_SEEN = {}
LAST_INTEGRITY = []
_OOC_WORKER = False      # v20.58: True inside an out-of-core task (one pixel partition): the checks of the WHOLE sample run in the parent
def sample_integrity(frame, control_zones=None, label=None, verbose=True):
    import _location as _L
    d = frame
    strict_f = ACTIVE.get("fragment_rule", "drop") == "drop"; strict_o = ACTIVE.get("overlap_rows", "drop") == "drop"
    rows = []
    def add(what, ok_, detail, strict=True): rows.append({"check": what, "ok": bool(ok_), "detail": detail, "strict": bool(strict)})
    has_site = "site_id" in d.columns and not d.attrs.get("synthetic")
    S = processing_sites()[0] if has_site and location_table().get("mode") != "none" else []
    sid = pd.to_numeric(d["site_id"], errors="coerce").fillna(0).astype(int).values if "site_id" in d.columns else np.zeros(len(d), int)
    st = sorted(set(sid.tolist()))
    if has_site:
        add("only the processed sub-watersheds", (not S) or set(st) <= set(S), f"in the sample: {st} | processed: {S or 'all (no ids)'}", strict_f)
    else:                                  # a frame without sub-watershed ids (a package check's synthetic panel): no location to check
        add("only the processed sub-watersheds", True, "this frame carries no sub-watershed id (a synthetic check panel): the location rule does not apply", False)
    if "site_check" in d.columns:
        n3 = int((pd.to_numeric(d["site_check"], errors="coerce").values == 3).sum()); add("nothing outside every polygon", n3 == 0, f"{n3} rows outside", strict_f)
    keys = [k for k in ("pixel_id", "Year", "Season") if k in d.columns]
    nd = int(d.duplicated(subset=keys).sum()) if len(keys) == 3 else 0
    add("no repeated pixel-year-season", nd == 0, f"{len(d):,} rows, every (pixel, year, season) once" if nd == 0 else f"{nd:,} repeated rows", strict_o)
    if {"site_id", "pixel_id", "buff_km"} <= set(d.columns):
        nr = d.groupby(["site_id", "pixel_id"], observed=True)["buff_km"].nunique()
        add("one ring per pixel", int((nr > 1).sum()) == 0, f"{int((nr > 1).sum())} pixel(s) with more than one ring", strict_o)
    if {"treatment", "pixel_id"} <= set(d.columns):
        tp = set(d.loc[d["treatment"].values == 1, "pixel_id"].tolist()); cp = set(d.loc[d["treatment"].values == 0, "pixel_id"].tolist())
        add("no pixel both treated and a control", not (tp & cp), f"{len(tp & cp)} pixel(s) on both sides", strict_o)
    cz = tuple(control_zones) if control_zones is not None else tuple(ACTIVE["control_zones"])
    rg = sorted(int(x) for x in pd.unique(pd.to_numeric(d["buff_km"], errors="coerce").dropna())) if "buff_km" in d.columns else []
    add("the rings of the design", set(rg) <= ({0} | set(int(x) for x in cz)) and 0 in rg and any(r > 0 for r in rg), f"rings in the sample {rg} | design {[0] + sorted(int(x) for x in cz)}")
    if "Year" in d.columns and len(d):
        yr = pd.to_numeric(d["Year"], errors="coerce").values; lo_, hi_ = scenario_years()
        ok_y = (lo_ is None or yr.min() >= lo_) and (hi_ is None or yr.max() <= hi_) and not np.isin(yr, ACTIVE.get("drop_years") or []).any()
        add("the years of the design", ok_y, f"years {int(yr.min())}-{int(yr.max())} | window {lo_ or 'start'}-{hi_ or 'end'}")
    if "Season" in d.columns and len(d):
        sc = season_codes(seasons_mode(verbose=False)); ss = sorted(int(x) for x in pd.unique(d["Season"]))
        add("the seasons of the design", sc is None or set(ss) <= set(sc), f"seasons {[SEASON_LABEL.get(x, x) for x in ss]} | {seasons_mode(verbose=False)}")
    tab = pd.DataFrame(rows); tab["outcome"] = label or CURRENT_OUTCOME or ""; tab["rows"] = len(d); tab["pixels"] = int(d["pixel_id"].nunique()) if "pixel_id" in d.columns else 0
    LAST_INTEGRITY[:] = rows
    bad = tab[~tab.ok]
    if len(bad[bad.strict]):
        raise InsufficientDataError("SAMPLE INTEGRITY FAILED for " + str(label or CURRENT_OUTCOME) + " -- " +
                                    " | ".join(f"{r.check}: {r.detail}" for r in bad[bad.strict].itertuples()) + ". Nothing was estimated (a leak would bias every model).")
    if len(bad): warn("sample integrity: " + " | ".join(f"{r.check}: {r.detail}" for r in bad.itertuples()) + " -- your option keeps these rows")
    if verbose:
        ok(f"sample integrity ({label or CURRENT_OUTCOME}): {len(d):,} rows, {int(tab.pixels.iloc[0]):,} pixels | sub-watershed(s) {st} | rings {rg} | "
           + (f"years {int(pd.to_numeric(d['Year']).min())}-{int(pd.to_numeric(d['Year']).max())} | " if "Year" in d.columns and len(d) else "")
           + (f"seasons {[SEASON_LABEL.get(int(x), x) for x in sorted(pd.unique(d['Season']))]} | " if "Season" in d.columns and len(d) else "")
           + "CONFIRMED: every (pixel, year, season) once, one ring per pixel, no pixel both treated and a control, nothing outside the processed sub-watershed(s)")
    return tab

FORCE_BATCH_UNITS = None      # v20.58 (tests only): a batch size that forces the batch path of a model, to prove it gives the all-at-once answer
LAST_DESIGN_SE = {}          # v20.58: {outcome: design-based check of the estimation sample} -- the headline's design line and fallback SE
def _cache_design_se(out):
    if _OOC_WORKER: return                                      # v20.58: one pixel partition -- the parent computes it on the whole sample
    try:
        o = CURRENT_OUTCOME
        if not o or o not in out.columns or "in_analysis_sample" not in out.columns: return
        m = out["in_analysis_sample"].values == 1
        key = (CURRENT_MODEL_ID, o, int(m.sum()), scenario_tag())
        if LAST_DESIGN_SE.get(o, {}).get("_key") == key: return
        smp = out[m]
        ds = design_se(o, df=smp) or {}
        ev = _design_event_parts(o, smp)
        try:                                                  # v20.58: the design's cluster count on THIS sample (R: uniqueN(dt[[cluster_col_for(dt)]]))
            _cc = _cluster_key(smp, "subwshed_id"); _G = int(pd.Series(smp[_cc]).nunique()) if _cc in smp.columns else None
        except Exception:
            _G = None
        LAST_DESIGN_SE[o] = {**ds, "_event": ev, "_key": key, "_n_clusters": _G}
    except Exception as e:
        LAST_DESIGN_SE[CURRENT_OUTCOME] = {"se_design_unit": f"design SE failed: {type(e).__name__}: {str(e)[:80]}"}

def _sample_integrity_once(out, control_zones):
    """sample_integrity on the in_analysis_sample rows -- printed once per model x outcome x sample (build_treatment_columns runs often)."""
    if _OOC_WORKER: return None                                 # v20.58: one pixel partition -- the parent checks the whole sample
    try:
        m = out["in_analysis_sample"].values == 1
        if not m.any(): return None
        key = (CURRENT_MODEL_ID, CURRENT_OUTCOME, int(m.sum()), tuple(control_zones))
        if key in _INTEGRITY_SEEN: return _INTEGRITY_SEEN[key]
        tab = sample_integrity(out[m], control_zones, verbose=True); _INTEGRITY_SEEN[key] = tab
        return tab
    except InsufficientDataError:
        raise
    except Exception as e:
        warn(f"sample integrity check could not run ({type(e).__name__}: {str(e)[:100]})"); return None

def _count_location(acc, d, codes):
    """Add the rows with a location code > 0 to acc {(code, treated, post): n}: treated = the core ring, post = from the sub-watershed's
    first treated year (its site year when the timing gives one, else TREATMENT_YEAR) -- the groups the rule leaves out rows from."""
    m = np.asarray(codes) > 0
    if not m.any(): return acc
    bk = pd.to_numeric(d["buff_km"], errors="coerce").values[m] if "buff_km" in d.columns else np.full(int(m.sum()), -1)
    yr = pd.to_numeric(d["Year"], errors="coerce").values[m] if "Year" in d.columns else np.zeros(int(m.sum()))
    ty = float(ACTIVE.get("treatment_year") or TREATMENT_YEAR)
    sy = ACTIVE.get("site_years") or {}
    if sy and "site_id" in d.columns:
        cy = pd.to_numeric(d["site_id"], errors="coerce").values[m]
        cy = pd.Series(cy).map({int(k): float(v) for k, v in sy.items()}).fillna(ty).values
    else:
        cy = np.full(int(m.sum()), ty)
    t = pd.DataFrame({"c": np.asarray(codes)[m].astype(int), "t": bk == 0, "p": yr >= cy}).value_counts()
    for (c_, t_, p_), n_ in t.items():
        acc[(int(c_), bool(t_), bool(p_))] = acc.get((int(c_), bool(t_), bool(p_)), 0) + int(n_)
    return acc

def site_rows(df):
    """Rows of the sites selected by SITE_FILTER (all rows when it is None or the panel has no site_id)."""
    if SITE_FILTER is None or "site_id" not in df.columns: return df
    want = [int(SITE_FILTER)] if np.isscalar(SITE_FILTER) else [int(x) for x in SITE_FILTER]
    return df[pd.to_numeric(df["site_id"], errors="coerce").isin(want)]

def site_design_table(path=None, save_as=None, verbose=True):
    """v20.28: one row per sub-watershed in the panel -- name, phase and treatment year (data/sites/sites.csv),
    treated (buffer 0) and control (buffers 1-5) pixels, rows before / from the treatment year, and how its rows were
    matched to the shapefile (confirmed / corrected / assigned / outside). Tells you at a glance which sites can be
    estimated alone, which cohorts the pooled run has, and whether the site tags can be trusted."""
    import pyarrow.parquet as pq
    p = path or PREPARED_PANEL
    pf = pq.ParquetFile(p); acc = {}
    try:
        names = pf.schema_arrow.names
        cols = [c_ for c_ in ("site_id", "sws_name", "pixel_id", "buff_km", "Year", "site_check") if c_ in names]
        if "site_id" not in cols: raise InsufficientDataError("the panel has no site_id -- rebuild it with engine >= 20.22")
        for i in progress(range(pf.num_row_groups), desc="site table", unit="rg"):
            d = pf.read_row_group(i, columns=cols).to_pandas()
            for sid, g in d.groupby("site_id", sort=False):
                a = acc.setdefault(int(sid), {"name": "", "treated": set(), "control": set(), "rows_pre": 0, "rows_post": 0, "check": {}})
                if "sws_name" in g and len(g) and str(g["sws_name"].iloc[0]): a["name"] = str(g["sws_name"].iloc[0])
                bk = pd.to_numeric(g["buff_km"], errors="coerce").values
                a["treated"].update(g.loc[bk == TREAT_CORE_BUFFKM, "pixel_id"].tolist())
                a["control"].update(g.loc[np.isin(bk, [1, 2, 3, 4, 5]), "pixel_id"].tolist())
                ty = int(ACTIVE["treatment_year"])
                a["rows_pre"] += int((g["Year"] < ty).sum()); a["rows_post"] += int((g["Year"] >= ty).sum())
                if "site_check" in g:
                    for k, v in g["site_check"].value_counts().items(): a["check"][int(k)] = a["check"].get(int(k), 0) + int(v)
    finally:
        try: pf.close()
        except Exception: pass
    try:
        import _sites as _S; reg = _S.registry().set_index("SWSiD_All")
    except Exception:
        reg = pd.DataFrame()
    lab = {0: "confirmed", 1: "corrected", 2: "assigned", 3: "outside", 4: "not_checked"}
    rows = []
    for sid, a in sorted(acc.items()):
        r = {"SWSiD_All": sid, "sws_name": a["name"] or (str(reg.loc[sid, "name"]) if sid in reg.index else ""),
             "phase": int(reg.loc[sid, "phase"]) if sid in reg.index else None,
             "treatment_year": (int(reg.loc[sid, "treatment_year"]) if sid in reg.index and pd.notna(reg.loc[sid, "treatment_year"]) else int(ACTIVE["treatment_year"])),
             "treated_pixels": len(a["treated"]), "control_pixels": len(a["control"]), "rows_pre": a["rows_pre"], "rows_post": a["rows_post"]}
        tot = max(sum(a["check"].values()), 1)
        for k, v in lab.items(): r[f"share_{v}"] = round(a["check"].get(k, 0) / tot, 4)
        rows.append(r)
    out = pd.DataFrame(rows)
    if save_as: out.to_csv(save_as, index=False)
    if verbose and len(out):
        info(f"{len(out)} sub-watershed(s) in the panel; start years {sorted(out.treatment_year.unique().tolist())} "
             f"-> {out.treatment_year.nunique()} cohort(s); clusters if pooled by site: {len(out)}")
        print(out.to_string(index=False))
        thin = out[(out.treated_pixels < 50) | (out.control_pixels < 50)]
        if len(thin): warn(f"sites too thin to estimate alone (< 50 treated or control pixels): {thin.sws_name.tolist()}")
        if (out.get("share_corrected", pd.Series(0)) > 0.05).any():
            warn("some sites had > 5 % of rows re-assigned from the shapefile -- check site_tagging_report.csv")
    return out

def sites_in_panel(path=None, after_fragments=False):
    """The SWSiD_All values present in the panel (a single-site export without the column gives {0}).
    v20.57: after_fragments=True -> the sub-watersheds FRAGMENT_RULE keeps (the major data; fragments of other sub-watersheds,
    and minor sub-watersheds of the panel, are not sub-watersheds of this run). A fragment made a single-sub-watershed panel
    look pooled in v20.56 (2 sub-watersheds: site x period effects, a second cohort, years within each of 2 sub-watersheds)."""
    import pyarrow.parquet as pq
    p = path or PREPARED_PANEL
    if not os.path.exists(p): return []
    if after_fragments:                                         # v20.58: the processing set of the location rule (SUB_WATERSHEDS / SITE_FILTER)
        tab = location_table(p)
        if tab.get("mode") != "none":
            if ACTIVE.get("fragment_rule", "drop") == "drop":
                return list(processing_sites(tab)[0])
            return sorted(int(k) for k in tab["own"])
    pf = pq.ParquetFile(p)
    try:
        if "site_id" not in pf.schema_arrow.names: return [0]
        seen = set()
        for i in range(pf.num_row_groups):
            seen.update(int(x) for x in pd.unique(pf.read_row_group(i, columns=["site_id"]).to_pandas()["site_id"]))
        return sorted(seen)
    finally:
        try: pf.close()
        except Exception: pass

def run_sites(model_fn, sites=None, pooled=True, per_site=True, cluster_pooled="site", pooled_fe="site_period",
              use_site_years=True, label="model"):
    """Run ONE model (a callable that runs the notebook's estimation and returns its result) once per site and
    once pooled, the way a single-site notebook does today -- no across-model batching. Results of each site
    land under <results>/<model>/<scenario>/site_<SWSiD_All>/ (RESULTS_DIR is re-pointed for the call), the
    pooled run under .../pooled/. Failures are logged and the loop continues."""
    global SITE_FILTER
    import _sites as _S
    all_sites = sites if sites is not None else [s for s in sites_in_panel(after_fragments=True) if s != 0]   # v20.57: no fragments
    saved = dict(ACTIVE); out = []
    # v20.57: each site on the timing in force (fund / registry / fixed, from CELL 1); use_site_years=True with a FIXED timing
    # still means "each site on its registry year" (the v20.22 switch)
    _usy = {"use_site_years": True} if use_site_years and ACTIVE.get("timing", "fixed") == "fixed" else {}
    try:
        if per_site:
            for s in all_sites:
                SITE_FILTER = int(s)
                set_scenario(verbose=False, cluster="site", pooled_fe="period", **_usy)   # v20.39: the sub-watershed is the cluster (one site -> years)
                resolve_design(verbose=False)                                            # v20.57: this site's own timing and data window
                info(f"[{label}] site {s} ({_S.name(s)}): timing {ACTIVE.get('timing')}, first treated year {ACTIVE['treatment_year']}"
                     + (f" ({_fund_label(int(s))})" if ACTIVE.get("site_start", {}).get(int(s)) else ""))
                try:
                    r = model_fn(f"site_{int(s)}"); out.append({"site": int(s), "name": _S.name(s), "status": "ok", "result": r})
                except InsufficientDataError as e:
                    warn(f"[{label}] site {s}: DATA GAP -- {str(e)[:140]}"); out.append({"site": int(s), "name": _S.name(s), "status": "data_gap", "reason": str(e)[:300]})
                except Exception as e:
                    fail(f"[{label}] site {s}: {type(e).__name__}: {str(e)[:140]}"); out.append({"site": int(s), "name": _S.name(s), "status": "failed", "reason": f"{type(e).__name__}: {str(e)[:300]}"})
        if pooled and len(all_sites) > 1:
            SITE_FILTER = list(all_sites)
            set_scenario(verbose=False, cluster=cluster_pooled, pooled_fe=pooled_fe, **_usy)
            resolve_design(verbose=False)
            info(f"[{label}] POOLED {len(all_sites)} sites: cohorts {sorted(set(ACTIVE['site_years'].values())) if ACTIVE.get('use_site_years') else [ACTIVE['treatment_year']]}, "
                 f"clusters by {ACTIVE['cluster']}, FE {ACTIVE['pooled_fe']}")
            try:
                r = model_fn("pooled"); out.append({"site": "pooled", "name": f"{len(all_sites)} sites", "status": "ok", "result": r})
            except InsufficientDataError as e:
                warn(f"[{label}] pooled: DATA GAP -- {str(e)[:140]}"); out.append({"site": "pooled", "status": "data_gap", "reason": str(e)[:300]})
            except Exception as e:
                fail(f"[{label}] pooled: {type(e).__name__}: {str(e)[:140]}"); out.append({"site": "pooled", "status": "failed", "reason": f"{type(e).__name__}: {str(e)[:300]}"})
    finally:
        SITE_FILTER = None
        ACTIVE.clear(); ACTIVE.update(saved)
    tab = pd.DataFrame(out)
    try:
        p = os.path.join(RESULTS_ROOT, "SITE_RUN_LOG.csv")
        old = pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()
        pd.concat([old, tab.assign(model=label, when=_ts()).drop(columns=["result"], errors="ignore")], ignore_index=True).to_csv(p, index=False)
    except Exception:
        pass
    return tab

def _fund_label(site):
    v = ACTIVE.get("site_start", {}).get(int(site))
    return f"{ {0: 'Yearly', 1: 'Kharif', 2: 'Rabi', 3: 'Zaid'}[int(v[1])]} {int(v[0])}" if v else ""

def run_other_outcomes(model_id, first_outcome=None, outcomes=None, overwrite=False, root=None):
    """Called by the LAST cell of every model notebook: after the notebook has finished the outcome you chose in
    CELL 1, it runs ITSELF once per remaining outcome in SELECTED_OUTCOMES -- one variable after another, in this
    module only. It never recurses (run_model_notebook skips this cell) and never starts another model."""
    if OUTCOME_LOOP_STATE.get("outcome"):
        return None                      # already inside a batch: the caller is iterating
    nb = find_model_notebook(model_id, root)
    if nb is None:
        warn(f"could not locate the notebook for {model_id}; auto outcome switching skipped"); return None
    outs = [o for o in outcomes_available(outcomes) if o != first_outcome]
    if not outs:
        info("no further outcomes to run"); return None
    step(9, f"{model_id}: continuing automatically with the other {len(outs)} outcome(s): {outs}")
    rows = []
    for i, o in enumerate(outs, 1):
        info(f"--- {model_id} [{i}/{len(outs)}] {o}")
        r_ = run_model_notebook(nb, o, overwrite=overwrite); r_["scenario"] = scenario_tag(); rows.append(r_)
    df = pd.DataFrame(rows)
    log = os.path.join(RESULTS_ROOT, "OUTCOME_RUN_LOG.csv")
    df.to_csv(log, mode="a", header=not os.path.exists(log), index=False)
    ok(f"{model_id}: " + ", ".join(f"{k}={v}" for k, v in df["status"].value_counts().items()) + f" (log -> {log})")
    return df

OOC_RUN = {"note": None}   # v20.58: set while a model runs out of core -- its headline says so (engine column), cleared after the report

def report_model_outcome(model_id, outcome, result=None, results_dir_=None):
    """v17.10: say whether THIS outcome produced output, judged by the files on disk -- not by whether run_model()
    happened to return a value (several notebooks save their results and return None, which printed a misleading
    'did not produce a result' warning in v17.9 even after a clean save)."""
    d = results_dir_ or results_dir(model_id, make=False)
    _gapf = (f"{model_id}_{outcome}_DATA_GAP.csv", f"{model_id}_{outcome}_FAILED.csv")
    files = [f for f in (os.listdir(d) if os.path.isdir(d) else []) if outcome in f and f not in _gapf]
    if files:
        for _g_ in _gapf:                                      # v20.58: a gap note of an EARLIER run of this folder is stale now
            if os.path.exists(os.path.join(d, _g_)):
                try: os.remove(os.path.join(d, _g_))
                except Exception: pass
        ok(f"{model_id} x {outcome}: {len(files)} result file(s) in {d} -> {files[:4]}")
        try:
            model_headline(model_id, outcome, d)                                     # v20.58: estimate, SE, p -- and the design check
        except Exception as _e:
            warn(f"{model_id} x {outcome}: the headline could not be read ({type(_e).__name__}: {str(_e)[:120]})")
    elif result is not None:
        ok(f"{model_id} x {outcome}: finished (in-memory result; nothing written to {d})")
    else:
        warn(f"{model_id} x {outcome}: NO result file was written -- see the message above. "
             f"A documented DATA GAP is expected; a FAILED line is a real problem worth reporting.")
        if LAST_GAP.get("reason"):                          # v20.58: the reason in a file beside the results -- as R's <model>_<outcome>_DATA_GAP.csv
            try:
                os.makedirs(d, exist_ok=True)
                pd.DataFrame([{"model": model_id, "outcome": outcome, "status": LAST_GAP.get("status", "data gap"), "reason": LAST_GAP["reason"],
                               "scenario": scenario_tag(), "engine_version": ENGINE_VERSION}]).to_csv(
                    os.path.join(d, f"{model_id}_{outcome}_{'DATA_GAP' if LAST_GAP.get('status') == 'data gap' else 'FAILED'}.csv"), index=False)
            except Exception as _e:
                warn(f"the data-gap note could not be written ({type(_e).__name__}: {_e})")
    OOC_RUN["note"] = None
    return bool(files)

def collect_results(models=None, outcomes=None, out_name="ALL_RESULTS_LONG.csv"):
    import re
    """Read-only helper: gather the result CSVs already on disk into one tidy table (model, outcome, file, columns).
    It runs nothing -- use it after you have run the modules you want."""
    import glob as _g
    rows = []
    for d_ in sorted(_g.glob(os.path.join(RESULTS_ROOT, "M*"))):
        mid = os.path.basename(d_)
        for f in sorted(_g.glob(os.path.join(d_, "*.csv"))):
            try: t = pd.read_csv(f)
            except Exception: continue
            t.insert(0, "file", os.path.basename(f)); t.insert(0, "model", mid)
            if "outcome" not in t.columns:
                m = re.search(r"_([A-Za-z]+)\.csv$", os.path.basename(f)); t.insert(2, "outcome", m.group(1) if m else "")
            rows.append(t)
    if not rows: warn("no result files found"); return pd.DataFrame()
    allr = pd.concat(rows, ignore_index=True, sort=False)
    p = os.path.join(RESULTS_ROOT, out_name); allr.to_csv(p, index=False); ok(f"{len(allr):,} result rows -> {p}")
    return allr

CURRENT_ESTIMATION_COLUMNS = set()   # v20.13: the outcome + covariates the model is about to estimate on
# v20.16: exact-zero cells in an outcome or a continuous covariate are no-data in these exports and are excluded
# exactly like NaN, in every model (load_panel, the 2x2 and streaming estimators, the event study).
ZERO_AS_MISSING = True
ZERO_RULE_EXCEPT = ()                # variables where 0 is a valid value (e.g. ("Rain",)); LandUse is never numeric here
FLOORED_COVARIATES = ("Rain", "Tmax", "Tmean", "Tmin")   # v20.30: floored at 0 during preparation -> a 0 is a real value
                                                          # (dry season / the floor), never a masked cell
DESIGN_TERM_COLS = {"did_term", "did_x_cov", "did_g3", "did_high", "did_low", "high_cov", "treat_core", "treatment", "post", "pre", "fake_did",
                    "treat", "did", "control",                       # v20.59: the panel's DiD columns (the names R's panel uses)
                    "did_placebo", "did_stack", "did_naive", "frac_seasons_treated", "is_near_ring", "dose_term"}
def _is_design_term(col):
    """v20.58: a design indicator (a DiD term, a group dummy) entering a regression as a regressor: 0 is a real value there. v20.57 applied the
    exported-zero rule to it when a model passed it as a 'covariate' (M10 / M26: 87 % of the rows left, the effect unidentified)."""
    c = str(col); return c in DESIGN_TERM_COLS or c.startswith(("did_", "centred_"))   # v20.58: a CENTRED covariate's 0 is its mean
def _usable(values, col=None):
    """Finite, and (when the zero rule applies to this column) non-zero."""
    v = pd.to_numeric(pd.Series(np.asarray(values)), errors="coerce").values.astype(np.float64)
    m = np.isfinite(v)
    if ZERO_AS_MISSING and col not in ZERO_RULE_EXCEPT and not _is_categorical_col(col) and col not in FLOORED_COVARIATES and not _is_design_term(col):
        m &= (v != 0)
    return m
LAST_LOAD_INFO = {}

# ====================== v20.35: WHAT ENTERS THE ESTIMATE -- structural causes of attenuated effects ======================
EXCLUDE_GAPFILLED = True   # the exporter fills the unpublished tail of an incomplete recent window with a day-weighted blend
                           # of the observed mean and the 3-YEAR HISTORICAL mean (GapFilled = 1). In the POST period such values
                           # are partly pre-treatment history, which pulls post back toward pre and shrinks the DiD toward
                           # zero. They are left out of estimation; False keeps them (every result records which).
LOAD_SCENARIO_ROWS_ONLY = True   # rows this scenario can never use (rings outside CONTROL_ZONES, invalid ring codes) are not
                                 # loaded -- smaller frames, faster demeaning. Models that use every ring keep them:
MODELS_NEEDING_ALL_RINGS = set()   # v20.58 (YOUR RULE: the rings you set are the rings EVERY model uses): was {"M24", "M17", "M18"} --
                                   # they read rings 1-5 whatever CONTROL_ZONES said; M24's gradient now runs over YOUR rings
CLEAN_CONTROLS = True      # pooled multi-site panels: a pixel TREATED in any sub-watershed is never a control, and a pixel in
                           # several sites' rings enters once -- otherwise one pixel's value sits on both sides of the DiD
CURRENT_MODEL_ID = None    # set by results_dir(MODEL_ID) in each notebook's CELL 1
OPTIONAL_READ_COLUMNS = {"sws_name", "site_check", "latitude", "longitude", "dose_per_subwshed", "GapFilled", "Coverage", "OptTier", "post",   # v20.59: post
                         "LandUse", "LandUseDW", "District", "area_hectare", "first_treat_season",   # v20.58: a four-model panel lacks them
                         "fragment", "sws_id_export", "dose_amount_sws", "dose_intensity_per_ha",   # v20.57: fragment rule, dose
                         "first_treat_agri_year"}      # v20.57: rebuilt by build_treatment_columns from the timing in force -- never required
LAST_DESIGN_INFO = {}

def columns_for(outcome, extra=()):
    """The minimal column set a model notebook needs for one outcome variable. v20.13: also records the outcome
    and the covariates, so load_panel() can exclude rows where any of them is missing -- the ONE place every
    model's data passes through."""
    assert_is_outcome(outcome)
    cols = set(ID_FE_COLS) | {outcome} | set(extra)
    cols |= {"GapFilled", "Coverage"}                                    # v20.35: read when present, never required
    cols |= {"post"}                                                     # v20.59: the panel's post (the exports' Treat flag) -- read when present,
                                                                         #   compared with the design in effect (build_treatment_columns), never estimated on
    cols |= {"LandUse"}                          # v20.44: a DESCRIPTOR (M10's land-use group, CATE splits) -- loaded,
                                                 # never required and never a covariate unless the model asks for it
    cols |= {c for c in DEFAULT_COVARIATES if c != outcome}
    try:                                                          # v20.57: no fund workbook here -> the panel's own dose column
        if fund_tables_in_force() is None: cols |= {ACTIVE.get("dose_variable", "dose_intensity_per_ha")}
    except Exception:
        pass
    CURRENT_ESTIMATION_COLUMNS.clear()
    CURRENT_ESTIMATION_COLUMNS.update({outcome} | {c for c in DEFAULT_COVARIATES if c != outcome})
    global CURRENT_OUTCOME
    CURRENT_OUTCOME = outcome                                     # v20.24: 'auto' seasons resolves per outcome
    return sorted(cols)

NUMERIC_RESULT_KEYS = ("beta", "att", "coef", "estimate", "se", "p_value", "p_wild", "ci_low", "ci_high", "effect")

def _result_is_empty(row):
    """True when a result dict has numeric coefficient/SE fields and ALL of them are missing."""
    vals = [v for k, v in row.items() if any(str(k).lower().startswith(n) for n in NUMERIC_RESULT_KEYS)]
    def _nan(v):
        if v is None: return True
        try: return bool(np.isnan(float(v)))
        except Exception: return False
    return bool(vals) and all(_nan(v) for v in vals)

PLACEHOLDER_TOKENS = ("tbd", "todo", "placeholder", "dummy", "xxx", "n/a", "na", "null", "none", "?", "-", "--")
HARD_PLACEHOLDER_TOKENS = ("tbd", "todo", "placeholder", "dummy", "xxx")   # v20.33: left-over text, refused ANYWHERE
# v20.33: "" left out, and descriptive columns exempt. An EMPTY 'leads_dropped' means NOTHING was dropped -- the good
# case -- yet it blocked every pre-trends result file (M16 wrote nothing for any outcome).
DESCRIPTIVE_COLUMNS = ("note", "notes", "reason", "dropped", "covariates", "engine", "message", "detail", "comment",
                       "warning", "identification", "status", "seasons_used", "nonnegative_filter", "negatives_blocked")

def _placeholder_cells(out):
    """Text cells that are placeholders rather than values (case-insensitive, stripped)."""
    hits = []
    for col in out.columns:
        if out[col].dtype == object or pd.api.types.is_string_dtype(out[col]):   # pandas 3 uses a 'str' dtype
            s = out[col].astype(str).str.strip().str.lower()
            # v20.33: in a DESCRIPTIVE column "none" / "-" mean "nothing to report" and "" means the same, so only
            # left-over authoring text ("TBD") is a placeholder there. Everywhere else the full list applies.
            toks = HARD_PLACEHOLDER_TOKENS if any(k in str(col).lower() for k in DESCRIPTIVE_COLUMNS) else PLACEHOLDER_TOKENS
            bad = s.isin(toks) & ~out[col].isna() & (s != "")
            if bad.any(): hits.append(f"{col}={s[bad].iloc[0]!r}")
    return hits

def record_not_estimated(results_dir, outcome, reason, model_id=None):
    """v20.20: an outcome that could not be estimated is recorded ONCE, in NOT_ESTIMATED.csv, with its reason --
    never as a result file full of NaN. Result files hold estimates only."""
    os.makedirs(results_dir, exist_ok=True)
    p = os.path.join(results_dir, "NOT_ESTIMATED.csv")
    row = {"model": model_id or os.path.basename(os.path.dirname(results_dir)), "scenario": scenario_tag(),
           "outcome": outcome, "reason": str(reason)[:400], "recorded": _ts()}
    try:
        old = pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()
        old = old[old.get("outcome", pd.Series(dtype=str)) != outcome] if len(old) else old
        pd.concat([old, pd.DataFrame([row])], ignore_index=True).to_csv(p, index=False)
    except Exception:
        pd.DataFrame([row]).to_csv(p, index=False)
    info(f"{outcome}: not estimated -> recorded in NOT_ESTIMATED.csv ({str(reason)[:90]})")
    return p

# ====================== v20.41: THE DESIGN-BASED STANDARD ERROR, ON EVERY RESULT ======================
# Estimators differ in how they compute a standard error; several (influence functions, pixel bootstraps, HC
# formulas) treat each of ~1.8 million pixels as independent, which gives SEs of ~1e-5 whatever the design. The
# independent information of this design is the treated-minus-control GAP over time: one draw per YEAR when the
# sample holds one sub-watershed, one DiD per SUB-WATERSHED when it holds several. design_se() collapses the data to
# that level (Bertrand-Duflo-Mullainathan) and gives the SE any honest estimate must respect; save_results attaches
# it to every result that has an outcome and an SE, and warns when the model's own SE is far smaller.
_DESIGN_SE_CACHE = {}
DESIGN_SE_WARN_RATIO = 3.0

def _design_draws(w):
    """w: DataFrame site, gap, post -> [(site, did, var_pre / n_pre, var_post / n_post, n_pre, n_post)] (the per-sub-watershed DiD of gaps)."""
    out = []
    for s_, g in w[np.isfinite(w["gap"].values)].groupby("site"):
        a_, b_ = g.loc[g["post"].values == 0, "gap"].values, g.loc[g["post"].values == 1, "gap"].values
        if not len(a_) or not len(b_): continue
        sa = a_.var(ddof=1) if len(a_) > 1 else np.nan; sb = b_.var(ddof=1) if len(b_) > 1 else np.nan
        out.append((int(s_), float(b_.mean() - a_.mean()), (sa if np.isfinite(sa) else sb) / len(a_), (sb if np.isfinite(sb) else sa) / len(b_), len(a_), len(b_)))
    return out

def _design_combine(per):
    import math
    S = len(per)
    if not S: return None
    dids = np.array([p_[1] for p_ in per], float)
    if S >= MIN_SWS_CLUSTERS:
        return {"did": float(dids.mean()), "se": float(dids.std(ddof=1) / math.sqrt(S)), "df": float(S - 1), "S": S, "by": "sub-watersheds"}
    v = np.array([p_[2] + p_[3] for p_ in per], float)
    return {"did": float(dids.mean()), "se": float(math.sqrt(np.nansum(v)) / S) if np.isfinite(v).any() else np.nan,
            "df": float(sum(p_[4] + p_[5] - 2 for p_ in per)), "S": S, "by": "years"}

def _design_frame(outcome, df):
    """The rows of the design SE: the estimation sample, processed sub-watersheds only (site_id > 0), the outcome net of each unit's own
    level (the model's unit: pixel x season series, or pixel -- the within transformation of the fixed-effects models)."""
    d = df if "in_analysis_sample" in df.columns and "post" in df.columns else build_treatment_columns(df)
    d = d[(d["in_analysis_sample"] == 1)] if "in_analysis_sample" in d.columns else d
    y = pd.to_numeric(d[outcome], errors="coerce").values.astype(np.float64); ok_ = np.isfinite(y)
    site = pd.to_numeric(d["site_id"], errors="coerce").fillna(0).astype(np.int64).values if "site_id" in d.columns else np.zeros(len(d), np.int64)
    if (site[ok_] > 0).any(): ok_ &= site > 0                   # v20.58: rows without a sub-watershed are no sub-watershed
    tr = (pd.to_numeric(d["treatment"], errors="coerce").values == 1) if "treatment" in d.columns else (pd.to_numeric(d["buff_km"], errors="coerce").values == TREAT_CORE_BUFFKM)
    unit = d["unit_id"].values if "unit_id" in d.columns else d["pixel_id"].values
    t = pd.DataFrame({"site": site[ok_], "Year": pd.to_numeric(d["Year"], errors="coerce").values[ok_].astype(int),
                      "Season": pd.to_numeric(d["Season"], errors="coerce").values[ok_].astype(int) if "Season" in d.columns else 0,
                      "tr": tr[ok_], "post": (pd.to_numeric(d["post"], errors="coerce").values[ok_] == 1).astype(int), "u": unit[ok_], "y": y[ok_]})
    t["y"] = t["y"] - t.groupby("u")["y"].transform("mean")    # each unit's own level removed
    return t

def design_se(outcome, df=None, verbose=False, estimate=None):
    """v20.58: the design-based SE -- identical to R's design_se (lib/reward_design.R). Your v20.56 log printed "design SE 0.003 ... p 0.944"
    on an estimate of -0.0066: the p-value belonged to a DIFFERENT number (the DiD of the collapsed gaps, never printed), the gaps were RAW
    means (the pixels present change from year to year; a year's seasons were pooled with changing weights) and rows without a
    sub-watershed (site 0) were a second "sub-watershed". Now: the outcome net of each unit's own level, treated-minus-control gaps per
    year x season, a year's gap = the mean of its seasons' gaps, processed sub-watersheds only -- the design DiD itself, its SE, df, p,
    and the p of the MODEL's estimate (`estimate`) against that SE."""
    from scipy import stats as _st
    key = (outcome, scenario_tag() if "scenario_tag" in globals() else "", str(SITE_FILTER), _panel_identity().get("panel_mtime"), "v20.58")
    if df is None and estimate is None and key in _DESIGN_SE_CACHE:
        return _DESIGN_SE_CACHE[key]
    loaded = df is None
    if getattr(df, "_ooc", False):                          # v20.58: out of core -- the same cells, summed over the pixel partitions
        cells = df.design_cells()
    else:
        if loaded:
            df = load_panel(columns=columns_for(outcome))
        t = _design_frame(outcome, df)
        if not len(t): return None
        cells = _design_cells(t)
    return _design_se_from_cells(outcome, cells, key, loaded, verbose, estimate)

def _design_cells(t):
    """v20.58: what the design-based SE needs of its frame t: the mean of the (unit-demeaned) outcome per sub-watershed x year x season x
    group (g), the post flags per sub-watershed x year x season (pp) and the number of seasons -- the same from one frame (in memory) or
    summed over pixel partitions (out of core)."""
    g = t.groupby(["site", "Year", "Season", "tr"])["y"].mean().unstack("tr")
    pp = t.groupby(["site", "Year", "Season"])["post"].agg(["max", "min"]).reset_index().rename(columns={"max": "post", "min": "_pmin"})
    return {"g": g, "pp": pp, "n_seasons": int(t["Season"].nunique())}

def _design_se_from_cells(outcome, cells, key=None, loaded=False, verbose=False, estimate=None):
    from scipy import stats as _st
    g, pp = cells["g"], cells["pp"]
    if True not in g.columns or False not in g.columns: return None
    w = (g[True] - g[False]).rename("gap").reset_index()
    w = w.merge(pp, on=["site", "Year", "Season"], how="left"); w = w[np.isfinite(w["gap"].values)]
    wy = w.groupby(["site", "Year"]).agg(gap=("gap", "mean"), post=("post", "max"), _pmin=("_pmin", "min")).reset_index()
    wy = wy[~((wy["post"] == 1) & (wy["_pmin"] == 0))]         # a year whose seasons are partly treated is no YEAR draw
    per = _design_draws(wy); cy = _design_combine(per)
    if cy is None: return None
    pt2 = lambda x, df_: float(2 * _st.t.sf(abs(x), df_)) if np.isfinite(x) and np.isfinite(df_) and df_ > 0 else np.nan
    unit = (f"{cy['S']} sub-watersheds as the draws" if cy["by"] == "sub-watersheds" else
            (f"years as the draws: {per[0][4]} pre, {per[0][5]} post; one sub-watershed" if cy["S"] == 1 else f"years within each of {cy['S']} sub-watersheds as the draws"))
    se_ = cy["se"]
    out = {"did_design": cy["did"], "did_collapsed": cy["did"], "se_design": se_, "df_design": cy["df"], "t_design": cy["did"] / se_ if se_ and np.isfinite(se_) and se_ > 0 else np.nan,
           "p_design": pt2(cy["did"] / se_, cy["df"]) if se_ and np.isfinite(se_) and se_ > 0 else np.nan, "n_units_design": int(sum(p_[4] + p_[5] for p_ in per)),
           "n_sites_design": cy["S"], "se_design_unit": unit,
           "p_estimate_design": pt2(float(estimate) / se_, cy["df"]) if estimate is not None and np.isfinite(float(estimate)) and se_ and np.isfinite(se_) and se_ > 0 else np.nan}
    if cy["by"] == "years" and cells["n_seasons"] > 1:         # each year x season a draw (the year-level pair is the conservative one)
        c2 = _design_combine(_design_draws(w[["site", "gap", "post"]]))
        if c2 is not None:
            s2 = c2["se"]
            out.update({"did_design_period": c2["did"], "se_design_period": s2, "df_design_period": c2["df"],
                        "p_design_period": pt2(c2["did"] / s2, c2["df"]) if s2 and np.isfinite(s2) and s2 > 0 else np.nan,
                        "n_periods_design": int(len(w)), "se_design_period_unit": "each year x season a draw",
                        "p_estimate_design_period": pt2(float(estimate) / s2, c2["df"]) if estimate is not None and np.isfinite(float(estimate)) and s2 and np.isfinite(s2) and s2 > 0 else np.nan})
    if loaded and estimate is None and key is not None:
        _DESIGN_SE_CACHE[key] = out
    if verbose:
        info(f"design-based check for {outcome}: DiD of the gaps {cy['did']:+.5f}, SE {se_:.5f} ({unit}, {cy['df']:g} df), p = {out['p_design']:.3g}")
    return out

def _design_event_parts(outcome, df):
    """The pieces of the design-based SE of an event-study headline: per sub-watershed the year-to-year variance of the PRE-period gaps,
    the number of pre and post years (as R's design_se_event)."""
    if getattr(df, "_ooc", False): return list(df.design_event_parts())   # v20.58: out of core -- the same parts from the partitions' cells
    return _design_event_from_cells(_design_cells(_design_frame(outcome, df)))

def _design_event_from_cells(cells):
    g = cells["g"]
    if True not in g.columns or False not in g.columns: return []
    w = (g[True] - g[False]).rename("gap").reset_index().merge(cells["pp"][["site", "Year", "Season", "post"]], on=["site", "Year", "Season"])
    wy = w[np.isfinite(w.gap.values)].groupby(["site", "Year"]).agg(gap=("gap", "mean"), post=("post", "max")).reset_index()
    rows = []
    for s_, gg in wy.groupby("site"):
        a_ = gg.loc[gg.post == 0, "gap"].values; n1 = int((gg.post == 1).sum())
        if len(a_) > 1 and n1: rows.append((float(a_.var(ddof=1)), int(len(a_)), n1))
    return rows

def design_se_event_from(rows, estimate=None):
    from scipy import stats as _st
    if not rows: return {"se": np.nan, "df": np.nan, "p": np.nan, "how": "not identified (fewer than 2 pre-period years)"}
    S = len(rows); se_ = float(np.sqrt(sum(v * (1 + 1 / n1) for v, _, n1 in rows)) / S); df_ = float(sum(n0 - 1 for _, n0, _ in rows))
    p_ = float(2 * _st.t.sf(abs(float(estimate) / se_), df_)) if estimate is not None and np.isfinite(float(estimate)) and se_ > 0 else np.nan
    return {"se": se_, "df": df_, "p": p_, "how": f"design-based: years as the draws (the year-to-year spread of the {sum(r[1] for r in rows)} pre-period gap(s) x "
                                                   f"sqrt(1 + 1/{round(np.mean([r[2] for r in rows]))} post years){f', {S} sub-watersheds' if S > 1 else ''})"}

def design_se_event(outcome, df, estimate=None):
    """The design-based SE of an EVENT-STUDY headline (the mean of the post-period coefficients against the reference year -1): with the
    years as the draws each coefficient is a gap minus the reference year's gap, so the headline has variance s2 (1 + 1 / n_post), s2 =
    the year-to-year variance of the PRE-period gaps (as R's design_se_event)."""
    return design_se_event_from(_design_event_parts(outcome, df), estimate)

# ====================== v20.58: THE HEADLINE OF EVERY MODEL -- one line, the same in R and Python ======================
# An EFFECT has an estimate, an SE and a p-value (never NaN: a model that gives no SE of its own takes the design-based SE of the same
# sample, and says so); a TEST gives its statistic and p; a STATISTIC (Moran's I) its value, SE and p; a DIAGNOSTIC (a variance share, a
# breakdown value) its value, described. The design-based check follows on its own line: the SAME for every model on the same sample (a
# property of the data). Written as HEADLINE_<outcome>.csv next to the model's results, with SAMPLE_INTEGRITY_<outcome>.csv and
# LOCATION_RULE_<outcome>.csv. report_model_outcome() (the last line of every model notebook) reads the model's result file with
# HEADLINE_SPEC below -- no notebook computes its headline by hand.
MODEL_KIND = {"M16": "test", "M17": "statistic", "M18": "statistic", "M19": "diagnostic", "M20": "test"}   # v20.58: M34 = an effect (+ its breakdown Mbar), as R
STAT_NAME = {"M16": "pre-trend F statistic", "M17": "Moran's I", "M18": "Moran's I (the LISA table beside it)", "M19": "ICC (variance share)",
             "M20": "Cochran's Q (heterogeneity across sub-watersheds)"}
NOT_ATT = {"M06": "the effect per unit of dose", "M10": "the triple difference (land use 2 minus the rest; truth 0 without heterogeneity)",
           "M15": "the mean placebo effect (truth 0)", "M24": "the spillover into the nearest control ring (truth 0)"}   # v20.58: M26 = the effect at the mean (as R)
# model: (result file stem, how the headline is read, estimate column, SE column, p column, what the SE is)
#   how: col = the one row | post_mean = mean over event time >= 0 (SE: design-based event SE) | rows_mean = mean of the rows |
#        tau50 = the row of quantile 0.5 | min_ring = the nearest ring's row | placebo = mean placebo, rms SE, Bonferroni p | chained = last cumulative
HEADLINE_SPEC = {
    "M01": ("canonical_twfe", "col", "beta", "se", "p_t_G1", "fit"),
    "M02": ("event_study_headline", "col", "estimate", "se", "p_value", ""),   # v20.58: event_headline() -- the post mean, its SE and p (as R)
    "M03": ("doubly_robust", "col", "ATT", "se", None, ""),   # v20.58: DRDID's improved DR DiD (ported); its influence-function SE (se_how in the file)
    "M04": ("changes_in_changes", "col", "ATT_CiC", "se", None, ""),   # v20.58: qte::CiC (ported) + its panel bootstrap SE (se_how in the file)
    "M05": ("cs_overall", "col", "ATT_simple", "se", None, ""),   # v20.58: the simple aggregation (as R's did::aggte(type = "simple"))
    "M06": ("dose_response", "col", "beta_per_unit_dose", "se", "p_t_G1", "fit"),
    "M08": ("instrumented_did", "col", "beta_2sls", None, None, ""),
    "M09": ("sun_abraham_headline", "col", "estimate", "se", "p_value", ""),   # v20.58: sun_abraham_fixest (as R's m09_sunab)
    "M10": ("ddd", "col", "DDD", "se", "p_t_G1", "fit"),
    "M11": ("synthetic_did", "col", "ATT", "se", None, ""),   # v20.58 (second pass): synthdid's placebo SE with R's draws
    "M12": ("chained_did", "col", "beta", "se", "p_value", ""),   # v20.58: chained_fd_did (R's first-difference estimator)
    "M13": ("switcher_overall", "col", "estimate", "se", None, ""),   # v20.58: DIDmultiplegtDYN's average total effect and its SE (engine = the package, ported)
    "M14": ("psm_did", "col", "PSM_DID", "se", "p_value", ""),   # v20.58: psm_did() -- matched as MatchIt, the two-way FE with its SE (as R)
    "M15": ("placebo_timing", "placebo", "placebo_beta", "placebo_se", "p_value", ""),   # v20.58: the mean placebo's own SE (se_how in the file)
    "M16": ("pretrends_ftest", "col", "f_stat", None, "p_value", ""),   # v20.58: the test USED (the file's method: the joint Wald F of the leads when
                                                                       #   well conditioned, else the design-based linear pre-trend) -- as R
    "M17": ("morans_i", "col", "morans_I", "se_moran", "p_value", "the variance of Moran's I under randomisation (spdep's formula); p two-sided"),
    "M18": ("lisa_global", "col", "morans_I", "se_moran", "p_value", "the variance of Moran's I under randomisation (spdep's formula); p two-sided"),
    "M19": ("variance_decomposition", "col", "ICC", None, None, ""),
    "M20": ("treatment_heterogeneity", "col", "Q", None, "p_value", "Cochran's Q against chi-square with (sub-watersheds - 1) df; pooled_effect / I2 / tau2 beside it"),
    "M21": ("aggregation_bias", "col", "dose_corrected", "se_dose_corrected", "p_dose_corrected", "fit"),
    "M22": ("goodman_bacon_summary", "col", "estimate", "se", "p_value", ""),   # v20.58: the exact decomposition + the SE of the two-way FE it adds up to (as R)
    "M23": ("wild_bootstrap", "col", "beta", "se_cluster_robust", "p_value_wild_bootstrap", "cluster-robust (CR1); p: the wild cluster bootstrap (Webb weights)"),
    "M24": ("spillover_gradient", "min_ring", "gradient_effect", "se", "p_value", "fit"),
    "M25": ("permutation", "col", "beta_actual", "se_permutation", "p_value_permutation", "the standard deviation of the permuted estimates; p: randomisation inference"),
    "M26": ("treatment_x_Rain", "col", "beta_at_mean", "se", "p_value", "fit"),   # v20.58: the effect at the covariate's mean (as R)
    "M27": ("bjs", "col", "ATT_bjs", "se", None, ""),   # v20.58 (second pass): didimputation's conservative SE (ported)
    "M28": ("gardner", "col", "ATT_gardner", None, None, "event"),   # v20.58: did2s's event-time mean (as R); SE: the design-based event SE
    "M29": ("exposure_headline", "col", "estimate", "se", "p_value", ""),   # v20.58: fixest i(exposure) (as R): the mean effect, delta-method SE
    "M30": ("cohort_group_att", "col", "estimate", "se", None, ""),   # v20.58 (second pass): did's analytical SE (ported) when R takes it   # v20.58: CS group aggregation (as R's did::aggte(type = "group"))
    "M31": ("stacked_did", "col", "ATT_stacked", "se", "p_value", ""),   # v20.58: R's stacked design on the series-year frame (se_how in the file)
    "M32": ("etwfe", "col", "ATT_etwfe", "se", "p_value", ""),   # v20.58 (second pass): etwfe's cohort effects + emfx's delta-method SE (as R)
    "M33": ("entropy_balanced", "col", "ATT_entropy_balanced", "se", "p_value", ""),   # v20.58: entropy_balanced_twfe (as R: WeightIt + fixest)
    "M34": ("honest_did", "col", "estimate", "se", "p_value", ""),   # v20.58: the effect assessed; breakdown_Mbar beside it (as R)
    "M35": ("quantile_did", "tau50", "QTE", "se", "p_value", ""),   # v20.58: quantreg::rq "fn" (ported); cluster-robust kernel SE with sub-watershed clusters
    "M36": ("fect_ife", "col", "att_avg", "se", None, ""),               # v20.58: fect ported (R's route): one fit per cohort x season, its bootstrap SE
    "M37": ("fect_mc", "col", "att_avg", "se", None, ""),
    "M38": ("gsynth", "col", "att_avg", "se", None, ""),
    "M39": ("causal_forest_cate", "col", "ATT", "se", "p_value", ""),   # v20.58: R's long difference; grf's doubly robust ATT (as R's M39 / M43)
    "M40": ("dml", "col", "theta_dml", "se", "p_value", ""),             # v20.58: se_how / p_how written by the notebook (the series, not pixels)
    "M41": ("meta_learners", "rows_mean", "mean_CATE", None, None, ""),
    "M42": ("dr_learner", "col", "ATE_dr", "se", "p_value", ""),   # v20.58: the SE of the AIPW scores (se_how in the file; as R's grf AIPW)
    "M43": ("causal_forest_att", "col", "ATT", "se", "p_value", ""),
    "M44": ("bart_style", "col", "ATT_bart_style", None, None, ""),     # v20.58: the effect on the treated (bartCause's estimand)
    "M45": ("lasso_sc", "col", "ATT_lasso_sc", None, None, "")}
NO_OWN_SE = {"M11": "synthdid's placebo SE was not identified here (it needs more control series than treated series)", "M12": "the chained first-difference SE is not identified when the treatment switches inside one cluster (one sub-watershed: the years are the clusters)", "M13": "DIDmultiplegtDYN's SE was not identified on this sample (no variation among the switchers' or the controls' changes)",
             "M14": "the matched DiD engine gives no SE", "M22": "the Goodman-Bacon decomposition is a weighting, not an estimator with an SE",
             "M27": "the imputation SE (didimputation's formula) was not computable on this sample", "M28": "the two-stage engine gives no SE", "M29": "the exposure engine gives no SE",
             "M30": "the influence-function SE of the group aggregation (did's aggte) was not computable on this sample", "M32": "the extended TWFE engine's cluster-robust SE was not computable (fewer than 2 clusters)", "M33": "the entropy-balancing engine gives no SE",
             "M36": "fect's bootstrap SE was not computable for every cohort x season fit", "M37": "fect's bootstrap SE was not computable for every cohort x season fit",
             "M38": "the bootstrap SE was not computable for every cohort x season fit",   # v20.58: the ported fect / gsynth give their SE (were: no SE)
             "M39": "the causal forest's ATT SE was not computable", "M41": "S / T / X learners give no SE", "M42": "the DR-learner's AIPW scores were not available",
             "M43": "the causal forest's ATT SE was not computable", "M44": "the BART-style stand-in gives no posterior SE", "M45": "the elastic-net synthetic control gives no SE",
             "M08": "the 2SLS engine gives no SE",
             "M35": "the years are the clusters: the quantile regression's cluster-robust SE rests on the post years only (the did scores of the pre years are 0) -- not valid",
             "M28": "did2s's corrected covariance is not ported (the R route gives it)", "M04": "the bootstrap failed"}

def _fmt_p(v):
    if v is None or not np.isfinite(v): return "not identified"
    if v == 0: return "< 1e-300 (below machine precision)"
    return f"{v:.3g}"

def _headline_read(model_id, outcome, rd):
    """(estimate, se, p, row dict, file) from the model's result file, as HEADLINE_SPEC says."""
    spec = HEADLINE_SPEC.get(model_id)
    if spec is None or not os.path.isdir(rd): return None
    stem, how, ec, sc, pc, _ = spec
    import glob as _g
    fs = sorted(_g.glob(os.path.join(rd, f"{stem}_{outcome}.csv")))
    if not fs: return None
    t = pd.read_csv(fs[0]); f = os.path.basename(fs[0])
    num = lambda c, r=None: (float(pd.to_numeric(pd.Series([(t if r is None else r)[c].iloc[0] if r is None else r[c]]), errors="coerce").iloc[0])
                             if c and c in (t.columns if r is None else r.index) else np.nan)
    if ec not in t.columns: return (np.nan, np.nan, np.nan, {}, f)
    v = pd.to_numeric(t[ec], errors="coerce")
    if how == "col": return (float(v.iloc[0]), num(sc), num(pc), t.iloc[0].to_dict(), f)
    if how == "post_mean":
        et = pd.to_numeric(t[next(c for c in ("event_time", "rel_time") if c in t.columns)], errors="coerce")
        m = (et >= 0) & v.notna(); return (float(v[m].mean()), np.nan, np.nan, {"post_event_times": int(m.sum())}, f)
    if how == "chained":
        c = pd.to_numeric(t.get("cumulative"), errors="coerce") if "cumulative" in t.columns else pd.Series(dtype=float)
        return (float(c.dropna().iloc[-1]) if len(c.dropna()) else np.nan, np.nan, np.nan, {}, f)
    if how == "weighted":
        w = pd.to_numeric(t.get("approx_weight_by_n_obs", pd.Series([1.0] * len(t))), errors="coerce")
        return (float(np.nansum(v * w) / np.nansum(w)), np.nan, np.nan, {}, f)
    if how in ("mean", "rows_mean"): return (float(v.mean()), np.nan, np.nan, {"rows": int(v.notna().sum())}, f)
    if how == "post_rows":
        et = pd.to_numeric(t["event_time"], errors="coerce") if "event_time" in t.columns else pd.Series(np.zeros(len(t)))
        return (float(v[et >= 0].mean()), np.nan, np.nan, {"rows": int((et >= 0).sum())}, f)
    if how == "tau50":
        q = pd.to_numeric(t["quantile"], errors="coerce"); r = t.loc[(q - 0.5).abs().idxmin()]
        return (float(pd.to_numeric(pd.Series([r[ec]]), errors="coerce").iloc[0]), num(sc, r), num(pc, r), r.to_dict(), f)
    if how == "min_ring":
        r = t.loc[pd.to_numeric(t["ring_km"], errors="coerce").idxmin()]
        return (float(r[ec]), num(sc, r), num(pc, r), r.to_dict(), f)
    if how == "placebo":                                  # v20.58: the mean placebo effect with ITS OWN SE and p (run_placebo_timing_test)
        b = v.dropna(); k = int(len(b))
        if {"mean_placebo_beta", "mean_placebo_se", "mean_placebo_p"} <= set(t.columns):
            r0 = t.iloc[0]
            return (num("mean_placebo_beta", r0), num("mean_placebo_se", r0), num("mean_placebo_p", r0),
                    {"placebo_years": k, "p_any_placebo_bonferroni": num("p_any_placebo_bonferroni", r0),
                     "se_how": str(r0.get("mean_se_how", "")), "p_how": str(r0.get("mean_p_how", ""))}, f)
        raise InsufficientDataError(f"{f} has no mean-placebo SE (written before v20.58) -- re-run M15")
    return None

def headline(model_id, outcome, estimate=None, se=None, p=None, kind=None, se_how="", p_how="", se_note="", engine="", results_dir_=None, extra=None):
    """The model's headline: printed, and written as HEADLINE_<outcome>.csv (with SAMPLE_INTEGRITY / LOCATION_RULE of the same run)."""
    from scipy import stats as _st
    kind = kind or MODEL_KIND.get(model_id, "effect")
    fnum = lambda x: float(x) if x is not None and np.isfinite(float(x)) else np.nan
    est, se_, pv = fnum(estimate), fnum(se), fnum(p)
    ds = {k: v for k, v in (LAST_DESIGN_SE.get(outcome) or {}).items() if not k.startswith("_")}
    ev = (LAST_DESIGN_SE.get(outcome) or {}).get("_event")
    not_att = model_id in NOT_ATT
    df_d = ds.get("df_design", np.nan); sd_d = ds.get("se_design", np.nan)
    if kind == "effect" and not not_att and np.isfinite(est) and np.isfinite(sd_d) and sd_d > 0 and np.isfinite(df_d):
        ds["p_estimate_design"] = float(2 * _st.t.sf(abs(est / sd_d), df_d))
    else:
        ds["p_estimate_design"] = np.nan
    # v20.58: G = the design's clusters on this sample (as R's save_result: uniqueN(dt[[cluster_col_for(dt)]])) -- the last fit's count could
    # belong to another fit of the session
    G = (LAST_DESIGN_SE.get(outcome) or {}).get("_n_clusters") or LAST_FIT_INFO.get("n_clusters")
    if kind == "effect" and se_how == "event" and ev is not None and not np.isfinite(se_):   # an event-study headline without its own SE
        e_ = design_se_event_from(ev, est); se_, pv, se_how, p_how = e_["se"], e_["p"], e_["how"], f"t with {e_['df']:g} df"
    if se_how == "event": se_how = ""
    if kind == "effect" and not not_att and not np.isfinite(se_) and np.isfinite(sd_d):   # never a NaN SE on an effect
        se_ = float(sd_d); pv = float(ds["p_estimate_design"])
        se_how = f"design-based ({ds.get('se_design_unit')}): {se_note or NO_OWN_SE.get(model_id, 'this model gives no SE of its own')}"
        p_how = f"t with {df_d:g} df against the design-based SE"
    if np.isfinite(est) and np.isfinite(se_) and se_ > 0 and not np.isfinite(pv) and kind in ("effect", "statistic"):
        dfp = max(1, int(G) - 1) if G else (df_d if np.isfinite(df_d) else None)
        if dfp: pv = float(2 * _st.t.sf(abs(est / se_), dfp)); p_how = p_how or f"t with {dfp:g} df from the estimate and its SE"
        else: pv = float(2 * _st.norm.sf(abs(est / se_))); p_how = p_how or "normal, from the estimate and its SE"
    row = {"model": model_id, "outcome": outcome, "kind": kind, "estimate": est, "se": se_, "p_value": pv, "se_how": se_how, "p_how": p_how,
           "se_note": se_note or ({"diagnostic": "a descriptive quantity: it has no sampling SE", "test": "a test statistic: read its p-value"}.get(kind, "")),
           "engine": (f"{engine} -- {OOC_RUN['note']}" if OOC_RUN.get("note") else engine), "scenario": scenario_tag(), "engine_version": ENGINE_VERSION, "what": NOT_ATT.get(model_id, "the treatment effect" if kind == "effect" else STAT_NAME.get(model_id, "")),
           **{k: ds.get(k, np.nan) for k in ("did_design", "se_design", "df_design", "p_design", "p_estimate_design", "did_design_period", "se_design_period",
                                             "df_design_period", "p_design_period")}, "se_design_unit": ds.get("se_design_unit", ""),
           "fragment_rule": ACTIVE.get("fragment_rule"), "overlap_rows": ACTIVE.get("overlap_rows"), "sub_watersheds": str(ACTIVE.get("sub_watersheds")),
           **(extra or {})}
    rd = results_dir_ or results_dir(model_id)
    try:
        os.makedirs(rd, exist_ok=True)
        pd.DataFrame([row]).to_csv(os.path.join(rd, f"HEADLINE_{outcome}.csv"), index=False)
        if LAST_INTEGRITY: pd.DataFrame(LAST_INTEGRITY).assign(outcome=outcome).to_csv(os.path.join(rd, f"SAMPLE_INTEGRITY_{outcome}.csv"), index=False)
        _lr = LAST_DESIGN_INFO.get("location_rows") or LAST_LOAD_INFO.get("location_rows") or {}
        import _location as _L
        pd.DataFrame([{"code": int(k.split("|")[0]), "treated": bool(int(k.split("|")[1])), "post": bool(int(k.split("|")[2])), "rows": int(v),
                       "text": _L.TEXT[int(k.split("|")[0])], "left_out": int(k.split("|")[0]) in location_drop_codes()}
                      for k, v in sorted(_lr.items(), key=lambda kv: tuple(int(x) for x in str(kv[0]).split("|")))]   # v20.58: one order (code, treated, post)
                     or [{"code": 0, "treated": np.nan, "post": np.nan, "rows": 0, "text": "no row of another location in this panel", "left_out": False}]).to_csv(
            os.path.join(rd, f"LOCATION_RULE_{outcome}.csv"), index=False)
    except Exception as e:
        warn(f"headline file not written ({type(e).__name__}: {str(e)[:80]})")
    if kind == "effect":
        txt = f"estimate {est:.5g} | SE {_fmt_p(se_)}, p {_fmt_p(pv)} (SE: {se_how}" + (f"; p: {p_how}" if p_how else "") + ")"
    elif kind == "test":
        txt = f"{STAT_NAME.get(model_id, 'test statistic')} {est:.4g}, p {_fmt_p(pv)}" + (f" ({se_how})" if se_how else "")
    elif kind == "statistic":
        txt = f"{STAT_NAME.get(model_id, 'statistic')} {est:.4g} | SE {_fmt_p(se_)}, p {_fmt_p(pv)}" + (f" ({se_how})" if se_how else "")
    else:
        txt = f"{STAT_NAME.get(model_id, 'value')} {est:.4g} ({row['se_note']})"
    ok(f"{model_id} x {outcome}: {txt}" + (f" -- {NOT_ATT[model_id]}" if not_att else ""))
    if kind == "effect" and np.isfinite(ds.get("se_design", np.nan)):
        per = (f" | each year x season a draw: {ds['did_design_period']:.5g}, SE {_fmt_p(ds['se_design_period'])} ({ds['df_design_period']:g} df), p {_fmt_p(ds['p_design_period'])}"
               if np.isfinite(ds.get("se_design_period", np.nan)) else "")
        info(f"{model_id} x {outcome} -- design-based check on this sample (the same for every model, it is a property of the data): DiD of the "
             f"treated-minus-control gaps {ds['did_design']:.5g}, SE {_fmt_p(ds['se_design'])} ({ds['se_design_unit']}, {ds['df_design']:g} df), p {_fmt_p(ds['p_design'])}{per}"
             + (f" ({NOT_ATT[model_id]}: not the treatment effect, so not tested against it)" if not_att else f"; this estimate against that SE: p {_fmt_p(ds['p_estimate_design'])}"))
    if kind == "effect" and not np.isfinite(se_):
        warn(f"{model_id} x {outcome}: NO standard error could be computed ({se_note or NO_OWN_SE.get(model_id, 'the model gave none and the design-based SE is not identified')})")
    if kind in ("effect", "statistic", "test") and not np.isfinite(est):
        warn(f"{model_id} x {outcome}: the headline value is missing in the result file -- see the messages above")
    return row

# ====================== v20.58: OUTCOMES THAT ARE THE SAME VARIABLE (said, never silent) -- as R's outcome_identities_R ======================
# Your v20.56 run gave LSWI exactly NDMI's result and WSSI exactly minus ESI's. That is not a copy: in your exports LSWI and NDMI are the same
# index, and WSSI = 1 - ESI. Every pair of outcomes that is an exact linear function of the other on the rows they share (|r| > 0.999999) is
# found once per panel (OUTCOME_IDENTITIES.json next to it; OUTCOME_IDENTITIES.csv in the results) and announced at every run of either one.
_IDENT_CACHE = {}
def outcome_identities(outcomes=None, verbose=True):
    import pyarrow.parquet as pq
    key = json.dumps(_panel_identity(), sort_keys=True, default=str)
    if key in _IDENT_CACHE: return _IDENT_CACHE[key]
    cf = os.path.join(os.path.dirname(PREPARED_PANEL), "OUTCOME_IDENTITIES.json")
    try:
        j = json.load(open(cf, encoding="utf-8")) if os.path.exists(cf) else None
        if j and j.get("panel") == key:
            t = pd.DataFrame(j["tab"], columns=["a", "b", "r", "slope", "intercept", "n"]); _IDENT_CACHE[key] = t; return t
    except Exception:
        pass
    rows = []
    try:
        _pfi = pq.ParquetFile(PREPARED_PANEL); names = _pfi.schema_arrow.names; _nr = _pfi.metadata.num_rows
        oc = [o for o in (outcomes or SELECTED_OUTCOMES) if o in names]
        try:
            import _hardware as _Hi, _outofcore as _Oi
            _stream = len(oc) >= 2 and (bool(_Oi.forced()) or not _Hi.fits(float(_nr) * len(oc) * 8.0 * 3.0))
        except Exception:
            _stream = False
        if _stream:                                   # v20.58: beyond 98 % of the RAM -- the same test, row group by row group (exact sums)
            rows = _identities_streamed(PREPARED_PANEL, oc)
            raise StopIteration
        x = pq.read_table(PREPARED_PANEL, columns=oc).to_pandas() if len(oc) >= 2 else pd.DataFrame()
        oc = [o for o in oc if np.isfinite(pd.to_numeric(x[o], errors="coerce").values).sum() > 2]
        first = x.head(1_000_000)
        for i in range(len(oc)):
            for j2 in range(i + 1, len(oc)):
                a = pd.to_numeric(first[oc[i]], errors="coerce").values.astype(np.float64); b = pd.to_numeric(first[oc[j2]], errors="coerce").values.astype(np.float64)
                m = np.isfinite(a) & np.isfinite(b)
                if m.sum() < 3 or np.std(a[m]) == 0 or np.std(b[m]) == 0 or abs(np.corrcoef(a[m], b[m])[0, 1]) <= 0.99999: continue   # screened on the first rows
                a = pd.to_numeric(x[oc[i]], errors="coerce").values.astype(np.float64); b = pd.to_numeric(x[oc[j2]], errors="coerce").values.astype(np.float64)
                m = np.isfinite(a) & np.isfinite(b); sa, sb = np.std(a[m]), np.std(b[m])                                             # confirmed on all
                if sa == 0 or sb == 0: continue
                r = float(np.corrcoef(a[m], b[m])[0, 1])
                if abs(r) > 0.999999:
                    sl = r * sb / sa; rows.append((oc[i], oc[j2], r, float(sl), float(np.mean(b[m]) - sl * np.mean(a[m])), int(m.sum())))
    except StopIteration:
        pass
    except Exception as e:
        warn(f"outcome identities not checked ({type(e).__name__}: {str(e)[:80]})")
    t = pd.DataFrame(rows, columns=["a", "b", "r", "slope", "intercept", "n"])
    try:
        json.dump({"panel": key, "tab": rows}, open(cf, "w", encoding="utf-8"))
        if len(t): os.makedirs(RESULTS_ROOT, exist_ok=True); t.to_csv(os.path.join(RESULTS_ROOT, "OUTCOME_IDENTITIES.csv"), index=False)
    except Exception:
        pass
    if verbose:
        for r_ in t.itertuples(): info(_identity_text(r_))
    _IDENT_CACHE[key] = t
    return t

def _identities_streamed(path, oc, first_n=1_000_000):
    """v20.58: outcome_identities beyond 98 % of the RAM: the pairs screened on the first rows (as in memory), confirmed on EVERY row by exact
    running sums (shifted by the first rows' means: no cancellation), one row group at a time."""
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    try:
        parts, got = [], 0
        for i in range(pf.num_row_groups):
            if got >= first_n: break
            d = pf.read_row_group(i, columns=oc).to_pandas(); parts.append(d); got += len(d)
        first = (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=oc)).head(first_n)
        fin = {o: 0 for o in oc}
        for i in range(pf.num_row_groups):
            d = pf.read_row_group(i, columns=oc)
            for o in oc: fin[o] += int(np.isfinite(pd.to_numeric(d[o].to_pandas(), errors="coerce").values.astype(np.float64)).sum())
        oc = [o for o in oc if fin[o] > 2]
        cand = []
        for i in range(len(oc)):
            for j2 in range(i + 1, len(oc)):
                a = pd.to_numeric(first[oc[i]], errors="coerce").values.astype(np.float64); b = pd.to_numeric(first[oc[j2]], errors="coerce").values.astype(np.float64)
                m = np.isfinite(a) & np.isfinite(b)
                if m.sum() < 3 or np.std(a[m]) == 0 or np.std(b[m]) == 0 or abs(np.corrcoef(a[m], b[m])[0, 1]) <= 0.99999: continue
                cand.append((oc[i], oc[j2], float(a[m].mean()), float(b[m].mean())))
        if not cand: return []
        acc = {(a_, b_): np.zeros(6) for a_, b_, _, _ in cand}
        need = sorted(set([c[0] for c in cand] + [c[1] for c in cand]))
        for i in range(pf.num_row_groups):
            d = pf.read_row_group(i, columns=need).to_pandas()
            for a_, b_, ma, mb in cand:
                a = pd.to_numeric(d[a_], errors="coerce").values.astype(np.float64) - ma; b = pd.to_numeric(d[b_], errors="coerce").values.astype(np.float64) - mb
                m = np.isfinite(a) & np.isfinite(b); a, b = a[m], b[m]
                acc[(a_, b_)] += (len(a), a.sum(), b.sum(), (a * a).sum(), (b * b).sum(), (a * b).sum())
    finally:
        try: pf.close()
        except Exception: pass
    rows = []
    for a_, b_, ma, mb in cand:
        n, sa1, sb1, saa, sbb, sab = acc[(a_, b_)]
        if n < 3: continue
        mua, mub = sa1 / n, sb1 / n
        va, vb, cv = saa / n - mua * mua, sbb / n - mub * mub, sab / n - mua * mub
        if va <= 0 or vb <= 0: continue
        sa, sb = np.sqrt(va), np.sqrt(vb); r = float(cv / (sa * sb))
        if abs(r) > 0.999999:
            sl = r * sb / sa; rows.append((a_, b_, r, float(sl), float((mub + mb) - sl * (mua + ma)), int(n)))
    return rows

def _identity_text(r_):
    same = abs(r_.slope - 1) < 1e-6 and abs(r_.intercept) < 1e-9
    return (f"OUTCOME IDENTITY: {r_.b} = {r_.intercept:.4g} {r_.slope:+.4g} x {r_.a} on all {int(r_.n):,} rows they share (r = {r_.r:.7f}) -- "
            + ("the SAME variable: identical results are expected" if same else
               f"a linear transform: the estimate of {r_.b} = {r_.slope:.4g} x that of {r_.a} (identical p-values)"))

def announce_identities(outcome):
    """At a model run: the identities the outcome takes part in (so an identical or mirrored result is read as what it is)."""
    try:
        t = outcome_identities(verbose=False)
        for r_ in t[(t.a == outcome) | (t.b == outcome)].itertuples(): info(_identity_text(r_))
    except Exception:
        pass

EVENT_MODELS = {"M02", "M09", "M28"}     # headline = the mean of the post-period event-time effects (SE: design-based event SE); v20.58: M05 = the
                                         # SIMPLE aggregation (as R's did::aggte)
# v20.58: columns a model adds to its headline row beside estimate / SE / p -- the same names as R's HEADLINE_EXTRA (reward_design.R)
HEADLINE_EXTRA = ("p_any_placebo_bonferroni", "n_placebo_years", "breakdown_Mbar", "breakdown_how", "ring", "reference_ring",
                  "Q_df", "pooled_effect", "pooled_se", "I2", "tau2", "n_sub_watersheds", "did_rest", "third_dim",
                  "beta_interaction", "se_interaction", "p_interaction", "covariate")
def _headline_extras(src):
    """The HEADLINE_EXTRA values of a result row (dict or one-row DataFrame / file)."""
    if src is None: return {}
    if isinstance(src, pd.DataFrame): src = src.iloc[0].to_dict() if len(src) else {}
    out = {}
    for k in HEADLINE_EXTRA:
        v = src.get(k) if isinstance(src, dict) else None
        if v is None or (isinstance(v, float) and not np.isfinite(v) and k not in ("breakdown_Mbar",)): continue
        if isinstance(v, str) and v in ("", "nan", "None"): continue
        out[k] = v
    return out
def _package_headline(model_id, outcome, rd):
    """(estimate, se, p, se_how, p_how, label) of <model>_PACKAGE_<outcome>.csv -- the PRIMARY result of a verified pre-built package
    (your rule: packages first) -- or None when no package computed this model."""
    f = os.path.join(rd, f"{model_id}_PACKAGE_{outcome}.csv")
    if not os.path.exists(f): return None
    # v20.58: a package result written by an EARLIER run of this model x outcome (the same scenario folder) is never this run's headline --
    # found by validate_model_parity.py --engine: with PREBUILT_MODE "off", or a package that did not compute this time, the headline read the
    # old <model>_PACKAGE_<outcome>.csv as the primary result. Such files are moved to _superseded/ (kept, never read as a result).
    t0_ = PACKAGE_RUN_START.get((model_id, str(outcome)))
    if t0_ is not None and os.path.getmtime(f) < t0_ - 2.0:
        try:
            sd_ = os.path.join(rd, "_superseded"); os.makedirs(sd_, exist_ok=True)
            for f_ in [f] + [os.path.join(rd, f"{model_id}_PACKAGE_{k_}_{outcome}.csv") for k_ in ("table", "meta_learners", "cate_by_covariate_quartile")]:
                if os.path.isfile(f_) and os.path.getmtime(f_) < t0_ - 2.0:   # exact names only (never another outcome's files)
                    os.replace(f_, os.path.join(sd_, os.path.basename(f_)))
            warn(f"{model_id} x {outcome}: the package result in this folder is from an EARLIER run (no package computed it this time: "
                 f"{(LAST_ENGINE.get(model_id) or {}).get('reason', 'see above')}) -- moved to _superseded/; the headline is this run's engine result")
        except Exception as e_:
            warn(f"{model_id} x {outcome}: an earlier run's package result could not be moved aside ({e_}) -- it is NOT used as this run's headline")
        return None
    t = pd.read_csv(f)
    if not len(t): return None
    label = str(t["engine"].iloc[0]) if "engine" in t.columns else "pre-built package"
    num = lambda c, r=0: float(pd.to_numeric(pd.Series([t[c].iloc[r]]), errors="coerce").iloc[0]) if c in t.columns else np.nan
    txt = lambda c: (str(t[c].iloc[0]) if c in t.columns and str(t[c].iloc[0]) not in ("nan", "None", "") else "")
    if model_id == "M18": return None                                   # the LISA table: the global I is the engine's lisa_global file
    if model_id == "M34" and "estimate" not in t.columns:              # v20.58: a pre-v20.58 grid-only file has no headline (re-run M34)
        return None
    if len(t) > 1:
        rc = next((c for c in ("relative_period", "event_time", "rel_time") if c in t.columns), None)
        ec = next((c for c in ("effect", "beta", "estimate", "att", "ATT") if c in t.columns), None)
        if rc and ec:                                                   # an event study: the mean over event time >= 0
            et = pd.to_numeric(t[rc], errors="coerce"); v = pd.to_numeric(t[ec], errors="coerce")
            return (float(v[(et >= 0) & v.notna()].mean()), np.nan, np.nan, "event", "", label + " (the mean of the post-period event-time effects)")
        if {"estimate", "weight"} <= set(t.columns):                    # Goodman-Bacon: the weights add up to the two-way FE
            v = pd.to_numeric(t["estimate"], errors="coerce"); w = pd.to_numeric(t["weight"], errors="coerce")
            se_b, p_b = num("headline_se"), num("headline_p")           # v20.58: the SE of the two-way FE the decomposition adds up to (as R)
            return (float(np.nansum(v * w) / np.nansum(w)), se_b, p_b, txt("se_how"), "t with G - 1 df (the clusters - 1)" if np.isfinite(p_b) else "",
                    label + " (the weighted 2 x 2 comparisons)")
        return None
    ec = next((c for c in ("estimate", "overall_att", "att", "att_per_unit_dose", "beta", "ate", "theta_dml", "morans_I", "moran_I", "ICC", "att_avg", "pooled")
               if c in t.columns and np.isfinite(num(c))), None)
    if ec is None: return None
    se_ = next((num(c) for c in ("se", "se_moran", "overall_se", "se_att") if c in t.columns and np.isfinite(num(c))), np.nan)
    pv = next((num(c) for c in ("p_value", "p_rand_two_sided", "p_ri") if c in t.columns and np.isfinite(num(c))), np.nan)
    p_how = "randomisation inference" if "p_ri" in t.columns and not np.isfinite(num("p_value")) else txt("p_how")
    # v20.58: a missing description is never replaced by a generic "its own SE" when there is no SE (a diagnostic: the ICC)
    return (num(ec), se_, pv, txt("se_how") or ("event" if model_id in EVENT_MODELS else (f"{label}: its own SE" if np.isfinite(se_) else "")), p_how, label)

def model_headline(model_id, outcome, results_dir_=None):
    """The headline of this model x outcome: the PRIMARY result -- a verified pre-built package when one computed it (your rule: packages
    first), else the engine -- with the engine's number beside it as the cross-check. Called by report_model_outcome."""
    rd = results_dir_ or results_dir(model_id, make=False)
    announce_identities(outcome)                                   # v20.58: LSWI = NDMI, WSSI = 1 - ESI in your exports -- said at every run
    r = _headline_read(model_id, outcome, rd)
    pk = _package_headline(model_id, outcome, rd)
    if r is None and pk is None: return None
    spec = HEADLINE_SPEC.get(model_id, ("", "", "", None, None, "")); how_se = spec[5]
    extra = {}
    if r is not None:
        est_e, se_e, pv_e, row, f = r
        if how_se == "fit":
            cu = row.get("cluster_used") or LAST_CLUSTER_USED.get("value"); G = row.get("n_clusters")
            how_se = f"engine two-way FE ({ACTIVE.get('unit_fe', 'pixel')} and year x season effects), cluster-robust (CR1)" + (f", clustered by {cu} ({int(G)} clusters)" if cu and G and np.isfinite(float(G)) else "")
            if G and np.isfinite(float(G)): LAST_FIT_INFO["n_clusters"] = int(G)
        p_how = ""
        if spec[4] == "p_t_G1" and np.isfinite(pv_e): p_how = f"t with {int(row.get('n_clusters')) - 1} df (the clusters - 1)" if row.get("n_clusters") else "t with G - 1 df"
        if not how_se and isinstance(row, dict) and str(row.get("se_how") or "") not in ("", "nan", "None"): how_se = str(row["se_how"])   # v20.58: the
        if not how_se and MODEL_KIND.get(model_id) == "test" and isinstance(row, dict) and str(row.get("method") or "") not in ("", "nan", "None"):
            how_se = str(row["method"])                                                                                   # (M16: the test used)
        if not p_how and isinstance(row, dict) and str(row.get("p_how") or "") not in ("", "nan", "None"): p_how = str(row["p_how"])      # file's own words
        le = LAST_ENGINE.get(model_id); le = le.get("engine") if isinstance(le, dict) else le
        eng = str(row.get("engine") if isinstance(row.get("engine"), str) and row.get("engine") else "engine")
        extra.update({"engine_estimate": est_e, "engine_se": se_e, "engine_file": f})
    if pk is not None:
        est, se_, pv, s_how, p_how_p, label = pk
        if np.isfinite(est):
            extra.update({"primary": "pre-built package", "package": label})
            try:                                                                  # v20.58: e.g. M34's breakdown Mbar, M20's pooled effect
                extra.update(_headline_extras(pd.read_csv(os.path.join(rd, f"{model_id}_PACKAGE_{outcome}.csv"))))
            except Exception:
                pass
            row_ = headline(model_id, outcome, estimate=est, se=se_, p=pv, se_how=s_how, p_how=p_how_p, engine=label, results_dir_=rd, extra=extra)
            if r is not None and np.isfinite(est_e):
                d_ = est - est_e; tol = max(2.0 * (row_["se"] if np.isfinite(row_["se"]) else 0.0), 0.005 * max(1.0, abs(est_e)), 1e-9)
                (info if abs(d_) <= tol else warn)(f"{model_id} x {outcome} -- cross-check: the engine ({f}) gives {est_e:.5g}; the package {est:.5g} "
                                                   f"(difference {d_:+.3g}{'' if abs(d_) <= tol else ' -- LARGER than the uncertainty: read both, see the engine file'})")
            return row_
    if r is None: return None
    extra.update({"primary": "engine"}); extra.update(_headline_extras(r[3] if isinstance(r[3], dict) else None))
    return headline(model_id, outcome, estimate=est_e, se=se_e, p=pv_e, se_how=how_se, p_how=p_how, engine=f"{eng} ({f})", results_dir_=rd, extra=extra)

def _attach_design_se(res):
    """v20.41: add the design-based SE to a result dict; warn when the model's own SE is far smaller."""
    try:                                                   # v20.46: every result says which engine and data rules made it
        res = {**res, "engine_version": ENGINE_VERSION, "data_rules": DATA_RULES_VERSION}
    except Exception:
        pass
    try:                                                   # v20.45: an SE of ~0 is never a valid result
        _se = res.get("se", res.get("SE")); _b = next((res[k] for k in ("beta", "att", "ATT", "estimate", "theta_dml") if k in res and res[k] is not None), None)
        if _se is not None and np.isfinite(float(_se)) and (float(_se) <= 1e-9 or (_b is not None and np.isfinite(float(_b))
                                                                                    and abs(float(_b)) > 0 and float(_se) < 1e-7 * abs(float(_b)))):
            res = {**res, "se_invalid": True,
                   "se_invalid_why": "SE ~ 0: no variation left to estimate from (fill / constant values, or a single cluster) -- NOT a result"}
            warn(f"{res.get('outcome')}: SE = {float(_se):.2e} -- no variation left (fill values, or one cluster). This is NOT a result; "
                 f"see OUTCOME_SCREEN.md and the design-based SE")
    except Exception:
        pass
    try:
        o = res.get("outcome"); se = res.get("se", res.get("SE"))
        if not o or se is None or not np.isfinite(float(se)) or "se_design" in res:
            return res
        # v20.58: the design-based check of THIS model's estimation sample (cached by build_treatment_columns); the panel is reloaded only
        # when the model never built one
        ds = {k: v for k, v in (LAST_DESIGN_SE.get(str(o)) or {}).items() if not k.startswith("_")} or design_se(str(o))
        if not ds or not np.isfinite(ds.get("se_design", np.nan)):
            return res
        res = {**res, **ds}
        ratio = ds["se_design"] / float(se) if float(se) > 0 else np.inf
        res["se_ratio_design_to_model"] = ratio
        if ratio > DESIGN_SE_WARN_RATIO:
            res["se_warning"] = (f"the model's SE is {ratio:,.0f}x smaller than the design-based SE -- it treats pixels (or "
                                 f"pseudo-units) as independent; report se_design / p_design")
            warn(f"{o}: model SE {float(se):.2e} is {ratio:,.0f}x smaller than the design-based SE {ds['se_design']:.2e} "
                 f"({ds['se_design_unit']}) -- report p_design = {ds['p_design']:.3f}")
    except Exception as _e:
        pass
    return res

# ====================== v20.45: THE DESIGN, CHOSEN FROM THE DATA -- NEVER FROM THE EFFECT ======================
# Which years and which control rings enter is decided by facts about the DATA, not by what makes the treatment effect
# biggest (that would be specification searching). The rules: (1) years whose export differs -- both groups jump
# together, or the treated pixels lose their history -- are left out: a pre-period starts after the last such break,
# a post-period ends before the first; (2) years the outcome screen marks as fill are not data; (3) an inner ring
# that moves WITH the core after implementation, relative to the farthest ring, is contaminated by spillover and is
# not a control (ring-vs-ring only; the core's own effect is never looked at); (4) seasons enter when they have
# coverage in every chosen year. DESIGN_MODE = "recommended" in P00_Settings applies it; "manual" keeps your settings.
def recommend_design(outcome="NDVI", treatment_year=None, write=True, verbose=True):
    import pyarrow.parquet as _pq
    T = int(treatment_year or ACTIVE.get("treatment_year") or 2022)
    pf = _pq.ParquetFile(PREPARED_PANEL); names = pf.schema_arrow.names
    if outcome not in names: return None
    acc, pix = {}, {}
    _ft = location_table(PREPARED_PANEL)                      # v20.58: the design is chosen on the rows the run estimates --
    _xc = [c_ for c_ in LOCATION_COLUMNS if c_ in names and c_ not in ("pixel_id", "buff_km", "Year", "Season")] if _ft.get("mode") != "none" else []   # the location rule
    _S_rec = processing_sites(_ft)[0] if _ft.get("mode") != "none" else None
    if SITE_FILTER is not None and "site_id" in names and "site_id" not in _xc: _xc.append("site_id")   # (and SITE_FILTER)
    if "site_id" in names and "site_id" not in _xc: _xc.append("site_id")
    # v20.57: and without the control rows of pixels TREATED in another sub-watershed (OVERLAP_ROWS = "drop"): in a pooled panel a
    # neighbour's treated core inside a ring moved that ring with the treatment and the spillover test dropped clean inner rings
    _tr_px = set(); _n_st = set()
    if ACTIVE.get("overlap_rows", "drop") == "drop":
        for i in range(pf.num_row_groups):
            d = pf.read_row_group(i, columns=["pixel_id", "buff_km"] + [x for x in ("Year", "Season") if x in names] + _xc).to_pandas()
            if _ft.get("mode") != "none": d = d[location_mask(d, _ft, _S_rec, pooled=False)[0]]
            d = site_rows(d)
            if "site_id" in d.columns: _n_st.update(int(x) for x in pd.unique(d["site_id"]) if int(x) > 0)
            _tr_px.update(d.loc[pd.to_numeric(d["buff_km"], errors="coerce").values == 0, "pixel_id"].tolist())
        if len(_n_st) < 2: _tr_px = set()
    for i in range(pf.num_row_groups):
        d = pf.read_row_group(i, columns=[x for x in ("pixel_id", "Year", "Season", "buff_km", outcome) if x in names] + _xc).to_pandas()
        if _xc:
            if _ft.get("mode") != "none":
                _kf, _ = location_mask(d, _ft, _S_rec, pooled=False); d = d[_kf]
            d = site_rows(d)
            if not len(d): continue
        if _tr_px:
            d = d[~((pd.to_numeric(d["buff_km"], errors="coerce").values > 0) & d["pixel_id"].isin(_tr_px).values)]
            if not len(d): continue
        d["_ring"] = pd.to_numeric(d["buff_km"], errors="coerce").fillna(-1).astype(int)
        core = d[d._ring == 0]                          # v20.55: the pixels PRESENT in the core per (Year, Season) -- presence of the
        for (yy, ss), gg in core.groupby(["Year", "Season"]):   # pixel, not of a finite outcome (a cloudy year is not a lost history);
            pix.setdefault((int(yy), int(ss)), set()).update(gg.pixel_id.values.tolist())   # the annual composite is chosen below over
        v = pd.to_numeric(d[outcome], errors="coerce"); f = np.isfinite(v.values); d = d[f].assign(_v=v[f].astype("float64"))   # the WHOLE file
        if not len(d): continue                         # (was: Season.min() of each row group -- the linkage depended on the parquet layout)
        for k, gg in d.groupby(["Year", "Season", "_ring"]):
            a = acc.setdefault(k, [0, 0.0, 0.0]); a[0] += len(gg); a[1] += float(gg._v.sum()); a[2] += float((gg._v ** 2).sum())
    if not acc: return None
    g = pd.DataFrame([{"Year": int(k[0]), "Season": int(k[1]), "ring": int(k[2]), "n": a[0], "mean": a[1] / a[0],
                       "sd": np.sqrt(max(0.0, a[2] / a[0] - (a[1] / a[0]) ** 2))} for k, a in acc.items()])
    s0 = g.Season.min(); ann = g[g.Season == s0]
    pix = {y: v for (y, ss), v in pix.items() if ss == s0}
    rings = sorted(int(r) for r in ann.ring.unique() if r > 0); far = max(rings) if rings else None
    yrs = sorted(ann.Year.unique())
    # (2) fill years on the annual rows
    tot = ann.groupby("Year").agg(n=("n", "sum")); sdv = ann.groupby("Year")[["sd", "n"]].apply(lambda t: np.average(t["sd"], weights=t["n"]))
    fill = [int(y) for y in yrs if sdv.get(y, 1) <= 1e-7 or tot.loc[y, "n"] < SCREEN_MIN_COVERAGE * tot.n.median()]
    # (1) export breaks: the core loses its pixels' history (linkage), or both groups jump together AND the spread across
    # pixels changes with them (a re-scaled export) AND the new level persists into the next year. v20.55: a common jump
    # alone -- a drought or a wet year moves the core and the rings together and reverts -- is a COMMON SHOCK: the year x
    # season fixed effects absorb it, so it is reported and no year is removed. Until v20.54 any common jump > 3x the
    # median year-to-year change ended the post window; on ordinary weather variation that cut the post period short.
    tm = ann[ann.ring == 0].set_index("Year")["mean"]; cm = ann[ann.ring > 0].groupby("Year")[["mean", "n"]].apply(lambda t: np.average(t["mean"], weights=t["n"]))
    ts = ann[ann.ring == 0].set_index("Year")["sd"]; cs = ann[ann.ring > 0].groupby("Year")[["sd", "n"]].apply(lambda t: np.average(t["sd"], weights=t["n"]))
    breaks, shocks = [], []
    dt, dc = tm.diff().dropna(), cm.diff().dropna()
    for y in dt.index:
        rt, rc = dt.drop(y).abs().median(), dc.drop(y, errors="ignore").abs().median()   # v20.58: a year the rings lack (every ring row of it
                                                                                          # left out by the location rule) no longer stops the design
        if y in dc.index and np.sign(dt[y]) == np.sign(dc[y]) and abs(dt[y]) > 3 * rt and abs(dc[y]) > 3 * rc:
            prev = max([z for z in tm.index if z < y], default=None); nxt = min([z for z in tm.index if z > y], default=None)
            r_t = ts[y] / ts[prev] if prev is not None and ts.get(prev, 0) > 0 else 1.0
            r_c = cs[y] / cs[prev] if prev is not None and cs.get(prev, 0) > 0 else 1.0
            rescaled = (r_t > 1.5 and r_c > 1.5) or (r_t < 1 / 1.5 and r_c < 1 / 1.5)
            persists = True if nxt is None else all(
                (np.sign(m[nxt] - m[y]) == np.sign(dm) or abs(m[nxt] - m[y]) < 0.5 * abs(dm)) for m, dm in ((tm, dt[y]), (cm, dc[y])) if nxt in m.index)
            (breaks if (rescaled and persists) else shocks).append(int(y))
    ref = pix.get(T - 1, set())
    link = {y: (len(pix[y] & ref) / len(pix[y]) if pix.get(y) else np.nan) for y in yrs}
    breaks += [int(y) for y in yrs if y >= T and np.isfinite(link.get(y, np.nan)) and link[y] < 0.9 and int(y) not in breaks]
    valid = [int(y) for y in yrs if y not in fill]
    pre_break = max([b for b in breaks if b < T], default=None)
    pre = [y for y in valid if y < T and (pre_break is None or y >= pre_break)]
    post_break = min([b for b in breaks if b >= T], default=None)
    post = [y for y in valid if y >= T and (post_break is None or y < post_break)]
    # (3) spillover: does an inner ring move with the core, relative to the farthest ring? (ring vs ring only)
    contaminated = []
    if far is not None and len(pre) >= 2 and post:
        fr = ann[ann.ring == far].set_index("Year")["mean"]
        for r_ in rings[:-1]:
            rr = ann[ann.ring == r_].set_index("Year")["mean"]; gap = (rr - fr).dropna()
            a_, b_ = gap.reindex(pre).dropna(), gap.reindex(post).dropna()
            if len(a_) >= 2 and len(b_) >= 1:
                did = b_.mean() - a_.mean(); se = np.sqrt(a_.var(ddof=1) / len(a_) + (b_.var(ddof=1) / len(b_) if len(b_) > 1 else a_.var(ddof=1)))
                if se > 0 and abs(did / se) > 2.0 and r_ <= 2: contaminated.append(int(r_))
    ctrl = [r for r in rings if r > (max(contaminated) if contaminated else 0)]
    if len(ctrl) < 2: ctrl = rings                         # keep at least two control rings
    # (4) seasons with coverage in every chosen year
    win = pre + post; seas = "yearly"
    sn = g[(g.Season != s0) & g.Year.isin(win)].groupby(["Season", "Year"]).n.sum().unstack("Year")
    if len(sn) and sn.reindex(columns=win).notna().all(axis=1).all() and (sn.reindex(columns=win).min(axis=1) >= 0.5 * tot.reindex(win).n.min()).all():
        seas = "all"
    rec = {"control_zones": f"{min(ctrl)}-{max(ctrl)}" if ctrl else "1-5", "pre_years": len(pre) or None, "post_years": len(post) or None,
           "seasons": seas, "pre_window": pre, "post_window": post, "breaks": sorted(set(breaks)), "common_shocks": sorted(set(shocks)), "fill_years": fill,
           "contaminated_rings": contaminated, "linkage": {int(k): round(float(v), 3) for k, v in link.items() if np.isfinite(v)}}
    if write:
        os.makedirs(RESULTS_ROOT, exist_ok=True)
        md = ["# Design chosen from the data (never from the effect)", "",
              f"Evidence outcome: {outcome}; implementation year {T}.", "",
              f"- **Pre-period:** {pre} -- " + (f"starts after the export break in {pre_break}" if pre_break else "no export break before implementation"),
              f"- **Post-period:** {post} -- " + (f"ends before the export break in {post_break} (that year differs: the pixels lose their history, or both groups jump and re-scale for good)" if post_break else "no export break after implementation"),
              f"- **Common shocks:** {sorted(set(shocks)) or 'none'} -- years in which the core and the rings move together (weather, not an export break): "
              f"the year x season fixed effects absorb them, no year is removed",
              f"- **Fill years (not data):** {fill or 'none'}",
              "- **SD across pixels on the annual rows, by year (the evidence of the fill years; a fill value has SD 0):** "   # v20.59
              + ", ".join(f"{int(y)}: {float(sdv.get(y, float('nan'))):.3g}" for y in yrs),
              f"- **Control rings:** {ctrl} -- " + (f"rings {contaminated} move with the core relative to ring {far} (spillover) and are left out" if contaminated else "no inner ring moves with the core"),
              f"- **Seasons:** {seas}", f"- **Share of core pixels with a history in {T - 1}, by year:** {rec['linkage']}", "",
              "The core's own effect is never used to choose any of this."]
        open(os.path.join(RESULTS_ROOT, "DESIGN_RECOMMENDATION.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    if verbose:
        info(f"design from the data: pre {pre}, post {post}, control rings {ctrl}, seasons {seas}"
             + (f"; export breaks {sorted(set(breaks))}" if breaks else "") + (f"; common shocks (kept) {sorted(set(shocks))}" if shocks else "")
             + (f"; fill years {fill} (SD across pixels on the annual rows: " + ", ".join(f"{int(y)} {float(sdv.get(y, float('nan'))):.3g}" for y in yrs) + ")" if fill else "")   # v20.59: the evidence
             + " -> DESIGN_RECOMMENDATION.md")
    return rec

def audit_results(root=None, write=True, verbose=True):
    """v20.45: every saved result checked -> RESULTS_AUDIT.csv / .md: SE ~ 0 (not a result), a model SE far below the
    design-based SE, effects that are ~0 against their design SE, and the outcomes the screen removed years from."""
    root = root or RESULTS_ROOT; rows = []
    for dp, _, fs in os.walk(root):
        for f in fs:
            if not f.endswith(".csv") or f.startswith(("RESULTS_AUDIT", "OUTCOME_SCREEN", "MODEL_READINESS", "PREBUILT_READINESS")): continue
            p = os.path.join(dp, f)
            try:
                d = pd.read_csv(p, nrows=3)
            except Exception:
                continue
            bcol = next((k for k in ("beta", "att", "ATT", "estimate", "theta_dml", "overall_att") if k in d.columns), None)
            if bcol is None or "se" not in d.columns or len(d) != 1: continue
            r = d.iloc[0]; b = pd.to_numeric(pd.Series([r[bcol]]), errors="coerce").iloc[0]; s = pd.to_numeric(pd.Series([r["se"]]), errors="coerce").iloc[0]
            sd = pd.to_numeric(pd.Series([r.get("se_design", np.nan)]), errors="coerce").iloc[0]
            m = re.search(r"(M\d\d)", p)
            flags = []
            if np.isfinite(s) and s <= 1e-9: flags.append("SE~0 (not a result)")
            if np.isfinite(sd) and np.isfinite(s) and s > 0 and sd / s > 3: flags.append(f"model SE {sd / s:,.0f}x below the design SE")
            if np.isfinite(b) and np.isfinite(sd) and sd > 0 and abs(b) < 0.5 * sd: flags.append("effect indistinguishable from 0 (|b| < 0.5 design SE)")
            if str(r.get("outcome", "")) in SCREEN_REPORT and SCREEN_REPORT.get(str(r.get("outcome"))): flags.append("fill years removed")
            if "_cov" not in p.replace(root, ""):         # v20.46: a folder without a covariate tag predates v20.46 -- it may hold
                flags.append("old folder (no covariate tag): may be a pre-v20.44 result with LandUse as a number -- re-run, then delete it")
            rows.append({"model": m.group(1) if m else "", "outcome": r.get("outcome", ""), "file": os.path.relpath(p, root), "estimate": b, "se": s,
                         "se_design": sd, "p_design": r.get("p_design", np.nan), "cluster_used": r.get("cluster_used", ""),
                         "engine": r.get("engine", ""), "flags": "; ".join(flags) or "ok"})
    out = pd.DataFrame(rows)
    if write and len(out):
        out.to_csv(os.path.join(root, "RESULTS_AUDIT.csv"), index=False)
        n0 = int(out.flags.str.contains("SE~0").sum())
        md = ["# Results audit", "", f"{len(out)} results; {n0} with an SE of ~0 (NOT results); "
              f"{int(out.flags.str.contains('below the design').sum())} with a model SE far below the design-based SE (read p_design).", "",
              "| model | outcome | estimate | SE | design SE | p (design) | flags |", "|---|---|---|---|---|---|---|"]
        md += [f"| {r.model} | {r.outcome} | {r.estimate:.3g} | {r.se:.2g} | {r.se_design:.2g} | {r.p_design} | {r.flags} |" for r in out.itertuples()]
        open(os.path.join(root, "RESULTS_AUDIT.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
        if verbose: info(f"results audit: {len(out)} results, {n0} with SE ~ 0 -> RESULTS_AUDIT.md")
    return out

def save_results(df_or_dict, results_dir, filename):
    """v20.32: every result records whether negative values were blocked, so no table can be read out of context."""
    """Write a result file. v20.20 -- NO PLACEHOLDERS: a row whose estimates are all NaN, or any cell holding a
    placeholder token (TBD, N/A, dummy, ...), is REFUSED with InsufficientDataError -- the notebook's cell_guard
    reports it as a data gap and the outcome goes to NOT_ESTIMATED.csv. Result files therefore contain only
    numbers that were actually estimated; an empty file or a status-only row is no longer possible."""
    os.makedirs(results_dir, exist_ok=True)
    if isinstance(df_or_dict, dict) and str(filename).startswith("canonical_twfe_") and (LAST_ANALYSIS.get("frame") is not None or LAST_ANALYSIS.get("ooc") is not None):
        _o = str(df_or_dict.get("outcome") or LAST_ANALYSIS["outcome"])       # v20.36: WHY the effect is this size,
        try:                                                                  # measured on the rows that entered it
            _fr = LAST_ANALYSIS.get("frame"); _oc = LAST_ANALYSIS.get("ooc")  # v20.58: out of core -- the partitions' pieces, the same finals
            _S, _yt = diagnose_effect_size(_o, df=_fr, beta=df_or_dict.get("beta"), se=df_or_dict.get("se"),
                                           n_clusters=df_or_dict.get("n_clusters"), save=False, verbose=True,
                                           parts=_oc["effect"] if _oc is not None else None)
            _rs = _repeat_final(_oc["repeat"]) if _oc is not None else repeat_shares(_fr, _o)
            _bl, _ = baseline_means(_o, df=_fr, out_dir=results_dir, parts=_oc["baseline"] if _oc is not None else None)
            pd.DataFrame([{**_S, **_rs}]).to_csv(os.path.join(results_dir, f"effect_size_diagnostics_{_o}.csv"), index=False)
            if _yt is not None and len(_yt): _yt.to_csv(os.path.join(results_dir, f"effect_size_diagnostics_{_o}_yearly.csv"), index=False)
            _worst = max([x for x in _rs.values() if np.isfinite(x)] or [0.0])
            if _worst > 0.20:
                warn(f"{_o}: {_worst:.0%} of consecutive-year values repeat EXACTLY in at least one group / period "
                     f"({', '.join(f'{k[13:]} {x:.0%}' for k, x in _rs.items() if np.isfinite(x))}). Real indices practically "
                     f"never do: those years carry no information and pull the estimate toward 0 with a tiny SE. Fix the export.")
            _keep = {k: v for k, v in {**_bl, **_rs}.items()}
            _keep.update({k: _S[k] for k in _S if k in ("raw_did_means", "mde_80pct", "treated_units_frozen_pre",
                                                          "treated_post_rows_with_pre_history", "control_post_rows_with_pre_history")})
            df_or_dict = {**df_or_dict, **{k: v for k, v in _keep.items() if k not in df_or_dict}}
        except Exception as _e:
            warn(f"effect diagnostics skipped ({type(_e).__name__}: {str(_e)[:100]})")
        finally:
            LAST_ANALYSIS["frame"] = None; LAST_ANALYSIS["ooc"] = None
    _ro = (df_or_dict.get("outcome") if isinstance(df_or_dict, dict) else (str(df_or_dict["outcome"].iloc[0]) if isinstance(df_or_dict, pd.DataFrame) and "outcome" in df_or_dict.columns and len(df_or_dict) else None))
    if LAST_DESIGN_COUNTS.get("table") is not None and (_ro is None or str(_ro) == str(LAST_DESIGN_COUNTS.get("outcome"))):   # v20.36 / v20.58: the
        try:                                                                   # pixel counts of THIS result's outcome only
            LAST_DESIGN_COUNTS["table"].to_csv(os.path.join(results_dir, f"design_counts_{LAST_DESIGN_COUNTS['outcome']}.csv"), index=False)
        except Exception:
            pass
    if isinstance(df_or_dict, dict):
        df_or_dict = _attach_design_se(df_or_dict)                        # v20.41: the honest SE travels with every result
    elif isinstance(df_or_dict, pd.DataFrame) and len(df_or_dict) == 1 and {"outcome", "se"} <= set(df_or_dict.columns):
        _r = _attach_design_se(df_or_dict.iloc[0].to_dict())
        df_or_dict = pd.DataFrame([_r])
    if isinstance(df_or_dict, dict) and LAST_CLUSTER_USED.get("value") and "cluster_used" not in df_or_dict:
        df_or_dict = {**df_or_dict, "cluster_used": LAST_CLUSTER_USED["value"]}   # v20.38
    if isinstance(df_or_dict, dict) and LAST_FIT_INFO:                    # v20.12: n_obs etc. travel with the estimate
        # v20.58: ONLY with the estimate they belong to. Until v20.57 the diagnostics of the LAST two-way FE fit of the session were added to
        # every later result -- a Moran's I row carried the p_t_G1 / n_clusters of an earlier DiD (your M17 / M27 / M32 files).
        _b = LAST_FIT_INFO.get("_beta")
        _hit = [k for k, v in df_or_dict.items() if _b is not None and isinstance(v, (int, float, np.floating)) and not isinstance(v, bool)
                and np.isfinite(float(v)) and float(v) == _b]
        if _hit:
            df_or_dict = {**df_or_dict, **{k: v for k, v in LAST_FIT_INFO.items() if k not in df_or_dict and k != "_beta"}, "fit_info_for": _hit[0]}
            df_or_dict.setdefault("status", "ok")
    out = pd.DataFrame([df_or_dict]) if isinstance(df_or_dict, dict) else df_or_dict
    if isinstance(out, pd.DataFrame) and len(out) and "seasons_used" not in out.columns:       # v20.24
        try:
            out = out.copy(); out["seasons_used"] = seasons_mode(verbose=False)
        except Exception:
            pass
    if isinstance(out, pd.DataFrame) and len(out) and "negatives_blocked" not in out.columns:      # v20.32
        _sync_negative_switch()                                                                        # v20.33
        out = out.copy(); out["negatives_blocked"] = (NONNEGATIVE_MODE if NONNEGATIVE_ESTIMATION else "no")
    if isinstance(out, pd.DataFrame) and len(out) and "gapfilled_rows_excluded" not in out.columns:        # v20.35
        out = out.copy()
        out["gapfilled_rows_excluded"] = int(LAST_LOAD_INFO.get("gapfilled_rows_excluded", 0)) if EXCLUDE_GAPFILLED else "kept"
        out["contaminated_controls_excluded"] = int(LAST_DESIGN_INFO.get("contaminated_control_rows", 0))
    if not isinstance(out, pd.DataFrame) or len(out) == 0:
        raise InsufficientDataError(f"{filename}: nothing to write -- the estimator returned no rows")
    num = out.select_dtypes("number")
    est_cols = [c_ for c_ in num.columns if any(c_.lower().startswith(k) for k in
                ("beta", "att", "coef", "estimate", "effect", "f_stat", "p_value", "breakdown", "moran", "icc", "q_stat", "i2", "cate", "tau",
                 "qte"))]                                                       # v20.58: a quantile effect table (M35: QTE, its SE NaN with year clusters)
    if est_cols and num[est_cols].isna().all().all():
        outcome = str(out["outcome"].iloc[0]) if "outcome" in out.columns else re.sub(r"^.*_([A-Za-z0-9]+)\.csv$", r"\1", filename)
        reason = str(out["reason"].iloc[0]) if "reason" in out.columns and pd.notna(out["reason"].iloc[0]) else \
                 "every estimate is NaN -- the outcome is not identified on this sample (see the coverage lines above)"
        record_not_estimated(results_dir, outcome, reason)
        raise InsufficientDataError(f"{filename} NOT written: {reason}")
    ph = _placeholder_cells(out)
    if ph:
        raise InsufficientDataError(f"{filename} NOT written: placeholder value(s) in the result ({', '.join(ph[:4])}) -- "
                                    f"a result file must hold estimated values only")
    if num.shape[1] and num.isna().all().all():
        raise InsufficientDataError(f"{filename} NOT written: every numeric column is empty")
    p = os.path.join(results_dir, filename)
    out.to_csv(p, index=False)
    ok(f"saved -> {p}")
    return p


# ===== CRITICAL SHARED BUILDERS (were missing in the first build; caught by the
# end-to-end notebook test rather than assumed -- see README 'How this was verified') =====

# ====================== v20: RUN-TIME SCENARIO (control rings + treatment timing) ======================
# Two choices are made in CELL 1 of whichever model you run, and EVERY panel column that depends on them is
# rebuilt from buff_km and Year for that run:
#     control ring(s): "1", "1-2", "1-3", "1-4", "1-5", or any explicit set like (1, 3, 5)
#     treatment year : shift the intervention earlier (2022) or later (2024); post = Year >= treatment year
# Rebuilt columns: treatment, control, pre, post, did_term, in_analysis_sample, event_time, period_index
# (plus the aliases treat_core / control_zone_selected / pre_period / post_period).
# Results are written to a per-scenario sub-folder, so scenarios never overwrite each other and can be compared.
ACTIVE = {"control_zones": tuple(DEFAULT_CONTROL_ZONES), "treatment_year": TREATMENT_YEAR,
          "post_cutoff": POST_CUTOFF, "exclude_transition_year": EXCLUDE_TRANSITION_YEAR,
          # v20.2 -- how many YEARS enter the estimation. None = every year present in the panel.
          "pre_years": None, "post_years": None, "year_min": None, "year_max": None,
          # v20.3: staggered models take their cohorts from the panel's first_treat_agri_year (P05, fund file).
          # cohort_offset shifts EVERY cohort by N years, so "shift the timing" also works for those designs.
          "cohort_offset": 0,
          # v20.22: MULTI-SITE. "site_years": per-site treatment years {SWSiD_All: year} (from data/sites/sites.csv when
          # use_site_years=True) -> post / did_term / event_time and first_treat_agri_year become site-specific, which
          # gives the staggered estimators their cohorts. "cluster": "site" (default) | "site" (cluster on SWSiD_All:
          # 20 clusters when pooled). "pooled_fe": "period" (Year x Season) | "site_period" (site x Year x Season, absorbs
          # site-specific shocks in a pooled run).
          "site_years": {}, "use_site_years": False, "cluster": "site", "pooled_fe": "period",
          # v20.57: TREATMENT TIMING. "timing": "fixed" (treatment_year for every sub-watershed) | "registry" (data/sites/sites.csv
          # years) | "fund" (your fund workbook: each sub-watershed's first treated SEASON -- see _fund.py). "site_start":
          # {SWSiD_All: [first treated year, its Season code]} -- per row, the cohort is the first Year that row's own series
          # (pixel x season) is treated, so a Rabi start treats Rabi of that year and every season of the next.
          "timing": "fixed", "site_start": {},
          # v20.57: EVERY OPTION OF THE DESIGN IS SET AT THE MODEL STAGE (CELL 1) and resolved when the model runs -- the panel P00
          # built is never rebuilt for it. "design_mode": "recommended" (an option set to "data" is chosen from the data) |
          # "manual" ("data" = every ring / every year). "data_keys": which options are "data". The *_setting keys keep what you set
          # (resolve_design writes the values in force into treatment_year / post_cutoff / site_years / site_start / control_zones ...).
          "design_mode": "recommended", "data_keys": [], "treatment_year_setting": TREATMENT_YEAR, "post_cutoff_setting": None,
          "seasons_setting": "all", "site_years_setting": None, "site_start_setting": None, "drop_years": [],
          # v20.57: YOUR RULE -- the major sub-watershed data are processed, smaller fragments of other sub-watersheds are dropped
          # ("drop"; "keep" keeps them). A sub-watershed with fewer kept rows than fragment_min_share x the largest one is a fragment.
          "fragment_rule": "drop", "fragment_min_share": 0.05, "sub_watersheds": "data",   # v20.58: the processing set (location rule)
          # v20.57: the fund workbook -> timing (TREATMENT_TIMING = "fund") and the dose of every timing (_fund.py)
          "dose_variable": "dose_intensity_per_ha", "fund_start_rule": "backcast", "fund_start_share": 0.10,
          "fund_rate_months": 12, "fund_dose_before_file": "backcast", "exclude_gapfilled": True,
          # v20.59: the outcome screen's rule -- "drop" (a fill-value / collapsed year-season leaves the model) | "keep" | "off" (OUTCOME_SCREEN)
          "outcome_screen": "drop",
          "design_source": "model",          # v20.59: "panel" = the PANEL's post / pre / did (the exports' Treat flag, PERIOD_RULE) are the design the model estimates
                                             #   on (the notebooks' default); "model" = the design in effect (timing, TREATMENT_YEAR ...) -- the design-based option
          # v20.12: which rows enter the estimation. "seasonal" = Kharif/Rabi/Zaid (Season 1-3, the default);
          # "yearly" = the annual composite rows (Season 0) -- the only place ESI / RUSLE / WSI / WSSI have values;
          # "all" = both (rarely appropriate: mixes two temporal resolutions).
          # v20.24: "auto" (default) = the ANNUAL composite (Season 0) whenever the panel has it -- complete for every
          # year, so the estimation sample is not shaped by seasonal cloud/footprint gaps -- else the seasonal rows.
          "seasons": "all", "seasons_resolved": None,
          # v20.29: ALL rows -- the annual composite AND Kharif / Rabi / Zaid -- with fixed effects for each pixel's
          # series (pixel x season: its annual, Kharif, Rabi and Zaid levels) and for each year x season (which
          # contains the year and the season effects). unit_fe = "pixel" puts one fixed effect per pixel instead.
          "unit_fe": "pixel_season", "covariates": list(DEFAULT_COVARIATES), "covariate_set": "all",
          # v20.55 (your option): in a pooled panel the rings of one sub-watershed overlap the core of the next. "drop" (default,
          # CLEAN_CONTROLS since v20.35) leaves out control rows of pixels TREATED elsewhere and rows repeating a pixel already in
          # the sample; "keep" keeps them (results carry the tag _keepOverlap).
          "overlap_rows": "drop"}

def parse_control_zones(spec):
    """'1' -> (1,) | '1-3' -> (1,2,3) | '1,3,5' -> (1,3,5) | (1,2) -> (1,2) | 3 -> (3,)."""
    if spec is None: return tuple(ACTIVE["control_zones"])
    if isinstance(spec, (int, np.integer)): return (int(spec),)
    if isinstance(spec, (list, tuple, set)): zones = sorted(int(z) for z in spec)
    else:
        t = str(spec).strip()
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", t)
        if m:
            a, b = int(m.group(1)), int(m.group(2)); zones = list(range(min(a, b), max(a, b) + 1))
        else:
            zones = sorted(int(x) for x in re.findall(r"\d+", t))
    if not zones: raise InsufficientDataError(f"could not read a control-ring choice from {spec!r}")
    if TREAT_CORE_BUFFKM in zones:
        raise InsufficientDataError(f"buff_km {TREAT_CORE_BUFFKM} is the TREATED core -- it cannot also be a control ring")
    return tuple(zones)

def _design_is_resolved(a=None):
    """v20.58: True once the timing of the scenario is known (a fund timing needs the fund workbook, read when the model runs)."""
    a = a or ACTIVE
    if a.get("timing") == "fund": return bool(a.get("site_start")) and int(a.get("n_fund_dated", 1) or 0) > 0
    if a.get("timing") == "registry": return bool(a.get("site_years"))
    return True

def _timing_request_text(a=None):
    """v20.58: the treatment timing in words -- the per-sub-watershed seasons once resolved, what WILL be read before that."""
    a = a or ACTIVE
    t = a.get("timing", "fixed")
    if t == "fund":
        if _design_is_resolved(a):
            return ("timing FUND (first treated season per sub-watershed: "
                    + ", ".join(f"{k}: {_fund_label(k)}" for k in sorted(a.get("site_start", {}))[:8]) + ")")
        return "timing FUND (each sub-watershed's first treated season is read from the fund workbook when the model runs)"
    if t == "registry":
        return ("timing REGISTRY " + (str(dict(sorted(a.get("site_years", {}).items())[:8])) if a.get("site_years")
                                      else "(each sub-watershed's implementation year from data/sites/sites.csv, read when the model runs)"))
    return f"treatment year {a['treatment_year']} (post = Year >= {a['post_cutoff']})"

def set_scenario(control_zones=None, treatment_year=None, post_cutoff=None, exclude_transition_year=None,
                 pre_years=None, post_years=None, year_min=None, year_max=None, all_years=False,
                 cohort_offset=None, seasons=None, use_site_years=None, site_years=None, cluster=None,
                 pooled_fe=None, unit_fe=None, covariates=None, allow_outcome_covariates=False,
                 nonnegative=None, nonnegative_mode=None, nonnegative_scope=None, overlap_rows=None, timing=None, site_start=None,
                 design_mode=None, fragment_rule=None, fragment_min_share=None, dose_variable=None, fund_start_rule=None,
                 fund_start_share=None, fund_rate_months=None, fund_dose_before_file=None, exclude_gapfilled=None, sub_watersheds=None,
                 outcome_screen=None, design_source=None, persist=False, verbose=True):
    """Set the run's control rings and treatment timing. Call it in CELL 1, BEFORE loading the panel.
    post_cutoff defaults to treatment_year (shifting the timing shifts the pre/post split with it).

    v20.1: when this runs INSIDE the outcome loop (CELL 9 re-executing the notebook for the next variable), the
    scenario you set interactively is kept and this call is ignored. Without that, the loop would read CELL 1 from
    the SAVED notebook file and silently estimate the remaining variables under the default rings/year -- the
    numbers would not match the scenario on your screen unless you had saved the notebook first."""
    locked = OUTCOME_LOOP_STATE.get("scenario")
    if locked and OUTCOME_LOOP_STATE.get("outcome"):
        ACTIVE.update(locked)
        _force_negative_from_active()                        # v20.34: the filter follows the locked scenario too
        if verbose:
            info(f"scenario locked to {scenario_tag()} by the outcome loop -- the SAME design as the first outcome")
        return dict(ACTIVE)
    # v20.34: remember what THIS call sets explicitly -- load_scenario() will not override those with the saved file
    _EXPLICIT_KEYS.clear()
    for _k, _v in (("control_zones", control_zones), ("treatment_year", treatment_year), ("post_cutoff", post_cutoff),
                   ("exclude_transition_year", exclude_transition_year), ("pre_years", pre_years), ("post_years", post_years),
                   ("year_min", year_min), ("year_max", year_max), ("cohort_offset", cohort_offset), ("seasons", seasons),
                   ("use_site_years", use_site_years), ("site_years", site_years), ("cluster", cluster),
                   ("pooled_fe", pooled_fe), ("unit_fe", unit_fe), ("nonnegative", nonnegative),
                   ("nonnegative_mode", nonnegative_mode), ("nonnegative_scope", nonnegative_scope),
                   ("timing", timing), ("site_start", site_start), ("design_mode", design_mode), ("fragment_rule", fragment_rule),
                   ("fragment_min_share", fragment_min_share), ("dose_variable", dose_variable), ("fund_start_rule", fund_start_rule),
                   ("fund_start_share", fund_start_share), ("fund_rate_months", fund_rate_months),
                   ("fund_dose_before_file", fund_dose_before_file), ("exclude_gapfilled", exclude_gapfilled),
                   ("overlap_rows", overlap_rows), ("sub_watersheds", sub_watersheds), ("outcome_screen", outcome_screen),
                   ("design_source", design_source)):   # v20.57: overlap_rows was missing; v20.58: the processing set; v20.59: the screen's rule, the design's source
        if _v is not None: _EXPLICIT_KEYS.add(_k)
    # v20.57: which keys the notebook set, in the form load_scenario() respects (a "data" option is explicit too)
    for _k, _v in (("treatment_year_setting", treatment_year), ("post_cutoff_setting", post_cutoff), ("seasons_setting", seasons),
                   ("site_years_setting", site_years), ("site_start_setting", site_start)):
        if _v is not None: _EXPLICIT_KEYS.add(_k)
    if any(v is not None for v in (control_zones, pre_years, post_years, seasons)) or all_years: _EXPLICIT_KEYS.add("data_keys")
    if pre_years is not None or post_years is not None or year_min is not None or year_max is not None or all_years:
        _EXPLICIT_KEYS.add("drop_years")
    _dk = set(ACTIVE.get("data_keys") or [])
    def _is_data(v): return isinstance(v, str) and v.strip().lower() in DATA_OPTION_WORDS
    def _is_all(v): return isinstance(v, str) and v.strip().lower() in ("all", "every", "none")
    if control_zones is not None:
        if _is_data(control_zones): _dk.add("control_zones"); control_zones = None
        else: _dk.discard("control_zones")
    for _k, _v in (("pre_years", pre_years), ("post_years", post_years)):
        if _v is None: continue
        if _is_data(_v): _dk.add(_k)
        else: _dk.discard(_k)
    if year_min is not None: _dk.discard("pre_years")
    if year_max is not None: _dk.discard("post_years")
    if all_years: _dk -= {"pre_years", "post_years"}
    if seasons is not None:
        if str(seasons).strip().lower() == "auto": _dk.add("seasons")
        else: _dk.discard("seasons")
        ACTIVE["seasons_setting"] = seasons if isinstance(seasons, str) else list(seasons)
    ACTIVE["data_keys"] = sorted(_dk)
    if _is_data(pre_years) or _is_all(pre_years):                 # "data" -> resolve_design; "all" -> every year before
        ACTIVE["pre_years"] = None; ACTIVE["year_min"] = None; pre_years = None
    if _is_data(post_years) or _is_all(post_years):
        ACTIVE["post_years"] = None; ACTIVE["year_max"] = None; post_years = None
    if design_mode is not None:
        _m = str(design_mode).strip().lower()
        if _m not in ("recommended", "manual"): raise InsufficientDataError(f"design_mode must be 'recommended' or 'manual' (got {design_mode!r})")
        ACTIVE["design_mode"] = _m
    if fragment_rule is not None:
        _f = str(fragment_rule).strip().lower()
        if _f not in ("drop", "keep"): raise InsufficientDataError(f"fragment_rule must be 'drop' or 'keep' (got {fragment_rule!r})")
        ACTIVE["fragment_rule"] = _f
    if sub_watersheds is not None:                                 # v20.58: "data" | "major" | names / ids
        _sw = sub_watersheds
        if isinstance(_sw, str) and _sw.strip().lower() in ("data", "recommended", "auto", "major"):
            ACTIVE["sub_watersheds"] = "major" if _sw.strip().lower() == "major" else "data"
        else:
            ACTIVE["sub_watersheds"] = [x for x in (list(_sw) if isinstance(_sw, (list, tuple, set)) else [_sw])]
    if fragment_min_share is not None:
        _fs = float(fragment_min_share)
        if not (0.0 <= _fs < 1.0): raise InsufficientDataError(f"fragment_min_share must be in [0, 1) (got {fragment_min_share!r})")
        ACTIVE["fragment_min_share"] = _fs
    if dose_variable is not None:
        _dv = str(dose_variable).strip()
        if _dv not in DOSE_VARIABLES: raise InsufficientDataError(f"dose_variable must be one of {list(DOSE_VARIABLES)} (got {dose_variable!r})")
        ACTIVE["dose_variable"] = _dv
    if fund_start_rule is not None:
        _r = str(fund_start_rule).strip().lower()
        if _r not in ("backcast", "share", "file_start"): raise InsufficientDataError(f"fund_start_rule must be 'backcast', 'share' or 'file_start' (got {fund_start_rule!r})")
        ACTIVE["fund_start_rule"] = _r
    if fund_start_share is not None:
        if not (0 < float(fund_start_share) <= 1): raise InsufficientDataError(f"fund_start_share must be in (0, 1] (got {fund_start_share!r})")
        ACTIVE["fund_start_share"] = float(fund_start_share)
    if fund_rate_months is not None:
        if int(fund_rate_months) < 2: raise InsufficientDataError(f"fund_rate_months must be >= 2 (got {fund_rate_months!r})")
        ACTIVE["fund_rate_months"] = int(fund_rate_months)
    if exclude_gapfilled is not None:                              # v20.57: a MODEL option (was an engine constant only)
        global EXCLUDE_GAPFILLED
        EXCLUDE_GAPFILLED = bool(exclude_gapfilled); ACTIVE["exclude_gapfilled"] = bool(exclude_gapfilled)
    if fund_dose_before_file is not None:
        _b = str(fund_dose_before_file).strip().lower()
        if _b not in ("backcast", "missing"): raise InsufficientDataError(f"fund_dose_before_file must be 'backcast' or 'missing' (got {fund_dose_before_file!r})")
        ACTIVE["fund_dose_before_file"] = _b
    if outcome_screen is not None: ACTIVE["outcome_screen"] = _screen_rule_of(outcome_screen)     # v20.59: drop | keep | off
    if design_source is not None: ACTIVE["design_source"] = _design_source_of(design_source)     # v20.59: panel | model
    if treatment_year is not None: _EXPLICIT_KEYS.add("post_cutoff")
    if all_years: _EXPLICIT_KEYS.update({"pre_years", "post_years", "year_min", "year_max"})
    if control_zones is not None: ACTIVE["control_zones"] = parse_control_zones(control_zones)
    if treatment_year is not None:
        ACTIVE["treatment_year"] = int(treatment_year); ACTIVE["treatment_year_setting"] = int(treatment_year)
        ACTIVE["post_cutoff"] = int(post_cutoff) if post_cutoff is not None else int(treatment_year)
        ACTIVE["post_cutoff_setting"] = int(post_cutoff) if post_cutoff is not None else None
    elif post_cutoff is not None:
        ACTIVE["post_cutoff"] = int(post_cutoff); ACTIVE["post_cutoff_setting"] = int(post_cutoff)
    if exclude_transition_year is not None: ACTIVE["exclude_transition_year"] = bool(exclude_transition_year)
    # ---- v20.2 YEAR WINDOW -------------------------------------------------------------------------
    #   pre_years  = number of years BEFORE the post cutoff to keep   (None = every earlier year)
    #   post_years = number of years FROM the post cutoff to keep     (None = every later year; 1 = cutoff year only)
    #   year_min / year_max = an explicit window that overrides the counts;  all_years=True clears the window.
    if cohort_offset is not None: ACTIVE["cohort_offset"] = int(cohort_offset)
    if unit_fe is not None:                                   # v20.29
        if str(unit_fe) not in ("pixel_season", "pixel"): raise InsufficientDataError("unit_fe must be 'pixel_season' or 'pixel'")
        ACTIVE["unit_fe"] = str(unit_fe)
    if covariates is not None:                                # v20.29/30: YOUR covariate choice for this model
        covs, _cov_label = resolve_covariates(covariates)
        ACTIVE["covariate_set"] = _cov_label
        outs = [x for x in covs if x in ALL_ESTIMATION_VARIABLES]
        if outs and not allow_outcome_covariates:
            raise InsufficientDataError(f"{outs} are OUTCOME variables -- the watershed works can change them, so as covariates they "
                                        f"would absorb part of the effect (bad controls). Use weather / land use, or pass "
                                        f"allow_outcome_covariates=True if you really mean it.")
        DEFAULT_COVARIATES[:] = covs; ACTIVE["covariates"] = list(covs)
    if nonnegative is not None:                               # v20.32: YOUR switch
        global NONNEGATIVE_ESTIMATION
        NONNEGATIVE_ESTIMATION = bool(nonnegative); ACTIVE["nonnegative"] = bool(nonnegative); _sync_negative_switch()
        if NONNEGATIVE_ESTIMATION:
            warn("NONNEGATIVE_ESTIMATION = True: rows whose outcome is negative are excluded from the DiD. That is "
                 "selection on the outcome (NDVI / NDWI / NDMI / NDRE / SMDI are negative over water, bare soil and "
                 "moisture stress), so the estimate is conditional on a censored sample -- results go to a separate "
                 "'_nonneg' folder and every saved file records it. The DiD coefficient is a DIFFERENCE and can be "
                 "negative with all-positive data; this switch does not remove a negative effect.")
    if nonnegative_mode is not None:
        global NONNEGATIVE_MODE
        if str(nonnegative_mode) not in ("drop", "zero"): raise InsufficientDataError("nonnegative_mode must be 'drop' or 'zero'")
        NONNEGATIVE_MODE = str(nonnegative_mode); ACTIVE["nonnegative_mode"] = NONNEGATIVE_MODE
    if nonnegative_scope is not None:
        global NONNEGATIVE_SCOPE
        if str(nonnegative_scope) not in ("outcome", "covariates", "outcome+covariates"):
            raise InsufficientDataError("nonnegative_scope must be 'outcome', 'covariates' or 'outcome+covariates'")
        NONNEGATIVE_SCOPE = str(nonnegative_scope); ACTIVE["nonnegative_scope"] = NONNEGATIVE_SCOPE
    if cluster is not None:
        if str(cluster) not in ("subwshed", "site", "year"):
            raise InsufficientDataError("cluster must be 'site' (the sub-watershed; default), 'year', or 'subwshed'")
        ACTIVE["cluster"] = str(cluster)
    if pooled_fe is not None:
        if str(pooled_fe) not in ("period", "site_period"): raise InsufficientDataError("pooled_fe must be 'period' or 'site_period'")
        ACTIVE["pooled_fe"] = str(pooled_fe)
    if site_years is not None:                                     # v20.57: your own years per site = the registry timing with them
        ACTIVE["site_years"] = {int(k): int(v) for k, v in dict(site_years).items() if v is not None}; ACTIVE["use_site_years"] = bool(ACTIVE["site_years"])
        ACTIVE["site_years_setting"] = dict(ACTIVE["site_years"]) or None
        if timing is None: ACTIVE["timing"] = "registry" if ACTIVE["site_years"] else "fixed"
    if use_site_years is not None and timing is None and site_years is None and site_start is None:
        # v20.57: the v20.22 switch maps onto the timing -- True = each site on its registry year, False = one year for all
        if bool(use_site_years): ACTIVE["timing"] = "registry" if ACTIVE.get("timing") != "fund" else "fund"
        elif ACTIVE.get("timing") == "registry": ACTIVE["timing"] = "fixed"
    if use_site_years is not None:
        ACTIVE["use_site_years"] = bool(use_site_years)
        if use_site_years and not ACTIVE["site_years"]:
            try:
                import _sites as _S
                ACTIVE["site_years"] = {k: v for k, v in _S.cohorts(int(ACTIVE["treatment_year"])).items() if v is not None}
                _assumed = [int(k) for k in ACTIVE["site_years"] if _S.treatment_year_source(int(k)) == "ASSUMED"]
                if _assumed and verbose:                                               # v20.39: never silent
                    warn(f"implementation year UNKNOWN for {len(_assumed)} sub-watershed(s) {_assumed} "
                         f"({', '.join(_S.name(k) for k in _assumed[:6])}{'...' if len(_assumed) > 6 else ''}): "
                         f"{int(ACTIVE['treatment_year'])} is ASSUMED. If they started earlier, their pre-period holds treated "
                         f"years and every effect is pulled toward zero -- fill treatment_year in data/sites/sites.csv.")
            except Exception as _e:
                warn(f"use_site_years=True but the sites registry could not be read ({_e}); single treatment year kept")
                ACTIVE["use_site_years"] = False
    if seasons is not None:
        ACTIVE["seasons"] = normalize_seasons(seasons); _SEASON_CHOICE.clear()
        ACTIVE["seasons_setting"] = ACTIVE["seasons"]
    if timing is not None:                                         # v20.57: fund | registry | fixed
        t_ = str(timing).strip().lower()
        if t_ not in ("fund", "registry", "fixed"): raise InsufficientDataError(f"timing must be 'fund', 'registry' or 'fixed' (got {timing!r})")
        ACTIVE["timing"] = t_
        if t_ == "fixed" and site_start is None: ACTIVE["site_start"] = {}; ACTIVE["site_start_setting"] = None
        if t_ != "registry" and site_years is None: ACTIVE["site_years_setting"] = None
    if site_start is not None:                                     # v20.57: {site: [first treated year, Season code]} -- given by hand
        ACTIVE["site_start"] = {int(k): [int(v[0]), int(v[1])] for k, v in dict(site_start).items() if v is not None}
        ACTIVE["site_start_setting"] = {int(k): list(v) for k, v in ACTIVE["site_start"].items()} or None
        if ACTIVE["site_start"]:
            ACTIVE["site_years"] = {k: int(v[0] + (1 if int(v[1]) == 2 else 0)) for k, v in ACTIVE["site_start"].items()}   # the annual cohort
            ACTIVE["use_site_years"] = True
            if timing is None: ACTIVE["timing"] = "fund"
    if overlap_rows is not None:                                   # v20.55: keep | drop the overlapping rows of other sub-watersheds
        o_ = str(overlap_rows).strip().lower()
        if o_ not in ("drop", "keep"): raise InsufficientDataError(f"overlap_rows must be 'drop' or 'keep' (got {overlap_rows!r})")
        ACTIVE["overlap_rows"] = o_
    if all_years: ACTIVE.update({"pre_years": None, "post_years": None, "year_min": None, "year_max": None, "drop_years": []})
    # v20.59: PRE_YEARS / POST_YEARS take a NUMBER OF YEARS (4 = the 4 years before / from the start) OR a CALENDAR YEAR (2015 = the first pre
    # year, 2025 = the last post year). v20.58 read every number as a count (R too): PRE_YEARS = 2022 became year_min = 2022 - 2022 = 0.
    if pre_years is not None:
        _n = _year_option("PRE_YEARS", pre_years)
        if _n >= 1900: ACTIVE.update({"year_min": _n, "pre_years": None}); _EXPLICIT_KEYS.add("year_min")
        else: ACTIVE.update({"pre_years": _n, "year_min": None})
    if post_years is not None:
        _n = _year_option("POST_YEARS", post_years)
        if _n >= 1900: ACTIVE.update({"year_max": _n, "post_years": None}); _EXPLICIT_KEYS.add("year_max")
        else: ACTIVE.update({"post_years": _n, "year_max": None})
    if year_min is not None: ACTIVE.update({"year_min": int(year_min), "pre_years": None})
    if year_max is not None: ACTIVE.update({"year_max": int(year_max), "post_years": None})
    lo, hi = scenario_years()
    if lo is not None and hi is not None and lo > hi:
        raise InsufficientDataError(f"the year window is empty ({lo} > {hi}): check pre_years / post_years / year_min / year_max")
    if hi is not None and hi < int(ACTIVE["post_cutoff"]):
        warn(f"the window ends at {hi}, before the post cutoff {ACTIVE['post_cutoff']}: there would be no POST period")
    if lo is not None and lo >= int(ACTIVE["post_cutoff"]):
        warn(f"the window starts at {lo}, at or after the post cutoff {ACTIVE['post_cutoff']}: there would be no PRE period")
    if verbose:
        # v20.58: the timing as it IS -- v20.57 printed "treatment year 2022 (post = Year >= 2022)" and a folder tag while the fund timing
        # was still unresolved (a placeholder the model never used); the design in force is printed at STEP 1 (SCENARIO IN FORCE)
        info(f"SCENARIO SET: treated = buff_km {TREAT_CORE_BUFFKM} | control rings {ACTIVE['control_zones']} | "
             f"{_timing_request_text()} | years "
             + (year_window_text() if (_EXPLICIT_KEYS & {"pre_years", "post_years", "year_min", "year_max"}) else "as the panel preparation set them")
             + ("" if _design_is_resolved() else " (options not set here are completed from the panel preparation; "
                                                 "the design in force and its results folder are printed at STEP 1)")
             + (f" | tag {scenario_tag()}" if _design_is_resolved() else ""))
        if ACTIVE.get("cohort_offset"):
            info(f"staggered cohorts (first_treat_agri_year) shifted by {ACTIVE['cohort_offset']:+d} year(s)")
        info("every treatment/period column is rebuilt from buff_km and Year for this scenario; "
             "results go to the scenario sub-folder so runs never overwrite each other")
    return dict(ACTIVE)

def _year_option(name, v):
    """v20.59: PRE_YEARS / POST_YEARS as an integer -- a count of years (1..200) or a calendar year (1900..2100); anything else is refused."""
    try:
        n = int(v)
    except Exception:
        raise InsufficientDataError(f"{name} must be 'data', 'all', a number of years (e.g. 4) or a calendar year (e.g. "
                                    f"{'2015 = the FIRST pre year' if name == 'PRE_YEARS' else '2025 = the LAST post year'}) -- got {v!r}")
    if n < 1 or (200 < n < 1900) or n > 2100:
        raise InsufficientDataError(f"{name} must be 'data', 'all', a number of years (e.g. 4) or a calendar year (e.g. "
                                    f"{'2015 = the FIRST pre year' if name == 'PRE_YEARS' else '2025 = the LAST post year'}) -- got {v!r}")
    return n

def year_window_setting_text(scn=None):
    """v20.59: PRE_YEARS / POST_YEARS as set, in words (for DESIGN IN EFFECT): (pre_text, post_text)."""
    a = scn or ACTIVE; dk = set(a.get("data_keys") or [])
    pre = ("data" if "pre_years" in dk else f"{a['pre_years']} (years before the start)" if a.get("pre_years") is not None
           else f"{a['year_min']} (calendar year)" if a.get("year_min") is not None else "all")
    post = ("data" if "post_years" in dk else f"{a['post_years']} (years from the start)" if a.get("post_years") is not None
            else f"{a['year_max']} (calendar year)" if a.get("year_max") is not None else "all")
    return pre, post

def year_window_dropped(scn=None):
    """v20.59: the bounds that leave NO year on their side of the start -- (year_min or None, year_max or None) -- such a bound is not a
    window and is not applied (scenario_years); resolve_design says so."""
    a = scn or ACTIVE; cut = int(a["post_cutoff"]); dk = set(a.get("data_keys") or [])
    lo = a.get("year_min") if ("pre_years" not in dk and a.get("year_min") is not None and int(a["year_min"]) >= cut) else None
    hi = a.get("year_max") if ("post_years" not in dk and a.get("year_max") is not None and int(a["year_max"]) < cut) else None
    return lo, hi

def scenario_years(scn=None):
    """(first_year, last_year) of the scenario's window; None means 'whatever the panel has'.
    v20.59: a lower bound at / after the start, or an upper bound before it, leaves no year on its side of the start and is not a
    window -- it is left out here (resolve_design reports it in DESIGN IN EFFECT and as a warning); the count forms never reach it."""
    a = scn or ACTIVE
    lo, hi = a.get("year_min"), a.get("year_max")
    cut = int(a["post_cutoff"])
    if lo is None and a.get("pre_years") is not None: lo = cut - int(a["pre_years"])
    if hi is None and a.get("post_years") is not None: hi = cut + int(a["post_years"]) - 1
    if lo is not None and int(lo) >= cut: lo = None
    if hi is not None and int(hi) < cut: hi = None
    return (int(lo) if lo is not None else None, int(hi) if hi is not None else None)

def year_window_text(scn=None):
    lo, hi = scenario_years(scn)
    if lo is None and hi is None: return "all years in the panel"
    return f"{lo if lo is not None else 'start'}..{hi if hi is not None else 'end'}"

def year_mask(years, scn=None):
    """Rows whose Year lies inside the scenario's window (v20.57: and is not a year the data-driven design leaves out)."""
    lo, hi = scenario_years(scn)
    y = pd.to_numeric(pd.Series(np.asarray(years)), errors="coerce")
    m = np.ones(len(y), dtype=bool)
    if lo is not None: m &= (y >= lo).values
    if hi is not None: m &= (y <= hi).values
    _dy = (scn or ACTIVE).get("drop_years") or []
    if _dy: m &= ~y.isin([int(v) for v in _dy]).values
    return m

_SEASON_SCAN = {}
def panel_has_yearly(path=None):
    """Does the panel (or the per-variable file) contain annual-composite rows (Season 0)? Cached per file."""
    p = path or PREPARED_PANEL
    if p in _SEASON_SCAN: return _SEASON_SCAN[p]
    has = False
    try:
        import pyarrow.parquet as pq
        pf = pq.ParquetFile(p)
        try:
            for i in range(pf.num_row_groups):
                s = pf.read_row_group(i, columns=["Season"]).to_pandas()["Season"]
                if (pd.to_numeric(s, errors="coerce") == 0).any(): has = True; break
        finally:
            try: pf.close()
            except Exception: pass
    except Exception:
        has = False
    _SEASON_SCAN[p] = has
    return has

_SEASON_CHOICE = {}          # (file, outcome) -> "yearly" | "seasonal"   (v20.24)
_YEARLY_OUTCOME_SCAN = {}    # (file, outcome) -> True if the annual composite carries finite values of it
CURRENT_OUTCOME = None       # set by columns_for(); lets the loaders resolve 'auto' per outcome

def yearly_outcome_available(outcome, path=None):
    """Does the annual composite (Season 0) carry finite values of `outcome`? Cached per (file, outcome)."""
    p = path or PREPARED_PANEL
    key = (p, outcome)
    if key in _YEARLY_OUTCOME_SCAN: return _YEARLY_OUTCOME_SCAN[key]
    found = False
    try:
        import pyarrow.parquet as pq
        pf = pq.ParquetFile(p)
        try:
            if outcome in pf.schema_arrow.names:
                for i in range(pf.num_row_groups):
                    d = pf.read_row_group(i, columns=["Season", outcome]).to_pandas()
                    v = pd.to_numeric(d[outcome], errors="coerce").values.astype(np.float64)
                    if (np.isfinite(v) & (pd.to_numeric(d["Season"], errors="coerce").values == 0)).any():
                        found = True; break
        finally:
            try: pf.close()
            except Exception: pass
    except Exception:
        found = False
    _YEARLY_OUTCOME_SCAN[key] = found
    return found

def seasons_mode(path=None, verbose=True, outcome=None):
    """The seasons setting IN FORCE for `outcome` (default: the outcome of the last columns_for call).
    'auto' (v20.24 default) = the ANNUAL composite (Season 0) whenever the file carries it for this outcome --
    complete for every year, so seasonal gaps (cloud / mask / footprint) cannot bias the DiD -- and the seasonal
    rows only for an outcome that has no annual values. Resolved per (file, outcome); never cached in ACTIVE, so
    switching panels or outcomes can never reuse a stale choice."""
    mode = ACTIVE.get("seasons", "auto")
    if mode != "auto": return mode
    p = path or PREPARED_PANEL
    o = outcome if outcome is not None else CURRENT_OUTCOME
    key = (p, o)
    if key in _SEASON_CHOICE: return _SEASON_CHOICE[key]
    if not panel_has_yearly(p):
        res = "seasonal"; why = "no annual-composite rows in the data; seasonal rows are used"
    elif o is not None and not yearly_outcome_available(o, p):
        res = "seasonal"; why = f"'{o}' has no values in the annual composite; its seasonal rows are used"
    else:
        res = "yearly"; why = ("the ANNUAL composite (Season 0) is used -- complete for every year, so seasonal gaps "
                               "cannot bias the estimate; pixel + year fixed effects (SEASONS = 'seasonal' to override)")
    _SEASON_CHOICE[key] = res
    if verbose or o is not None:
        info(f"seasons = auto -> {res}" + (f" for {o}" if o else "") + f": {why}")
    return res

_YEARLY_COV_TABLES = {}      # (file, covariates) -> DataFrame indexed by (pixel_id, Year): seasonal means

def yearly_covariate_table(covs, path=None):
    """v20.24: pixel-year MEANS of the covariates over that year's SEASONAL rows. Used to fill a covariate that the
    annual composite does not carry (or carries with gaps), so a yearly-first estimate keeps its weather
    adjustment instead of losing every row to the missing-value policy. Built once per (file, covariates)."""
    p = path or PREPARED_PANEL
    key = (p, tuple(sorted(covs)))
    if key in _YEARLY_COV_TABLES: return _YEARLY_COV_TABLES[key]
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(p); parts = []
    try:
        cols = [c_ for c_ in ["pixel_id", "Year", "Season"] + list(covs) if c_ in pf.schema_arrow.names]
        for i in range(pf.num_row_groups):
            d = pf.read_row_group(i, columns=cols).to_pandas()
            d = d[pd.to_numeric(d["Season"], errors="coerce") != 0]
            if len(d): parts.append(d.drop(columns=["Season"]))
    finally:
        try: pf.close()
        except Exception: pass
    if not parts:
        tab = pd.DataFrame(columns=list(covs)); tab.index = pd.MultiIndex.from_arrays([[], []], names=["pixel_id", "Year"])
    else:
        allp = pd.concat(parts, ignore_index=True)
        for c_ in covs:
            if c_ in allp.columns: allp[c_] = pd.to_numeric(allp[c_], errors="coerce")
        tab = allp.groupby(["pixel_id", "Year"])[[c_ for c_ in covs if c_ in allp.columns]].mean()
    _YEARLY_COV_TABLES[key] = tab
    return tab

def fill_yearly_covariates(d, covs, path=None):
    """Fill NaN covariates of ANNUAL rows from the same pixel-year's seasonal means. Returns (frame, n_filled)."""
    if not len(d) or "Season" not in d.columns: return d, 0
    yr = pd.to_numeric(d["Season"], errors="coerce").values == 0
    need = [c_ for c_ in covs if c_ in d.columns and pd.to_numeric(d.loc[yr, c_], errors="coerce").isna().any()] if yr.any() else []
    if not need: return d, 0
    tab = yearly_covariate_table(need, path)
    if not len(tab): return d, 0
    idx = pd.MultiIndex.from_arrays([d.loc[yr, "pixel_id"].values, pd.to_numeric(d.loc[yr, "Year"], errors="coerce").values])
    vals = tab.reindex(idx)
    n = 0
    d = d.copy()
    for c_ in need:
        cur = pd.to_numeric(d.loc[yr, c_], errors="coerce").values.astype(np.float64)
        fill = vals[c_].values.astype(np.float64) if c_ in vals.columns else np.full(len(cur), np.nan)
        m = ~np.isfinite(cur) & np.isfinite(fill)
        if m.any():
            cur[m] = fill[m]; n += int(m.sum())
            d.loc[yr, c_] = cur
    return d, n

SEASON_NAME_CODE = {"yearly": 0, "annual": 0, "kharif": 1, "rabi": 2, "zaid": 3}

def normalize_seasons(value):
    """v20.55: the `seasons` setting as ONE canonical string.
       "all"       annual composite + Kharif / Rabi / Zaid together (your rule: year AND season variation, with
                   pixel x season and year x season fixed effects)              -- the default
       "seasonal"  Kharif / Rabi / Zaid only (season-based)
       "yearly"    the annual composite only
       "Rabi", "Kharif+Zaid", ["Rabi", "Zaid"] ...   one or several named seasons (each pixel x season is a unit)
       "auto"      the data decide (the v20.24 / v20.45 rule: the annual composite when the file carries it)"""
    if isinstance(value, (list, tuple, set)):
        parts = [str(v) for v in value]
    else:
        parts = [x for x in str(value).replace(",", "+").replace(" ", "+").split("+") if x]
    parts = [x.strip().lower() for x in parts]
    if len(parts) == 1 and parts[0] in ("seasonal", "yearly", "all", "auto"): return parts[0]
    bad_ = [x for x in parts if x not in SEASON_NAME_CODE]
    if bad_ or not parts:
        raise InsufficientDataError(f"seasons must be 'all', 'seasonal', 'yearly', 'auto' or season names (Kharif, Rabi, Zaid, "
                                    f"e.g. 'Rabi' or 'Rabi+Zaid') -- got {value!r}")
    codes = sorted({SEASON_NAME_CODE[x] for x in parts})
    if codes == [0]: return "yearly"
    if codes == [1, 2, 3]: return "seasonal"
    if codes == [0, 1, 2, 3]: return "all"
    inv = {0: "yearly", 1: "kharif", 2: "rabi", 3: "zaid"}
    return "+".join(inv[c] for c in codes)

def season_codes(mode):
    """The Season codes a resolved `seasons` mode keeps (None = every row)."""
    if mode == "all": return None
    if mode == "yearly": return {0}
    if mode == "seasonal": return {1, 2, 3}
    return {SEASON_NAME_CODE[x] for x in str(mode).split("+")}

def season_rows(t_or_seasons):
    """pyarrow filter (or a pandas mask) selecting the rows the scenario's `seasons` setting keeps."""
    mode = seasons_mode(verbose=False); codes = season_codes(mode)
    if hasattr(t_or_seasons, "num_rows"):                     # a pyarrow Table
        import pyarrow as pa, pyarrow.compute as pc
        t = t_or_seasons
        if codes is None: return t
        return t.filter(pc.is_in(t["Season"], value_set=pa.array(sorted(codes), type=t["Season"].type)))
    s = pd.to_numeric(pd.Series(np.asarray(t_or_seasons)), errors="coerce").values
    if codes is None: return np.ones(len(s), dtype=bool)
    return np.isin(s, sorted(codes))

def has_year_window(scn=None):
    return scenario_years(scn) != (None, None) or bool((scn or ACTIVE).get("drop_years"))

def _fund_rule_tag(a=None):
    """'' for the default back-cast start, else the rule (the results of another start rule get their own folder)."""
    a = a or ACTIVE
    r = a.get("fund_start_rule", "backcast"); t = ""
    if r == "share": t = "Share%d" % round(100 * float(a.get("fund_start_share", 0.10)))
    elif r == "file_start": t = "FileStart"
    if int(a.get("fund_rate_months", 12) or 12) != 12: t += "Rate%d" % int(a["fund_rate_months"])
    return t

def scenario_tag(scn=None):
    a = scn or ACTIVE
    z = list(a["control_zones"])
    zs = f"{z[0]}-{z[-1]}" if z == list(range(z[0], z[-1] + 1)) and len(z) > 1 else "+".join(map(str, z))
    # v20.57: the fund timing -- "treatFund" only when the fund file (or your site_start) dated at least one sub-watershed; a fund
    # timing that fell back to the registry for every sub-watershed (no workbook) says so: _siteyrs<years>_fundMissing
    _fund_t = bool(a.get("timing") == "fund" and a.get("site_start") and int(a.get("n_fund_dated", 1) or 0) > 0)
    t = f"ctrl{zs}_treat{'Fund' + _fund_rule_tag(a) if _fund_t else a['treatment_year']}"
    if int(a["post_cutoff"]) != int(a["treatment_year"]) and not _fund_t: t += f"_post{a['post_cutoff']}"
    if a.get("exclude_transition_year"): t += "_noTransition"
    if a.get("cohort_offset"): t += f"_cohort{a['cohort_offset']:+d}"
    _sm = a.get("seasons", "seasonal")
    if _sm == "auto": _sm = "yearly" if panel_has_yearly() else "seasonal"     # folder = the panel-level choice
    if _sm != "seasonal": t += f"_{_sm}"
    if a.get("use_site_years") and a.get("site_years") and not _fund_t:
        ys = sorted(set(int(v) for v in a["site_years"].values())); t += "_siteyrs" + "-".join(str(y) for y in ys)
    if a.get("timing") == "fund" and not _fund_t: t += "_fundMissing"
    if a.get("cluster", "subwshed") == "site": t += "_clSite"
    if a.get("pooled_fe", "period") == "site_period" and int(a.get("n_sites", 2) or 0) != 1: t += "_feSitePeriod"   # v20.57: one site = 'period' 
    if a.get("unit_fe", "pixel_season") == "pixel": t += "_fePixel"                       # v20.29
    if a.get("nonnegative"): t += "_nonneg" + ("Zero" if a.get("nonnegative_mode", "drop") == "zero" else "")   # v20.32
    if a.get("overlap_rows", "drop") == "keep": t += "_keepOverlap"                                              # v20.55
    if a.get("fragment_rule", "drop") == "keep": t += "_keepFragments"                                           # v20.57
    elif abs(float(a.get("fragment_min_share", 0.05)) - 0.05) > 1e-12: t += "_frag%g" % round(100 * float(a["fragment_min_share"]), 3)
    _sw = a.get("sub_watersheds", "data")                                                                        # v20.58: a processing set
    if _sw != "data":                                                                                            # you chose has its own folder
        if _sw == "major": t += "_swsMajor"
        else:
            try: t += "_sws" + "-".join(str(x) for x in processing_sites()[0])
            except Exception: t += "_sws" + "-".join(str(x) for x in (_sw if isinstance(_sw, (list, tuple)) else [_sw]))
    if a.get("dose_variable", "dose_intensity_per_ha") != "dose_intensity_per_ha":
        t += {"dose_amount_sws": "_doseAmount", "dose_share_of_target": "_doseShare"}.get(a.get("dose_variable"), "_dose")
    if a.get("fund_dose_before_file", "backcast") == "missing": t += "_doseObsOnly"
    if a.get("exclude_gapfilled", True) is False: t += "_withGapFilled"                                          # v20.57
    if screen_rule(a) == "keep": t += "_screenKept"                                                           # v20.59: the screen's cells kept
    if a.get("design_source", "model") == "panel": t += "_panelDesign"                                        # v20.59: the panel's design estimated on
    if a.get("drop_years"): t += "_no" + "-".join(str(int(y)) for y in a["drop_years"])
    _sync_negative_switch()                                                               # v20.33: one suffix only
    _cv = list(a.get("covariates", STANDARD_COVARIATES))
    if _cv == list(WEATHER_COVARIATES):                  # v20.46: EXPLICIT -- the default set had no tag, so new results (four
        t += "_covAll4"                                  # weather covariates) shared folders with pre-v20.44 ones (LandUse as a number)
    elif _cv != list(STANDARD_COVARIATES):                                                  # v20.29/30: own folder per covariate set
        _lab = a.get("covariate_set")
        t += "_cov" + ({"none": "None", "mean_temp_rain": "MeanTempRain", "weather": "Weather"}.get(_lab)
                       or ("None" if not _cv else "-".join(x[:4] for x in _cv)))
    lo, hi = scenario_years(a)
    if lo is not None or hi is not None:
        t += f"_yr{lo if lo is not None else 'start'}-{hi if hi is not None else 'end'}"
    return t

_EXPLICIT_KEYS = set()     # v20.34: scenario keys the notebook's CELL 1 set explicitly (they win)
PANEL_SCENARIO_OVERRIDES_CELL1 = False   # v20.34: False = CELL 1 wins (default). True = the saved panel scenario is
                                         # FORCED on every notebook (the pre-v20.34 behaviour; used by the model gate)
SCENARIO_KEYS = ("control_zones", "treatment_year", "post_cutoff", "exclude_transition_year",
                 "pre_years", "post_years", "year_min", "year_max", "cohort_offset", "seasons",
                 "site_years", "use_site_years", "cluster", "pooled_fe", "unit_fe",
                 "nonnegative", "nonnegative_mode", "nonnegative_scope", "overlap_rows",   # v20.30: covariates are per model; v20.55: overlap_rows
                 "timing", "site_start",                                                     # v20.57: the fund / registry / fixed timing
                 "design_mode", "data_keys", "treatment_year_setting", "post_cutoff_setting", "seasons_setting",
                 "site_years_setting", "site_start_setting", "drop_years", "fragment_rule", "fragment_min_share", "sub_watersheds", "dose_variable",
                 "fund_start_rule", "fund_start_share", "fund_rate_months", "fund_dose_before_file", "exclude_gapfilled", "outcome_screen",
                 "design_source")   # v20.59
def scenario_file(path=None):
    """Where a scenario chosen during panel preparation is stored: next to the prepared panel."""
    return path or os.path.join(os.path.dirname(PREPARED_PANEL), "did_scenario.json")

def save_scenario(path=None, verbose=True):
    """v20.3: record the ACTIVE scenario next to the panel so EVERY model inherits it (P05 / P09 call this).
    A choice made at preprocessing therefore governs the whole pipeline without editing 45 notebooks."""
    p = scenario_file(path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({**{k: (list(ACTIVE.get(k, ())) if k == "control_zones" else ACTIVE.get(k)) for k in SCENARIO_KEYS},   # v20.32: a key a caller
                   "scenario_tag": scenario_tag(), "written": _ts(), "engine": ENGINE_VERSION,
                   "seasons_policy": "v20.29", "timing_policy": "v20.27"}, fh, indent=1)
    if verbose: ok(f"scenario {scenario_tag()} saved for the whole pipeline -> {p}")
    return p

def load_scenario(path=None, apply=True, verbose=True, required=False):
    load_derived_variables()                                  # v20.41: GND_* outcomes join ALL_ESTIMATION_VARIABLES
    """Adopt the scenario saved at panel-preparation time, if one exists. Returns the dict or None.
    Inside the outcome loop the parent's scenario wins (same rule as set_scenario)."""
    if OUTCOME_LOOP_STATE.get("scenario") and OUTCOME_LOOP_STATE.get("outcome"):
        return dict(ACTIVE)
    p = scenario_file(path)
    if not os.path.exists(p):
        if required: raise InsufficientDataError(f"no scenario file at {p} -- run P09 (or call C.save_scenario()) first")
        if verbose: info(f"no panel-level scenario at {p}; using the values set in this notebook ({scenario_tag()})")
        return None
    with open(p, encoding="utf-8") as fh: m = json.load(fh)
    # v20.24: a scenario file written BEFORE the yearly-first policy stored 'seasonal' only because that was the old
    # default, not a choice -- it must not pin every model back to the gap-prone seasonal rows. A file written from
    # v20.24 on is honoured exactly as saved (an explicit 'seasonal' there IS a choice).
    # v20.29: a file written before the all-years-and-seasons policy stored the OLD default ('auto' = annual rows only,
    # or 'seasonal'), not a choice -- its seasons are not adopted; this notebook's (all years AND seasons) stays in force.
    # From v20.29 on a saved seasons choice is honoured exactly.
    if m.get("seasons_policy") != "v20.29" and "seasons" in m:
        if verbose and m.get("seasons") != ACTIVE.get("seasons"):
            info(f"the saved scenario predates the all-years-and-seasons policy (it says seasons = {m.get('seasons')!r}) -> "
                 f"its seasons are not adopted; using {ACTIVE.get('seasons')!r}. Set SEASONS in this model's CELL 1 (v20.57: the design is chosen there).")
        m = {k: v for k, v in m.items() if k != "seasons"}

    # v20.26: a file written before the 2022-start timing policy carries the old split (treatment 2023, or 2022 with
    # post from 2023 and no transition exclusion). Its TIMING is not adopted -- this notebook's CELL 1 values (2022,
    # transition year excluded) stay in force -- and it says so. From v20.26 on, a saved timing is honoured exactly.
    _skip = set()
    if m.get("timing_policy") != "v20.27":
        _skip = {"treatment_year", "post_cutoff", "exclude_transition_year"}
        if verbose:
            info(f"the saved scenario predates the current timing rule (it says treatment {m.get('treatment_year')}, "
                 f"post from {m.get('post_cutoff')}, transition excluded {bool(m.get('exclude_transition_year'))}) -> its timing "
                 f"is NOT adopted; this notebook's timing is used ({ACTIVE['treatment_year']}, transition excluded "
                 f"{bool(ACTIVE.get('exclude_transition_year'))}). Set the timing in this model's CELL 1 (v20.57: TREATMENT_TIMING / TREATMENT_YEAR there).")
    if apply:
        # v20.34: what CELL 1 set EXPLICITLY wins; the saved panel scenario fills only what CELL 1 left unset.
        # (Before, the file silently replaced CELL 1: you set rings 1-3 and the notebook printed them, then every
        # estimate ran on rings 1-5 and was saved under ctrl1-5.)
        kept, adopted = [], []
        for k in SCENARIO_KEYS:
            if k not in m or k in _skip: continue
            new_v = tuple(m[k]) if k == "control_zones" else m[k]
            if k in ("site_years", "site_start", "site_years_setting", "site_start_setting") and isinstance(new_v, dict):   # v20.57: JSON
                new_v = {int(kk): (int(vv) if k.startswith("site_years") else [int(x) for x in vv])   # writes the site ids as TEXT keys;
                         for kk, vv in new_v.items() if vv is not None}                         # build_treatment_columns maps the
                # integer site_id -- with text keys every site fell back to the single treatment year, so a pooled run with
                # per-site (staggered) years used ONE year
            if k == "data_keys" and not PANEL_SCENARIO_OVERRIDES_CELL1:    # v20.57: an option CELL 1 set keeps its own form;
                _set = {x for x in ("control_zones", "pre_years", "post_years", "seasons") if x in _EXPLICIT_KEYS}   # one it left
                _mine = set(ACTIVE.get("data_keys") or []) & _set                                                    # unset takes
                new_v = sorted(_mine | (set(new_v or []) - _set))                                                    # the saved form
                if new_v != list(ACTIVE.get("data_keys") or []): adopted.append(f"data options = {new_v!r}")
                ACTIVE[k] = new_v; continue
            if k in _EXPLICIT_KEYS and not PANEL_SCENARIO_OVERRIDES_CELL1:
                if new_v != ACTIVE.get(k): kept.append(f"{k} = {ACTIVE.get(k)!r} (panel preparation: {new_v!r})")
                continue
            if new_v != ACTIVE.get(k): adopted.append(f"{k} = {new_v!r}")
            ACTIVE[k] = new_v
        if "seasons" in m and ("seasons" not in _EXPLICIT_KEYS or PANEL_SCENARIO_OVERRIDES_CELL1): _SEASON_CHOICE.clear()
        if "exclude_gapfilled" in ACTIVE:                          # v20.57: the loader reads the engine flag -- kept in step
            globals()["EXCLUDE_GAPFILLED"] = bool(ACTIVE["exclude_gapfilled"])
        if "timing" not in m and m.get("use_site_years") and "timing" not in _EXPLICIT_KEYS:   # v20.57: a v20.56 file said
            ACTIVE["timing"] = "registry"; adopted.append("timing = 'registry' (the saved use_site_years = True)")   # "per-site years"
        _force_negative_from_active()
        if verbose:
            if kept: info("CELL 1 wins over panel preparation for: " + "; ".join(kept))
            if adopted: info("taken from panel preparation (not set in CELL 1): " + "; ".join(adopted))
            if _design_is_resolved():
                info(f"scenario in force: {scenario_tag()} (panel file {p})")
            else:                                              # v20.58: no folder tag of an unresolved timing (was "..._fundMissing_...")
                info(f"scenario options after the panel preparation: control rings {ACTIVE['control_zones']} | {_timing_request_text()} | "
                     f"years {year_window_text()} (panel file {p}); the design in force is resolved and printed at STEP 1")
    return m

# ====================== v20.57: THE DESIGN IS RESOLVED WHEN THE MODEL RUNS ======================
# Every option of the design is set in the MODEL notebook (CELL 1: set_scenario) and turned into the design the estimators use
# HERE, on the panel P00 built once -- change any option and re-run the model; P00 is never re-run for it:
#   TREATMENT_TIMING  "fund"     each sub-watershed's first treated SEASON from your fund workbook (_fund.py: the release timing
#                                back-cast before the file's first month, the season AFTER the start month -- no anticipation)
#                     "registry" its implementation year in data/sites/sites.csv       "fixed"  TREATMENT_YEAR for every one
#   the dose          the fund file's amount released by the end of the previous season / the treatment area (every timing)
#   FRAGMENT_RULE     "drop": the major sub-watershed data only (fragments of other sub-watersheds out, core or ring alike)
#   CONTROL_ZONES / PRE_YEARS / POST_YEARS = "data", SEASONS = "auto"   chosen from the data (DESIGN_MODE = "recommended")
# What you set is what runs: DESIGN_IN_EFFECT (printed, and saved next to every result) lists each option as you set it, the
# value in force and where it came from; validate_design_options.py proves it option by option (and R == Python).
_RESOLVED = {"key": None, "choices": [], "notes": []}
_REC_CACHE = {}
_FRAG_CACHE = {}
_PANEL_YEARS = {}
LAST_DESIGN_CHOICES = []

def _pq_close(pf):
    try: pf.close()
    except Exception: pass

def panel_years(path=None):
    """The Years present in the panel (parquet statistics; the Year column itself when a file has none). Cached per file."""
    import pyarrow.parquet as pq
    p = path or PREPARED_PANEL
    key = tuple(_panel_identity(p).values())
    if key in _PANEL_YEARS: return list(_PANEL_YEARS[key])
    yrs = set()
    if os.path.exists(p):
        pf = pq.ParquetFile(p)
        try:
            if "Year" in pf.schema_arrow.names:
                j = pf.schema_arrow.names.index("Year"); lo = hi = None; stats_ok = pf.num_row_groups > 0
                for i in range(pf.num_row_groups):
                    st = pf.metadata.row_group(i).column(j).statistics
                    if st is None or not st.has_min_max: stats_ok = False; break
                    lo = st.min if lo is None else min(lo, st.min); hi = st.max if hi is None else max(hi, st.max)
                if stats_ok and lo is not None:
                    yrs = set(range(int(lo), int(hi) + 1))
                else:
                    for i in range(pf.num_row_groups):
                        yrs.update(int(x) for x in pd.unique(pf.read_row_group(i, columns=["Year"]).column(0).to_numpy(zero_copy_only=False)))
        finally:
            _pq_close(pf)
    _PANEL_YEARS[key] = sorted(yrs)
    return list(_PANEL_YEARS[key])

# ====================== v20.58: THE LOCATION RULE -- YOUR RULE: only the CURRENT sub-watershed's own data ======================
# (_location.py; the same rule and codes as R's lib/reward_design.R): the rows of sub-watersheds this run does not process, rows OUTSIDE
# every polygon, overlapping / repeated / near-duplicate pixels and pixels whose ring the exports disagree on leave EVERY group --
# treated and control, pre and post (FRAGMENT_RULE / OVERLAP_ROWS "drop"). Until v20.57 the per-FILE fragment codes decided: the rows
# outside every polygon of a NAMED file stayed in, and rows with no sub-watershed (site 0) counted as a second sub-watershed in the
# design-based SE ("2 sub-watersheds" on a one-sub-watershed panel).
_LOC_CACHE = {}
LOCATION_COLUMNS = ("site_id", "site_check", "pixel_id", "buff_km", "Year", "Season")   # what the location rule reads when present

def _location_cache_file(p):
    return os.path.join(os.path.dirname(os.path.abspath(p)), "LOCATION_TABLE.json")

def _overlap_min():
    try:
        import _prep_common as _Pp; return float(getattr(_Pp, "PIXEL_OVERLAP_MIN", 0.65))
    except Exception:
        return 0.65

def location_table(path=None, verbose=False):
    """The panel's location facts, once per panel version (LOCATION_TABLE.json next to the panel): each sub-watershed's OWN rows (inside
    its polygons), the rows per (sub-watershed, overlay check), the pixels whose ring differs between rows, and the pixel pairs whose
    footprints still overlap >= PIXEL_OVERLAP_MIN (P00 merges them -- this CONFIRMS it; the smaller of any remaining pair leaves)."""
    import pyarrow.parquet as pq, pyarrow as pa, pyarrow.compute as pc, time as _t
    import _location as _L
    p = path or PREPARED_PANEL
    ident = _panel_identity(p); key = (tuple(ident.values()), _overlap_min())
    if key in _LOC_CACHE: return _LOC_CACHE[key]
    out = {"mode": "none", "own": {}, "by_site_check": [], "ring_conflict": set(), "near_dup": {}, "n_pixels": 0, "n_pairs": 0, "seconds": 0.0}
    if not os.path.exists(p): return out
    cf = _location_cache_file(p)
    try:
        if os.path.exists(cf):
            j = json.load(open(cf, encoding="utf-8"))
            if (j.get("panel") == ident["panel"] and j.get("panel_mtime") == ident["panel_mtime"] and j.get("panel_bytes") == ident["panel_bytes"]
                    and j.get("overlap_min") == _overlap_min() and j.get("rule") == "v20.58"):
                out = {"mode": j["mode"], "own": {int(k): float(v) for k, v in j["own"].items()}, "by_site_check": [tuple(x) for x in j["by_site_check"]],
                       "ring_conflict": set((int(a_), int(b_)) for a_, b_ in j["ring_conflict"]), "near_dup": {int(a_): int(b_) for a_, b_ in j["near_dup"]},
                       "n_pixels": int(j["n_pixels"]), "n_pairs": int(j["n_pairs"]), "seconds": float(j.get("seconds", 0))}
                _LOC_CACHE[key] = out; return out
    except Exception:
        pass
    t0 = _t.time()
    pf = pq.ParquetFile(p); names = pf.schema_arrow.names
    try:
        if "site_id" not in names:
            _LOC_CACHE[key] = out; return out
        cols = [c for c in ("site_id", "site_check", "pixel_id", "buff_km", "latitude", "longitude") if c in names]
        nrg = pf.num_row_groups; nrows = pf.metadata.num_rows
    finally:
        _pq_close(pf)
    # v20.58: the whole table at once when it fits below 98 % of the RAM; beyond it (or forced: the checks) row group by row group --
    # the same exact aggregates (counts, min / max rings, per-pixel coordinate sums) merged as they come: every row, nothing sampled
    try:
        import _hardware as _Hl, _outofcore as _Ol
        _stream = bool(_Ol.forced()) or not _Hl.fits(float(nrows) * len(cols) * 8.0 * 4.0)
    except Exception:
        _stream = False
    if _stream: info(f"location table: {nrows:,} rows read row group by row group (all at once would pass 98 % of the RAM) -- exact")
    def _tables():
        pf_ = pq.ParquetFile(p)
        try:
            if not _stream:
                yield (pa.concat_tables([pf_.read_row_group(i, columns=cols) for i in range(nrg)]) if nrg else pf_.schema_arrow.empty_table()); return
            for i in range(nrg): yield pf_.read_row_group(i, columns=cols)
        finally:
            _pq_close(pf_)
    has_c = "site_check" in cols; has_b = "buff_km" in cols; has_ll = {"latitude", "longitude"} <= set(cols)
    bsc_p, rc_p, reg_p = [], [], []
    def _compact():
        if len(bsc_p) > 1:
            x = pa.concat_tables(bsc_p).group_by(["s", "c"]).aggregate([("n", "sum")]).select(["s", "c", "n_sum"]).rename_columns(["s", "c", "n"]); bsc_p[:] = [x]
        if len(rc_p) > 1:
            x = pa.concat_tables(rc_p).group_by(["site_id", "pixel_id"]).aggregate([("bmin", "min"), ("bmax", "max")]).select(
                ["site_id", "pixel_id", "bmin_min", "bmax_max"]).rename_columns(["site_id", "pixel_id", "bmin", "bmax"]); rc_p[:] = [x]
        if len(reg_p) > 1:
            x = pa.concat_tables(reg_p).group_by(["pixel_id"]).aggregate([("slat", "sum"), ("nlat", "sum"), ("slon", "sum"), ("nlon", "sum"), ("n", "sum")]).select(
                ["pixel_id", "slat_sum", "nlat_sum", "slon_sum", "nlon_sum", "n_sum"]).rename_columns(["pixel_id", "slat", "nlat", "slon", "nlon", "n"]); reg_p[:] = [x]
    for j, t in enumerate(_tables()):
        site = pc.fill_null(pc.cast(t["site_id"], pa.int64()), 0)
        chk = pc.fill_null(pc.cast(t["site_check"], pa.int64()), 4) if has_c else pa.array(np.full(t.num_rows, 4, np.int64))
        bsc_p.append(pa.table({"s": site, "c": chk}).group_by(["s", "c"]).aggregate([("s", "count")]).select(["s", "c", "s_count"]).rename_columns(["s", "c", "n"]))
        inside = pc.not_equal(chk, 3)
        ti = pa.table({"site_id": site, "pixel_id": pc.cast(t["pixel_id"], pa.int64()) if "pixel_id" in t.column_names else pa.array(np.zeros(t.num_rows, np.int64)),
                       "buff_km": pc.cast(t["buff_km"], pa.int64()) if has_b else pa.array(np.zeros(t.num_rows, np.int64)),
                       **({"lat": t["latitude"], "lon": t["longitude"]} if has_ll else {})}).filter(inside)
        if has_b and ti.num_rows:
            rc_p.append(ti.group_by(["site_id", "pixel_id"]).aggregate([("buff_km", "min"), ("buff_km", "max")]).select(
                ["site_id", "pixel_id", "buff_km_min", "buff_km_max"]).rename_columns(["site_id", "pixel_id", "bmin", "bmax"]))
        if has_ll and ti.num_rows:
            reg_p.append(ti.group_by(["pixel_id"]).aggregate([("lat", "sum"), ("lat", "count"), ("lon", "sum"), ("lon", "count"), ("pixel_id", "count")]).select(
                ["pixel_id", "lat_sum", "lat_count", "lon_sum", "lon_count", "pixel_id_count"]).rename_columns(["pixel_id", "slat", "nlat", "slon", "nlon", "n"]))
        del t, ti
        if (j + 1) % 16 == 0: _compact()
    _compact()
    bsc = bsc_p[0].to_pandas() if bsc_p else pd.DataFrame(columns=["s", "c", "n"])
    own = bsc[(bsc.s > 0) & bsc.c.isin(_L.IN_POLYGON)].groupby("s")["n"].sum()
    rc = set()
    if rc_p:
        g = rc_p[0].to_pandas(); g = g[g["bmin"] != g["bmax"]]
        rc = set(zip(g["site_id"].astype(int).tolist(), g["pixel_id"].astype(np.int64).tolist()))
    nd = {}; npx = 0; npairs = 0
    if reg_p:
        rg_ = reg_p[0].to_pandas()
        reg = pd.DataFrame({"pixel_id": rg_["pixel_id"].values, "lat": rg_["slat"].values / rg_["nlat"].replace(0, np.nan).values,
                            "lon": rg_["slon"].values / rg_["nlon"].replace(0, np.nan).values, "n_rows": rg_["n"].values})
        reg = reg[np.isfinite(reg.lat.values) & np.isfinite(reg.lon.values)].sort_values("pixel_id").reset_index(drop=True); npx = len(reg)
        try:
            import _prep_common as _Pp
            pairs = _Pp.near_duplicate_pairs(reg, overlap_min=_overlap_min()); npairs = int(len(pairs))
            nd = _L.near_dup_losers(reg, pairs)
        except Exception as e:
            warn(f"near-duplicate check skipped ({type(e).__name__}: {str(e)[:80]})")
    out = {"mode": "overlay" if "site_check" in names else "ids only (no site_check: every row counts as inside its sub-watershed)",
           "own": {int(k): float(v) for k, v in own.items()}, "by_site_check": [(int(a_), int(b_), int(c_)) for a_, b_, c_ in bsc[["s", "c", "n"]].values.tolist()],
           "ring_conflict": rc, "near_dup": nd, "n_pixels": int(npx), "n_pairs": int(npairs), "seconds": round(_t.time() - t0, 1)}
    try:
        json.dump({**ident, "rule": "v20.58", "overlap_min": _overlap_min(), "mode": out["mode"], "own": {str(k): v for k, v in out["own"].items()},
                   "by_site_check": out["by_site_check"], "ring_conflict": [list(x) for x in sorted(rc)], "near_dup": [[int(a_), int(b_)] for a_, b_ in nd.items()],
                   "n_pixels": out["n_pixels"], "n_pairs": out["n_pairs"], "seconds": out["seconds"], "written": _ts()}, open(cf, "w", encoding="utf-8"))
    except Exception:
        pass
    n_out = sum(n for s_, c_, n in out["by_site_check"] if c_ == 3)
    if verbose or True:
        info(f"location table of this panel (once; {out['seconds']:.0f} s): {n_out:,} rows outside every polygon, {len(rc):,} pixel(s) whose ring differs "
             f"between rows, {npairs:,} near-duplicate pixel pair(s) >= {100 * _overlap_min():.0f} % of {npx:,} pixels")
    _LOC_CACHE[key] = out
    return out

def _sws_names_map():
    try:
        import _sites as _S; return {int(k): str(_S.name(int(k))) for k in range(1, 21)}
    except Exception:
        return {}

def _name_to_site(name):
    try:
        L = _sws_locator_common()
        if L is not None:
            sid = L.site_id_for_name(name)
            if sid: return int(sid)
    except Exception:
        pass
    try:
        import _sites as _S; sid = _S.site_id(name); return int(sid) if sid else None
    except Exception:
        return None

def _sws_locator_common():
    try:
        import _prep_common as _Pp; return _Pp._sws_locator()
    except Exception:
        return None

def processing_sites(tab=None, verbose=False):
    """(sites, how): the sub-watersheds THIS run processes -- SITE_FILTER (the MS01 loop) first, else SUB_WATERSHEDS."""
    import _location as _L
    tab = tab if tab is not None else location_table()
    if SITE_FILTER is not None:
        want = [int(SITE_FILTER)] if np.isscalar(SITE_FILTER) else [int(x) for x in SITE_FILTER]
        return sorted(want), "SITE_FILTER (the multi-site loop): " + ", ".join(f"{_sws_names_map().get(k, k)} ({k})" for k in sorted(want))
    try:
        return _L.processing_set(tab.get("own", {}), ACTIVE.get("sub_watersheds", "data"), float(ACTIVE.get("fragment_min_share", 0.05)),
                                 name_to_id=_name_to_site, names=_sws_names_map())
    except ValueError as e:
        raise InsufficientDataError(str(e))

def location_codes(frame, tab=None, S=None, pooled=True):
    """The location code of every row of `frame` (0 kept ... 4); S = the processing set (default processing_sites())."""
    import _location as _L
    tab = tab if tab is not None else location_table()
    if "site_id" not in frame.columns: return np.zeros(len(frame), dtype=np.int8)
    if tab.get("mode") == "none":
        # v20.58: a frame WITHOUT a panel (built directly, a check): the rules that need the frame only -- a control row of a pixel treated in
        # another sub-watershed and a repeated pixel-year-season (code 3), a pixel whose ring differs between its rows (code 4); the polygon
        # rules (codes 1 / 2) need the panel's location table. CLEAN_CONTROLS = False switches this off (v20.35's switch).
        if not CLEAN_CONTROLS or "pixel_id" not in frame.columns: return np.zeros(len(frame), dtype=np.int8)
        rc = set()
        if "buff_km" in frame.columns:
            _g = pd.DataFrame({"s": pd.to_numeric(frame["site_id"], errors="coerce").fillna(0).astype(np.int64).values, "p": frame["pixel_id"].values,
                               "b": pd.to_numeric(frame["buff_km"], errors="coerce").values}).groupby(["s", "p"])["b"].nunique()
            rc = set(_g.index[_g.values > 1].tolist())
        g = lambda c, fill=None: frame[c].values if c in frame.columns else (np.full(len(frame), fill) if fill is not None else None)
        return _L.row_codes(g("site_id"), g("site_check", 4), g("pixel_id", 0), g("buff_km", -1), g("Year", 0), g("Season", 0), None,
                            ring_conflict=rc, near_dup=None, pooled_checks=pooled)
    if S is None: S = processing_sites(tab)[0]
    g = lambda c, fill=None: frame[c].values if c in frame.columns else (np.full(len(frame), fill) if fill is not None else None)
    return _L.row_codes(g("site_id"), g("site_check", 4), g("pixel_id", 0), g("buff_km", -1), g("Year", 0), g("Season", 0), S,
                        ring_conflict=tab.get("ring_conflict"), near_dup=set(tab.get("near_dup", {}).keys()), pooled_checks=pooled)

def location_drop_codes():
    return tuple(([1, 2] if ACTIVE.get("fragment_rule", "drop") == "drop" else []) + ([3, 4] if ACTIVE.get("overlap_rows", "drop") == "drop" else []))

def location_mask(frame, tab=None, S=None, pooled=True):
    """(keep, codes) under FRAGMENT_RULE / OVERLAP_ROWS."""
    codes = location_codes(frame, tab, S, pooled)
    dc = location_drop_codes()
    return (~np.isin(codes, dc)) if dc else np.ones(len(codes), dtype=bool), codes

def location_report_lines(counts, label=""):
    """counts: {(code, treated, post): n} -> the printed lines (as R)."""
    import _location as _L
    dc = location_drop_codes()
    for k in sorted({c for c, _, _ in counts}):
        g = lambda t, p_: int(counts.get((k, t, p_), 0))
        n = sum(v for (c, _, _), v in counts.items() if c == k)
        (info if k in dc else warn)(f"{label}{n:,} rows {'left out' if k in dc else 'KEPT (your option)'} -- {_L.TEXT[k]} "
                                    f"(treated pre {g(True, False):,} / post {g(True, True):,}, control pre {g(False, False):,} / post {g(False, True):,})")

# v20.57 names kept for callers written against them: the per-file fragment table is a REPORT since v20.58 (P00's site_tagging);
# fragment_table() / fragment_mask() now return the LOCATION rule's table and mask
def fragment_table(path=None, verbose=False):
    return location_table(path, verbose)

def fragment_mask(frame, table=None):
    return location_mask(frame, table)

def _fragment_cache_file(p):
    """v20.57 name kept (nothing removed): the file of the panel's location table since v20.58 (LOCATION_TABLE.json)."""
    return _location_cache_file(p)

def _fragment_report(tab):
    """v20.57 name kept (nothing removed): the summary of a location table -- each processed candidate's own rows, the rows outside every
    polygon, the pixels whose ring differs between rows and the near-duplicate pixels (what the location rule leaves out)."""
    tab = tab or {}
    own = tab.get("own", {}) or {}
    if not own:
        info("location table: the panel has no sub-watershed columns -- nothing to check"); return
    nm = _sws_names_map(); n_out = sum(n for s_, c_, n in tab.get("by_site_check", []) if c_ == 3)
    parts = [f"{nm.get(int(k), 'site ' + str(int(k)))} {int(v):,}" for k, v in sorted(own.items(), key=lambda x: -x[1])[:6]]
    info(f"location table ({tab.get('mode', '?')}): own rows per sub-watershed: {', '.join(parts)}; outside every polygon: {n_out:,}; "
         f"pixels whose ring differs between rows: {len(tab.get('ring_conflict', ()) or ()):,}; near-duplicate pixels left out: {len(tab.get('near_dup', {}) or {}):,}")

FRAGMENT_COLUMNS = LOCATION_COLUMNS

def recommend_design_cached(outcome=None, treatment_year=None, path=None, verbose=True):
    """recommend_design once per (panel version, implementation year, fragment rule) -- kept on disk next to the panel so
    the next model does not re-read the panel for it."""
    outcome = outcome or DESIGN_OUTCOME; p = path or PREPARED_PANEL
    T = int(treatment_year or ACTIVE.get("treatment_year") or TREATMENT_YEAR)
    ident = _panel_identity(p)
    key = (tuple(ident.values()), outcome, T, ACTIVE.get("fragment_rule", "drop"), float(ACTIVE.get("fragment_min_share", 0.05)), tuple(_site_list() or ()),
           ACTIVE.get("overlap_rows", "drop"))
    if key in _REC_CACHE: return _REC_CACHE[key]
    import hashlib
    cf = os.path.join(os.path.dirname(os.path.abspath(p)), "design_cache", "rec_" + hashlib.sha1(repr(key).encode()).hexdigest()[:16] + ".json")
    rec = None
    try:
        if os.path.exists(cf):
            j = json.load(open(cf, encoding="utf-8"))
            if j.get("key") == repr(key): rec = j["rec"]
    except Exception:
        rec = None
    if rec is None:
        rec = recommend_design(outcome, treatment_year=T, write=True, verbose=verbose)
        if rec is not None:
            try:
                os.makedirs(os.path.dirname(cf), exist_ok=True)
                json.dump({"key": repr(key), "rec": rec, "written": _ts()}, open(cf, "w", encoding="utf-8"), default=str)
            except Exception:
                pass
    elif verbose:
        info(f"design from the data (cached for this panel, implementation year {T}): pre {rec.get('pre_window')}, post {rec.get('post_window')}, "
             f"control rings {rec.get('control_zones')}, seasons {rec.get('seasons')}")
    _REC_CACHE[key] = rec
    return rec

def _fund_path():
    """The fund workbook of this layout (_paths.FUND_RELEASE_PATH, or set_paths(fund_release=...))."""
    p_ = ACTIVE_PATHS.get("FUND_RELEASE_PATH")
    if not p_:
        try:
            import _paths as _PP; p_ = _PP.derive().get("FUND_RELEASE_PATH")
        except Exception:
            p_ = None
    return p_

def fund_tables_in_force(years=None, verbose=False):
    """The fund workbook's (timing, season dose, series) under the fund options in force (None when the file is absent)."""
    import _fund as _F
    path = _fund_path()
    if not path or not os.path.exists(path): return None
    yrs = years or panel_years() or list(range(2010, 2036))
    try:
        return _F.fund_tables(path, yrs, rule=ACTIVE.get("fund_start_rule"), share=ACTIVE.get("fund_start_share"),
                              rate_months=ACTIVE.get("fund_rate_months"), before_file=ACTIVE.get("fund_dose_before_file"),
                              crosswalk=None, verbose=verbose)
    except Exception as e:
        warn(f"fund workbook {path}: {type(e).__name__}: {str(e)[:160]} -- no fund timing or dose")
        return None

def _design_key(frame_sites=None):
    """What the resolution depends on: every setting, the panel version, the fund file version and the sites selected."""
    import _fund as _F
    keys = ("design_mode", "data_keys", "timing", "treatment_year_setting", "post_cutoff_setting", "seasons_setting",
            "site_years_setting", "site_start_setting", "fragment_rule", "fragment_min_share", "sub_watersheds", "dose_variable", "fund_start_rule",
            "fund_start_share", "fund_rate_months", "fund_dose_before_file", "exclude_transition_year", "overlap_rows",
            # v20.59 (found by the self-check): the cache restores the RESOLVED snapshot on a hit, so every raw setting the snapshot carries must be
            # part of the key -- before, CELL 1 re-run in the same kernel with another OUTCOME_SCREEN / EXCLUDE_GAPFILLED / COVARIATES / DESIGN_SOURCE
            # kept the OLD value silently (the design key had not changed)
            "design_source", "outcome_screen", "exclude_gapfilled", "covariates", "cluster", "pooled_fe", "unit_fe", "cohort_offset", "nonnegative")
    k = {x: ACTIVE.get(x) for x in keys}
    dk = set(ACTIVE.get("data_keys") or [])
    if "control_zones" not in dk: k["control_zones"] = list(ACTIVE["control_zones"])
    for x in ("pre_years", "post_years", "year_min", "year_max"):
        if not (dk & {"pre_years", "post_years"}): k[x] = ACTIVE.get(x)
    k["panel"] = _panel_identity(); k["fund"] = _F.file_identity(_fund_path()) if _fund_path() else None
    k["sites"] = _site_list(); k["frame_sites"] = frame_sites
    return json.dumps(k, sort_keys=True, default=str)

def resolve_design(verbose=True, force=False, frame=None):
    """v20.57: the design of THIS run, from the options set in the model (CELL 1). Idempotent and cached: called by CELL 1 and
    again by every loader / estimator entry point, it re-resolves only when a setting, the panel or the fund file changed."""
    import _fund as _F
    frame_sites = None
    if not os.path.exists(PREPARED_PANEL) and frame is not None and "site_id" in getattr(frame, "columns", ()):
        frame_sites = sorted(int(x) for x in pd.unique(pd.to_numeric(frame["site_id"], errors="coerce").fillna(0).astype(int)))
    key = _design_key(frame_sites)
    if not force and _RESOLVED.get("key") == key and _RESOLVED.get("active") is not None:
        # v20.58: the cache holds the RESOLVED design and restores it -- v20.57 returned ACTIVE as it was, but CELL 1 of the NEXT notebook in the
        # same kernel (MS01, the test harness) had reset it with set_scenario: the fund timing then silently became TREATMENT_YEAR ("fundMissing")
        import copy as _cp
        ACTIVE.clear(); ACTIVE.update(_cp.deepcopy(_RESOLVED["active"])); return dict(ACTIVE)
    choices, notes = [], []
    def ch(option, setting, used, source): choices.append({"option": option, "your_setting": str(setting), "used": str(used), "from": source})
    # ---- the sub-watersheds this run estimates (after the fragment rule; SITE_FILTER respected)
    if os.path.exists(PREPARED_PANEL):                          # v20.58: the location rule's processing set
        tab = location_table()
        sites = sites_in_panel(after_fragments=True)
        _ps_how = processing_sites(tab)[1] if tab.get("mode") != "none" else "no sub-watershed id in the panel"
    else:
        tab = {"mode": "none", "own": {}, "by_site_check": [], "ring_conflict": set(), "n_pairs": 0}
        sites = frame_sites or []; _ps_how = "the frame's sub-watersheds (no panel file)"
    if _site_list() is not None: sites = [s for s in sites if s in _site_list()]
    real = [int(s) for s in sites if int(s) > 0]
    ty_set = int(ACTIVE.get("treatment_year_setting") or TREATMENT_YEAR)
    pc_set = ACTIVE.get("post_cutoff_setting")
    t = ACTIVE.get("timing", "fixed")
    ch("DESIGN_MODE", ACTIVE.get("design_mode"), ACTIVE.get("design_mode"), "your setting")
    try:
        import _sites as _S
    except Exception:
        _S = None
    def reg_year(s):
        y = _S.treatment_year(s, None) if _S is not None else None
        return (int(y), _S.treatment_year_source(s)) if y is not None else (ty_set, f"TREATMENT_YEAR {ty_set} (neither the fund file nor the registry dates it)")
    per_site = []
    # ---- 1. timing
    if t == "fund":
        ss = {}
        if ACTIVE.get("site_start_setting"):                          # given by hand (tests, or your own season starts)
            for k_, v_ in ACTIVE["site_start_setting"].items():
                if not real or int(k_) in real: ss[int(k_)] = [int(v_[0]), int(v_[1])]; per_site.append((int(k_), f"{_F.SEASON_NAME[int(v_[1])]} {int(v_[0])}", "your site_start"))
        else:
            got = fund_tables_in_force(verbose=verbose)
            if got is not None:
                tim = got[0]
                for r in tim.itertuples():
                    if (not real or int(r.site_id) in real) and pd.notna(r.first_treated_year):
                        ss[int(r.site_id)] = [int(r.first_treated_year), int(r.first_treated_season)]
                        per_site.append((int(r.site_id), r.first_treated_label, f"fund file: start {r.start_month} ({r.start_rule}; {r.start_how[:60]})"))
            else:
                notes.append(f"the fund workbook {_fund_path()} is not available: every sub-watershed falls back to its registry year")
        ACTIVE["n_fund_dated"] = len(ss)                                  # dated by the fund file (or your site_start), before any fallback
        for s in real:
            if s not in ss:
                y, src = reg_year(s); ss[s] = [int(y), 3]                     # a year alone = Zaid of that year: the whole year
                per_site.append((s, f"Zaid {y} (whole year)", f"NOT in the fund file -> {src}"))
                notes.append(f"sub-watershed {s} is not dated by the fund file: {src} {y} is used")
        ACTIVE["site_start"] = ss
        ACTIVE["site_years"] = {k_: int(v_[0] + (1 if int(v_[1]) == 2 else 0)) for k_, v_ in ss.items()}
        ACTIVE["use_site_years"] = bool(ss)
        base = min(v_[0] for v_ in ss.values()) if ss else ty_set
        if not ss: notes.append(f"no sub-watershed id in the panel: every row uses TREATMENT_YEAR {ty_set}")
        ACTIVE["treatment_year"] = ACTIVE["post_cutoff"] = int(base)
        ch("TREATMENT_TIMING", "fund", "fund: first treated season per sub-watershed",
           "your site_start" if ACTIVE.get("site_start_setting") else f"the fund workbook {_fund_path()}")
    elif t == "registry":
        sy = {}
        given = ACTIVE.get("site_years_setting") or {}
        for s in (real or [int(k_) for k_ in given]):
            if int(s) in given: sy[int(s)] = int(given[int(s)]); per_site.append((int(s), str(given[int(s)]), "your site_years"))
            else:
                y, src = reg_year(int(s)); sy[int(s)] = int(y); per_site.append((int(s), str(y), src))
                if "TREATMENT_YEAR" in src: notes.append(f"sub-watershed {s}: implementation year UNKNOWN -> {src}")
        ACTIVE["site_start"] = {}; ACTIVE["site_years"] = sy; ACTIVE["use_site_years"] = bool(sy)
        base = min(sy.values()) if sy else ty_set
        ACTIVE["treatment_year"] = ACTIVE["post_cutoff"] = int(base)
        ch("TREATMENT_TIMING", "registry", "registry: implementation year per sub-watershed", "data/sites/sites.csv" + (" + your site_years" if given else ""))
    else:
        ACTIVE["site_start"] = {}; ACTIVE["site_years"] = {}; ACTIVE["use_site_years"] = False
        ACTIVE["treatment_year"] = ty_set; ACTIVE["post_cutoff"] = int(pc_set) if pc_set is not None else ty_set
        ch("TREATMENT_TIMING", "fixed", f"fixed: {ty_set} for every sub-watershed", "your TREATMENT_YEAR")
    if t != "fund": ACTIVE["n_fund_dated"] = 0
    ch("TREATMENT_YEAR", ty_set, ACTIVE["treatment_year"], "your setting" if t == "fixed" else
       f"the earliest first treated year of the {len(per_site)} sub-watershed(s) (the base of PRE_YEARS / POST_YEARS); yours = the fallback")
    for s, lab, src in per_site:
        ch(f"  start of sub-watershed {s}", f"(from TREATMENT_TIMING = {t})", lab, src)
    # ---- 2. the options set to "data" (DESIGN_MODE = "recommended") -- chosen from the DATA, never from the effect
    dk = set(ACTIVE.get("data_keys") or [])
    rec = None; usable = False
    if dk:
        if ACTIVE.get("design_mode", "recommended") == "recommended" and os.path.exists(PREPARED_PANEL):
            rec = recommend_design_cached(DESIGN_OUTCOME, ACTIVE["treatment_year"], verbose=verbose)
            usable = bool(rec and rec.get("pre_window") and rec.get("post_window"))
            if not usable:
                notes.append("the data-driven design found no usable pre AND post window" + (f" (export breaks {rec.get('breaks')}, fill years {rec.get('fill_years')})" if rec else "")
                             + " -> every ring / every year is used for the options set to 'data'")
        src_d = (f"the data (DESIGN_RECOMMENDATION.md, {DESIGN_OUTCOME}, implementation year {ACTIVE['treatment_year']})" if usable
                 else ("DESIGN_MODE = 'manual': 'data' = every ring / every year" if ACTIVE.get("design_mode") == "manual" else "no usable data-driven window: every ring / every year"))
        if "control_zones" in dk:
            ACTIVE["control_zones"] = parse_control_zones(rec["control_zones"]) if usable else tuple(DEFAULT_CONTROL_ZONES)
        if "pre_years" in dk:
            ACTIVE["pre_years"] = None; ACTIVE["year_min"] = int(min(rec["pre_window"])) if usable else None
        if "post_years" in dk:
            ACTIVE["post_years"] = None; ACTIVE["year_max"] = int(max(rec["post_window"])) if usable else None
        if "seasons" in dk:
            ACTIVE["seasons"] = normalize_seasons(rec["seasons"]) if usable else "all"; _SEASON_CHOICE.clear()
        if dk & {"pre_years", "post_years"} and usable and screen_rule() == "drop":   # v20.59: OUTCOME_SCREEN keep / off keeps the fill years too
            lo_, hi_ = scenario_years()
            ACTIVE["drop_years"] = sorted(int(y) for y in (rec.get("fill_years") or []) if (lo_ is None or y >= lo_) and (hi_ is None or y <= hi_))
        else:
            ACTIVE["drop_years"] = []
    else:
        ACTIVE["drop_years"] = []
        src_d = "your setting"
    _cz = ACTIVE["control_zones"]
    ch("CONTROL_ZONES", "data" if "control_zones" in dk else list(_cz), list(_cz), src_d if "control_zones" in dk else "your setting")
    lo_, hi_ = scenario_years()
    # v20.59: a calendar-year bound that leaves no year on its side of the start (PRE_YEARS = 2022 with the start in 2022) is said, never applied
    _dlo, _dhi = year_window_dropped(); _base_ = int(ACTIVE["treatment_year"]); _pre_txt, _post_txt = year_window_setting_text()
    _how_lo = "your setting"; _how_hi = "your setting"
    if _dlo is not None:
        notes.append(f"PRE_YEARS = {_dlo} leaves NO year before the start {_base_} (a calendar year at or after it): every year before the start is used "
                     f"instead. Set PRE_YEARS to the FIRST pre year (e.g. {_base_ - 7}), to a number of years before the start (e.g. 7) or 'all'")
        _how_lo = f"PRE_YEARS {_dlo} is not before the start {_base_} -> every year before it"
    if _dhi is not None:
        notes.append(f"POST_YEARS = {_dhi} leaves NO year from the start {_base_} on (a calendar year before it): every year from the start is used "
                     f"instead. Set POST_YEARS to the LAST post year (e.g. {_base_ + 3}), to a number of years from the start (e.g. 2) or 'all'")
        _how_hi = f"POST_YEARS {_dhi} is before the start {_base_} -> every year from it"
    ch("PRE_YEARS", _pre_txt, f"from {lo_}" if lo_ is not None else "every year before the start", src_d if "pre_years" in dk else _how_lo)
    ch("POST_YEARS", _post_txt, f"to {hi_}" if hi_ is not None else "every year from the start", src_d if "post_years" in dk else _how_hi)
    if ACTIVE.get("drop_years"):
        ch("  years left out", "(from PRE_YEARS / POST_YEARS = data)", ACTIVE["drop_years"], "fill years of the data-driven window (not data)")
    ch("SEASONS", ACTIVE.get("seasons_setting"), ACTIVE.get("seasons"), src_d if "seasons" in dk else "your setting")
    ch("EXCLUDE_TRANSITION_YEAR", ACTIVE.get("exclude_transition_year"), ACTIVE.get("exclude_transition_year"), "your setting")
    ch("UNIT_FE", ACTIVE.get("unit_fe"), ACTIVE.get("unit_fe"), "your setting")
    ch("COHORT_OFFSET", ACTIVE.get("cohort_offset", 0), ACTIVE.get("cohort_offset", 0), "your setting")
    _bsc = tab.get("by_site_check", []) if isinstance(tab, dict) else []
    _n_out = sum(n for s_, c_, n in _bsc if c_ == 3); _n_oth = sum(n for s_, c_, n in _bsc if c_ != 3 and real and s_ not in real)
    ch("SUB_WATERSHEDS", ",".join(str(x) for x in (ACTIVE.get("sub_watersheds") if isinstance(ACTIVE.get("sub_watersheds"), (list, tuple)) else [ACTIVE.get("sub_watersheds", "data")])),
       real or "none (no sub-watershed id)", _ps_how)
    ch("FRAGMENT_RULE", ACTIVE.get("fragment_rule"), ACTIVE.get("fragment_rule"),
       f"your setting: rows of sub-watersheds NOT processed {_n_oth:,}, rows outside every polygon {_n_out:,} -- "
       f"{'left out' if ACTIVE.get('fragment_rule', 'drop') == 'drop' else 'KEPT'} (treated and control, pre and post)")
    ch("OVERLAP_ROWS", ACTIVE.get("overlap_rows"), ACTIVE.get("overlap_rows"),
       f"your setting: {len(tab.get('ring_conflict', ()) or ()):,} pixel(s) whose ring differs between rows, {int(tab.get('n_pairs', 0)):,} near-duplicate pair(s), "
       f"pixels treated in another processed sub-watershed / repeated -- {'left out' if ACTIVE.get('overlap_rows', 'drop') == 'drop' else 'KEPT'}")
    ch("POOLED_FE", ACTIVE.get("pooled_fe"), ACTIVE.get("pooled_fe") if len(real) > 1 else f"{ACTIVE.get('pooled_fe')} (one sub-watershed: the same as 'period')", "your setting")
    ch("DOSE_VARIABLE", ACTIVE.get("dose_variable"), ACTIVE.get("dose_variable"), "your setting (fund file; controls and untreated periods 0)")
    ch("FUND_START_RULE", ACTIVE.get("fund_start_rule"), ACTIVE.get("fund_start_rule"),
       "your setting" + ("" if t == "fund" else " (used for the dose only: TREATMENT_TIMING is not 'fund')"))
    ch("EXCLUDE_GAPFILLED", ACTIVE.get("exclude_gapfilled", True), ACTIVE.get("exclude_gapfilled", True), "your setting")
    ch("OUTCOME_SCREEN", ACTIVE.get("outcome_screen", OUTCOME_SCREEN), screen_rule(),
       "your setting" + {"drop": " (a year-season constant across pixels -- a fill value -- or with collapsed coverage leaves the model; evidence: OUTCOME_SCREEN_<outcome>.csv)",
                         "keep": " (such year-seasons are reported and KEPT; results tagged _screenKept)", "off": " (no screen)"}[screen_rule()])
    ch("DESIGN_SOURCE", ACTIVE.get("design_source", "model"), ACTIVE.get("design_source", "model"),
       "your setting" + {"panel": " (the PANEL's treat / control / pre / post / did -- the exports' Treat flag, PERIOD_RULE -- are estimated on; the design in effect above is compared with them)",
                         "model": " (the design in effect above is estimated on -- design-based modelling; DESIGN_SOURCE = 'panel' estimates on the panel's columns)"}[ACTIVE.get("design_source", "model")])
    ch("COVARIATES", ",".join(ACTIVE.get("covariates") or []) or "none", ",".join(ACTIVE.get("covariates") or []) or "none", "your setting")
    import copy as _cp
    ACTIVE["n_sites"] = len(real)
    _RESOLVED.update({"key": key, "choices": choices, "notes": notes, "per_site": list(per_site), "n_sites": len(real), "active": _cp.deepcopy(dict(ACTIVE))})
    LAST_DESIGN_CHOICES[:] = choices
    if verbose:
        w = max(len(c["option"]) for c in choices)
        lines = [f"  {c['option']:<{w}}  your setting: {c['your_setting'][:34]:<34}  USED: {c['used'][:48]:<48}  <- {c['from'][:90]}" for c in choices]
        info("DESIGN IN EFFECT (v20.59: every option is applied here, at the model stage -- the panel is not rebuilt; the location rule: only the processed sub-watershed(s)):\n" + "\n".join(lines))
        for n_ in notes: warn(n_)
    return dict(ACTIVE)

def _ensure_resolved(frame=None):
    """v20.57: every entry point makes sure the design in force is the one the settings describe (cheap when nothing changed)."""
    try:
        return resolve_design(verbose=_RESOLVED.get("key") is None, frame=frame)
    except InsufficientDataError:
        raise
    except Exception as e:
        warn(f"the design could not be resolved ({type(e).__name__}: {str(e)[:160]}) -- the values set in CELL 1 are used as they are")
        return dict(ACTIVE)

def timing_table(save_as=None):
    """v20.57: one row per sub-watershed of this run -- the timing in force: first treated season and year, the annual cohort,
    where it came from (fund file / registry / TREATMENT_YEAR)."""
    _ensure_resolved()
    try:
        import _sites as _S; nm = _S.name
    except Exception:
        nm = lambda s_: f"site_{s_}"
    rows = []
    src = {int(s_): (lab, why) for s_, lab, why in (_RESOLVED.get("per_site") or [])}
    sites_ = sorted(set(ACTIVE.get("site_start", {})) | set(ACTIVE.get("site_years", {})) | set(src))
    for s_ in sites_:
        st = ACTIVE.get("site_start", {}).get(s_)
        rows.append({"site_id": int(s_), "sws_name": nm(int(s_)), "timing": ACTIVE.get("timing"),
                     "first_treated_year": int(st[0]) if st else ACTIVE.get("site_years", {}).get(s_),
                     "first_treated_season": ({0: "Yearly", 1: "Kharif", 2: "Rabi", 3: "Zaid"}[int(st[1])] if st else "Zaid (whole year)"),
                     "cohort_annual": ACTIVE.get("site_years", {}).get(s_), "source": src.get(int(s_), ("", ""))[1]})
    if not rows:
        rows.append({"site_id": 0, "sws_name": "", "timing": ACTIVE.get("timing"), "first_treated_year": ACTIVE["treatment_year"],
                     "first_treated_season": "Zaid (whole year)", "cohort_annual": ACTIVE["treatment_year"], "source": "TREATMENT_YEAR"})
    t = pd.DataFrame(rows)
    if save_as:
        os.makedirs(os.path.dirname(save_as), exist_ok=True); t.to_csv(save_as, index=False)
    return t

def design_in_effect():
    """The table DESIGN IN EFFECT: option, your setting, the value used, where it came from."""
    _ensure_resolved()
    return pd.DataFrame(_RESOLVED.get("choices") or [])

def write_design_in_effect(folder):
    """DESIGN_IN_EFFECT.csv / .json next to a model's results -- the audit trail of what this run used."""
    try:
        os.makedirs(folder, exist_ok=True)
        t = pd.DataFrame(_RESOLVED.get("choices") or [])
        if len(t): t.to_csv(os.path.join(folder, "DESIGN_IN_EFFECT.csv"), index=False)
        json.dump({"scenario_tag": scenario_tag(), "active": {k: (list(v) if isinstance(v, tuple) else v) for k, v in ACTIVE.items()},
                   "choices": _RESOLVED.get("choices"), "notes": _RESOLVED.get("notes"), "engine": ENGINE_VERSION, "written": _ts()},
                  open(os.path.join(folder, "DESIGN_IN_EFFECT.json"), "w", encoding="utf-8"), indent=1, default=str)
    except Exception as e:
        warn(f"DESIGN_IN_EFFECT not written to {folder}: {e}")

DOSE_COLUMNS = ("dose_amount_sws", "dose_intensity_per_ha", "dose_share_of_target", "dose_estimated")
_DOSE_NOTICE = []

def attach_fund_dose(out):
    """v20.57: the dose of every row from the fund workbook (site x Year x Season, the options in force) -- 0 for the control
    rings and for untreated periods (the dose belongs to the TREATMENT AREA once treated), NaN where the file cannot say (after
    its last month; before it with FUND_DOSE_BEFORE_FILE = 'missing'). `dose` and the legacy `dose_per_subwshed` = DOSE_VARIABLE."""
    have = {"site_id", "Year", "Season"} <= set(out.columns)
    got = fund_tables_in_force() if have else None
    if got is not None:
        d = got[1]
        kt = (d["site_id"].astype(np.int64).values * 10000 + d["Year"].astype(np.int64).values) * 10 + d["Season"].astype(np.int64).values
        kr = ((pd.to_numeric(out["site_id"], errors="coerce").fillna(0).astype(np.int64).values * 10000
               + pd.to_numeric(out["Year"], errors="coerce").fillna(0).astype(np.int64).values) * 10
              + pd.to_numeric(out["Season"], errors="coerce").fillna(0).astype(np.int64).values)
        idx = pd.Index(kt).get_indexer(kr); hit = idx >= 0
        for c_ in DOSE_COLUMNS:
            v = np.full(len(out), np.nan, dtype=np.float64)
            v[hit] = pd.to_numeric(d[c_], errors="coerce").values.astype(np.float64)[idx[hit]]
            out[c_] = v
    else:                                                  # no fund workbook: the panel's dose columns (P00), said once
        for c_ in DOSE_COLUMNS:
            out[c_] = np.nan if c_ not in out.columns else pd.to_numeric(out[c_], errors="coerce").astype("float64")
        if not _DOSE_NOTICE:
            _DOSE_NOTICE.append(1)
            warn(f"the fund workbook ({_fund_path()}) is not available: the dose is the panel's own "
                 f"{ACTIVE.get('dose_variable', 'dose_intensity_per_ha')} column (P00) where it has one -- set FUND_RELEASE_PATH in _paths.py")
    if "did_term" in out.columns:
        _z = out["did_term"].values != 1
        for c_ in DOSE_COLUMNS:
            v = pd.to_numeric(out[c_], errors="coerce").values.astype(np.float64); v[_z] = 0.0; out[c_] = v
    dv = ACTIVE.get("dose_variable", "dose_intensity_per_ha")
    out["dose"] = out[dv] if dv in out.columns else np.nan
    out["dose_per_subwshed"] = out["dose"]
    return out


def scenario_banner():
    _ensure_resolved()
    lo, hi = scenario_years()
    _t = ACTIVE.get("timing", "fixed")
    _tt = (f"timing FUND (first treated season per sub-watershed: "
           + ", ".join(f"{k}: {_fund_label(k)}" for k in sorted(ACTIVE.get("site_start", {}))[:8]) + ")") if _t == "fund" and ACTIVE.get("site_start") else \
          (f"timing REGISTRY {dict(sorted(ACTIVE.get('site_years', {}).items())[:8])}" if _t == "registry" else f"treatment {ACTIVE['treatment_year']} (post >= {ACTIVE['post_cutoff']})")
    return (f"rings {ACTIVE['control_zones']} | {_tt} | years {year_window_text()}"
            + (f" (without {ACTIVE['drop_years']})" if ACTIVE.get("drop_years") else "") + f" | rows {seasons_mode(verbose=False)}"
            + f" | fragments {ACTIVE.get('fragment_rule', 'drop')} | overlap {ACTIVE.get('overlap_rows', 'drop')} | dose {ACTIVE.get('dose_variable')}"
            + (f" | cohorts {ACTIVE['cohort_offset']:+d}" if ACTIVE.get("cohort_offset") else ""))

def results_dir(model_id, scn=None, make=True):
    global CURRENT_MODEL_ID
    if str(model_id).startswith("M"): CURRENT_MODEL_ID = str(model_id)  # v20.35: which model is loading
    """RESULTS_ROOT/<MODEL_ID>/<scenario tag>. Every model notebook writes here (v20)."""
    if scn is None: _ensure_resolved()                       # v20.57: the folder names the design IN FORCE
    d = os.path.join(RESULTS_ROOT, model_id, scenario_tag(scn))
    if make:
        os.makedirs(d, exist_ok=True)
        if scn is None: write_design_in_effect(d)            # v20.57: what this run used, next to its results
    return d

def scenario_columns_match(df):
    """True when df's treatment columns were built with the ACTIVE scenario (checked against buff_km / Year)."""
    need = {"treatment", "control", "post", "did_term", "in_analysis_sample", "event_time", "treat", "did"}   # v20.59: + the aliases treat / did
    if not need <= set(df.columns) or "buff_km" not in df.columns or "Year" not in df.columns:
        return False
    if len(df) == 0: return True
    h = df.head(20000)
    bk = pd.to_numeric(h["buff_km"], errors="coerce")
    ok_ctrl = bool((h["control"].astype("int8").values == bk.isin(list(ACTIVE["control_zones"])).astype("int8").values).all())
    ok_post = bool((h["post"].astype("int8").values == (h["Year"] >= ACTIVE["post_cutoff"]).astype("int8").values).all())
    ok_et = bool((h["event_time"].values == (h["Year"] - ACTIVE["treatment_year"]).values).all())
    ok_alias = bool((h["treat"].astype("int8").values == h["treatment"].astype("int8").values).all()
                    and (h["did"].astype("int8").values == h["did_term"].astype("int8").values).all())   # v20.59: a stale alias = a rebuild
    return ok_ctrl and ok_post and ok_et and ok_alias

def _drop_years_outside_window(df):
    """v20.2: rows outside the scenario's year window never reach an estimator."""
    if not has_year_window() or "Year" not in df.columns: return df
    m = year_mask(df["Year"].values)
    if not m.all():
        info(f"year window {year_window_text()}: keeping {int(m.sum()):,} of {len(df):,} rows")
        df = df[m]
    return df

def scenario_coverage(df, verbose=True):
    """v20.11: what the estimator will actually see -- printed by every model after the scenario is applied,
    so an empty coefficient can never be a mystery. Returns the counts."""
    if "in_analysis_sample" not in df.columns: return {}
    d = df[df["in_analysis_sample"] == 1]
    cov = {"rows": int(len(d)),
           "treated_pixels": int(d.loc[d["treatment"] == 1, "pixel_id"].nunique()) if "treatment" in d else 0,
           "control_pixels": int(d.loc[d["control"] == 1, "pixel_id"].nunique()) if "control" in d else 0,
           "pre_rows": int((d["post"] == 0).sum()) if "post" in d else 0,
           "post_rows": int((d["post"] == 1).sum()) if "post" in d else 0,
           "treated_post_rows": int(((d.get("treatment", 0) == 1) & (d.get("post", 0) == 1)).sum()),
           "did_term_varies": bool(d["did_term"].nunique() > 1) if "did_term" in d else False,
           "years": (int(d["Year"].min()), int(d["Year"].max())) if len(d) and "Year" in d else None}
    if verbose:
        info(f"coverage under {scenario_banner()}: {cov['rows']:,} rows | treated pixels {cov['treated_pixels']:,} | "
             f"control pixels {cov['control_pixels']:,} | pre rows {cov['pre_rows']:,} | post rows {cov['post_rows']:,} "
             f"| treated x post rows {cov['treated_post_rows']:,} | years {cov['years']}")
        problems = []
        if cov["treated_pixels"] == 0: problems.append("NO treated pixels (buff_km == 0 never occurs in the sample)")
        if cov["control_pixels"] == 0: problems.append("NO control pixels (the chosen rings never occur)")
        if cov["pre_rows"] == 0: problems.append("NO pre-period rows (year window / treatment year leaves no pre period)")
        if cov["post_rows"] == 0: problems.append("NO post-period rows (data ends before the treatment year)")
        if cov["rows"] and not cov["did_term_varies"]: problems.append("did_term has no variation")
        for p in problems: warn(f"   COVERAGE PROBLEM: {p} -> every coefficient will be empty")
    return cov

def apply_scenario(df, force=False):
    """Make df consistent with the ACTIVE scenario. Columns baked into a per-variable estimator file by P09 carry
    the scenario in use when it was built; if you then choose different rings or a different treatment year, they
    are REBUILT here (cheap: two integer comparisons per row) instead of being silently wrong."""
    if force or not scenario_columns_match(df):
        info(f"rebuilding treatment/period columns for scenario {scenario_tag()}")
        df = build_treatment_columns(df)
    df = _drop_years_outside_window(df)
    try: scenario_coverage(df)                              # v20.11: say what the estimator will see (v20.58: its own name -- the
    except Exception: pass                                  #   table version treatment_coverage() below shadowed it and called
    return df                                               #   apply_scenario again: 328 nested copies of the frame per model)

_DESIGN_VS_PANEL_SAID = set()
def _design_timing_text():
    """v20.59: the timing in force, in words, for the design-vs-panel line."""
    t = ACTIVE.get("timing", "fixed")
    if t == "fund": return f"fund timing: the first treated season per sub-watershed, base year {ACTIVE.get('treatment_year')}"
    if t == "registry": return f"registry timing, base year {ACTIVE.get('treatment_year')}"
    return (f"fixed: post = Year >= {ACTIVE.get('post_cutoff')}"
            + (" with the transition year held out" if ACTIVE.get("exclude_transition_year") else ""))

def say_design_vs_panel(n_differ, n_rows):
    """v20.59: the one line every model prints -- the design IN EFFECT against the panel's post column (the exports' Treat flag, P00 /
    R_P00): the same on every row, or on how many rows (and why) they differ. The DESIGN's columns are what the model estimates on."""
    LAST_DESIGN_INFO["post_rows_differ_from_panel"] = int(n_differ); LAST_DESIGN_INFO["post_rows_compared"] = int(n_rows)
    if not n_rows: return
    _src = ACTIVE.get("design_source", "model")
    if n_differ == 0:
        info(f"DESIGN vs PANEL: the design in effect ({_design_timing_text()}) gives the same post period as the panel's post column "
             f"(the exports' Treat flag) on every one of {n_rows:,} rows" + (" -- DESIGN_SOURCE = 'panel': the panel's columns are estimated on" if _src == "panel" else ""))
    elif _src == "panel":
        info(f"DESIGN vs PANEL: DESIGN_SOURCE = 'panel' -- this model estimates on the PANEL's post / pre / did (the exports' Treat flag, PERIOD_RULE); "
             f"the design in effect ({_design_timing_text()}) would differ on {n_differ:,} of {n_rows:,} rows ({n_differ / n_rows:.1%}) -- set DESIGN_SOURCE = 'model' "
             f"to estimate on it (your settings: TREATMENT_TIMING / TREATMENT_YEAR / EXCLUDE_TRANSITION_YEAR)")
    else:
        info(f"DESIGN vs PANEL: the design in effect ({_design_timing_text()}) differs from the panel's post column (the exports' Treat flag, P00) "
             f"on {n_differ:,} of {n_rows:,} rows ({n_differ / n_rows:.1%}) -- DESIGN_SOURCE = 'model': the DESIGN's columns are what this model estimates on "
             f"(your settings: TREATMENT_TIMING / TREATMENT_YEAR / EXCLUDE_TRANSITION_YEAR); DESIGN_SOURCE = 'panel' estimates on the panel's")

def design_vs_panel(out, post_panel, post_design=None):
    """v20.59: compare the design's post with the panel's (None: the frame carried none -- a panel built before v20.59, or a synthetic
    frame); inside an out-of-core worker the counts are recorded and the parent says them once. post_design: the design in effect's post
    when out['post'] already holds the panel's (DESIGN_SOURCE = 'panel')."""
    if post_panel is None:
        LAST_DESIGN_INFO["post_rows_differ_from_panel"] = None; LAST_DESIGN_INFO["post_rows_compared"] = 0
        if not _OOC_WORKER and "no_post" not in _DESIGN_VS_PANEL_SAID and not getattr(out, "attrs", {}).get("synthetic"):
            _DESIGN_VS_PANEL_SAID.add("no_post")
            info("this frame carries no post column of the panel (built before v20.59, or not read): the design in effect is used as it is -- "
                 "re-run P00 to get the exports' design columns (treat, control, pre, post, did) into the panel")
        return
    _pd_ = out["post"].values.astype(np.int8) if post_design is None else np.asarray(post_design, dtype=np.int8)
    n = int(len(out)); k = int((_pd_ != post_panel).sum()) if n else 0
    if _OOC_WORKER:
        LAST_DESIGN_INFO["post_rows_differ_from_panel"] = k; LAST_DESIGN_INFO["post_rows_compared"] = n
    else:
        say_design_vs_panel(k, n)

def build_treatment_columns(df, control_zones=None, treatment_year=None,
                             pre_cutoff=None, post_cutoff=None, year_col="Year",
                             exclude_transition_year=None, copy=False):
    """v14 -- YOUR SPECIFICATION, implemented literally:
        treatment  = 1 where buff_km == 0, else 0
        control    = 1 where buff_km in {1,2,3,4,5}, else 0
        post       = 1 where Year >= 2023, else 0
        pre        = 1 where Year <  2023, else 0            (2022 is PRE, per your latest spec)
        did_term   = treatment * post
    The earlier names (treat_core, control_zone_selected, pre_period, post_period) are kept as
    exact aliases so every model notebook keeps working unchanged.
    exclude_transition_year=True restores the earlier design that drops 2022 from BOTH periods.
    v17.2: columns are added IN PLACE (copy=False) -- a full copy of a 100M-row frame was the first
    of three copies that killed the kernel in M01. The added columns are int8; nothing else changes."""
    # v20: unset arguments come from the ACTIVE scenario (set_scenario in CELL 1); an explicit argument still wins
    _ensure_resolved(frame=df)                                  # v20.57: timing, "data" options, fragments -- resolved at the model stage
    control_zones = parse_control_zones(control_zones) if control_zones is not None else tuple(ACTIVE["control_zones"])
    treatment_year = int(treatment_year) if treatment_year is not None else int(ACTIVE["treatment_year"])
    post_cutoff = int(post_cutoff) if post_cutoff is not None else int(ACTIVE["post_cutoff"])
    exclude_transition_year = ACTIVE["exclude_transition_year"] if exclude_transition_year is None else bool(exclude_transition_year)
    out = df.copy() if copy else df
    # v20.59: the panel's OWN post (the exports' Treat flag, P00) is kept aside and compared with the design in effect below -- the design's
    # columns are what the model estimates on; the comparison says whether, and on how many rows, your settings change the period split
    _post_panel = pd.to_numeric(out["post"], errors="coerce").fillna(-1).astype("int8").values.copy() if "post" in out.columns else None
    bk = pd.to_numeric(out["buff_km"], errors="coerce")
    out["treatment"] = (bk == TREAT_CORE_BUFFKM).astype("int8")
    out["control"]   = bk.isin(list(control_zones)).astype("int8")
    # v20.22: per-site treatment years (two saturation phases) -> a site-specific cutoff
    if ACTIVE.get("use_site_years") and ACTIVE.get("site_years") and "site_id" in out.columns:
        _sy = pd.to_numeric(out["site_id"], errors="coerce").map({int(k): int(v) for k, v in ACTIVE["site_years"].items()})
        _cut = _sy.fillna(post_cutoff).astype(int).values
        post_cutoff_row = _cut
    else:
        post_cutoff_row = None
    # v20.57: a site with a SEASON start (the fund timing): each row's cohort is the first Year ITS series is treated -- a Rabi
    # start treats Rabi of the start year and every season (and the annual composite) of the next; a Kharif start treats Kharif
    # and Rabi of the start year and its annual composite (June-December = the larger part of the calendar year)
    if ACTIVE.get("site_start") and "site_id" in out.columns and "Season" in out.columns:
        import _fund as _F_
        _base = post_cutoff_row if post_cutoff_row is not None else np.full(len(out), post_cutoff, np.int64)
        _sid = pd.to_numeric(out["site_id"], errors="coerce").fillna(0).astype(np.int64).values
        _rc = _F_.row_cohort(_sid, out["Season"].values, ACTIVE["site_start"], post_cutoff)
        _has = np.isin(_sid, [int(k) for k in ACTIVE["site_start"]])
        post_cutoff_row = np.where(_has, _rc, _base).astype(np.int64)
    # v20.26: TRANSITION YEAR done properly. The treatment (implementation) year is the year works STARTED; when the
    # start month is unknown, that year is partly before and partly after the works, so it belongs to neither period:
    #   pre  = Year <  treatment year            (2015-2021 for 2022)
    #   post = Year >= treatment year + 1        (2023 onwards)
    #   the treatment year itself leaves the sample (transition_year = 1, in_analysis_sample = 0)
    # The old code zeroed pre/post but kept those rows in the regression (where did = 0 made them act as untreated
    # periods), started post AT the treatment year and ended pre two years early -- verified: +0.043 for a true +0.050.
    # Per-site treatment years (use_site_years) get a per-site transition year.
    _yr = out[year_col].values.astype(np.int64)
    _ty = (post_cutoff_row - (post_cutoff - treatment_year)) if post_cutoff_row is not None else np.full(len(out), treatment_year, np.int64)
    _pc = post_cutoff_row if post_cutoff_row is not None else np.full(len(out), post_cutoff, np.int64)
    if exclude_transition_year:
        _post_start = np.maximum(_pc, _ty + 1)
        _trans = (_yr >= _ty) & (_yr < _post_start)
        out["post"] = (_yr >= _post_start).astype("int8")
        out["pre"] = (_yr < _ty).astype("int8")
    else:
        _trans = np.zeros(len(out), dtype=bool)
        out["post"] = (_yr >= _pc).astype("int8")
        out["pre"] = (_yr < _pc).astype("int8")
    out["transition_year"] = _trans.astype("int8")
    # v20.59 -- DESIGN_SOURCE = "panel" (the notebooks' default): the PANEL's post (the exports' Treat flag, P00's PERIOD_RULE) is the design
    # the model estimates on; the design in effect (timing, TREATMENT_YEAR, the transition year) is computed above only to be COMPARED with
    # it (DESIGN vs PANEL). "model": the design in effect is estimated on (design-based modelling).
    _post_design = out["post"].values.astype(np.int8).copy() if _post_panel is not None else None
    _panel_src = ACTIVE.get("design_source", "model") == "panel" and _post_panel is not None
    if _panel_src:
        _pp = np.where(_post_panel >= 0, _post_panel, out["post"].values).astype(np.int8)
        out["post"] = _pp; out["pre"] = (1 - _pp).astype("int8")
        _trans = np.zeros(len(out), dtype=bool); out["transition_year"] = np.zeros(len(out), dtype=np.int8)
        # each series' cohort: the first post year of its sub-watershed in the panel's own columns (the exporter's timing)
        _sid_c = pd.to_numeric(out["site_id"], errors="coerce").fillna(0).astype(np.int64).values if "site_id" in out.columns else np.zeros(len(out), np.int64)
        _is_post = _pp == 1
        _first = pd.Series(_yr[_is_post]).groupby(_sid_c[_is_post]).min() if _is_post.any() else pd.Series(dtype="float64")
        post_cutoff_row = pd.Series(_sid_c).map(_first).fillna(post_cutoff).astype(np.int64).values
    # v20.29: the unit that carries the unit fixed effect. With annual AND seasonal rows, each pixel's annual,
    # Kharif, Rabi and Zaid series is its own unit (unit_fe = "pixel_season"): a pixel's level differs by season, and
    # one fixed effect per pixel would let the seasonal mix of its rows move the estimate. unit_fe = "pixel": the pixel.
    if "pixel_id" in out.columns:
        _raw = out["pixel_id"]
        if pd.api.types.is_integer_dtype(_raw.dtype):
            _pid = _raw.astype("int64").values                   # the pipeline's own ids (int64): arithmetic, stable
        else:                                                    # any other id type (text, float, blanks): factorised,
            _pid = pd.factorize(_raw)[0].astype("int64")         # so distinct ids stay distinct units (blank -> -1)
        if ACTIVE.get("unit_fe", "pixel_season") == "pixel_season" and "Season" in out.columns:
            out["unit_id"] = (_pid * 8 + pd.to_numeric(out["Season"], errors="coerce").fillna(0).astype("int64").values).astype("int64")
        else:
            out["unit_id"] = _pid
    out["did_term"] = (out["treatment"] * out["post"]).astype("int8")
    out["treat"] = out["treatment"]; out["did"] = out["did_term"]      # v20.59: the panel's DiD names, REBUILT here for this design (never stale)
    # staggered designs read the cohort from first_treat_agri_year: the first treated year of the row's own series (the timing in
    # force); control rings are never treated by design -> +inf, the never-treated code the staggered estimators use.
    # v20.57: ALWAYS rebuilt. v20.56 rebuilt it only with per-site years -- with ONE treatment year the panel's column stayed as
    # PASS B wrote it (the fund file's 50 %-completion MILESTONE, e.g. 2026): the staggered estimators (M05, M09, M22, M27, M30,
    # M31 ...) then dated the treatment years later than post / did_term did.
    _coh = post_cutoff_row.astype(float) if post_cutoff_row is not None else np.full(len(out), float(post_cutoff))
    out["first_treat_agri_year"] = np.where(out["treatment"].values == 1, _coh, np.inf).astype("float64")
    if ACTIVE.get("cluster", "site") == "site" and "site_id" in out.columns:
        if "subwshed_id_orig" not in out.columns: out["subwshed_id_orig"] = out["subwshed_id"]
        out["subwshed_id"] = ("S" + pd.to_numeric(out["site_id"], errors="coerce").fillna(0).astype(int).astype(str)).astype("category")
    if ACTIVE.get("pooled_fe", "period") == "site_period" and "site_id" in out.columns and "time_fe_yearseason" in out.columns:
        if "time_fe_yearseason_orig" not in out.columns: out["time_fe_yearseason_orig"] = out["time_fe_yearseason"]
        out["time_fe_yearseason"] = (pd.to_numeric(out["site_id"], errors="coerce").fillna(0).astype(int).astype(str) + "|"
                                     + out["time_fe_yearseason_orig"].astype(str)).astype("category")
    # aliases used by the 45 model notebooks
    out["treat_core"] = out["treatment"]; out["control_zone_selected"] = out["control"]
    out["pre_period"] = out["pre"];       out["post_period"] = out["post"]
    if ACTIVE.get("cohort_offset") and "first_treat_agri_year" in out.columns:   # v20.3 staggered designs
        out["first_treat_agri_year"] = pd.to_numeric(out["first_treat_agri_year"], errors="coerce") + int(ACTIVE["cohort_offset"])
    in_grp = ((out["treatment"] == 1) | (out["control"] == 1)) & (out["transition_year"].values == 0)   # v20.26
    _loc_counts = {}
    if "site_id" in out.columns and "pixel_id" in out.columns and not df.attrs.get("location_rule_applied") and not df.attrs.get("synthetic"):   # v20.58: a frame that did
        _lt = location_table()                                                                            # not pass load_panel: the
        if _lt.get("mode") != "none" or CLEAN_CONTROLS:                                                   # location rule here (no panel:
                                                                                                          # its frame-level codes 3 / 4)
            _kf, _cf = location_mask(out, _lt, pooled=True)
            if (_cf > 0).any(): _count_location(_loc_counts, out, _cf); location_report_lines(_loc_counts, label=f"{CURRENT_OUTCOME or 'frame'}: ")
            in_grp = np.asarray(in_grp) & _kf
    if "Season" in out.columns and seasons_mode(verbose=False) != "all":   # v20.12 / v20.24
        in_grp &= season_rows(out["Season"].values)
    if has_year_window(): in_grp &= year_mask(out[year_col].values)     # v20.2
    LAST_DESIGN_INFO.clear()
    _site_col = "site_id" if "site_id" in out.columns else None
    # v20.58: the pooled overlap (a pixel TREATED in one processed sub-watershed is never a control of another; a pixel-year-season enters
    # once) is part of the LOCATION rule (code 3, load_panel / above) -- leaving treated and control, pre and post alike
    _lr = LAST_LOAD_INFO.get("location_rows", {}) if df.attrs.get("location_rule_applied") else {f"{k[0]}|{int(k[1])}|{int(k[2])}": v for k, v in _loc_counts.items()}
    LAST_DESIGN_INFO.update({"contaminated_control_rows": int(sum(v for k, v in _lr.items() if str(k).startswith("3|0|"))),
                             "duplicate_rows_across_sites": int(sum(v for k, v in _lr.items() if str(k).startswith("3|1|"))),
                             "location_rows": dict(_lr)})
    design_vs_panel(out, _post_panel, _post_design)                      # v20.59: the design in effect against the panel's post column, said (after the
                                                                         #   info above is reset, so the count stays in LAST_DESIGN_INFO)
    out["in_analysis_sample"] = np.asarray(in_grp).astype("int8")
    _sample_integrity_once(out, control_zones)                      # v20.58: the post-conditions, CONFIRMED on the estimation sample
    if not df.attrs.get("synthetic"): _cache_design_se(out)          # v20.58: the design-based check of THIS sample, for the headline
    out["event_time"] = (out[year_col].values - post_cutoff_row) if _panel_src else \
        (out[year_col].values - (post_cutoff_row - (post_cutoff - treatment_year))) if post_cutoff_row is not None else (out[year_col] - treatment_year)   # v20.59: panel source = the panel's first post year
    attach_fund_dose(out)                                        # v20.57: the fund file's dose under the timing in force
    if "season_sort_rank" in out.columns:
        out["period_index"] = out[year_col].astype(int) * 10 + out["season_sort_rank"].astype(int)
    else:
        out["period_index"] = out[year_col].astype(int) * 10
    return out


def _nn_match_torch_chunked(query_xy, registry_xy, query_chunk=20000, registry_chunk=20000):   # v20.58: blocks 5x larger (was 4000 x 20000)
    """Brute-force GPU nearest-neighbor via PyTorch -- works natively on Windows.
    Double-chunked (query AND registry) so GPU memory stays bounded as the registry grows into
    the millions of points at full 40k-file scale. Coordinates are CENTERED before the
    |q|^2+|r|^2-2q.r distance identity -- validated this against scipy cKDTree on real data:
    uncentered, worst-case distance error was 0.125m (close enough to the 3m tolerance to risk
    flipping a same/different-pixel decision); centered, the error drops to 3e-5m.
    v20.49: torch.cdist still used the |q|^2+|r|^2-2q.r identity (a matrix product) for large chunks -- in float32 that
    chose another neighbour for 2 of 3,000 points with a 1.46 m distance error across a 5 km area (V00d, G5). Distances
    are now computed from the coordinate differences themselves (compute_mode="donot_use_mm_for_euclid_dist")."""
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
            d2 = torch.cdist(q, r, p=2, compute_mode="donot_use_mm_for_euclid_dist") ** 2   # v20.49: exact differences
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




# ====================== TIME FIXED EFFECTS: how year and season enter ======================
# "yearseason" (DEFAULT) : one dummy per Year x Season cell  -> absorbs year shocks, season
#                          shocks, AND year-specific seasonal shocks (a bad monsoon in one
#                          Kharif). This is the more robust choice for agricultural outcomes and
#                          is what every model uses via the `time_fe_yearseason` column.
# "additive"             : separate Year dummies + separate Season dummies -> assumes the
#                          seasonal pattern is the SAME every year. More parsimonious; use it as
#                          a robustness check, not as the primary specification.
TIME_FE_MODE = "yearseason"

def time_fe_columns(mode=None):
    """Which FE column(s) a model should pass. yearseason -> ["time_fe_yearseason"];
    additive -> ["time_fe_year", "time_fe_season"]."""
    m = mode or TIME_FE_MODE
    return ["time_fe_yearseason"] if m == "yearseason" else ["time_fe_year", "time_fe_season"]


# ======================= v16: GPU FIXED-EFFECTS DEMEANING (NVIDIA A40) =======================
# The alternating-projections demeaning is the inner loop of almost every estimator here
# (M01, M02, M16, M23 x999 replicates, M25 x999, M26, M28, M29, ...). Each sweep is a
# group-mean per fixed effect -- a memory-bandwidth-bound scatter/gather that a GPU does
# 20-100x faster than pandas groupby. Falls back to numpy automatically if torch/CUDA is
# absent, so every notebook runs identically on any machine.
USE_GPU       = True            # set False to force CPU
GPU_MIN_ROWS  = 1_000_000       # below this the transfer overhead outweighs the gain
GPU_MAX_ROWS  = None            # v20.57: None = the 98 % VRAM ceiling decides (was a fixed 500 M-row cap); a number caps it
                                # a 48 GB A40; use subwshed_filter= or the CPU path (500 GB RAM)
_torch = None
GPU_AUTO_SELFTEST = True        # v20.50: the first time a CUDA device (your A40) is found, gpu_selftest() runs by itself
GPU_SELFTEST_STATE = {"ok": None, "speedup": None}
def _torch_cuda():
    global _torch
    if _torch is None:
        try:
            import torch
            _torch = torch if torch.cuda.is_available() else False
        except Exception:
            _torch = False
        if _torch and GPU_AUTO_SELFTEST and GPU_SELFTEST_STATE["ok"] is None:
            GPU_SELFTEST_STATE["ok"] = "running"                  # (gpu_selftest calls back here: no recursion)
            try:
                GPU_SELFTEST_STATE["speedup"] = gpu_selftest(n=2_000_000); GPU_SELFTEST_STATE["ok"] = True
            except Exception as e:                                # disagreement or a CUDA error: the CPU computes
                print(f"[WARNING] GPU self-test failed ({type(e).__name__}: {str(e)[:120]}) -- GPU paths OFF for this session, the CPU computes")
                _torch = False; GPU_SELFTEST_STATE["ok"] = False
    return _torch

def gpu_status():
    T = _torch_cuda()
    if not T: return "CPU (torch/CUDA not available)"
    p = T.cuda.get_device_properties(0)
    return f"GPU {p.name}, {p.total_memory/1e9:.0f} GB VRAM, torch {T.__version__}"

# v20.58: the demeaning never stops SILENTLY short of its tolerance. Within the passes a caller allows (max_iter) nothing changed: the
# same test, the same passes, the same numbers wherever v20.57 converged. Where it did NOT (a sparse or unbalanced design -- e.g. 3 %
# of the rows without a unit key: after 200 passes the change was still 1e-5), the passes are extended up to FE_MAX_ITER until the
# change is below the tolerance -- or at the column's floating-point noise floor (FE_NOISE_ULPS x machine epsilon x its largest value:
# an absolute 1e-10 is unreachable for a column of values ~1e7). If even that is not reached, the run says so (once per model) with the
# last change -- the size of the error the estimate may carry. (Until v20.58 the loop ended after 100 / 200 passes without a word.)
# A NaN in the input never converges: the loop stops after the caller's passes, as before, and says so.
FE_MAX_ITER = 10_000
FE_NOISE_ULPS = 64.0
_FE_CONV_SAID = set()
def _fe_not_converged(where, n, it, chg, tol):
    key = (CURRENT_MODEL_ID, where, bool(np.isfinite(chg)))
    if key in _FE_CONV_SAID: return
    _FE_CONV_SAID.add(key)
    if np.isfinite(chg):
        warn(f"fixed-effects demeaning ({where}, {n:,} rows) did not reach {tol:g} in {it:,} passes (last change {chg:.2e}): "
             f"the estimate may carry an error of about that size")
    else:
        warn(f"fixed-effects demeaning ({where}, {n:,} rows): the input holds a missing value (NaN) -- the rows connected to it are NaN "
             f"after the demeaning; filter the rows first (every estimator of this pipeline does)")

def _fe_more(it, max_iter, chg, tol, over_floor=True):
    """True while the alternating projections should go on: not converged (the change >= tol), and within the caller's passes -- or,
    v20.58, beyond them while the change is finite and above the noise floor (over_floor), up to FE_MAX_ITER."""
    if chg < tol: return False
    if it < max_iter: return True
    return bool(np.isfinite(chg)) and bool(over_floor) and it < FE_MAX_ITER

def _demean_gpu_matrix(T, Y, fes, tol, max_iter):
    """v20.23: the GPU path for a whole matrix -- index_add_ on (K x k) sums handles every column in one kernel."""
    dev = T.device("cuda")
    R = T.as_tensor(np.ascontiguousarray(np.asarray(Y, dtype=np.float64)), device=dev)
    if R.ndim == 1: R = R.reshape(-1, 1)
    R = R.clone(); k = R.shape[1]
    codes, counts, rows_ok = [], [], []
    for f in fes:
        cd = _codes(f); okm = cd >= 0
        idx = None if okm.all() else T.as_tensor(np.nonzero(okm)[0], device=dev)
        ct = T.as_tensor(cd[okm].astype(np.int64), device=dev)
        codes.append(ct); rows_ok.append(idx)
        counts.append(T.bincount(ct, minlength=int(cd.max()) + 1 if okm.any() else 1).to(T.float64).clamp_(min=1.0).reshape(-1, 1))
    Ks = [int(n.shape[0]) for n in counts]
    T.cuda.synchronize()
    floor = (R.abs().max(dim=0).values * (FE_NOISE_ULPS * np.finfo(np.float64).eps)).clamp(min=tol) if R.shape[0] else None
    it = 0; chg = np.inf; over = True
    while True:
        it += 1
        prev = R.clone()
        for ct, n, K, idx in zip(codes, counts, Ks, rows_ok):
            if idx is None:
                sums = T.zeros((K, k), dtype=T.float64, device=dev).index_add_(0, ct, R)
                R = R - (sums / n)[ct]
            else:
                sums = T.zeros((K, k), dtype=T.float64, device=dev).index_add_(0, ct, R[idx])
                R[idx] = R[idx] - (sums / n)[ct]
        cc = (R - prev).abs().max(dim=0).values if R.shape[0] else None
        chg = float(cc.max()) if cc is not None else 0.0
        if it >= max_iter and cc is not None: over = bool((cc >= floor).any())
        if not _fe_more(it, max_iter, chg, tol, over): break
    if not (chg < tol or (np.isfinite(chg) and not over)): _fe_not_converged("matrix, GPU", int(R.shape[0]), it, chg, tol)
    out = R.cpu().numpy()
    del R, prev, codes, counts
    T.cuda.empty_cache()
    return out

def _demean_gpu(T, y, fes, tol, max_iter):
    dev = "cuda"
    r = T.as_tensor(np.ascontiguousarray(y, dtype=np.float64), device=dev)
    codes, counts, rows_ok = [], [], []
    for f in fes:
        cd, uniq = pd.factorize(pd.Series(np.asarray(f)), sort=False)
        okm = cd >= 0                                      # v20.15: a missing key (code -1) is left untouched,
        idx = None if okm.all() else T.as_tensor(np.nonzero(okm)[0], device=dev)   # as the CPU path does
        ct = T.as_tensor(cd[okm].astype(np.int64), device=dev)
        codes.append(ct); rows_ok.append(idx)
        counts.append(T.bincount(ct, minlength=len(uniq)).to(T.float64).clamp_(min=1.0))
    Ks = [int(n.numel()) for n in counts]
    T.cuda.synchronize()                                   # v17.4: surface transfer errors here, as exceptions
    floor = max(tol, FE_NOISE_ULPS * np.finfo(np.float64).eps * float(r.abs().max())) if r.numel() else tol
    it = 0; chg = np.inf
    while True:
        it += 1
        prev = r.clone()
        for ct, n, K, idx in zip(codes, counts, Ks, rows_ok):
            if idx is None:
                sums = T.zeros(K, dtype=T.float64, device=dev).index_add_(0, ct, r)
                r = r - (sums / n)[ct]
            else:
                sums = T.zeros(K, dtype=T.float64, device=dev).index_add_(0, ct, r[idx])
                r[idx] = r[idx] - (sums / n)[ct]
        chg = float((r - prev).abs().max()) if r.numel() else 0.0
        if not _fe_more(it, max_iter, chg, tol, chg >= floor): break
    if not (chg < tol or (np.isfinite(chg) and chg < floor)): _fe_not_converged("vector, GPU", int(r.shape[0]), it, chg, tol)
    T.cuda.synchronize()
    out = r.cpu().numpy()
    del r, prev, codes, counts; T.cuda.empty_cache()
    return out

def _demean_cpu_pandas(y, fes, tol, max_iter):
    """v17.4 reference implementation (pandas groupby-transform); kept for tests."""
    resid = np.asarray(y, dtype=float).copy()
    fes = [np.asarray(f) for f in fes]
    for _ in range(max_iter):
        prev = resid.copy()
        for f in fes:
            resid = resid - pd.Series(resid).groupby(f).transform("mean").values
        if np.max(np.abs(resid - prev)) < tol:
            break
    return resid

def _codes(f):
    """Integer group codes 0..K-1 (NaN keys -> -1) for any key array (ints, strings, categoricals).
    v20.15: ALWAYS re-factorised on the rows given. A categorical's own .codes keep every category of the frame
    it came from, so after any row filter the code space had empty groups -> 0/0 in the group means
    ('RuntimeWarning: invalid value encountered in divide') and a code space that differed from the GPU's."""
    if hasattr(f, "codes") and hasattr(f, "categories"):          # v20.23: re-factorise the INT codes, not the strings
        raw = np.asarray(f.codes, dtype=np.int64)
        a = pd.factorize(raw, sort=False)[0]
        a[raw < 0] = -1                                            # a missing key stays missing
        return np.asarray(a, dtype=np.int64)
    arr = np.asarray(f)
    if arr.dtype.kind in "iu":                                       # int keys: already cheap to factorise
        return np.asarray(pd.factorize(arr, sort=False)[0], dtype=np.int64)
    a = pd.factorize(pd.Series(arr), sort=False)[0]
    return np.asarray(a, dtype=np.int64)

def _demean_cpu_matrix(Y, fes, tol, max_iter):
    """v20.23: demean EVERY column of Y (n x k) in one alternating-projection loop. Each fixed effect is a sparse
    group-mean operator P (K x n, entries 1/n_g): a sweep is one sparse matmul (all columns at once) and one
    gather -- the fixest approach -- instead of k separate bincount passes."""
    from scipy import sparse as _sp
    R = np.array(np.asarray(Y, dtype=np.float64), order="C")
    if R.ndim == 1: R = R.reshape(-1, 1)
    n = R.shape[0]
    ops = []
    for f in fes:
        cd = _codes(f); ok = cd >= 0
        K = int(cd.max()) + 1 if ok.any() else 1
        cnt = np.bincount(cd[ok], minlength=K).astype(np.float64); cnt[cnt == 0] = 1.0
        rows = np.nonzero(ok)[0]
        P = _sp.csr_matrix((1.0 / cnt[cd[ok]], (cd[ok], rows)), shape=(K, n))
        ops.append((P, cd, ok, ok.all()))
    floor = np.maximum(tol, FE_NOISE_ULPS * np.finfo(np.float64).eps * np.abs(R).max(axis=0)) if R.size else None   # per column
    it = 0; chg = np.inf; over = True
    while True:
        it += 1
        prev = R.copy()
        for P, cd, ok, allok in ops:
            means = P @ R                                   # K x k group means of every column
            if allok: R -= means[cd]
            else:     R[ok] -= means[cd[ok]]
        np.subtract(R, prev, out=prev); np.abs(prev, out=prev)   # v20.58: the change in place -- the same test as np.max(np.abs(R - prev)),
        if it < max_iter or not prev.size:                       #   without two more n x k temporaries (the 98 % rule's batch sizes count on it)
            chg = float(prev.max()) if prev.size else 0.0
        else:                                                    # beyond the caller's passes: each column down to its noise floor
            cc = prev.max(axis=0); chg = float(cc.max()); over = bool((cc >= floor).any())
        if not _fe_more(it, max_iter, chg, tol, over): break
    if not (chg < tol or (np.isfinite(chg) and not over)): _fe_not_converged("matrix", n, it, chg, tol)
    return R

def _demean_cpu(y, fes, tol, max_iter):
    """v17.5: alternating projections with np.bincount over factorised codes -- the same numbers as the pandas
    version (tested to 1e-12) at a fraction of the time and memory (no per-iteration groupby/hash tables).
    Rows whose key is missing (code -1) are left untouched by that fixed effect, as pandas did."""
    resid = np.asarray(y, dtype=np.float64).copy()
    codes = [_codes(f) for f in fes]
    cnts = []
    for cd in codes:
        ok = cd >= 0
        K = int(cd.max()) + 1 if ok.any() else 1
        cnts.append((ok, K, np.bincount(cd[ok], minlength=K).astype(np.float64)))
    # BALANCED TWO-WAY SHORTCUT: with exactly two fixed effects and every cell of the (fe1 x fe2) grid observed
    # once, the projection is exact in ONE step: r = y - m1[c1] - m2[c2] + mean(y).
    if len(codes) == 2 and all(c.min() >= 0 for c in codes):
        (ok1, K1, n1), (ok2, K2, n2) = cnts
        if n1.min() == n1.max() == K2 and n2.min() == n2.max() == K1 and len(resid) == K1 * K2:
            m1 = np.bincount(codes[0], weights=resid, minlength=K1) / n1
            m2 = np.bincount(codes[1], weights=resid, minlength=K2) / n2
            return resid - m1[codes[0]] - m2[codes[1]] + resid.mean()
    floor = max(tol, FE_NOISE_ULPS * np.finfo(np.float64).eps * float(np.max(np.abs(resid)))) if resid.size else tol
    it = 0; chg = np.inf
    while True:
        it += 1
        prev = resid.copy()
        for cd, (ok, K, n) in zip(codes, cnts):
            sums = np.bincount(cd[ok], weights=resid[ok], minlength=K)
            resid[ok] -= (sums / n)[cd[ok]]
        chg = float(np.max(np.abs(resid - prev))) if resid.size else 0.0
        if not _fe_more(it, max_iter, chg, tol, chg >= floor): break
    if not (chg < tol or (np.isfinite(chg) and chg < floor)): _fe_not_converged("vector", len(resid), it, chg, tol)
    return resid

# ======================= GPU (v16): alternating-projection demeaning on the A40 =======================
# The FE demeaner is nothing but repeated group-means; on a GPU that is index_add_ over a
# codes array -- memory-bound and very fast. float64 is used so results match the numpy path
# to ~1e-12 (the A40's FP64 rate is irrelevant: the kernel is bandwidth-bound).
# A 1B-row problem needs ~8 GB (y) + 3 x 8 GB (codes as int64) = 32 GB of the A40's 48 GB.
# Set USE_GPU=False to force numpy. Requires torch WITH CUDA: pip install torch --index-url https://download.pytorch.org/whl/<cuXXX>
# (the CUDA build for your NVIDIA driver -- pytorch.org "Get started"); check: torch.cuda.get_device_name(0) -> "NVIDIA A40"
USE_GPU = True
_TORCH = None
def _gpu_available():
    global _TORCH
    if not USE_GPU: return False
    if _TORCH is None:
        try:
            import torch; _TORCH = torch if torch.cuda.is_available() else False
        except Exception:
            _TORCH = False
    return bool(_TORCH)

def _demean_torch(y, fes, tol, max_iter):
    torch = _TORCH; dev = "cuda"
    codes, sizes = [], []
    for f in fes:
        cd, uniq = pd.factorize(pd.Series(f), sort=False)
        codes.append(torch.as_tensor(cd, dtype=torch.int64, device=dev)); sizes.append(len(uniq))
    r = torch.as_tensor(np.asarray(y, dtype=np.float64), dtype=torch.float64, device=dev)
    counts = [torch.zeros(k, dtype=torch.float64, device=dev).index_add_(0, cd, torch.ones_like(r)) for cd, k in zip(codes, sizes)]
    floor = max(tol, FE_NOISE_ULPS * np.finfo(np.float64).eps * float(r.abs().max())) if r.numel() else tol
    it = 0; chg = np.inf
    while True:
        it += 1
        prev = r.clone()
        for cd, k, cnt in zip(codes, sizes, counts):
            means = torch.zeros(k, dtype=torch.float64, device=dev).index_add_(0, cd, r) / cnt
            r = r - means[cd]
        chg = float((r - prev).abs().max()) if r.numel() else 0.0
        if not _fe_more(it, max_iter, chg, tol, chg >= floor): break
    if not (chg < tol or (np.isfinite(chg) and chg < floor)): _fe_not_converged("vector, torch", int(r.shape[0]), it, chg, tol)
    out = r.cpu().numpy(); del r, prev, codes, counts; torch.cuda.empty_cache()
    return out



# ====================== v17.3: GPU vs HOST MEMORY CAPACITY ======================
BYTES_PER_ROW_DEMEAN = 40.0      # float64 y + prev + 2 temporaries + codes: ~8 B x (3 + n_FE) per row, n_FE=2
def host_free_bytes():
    try:
        import psutil; return float(psutil.virtual_memory().available)
    except Exception:
        return None
def gpu_free_bytes():
    T = _torch_cuda()
    if not T: return None
    try:
        free, total = T.cuda.mem_get_info(); return float(free)
    except Exception:
        try: return float(T.cuda.get_device_properties(0).total_memory) * 0.98     # v20.57: the 98 % rule
        except Exception: return None
def gpu_capacity_rows(n_fe=2, safety=None):
    """Rows the GPU demeaner can hold RIGHT NOW. v20.57: 8 B x (3 + n_FE) per row against what the 98 % VRAM ceiling
    still allows (v20.30: 95 %; before: 60 % of the free VRAM); `safety` still scales it if given."""
    try:
        import _hardware as _H
        b = _H.gpu_budget_bytes()
    except Exception:
        b = None
    if b is None:
        free = gpu_free_bytes()
        if free is None: return 0
        b = free                                                     # v20.57: all of it (the ceiling is in gpu_budget_bytes)
    return int((safety or 1.0) * b / (8.0 * (3 + n_fe)))
def host_capacity_rows(bytes_per_row=BYTES_PER_ROW_DEMEAN, safety=MEMORY_HEADROOM):
    b = _memory_budget_bytes()                                       # v20.57: below 98 % of the TOTAL RAM
    if b is None: return None
    return int(safety * b / bytes_per_row)
def assert_fits_in_memory(n_rows, bytes_per_row=BYTES_PER_ROW_DEMEAN, what="estimator"):
    """Raise a READABLE InsufficientDataError instead of letting the OS kill the kernel."""
    free = _memory_budget_bytes()                                   # v20.57: what 98 % of the TOTAL RAM still allows
    if free is None: return True
    need = n_rows * bytes_per_row
    if need > MEMORY_HEADROOM * free:
        raise InsufficientDataError(
            f"{what} needs ~{need/1e9:.1f} GB of host RAM for {n_rows:,} rows but only {free/1e9:.1f} GB is left below 98 % of the RAM "
            f"(the kernel would be killed). Use M01_MODE='stream' (exact, never loads the panel), set MAX_ROWS / "
            f"sample_fraction in CELL 1, close other notebooks, or run R06/fixest on the full panel.")
    return True
def memory_report(n_rows=None):
    free = host_free_bytes(); g = gpu_free_bytes()
    line = f"host RAM free {free/1e9:.1f} GB" if free else "host RAM free: unknown (pip install psutil)"
    line += f" | GPU VRAM free {g/1e9:.1f} GB (capacity {gpu_capacity_rows():,} rows for a 2-FE demean)" if g else " | GPU: none"
    if n_rows: line += f" | this frame: {n_rows:,} rows -> in-RAM estimator needs ~{n_rows*BYTES_PER_ROW_DEMEAN/1e9:.1f} GB"
    info(line)
    return {"host_free": free, "gpu_free": g}


_GPU_CHECKED = {"done": False, "ok": None}
GPU_CROSSCHECK_ROWS = 300_000
def _gpu_crosscheck(y, fes, gpu_out, tol, max_iter, rows=GPU_CROSSCHECK_ROWS, rel_tol=1e-6):   # RETIRED in v20.30 -- not called;
    # the subsample check was replaced by _gpu_verify (all rows, every call). Kept only so old scripts that import it still load.
    """v20.15: the GPU implementation is verified ONCE per session by demeaning the SAME subsample of rows with
    both implementations and comparing them. (The v17.10 check re-demeaned a random row subsample of the GPU
    residual on the CPU; in a random subsample most pixels have a single row, so the CPU 're-demeaning' zeroed
    every value and the 'drift' was just the size of the residual -- 8.68 on your event-study dummies. The GPU was
    right and was switched off for nothing.) If the two implementations disagree on identical input, the GPU is
    switched off for the session."""
    global USE_GPU
    if _GPU_CHECKED["done"]:
        return _GPU_CHECKED["ok"]
    _GPU_CHECKED["done"] = True
    try:
        import torch as T
        n = len(gpu_out)
        idx = np.arange(n) if n <= rows else np.sort(np.random.default_rng(0).choice(n, rows, replace=False))
        y_sub = np.asarray(y, dtype=np.float64)[idx]
        f_sub = [np.asarray(f)[idx] for f in fes]
        a = _demean_cpu(y_sub.copy(), f_sub, tol, max_iter)
        b = _demean_gpu(T, y_sub.copy(), f_sub, tol, max_iter)
        scale = max(float(np.max(np.abs(a))), 1e-12)
        drift = float(np.max(np.abs(a - b))) / scale
        if not np.isfinite(drift) or drift > rel_tol * 100:
            warn(f"GPU demeaning cross-check FAILED (relative difference {drift:.2e} on identical input, {len(idx):,} "
                 f"rows) -- switching to the CPU path for this session")
            USE_GPU = False; _GPU_CHECKED["ok"] = False
        else:
            ok(f"GPU demeaning cross-check passed (CPU and GPU agree to {drift:.1e} on the same {len(idx):,} rows)")
            _GPU_CHECKED["ok"] = True
    except Exception as e:
        warn(f"GPU cross-check could not run ({type(e).__name__}: {e}); continuing")
        _GPU_CHECKED["ok"] = None
    return _GPU_CHECKED["ok"]

# ====================== v20.30: EVERY GPU demeaning is verified on ALL the data ======================
# (the v20.15 check compared CPU and GPU once per session on a 300,000-row SUBSAMPLE -- where most pixels have one row
# and demeaning is trivially zero on both -- and even when it FAILED it returned that call's GPU result.)
GPU_VERIFY = "full"          # "full": every GPU result is checked on all rows; the first of each kind is also recomputed
                             # on the CPU on all rows | "off": trust the GPU (not recommended)
GPU_VERIFY_REL_TOL = 1e-6    # GPU vs CPU: max |difference| / max |value|
GPU_INVARIANT_REL_TOL = 1e-6 # every call: max |group mean of the result| / max |input|  (a projection leaves all group means 0)
_GPU_TRUST = {"vector": None, "matrix": None}   # None = not yet compared with the CPU in this session

def _fe_group_mean_max(R, fes):
    """Per column: max |mean of R within any fixed-effect group| over every fixed effect -- on ALL rows. A correct
    two-way demeaning leaves every group mean at 0 (the residual is orthogonal to every fixed-effect dummy)."""
    R = np.asarray(R, dtype=np.float64)
    if R.ndim == 1: R = R.reshape(-1, 1)
    worst = np.zeros(R.shape[1])
    for f in fes:
        cd = _codes(f); ok_ = cd >= 0
        if not ok_.any(): continue
        K = int(cd[ok_].max()) + 1; n_ = np.bincount(cd[ok_], minlength=K).astype(np.float64); n_[n_ == 0] = 1.0
        for j in range(R.shape[1]):
            m = np.abs(np.bincount(cd[ok_], weights=R[ok_, j], minlength=K) / n_)
            worst[j] = max(worst[j], float(np.nanmax(m)) if len(m) else 0.0)
    return worst

def _gpu_verify(kind, Y, fes, gpu_out, tol, max_iter):
    """Returns the GPU result only if it passes on ALL rows; otherwise the CPU result (and the CPU from then on)."""
    global USE_GPU
    if GPU_VERIFY == "off": return gpu_out
    Y2 = np.asarray(Y, dtype=np.float64); G2 = np.asarray(gpu_out, dtype=np.float64)
    _Ym = Y2.reshape(len(Y2), -1)                                 # each COLUMN is judged on its own scale
    scale = np.maximum(np.nanmax(np.abs(_Ym), axis=0) if _Ym.size else np.zeros(_Ym.shape[1]), 1e-12)
    cpu = None; why = None
    try:
        if G2.shape != (Y2.shape if Y2.ndim == G2.ndim else G2.shape) or not np.all(np.isfinite(G2[np.isfinite(Y2)] if Y2.shape == G2.shape else G2)):
            why = "non-finite or mis-shaped values"
        else:
            inv = _fe_group_mean_max(G2, fes); rel = inv / scale
            if not np.all(np.isfinite(rel)) or rel.max() > GPU_INVARIANT_REL_TOL:
                j_ = int(np.nanargmax(np.where(np.isfinite(rel), rel, np.inf)))
                why = (f"group means of column {j_} are {inv[j_]:.2e} (must be ~0; allowed {GPU_INVARIANT_REL_TOL * scale[j_]:.1e} "
                       f"for a column of scale {scale[j_]:.3g})")
        if why is None and _GPU_TRUST[kind] is None:
            cpu = (_demean_cpu_matrix(Y2, fes, tol, max_iter) if kind == "matrix"
                   else _demean_cpu(Y2.copy(), list(fes), tol, max_iter))
            _d = np.abs(np.asarray(cpu).reshape(G2.shape) - G2).reshape(len(G2), -1)
            drift = float(np.nanmax(np.nanmax(_d, axis=0) / scale))
            if not np.isfinite(drift) or drift > GPU_VERIFY_REL_TOL:
                why = f"GPU and CPU differ by {drift:.2e} (relative) on the same {Y2.shape[0]:,} rows"
            else:
                _GPU_TRUST[kind] = True
                ok(f"GPU {kind} demeaning verified on ALL {Y2.shape[0]:,} rows{'' if Y2.ndim == 1 else f' x {Y2.shape[1]} columns'}: "
                   f"CPU and GPU agree to {drift:.1e}; group means ~0")
    except Exception as e:
        why = f"the check itself failed ({type(e).__name__}: {str(e)[:80]})"
    if why is None:
        return gpu_out
    warn(f"GPU {kind} demeaning REJECTED: {why} -- this result and the rest of the session use the CPU")
    _GPU_TRUST[kind] = False; USE_GPU = False
    if cpu is None:
        cpu = _demean_cpu_matrix(Y2, fes, tol, max_iter) if kind == "matrix" else _demean_cpu(Y2.copy(), list(fes), tol, max_iter)
    return np.asarray(cpu).reshape(np.asarray(gpu_out).shape)

def demean_multi_way(y, *fes, tol=1e-10, max_iter=200):
    """Alternating-projections demeaning over ANY number of fixed-effect dimensions
    (Guimaraes & Portugal 2010). Routes to the GPU when available and the problem is large
    enough; the two paths are the SAME algorithm and agree to ~1e-12 (see gpu_selftest())."""
    global USE_GPU
    n = len(y); T = _torch_cuda()
    # v17.3: the host must hold the arrays in both paths -> readable error instead of a dead kernel
    assert_fits_in_memory(n, bytes_per_row=8.0 * (3 + len(fes)), what="fixed-effects demeaning")
    trace(f"demean start n={n:,} n_fe={len(fes)} gpu={'on' if (USE_GPU and T) else 'off'}")
    if USE_GPU and T and GPU_MIN_ROWS <= n:
        cap = gpu_capacity_rows(n_fe=len(fes))
        # v17.4: a factorised code of -1 (NaN key) or a code >= K would be an out-of-range index_add_ on the GPU --
        # a device-side assert that can take the whole process down. Validate on the host first.
        _codes_ok = True
        for f in fes:
            cd = pd.factorize(pd.Series(np.asarray(f)), sort=False)[0]
            if len(cd) and cd.min() < 0: _codes_ok = False; break
        if not _codes_ok:
            info("GPU skipped: a fixed-effect column has missing keys (factorised code -1) -- CPU path (groupby ignores NaN keys)")
        elif n <= (min(cap, GPU_MAX_ROWS) if GPU_MAX_ROWS else cap):
            try:
                out = _demean_gpu(T, y, fes, tol, max_iter)
                out = _gpu_verify("vector", y, fes, out, tol, max_iter)   # v20.30: ALL rows, every call; CPU if rejected
                trace("demean done on GPU" if USE_GPU else "demean GPU result rejected -> CPU result")
                return out
            except Exception as e:           # e.g. CUDA OOM -> transparent CPU fallback, never a crash
                warn(f"GPU demeaning failed ({type(e).__name__}: {str(e)[:60]}) -- using CPU for the rest of this session")
                USE_GPU = False              # v17.4: a CUDA context that has errored once is not trusted again
                try: T.cuda.empty_cache()
                except Exception: pass
        else:
            info(f"GPU skipped: {n:,} rows exceed the free-VRAM capacity ({cap:,} rows) -- CPU path (same numbers)")
    out = _demean_cpu(y, fes, tol, max_iter)
    trace("demean done on CPU")
    return out

def gpu_selftest(n=2_000_000, seed=0):
    """Run once on your A40: proves the GPU path equals the CPU path to ~1e-12 and reports the
    speed-up. If torch/CUDA is absent it says so and returns."""
    import time
    T = _torch_cuda()
    print(f"[INFO]    backend: {gpu_status()}")
    if not T:
        print("[INFO]    no GPU -- all estimators run on CPU (identical results, slower)"); return None
    rng = np.random.default_rng(seed)
    y = rng.normal(0, 1, n); f1 = rng.integers(0, n // 20, n); f2 = rng.integers(0, 40, n); f3 = rng.integers(0, 3, n)
    t0 = time.time(); a = _demean_cpu(y, (f1, f2, f3), 1e-10, 200); tc = time.time() - t0
    t0 = time.time(); b = _demean_gpu(T, y, (f1, f2, f3), 1e-10, 200); tg = time.time() - t0
    diff = float(np.max(np.abs(a - b)))
    assert diff < 1e-8, f"GPU and CPU demeaning disagree by {diff:.1e} -- do not use GPU until resolved"   # v20.50: judged first
    ok(f"GPU == CPU to {diff:.1e} | CPU {tc:.2f}s  GPU {tg:.2f}s  -> {tc/max(tg,1e-9):.0f}x faster on {n:,} rows")
    return tc / max(tg, 1e-9)


# ====================== v20.38: THE SUB-WATERSHED IS THE CLUSTER ======================
# Your rule: there are no defined clusters inside a sub-watershed -- the sub-watershed (site_id, the shapefile's
# SWSiD_All) is the cluster; a run over all 20 sub-watersheds has 20 clusters. A run over ONE sub-watershed has ONE
# cluster, and cluster-robust inference needs at least two: the independent information of a single treated area is
# in its YEARS (every year's core-vs-ring difference is one draw), so such a run clusters on Year. Tested: with one
# sub-watershed and yearly core-vs-ring shocks, clustering on within-SWS units understated the true spread of the
# estimate 6-fold; clustering on years gave 1.4x (conservative, as it should be with few years).
LAST_CLUSTER_USED = {"value": None}
MIN_SWS_CLUSTERS = 6        # v20.41: fewer sub-watersheds than this -> cluster on years (2 clusters gave an SE of 0.0000)
_CLUSTER_SAID = {"n": 0}

def _cluster_key(df, col):
    """The cluster column the scenario asks for. Models pass 'subwshed_id'; 'site' (default) turns it into the
    sub-watershed id, or into Year when the sample holds a single sub-watershed. A column the model chose itself
    (anything else) is left alone."""
    cols = getattr(df, "columns", ())
    if col not in ("subwshed_id", "site_id", "cluster_id"):
        LAST_CLUSTER_USED["value"] = col; return col
    mode = ACTIVE.get("cluster", "site")
    if mode == "year" and "Year" in cols:
        LAST_CLUSTER_USED["value"] = "Year"; return "Year"
    if mode == "subwshed" and col in cols:
        LAST_CLUSTER_USED["value"] = col; return col
    if "site_id" in cols:
        n_ = int(pd.Series(df["site_id"]).nunique(dropna=True))
        if n_ >= MIN_SWS_CLUSTERS:
            LAST_CLUSTER_USED["value"] = "site_id"; return "site_id"
        if "Year" in cols:
            if _CLUSTER_SAID["n"] < 1:
                info(f"{n_} sub-watershed(s) in this sample: the sub-watershed is the cluster, but fewer than "
                     f"{MIN_SWS_CLUSTERS} clusters cannot carry cluster-robust inference -- clustering on Year instead "
                     f"(each year's core-vs-ring contrast is one independent draw). With >= {MIN_SWS_CLUSTERS} sub-watersheds "
                     f"the pooled run clusters on them.")
                _CLUSTER_SAID["n"] += 1
            LAST_CLUSTER_USED["value"] = f"Year ({n_} sub-watershed{'s' if n_ != 1 else ''})"; return "Year"
    LAST_CLUSTER_USED["value"] = col if col in cols else None
    return col

def _stream_cluster_key(col):
    """v20.41: the cluster for estimators that read the files in chunks (no frame to inspect): the sub-watershed when
    the panel holds several, the Year when it holds one -- the same rule as _cluster_key."""
    if col not in ("subwshed_id", "site_id", "cluster_id"):
        LAST_CLUSTER_USED["value"] = col; return col
    mode = ACTIVE.get("cluster", "site")
    if mode == "year":
        LAST_CLUSTER_USED["value"] = "Year"; return "Year"
    if mode == "subwshed":
        LAST_CLUSTER_USED["value"] = col; return col
    try:
        sws = [int(s) for s in sites_in_panel() if int(s) != 0]
        if SITE_FILTER is not None:
            keep = SITE_FILTER if isinstance(SITE_FILTER, (list, tuple, set)) else [SITE_FILTER]
            sws = [s for s in sws if s in set(int(k) for k in keep)]
    except Exception:
        sws = []
    if len(sws) >= MIN_SWS_CLUSTERS:
        LAST_CLUSTER_USED["value"] = "site_id"; return "site_id"
    LAST_CLUSTER_USED["value"] = f"Year ({len(sws)} sub-watershed{'s' if len(sws) != 1 else ''})"; return "Year"

def _unit_key(df, col):
    """v20.29: 'pixel_id' used as a FIXED EFFECT / panel unit becomes the scenario's unit (pixel x season by default)."""
    if col == "pixel_id" and "unit_id" in getattr(df, "columns", ()) and ACTIVE.get("unit_fe", "pixel_season") == "pixel_season":
        return "unit_id"
    return col

# ====================== v20.29: PRE-BUILT PACKAGES -- used once VERIFIED on this machine ======================
# The core estimators hand their computation to peer-reviewed packages: 2x2 TWFE, the event study and the wild
# cluster bootstrap to pyfixest; Callaway-Sant'Anna to diff-diff. A package is used only after P12 has run it on THIS
# machine against the validated engine, on a panel with a known answer, and they agreed (prebuilt_verified.json,
# per package VERSION -- an upgrade must be re-verified). Until then, or if the package fails at run time, the
# engine runs and says so. Every result records which one produced it (column `engine`). The engine's data checks
# (missing values, frozen series, coverage notes) always run first, whichever computes the estimate.
PREBUILT_MODE = os.environ.get("REWARD_PREBUILT_MODE") or "auto"   # "auto": a verified package computes, else the engine | "require": package or refuse | "off"
                                                                     # (v20.58: the env var is for the checks -- validate_model_parity.py --engine)
PREBUILT_ROUTES = {"twfe": "pyfixest", "event_study": "pyfixest", "wild_bootstrap": "pyfixest",
                   "callaway_santanna": "diff_diff"}
PREBUILT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prebuilt_verified.json")
LAST_ENGINE = {}
PACKAGE_RUN_START = {}          # v20.58: (model, outcome) -> when prebuilt_first ran for it (a PACKAGE file older than that is stale)

def _pkg_version(pkg):
    """Installed version of a package, or None."""
    try:
        from importlib import metadata as _md
        return _md.version(pkg.split("[")[0].replace("_", "-"))            # v20.58: "dask[distributed]" -> dask
    except Exception:
        try:
            import importlib as _il
            return str(getattr(_il.import_module(pkg), "__version__", "unknown"))
        except Exception:
            return None

def _prebuilt_verified():
    try:
        with open(PREBUILT_FILE, encoding="utf-8") as fh: return json.load(fh)
    except Exception:
        return {}

def prebuilt_status(verbose=True):
    """Which estimator is computed by which package on this machine, and why."""
    rec = _prebuilt_verified(); rows = []
    for route, pkg in PREBUILT_ROUTES.items():
        ver = _pkg_version(pkg); v = rec.get(route, {})
        used = PREBUILT_MODE != "off" and bool(ver) and bool(v.get("verified")) and v.get("version") == ver
        rows.append({"estimator": route, "package": pkg, "installed": ver or "not installed",
                     "verified_version": v.get("version", ""), "verified": bool(v.get("verified")),
                     "computes_now": pkg if used else "engine", "detail": v.get("detail", "run P12 to verify")})
    out = pd.DataFrame(rows)
    if verbose:
        info(f"pre-built packages (PREBUILT_MODE = {PREBUILT_MODE!r}):"); print(out.to_string(index=False))
    return out

_AUTO_INSTALL_TRIED = set()
def _use_prebuilt(route):
    if PREBUILT_MODE == "off": return False
    pkg = PREBUILT_ROUTES[route]; ver = _pkg_version(pkg); v = _prebuilt_verified().get(route, {})
    if not ver and AUTO_INSTALL_PACKAGES and pkg not in _AUTO_INSTALL_TRIED:      # v20.55: the package first -- fetched now when
        _AUTO_INSTALL_TRIED.add(pkg)                                                 # missing (wheel, then source), then verified
        how = install_python_package(PYTHON_PACKAGES.get(pkg, (pkg,))[0], verbose=True)   # on the known answer before it computes
        ver = _pkg_version(pkg)
        if ver:
            try:
                verify_prebuilt_routes([r_ for r_, p_ in PREBUILT_ROUTES.items() if p_ == pkg], verbose=True); v = _prebuilt_verified().get(route, {})
            except Exception as e:
                warn(f"{pkg} installed ({how}) but its verification failed: {e} -- the engine computes {route}")
    good = bool(ver) and bool(v.get("verified")) and v.get("version") == ver
    if not good and PREBUILT_MODE == "require":
        raise InsufficientDataError(f"PREBUILT_MODE = 'require' but {route} ({pkg}) is "
                                    f"{'not installed' if not ver else 'not verified for version ' + ver} -- run P12")
    return good

def _route_call(route, fn, *a, **kw):
    try:                                                   # v20.45: a package copies the frame -- only when it fits
        d0 = a[0] if a and isinstance(a[0], pd.DataFrame) else None
        if d0 is not None:
            import _hardware as _Hh
            need = float(len(d0)) * (min(len(d0.columns), 40) + 6) * 8 * 4
            bud = _Hh.ram_budget_bytes()
            if bud is not None and need > bud:                      # v20.57: YOUR 98 % rule is the only limit. v20.52 had
                # switched this check off entirely: a package copy larger than the RAM left below 98 % was attempted and
                # could kill the kernel. The package is still used first whenever its copy fits below the ceiling.
                LAST_ENGINE[route] = (f"engine (the package would need ~{need / 2**30:.0f} GB; {bud / 2**30:.0f} GB left below "
                                      f"the {_Hh.MEMORY_CEILING:.0%} RAM ceiling)")
                warn(f"{route}: {LAST_ENGINE[route]} -- your 98 % rule; the verified engine computes the same estimate"); return None
    except Exception:
        pass
    try:
        out = fn(*a, **kw)
        LAST_ENGINE[route] = f"{PREBUILT_ROUTES[route]} {_pkg_version(PREBUILT_ROUTES[route])}"
        return out
    except Exception as e:
        if PREBUILT_MODE == "require": raise
        warn(f"{route}: {PREBUILT_ROUTES[route]} failed ({type(e).__name__}: {str(e)[:120]}) -- the validated engine computes instead")
        LAST_ENGINE[route] = "engine (package failed)"
        return None

# v20.58: pyfixest's demeaning converged to its DEFAULT tolerance (1e-6) only: it stopped ~4 passes early, and the SE's 8th digit then
# depended on the order in which it visited the fixed effects -- an order that follows Python's string hashing, which differs from one
# process to the next (found by the poison test: M31's cross-check SE differed by 4.5e-8 between two runs of the same rows; reproduced
# with PYTHONHASHSEED 0 / 1 on one frame). Every pyfixest fit here converges to PYFIXEST_FIXEF_TOL, as the engine's own demeaning (1e-10):
# the same numbers in every process, to ~1e-14, and closer to the exact solution; a converging fit needs a few more passes only.
PYFIXEST_FIXEF_TOL = 1e-12
PYFIXEST_FIXEF_MAXITER = 100_000
def _pf_demeaner_kw(fn, kw):
    """The tight convergence for a pyfixest estimation call (feols / fepois / feglm), unless the call sets its own."""
    if "demeaner" in kw or "fixef_tol" in kw or getattr(fn, "__name__", "") not in ("feols", "fepois", "feglm"): return kw
    try:
        import inspect as _ins
        ps = _ins.signature(fn).parameters
        kw = dict(kw)
        if "demeaner" in ps:                                           # pyfixest >= 0.4x: the typed configuration
            from pyfixest.demeaners import MapDemeaner as _MD
            kw["demeaner"] = _MD(fixef_tol=PYFIXEST_FIXEF_TOL, fixef_maxiter=PYFIXEST_FIXEF_MAXITER)
        elif "fixef_tol" in ps:                                        # older pyfixest: the plain arguments
            kw["fixef_tol"] = PYFIXEST_FIXEF_TOL
            if "fixef_maxiter" in ps: kw["fixef_maxiter"] = PYFIXEST_FIXEF_MAXITER
    except Exception:
        pass
    return kw

def _pf_quiet(fn, *a, **kw):
    """v20.44: run a pyfixest call; its 'N singleton fixed effect(s) dropped' warning becomes one explained line.
    v20.58: every estimation converges to PYFIXEST_FIXEF_TOL (see above)."""
    import warnings as _w
    kw = _pf_demeaner_kw(fn, kw)
    with _w.catch_warnings(record=True) as ws:
        _w.simplefilter("always")
        out = fn(*a, **kw)
    for w in ws:
        m = re.search(r"(\d+) singleton", str(w.message))
        if m:
            n = int(m.group(1)); LAST_FIT_INFO["pyfixest_singletons_dropped"] = n
            if not _LANDUSE_SAID.get(("single", n)):
                info(f"pyfixest dropped {n:,} singleton fixed effects -- series seen once, which carry no within-series "
                     f"information: the estimate is unchanged; pyfixest's n_obs excludes them, the engine's keeps them")
                _LANDUSE_SAID[("single", n)] = True
        else:
            _w.warn_explicit(w.message, w.category, w.filename, w.lineno)
    return out

def _pf_frame(df, cols, codes=()):
    """The columns a package needs; fixed-effect / cluster keys as compact integer codes (any id type, no precision loss)."""
    data = df[list(dict.fromkeys(cols))].copy()
    for c_ in codes: data[c_] = pd.factorize(data[c_])[0].astype("int64")
    return data.reset_index(drop=True)

def _pf_twfe(df, y_col, d_col, fe1, fe2, cl, covs):
    import pyfixest as pf
    data = _pf_frame(df, [y_col, d_col, fe1, fe2, cl] + list(covs), codes=(fe1, fe2, cl))
    fit = _pf_quiet(pf.feols, f"{y_col} ~ {' + '.join([d_col] + list(covs))} | {fe1} + {fe2}", data=data, vcov={"CRV1": cl})
    return float(fit.coef()[d_col]), float(fit.se()[d_col])

def _pf_event_study(d, y_col, tc_col, et, periods, fe1, fe2, cl, covariates=None):
    """The SAME design as the engine: one dummy treat x 1{event_time == k} per estimated period k (+ the same covariates, v20.58)."""
    import pyfixest as pf
    cv = [c_ for c_ in (covariates or []) if c_ in d.columns]
    data = _pf_frame(d, [y_col, fe1, fe2, cl] + cv, codes=(fe1, fe2, cl))
    tc = pd.to_numeric(d[tc_col], errors="coerce").values.astype(float); et_ = np.asarray(et)
    names = []
    for k in periods:
        nm = f"ev_{'m' if k < 0 else 'p'}{abs(int(k))}"; data[nm] = tc * (et_ == k); names.append((nm, int(k)))
    fit = _pf_quiet(pf.feols, f"{y_col} ~ {' + '.join([n for n, _ in names] + cv)} | {fe1} + {fe2}", data=data, vcov={"CRV1": cl})
    co, se = fit.coef(), fit.se()
    return {k: (float(co[n]), float(se[n])) for n, k in names if n in co.index}

def _pf_wild_bootstrap(df, y_col, d_col, fe1, fe2, cl, reps, seed, weights, covariates=None):
    import pyfixest as pf
    cv = [c for c in (covariates or []) if c in df.columns]                   # v20.58: the SAME regression as M01 (the engine partials them out)
    data = _pf_frame(df, [y_col, d_col, fe1, fe2, cl] + cv, codes=(fe1, fe2, cl))
    fit = _pf_quiet(pf.feols, f"{y_col} ~ {' + '.join([d_col] + cv)} | {fe1} + {fe2}", data=data, vcov={"CRV1": cl})
    res = fit.wildboottest(param=d_col, reps=int(reps), seed=int(seed), weights_type=str(weights))
    ser = res.iloc[0] if isinstance(res, pd.DataFrame) else pd.Series(res)
    key = [k for k in ser.index if "Pr" in str(k)]
    if not key: raise KeyError(f"no p-value in the wildboottest result ({list(ser.index)})")
    return float(ser[key[0]])

_CS_LAST_FIT = {}
def _cs_event_study_table(est, data, **kw):
    """v20.44: diff-diff >= 3.x fits once and aggregates after (results.aggregate('event_study')); fit(aggregate=) is
    deprecated and goes in 4.0. Older versions only have fit(aggregate=). Either way -> the event-study table.
    v20.58: the fit's overall ATT (the SIMPLE aggregation, as did::aggte(type = "simple")) and its SE are kept in _CS_LAST_FIT."""
    import warnings as _w
    r = est.fit(data, **kw)
    _CS_LAST_FIT.clear()
    try: _CS_LAST_FIT.update({"overall_att": float(getattr(r, "overall_att")), "overall_se": float(getattr(r, "overall_se"))})
    except Exception: pass
    agg = None
    if hasattr(r, "aggregate"):
        try:
            agg = r.aggregate("event_study")
        except Exception:
            agg = None
    if agg is None:                                          # an older diff-diff
        with _w.catch_warnings():
            _w.simplefilter("ignore", FutureWarning)
            agg = r = est.fit(data, aggregate="event_study", **kw)
    for obj, args in ((agg, ("event_study",)), (agg, ()), (r, ("event_study",))):
        try:
            if hasattr(obj, "to_dataframe"): return obj.to_dataframe(*args)
        except Exception:
            continue
    return pd.DataFrame(getattr(agg, "event_study_effects", getattr(r, "event_study_effects", {})))

def _dd_callaway_santanna(df, y_col, unit_col, time_col, first_treat_col):
    """diff-diff CallawaySantAnna -> {event_time: ATT}. v20.58: the never-treated series are the comparison when there are any (as the engine
    and R's did::att_gt(control_group = "nevertreated")); not-yet-treated only without them."""
    import diff_diff as dd
    data = df[[c_ for c_ in dict.fromkeys([unit_col, time_col, y_col, first_treat_col, "site_id"]) if c_ in df.columns]].copy()
    data["unit__"] = pd.factorize(data[unit_col])[0].astype("int64")
    ft = pd.to_numeric(data[first_treat_col], errors="coerce").values.astype(float)
    data["first_treat__"] = np.where(np.isfinite(ft), ft, 0).astype("int64")
    data["site__"] = pd.to_numeric(data["site_id"], errors="coerce").fillna(0).astype("int64") if "site_id" in data.columns else 0
    data = data.groupby(["unit__", time_col], as_index=False).agg(y__=(y_col, "mean"), first_treat__=("first_treat__", "first"), site__=("site__", "first"))
    # v20.58 (as R's m05_cs): the sub-watersheds are the clusters with >= MIN_SWS_CLUSTERS of them; else each series (the analytical
    # influence-function SE -- identical to R's did::aggte with bstrap = FALSE)
    _cl = "site__" if int((data["site__"] > 0).groupby(data["site__"]).any().sum()) >= MIN_SWS_CLUSTERS else None
    est = dd.CallawaySantAnna(control_group="never_treated" if (data["first_treat__"] == 0).any() else "not_yet_treated", base_period="universal", cluster=_cl)
    tab = _cs_event_study_table(est, data, outcome="y__", unit="unit__", time=time_col, first_treat="first_treat__")
    _CS_LAST_FIT["se_how"] = ("the analytical influence-function SE of the simple aggregation, " +
                              ("clustered by sub-watershed" if _cl else "each series a draw (= R's did::aggte, bstrap = FALSE)"))
    ecol = next(c_ for c_ in ("event_time", "relative_period", "rel_time", "e", "relative_time") if c_ in tab.columns)
    acol = next(c_ for c_ in ("att", "effect", "estimate", "ATT") if c_ in tab.columns)
    return {int(e): float(a) for e, a in zip(tab[ecol], tab[acol])}

# ====================== v20.42: PRE-BUILT PACKAGES FIRST, FOR EVERY MODEL THAT HAS ONE ======================
# layer "function": the package computes INSIDE the engine function the model calls (pyfixest / wildboottest /
#                   diff-diff); the engine code runs only if the package is missing, unverified or fails.
# layer "model":    the package pipeline (python_prebuilt/) computes the model's PRIMARY result before the engine
#                   code; the engine then runs as the fallback -- and, when the package succeeded, as the cross-check.
# layer "engine":   no established Python package for this estimator (or the engine is the safer implementation);
#                   the reason is stated, and any TWFE regression inside it still runs on pyfixest.
PREBUILT_PACKAGES = {"pyfixest": "pyfixest", "wildboottest": "wildboottest", "diff_diff": "diff-diff",
                     "econml": "econml", "doubleml": "doubleml", "esda": "esda", "libpysal": "libpysal"}
_F, _M, _E = "function", "model", "engine"
PREBUILT_MODELS = {
    "M01": dict(layer=_F, package="pyfixest", route="twfe", label="pyfixest feols"),
    "M02": dict(layer=_F, package="pyfixest", route="event_study", label="pyfixest feols i()"),
    "M03": dict(layer=_E, reason="no Python package; R DRDID::drdid -- else the existing implementation"),
    "M04": dict(layer=_E, reason="no Python package; R qte::CiC -- else the existing implementation"),
    "M05": dict(layer=_F, package="diff_diff", route="callaway_santanna", label="diff-diff CallawaySantAnna"),
    # v20.58: M06's headline is the TWO-WAY FE SLOPE on the time-varying fund dose (the effect per unit of dose) -- R's m06_dose (fixest) and this
    # engine (pyfixest inside). v20.57 took diff-diff ContinuousDiD's ACRT as the PRIMARY: a DIFFERENT estimand (the derivative of a dose-response
    # curve ACROSS units, with each unit's dose fixed at its maximum) -- 1.17 against R's 2.74 / the engine's 2.84 on the poison test. It is
    # reported beside the headline (dose_response_continuousdid_<outcome>.csv) when the doses differ across units (several sub-watersheds).
    "M06": dict(layer=_F, package="pyfixest", route="twfe", label="pyfixest feols (the slope on the fund dose)"),
    "M07": dict(layer=_F, package="pyfixest", route="twfe", label="pyfixest feols (the surrogate DiD's regression)"),
    "M08": dict(layer=_E, reason="IV-DiD: needs an instrument (data that do not exist); pyfixest / fixest 2SLS would compute it once it does"),
    "M09": dict(layer=_E, reason="R fixest::sunab (the R pipeline's own code) when verified, else the engine's fixest-equivalent interaction-weighted "
                "estimator -- v20.58: diff-diff's SunAbraham has YEAR effects on a season-matched outcome, another design than R's (0.053255 against "
                "0.053274); it stays the supplementary check of python_prebuilt/dd_pipeline.py"),
    "M10": dict(layer=_E, reason="no Python package; R fixest triple differences -- else the existing implementation"),
    "M11": dict(layer=_M, package="diff_diff", runner="dd", label="diff-diff SyntheticDiD"),
    "M12": dict(layer=_E, reason="no Python package; R fixest first differences (chained) -- else the existing implementation"),
    "M13": dict(layer=_E, reason="no Python package; R DIDmultiplegtDYN -- else the existing implementation"),
    "M14": dict(layer=_E, reason="no Python package; R MatchIt + fixest -- else the existing implementation"),
    "M15": dict(layer=_E, reason="no Python package; R fixest placebo timing -- else the existing implementation"),
    "M16": dict(layer=_E, reason="joint pre-trends F: the engine's rank-safe test is kept (a package Wald test on a near-singular lead "
                                "covariance gave F = 4748 in v20.33); its event-study leads come from the pyfixest route"),
    "M17": dict(layer=_M, package="esda", runner="sp", label="PySAL esda Moran", needs="latitude / longitude"),
    "M18": dict(layer=_M, package="esda", runner="sp", label="PySAL esda Moran_Local", needs="latitude / longitude"),
    "M19": dict(layer=_E, reason="no Python package; R lme4 + performance::icc (pixel sample) -- else the existing implementation"),
    "M20": dict(layer=_F, package="pyfixest", route="twfe", label="pyfixest feols (per sub-watershed)"),
    "M21": dict(layer=_F, package="pyfixest", route="twfe", label="pyfixest feols"),
    "M22": dict(layer=_M, package="diff_diff", runner="dd", label="diff-diff BaconDecomposition", needs=">= 2 treatment cohorts"),
    "M23": dict(layer=_F, package="pyfixest", route="wild_bootstrap", label="pyfixest + wildboottest (Webb)"),
    "M24": dict(layer=_F, package="pyfixest", route="twfe", label="pyfixest feols (every ring in one fit, as R's fixest i(ring, post))"),
    "M25": dict(layer=_F, package="pyfixest", route="twfe", label="pyfixest feols (each permutation)"),
    "M26": dict(layer=_E, reason="no Python package; R fixest interaction -- else the existing implementation"),
    "M27": dict(layer=_M, package="diff_diff", runner="dd", label="diff-diff ImputationDiD (BJS)", needs=">= 2 treatment cohorts"),
    "M28": dict(layer=_E, reason="no Python package; R did2s -- else the existing implementation"),
    "M29": dict(layer=_E, reason="no Python package; R fixest exposure -- else the existing implementation"),
    "M30": dict(layer=_E, reason="no Python package; R did::aggte(group) -- else the existing implementation"),
    # v20.58: M31 is the stacked two-way FE of R's m31_stacked (clean controls, window -3..3 truncated to the data, stack x unit and stack x
    # year effects) -- the R fixest route first, this engine (the same design, pyfixest inside) as the cross-check. diff-diff's StackedDiD is a
    # DIFFERENT estimator (Wing et al. Q-weights, cohorts whose window leaves the data TRIMMED: your 2025 series dropped) -- 0.0547 against
    # R's 0.0512 on the poison test; it is no longer the headline.
    "M31": dict(layer=_F, package="pyfixest", route="twfe", label="pyfixest feols on the stacked data (the R fixest route first)"),
    "M32": dict(layer=_E, reason="no Python package; R etwfe -- else the existing implementation"),
    "M33": dict(layer=_E, reason="no Python package; R WeightIt (ebal) + fixest -- else the existing implementation"),
    "M34": dict(layer=_E, reason="HonestDiD on M02's event study: R HonestDiD (the R pipeline's own code, through run_one.R) when verified, "
                "else the engine's honest_did_summary -- the same base and target; diff-diff's HonestDiD takes a Callaway-Sant'Anna event study "
                "(another base: v20.57's R-vs-Python difference) and stays the supplementary check of python_prebuilt/dd_pipeline.py"),
    "M35": dict(layer=_E, reason="no Python package; R quantreg (pixel sample) -- else the existing implementation"),
    "M36": dict(layer=_F, package="pyfixest", route="twfe", label="pyfixest feols (TWFE benchmark); interactive FE by the engine"),
    "M37": dict(layer=_E, reason="no Python package; R fect (matrix completion) -- else the existing implementation"),
    "M38": dict(layer=_E, reason="no Python package; R gsynth -- else the existing implementation"),
    "M39": dict(layer=_M, package="econml", runner="ml", label="econml CausalForestDML (CATE by covariate)", needs="covariates"),
    "M40": dict(layer=_M, package="econml", runner="ml", label="econml LinearDML / DoubleML PLR", needs="covariates"),
    "M41": dict(layer=_M, package="econml", runner="ml", label="econml meta-learners (S / T / X)", needs="covariates"),
    "M42": dict(layer=_M, package="econml", runner="ml", label="econml DRLearner", needs="covariates"),
    "M43": dict(layer=_M, package="econml", runner="ml", label="econml CausalForestDML", needs="covariates"),
    "M44": dict(layer=_E, reason="no Python package; R bartCause -- else the existing implementation"),
    "M45": dict(layer=_E, reason="no Python package for the synthetic control itself (scikit-learn's ElasticNetCV is its solver); R glmnet "
                "(the same estimator, R's m45) when verified -- else the existing implementation"),
}

def _prebuilt_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "python_prebuilt")

def _prebuilt_module(runner):
    import importlib
    if _prebuilt_dir() not in sys.path: sys.path.insert(0, _prebuilt_dir())
    return importlib.import_module({"dd": "dd_pipeline", "ml": "ml_spatial_pipeline", "sp": "ml_spatial_pipeline"}[runner])

def _run_model_package(model, outcome, write=False):
    spec = PREBUILT_MODELS[model]; mod = _prebuilt_module(spec["runner"]); me = sys.modules[__name__]
    if spec["runner"] == "dd":
        res = mod.run(outcome, C=me, models=[model], write=write)
    elif spec["runner"] == "ml":
        res = mod.run_ml(outcome, C=me, models=(model,))
    else:
        r17, lisa = mod.run_spatial(outcome, C=me)                # returns (Moran dict, LISA table)
        return r17 if model == "M17" else lisa
    return res.get(model) if isinstance(res, dict) else None

# ====================== v20.43: R PACKAGES -- the second choice; the existing implementation the last ======================
R_SCRIPT = None                      # path to Rscript; None = found automatically (PATH, R_HOME, C:\Program Files\R\R-*)
R_TIMEOUT = 7200                     # seconds for one model on the full panel
R_BASE_PACKAGES = ["data.table", "jsonlite", "arrow", "fixest"]
R_GITHUB = {"ritest": "grantmcdermott/ritest", "synthdid": "synth-inference/synthdid"}
R_ROUTES = {                         # model: the R package(s) R/lib/models_prebuilt.R uses for it
    "M03": ["DRDID"], "M04": ["qte"], "M09": ["fixest"], "M10": ["fixest"], "M12": ["fixest"], "M13": ["DIDmultiplegtDYN"],
    "M14": ["MatchIt", "fixest"], "M15": ["fixest"], "M17": ["spdep"], "M18": ["spdep"], "M19": ["lme4", "performance"],
    "M20": ["metafor", "fixest"], "M22": ["bacondecomp"], "M24": ["fixest"], "M25": ["ritest", "fixest"], "M26": ["fixest"],
    "M27": ["didimputation"], "M28": ["did2s"], "M29": ["fixest"], "M30": ["did"], "M31": ["fixest"], "M32": ["etwfe"],
    "M33": ["WeightIt", "fixest"], "M35": ["quantreg"], "M36": ["fect"], "M37": ["fect"], "M38": ["gsynth"], "M39": ["grf"],
    "M40": ["DoubleML", "mlr3", "mlr3learners", "ranger"], "M41": ["grf"], "M42": ["grf"], "M43": ["grf"], "M44": ["bartCause"],
    "M45": ["glmnet"],               # v20.58: the elastic-net synthetic control on the core-vs-ring series (as the engine; v20.57: synthdid, site level)
    "M34": ["HonestDiD", "fixest"],  # v20.58: HonestDiD on M02's event study -- R's core model through the bridge (run_one.R, CORE_R)
}
_R_CACHE = {}

def find_rscript():
    """Rscript: R_SCRIPT if set, else PATH, R_HOME, or the newest R under C:\\Program Files\\R. None if R is absent."""
    import shutil, glob as _gl
    if R_SCRIPT and os.path.exists(R_SCRIPT): return R_SCRIPT
    hit = shutil.which("Rscript") or shutil.which("Rscript.exe")
    if hit: return hit
    home = os.environ.get("R_HOME")
    cands = ([os.path.join(home, "bin", "Rscript.exe"), os.path.join(home, "bin", "Rscript")] if home else [])
    cands += sorted(_gl.glob(r"C:\Program Files\R\R-*\bin\Rscript.exe") + _gl.glob(r"C:\Program Files\R\R-*\bin\x64\Rscript.exe"), reverse=True)
    for p in cands:
        if os.path.exists(p): return p
    return None

def r_versions(packages=None, refresh=False):
    """{'R': version, package: version or None} -- one Rscript call, cached for the session."""
    rs = find_rscript()
    if not rs: return {}
    pk = sorted(set(packages or (R_BASE_PACKAGES + [p for v in R_ROUTES.values() for p in v])))
    key = (rs, tuple(pk))
    if key in _R_CACHE and not refresh: return _R_CACHE[key]
    code = ("p <- c(" + ",".join(f"'{x}'" for x in pk) + "); v <- sapply(p, function(x) tryCatch(as.character(utils::packageVersion(x)), "
            "error = function(e) 'NA')); cat(paste0('R=', R.version$major, '.', R.version$minor), paste0(p, '=', v), sep = '\\n')")
    import subprocess as _sp
    try:
        r = _sp.run([rs, "--vanilla", "-e", code], capture_output=True, text=True, timeout=120)
        out = {k: (None if v == "NA" else v) for k, v in (l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)}
    except Exception as e:
        out = {"_error": str(e)}
    _R_CACHE[key] = out
    return out

def install_r_packages(packages=None, verbose=True):
    """Install missing R packages through the R pipeline's own chain (lib/reward_packages.R: CRAN binary -> source ->
    author's r-universe -> GitHub -> source archive -> mirror). Needs internet. Returns True when all are installed."""
    st = r_package_status(install=True, verbose=verbose)
    if st is None:
        warn("R is not installed (or Rscript is not found): set R_SCRIPT in P00_Settings, or install R from https://cran.r-project.org"); return False
    if packages:
        st = st[st.package.isin(list(packages))]
    return bool(st.installed.all())

def _r_signature(model):
    v = r_versions()
    return "R " + str(v.get("R")) + "; " + ", ".join(f"{p} {v.get(p)}" for p in R_BASE_PACKAGES[:1] + R_ROUTES.get(model, []))

def _r_input_path(outcome, frame=None):
    """What the R side reads: the package input (parquet when R has arrow, else CSV)."""
    import tempfile as _tf
    have = r_versions()
    if frame is not None:
        p = os.path.join(_tf.mkdtemp(prefix="reward_r_in_"), "input.csv"); frame.to_csv(p, index=False); return p
    stem = package_input_ready(outcome)                   # v20.54: rebuilt when cut from an older panel or other sites
    if os.path.exists(stem + ".parquet") and have.get("arrow"): return stem + ".parquet"
    if os.path.exists(stem + ".csv"): return stem + ".csv"
    warn("R has no 'arrow' package: writing the package input as CSV for R (slower; install arrow in R)")
    pd.read_parquet(stem + ".parquet").to_csv(stem + ".csv", index=False); return stem + ".csv"

def _rm_temp(path):
    """v20.58: remove a temporary folder this pipeline made (the R bridge's input frame and output, the package status, the verification
    runs) -- they were left in the system's temp folder at every call: 3,900 folders / 4.7 GB after the validation runs here, and a copy of
    the model's input frame per R call on your machine. REWARD_KEEP_TEMP=1 keeps them (to inspect an R call)."""
    import shutil as _sh, tempfile as _tf
    try:
        if path and not os.environ.get("REWARD_KEEP_TEMP") and os.path.isdir(path) \
                and os.path.abspath(path).startswith(os.path.abspath(_tf.gettempdir())) and os.path.basename(path).startswith("reward_"):
            _sh.rmtree(path, ignore_errors=True)
    except Exception:
        pass

def _run_r_model(model, outcome, frame=None, timeout=None):
    """Run ONE model through R/lib/run_one.R (the bundle's R folder); returns the parsed result.json (raises with R's own error)."""
    import subprocess as _sp, tempfile as _tf
    rs = find_rscript()
    if not rs: raise RuntimeError("R is not installed (Rscript not found)")
    script = r_bridge_script()
    out = _tf.mkdtemp(prefix=f"reward_r_{model}_")
    inp = None
    try:
        inp = _r_input_path(outcome, frame)
        _env = dict(os.environ); _env["REWARD_COVARIATES"] = ",".join(str(c_) for c_ in (ACTIVE.get("covariates") if ACTIVE.get("covariates") is not None else DEFAULT_COVARIATES))
        r = _sp.run([rs, "--vanilla", script, model, outcome, inp, out], capture_output=True, text=True, timeout=timeout or R_TIMEOUT, env=_env)   # v20.58: the design's covariates
        js = os.path.join(out, "result.json")
        if not os.path.exists(js):
            raise RuntimeError(f"R wrote no result (exit {r.returncode}): {(r.stderr or r.stdout).strip()[-300:]}")
        res = json.load(open(js, encoding="utf-8"))
        if not res.get("ok"):
            raise RuntimeError(f"R: {res.get('error') or 'no usable estimate'}")
        return res
    finally:
        _rm_temp(out)
        if frame is not None and inp: _rm_temp(os.path.dirname(inp))   # the frame written for this call only (the package input stays)

def _save_r_primary(model, outcome, res, label):
    rdir = results_dir(model) if "results_dir" in globals() else os.path.join(RESULTS_ROOT, model)
    head = {k: v for k, v in (res.get("head") or {}).items() if not isinstance(v, (list, dict))}
    head.update(outcome=outcome, estimate=res.get("estimate"), se=res.get("se"), p_value=res.get("p_value"),
                engine=label, primary=True)
    if res.get("se_how"): head["se_how"] = str(res["se_how"])            # v20.58: what the package's SE and p are
    if res.get("p_how"): head["p_how"] = str(res["p_how"])
    save_results(head, rdir, f"{model}_PACKAGE_{outcome}.csv")
    if res.get("table"):
        save_results(pd.DataFrame(res["table"]).assign(engine=label), rdir, f"{model}_PACKAGE_table_{outcome}.csv")
    return head

def _try_python_model(model, outcome, verbose):
    spec = PREBUILT_MODELS[model]; pkg = spec["package"]; ver = _pkg_version(pkg); v = _prebuilt_verified().get(f"model:{model}", {})
    if not ver: return None, f"Python {pkg} not installed"
    if not (v.get("verified") and v.get("version") == ver and v.get("frame") == KNOWN_ANSWER_VERSION):
        return None, f"Python {pkg} {ver} not verified for {model} on the v20.58 check panel (season series, a Rabi start a year before the other seasons)"
    try:
        obj = _run_model_package(model, outcome, write=False)
        if obj is None: return None, f"Python {pkg}: no result (needs {spec.get('needs', 'its inputs')})"
        name = f"{spec['label']} ({pkg} {ver})"
        rdir = results_dir(model) if "results_dir" in globals() else os.path.join(RESULTS_ROOT, model)
        if isinstance(obj, pd.DataFrame):
            t = obj.copy(); t["engine"] = name; t["primary"] = True
            if "outcome" not in t.columns: t["outcome"] = outcome
            save_results(t, rdir, f"{model}_PACKAGE_{outcome}.csv"); head = t
        else:
            head = {k: v for k, v in obj.items() if not isinstance(v, (pd.DataFrame, pd.Series)) and not k.startswith("_")}
            if "se" not in head:
                for alt in ("overall_se", "se_att"):
                    if alt in head: head["se"] = head[alt]
            head.update(outcome=outcome, engine=name, primary=True)
            save_results(head, rdir, f"{model}_PACKAGE_{outcome}.csv")
            for k, v in obj.items():
                if isinstance(v, pd.DataFrame): save_results(v.assign(engine=name), rdir, f"{model}_PACKAGE_{k}_{outcome}.csv")
        LAST_ENGINE[model] = {"engine": name, "reason": "verified Python package: PRIMARY result"}
        if verbose: ok(f"{model}: PRIMARY result by {name} -> {model}_PACKAGE_{outcome}.csv (the engine cells below are the cross-check)")
        return head, None
    except Exception as e:
        return None, f"Python {pkg} failed: {type(e).__name__}: {str(e)[:140]}"

def _try_r_model(model, outcome, verbose):
    if model not in R_ROUTES: return None, "no R route"
    if not find_rscript(): return None, "R not installed"
    sig = _r_signature(model); v = _prebuilt_verified().get(f"r:{model}", {})
    miss = [p for p in R_ROUTES[model] if not r_versions().get(p)]
    if miss: return None, f"R package(s) {miss} not installed"
    if not (v.get("verified") and v.get("signature") == sig and v.get("frame") == KNOWN_ANSWER_VERSION):
        return None, f"R route not verified for {sig} on the v20.58 check panel (season series, a Rabi start a year before the other seasons)"
    try:
        res = _run_r_model(model, outcome)
        label = f"{res.get('engine', 'R')} ({sig})"
        head = _save_r_primary(model, outcome, res, label)
        LAST_ENGINE[model] = {"engine": label, "reason": "verified R package: PRIMARY result"}
        if verbose: ok(f"{model}: PRIMARY result by {label} -> {model}_PACKAGE_{outcome}.csv (the engine cells below are the cross-check)")
        return head, None
    except Exception as e:
        return None, f"R failed: {str(e)[:160]}"

def _data_requirement(model):
    """v20.43: does THIS panel meet the model's data requirements? From P00's readiness step (MODEL_READINESS.csv).
    Returns (met, reason). Unknown readiness is treated as met (and said so)."""
    p = os.path.join(RESULTS_ROOT, "MODEL_READINESS.csv")
    if not os.path.exists(p): return True, "readiness not assessed yet (P00 P10)"
    try:
        t = pd.read_csv(p); r = t[t["model"] == model]
        if len(r) and str(r["status"].iloc[0]) == "incomplete-need data":
            why = str(r.get("model_own_gap", r.get("reason", pd.Series([""]))).iloc[0] or r["reason"].iloc[0])
            return False, f"the data do not meet {model}'s requirements ({why[:150]})"
        return True, ""
    except Exception as e:
        return True, f"readiness unreadable ({e})"

def prebuilt_first(model, outcome=None, verbose=True):
    """The model's PRIMARY result from a verified PRE-BUILT package: Python first, then R; None when neither can
    compute it on this data -- the existing implementation then runs, and LAST_ENGINE[model] says why."""
    spec = PREBUILT_MODELS.get(model, {}); outcome = outcome or (current_outcome() if "current_outcome" in globals() else None)
    layer = spec.get("layer", _E); why = []
    PACKAGE_RUN_START[(model, str(outcome))] = _time.time()            # v20.58: what this run's package wrote is newer (_package_headline)
    if PREBUILT_MODE == "off":
        LAST_ENGINE[model] = {"engine": "engine", "reason": "PREBUILT_MODE = 'off'"}; return None
    met, req = _data_requirement(model)                  # your rule: incomplete data -> the existing implementation
    if not met:
        LAST_ENGINE[model] = {"engine": "engine", "reason": req + " -- the existing implementation reports the gap"}
        if verbose: info(f"{model}: {req} -> no package is run; the existing implementation reports the gap")
        return None
    if layer == _M:
        head, r = _try_python_model(model, outcome, verbose)
        if head is not None: return head
        why.append(r)
    if model in R_ROUTES:
        head, r = _try_r_model(model, outcome, verbose)
        if head is not None: return head
        why.append(r)
    if layer == _F:
        LAST_ENGINE[model] = {"engine": spec.get("label", "engine"), "reason": "Python package inside the engine function"
                              + (f" ({'; '.join(why)})" if why else "")}
        return None
    reason = "; ".join(w for w in why if w) or spec.get("reason", "no pre-built package")
    LAST_ENGINE[model] = {"engine": "engine", "reason": reason}
    if PREBUILT_MODE == "require" and layer != _F:
        raise InsufficientDataError(f"PREBUILT_MODE = 'require': {model} -- {reason}")
    if verbose: info(f"{model}: no verified pre-built package can compute it here ({reason}) -> the existing implementation computes")
    return None

def r_bridge_script():
    """v20.45: the R library lives in the bundle's R folder (FINAL/R/lib) -- found from this engine (python/<engine>)
    two levels up, or an older layout's engine/R."""
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "..", "..", "R", "lib", "run_one.R"), os.path.join(here, "..", "R", "lib", "run_one.R")):   # never an old engine/R
        if os.path.exists(p): return os.path.abspath(p)
    return os.path.abspath(os.path.join(here, "..", "..", "R", "lib", "run_one.R"))

def verify_r_models(models=None, verbose=True):
    """Every R route on a panel with a KNOWN answer (+0.05; placebo effects 0; Moran's I = the engine's), per R and
    package version -> prebuilt_verified.json (key 'r:<Mxx>'). An R route is used only after it passes here."""
    rec = _prebuilt_verified(); rows = []
    if not find_rscript():
        if verbose: warn("R not found: the R routes stay off (set R_SCRIPT in P00_Settings if R is installed)")
        return pd.DataFrame(rows)
    vers = r_versions(refresh=True)
    staggered = {"M09", "M22", "M27", "M28", "M30", "M31", "M32"}
    for m in [x for x in R_ROUTES if (models is None or x in models) and in_pipeline(x)]:
        miss = [p for p in R_ROUTES[m] if not vers.get(p)]
        if miss:
            rows.append({"model": m, "r_packages": ", ".join(R_ROUTES[m]), "verified": False, "detail": f"not installed: {miss}"}); continue
        kind = "staggered" if m in staggered else ("sites" if m == "M20" else "block")
        try:
            res = _run_r_model(m, "VERIFY_Y", frame=_known_answer_frame(kind), timeout=1800)
            okv, det = _judge_r_known_answer(m, res)
        except Exception as e:
            okv, det = False, str(e)[:170]
        rec[f"r:{m}"] = {"verified": bool(okv), "signature": _r_signature(m), "detail": det, "frame": KNOWN_ANSWER_VERSION}
        rows.append({"model": m, "r_packages": ", ".join(R_ROUTES[m]), "verified": bool(okv), "detail": det})
    try:
        with open(PREBUILT_FILE, "w", encoding="utf-8") as fh: json.dump(rec, fh, indent=1, default=str)
    except Exception as e:
        warn(f"verdicts not saved ({e})")
    out = pd.DataFrame(rows)
    if verbose and len(out):
        info(f"R routes on a known answer (R {vers.get('R')}):"); print(out.to_string(index=False))
    return out

def _judge_r_known_answer(model, res):
    est = res.get("estimate"); est = float(est) if est is not None else np.nan
    if model == "M15": return abs(est) < 0.01, f"mean placebo effect {est:+.4f} (truth 0)"
    if model == "M24": return abs(est) < 0.01, f"spillover into the nearest ring {est:+.4f} (truth 0: none simulated)"   # v20.58: was judged against 0.05
    if model == "M20":                                                  # v20.58: the headline is Cochran's Q (homogeneous effects simulated)
        h = res.get("head") or {}; pe = float(h.get("pooled_effect")) if h.get("pooled_effect") is not None else np.nan
        pv = float(res.get("p_value")) if res.get("p_value") is not None else np.nan
        return (np.isfinite(est) and est >= 0 and np.isfinite(pv) and pv > 0.001 and abs(pe - 0.05) < 0.015), f"Q {est:.3g}, p {pv:.3g}, pooled {pe:.4f} (truth 0.0500)"
    if model == "M19": return 0 <= est <= 1, f"ICC {est:.3f}"
    if model in ("M17", "M18"):
        I_e = _engine_moran_known_answer(); return abs(est - I_e) < 0.05, f"{'Moran I' if model == 'M17' else 'mean local I'} {est:.4f} vs the engine's {I_e:.4f}"
    tol = 0.025 if model in ("M04", "M35", "M39", "M40", "M41", "M42", "M43", "M44", "M13", "M36", "M37", "M38", "M45") else 0.015
    return abs(est - 0.05) < tol, f"estimate {est:.4f} (truth 0.0500, tolerance {tol})"

KNOWN_ANSWER_VERSION = "20.58-seasons-ml"   # a verdict on an older check panel is re-done (the season starts below; v20.58-ml: the ML headlines as R)
def _known_answer_frame(kind, seed=20260924):
    """A package-input panel with a KNOWN effect: +0.05 for every treated series ("staggered": cohorts 2020 and 2022 plus never-treated;
    "block": one cohort, 2022), or +0.05 per unit of dose ("dose": doses 1 and 2).
    v20.58 -- the structure of YOUR design, so a route that cannot handle it fails here and is never used: every pixel carries three
    SEASON series (Kharif, Rabi, Zaid; each series a unit, as the export), the seasons have their OWN year-to-year shocks, and the start is
    a SEASON -- Rabi of the cohort year, the other seasons the year after (your fund timing). Until v20.57 the panel had one annual row per
    pixel: routes that compare a Rabi series with rings of every season passed it and were biased on your data."""
    staggered = kind == "staggered"
    by_site = kind == "sites"                                  # clusters = the three sites (per-cluster routes, M20)
    rng = np.random.default_rng(seed); rows = []
    shock = {(y, s_): rng.normal(0, 0.02) for y in range(2016, 2026) for s_ in (1, 2, 3)}
    for u in range(300):
        coh0 = (2020.0 if u < 100 else 2022.0 if u < 200 else np.inf) if staggered else (2022.0 if u < 150 else np.inf)
        dose = ((1.0 + (u % 2)) if kind == "dose" else 1.0) if np.isfinite(coh0) else 0.0
        a = rng.normal(0, 0.05); lat = 15.0 + (u // 20) * 0.001; lon = 75.0 + (u % 20) * 0.001
        for s_ in (1, 2, 3):
            coh = coh0 if s_ == 2 else coh0 + 1.0                                          # Rabi first, the other seasons a year later
            for y in range(2016, 2026):
                D = int(np.isfinite(coh) and y >= coh)
                eff = 0.05 * dose * D
                start_s = (coh0 if s_ == 2 else coh0 + 1.0) if np.isfinite(coh0) else ((2022.0 if s_ == 2 else 2023.0) if not staggered else 2022.0)
                rows.append({"pixel_id": 900_000 + u, "unit": (900_000 + u) * 8 + s_, "site_id": 1 + u % 3, "subwshed_id": f"S{1 + u % 3}",
                             "cluster_id": (f"S{1 + u % 3}" if by_site else str(y)), "Year": y, "Season": s_, "period": f"{y}_{s_}",
                             "treat": int(np.isfinite(coh)), "post": int(y >= start_s), "did": D, "event_time": (y - coh) if np.isfinite(coh) else np.nan,
                             "cohort": coh, "buff_km": 0 if np.isfinite(coh) else 1 + u % 5, "dose": dose, "LandUse": 1 + u % 2,
                             "VERIFY_Y": 0.4 + a + (0.06, 0.01, -0.05)[s_ - 1] + 0.01 * (y - 2016) + shock[(y, s_)] + eff + rng.normal(0, 0.01),
                             "Rain": 600 + rng.normal(0, 40), "Tmax": 33 + rng.normal(0, 1), "Tmean": 26 + rng.normal(0, 1),
                             "Tmin": 19 + rng.normal(0, 1), "latitude": lat, "longitude": lon})
    _f = pd.DataFrame(rows); _f.attrs["synthetic"] = True; return _f      # v20.58: a check panel, not your data

def verify_prebuilt_models(models=None, verbose=True):
    """Verify every model-level package route on a panel with a KNOWN answer, per installed version; the verdicts
    go to prebuilt_verified.json (key 'model:<Mxx>'). A route is used only after it passes here."""
    import importlib
    rec = _prebuilt_verified(); rows = []
    mods = [m for m, s in PREBUILT_MODELS.items() if s.get("layer") == _M and (models is None or m in models) and in_pipeline(m)]
    pf_ = _prebuilt_module("dd").__dict__.get("package_input") and importlib.import_module("pf_pipeline")
    saved = dict(ACTIVE); saved_root = RESULTS_ROOT
    import tempfile as _tf
    globals()["RESULTS_ROOT"] = _tf.mkdtemp(prefix="reward_verify_")   # the pipelines' own files never reach your results
    try:
        # v20.58: timing "fixed" -- the check panels carry their own start; the notebook's TREATMENT_TIMING ("fund") left in force made P00's
        # route check score the fund fall-back design instead (both engine and package 0.0372 for the true 0.05 on the twfe route)
        set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, exclude_transition_year=False, timing="fixed")
        for m in mods:
            spec = PREBUILT_MODELS[m]; pkg = spec["package"]; ver = _pkg_version(pkg)
            if not ver:
                rows.append({"model": m, "package": pkg, "installed": "not installed", "verified": False, "detail": "install it (P00 P12)"}); continue
            kind = "staggered" if m in ("M09", "M22", "M27", "M31", "M34") else ("dose" if m == "M06" else "block")
            pf_._FRAME_OVERRIDE["VERIFY_Y"] = _known_answer_frame(kind)
            try:
                obj = _run_model_package(m, "VERIFY_Y", write=False)
                okv, det = _judge_known_answer(m, obj)
            except Exception as e:
                okv, det = False, f"{type(e).__name__}: {str(e)[:150]}"
            finally:
                pf_._FRAME_OVERRIDE.pop("VERIFY_Y", None)
            rec[f"model:{m}"] = {"verified": bool(okv), "version": ver, "package": pkg, "detail": det, "frame": KNOWN_ANSWER_VERSION}
            rows.append({"model": m, "package": pkg, "installed": ver, "verified": bool(okv), "detail": det})
    finally:
        _vroot = RESULTS_ROOT
        ACTIVE.clear(); ACTIVE.update(saved); globals()["RESULTS_ROOT"] = saved_root
        _rm_temp(_vroot)                                                # v20.58: the verification's own results (a temporary folder)
        try:
            with open(PREBUILT_FILE, "w", encoding="utf-8") as fh: json.dump(rec, fh, indent=1, default=str)
        except Exception as e:
            warn(f"verdicts not saved ({e})")
    out = pd.DataFrame(rows)
    if verbose and len(out):
        info("model-level pre-built routes on a known answer (+0.05):"); print(out.to_string(index=False))
    return out

def _judge_known_answer(model, obj):
    """Does the package recover the known +0.05?"""
    if obj is None: return False, "no result"
    def num(d, *keys):
        for k in keys:
            if isinstance(d, dict) and k in d and d[k] is not None and np.isfinite(float(d[k])): return float(d[k])
        return np.nan
    if model in ("M27", "M31", "M11"):
        a = num(obj, "att"); return abs(a - 0.05) < 0.01, f"ATT {a:.4f} (truth 0.0500)"
    if model == "M06":
        a = num(obj, "att_per_unit_dose"); return abs(a - 0.05) < 0.01, f"ATT per unit dose {a:.4f} (truth 0.0500)"
    if model in ("M40", "M42", "M43", "M39", "M41") and isinstance(obj, dict):   # v20.58: M39 / M41 give a headline (+ their tables) as R
        a = num(obj, "estimate", "ate", "att"); s_ = num(obj, "se")
        return abs(a - 0.05) < 0.02, f"{obj.get('target', 'ATE')} {a:.4f} (truth 0.0500)" + (f", SE {s_:.4f}" if np.isfinite(s_) else "")
    if model == "M34" and isinstance(obj, dict):                        # v20.58: the effect whose robustness is assessed + its breakdown
        a = num(obj, "estimate"); b_ = obj.get("breakdown_Mbar")
        return (abs(a - 0.05) < 0.01 and b_ is not None and float(b_) >= 0), f"effect {a:.4f} (truth 0.0500), breakdown Mbar {float(b_) if b_ is not None else float('nan'):.3g}"
    if model in ("M09", "M22", "M41", "M39", "M34", "M18") and isinstance(obj, pd.DataFrame):
        cols = [c for c in ("effect", "att", "estimate", "ate", "ci_low", "local_I", "weight") if c in obj.columns]
        if model == "M09":
            p = obj[pd.to_numeric(obj.get("event_time", obj.get("relative_period", pd.Series(dtype=float))), errors="coerce") >= 0]
            e = pd.to_numeric(p[[c for c in ("effect", "att", "estimate") if c in p.columns][0]], errors="coerce").mean() if len(p) else np.nan
            return abs(e - 0.05) < 0.01, f"post-period effects mean {e:.4f} (truth 0.0500)"
        if model == "M22":
            return bool(len(obj)) and "weight" in obj.columns and abs(float(obj["weight"].sum()) - 1) < 0.02, f"{len(obj)} comparisons, weights sum {obj['weight'].sum():.3f}"
        if model == "M34":
            r0 = obj.sort_values("M").iloc[0]; return bool(r0["ci_low"] <= 0.05 <= r0["ci_high"]), f"M = {r0['M']}: CI [{r0['ci_low']:.4f}, {r0['ci_high']:.4f}] covers 0.05"
        if model in ("M41", "M39"):
            col = "cate_mean" if "cate_mean" in obj.columns else ("ate" if "ate" in obj.columns else "att")
            a = pd.to_numeric(obj[col], errors="coerce").mean(); return abs(a - 0.05) < 0.02, f"mean effect {a:.4f} (truth 0.0500)"
        if model == "M18" and "local_I" in obj.columns:
            I_e = _engine_moran_known_answer(); m_ = float(pd.to_numeric(obj["local_I"], errors="coerce").mean())
            return abs(m_ - I_e) < 0.05, f"mean local I {m_:.4f} vs the engine's global I {I_e:.4f} (identical for row-standardised weights)"
    if model == "M17":
        I = num(obj, "moran_I"); I_e = _engine_moran_known_answer()
        return abs(I - I_e) < 0.05, f"Moran's I {I:.4f} vs the engine's {I_e:.4f} on the same data and k = 8 neighbours"
    return False, f"no known-answer rule for {model} with this result shape"

def _engine_moran_known_answer():
    """The engine's own Moran's I on the known-answer panel's long difference (the reference for M17 / M18)."""
    ml = _prebuilt_module("ml"); fr = _known_answer_frame("block")
    ld, _ = ml.long_difference(fr, "VERIFY_Y", covariates=("latitude", "longitude"), by="pixel_id")
    w = build_knn_spatial_weights(ld["latitude"].values, ld["longitude"].values, k=8)
    I = global_morans_i(ld["dY"].values.astype(float), *w[:3]) if isinstance(w, tuple) else global_morans_i(ld["dY"].values.astype(float), *w)
    return float(I[0] if isinstance(I, tuple) else I)

def prebuilt_readiness(write=True, verbose=True):
    """All 45 models: which package would compute each, installed version, verified, what computes it NOW, why, and
    whether the panel holds what that route needs. -> PREBUILT_READINESS.csv / .md"""
    rec = _prebuilt_verified(); rows = []
    try:
        import pyarrow.parquet as _pq
        names = set(_pq.ParquetFile(PREPARED_PANEL).schema_arrow.names) if os.path.exists(PREPARED_PANEL) else set()
    except Exception:
        names = set()
    for m, s in PREBUILT_MODELS.items():
        if not in_pipeline(m): continue                                   # v20.58: the project's models only
        layer = s.get("layer"); pkg = s.get("package"); ver = _pkg_version(pkg) if pkg else None
        key = f"model:{m}" if layer == _M else s.get("route"); v = rec.get(key, {}) if key else {}
        verified = (bool(v.get("verified")) and v.get("version") == ver and (layer != _M or v.get("frame") == KNOWN_ANSWER_VERSION)) if pkg else False
        active = PREBUILT_MODE != "off" and bool(ver) and verified
        need = s.get("needs", ""); miss = []
        if names:
            if "lat" in need and not {"latitude", "longitude"} <= names: miss.append("latitude/longitude")
            if "dose" in need and not ({"dose_amount_sws", "dose_per_subwshed"} & names): miss.append("dose columns")
            if "covariates" in need and not (set(WEATHER_COVARIATES) & names): miss.append("weather covariates")
        r_pk = R_ROUTES.get(m); r_v = rec.get(f"r:{m}", {})
        r_ok = bool(r_pk) and bool(find_rscript()) and bool(r_v.get("verified")) and r_v.get("signature") == _r_signature(m) and r_v.get("frame") == KNOWN_ANSWER_VERSION
        if not active and r_ok and PREBUILT_MODE != "off":
            active_label = "R " + " + ".join(r_pk)
        else:
            active_label = None
        rows.append({"model": m, "layer": layer, "package": pkg or "-", "route": s.get("label", ""),
                     "r_route": ("R " + " + ".join(r_pk)) if r_pk else "-", "r_verified": r_ok,
                     "installed": ver or ("-" if not pkg else "not installed"), "verified": verified,
                     "computes_now": (s.get("label") if active else (active_label or "engine")),
                     "why": ("verified Python package" if active else ("verified R package" if active_label else
                             (s.get("reason") if layer == _E and not r_pk else
                              ("not installed (Python / R)" if (pkg and not ver) or (r_pk and not find_rscript()) else "not verified -- run P00 P12")))),
                     "panel_inputs": ("missing: " + ", ".join(miss)) if miss else ("ok" if names else "panel not built yet"),
                     "also_needs": need})
    out = pd.DataFrame(rows)
    if write:
        try:
            os.makedirs(RESULTS_ROOT, exist_ok=True)
            out.to_csv(os.path.join(RESULTS_ROOT, "PREBUILT_READINESS.csv"), index=False)
            n_pkg = int((out.computes_now != "engine").sum())
            md = ["# Pre-built packages first -- what computes each model on this machine", "",
                  f"PREBUILT_MODE = '{PREBUILT_MODE}'. {n_pkg} of 45 models are computed by a verified package now; "
                  f"{int((out.layer != _E).sum())} have one; {int((out.layer == _E).sum())} have none (engine, reason stated).", "",
                  "| model | Python route | installed | verified | R route | R verified | computes now | why | panel inputs |",
                  "|---|---|---|---|---|---|---|---|---|"]
            md += [f"| {r.model} | {r.route or '-'} | {r.installed} | {r.verified} | {r.r_route} | {r.r_verified} | {r.computes_now} | "
                   f"{str(r.why).replace('|', '/')} | {r.panel_inputs} |" for r in out.itertuples()]
            open(os.path.join(RESULTS_ROOT, "PREBUILT_READINESS.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
        except Exception as e:
            warn(f"PREBUILT_READINESS not written ({e})")
    if verbose:
        c = out.groupby(["layer", "computes_now"]).size()
        info(f"pre-built readiness: {int((out.computes_now != 'engine').sum())} of 45 models computed by a verified package now "
             f"({int((out.layer != _E).sum())} have one) -> PREBUILT_READINESS.csv / .md")
    return out

def verify_prebuilt_routes(routes=None, verbose=True):
    """P12: run every installed package against the validated engine on a panel with a KNOWN answer (true effect
    +0.05, 2022 start, annual + seasonal rows, pixel x season units, 6 clusters) and record the verdict per package
    version in prebuilt_verified.json. Tolerances: point estimates to 1e-6 (the designs are identical, so a correct
    package agrees to rounding), standard errors within 10 % (small-sample conventions differ), bootstrap p-values
    within 0.1 and both significant."""
    global PREBUILT_MODE
    rng = np.random.default_rng(20260922); rows = []
    for p_ in range(300):
        b_ = 0 if p_ % 5 == 0 else p_ % 5; a_ = rng.normal(0, .05)
        for y_ in range(2016, 2026):
            for s_ in (0, 1, 2):
                rows.append((10_000 + p_, y_, s_, b_, "SW" + str(p_ % 6), 0.4 + 0.1 * s_ + a_ + (0.05 if (b_ == 0 and y_ >= 2022) else 0)
                             + rng.normal(0, .01), 500 + rng.normal(0, 30)))
    df0 = pd.DataFrame(rows, columns=["pixel_id", "Year", "Season", "buff_km", "subwshed_id", "NDVI", "Rain"])
    df0["time_fe_yearseason"] = df0.Year.astype(str) + "_" + df0.Season.astype(str)
    df0.attrs["synthetic"] = True                                       # v20.58: a check panel, not your data (no location rule)
    saved_active, saved_mode, saved_cov = dict(ACTIVE), PREBUILT_MODE, list(DEFAULT_COVARIATES)
    rec = _prebuilt_verified(); results = []
    try:
        set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, exclude_transition_year=False,
                     seasons="all", unit_fe="pixel_season", covariates=["Rain"], cluster="subwshed", pooled_fe="period",
                     use_site_years=False, cohort_offset=0, timing="fixed")      # v20.58: never the notebook's fund timing (see above)
        d = build_treatment_columns(df0.copy()); d = d[d.in_analysis_sample == 1].copy()
        d["first_treat_agri_year"] = np.where(d.treatment == 1, 2022.0, np.inf)
        _rts = routes or [r_ for r_ in PREBUILT_ROUTES                   # v20.58: the routes of the project's models only
                          if PIPELINE_MODELS is None or any(PREBUILT_MODELS.get(m_, {}).get("route") == r_ for m_ in PIPELINE_MODELS)]
        for route in _rts:
            pkg = PREBUILT_ROUTES[route]; ver = _pkg_version(pkg)
            if not ver:
                results.append({"estimator": route, "package": pkg, "version": None, "verified": False, "detail": "not installed"}); continue
            PREBUILT_MODE = "off"; detail = ""; ok_ = False
            try:
                if route == "twfe":
                    be, se_ = estimate_twfe_did(d, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id", covariates=["Rain"])
                    bp, sp = _pf_twfe(d, "NDVI", "did_term", "unit_id", "time_fe_yearseason", "subwshed_id", ["Rain"])
                    ok_ = abs(bp - be) <= 1e-6 * max(1, abs(be)) and abs(sp / se_ - 1) <= 0.10 and abs(bp - 0.05) < 0.01
                    detail = f"beta engine {be:+.8f} package {bp:+.8f}; se ratio {sp / se_:.3f}"
                elif route == "event_study":
                    es = estimate_event_study(d, "NDVI", "treat_core", "event_time", "pixel_id", "time_fe_yearseason", "subwshed_id")
                    idn = es[es.identified & es.beta.notna()]
                    dw = d[(d["event_time"] >= -3) & (d["event_time"] <= 3)]            # the engine's window (-3, 3): same rows
                    pk = _pf_event_study(dw, "NDVI", "treat_core", dw["event_time"].values, [int(k) for k in idn.event_time], "unit_id", "time_fe_yearseason", "subwshed_id")
                    diffs = [abs(pk[int(k)][0] - b) for k, b in zip(idn.event_time, idn.beta) if int(k) in pk]
                    ok_ = len(diffs) == len(idn) and max(diffs) <= 1e-6
                    detail = f"{len(diffs)}/{len(idn)} event-time betas compared, max |difference| {max(diffs) if diffs else float('nan'):.2e}"
                elif route == "wild_bootstrap":
                    we = wild_cluster_bootstrap_pvalue(d, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id", n_boot=999, seed=1)
                    pp = _pf_wild_bootstrap(d, "NDVI", "did_term", "unit_id", "time_fe_yearseason", "subwshed_id", 999, 1, we["weights"])
                    pe = we["p_value_wild_bootstrap"]; ok_ = abs(pp - pe) <= 0.10 and pp < 0.05 and pe < 0.05
                    detail = f"p engine {pe:.3f} package {pp:.3f} ({we['weights']} weights)"
                elif route == "callaway_santanna":
                    _t, be_ = callaway_santanna_att(d, "NDVI", "pixel_id", "Year", "first_treat_agri_year")
                    pk = _dd_callaway_santanna(d, "NDVI", "unit_id", "Year", "first_treat_agri_year")
                    post = be_[be_.event_time >= 0].dropna(subset=["ATT"])
                    diffs = [abs(pk[int(k)] - a) for k, a in zip(post.event_time, post.ATT) if int(k) in pk]
                    ok_ = len(diffs) == len(post) and len(diffs) > 0 and max(diffs) <= 1e-6
                    detail = f"{len(diffs)}/{len(post)} post event-time ATTs compared, max |difference| {max(diffs) if diffs else float('nan'):.2e}"
            except Exception as e:
                detail = f"failed: {type(e).__name__}: {str(e)[:160]}"; ok_ = False
            finally:
                PREBUILT_MODE = saved_mode
            results.append({"estimator": route, "package": pkg, "version": ver, "verified": bool(ok_), "detail": detail})
            rec[route] = {"package": pkg, "version": ver, "verified": bool(ok_), "detail": detail, "when": _ts()}
    finally:
        PREBUILT_MODE = saved_mode
        ACTIVE.clear(); ACTIVE.update(saved_active); DEFAULT_COVARIATES[:] = saved_cov
    with open(PREBUILT_FILE, "w", encoding="utf-8") as fh: json.dump(rec, fh, indent=1)
    out = pd.DataFrame(results)
    if verbose:
        info(f"pre-built package verification -> {PREBUILT_FILE}"); print(out.to_string(index=False))
        n = int(out.verified.sum()); (ok if n else warn)(f"{n} of {len(out)} estimators will be computed by their package from now on")
    return out

def estimate_twfe_did_multi(df, y_col, treat_col, unit_col, time_fe_cols, cluster_col):
    """Same estimator as estimate_twfe_did, but with an arbitrary list of time-FE columns
    (e.g. ["time_fe_year","time_fe_season"] for the additive specification)."""
    cluster_col = _cluster_key(df, cluster_col)       # v20.38: the sub-watershed is the cluster
    unit_col = _unit_key(df, unit_col)             # v20.29: pixel x season unit when the scenario says so
    fes = [df[unit_col].values] + [df[c].values for c in time_fe_cols]
    y_dm = demean_multi_way(df[y_col].values, *fes)
    _tr_rows = (pd.to_numeric(df[treat_col], errors="coerce").values != 0)
    _frozen_treated_guard(pd.to_numeric(df[y_col], errors="coerce").values, df[unit_col].values, _tr_rows,
                          (pd.to_numeric(df["pre"], errors="coerce").values == 1) if "pre" in df.columns else None, y_col)   # v20.21
    d_dm = demean_multi_way(df[treat_col].values.astype(float), *fes)
    X = d_dm.reshape(-1, 1)
    if float(np.sum(X**2)) < 1e-12:
        raise InsufficientDataError("no residual treatment variation after absorbing the fixed effects")
    beta = float(np.linalg.lstsq(X, y_dm, rcond=None)[0][0])
    resid = y_dm - X.flatten() * beta
    se = float(np.sqrt(np.diag(cluster_robust_se(X, resid, df[cluster_col].values,
                                                  k_fe=_k_fe_nonnested(fes, pd.factorize(df[cluster_col].values)[0]))))[0])
    return beta, se


def demean_columns(Y, *fes, tol=1e-10, max_iter=200):
    """v20.23: demean a MATRIX (n x k) -- outcome, treatment terms and covariates together -- in one pass. GPU when
    available and the sample is large enough, else CPU; identical numbers to column-by-column demeaning."""
    global USE_GPU
    Y = np.asarray(Y, dtype=np.float64)
    n = Y.shape[0]
    T = _torch_cuda() if USE_GPU else None
    _k = (Y.shape[1] if Y.ndim == 2 else 1) + len(fes)
    if USE_GPU and T and GPU_MIN_ROWS <= n and gpu_capacity_rows(n_fe=_k) >= n:     # v20.57: fits below 98 % VRAM
        try:
            trace(f"demean matrix start n={n:,} k={Y.shape[1] if Y.ndim == 2 else 1} n_fe={len(fes)} gpu=on")
            out = _demean_gpu_matrix(T, Y, fes, tol, max_iter)
            out = _gpu_verify("matrix", Y, fes, out, tol, max_iter)     # v20.30: ALL rows x columns; CPU if rejected
            trace("demean matrix done on GPU")
            return out
        except Exception as e:
            warn(f"GPU matrix demeaning failed ({type(e).__name__}: {e}); CPU for this session")
            USE_GPU = False
    trace(f"demean matrix start n={n:,} k={Y.shape[1] if Y.ndim == 2 else 1} n_fe={len(fes)} gpu=off")
    out = _demean_cpu_matrix(Y, fes, tol, max_iter)
    trace("demean matrix done on CPU")
    return out

def demean_two_way(y, fe1, fe2, tol=1e-10, max_iter=100):
    """2-FE special case; routes through demean_multi_way so it inherits the GPU path."""
    return demean_multi_way(y, fe1, fe2, tol=tol, max_iter=max_iter)


def _k_fe_nonnested(fe_list, cl_codes):
    """v20.58: the fixed-effect parameters counted in the CR1 small-sample factor (N - 1) / (N - K) -- the rule of fixest (fixef.K = "nested",
    its default) and pyfixest (k_fixef = "nonnested", its default): each FE dimension's levels, one less per dimension beyond the first,
    and a dimension NESTED in the clusters (every level inside one cluster) counted as one. v20.57's engine counted none: with the years as
    the clusters (one sub-watershed) its SE was ~9 % below R's for the same estimate (the pixel x season effects are not nested in years)."""
    if not fe_list: return 0
    cl = np.asarray(cl_codes)
    L, nested = [], []
    for f in fe_list:
        codes = pd.factorize(np.asarray(f), sort=False)[0]
        L.append(int(codes.max()) + 1 if len(codes) else 0)
        u = pd.DataFrame({"f": codes, "c": cl}).drop_duplicates()
        nested.append(bool(not u["f"].duplicated().any()))
    k_adj = sum(L) - (len(L) - 1) if len(L) > 1 else sum(L)
    k_nest = sum(l_ for l_, n_ in zip(L, nested) if n_)
    return int(k_adj - k_nest + sum(nested)) if k_nest else int(k_adj)

def cluster_robust_se(X, resid, cluster_ids, k_fe=0):
    n, k = X.shape
    clusters = pd.unique(cluster_ids)
    G = len(clusters)
    if G < 2:
        raise InsufficientDataError(
            f"Only {G} distinct cluster(s) -- cluster-robust SEs are undefined with fewer "
            f"than 2 clusters (the standard CR1 finite-sample correction divides by G-1). "
            f"This is a genuine data limitation, not a code bug: you need at least 2 "
            f"distinct values of the clustering variable in this sample.")
    XtX_inv = np.linalg.inv(X.T @ X)
    meat = np.zeros((k, k))
    for c in clusters:
        idx = cluster_ids == c
        score = X[idx].T @ resid[idx]
        meat += np.outer(score, score)
    dfc = (G / (G - 1)) * ((n - 1) / max(1, n - k - int(k_fe)))    # v20.58: + the non-nested fixed effects (fixest / pyfixest)
    return dfc * XtX_inv @ meat @ XtX_inv


def cluster_robust_vcov(X, resid, cluster_ids, k_fe=0):
    """Full k x k cluster-robust vcov (not just per-coefficient SE) -- needed for the
    JOINT test below, since separate t-tests would ignore correlation between leads."""
    n, k = X.shape
    XtX_inv = np.linalg.inv(X.T @ X)
    clusters = pd.unique(cluster_ids)
    G = len(clusters)
    meat = np.zeros((k, k))
    for c in clusters:
        idx = cluster_ids == c
        score = X[idx].T @ resid[idx]
        meat += np.outer(score, score)
    dfc = (G / (G - 1)) * ((n - 1) / max(1, n - k - int(k_fe)))    # v20.58: + the non-nested fixed effects (fixest / pyfixest)
    return dfc * XtX_inv @ meat @ XtX_inv, G



def _solve_normal(G_, g_, names=None):
    """v17.8: solve the normal equations, tolerating a rank-deficient design (a covariate that is collinear with the
    fixed effects or with another covariate). Exact solve when the matrix is well conditioned; otherwise the
    Moore-Penrose pseudo-inverse, with the offending column names reported -- never a bare LinAlgError."""
    d = np.sqrt(np.clip(np.diag(G_), 1e-300, None))
    Gs = G_ / np.outer(d, d)
    if np.linalg.cond(Gs) < 1e10:
        Ginv = np.linalg.inv(G_)
        return Ginv @ g_, Ginv
    zero = [i for i in range(G_.shape[0]) if G_[i, i] < 1e-12]
    if zero and names:
        warn(f"design is rank deficient -- no within variation in: {[names[i] for i in zero if i < len(names)]}; "
             f"pseudo-inverse used (those coefficients are 0 and do not affect the treatment estimate)")
    else:
        warn("design is near-singular (collinear covariates) -- pseudo-inverse used; interpret covariate coefficients with care")
    Ginv = np.linalg.pinv(G_, rcond=1e-12)
    return Ginv @ g_, Ginv


def model_readiness(path=None, save_dir=None, verbose=True):
    """v20.16: which of the 45 models can run to a complete result on THIS panel -- see readiness.py."""
    import importlib
    return importlib.import_module("readiness").model_readiness(path=path, save_dir=save_dir, verbose=verbose)

def season_choice_report(outcomes=None, path=None, save_as=None, verbose=True):
    """v20.24: ONE streamed pass over the panel -> for every outcome, how complete the ANNUAL composite (Season 0) and
    the SEASONAL rows are, in the treated core and in the control rings, and which rows the models will use
    (seasons='auto': annual first, seasonal only for an outcome without annual values). Written to
    <OUTPUT_DIR>/season_choice_report.csv by P00; the numbers behind the yearly-first decision."""
    import pyarrow.parquet as pq
    p = path or PREPARED_PANEL
    pf = pq.ParquetFile(p)
    try:
        names = pf.schema_arrow.names
        outs = [o for o in (outcomes or ALL_ESTIMATION_VARIABLES) if o in names]
        cols = [c_ for c_ in ("Year", "Season", "buff_km") if c_ in names] + outs
        acc = {o: {"annual_rows": 0, "annual_finite": 0, "annual_core_rows": 0, "annual_core_finite": 0,
                   "seasonal_rows": 0, "seasonal_finite": 0, "seasonal_core_rows": 0, "seasonal_core_finite": 0,
                   "annual_years": set(), "seasonal_years": set()} for o in outs}
        for i in progress(range(pf.num_row_groups), desc="season coverage", unit="rg"):
            d = pf.read_row_group(i, columns=cols).to_pandas()
            s0 = pd.to_numeric(d["Season"], errors="coerce").values == 0
            core = (pd.to_numeric(d["buff_km"], errors="coerce").values == TREAT_CORE_BUFFKM) if "buff_km" in d else np.zeros(len(d), bool)
            yrs = pd.to_numeric(d["Year"], errors="coerce").values
            for o in outs:
                f = np.isfinite(pd.to_numeric(d[o], errors="coerce").values.astype(np.float64)); a = acc[o]
                for tag, m in (("annual", s0), ("seasonal", ~s0)):
                    a[f"{tag}_rows"] += int(m.sum()); a[f"{tag}_finite"] += int((m & f).sum())
                    a[f"{tag}_core_rows"] += int((m & core).sum()); a[f"{tag}_core_finite"] += int((m & core & f).sum())
                    if (m & f).any(): a[f"{tag}_years"].update(int(y) for y in np.unique(yrs[m & f]))
    finally:
        try: pf.close()
        except Exception: pass
    rows = []
    for o, a in acc.items():
        r = {"outcome": o}
        for tag in ("annual", "seasonal"):
            r[f"{tag}_share_finite"] = round(a[f"{tag}_finite"] / a[f"{tag}_rows"], 4) if a[f"{tag}_rows"] else np.nan
            r[f"{tag}_core_share_finite"] = round(a[f"{tag}_core_finite"] / a[f"{tag}_core_rows"], 4) if a[f"{tag}_core_rows"] else np.nan
            r[f"{tag}_finite_values"] = a[f"{tag}_finite"]
            r[f"{tag}_years"] = f"{min(a[f'{tag}_years'])}-{max(a[f'{tag}_years'])} ({len(a[f'{tag}_years'])})" if a[f"{tag}_years"] else "-"
        r["rows_used_with_auto"] = "annual (Season 0)" if a["annual_finite"] > 0 else "seasonal (no annual values)"
        rows.append(r)
    out = pd.DataFrame(rows)
    if save_as: out.to_csv(save_as, index=False)
    if verbose and len(out):
        info("which rows each outcome is estimated on (seasons = 'auto': ANNUAL composite first):")
        show = out[["outcome", "annual_share_finite", "annual_core_share_finite", "seasonal_share_finite",
                    "seasonal_core_share_finite", "rows_used_with_auto"]]
        print(show.to_string(index=False))
        gap = out[(out.seasonal_core_share_finite < out.annual_core_share_finite - 0.05)]
        if len(gap):
            warn(f"the SEASONAL rows of the treated core are notably less complete than the annual ones for "
                 f"{gap.outcome.tolist()} -- estimating on them would let the gaps (cloud / mask / footprint) bias the "
                 f"DiD; the annual composite is used for these")
    return out

def outcome_coverage(outcome, path=None, save_as=None, verbose=True):
    """v20.12: WHERE does this outcome have values? One row per (Year, Season) with the number of finite values in
    the treated core and in the control rings -- read straight from the per-variable file (or the panel), every
    season INCLUDING the annual composite, regardless of the scenario in force. This is the table to look at when
    an estimate comes back 'no finite values' / 'not identified'."""
    p = path or estimator_file_path(outcome)
    if not p or not os.path.exists(p): p = PREPARED_PANEL
    pf = pq.ParquetFile(p)
    rows = {}
    try:
        cols = [c for c in ("Year", "Season", "buff_km", outcome) if c in pf.schema_arrow.names]
        if outcome not in cols:
            raise InsufficientDataError(f"'{outcome}' is not a column of {p}")
        for i in range(pf.num_row_groups):
            d = pf.read_row_group(i, columns=cols).to_pandas()
            v = _usable(d[outcome].values, outcome)                 # v20.16: finite AND non-zero
            tr = (pd.to_numeric(d["buff_km"], errors="coerce").values == TREAT_CORE_BUFFKM) if "buff_km" in d else np.zeros(len(d), bool)
            for (y, s), idx in d.groupby(["Year", "Season"]).indices.items():
                r = rows.setdefault((int(y), int(s)), {"rows": 0, "finite": 0, "finite_treated": 0, "finite_control": 0})
                r["rows"] += len(idx); r["finite"] += int(v[idx].sum())
                r["finite_treated"] += int((v[idx] & tr[idx]).sum()); r["finite_control"] += int((v[idx] & ~tr[idx]).sum())
    finally:
        try: pf.close()
        except Exception: pass
    out = pd.DataFrame([{"Year": y, "Season": SEASON_LABEL.get(s, s), "Season_code": s, **r} for (y, s), r in sorted(rows.items())])
    if len(out):
        out["share_finite"] = (out["finite"] / out["rows"].replace(0, np.nan)).round(4)
    if verbose and len(out):
        seasonal = out[out.Season_code != 0]; yearly = out[out.Season_code == 0]
        info(f"coverage of '{outcome}': seasonal rows with a value {int(seasonal.finite.sum()):,} of {int(seasonal.rows.sum()):,} | "
             f"yearly (Season 0) {int(yearly.finite.sum()):,} of {int(yearly.rows.sum()):,}")
        if seasonal.finite.sum() == 0 and yearly.finite.sum() > 0:
            warn(f"'{outcome}' has values ONLY in the annual composite -> estimate it with C.set_scenario(seasons='yearly')")
        print(out.to_string(index=False))
    if save_as: out.to_csv(save_as, index=False)
    return out

def within_pixel_variation(outcome, path=None, sample_mod=100, verbose=True):
    """v20.21: FROZEN-SERIES DETECTOR. For a 1-in-`sample_mod` sample of pixels (by pixel_id modulo, so the same
    pixels every run), report per season the share of pixel-years whose value is IDENTICAL to the same pixel's
    value in the previous year, and the within-pixel SD across years -- for the treated core and the control
    rings separately. A DiD identifies an effect from within-pixel change; if the value never changes, every
    lead, lag and effect is exactly zero (1e-14) with an SE of 1e-10, which is a degenerate fit, not a finding.
    Values that repeat year after year usually mean the export wrote one composite under many dates."""
    import pyarrow.parquet as pq
    p = path or estimator_file_path(outcome)
    if not p or not os.path.exists(p): p = PREPARED_PANEL
    pf = pq.ParquetFile(p); parts = []
    try:
        cols = [k for k in ("pixel_id", "Year", "Season", "buff_km", outcome) if k in pf.schema_arrow.names]
        for i in range(pf.num_row_groups):
            d = pf.read_row_group(i, columns=cols).to_pandas()
            d = d[(pd.to_numeric(d["pixel_id"], errors="coerce") % sample_mod) == 0]
            if len(d): parts.append(d)
    finally:
        try: pf.close()
        except Exception: pass
    if not parts: raise InsufficientDataError(f"no rows sampled for '{outcome}' (sample_mod={sample_mod})")
    d = pd.concat(parts, ignore_index=True)
    d[outcome] = pd.to_numeric(d[outcome], errors="coerce"); d = d[np.isfinite(d[outcome])]
    d["group"] = np.where(pd.to_numeric(d["buff_km"], errors="coerce") == TREAT_CORE_BUFFKM, "treated_core", "control_rings")
    d = d.sort_values(["pixel_id", "Season", "Year"])
    same_pix = d["pixel_id"].values[1:] == d["pixel_id"].values[:-1]
    same_sea = d["Season"].values[1:] == d["Season"].values[:-1]
    consec = (pd.to_numeric(d["Year"], errors="coerce").values[1:] - pd.to_numeric(d["Year"], errors="coerce").values[:-1]) == 1
    ident = np.isclose(d[outcome].values[1:], d[outcome].values[:-1], rtol=0, atol=1e-12)
    ok_pair = same_pix & same_sea & consec
    pair = pd.DataFrame({"Year": d["Year"].values[1:][ok_pair], "Season": d["Season"].values[1:][ok_pair],
                         "group": d["group"].values[1:][ok_pair], "identical_to_previous_year": ident[ok_pair]})
    rows = []
    for (g, s), sub in pair.groupby(["group", "Season"]):
        rows.append({"group": g, "Season": SEASON_LABEL.get(int(s), s), "pixel_years_compared": int(len(sub)),
                     "share_identical_to_previous_year": round(float(sub.identical_to_previous_year.mean()), 4)})
    sd = d.groupby(["group", "Season", "pixel_id"])[outcome].std(ddof=0).groupby(["group", "Season"]).median().rename("median_within_pixel_sd_across_years").reset_index()
    sd["Season"] = sd["Season"].map(lambda s: SEASON_LABEL.get(int(s), s))
    out = pd.DataFrame(rows).merge(sd, on=["group", "Season"], how="left")
    out["frozen"] = out["share_identical_to_previous_year"] >= 0.5
    if verbose:
        info(f"within-pixel variation of '{outcome}' on {d.pixel_id.nunique():,} sampled pixels (1 in {sample_mod}):")
        print(out.to_string(index=False))
        fr = out[out.frozen]
        if len(fr):
            warn(f"FROZEN SERIES: {outcome} is identical to the previous year for >=50% of pixel-years in "
                 f"{[(r.group, r.Season) for r in fr.itertuples()]}. A DiD on these rows has no within-pixel change to "
                 f"identify from -- every lead/lag/effect comes out exactly 0 with an SE of ~1e-10. This is an EXPORT "
                 f"problem (one composite written under many dates); re-export before estimating.")
    return out

def _moments(v):
    """(n, mean, M2) of the finite values of v -- merged exactly across partitions by _merge_moments (Chan et al.)."""
    v = np.asarray(v, dtype=np.float64); v = v[np.isfinite(v)]
    if not len(v): return (0, 0.0, 0.0)
    m = float(v.mean()); return (int(len(v)), m, float(((v - m) ** 2).sum()))

def _merge_moments(parts):
    n, mean, m2 = 0, 0.0, 0.0
    for n_, mean_, m2_ in parts:
        if not n_: continue
        if not n: n, mean, m2 = int(n_), float(mean_), float(m2_); continue
        N = n + n_; d_ = mean_ - mean
        mean = mean + d_ * n_ / N; m2 = m2 + m2_ + d_ * d_ * n * n_ / N; n = N
    return n, mean, m2

def _frozen_partial(y_raw, pixel_ids, treated_mask, pre_mask):
    """v20.58: the pieces of the frozen-series guard of one frame (or one pixel partition): the treated pre rows, the within-series SD
    of every treated series with >= 2 of them, and the moments of the outcome."""
    y = np.asarray(y_raw, dtype=np.float64); pix = np.asarray(pixel_ids)
    m = treated_mask & pre_mask if pre_mask is not None else treated_mask
    out = {"rows": int(np.asarray(m).sum()), "std": np.zeros(0), "mom": _moments(y)}
    if out["rows"]:
        s = pd.Series(y[m]).groupby(pix[m]).agg(["std", "count"])
        out["std"] = s.loc[s["count"] >= 2, "std"].values.astype(np.float64)
    return out

def _frozen_final(parts, y_col, min_pixels=50):
    if sum(p_["rows"] for p_ in parts) < min_pixels: return
    sd_ = np.concatenate([p_["std"] for p_ in parts]) if parts else np.zeros(0)
    if len(sd_) < min_pixels: return
    n_, _m, m2_ = _merge_moments([p_["mom"] for p_ in parts])
    med_within = float(np.nanmedian(sd_)); sd_all = float(np.sqrt(m2_ / n_)) if n_ else float("nan")
    share_zero = float((sd_ < 1e-12).mean())
    if med_within < 1e-6 * max(sd_all, 1e-300) or share_zero > 0.5:
        raise InsufficientDataError(
            f"'{y_col}': FROZEN SERIES -- within {share_zero:.0%} of the treated pixels the pre-period rows all carry "
            f"the same value (median within-pixel SD {med_within:.1e} vs {sd_all:.3g} overall). A DiD has no baseline "
            f"change to identify from, so every lead comes out exactly 0 with an SE of ~1e-10 and any pooled effect is "
            f"driven only by the periods that do vary. Run C.within_pixel_variation('{y_col}'): the export has most "
            f"likely written one composite under many dates. Re-export before estimating.")

def _frozen_treated_guard(y_raw, pixel_ids, treated_mask, pre_mask, y_col, min_pixels=50):
    """v20.21 FROZEN-SERIES GUARD. A DiD is identified from the change of the outcome WITHIN a treated pixel between
    its pre- and post-period rows. If, within each treated pixel, the pre-period rows all carry the same value,
    there is no baseline change to compare against: the leads come out exactly 0 (1e-14) with SEs of 1e-10, the
    pre-trends F is exactly 0, and any pooled effect is driven entirely by whichever periods do vary (in your
    panel: the 2025 export). That is a degenerate fit, not a finding, so it is refused with the reason.
    Test: median over treated pixels of the standard deviation of the RAW outcome across that pixel's pre-period
    rows, relative to the outcome's overall spread. v20.58: partial (one frame / one pixel partition) + final -- the out-of-core
    path merges the partitions' pieces with the same final."""
    return _frozen_final([_frozen_partial(y_raw, pixel_ids, treated_mask, pre_mask)], y_col, min_pixels)

def treatment_coverage(df=None, path=None, columns=None, by=("Year", "Season"), save_as=None):
    """v17.10: the table to look at when a coefficient comes out as numerical zero. For every period it reports how
    many rows and pixels are TREATED (buff_km == 0) and CONTROL, and it summarises how many periods each pixel is
    observed in. A period with only one of the two groups identifies nothing; pixels seen in a single period
    contribute nothing once the pixel fixed effect is removed."""
    if df is None:
        cols = list(columns or ["pixel_id", "Year", "Season", "buff_km"])
        df = load_panel(columns=cols, path=path)
    d = apply_scenario(df.copy() if "treatment" in df.columns else build_treatment_columns(df, copy=True))
    d = d[d.get("in_analysis_sample", 1) == 1] if "in_analysis_sample" in d.columns else d
    g = d.groupby(list(by), observed=True)
    cov = pd.DataFrame({
        "rows_treated": g["treatment"].sum(),
        "rows_control": g["control"].sum() if "control" in d.columns else g["treatment"].size() - g["treatment"].sum(),
        "pixels_treated": g.apply(lambda x: x.loc[x["treatment"] == 1, "pixel_id"].nunique(), include_groups=False),
        "pixels_control": g.apply(lambda x: x.loc[x["treatment"] == 0, "pixel_id"].nunique(), include_groups=False),
    }).reset_index()
    cov["both_groups_present"] = (cov.rows_treated > 0) & (cov.rows_control > 0)
    per_pixel = d.groupby("pixel_id", observed=True).size()
    hist = per_pixel.value_counts().sort_index().rename("n_pixels").reset_index().rename(columns={"index": "periods_observed"})
    info(f"periods with BOTH groups: {int(cov.both_groups_present.sum())} of {len(cov)}")
    info(f"pixels observed once (contribute nothing after the pixel FE): {int((per_pixel == 1).sum()):,} of {len(per_pixel):,}")
    save_as = save_as or f"TREATMENT_COVERAGE_{scenario_tag()}.csv"      # v20: one file per scenario
    if save_as:
        os.makedirs(RESULTS_ROOT, exist_ok=True)
        cov.to_csv(os.path.join(RESULTS_ROOT, save_as), index=False)
        hist.to_csv(os.path.join(RESULTS_ROOT, save_as.replace(".csv", "_pixel_periods.csv")), index=False)
        ok(f"coverage -> {os.path.join(RESULTS_ROOT, save_as)}")
    return cov, hist

ABSORBED_REL_TOL = 1e-8   # v20.23: a covariate whose within-(pixel x period) SD is below this fraction of its raw SD is absorbed
LAST_FIT_INFO = {}       # v20.12: diagnostics of the most recent 2x2 fit; save_results() adds them to the CSV row

def _finite_rows(df, y_col, treat_col, covariates):
    """v20.12: rows that can enter the regression -- outcome, treatment term and covariates all finite.
    A NaN anywhere used to poison the fixed-effect means and come out the other end as beta = NaN (ESI, RUSLE,
    WSI, WSSI) or, through the pseudo-inverse, as a silent beta = 0.000 / se = 0.000 (NDVI)."""
    # v20.32: with the negative switch in "zero" mode the clipped values ARE zeros and must be used, not read as
    # masked cells (masked zeros were already turned into missing when the panel was built).
    _zero_ok = BLOCK_NEGATIVES_IN_ESTIMATION and str(NEGATIVE_BLOCK_MODE) == "zero"
    m = (np.isfinite(pd.to_numeric(df[y_col], errors="coerce").values.astype(np.float64)) if _zero_ok
         else _usable(df[y_col].values, y_col))          # v20.16: NaN or exact zero = missing
    if treat_col and treat_col in df.columns:            # the streaming path builds did_term AFTER this filter
        m &= np.isfinite(pd.to_numeric(df[treat_col], errors="coerce").values.astype(np.float64))
    for cv in (covariates or []):
        if cv in df.columns:
            m &= (np.isfinite(pd.to_numeric(df[cv], errors="coerce").values.astype(np.float64)) if _zero_ok
                  else _usable(df[cv].values, cv))
    return m

COVARIATES_BY_POST = False   # v20.23: True = each covariate also enters interacted with post (covariate-specific trends)

MODEL_RANKING = [   # v20.32: see RANKED_MODELS.md for the reasoning
    (1, "M16", "pre-trends F-test", "decides whether any DiD number is admissible"),
    (1, "M02", "event study", "year-by-year dynamics; exposes frozen or footprint-shifted series"),
    (1, "M24", "spillover / ring gradient", "tests the assumption the control rings rest on"),
    (1, "M23", "wild cluster bootstrap", "the p-value to quote with few clusters"),
    (1, "M01", "canonical 2x2 TWFE", "the headline effect size, once the checks above pass"),
    (1, "M34", "HonestDiD", "how large a pre-trend violation the conclusion survives"),
    (1, "M15", "placebo timing", "a fake treatment year must produce nothing"),
    (1, "M25", "permutation inference", "assignment-based p-value, no asymptotics in the cluster count"),
    (2, "M21", "season-to-annual aggregation", "whether the effect is a season-mix artefact"),
    (2, "M03", "doubly robust AIPW", "consistent if either the outcome or the weighting model is right"),
    (2, "M14", "PSM-DiD", "balances core against rings on pre-period levels"),
    (2, "M33", "entropy balancing", "exact covariate balance without discarding rows"),
    (2, "M35", "quantile DiD", "where in the distribution the change sits"),
    (2, "M04", "changes-in-changes", "distributional, invariant to monotone rescaling"),
    (2, "M17", "global Moran's I", "spatial dependence in the residuals"),
    (2, "M18", "local Moran / LISA", "where that dependence sits"),
    (2, "M19", "variance decomposition ICC", "how much varies between sub-watersheds"),
    (2, "M20", "Cochran Q / I2", "heterogeneity across sites"),
    (2, "M26", "treatment x covariate heterogeneity", "whether the effect depends on rainfall or land use"),
    (2, "M12", "chained DiD", "robust to a changing export footprint"),
    (2, "M30", "BJS imputation", "efficient with never-treated rings and one cohort"),
    (2, "M28", "Gardner two-stage", "same, two-stage form"),
    (2, "M22", "Goodman-Bacon", "with one cohort a weighting diagnostic, not an estimate"),
    (3, "M39", "double ML", "heterogeneity mapping only"), (3, "M40", "DML variants", "heterogeneity mapping only"),
    (3, "M41", "meta-learners", "heterogeneity mapping only"), (3, "M42", "DR-learner", "heterogeneity mapping only"),
    (3, "M43", "causal forest", "heterogeneity mapping only"), (3, "M44", "BART", "heterogeneity mapping only"),
]

def model_ranking(verbose=True):
    """v20.32: the models ranked for THIS design, crossed with what the panel can currently support (P10)."""
    rows = [{"rank_tier": t, "model": m, "what": w, "why": r} for t, m, w, r in MODEL_RANKING]
    out = pd.DataFrame(rows)
    try:
        import _readiness as _R
        rep = _R.assess(verbose=False) if hasattr(_R, "assess") else None
        st = {r["model"]: r.get("status") for _, r in rep.iterrows()} if rep is not None and hasattr(rep, "iterrows") else {}
        if st: out["data_supports"] = out["model"].map(st).fillna("unknown")
    except Exception:
        pass
    if verbose:
        info("model ranking for this design (RANKED_MODELS.md explains each):")
        print(out.to_string(index=False))
    return out

# ====================== v20.35: WHY IS THE EFFECT SO SMALL? -- measured on the panel, not guessed ======================
def _pixel_xy_m(pid):
    """pixel_id = rint((lat+90)*1e5)*1e9 + rint((lon+180)*1e5)  ->  local metres (equirectangular around the data)."""
    pid = np.asarray(pid, dtype=np.int64)
    lat = (pid // 1_000_000_000) / 1e5 - 90.0
    lon = (pid % 1_000_000_000) / 1e5 - 180.0
    lat0 = float(np.nanmedian(lat)) if len(lat) else 0.0
    return lon * 111_320.0 * np.cos(np.radians(lat0)), lat * 110_540.0

def _effect_frame(outcome, df):
    d = build_treatment_columns(df)
    d = d[d["in_analysis_sample"] == 1]
    y = pd.to_numeric(d[outcome], errors="coerce").values.astype(float)
    ok_ = np.isfinite(y)
    return d.loc[ok_], y[ok_]

def _effect_partial(outcome, df):
    """v20.58: the pieces of diagnose_effect_size of one frame (or one pixel partition: every row of a pixel -- and so of its series --
    is in the same partition, so every per-pixel / per-series quantity is complete inside it)."""
    d, y = _effect_frame(outcome, df)
    tr = d["treatment"].values == 1; po = d["post"].values == 1
    unit = d["unit_id"].values if "unit_id" in d.columns else d["pixel_id"].values
    pix = d["pixel_id"].values; yr = d["Year"].values.astype(int)
    P = {"rows": int(len(d))}
    for k_, m_ in (("tpre", tr & ~po), ("tpost", tr & po), ("cpre", ~tr & ~po), ("cpost", ~tr & po)):
        P[k_] = (float(y[m_].sum()), int(m_.sum()))
    pre_t = np.unique(unit[tr & ~po]); pre_c = np.unique(unit[~tr & ~po])
    lk_t = np.isin(unit[tr & po], pre_t); lk_c = np.isin(unit[~tr & po], pre_c)
    P["lk_t"] = (int(lk_t.sum()), int(lk_t.size)); P["lk_c"] = (int(lk_c.sum()), int(lk_c.size))
    yrows = {}
    for Y in np.unique(yr):
        mt = tr & (yr == Y); mc = ~tr & (yr == Y)
        yrows[int(Y)] = {"post": bool((po & (yr == Y)).any()), "ts": float(y[mt].sum()), "tn": int(mt.sum()), "cs": float(y[mc].sum()), "cn": int(mc.sum()),
                         "tp": int(len(np.unique(pix[mt]))), "cp": int(len(np.unique(pix[mc]))), "th": int(np.isin(unit[mt], pre_t).sum())}
    P["years"] = yrows
    ag = pd.DataFrame({"p": pix, "t": tr.astype(np.int8)}).groupby("p")["t"].agg(["min", "max"])
    P["switch"] = (int((ag["min"] != ag["max"]).sum()), int(len(ag)))
    g = pd.DataFrame({"u": unit[tr & ~po], "y": y[tr & ~po]}).groupby("u")["y"].agg(["count", "std"])
    g = g[g["count"] >= 3]
    P["frozen"] = (int((g["std"].fillna(0) <= 1e-9).sum()), int(len(g)))
    unl_units = np.unique(unit[tr & po][~lk_t]) if lk_t.size else np.array([], dtype=unit.dtype)
    P["unl_units"] = (int(np.isin(unl_units, pre_c).sum()), int(len(unl_units)))
    P["unl"] = np.unique(pix[tr & po][~lk_t]) if lk_t.size else np.array([], dtype=np.int64)
    P["ref"] = np.unique(pix[tr & ~po])
    P["sws"] = sorted(set(pd.unique(d["subwshed_id"]).tolist())) if "subwshed_id" in d.columns else None
    P["base"] = _moments(y[tr & ~po])
    if "Coverage" in d.columns:
        _cv = pd.to_numeric(d["Coverage"], errors="coerce").values
        P["coverage"] = {}
        for g_, gm_ in (("treated", tr), ("control", ~tr)):
            for p_, pm_ in (("pre", ~po), ("post", po)):
                sel_ = gm_ & pm_ & np.isfinite(_cv); P["coverage"][(g_, p_)] = (float(_cv[sel_].sum()), int(sel_.sum()))
    if not EXCLUDE_GAPFILLED and "GapFilled" in d.columns:
        _gfp = pd.to_numeric(d["GapFilled"], errors="coerce").fillna(0).values > 0
        P["gapfilled_post"] = (int((_gfp & po).sum()), int(po.sum()))
    return P

def _effect_final(outcome, parts, beta=None, se=None, n_clusters=None, nn_sample=None):
    from scipy import stats as _st
    S = {"outcome": outcome, "rows": int(sum(p_["rows"] for p_ in parts)), "scenario": scenario_tag()}
    tot = lambda k: (sum(p_[k][0] for p_ in parts), sum(p_[k][1] for p_ in parts))
    mean_ = lambda k: (lambda a: float(a[0] / a[1]) if a[1] else float("nan"))(tot(k))
    S.update({"mean_treated_pre": mean_("tpre"), "mean_treated_post": mean_("tpost"),
              "mean_control_pre": mean_("cpre"), "mean_control_post": mean_("cpost")})
    S["raw_did_means"] = (S["mean_treated_post"] - S["mean_treated_pre"]) - (S["mean_control_post"] - S["mean_control_pre"])
    lt, lc = tot("lk_t"), tot("lk_c")
    S["treated_post_rows_with_pre_history"] = float(lt[0] / lt[1]) if lt[1] else float("nan")
    S["control_post_rows_with_pre_history"] = float(lc[0] / lc[1]) if lc[1] else float("nan")
    yrs = {}
    for p_ in parts:
        for Y, r in p_["years"].items():
            a = yrs.setdefault(Y, {"post": False, "ts": 0.0, "tn": 0, "cs": 0.0, "cn": 0, "tp": 0, "cp": 0, "th": 0})
            a["post"] = a["post"] or r["post"]
            for k_ in ("ts", "tn", "cs", "cn", "tp", "cp", "th"): a[k_] += r[k_]
    rows = []
    for Y in sorted(yrs):
        a = yrs[Y]; tm = a["ts"] / a["tn"] if a["tn"] else float("nan"); cm = a["cs"] / a["cn"] if a["cn"] else float("nan")
        rows.append({"Year": int(Y), "period": "post" if a["post"] else "pre", "treated_mean": tm, "control_mean": cm, "difference": tm - cm,
                     "treated_pixels": int(a["tp"]), "control_pixels": int(a["cp"]),
                     "treated_rows_with_pre_history": float(a["th"] / a["tn"]) if a["tn"] else float("nan")})
    Yt = pd.DataFrame(rows, columns=["Year", "period", "treated_mean", "control_mean", "difference", "treated_pixels", "control_pixels",
                                     "treated_rows_with_pre_history"])
    Yt.insert(0, "outcome", outcome)
    S["sd_yearly_treated_mean"] = float(Yt["treated_mean"].std()); S["sd_yearly_control_mean"] = float(Yt["control_mean"].std())
    S["sd_yearly_difference"] = float(Yt["difference"].std())
    tp = Yt["treated_pixels"].replace(0, np.nan)
    S["treated_pixel_count_max_over_min"] = float(tp.max() / tp.min()) if tp.notna().any() else float("nan")
    sw = tot("switch"); S["pixels_switching_treatment"] = float(sw[0] / sw[1]) if sw[1] else float("nan")
    fz = tot("frozen"); S["treated_units_frozen_pre"] = float(fz[0] / fz[1]) if fz[1] else float("nan")
    uu = tot("unl_units"); S["unlinked_that_were_controls_pre"] = float(uu[0] / uu[1]) if uu[1] else float("nan")
    unl = np.unique(np.concatenate([p_["unl"] for p_ in parts])) if parts else np.array([], dtype=np.int64)
    S["median_offset_to_nearest_pre_pixel_m"] = float("nan"); S["share_unlinked_within_half_pixel"] = float("nan")
    S["overlap_needed_to_link_95pct"] = float("nan")
    if len(unl):
        try:
            from scipy.spatial import cKDTree
            ref = np.unique(np.concatenate([p_["ref"] for p_ in parts])); rx, ry = _pixel_xy_m(ref)
            _nn = nn_sample or rows_that_fit(2.0 * (16 + 64 + 24)) or len(unl)          # v20.58: EVERY unlinked pixel -- the queries run in
            q = unl                                                                      #   batches beyond 98 % of the RAM (v20.57 sampled)
            qx, qy = _pixel_xy_m(q); _tree = cKDTree(np.column_stack([rx, ry]))
            dist = np.empty(len(q)); idx = np.empty(len(q), np.int64)
            for _a in range(0, len(q), max(1, int(_nn))):
                dist[_a:_a + _nn], idx[_a:_a + _nn] = _tree.query(np.column_stack([qx[_a:_a + _nn], qy[_a:_a + _nn]]), k=1)
            dx, dy = np.abs(qx - rx[idx]), np.abs(qy - ry[idx])
            size = float(globals().get("PIXEL_SIZE_M", 10.0))
            ov = np.clip((size - dx) / size, 0, 1) * np.clip((size - dy) / size, 0, 1)
            S["median_offset_to_nearest_pre_pixel_m"] = float(np.median(dist))
            S["share_unlinked_within_half_pixel"] = float(np.mean((dx <= size / 2) & (dy <= size / 2)))
            S["overlap_needed_to_link_95pct"] = float(np.quantile(ov, 0.05))
        except Exception as e:
            info(f"offset analysis skipped ({type(e).__name__}: {str(e)[:80]})")
    sws = [p_["sws"] for p_ in parts if p_["sws"] is not None]
    G = n_clusters or (len(set().union(*[set(x) for x in sws])) if sws else None)
    if se is not None and G:
        S["mde_80pct"] = float((_st.t.ppf(0.975, max(G - 1, 1)) + _st.t.ppf(0.80, max(G - 1, 1))) * se)
    if beta is not None: S["beta"] = float(beta)
    n_, _m, m2_ = _merge_moments([p_["base"] for p_ in parts])
    S["baseline_sd_treated_pre"] = float(np.sqrt(m2_ / n_)) if n_ else float("nan")
    S["gapfilled_rows_left_out"] = int(LAST_LOAD_INFO.get("gapfilled_rows_excluded", 0))                 # v20.35
    for k_, v_ in (LAST_LOAD_INFO.get("gapfilled_by_group") or {}).items(): S[f"gapfilled_left_out_{k_}"] = int(v_)
    S["contaminated_control_rows_left_out"] = int(LAST_DESIGN_INFO.get("contaminated_control_rows", 0))
    S["duplicate_rows_across_sites_left_out"] = int(LAST_DESIGN_INFO.get("duplicate_rows_across_sites", 0))
    if parts and all("coverage" in p_ for p_ in parts):
        for g_ in ("treated", "control"):
            for p_n in ("pre", "post"):
                a = (sum(p_["coverage"][(g_, p_n)][0] for p_ in parts), sum(p_["coverage"][(g_, p_n)][1] for p_ in parts))
                S[f"coverage_{g_}_{p_n}"] = float(a[0] / a[1]) if a[1] else float("nan")
    return S, Yt

def diagnose_effect_size(outcome, df=None, beta=None, se=None, n_clusters=None, save=True, model_id="DIAGNOSTICS",
                         nn_sample=None, verbose=True, parts=None):   # v20.57: None = every pixel that fits below 98 % of the RAM
    """Measure, on YOUR panel, each mechanism that shrinks a difference-in-differences toward zero:
      1. post-period rows on pixels with NO pre-period history (a later export on another pixel grid or footprint):
         they cannot identify anything -- the years that carry the change drop out;
      2. pixels whose treated / control status changes between years (exports coding buff_km differently);
      3. treated pixels repeating one value across the pre years (a composite written under many dates);
      4. how much the core and the rings MOVE TOGETHER (shared yearly swings vs their difference);
      5. the minimum detectable effect with this many clusters.
    Writes effect_size_diagnostics_<OUTCOME>.csv (+ _yearly) and returns (summary dict, yearly table).
    v20.58: partial + final -- `parts` (the out-of-core path: one per pixel partition) instead of `df`."""
    if parts is None:
        if df is None:
            df = load_panel(columns=columns_for(outcome, ["pixel_id", "Year", "Season", "buff_km"]))
        parts = [_effect_partial(outcome, df)]
    S, Yt = _effect_final(outcome, parts, beta=beta, se=se, n_clusters=n_clusters, nn_sample=nn_sample)
    _gp = [p_["gapfilled_post"] for p_ in parts if "gapfilled_post" in p_]
    gp_ = (sum(a for a, _ in _gp), sum(b for _, b in _gp)) if _gp else None
    # ---- verdicts, in order of how badly each would shrink the estimate ----
    V = []
    if gp_ is not None:                                                                                # v20.35
        if gp_[1] and gp_[0] / gp_[1] > 0.01:
            V.append(("STRUCTURING", f"{gp_[0] / gp_[1]:.0%} of the post-period rows are GAP-FILLED (their unpublished "
                      f"days blended with the 3-year historical mean): post values pulled back toward pre. Fix: EXCLUDE_GAPFILLED = True."))
    if S["contaminated_control_rows_left_out"]:
        V.append(("STRUCTURING-FIXED", f"{S['contaminated_control_rows_left_out']:,} control rows on pixels treated in another "
                  f"sub-watershed were left out (CLEAN_CONTROLS) -- with them in, the DiD is pulled toward zero."))
    lt = S["treated_post_rows_with_pre_history"]
    _sw_explains = np.isfinite(S.get("unlinked_that_were_controls_pre", np.nan)) and S["unlinked_that_were_controls_pre"] >= 0.5
    if np.isfinite(lt) and lt < 0.90 and _sw_explains:
        V.append(("STRUCTURING", f"{1 - lt:.0%} of the treated post-period rows are pixels that were CONTROLS before 2022 "
                  f"({S['unlinked_that_were_controls_pre']:.0%} of them): a later export codes their ring differently, so they "
                  f"switch from control to treated. Fix: in P00 set P.BUFF_FROM_GEOMETRY = True (rings from the shapefile, "
                  f"identical every year) and rebuild."))
    elif np.isfinite(lt) and lt < 0.90:
        off = S["median_offset_to_nearest_pre_pixel_m"]; need = S["overlap_needed_to_link_95pct"]
        if np.isfinite(off) and S["share_unlinked_within_half_pixel"] >= 0.8:
            V.append(("STRUCTURING", f"{1 - lt:.0%} of the treated post-period rows sit on pixels with NO pre-period history -- "
                      f"a later export is on a SHIFTED pixel grid (median {off:.1f} m from the nearest earlier pixel). Those "
                      f"rows identify nothing, so the years they cover drop out of the estimate. Fix: in P00 set "
                      f"P.PIXEL_OVERLAP_MIN = {max(0.25, np.floor(need * 20) / 20):.2f} (links 95 % of them) and rebuild PASS B."))
        else:
            V.append(("STRUCTURING", f"{1 - lt:.0%} of the treated post-period rows sit on pixels with NO pre-period history, "
                      f"and they are not a shifted copy of the earlier grid (median {off:.1f} m away): the later export covers "
                      f"DIFFERENT ground. Fix: re-export 2015-2024 on the later footprint (or restrict every year to the common "
                      f"footprint) -- until then those pixels cannot contribute."))
    if S["pixels_switching_treatment"] > 0.01 and not _sw_explains:
        V.append(("STRUCTURING", f"{S['pixels_switching_treatment']:.1%} of pixels change between treated and control across "
                  f"years -- the exports code buff_km differently. Fix: in P00 set P.BUFF_FROM_GEOMETRY = True (rings from the "
                  f"shapefile, identical every year) and rebuild."))
    if np.isfinite(S["treated_units_frozen_pre"]) and S["treated_units_frozen_pre"] > 0.05:
        V.append(("DATA", f"{S['treated_units_frozen_pre']:.0%} of treated pixels repeat ONE value across the pre years (a "
                  f"composite written under several dates): no baseline change to compare against. Fix: re-export."))
    if S["treated_pixel_count_max_over_min"] > 1.5:
        V.append(("DATA", f"the number of treated pixels changes {S['treated_pixel_count_max_over_min']:.1f}x across years "
                  f"(see the yearly table): different years describe different ground."))
    if not [v_ for v_ in V if v_[0] != "STRUCTURING-FIXED"]:
        mde = S.get("mde_80pct", float("nan"))
        V.append(("SUBSTANTIVE", f"no structuring defect found. The core and the rings move together: their yearly means swing "
                  f"with SD {S['sd_yearly_treated_mean']:.4g}, their DIFFERENCE only with SD {S['sd_yearly_difference']:.4g}. "
                  f"The estimate is small because the core changed almost exactly as the rings did"
                  + (f"; this design would have detected an effect of {mde:.3g} or more" if np.isfinite(mde) else "")
                  + ". At landscape scale an effect confined to structure sites is averaged over the whole core, and "
                    "anything the works do to the 1-5 km rings is differenced away (test with M24)."))
    S["verdicts"] = " || ".join(f"[{k}] {t}" for k, t in V)
    if save:
        rd = results_dir(model_id); os.makedirs(rd, exist_ok=True)
        pd.DataFrame([S]).to_csv(os.path.join(rd, f"effect_size_diagnostics_{outcome}.csv"), index=False)
        Yt.to_csv(os.path.join(rd, f"effect_size_diagnostics_{outcome}_yearly.csv"), index=False)
    if verbose:
        info(f"{outcome}: treated {S['mean_treated_pre']:.4g} -> {S['mean_treated_post']:.4g}, rings "
             f"{S['mean_control_pre']:.4g} -> {S['mean_control_post']:.4g}; raw DiD {S['raw_did_means']:+.3g}")
        for k, t in V: (warn if k not in ("SUBSTANTIVE", "STRUCTURING-FIXED") else info)(f"[{k}] {t}")
    return S, Yt


# ====================== v20.36: PIXEL COUNTS ON EVERY RESULT, AUTOMATIC DIAGNOSTICS, CELL LOGS ======================
DESIGN_COUNTS = True
LAST_ANALYSIS = {"frame": None, "outcome": None, "ooc": None}   # v20.58: "ooc" = the pixel partitions' diagnostic pieces
LAST_EVENT_VCOV = {}      # v20.58: the covariance of the last event study (estimate_event_study) -- M34's delta-method SE
_RESAMPLING = {"depth": 0}
class resampling_scope:
    """v20.58: the fits INSIDE a resampling loop (permutations, placebo re-assignments) leave the diagnostics of the ACTUAL fit alone: no
    design counts on a permuted frame (v20.57 tried them on every permutation and printed 'design counts skipped (KeyError)' up to 999 times
    in M25), and LAST_FIT_INFO / LAST_DESIGN_COUNTS / LAST_ANALYSIS / LAST_CLUSTER_USED are restored on exit, so a saved result never
    carries the n_obs / clusters / pixel counts of the last permuted fit."""
    def __enter__(self):
        self._saved = tuple(dict(g) for g in (LAST_FIT_INFO, LAST_DESIGN_COUNTS, LAST_ANALYSIS, LAST_CLUSTER_USED))
        _RESAMPLING["depth"] += 1
        return self
    def __exit__(self, *exc):
        _RESAMPLING["depth"] = max(0, _RESAMPLING["depth"] - 1)
        for tgt, src in zip((LAST_FIT_INFO, LAST_DESIGN_COUNTS, LAST_ANALYSIS, LAST_CLUSTER_USED), self._saved):
            tgt.clear(); tgt.update(src)
        return False
_DC_SKIP_SAID = set()
LAST_DESIGN_COUNTS = {"table": None, "outcome": None}

def _grp_period(d):
    tr = (pd.to_numeric(d["treatment"], errors="coerce").values == 1) if "treatment" in d.columns else \
         (pd.to_numeric(d["buff_km"], errors="coerce").values == 0)
    po = (pd.to_numeric(d["post"], errors="coerce").values == 1) if "post" in d.columns else \
         (pd.to_numeric(d["Year"], errors="coerce").values >= int(ACTIVE["treatment_year"]))
    return tr, po

def _design_counts_partial(df, outcome=None):
    """v20.58: the pixel and row counts of one frame (or one pixel partition: a pixel is never in two, so counts of pixels add)."""
    d = df[df["in_analysis_sample"] == 1] if "in_analysis_sample" in df.columns else df
    if outcome and outcome in d.columns:
        d = d[np.isfinite(pd.to_numeric(d[outcome], errors="coerce").values)]
    pid = pd.to_numeric(d["pixel_id"], errors="coerce").values if "pixel_id" in d.columns else np.arange(len(d))
    tr, po = _grp_period(d)
    ring = pd.to_numeric(d["buff_km"], errors="coerce").values if "buff_km" in d.columns else np.where(tr, 0, 1)
    gp, rp = {}, {}
    for g, gm in (("treated", tr), ("control", ~tr)):
        gp[(g, "all")] = (int(len(pd.unique(pid[gm]))), int(gm.sum()))
        for p, pm in (("pre", ~po), ("post", po)):
            m = gm & pm; gp[(g, p)] = (int(len(pd.unique(pid[m]))), int(m.sum()))
    for r in sorted(int(x) for x in pd.unique(ring[np.isfinite(ring)])):
        for p, pm in (("pre", ~po), ("post", po)):
            m = (ring == r) & pm; rp[(r, p)] = (int(len(pd.unique(pid[m]))), int(m.sum()))
    t = pd.DataFrame({"group": np.where(tr, "treated", "control"), "period": np.where(po, "post", "pre"),
                      "Year": pd.to_numeric(d["Year"], errors="coerce").values,
                      "Season": pd.to_numeric(d["Season"], errors="coerce").values if "Season" in d.columns else 0})
    ys = t.groupby(["group", "period", "Year", "Season"], as_index=False).size().rename(columns={"size": "n_rows"})
    return {"gp": gp, "rp": rp, "ys": ys}

def _design_counts_final(parts, outcome=None):
    gp, rp = {}, {}
    for pt in parts:
        for k, (a, b) in pt["gp"].items(): x = gp.get(k, (0, 0)); gp[k] = (x[0] + a, x[1] + b)
        for k, (a, b) in pt["rp"].items(): x = rp.get(k, (0, 0)); rp[k] = (x[0] + a, x[1] + b)
    summ, rows = {}, []
    for g in ("treated", "control"):
        summ[f"n_pixels_{g}"] = int(gp.get((g, "all"), (0, 0))[0])
        for p in ("pre", "post"):
            summ[f"n_pixels_{g}_{p}"], summ[f"n_rows_{g}_{p}"] = (int(v) for v in gp.get((g, p), (0, 0)))
            rows.append({"level": "group x period", "group": g, "ring": "0" if g == "treated" else "controls", "period": p,
                         "Year": "ALL", "Season": "ALL", "n_pixels": summ[f"n_pixels_{g}_{p}"], "n_rows": summ[f"n_rows_{g}_{p}"]})
    for r in sorted({k[0] for k in rp}):
        for p in ("pre", "post"):
            a, b = rp.get((r, p), (0, 0))
            rows.append({"level": "ring x period", "group": "treated" if r == 0 else "control", "ring": str(r), "period": p,
                         "Year": "ALL", "Season": "ALL", "n_pixels": int(a), "n_rows": int(b)})
    yl = [pt["ys"] for pt in parts if len(pt["ys"])]
    ys = (pd.concat(yl, ignore_index=True).groupby(["group", "period", "Year", "Season"], as_index=False)["n_rows"].sum() if yl else
          pd.DataFrame(columns=["group", "period", "Year", "Season", "n_rows"]))
    ys["n_pixels"] = ys["n_rows"]                 # one row per pixel per year-season (de-duplicated when the panel is built)
    ys["level"] = "Year x Season x group"; ys["ring"] = np.where(ys["group"] == "treated", "0", "controls")
    table = pd.concat([pd.DataFrame(rows), ys[["level", "group", "ring", "period", "Year", "Season", "n_pixels", "n_rows"]]],
                      ignore_index=True)
    if outcome: table.insert(0, "outcome", outcome)
    return summ, table

def design_counts(df, outcome=None):
    """Pixels and rows in every design category, on the rows that enter the estimate: treated core / control rings x
    pre / post, each ring x pre / post, and each Year x Season x group. Returns (summary dict, long table).
    v20.58: partial + final (the out-of-core path merges the pixel partitions' counts with the same final)."""
    return _design_counts_final([_design_counts_partial(df, outcome)], outcome)

def _repeat_partial(df, outcome):
    d = df[df["in_analysis_sample"] == 1] if "in_analysis_sample" in df.columns else df
    v = pd.to_numeric(d[outcome], errors="coerce").values.astype(float); k = np.isfinite(v); d = d[k]; v = v[k]
    tr, po = _grp_period(d); yr = pd.to_numeric(d["Year"], errors="coerce").values
    unit = d["unit_id"].values if "unit_id" in d.columns else pd.to_numeric(d["pixel_id"], errors="coerce").values
    o = np.lexsort((yr, unit)); u_, y_, v_, t_, p_ = unit[o], yr[o], v[o], tr[o], po[o]
    nxt = (u_[1:] == u_[:-1]) & (y_[1:] - y_[:-1] == 1); same = nxt & (v_[1:] == v_[:-1])
    out = {}
    for g, gm in (("treated", t_[1:]), ("control", ~t_[1:])):
        for p, pm in (("pre", ~p_[1:]), ("post", p_[1:])):
            out[(g, p)] = (int((nxt & gm & pm).sum()), int((same & gm & pm).sum()))
    return out

def _repeat_final(parts):
    out = {}
    for g in ("treated", "control"):
        for p in ("pre", "post"):
            n = sum(pt[(g, p)][0] for pt in parts); s_ = sum(pt[(g, p)][1] for pt in parts)
            out[f"repeat_share_{g}_{p}"] = float(s_ / n) if n else float("nan")
    return out

def repeat_shares(df, outcome):
    """Share of consecutive-year values of the same pixel series that repeat EXACTLY, per group x period. Real indices
    practically never repeat to the last digit; an export that wrote one composite under many dates repeats them all.
    The frozen guard refuses only when > 50 % of TREATED pre-period series are frozen -- this measures every group.
    v20.58: partial + final (a series never spans two pixel partitions)."""
    return _repeat_final([_repeat_partial(df, outcome)])

def baseline_and_counts_all(outcomes=None, model_id="BASELINE"):
    """Baseline means AND pixel counts for EVERY variable: one combined CSV and TXT (P09 calls it)."""
    rows, counts = [], []
    for o in (outcomes or ALL_ESTIMATION_VARIABLES):
        try:
            d = build_treatment_columns(load_panel(columns=columns_for(o)))
            s, _ = baseline_means(o, df=d, model_id=model_id)
            dc, tab = design_counts(d, o)
            rows.append({"outcome": o, **s, **dc}); counts.append(tab)
            tab.to_csv(os.path.join(results_dir(model_id), f"design_counts_{o}.csv"), index=False)
        except Exception as e:
            info(f"{o}: baseline / counts skipped ({type(e).__name__}: {str(e)[:90]})")
    if not rows: return None
    od = results_dir(model_id); allb = pd.DataFrame(rows)
    allb.to_csv(os.path.join(od, "BASELINE_MEANS_ALL_VARIABLES.csv"), index=False)
    pd.concat(counts, ignore_index=True).to_csv(os.path.join(od, "DESIGN_COUNTS_ALL_VARIABLES.csv"), index=False)
    cols = [c_ for c_ in ("outcome", "baseline_mean_treated_pre", "baseline_mean_control_pre", "mean_treated_post",
                          "mean_control_post", "share_negative_all", "n_pixels_treated_pre", "n_pixels_treated_post",
                          "n_pixels_control_pre", "n_pixels_control_post") if c_ in allb.columns]
    with open(os.path.join(od, "BASELINE_MEANS_ALL_VARIABLES.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"BASELINE (pre-{int(ACTIVE['treatment_year'])}) MEANS AND PIXEL COUNTS -- {scenario_tag()} -- engine {ENGINE_VERSION} -- {_ts()}\n\n")
        fh.write(allb[cols].to_string(index=False, float_format=lambda x: f"{x:.6g}") + "\n")
    ok(f"baselines and pixel counts for {len(rows)} variables -> {os.path.join(od, 'BASELINE_MEANS_ALL_VARIABLES.csv')} (+ .txt, DESIGN_COUNTS_ALL_VARIABLES.csv)")
    return allb

_CELL_LOG = {"fh": None, "module": None, "path": None, "n": 0, "t0": None, "hooked": False, "orig": None}

class _TeeStream:
    """Screen output unchanged; the same text also goes to the module's log file (progress-bar redraws are skipped)."""
    def __init__(self, orig): self._orig = orig
    def write(self, s):
        n = self._orig.write(s)
        fh = _CELL_LOG["fh"]
        if fh is not None and s and not ("\r" in s and "\n" not in s):
            try: fh.write(s.replace("\r", "")); fh.flush()
            except Exception: pass
        return n
    def flush(self):
        try: self._orig.flush()
        except Exception: pass
    def __getattr__(self, a): return getattr(self._orig, a)

def _log_line(s):
    fh = _CELL_LOG["fh"]
    if fh is not None:
        try: fh.write(s); fh.flush()
        except Exception: pass

def start_cell_log(module=None):
    """Every message of every cell of this notebook -> <OUTPUT_DIR>/cell_logs/<MODULE>_<date_time>.txt, with a header
    per cell and its outcome (ok / the full error). The screen output is unchanged. Safe to call again."""
    import datetime as _dt, tempfile as _tf
    module = str(module or "notebook")
    if _CELL_LOG["fh"] is not None and _CELL_LOG["module"] == module: return _CELL_LOG["path"]
    if _CELL_LOG["fh"] is not None:
        try: _CELL_LOG["fh"].close()
        except Exception: pass
    _rr = globals().get("RESULTS_ROOT")        # v20.37: the Windows-path check BEFORE abspath (abspath hides it on Linux)
    _od = globals().get("OUTPUT_DIR") or (None if (not _rr or _foreign_path(_rr)) else os.path.dirname(os.path.abspath(_rr)))
    base = _od if (_PATHS_APPLIED[0] and _od and not _foreign_path(_od)) else _tf.gettempdir()   # <OUTPUT_DIR> = parent of results
    d = os.path.join(base, "cell_logs"); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{module}_{_dt.datetime.now():%Y%m%d_%H%M%S}.txt")
    _CELL_LOG.update({"fh": open(p, "a", encoding="utf-8", errors="replace"), "module": module, "path": p})
    if _CELL_LOG["orig"] is None:
        _CELL_LOG["orig"] = (sys.stdout, sys.stderr)
        sys.stdout = _TeeStream(sys.stdout); sys.stderr = _TeeStream(sys.stderr)
    _log_line(f"CELL LOG -- {module} -- engine {ENGINE_VERSION} -- started {_ts()}\n")
    try:
        from IPython import get_ipython as _gi
        ip = _gi()
    except Exception:
        ip = None
    if ip is not None and not _CELL_LOG["hooked"]:
        def _pre(info=None):
            _CELL_LOG["n"] += 1; _CELL_LOG["t0"] = _time.time()
            first = (getattr(info, "raw_cell", "") or "").strip().split("\n")[:2]
            _log_line(f"\n===== {_CELL_LOG['module']} cell {_CELL_LOG['n']} started {_ts()} =====\n" + "".join(f">> {l[:150]}\n" for l in first))
        def _post(result=None):
            err = getattr(result, "error_in_exec", None) or getattr(result, "error_before_exec", None)
            dt = _time.time() - (_CELL_LOG["t0"] or _time.time())
            if err is not None:
                import traceback as _tb
                _log_line(f"----- cell {_CELL_LOG['n']} FAILED after {dt:.1f}s:\n" + "".join(_tb.format_exception(type(err), err, err.__traceback__))[-4000:])
            else:
                _log_line(f"----- cell {_CELL_LOG['n']} finished ok ({dt:.1f}s)\n")
        try:
            ip.events.register("pre_run_cell", _pre); ip.events.register("post_run_cell", _post); _CELL_LOG["hooked"] = True
        except Exception:
            pass
    info(f"every message of this notebook is also written to {p}")
    return p

# ====================== v20.38: DOSE WITHIN A SUB-WATERSHED (ready for structure-level data) ======================
WITHIN_SWS_DOSE_PATH = None   # a CSV of works / structures: site_id, latitude, longitude, amount, completion_date

def within_sws_dose(df, structures=None, radius_m=500.0, amount_col="amount", date_col="completion_date"):
    """Pixel-level dose INSIDE a sub-watershed. Today the sub-watershed dose (dose_amount_sws, dose_intensity_per_ha)
    applies to its whole treatment area. When structure-level data arrive (WITHIN_SWS_DOSE_PATH, or `structures`: one
    row per structure with site_id, latitude, longitude, amount, completion_date), each structure's amount is shared
    equally among the TREATED pixels of its sub-watershed within radius_m, from the season after completion (the same
    next-season rule as the fund releases), and accumulated -> column dose_within_sws. Without such data the column
    equals the sub-watershed dose, so models can use it now and gain precision later without a code change."""
    import datetime as _dtm
    if structures is None and WITHIN_SWS_DOSE_PATH and os.path.exists(WITHIN_SWS_DOSE_PATH):
        structures = pd.read_csv(WITHIN_SWS_DOSE_PATH)
    out = df.copy()
    if structures is None or not len(structures):
        out["dose_within_sws"] = pd.to_numeric(out["dose_amount_sws"], errors="coerce") if "dose_amount_sws" in out.columns else np.nan
        out.attrs["within_sws_dose"] = "uniform over the treatment area (no structure data yet)"
        return out
    import _prep_common as _P
    st = structures.copy()
    st["eff_date"] = pd.to_datetime(st[date_col], errors="coerce"); st = st[st["eff_date"].notna()]
    nx = [_P.next_season_after(t) for t in st["eff_date"]]
    st["eff_year"] = [a for a, _ in nx]; st["eff_season"] = [b for _, b in nx]
    pid = pd.to_numeric(out["pixel_id"], errors="coerce").astype("int64").values
    lat = (pid // 1_000_000_000) / 1e5 - 90.0; lon = (pid % 1_000_000_000) / 1e5 - 180.0
    trt = (pd.to_numeric(out["treatment"], errors="coerce").values == 1) if "treatment" in out.columns else \
          (pd.to_numeric(out["buff_km"], errors="coerce").values == 0)
    site = pd.to_numeric(out["site_id"], errors="coerce").values if "site_id" in out.columns else np.zeros(len(out))
    u = pd.DataFrame({"pixel_id": pid[trt], "lat": lat[trt], "lon": lon[trt], "site_id": site[trt]}).drop_duplicates("pixel_id")
    sched = []
    for r in st.itertuples():
        cand = u[u["site_id"] == getattr(r, "site_id")] if "site_id" in st.columns else u
        if not len(cand): continue
        dy = (cand["lat"].values - float(getattr(r, "latitude"))) * 110_540.0
        dx = (cand["lon"].values - float(getattr(r, "longitude"))) * 111_320.0 * np.cos(np.radians(float(getattr(r, "latitude"))))
        near = cand["pixel_id"].values[np.hypot(dx, dy) <= radius_m]
        if len(near):
            share = float(getattr(r, amount_col)) / len(near)
            sched.append(pd.DataFrame({"pixel_id": near, "_y": int(r.eff_year), "_s": int(r.eff_season), "_amt": share}))
    out["dose_within_sws"] = 0.0
    if sched:
        s_ = pd.concat(sched, ignore_index=True)
        order = {3: 0, 1: 1, 2: 2}     # time order within a label year: Zaid -> Kharif -> Rabi (export calendar)
        s_["_t"] = s_["_y"] * 10 + s_["_s"].map(order).fillna(0)
        se_ = pd.to_numeric(out["Season"], errors="coerce").fillna(0).astype(int).values
        tt = pd.to_numeric(out["Year"], errors="coerce").values * 10 + pd.Series(se_).map({**order, 0: 3}).values
        for p_, g in s_.groupby("pixel_id"):
            m = pid == p_
            if not m.any(): continue
            t_row = tt[m]; cum = np.zeros(m.sum())
            for t_eff, a in zip(g["_t"].values, g["_amt"].values): cum += np.where(t_row >= t_eff, a, 0.0)
            out.loc[m, "dose_within_sws"] = cum
    out.attrs["within_sws_dose"] = f"{len(st)} structures, radius {radius_m:.0f} m"
    return out

def _baseline_partial(df, outcome):
    """v20.58: the pieces of baseline_means of one frame (or one pixel partition): per group x period (x Year) n, mean, M2, min, max and
    the counts of negative and zero values -- merged exactly (Chan) by _baseline_final."""
    d = df[df["in_analysis_sample"] == 1] if "in_analysis_sample" in df.columns else df
    v = pd.to_numeric(d[outcome], errors="coerce")
    grp = np.where(pd.to_numeric(d["treatment"], errors="coerce").values == 1, "treated_core", "control_rings")
    per = np.where(pd.to_numeric(d["post"], errors="coerce").values == 1, "post", "pre")
    t = pd.DataFrame({"group": grp, "period": per, "Year": pd.to_numeric(d["Year"], errors="coerce").values, "value": v.values})
    t = t[np.isfinite(t["value"].values)]
    def agg(keys):
        if not len(t): return []
        g = t.groupby(keys)["value"]
        a = pd.DataFrame({"n": g.size(), "mean": g.mean(), "var": g.var(), "min": g.min(), "max": g.max()})
        a["neg"] = t.assign(_n=(t["value"] < 0).astype(int)).groupby(keys)["_n"].sum()
        a["zero"] = t.assign(_z=(t["value"] == 0).astype(int)).groupby(keys)["_z"].sum()
        return [(k if isinstance(k, tuple) else (k,), int(r.n), float(r["mean"]), float(0.0 if not np.isfinite(r["var"]) else r["var"] * (r.n - 1)),
                 float(r["min"]), float(r["max"]), int(r.neg), int(r.zero)) for k, r in a.iterrows()]
    return {"overall": agg(["group", "period"]), "by_year": agg(["group", "period", "Year"]),
            "n_all": int(len(t)), "neg_all": int((t["value"] < 0).sum())}

def _baseline_final(parts, outcome):
    def merge(key):
        acc = {}
        for pt in parts:
            for k, n, mean, m2, mn, mx, ng, zr in pt[key]:
                a = acc.get(k)
                if a is None: acc[k] = [n, mean, m2, mn, mx, ng, zr]; continue
                N = a[0] + n; d_ = mean - a[1]
                a[1] = a[1] + d_ * n / N; a[2] = a[2] + m2 + d_ * d_ * a[0] * n / N; a[0] = N
                a[3] = min(a[3], mn); a[4] = max(a[4], mx); a[5] += ng; a[6] += zr
        return acc
    def frame(acc, names):
        rows = []
        for k in sorted(acc):
            n, mean, m2, mn, mx, ng, zr = acc[k]
            rows.append({**dict(zip(names, k)), "n_rows": float(n), "mean": float(mean), "sd": float(np.sqrt(m2 / (n - 1))) if n > 1 else np.nan,
                         "min": float(mn), "max": float(mx), "share_negative": float(ng / n), "share_zero": float(zr / n)})
        return pd.DataFrame(rows)
    n_all = sum(pt["n_all"] for pt in parts)
    if not n_all:
        table = pd.DataFrame()
    else:
        overall = frame(merge("overall"), ["group", "period"]); by_year = frame(merge("by_year"), ["group", "period", "Year"])
        overall["Year"] = "ALL"
        table = pd.concat([overall, by_year], ignore_index=True); table.insert(0, "outcome", outcome)
    pick = lambda g, p, col="mean": (float(table[(table.group == g) & (table.period == p) & (table.Year == "ALL")][col].iloc[0])
                                     if len(table) and len(table[(table.group == g) & (table.period == p) & (table.Year == "ALL")]) else np.nan)
    summary = {"baseline_mean_treated_pre": pick("treated_core", "pre"),
               "baseline_mean_control_pre": pick("control_rings", "pre"),
               "baseline_sd_treated_pre": pick("treated_core", "pre", "sd"),
               "mean_treated_post": pick("treated_core", "post"),
               "mean_control_post": pick("control_rings", "post"),
               "share_negative_treated_pre": pick("treated_core", "pre", "share_negative"),
               "share_negative_all": float(sum(pt["neg_all"] for pt in parts) / n_all) if n_all else np.nan,
               "n_rows_baseline": int(table[(table.group == "treated_core") & (table.period == "pre") & (table.Year == "ALL")]["n_rows"].iloc[0])
                                  if len(table) and len(table[(table.group == "treated_core") & (table.period == "pre") & (table.Year == "ALL")]) else 0}
    return summary, table

def baseline_means(outcome, df=None, save=True, out_dir=None, model_id="BASELINE", path=None, parts=None):
    """v20.32: the pre-treatment (baseline) level of an outcome, and how often it is negative.

    Writes baseline_means_<OUTCOME>.csv (one row per group x period x year) and returns the summary the models put
    next to their coefficients, so an effect can be read as a share of the baseline it started from.
    Groups: treated core (buff_km 0) and control rings; periods: pre (Year < treatment year) and post.
    v20.58: partial + final -- `parts` (the out-of-core path: one per pixel partition) instead of `df`.
    """
    if parts is None:
        if df is None:
            df = build_treatment_columns(load_panel(columns=columns_for(outcome), path=path))
        parts = [_baseline_partial(df, outcome)]
    summary, table = _baseline_final(parts, outcome)
    if save and len(table):
        rd = out_dir or results_dir(model_id)
        os.makedirs(rd, exist_ok=True)
        dst = os.path.join(rd, f"baseline_means_{outcome}.csv")
        table.to_csv(dst, index=False)
        info(f"{outcome}: baseline (pre-{int(ACTIVE['treatment_year'])}) mean {summary['baseline_mean_treated_pre']:.6g} in the treated core, "
             f"{summary['baseline_mean_control_pre']:.6g} in the rings; {summary['share_negative_all']:.2%} of values are negative -> {os.path.basename(dst)}")
    return summary, table

def effect_in_context(beta, summary):
    """The coefficient as a share of the baseline it started from (what a reader needs to judge the size)."""
    b0 = summary.get("baseline_mean_treated_pre", np.nan)
    sd = summary.get("baseline_sd_treated_pre", np.nan)
    return {"baseline_mean_treated_pre": b0, "baseline_mean_control_pre": summary.get("baseline_mean_control_pre", np.nan),
            "effect_pct_of_baseline": (100.0 * beta / b0) if (b0 and np.isfinite(b0) and abs(b0) > 1e-12) else np.nan,
            "effect_in_baseline_sd": (beta / sd) if (sd and np.isfinite(sd) and sd > 1e-12) else np.nan,
            "share_negative_all": summary.get("share_negative_all", np.nan)}

def estimate_twfe_did(df, y_col, treat_col, fe1_col, fe2_col, cluster_col, covariates=None, return_all=False,
                      covariates_by_post=None):
    df, covariates = _expand_categorical_covariates(df, covariates)   # v20.44: land-use CLASSES
    cluster_col = _cluster_key(df, cluster_col)       # v20.38: the sub-watershed is the cluster
    fe1_col = _unit_key(df, fe1_col)             # v20.29: pixel x season unit when the scenario says so
    if len(df) == 0:
        raise InsufficientDataError(f"Empty dataframe for outcome '{y_col}' -- nothing to estimate.")
    # ---- v20.12: missing-value policy, stated and enforced ----
    n0 = len(df)
    keep = _finite_rows(df, y_col, treat_col, covariates)
    n_drop = int(n0 - keep.sum())
    if n_drop:
        df = df[keep]
        share = n_drop / n0
        (warn if share > 0.25 else info)(f"'{y_col}': {n_drop:,} of {n0:,} rows ({share:.1%}) have a missing (NaN or zero) "
                                          f"outcome or covariate and are excluded from the regression")
    if len(df) == 0:
        raise InsufficientDataError(
            f"'{y_col}' has NO finite values in the analysis sample -- nothing to estimate. If this variable exists "
            f"only in the annual composite (Season 0 'Yearly'), run it with C.set_scenario(seasons='yearly'). "
            f"C.outcome_coverage('{y_col}') shows where it has values.")
    _tv = pd.to_numeric(df[treat_col], errors="coerce").values.astype(np.float64)
    n_tp = int((_tv != 0).sum())                       # rows where the treatment term is "on" (0/1 OR continuous)
    if n_tp == 0:
        raise InsufficientDataError(f"'{y_col}': the treatment term '{treat_col}' is zero on every row with a finite "
                                    f"outcome -- the effect is not identified. See C.outcome_coverage('{y_col}').")
    LAST_FIT_INFO.clear()
    LAST_FIT_INFO.update({"n_obs": int(len(df)), "n_dropped_missing": n_drop, "n_treated_post": n_tp})
    if DESIGN_COUNTS and not _RESAMPLING["depth"]:                                # v20.36: pixels per design category (v20.58: never
        try:                                                                     # on a permuted / re-assigned frame -- resampling_scope)
            _dc, _tab = design_counts(df, y_col)
            LAST_FIT_INFO.update(_dc); LAST_DESIGN_COUNTS.update({"table": _tab, "outcome": y_col})
            LAST_ANALYSIS.update({"frame": df, "outcome": y_col})
        except Exception as _e:
            _why = f"{type(_e).__name__}: {str(_e)[:80]}"
            if (CURRENT_MODEL_ID, y_col, _why) not in _DC_SKIP_SAID:              # v20.58: said once per model and outcome, not per fit
                _DC_SKIP_SAID.add((CURRENT_MODEL_ID, y_col, _why))
                info(f"design counts (pixels per group x period) not tabulated for '{y_col}': this frame has no "
                     f"{'treatment/post columns' if 'KeyError' in _why else 'usable design columns'} ({_why}); the estimate is unaffected")
    f1 = pd.factorize(df[fe1_col].values)[0]; f2 = pd.factorize(df[fe2_col].values)[0]   # v17.2: int codes, hashed once
    try:                                                    # v20.44: series seen ONCE carry no within-series information
        _sz = np.bincount(f1); _one = _sz[f1] == 1; _n1 = int(_one.sum())
        LAST_FIT_INFO["n_singleton_series"] = _n1
        if _n1:
            _by = []
            for _col, _lab in (("Season", "season"), ("Year", "year")):
                if _col in df.columns:
                    _vc = pd.Series(df[_col].values[_one]).value_counts().head(4)
                    _by.append(f"{_lab} " + ", ".join(f"{(SEASON_LABEL.get(int(k), k) if _col == 'Season' else int(k))}: {int(v):,}" for k, v in _vc.items()))
            LAST_FIT_INFO["singleton_rows_where"] = "; ".join(_by)
            (info if _n1 > 0.01 * len(df) else trace)(
                f"{y_col}: {_n1:,} {fe1_col} series are seen ONCE in this sample ({_n1 / len(df):.1%} of rows) -- they identify nothing "
                f"(pyfixest drops them as 'singleton fixed effects'; the estimate is the same). Where: {LAST_FIT_INFO['singleton_rows_where']}")
    except Exception:
        pass
    covs = [c for c in (covariates or []) if c in df.columns]
    if covs:
        trace(f"twfe: covariates {covs} (Frisch-Waugh partialling within the two-way FE)")
    y_dm = demean_two_way(df[y_col].values, f1, f2)
    # v20.21 frozen-series guard: the treated PRE-period rows must carry within-pixel variation (the baseline a DiD
    # differences against); live post rows must not be allowed to mask a frozen baseline
    _tr_pix = (pd.to_numeric(df["treatment"], errors="coerce").values == 1) if "treatment" in df.columns else \
              (pd.to_numeric(df[treat_col], errors="coerce").values != 0)
    _pre = (pd.to_numeric(df["pre"], errors="coerce").values == 1) if "pre" in df.columns else None
    _frozen_treated_guard(pd.to_numeric(df[y_col], errors="coerce").values, df[fe1_col].values, _tr_pix, _pre, y_col)
    _bp_ = COVARIATES_BY_POST if covariates_by_post is None else bool(covariates_by_post)
    LAST_ENGINE["twfe"] = "engine"
    if not return_all and not _bp_ and _use_prebuilt("twfe"):                         # v20.29: verified pyfixest
        _r = _route_call("twfe", _pf_twfe, df, y_col, treat_col, fe1_col, fe2_col, cluster_col, covs)
        if _r is not None:
            _G = int(pd.Series(df[cluster_col]).nunique())
            LAST_FIT_INFO.update({"n_clusters": _G, "engine": LAST_ENGINE["twfe"], "covariates": ";".join(covs)})
            try:
                from scipy import stats as _st
                _t = _r[0] / _r[1] if _r[1] > 0 else np.nan
                LAST_FIT_INFO["p_t_G1"] = float(2 * _st.t.sf(abs(_t), max(_G - 1, 1))) if np.isfinite(_t) else np.nan
                LAST_FIT_INFO["ci95_low_tG1"] = float(_r[0] - _st.t.ppf(0.975, max(_G - 1, 1)) * _r[1])
                LAST_FIT_INFO["ci95_high_tG1"] = float(_r[0] + _st.t.ppf(0.975, max(_G - 1, 1)) * _r[1])
                # v20.49: the package route carries the same diagnostics as the engine (found with the real pyfixest:
                # once P12 had verified it, every TWFE result lost its minimum detectable effect and its raw 2x2)
                LAST_FIT_INFO["mde_80pct_tG1"] = float((_st.t.ppf(0.975, max(_G - 1, 1)) + _st.t.ppf(0.80, max(_G - 1, 1))) * float(_r[1]))
                if {"treatment", "post"} <= set(df.columns):
                    _yv = pd.to_numeric(df[y_col], errors="coerce").values; _tt = df["treatment"].values == 1; _pp = df["post"].values == 1
                    _m = lambda mk: float(np.nanmean(_yv[mk])) if mk.any() else np.nan
                    LAST_FIT_INFO["raw_did_means"] = (_m(_tt & _pp) - _m(_tt & ~_pp)) - (_m(~_tt & _pp) - _m(~_tt & ~_pp))
            except Exception:
                pass
            try: LAST_FIT_INFO["_beta"] = float(_r[0])      # v20.58: the fit info belongs to THIS estimate only
            except Exception: pass
            return _r
    LAST_FIT_INFO["engine"] = "engine"
    # v20.23: treatment term and covariates demeaned together in ONE matrix pass. With covariates_by_post the
    # covariates also enter interacted with post -- linear covariates in a TWFE impose the SAME covariate
    # effect before and after treatment, which does not respect conditional parallel trends (Sant'Anna & Zhao);
    # the interaction lets each covariate carry its own trend across the cutoff.
    _by_post = COVARIATES_BY_POST if covariates_by_post is None else bool(covariates_by_post)
    if _by_post and covs and "post" in df.columns:
        _postv = pd.to_numeric(df["post"], errors="coerce").values.astype(np.float64)
        for c_ in list(covs):
            df[f"{c_}_x_post"] = pd.to_numeric(df[c_], errors="coerce").values.astype(np.float64) * _postv
        covs = list(covs) + [f"{c_}_x_post" for c_ in covs]
    _raw = [pd.to_numeric(df[treat_col], errors="coerce").values.astype(np.float64)] + \
           [pd.to_numeric(df[c], errors="coerce").values.astype(np.float64) for c in covs]
    _M = demean_columns(np.column_stack(_raw), f1, f2); del _raw
    d_dm = _M[:, 0]
    if covs:
        keep, keep_idx = [], []
        for j, c in enumerate(covs, start=1):
            _raw_sd = float(np.std(pd.to_numeric(df[c], errors="coerce").values.astype(np.float64)))
            if np.std(_M[:, j]) <= ABSORBED_REL_TOL * max(_raw_sd, 1e-300):
                warn(f"covariate '{c}' has no variation within pixel x period -- dropped (it is absorbed by the fixed effects)")
            else:
                keep.append(c); keep_idx.append(j)
        covs = keep
        X_dm = _M[:, [0] + keep_idx] if keep_idx else d_dm.reshape(-1, 1)
    else:
        X_dm = d_dm.reshape(-1, 1)
    _cl0 = pd.factorize(pd.Series(np.asarray(df[cluster_col].values)), sort=False)[0]
    _kfe = _k_fe_nonnested([f1, f2], _cl0)                   # v20.58: the FE parameters in (N - 1) / (N - K), as fixest / pyfixest
    del _M, f1, f2
    if np.std(d_dm) < 1e-10:
        raise InsufficientDataError("Treatment x post has no within-pixel/period variation (all units treated or all control, or no unit spans the cutoff)")
    # v17.5: closed-form OLS on the demeaned design (k+1 small; no LAPACK on n-length arrays) and the CR1
    # cluster-robust sandwich from per-cluster score sums (vectorised)
    trace("twfe: cross products")
    G_ = X_dm.T @ X_dm; g_ = X_dm.T @ y_dm
    beta, Ginv_ = _solve_normal(G_, g_, [treat_col] + covs)
    e = y_dm - X_dm @ beta
    cl = pd.factorize(pd.Series(np.asarray(df[cluster_col].values)), sort=False)[0]
    G = int(cl.max()) + 1
    if G < 2:
        raise InsufficientDataError("Only 1 distinct cluster -- cluster-robust SEs are undefined (need >= 2 values of the clustering variable)")
    k = X_dm.shape[1]; n = len(y_dm)
    S = np.column_stack([np.bincount(cl, weights=X_dm[:, j] * e, minlength=G) for j in range(k)])   # G x k score sums
    Ginv = Ginv_
    V = Ginv @ (S.T @ S) @ Ginv * (G / (G - 1)) * ((n - 1) / max(1, n - k - _kfe))
    se = np.sqrt(np.diag(V))
    LAST_FIT_INFO["n_clusters"] = int(G); LAST_FIT_INFO["k_fe_in_ssc"] = int(_kfe)
    try:                                                   # v20.35: the smallest effect this design could detect
        from scipy import stats as _st_
        LAST_FIT_INFO["mde_80pct_tG1"] = float((_st_.t.ppf(0.975, max(int(G) - 1, 1)) + _st_.t.ppf(0.80, max(int(G) - 1, 1)))
                                               * float(se[0]))
    except Exception:
        pass
    if {"treatment", "post"} <= set(df.columns):           # v20.35: the raw 2x2 of group means behind the coefficient
        try:
            _yv = pd.to_numeric(df[y_col], errors="coerce").values; _t = df["treatment"].values == 1; _p = df["post"].values == 1
            _m = lambda mk: float(np.nanmean(_yv[mk])) if mk.any() else np.nan
            LAST_FIT_INFO["raw_did_means"] = (_m(_t & _p) - _m(_t & ~_p)) - (_m(~_t & _p) - _m(~_t & ~_p))
        except Exception:
            pass
    try:                                                    # v20.23: p-value with G-1 degrees of freedom (few clusters)
        from scipy import stats as _st
        _t = beta[0] / se[0] if se[0] > 0 else np.nan
        LAST_FIT_INFO["p_t_G1"] = float(2 * _st.t.sf(abs(_t), max(int(G) - 1, 1))) if np.isfinite(_t) else np.nan
        LAST_FIT_INFO["ci95_low_tG1"] = float(beta[0] - _st.t.ppf(0.975, max(int(G) - 1, 1)) * se[0])
        LAST_FIT_INFO["ci95_high_tG1"] = float(beta[0] + _st.t.ppf(0.975, max(int(G) - 1, 1)) * se[0])
    except Exception:
        pass
    # ---- v20.12: a degenerate fit is an error, never a number ----
    if not (np.isfinite(beta[0]) and np.isfinite(se[0])):
        raise InsufficientDataError(f"'{y_col}': the fit produced a non-finite estimate (beta={beta[0]}, se={se[0]}) "
                                    f"after excluding missing rows -- the design is singular; see C.outcome_coverage('{y_col}')")
    if abs(beta[0]) < 1e-300 and se[0] < 1e-300:
        raise InsufficientDataError(f"'{y_col}': beta and its SE are both exactly zero -- the outcome has no within "
                                    f"pixel x period variation on the estimation sample (a constant or a fully absorbed "
                                    f"series), not a genuine null effect")
    del y_dm, d_dm, X_dm, e, cl, S
    trace("twfe: done")
    LAST_FIT_INFO["_beta"] = float(beta[0])                 # v20.58: the fit info belongs to THIS estimate only (see save_results)
    if return_all:
        return {"beta": float(beta[0]), "se": float(se[0]), "coef": dict(zip([treat_col] + covs, map(float, beta))),
                "se_all": dict(zip([treat_col] + covs, map(float, se))), "n": n, "k": k, "n_clusters": G}
    return float(beta[0]), float(se[0])

# ====================== v17.2: STREAMING 2x2 TWFE (exact on a balanced panel) ======================

def recommend_mode(columns=None, path=None, stream_above_rows=None, bytes_per_row=None):
    """v17.7: 'memory' whenever the in-RAM path FITS the RAM free right now (exact for unbalanced panels through
    iterative demeaning), else 'stream' (exact too, see estimate_twfe_did_streaming). stream_above_rows=None
    disables the old row-count rule (it sent a 78 M-row sample to stream mode on a 500 GB machine)."""
    import pyarrow.parquet as pq
    p = path or PREPARED_PANEL
    ef = estimator_file_for(columns) if columns else None
    pf = pq.ParquetFile(ef or p)
    n = pf.metadata.num_rows * (1.0 if ef else 33.0 / 34.0)
    bpr = bytes_per_row or (4.0 * len(columns) + 20 if columns else 40.0)
    need = n * bpr * MEMORY_COPIES
    free = host_free_bytes()
    if NO_CHUNKING and (free is None or need <= 0.98 * free):      # v20.56 / v20.58 YOUR RULE: all rows in RAM (+ GPU), one regression,
        return "memory", (f"your rule (no chunking): all {n:,.0f} rows in RAM and on the GPU at once, one regression "   # whenever they fit
                          f"(needs ~{need/1e9:.1f} GB of {free/1e9 if free else float('nan'):.1f} GB free)")
    if NO_CHUNKING:                                                # beyond 98 % of the RAM: the exact two-pass estimator in batches
        return "stream", (f"all {n:,.0f} rows need ~{need/1e9:.1f} GB, above 98 % of the {free/1e9:.1f} GB free -> the exact two-pass streaming "
                          f"estimator (every row, read in batches of 2,500,000 -- 5x the v20.57 batch); nothing is sampled")
    if stream_above_rows and n > stream_above_rows:
        return "stream", f"{n:,.0f} rows > {stream_above_rows:,} -> stream"
    if free is not None and need > MEMORY_HEADROOM * free:
        return "stream", f"in-RAM path needs ~{need/1e9:.1f} GB, {free/1e9:.1f} GB free -> stream (exact, ~8 B x (2+k) per pixel)"
    return "memory", f"{n:,.0f} rows fit in RAM (needs ~{need/1e9:.1f} GB of {free/1e9 if free else float('nan'):.1f} GB free)"

def estimate_twfe_did_streaming(y_col, control_zones=None, cluster_col="subwshed_id",
                                path=None, post_cutoff=None, balanced_only=False, verbose=True, covariates=None,
                                chunk_rows=2_500_000):   # v20.58: the batch 5x larger (the streaming path runs only beyond 98 % of the RAM)
    """Canonical 2x2 TWFE (pixel FE + Year-Season FE, treatment x post, optional covariates) in TWO streaming passes
    over the Parquet panel -- the panel is never in RAM -- EXACT FOR UNBALANCED PANELS (v17.7).

    Method: the pixel fixed effect is removed exactly by within-pixel demeaning (pass 1 gives every pixel's means and
    the set of periods it is observed in). The period fixed effects are then estimated JOINTLY with beta from the
    pixel-demeaned data: the regressors are [d~, X~, D~_s for all periods but one], where the demeaned period dummy is
    D~_is = 1[t = s] - 1[pixel i observed in s] / n_i. Pass 2 accumulates the (k+T-1)-dimensional normal equations and
    the per-cluster score sums for the CR1 sandwich. This is the Frisch-Waugh two-way within estimator, so it equals
    estimate_twfe_did() (iterative demeaning) on the same rows -- balanced or not -- to solver tolerance.
    balanced_only=True keeps the v17.6 behaviour (drop pixels with missing periods) for comparison only.
    Memory: ~8 B x (3 + k) per pixel + one uint64 period-bitmask per pixel; nothing per row.
    v20.56 -- NOT used by any model notebook (your rule: no chunking; every regression runs on all rows in RAM + GPU at
    once). Kept only as the validation scripts' independent cross-check of the in-RAM estimate.
    """
    if covariates and any(x in CATEGORICAL_COVARIATES for x in covariates):       # v20.44
        warn("the streaming path cannot build land-use classes consistently across chunks -- LandUse is left out of this fit")
        covariates = [x for x in covariates if x not in CATEGORICAL_COVARIATES]
    cluster_col = _stream_cluster_key(cluster_col)          # v20.41: sub-watershed, or years for one sub-watershed
    import pyarrow.parquet as pq, pyarrow.compute as pc
    assert_is_outcome(y_col)
    _ensure_resolved()
    if ACTIVE.get("site_start") or (ACTIVE.get("use_site_years") and ACTIVE.get("site_years")) or \
            (location_table().get("mode") != "none" and (ACTIVE.get("fragment_rule", "drop") == "drop" or ACTIVE.get("overlap_rows", "drop") == "drop") and
             (len(location_table().get("own", {})) > 1 or any(c_ == 3 for _s, c_, _n in location_table().get("by_site_check", [])) or
              location_table().get("ring_conflict") or location_table().get("near_dup"))):
        # v20.57: the two-pass cross-check handles ONE treatment year for every row and no fragment rule; the timing in force
        # (per sub-watershed / per season) and the fragment rule are applied by the in-memory path every model uses
        raise InsufficientDataError("the streaming cross-check needs ONE treatment year for every row and a panel without fragments; "
                                    "the design in force (TREATMENT_TIMING 'fund' / 'registry', or fragments to drop) is estimated by the "
                                    "in-memory path (M01_MODE = 'memory', your rule)")
    p = path or PREPARED_PANEL
    pf = pq.ParquetFile(p)
    _bad_ys, _good_years = screened_year_seasons(y_col, with_years=True) if OUTCOME_SCREEN else (set(), None)   # v20.46
    if _bad_ys:
        warn(f"{y_col}: {len(_bad_ys)} year-season(s) are fill / collapsed and are left out of the streaming fit: {sorted(_bad_ys)[:6]}")
        _T = int(ACTIVE.get("treatment_year") or 2022)
        _left = sorted(_good_years or [])                    # years with at least one EXISTING usable year-season
        _pre, _post = [y for y in _left if y < _T], [y for y in _left if y >= _T]
        if len(_pre) < 2 or not _post:
            raise InsufficientDataError(f"'{y_col}' is not usable: after the fill years are removed it has {len(_pre)} valid pre-period "
                                        f"year(s) and {len(_post)} post-period year(s) (need >= 2 and >= 1). Re-export it.")
    covs = [c for c in (covariates or []) if c in pf.schema_arrow.names]
    # v20.16: read the policy columns too (outcome + every estimation covariate) so the streaming path excludes
    # exactly the rows load_panel excludes, whether or not the regression uses those covariates
    policy_cols = [c for c in sorted(CURRENT_ESTIMATION_COLUMNS or set()) if c in pf.schema_arrow.names and c != y_col]
    vars_ = ["y", "did"] + covs
    need = list(dict.fromkeys(["pixel_id", "Year", "Season", "buff_km", y_col, cluster_col] + covs + policy_cols))
    miss = [c for c in need if c not in pf.schema_arrow.names]
    if miss: raise InsufficientDataError(f"panel lacks {miss}")
    czs = list(parse_control_zones(control_zones) if control_zones is not None else ACTIVE["control_zones"])
    post_cutoff = int(post_cutoff) if post_cutoff is not None else int(ACTIVE["post_cutoff"])   # v20
    # v20.26: the same transition-year rule as build_treatment_columns -- the treatment year leaves the sample and
    # the post period starts the year after, so memory and streaming estimate the identical design
    _ty_s = int(ACTIVE["treatment_year"]); _excl = bool(ACTIVE.get("exclude_transition_year"))
    _trans_lo, _trans_hi = (_ty_s, max(post_cutoff, _ty_s + 1)) if _excl else (None, None)
    if _excl: post_cutoff = _trans_hi
    if verbose: info(f"streaming under scenario {scenario_tag()} (control rings {czs}, post = Year >= {post_cutoff}"
                     + (f"; transition year(s) {_trans_lo}..{_trans_hi - 1} excluded)" if _excl else ")"))
    global CURRENT_OUTCOME
    CURRENT_OUTCOME = y_col                                  # v20.24: 'auto' seasons resolves for this outcome
    def _prep(t):
        t = season_rows(t)                                       # v20.12: seasonal / yearly / all
        d = t.to_pandas()
        if len(d) and "Season" in d.columns and (pd.to_numeric(d["Season"], errors="coerce") == 0).any():
            _fc = sorted(((CURRENT_ESTIMATION_COLUMNS or set()) | set(covariates or [])) - {y_col, "LandUse"})
            d, _ = fill_yearly_covariates(d, [c_ for c_ in _fc if c_ in d.columns], path=p)   # v20.24: as load_panel
        if len(d):                                               # v20.12/16: the SAME sample as the in-memory path --
            _pol = sorted((CURRENT_ESTIMATION_COLUMNS or set()) | set(covariates or []))   # outcome + every estimation
            _pol = [c_ for c_ in _pol if c_ in d.columns and c_ != y_col]                 # column load_panel filters on
            d = d[_finite_rows(d, y_col, None, _pol)]
            if not len(d): return d
        if has_year_window():                                    # v20.2
            d = d[year_mask(d["Year"].values)]
            if _bad_ys and len(d):                           # v20.46: the outcome screen, as load_panel applies it
                d = d[~pd.MultiIndex.from_arrays([d["Year"].astype(int).values, d["Season"].astype(int).values]).isin(list(_bad_ys))]
            if not len(d): return d
        if _trans_lo is not None:                                # v20.26: transition year out of the sample
            _y = d["Year"].astype(int)
            d = d[~((_y >= _trans_lo) & (_y < _trans_hi))]
            if not len(d): return d
        if BLOCK_NEGATIVES_IN_ESTIMATION:                                                      # v20.32: same switch
            _cols_ = [c_ for c_ in CURRENT_ESTIMATION_COLUMNS if c_ in d.columns and not _is_categorical_col(c_)]
            if _cols_:
                if str(NEGATIVE_BLOCK_MODE) == "zero":
                    for c_ in _cols_: d[c_] = pd.to_numeric(d[c_], errors="coerce").clip(lower=0)
                else:
                    _keep_ = np.ones(len(d), dtype=bool)
                    for c_ in _cols_: _keep_ &= (pd.to_numeric(d[c_], errors="coerce").values >= 0)
                    d = d[_keep_]
                    if not len(d): return d
        if ACTIVE.get("unit_fe", "pixel_season") == "pixel_season" and "Season" in d.columns:   # v20.29: same unit FE
            d = d.assign(pixel_id=pd.to_numeric(d["pixel_id"]).astype("int64") * 8 + pd.to_numeric(d["Season"]).fillna(0).astype("int64"))
        bk = pd.to_numeric(d["buff_km"], errors="coerce")
        treat = (bk == TREAT_CORE_BUFFKM); ctrl = bk.isin(czs)
        d = d[treat | ctrl]
        if not len(d): return d
        d = d.assign(period=(d["Year"].astype(int) * 10 + d["Season"].astype(int)).astype(np.int64),
                     did=((bk[treat | ctrl] == TREAT_CORE_BUFFKM) & (d["Year"].astype(int) >= post_cutoff)).astype(np.float64),
                     y=d[y_col].astype(np.float64))
        for c in covs: d[c] = d[c].astype(np.float64)
        return d.dropna(subset=["y"] + covs)
    aggs = {f"s_{v}": (v, "sum") for v in vars_}; aggs["n"] = ("y", "size")
    # ---- pass 1: per-pixel sums, per-pixel observed-period set (bitmask), period catalogue ----
    pix_parts, bit_parts, periods = [], [], set()
    for i in progress(range(pf.num_row_groups), desc="M01 stream pass 1 (pixel means)", unit="rg"):
        d = _prep(pf.read_row_group(i, columns=need))
        if not len(d): continue
        periods |= set(np.unique(d["period"].values).tolist())
        pix_parts.append(d.groupby("pixel_id", sort=False).agg(**aggs))
        bit_parts.append(d[["pixel_id", "period"]].drop_duplicates())
        if len(pix_parts) >= 8:
            pix_parts = [pd.concat(pix_parts).groupby(level=0).sum()]; bit_parts = [pd.concat(bit_parts).drop_duplicates()]
    if not pix_parts: raise InsufficientDataError("no analysis-sample rows in the panel")
    pix = pd.concat(pix_parts).groupby(level=0).sum(); bits = pd.concat(bit_parts).drop_duplicates()
    per_list = sorted(periods); T = len(per_list); per_idx = {pv: j for j, pv in enumerate(per_list)}
    if T > 62: raise InsufficientDataError(f"{T} periods > 62: extend the bitmask to two words")
    bits["bit"] = np.left_shift(np.uint64(1), bits["period"].map(per_idx).values.astype(np.uint64))
    mask = bits.groupby("pixel_id")["bit"].agg(lambda a: np.bitwise_or.reduce(a.values.astype(np.uint64)))
    n_periods = T
    unbalanced = pix[pix["n"] != n_periods]
    if len(unbalanced):
        msg = f"{len(unbalanced):,} of {len(pix):,} pixels are observed in fewer than {n_periods} periods"
        if balanced_only:
            warn(msg + " -- DROPPED (balanced_only=True; exact only on the balanced sub-panel)"); pix = pix[pix["n"] == n_periods]
        else:
            info(msg + " -- kept: v17.7 estimates the period effects jointly (exact two-way within estimator on the unbalanced panel)")
    keep_idx = pd.Index(pix.index)
    pm = {v: (pix[f"s_{v}"] / pix["n"]) for v in vars_}; n_i = pix["n"].astype(np.float64)
    mask = mask.reindex(keep_idx).fillna(np.uint64(0)).astype(np.uint64)
    k = len(vars_) - 1; K = k + (T - 1)
    Gm = np.zeros((K, K)); gv = np.zeros(K); cl = {}; n_rows = 0; cf_acc = {}
    raw_s = np.zeros(max(len(covs), 1)); raw_ss = np.zeros(max(len(covs), 1))      # v20.23
    shifts = np.arange(T - 1, dtype=np.uint64)           # periods 0..T-2 get dummies; period T-1 is the reference
    # ---- pass 2: normal equations of the pixel-demeaned regression with period dummies ----
    for i in progress(range(pf.num_row_groups), desc="M01 stream pass 2 (estimate)", unit="rg"):
        d = _prep(pf.read_row_group(i, columns=need))
        if not len(d): continue
        d = d[d["pixel_id"].isin(keep_idx)]
        if not len(d): continue
        for a0 in range(0, len(d), chunk_rows):
            dd = d.iloc[a0:a0 + chunk_rows]
            pid = dd["pixel_id"].values; pj = dd["period"].map(per_idx).values.astype(np.int64)
            ni = n_i.reindex(pid).values
            tilde = {v: dd[v].values - pm[v].reindex(pid).values for v in vars_}
            has = ((mask.reindex(pid).values[:, None] >> shifts[None, :]) & np.uint64(1)).astype(np.float64)   # rows x (T-1)
            Dt = -has / ni[:, None]
            rows_with_dummy = pj < (T - 1)
            Dt[np.arange(len(dd))[rows_with_dummy], pj[rows_with_dummy]] += 1.0
            Z = np.column_stack([tilde[v] for v in vars_[1:]] + [Dt]); yt = tilde["y"]
            Gm += Z.T @ Z; gv += Z.T @ yt; n_rows += len(dd)
            for _j, _c in enumerate(covs):                       # v20.23: raw moments, to detect absorbed covariates
                _x = dd[_c].values.astype(np.float64); raw_s[_j] += _x.sum(); raw_ss[_j] += (_x * _x).sum()
            cid = dd[cluster_col].astype(str).values
            for c in np.unique(cid):
                m_ = cid == c; Zc = Z[m_]
                a = cl.setdefault(c, {"xy": np.zeros(K), "xx": np.zeros((K, K))}); a["xy"] += Zc.T @ yt[m_]; a["xx"] += Zc.T @ Zc
            _tr = dd[pd.to_numeric(dd["buff_km"], errors="coerce") == TREAT_CORE_BUFFKM]
            if len(_tr):
                _g = _tr.groupby("Year").agg(sy=("y", "sum"), sd=("did", "sum"), n=("y", "size"))
                for yr, r_ in _g.iterrows():
                    a = cf_acc.setdefault(int(yr), [0.0, 0.0, 0]); a[0] += r_["sy"]; a[1] += r_["sd"]; a[2] += int(r_["n"])
    if Gm[0, 0] < 1e-12:
        raise InsufficientDataError("no within-pixel variation in treatment x post (no unit spans the cutoff)")
    # v20.23: drop absorbed covariates by the SAME relative rule as the in-memory estimator, so both paths solve
    # the same design and use the same degrees of freedom
    if covs:
        _drop = []
        for _j, _c in enumerate(covs):
            _raw_var = max(raw_ss[_j] / n_rows - (raw_s[_j] / n_rows) ** 2, 0.0)
            _within_var = Gm[1 + _j, 1 + _j] / n_rows
            if _within_var <= (ABSORBED_REL_TOL ** 2) * max(_raw_var, 1e-300):
                warn(f"covariate '{_c}' has no variation within pixel x period -- dropped (it is absorbed by the fixed effects)")
                _drop.append(1 + _j)
        if _drop:
            _keep = [i for i in range(Gm.shape[0]) if i not in _drop]
            Gm = Gm[np.ix_(_keep, _keep)]; gv = gv[_keep]
            for a in cl.values(): a["xy"] = a["xy"][_keep]; a["xx"] = a["xx"][np.ix_(_keep, _keep)]
            covs = [c_ for i_, c_ in enumerate(covs) if (1 + i_) not in _drop]; k = 1 + len(covs); K = Gm.shape[0]
    beta, Ginv = _solve_normal(Gm, gv, ["did_term"] + covs + [f"period_{j}" for j in range(T - 1)])
    G = len(cl)
    if G < 2: raise InsufficientDataError(f"only {G} cluster(s) -- cluster-robust SE undefined")
    S = np.array([a["xy"] - a["xx"] @ beta for a in cl.values()])
    # v20.58: the FE parameters in (N - 1) / (N - K) by the rule of fixest / pyfixest (as the in-memory engine): with the YEARS as the clusters
    # the pixel effects are not nested in them (all counted) and the periods are (one); with sub-watershed clusters the reverse
    _yr_cl = str(cluster_col) == "Year" or str(cluster_col).startswith("Year")
    _kfe_s = int(len(pix)) if _yr_cl else int(T)
    V = Ginv @ (S.T @ S) @ Ginv * (G / (G - 1)) * ((n_rows - 1) / max(1, n_rows - k - _kfe_s))
    se = np.sqrt(np.diag(V))
    if verbose:
        ok(f"streaming 2x2 TWFE{' + ' + str(covs) if covs else ''}: beta={beta[0]:.6f} se={se[0]:.6f} on {n_rows:,} rows, "
           f"{len(pix):,} pixels ({len(unbalanced):,} unbalanced, {'dropped' if balanced_only else 'kept'}), {T} periods, {G} clusters")
    cf = pd.DataFrame([{"Year": yr, y_col: a[0] / a[2], "Y_counterfactual": a[0] / a[2] - beta[0] * a[1] / a[2], "n_rows": a[2]}
                       for yr, a in sorted(cf_acc.items())])
    return float(beta[0]), float(se[0]), {"n_rows": n_rows, "n_pixels": int(len(pix)), "n_periods": int(T), "n_clusters": G,
                                          "n_unbalanced_pixels": int(len(unbalanced)), "unbalanced_dropped": bool(balanced_only and len(unbalanced)),
                                          "counterfactual": cf, "coef": dict(zip(["did_term"] + covs, map(float, beta[:1 + k]))),
                                          "se_all": dict(zip(["did_term"] + covs, map(float, se[:1 + k])))}

def estimate_event_study(df, y_col, treat_core_col, event_time_col, fe1_col, fe2_col,
                          cluster_col, ref_period=-1, window=(-3, 3), min_share=1e-4, covariates=None):
    """Event study with COVERAGE DIAGNOSTICS (v17.10). Each lead/lag coefficient is identified only from periods
    where BOTH groups are observed and from pixels seen in more than one period; when that support is thin the
    coefficient collapses to numerical zero with a meaningless standard error (this is what produced the
    1e-14 coefficients in the v17.9 run). The returned frame therefore carries, per event time:
        n_rows_treated / n_rows_control   -- rows of each group in that relative period
        n_pixels_treated / n_pixels_control
        share_treated                     -- treated share of that period's rows
        sd_after_demeaning                -- spread of the regressor once both fixed effects are removed
        identified                        -- False when the column is numerically absorbed (its coefficient is noise)
    Coefficients flagged identified=False must NOT be reported: fix the data coverage instead."""
    df, covariates = _expand_categorical_covariates(df, covariates)   # v20.44: land-use CLASSES
    cluster_col = _cluster_key(df, cluster_col)       # v20.38: the sub-watershed is the cluster
    fe1_col = _unit_key(df, fe1_col)             # v20.29: pixel x season unit when the scenario says so
    covs_ = [c for c in ([]) if c in df.columns]
    _keep = _finite_rows(df, y_col, None, covs_)                       # v20.13 missing-value policy
    if not _keep.all():
        info(f"event study: excluding {int((~_keep).sum()):,} rows with a missing outcome/covariate")
        df = df[_keep]
    if len(df) == 0:
        raise InsufficientDataError(f"'{y_col}': no finite values in the event-study sample -- see C.outcome_coverage('{y_col}')")
    if window is None:                                     # v20.58: every event time of the design's own window (as R's m02_event): the
        _etv = pd.to_numeric(df[event_time_col], errors="coerce").values          # design's PRE_YEARS / POST_YEARS already chose the years;
        _trv = pd.to_numeric(df[treat_core_col], errors="coerce").values == 1    # (-3, 3) dropped the design's earliest pre year(s) on top
        _fin = np.isfinite(_etv) & _trv
        if not _fin.any(): raise InsufficientDataError("no treated row with an event time in this sample")
        lo, hi = int(np.nanmin(_etv[_fin])), int(np.nanmax(_etv[_fin]))
        d = df.copy()
    else:
        lo, hi = window
        d = df[(df[event_time_col] >= lo) & (df[event_time_col] <= hi)].copy()
    if len(d) == 0:
        raise InsufficientDataError(
            f"No rows with event_time in [{lo},{hi}] -- your sample's years don't reach "
            f"this window relative to the treatment year. This is a DATA COVERAGE gap: "
            f"check event_time = Year - TREATMENT_YEAR against what years you actually have.")
    tr = d[treat_core_col].values.astype(bool); et = d[event_time_col].values
    cov = []
    # v20.15: WHICH pixels identify each coefficient. A lead/lag coefficient is estimated from the treated pixels
    # that are observed BOTH at that event time AND at the reference period (within-pixel comparison); a treated
    # pixel that appears only in one period is absorbed by its own fixed effect and contributes nothing. When the
    # treated population changes across periods (a new export footprint, a re-labelled buff_km) the coefficients
    # compare different pixels -- the table now says so instead of leaving it to be inferred from 1e-13 betas.
    pix_all = d[fe1_col].values
    ref_tr_pix = set(pd.unique(pix_all[(et == ref_period) & tr]))
    ref_ct_pix = set(pd.unique(pix_all[(et == ref_period) & ~tr]))
    for k in range(lo, hi + 1):
        m = et == k
        tp = pd.unique(pix_all[m & tr]); cp = pd.unique(pix_all[m & ~tr])
        n_tr_in_ref = int(sum(1 for p in tp if p in ref_tr_pix)) if k != ref_period else int(len(tp))
        n_ct_in_ref = int(sum(1 for p in cp if p in ref_ct_pix)) if k != ref_period else int(len(cp))
        cov.append({"event_time": k, "n_rows_treated": int((m & tr).sum()), "n_rows_control": int((m & ~tr).sum()),
                    "n_pixels_treated": int(len(tp)), "n_pixels_control": int(len(cp)),
                    "n_treated_pixels_also_in_ref": n_tr_in_ref, "n_control_pixels_also_in_ref": n_ct_in_ref})
    cov = pd.DataFrame(cov)
    cov["share_treated"] = cov["n_rows_treated"] / (cov["n_rows_treated"] + cov["n_rows_control"]).replace(0, np.nan)
    cov["share_treated_pixels_also_in_ref"] = (cov["n_treated_pixels_also_in_ref"]
                                               / cov["n_pixels_treated"].replace(0, np.nan)).round(4)
    def _note(r):
        if r.event_time == ref_period: return "reference period"
        if r.n_rows_treated == 0 and r.n_rows_control == 0: return "no rows in the panel for this period -- not estimated"
        if r.n_rows_treated == 0: return "no treated rows -- not identified"
        if r.n_rows_control == 0: return "no control rows -- not identified"
        if r.n_treated_pixels_also_in_ref == 0:
            return "NONE of the treated pixels here are observed in the reference period -- coefficient not identified from within-pixel change"
        if r.share_treated_pixels_also_in_ref < 0.5:
            return (f"identified from {int(r.n_treated_pixels_also_in_ref):,} treated pixels also seen in the reference period; "
                    f"the other {int(r.n_pixels_treated - r.n_treated_pixels_also_in_ref):,} treated pixels appear here but not there (different population)")
        return f"identified from {int(r.n_treated_pixels_also_in_ref):,} treated pixels observed in both periods"
    cov["identification_note"] = cov.apply(_note, axis=1)
    no_rows = cov[(cov.n_rows_treated == 0) & (cov.n_rows_control == 0)]
    if len(no_rows):
        info(f"event times {no_rows.event_time.tolist()} have no rows in the panel window (year "
             f"{[int(ACTIVE['treatment_year']) + int(k) for k in no_rows.event_time]}) -- not estimated, listed with a note")
    empty = cov[((cov.n_rows_treated == 0) | (cov.n_rows_control == 0)) & ~((cov.n_rows_treated == 0) & (cov.n_rows_control == 0))]
    if len(empty):
        warn(f"event times {empty.event_time.tolist()} have no treated OR no control rows -- their coefficients cannot "
             f"be identified; see identification_note")
    est_tr = cov[(cov.event_time != ref_period) & (cov.n_pixels_treated > 0)]
    if len(est_tr) and est_tr.n_pixels_treated.max() > 5 * max(est_tr.n_pixels_treated.min(), 1):
        warn(f"the TREATED population is not the same pixels across periods: {int(est_tr.n_pixels_treated.min()):,} treated "
             f"pixels in some periods vs {int(est_tr.n_pixels_treated.max()):,} in others. The coefficients therefore "
             f"compare different pixel populations, and a period-specific jump (a new export footprint, a "
             f"re-labelled buff_km, a different index scale) will show up as an 'effect'. See "
             f"panel_balance_by_block.csv, C.treatment_coverage() and the identification_note column.")
    thin = cov[(cov.event_time != ref_period) & (cov.n_pixels_treated > 0) & (cov.n_treated_pixels_also_in_ref < 0.5 * cov.n_pixels_treated)]
    if len(thin):
        warn(f"at event times {thin.event_time.tolist()} fewer than half of the treated pixels are observed in the "
             f"reference period ({ref_period}); those coefficients rest on the minority that is")
    y_dm = demean_two_way(d[y_col].values, d[fe1_col].values, d[fe2_col].values)
    sd_y = float(np.std(y_dm))
    _frozen_treated_guard(d[y_col].values, d[fe1_col].values, tr, et <= ref_period, y_col)   # v20.21/24: leads + reference
    if sd_y < 1e-9:
        raise InsufficientDataError(
            f"the outcome has NO variation left after removing pixel and period fixed effects (sd={sd_y:.2e}). "
            f"Almost every pixel is observed in a single period in this window, so nothing is identified. "
            f"Run C.treatment_coverage() and check how many periods each pixel actually has.")
    present = set(cov.loc[(cov.n_rows_treated > 0) | (cov.n_rows_control > 0), "event_time"].tolist())
    periods = [k for k in range(lo, hi + 1) if k != ref_period and k in present]     # v20.15: no phantom periods
    if not periods:
        raise InsufficientDataError("window collapses to only the reference period; nothing to estimate.")
    # v20.23: every event-time regressor demeaned in ONE pass (shared group structure, one convergence loop)
    _tc = d[treat_core_col].values.astype(float)
    _cv = [c_ for c_ in (covariates or []) if c_ in d.columns]          # v20.32: covariate-adjusted event study
    Xraw = np.column_stack([(_tc * (et == k)).astype(np.float64) for k in periods]
                           + [pd.to_numeric(d[c_], errors="coerce").astype(np.float64).values for c_ in _cv])
    X = demean_columns(Xraw, d[fe1_col].values, d[fe2_col].values)
    del Xraw
    _nk = len(periods)
    if _cv:                                                             # drop covariates the fixed effects absorb
        _csd = np.std(X[:, _nk:], axis=0); _craw = np.array([float(np.std(pd.to_numeric(d[c_], errors="coerce").values)) for c_ in _cv])
        _keep = _csd > 1e-8 * np.maximum(_craw, 1e-12)
        if not _keep.all():
            info(f"event study: covariates {[c_ for c_, k_ in zip(_cv, _keep) if not k_]} are absorbed by the fixed effects -- dropped")
            X = np.column_stack([X[:, :_nk], X[:, _nk:][:, _keep]]); _cv = [c_ for c_, k_ in zip(_cv, _keep) if k_]
    sds = np.std(X[:, :_nk], axis=0)
    ref_sd = np.nanmax(sds) if np.isfinite(sds).any() else 0.0
    identified = (sds > max(1e-10, min_share * ref_sd))
    if not identified.any():
        raise InsufficientDataError(
            "every lead/lag dummy is absorbed by the fixed effects -- in each relative period only ONE group is "
            "observed (or each pixel appears once). This is a data-coverage failure, not an estimation failure.")
    if not identified.all():
        warn(f"event times {[periods[i] for i in np.where(~identified)[0]]} are numerically absorbed "
             f"(sd after demeaning <= {min_share:g} x the largest): their coefficients are noise and are flagged "
             f"identified=False in the output")
    beta = np.full(len(periods), np.nan); se = np.full(len(periods), np.nan)
    Xi = np.column_stack([X[:, :_nk][:, identified], X[:, _nk:]]) if _cv else X[:, :_nk][:, identified]
    _n_id = int(identified.sum())
    try:
        b = np.linalg.lstsq(Xi, y_dm, rcond=None)[0]
    except np.linalg.LinAlgError:                        # v20.13: never "SVD did not converge" -- normal equations + pinv
        warn("event-study least squares did not converge (a non-finite or collinear column); solving the normal "
             "equations with a pseudo-inverse instead")
        b = np.linalg.pinv(Xi.T @ Xi, rcond=1e-12) @ (Xi.T @ y_dm)
    resid = y_dm - Xi @ b
    _V = cluster_robust_se(Xi, resid, d[cluster_col].values,
                           k_fe=_k_fe_nonnested([d[fe1_col].values, d[fe2_col].values], pd.factorize(d[cluster_col].values)[0]))   # v20.58
    _vc_et = [periods[i] for i in np.flatnonzero(identified)]; _vc = np.asarray(_V[:_n_id, :_n_id], dtype=np.float64).copy()   # v20.58: the
    _vc_G = int(pd.Series(d[cluster_col].values).nunique())                                                                 # covariance kept
    _dg = np.diag(_V).astype(np.float64)
    # v20.18: the sandwich is PSD in exact arithmetic, so a negative diagonal is cancellation error on a
    # coefficient whose regressor is (nearly) absorbed by the fixed effects. Clip it to zero, mark the coefficient
    # not identified, and never let numpy print "invalid value encountered in sqrt".
    _neg = _dg < 0
    if _neg.any():
        _dg = np.where(_neg, 0.0, _dg)
        info(f"{int(_neg.sum())} event-time SE(s) came out non-positive through cancellation (absorbed regressor) -> marked not identified")
    s_ = np.sqrt(_dg)
    beta[identified] = b[:_n_id]; se[identified] = s_[:_n_id]          # the covariate columns sit after the event times
    _dg = _dg[:_n_id]; _neg = _neg[:_n_id]
    if _neg.any():
        _ids = np.flatnonzero(identified)[_neg]
        identified[_ids] = False
    out = pd.DataFrame({"event_time": periods, "beta": beta, "se": se,
                        "sd_after_demeaning": sds, "identified": identified})
    out = cov.merge(out, on="event_time", how="left").sort_values("event_time").reset_index(drop=True)   # v20.15: every
    out = out[["event_time", "beta", "se", "sd_after_demeaning", "identified"] +                          # period listed,
              [c_ for c_ in cov.columns if c_ != "event_time"]]                                          # with its note
    out["identified"] = pd.Series([bool(v) if pd.notna(v) else False for v in out["identified"]], index=out.index)   # v20.49: no object downcast (pandas 3)
    out.attrs["sd_outcome_after_demeaning"] = sd_y
    # v20.58 (M34): the event study's covariance is kept in LAST_EVENT_VCOV -- NOT in DataFrame.attrs (pandas compares attrs when frames are
    # concatenated / merged: an array there raised "truth value of an array ... is ambiguous" in M02)
    LAST_EVENT_VCOV.clear(); LAST_EVENT_VCOV.update({"vcov": _vc, "event_times": list(_vc_et), "n_clusters": _vc_G, "cluster_used": str(LAST_CLUSTER_USED.get("value") or ""),
                                                     "outcome": y_col, "n_rows": int(len(d))})
    out.attrs.update({"n_clusters": _vc_G, "cluster_used": str(LAST_CLUSTER_USED.get("value") or "")})
    out["engine"] = "engine"; out["covariates"] = ";".join(_cv) if _cv else ""    # v20.32
    LAST_ENGINE["event_study"] = "engine"
    if _use_prebuilt("event_study"):                                                   # v20.29: verified pyfixest
        _ks = [int(k) for k in out.loc[out["identified"], "event_time"]]
        _r = _route_call("event_study", _pf_event_study, d, y_col, treat_core_col, et, _ks, fe1_col, fe2_col, cluster_col, _cv)
        if _r:
            for k, (b_, s_) in _r.items():
                m_ = out["event_time"] == k
                out.loc[m_, "beta"] = b_; out.loc[m_, "se"] = s_; out.loc[m_, "engine"] = LAST_ENGINE["event_study"]
    try:                                                    # v20.49: clusters = years -> each coefficient rests on ONE year
        if str(LAST_CLUSTER_USED.get("value", "")).startswith("Year"):
            _lead = pd.to_numeric(out.loc[(out["event_time"] < ref_period) & out["beta"].notna(), "beta"], errors="coerce").dropna()
            if len(_lead) >= 2:
                out["se_design"] = float(_lead.std(ddof=1))
                out["se_note"] = "cluster = Year: the per-year cluster SEs are not valid; se_design = SD of the pre-period leads"
    except Exception:
        pass
    return out

def common_pixel_mask(df, unit_col="pixel_id", period_col="Year", verbose=True):
    """v20.15: rows of the pixels observed in EVERY period present in `df` -- the balanced footprint. Use it when the
    event study reports that the treated population changes across periods: the coefficients then compare the
    same pixels with themselves over time, at the price of dropping the periods-only pixels."""
    per = pd.to_numeric(df[period_col], errors="coerce")
    n_per = per.nunique()
    cnt = df.groupby(unit_col)[period_col].nunique()
    keep_units = cnt.index[cnt.values >= n_per]
    m = df[unit_col].isin(keep_units).values
    if verbose:
        info(f"balanced footprint: {len(keep_units):,} of {int(cnt.shape[0]):,} pixels are observed in all {n_per} "
             f"periods -> keeping {int(m.sum()):,} of {len(df):,} rows")
    return m

def construct_counterfactual(df, outcome_col, effect_col, out_col="Y_counterfactual", copy=False):
    """Y(0)_hat = Y_observed - effect, where `effect_col` is the PER-ROW estimated effect
    already applicable to that row (0 for control/pre-period rows, the relevant beta for
    treated-post rows) -- computed by whichever module calls this, matched to its own
    estimator's granularity (a single pooled beta for Module 1/6, a period-specific beta_k
    for Module 2, a cohort-and-period-specific CATT for Module 9).
    v17.2: in place by default (copy=False)."""
    d = df.copy() if copy else df
    d[out_col] = d[outcome_col] - d[effect_col]
    return d


# ====================== v20.58 (second pass): did's ANALYTICAL influence-function SE, ported ======================
# did 2.5.1 (att_gt: est_method "dr" without covariates, the never-treated series as the comparison, the varying base period, allow_unbalanced
# panel -- a balanced series x year frame takes DRDID's panel estimator, an unbalanced one its repeated-cross-section estimator with the
# influence function summed over each series' rows) and aggte (type "simple" / "group": the weights' own influence function, wif();
# getSE = sqrt(mean(IF^2) / n)); DRDID 1.3.0 drdid_panel / drdid_rc with an intercept as the only covariate, line by line. R's M05 / M30 take
# this SE when the design has no sub-watershed clusters (else did's multiplier bootstrap clustered by sub-watershed -- the engine then keeps
# the design-based SE). Checked against did on four panels (balanced / unbalanced, one / two cohorts): estimate and SE to 1e-14.
def _drdid_panel_if(y1, y0, D):
    n = len(D); D = np.asarray(D, np.float64); dY = np.asarray(y1, np.float64) - np.asarray(y0, np.float64)
    ps = np.full(n, min(D.mean(), 1 - 1e-6)); trim = np.ones(n); trim[D == 0] = (ps[D == 0] < 0.995); W = ps * (1 - ps)
    out = dY[D == 0].mean(); w_t = trim * D; w_c = trim * ps * (1 - D) / (1 - ps); mw_t, mw_c = w_t.mean(), w_c.mean()
    a_t = w_t * (dY - out); a_c = w_c * (dY - out); eta_t = a_t.mean() / mw_t; eta_c = a_c.mean() / mw_c
    asy_ols = (1 - D) * (dY - out) / ((1 - D).sum() / n); asy_ps = (D - ps) * (n / W.sum())
    inf_t = ((a_t - w_t * eta_t) - asy_ols * (w_t.sum() / n)) / mw_t
    inf_c = ((a_c - w_c * eta_c) + asy_ps * ((w_c * (dY - out - eta_c)).sum() / n) - asy_ols * (w_c.sum() / n)) / mw_c
    return float(eta_t - eta_c), inf_t - inf_c


def _drdid_rc_if(y, post, D):
    n = len(D); D = np.asarray(D, np.float64); post = np.asarray(post, np.float64); y = np.asarray(y, np.float64)
    ps = np.full(n, min(D.mean(), 1 - 1e-6)); W = ps * (1 - ps); trim = np.ones(n); trim[D == 0] = (ps[D == 0] < 0.995)
    oc_pre = y[(D == 0) & (post == 0)].mean(); oc_post = y[(D == 0) & (post == 1)].mean(); oc = post * oc_post + (1 - post) * oc_pre
    ot_pre = y[(D == 1) & (post == 0)].mean(); ot_post = y[(D == 1) & (post == 1)].mean()
    w = {"tpre": trim * D * (1 - post), "tpost": trim * D * post, "cpre": trim * ps * (1 - D) * (1 - post) / (1 - ps),
         "cpost": trim * ps * (1 - D) * post / (1 - ps), "d": trim * D, "dt1": trim * D * post, "dt0": trim * D * (1 - post)}
    mw = {k: v.mean() for k, v in w.items()}
    e = {"tpre": w["tpre"] * (y - oc) / mw["tpre"], "tpost": w["tpost"] * (y - oc) / mw["tpost"], "cpre": w["cpre"] * (y - oc) / mw["cpre"],
         "cpost": w["cpost"] * (y - oc) / mw["cpost"], "dpost": w["d"] * (ot_post - oc_post) / mw["d"], "dt1post": w["dt1"] * (ot_post - oc_post) / mw["dt1"],
         "dpre": w["d"] * (ot_pre - oc_pre) / mw["d"], "dt0pre": w["dt0"] * (ot_pre - oc_pre) / mw["dt0"]}
    a = {k: v.mean() for k, v in e.items()}
    att = (a["tpost"] - a["tpre"]) - (a["cpost"] - a["cpre"]) + (a["dpost"] - a["dt1post"]) - (a["dpre"] - a["dt0pre"])
    asy = lambda ws, fit: ws * (y - fit) / (ws.sum() / n)
    asy_pre = asy((1 - D) * (1 - post), oc_pre); asy_post = asy((1 - D) * post, oc_post)
    asy_pre_t = asy(D * (1 - post), ot_pre); asy_post_t = asy(D * post, ot_post); asy_ps = (D - ps) * (n / W.sum())
    inf_t = (e["tpost"] - w["tpost"] * a["tpost"] / mw["tpost"]) - (e["tpre"] - w["tpre"] * a["tpre"] / mw["tpre"]) \
        + asy_post * (-w["tpost"].sum() / n / mw["tpost"]) + asy_pre * (-w["tpre"].sum() / n / mw["tpre"])
    m2pre = (w["cpre"] * (y - oc - a["cpre"])).sum() / n / mw["cpre"]; m2post = (w["cpost"] * (y - oc - a["cpost"])).sum() / n / mw["cpost"]
    inf_c = (e["cpost"] - w["cpost"] * a["cpost"] / mw["cpost"]) - (e["cpre"] - w["cpre"] * a["cpre"] / mw["cpre"]) + asy_ps * (m2post - m2pre) \
        + asy_post * (-w["cpost"].sum() / n / mw["cpost"]) + asy_pre * (-w["cpre"].sum() / n / mw["cpre"])
    inf_eff = ((e["dpost"] - w["d"] * a["dpost"] / mw["d"]) - (e["dt1post"] - w["dt1"] * a["dt1post"] / mw["dt1"])) \
        - ((e["dpre"] - w["d"] * a["dpre"] / mw["d"]) - (e["dt0pre"] - w["dt0"] * a["dt0pre"] / mw["dt0"]))
    mom_post = (w["d"] / mw["d"] - w["dt1"] / mw["dt1"]).sum() / n; mom_pre = (w["d"] / mw["d"] - w["dt0"] / mw["dt0"]).sum() / n
    inf_or = (asy_post_t - asy_post) * mom_post - (asy_pre_t - asy_pre) * mom_pre
    return float(att), inf_t - inf_c + inf_eff + inf_or


def did_aggte_se(uy, kind="simple"):
    """did::att_gt + aggte(type = kind) on uy (unit, Year, y, gvar; gvar 0 = never treated): (estimate, analytical SE, balanced, cells)."""
    uy = uy[np.isfinite(pd.to_numeric(uy["y"], errors="coerce").values)]
    units = pd.unique(uy["unit"].values); n = len(units); upos = pd.Index(units)
    tlist = sorted(uy["Year"].unique()); glist = [g for g in sorted(uy["gvar"].unique()) if g > 0]
    G = uy.groupby("unit", sort=False)["gvar"].first().reindex(units).values
    if not (G == 0).any(): raise InsufficientDataError("did's never-treated comparison: no never-treated series")
    balanced = len(uy) == n * len(tlist) and not uy.duplicated(["unit", "Year"]).any()
    Ym = uy.pivot(index="unit", columns="Year", values="y").reindex(units) if balanced else None
    cells, IF = [], []
    for g in glist:
        pre = [t_ for t_ in tlist if t_ < g]
        if not pre: continue                                                   # did drops a cohort treated in the first period
        b = pre[-1]
        for t in [t_ for t_ in tlist[1:] if t_ >= g]:
            sel = (G == g) | (G == 0); inf = np.zeros(n)
            if balanced:
                att, f = _drdid_panel_if(Ym[t].values[sel], Ym[b].values[sel], (G[sel] == g)); inf[np.where(sel)[0]] = (n / int(sel.sum())) * f
            else:
                r = uy[uy["unit"].isin(set(units[sel])) & uy["Year"].isin([t, b])]
                att, f = _drdid_rc_if(r["y"].values, (r["Year"].values == t), (r["gvar"].values == g))
                np.add.at(inf, upos.get_indexer(r["unit"].values), (n / len(r)) * f)
            cells.append((g, t, att)); IF.append(inf)
    if not cells: raise InsufficientDataError("did: no post-treatment ATT(g,t)")
    att = np.array([c[2] for c in cells]); grp = np.array([c[0] for c in cells]); IF = np.column_stack(IF)
    pgg = np.array([np.mean(G == g) for g in glist]); pg = pgg[pd.Index(glist).get_indexer(grp)]
    def wif(keep, pgv, grpv):
        S = pgv[keep].sum(); cen = np.column_stack([(G == grpv[k]).astype(float) - pgv[k] for k in keep])
        return cen / S - np.outer(cen.sum(axis=1), pgv[keep] / S ** 2)
    if kind == "simple":
        k_ = np.arange(len(att)); est = float(np.sum(att * pg) / pg.sum())
        f = IF @ (pg / pg.sum()) + wif(k_, pg, grp) @ att
    else:
        ag, IFg = [], []
        for g in glist:
            w_ = np.where(grp == g)[0]
            if not len(w_): continue
            ag.append(att[w_].mean()); IFg.append(IF[:, w_] @ (pg[w_] / pg[w_].sum()))
        ag = np.array(ag); IFg = np.column_stack(IFg); gl = np.array([g for g in glist if (grp == g).any()])
        pgs = np.array([np.mean(G == g) for g in gl])
        est = float(np.sum(ag * pgs) / pgs.sum()); f = IFg @ (pgs / pgs.sum()) + wif(np.arange(len(gl)), pgs, gl) @ ag
    se = float(np.sqrt(np.mean(f ** 2) / n))
    return est, (se if se > np.sqrt(np.finfo(float).eps) * 10 else np.nan), balanced, pd.DataFrame(cells, columns=["g", "t", "att"])


def _r_site_cluster(df):
    """R's site_cluster(dt): the sub-watersheds are the clusters when there are >= MIN_SWS_CLUSTERS of them (ids > 0); else none."""
    if "site_id" not in getattr(df, "columns", ()): return False
    s_ = pd.to_numeric(df["site_id"], errors="coerce"); return int(s_[s_ > 0].nunique()) >= MIN_SWS_CLUSTERS


def _did_uy(df, y_col, unit_col, time_col, first_treat_col, never_treated_value=np.inf):
    """R's frame for did (m05_cs / m30_cohorts): one row per series x Year -- the mean outcome, gvar = the cohort (0 = never treated)."""
    ft = pd.to_numeric(df[first_treat_col], errors="coerce").values.astype(np.float64)
    gv = np.where(np.isfinite(ft) & (ft != never_treated_value), ft, 0.0)
    d = pd.DataFrame({"unit": df[unit_col].values, "Year": pd.to_numeric(df[time_col], errors="coerce").values,
                      "y": pd.to_numeric(df[y_col], errors="coerce").values.astype(np.float64), "gvar": gv})
    d = d[np.isfinite(d["y"].values)]
    return d.groupby(["unit", "Year"], sort=False, observed=True).agg(y=("y", "mean"), gvar=("gvar", "first")).reset_index()


def callaway_santanna_att(df, y_col, unit_col, time_col, first_treat_col, never_treated_value=np.inf):
    """Group-time ATT(g,t) = [E(Y_t - Y_{g-1} | G=g)] - [E(Y_t - Y_{g-1} | not yet treated by t)]
    for each cohort g and post-period t >= g. Returns (per-(g,t) table, event-time-aggregated
    average, weighted by cohort size -- CS2021 sec 3.3 event-study aggregation)."""
    unit_col = _unit_key(df, unit_col)             # v20.29: pixel x season unit when the scenario says so
    if "Season" in df.columns and df["Season"].nunique() > 1 and time_col == "Year":    # v20.58: the YEARS of season series -- season-
        df = df.copy(); df["_y_sn"] = season_net(df, y_col); y_col = "_y_sn"             #   matched (as R's M05 / did::att_gt on y_sn)
    cohorts = sorted(g for g in df[first_treat_col].unique() if g != never_treated_value)
    times = sorted(df[time_col].unique())
    results = []
    _never = bool((df[first_treat_col] == never_treated_value).any())    # v20.58: the never-treated series are the comparison when there are
    for g in cohorts:                                                    # any (as R's did::att_gt(control_group = "nevertreated") and diff-diff)
        if g - 1 not in times:
            continue
        base = df[df[time_col] == g - 1]
        treated_units = df[df[first_treat_col] == g]
        for t in [tt for tt in times if tt >= g]:
            y_treat_post = treated_units[treated_units[time_col] == t][y_col].mean()
            y_treat_pre = base[base[unit_col].isin(treated_units[unit_col])][y_col].mean()

            control_units = df[df[first_treat_col] == never_treated_value] if _never else df[df[first_treat_col] > t]
            control_units = control_units[control_units[first_treat_col] != g]
            y_ctrl_post = control_units[control_units[time_col] == t][y_col].mean()
            y_ctrl_pre = base[base[unit_col].isin(control_units[unit_col])][y_col].mean()

            att_gt = (y_treat_post - y_treat_pre) - (y_ctrl_post - y_ctrl_pre)
            results.append({"g": g, "t": t, "event_time": t - g, "ATT_gt": att_gt,
                             "n_treated": treated_units[unit_col].nunique()})

    table = pd.DataFrame(results)
    if table.empty:
        raise InsufficientDataError(
            "No valid ATT(g,t) cells could be formed -- this needs at least one cohort g "
            "with both a pre-period (g-1) present in the data AND a not-yet-treated/never-"
            "treated comparison group observed at some t>=g. Check that first_treat_agri_year "
            "actually varies across units and that years surrounding each cohort's g-1/g exist.")
    # v20.13: aggregate ONLY the identified (g,t) cells. A cell is NaN when no not-yet-treated / never-treated
    # comparison unit exists at time t (every unit treated by then); averaging NaN into the event-time mean
    # used to blank the WHOLE event-time table, hiding the cells that were identified.
    def _agg(d):
        ok_ = d["ATT_gt"].notna()
        if not ok_.any():
            return pd.Series({"ATT": np.nan, "n_cells": 0, "n_cells_identified": 0, "n_treated": int(d["n_treated"].sum())})
        return pd.Series({"ATT": float(np.average(d.loc[ok_, "ATT_gt"], weights=d.loc[ok_, "n_treated"])),
                          "n_cells": int(len(d)), "n_cells_identified": int(ok_.sum()),
                          "n_treated": int(d.loc[ok_, "n_treated"].sum())})
    by_event_time = table.groupby("event_time").apply(_agg, include_groups=False).reset_index()
    by_event_time["ATT_avg"] = by_event_time["ATT"]                 # historical name, kept
    n_unid = int(table["ATT_gt"].isna().sum())
    if n_unid:
        warn(f"Callaway-Sant'Anna: {n_unid} of {len(table)} (g,t) cells have no comparison group (all units treated by "
             f"then) -- those cells are left out of the event-time aggregate; see n_cells_identified")
    by_event_time["engine"] = "engine"; LAST_ENGINE["callaway_santanna"] = "engine"
    # v20.58: the HEADLINE is the SIMPLE aggregation -- every identified post-period ATT(g,t) weighted by its cohort's size -- as R's
    # did::aggte(type = "simple") and diff-diff's overall_att (v20.57 Python took the mean of the event-time effects, R the simple one)
    _post = table[(table["event_time"] >= 0) & table["ATT_gt"].notna()]
    _simple = float(np.average(_post["ATT_gt"], weights=_post["n_treated"])) if len(_post) else np.nan
    by_event_time.attrs.update({"ATT_simple": _simple, "ATT_simple_se": np.nan, "ATT_simple_engine": "engine",
                                "comparison": "never-treated series" if _never else "not-yet-treated series"})
    if _never and not _r_site_cluster(df):                                    # v20.58 (second pass): did's analytical SE (R's M05 with no
        try:                                                                  #   sub-watershed clusters), ported
            _e, _s, _bal, _ = did_aggte_se(_did_uy(df, y_col, unit_col, time_col, first_treat_col, never_treated_value), "simple")
            if np.isfinite(_s) and abs(_e - _simple) <= 1e-9 * max(1.0, abs(_simple)):
                by_event_time.attrs.update({"ATT_simple_se": _s, "ATT_simple_se_how": "did's analytical influence-function SE of the simple aggregation (ported; "
                                            + ("DRDID's panel" if _bal else "DRDID's repeated-cross-section (unbalanced series)") + " estimator), each series a draw"})
            elif np.isfinite(_s):
                warn(f"Callaway-Sant'Anna: did's port gives {_e:.6g}, the engine {_simple:.6g} -- the analytical SE is not attached (the design-based SE is used)")
        except (InsufficientDataError, ValueError, np.linalg.LinAlgError, ZeroDivisionError) as _x:
            info(f"Callaway-Sant'Anna: did's analytical SE not computed ({_x}) -- the design-based SE is used")
    # v20.58 (fifth pass, found by the parity run with cloud gaps): diff-diff's CallawaySantAnna is did::att_gt only on BALANCED series. On
    # series with gaps R's route runs did::att_gt(allow_unbalanced_panel = TRUE) -- DRDID's repeated-cross-section estimator -- which neither
    # of diff-diff's options reproduces (0.0522 / 0.0514 against did's 0.0516 on a panel with 2 % gaps; the engine: 0.0516437, did's to 1e-12).
    # There the ENGINE is did's estimator (ported), so it computes, and says why; on balanced series the verified package, as before.
    _yv = pd.to_numeric(df[y_col], errors="coerce").values.astype(float)
    _uy = df.loc[np.isfinite(_yv), [unit_col, time_col]].drop_duplicates()
    _balanced = len(_uy) == _uy[unit_col].nunique() * _uy[time_col].nunique()
    if _use_prebuilt("callaway_santanna") and not _balanced:
        LAST_ENGINE["callaway_santanna"] = ("engine (did::att_gt's estimator, ported: the series have gaps, and diff-diff's CallawaySantAnna "
                                            "is not did's allow_unbalanced_panel estimator on them)")
        by_event_time["engine"] = LAST_ENGINE["callaway_santanna"]
        by_event_time.attrs["ATT_simple_engine"] = LAST_ENGINE["callaway_santanna"]
        info(f"Callaway-Sant'Anna: {len(_uy):,} of {_uy[unit_col].nunique() * _uy[time_col].nunique():,} series x period cells observed (the series "
             f"have gaps) -- {LAST_ENGINE['callaway_santanna']}")
    elif _use_prebuilt("callaway_santanna"):                                           # v20.29: verified diff-diff
        _r = _route_call("callaway_santanna", _dd_callaway_santanna, df, y_col, unit_col, time_col, first_treat_col)
        if _r:
            for k, a_ in _r.items():
                m_ = (by_event_time["event_time"] == k) & (by_event_time["event_time"] >= 0)
                by_event_time.loc[m_, "ATT"] = a_; by_event_time.loc[m_, "ATT_avg"] = a_
                by_event_time.loc[m_, "engine"] = LAST_ENGINE["callaway_santanna"]
            if np.isfinite(_CS_LAST_FIT.get("overall_att", np.nan)):
                by_event_time.attrs.update({"ATT_simple": _CS_LAST_FIT["overall_att"], "ATT_simple_se": _CS_LAST_FIT.get("overall_se", np.nan),
                                            "ATT_simple_engine": LAST_ENGINE["callaway_santanna"],
                                            "ATT_simple_se_how": f"{LAST_ENGINE['callaway_santanna']}: {_CS_LAST_FIT.get('se_how', 'its own SE')}"})
    return table, by_event_time


def cs_group_aggregation(df, y_col, unit_col, time_col, first_treat_col, never_treated_value=np.inf):
    """v20.58 -- M30 as R's m30_cohorts: Callaway-Sant'Anna's GROUP aggregation on M05's design (the series, the season-matched outcome, the
    never-treated series as the comparison, no covariates): each cohort's effect theta(g) = the mean of its post-period ATT(g,t), and their
    average weighted by cohort size (did::aggte(type = "group")). The ATT(g,t) are callaway_santanna_att's (diff-diff's when verified).
    v20.57's engine estimated another quantity (a two-stage imputation per cohort, unweighted): 0.0507 against R's 0.0522."""
    table, _by = callaway_santanna_att(df, y_col, unit_col, time_col, first_treat_col, never_treated_value)
    post = table[(table["event_time"] >= 0) & table["ATT_gt"].notna()]
    if not len(post): raise InsufficientDataError("no identified post-period ATT(g,t) cell")
    th = post.groupby("g").agg(ATT_cohort=("ATT_gt", "mean"), n_units=("n_treated", "first"), n_post_periods=("t", "size")).reset_index()
    th["weight"] = th["n_units"] / th["n_units"].sum()
    th["engine"] = LAST_ENGINE.get("callaway_santanna", "engine")
    overall = float((th["ATT_cohort"] * th["weight"]).sum())
    th = th.rename(columns={"g": "cohort"}); th.attrs.update({"se": np.nan, "se_how": ""})
    if (df[first_treat_col] == never_treated_value).any() and not _r_site_cluster(df):                     # v20.58 (second pass): did's
        try:                                                                                                   #   analytical SE (as R's M30)
            _d = df.copy(); _y = y_col
            if "Season" in _d.columns and _d["Season"].nunique() > 1 and time_col == "Year": _d["_y_sn"] = season_net(_d, y_col); _y = "_y_sn"
            _e, _s, _bal, _ = did_aggte_se(_did_uy(_d, _y, _unit_key(_d, unit_col), time_col, first_treat_col, never_treated_value), "group")
            if np.isfinite(_s) and abs(_e - overall) <= 1e-9 * max(1.0, abs(overall)):
                th.attrs.update({"se": _s, "se_how": "did::aggte(type = 'group') analytical influence-function SE (ported; "
                                 + ("DRDID's panel" if _bal else "DRDID's repeated-cross-section (unbalanced series)") + " estimator), each series a draw"})
            elif np.isfinite(_s):
                warn(f"cohort aggregation: did's port gives {_e:.6g}, the engine {overall:.6g} -- the analytical SE is not attached")
        except (InsufficientDataError, ValueError, np.linalg.LinAlgError, ZeroDivisionError) as _x:
            info(f"cohort aggregation: did's analytical SE not computed ({_x}) -- the design-based SE is used")
    return th, overall


def sun_abraham_iw(df, y_col, unit_col, time_col, cohort_col, never_treated_value=np.inf,
                    window=(-4, 4), time_fe_col=None):
    """AUDIT FIX (v5.1): `time_col` must stay NUMERIC (Year) because rel_time arithmetic
    needs it, but the TIME FIXED EFFECT should absorb season as well as year. These are
    now two separate arguments: pass time_fe_col="time_fe_yearseason" so seasonal NDVI
    variation is absorbed. Previously this function used the numeric Year for BOTH, which
    left season effects unabsorbed -- measured at 3.4x more bias than the year x season
    spec on a realistic simulated panel with unbalanced seasonal coverage."""
    unit_col = _unit_key(df, unit_col)             # v20.29: pixel x season unit when the scenario says so
    df = df.copy()
    if time_fe_col is None:
        time_fe_col = time_col
    df["rel_time"] = df[time_col] - df[cohort_col].replace(never_treated_value, np.nan)
    lo, hi = window
    in_window_or_never = (df["rel_time"].between(lo, hi)) | (df[cohort_col] == never_treated_value)
    df = df[in_window_or_never].copy()
    if len(df) == 0:
        raise InsufficientDataError(
            f"No rows remain after restricting to rel_time in [{lo},{hi}] or never-treated "
            f"units -- this sample's years/cohorts don't reach the requested window. A DATA "
            f"COVERAGE gap, not a code bug.")

    cohorts = sorted(c for c in df[cohort_col].unique() if c != never_treated_value)
    y_dm = demean_two_way(df[y_col].values, df[unit_col].values, df[time_fe_col].values)
    rel_times = [k for k in range(lo, hi + 1) if k != -1]
    cols, col_meta = [], []
    for g in cohorts:
        for k in rel_times:
            dummy = ((df[cohort_col].values == g) & (df["rel_time"].values == k)).astype(float)
            if dummy.sum() == 0:
                continue
            cols.append(demean_two_way(dummy, df[unit_col].values, df[time_fe_col].values))
            col_meta.append((g, k))
    if not cols:
        raise InsufficientDataError(
            "No cohort x relative-time dummy had any variation -- need at least one "
            "treated cohort with data inside the specified window and a never-treated "
            "comparison group.")
    X = np.column_stack(cols)
    beta = np.linalg.lstsq(X, y_dm, rcond=None)[0]
    coefs = pd.DataFrame(col_meta, columns=["cohort", "rel_time"])
    coefs["beta"] = beta
    cohort_size = df[df[cohort_col] != never_treated_value].groupby(cohort_col)[unit_col].nunique()
    coefs["weight"] = coefs["cohort"].map(cohort_size)
    catt_es = coefs.groupby("rel_time").apply(
        lambda d: np.average(d["beta"], weights=d["weight"]), include_groups=False
    ).rename("CATT_es").reset_index()
    return catt_es


def sun_abraham_fixest(df, y_col, covariates=None, unit_col="pixel_id", time_col="Year", cohort_col="first_treat_agri_year",
                       time_fe_col="time_fe_yearseason", cluster_col="subwshed_id", never_treated_value=np.inf, ref_period=-1):
    """v20.58 -- M09 as R's m09_sunab (fixest::sunab): one dummy per cohort x relative YEAR (every relative year of the treated rows, the
    reference -1 left out, the never-treated series without dummies), the design's covariates, unit (pixel x season) and year x season effects;
    each relative year's effect = the cohorts' coefficients weighted by their OBSERVATIONS in the estimation sample (fixest's aggregation);
    the headline = the mean of the post-period effects with its SE -- the delta method on the cluster-robust covariance of the cohort x period
    coefficients (clusters = sub-watersheds), the design-based SE of the headline when the years are the clusters. v20.57's engine cut the
    window to (-4, 4), had no covariates and weighted the cohorts by their pixels (0.053228 against R's 0.053274)."""
    from scipy import stats as _st
    unit = _unit_key(df, unit_col); cl = _cluster_key(df, cluster_col)
    covs = [c_ for c_ in (covariates or []) if c_ in df.columns]
    d = df[np.isfinite(pd.to_numeric(df[y_col], errors="coerce").values)].copy()
    for c_ in covs: d = d[np.isfinite(pd.to_numeric(d[c_], errors="coerce").values)]
    coh = pd.to_numeric(d[cohort_col], errors="coerce").replace(never_treated_value, np.nan).values
    rel = pd.to_numeric(d[time_col], errors="coerce").values - coh
    fin = np.isfinite(rel)
    cells = sorted({(float(g), int(k)) for g, k in zip(coh[fin], rel[fin]) if int(k) != ref_period})
    if not cells: raise InsufficientDataError("no treated cohort x relative year other than the reference")
    u = d[unit].values; t_ = d[time_fe_col].values
    y_dm = demean_two_way(pd.to_numeric(d[y_col], errors="coerce").values.astype(np.float64), u, t_)
    cols, meta = [], []
    for g, k in cells:
        m = fin & (coh == g) & (rel == k)
        if not m.any(): continue
        cols.append(demean_two_way(m.astype(np.float64), u, t_)); meta.append((g, k, int(m.sum())))
    nd = len(cols)
    for c_ in covs: cols.append(demean_two_way(pd.to_numeric(d[c_], errors="coerce").values.astype(np.float64), u, t_))
    X = np.column_stack(cols); sd_ = X.std(axis=0); keep = sd_ > 1e-10 * max(1.0, float(sd_.max()))
    if not keep[:nd].any(): raise InsufficientDataError("every cohort x relative-year dummy is absorbed by the fixed effects")
    Xk = X[:, keep]; b = np.linalg.lstsq(Xk, y_dm, rcond=None)[0]; e = y_dm - Xk @ b
    cc = pd.factorize(d[cl].values)[0]
    V = cluster_robust_vcov(Xk, e, cc, k_fe=_k_fe_nonnested([u, t_], cc))[0] if int(cc.max()) + 1 >= 2 else None
    kept_d = [i for i in range(nd) if keep[i]]; bd = dict(zip(kept_d, b[:len(kept_d)]))
    tab = pd.DataFrame([{"cohort": g, "rel_time": k, "n_obs": n_, "beta": bd.get(i, np.nan)} for i, (g, k, n_) in enumerate(meta)])
    ok_ = tab["beta"].notna()
    agg = tab[ok_].groupby("rel_time").apply(lambda q: pd.Series({"CATT_es": float(np.average(q["beta"], weights=q["n_obs"])), "n_obs": int(q["n_obs"].sum()),
                                                                   "n_cohorts": int(len(q))}), include_groups=False).reset_index()
    post = sorted(int(k) for k in agg.loc[agg["rel_time"] >= 0, "rel_time"])
    if not post: raise InsufficientDataError("no identified post-period effect")
    L = np.zeros(Xk.shape[1]); pos = {i: j for j, i in enumerate(kept_d)}
    for k in post:
        ix = [i for i, (g, kk, n_) in enumerate(meta) if kk == k and i in pos]; tot = sum(meta[i][2] for i in ix)
        for i in ix: L[pos[i]] = meta[i][2] / tot / len(post)
    est = float(L @ b)
    if str(LAST_CLUSTER_USED.get("value", "")).startswith("Year") or V is None:
        de = design_se_event(y_col, df, est); se, dfp, how = float(de["se"]), float(de["df"]), de["how"]
    else:
        G = int(cc.max()) + 1; se = float(np.sqrt(max(0.0, L @ V @ L))); dfp = float(max(1, G - 1))
        how = f"delta method on the cluster-robust covariance of the cohort x period coefficients ({G} clusters)"
    p = float(2 * _st.t.sf(abs(est / se), dfp)) if np.isfinite(se) and se > 0 else np.nan
    head = {"outcome": y_col, "estimate": est, "se": se, "p_value": p, "se_how": how, "p_how": f"t with {dfp:g} df", "post_event_times": ";".join(map(str, post)),
            "covariates": ",".join(covs), "engine": "engine: interaction-weighted (fixest::sunab's design and aggregation)"}
    return agg, tab, head


def by_season_table(df, y_col, covariates=None):
    """v20.58 (as R's by_season_R): the canonical DiD per SEASON -- estimate, cluster-robust SE, p (t, clusters - 1), rows -- and each season's
    weight in the pooled estimate (its share of the treatment variation left after the fixed effects). Your v20.56 log: the annual composite
    and the seasons gave different pictures; this table shows which season carries the pooled number."""
    from scipy import stats as _st
    if "Season" not in df.columns or df["Season"].nunique() < 2: return None
    rows = []
    for s_ in sorted(pd.unique(df["Season"])):
        x = df[df["Season"] == s_]
        try:
            b, se = estimate_twfe_did(x, y_col, "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id", covariates=covariates)
            G_ = int(LAST_FIT_INFO.get("n_clusters") or 2); p_ = float(2 * _st.t.sf(abs(b / se), max(1, G_ - 1))) if se > 0 else np.nan
            u = _unit_key(x, "pixel_id"); dd_ = demean_two_way(pd.to_numeric(x["did_term"], errors="coerce").values.astype(np.float64), x[u].values, x["time_fe_yearseason"].values)
            rows.append({"season": SEASON_LABEL.get(int(s_), s_), "estimate": b, "se": se, "p_value": p_, "clusters": G_, "rows": int(len(x)), "weight": float(np.sum(dd_ ** 2))})
        except Exception as e:
            rows.append({"season": SEASON_LABEL.get(int(s_), s_), "estimate": np.nan, "se": np.nan, "p_value": np.nan, "clusters": np.nan, "rows": int(len(x)),
                         "weight": np.nan, "note": f"{type(e).__name__}: {str(e)[:80]}"})
    t = pd.DataFrame(rows); w = t["weight"].values
    t["weight"] = w / np.nansum(w) if np.nansum(w) > 0 else np.nan; t.insert(0, "outcome", y_col)
    info(f"{y_col} by season -- the pooled estimate is their weighted mean (weight = the treatment variation each season holds): "
         + "; ".join(f"{r_.season} {r_.estimate:.4g} (SE {r_.se:.2g}, weight {100 * r_.weight:.0f} %)" for r_ in t.itertuples()))
    return t

def ddd_regression(df, y_col, group3_col, unit_col="pixel_id", time_col="time_fe_yearseason"):
    """v20.58 (M10): the triple difference as a regression -- y ~ did x g3 + did | unit + (year x season) x g3 -- with the cluster-robust SE on
    the design cluster (the sub-watershed, or the year below MIN_SWS_CLUSTERS of them); p from t with clusters - 1 df. did x g3 = the DiD in
    group 3 minus the DiD in the rest (0 without heterogeneity); did = the DiD in the rest."""
    from scipy import stats as _st
    d = df.copy()
    d["did_term"] = pd.to_numeric(d["did_term"], errors="coerce").astype("float64")
    g3 = pd.to_numeric(d[group3_col], errors="coerce").fillna(0).astype(int)
    if g3.nunique() < 2: raise InsufficientDataError(f"{group3_col} has one value only -- no triple difference")
    d["did_g3"] = d["did_term"] * g3; d["_tfe_g3"] = d[time_col].astype(str) + "|" + g3.astype(str)
    r = estimate_twfe_did(d, y_col, "did_g3", unit_col, "_tfe_g3", "subwshed_id", covariates=["did_term"], return_all=True, covariates_by_post=False)
    G_ = int(r.get("n_clusters") or 2); b, se = r["beta"], r["se"]
    return {"DDD": b, "se": se, "p_t_G1": float(2 * _st.t.sf(abs(b / se), max(1, G_ - 1))) if se > 0 else np.nan, "n_clusters": G_,
            "cluster_used": LAST_CLUSTER_USED.get("value"), "did_rest": r["coef"].get("did_term", np.nan), "se_did_rest": r["se_all"].get("did_term", np.nan)}

def run_ddd(df, y_col, treat_col, post_col, group3_col):
    def cell(t, p, g):
        sub = df[(df[treat_col]==t)&(df[post_col]==p)&(df[group3_col]==g)][y_col]
        if len(sub) == 0:
            raise InsufficientDataError(
                f"DDD needs all 8 (treat x post x group3) cells populated -- cell "
                f"(treat={t}, post={p}, group3={g}) has zero rows in this sample.")
        return sub.mean()
    did_g1 = (cell(1,1,1) - cell(1,0,1)) - (cell(0,1,1) - cell(0,0,1))
    did_g0 = (cell(1,1,0) - cell(1,0,0)) - (cell(0,1,0) - cell(0,0,0))
    return did_g1 - did_g0


def compute_sdid_regularization(Y_control_pre, n_treated, t_post):
    diffs = np.diff(Y_control_pre, axis=1).flatten()
    sigma_hat = np.std(diffs, ddof=1)
    return (n_treated * t_post) ** 0.25 * sigma_hat


def fit_sdid_unit_weights(Y_control_pre, Y_treated_pre_mean, zeta):
    N0, T0 = Y_control_pre.shape
    def objective(params):
        omega0, omega = params[0], params[1:]
        pred = omega0 + Y_control_pre.T @ omega
        return np.sum((pred - Y_treated_pre_mean) ** 2) + (zeta ** 2) * T0 * np.sum(omega ** 2)
    constraints = [{'type': 'eq', 'fun': lambda p: np.sum(p[1:]) - 1}]
    bounds = [(None, None)] + [(0, 1)] * N0
    x0 = np.concatenate([[0.0], np.ones(N0) / N0])
    res = minimize(objective, x0, method='SLSQP', constraints=constraints, bounds=bounds,
                   options={'maxiter': 1000, 'ftol': 1e-10})
    omega0, omega = res.x[0], res.x[1:]
    omega = np.clip(omega, 0, None)
    return omega0, omega / max(omega.sum(), 1e-12)


def fit_sdid_time_weights(Y_control_pre, Y_control_unit_mean):
    N0, T0 = Y_control_pre.shape
    def objective(params):
        lambda0, lam = params[0], params[1:]
        pred = lambda0 + Y_control_pre @ lam
        return np.sum((pred - Y_control_unit_mean) ** 2)
    constraints = [{'type': 'eq', 'fun': lambda p: np.sum(p[1:]) - 1}]
    bounds = [(None, None)] + [(0, 1)] * T0
    x0 = np.concatenate([[0.0], np.ones(T0) / T0])
    res = minimize(objective, x0, method='SLSQP', constraints=constraints, bounds=bounds,
                   options={'maxiter': 1000, 'ftol': 1e-10})
    lambda0, lam = res.x[0], res.x[1:]
    lam = np.clip(lam, 0, None)
    return lambda0, lam / max(lam.sum(), 1e-12)


def run_synthetic_diD(y_treated_pre, donor_pre_matrix, y_treated_post, donor_post_matrix):
    """Full point estimate using both unit and time weights + intercepts (see markdown)."""
    zeta = compute_sdid_regularization(donor_pre_matrix, n_treated=1, t_post=donor_post_matrix.shape[1])
    omega0, omega = fit_sdid_unit_weights(donor_pre_matrix, y_treated_pre, zeta)
    control_unit_mean = donor_pre_matrix.mean(axis=1)
    lambda0, lam = fit_sdid_time_weights(donor_pre_matrix, control_unit_mean)

    treated_post_avg = y_treated_post.mean()
    treated_weighted_pre = (lam * y_treated_pre).sum()
    control_post_weighted = omega @ donor_post_matrix.mean(axis=1)
    control_pre_weighted = omega @ (donor_pre_matrix @ lam)
    tau = (treated_post_avg - treated_weighted_pre) - (control_post_weighted - control_pre_weighted)
    return tau, omega, lam


def run_chained_did(df, y_col, unit_col, time_col, treat_col, times_chain):
    unit_col = _unit_key(df, unit_col)             # v20.29: pixel x season unit when the scenario says so
    # v20.29: a pixel x season series is observed once a YEAR, so it is chained year to year within its season
    # (consecutive Year x Season periods are different seasons and never share a unit). With unit_fe = "pixel" the
    # chain over consecutive Year x Season periods is kept exactly as before.
    if unit_col == "unit_id" and time_col in ("period_index", "time_fe_yearseason") and "Year" in df.columns:
        time_col = "Year"; times_chain = sorted(int(y) for y in pd.unique(df["Year"]))
    chained = []
    cumulative = 0.0
    for i in range(len(times_chain) - 1):
        t0, t1 = times_chain[i], times_chain[i+1]
        sub = df[df[time_col].isin([t0, t1])]
        units_both = sub.groupby(unit_col)[time_col].nunique()
        sub = sub[sub[unit_col].isin(units_both[units_both == 2].index)]
        if sub.empty:
            continue
        piv = sub.pivot_table(index=unit_col, columns=time_col, values=y_col)
        treat_status = sub.groupby(unit_col)[treat_col].first()
        d_y = piv[t1] - piv[t0]
        if (treat_status == 1).sum() == 0 or (treat_status == 0).sum() == 0:
            continue   # this specific period-pair has no overlap on one side -- try the next pair
        step_did = d_y[treat_status == 1].mean() - d_y[treat_status == 0].mean()
        cumulative += step_did
        chained.append({"t0": t0, "t1": t1, "step_did": step_did,
                         "n_overlap": len(sub[unit_col].unique()), "cumulative": cumulative})
    if not chained:
        raise InsufficientDataError(
            f"No consecutive period-pair in {times_chain} had any unit observed in BOTH "
            f"periods AND spanning both treat_core values -- chaining needs at least one "
            f"such pair to produce a single step. This is a DATA COVERAGE gap (panel "
            f"unbalance is worse than this sample can bridge), not a code bug.")
    return pd.DataFrame(chained)


def chained_fd_did(df, y_col, unit_col="pixel_id", did_col="did_term", period_col="time_fe_yearseason", cluster_col="subwshed_id"):
    """v20.58 -- M12 as R's m12_chained: FIRST DIFFERENCES between consecutive observations of each series (the model's unit: pixel x season,
    so a series steps from one year to its next observed year), the change in the outcome regressed on the change in the treatment with one
    effect per period PAIR (prev -> this period), cluster-robust SE (fixest's CR1 factor, t with G - 1 df). v20.57's engine summed the
    treated-minus-control step changes over the chain -- the long difference between the first and the LAST year (the effect of the last
    year only, 0.0496 against R's 0.0523 on the poison test): another estimand under the model's name. The SE is not identified when the
    treatment switches inside ONE cluster (one sub-watershed: the years are the clusters) -- then NaN with the reason (the headline takes the
    design-based SE, as R)."""
    from scipy import stats as _st
    unit = _unit_key(df, unit_col); cl = _cluster_key(df, cluster_col)
    cols = list(dict.fromkeys([unit, "Year", "Season", period_col, y_col, did_col, cl]))
    d = df[[c_ for c_ in cols if c_ in df.columns]].copy()
    d[y_col] = pd.to_numeric(d[y_col], errors="coerce"); d = d[np.isfinite(d[y_col].values)]
    if "Season" not in d.columns: d["Season"] = 0
    d = d.sort_values([unit, "Year", "Season"], kind="mergesort")
    g = d.groupby(unit, sort=False)
    dy = (d[y_col] - g[y_col].shift()).values.astype(np.float64)
    ddid = (pd.to_numeric(d[did_col], errors="coerce") - g[did_col].shift()).values.astype(np.float64)
    pair = (g[period_col].shift().astype(str) + ">" + d[period_col].astype(str)).values
    ok_ = np.isfinite(dy) & np.isfinite(ddid)
    dy, ddid, pair, clv = dy[ok_], ddid[ok_], pair[ok_], d[cl].values[ok_]
    if not len(dy) or not np.any(ddid != 0): raise InsufficientDataError("no series switches into treatment between two of its observations")
    pc = pd.factorize(pair)[0]
    x = ddid - (np.bincount(pc, weights=ddid) / np.bincount(pc))[pc]; yv = dy - (np.bincount(pc, weights=dy) / np.bincount(pc))[pc]
    xx = float(x @ x)
    if not xx > 0: raise InsufficientDataError("the change in the treatment is absorbed by the period-pair effects")
    b = float(x @ yv) / xx; e = yv - b * x
    cc = pd.factorize(clv)[0]; G = int(cc.max()) + 1
    n_cl = int(pd.Series(clv[ddid != 0]).nunique())
    if n_cl >= 2 and G >= 2:
        V = cluster_robust_se(x.reshape(-1, 1), e, cc, k_fe=_k_fe_nonnested([pc], cc)); se = float(np.sqrt(max(0.0, V[0, 0])))
        p = float(2 * _st.t.sf(abs(b / se), G - 1)) if se > 0 else np.nan; note = ""
    else:
        se, p = np.nan, np.nan; note = "cluster-robust SE not identified (the switch lies in one cluster); read the design-based SE"
    return pd.DataFrame([{"outcome": y_col, "beta": b, "se": se, "p_value": p, "se_note": note, "n_differences": int(len(dy)),
                          "n_switch_differences": int(np.sum(ddid != 0)), "n_clusters": G, "cluster_used": str(LAST_CLUSTER_USED.get("value") or cl),
                          "engine": "engine: first differences (chained), period-pair effects -- R's m12_chained"}])


def run_switcher_did_simplified(df, y_col, unit_col, time_col, treat_col):
    unit_col = _unit_key(df, unit_col)             # v20.29: pixel x season unit when the scenario says so
    times = sorted(df[time_col].unique())
    results = []
    for i in range(len(times) - 1):
        t0, t1 = times[i], times[i+1]
        sub = df[df[time_col].isin([t0, t1])]
        piv_y = sub.pivot_table(index=unit_col, columns=time_col, values=y_col)
        piv_d = sub.pivot_table(index=unit_col, columns=time_col, values=treat_col)
        both = piv_y.dropna().index.intersection(piv_d.dropna().index)
        if len(both) == 0:
            continue
        dy = piv_y.loc[both, t1] - piv_y.loc[both, t0]
        dd = piv_d.loc[both, t1] - piv_d.loc[both, t0]
        switch_on, switch_off, stayers = dd > 0, dd < 0, dd == 0
        if stayers.sum() == 0:
            continue
        stayer_mean = dy[stayers].mean()
        if switch_on.sum() > 0:
            results.append({"t0": t0, "t1": t1, "direction": "switch_on",
                             "effect": dy[switch_on].mean() - stayer_mean, "n_switchers": int(switch_on.sum())})
        if switch_off.sum() > 0:
            results.append({"t0": t0, "t1": t1, "direction": "switch_off",
                             "effect": -(dy[switch_off].mean() - stayer_mean), "n_switchers": int(switch_off.sum())})
    table = pd.DataFrame(results)
    if table.empty:
        return table, np.nan
    return table, np.average(table["effect"], weights=table["n_switchers"])



def did_multiplegt_dyn_port(uy, effects=3, placebo=2, cluster_col=None, group="u", time="Year", outcome="y", treatment="D"):
    """v20.58 (fourth pass): DIDmultiplegtDYN 2.4.0's did_multiplegt_dyn() ported (binary / discrete treatment; no controls, weights,
    trends or normalisation -- R's m13_switchers call): its panel preparation (the status quo = the first observed treatment, F_g the first
    change, a switcher whose last pre-switch period is missing becomes a control truncated there, never-switchers truncated after their last
    observation, the balanced grid, T_g / L_g / S_g), the effects DID_l with their influence functions U_g and the variance's cohort-demeaned
    U_g (E_hat_gt: the mean change of the switchers of the same status quo and switch date, or of the not-yet-switched groups of the same
    status quo and period; DOF_gt = sqrt(n / (n - 1)) small-sample factors), the placebos (compute_placebo_effects_polars) and the average
    total effect (the effects weighted by their switchers, its U_g the same combination). SE = sqrt(sum_g U_g^2) / G, clustered: the U_g
    summed within the cluster first (the cohort counts then count clusters). Checked against the package on ten panels (balanced,
    unbalanced up to 20 % missing, 1-3 cohorts, a year missing, late cohorts, clusters): every estimate and SE to 1.4e-16.
    uy: one row per group x period (group, time, outcome, treatment[, cluster]). Returns (effects table, ATE, ATE SE, placebos table)."""
    cols = [group, time, outcome, treatment] + ([cluster_col] if cluster_col else [])
    d = uy[cols].copy()
    d = d[d[group].notna() & d[time].notna()]
    times = np.sort(d[time].unique()); tix = {v: k + 1 for k, v in enumerate(times)}               # the dense rank of the period, 1-based
    d["t"] = d[time].map(tix).astype(int)
    d = d.sort_values([group, "t"], kind="mergesort")
    dn = d[d[treatment].notna()]
    d["d_sq"] = d[group].map(dn.groupby(group)[treatment].first())                                    # the status quo
    d["diff_sq"] = d[treatment] - d["d_sq"]
    inc = ((d["diff_sq"] > 0) & d[treatment].notna()).astype(int).groupby(d[group]).cummax()
    dec = ((d["diff_sq"] < 0) & d[treatment].notna()).astype(int).groupby(d[group]).cummax()
    d = d[~((inc == 1) & (dec == 1))]
    d["ever"] = ((d["diff_sq"].abs() > 0) & d[treatment].notna()).astype(int).groupby(d[group]).cummax().values
    prev = d.groupby(group)["ever"].shift(1)
    d["tmpF"] = np.where((d["ever"] == 1) & (prev == 0), d["t"], 0)
    d["F"] = d.groupby(group)["tmpF"].transform("max")
    sdF = d.groupby("d_sq")["F"].transform(lambda s_: s_.std(ddof=1) if len(s_) > 1 else np.nan)
    d = d[sdF > 0]                                                                                    # status quos whose F varies
    G = int(d[group].nunique())
    if G == 0: raise InsufficientDataError("DIDmultiplegtDYN: no status quo with both switching and not-yet-switched groups")
    d["never_all"] = 1 - d["ever"]
    d = d[d.groupby(["t", "d_sq"])["never_all"].transform("max") > 0]                                  # periods with a control
    t_min, T_max = int(d["t"].min()), int(d["t"].max())
    d.loc[d["F"] == 0, "F"] = T_max + 1
    d["yv"] = pd.to_numeric(d[outcome], errors="coerce").astype(float)
    dnn = d[d[treatment].notna()]
    d["min_d"] = d[group].map(dnn.groupby(group)["t"].min()); d["max_d"] = d[group].map(dnn.groupby(group)["t"].max())
    d["lob"] = d[group].map(d[(d["t"] < d["F"]) & d[treatment].notna()].groupby(group)["t"].max())
    d.loc[d["t"] < d["min_d"], "yv"] = np.nan
    cond = (d["F"] < T_max + 1) & (d["lob"] < d["F"] - 1)                                              # the pre-switch period missing:
    d.loc[cond & (d["t"] > d["lob"]), "yv"] = np.nan                                                  #   a control, truncated
    d["trunc"] = np.where(cond, d["lob"] + 1, np.nan)
    d.loc[cond, "F"] = T_max + 1
    nevr = d["F"] == T_max + 1
    d.loc[nevr & (d["t"] > d["max_d"]), "yv"] = np.nan
    d.loc[nevr, "trunc"] = d.loc[nevr, "max_d"] + 1
    gids = np.sort(d[group].unique()); gi = {g_: k for k, g_ in enumerate(gids)}
    Y = np.full((len(gids), T_max + 2), np.nan); Dm = np.full((len(gids), T_max + 2), np.nan)
    ri = d[group].map(gi).values; Y[ri, d["t"].values] = d["yv"].values; Dm[ri, d["t"].values] = pd.to_numeric(d[treatment], errors="coerce").values
    gg = d.groupby(group).agg(d_sq=("d_sq", "first"), F=("F", "first"), trunc=("trunc", "first")).reindex(gids)
    CL = d.groupby(group)[cluster_col].first().reindex(gids).values if cluster_col else None
    dsq = gg["d_sq"].values.astype(float); F = gg["F"].values.astype(float); tr = gg["trunc"].values.astype(float)
    Ngt = np.where(np.isfinite(Y) & np.isfinite(Dm), 1.0, 0.0); Ngt[:, :t_min] = 0.0
    Ftr = np.where(np.isnan(tr), F, np.minimum(F, tr))
    Tg = pd.Series(Ftr).groupby(dsq).transform("max").values - 1
    S = np.full(len(gids), np.nan)
    for k in range(len(gids)):
        if F[k] < T_max + 1:
            v = Dm[k, int(F[k]):int(Tg[k]) + 1]; v = v[np.isfinite(v)]
            S[k] = float(v.mean() > dsq[k]) if len(v) else np.nan
    dfg = np.array([Dm[k, int(F[k])] if F[k] <= T_max and np.isfinite(Dm[k, int(F[k])]) else (dsq[k] if F[k] == T_max + 1 else np.nan) for k in range(len(gids))])
    L = Tg - F + 1
    Lu = np.nanmax(np.where(S == 1, L, np.nan)) if np.any(S == 1) else 0
    lmax = int(max(min(Lu, effects), 0))
    Lpl = np.where((F >= 3) & np.isfinite(L), np.minimum(L, F - 2), np.nan)
    Lpu = np.nanmax(np.where(S == 1, Lpl, np.nan)) if np.any((S == 1) & np.isfinite(Lpl)) else 0
    lpmax = int(min(placebo, max(Lpu, 0))) if placebo else 0
    tt = np.arange(T_max + 2)[None, :]
    sk = pd.Series(list(zip(dsq, F, dfg))).astype(str).values                                          # the switchers' cohort (d_sq, F, d_F)
    def _bydsq(A):
        out_ = np.zeros_like(Y)
        for s_ in np.unique(dsq):
            m_ = dsq == s_; out_[m_] = np.nansum(A[m_], axis=0)[None, :]
        return out_
    def _cohort(mask, keys, by_t, dy_):
        m_ = np.full_like(Y, np.nan); c_ = np.full_like(Y, np.nan)
        rr, cc = np.nonzero(mask)
        if not len(rr): return m_, c_
        f_ = pd.DataFrame({"k": keys[rr], "t": cc if by_t else 0, "n": Ngt[rr, cc], "ny": Ngt[rr, cc] * dy_[rr, cc], "cl": (CL[rr] if CL is not None else rr)})
        a_ = f_.groupby(["k", "t"]).agg(n=("n", "sum"), ny=("ny", "sum"), dof=("cl", "nunique") if CL is not None else ("cl", "size"))
        a_ = a_.reindex(pd.MultiIndex.from_arrays([f_["k"], f_["t"]]))
        m_[rr, cc] = (a_["ny"] / a_["n"]).values; c_[rr, cc] = a_["dof"].values
        return m_, c_
    def _var(U_):
        return float(np.sum(U_ ** 2)) if CL is None else float(pd.Series(U_).groupby(CL).sum().pow(2).sum())
    def _ehat_dof(pre, swt, ok_ns, ok_s, dy_):
        mns, dns = _cohort(ok_ns, dsq, True, dy_); ms_, ds_ = _cohort(ok_s, sk, False, dy_); mnss, dnss = _cohort(ok_ns | ok_s, dsq, True, dy_)
        E = np.full_like(Y, np.nan); DOF = np.full_like(Y, np.nan); E[pre | swt] = 0.0; DOF[pre | swt] = 1.0
        c1 = pre & np.isfinite(dns) & (dns >= 2); E[c1] = mns[c1]
        c2 = swt & np.isfinite(ds_) & (ds_ >= 2); E[c2] = ms_[c2]
        c3 = np.isfinite(dnss) & (dnss >= 2) & ((swt & np.isfinite(ds_) & (ds_ == 1)) | (pre & np.isfinite(dns) & (dns == 1))); E[c3] = mnss[c3]
        c4 = swt & np.isfinite(ds_) & (ds_ > 1); DOF[c4] = np.sqrt(ds_[c4] / (ds_[c4] - 1))
        c5 = pre & np.isfinite(dns) & (dns > 1); DOF[c5] = np.sqrt(dns[c5] / (dns[c5] - 1))
        DOF[c3] = np.sqrt(dnss[c3] / (dnss[c3] - 1))
        return E, DOF
    eff, plc, Us, Uvs, Ns = [], [], [], [], []
    for i in range(1, max(lmax, lpmax) + 1):
        dy = np.full_like(Y, np.nan); dy[:, i:] = Y[:, i:] - Y[:, :-i]; ok = np.isfinite(dy)
        never = np.where(ok, (F[:, None] > tt).astype(float), np.nan)
        ctrl = _bydsq(never * Ngt)
        dist = np.where(ok, ((tt == F[:, None] - 1 + i) & (i <= L[:, None]) & (S[:, None] == 1) & (ctrl > 0)).astype(float), np.nan)
        Nt = np.nansum(dist * Ngt, axis=0); N1 = float(Nt[t_min:T_max + 1].sum())
        pre = tt < F[:, None]; swt = tt == (F[:, None] - 1 + i)
        dum = (i <= Tg - 1).astype(float)[:, None]; win = ((tt >= i + 1) & (tt <= Tg[:, None])).astype(float)
        if N1 == 0:
            if i <= lmax: eff.append({"l": i, "estimate": np.nan, "se": np.nan, "N_switcher_obs": 0.0})
            if i <= lpmax: plc.append({"l": i, "estimate": np.nan, "se": np.nan, "N_switcher_obs": 0.0})
            continue
        Ntg = _bydsq(dist * Ngt); ratio = np.where(ctrl == 0, 0.0, Ntg / np.where(ctrl == 0, 1.0, ctrl))
        E, DOF = _ehat_dof(pre, swt, (Ngt != 0) & ok & (never == 1) & (Nt[None, :] > 0), (Ngt != 0) & (dist == 1), dy)
        base = dum * (G / N1) * win * Ngt * (dist - ratio * never)
        U = np.nansum(base * dy, axis=1); Uv = np.nansum(base * DOF * (dy - E), axis=1); v = _var(Uv)
        if i <= lmax:
            eff.append({"l": i, "estimate": float(U.sum() / G), "se": float(np.sqrt(v) / G) if v > 0 else np.nan, "N_switcher_obs": N1})
            Us.append(U); Uvs.append(Uv); Ns.append(N1)
        if i <= lpmax:
            dyp = np.full_like(Y, np.nan)
            if Y.shape[1] > 2 * i: dyp[:, 2 * i:] = Y[:, :-2 * i] - Y[:, i:-i]
            okp = np.isfinite(dyp); nevp = never * okp.astype(float)
            ctrlp = _bydsq(nevp * Ngt)
            distp = np.where(np.isfinite(dist), dist * okp.astype(float) * (ctrlp > 0).astype(float), np.nan)
            Ntp = np.nansum(distp * Ngt, axis=0); Np = float(Ntp[t_min:T_max + 1].sum())
            if Np == 0: plc.append({"l": i, "estimate": np.nan, "se": np.nan, "N_switcher_obs": 0.0}); continue
            Ntgp = _bydsq(distp * Ngt); ratp = np.where(ctrlp == 0, 0.0, Ntgp / np.where(ctrlp == 0, 1.0, ctrlp))
            Ep, DOFp = _ehat_dof(pre, swt, (Ngt != 0) & okp & (nevp == 1) & (Ntp[None, :] > 0), (Ngt != 0) & (distp == 1), dyp)
            basep = dum * (G / Np) * win * Ngt * (distp - ratp * nevp)
            Up = np.nansum(basep * dyp, axis=1); vp = _var(np.nansum(basep * DOFp * (dyp - Ep), axis=1))
            plc.append({"l": i, "estimate": float(Up.sum() / G), "se": float(np.sqrt(vp) / G) if vp > 0 else np.nan, "N_switcher_obs": Np})
    if not Ns: raise InsufficientDataError("DIDmultiplegtDYN: no effect is estimable (no switcher with a not-yet-switched control)")
    w = np.array(Ns) / float(sum(Ns))                                                                  # delta_D = 1 for a 0 -> 1 switch
    Ua = np.sum([w_ * u_ for w_, u_ in zip(w, Us)], axis=0); Uva = np.sum([w_ * u_ for w_, u_ in zip(w, Uvs)], axis=0)
    va = _var(Uva)
    return pd.DataFrame(eff), float(Ua.sum() / G), (float(np.sqrt(va) / G) if va > 0 else np.nan), pd.DataFrame(plc)


def switcher_did(df, y_col, unit_col="pixel_id", effects=3, placebo=2):
    """v20.58 -- M13 (de Chaisemartin & D'Haultfoeuille) as R's m13_switchers: DIDmultiplegtDYN's estimator on the SAME season-netted unit x year
    panel (R's unit_year: the outcome net of the control rings' mean in the same season and year, one row per pixel x season series and
    year). The treatment is D = treated x post -- a watershed programme SWITCHES ON (v20.57 looked for a change of treat_core, the GROUP,
    which never changes, and reported "no switchers" on every panel: M13 never ran in Python while R computed it). For each series that
    switches on in year F, the effect l years later (l = 1 .. `effects`: l = 1 is year F) is its change from F - 1 minus the mean change of
    the series not yet switched by F - 1 + l (never-treated rings included), observed in both years; DID_l averages them over the switchers;
    the headline -- DIDmultiplegtDYN's average total effect -- averages the DID_l weighted by their numbers of switchers.
    v20.58 (fourth pass): the estimates and their SEs are the PACKAGE's -- did_multiplegt_dyn_port (the effects, the placebos with their
    sign and sample -- the change from F - 1 to F - 1 - l, among the switchers whose effect l is computed; v20.58's first version had the
    opposite sign and every switcher -- the average total effect and the analytic SEs, clustered on the sub-watersheds when there are
    >= MIN_SWS_CLUSTERS of them, as R's site_cluster). The simplified per-cell computation stays as the cross-check (estimate_simplified,
    n_switchers, n_controls, switch_years)."""
    unit = _unit_key(df, unit_col)
    tc = "treatment" if "treatment" in df.columns else ("treat_core" if "treat_core" in df.columns else "treat")
    d = pd.DataFrame({"u": df[unit].values, "Year": pd.to_numeric(df["Year"], errors="coerce").values,
                      "y": season_net(df, y_col, treat_col=tc),
                      "treat": pd.to_numeric(df[tc], errors="coerce").values == 1, "post": pd.to_numeric(df["post"], errors="coerce").values == 1})
    d = d[np.isfinite(d["y"].values) & np.isfinite(d["Year"].values)]
    if "site_id" in df.columns: d["site_id"] = pd.to_numeric(df["site_id"], errors="coerce").values[d.index.values]   # (d's index = positions)
    uy = d.groupby(["u", "Year"], observed=True).agg(y=("y", "mean"), treat=("treat", "max"), post=("post", "max"),
                                                     **({"site_id": ("site_id", "first")} if "site_id" in d.columns else {})).reset_index()
    uy["D"] = (uy["treat"] & uy["post"]).astype(int)
    yrs = sorted(int(v) for v in uy["Year"].unique()); ix = {y_: i for i, y_ in enumerate(yrs)}
    uy["t"] = uy["Year"].astype(int).map(ix)
    Y = uy.pivot(index="u", columns="t", values="y"); Dm = uy.pivot(index="u", columns="t", values="D")
    first_obs = Dm.notna().values.argmax(axis=1)
    D0 = Dm.values[np.arange(len(Dm)), first_obs]
    sw = np.where(np.nan_to_num(Dm.values, nan=0.0) != D0[:, None], 1, 0)
    F = np.where(sw.any(axis=1), sw.argmax(axis=1), np.iinfo(np.int32).max)       # the first period whose D differs from the first one
    base0 = D0 == 0
    Yv = Y.values
    def _l(l, plac=False):
        vals = []
        for Fv in sorted(set(F[(F < 10**9) & base0])):
            if Fv < 1: continue
            a, b_ = (Fv - 1 - l, Fv - 1) if plac else (Fv - 1, Fv - 1 + l)
            if a < 0 or b_ >= Yv.shape[1]: continue
            g_ = np.flatnonzero((F == Fv) & base0)
            c_ = np.flatnonzero(base0 & (F > Fv - 1 + l))
            dg = Yv[g_, b_] - Yv[g_, a]; dc = Yv[c_, b_] - Yv[c_, a]
            dg = dg[np.isfinite(dg)]; dc = dc[np.isfinite(dc)]
            if len(dg) and len(dc): vals.append((len(dg), float(dg.mean() - dc.mean()), len(dc), Fv))
        if not vals: return np.nan, 0, []
        n = sum(v[0] for v in vals); return float(sum(v[0] * v[1] for v in vals) / n), int(n), vals
    rows = []
    for l in range(1, int(effects) + 1):
        e_, n_, v_ = _l(l); rows.append({"kind": "effect", "l": l, "estimate": e_, "n_switchers": n_,
                                         "n_controls": int(sum(v[2] for v in v_)), "switch_years": ",".join(str(yrs[v[3]]) for v in v_)})
    for l in range(1, int(placebo) + 1):
        e_, n_, v_ = _l(l, plac=True); rows.append({"kind": "placebo", "l": l, "estimate": e_, "n_switchers": n_,
                                                   "n_controls": int(sum(v[2] for v in v_)), "switch_years": ",".join(str(yrs[v[3]]) for v in v_)})
    tab = pd.DataFrame(rows)
    ef = tab[(tab["kind"] == "effect") & (tab["n_switchers"] > 0) & np.isfinite(tab["estimate"])]
    if not len(ef):
        raise InsufficientDataError("no series switches on with a not-yet-switched control observed in the same years -- the switcher DiD is not identified")
    ate_simpl = float(np.sum(ef["estimate"] * ef["n_switchers"]) / ef["n_switchers"].sum())
    # v20.58 (fourth pass): the package's numbers -- estimates, placebos and SEs (did_multiplegt_dyn_port); the simplified ones beside them
    _cl = "site_id" if (_r_site_cluster(df) and "site_id" in uy.columns) else None
    tab["estimate_simplified"] = tab["estimate"]; tab["se"] = np.nan; tab["N_switcher_obs"] = np.nan
    ate, ate_se, se_how = ate_simpl, float("nan"), ""
    try:
        e_p, a_p, a_se, p_p = did_multiplegt_dyn_port(uy, effects=int(effects), placebo=int(placebo), cluster_col=_cl)
        for kind_, t_ in (("effect", e_p), ("placebo", p_p)):
            for _, r_ in t_.iterrows():
                m_ = (tab["kind"] == kind_) & (tab["l"] == int(r_["l"]))
                if m_.any():
                    tab.loc[m_, "estimate"] = r_["estimate"]; tab.loc[m_, "se"] = r_["se"]; tab.loc[m_, "N_switcher_obs"] = r_["N_switcher_obs"]
                else:
                    tab = pd.concat([tab, pd.DataFrame([{"kind": kind_, "l": int(r_["l"]), "estimate": r_["estimate"], "se": r_["se"], "N_switcher_obs": r_["N_switcher_obs"]}])], ignore_index=True)
        if abs(a_p - ate_simpl) > 1e-9 * max(1.0, abs(a_p)):
            warn(f"M13: the package's average total effect {a_p:.6g} differs from the simplified per-cell one {ate_simpl:.6g} -- the package's is used")
        ate, ate_se = a_p, a_se
        se_how = ("DIDmultiplegtDYN's analytic SE (its influence functions, cohort-demeaned, with its small-sample factors; ported and checked to "
                  "1e-16 against the package)" + (f", clustered on the {int(pd.Series(uy['site_id']).nunique())} sub-watersheds" if _cl else ", the series as the units"))
    except InsufficientDataError:
        raise
    except Exception as e_:
        warn(f"M13: the package's computation failed ({type(e_).__name__}: {str(e_)[:120]}) -- the simplified estimate, no SE")
    tab.attrs["ate"] = ate; tab.attrs["ate_se"] = ate_se; tab.attrs["se_how"] = se_how; tab.attrs["ate_simplified"] = ate_simpl
    tab.attrs["n_switchers"] = int(np.sum((F < 10**9) & base0)); tab.attrs["n_series"] = int(len(Dm))
    return tab, ate


def logistic_regression_fit(X, y, n_iter=100):
    Xb = np.column_stack([np.ones(len(X)), X])
    beta = np.zeros(Xb.shape[1])
    for _ in range(n_iter):
        p = 1 / (1 + np.exp(-Xb @ beta))
        grad = Xb.T @ (y - p)
        W = p * (1 - p)
        H = -(Xb * W[:, None]).T @ Xb
        beta -= np.linalg.solve(H - 1e-6 * np.eye(len(beta)), grad)
    return beta


def propensity_score_match(X, treat, caliper_sd_mult=0.2, seed=0, order="largest"):
    """1:1 nearest-neighbor, without replacement, on the LOGIT of the propensity score,
    caliper = 0.2*SD(logit(PS)) -- Austin (2011)'s recommended convention. Corrects the
    uploaded file's version, which matched on the RAW propensity score.
    v20.58: the treated units are matched in MatchIt's order (m.order = "largest": the highest propensity first), as R's m14 --
    order="random" keeps v20.57's random order (seeded)."""
    X = (X - X.mean(axis=0)) / X.std(axis=0)
    beta = logistic_regression_fit(X, treat)
    Xb = np.column_stack([np.ones(len(X)), X])
    ps = np.clip(1 / (1 + np.exp(-Xb @ beta)), 1e-6, 1 - 1e-6)
    logit_ps = np.log(ps / (1 - ps))
    caliper = caliper_sd_mult * logit_ps.std(ddof=1)

    treat_idx = np.where(treat == 1)[0]
    ctrl_idx = list(np.where(treat == 0)[0])
    matches = []
    rng = np.random.default_rng(seed)
    _ord = treat_idx[np.argsort(-logit_ps[treat_idx], kind="stable")] if order == "largest" else rng.permutation(treat_idx)
    for ti in _ord:
        if not ctrl_idx:
            break
        dists = np.abs(logit_ps[ctrl_idx] - logit_ps[ti])
        best = np.argmin(dists)
        if dists[best] <= caliper:
            matches.append((ti, ctrl_idx[best]))
            ctrl_idx.pop(best)
    return matches, ps, logit_ps, caliper


def run_psm_did_core(df, y_col, treat_col, post_col, covariate_cols, unit_col):
    # v20.58: the covariates matched on are the PRE-period means (the columns were named "_pre" but averaged every period -- post-period
    # weather is not affected by the works, but a matching variable must be measured before the treatment; R's m14 always did)
    _pre = pd.to_numeric(df[post_col], errors="coerce").values == 0
    _base = df[_pre] if _pre.any() else df
    unit_level = _base.groupby(unit_col).agg(
        **{treat_col: (treat_col, "first")},
        **{f"{c}_pre": (c, "mean") for c in covariate_cols}
    ).reset_index()
    X = unit_level[[f"{c}_pre" for c in covariate_cols]].values
    treat = unit_level[treat_col].values
    if treat.sum() == 0 or (treat == 0).sum() == 0:
        raise InsufficientDataError(
            f"Need at least 1 treated and 1 control unit at the {unit_col} level to match on -- "
            f"got {int(treat.sum())} treated, {int((treat==0).sum())} control. This is a DATA "
            f"COVERAGE gap (check control_zones and whether this outcome's rows even include both "
            f"treat_core values), not a code bug.")
    matches, ps, logit_ps, caliper = propensity_score_match(X, treat)
    if len(matches) == 0:
        raise InsufficientDataError(
            f"No treated unit matched any control within the caliper (caliper={caliper:.4f} on "
            f"logit-propensity-score scale). This means the treated and control groups' pre-"
            f"treatment covariates don't overlap enough for credible matching in this sample -- "
            f"a genuine common-support problem, not a code bug. Consider a wider caliper or more "
            f"covariate-comparable control units.")

    matched_units = set()
    for ti, ci in matches:
        matched_units.add(unit_level.iloc[ti][unit_col])
        matched_units.add(unit_level.iloc[ci][unit_col])
    matched_df = df[df[unit_col].isin(matched_units)]
    d, p, y = matched_df[treat_col].values, matched_df[post_col].values, matched_df[y_col].values
    cells_needed = {"treated-pre": (d==1)&(p==0), "treated-post": (d==1)&(p==1),
                     "control-pre": (d==0)&(p==0), "control-post": (d==0)&(p==1)}
    empty = [name for name, mask in cells_needed.items() if mask.sum() == 0]
    if empty:
        raise InsufficientDataError(
            f"PSM-DID needs all 4 (treat x post) cells populated in the MATCHED sample -- "
            f"missing: {empty}. Matching succeeded ({len(matches)} pairs), but this sample's "
            f"year coverage still leaves at least one required cell empty for those matched "
            f"units -- a DATA COVERAGE gap, not a code bug.")
    did = ((y[(d==1)&(p==1)].mean() - y[(d==1)&(p==0)].mean()) -
           (y[(d==0)&(p==1)].mean() - y[(d==0)&(p==0)].mean()))
    return did, len(matches), matched_units


def psm_did(df, y_col, covariate_cols, treat_col="treat_core", post_col="post", did_col="did_term", pixel_col="pixel_id",
            time_fe_col="time_fe_yearseason", cluster_col="subwshed_id"):
    """v20.58 -- M14 as R's m14 (MatchIt + fixest): each pixel's PRE-period covariate means, the logistic propensity score, 1:1 nearest
    neighbour on its logit without replacement, the highest propensity first (MatchIt's m.order = "largest"), caliper 0.2 SD of the logit
    (Austin 2011; R: distance = "glm", link = "linear.logit", caliper = 0.2) -- then the design's two-way FE DiD (unit and year x season
    effects, cluster-robust SE) on every row of the matched pixels. v20.57's engine averaged the covariates over every period, matched in a
    random order and took the 2 x 2 difference of raw means (0.0505 against R's 0.0512 on the poison test)."""
    cv = [c_ for c_ in covariate_cols if c_ in df.columns]
    if not cv: raise InsufficientDataError("PSM needs covariates to match on (COVARIATES is empty)")
    d = df[np.isfinite(pd.to_numeric(df[y_col], errors="coerce").values)]
    _, npairs, units = run_psm_did_core(d, y_col, treat_col, post_col, cv, pixel_col)
    m = d[d[pixel_col].isin(units)]
    b, se = estimate_twfe_did(m, y_col, did_col, pixel_col, time_fe_col, cluster_col)
    from scipy import stats as _st
    G = int(LAST_FIT_INFO.get("n_clusters") or 0)
    p = float(2 * _st.t.sf(abs(b / se), G - 1)) if G > 1 and np.isfinite(se) and se > 0 else np.nan
    return {"outcome": y_col, "PSM_DID": float(b), "se": float(se), "p_value": p, "n_matched_pairs": int(npairs), "n_matched_pixels": int(len(units)),
            "covariates": ",".join(cv), "se_how": f"the two-way FE DiD on the matched pixels, cluster-robust (CR1){f', {G} clusters' if G else ''}",
            "engine": "engine: logit-PS nearest neighbour (MatchIt's rule) + two-way FE"}


def run_placebo_timing_test(df, y_col, treat_col, unit_col, time_col, true_treatment_year,
                             false_years=None, time_fe_col=None):
    """AUDIT FIX (v5.1): time_col stays NUMERIC (Year) for the < true_treatment_year
    comparison; time_fe_col carries the year x season FE so seasonal variation is absorbed.
    Previously both used Year, leaving season effects unabsorbed."""
    unit_col = _unit_key(df, unit_col)             # v20.29: pixel x season unit when the scenario says so
    if time_fe_col is None:
        time_fe_col = time_col
    if false_years is None:
        _pm = (pd.to_numeric(df["post"], errors="coerce").values == 0) if "post" in df.columns else (df[time_col].values < true_treatment_year)
        available = sorted(int(y) for y in pd.unique(df.loc[_pm, time_col]))
        false_years = available[1:]                               # a fake start needs at least one year before it; v20.58: EVERY such
                                                                  # year, as R's m15_placebo (v20.57 took only the later half: 2 of R's 4)

    results = []
    # v20.57: the placebo sample is each series' OWN pre-period (post == 0). Before, it was Year < ONE treatment year: in a
    # pooled run with per-site (staggered) starts, the earlier cohorts' treated years entered the "pre" sample and the placebo
    # picked up the real effect (known-answer test: +0.016 to +0.025 for a true 0).
    _pre_mask = (pd.to_numeric(df["post"], errors="coerce").values == 0) if "post" in df.columns else (df[time_col].values < true_treatment_year)
    # v20.58 (as R's m15_placebo): the SE of a placebo is the DESIGN's. v20.57 took every ROW as an independent draw (an iid OLS SE: the rows of
    # a year share its shock) and |t| > 1.96 -> false alarms. With the YEARS as the clusters (fewer than MIN_SWS_CLUSTERS sub-watersheds) a
    # placebo's SE is the design-based one: the year-to-year spread of the pre-period treated-minus-control gaps (within each unit, a year's
    # seasons averaged) x sqrt(1/n_before + 1/n_after), t with n - 2 df; with >= MIN_SWS_CLUSTERS sub-watersheds the cluster-robust SE, t(G - 1).
    from scipy import stats as _st
    pre = df[_pre_mask]
    _ns = int(pd.to_numeric(pre["site_id"], errors="coerce").fillna(0).astype(int).pipe(lambda x: x[x > 0]).nunique()) if "site_id" in pre.columns else 0
    yr_cl = _ns < MIN_SWS_CLUSTERS; gy = None
    if yr_cl and len(pre):
        _tr = (pd.to_numeric(pre[treat_col], errors="coerce").values == 1)
        q = pd.DataFrame({"site": pd.to_numeric(pre["site_id"], errors="coerce").fillna(0).astype(int).values if "site_id" in pre.columns else 0,
                          "Year": pre[time_col].values.astype(int), "Season": pre["Season"].values if "Season" in pre.columns else 0,
                          "tr": _tr, "u": pre[unit_col].values, "y": pd.to_numeric(pre[y_col], errors="coerce").values.astype(np.float64)})
        q = q[np.isfinite(q.y.values)]; q["y"] = q["y"] - q.groupby("u")["y"].transform("mean")
        gg = q.groupby(["site", "Year", "Season", "tr"])["y"].mean().unstack("tr")
        if True in gg.columns and False in gg.columns:
            gy = (gg[True] - gg[False]).rename("gap").reset_index().dropna().groupby(["site", "Year"])["gap"].mean().reset_index()
    psi = {}                                                                  # v20.58: each cluster's influence on every placebo
    _ck = None if yr_cl else _cluster_key(pre, "subwshed_id")
    _cl_codes = pd.factorize(pre[_ck].values)[0] if (_ck is not None and _ck in pre.columns) else None
    y_dm = demean_two_way(pd.to_numeric(pre[y_col], errors="coerce").values.astype(np.float64), pre[unit_col].values, pre[time_fe_col].values)
    for fy in false_years:
        d = pre.copy()
        d["post_placebo"] = (d[time_col] >= fy).astype("int8")
        d["did_placebo"] = d[treat_col] * d["post_placebo"]
        if d["did_placebo"].nunique() < 2:
            continue
        x_dm = demean_two_way(d["did_placebo"].values.astype(np.float64), d[unit_col].values, d[time_fe_col].values)
        beta = float(np.linalg.lstsq(x_dm.reshape(-1,1), y_dm, rcond=None)[0][0])
        if _cl_codes is not None:
            _xx = float(np.dot(x_dm, x_dm))
            psi[fy] = np.bincount(_cl_codes, weights=x_dm * (y_dm - beta * x_dm)) / _xx if _xx > 0 else None
        se, p_, how = np.nan, np.nan, ""
        if gy is not None and len(gy) >= 3:
            a_ = gy.loc[gy.Year < fy, "gap"].values; z_ = gy.loc[gy.Year >= fy, "gap"].values; N_ = len(a_) + len(z_)
            if len(a_) and len(z_) and N_ >= 3:
                dev = np.concatenate([a_ - a_.mean(), z_ - z_.mean()]); s2 = float(np.sum(dev ** 2) / max(1, N_ - 2))
                se = float(np.sqrt(s2 * (1 / len(a_) + 1 / len(z_)))); p_ = float(2 * _st.t.sf(abs(beta / se), max(1, N_ - 2))) if se > 0 else np.nan
                how = f"design-based (years as the draws: {len(a_)} before, {len(z_)} from the placebo start), t with {max(1, N_ - 2)} df"
        if not np.isfinite(se):
            b2, se2 = estimate_twfe_did(d, y_col, "did_placebo", unit_col, time_fe_col, "subwshed_id")
            G_ = int(LAST_FIT_INFO.get("n_clusters") or 2); se = float(se2); p_ = float(2 * _st.t.sf(abs(beta / se), max(1, G_ - 1))) if se > 0 else np.nan
            how = f"cluster-robust, clustered by {LAST_CLUSTER_USED.get('value')} ({G_} clusters), t with {max(1, G_ - 1)} df"
        results.append({"false_year": fy, "placebo_beta": beta, "placebo_se": se, "p_value": p_, "se_how": how,
                        "significant": bool(np.isfinite(p_) and p_ < 0.05)})
    out = pd.DataFrame(results)
    if len(out):
        # v20.58 (as R's m15_placebo): the headline is the MEAN placebo effect WITH ITS OWN SE and p -- v20.57 printed the mean effect, the
        # typical SE of ONE placebo and a Bonferroni p of the most significant year in one row (numbers that did not belong together).
        # Design-based (years as the clusters): the mean is a fixed combination of the yearly treated-minus-control gaps -> SE = SD of the
        # gaps x the norm of that combination, t with n - 1 df. Cluster-robust: the placebo years' joint covariance from each cluster's
        # influence on every placebo (CR1), t with G - 1 df. Whether ANY single year looks like an effect: p_any_placebo_bonferroni.
        k = len(out); est = float(out["placebo_beta"].mean()); se_m, df_m, how_m = np.nan, np.nan, ""
        if gy is not None and len(gy) >= 3:
            g = gy["gap"].values.astype(float); Yr = gy["Year"].values; cb = np.zeros(len(g))
            for fy in out["false_year"].values:
                a = Yr < fy; z = Yr >= fy
                if a.any() and z.any(): cb += (z / z.sum() - a / a.sum()) / k
            se_m = float(np.sqrt(np.var(g, ddof=1) * np.sum(cb ** 2))); df_m = len(g) - 1
            how_m = f"design-based: the mean of the {k} placebo effects as a combination of the {len(g)} yearly treated-minus-control gaps (years as the draws)"
        elif psi and all(psi.get(fy) is not None for fy in out["false_year"].values):
            P = np.column_stack([psi[fy] for fy in out["false_year"].values]); G = P.shape[0]; sc = P @ np.full(k, 1.0 / k)
            se_m = float(np.sqrt(np.sum(sc ** 2) * G / max(1, G - 1))); df_m = G - 1
            how_m = f"cluster-robust (CR1) over the {k} placebo years jointly -- their covariance from each of the {G} clusters' influence"
        p_m = float(2 * _st.t.sf(abs(est / se_m), max(1, df_m))) if np.isfinite(se_m) and se_m > 0 else np.nan
        pb = float(min(1.0, k * pd.to_numeric(out["p_value"], errors="coerce").min())) if out["p_value"].notna().any() else np.nan
        out["mean_placebo_beta"] = est; out["mean_placebo_se"] = se_m; out["mean_placebo_p"] = p_m
        out["p_any_placebo_bonferroni"] = pb; out["mean_se_how"] = how_m
        out["mean_p_how"] = (f"t with {int(df_m)} df on the mean placebo effect; p_any_placebo_bonferroni = {pb:.3g} (the smallest of the "
                             f"{k} placebo p-values x {k})") if np.isfinite(df_m) else ""
    return out


def pretrends_joint_ftest(df, y_col, treat_core_col, event_time_col, fe1_col, fe2_col,
                            cluster_col, pre_window=(-4, -2), ref_period=-1, covariates=None):
    """Joint Wald/F test that all pre-treatment leads are zero (H0: beta_k = 0 for every lead k).

    v20.19 -- specification fix. The previous version restricted the sample to the lead years ONLY (-4..-2) and
    then included a dummy for each of them. Inside that sample the lead dummies sum to the treated indicator,
    which is constant within a pixel and absorbed by the pixel fixed effect, so the columns were exactly
    collinear: the covariance had no inverse and numpy raised `LinAlgError: Singular matrix` (it only ran before
    through floating-point noise). The REFERENCE PERIOD (event time -1) is now always in the test sample, so each
    lead is identified as a change relative to it -- the same normalisation as the event study.
    Also handled: leads whose regressor is absorbed (no treated pixel observed at that lead and at the reference,
    or no within-pixel variation) are dropped from the test and reported; with G clusters a cluster-robust
    covariance has rank at most G-1, so the number of restrictions tested is capped at its rank (pseudo-inverse),
    and the small-sample F uses (rank, G-1) degrees of freedom."""
    df, covariates = _expand_categorical_covariates(df, covariates)   # v20.44: land-use CLASSES
    cluster_col = _cluster_key(df, cluster_col)       # v20.38: the sub-watershed is the cluster
    fe1_col = _unit_key(df, fe1_col)             # v20.29: pixel x season unit when the scenario says so
    from scipy import stats as sstats
    lo, hi = pre_window
    et_all = pd.to_numeric(df[event_time_col], errors="coerce").values
    if "post" in df.columns:                                  # v20.58 (as R's m16_pretrends): the PRE rows -- the treated rows at the leads
        _pre = pd.to_numeric(df["post"], errors="coerce").values == 0          # and the reference year, the controls in the same years
        _trv = pd.to_numeric(df[treat_core_col], errors="coerce").fillna(0).values == 1
        _tsel = _pre & _trv & (et_all >= lo) & (et_all <= max(hi, ref_period))
        _yrs = set(pd.to_numeric(df.loc[_tsel, "Year"], errors="coerce").dropna().astype(int).tolist()) if "Year" in df.columns else set()
        _csel = _pre & ~_trv & (pd.to_numeric(df["Year"], errors="coerce").isin(_yrs).values if "Year" in df.columns else True)
        d = df[_tsel | _csel].copy()
    else:
        d = df[(et_all >= lo) & (et_all <= max(hi, ref_period))].copy()
    if len(d) == 0:
        raise InsufficientDataError(
            f"No rows with event_time in [{lo},{max(hi, ref_period)}] -- this sample's years don't reach the "
            f"pre-trends test window relative to the treatment year. A DATA COVERAGE gap, not a code bug: check "
            f"event_time = Year - TREATMENT_YEAR against what years you actually have.")
    et = pd.to_numeric(d[event_time_col], errors="coerce").values
    tr = pd.to_numeric(d[treat_core_col], errors="coerce").fillna(0).values.astype(float)
    if not ((et == ref_period) & (tr == 1)).any():
        raise InsufficientDataError(
            f"the reference period (event time {ref_period}) has no treated rows -- the leads cannot be anchored. "
            f"See C.outcome_coverage('{y_col}') / C.treatment_coverage().")
    keep = _finite_rows(d, y_col, None, None)
    if not keep.all():
        d = d[keep]; et = et[keep]; tr = tr[keep]
    y_dm = demean_two_way(d[y_col].values.astype(float), d[fe1_col].values, d[fe2_col].values)
    sd_y = float(np.std(y_dm)) if len(y_dm) else 0.0
    _frozen_treated_guard(d[y_col].values, d[fe1_col].values, tr == 1, et <= ref_period, y_col)   # v20.21/24: leads + reference
    pix = d[fe1_col].values
    ref_pix = set(pd.unique(pix[(et == ref_period) & (tr == 1)]))
    pre_periods = [k for k in range(lo, hi + 1) if k != ref_period]
    cols, kept, dropped = [], [], {}
    for k in pre_periods:
        m = (et == k) & (tr == 1)
        if not m.any():
            dropped[k] = "no treated rows at this lead"; continue
        n_in_ref = len(set(pd.unique(pix[m])) & ref_pix)
        if n_in_ref == 0:
            dropped[k] = "none of the treated pixels at this lead are observed in the reference period (absorbed)"; continue
        v = demean_two_way((tr * (et == k)).astype(float), d[fe1_col].values, d[fe2_col].values)
        if np.std(v) <= 1e-4 * max(sd_y, 1e-12):
            dropped[k] = "no within-pixel variation after the fixed effects (absorbed)"; continue
        cols.append(v); kept.append(k)
    if not kept:
        raise InsufficientDataError(
            f"none of the leads {pre_periods} is identified on this sample ({dropped}) -- the pre-trends test has "
            f"nothing to test. This is a coverage gap (treated pixels not observed across the pre-period), not a bug.")
    if dropped:
        warn(f"pre-trends test: leads {sorted(dropped)} dropped -- " + "; ".join(f"{k}: {v}" for k, v in dropped.items()))
    q = len(cols)                                                     # v20.32: covariates enter the regression but
    _cv = [c_ for c_ in (covariates or []) if c_ in d.columns]        # are NOT part of the joint restriction
    for c_ in _cv:
        _vc = demean_two_way(pd.to_numeric(d[c_], errors="coerce").astype(float).values, d[fe1_col].values, d[fe2_col].values)
        if float(np.std(_vc)) > 1e-10: cols.append(_vc)
    X = np.column_stack(cols)
    beta_all = np.linalg.lstsq(X, y_dm, rcond=None)[0]
    resid = y_dm - X @ beta_all
    vcov_all, G = cluster_robust_vcov(X, resid, d[cluster_col].values,
                                      k_fe=_k_fe_nonnested([d[fe1_col].values, d[fe2_col].values], pd.factorize(d[cluster_col].values)[0]))   # v20.58
    beta = beta_all[:q]; vcov = vcov_all[:q, :q]
    vcov = 0.5 * (vcov + vcov.T)
    rank = int(np.linalg.matrix_rank(vcov, tol=1e-12 * max(float(np.max(np.abs(vcov))), 1e-300)))
    if rank < q:
        warn(f"pre-trends test: the cluster-robust covariance of {q} lead(s) has rank {rank} "
             f"({G} clusters allow at most {G - 1} restrictions); testing {rank} restriction(s) with a pseudo-inverse")
    if q > G - 1:
        warn(f"pre-trends test: {q} leads but only {G} clusters -- the joint test can have at most {G - 1} degrees of "
             f"freedom; prefer fewer leads (pre_window) or the 1-df linear-trend test")
    # v20.34: with few clusters the cluster-robust covariance of the leads can be NEAR-singular. A pseudo-inverse with a
    # 1e-12 cutoff then divides by an almost-zero variance and the F explodes -- your run gave F = 4748.36 for NDVI,
    # SAVI, EVI, LAI, NDRE and VHI alike and 4090.98 for LSWI, NDMI and VCI: a statistic that does not change with the
    # data measures the covariance geometry, not a pre-trend. Only well-conditioned directions are tested now, and a
    # test resting on an ill-conditioned covariance is reported as INCONCLUSIVE instead of "REJECT".
    if str(cluster_col) == "Year":
        # v20.49: with fewer than MIN_SWS_CLUSTERS sub-watersheds the clusters are YEARS, and every lead is the dummy of
        # ONE year: its cluster scores are zero by construction, so the covariance of the leads is ~1e-30 and the Wald F
        # exploded (1e27-1e29, "REJECT parallel trends") on panels simulated WITHOUT any pre-trend -- 5 of 5 seeds. The
        # well-conditioned-looking matrix passed the v20.34 checks. The test is then the DESIGN-BASED one: the linear
        # trend of the core-minus-control gap over the pre-period years (years as the draws; sub-watershed FE).
        dz = _design_pretrend_test(df, y_col, treat_core_col, event_time_col, ref_period)
        se_lead = float(np.std(beta, ddof=1)) if len(beta) > 1 else float("nan")
        return {"q_leads_tested": q, "leads_tested": kept, "leads_dropped": dropped, "vcov_rank": int(np.linalg.matrix_rank(vcov)) if vcov.size else 0,
                "f_stat": dz["F"], "df1": 1, "df2": dz["df"], "p_value": dz["p"], "n_clusters": int(G),
                "reject_parallel_trends_at_5pct": bool(dz["p"] < 0.05), "test_reliable": bool(np.isfinite(dz["p"])),
                "vcov_condition_number": float("nan"), "method": "design-based linear pre-trend of the core-minus-control gap (years as draws)",
                "slope_per_year": dz["slope"], "slope_se": dz["se"], "pre_years": dz["n_years"], "sub_watersheds": dz["n_sws"],
                "cluster_wald_note": f"not applicable: {G} year clusters, one lead per year -- its cluster covariance is degenerate",
                "verdict": ("REJECT: the core-minus-control gap trends before implementation" if dz["p"] < 0.05 else
                            "no evidence against parallel pre-trends"),
                "lead_coefficients": dict(zip(kept, beta)), "lead_se": {k_: se_lead for k_ in kept},
                "n_obs": int(len(d)), "n_treated_pixels_in_ref": int(len(ref_pix))}
    _w, _U = np.linalg.eigh(vcov)
    _wmax = float(np.max(_w)) if _w.size else 0.0
    _keep = _w > max(1e-7 * _wmax, 1e-300)
    _cond = float(_wmax / np.min(_w[_keep])) if _keep.any() else float("inf")
    _z = _U[:, _keep].T @ beta
    wald_stat = float(np.sum(_z ** 2 / _w[_keep])) if _keep.any() else float("nan")
    rank = int(_keep.sum())
    df1 = max(rank, 1); df2 = max(G - 1, 1)
    f_stat = wald_stat / df1
    _reliable = bool(_keep.any() and rank == q and q <= G - 1 and _cond < 1e6)
    p_value = float(1 - sstats.f.cdf(f_stat, df1, df2))
    se = np.sqrt(np.clip(np.diag(vcov), 0, None))
    return {"q_leads_tested": q, "leads_tested": kept, "leads_dropped": dropped, "vcov_rank": rank,
            "f_stat": f_stat, "df1": df1, "df2": df2, "p_value": p_value, "n_clusters": int(G),
            "reject_parallel_trends_at_5pct": bool(p_value < 0.05) if _reliable else False,
            "test_reliable": _reliable, "vcov_condition_number": _cond,       # v20.34
            "verdict": ("REJECT parallel trends" if (_reliable and p_value < 0.05) else
                        "no evidence against parallel trends" if _reliable else
                        f"INCONCLUSIVE: the cluster covariance of the leads is ill-conditioned ({G} clusters, condition "
                        f"number {_cond:.1e}) -- read the event-study leads (M02) and HonestDiD (M34) instead"),
            "lead_coefficients": dict(zip(kept, beta)), "lead_se": dict(zip(kept, se)),
            "n_obs": int(len(d)), "n_treated_pixels_in_ref": int(len(ref_pix))}

def _design_pretrend_test(df, y_col, treat_col, event_time_col, ref_period=-1):
    """v20.49: slope of the yearly core-minus-control gap over the pre-period (event time <= ref), with a fixed effect
    per sub-watershed when there are several; t with its residual degrees of freedom. {F = t^2, p, slope, se, df}."""
    from scipy import stats as _st
    et = pd.to_numeric(df[event_time_col], errors="coerce"); y = pd.to_numeric(df[y_col], errors="coerce")
    # v20.58 (as R's m16_pretrends): the design's PRE rows (post == 0 -- each series' own untreated years, the rings' of their season too);
    # event time <= -1 left out the control rows whose event time the other seasons' start sets (3.83128 against R's 3.83122)
    m = ((pd.to_numeric(df["post"], errors="coerce") == 0) if "post" in df.columns else (et <= ref_period)) & np.isfinite(y)
    site = df["site_id"] if "site_id" in df.columns else pd.Series(1, index=df.index)
    g = pd.DataFrame({"s": site[m].values, "yr": pd.to_numeric(df.loc[m, "Year"], errors="coerce").values,
                      "t": pd.to_numeric(df.loc[m, treat_col], errors="coerce").values, "y": y[m].values})
    w = g.groupby(["s", "yr", "t"])["y"].mean().unstack("t")
    if 0 not in w.columns or 1 not in w.columns:
        raise InsufficientDataError("the pre-period has no year with both core and control pixels -- no pre-trend test")
    gap = (w[1] - w[0]).dropna().reset_index(); gap.columns = ["s", "yr", "gap"]
    S = gap["s"].nunique(); X = [np.ones(len(gap)), gap["yr"].values.astype(float)]
    for s_ in sorted(gap["s"].unique())[1:]: X.append((gap["s"].values == s_).astype(float))
    X = np.column_stack(X); dfree = len(gap) - X.shape[1]
    if dfree < 1:
        raise InsufficientDataError(f"the pre-trend test needs >= 3 pre-period years per sub-watershed (have {len(gap)} gap(s) for {S})")
    b, *_ = np.linalg.lstsq(X, gap["gap"].values, rcond=None); e = gap["gap"].values - X @ b
    se = float(np.sqrt((e @ e) / dfree * np.linalg.inv(X.T @ X)[1, 1])); t = float(b[1] / se) if se > 0 else float("nan")
    return {"F": t * t, "p": float(2 * _st.t.sf(abs(t), dfree)) if np.isfinite(t) else float("nan"), "slope": float(b[1]), "se": se,
            "df": int(dfree), "n_years": int(gap["yr"].nunique()), "n_sws": int(S)}

def goodman_bacon_diagnostic(df, y_col, d_col, unit_col, time_col, cohort_col):
    """Pairwise 2x2 comparisons + forbidden-comparison flagging, with an approximate
    observation-count weight -- NOT the exact GB(2021) analytical weight (see Module 22's
    honesty note: two attempts at the exact formula both failed reconstitution testing)."""
    unit_col = _unit_key(df, unit_col)             # v20.29: pixel x season unit when the scenario says so
    if "Season" in df.columns and df["Season"].nunique() > 1 and time_col == "Year":    # v20.58: season-matched (as R's M22)
        df = df.copy(); df["_y_sn"] = season_net(df, y_col); y_col = "_y_sn"
    groups = df[cohort_col].unique()
    Dbar_g = df.groupby(cohort_col)[d_col].mean()
    n_obs_g = df.groupby(cohort_col).size()
    rows = []
    for k, l in combinations(sorted(groups, key=lambda x: (x == np.inf, x)), 2):
        sub = df[df[cohort_col].isin([k, l])]
        beta_kl, _ = estimate_twfe_did(sub, y_col, d_col, unit_col, time_col, unit_col)
        Dk, Dl = Dbar_g[k], Dbar_g[l]
        comparison_type = ("treated_vs_never" if (k == np.inf or l == np.inf) else
                            "forbidden_later_vs_earlier" if (Dk - Dl) * (1 - Dk - Dl) < 0 else
                            "clean_earlier_vs_later")
        rows.append({"group_k": k, "group_l": l, "beta_2x2": beta_kl,
                     "approx_weight_by_n_obs": n_obs_g[k] + n_obs_g[l],
                     "comparison_type": comparison_type})
    table = pd.DataFrame(rows)
    table["approx_weight_by_n_obs"] = table["approx_weight_by_n_obs"] / table["approx_weight_by_n_obs"].sum()
    return table


# ====================== v20.58: THE GOODMAN-BACON DECOMPOSITION, EXACT (M22 -- the same units and numbers as R's m22_bacon) ======================
# v20.57's engine (goodman_bacon_diagnostic, kept) weighted each 2 x 2 by its OBSERVATION COUNT ("approximate": the exact formula had failed
# its reconstitution test) on pixel units, so its weighted mean was not the two-way FE it decomposes (0.0509 against R's 0.0508 on the
# poison test). Now: R's units (series of ONE season: sub-watershed x ring x season, net of the control rings' mean in the same
# sub-watershed, season and year), Goodman-Bacon's (2021) exact weights, and a PROOF on every run -- the weights add up to 1 and the
# weighted 2 x 2s to the two-way FE, or the model stops (no approximate number is ever reported as the decomposition).
def bacon_series(df, y_col, d_col="did_term"):
    """R's m22_bacon series: one row per (series, Year) -- unit = sub-watershed x ring x season (x its first treated Year), y = the mean of
    the outcome, net of the CONTROL series' mean in the same sub-watershed, season and Year; D = 1 when the series is treated that Year;
    the balanced panel (series present in every Year). Returns (frame unit, site_id, Season, Year, y, D; n series dropped as unbalanced)."""
    tc = "treatment" if "treatment" in df.columns else ("treat" if "treat" in df.columns else None)
    y = pd.to_numeric(df[y_col], errors="coerce").values.astype(np.float64)
    d = pd.DataFrame({"site_id": pd.to_numeric(df["site_id"], errors="coerce").fillna(0).astype(np.int64).values if "site_id" in df.columns else 0,
                      "buff_km": pd.to_numeric(df["buff_km"], errors="coerce").values,
                      "Season": pd.to_numeric(df["Season"], errors="coerce").fillna(0).astype(np.int64).values if "Season" in df.columns else 0,
                      "Year": pd.to_numeric(df["Year"], errors="coerce").astype(np.int64).values, "y": y,
                      "D": (pd.to_numeric(df[d_col], errors="coerce").values == 1).astype(np.int64),
                      "ctl": (pd.to_numeric(df[tc], errors="coerce").values == 0) if tc else (pd.to_numeric(df["buff_km"], errors="coerce").values != TREAT_CORE_BUFFKM)})
    d = d[np.isfinite(d["y"].values)]
    if not len(d): raise InsufficientDataError("no finite outcome for the Goodman-Bacon series")
    first = d[d.D == 1].groupby(["site_id", "buff_km", "Season"])["Year"].min()
    key = pd.MultiIndex.from_frame(d[["site_id", "buff_km", "Season"]])
    d["cohort"] = first.reindex(key).astype(float).fillna(np.inf).values
    g = d.groupby(["site_id", "buff_km", "Season", "cohort", "Year", "ctl"], as_index=False).agg(y=("y", "mean"), D=("D", "max"))
    cm = g[g["ctl"]].groupby(["site_id", "Season", "Year"])["y"].mean().rename("_cm").reset_index()
    g = g.merge(cm, on=["site_id", "Season", "Year"], how="left"); g["y"] = g["y"] - g["_cm"]
    g = g[np.isfinite(g["y"].values)]
    g["unit"] = (g["site_id"].astype(str) + "_" + g["buff_km"].astype(str) + "_" + g["Season"].astype(str) + "_" + g["cohort"].astype(str))
    ny = g["Year"].nunique(); nn = g.groupby("unit")["Year"].nunique(); keep = nn.index[nn == ny]
    out = g[g["unit"].isin(keep)][["unit", "site_id", "Season", "Year", "y", "D"]].reset_index(drop=True)
    return out, int((nn != ny).sum())

def goodman_bacon_exact(uy, y="y", d="D", unit="unit", time="Year"):
    """Goodman-Bacon (2021) on a BALANCED panel with staggered (absorbing) adoption: every 2 x 2 comparison, its estimate and its EXACT
    weight (eqs. 10a-10c). Returns (table: type, group_k, group_l, estimate, weight, comparison_type; the two-way FE beta). The weights add
    up to 1 and the weighted estimates to the two-way FE -- checked here (to 1e-9), never assumed."""
    P = uy.pivot(index=unit, columns=time, values=y).sort_index(axis=1); Dm = uy.pivot(index=unit, columns=time, values=d).reindex_like(P)
    if P.isna().any().any() or Dm.isna().any().any(): raise InsufficientDataError("Goodman-Bacon needs a balanced panel (every series in every year)")
    Y = P.values.astype(np.float64); D = Dm.values.astype(np.float64); times = np.asarray(P.columns); N, T = Y.shape
    if (np.diff(D, axis=1) < 0).any(): raise InsufficientDataError("the treatment switches OFF in some series: the decomposition needs staggered adoption")
    gi = np.array([times[np.argmax(r > 0)] if (r > 0).any() else np.inf for r in D], dtype=float)   # each series' first treated year
    Dt = D - D.mean(axis=1, keepdims=True) - D.mean(axis=0, keepdims=True) + D.mean()
    Yt = Y - Y.mean(axis=1, keepdims=True) - Y.mean(axis=0, keepdims=True) + Y.mean()
    VD = float((Dt ** 2).sum()) / (N * T)
    if not VD > 0: raise InsufficientDataError("no treatment variation left after the two-way fixed effects")
    beta = float((Dt * Yt).sum() / (Dt ** 2).sum())
    groups = sorted(set(gi.tolist()), key=lambda g: (g == np.inf, g))
    n = {g: float((gi == g).sum()) / N for g in groups}
    Db = {g: float(D[gi == g].mean()) for g in groups}                       # the share of years each group is treated
    ym = lambda g, m: float(Y[np.ix_(gi == g, m)].mean())
    def did(tg, cg, pre, post):                                             # the 2 x 2: group tg against cg, window masks pre / post
        if not pre.any() or not post.any(): return np.nan
        return (ym(tg, post) - ym(tg, pre)) - (ym(cg, post) - ym(cg, pre))
    rows = []
    for i_, k in enumerate(groups):
        for l in groups[i_ + 1:]:
            nk, nl = n[k], n[l]; nkl = nk / (nk + nl)
            if l == np.inf:                                                 # treated (k) vs never treated
                w = (nk + nl) ** 2 * nkl * (1 - nkl) * Db[k] * (1 - Db[k]) / VD
                rows.append(("Treated vs Untreated", k, l, did(k, l, times < k, times >= k), w, "treated_vs_never"))
                continue
            # k earlier, l later: k against the not-yet-treated l (years before l), then l against the already-treated k (years from k)
            wk = ((nk + nl) * (1 - Db[l])) ** 2 * nkl * (1 - nkl) * ((Db[k] - Db[l]) / (1 - Db[l])) * ((1 - Db[k]) / (1 - Db[l])) / VD if Db[l] < 1 else 0.0
            wl = ((nk + nl) * Db[k]) ** 2 * nkl * (1 - nkl) * (Db[l] / Db[k]) * ((Db[k] - Db[l]) / Db[k]) / VD if Db[k] > 0 else 0.0
            win_k = times < l; win_l = times >= k
            always = Db[k] >= 1.0
            if not always:
                rows.append(("Earlier vs Later Treated", k, l, did(k, l, win_k & (times < k), win_k & (times >= k)), wk, "clean_earlier_vs_later"))
            rows.append(("Later vs Always Treated" if always else "Later vs Earlier Treated", l, k,
                         did(l, k, win_l & (times < l), win_l & (times >= l)), wl, "forbidden_later_vs_earlier"))
    t = pd.DataFrame(rows, columns=["type", "group_k", "group_l", "estimate", "weight", "comparison_type"])
    t = t[(t["weight"] > 0) | t["estimate"].notna()].reset_index(drop=True)
    sw = float(t["weight"].sum()); rec = float(np.nansum(t["estimate"] * t["weight"]))
    if abs(sw - 1.0) > 1e-9 or abs(rec - beta) > 1e-9 * max(1.0, abs(beta)):
        raise InsufficientDataError(f"the Goodman-Bacon weights do not reconstitute the two-way FE (weights sum {sw:.12f}, weighted 2 x 2s {rec:.10g} "
                                    f"vs the two-way FE {beta:.10g}) -- no decomposition is reported")
    t["beta_2x2"] = t["estimate"]                                           # the v20.57 column names, kept
    return t, beta

def bacon_twfe_inference(uy, y="y", d="D", unit="unit", time="Year"):
    """The two-way FE the decomposition adds up to (unit + Year effects on the balanced series) with its CR1 SE -- clustered by
    sub-watershed with >= MIN_SWS_CLUSTERS of them, else by Year (as every model); fixest's small-sample factor (the non-nested fixed
    effects counted) and a t with G - 1 df: the numbers of R's feols(y ~ D | unit + Year, cluster = ...) in m22_bacon."""
    from scipy import stats as _st
    P = uy.pivot(index=unit, columns=time, values=y).sort_index(axis=1); Dm = uy.pivot(index=unit, columns=time, values=d).reindex_like(P)
    Y = P.values.astype(np.float64); D = Dm.values.astype(np.float64); N, T = Y.shape
    Dt = D - D.mean(axis=1, keepdims=True) - D.mean(axis=0, keepdims=True) + D.mean()
    Yt = Y - Y.mean(axis=1, keepdims=True) - Y.mean(axis=0, keepdims=True) + Y.mean()
    b = float((Dt * Yt).sum() / (Dt ** 2).sum()); e = (Yt - b * Dt).ravel(); x = Dt.ravel()
    site = uy.drop_duplicates(unit).set_index(unit).reindex(P.index)["site_id"].values if "site_id" in uy.columns else np.zeros(N)
    n_sws = int(len({int(s_) for s_ in site if int(s_) > 0}))
    by_site = n_sws >= MIN_SWS_CLUSTERS
    cl = np.repeat(site, T) if by_site else np.tile(np.asarray(P.columns), N)
    uc = np.repeat(np.arange(N), T); tcodes = np.tile(np.arange(T), N)
    cl_codes = pd.factorize(cl)[0]; G = int(cl_codes.max()) + 1
    if G < 2: raise InsufficientDataError("fewer than 2 clusters for the two-way FE's SE")
    k_fe = _k_fe_nonnested([uc, tcodes], cl_codes)
    sc = np.bincount(cl_codes, weights=x * e, minlength=G)
    nobs = N * T; se = float(np.sqrt((G / (G - 1)) * ((nobs - 1) / max(1, nobs - 1 - k_fe)) * float((sc ** 2).sum())) / float((x ** 2).sum()))
    p = float(2 * _st.t.sf(abs(b / se), G - 1)) if se > 0 else np.nan
    how = (f"the two-way FE the decomposition adds up to ({N} series x {T} years), cluster-robust (CR1) by "
           + (f"sub-watershed ({G} clusters)" if by_site else f"year ({G} clusters)") + f"; p: t with {G - 1} df")
    return {"twfe_beta": b, "se": se, "p_value": p, "n_clusters": G, "cluster": "sub-watershed" if by_site else "year", "se_how": how}


WEBB_WEIGHTS = np.array([-np.sqrt(1.5), -1.0, -np.sqrt(0.5), np.sqrt(0.5), 1.0, np.sqrt(1.5)])   # Webb (2014) six-point

def _wb_one_rep(seed_b, y_restricted_fitted, resid_restricted, X, cl_codes, n_cl, null_beta, weights="rademacher"):
    rng = np.random.default_rng(seed_b)
    # v20.23: with G < 12 clusters Rademacher weights give only 2^G distinct bootstrap samples (64 with G = 6, 128
    # with G = 7), so the p-value cannot resolve below ~1/2^G; Webb's six-point distribution fixes that.
    w = (rng.choice(WEBB_WEIGHTS, size=n_cl) if weights == "webb" else rng.choice([-1.0, 1.0], size=n_cl))[cl_codes]
    y_star = y_restricted_fitted + w * resid_restricted
    beta_star = float(np.linalg.lstsq(X, y_star, rcond=None)[0][0])
    resid_star = y_star - X.flatten() * beta_star
    se_star = np.sqrt(np.diag(cluster_robust_se(X, resid_star, cl_codes)))[0]
    return (beta_star - null_beta) / se_star if se_star > 0 else 0.0

def wild_cluster_bootstrap_pvalue(df, y_col, d_col, fe1_col, fe2_col, cluster_col,
                                    n_boot=9999, seed=0, null_beta=0.0, n_jobs=None, weights="auto", covariates=None):
    """WCR wild cluster bootstrap-t (Cameron, Gelbach & Miller 2008) on the TWFE DiD.
    v20.58 -- (1) the SAME regression as M01: the design's covariates partialled out (Frisch-Waugh, after the two-way demeaning), as R's
    m23_wild; v20.57 Python left them out, so its beta was M25's (0.0506846) and not the headline's (0.0506966) whose p-value M23 reports.
    (2) Every replicate EXACTLY from per-cluster sums: with x the demeaned treatment and y the demeaned outcome, a replicate's
    per-cluster score is null*Q_g + w_g*(S_g - null*Q_g) - beta* x Q_g (S_g = sum x*y, Q_g = sum x^2 in cluster g) -- O(clusters) per
    replicate instead of O(rows): 9,999 replicates on any panel in milliseconds (the replicate-by-replicate loop needed one pass over
    every row per replicate). The SE is CR1 with sqrt(G / (G - 1)) (the observed and the bootstrap t alike); weights: Webb (six-point)
    with fewer than 12 clusters, Rademacher otherwise -- the same rule in R."""
    cluster_col = _cluster_key(df, cluster_col)       # v20.38: the sub-watershed is the cluster
    fe1_col = _unit_key(df, fe1_col)                  # v20.29: pixel x season unit when the scenario says so
    df, covariates = _expand_categorical_covariates(df, list(covariates) if covariates else None)
    covariates = [c for c in (covariates or []) if c in df.columns]
    keep = _finite_rows(df, y_col, d_col, covariates)
    if not keep.all(): df = df[keep]
    f1 = df[fe1_col].values; f2 = df[fe2_col].values
    y_dm = demean_two_way(pd.to_numeric(df[y_col], errors="coerce").values.astype(np.float64), f1, f2)
    x = demean_two_way(pd.to_numeric(df[d_col], errors="coerce").values.astype(np.float64), f1, f2)
    if covariates:                                    # Frisch-Waugh: the demeaned covariates partialled out of y and the treatment
        W = np.column_stack([demean_two_way(pd.to_numeric(df[c], errors="coerce").values.astype(np.float64), f1, f2) for c in covariates])
        y_dm = y_dm - W @ np.linalg.lstsq(W, y_dm, rcond=None)[0]
        x = x - W @ np.linalg.lstsq(W, x, rcond=None)[0]
    xx = float(x @ x)
    if not xx > 0: raise InsufficientDataError("the treatment term has no variation left after the fixed effects and covariates")
    beta_hat = float(x @ y_dm) / xx
    cl_codes, cl_uniq = pd.factorize(df[cluster_col].values); n_cl = len(cl_uniq)
    if n_cl < 2:
        raise InsufficientDataError("Wild cluster bootstrap needs at least 2 clusters.")
    S = np.bincount(cl_codes, weights=x * y_dm, minlength=n_cl); Qg = np.bincount(cl_codes, weights=x * x, minlength=n_cl)
    adj = np.sqrt(n_cl / (n_cl - 1.0))
    se_hat = float(np.sqrt(np.sum((S - beta_hat * Qg) ** 2)) / xx * adj)
    if se_hat == 0:
        raise InsufficientDataError("Zero cluster-robust SE -- degenerate design.")
    t_observed = (beta_hat - null_beta) / se_hat
    if weights == "auto": weights = "webb" if n_cl < 12 else "rademacher"          # v20.23
    info(f"wild cluster bootstrap: {n_cl} clusters, {weights} weights, {n_boot:,} replicates (exact per-cluster sums)"
         + (" (Webb: Rademacher would allow only %d distinct samples)" % (2 ** n_cl) if weights == "webb" else ""))
    rng = np.random.default_rng(seed); Sr = S - null_beta * Qg; t_boot = np.empty(int(n_boot)); done = 0
    blk = max(1, min(int(n_boot), int(2e7 // max(n_cl, 1))))                         # the draws in blocks (G x block numbers)
    while done < n_boot:
        k = min(blk, int(n_boot) - done)
        Wd = rng.choice(WEBB_WEIGHTS, size=(n_cl, k)) if weights == "webb" else rng.choice(np.array([-1.0, 1.0]), size=(n_cl, k))
        Sb = null_beta * Qg[:, None] + Sr[:, None] * Wd
        bb = Sb.sum(axis=0) / xx
        sb = np.sqrt(np.sum((Sb - Qg[:, None] * bb[None, :]) ** 2, axis=0)) / xx * adj
        t_boot[done:done + k] = np.where(sb > 0, (bb - null_beta) / np.where(sb > 0, sb, 1.0), 0.0); done += k
    p_value = float((1 + np.sum(np.abs(t_boot) >= np.abs(t_observed))) / (1 + len(t_boot)))   # v20.58: a bootstrap p is never 0 (it was
    LAST_ENGINE["wild_bootstrap"] = "engine"                                                   #   printed "< 1e-300": wrong, it is < 1/(B+1))
    if _use_prebuilt("wild_bootstrap"):                                                # v20.29: verified pyfixest
        # v20.57 (found when a known-answer run was killed for memory): pyfixest's wildboottest expands the ABSORBED fixed effects
        # into dense dummies -- measured ~4 x rows x levels x 8 B (1.3 GB for 20,000 rows and 2,000 units; your panel: millions of
        # pixel x season units -> far beyond any RAM, the kernel is killed). The package is used first whenever that fits below
        # YOUR 98 % rule; otherwise the engine's exact bootstrap above is the result.
        _nlev = int(pd.Series(df[fe1_col].values).nunique()) + int(pd.Series(df[fe2_col].values).nunique())
        _need = float(len(df)) * (_nlev + len(covariates)) * 8.0 * 4.0
        try:
            import _hardware as _Hw; _bud = _Hw.ram_budget_bytes()
        except Exception:
            _bud = None
        if _bud is not None and _need > _bud:
            LAST_ENGINE["wild_bootstrap"] = (f"engine (pyfixest's wildboottest would expand {_nlev:,} fixed-effect levels into dense dummies: "
                                             f"~{_need / 2**30:.1f} GB, {_bud / 2**30:.1f} GB left below 98 % of the RAM)")
            info(f"wild bootstrap: {LAST_ENGINE['wild_bootstrap']} -- the engine's exact bootstrap is the result")
        else:
            _p = _route_call("wild_bootstrap", _pf_wild_bootstrap, df, y_col, d_col, fe1_col, fe2_col, cluster_col, n_boot, seed, weights, covariates)
            if _p is not None: p_value = max(float(_p), 1.0 / (1 + n_boot))                  # v20.58: never below 1 / (B + 1)
    return {"beta": beta_hat, "se_cluster_robust": se_hat, "t_observed": t_observed, "weights": weights,
            "p_value_wild_bootstrap": p_value, "n_clusters": n_cl, "n_boot": int(n_boot), "covariates": ",".join(covariates),
            "n_rows": int(len(df)), "engine": LAST_ENGINE["wild_bootstrap"]}


def _pf_ring_gradient(d, y_col, dcols, fe1, fe2, cl):
    """v20.58 (fifth pass): M24's ONE fit in pyfixest -- every ring x post dummy together (R: fixest i(ring, post, ref = farthest))."""
    import pyfixest as pf
    data = _pf_frame(d, [y_col, fe1, fe2, cl] + list(dcols), codes=(fe1, fe2, cl))
    fit = _pf_quiet(pf.feols, f"{y_col} ~ {' + '.join(dcols)} | {fe1} + {fe2}", data=data, vcov={"CRV1": cl})
    co, se = fit.coef(), fit.se()
    return {c: (float(co[c]), float(se[c])) for c in dcols if c in co.index}

def _ring_gradient_engine(d, y_col, dcols, fe1, fe2, cl):
    """v20.58 (fifth pass): the same ONE fit in the engine -- the dummies demeaned by both fixed effects together, OLS, the CR1 cluster-robust
    covariance with fixest's small-sample factor (the fixed effects not nested in the clusters counted, as estimate_twfe_did)."""
    f1 = pd.factorize(d[fe1].values)[0]; f2 = pd.factorize(d[fe2].values)[0]
    Y = np.column_stack([pd.to_numeric(d[y_col], errors="coerce").values.astype(np.float64)] + [d[c].values.astype(np.float64) for c in dcols])
    M = demean_columns(Y, f1, f2)
    keep = [j for j in range(len(dcols)) if np.std(M[:, 1 + j]) > ABSORBED_REL_TOL * max(float(np.std(Y[:, 1 + j])), 1e-300)]
    if not keep: raise InsufficientDataError("no ring x post term varies within the series and periods")
    names = [dcols[j] for j in keep]; X = M[:, [1 + j for j in keep]]; yd = M[:, 0]
    beta, Ginv = _solve_normal(X.T @ X, X.T @ yd, names)
    e = yd - X @ beta
    clc = pd.factorize(pd.Series(np.asarray(d[cl].values)), sort=False)[0]; G = int(clc.max()) + 1
    if G < 2: raise InsufficientDataError("Only 1 distinct cluster -- cluster-robust SEs are undefined")
    kfe = _k_fe_nonnested([f1, f2], clc); n, k = X.shape
    S = np.column_stack([np.bincount(clc, weights=X[:, j] * e, minlength=G) for j in range(k)])
    V = Ginv @ (S.T @ S) @ Ginv * (G / (G - 1)) * ((n - 1) / max(1, n - k - kfe))
    return {nm: (float(b_), float(s_)) for nm, b_, s_ in zip(names, beta, np.sqrt(np.diag(V)))}

def spillover_gradient_test(df, y_col, post_col, buffkm_col, unit_col, time_col,
                             ring_values=(1,2,3,4,5), cluster_col="subwshed_id"):
    """Each inner ring against the farthest ring, before vs after the start. v20.57 (false positives): the SE is clustered as
    every other model (the sub-watershed, or the years with fewer than 6 -- v20.56 clustered on the PIXEL, so a shared ring
    shock looked like thousands of independent draws), and t / p are reported so spillover is claimed only when significant.
    v20.58 (fifth pass, found by the parity run with cloud gaps): ONE regression, as R's m24 (fixest: y ~ i(ring, post, ref = farthest) |
    unit + period) -- every ring of the design's sample (the core too) interacted with post against the farthest ring present, the unit
    and period effects estimated on all of them. v20.57's fits ring by ring (each ring with the farthest one only) are the same numbers on
    balanced series only: with gaps the period effects differ (0.000158 against R's 0.000152 on the parity panel). The table lists the
    control rings (the core's own row is the treatment effect against the farthest ring, not a spillover)."""
    unit_col = _unit_key(df, unit_col)             # v20.29: pixel x season unit when the scenario says so
    rv = sorted(int(x) for x in ring_values)
    bk_all = pd.to_numeric(df[buffkm_col], errors="coerce").values
    d = df[np.isin(bk_all, [0] + rv)]
    d = d[np.isfinite(pd.to_numeric(d[y_col], errors="coerce").values.astype(np.float64))].copy()
    bk = pd.to_numeric(d[buffkm_col], errors="coerce").values.astype(int)
    present = sorted(set(bk.tolist())); ctrl = [r for r in present if r in rv]
    if len(ctrl) < 2:
        raise InsufficientDataError(f"Need at least 2 distinct buffer rings among {tuple(rv)} present in this data.")
    far = max(present)                                                           # R: max(d$buff_km) -- the farthest ring PRESENT
    post = pd.to_numeric(d[post_col], errors="coerce").fillna(0).values.astype(np.float64)
    dcols = []
    for r in present:
        if r == far: continue
        nm = f"ring{r}_x_post"; d[nm] = (bk == r).astype(np.float64) * post; dcols.append(nm)
    cl_col = _cluster_key(d, cluster_col)
    res = None
    if _use_prebuilt("twfe"):
        res = _route_call("twfe", _pf_ring_gradient, d, y_col, dcols, unit_col, time_col, cl_col)
    if not res:
        LAST_ENGINE["twfe"] = "engine"; res = _ring_gradient_engine(d, y_col, dcols, unit_col, time_col, cl_col)
    G_ = int(pd.Series(d[cl_col]).nunique()); dfp = max(1, G_ - 1)                  # v20.58: t with G - 1 df (was the normal: 6 year
    from scipy import stats as _st                                                #   clusters gave false spillover alarms)
    results = []
    for ring in ctrl:
        if ring == far or f"ring{ring}_x_post" not in res: continue
        beta, se = res[f"ring{ring}_x_post"]
        t_ = beta / se if se else float("nan")
        p_ = float(2 * _st.t.sf(abs(t_), dfp)) if np.isfinite(t_) else float("nan")
        results.append({"ring_km": ring, "vs_reference_km": far, "gradient_effect": beta, "se": se, "t": t_, "p_value": p_, "df": dfp,
                        "n_clusters": G_, "cluster_used": LAST_CLUSTER_USED.get("value"), "significant_5pct": bool(np.isfinite(p_) and p_ < 0.05)})
    if not results:
        raise InsufficientDataError("No ring pair had enough data to compare against the reference ring.")
    LAST_FIT_INFO.clear()
    LAST_FIT_INFO.update({"n_obs": int(len(d)), "n_clusters": G_, "engine": LAST_ENGINE.get("twfe", "engine"), "_beta": float(results[0]["gradient_effect"])})
    return pd.DataFrame(results)


def _perm_one(seed_p, df, y_col, post_col, unit_col, time_col, units, n_treated):
    rng = np.random.default_rng(seed_p)
    fake = set(rng.choice(units, size=n_treated, replace=False))
    d = df[[y_col, post_col, unit_col, time_col]].copy()
    d["fake_did"] = d[unit_col].isin(fake).astype(int) * d[post_col]
    b, _ = estimate_twfe_did(d, y_col, "fake_did", unit_col, time_col, unit_col)
    return b

def permutation_inference(df, *a, n_jobs=None, **kw):
    """v20.50: randomisation inference with the PRE-BUILT PACKAGE first again, as every other model. v20.45 had forced the
    engine path here because a kernel was reported to crash -- it did not crash (its status only showed "Unknown" while
    busy), so that restriction is reverted, and the memory allowance for the parallel workers is doubled (the whole
    budget below the 98 % ceiling instead of half of it). The package setting is left exactly as it was."""
    global PREBUILT_MODE
    saved = PREBUILT_MODE
    try:
        try:
            import _hardware as _Hp
            _bud = _Hp.ram_budget_bytes(); _per = float(len(df)) * 8 * 10          # None (no psutil) = no limit
            n_jobs = max(1, int(n_jobs or os.cpu_count() or 1))                   # v20.52: every core -- v20.53: fewer ONLY if
            if _bud is not None: n_jobs = max(1, min(n_jobs, int(_bud // max(_per, 1))))   # they would not fit below 98 % RAM
        except Exception:
            pass
        return _permutation_inference_impl(df, *a, n_jobs=n_jobs, **kw)
    finally:
        PREBUILT_MODE = saved

def _permutation_inference_impl(df, y_col, treat_col, post_col, unit_col, time_col,
                            n_permutations=999, seed=12345, n_jobs=None):
    """Fisher randomisation inference -- v20.58 (second pass) as R's m25_ritest, the SAME null distribution: the treated status permuted
    across the DESIGN'S UNITS (the pixel x season series under UNIT_FE = "pixel_season"; until now this engine permuted whole PIXELS --
    every season of a pixel together -- while its fit's unit was the series: a permutation SD 57 % above R's on the parity panel), the
    number of treated units kept, the DiD refitted with the same unit and period effects (Frisch-Waugh: the outcome demeaned once, the
    permuted did columns demeaned in batches that fit below 98 % of the RAM, as R); the draws are R's own (Mersenne-Twister after
    set.seed(12345), sample.int(units, treated units) per permutation, the units in (pixel, season) order -- R's route takes the same
    order), so the permuted estimates, their SD and the p-value are R's. p = (1 + #{|b_perm| >= |b|}) / (1 + reps): never 0."""
    df = df.copy()
    df["did_term"] = pd.to_numeric(df[treat_col], errors="coerce") * pd.to_numeric(df[post_col], errors="coerce")
    beta_actual, _ = estimate_twfe_did(df, y_col, "did_term", unit_col, time_col, unit_col)
    uk = _unit_key(df, unit_col)
    d = df[_finite_rows(df, y_col, "did_term", None)]
    oc = [c for c in ("pixel_id", "Season") if c in d.columns]
    units = (d.sort_values(oc, kind="mergesort") if oc else d)[uk].drop_duplicates().to_numpy()
    n1 = int(pd.Series(d.loc[pd.to_numeric(d[treat_col], errors="coerce").values == 1, uk]).nunique())
    if n1 == 0 or n1 == len(units):
        raise InsufficientDataError("Need at least 1 treated AND 1 control unit for permutation inference.")
    ui = pd.Index(units).get_indexer(d[uk].to_numpy())
    post = pd.to_numeric(d[post_col], errors="coerce").to_numpy(np.float64)
    f1 = pd.factorize(d[uk].to_numpy())[0]; f2 = pd.factorize(d[time_col].to_numpy())[0]
    yd = demean_columns(pd.to_numeric(d[y_col], errors="coerce").to_numpy(np.float64).reshape(-1, 1), f1, f2)[:, 0]
    n = len(d); reps = int(n_permutations)
    try:                                                               # YOUR 98 % RULE: every permutation at once when the n x reps
        import _hardware as _Hp                                        #   matrices fit, else the largest batch that fits. v20.58: SIX
        _bud = _Hp.ram_budget_bytes()                                  #   n-vectors per permutation (the permuted column, its demeaned
        k = reps if _bud is None else max(1, min(reps, int(_bud // max(48.0 * n, 1.0))))   # copy, the demeaning's working copy and gather,
    except Exception:                                                  #   a product; peak 4, 2 of margin) -- v20.57 counted 3 while the
        k = reps                                                       #   peak was 5: a chain run was killed for memory (the OOM killer)
    if k < reps: info(f"M25: {reps} permutations in batches of {k} (all at once would pass 98 % of the RAM)")
    rr = _RRandom(12345); placebo = []
    with resampling_scope():                               # v20.58: the permuted fits leave the actual fit's diagnostics alone
        for s0 in range(0, reps, k):
            kk = min(k, reps - s0); M = np.empty((n, kk))
            for i in range(kk):
                t_ = np.zeros(len(units)); t_[np.asarray(rr.sample_int(len(units), n1)) - 1] = 1.0
                M[:, i] = t_[ui] * post
            Md = demean_columns(M, f1, f2); del M
            placebo.extend(((Md * yd[:, None]).sum(axis=0) / (Md * Md).sum(axis=0)).tolist()); del Md
    placebo = np.asarray(placebo, np.float64)
    p_value = float((1 + np.sum(np.abs(placebo) >= np.abs(beta_actual))) / (1 + len(placebo)))
    return {"beta_actual": beta_actual, "p_value_permutation": p_value, "se_permutation": float(np.std(placebo, ddof=1)),
            "n_permutations": int(len(placebo)), "n_jobs_used": 1, "permuted": f"treated status across {len(units):,} {uk} units ({n1:,} treated; as R's M25)",
            "batch": int(k)}


def treatment_covariate_interaction(df, y_col, covariate_col, unit_col="pixel_id", time_col="time_fe_yearseason"):
    """v20.58 -- M26 as R's m26_interaction: y ~ did + did x c + c | unit + period with the covariate CENTRED (c = x - its mean), clustered on the
    design cluster. The HEADLINE is did = the effect at the covariate's mean (the ATT when the effect is linear in it); did x c = how much the
    effect changes per unit of the covariate. v20.57's engine split the covariate at its median and reported the below-median group's
    effect while R (the PRIMARY) reported the effect at the mean: two estimands under one model name."""
    from scipy import stats as _st
    d = df.copy()
    x = pd.to_numeric(d[covariate_col], errors="coerce").astype("float64")
    if not np.isfinite(x).any() or x.nunique() < 2: raise InsufficientDataError(f"{covariate_col} has no variation in this sample")
    cc = "centred_" + str(covariate_col)                                     # (the exported-zero rule never applies to these two terms:
    d[cc] = x - x.mean(); d["did_term"] = pd.to_numeric(d["did_term"], errors="coerce").astype("float64")   # 0 is a real value there)
    d["did_x_cov"] = d["did_term"] * d[cc]
    r = estimate_twfe_did(d, y_col, "did_term", unit_col, time_col, "subwshed_id", covariates=["did_x_cov", cc], return_all=True, covariates_by_post=False)
    G_ = int(r.get("n_clusters") or 2); dfp = max(1, G_ - 1)
    pt_ = lambda b, s_: float(2 * _st.t.sf(abs(b / s_), dfp)) if np.isfinite(b) and np.isfinite(s_) and s_ > 0 else np.nan
    b0, s0 = float(r["beta"]), float(r["se"]); b1, s1 = float(r["coef"].get("did_x_cov", np.nan)), float(r["se_all"].get("did_x_cov", np.nan))
    return {"beta_at_mean": b0, "se": s0, "p_value": pt_(b0, s0), "beta_interaction": b1, "se_interaction": s1, "p_interaction": pt_(b1, s1),
            "covariate": covariate_col, "covariate_mean": float(x.mean()), "n_clusters": G_, "cluster_used": LAST_CLUSTER_USED.get("value"),
            "se_how": f"cluster-robust (CR1), clustered by {LAST_CLUSTER_USED.get('value')} ({G_} clusters)", "p_how": f"t with {dfp} df"}


def treatment_covariate_heterogeneity(df, y_col, treat_col, post_col, covariate_col,
                                        unit_col, time_col, median_split=True):
    d = df.copy()
    if median_split:
        med = d[covariate_col].median()
        d["high_cov"] = (d[covariate_col] > med).astype(int)
    else:
        d["high_cov"] = d[covariate_col]
    if d["high_cov"].nunique() < 2:
        raise InsufficientDataError(f"Covariate {covariate_col} has no variation to split on in this sample.")
    d["did_term"] = (d[treat_col] * d[post_col]).astype("float64")
    d["did_x_cov"] = d["did_term"] * d["high_cov"]
    # v20.58: the same regression through the engine's two-way FE (the unit of the design, year x season effects) -- WITH cluster-robust SEs
    # on the design cluster (v20.57 gave no SE); the low group's effect, the differential and the high group's effect (delta method)
    from scipy import stats as _st
    r1 = estimate_twfe_did(d, y_col, "did_term", unit_col, time_col, "subwshed_id", covariates=["did_x_cov"], return_all=True, covariates_by_post=False)
    G_ = int(r1.get("n_clusters") or 2); dfp = max(1, G_ - 1)
    b0, s0 = r1["coef"]["did_term"], r1["se_all"]["did_term"]; b1, s1 = r1["coef"].get("did_x_cov", np.nan), r1["se_all"].get("did_x_cov", np.nan)
    r2 = estimate_twfe_did(d.assign(did_high=d["did_term"] * d["high_cov"], did_low=d["did_term"] * (1 - d["high_cov"])), y_col, "did_high", unit_col, time_col,
                           "subwshed_id", covariates=["did_low"], return_all=True, covariates_by_post=False)
    pt_ = lambda b, s: float(2 * _st.t.sf(abs(b / s), dfp)) if np.isfinite(b) and np.isfinite(s) and s > 0 else np.nan
    return {"beta_low_cov_group": b0, "se_low_cov_group": s0, "p_low_cov_group": pt_(b0, s0),
            "beta_differential_high_vs_low": b1, "se_differential": s1, "p_differential": pt_(b1, s1),
            "beta_high_cov_group": r2["beta"], "se_high_cov_group": r2["se"], "p_high_cov_group": pt_(r2["beta"], r2["se"]),
            "n_clusters": G_, "cluster_used": LAST_CLUSTER_USED.get("value")}



def _num_map(series, mapping):
    """v20.3: map a key column onto numeric values and ALWAYS return floats. A fixed-effect key stored as a
    pandas `category` (the v17.2 memory optimisation) maps to a CATEGORICAL result, and categoricals refuse
    arithmetic -- that is what broke M28/M29 with 'Object with dtype category cannot perform the numpy op
    subtract'. Use this helper for every unit/time mean lookup."""
    out = pd.Series(series).astype(object).map(mapping)
    return pd.to_numeric(out, errors="coerce").astype(float)

def _fit_untreated_two_way_fe(untreated, y_col, unit_col, time_col, max_iter=10000, tol=1e-12):
    """Shared helper for BJS (Module 27) and Gardner (Module 28): iteratively fit two-way
    fixed effects using ONLY untreated observations. Iteration is necessary because with an
    unbalanced panel the two-way FE are NOT simply the raw unit/time margins."""
    if len(untreated) == 0:
        raise InsufficientDataError(
            "No untreated observations available to fit the counterfactual model. Both BJS "
            "and Gardner require never-treated units and/or not-yet-treated periods.")
    grand = untreated[y_col].mean()
    # v20.54: observed=True -- a categorical unit / period column (the loader stores text as categories) otherwise yields every
    # category, used or not, under pandas 2 (pandas 3 made observed=True the default; the values here are unchanged)
    alpha = untreated.groupby(unit_col, observed=True)[y_col].mean() - grand
    gamma = untreated.groupby(time_col, observed=True)[y_col].mean() - grand
    for _ in range(max_iter):
        r_a = untreated[y_col].astype(float) - _num_map(untreated[time_col], gamma) - grand
        alpha_new = r_a.groupby(untreated[unit_col], observed=True).mean()
        r_g = untreated[y_col].astype(float) - _num_map(untreated[unit_col], alpha_new) - grand
        gamma_new = r_g.groupby(untreated[time_col], observed=True).mean()
        if (np.max(np.abs(alpha_new.reindex(alpha.index).fillna(0) - alpha.fillna(0))) < tol and
            np.max(np.abs(gamma_new.reindex(gamma.index).fillna(0) - gamma.fillna(0))) < tol):
            return grand, alpha_new, gamma_new
        alpha, gamma = alpha_new, gamma_new
    warn(f"the untreated two-way FE did not converge to {tol:g} in {max_iter} passes -- the imputation uses the last pass")   # v20.58: said, never silent
    return grand, alpha, gamma


def bjs_imputation_did(df, y_col, unit_col, time_col, treated_flag_col, event_time_col=None):
    unit_col = _unit_key(df, unit_col)             # v20.29: pixel x season unit when the scenario says so
    d = df.copy()
    grand, alpha, gamma = _fit_untreated_two_way_fe(d[d[treated_flag_col] == 0], y_col, unit_col, time_col)
    treated = d[d[treated_flag_col] == 1].copy()
    if len(treated) == 0:
        raise InsufficientDataError("No treated observations to impute counterfactuals for.")
    treated["Y0_hat"] = (grand + _num_map(treated[unit_col], alpha).fillna(0)
                          + _num_map(treated[time_col], gamma).fillna(0))
    treated["tau_it"] = treated[y_col] - treated["Y0_hat"]
    by_event = None
    if event_time_col is not None and event_time_col in treated.columns:
        by_event = treated.groupby(event_time_col)["tau_it"].mean().reset_index()
        by_event.columns = [event_time_col, "ATT_bjs"]
    return {"overall_ATT": treated["tau_it"].mean(), "by_event_time": by_event,
            "treated_with_tau": treated}


def _twoway_alternating(v, a, b, w=None, tol=1e-14, max_iter=100000):
    """v minus its two-way (a, b) fixed effects, by alternating (weighted) means to a relative change < tol -- warned if not reached."""
    w = np.ones(len(v)) if w is None else w
    sa = np.bincount(a, weights=w); sb = np.bincount(b, weights=w); x = np.asarray(v, dtype=np.float64).copy()
    for _ in range(max_iter):
        x1 = x - (np.bincount(a, weights=w * x) / sa)[a]
        x2 = x1 - (np.bincount(b, weights=w * x1) / sb)[b]
        if np.max(np.abs(x2 - x)) <= tol * max(1.0, float(np.max(np.abs(x2)))): return x2
        x = x2
    warn(f"two-way demeaning: {max_iter} passes without reaching {tol:g}"); return x

def bjs_imputation_series(df, y_col, covariates=None, unit_col="pixel_id", did_col="did_term"):
    """v20.58 -- M27 as R's m27 (didimputation, Borusyak-Jaravel-Spiess): one row per series x Year (R's unit_year: the mean of the SEASON-
    MATCHED outcome and of the covariates), the untreated model y = unit + Year effects + the design's covariates fitted on the untreated
    rows (exactly: Frisch-Waugh, alternating projections to 1e-14), Y(0) imputed for every treated row whose series and year are identified,
    the ATT = the mean of the treated rows' y - Y(0) (didimputation's default weights). v20.57's engine used the row-level data with year x
    season effects and no covariates (0.050728 against R's 0.050771)."""
    unit = _unit_key(df, unit_col)
    covs = [c_ for c_ in (covariates or []) if c_ in df.columns]
    d = df.copy(); d["_y_sn"] = season_net(d, y_col); d = d[np.isfinite(d["_y_sn"].values)]
    for c_ in covs: d = d[np.isfinite(pd.to_numeric(d[c_], errors="coerce").values)]
    g = d.groupby([unit, "Year"], observed=True).agg(y=("_y_sn", "mean"), Dr=(did_col, "max"), **{c_: (c_, "mean") for c_ in covs},
                                                     **({"site_id": ("site_id", "first")} if "site_id" in d.columns else {})).reset_index()
    ft = g[g["Dr"] == 1].groupby(unit, observed=True)["Year"].min()
    g["gvar"] = g[unit].map(ft).fillna(0).astype(float)
    if "first_treat_agri_year" in d.columns:                         # v20.58 (second pass): the DESIGN's cohort, as R's unit_year (gvar =
        _fc = pd.to_numeric(d["first_treat_agri_year"], errors="coerce").groupby(d[unit].values).first()   # cohort): a series whose first
        _fc = g[unit].map(_fc).astype(float)                                                               # treated year is missing kept
        g["gvar"] = np.where(np.isfinite(_fc.values) & (_fc.values > 0), _fc.values, g["gvar"].values)    # its cohort (the SE's cells)
    g["D"] = ((g["gvar"] > 0) & (g["Year"] >= g["gvar"])).astype(int)
    u0 = g[g["D"] == 0]; tr = g[g["D"] == 1]
    if not len(tr): raise InsufficientDataError("no treated series-year to impute")
    if not len(u0): raise InsufficientDataError("no untreated series-year to fit the counterfactual model")
    ua = pd.factorize(u0[unit])[0]; ub = pd.factorize(u0["Year"])[0]
    beta = np.zeros(len(covs))
    keep = np.zeros(len(covs), bool); Xd = None
    if covs:                                                           # Frisch-Waugh on the untreated rows
        Xd = np.column_stack([_twoway_alternating(u0[c_].values, ua, ub) for c_ in covs]); yd = _twoway_alternating(u0["y"].values, ua, ub)
        keep = Xd.std(axis=0) > 1e-12 * np.maximum(1.0, np.abs(u0[covs].values).max(axis=0))
        if keep.any(): beta[keep] = np.linalg.lstsq(Xd[:, keep], yd, rcond=None)[0]
    r0 = u0["y"].values - (u0[covs].values @ beta if covs else 0.0)
    e0 = _twoway_alternating(r0, ua, ub)                               # the residual after the two-way effects
    fe = r0 - e0                                                       # grand + alpha_i + gamma_t on the untreated rows
    # alpha_i + gamma_t, recovered per series and per year (identified up to one constant, which cancels in fe)
    a_i = pd.Series(ua); b_t = pd.Series(ub)
    gam = np.zeros(int(ub.max()) + 1); alp = np.zeros(int(ua.max()) + 1)
    for _ in range(100000):                                            # solve fe = alp[a] + gam[b] (exact on the untreated rows)
        alp_n = np.bincount(ua, weights=fe - gam[ub]) / np.bincount(ua)
        gam_n = np.bincount(ub, weights=fe - alp_n[ua]) / np.bincount(ub)
        if max(np.max(np.abs(alp_n - alp)), np.max(np.abs(gam_n - gam))) < 1e-15 * max(1.0, float(np.max(np.abs(fe)))): alp, gam = alp_n, gam_n; break
        alp, gam = alp_n, gam_n
    umap = dict(zip(u0[unit].values, ua)); ymap = dict(zip(u0["Year"].values, ub))
    ti = tr[unit].map(umap); tt = tr["Year"].map(ymap); ok_ = ti.notna().values & tt.notna().values
    n_lost = int((~ok_).sum()); tr = tr[ok_]
    if not len(tr): raise InsufficientDataError("no treated row has an untreated row of its series AND of its year to impute from")
    y0 = alp[ti[ok_].astype(int).values] + gam[tt[ok_].astype(int).values] + (tr[covs].values @ beta if covs else 0.0)
    tau = tr["y"].values - y0
    by_event = pd.DataFrame({"event_time": (tr["Year"] - tr["gvar"]).astype(int).values, "tau": tau}).groupby("event_time")["tau"].mean().reset_index().rename(columns={"tau": "ATT_bjs"})
    # v20.58 (second pass): didimputation's SE (BJS 2024, Theorem 3; did_imputation + se_inner, ported): each untreated row's weight in the
    # estimate v0 = -Z0 (Z0'Z0)^- Z1' w (Z = the first stage's covariates + series and year dummies, w = 1 / #treated rows), by Frisch-Waugh:
    # h = the two-way projection of the treated weights (Gauss-Seidel on the normal equations), v0 = -(h + X0~ dX), dX = (X0~'X0~)^-1 (X1'w -
    # X0'h); the treated rows' effects net of their cohort x event-time mean (v^2-weighted); SE^2 = sum over clusters (sum v e)^2, the
    # cluster = the series (didimputation's idname) -- the sub-watershed with >= MIN_SWS_CLUSTERS of them (R's cluster_var = "site_id")
    se = np.nan
    try:
        n1 = len(tr); wt = np.full(n1, 1.0 / n1)
        tu = ti[ok_].astype(int).values; tt_ = tt[ok_].astype(int).values
        nu = np.bincount(ua); nt = np.bincount(ub)
        cu = np.bincount(tu, weights=wt, minlength=len(nu)); ct = np.bincount(tt_, weights=wt, minlength=len(nt))
        al = np.zeros(len(nu)); ga = np.zeros(len(nt))
        for _ in range(1_000_000):                                       # (F0'F0) delta = F1'w, Gauss-Seidel (consistent, singular by one)
            al_n = (cu - np.bincount(ua, weights=ga[ub], minlength=len(nu))) / nu
            ga_n = (ct - np.bincount(ub, weights=al_n[ua], minlength=len(nt))) / nt
            dlt = max(float(np.max(np.abs(al_n - al))), float(np.max(np.abs(ga_n - ga)))); al, ga = al_n, ga_n
            if dlt <= 1e-16 * max(1.0, float(np.max(np.abs(al))), float(np.max(np.abs(ga)))): break
        h = al[ua] + ga[ub]
        v0 = -h
        if covs and keep.any():
            ck_ = [c_ for c_, k_ in zip(covs, keep) if k_]
            Xt0 = Xd[:, keep]; X0 = u0[ck_].values.astype(np.float64); X1 = tr[ck_].values.astype(np.float64)
            dX = np.linalg.solve(Xt0.T @ Xt0, X1.T @ wt - X0.T @ h)
            v0 = -(h + Xt0 @ dX)
        ev = (tr["Year"] - tr["gvar"]).values
        tcell = pd.Series(tau).groupby([tr["gvar"].values, ev]).transform("mean").values   # v = w is constant: the v^2-weighted mean = the mean
        e1 = tau - tcell
        clus = "site_id" if ("site_id" in g.columns and _r_site_cluster(g)) else unit
        if clus == "site_id" and "site_id" not in u0.columns: clus = unit
        c0 = u0[clus].values if clus in u0.columns else u0[unit].values; c1 = tr[clus].values if clus in tr.columns else tr[unit].values
        sc = pd.Series(np.concatenate([v0 * e0, wt * e1])).groupby(np.concatenate([np.asarray(c0, object), np.asarray(c1, object)])).sum().values
        se = float(np.sqrt(np.sum(sc ** 2)))
    except (np.linalg.LinAlgError, ValueError, KeyError, ZeroDivisionError) as _x:
        info(f"BJS: didimputation's SE not computed ({type(_x).__name__}: {str(_x)[:80]}) -- the design-based SE is used")
    return {"overall_ATT": float(np.mean(tau)), "by_event_time": by_event, "n_treated_rows": int(len(tr)), "n_treated_not_imputable": n_lost,
            "covariates": ",".join(covs), "covariate_coefs": dict(zip(covs, beta.tolist())), "se": se,
            "se_how": ("didimputation (Borusyak, Jaravel & Spiess 2024): its conservative analytic SE (ported), " +
                       ("clustered by sub-watershed" if (np.isfinite(se) and "site_id" in g.columns and _r_site_cluster(g)) else "each series one cluster (its idname)"))
                      if np.isfinite(se) else ""}


def gardner_two_stage_did(df, y_col, unit_col, time_col, treated_flag_col):
    unit_col = _unit_key(df, unit_col)             # v20.29: pixel x season unit when the scenario says so
    d = df.copy()
    grand, alpha, gamma = _fit_untreated_two_way_fe(d[d[treated_flag_col] == 0], y_col, unit_col, time_col)
    d["Y_residualized"] = (d[y_col].astype(float) - grand - _num_map(d[unit_col], alpha).fillna(0)
                            - _num_map(d[time_col], gamma).fillna(0))
    X = d[treated_flag_col].values.astype(float).reshape(-1, 1)
    if X.sum() == 0:
        raise InsufficientDataError("No treated observations for Gardner stage 2.")
    beta = float(np.linalg.lstsq(X, d["Y_residualized"].values, rcond=None)[0][0])
    return {"ATT_gardner": beta, "residualized_df": d}


def exposure_duration_effects(df, y_col, unit_col, time_col, treated_flag_col, event_time_col):
    unit_col = _unit_key(df, unit_col)             # v20.29: pixel x season unit when the scenario says so
    res = gardner_two_stage_did(df, y_col, unit_col, time_col, treated_flag_col)
    treated = res["residualized_df"]
    treated = treated[treated[treated_flag_col] == 1]
    out = treated.groupby(event_time_col)["Y_residualized"].agg(["mean", "std", "count"]).reset_index()
    out.columns = [event_time_col, "ATT_by_exposure", "sd", "n"]
    return out


def cohort_heterogeneity_effects(df, y_col, unit_col, time_col, treated_flag_col, cohort_col):
    """ATT separately per treatment-timing cohort -- 'do early and late adopters differ?'"""
    unit_col = _unit_key(df, unit_col)             # v20.29: pixel x season unit when the scenario says so
    res = gardner_two_stage_did(df, y_col, unit_col, time_col, treated_flag_col)
    treated = res["residualized_df"]
    treated = treated[treated[treated_flag_col] == 1]
    out = treated.groupby(cohort_col)["Y_residualized"].agg(["mean", "std", "count"]).reset_index()
    out.columns = [cohort_col, "ATT_by_cohort", "sd", "n"]
    return out


# ====================== v20.58: M17 / M18 -- one point per pixel, exact k-NN, spdep's formulas (identical in R) ======================
# v20.57 took every ROW of the loaded panel as a point: each pixel appeared once per year x season at the SAME place, so its 8 "nearest
# neighbours" were its own other years (distance 0) -- the I measured a pixel's persistence over time, not space -- and it used rows the
# design excludes (rings, years, seasons, other locations). Now: the estimation sample, one point per pixel (its change post minus pre, as
# R's M17), k-NN on metres (an exact kd-tree, queries in batches only beyond 98 % of the RAM), Moran's I with its randomisation variance,
# SE and a two-sided p, the local Moran's I with spdep's conditional variance.
def pixel_change(df, outcome):
    """One row per pixel of the estimation sample: dY = mean(post) - mean(pre) of the outcome, treat, mean latitude / longitude."""
    d = df[df["in_analysis_sample"].values == 1] if "in_analysis_sample" in df.columns else df
    y = pd.to_numeric(d[outcome], errors="coerce").values.astype(np.float64)
    t = pd.DataFrame({"pixel_id": d["pixel_id"].values, "post": pd.to_numeric(d["post"], errors="coerce").values.astype(np.int64), "y": y,
                      "treat": pd.to_numeric(d["treatment"], errors="coerce").values if "treatment" in d.columns else 0,
                      "lat": pd.to_numeric(d["latitude"], errors="coerce").values, "lon": pd.to_numeric(d["longitude"], errors="coerce").values})
    t = t[np.isfinite(t["y"].values)]
    m = t.groupby(["pixel_id", "post"])["y"].mean().unstack("post")
    if 0 not in m.columns or 1 not in m.columns: raise InsufficientDataError("no pixel is seen both before and after the start")
    g = t.groupby("pixel_id").agg(treat=("treat", "max"), lat=("lat", "mean"), lon=("lon", "mean"))
    g["dY"] = (m[1] - m[0]).reindex(g.index)
    g = g[np.isfinite(g["dY"].values) & np.isfinite(g["lat"].values) & np.isfinite(g["lon"].values)].reset_index()
    if len(g) < 10: raise InsufficientDataError(f"only {len(g)} pixels have a change before -> after: too few for spatial weights")
    return g

def knn_xy(lat, lon):
    R = 6371000.0; lat0 = np.radians(np.mean(lat))
    return np.column_stack([np.radians(lon) * R * np.cos(lat0), np.radians(lat) * R])

def knn_index(xy, k=8):
    """The k nearest neighbours of every point (n x k int64), exact (scipy cKDTree); the queries in batches only beyond 98 % of the RAM."""
    from scipy.spatial import cKDTree
    n = len(xy)
    if n <= k: raise InsufficientDataError(f"k-NN weights need more than k = {k} points (have {n})")
    tree = cKDTree(xy); nn = np.empty((n, k), np.int64)
    try:
        import _hardware as _H; bud = _H.ram_budget_bytes()
    except Exception:
        bud = None
    per = 16 * (k + 1) + 96; cap = n if bud is None else max(1, int(bud // per))
    if FORCE_BATCH_UNITS: cap = min(cap, int(FORCE_BATCH_UNITS))
    starts = list(range(0, n, cap))
    if len(starts) > 1: info(f"k-NN search: {n:,} pixels in {len(starts)} batches of <= {cap:,} -- all at once would pass 98 % of the RAM; every pixel is used")
    for a in starts:
        q = np.arange(a, min(n, a + cap))
        _, r = tree.query(xy[q], k=k + 1)
        self_ = r == q[:, None]; none = ~self_.any(axis=1); self_[none, k] = True        # the point itself leaves its own list
        nn[q] = r[~self_].reshape(len(q), k)
    return nn

def moran_knn(v, nn, k=8):
    """Moran's I (spdep moran.test, randomisation variance) and the local Moran's I (spdep localmoran, conditional) from row-standardised
    k-NN weights, computed from the n x k index. p-values two-sided. Identical to R's moran_knn (lib/models_prebuilt.R)."""
    from scipy import stats as _st
    v = np.asarray(v, np.float64); n = len(v); z = v - v.mean()
    lag = z[nn].mean(axis=1)
    # directed edges whose reverse exists (i in N(j) for j in N(i)) -- in batches of rows
    mutual = 0
    for a in range(0, n, 2_000_000):
        i = np.arange(a, min(n, a + 2_000_000)); J = nn[i]
        mutual += int(sum((nn[J[:, m]] == i[:, None]).any(axis=1).sum() for m in range(k)))
    S0 = float(n); S1 = (n * k + mutual) / k ** 2; S2 = float(np.sum((1.0 + np.bincount(nn.ravel(), minlength=n) / k) ** 2))
    sz2 = float(np.sum(z ** 2))
    if sz2 <= 0: raise InsufficientDataError("zero variance -- Moran's I is undefined for a constant field")
    m2 = sz2 / n; I = float(np.sum(z * lag) / sz2); K = n * float(np.sum(z ** 4)) / sz2 ** 2; EI = -1.0 / (n - 1)
    VI = n * (S1 * (n * n - 3 * n + 3) - n * S2 + 3 * S0 ** 2) - K * (S1 * (n * n - n) - 2 * n * S2 + 6 * S0 ** 2)
    VI = VI / ((n - 1) * (n - 2) * (n - 3) * S0 ** 2) - EI ** 2
    Z = (I - EI) / np.sqrt(VI) if VI > 0 else np.nan
    Ii = z * lag / m2; E_Ii = -(z ** 2) / ((n - 1) * m2); V_Ii = (z / m2) ** 2 * (n / (n - 2)) * (1.0 / k - 1.0 / (n - 1)) * (m2 - z ** 2 / (n - 1))
    with np.errstate(divide="ignore", invalid="ignore"):
        Z_Ii = (Ii - E_Ii) / np.sqrt(V_Ii)
    return {"I": I, "EI": EI, "VI": float(VI), "Z": float(Z), "p": float(2 * _st.norm.sf(abs(Z))) if np.isfinite(Z) else np.nan,
            "Ii": Ii, "E_Ii": E_Ii, "V_Ii": V_Ii, "Z_Ii": Z_Ii, "p_Ii": 2 * _st.norm.sf(np.abs(Z_Ii)), "z": z, "lag": lag}

def spatial_moran(df, outcome, k=8):
    """M17 / M18: (global row dict, LISA frame) on the estimation sample -- see the block comment above."""
    g = pixel_change(df, outcome)
    nn = knn_index(knn_xy(g["lat"].values, g["lon"].values), k)
    r = moran_knn(g["dY"].values, nn, k)
    glob_ = {"outcome": outcome, "morans_I": r["I"], "expected_I": r["EI"], "variance_I": r["VI"], "se_moran": float(np.sqrt(r["VI"])), "z": r["Z"],
             "p_value": r["p"], "alternative": "two.sided", "k": k, "n": len(g), "points": "one per pixel: its change post minus pre (the estimation sample)",
             "engine": "spdep's moran.test / localmoran formulas on an exact k-NN (scipy cKDTree)"}
    z, lag = r["z"], r["lag"]
    q = np.where((z > 0) & (lag > 0), "High-High (hot spot)", np.where((z <= 0) & (lag <= 0), "Low-Low (cold spot)",
                 np.where(z > 0, "High-Low (spatial outlier)", "Low-High (spatial outlier)")))
    lisa = pd.DataFrame({"pixel_id": g["pixel_id"].values, "latitude": g["lat"].values, "longitude": g["lon"].values, "treat": g["treat"].values,
                         "dY": g["dY"].values, "local_I": r["Ii"], "expectation": r["E_Ii"], "variance": r["V_Ii"], "z": r["Z_Ii"], "p_value": r["p_Ii"],
                         "quadrant": np.where(r["p_Ii"] < 0.05, q, "Not significant (p >= 0.05)")})
    return glob_, lisa

def build_knn_spatial_weights(lat, lon, k=8):
    """Row-standardized k-NN spatial weights. Reuses the SAME nearest-neighbor backend
    (_nn_match, from Step 3) that already auto-selects cuML / PyTorch-CUDA / scipy cKDTree
    depending on GPU_BACKEND -- this is the one genuinely GPU-relevant step here."""
    R = 6371000.0
    lat0 = np.radians(np.mean(lat))
    x = np.radians(lon) * R * np.cos(lat0)
    y = np.radians(lat) * R
    coords = np.column_stack([x, y])
    dist, idx = _nn_match(coords, coords)  # self-query; caller must drop the self-match column
    # _nn_match (Step 3) returns only the SINGLE nearest neighbor -- for k>1 we fall back to
    # cKDTree directly here (GPU backend is only worth its transfer overhead for the pixel-UID
    # matching case's specific access pattern; k-NN-for-spatial-weights is a one-time,
    # not-in-a-loop computation, so plain cKDTree is both simpler and fast enough)
    tree = cKDTree(coords)
    dist, idx = tree.query(coords, k=k + 1)
    n = len(lat)
    # v17: vectorised (was a Python loop over every edge -- 100x slower at 200k points x 8 nbrs)
    rows = np.repeat(np.arange(n), k)
    cols = idx[:, 1:].ravel()
    vals = np.full(n * k, 1.0 / k)
    return rows, cols, vals


def global_morans_i(x, w_rows, w_cols, w_vals):
    n = len(x)
    xbar = x.mean()
    z = x - xbar
    S0 = w_vals.sum()
    numerator = np.sum(w_vals * z[w_rows] * z[w_cols])
    denominator = np.sum(z ** 2)
    if denominator == 0:
        raise InsufficientDataError("Zero variance in this variable -- Moran's I is undefined "
                                     "(nothing to test for spatial autocorrelation in a constant field).")
    I = (n / S0) * (numerator / denominator)
    E_I = -1.0 / (n - 1)
    return I, E_I


def local_morans_i(x, w_rows, w_cols, w_vals):
    n = len(x)
    z = x - x.mean()
    m2 = np.sum(z ** 2) / n
    if m2 == 0:
        raise InsufficientDataError("Zero variance -- local Moran's I is undefined for a constant field.")
    lag = np.zeros(n)
    np.add.at(lag, w_rows, w_vals * z[w_cols])   # v17: vectorised spatial lag
    local_I = (z / m2) * lag
    quadrant = np.full(n, "Not Significant", dtype=object)
    high_z, high_lag = z > 0, lag > 0
    quadrant[high_z & high_lag] = "High-High (hot spot)"
    quadrant[~high_z & ~high_lag] = "Low-Low (cold spot)"
    quadrant[high_z & ~high_lag] = "High-Low (spatial outlier)"
    quadrant[~high_z & high_lag] = "Low-High (spatial outlier)"
    return local_I, quadrant


def variance_decomposition(x, group):
    df = pd.DataFrame({"x": x, "group": group})
    if df["group"].nunique() < 2:
        raise InsufficientDataError("Need at least 2 sub-watersheds to decompose within/among variance.")
    grand_mean = df["x"].mean()
    # v20.54: observed=True. With the sub-watershed as a categorical column holding sub-watersheds that are NOT in this sample
    # (the loader keeps every category of the file), pandas 2 counted them as empty groups: k too large and the ICC biased
    # (a test with 2 of 20 sub-watersheds: 0.281 instead of 0.317). pandas 3 already behaves this way.
    group_means = df.groupby("group", observed=True)["x"].mean()
    group_sizes = df.groupby("group", observed=True)["x"].size()
    n, k = len(df), len(group_means)
    ss_between = np.sum(group_sizes * (group_means - grand_mean) ** 2)
    ss_within = np.sum(df.groupby("group", observed=True)["x"].apply(lambda g: np.sum((g - g.mean()) ** 2)))
    ms_between = ss_between / (k - 1)
    ms_within = ss_within / max(n - k, 1)
    n0 = (n - np.sum(group_sizes**2) / n) / (k - 1)
    sigma_b2 = max((ms_between - ms_within) / n0, 0.0)
    sigma_w2 = ms_within
    icc = sigma_b2 / (sigma_b2 + sigma_w2) if (sigma_b2 + sigma_w2) > 0 else 0.0
    return {"ICC": icc, "sigma_between2": sigma_b2, "sigma_within2": sigma_w2}


def variance_components_crossed(df, y_col, grp_col, pixel_col="pixel_id", did_col="did_term"):
    """v20.58 -- M19 as R's m19_icc (lme4::lmer(y ~ did + (1 | group) + (1 | pixel_id)), REML): the variance of the outcome split into the
    GROUP (sub-watersheds, or years with one sub-watershed), the PIXEL and the residual, the treatment a FIXED effect; ICC = the group's share.
    v20.57's engine was a one-way ANOVA without the treatment: the effect's +0.05 on the treated post rows became "variance between years"
    (0.101 against lme4's 0.059 on the poison test). Here: the treatment removed first (its two-way FE coefficient on pixel and group), then
    the ANOVA (method-of-moments) estimators of the crossed components -- REML's answer when the panel is balanced, close to it otherwise."""
    y = pd.to_numeric(df[y_col], errors="coerce").values.astype(np.float64)
    D = pd.to_numeric(df[did_col], errors="coerce").fillna(0).values.astype(np.float64) if did_col in df.columns else np.zeros(len(y))
    gi = pd.factorize(df[grp_col].astype(str).values)[0]; pi_ = pd.factorize(df[pixel_col].values)[0]
    ok_ = np.isfinite(y); y, D, gi, pi_ = y[ok_], D[ok_], gi[ok_], pi_[ok_]
    g_n, p_n, N = int(gi.max() + 1), int(pi_.max() + 1), len(y)
    if g_n < 2: raise InsufficientDataError("Need at least 2 groups (sub-watersheds, or years) to decompose the variance.")
    if D.std() > 0:                                                            # the treatment as a fixed effect
        yd = demean_two_way(y, pi_, gi); dd_ = demean_two_way(D, pi_, gi)
        b = float(np.dot(dd_, yd) / np.dot(dd_, dd_)) if np.dot(dd_, dd_) > 0 else 0.0
    else:
        b = 0.0
    ys = y - b * D
    r = demean_two_way(ys, pi_, gi)                                            # the two-way (additive) residual
    ms_e = float(np.dot(r, r) / max(1, N - p_n - g_n + 1))
    def comp(ix, k):
        n_ = np.bincount(ix, minlength=k).astype(float); m_ = np.bincount(ix, weights=ys, minlength=k) / np.maximum(n_, 1)
        ss = float(np.sum(n_ * (m_ - ys.mean()) ** 2)); ms = ss / max(1, k - 1); k0 = (N - np.sum(n_ ** 2) / N) / max(1, k - 1)
        return max(0.0, (ms - ms_e) / k0) if k0 > 0 else 0.0
    s_g, s_p = comp(gi, g_n), comp(pi_, p_n)
    tot = s_g + s_p + ms_e
    return {"ICC": s_g / tot if tot > 0 else 0.0, "variance_group": s_g, "variance_pixel": s_p, "variance_residual": ms_e,
            "share_pixel": s_p / tot if tot > 0 else 0.0, "share_residual": ms_e / tot if tot > 0 else 0.0,
            "treatment_fixed_effect": b, "n_groups": g_n, "n_pixels": p_n, "n_rows": N,
            "engine": "engine (crossed variance components by the ANOVA method; the treatment a fixed effect -- as lme4's model)"}


def treatment_heterogeneity_test(effects, ses):
    """v20.58 -- the SAME as R's m20_heterogeneity (metafor::rma, DerSimonian-Laird): Cochran's Q with inverse-variance weights against
    chi-square with k - 1 df (the headline), Higgins' I2 = (Q - df) / Q, the DerSimonian-Laird tau2 and the random-effects pooled effect
    with its SE. v20.57 gave the fixed-effect mean as 'pooled' while R gave REML."""
    from scipy import stats as sstats
    effects = np.asarray(effects, dtype=float); ses = np.asarray(ses, dtype=float)
    if len(effects) < 2:
        raise InsufficientDataError("Need effect estimates from at least 2 sub-watersheds to test heterogeneity.")
    w = 1.0 / (ses ** 2)
    theta_fe = np.sum(w * effects) / np.sum(w)
    Q = float(np.sum(w * (effects - theta_fe) ** 2))
    df_ = len(effects) - 1
    p_value = float(sstats.chi2.sf(Q, df_))
    I2 = max(0.0, (Q - df_) / Q) * 100 if Q > 0 else 0.0
    tau2 = max(0.0, (Q - df_) / (np.sum(w) - np.sum(w ** 2) / np.sum(w)))          # DerSimonian-Laird
    ws = 1.0 / (ses ** 2 + tau2); pooled = float(np.sum(ws * effects) / np.sum(ws)); pooled_se = float(np.sqrt(1.0 / np.sum(ws)))
    return {"Q": Q, "Q_df": df_, "p_value": p_value, "pooled_effect": pooled, "pooled_se": pooled_se, "I2": I2, "tau2": float(tau2),
            "n_sub_watersheds": int(len(effects)), "reject_homogeneity_at_5pct": bool(p_value < 0.05),
            "se_how": "each sub-watershed's DiD with its design-based SE (years as the draws); Q with inverse-variance weights",
            "p_how": f"chi-square with {df_} df", "engine": "engine (DerSimonian-Laird, as metafor::rma)"}


def build_season_fraction_dose(df, unit_col, year_col, season_col, treat_col, n_seasons=3):
    """For each unit-year, computes the FRACTION of that year's seasons where treat_col==1
    -- the continuous dose that avoids the aggregation bias demonstrated above. Use this
    dose in Module 6 rather than a binary Post flag if you need an annual-frequency panel."""
    d = df.copy()
    seasons_treated = d.groupby([unit_col, year_col])[treat_col].sum().rename("k_seasons_treated")
    out = d.groupby([unit_col, year_col]).first().join(seasons_treated).reset_index()
    out["frac_seasons_treated"] = out["k_seasons_treated"] / n_seasons
    return out


# ==========================================================================
# NEW IN v6.0 -- the previously-deferred methods, each validated against
# simulated data with a KNOWN true effect (see validate_all() at the bottom).
# ==========================================================================

def stacked_did(df, y_col, unit_col, time_col, cohort_col, never_treated_value=np.inf,
                window=(-3, 3)):
    """STACKED DiD (Cengiz, Dube, Lindner & Zipperer 2019 style). One clean SUB-EXPERIMENT
    per cohort g: g's treated units + only CLEAN controls (never-treated, or not-yet-treated
    through the window end), restricted to an event window around g. Stack them and run TWFE
    with sub-experiment-SPECIFIC unit and time FE, so an already-treated unit can never act
    as another cohort's control -- structurally eliminating the forbidden comparison.
      Y_ist = alpha_is + gamma_ts + beta*(Treat_i^s * Post_t^s) + e_ist
    """
    unit_col = _unit_key(df, unit_col)             # v20.29: pixel x season unit when the scenario says so
    lo, hi = window
    stacks = []
    for g in sorted(c for c in df[cohort_col].unique() if c != never_treated_value):
        yrs = [g + k for k in range(lo, hi + 1)]
        treated = df[(df[cohort_col] == g) & (df[time_col].isin(yrs))].copy()
        ctrl = df[((df[cohort_col] == never_treated_value) | (df[cohort_col] > g + hi))
                  & (df[time_col].isin(yrs))].copy()
        if treated.empty or ctrl.empty:
            continue
        s = pd.concat([treated, ctrl])
        s["stack"] = str(g)
        s["treat_g"] = (s[cohort_col] == g).astype(int)
        s["post_g"] = (s[time_col] >= g).astype(int)
        s["did_stack"] = s["treat_g"] * s["post_g"]
        stacks.append(s)
    if not stacks:
        raise InsufficientDataError(
            "No valid sub-experiment could be built: every cohort lacked either treated units "
            "or clean (never/not-yet-treated) controls inside its event window.")
    st = pd.concat(stacks, ignore_index=True)
    st["_su"] = st["stack"] + "_" + st[unit_col].astype(str)
    st["_st"] = st["stack"] + "_" + st[time_col].astype(str)
    # v20.58: the time effect is stack x year x season (the seasons' own shocks, as every other model) and the SE is clustered as the design is
    # (sub-watersheds, or the years below 6 of them) -- v20.57 clustered on the stacked PIXEL series: an SE several times too small
    if "time_fe_yearseason" in st.columns: st["_st"] = st["stack"] + "_" + st["time_fe_yearseason"].astype(str)
    cl_ = _cluster_key(st, "subwshed_id")
    if cl_ not in st.columns: cl_ = "_su"          # a frame without sub-watersheds or years (a simulation): the stacked unit series, as v20.57
    beta, se = estimate_twfe_did(st, y_col, "did_stack", "_su", "_st", cl_)
    return {"ATT_stacked": beta, "se": se, "n_sub_experiments": st["stack"].nunique()}, st


def etwfe(df, y_col, unit_col, time_col, cohort_col, never_treated_value=np.inf, fe="cohort", cluster_col="subwshed_id"):
    """EXTENDED TWFE (Wooldridge 2021). Fully saturated cohort x period treatment dummies --
    one coefficient per (g,t) cell with t>=g -- then aggregate to an overall ATT weighted by
    cell size. Heterogeneity-robust because no coefficient is forced to average across
    cohorts or periods.
      Y_it = alpha_g + gamma_t + sum_g sum_{t>=g} beta_gt * 1[G_i=g] * 1[T=t] + e_it
    v20.58 (second pass) -- etwfe's own specification, as R's m32_etwfe (etwfe::etwfe + emfx(type = "simple")): the COHORT's effect alpha_g
    (etwfe's default, ivar = NULL; this engine used the series' effect -- the same coefficients on a balanced panel, not on an unbalanced
    one; fe = "unit" keeps that), the year effects, the post-treatment cells against every not-yet- and never-treated row (cgroup "notyet");
    the ATT = the cells weighted by their treated rows; its SE by the delta method on the cluster-robust covariance (fixest's CR1: the
    design's clusters, G / (G - 1) (n - 1) / (n - K), the fixed effects counted as fixest's "nested" rule); p from t with G - 1 df (R: the
    same; etwfe's own normal p is beside it there)."""
    unit_col = _unit_key(df, unit_col)             # v20.29: pixel x season unit when the scenario says so
    d = df.copy()
    if "Season" in d.columns and d["Season"].nunique() > 1 and time_col == "Year":     # v20.58: season-matched (as R's M32 on y_sn)
        d["_y_sn"] = season_net(d, y_col); y_col = "_y_sn"; d = d[np.isfinite(d[y_col].values)]
    cells = []
    for g in sorted(c for c in d[cohort_col].unique() if c != never_treated_value):
        for t in sorted(d[d[time_col] >= g][time_col].unique()):
            col = ((d[cohort_col] == g) & (d[time_col] == t)).astype(float).values
            if col.sum() == 0:
                continue
            cells.append(((g, t), col))
    if not cells:
        raise InsufficientDataError("No treated (cohort, period) cells found for ETWFE.")
    f1 = pd.factorize((d[cohort_col] if fe == "cohort" else d[unit_col]).astype(str).values)[0]
    f2 = pd.factorize(d[time_col].values)[0]
    yd = demean_two_way(d[y_col].values.astype(np.float64), f1, f2)
    X = np.column_stack([demean_two_way(c, f1, f2) for _, c in cells])
    beta = np.linalg.lstsq(X, yd, rcond=None)[0]
    w = np.array([c.sum() for _, c in cells]); w = w / w.sum()
    att = float(np.sum(beta * w)); se = np.nan; G = 0; ck = None
    try:
        ck = _cluster_key(d, cluster_col); clv = d[ck].astype(str).values; G = int(pd.Series(clv).nunique())
        V = cluster_robust_se(X, yd - X @ beta, clv, k_fe=_k_fe_nonnested([f1, f2], pd.factorize(clv)[0]))
        se = float(np.sqrt(max(float(w @ V @ w), 0.0)))
    except (InsufficientDataError, np.linalg.LinAlgError, KeyError) as e:
        info(f"ETWFE: no cluster-robust SE ({type(e).__name__}: {str(e)[:80]}) -- the design-based SE is used")
    from scipy import stats as _st
    dfp = max(1, G - 1)
    tbl = pd.DataFrame([{"cohort": k[0], "period": k[1], "ATT_gt": b, "weight": wt}
                        for (k, _), b, wt in zip(cells, beta, w)])
    return {"ATT_etwfe": att, "n_cells": len(cells), "se": se,
            "p_value": float(2 * _st.t.sf(abs(att / se), dfp)) if np.isfinite(se) and se > 0 else np.nan, "n_clusters": G,
            "se_how": (f"etwfe's delta method on the covariance clustered by {ck} ({G} clusters; fixest's CR1), the cells weighted by their treated rows"
                       if np.isfinite(se) else ""), "p_how": f"t with {dfp} df" if np.isfinite(se) else "",
            "fixed_effects": "cohort + year (etwfe's)" if fe == "cohort" else "series + year"}, tbl


def entropy_balance(X_ctrl, target_moments, max_iter=500, tol=1e-8):
    """ENTROPY BALANCING (Hainmueller 2012, Political Analysis 20:25-46). Finds control
    weights w that EXACTLY reproduce the treated group's covariate moments while staying as
    close as possible to uniform (maximum entropy). Solved on the convex dual:
      min_lambda  log(sum_i exp(-X_i'lambda)) + target'lambda
      w_i proportional to exp(-X_i'lambda)
    Unlike propensity matching it does not discard controls and needs no caliper -- balance
    is imposed as a hard constraint rather than hoped for."""
    n, k = np.asarray(X_ctrl).shape
    X_ctrl = np.asarray(X_ctrl, dtype=float)
    target_moments = np.asarray(target_moments, dtype=float)
    def dual(lam):
        z = -X_ctrl @ lam; m = z.max()
        return np.log(np.sum(np.exp(z - m))) + m + target_moments @ lam
    def grad(lam):
        z = -X_ctrl @ lam; z = z - z.max()
        w = np.exp(z); w = w / w.sum()
        return target_moments - X_ctrl.T @ w
    res = minimize(dual, np.zeros(k), jac=grad, method="BFGS",
                   options={"maxiter": max_iter, "gtol": tol})
    z = -X_ctrl @ res.x; z = z - z.max()
    w = np.exp(z); w = w / w.sum()
    achieved = X_ctrl.T @ w
    if np.max(np.abs(achieved - target_moments)) > 1e-4:
        raise InsufficientDataError(
            "Entropy balancing could not match the treated group's covariate moments -- the "
            "treated group likely lies outside the control group's covariate support "
            "(a real common-support problem, not a solver failure).")
    return w, achieved


def entropy_balanced_did(df, y_col, treat_col, post_col, covariate_cols, unit_col):
    """Entropy-balanced DiD: balance controls to the treated group on pre-treatment
    covariate means, then compute the standard 2x2 DiD using those weights."""
    unit_lvl = df.groupby(unit_col).agg(
        **{treat_col: (treat_col, "first")},
        **{f"{c}_pre": (c, "mean") for c in covariate_cols}).reset_index()
    cols = [f"{c}_pre" for c in covariate_cols]
    Xt = unit_lvl.loc[unit_lvl[treat_col] == 1, cols].values
    Xc = unit_lvl.loc[unit_lvl[treat_col] == 0, cols].values
    if len(Xt) == 0 or len(Xc) == 0:
        raise InsufficientDataError("Need both treated and control units for entropy balancing.")
    mu, sd = Xc.mean(axis=0), Xc.std(axis=0); sd[sd == 0] = 1.0
    w, _ = entropy_balance((Xc - mu) / sd, ((Xt.mean(axis=0)) - mu) / sd)
    wmap = dict(zip(unit_lvl.loc[unit_lvl[treat_col] == 0, unit_col], w))
    d = df.copy()
    d["_w"] = d.apply(lambda r: 1.0 if r[treat_col] == 1 else wmap.get(r[unit_col], 0.0), axis=1)
    def wm(mask):
        s = d.loc[mask, "_w"].sum()
        return np.nan if s == 0 else float((d.loc[mask, y_col] * d.loc[mask, "_w"]).sum() / s)
    t1 = d[treat_col] == 1; t0 = d[treat_col] == 0; p1 = d[post_col] == 1; p0 = d[post_col] == 0
    did = (wm(t1 & p1) - wm(t1 & p0)) - (wm(t0 & p1) - wm(t0 & p0))
    return {"ATT_entropy_balanced": did, "n_control_units_weighted": int((w > 1e-8).sum())}


def weighted_twfe_did(df, y_col, d_col, fe1_col, fe2_col, cluster_col, w_col, tol=1e-13, max_iter=100000):
    """v20.58: the WEIGHTED two-way FE DiD with its cluster-robust SE -- fixest's feols(y ~ d | fe1 + fe2, weights = ~w, cluster = ~cl): the
    fixed effects removed by weighted alternating projections, rows of weight 0 left out (as fixest), the CR1 factor with the non-nested fixed
    effects counted, t with G - 1 df. Used by M33 (entropy-balanced DiD, as R's WeightIt + fixest)."""
    from scipy import stats as _st
    fe1_col = _unit_key(df, fe1_col); cl = _cluster_key(df, cluster_col)
    w = pd.to_numeric(df[w_col], errors="coerce").values.astype(np.float64)
    y = pd.to_numeric(df[y_col], errors="coerce").values.astype(np.float64); x = pd.to_numeric(df[d_col], errors="coerce").values.astype(np.float64)
    ok_ = np.isfinite(w) & (w > 0) & np.isfinite(y) & np.isfinite(x)
    w, y, x = w[ok_], y[ok_], x[ok_]
    f1 = pd.factorize(df[fe1_col].values[ok_])[0]; f2 = pd.factorize(df[fe2_col].values[ok_])[0]; clv = df[cl].values[ok_]
    s1 = np.bincount(f1, weights=w); s2 = np.bincount(f2, weights=w)
    def dm(v):
        v = v.copy()
        for _ in range(max_iter):
            v1 = v - (np.bincount(f1, weights=w * v) / s1)[f1]
            v2 = v1 - (np.bincount(f2, weights=w * v1) / s2)[f2]
            if np.max(np.abs(v2 - v)) < tol * max(1.0, float(np.max(np.abs(v2)))): return v2
            v = v2
        warn(f"weighted demeaning: {max_iter} passes without reaching {tol:g} -- the result is the last pass"); return v
    xt, yt = dm(x), dm(y)
    sxx = float(np.sum(w * xt * xt))
    if not sxx > 0: raise InsufficientDataError("the treatment has no variation left after the fixed effects (weighted)")
    b = float(np.sum(w * xt * yt)) / sxx; e = yt - b * xt
    cc = pd.factorize(clv)[0]; G = int(cc.max()) + 1
    if G < 2: raise InsufficientDataError("fewer than 2 clusters")
    k_fe = _k_fe_nonnested([f1, f2], cc); n = len(y)
    sc = np.bincount(cc, weights=w * xt * e, minlength=G)
    se = float(np.sqrt((G / (G - 1)) * ((n - 1) / max(1, n - 1 - k_fe)) * float(np.sum(sc ** 2))) / sxx)
    p = float(2 * _st.t.sf(abs(b / se), G - 1)) if se > 0 else np.nan
    return {"beta": b, "se": se, "p_value": p, "n_obs": int(n), "n_clusters": G, "cluster_used": str(LAST_CLUSTER_USED.get("value") or cl)}

def entropy_balanced_twfe(df, y_col, covariate_cols, treat_col="treat_core", post_col="post", did_col="did_term", pixel_col="pixel_id",
                          time_fe_col="time_fe_yearseason", cluster_col="subwshed_id"):
    """v20.58 -- M33 as R's m33 (WeightIt ebal + fixest): each pixel's PRE-period covariate means, entropy-balancing weights for the control
    pixels (their weighted means = the treated pixels' means; the treated weight 1, the control weights summing to the number of treated
    pixels -- WeightIt's scale), then the WEIGHTED two-way FE DiD (unit and year x season effects) with its cluster-robust SE on every row.
    v20.57's engine averaged the covariates over every period and took a weighted 2 x 2 of raw means (0.0506 against R's 0.0507)."""
    cv = [c_ for c_ in covariate_cols if c_ in df.columns]
    if not cv: raise InsufficientDataError("entropy balancing needs covariates (COVARIATES is empty)")
    d = df[np.isfinite(pd.to_numeric(df[y_col], errors="coerce").values)].copy()
    pre = d[pd.to_numeric(d[post_col], errors="coerce").values == 0]
    base = pre.groupby(pixel_col).agg(**{treat_col: (treat_col, "max")}, **{c_: (c_, "mean") for c_ in cv}).reset_index()
    Xt = base.loc[base[treat_col] == 1, cv].values.astype(float); Xc = base.loc[base[treat_col] == 0, cv].values.astype(float)
    if not len(Xt) or not len(Xc): raise InsufficientDataError("entropy balancing needs treated and control pixels with pre-period rows")
    mu, sd = Xc.mean(axis=0), Xc.std(axis=0); sd[sd == 0] = 1.0
    wc, _ = entropy_balance((Xc - mu) / sd, (Xt.mean(axis=0) - mu) / sd, max_iter=5000, tol=1e-12)
    wmap = dict(zip(base.loc[base[treat_col] == 0, pixel_col].values, wc * len(Xt)))       # WeightIt's scale: the control weights sum to n treated
    trv = pd.to_numeric(d[treat_col], errors="coerce").values == 1
    in_base = d[pixel_col].isin(base[pixel_col]).values                                    # a pixel with no pre-period row leaves (R: the merge)
    d["_w_ebal"] = np.where(trv & in_base, 1.0, d[pixel_col].map(wmap).fillna(0.0).values)
    r = weighted_twfe_did(d, y_col, did_col, pixel_col, time_fe_col, cluster_col, "_w_ebal")
    return {"outcome": y_col, "ATT_entropy_balanced": r["beta"], "se": r["se"], "p_value": r["p_value"], "n_control_units_weighted": int((wc > 1e-8).sum()),
            "n_treated_pixels": int(len(Xt)), "covariates": ",".join(cv),
            "se_how": f"the weighted two-way FE DiD, cluster-robust (CR1), {r['n_clusters']} clusters ({r['cluster_used']})",
            "engine": "engine: entropy balancing (Hainmueller 2012; WeightIt's scale) + weighted two-way FE"}


def honest_did_relative_magnitudes(event_betas, event_ses, pre_periods, post_period,
                                    M_grid=None):
    """HONEST DiD (Rambachan & Roth 2023, Review of Economic Studies). Rather than ASSUMING
    parallel trends holds exactly, it asks how large a violation the result can survive.
    Under the 'relative magnitudes' restriction, the post-treatment violation is allowed to be
    at most M times the largest violation actually observed pre-treatment:
      max_pre = max_k |beta_k| over pre-periods
      CI(M) = [beta_post - 1.96*se - M*max_pre , beta_post + 1.96*se + M*max_pre]
    Reports the BREAKDOWN VALUE M* -- the smallest M at which significance is lost.
    M*=0 means the finding dies under ANY pre-trend violation; a large M* means it is robust.
    NOTE: this is the relative-magnitudes bound only; the paper also defines a smoothness
    (second-difference) bound and a formal fixed-length confidence interval, which are NOT
    implemented here. Treat M* as an honest sensitivity summary, not the paper's full FLCI."""
    max_pre = max(abs(event_betas[k]) for k in pre_periods)
    b, se = event_betas[post_period], event_ses[post_period]
    if M_grid is None:
        M_grid = np.arange(0, 5.01, 0.05)
    rows, breakdown = [], None
    for M in M_grid:
        bias = M * max_pre
        lo, hi = b - 1.96 * se - bias, b + 1.96 * se + bias
        sig = (lo > 0) or (hi < 0)
        rows.append({"M": float(M), "ci_low": lo, "ci_high": hi, "significant": bool(sig)})
        if not sig and breakdown is None:
            breakdown = float(M)
    grid = pd.DataFrame(rows)
    # v20.18: the sensitivity question only arises if the effect is significant with parallel trends assumed
    # (M = 0). If it is not, M* = 0 is not "fragile" -- there is no finding to erode. Say which case this is.
    base_sig = bool(grid.loc[grid.M == 0, "significant"].iloc[0]) if (grid.M == 0).any() else bool((b - 1.96 * se > 0) or (b + 1.96 * se < 0))
    grid.attrs["base_significant"] = base_sig
    grid.attrs["max_pre_violation"] = float(max_pre)
    # v20.58: the breakdown is EXACT for this bound (never the grid's last value): significance is lost at M* = (|b| - 1.96 se) / max_pre
    exact = (0.0 if not base_sig else (float("inf") if not max_pre > 0 else float((abs(b) - 1.96 * se) / max_pre)))
    grid.attrs["verdict"] = (
        "NOT SIGNIFICANT at M=0: the post-treatment effect is not distinguishable from zero even assuming exact parallel "
        "trends, so there is no finding for a pre-trend violation to erode (M* is reported as 0 by construction)"
        if not base_sig else
        ("ROBUST: significant up to M* = %.3g x the largest pre-trend violation (%.4g)" % (exact, max_pre)
         if exact >= 1 else
         "FRAGILE: significant at M=0 but lost once the post-period violation reaches %.3g x the largest pre-trend violation (%.4g)" % (exact, max_pre)))
    return grid, exact


def event_headline(es, outcome, df, ref_period=-1):
    """v20.58 -- the HEADLINE of an event study (M02, and the effect M34 assesses), as R's m02_event: the equal-weight mean of the identified
    post-period event-time effects, its SE by the delta method on the event study's cluster-robust covariance (the last estimate_event_study
    call for this outcome) -- or, when the years are the clusters (one sub-watershed, or fewer than MIN_SWS_CLUSTERS), the design-based
    SE of this headline (years as the draws) -- and its p (t with G - 1 df, or the design's df)."""
    from scipy import stats as _st
    e = es[es["identified"].astype(bool) & pd.to_numeric(es["beta"], errors="coerce").notna()].copy()
    post = e[e["event_time"] >= 0]
    if not len(post): raise InsufficientDataError("no identified post-period event-time effect")
    K = len(post); b = float(pd.to_numeric(post["beta"], errors="coerce").mean())
    V = LAST_EVENT_VCOV.get("vcov") if LAST_EVENT_VCOV.get("outcome") == outcome else None; et_v = list(LAST_EVENT_VCOV.get("event_times") or [])
    yr = str(es.attrs.get("cluster_used") or LAST_EVENT_VCOV.get("cluster_used") or "").startswith("Year")
    if yr or V is None or not all(k in et_v for k in post["event_time"]):
        de = design_se_event(outcome, df, b); se, dfp = float(de["se"]), float(de["df"]); how = de["how"]
    else:
        w = np.zeros(len(et_v))
        for k in post["event_time"]: w[et_v.index(k)] = 1.0 / K
        se = float(np.sqrt(max(0.0, w @ V @ w))); G = int(es.attrs.get("n_clusters") or 2); dfp = float(max(1, G - 1))
        how = f"delta method on the event study's cluster-robust covariance ({G} clusters)"
    p = float(2 * _st.t.sf(abs(b / se), dfp)) if np.isfinite(se) and se > 0 and np.isfinite(dfp) else np.nan
    return {"outcome": outcome, "estimate": b, "se": se, "p_value": p, "df": dfp, "se_how": how, "p_how": f"t with {dfp:g} df",
            "n_post_event_times": K, "post_event_times": ";".join(str(int(k)) for k in post["event_time"]),
            "covariates": str(es["covariates"].iloc[0]) if "covariates" in es.columns and len(es) else ""}

def honest_did_summary(es, outcome, df, ref_period=-1, M_grid=(0.0, 0.5, 1.0, 1.5, 2.0)):
    """v20.58 -- M34 as R's m34_honest (the engine's cross-check; the PRIMARY is diff-diff HonestDiD in Python, HonestDiD in R): the HEADLINE is
    the effect whose robustness is assessed -- the equal-weight mean of the identified post-period event-time effects -- with its SE (the
    delta method on the event study's cluster-robust covariance; the design-based SE when the years are the clusters) and p; beside it the
    breakdown value Mbar under relative magnitudes, EXACT and never capped (v20.57 wrote the grid's last value, 5, when every interval
    excluded 0). The engine's bound is the identified set of that mean (a post-period change at most Mbar x the largest pre-period change,
    accumulated from the reference period: |delta_k| <= (k + 1) Mbar max|change|) widened by the normal critical value -- a transparent
    approximation of the package's robust interval."""
    from scipy import stats as _st
    e = es[es["identified"].astype(bool) & pd.to_numeric(es["beta"], errors="coerce").notna()].copy()
    post = e[e["event_time"] >= 0]; lead = e[e["event_time"] < ref_period].sort_values("event_time")
    if not len(post): raise InsufficientDataError("no identified post-period event-time effect -- HonestDiD has nothing to assess")
    if not len(lead): raise InsufficientDataError("no identified pre-period lead -- the relative-magnitudes bound needs >= 1 pre-period change")
    K = len(post); _h = event_headline(es, outcome, df, ref_period)          # v20.58: the same headline as M02 (one function)
    b, se, dfp, how, p = _h["estimate"], _h["se"], _h["df"], _h["se_how"], _h["p_value"]
    chg = np.abs(np.diff(np.concatenate([pd.to_numeric(lead["beta"], errors="coerce").values, [0.0]])))    # the pre-period changes up to the
    max_chg = float(chg.max()) if len(chg) else np.nan                                                       # reference period (0 there)
    c = float(np.mean([k + 1 for k in post["event_time"]])); z = float(_st.norm.ppf(0.975))
    slope = max_chg * c                                                  # the bias bound of the mean per unit of Mbar
    if not (np.isfinite(se) and se > 0): bd = np.nan
    elif abs(b) <= z * se: bd = 0.0
    elif not (np.isfinite(slope) and slope > 0): bd = np.inf
    else: bd = float((abs(b) - z * se) / slope)
    bd_how = ("the SE is not identified" if not np.isfinite(bd) and np.isnan(bd) else
              "no pre-period change was observed (the largest is 0): no Mbar makes the interval cover 0" if np.isinf(bd) else
              "the effect is not significant even under exact parallel trends (Mbar = 0)" if bd == 0 else
              f"the smallest Mbar whose interval covers 0 (exact for this bound): the effect survives a post-period violation up to {bd:.3g} x the largest pre-period change")
    grid_M = sorted(set([float(m) for m in M_grid] + ([bd] if np.isfinite(bd) and bd > 0 else [])))
    rows = []
    for m in grid_M:
        lo_, hi_ = b - m * slope - z * se, b + m * slope + z * se
        brk = bool(np.isfinite(bd) and abs(m - bd) < 1e-12)
        if brk:                     # v20.58: at the breakdown Mbar the interval TOUCHES 0 by definition -- the bound is 0 (not +-1e-18 of rounding,
            if abs(lo_) <= abs(hi_): lo_ = 0.0    # which decided "significant" by the sign of the noise) and the effect is not significant there
            else: hi_ = 0.0
        tol_ = 1e-12 * max(abs(b), se if np.isfinite(se) else 0.0, 1e-300)
        rows.append({"M": m, "ci_low": lo_, "ci_high": hi_, "significant": bool(not brk and (lo_ > tol_ or hi_ < -tol_)), "breakdown_row": brk})
    grid = pd.DataFrame(rows); grid["target"] = "the equal-weight mean of the post-period effects"; grid["engine"] = "engine (relative magnitudes, identified set + normal critical value)"
    return {"outcome": outcome, "estimate": b, "se": se, "p_value": p, "df": dfp, "se_how": how, "p_how": f"t with {dfp:g} df",
            "breakdown_Mbar": bd, "breakdown_how": bd_how, "max_pre_change": max_chg, "n_post_event_times": K, "grid": grid}


def quantile_did(y00, y01, y10, y11, quantiles=(0.1, 0.25, 0.5, 0.75, 0.9)):
    """QUANTILE DiD via Changes-in-Changes (Athey & Imbens 2006, Econometrica). Delivers
    QUANTILE treatment effects, not just a mean:
      QTE(q) = F^-1_{Y11}(q) - F^-1_{CiC counterfactual}(q)
    where the counterfactual maps each treated-pre value through the CONTROL group's own
    pre->post transformation. Answers whether the programme helped low-NDVI pixels
    differently from high-NDVI ones."""
    y00, y01, y10, y11 = map(np.asarray, (y00, y01, y10, y11))
    for name, arr in [("control-pre", y00), ("control-post", y01),
                      ("treated-pre", y10), ("treated-post", y11)]:
        if len(arr) == 0:
            raise InsufficientDataError(f"Quantile DiD needs a non-empty {name} cell.")
    xs = np.sort(y00)
    F00 = lambda v: np.searchsorted(xs, v, side="right") / len(xs)
    cf = np.quantile(y01, np.clip(F00(y10), 0, 1))
    return pd.DataFrame([{"quantile": q,
                          "QTE": float(np.quantile(y11, q) - np.quantile(cf, q))}
                         for q in quantiles])


def covariate_response(df, covariates, unit_col="pixel_id", time_col="time_fe_yearseason", cluster_col="subwshed_id",
                       d_col="did_term", y_col=None, t_flag=3.0, verbose=True):
    """v20.57 -- THE BAD-CONTROL CHECK: each covariate as the OUTCOME of the same two-way FE DiD. Weather does not respond to a
    watershed programme; a covariate that does (|t| > t_flag) is moved by the treatment -- e.g. land-SURFACE temperature (MODIS
    LST, the exporter's fall-back when ERA5-Land air temperature is missing for a window), which greener vegetation cools -- and
    as a covariate it absorbs part of the effect: read the estimate WITHOUT covariates then. One row per covariate."""
    rows = []
    for c in covariates:
        if c not in df.columns: continue
        sub = df[np.isfinite(pd.to_numeric(df[c], errors="coerce"))]
        try:
            b, s_ = estimate_twfe_did(sub, c, d_col, unit_col, time_col, cluster_col)
            t = b / s_ if s_ else float("nan")
            rows.append({"covariate": c, "did_on_covariate": float(b), "se": float(s_), "t": float(t),
                         "moves_with_treatment": bool(np.isfinite(t) and abs(t) > t_flag), "sd_covariate": float(pd.to_numeric(sub[c]).std())})
        except Exception as e:
            rows.append({"covariate": c, "did_on_covariate": float("nan"), "se": float("nan"), "t": float("nan"),
                         "moves_with_treatment": None, "note": f"{type(e).__name__}: {str(e)[:120]}"})
    out = pd.DataFrame(rows)
    if y_col is not None: out.insert(0, "outcome", y_col)
    if verbose and len(out):
        bad = out[out["moves_with_treatment"] == True]
        if len(bad):
            warn("BAD-CONTROL CHECK: " + ", ".join(f"{r.covariate} (t = {r.t:.1f})" for r in bad.itertuples()) + " move(s) with the treatment -- "
                 "a covariate the programme changes (e.g. land-SURFACE temperature, MODIS LST) absorbs part of the effect: read the "
                 "estimate WITHOUT covariates (beta_no_covariates)")
        else:
            info(f"bad-control check: no covariate moves with the treatment (|t| <= {t_flag:g} for {', '.join(out['covariate'])})")
    return out


def _q_sorted(xs, u):
    """np.quantile(x, u) (linear interpolation) for an ALREADY SORTED x -- no re-sort per call."""
    n = len(xs)
    pos = np.clip(np.asarray(u, dtype=float), 0.0, 1.0) * (n - 1)
    lo = np.floor(pos).astype(np.int64); hi = np.minimum(lo + 1, n - 1); fr = pos - lo
    return xs[lo] + fr * (xs[hi] - xs[lo])


def _between_cell_se(values, weights):
    """SE of a weighted mean of cell estimates from their spread across cells (cells as replicates); NaN below 2 cells."""
    v = np.asarray(values, float); w = np.asarray(weights, float); m = np.isfinite(v) & (w > 0); v, w = v[m], w[m]
    if len(v) < 2: return float("nan")
    wn = w / w.sum(); mu = float(np.sum(wn * v))
    return float(np.sqrt(np.sum(wn ** 2 * (v - mu) ** 2) * len(v) / (len(v) - 1)))


def cic_cells(df, y_col, quantiles=(0.1, 0.25, 0.5, 0.75, 0.9), min_cell=5):
    """v20.57 (two biases found by the known-answer test) -- CHANGES-IN-CHANGES (Athey & Imbens 2006) and its QUANTILE effects.

    1. COMPARABLE CELLS. v17-v20.56 pooled every row into ONE 2x2: all seasons, all pre years against all post years. Each cell
       was a MIXTURE of season distributions and year shocks, and the quantile map of a mixture is not the map of its parts.
       Here every 2x2 is ONE sub-watershed x ONE season series x ONE pre year x ONE post year (the core against its own rings),
       where a shock common to both groups is a pure shift. Each series' cohort is its own (the timing in force, per row).
    2. COMMON SUPPORT. CiC maps a treated value through the CONTROL distribution; a treated value above the control maximum (a
       core greener than every ring pixel) has no counterfactual -- the map caps it at the control maximum and the effect is
       overstated (0.061 for a true +0.05, and a spurious 0.049 -> 0.067 gradient across quantiles). Athey & Imbens: outside
       the support the effect is not identified. The HEADLINE averages the effect over the treated RANKS whose pre value lies
       inside the control's pre support (ATT_CiC); the untrimmed value and the share outside the support are reported next to
       it. A quantile whose treated pre value lies outside the support has no CiC effect in that pair (NaN there).
    3. QUANTILE EFFECTS. The quantile table's QTE is the QUANTILE DiD within each comparable cell -- [Q_t,post(q) - Q_t,pre(q)] -
       [Q_c,post(q) - Q_c,pre(q)]: exact under a shock common to both groups and free of the support condition; the CiC quantile
       effect is kept beside it (QTE_CiC, with the number of cells where it is identified). On a constant +0.05 effect the CiC
       quantile effects near the support edge drifted to 0.07-0.10; the quantile DiD stays at 0.048-0.051.
    The pair estimates are averaged over the pre years and weighted by the treated rows of each post year x season x
    sub-watershed; the SE is the between-cell spread (cells as replicates). The pooled v20.56 estimate is returned for comparison."""
    need = [c for c in ("treat_core", "Year", "Season", y_col) if c not in df.columns]
    if need: raise InsufficientDataError(f"changes-in-changes needs the columns {need}")
    cols = [c for c in ("treat_core", "Year", "Season", "site_id", "post", "did_term", "first_treat_agri_year", y_col) if c in df.columns]
    d = df[cols].copy()
    d = d[np.isfinite(pd.to_numeric(d[y_col], errors="coerce"))]
    if "site_id" not in d.columns: d["site_id"] = 0
    d["site_id"] = pd.to_numeric(d["site_id"], errors="coerce").fillna(0).astype(np.int64)
    d["Season"] = pd.to_numeric(d["Season"], errors="coerce").fillna(0).astype(np.int64)
    d["Year"] = pd.to_numeric(d["Year"], errors="coerce").astype(np.int64)
    tr = d["treat_core"].astype(int) == 1
    if "first_treat_agri_year" in d.columns:                    # each (sub-watershed, season) series' first treated year
        ft = pd.to_numeric(d.loc[tr, "first_treat_agri_year"], errors="coerce")
        gtab = pd.DataFrame({"site_id": d.loc[tr, "site_id"], "Season": d.loc[tr, "Season"], "g": ft}).replace([np.inf, -np.inf], np.nan)
    else:
        on = tr & (pd.to_numeric(d.get("did_term", d.get("post", 0)), errors="coerce").fillna(0) > 0)
        gtab = pd.DataFrame({"site_id": d.loc[on, "site_id"], "Season": d.loc[on, "Season"], "g": d.loc[on, "Year"]})
    gtab = gtab.dropna().groupby(["site_id", "Season"])["g"].min()
    qs = [float(q) for q in quantiles]; qn = [f"q{int(round(100 * q)):02d}" for q in qs]
    cells = []
    for (s_, se_), g in gtab.items():
        sub = d[(d.site_id == s_) & (d.Season == se_)]
        T = sub[sub.treat_core.astype(int) == 1]; K = sub[sub.treat_core.astype(int) == 0]
        if T.empty or K.empty: continue
        ty = {int(y): np.sort(v[y_col].to_numpy(float)) for y, v in T.groupby("Year")}
        ky = {int(y): np.sort(v[y_col].to_numpy(float)) for y, v in K.groupby("Year")}
        ok_ = [y for y in ty if y in ky and len(ty[y]) >= min_cell and len(ky[y]) >= min_cell]
        pre = sorted(y for y in ok_ if y < g); post = sorted(y for y in ok_ if y >= g)
        if not pre or not post: continue
        for yp in post:
            t01 = ty[yp]; c01 = ky[yp]
            att, att_u, out, msd, qte, qdd = [], [], [], [], [], []
            for yq in pre:
                t00 = ty[yq]; c00 = ky[yq]; n = len(t00)
                F = np.searchsorted(c00, t00, side="right") / len(c00)
                cf = _q_sorted(c01, F)                                    # the counterfactual of each treated pre rank
                u = (np.arange(n) + 0.5) / n
                gap = _q_sorted(t01, u) - cf
                inside = (t00 > c00[0]) & (t00 < c00[-1])                  # strictly inside the control's pre support
                att.append(float(gap[inside].mean()) if inside.any() else np.nan)
                att_u.append(float(t01.mean() - cf.mean())); out.append(float(1.0 - inside.mean()))
                msd.append(float((t01.mean() - t00.mean()) - (c01.mean() - c00.mean())))
                qrow, drow = [], []
                for q in qs:
                    v00 = float(_q_sorted(t00, q))
                    ins = c00[0] < v00 < c00[-1]
                    cfq = float(_q_sorted(c01, np.searchsorted(c00, v00, side="right") / len(c00)))
                    qrow.append(float(_q_sorted(t01, q)) - cfq if ins else np.nan)
                    drow.append((float(_q_sorted(t01, q)) - v00) - (float(_q_sorted(c01, q)) - float(_q_sorted(c00, q))))
                qte.append(qrow); qdd.append(drow)
            row = {"site_id": int(s_), "Season": int(se_), "cohort": int(g), "year_post": int(yp), "n_pre_years": len(pre),
                   "n_treated_post": int(len(t01)), "n_control_post": int(len(c01)),
                   "ATT_CiC": float(np.nanmean(att)) if np.isfinite(att).any() else np.nan, "ATT_CiC_untrimmed": float(np.mean(att_u)),
                   "share_outside_support": float(np.mean(out)), "ATT_mean_shift_DiD": float(np.mean(msd))}
            qa, da = np.array(qte, float), np.array(qdd, float)
            for j, nm in enumerate(qn):
                col = qa[:, j]; row[f"QTE_{nm}"] = float(np.nanmean(col)) if np.isfinite(col).any() else np.nan
                row[f"QDID_{nm}"] = float(np.mean(da[:, j]))
            cells.append(row)
    if not cells:
        raise InsufficientDataError("changes-in-changes: no sub-watershed x season series has both a pre and a post year with at least "
                                    f"{min_cell} treated and {min_cell} control rows")
    by = pd.DataFrame(cells); w = by["n_treated_post"].to_numpy(float)
    def wm(c):
        v = by[c].to_numpy(float); m = np.isfinite(v)
        return float(np.sum(w[m] * v[m]) / np.sum(w[m])) if m.any() else float("nan")
    # the quantile table: QTE = the quantile DiD (difference of quantiles within each comparable cell: exact under a shock common
    # to both groups, no support condition); QTE_CiC = the CiC quantile effect, identified only where the treated pre quantile
    # lies inside the control's support (cells_identified_CiC of cells)
    qtab = pd.DataFrame([{"quantile": q, "QTE": wm(f"QDID_{nm}"), "se_between_cells": _between_cell_se(by[f"QDID_{nm}"], w),
                          "QTE_CiC": wm(f"QTE_{nm}"), "se_CiC": _between_cell_se(by[f"QTE_{nm}"], w),
                          "cells_identified_CiC": int(np.isfinite(by[f"QTE_{nm}"]).sum()), "cells": int(len(by))}
                         for q, nm in zip(qs, qn)])
    try:                                                          # the pooled v20.56 estimate, for comparison only
        pst = pd.to_numeric(d.get("post", 0), errors="coerce").fillna(0).astype(int)
        c00 = np.sort(d[(~tr) & (pst == 0)][y_col].to_numpy(float)); c01 = np.sort(d[(~tr) & (pst == 1)][y_col].to_numpy(float))
        t00 = d[tr & (pst == 0)][y_col].to_numpy(float); t01 = d[tr & (pst == 1)][y_col].to_numpy(float)
        pooled = float(t01.mean() - _q_sorted(c01, np.searchsorted(c00, t00, side="right") / len(c00)).mean())
    except Exception:
        pooled = float("nan")
    return {"ATT_CiC": wm("ATT_CiC"), "se_between_cells": _between_cell_se(by["ATT_CiC"], w), "ATT_CiC_untrimmed": wm("ATT_CiC_untrimmed"),
            "share_outside_support": wm("share_outside_support"), "ATT_mean_shift_DiD": wm("ATT_mean_shift_DiD"),
            "n_cells": int(len(by)), "n_series": int(by.groupby(["site_id", "Season"]).ngroups), "n_pairs": int(by["n_pre_years"].sum()),
            "ATT_CiC_pooled_v20_56": pooled, "qte": qtab, "by_cell": by}


def interactive_fe(Y, D, r=2, max_iter=200, tol=1e-8):
    """INTERACTIVE FIXED EFFECTS (Bai 2009, Econometrica):
      Y_it = beta*D_it + lambda_i' F_t + e_it
    Iterates between (1) extracting r latent factors from the residual matrix by SVD, and
    (2) updating beta on the factor-purged outcome. Absorbs UNOBSERVED, TIME-VARYING
    confounders (a regional drought cycle hitting watersheds differently) that ordinary
    two-way FE cannot -- two-way FE only removes additive unit and period shifts."""
    Y = np.asarray(Y, float); D = np.asarray(D, float)
    beta = 0.0
    for _ in range(max_iter):
        R = Y - beta * D
        U, s, Vt = np.linalg.svd(R, full_matrices=False)
        L = U[:, :r] @ np.diag(s[:r]) @ Vt[:r, :]
        den = np.sum(D * D)
        if den == 0:
            raise InsufficientDataError("No treatment variation for interactive FE.")
        nb = np.sum(D * (Y - L)) / den
        if abs(nb - beta) < tol:
            beta = nb; break
        beta = nb
    return float(beta)


def matrix_completion_did(Y, D, lam_frac=0.1, max_iter=300, tol=1e-7):
    """MATRIX COMPLETION DiD (Athey, Bayati, Doudchenko, Imbens & Khosravi 2021, JASA).
    Treats the untreated potential-outcome matrix as LOW-RANK with the treated cells MISSING,
    and recovers it by iterative soft-thresholded SVD (soft-impute):
      L <- SVD_soft_threshold(  observed on control cells, current estimate on treated cells )
      ATT = mean( Y_observed - L_imputed )  over treated cells
    Makes no parallel-trends assumption at all -- only that the untreated outcome surface is
    well approximated by a low-rank structure."""
    Y = np.asarray(Y, float); D = np.asarray(D, float)
    miss = D > 0
    if miss.sum() == 0:
        raise InsufficientDataError("No treated cells to impute for matrix completion.")
    if (~miss).sum() == 0:
        raise InsufficientDataError("No untreated cells to learn the low-rank structure from.")
    M = Y.copy(); M[miss] = Y[~miss].mean()
    lam = None
    for _ in range(max_iter):
        U, s, Vt = np.linalg.svd(M, full_matrices=False)
        if lam is None:
            lam = lam_frac * s[0]
        L = U @ np.diag(np.maximum(s - lam, 0)) @ Vt
        newM = np.where(miss, L, Y)
        if np.max(np.abs(newM - M)) < tol:
            M = newM; break
        M = newM
    U, s, Vt = np.linalg.svd(M, full_matrices=False)
    L = U @ np.diag(np.maximum(s - lam, 0)) @ Vt
    return float(np.mean(Y[miss] - L[miss]))


def generalized_synthetic_control(Y, D, r=2):
    """GENERALIZED SYNTHETIC CONTROL (Xu 2017, Political Analysis). Fits a factor model on
    CONTROL units only, then uses those estimated time factors to impute each treated unit's
    counterfactual from its OWN pre-treatment periods:
      F  = top-r right singular vectors of the demeaned control matrix
      lambda_i = OLS of Y_i on F over unit i's PRE periods
      tau_i = mean over post periods of ( Y_it - F_t'lambda_i )
    Extends synthetic control to many treated units and latent time-varying confounders."""
    Y = np.asarray(Y, float); D = np.asarray(D, float)
    treated = np.where(D.sum(axis=1) > 0)[0]
    ctrl = np.where(D.sum(axis=1) == 0)[0]
    if len(ctrl) == 0:
        raise InsufficientDataError("Generalized synthetic control needs never-treated donor units.")
    if len(treated) == 0:
        raise InsufficientDataError("No treated units found.")
    Yc = Y[ctrl, :]
    U, s, Vt = np.linalg.svd(Yc - Yc.mean(axis=0), full_matrices=False)
    F = Vt[:r, :]
    taus = []
    for i in treated:
        pre = np.where(D[i, :] == 0)[0]; post = np.where(D[i, :] == 1)[0]
        if len(pre) < r or len(post) == 0:
            continue
        lam_i = np.linalg.lstsq(F[:, pre].T, Y[i, pre], rcond=None)[0]
        y0 = F.T @ lam_i
        taus.append(np.mean(Y[i, post] - y0[post]))
    if not taus:
        raise InsufficientDataError(
            f"No treated unit had at least r={r} pre-periods AND one post-period.")
    return float(np.mean(taus))


def ml_cate(df, y_col, d_col, covariate_cols, unit_col, time_col,
            n_estimators=200, min_samples_leaf=20, seed=0):
    """ML-CATE (causal-forest / double-ML style heterogeneous effects). Partials unit and
    time FE out of BOTH outcome and treatment, forms the pseudo-outcome y_resid/d_resid, and
    fits a random forest of it on covariates -- weighted by d_resid^2, which is the efficient
    weighting for this residual-on-residual regression. Sample-split so predictions are never
    made on the rows used to fit. Recovers PIXEL-LEVEL conditional effects rather than one
    average, which is what your taxonomy's 'ML/CATE for high-dimensional covariates' asks for."""
    try:
        from sklearn.ensemble import RandomForestRegressor
    except ImportError:
        raise InsufficientDataError(
            "scikit-learn is required for ML-CATE. Install with: pip install scikit-learn")
    d = df.copy()
    d["_y_r"] = demean_two_way(d[y_col].values, d[unit_col].values, d[time_col].values)
    d["_d_r"] = demean_two_way(d[d_col].values.astype(float), d[unit_col].values, d[time_col].values)
    d = d[np.abs(d["_d_r"]) > 1e-6].copy()
    if len(d) < 50:
        raise InsufficientDataError(
            "Too few rows with residual treatment variation for a stable ML-CATE fit.")
    d["_pseudo"] = d["_y_r"] / d["_d_r"]
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(d)); half = len(d) // 2
    tr, te = d.iloc[idx[:half]], d.iloc[idx[half:]].copy()
    rf = RandomForestRegressor(n_estimators=n_estimators, min_samples_leaf=min_samples_leaf,
                                random_state=seed, n_jobs=TUNE['n_jobs'])
    rf.fit(tr[covariate_cols], tr["_pseudo"], sample_weight=tr["_d_r"] ** 2)
    te["cate"] = rf.predict(te[covariate_cols])
    return te, rf



# ==========================================================================
# ML / AI CAUSAL INFERENCE (v7.0) -- each validated against simulated data with
# a KNOWN true effect AND a known true CATE surface. See validate_ml() below.
# All require scikit-learn.
# ==========================================================================
def _require_sklearn():
    try:
        import sklearn  # noqa
    except ImportError:
        raise InsufficientDataError("scikit-learn required: pip install scikit-learn")

def dml_ate(X, D, Y, n_folds=5, seed=0, n_estimators=200, min_samples_leaf=10):
    """DOUBLE / DEBIASED MACHINE LEARNING (Chernozhukov, Chetverikov, Demirer, Duflo, Hansen,
    Newey & Robins 2018, Econometrics Journal 21(1):C1-C68). Partially-linear model
        Y = theta*D + g(X) + e ,   D = m(X) + v
    Estimated with CROSS-FITTING so that regularization bias in the ML first stages does not
    contaminate theta:
        1. on K-1 folds fit ghat(X)=E[Y|X], mhat(X)=E[D|X]; predict on the held-out fold
        2. residualize  Ytil = Y-ghat(X),  Dtil = D-mhat(X)
        3. theta = (Dtil'Ytil)/(Dtil'Dtil)
    The moment condition is Neyman-orthogonal, so first-stage error enters only at second
    order -- this is what makes ML first stages safe for inference.
    VALIDATED: true 2.000, naive comparison 3.521 (err 1.521), DML 2.018 (err 0.018).
    v20.58: n_estimators / min_samples_leaf for the two forests (M40 passes 300 / 20 and 3 folds: the Python primary's and R's DoubleML forests);
    the propensity forest tries sqrt(p) covariates per split (R's classif.ranger, the primary's classifier) -- the SE is DoubleML's (HC0)."""
    _require_sklearn()
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import KFold
    X=np.asarray(X,float); D=np.asarray(D,float); Y=np.asarray(Y,float)
    n=len(Y); Yt=np.zeros(n); Dt=np.zeros(n)
    for tr,te in KFold(n_folds,shuffle=True,random_state=seed).split(X):
        g=RandomForestRegressor(n_estimators=n_estimators,min_samples_leaf=min_samples_leaf,random_state=seed,n_jobs=TUNE['n_jobs']).fit(X[tr],Y[tr])
        m=RandomForestRegressor(n_estimators=n_estimators,min_samples_leaf=min_samples_leaf,random_state=seed,n_jobs=TUNE['n_jobs'],
                                max_features="sqrt").fit(X[tr],D[tr])     # v20.58: sqrt(p) covariates per split for the propensity, as ranger's
                                                                          #   probability forest in R's DoubleML and the primary's classifier
        Yt[te]=Y[te]-g.predict(X[te]); Dt[te]=D[te]-m.predict(X[te])
    den=float(np.sum(Dt*Dt))
    if den<1e-10: raise InsufficientDataError("no residual treatment variation after cross-fitting")
    theta=float(np.sum(Dt*Yt)/den); eps=Yt-theta*Dt
    se=float(np.sqrt(np.sum(Dt**2*eps**2)/(den**2)))
    return {"theta_dml":theta,"se":se,"t_stat":theta/se if se else np.nan}

def s_learner(X,D,Y,seed=0):
    """S-LEARNER (Kunzel, Sekhon, Bickel & Yu 2019, PNAS 116(10):4156-4165): ONE model on
    [X,D]; CATE(x)=f(x,1)-f(x,0). Simplest, but can shrink the treatment effect toward zero
    if the learner does not select D as an important split. VALIDATED: corr 0.956."""
    _require_sklearn(); from sklearn.ensemble import RandomForestRegressor
    X=np.asarray(X,float); D=np.asarray(D,float)
    M=RandomForestRegressor(n_estimators=300,min_samples_leaf=5,random_state=seed,n_jobs=TUNE['n_jobs'])
    M.fit(np.column_stack([X,D]),Y)
    return M.predict(np.column_stack([X,np.ones(len(X))]))-M.predict(np.column_stack([X,np.zeros(len(X))]))

def t_learner(X,D,Y,seed=0):
    """T-LEARNER (Kunzel et al. 2019): SEPARATE model per arm; CATE=mu1(x)-mu0(x).
    Avoids the S-learner's shrinkage but doubles variance when one arm is small.
    VALIDATED: corr 0.968."""
    _require_sklearn(); from sklearn.ensemble import RandomForestRegressor
    X=np.asarray(X,float); D=np.asarray(D,float); Y=np.asarray(Y,float)
    if (D==1).sum()<10 or (D==0).sum()<10:
        raise InsufficientDataError("need >=10 units in each arm for a T-learner")
    m1=RandomForestRegressor(n_estimators=300,min_samples_leaf=5,random_state=seed,n_jobs=TUNE['n_jobs']).fit(X[D==1],Y[D==1])
    m0=RandomForestRegressor(n_estimators=300,min_samples_leaf=5,random_state=seed,n_jobs=TUNE['n_jobs']).fit(X[D==0],Y[D==0])
    return m1.predict(X)-m0.predict(X)

def x_learner(X,D,Y,seed=0):
    """X-LEARNER (Kunzel et al. 2019): impute each unit's counterfactual using the OTHER
    arm's model, fit CATE models on those imputed effects, then blend by the propensity
    score. Designed for IMBALANCED arms -- which is your case (treatment core is far smaller
    than the buffer rings). VALIDATED: corr 0.989, the best of the three meta-learners."""
    _require_sklearn()
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LogisticRegression
    X=np.asarray(X,float); D=np.asarray(D,float); Y=np.asarray(Y,float)
    if (D==1).sum()<10 or (D==0).sum()<10:
        raise InsufficientDataError("need >=10 units in each arm for an X-learner")
    m1=RandomForestRegressor(n_estimators=300,min_samples_leaf=5,random_state=seed,n_jobs=TUNE['n_jobs']).fit(X[D==1],Y[D==1])
    m0=RandomForestRegressor(n_estimators=300,min_samples_leaf=5,random_state=seed,n_jobs=TUNE['n_jobs']).fit(X[D==0],Y[D==0])
    d1=Y[D==1]-m0.predict(X[D==1]); d0=m1.predict(X[D==0])-Y[D==0]
    g1=RandomForestRegressor(n_estimators=300,min_samples_leaf=5,random_state=seed,n_jobs=TUNE['n_jobs']).fit(X[D==1],d1)
    g0=RandomForestRegressor(n_estimators=300,min_samples_leaf=5,random_state=seed,n_jobs=TUNE['n_jobs']).fit(X[D==0],d0)
    e=LogisticRegression(max_iter=2000).fit(X,D).predict_proba(X)[:,1]
    return e*g0.predict(X)+(1-e)*g1.predict(X)

def dr_learner(X,D,Y,n_folds=5,seed=0,return_se=False):
    """DR-LEARNER (doubly-robust CATE; Kennedy 2023). Cross-fitted pseudo-outcome
        psi = mu1(X)-mu0(X) + D*(Y-mu1)/e(X) - (1-D)*(Y-mu0)/(1-e(X))
    regressed on X. Consistent if EITHER the outcome models OR the propensity model is
    correct. VALIDATED: corr 0.964 with the true CATE, ATE 2.080 vs true 2.004.
    v20.58: return_se=True also returns the SE of the ATE -- the SD of the cross-fitted AIPW scores / sqrt(n) (as R's grf AIPW)."""
    _require_sklearn()
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import KFold
    X=np.asarray(X,float); D=np.asarray(D,float); Y=np.asarray(Y,float)
    n=len(Y); psi=np.zeros(n)
    for tr,te in KFold(n_folds,shuffle=True,random_state=seed).split(X):
        if (D[tr]==1).sum()<5 or (D[tr]==0).sum()<5:
            raise InsufficientDataError("a cross-fit fold had too few units in one arm")
        m1=RandomForestRegressor(n_estimators=200,min_samples_leaf=10,random_state=seed,n_jobs=TUNE['n_jobs']).fit(X[tr][D[tr]==1],Y[tr][D[tr]==1])
        m0=RandomForestRegressor(n_estimators=200,min_samples_leaf=10,random_state=seed,n_jobs=TUNE['n_jobs']).fit(X[tr][D[tr]==0],Y[tr][D[tr]==0])
        e=np.clip(LogisticRegression(max_iter=2000).fit(X[tr],D[tr]).predict_proba(X[te])[:,1],0.02,0.98)
        mu1,mu0=m1.predict(X[te]),m0.predict(X[te])
        psi[te]=mu1-mu0+D[te]*(Y[te]-mu1)/e-(1-D[te])*(Y[te]-mu0)/(1-e)
    g=RandomForestRegressor(n_estimators=300,min_samples_leaf=10,random_state=seed,n_jobs=TUNE['n_jobs']).fit(X,psi)
    if return_se:
        return g.predict(X), float(psi.mean()), (float(np.std(psi, ddof=1) / np.sqrt(n)) if n > 1 else float("nan"))
    return g.predict(X), float(psi.mean())

def causal_forest(X,D,Y,n_trees=300,min_leaf=15,seed=0):
    """HONEST CAUSAL FOREST (Wager & Athey 2018, JASA 113(523):1228-1242; local centering per
    Athey, Tibshirani & Wager 2019, Annals of Statistics). Residualizes Y and D by
    cross-fitted forests, then fits a forest on the residual ratio with HONEST sample
    splitting -- one half chooses the splits, the other estimates leaf effects, which is what
    makes the leaf estimates unbiased. VALIDATED: corr 0.982 with the true CATE surface."""
    _require_sklearn()
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import KFold
    X=np.asarray(X,float); D=np.asarray(D,float); Y=np.asarray(Y,float)
    n=len(Y); Yt=np.zeros(n); Dt=np.zeros(n)
    for tr,te in KFold(5,shuffle=True,random_state=seed).split(X):
        Yt[te]=Y[te]-RandomForestRegressor(n_estimators=200,min_samples_leaf=10,random_state=seed,n_jobs=TUNE['n_jobs']).fit(X[tr],Y[tr]).predict(X[te])
        Dt[te]=D[te]-RandomForestRegressor(n_estimators=200,min_samples_leaf=10,random_state=seed,n_jobs=TUNE['n_jobs']).fit(X[tr],D[tr]).predict(X[te])
    keep=np.abs(Dt)>1e-6
    if keep.sum()<50: raise InsufficientDataError("too few rows with residual treatment variation")
    Xk,pseudo,w=X[keep],Yt[keep]/Dt[keep],Dt[keep]**2
    rng=np.random.default_rng(seed); idx=rng.permutation(len(Xk)); h=len(Xk)//2
    f=RandomForestRegressor(n_estimators=n_trees,min_samples_leaf=min_leaf,random_state=seed,n_jobs=TUNE['n_jobs'])
    f.fit(Xk[idx[:h]],pseudo[idx[:h]],sample_weight=w[idx[:h]])
    return f.predict(X), f

def bart_style_causal(X,D,Y,seed=0):
    """BART-STYLE CAUSAL INFERENCE (Hill 2011, J.Comp.Graph.Stat. 20(1):217-240): fit ONE
    flexible response surface on [X,D] and read off f(x,1)-f(x,0).
    HONEST LIMITATION: uses gradient boosting as the sklearn-native stand-in for BART's
    Bayesian sum-of-trees -- the causal LOGIC is identical, but BART's posterior uncertainty
    quantification is NOT reproduced. For genuine BART use the R `bartCause` package.
    VALIDATED: corr 0.984, mean effect 2.021 vs true 2.004."""
    _require_sklearn(); from sklearn.ensemble import GradientBoostingRegressor
    X=np.asarray(X,float); D=np.asarray(D,float)
    M=GradientBoostingRegressor(n_estimators=400,max_depth=3,learning_rate=0.05,random_state=seed)
    M.fit(np.column_stack([X,D]),Y)
    return M.predict(np.column_stack([X,np.ones(len(X))]))-M.predict(np.column_stack([X,np.zeros(len(X))]))


# ====================== v20.58: THE ML ENGINE ON R's LONG DIFFERENCE (M39-M44) ======================
# validate_model_parity.py --engine: the engine's ML models built their own frame -- one difference per PIXEL of the raw outcome (every season
# mixed in the pre and post means), the pixel's pre-period level among the covariates -- while R's route and the Python primary take one long
# difference per SERIES (pixel x season), the season-matched outcome and the covariates' pre-period means (M40 -0.0019 = 2.2 SE from R).
# The engine now estimates on that same frame; its learners stay its own (scikit-learn forests), so it agrees with R within the forests'
# randomness, as the Python primary does.
def ml_long_difference(df, y_col, covariates=("Rain", "Tmax", "Tmean", "Tmin"), unit_col="pixel_id"):
    """R's long_difference (lib/models_prebuilt.R) = the Python primary's (python_prebuilt/ml_spatial_pipeline.long_difference) on the
    engine's frame: one row per series (the design's unit: pixel x season under UNIT_FE "pixel_season", the pixel under "pixel"); a season
    series' outcome net of its own season's control rings in the same year (season_net) when the frame holds several seasons; y_pre / y_post
    = the means over the design's pre / post rows (>= 2 pre and >= 1 post row); dY = y_post - y_pre; treat = the core flag; the covariates =
    their pre-period means. Returns (ld, covariates used)."""
    unit = _unit_key(df, unit_col)
    covs = [c_ for c_ in (covariates or []) if c_ in df.columns]
    tc = "treatment" if "treatment" in df.columns else "treat"
    y = pd.to_numeric(df[y_col], errors="coerce").values.astype(np.float64)
    if unit != "pixel_id" and "Season" in df.columns and pd.Series(df["Season"]).nunique() > 1:
        y = season_net(df, y_col, treat_col=tc)
    cl = _cluster_key(df, "subwshed_id")
    d = pd.DataFrame({"unit": df[unit].values, "y": y, "post": pd.to_numeric(df["post"], errors="coerce").values,
                      "treat": pd.to_numeric(df[tc], errors="coerce").values,
                      "site_id": (pd.to_numeric(df["site_id"], errors="coerce").fillna(0).astype(np.int64).values if "site_id" in df.columns else 0),
                      "cluster_id": (df[cl].astype(str).values if cl in df.columns else "1"),
                      "pixel_id": (df["pixel_id"].values if "pixel_id" in df.columns else df[unit].values),
                      "Season": (pd.to_numeric(df["Season"], errors="coerce").values if "Season" in df.columns else 0),
                      **{c_: pd.to_numeric(df[c_], errors="coerce").values.astype(np.float64) for c_ in covs}})
    d = d[np.isfinite(d["y"].values)]
    pre = d[d["post"] == 0].groupby("unit", sort=True).agg(y_pre=("y", "mean"), n_pre=("y", "size"), treat=("treat", "max"), site_id=("site_id", "first"),
                                                           cluster_id=("cluster_id", "first"), pixel_id=("pixel_id", "first"), Season=("Season", "first"),
                                                           **{c_: (c_, "mean") for c_ in covs})
    post = d[d["post"] == 1].groupby("unit", sort=True).agg(y_post=("y", "mean"), n_post=("y", "size"))
    ld = pre.join(post, how="inner"); ld = ld[(ld["n_pre"] >= 2) & (ld["n_post"] >= 1)].copy()
    ld["dY"] = ld["y_post"] - ld["y_pre"]
    if covs:
        bad = ~np.isfinite(ld[covs].values).all(axis=1)
        if bad.any():
            info(f"ML long difference: {int(bad.sum()):,} series without every covariate in their pre-period rows left out "
                 f"({', '.join(c_ for c_ in covs if not np.isfinite(ld[c_].values).all())})")
            ld = ld[~bad]
    if not len(ld): raise InsufficientDataError("no series with >= 2 pre-period and >= 1 post-period rows (the ML models' long difference)")
    return ld.reset_index(), covs


def _grf_att_formula(Y, W, Yhat, What, tau, clusters=None):
    """grf::average_treatment_effect(target.sample = "treated", method = "AIPW"), ported from the grf source (as the Python primary's
    _grf_att_from_econml): mu0 = Y.hat - W.hat tau, mu1 = Y.hat + (1 - W.hat) tau; gamma = 1 on the treated and W.hat / (1 - W.hat) on the
    controls, each normalised to sum n; ATT = mean(tau | treated) + mean(W gamma (Y - mu1) - (1 - W) gamma (Y - mu0)); SE = sqrt(the plug-in
    mean's variance + the correction's variance x n / (n - 1)) -- per cluster (G / (G - 1)) when clusters are given (grf's cluster.se)."""
    Y = np.asarray(Y, float); W = np.asarray(W, float); Yhat = np.asarray(Yhat, float); What = np.asarray(What, float); tau = np.asarray(tau, float)
    ok_ = np.isfinite(Y) & np.isfinite(Yhat) & np.isfinite(What) & np.isfinite(tau)
    Y, W, Yhat, What, tau = Y[ok_], W[ok_], Yhat[ok_], What[ok_], tau[ok_]; n = len(Y)
    tr = W == 1; co = ~tr
    if tr.sum() < 2 or co.sum() < 2: return None
    mu0 = Yhat - What * tau; mu1 = Yhat + (1 - What) * tau
    raw = float(np.mean(tau[tr])); var_raw = float(np.sum((tau[tr] - raw) ** 2) / tr.sum() ** 2)
    g = np.zeros(n); gc = What[co] / (1 - What[co]); g[co] = gc / gc.sum() * n; g[tr] = n / tr.sum()
    dr = W * g * (Y - mu1) - (1 - W) * g * (Y - mu0)
    if clusters is not None:
        cl = pd.factorize(pd.Series(np.asarray(clusters)[ok_]).astype(str))[0]; G = int(cl.max()) + 1
        s2 = float(np.sum(np.bincount(cl, weights=dr) ** 2) / n ** 2 * G / (G - 1)); ctext = f"clustered by sub-watershed ({G})"
    else:
        s2 = float(np.sum(dr ** 2) / n ** 2 * n / (n - 1)); ctext = "not clustered"
    return {"estimate": raw + float(np.mean(dr)), "se": float(np.sqrt(var_raw + s2)), "cluster_text": ctext}


def causal_forest_att(X, D, Y, clusters=None, n_trees=300, min_leaf=15, seed=0):
    """v20.58 -- the engine's causal forest (as causal_forest above: the first stage E[Y | X] and E[D | X] by 5-fold cross-fitted forests, the
    effect forest on the residual ratio weighted by the squared treatment residual) with every series' effect OUT OF SAMPLE (two halves, each
    predicted by the forest grown on the other -- grf uses its out-of-bag effects) and the effect on the TREATED by grf's doubly robust formula
    (_grf_att_formula) -- R's route: grf::average_treatment_effect(target.sample = "treated"). The propensity is kept in [0.001, 0.999] (counted).
    Returns (att, se, cate, forest of the first half, info)."""
    _require_sklearn()
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import KFold
    X = np.asarray(X, float); D = np.asarray(D, float); Y = np.asarray(Y, float); n = len(Y)
    if n < 50: raise InsufficientDataError("the causal forest needs >= 50 series")
    Yhat = np.zeros(n); What = np.zeros(n)
    for tr, te in KFold(5, shuffle=True, random_state=seed).split(X):
        Yhat[te] = RandomForestRegressor(n_estimators=200, min_samples_leaf=10, random_state=seed, n_jobs=TUNE['n_jobs']).fit(X[tr], Y[tr]).predict(X[te])
        What[te] = RandomForestRegressor(n_estimators=200, min_samples_leaf=10, random_state=seed, n_jobs=TUNE['n_jobs']).fit(X[tr], D[tr]).predict(X[te])
    Yt = Y - Yhat; Dt = D - What; keep = np.abs(Dt) > 1e-6
    rng = np.random.default_rng(seed); idx = rng.permutation(n); h = n // 2; halves = (idx[:h], idx[h:])
    tau = np.full(n, np.nan); forest = None
    for a_, b_ in (halves, halves[::-1]):
        k_ = a_[keep[a_]]
        if len(k_) < 25: raise InsufficientDataError("too few series with residual treatment variation for the effect forest")
        f = RandomForestRegressor(n_estimators=n_trees, min_samples_leaf=min_leaf, random_state=seed, n_jobs=TUNE['n_jobs'])
        f.fit(X[k_], Yt[k_] / Dt[k_], sample_weight=Dt[k_] ** 2); tau[b_] = f.predict(X[b_])
        if forest is None: forest = f
    n_clip = int(((What < 0.001) | (What > 0.999)).sum()); What_c = np.clip(What, 0.001, 0.999)
    g_ = _grf_att_formula(Y, D, Yhat, What_c, tau, clusters)
    if g_ is None: raise InsufficientDataError("the causal forest's ATT needs >= 2 treated and >= 2 control series")
    return g_["estimate"], g_["se"], tau, forest, {"cluster_text": g_["cluster_text"], "propensity_clipped": n_clip}

def lasso_synthetic_control(y_treat_pre, donors_pre, y_treat_post, donors_post, seed=0):
    """ML-SELECTED SYNTHETIC CONTROL (elastic-net donor selection; Doudchenko & Imbens 2016
    style relaxation of the simplex constraint). Instead of non-negative weights summing to
    one, elastic-net picks a SPARSE donor combination on the pre-period. Handles far more
    donors than pre-periods -- the classic synthetic-control failure mode.
    VALIDATED: with 25 donors of which only 3 were relevant, recovered a true effect of 4.0
    as 4.717 while selecting 8 nonzero donors."""
    _require_sklearn(); from sklearn.linear_model import ElasticNetCV
    import warnings as _w
    from sklearn.exceptions import ConvergenceWarning as _CW
    dp=np.asarray(donors_pre,float); dq=np.asarray(donors_post,float)
    if dp.shape[1] < 3: raise InsufficientDataError("need >=3 pre-periods for elastic-net donor selection")
    # v20.58: every fit of the cross-validation converged tightly (tol 1e-12 x y'y on the duality gap; sklearn's default 1e-4 moved the
    # chosen penalty and the effect by up to 0.005 on test problems -- 9 % of a 0.05 effect). R's m45 solves the same problem with glmnet
    # (models_prebuilt.R: enet_cv_sk) and agrees to 1e-9. Fits that still do not converge are COUNTED and reported, never silent.
    m=ElasticNetCV(l1_ratio=[.3,.5,.7,.9,1.0],cv=min(5,dp.shape[1]),random_state=seed,max_iter=1_000_000,tol=1e-12)
    with _w.catch_warnings(record=True) as _wl:
        _w.simplefilter("always", _CW)
        m.fit(dp.T, np.asarray(y_treat_pre,float))
    # v20.58: a fit counts as NOT converged when its duality gap stays above 1e-9 x y'y (1000 x the requested 1e-12): below that the gap is
    # at the floating-point floor of the coordinate descent (e.g. 3.4e-15 for a requested 2.0e-15 on 8 pre-periods -- the effect is the
    # same to 1e-10 with tol 1e-8); sklearn warns on those too
    import re as _re_
    def _nc(msg):
        g_ = _re_.search(r"Duality gap: ([0-9.eE+-]+), tolerance: ([0-9.eE+-]+)", msg)
        return True if not g_ else float(g_.group(1)) > 1000.0 * float(g_.group(2))
    n_nc=sum(1 for x in _wl if issubclass(x.category, _CW) and _nc(str(x.message)))
    n_floor=sum(1 for x in _wl if issubclass(x.category, _CW)) - n_nc
    att=float(np.mean(np.asarray(y_treat_post,float)-m.predict(dq.T)))
    return {"ATT_lasso_sc":att,"n_nonzero_donors":int((m.coef_!=0).sum()),
            "n_donors_available":dp.shape[0], "alpha":float(m.alpha_), "l1_ratio":float(m.l1_ratio_), "n_not_converged":int(n_nc),
            "n_fits_at_float_floor":int(n_floor)}, m.coef_



# ====================== v20.57: THE CORE-vs-RING SERIES DESIGN for the unit-level estimators (M11, M36-M38, M45) ======================
# Found by validate_known_answers.py (true effect +0.05): these models built their units from WHOLE sub-watersheds -- core and
# rings averaged together, and the other (also treated) sub-watersheds as donors. With one sub-watershed they had no donor and
# stopped; pooled, every donor was itself treated and the estimate was ~0 (M11 -0.002, M45 +0.002). The design every other model
# uses is the comparison of the core with its rings: the TREATED units are the core series of each sub-watershed (ring 0, each
# season its own series), the CONTROLS the ring series (never treated). The R pipeline has used it since v20.49.
def ring_series(df, y_col, time_col="Year"):
    """Units = (sub-watershed, ring, season) series, one mean per Year. Returns (Y units x years, meta per unit: site_id,
    buff_km, Season, treated, cohort = the first Year the series is treated (inf for the rings), n_pixels)."""
    need = ["site_id", "buff_km", "Season", time_col, y_col, "did_term"]
    d = df[[c for c in need if c in df.columns]].copy()
    if "site_id" not in d.columns: d["site_id"] = 0
    if "Season" not in d.columns: d["Season"] = 0
    d[y_col] = pd.to_numeric(d[y_col], errors="coerce"); d = d[np.isfinite(d[y_col].values)]
    keys = ["site_id", "buff_km", "Season"]
    Y = d.groupby(keys + [time_col], observed=True)[y_col].mean().unstack(time_col).sort_index(axis=1)
    tr = d[d["did_term"] == 1].groupby(keys, observed=True)[time_col].min()
    meta = pd.DataFrame(index=Y.index)
    meta["cohort"] = tr.reindex(Y.index).astype(float).fillna(np.inf).values
    meta["treated"] = np.isfinite(meta["cohort"].values)
    meta = meta.reset_index()
    return Y, meta


def _cohort_blocks(Y, meta, min_pre=2):
    """For each cohort g: (treated rows, donor rows, pre years, post years) -- donors are never-treated series complete over the window."""
    yrs = [int(c) for c in Y.columns]
    for g in sorted(set(meta.loc[meta.treated, "cohort"].astype(int))):
        pre = [y for y in yrs if y < g]; post = [y for y in yrs if y >= g]
        if len(pre) < min_pre or not post: continue
        ti = np.where((meta.cohort.values == g))[0]; di = np.where(~meta.treated.values)[0]
        win = pre + post
        di = [i for i in di if Y.iloc[i][win].notna().all()]
        ti = [i for i in ti if Y.iloc[i][pre].notna().sum() >= min_pre and Y.iloc[i][post].notna().any()]
        if not ti or len(di) < 2: continue
        yield g, ti, di, pre, post


# ---- v20.58: synthdid's point estimator, ported line by line (Arkhangelsky, Athey, Hirshberg, Imbens & Wager 2021; R package synthdid) --
# the engine's own SDID (run_synthetic_diD, kept) fitted the TIME weights to the controls' PRE-period mean (the uniform weights solve that
# exactly, so the time weights did nothing), did not sparsify the unit weights and took one treated unit: 0.0507 against synthdid's 0.0500
def _sdid_fw_step(A, x, b, eta):
    Ax = A @ x
    half_grad = (Ax - b) @ A + eta * x
    i = int(np.argmin(half_grad))
    d_x = -x.copy(); d_x[i] = 1.0 - x[i]
    if np.all(d_x == 0): return x
    d_err = A[:, i] - Ax
    step = -float(half_grad @ d_x) / (float(d_err @ d_err) + eta * float(d_x @ d_x))
    return x + min(1.0, max(0.0, step)) * d_x

def _sdid_sc_weight_fw(Y, zeta, intercept=True, lam=None, min_decrease=1e-3, max_iter=1000):
    """synthdid's sc.weight.fw: Frank-Wolfe on min zeta^2 ||lam||^2 + ||A lam - b||^2 / N0 over the simplex (columns demeaned with an intercept)."""
    T0 = Y.shape[1] - 1; N0 = Y.shape[0]
    lam = np.full(T0, 1.0 / T0) if lam is None else np.asarray(lam, dtype=np.float64).copy()
    if intercept: Y = Y - Y.mean(axis=0, keepdims=True)
    A = Y[:, :T0]; b = Y[:, T0]; eta = N0 * zeta ** 2
    vals = []; t = 0
    while t < max_iter and (t < 2 or vals[t - 2] - vals[t - 1] > min_decrease ** 2):
        t += 1
        lam = _sdid_fw_step(A, lam, b, eta)
        err = Y @ np.concatenate([lam, [-1.0]])
        vals.append(zeta ** 2 * float(lam @ lam) + float(err @ err) / N0)
    return lam

def _sdid_sparsify(v):
    v = v.copy(); v[v <= v.max() / 4] = 0.0; return v / v.sum()

def _synthdid_opts(Y, N0, T0):
    """synthdid_estimate's defaults: (zeta.omega, zeta.lambda, min.decrease) from the noise level sd(diff of the controls' pre rows)."""
    Y = np.asarray(Y, dtype=np.float64); N, T = Y.shape; N1, T1 = N - N0, T - T0
    noise = float(np.std(np.diff(Y[:N0, :T0], axis=1).ravel(order="F"), ddof=1)) if T0 > 1 else 0.0
    return ((N1 * T1) ** 0.25) * noise, 1e-6 * noise, 1e-5 * noise

def _synthdid_fit(Y, N0, T0, opts, lam0=None, om0=None):
    """synthdid_estimate's weights (update.lambda / update.omega TRUE: Frank-Wolfe from lam0 / om0, 100 passes, sparsify, then up to 10,000)
    and its estimate. Returns (tau, omega, lambda)."""
    Y = np.asarray(Y, dtype=np.float64); N, T = Y.shape; N1, T1 = N - N0, T - T0
    zeta_omega, zeta_lambda, min_dec = opts
    Yc = np.vstack([np.column_stack([Y[:N0, :T0], Y[:N0, T0:].mean(axis=1)]),
                    np.concatenate([Y[N0:, :T0].mean(axis=0), [Y[N0:, T0:].mean()]])[None, :]])
    lam = _sdid_sc_weight_fw(Yc[:N0, :], zeta_lambda, True, lam0, min_dec, 100)
    lam = _sdid_sc_weight_fw(Yc[:N0, :], zeta_lambda, True, _sdid_sparsify(lam), min_dec, 10000)
    om = _sdid_sc_weight_fw(Yc[:, :T0].T, zeta_omega, True, om0, min_dec, 100)
    om = _sdid_sc_weight_fw(Yc[:, :T0].T, zeta_omega, True, _sdid_sparsify(om), min_dec, 10000)
    tau = float(np.concatenate([-om, np.full(N1, 1.0 / N1)]) @ Y @ np.concatenate([-lam, np.full(T1, 1.0 / T1)]))
    return tau, om, lam

def synthdid_point(Y, N0, T0):
    """synthdid::synthdid_estimate(Y, N0, T0) without covariates: Y (N0 controls first, then the treated rows) x (T0 pre columns, then the post
    columns). Returns (tau, omega, lambda)."""
    return _synthdid_fit(Y, N0, T0, _synthdid_opts(Y, N0, T0))


def synthdid_placebo_se(Y, N0, T0, omega, lam, reps=200, seed=12345):
    """v20.58 (second pass): synthdid's placebo SE (vcov(method = "placebo"), synthdid:::placebo_se) with R's OWN draws -- R's route
    (lib/models_prebuilt.R sdid_fit) runs it inside seeded(): L'Ecuyer-CMRG after set.seed(12345), sequential. Each of the 200 replications
    permutes the control rows (sample(1:N0)), makes the last N1 of them the placebo treated and re-fits synthdid_estimate from the fit's
    time weights and the controls' unit weights renormalised (the original call's options: update.omega / update.lambda TRUE, its zeta and
    min.decrease); SE = sqrt((r - 1) / r) sd. Y: controls first (in panel.matrices' order), then the treated rows."""
    Y = np.asarray(Y, np.float64); N, T = Y.shape; N1, T1 = N - N0, T - T0
    if N0 <= N1: return float("nan")                                   # synthdid: "must have more controls than treated units"
    opts = _synthdid_opts(Y, N0, T0)                                   # the ORIGINAL fit's zeta / min.decrease (synthdid's attr "opts")
    rr = _RRandom(seed, "L'Ecuyer-CMRG"); ests = []
    om = np.asarray(omega, np.float64); n0p = N0 - N1
    for _ in range(int(reps)):
        ind = np.asarray(rr.sample_int(N0, N0)) - 1
        ob = om[ind[:n0p]]; sb = ob.sum(); ob = ob / sb if sb != 0 else np.full(n0p, 1.0 / n0p)
        ests.append(_synthdid_fit(Y[ind, :], n0p, T0, opts, lam0=np.asarray(lam, np.float64), om0=ob)[0])   # opts: update.* TRUE (re-fitted
    return float(np.sqrt((reps - 1) / reps) * np.std(ests, ddof=1))                                          #   from the weights given)


def sdid_ring_series(df, y_col):
    """Synthetic DiD (Arkhangelsky et al. 2021), one fit per cohort on the core-vs-ring series; ATT = the cohorts' estimates
    weighted by their treated series. Returns (summary dict, per-cohort table, donor weights)."""
    Y, meta = ring_series(df, y_col)
    rows, wts = [], []
    for g, ti, di, pre, post in _cohort_blocks(Y, meta):
        # v20.58 -- as R's m11_sdid (by_cohort_season): one fit per cohort x SEASON, the treated series against the SAME season's ring series
        # (v20.57 averaged every season's treated series and took the ring series of every season as donors -- their shocks differ),
        # the fits averaged with weights = treated series x post years
        for se_ in sorted(set(int(meta.Season.iloc[i]) for i in ti)):
            win = list(pre) + list(post)                                    # v20.58: the balanced panel (as R's by_cohort_season)
            tis = [i for i in ti if int(meta.Season.iloc[i]) == se_ and Y.iloc[i][win].notna().all()]
            dis = [j for j in di if int(meta.Season.iloc[j]) == se_]
            if not tis or len(dis) < 2: continue
            # v20.58 (second pass): the rows in R's order -- R's sdid_fit gives synthdid INTEGER series ids (the treated first, then the ring
            # series, each by sub-watershed and ring) and panel.matrices sorts the controls by those ids AS TEXT ("10" before "2"); the order
            # decides which ring series each placebo replication picks
            _key = lambda i: (int(meta.site_id.iloc[i]), int(meta.buff_km.iloc[i]))
            tis = sorted(tis, key=_key); dis = sorted(dis, key=_key)
            _uid = {j: len(tis) + 1 + k for k, j in enumerate(dis)}
            dis = sorted(dis, key=lambda j: str(_uid[j]))
            Ym = np.vstack([Y.iloc[dis][win].values, Y.iloc[tis][win].values])
            tau, om, lam = synthdid_point(Ym, len(dis), len(pre))           # v20.58: synthdid's own algorithm (was run_synthetic_diD)
            se_f = synthdid_placebo_se(Ym, len(dis), len(pre), om, lam)
            rows.append({"cohort": g, "Season": se_, "ATT": float(tau), "se": se_f, "n_treated_series": len(tis), "n_donor_series": len(dis), "pre_years": len(pre), "post_years": len(post)})
            for k, i in enumerate(dis):
                wts.append({"cohort": g, "Season": se_, "donor": f"site {int(meta.site_id.iloc[i])} ring {int(meta.buff_km.iloc[i])} season {int(meta.Season.iloc[i])}", "unit_weight": float(om[k])})
    if not rows: raise InsufficientDataError("no cohort x season with >= 2 pre-years, a post-year and >= 2 complete same-season ring series as donors")
    t = pd.DataFrame(rows); w_ = (t.n_treated_series * t.post_years).values.astype(float); w_ = w_ / w_.sum()
    att = float(np.sum(w_ * t.ATT.values))
    se = float(np.sqrt(np.sum(w_ ** 2 * t.se.values ** 2))) if np.all(np.isfinite(t.se.values)) else float("nan")
    return {"ATT": att, "se": se, "n_cohorts": int(t.cohort.nunique()), "n_fits": int(len(t)), "n_treated_series": int(t.n_treated_series.sum()),
            "se_how": (f"{len(t)} cohort x season fit(s), each a core series against the same season's ring series; each fit's SE by synthdid's placebo "
                       f"variance (200 replications; R's own draws: L'Ecuyer-CMRG after set.seed(12345)), combined as independent") if np.isfinite(se) else "",
            "design": "core vs ring series (site x ring x season), one fit per cohort x season (as R)"}, t, pd.DataFrame(wts)


def lasso_sc_ring_series(df, y_col, seed=0):
    """Elastic-net synthetic control on the core-vs-ring series. v20.57 (a bias found by the known-answer test, 0.064 for a true
    +0.05 on the staggered panel): v20.57's first version fitted the MEAN of a cohort's core series (every season mixed) on every
    ring series with only 4-6 pre years; the penalty shrank the donor weights, so the counterfactual carried only part of the
    trend all series share and the effect grew with the years after the start. Now each treated series (sub-watershed x season)
    is fitted on the ring series of the SAME season, after removing their common year effect (the donors' mean per year -- as
    the time effects of SDID / DiD): the penalty acts on the idiosyncratic part only. The series' effects are averaged, weighted
    by their treated years."""
    Y, meta = ring_series(df, y_col)
    rows, wts = [], []
    for g, ti, di, pre, post in _cohort_blocks(Y, meta, min_pre=3):
        for i in ti:
            se_ = int(meta.Season.iloc[i])
            dj = [j for j in di if int(meta.Season.iloc[j]) == se_]
            if len(dj) < 3: dj = list(di)                                  # too few same-season donors: every ring series
            y1 = Y.iloc[i]; D_ = Y.iloc[dj]
            mu = D_.mean(axis=0)                                           # the common year effect of the donors
            pre_i = [y for y in pre if np.isfinite(y1[y])]; post_i = [y for y in post if np.isfinite(y1[y])]
            if len(pre_i) < 3 or not post_i: continue
            r, coefs = lasso_synthetic_control((y1[pre_i] - mu[pre_i]).values, (D_[pre_i] - mu[pre_i]).values,
                                               (y1[post_i] - mu[post_i]).values, (D_[post_i] - mu[post_i]).values, seed=seed)
            rows.append({"cohort": g, "site_id": int(meta.site_id.iloc[i]), "Season": se_, "ATT": float(r["ATT_lasso_sc"]),
                         "n_nonzero_donors": r["n_nonzero_donors"], "n_donors_available": r["n_donors_available"],
                         "pre_years": len(pre_i), "post_years": len(post_i), "alpha": r["alpha"], "l1_ratio": r["l1_ratio"],
                         "n_not_converged": r["n_not_converged"]})
            for k, j in enumerate(dj):
                wts.append({"cohort": g, "treated": f"site {int(meta.site_id.iloc[i])} season {se_}",
                            "donor": f"site {int(meta.site_id.iloc[j])} ring {int(meta.buff_km.iloc[j])} season {int(meta.Season.iloc[j])}", "weight": float(coefs[k])})
    if not rows: raise InsufficientDataError("no treated series with >= 3 pre-years, a post-year and >= 2 complete ring series as donors")
    t = pd.DataFrame(rows); att = float(np.average(t.ATT, weights=t.post_years))
    if int(t.n_not_converged.sum()):
        warn(f"elastic-net SC: {int(t.n_not_converged.sum())} fit(s) of the cross-validation stayed above 1e-9 x y'y in duality gap after 1,000,000 passes "
             f"(series: {t.loc[t.n_not_converged > 0, ['site_id', 'Season']].to_dict('records')}) -- their penalty choice may be approximate")
    return {"ATT_lasso_sc": att, "n_cohorts": int(t.cohort.nunique()), "n_treated_series": int(len(t)), "n_nonzero_donors": int(t.n_nonzero_donors.sum()),
            "n_not_converged": int(t.n_not_converged.sum()),
            "n_donors_available": int(t.n_donors_available.max()),
            "design": "each core series (site x season) on the same-season ring series, net of their common year effect"}, t, pd.DataFrame(wts)


def _twoway_fit(Y, W, iters=200, tol=1e-12):
    """Additive unit + period effects fitted on the cells where W is True (alternating means)."""
    a = np.zeros(Y.shape[0]); b = np.zeros(Y.shape[1]); mu = np.nanmean(np.where(W, Y, np.nan))
    for _ in range(iters):
        R = np.where(W, Y - mu - b[None, :], np.nan); a_new = np.nan_to_num(np.nanmean(R, axis=1))
        R = np.where(W, Y - mu - a_new[:, None], np.nan); b_new = np.nan_to_num(np.nanmean(R, axis=0))
        if max(np.max(np.abs(a_new - a)), np.max(np.abs(b_new - b))) < tol: a, b = a_new, b_new; break
        a, b = a_new, b_new
    return mu + a[:, None] + b[None, :]


def factor_models_ring_series(df, y_col, r=2, which=("ife", "mc", "gsc")):
    """Interactive FE (Bai 2009), matrix completion (Athey et al. 2021) and the generalized synthetic control (Xu 2017) on the
    core-vs-ring series matrix (series x years). Every one of them now includes the additive series and year effects (fitted on
    the untreated cells) and puts the factors on top -- before, the factors had to absorb the levels (IFE, MC shrank the level
    by 10 % of the largest singular value) and the GSC imputation had no intercept."""
    Y_df, meta = ring_series(df, y_col)
    yrs = np.array([int(c) for c in Y_df.columns]); Y = Y_df.values.astype(float)
    D = (np.isfinite(meta.cohort.values)[:, None] & (yrs[None, :] >= np.nan_to_num(meta.cohort.values, posinf=9999)[:, None])).astype(float)
    obs = np.isfinite(Y); untreated = obs & (D == 0)
    if D.sum() == 0: raise InsufficientDataError("no treated core series in the window")
    if (~meta.treated).sum() < r + 2: raise InsufficientDataError(f"need >= {r + 2} ring series as controls")
    out = {"n_series": int(Y.shape[0]), "n_years": int(Y.shape[1]), "n_treated_cells": int((D * obs).sum())}
    FE = _twoway_fit(Y, untreated)
    if "ife" in which:
        keep = obs.all(axis=1)
        Yk, Dk = Y[keep], D[keep]
        # FWL: the additive effects partialled out of Y and D (balanced series), then Bai's iteration on the residual
        def dm(M): return M - M.mean(axis=1, keepdims=True) - M.mean(axis=0, keepdims=True) + M.mean()
        out["beta_interactive_fe"] = interactive_fe(dm(Yk), dm(Dk), r=r) if keep.sum() > r + 1 else np.nan
        out["beta_plain_twfe"] = float(np.sum(dm(Dk) * dm(Yk)) / np.sum(dm(Dk) ** 2)) if keep.sum() > 1 else np.nan
    if "mc" in which:
        R = np.where(untreated, Y - FE, np.nan)
        M = np.where(untreated, R, 0.0); lam = None; L = np.zeros_like(M)
        for _ in range(500):
            U, s, Vt = np.linalg.svd(M, full_matrices=False)
            if lam is None: lam = 0.1 * (s[0] if len(s) else 0.0)
            L = U @ np.diag(np.maximum(s - lam, 0)) @ Vt
            newM = np.where(untreated, R, L)
            if np.max(np.abs(newM - M)) < 1e-9: M = newM; break
            M = newM
        cf = FE + L; cells = (D == 1) & obs
        out["ATT_matrix_completion"] = float(np.mean(Y[cells] - cf[cells]))
    if "gsc" in which:
        ctrl = np.where(~meta.treated.values & obs.all(axis=1))[0]
        if len(ctrl) >= r + 2:
            Yc = Y[ctrl]; mu_t = Yc.mean(axis=0); Rc = Yc - mu_t - (Yc - mu_t).mean(axis=1, keepdims=True)
            _, _, Vt = np.linalg.svd(Rc, full_matrices=False); F = Vt[:r, :]
            taus = []
            for i in np.where(meta.treated.values)[0]:
                pre = np.where((D[i] == 0) & obs[i])[0]; post = np.where((D[i] == 1) & obs[i])[0]
                if len(pre) < r + 1 or not len(post): continue
                Xp = np.column_stack([np.ones(len(pre)), F[:, pre].T]); coef = np.linalg.lstsq(Xp, (Y[i] - mu_t)[pre], rcond=None)[0]
                cf_i = mu_t + coef[0] + F.T @ coef[1:]
                taus.append(np.mean(Y[i, post] - cf_i[post]))
            out["ATT_gsc"] = float(np.mean(taus)) if taus else np.nan
        else:
            out["ATT_gsc"] = np.nan
    return out


# ====================== v20.58: M36 / M37 / M38 -- fect / gsynth PORTED (the engine computes what R's route computes) ======================
# validate_model_parity.py --engine: the engine's factor models (factor_models_ring_series above, kept as the cross-check) put every season's
# series into ONE matrix with a FIXED number of factors (N_FACTORS) -- M36 -0.00019, M37 +0.0017, M38 -0.0005 against R's fect / gsynth, which
# fit one cohort x season at a time (a core series against the SAME season's ring series) with the number of factors (the penalty for
# matrix completion) chosen by fect's cross-validation. Ported here from fect 2.4.5's source line by line: the initial two-way fit on the
# untreated cells (initialFit), the EM of inter_fe_ub / inter_fe_mc (ife.cpp, ife_sub.cpp, fe_sub.cpp, mc.cpp: Y_demean, fe_add,
# panel_factor, panel_FE, their stopping rule and tolerances), gsynth's factors from the ring series only (inter_fe, balanced) with each
# core series' loadings by OLS on its own pre years (fect_nevertreated.R), fect's rolling-window cross-validation (.build_cv_mask_rolling:
# k folds, cv.prop of the eligible series, a random anchor, cv.nobs scored cells, a cv.buffer, the future dropped), its pooled MSPE, the
# fold SE and the 1-SE rule (.fect_apply_cv_rule), the lambda grid of matrix completion and its early stop. The folds are drawn by R's OWN
# generator, replicated (Mersenne-Twister after set.seed(12345), unif_rand, R_unif_index's rejection sampling, sample.int) -- R's route
# seeds fect's cross-validation with the same set.seed(12345), so both mask the same cells (checked: the masks, the CV tables to 1e-10,
# the chosen r / lambda and the ATT to 1e-14 on 6 test panels, r = 0 / 1 / 2 chosen). v20.58 (second pass): the SE with R's OWN draws too --
# fect's nonparametric bootstrap for M36 / M37 (R's route: seeded() = L'Ecuyer-CMRG after set.seed(12345); fect(parallel = TRUE, seed)
# registers doRNG, whose streams are the current state and its nextRNGStream()s, one per draw; the treated and ring series resampled with
# sample(), the fit repeated at the SAME tuning -- matrix completion as the FE model when the real fit kept no factor, fect's validF) and
# gsynth's PARAMETRIC bootstrap for M38 (fect vartype "parametric", sequential: 200 simulated prediction errors of a ring series fitted as
# if treated, then 200 draws of the fitted values + resampled errors). Checked against fect 2.4.5 / gsynth 1.4.0 on the 6 test panels: every
# bootstrap draw to 1e-14 and the SE to 10 digits (r = 0 / 1 / 2, lambda with and without a factor).
_LEC_M1, _LEC_M2 = 4294967087, 4294944443


def _lec_matpow2(A, e, m):
    R = [row[:] for row in A]
    for _ in range(e):
        R = [[sum(R[i][k] * R[k][j] for k in range(3)) % m for j in range(3)] for i in range(3)]
    return R


_LEC_A1 = [[0, 1, 0], [0, 0, 1], [(-810728) % _LEC_M1, 1403580, 0]]
_LEC_A2 = [[0, 1, 0], [0, 0, 1], [(-1370589) % _LEC_M2, 0, 527612]]
_LEC_A1P127, _LEC_A2P127 = _lec_matpow2(_LEC_A1, 127, _LEC_M1), _lec_matpow2(_LEC_A2, 127, _LEC_M2)


def _r_next_stream(six):
    """parallel::nextRNGStream -- the L'Ecuyer-CMRG state 2^127 steps on (R's src/library/parallel/src/rngstream.c)."""
    s = [int(v) & 0xFFFFFFFF for v in six]
    return ([sum(_LEC_A1P127[i][j] * s[j] for j in range(3)) % _LEC_M1 for i in range(3)]
            + [sum(_LEC_A2P127[i][j] * s[j + 3] for j in range(3)) % _LEC_M2 for i in range(3)])


class _RRandom:
    """R's generator after set.seed(seed, kind = "Mersenne-Twister" (default) | "L'Ecuyer-CMRG", sample.kind = "Rejection") -- R's
    src/main/RNG.c and random.c; `state` starts an L'Ecuyer-CMRG generator at a given .Random.seed[2:7] (a doRNG / nextRNGStream stream)."""
    def __init__(self, seed=None, kind="Mersenne-Twister", state=None):
        self.kind = kind
        if kind == "L'Ecuyer-CMRG":
            if state is not None:
                self.s = [int(v) & 0xFFFFFFFF for v in state]; return
            s = int(seed) & 0xFFFFFFFF
            for _ in range(50): s = (69069 * s + 1) & 0xFFFFFFFF          # RNG_Init's initial scrambling
            self.s = []
            for _ in range(6):
                s = (69069 * s + 1) & 0xFFFFFFFF
                while s >= _LEC_M2: s = (69069 * s + 1) & 0xFFFFFFFF
                self.s.append(s)
            return
        s = int(seed) & 0xFFFFFFFF
        for _ in range(50): s = (69069 * s + 1) & 0xFFFFFFFF            # RNG_Init's initial scrambling
        seeds = []
        for _ in range(625):
            s = (69069 * s + 1) & 0xFFFFFFFF; seeds.append(s)
        self.mt = seeds[1:]; self.mti = 624                                # dummy[0] = mti = 624 (FixupSeeds)

    @property
    def state(self):
        return list(self.s)

    def _genrand(self):
        N, M, mt = 624, 397, self.mt
        if self.mti >= N:
            for kk in range(N - M):
                y = (mt[kk] & 0x80000000) | (mt[kk + 1] & 0x7FFFFFFF); mt[kk] = mt[kk + M] ^ (y >> 1) ^ (0x9908B0DF if y & 1 else 0)
            for kk in range(N - M, N - 1):
                y = (mt[kk] & 0x80000000) | (mt[kk + 1] & 0x7FFFFFFF); mt[kk] = mt[kk + (M - N)] ^ (y >> 1) ^ (0x9908B0DF if y & 1 else 0)
            y = (mt[N - 1] & 0x80000000) | (mt[0] & 0x7FFFFFFF); mt[N - 1] = mt[M - 1] ^ (y >> 1) ^ (0x9908B0DF if y & 1 else 0)
            self.mti = 0
        y = mt[self.mti]; self.mti += 1
        y ^= (y >> 11); y ^= (y << 7) & 0x9D2C5680; y ^= (y << 15) & 0xEFC60000; y ^= (y >> 18)
        return (y & 0xFFFFFFFF) * 2.3283064365386963e-10

    def unif_rand(self):
        if self.kind == "L'Ecuyer-CMRG":                                   # RNG.c: no fixup for this generator
            s = self.s
            p1 = (1403580 * s[1] - 810728 * s[0]) % _LEC_M1; s[0], s[1], s[2] = s[1], s[2], p1
            p2 = (527612 * s[5] - 1370589 * s[3]) % _LEC_M2; s[3], s[4], s[5] = s[4], s[5], p2
            return ((p1 - p2) if p1 > p2 else (p1 - p2 + _LEC_M1)) * 2.328306549295727688e-10
        x = self._genrand()
        if x <= 0.0: return 0.5 * 2.328306437080797e-10
        if (1.0 - x) <= 0.0: return 1.0 - 0.5 * 2.328306437080797e-10
        return x

    def _unif_index(self, dn):                                             # R_unif_index, sample.kind = "Rejection"
        if dn <= 0: return 0.0
        bits = int(np.ceil(np.log2(dn)))
        while True:
            v = 0; n = 0
            while n <= bits:
                v = 65536 * v + int(np.floor(self.unif_rand() * 65536)); n += 16
            dv = float(v & ((1 << bits) - 1))
            if dn > dv: return dv

    def sample_int(self, n, size, replace=False):
        """sample.int(n, size, replace) (1-based, as R)."""
        n = int(n); size = int(size)
        if replace or size < 2: return [int(self._unif_index(float(n))) + 1 for _ in range(size)]
        x = list(range(n)); out = []
        for _ in range(size):
            j = int(self._unif_index(float(n))); out.append(x[j] + 1); n -= 1; x[j] = x[n]
        return out

    def sample(self, x, size, replace=False):
        """R's sample(x, size, replace) -- with R's rule that ONE number x >= 1 means 1:x."""
        x = list(x)
        if len(x) == 1 and float(x[0]) >= 1 and float(x[0]) == int(x[0]):
            return self.sample_int(int(x[0]), size, replace)
        return [x[i - 1] for i in self.sample_int(len(x), size, replace)]


def _fect_cv_masks(II, D, k, cv_nobs, cv_buffer, cv_prop, min_T0, rng):
    """fect:::.build_cv_mask_rolling (seed = NULL: the generator `rng`). k (cv.id, est.id) pairs of 1-based column-major cell indices."""
    II = np.asarray(II); D = np.asarray(D); TT, N = II.shape
    elig = []
    for j in range(N):
        tt = np.where(D[:, j] >= 1)[0]; onset = int(tt.min()) + 1 if len(tt) else None
        obs_t = [int(t) + 1 for t in np.where(II[:, j] == 1)[0]]
        elig.append([t for t in obs_t if onset is None or t < onset])
    units = [j + 1 for j in range(N) if len(elig[j]) >= min_T0 + cv_nobs]
    if not units: raise InsufficientDataError(f"fect's cross-validation: no series has min.T0 + cv.nobs = {min_T0 + cv_nobs} eligible years")
    n_s = max(1, int(np.round(cv_prop * len(units))))
    folds = []
    for _ in range(int(k)):
        sampled = list(units) if n_s >= len(units) else [units[i - 1] for i in sorted(rng.sample_int(len(units), n_s))]
        cv_acc, est_acc = [], []
        for j in sampled:
            obs_t = elig[j - 1]; n_obs = len(obs_t)
            lo, hi = min_T0 + 1, n_obs - cv_nobs + 1
            valid = list(range(lo, hi + 1)) if lo <= hi else list(range(lo, hi - 1, -1))
            if not valid: continue
            a = valid[rng.sample_int(len(valid), 1)[0] - 1]
            hold = obs_t[a - 1:a - 1 + cv_nobs]
            buf = obs_t[max(1, a - cv_buffer) - 1:a - 1] if cv_buffer > 0 else []
            drop = obs_t[a + cv_nobs - 1:n_obs] if (a + cv_nobs) <= n_obs else []
            base = (j - 1) * TT
            cv_acc += [base + t for t in hold + buf + drop]; est_acc += [base + t for t in hold]
        folds.append((sorted(set(cv_acc)), sorted(set(est_acc))))
    return folds


def _fect_initial_fit(Y, obs):
    """fect's initialFit(force = "two-way"): fixest's y ~ 1 | unit + time on the cells `obs`, predicted on every cell -- the exact least-squares
    fit, by the normal equations with the time effects eliminated (an N x N system: (diag(n_i) - O' diag(1 / m_t) O) a = r, one unit effect
    fixed; then b_t = the mean over its observed cells of y - a). The same fitted values as a dense least squares on the dummy design, ~100 x
    faster (that solve was 90 % of the fect port's time)."""
    O = np.asarray(obs, dtype=np.float64); TT, N = Y.shape
    Yo = np.where(O > 0, np.asarray(Y, np.float64), 0.0)
    m = O.sum(axis=1); n = O.sum(axis=0)
    if np.any(m == 0) or np.any(n == 0): raise InsufficientDataError("fect's initial fit: a year or a series without an untreated cell")
    Ow = O / m[:, None]
    M = np.diag(n) - O.T @ Ow
    r_ = Yo.sum(axis=0) - O.T @ (Yo.sum(axis=1) / m)
    a = np.zeros(N)
    a[1:] = np.linalg.lstsq(M[1:, 1:], r_[1:], rcond=None)[0] if N > 1 else a[1:]
    b = (Yo.sum(axis=1) - O @ a) / m
    return a[None, :] + b[:, None]


def _fect_ife_step(E, mc, r, lam):
    """fect's ife(): Y_demean + fe_add (force = 3), then panel_factor (r factors) or panel_FE (soft-thresholded SVD, matrix completion)."""
    T, N = E.shape
    mu = E.sum() / (N * T); a = E.mean(axis=0); x = E.mean(axis=1)
    EE = E - a[None, :] - x[:, None] + mu
    fit = mu + (a - mu)[None, :] + (x - mu)[:, None]
    inter = np.zeros_like(E); F = None
    if r > 0:
        if mc == 0:
            if T < N:
                U, s, Vt = np.linalg.svd(EE @ EE.T / (N * T)); F = U[:, :r] * np.sqrt(T); L = EE.T @ F / T
            else:
                U, s, Vt = np.linalg.svd(EE.T @ EE / (N * T)); L = U[:, :r] * np.sqrt(N); F = EE @ L / N
            inter = F @ L.T
        else:
            U, s, Vt = np.linalg.svd(EE / (T * N), full_matrices=False)
            d = np.where(s > lam, s - lam, 0.0)
            inter = (U * d) @ Vt * (T * N)
    return fit + inter, inter, F


def _fect_em(YY, Y0, II, r=0, mc=0, lam=0.0, tol=1e-5, max_iter=5000):
    """inter_fe_ub (r = 0: fe_ad_iter, at most 501 passes; r > 0: fe_ad_inter_iter) and inter_fe_mc (mc = 1, r = 1): the EM on the untreated
    cells II, from the initial fit Y0, until the relative change of the fit (and of the factor part) is <= tol -- fect's arithmetic."""
    fit = Y0.copy(); fit_old = fit.copy(); dif = 1.0; niter = 0; inter_old = np.zeros_like(YY)
    if r == 0 and not mc:
        while dif > tol and niter <= 500:
            E = np.where(II == 0, fit, YY)
            mu = E.sum() / E.size; a = E.mean(axis=0); x = E.mean(axis=1)
            fit = mu + (a - mu)[None, :] + (x - mu)[:, None]
            dif = np.linalg.norm(fit - fit_old) / np.linalg.norm(fit_old); fit_old = fit; niter += 1
        return fit
    while dif > tol and niter <= max_iter:
        E = np.where(II == 0, fit, YY)
        fit, inter, _ = _fect_ife_step(E, mc, r, lam)
        dif = np.linalg.norm(fit - fit_old) / (np.linalg.norm(fit_old) + 1e-10)
        if r > 0 and not mc:
            n_old = np.linalg.norm(inter_old)
            if n_old > 1e-10: dif = max(dif, np.linalg.norm(inter - inter_old) / n_old)
            inter_old = inter
        fit_old = fit; niter += 1
    return fit


def _fect_rule_1se(means, ses):
    """.fect_apply_cv_rule(rule = "1se"): the smallest index whose mean CV error is within one fold-SE of the minimum."""
    m = np.asarray(means, float); ok = np.isfinite(m)
    if not ok.any(): return None
    i_min = int(np.where(ok & (m == m[ok].min()))[0].min())
    se_min = ses[i_min] if (ses is not None and np.isfinite(ses[i_min])) else 0.0
    return int(np.where(ok & (m <= m[i_min] + se_min))[0].min())


def _fect_fold_scores(res):
    """.fect_cv_aggregate_folds: the pooled MSPE (every fold's held-out cells) and the SE = sd(per-fold MSPE) / sqrt(K)."""
    pooled = float(np.sum(np.concatenate(res) ** 2) / sum(len(r_) for r_ in res))
    per = np.array([np.sum(r_ ** 2) / len(r_) for r_ in res]); per = per[np.isfinite(per)]
    return pooled, (float(np.std(per, ddof=1) / np.sqrt(len(per))) if len(per) > 1 else 0.0)


def _fect_cell(M, idx1):
    return M.ravel(order="F")[np.asarray(idx1, int) - 1]


def _fect_masked(M, idx1):
    v = M.ravel(order="F").copy(); v[np.asarray(idx1, int) - 1] = 0; return v.reshape(M.shape, order="F")


def fect_fit(Y, D, method, r_end=0, min_T0=5, cv_nobs=3, do_cv=True, tuning=None, k=None, cv_prop=0.1, cv_buffer=1, tol=None,
             max_iter=5000, nlambda=10, seed=12345):
    """ONE fect fit (method "ife" | "mc") or gsynth fit ("gsynth"), force = "two-way", no covariates, as R's route calls them:
    fect(Y ~ D, CV = TRUE, r = c(0, r_end), min.T0, cv.nobs) -> the tuning; then fect(CV = FALSE, r | lambda = that tuning) -> att.avg.
    gsynth: gsynth(CV = TRUE, r = c(0, r_end), min.T0) (its k = 5, tol = 0.001; fect's cv.nobs = 3) and gsynth(CV = FALSE, r). Y, D: years x
    series (balanced; the treated series first). tuning (with do_cv False): r, or lambda (None = no lambda: fect then fits the FE model).
    Returns (att, tuning, cv table)."""
    Y = np.asarray(Y, np.float64); D = np.asarray(D, np.float64); TT, N = Y.shape
    II = np.ones_like(Y); II[D == 1] = 0.0
    YY = np.where(II == 0, 0.0, Y)
    k = k or (5 if method == "gsynth" else 20); tol = tol or (1e-3 if method == "gsynth" else 1e-5); cv_tol = max(tol, 1e-3)
    cv_tab = []
    colsum = II.sum(axis=0); T0min = int(colsum[colsum > 0].min())
    if do_cv:
        rng = _RRandom(seed)
        re = int(r_end)
        if method in ("ife", "gsynth"):
            while (II.sum() - re * (N + TT) + re ** 2) <= 0: re -= 1           # fect_cv's restrictions on r.end
            if re >= T0min: re = T0min - 1
    if method == "gsynth":
        Dc = (np.cumsum(D, axis=0) > 0); tr = np.where(Dc.sum(axis=0) >= 1)[0]; co = np.where(Dc.sum(axis=0) == 0)[0]
        Yco = Y[:, co]; Nco = len(co); r_cv = int(tuning or 0)
        if do_cv:
            r0 = 0                                                          # fect_nevertreated: r = min(0, TT, Nco) = 0
            r_max = max(min(T0min - 2, re), 0)
            if r_max > 0:
                IIco = np.ones((TT, Nco))
                folds = _fect_cv_masks(IIco, np.zeros((TT, Nco)), k, 3, cv_buffer, cv_prop, min_T0, rng)
                Y0cv = [_fect_initial_fit(Yco, _fect_masked(IIco, cv_)) for cv_, _ in folds]
                for rr in range(r0, r_max + 1):
                    res = [_fect_cell(Yco, est_) - _fect_cell(_fect_em(_fect_masked(Yco, cv_), Y0cv[i], _fect_masked(IIco, cv_), rr, 0, 0.0, cv_tol, max_iter), est_)
                           for i, (cv_, est_) in enumerate(folds)]
                    cv_tab.append((rr,) + _fect_fold_scores(res))
                m_ = [x[1] if x[1] < 1e9 else np.nan for x in cv_tab]
                ip = _fect_rule_1se(m_, [x[2] for x in cv_tab]); r_cv = cv_tab[ip][0] if ip is not None else 0
            else:
                r_cv = 0
        mu = Yco.sum() / Yco.size; Yd = Yco - mu; a = Yd.mean(axis=0); Yd = Yd - a[None, :]; xi = Yd.mean(axis=1); Yd = Yd - xi[:, None]
        U = Y[:, tr] - mu - xi[:, None]; eff = np.zeros_like(U)
        if r_cv > 0:
            if TT < Nco:
                Uu, s, Vt = np.linalg.svd(Yd @ Yd.T / (Nco * TT)); F = Uu[:, :r_cv] * np.sqrt(TT)
            else:
                Uu, s, Vt = np.linalg.svd(Yd.T @ Yd / (Nco * TT)); F = Yd @ (Uu[:, :r_cv] * np.sqrt(Nco)) / Nco
            Fh = np.column_stack([F, np.ones(TT)])
        for j in range(len(tr)):
            pj = np.where(~Dc[:, tr[j]])[0]
            if r_cv == 0:
                eff[:, j] = U[:, j] - U[pj, j].mean()
            else:
                Fp = Fh[pj]; lam_ = np.linalg.solve(Fp.T @ Fp, Fp.T @ U[pj, j]); eff[:, j] = U[:, j] - Fh @ lam_
        Dt = D[:, tr]
        return float(np.sum(eff * Dt) / Dt.sum()), r_cv, cv_tab
    Y0 = _fect_initial_fit(Y, II)
    tune = tuning
    if do_cv:
        oci = set(int(i) + 1 for i in np.where(II.ravel(order="F") == 1)[0])
        folds = _fect_cv_masks(II, D, k, cv_nobs, cv_buffer, cv_prop, min_T0, rng)
        Y0cv = []
        for cv_, _ in folds:
            m = np.zeros(TT * N); m[np.asarray(sorted(oci - set(cv_)), int) - 1] = 1.0
            Y0cv.append(_fect_initial_fit(Y, m.reshape((TT, N), order="F")))
        if method == "ife":
            for rr in range(0, min(TT, re) + 1):
                res = [_fect_cell(YY, est_) - _fect_cell(_fect_em(_fect_masked(YY, cv_), Y0cv[i], _fect_masked(II, cv_), rr, 0, 0.0, cv_tol, max_iter), est_)
                       for i, (cv_, est_) in enumerate(folds)]
                cv_tab.append((rr,) + _fect_fold_scores(res))
            m_ = [x[1] if (np.isfinite(x[1]) and x[1] < 1e19) else np.nan for x in cv_tab]
            ip = _fect_rule_1se(m_, [x[2] for x in cv_tab]); tune = cv_tab[ip][0] if ip is not None else 0
        else:
            Yl = np.where(II == 0, 0.0, YY - Y0)
            lmax = np.log10(np.linalg.svd(Yl / (TT * N), compute_uv=False).max()); by = 3.0 / (nlambda - 2)
            lams = [10 ** (lmax - i * by) for i in range(nlambda - 1)] + [0.0]
            mspe = [1e20] * len(lams); ses = [np.nan] * len(lams); lam_cv = None; bc = 0; bchk = 0
            for i, lam in enumerate(lams):
                res = [_fect_cell(YY, est_) - _fect_cell(_fect_em(_fect_masked(YY, cv_), Y0cv[j], _fect_masked(II, cv_), 1, 1, lam, cv_tol, max_iter), est_)
                       for j, (cv_, est_) in enumerate(folds)]
                pooled, se_ = _fect_fold_scores(res); ses[i] = se_
                if (min(mspe) - pooled) > 0.01 * min(mspe):
                    lam_cv = lam; bc = 0; bchk = 0
                elif i > 0 and lam_cv == lams[i - 1]:
                    bchk = 1; bc = 0
                if bchk == 1: bc += 1
                mspe[i] = pooled; cv_tab.append((lam, pooled, se_))
                if bc == 3: break
            ip = _fect_rule_1se(mspe, ses); tune = lams[ip] if ip is not None else lam_cv
    if method == "ife" or tune is None or (isinstance(tune, float) and not np.isfinite(tune)):
        fit = _fect_em(YY, Y0, II, int(tune or 0) if method == "ife" else 0, 0, 0.0, tol, max_iter)   # mc without a lambda: fect fits the FE model
    else:
        fit = _fect_em(YY, Y0, II, 1, 1, float(tune), tol, max_iter)
    return float(np.sum((Y - fit) * D) / D.sum()), tune, cv_tab


def _fect_mc_validf(Y, D, lam, tol=1e-5, max_iter=5000):
    """fect's validF of a matrix-completion fit (fe_ad_inter_iter): 0 when the last soft-thresholded low-rank part sums to < 1e-10 -- the
    fit IS the FE model; fect's bootstrap then refits the FE model in every draw (fect_mc(hasF = out$validF))."""
    Y = np.asarray(Y, np.float64); D = np.asarray(D, np.float64)
    II = np.ones_like(Y); II[D == 1] = 0.0; YY = np.where(II == 0, 0.0, Y)
    fit = _fect_initial_fit(Y, II); fit_old = fit.copy(); dif = 1.0; niter = 0; inter = np.zeros_like(Y)
    while dif > tol and niter <= max_iter:
        E = np.where(II == 0, fit, YY)
        fit, inter, _ = _fect_ife_step(E, 1, 1, lam)
        dif = np.linalg.norm(fit - fit_old) / (np.linalg.norm(fit_old) + 1e-10); fit_old = fit; niter += 1
    return 0 if float(np.abs(inter).sum()) < 1e-10 else 1


def _gsynth_parts(Y, D, r):
    """gsynth's fit (force = "two-way", balanced, the never-treated series as the controls): (Y.ct of every series -- the controls' fitted
    values mu + alpha + xi + F lambda', the treated series' counterfactual --, Y - Y.ct, treated columns, control columns). The factors are
    fect_fit's (the ring series' two-way demeaned matrix); each control's loadings by least squares on them (fect_nevertreated's Y.ct /
    res.full, checked to 1e-16)."""
    Y = np.asarray(Y, np.float64); D = np.asarray(D, np.float64); TT, N = Y.shape
    Dc = (np.cumsum(D, axis=0) > 0); tr = np.where(Dc.sum(axis=0) >= 1)[0]; co = np.where(Dc.sum(axis=0) == 0)[0]
    Yco = Y[:, co]; Nco = len(co); r = int(r or 0)
    mu = Yco.sum() / Yco.size; Yd = Yco - mu; a = Yd.mean(axis=0); Yd = Yd - a[None, :]; xi = Yd.mean(axis=1); Yd = Yd - xi[:, None]
    fit_co = mu + a[None, :] + xi[:, None]
    U = Y[:, tr] - mu - xi[:, None]; ct_tr = np.zeros_like(U)
    if r > 0:
        if TT < Nco:
            Uu, s_, Vt = np.linalg.svd(Yd @ Yd.T / (Nco * TT)); F = Uu[:, :r] * np.sqrt(TT)
        else:
            Uu, s_, Vt = np.linalg.svd(Yd.T @ Yd / (Nco * TT)); F = Yd @ (Uu[:, :r] * np.sqrt(Nco)) / Nco
        fit_co = fit_co + F @ (Yd.T @ F @ np.linalg.inv(F.T @ F)).T
        Fh = np.column_stack([F, np.ones(TT)])
    for j in range(len(tr)):
        pj = np.where(~Dc[:, tr[j]])[0]
        if r == 0:
            ct_tr[:, j] = mu + xi + U[pj, j].mean()
        else:
            Fp = Fh[pj]; ct_tr[:, j] = mu + xi + Fh @ np.linalg.solve(Fp.T @ Fp, Fp.T @ U[pj, j])
    Yct = np.zeros_like(Y); Yct[:, co] = fit_co; Yct[:, tr] = ct_tr
    return Yct, Y - Yct, tr, co


def _fect_boot_se(Y, D, method, tune, nboots=200, seed=12345, return_draws=False):
    """The SE of one fect / gsynth fit as R's route computes it, with R's OWN random draws (checked draw by draw against fect 2.4.5).
    ife / mc -- fect's nonparametric bootstrap: R's route runs fect(se = TRUE, nboots = 200, parallel = TRUE, seed = 12345) inside seeded()
      (L'Ecuyer-CMRG, set.seed(12345)); fect registers doRNG, whose draw j uses the stream nextRNGStream^(j-1) of the state after
      set.seed(12345); per draw: fake.co <- sample(co, Nco, TRUE), fake.tr <- sample(tr, Ntr, TRUE) until every year keeps an untreated
      cell, the fit repeated at the SAME tuning (matrix completion: the FE model when the real fit kept no factor -- validF 0).
    gsynth -- gsynth's parametric bootstrap (fect vartype "parametric", para.error "empirical" on these complete series, sequential after
      set.seed(12345) in L'Ecuyer-CMRG): 200 prediction errors, each a ring series fitted AS IF treated against a resample of the other ring
      series; then per draw the rings resampled, the fitted values plus a drawn error (treated) and resampled residuals (rings), refitted.
    SE = sd of the draws (the failed ones left out, as fect)."""
    Y = np.asarray(Y, np.float64); D = np.asarray(D, np.float64); TT, N = Y.shape
    atts = []
    if method == "gsynth":
        r = int(tune or 0)
        Yct, res, tr, co = _gsynth_parts(Y, D, r)
        id_tr = [j + 1 for j in tr]; id_co = [j + 1 for j in co]; Ntr, Nco = len(id_tr), len(id_co)
        if Nco < 2 or not Ntr: return (float("nan"), []) if return_draws else float("nan")
        t0 = (D[:, tr] == 0).sum(axis=0)                                    # fect:::valid_controls on complete series: >= r + 1 (force
        if not (int(t0.min()) >= r + 1 and TT - int(t0.max()) >= 1):       #   two-way) years before the earliest start, >= 1 after the
            return (float("nan"), []) if return_draws else float("nan")     #   latest (else fect's draw.error() never ends)
        rng = _RRandom(seed, "L'Ecuyer-CMRG")
        errs = np.full((TT, Ntr, int(nboots)), np.nan)
        for b in range(int(nboots)):                                        # draw.error()
            ft = rng.sample(id_co, 1, False)[0]
            pseudo = rng.sample([i for i in id_co if i != ft], Nco, True)
            Dp = D[:, [i - 1 for i in id_tr + pseudo]]; Yp = Y[:, [ft - 1] * Ntr + [i - 1 for i in pseudo]]
            try:
                Yct_p, _r, _t, _c = _gsynth_parts(Yp, Dp, r); errs[:, :, b] = Yp[:, :Ntr] - Yct_p[:, :Ntr]
            except (np.linalg.LinAlgError, ValueError, ZeroDivisionError):
                pass
        for b in range(int(nboots)):                                        # one.nonpara()
            idb = id_tr + rng.sample(id_co, Nco, True)
            etr = np.column_stack([errs[:, w, rng.sample_int(int(nboots), 1, True)[0] - 1] for w in range(Ntr)])
            eco = res[:, [co[i - 1] for i in rng.sample_int(Nco, Nco, True)]]
            Yb = Yct[:, [i - 1 for i in idb]].copy(); Yb[:, :Ntr] += etr; Yb[:, Ntr:] += eco
            Db = D[:, [i - 1 for i in idb]]
            try:
                Yct_b, _r, _t, _c = _gsynth_parts(Yb, Db, r); Dt = Db[:, :Ntr]
                atts.append(float(np.sum((Yb[:, :Ntr] - Yct_b[:, :Ntr]) * Dt) / Dt.sum()))
            except (np.linalg.LinAlgError, ValueError, ZeroDivisionError):
                atts.append(np.nan)
    else:
        tr = [j + 1 for j in range(N) if D[:, j].sum() > 0]; co = [j + 1 for j in range(N) if D[:, j].sum() == 0]
        if len(co) < 2 or not tr: return (float("nan"), []) if return_draws else float("nan")
        II = 1.0 - D
        if method == "mc" and tune is not None and np.isfinite(float(tune)) and _fect_mc_validf(Y, D, float(tune)) == 0:
            tune = None                                                     # fect_mc(hasF = validF = 0): the FE model in every draw
        st = _RRandom(seed, "L'Ecuyer-CMRG").state
        for b in range(int(nboots)):
            rng = _RRandom(kind="L'Ecuyer-CMRG", state=st); st = _r_next_stream(st)
            while True:
                fco = rng.sample(co, len(co), True); ftr = rng.sample(tr, len(tr), True)
                ids = [i - 1 for i in ftr + fco]
                if (II[:, ids].sum(axis=1) >= 1).all(): break               # fect: every year keeps an untreated cell
            try:
                a_ = fect_fit(Y[:, ids], D[:, ids], method, do_cv=False, tuning=tune)[0]
            except (InsufficientDataError, np.linalg.LinAlgError, ValueError, ZeroDivisionError):
                a_ = np.nan
            atts.append(float(a_))
    a = np.asarray(atts, np.float64); a = a[np.isfinite(a)]
    se = float(np.std(a, ddof=1)) if len(a) > 1 else float("nan")
    return (se, atts) if return_draws else se


def fect_ring_series(df, y_col, method="ife", nboots=200):
    """v20.58 -- M36 ("ife"), M37 ("mc"), M38 ("gsynth") as R's m36_38_factor (lib/models_prebuilt.R): season_series (one mean per
    sub-watershed x ring x season x Year; the ring series never treated, the core series with the first Year its season is treated as its
    cohort), by_cohort_season (each season, each cohort: that cohort's core series against the SAME season's ring series, the series
    complete over the block's years, >= 1 treated, >= 2 ring series, >= 1 post and >= 2 pre years), per fit n_pre = its pre years,
    cv.nobs = min(3, max(1, n_pre - 2)), min.T0 = max(1, min(5, n_pre - cv.nobs)), the CV over r = 0 .. min(4, n_pre - 2, ring series - 1)
    when n_pre >= 3 (else r = 0 / the FE model), fect_fit above; the fits averaged with weights = treated series x post years, their SEs
    combined as independent. The series order within a fit: the core series, then the ring series, each by (sub-watershed, ring) -- R's
    route passes the same integer ids to fect."""
    tc = "treatment" if "treatment" in df.columns else "treat"
    need = ["site_id", "buff_km", "Season", "Year", y_col, "did_term", tc]
    d = df[[c_ for c_ in need if c_ in df.columns]].copy()
    if "site_id" not in d.columns: d["site_id"] = 0
    if "Season" not in d.columns: d["Season"] = 0
    d[y_col] = pd.to_numeric(d[y_col], errors="coerce"); d = d[np.isfinite(d[y_col].values)]
    keys = ["site_id", "buff_km", "Season"]
    Yw = d.groupby(keys + ["Year"], observed=True)[y_col].mean().unstack("Year").sort_index(axis=1)
    core = d.groupby(keys, observed=True)[tc].max().reindex(Yw.index).fillna(0).values.astype(float) == 1
    coh = d[d["did_term"] == 1].groupby(keys, observed=True)["Year"].min().reindex(Yw.index).astype(float).values
    meta = Yw.index.to_frame(index=False); meta["core"] = core; meta["cohort"] = np.where(core, coh, np.inf)
    rows = []
    for s_ in sorted(meta["Season"].unique()):
        for g in sorted(set(meta.loc[meta["core"] & (meta["Season"] == s_) & np.isfinite(meta["cohort"]), "cohort"].astype(int))):
            sel = meta.index[(meta["Season"] == s_) & ((meta["core"] & (meta["cohort"] == g)) | ~meta["core"])]
            sub = Yw.loc[[Yw.index[i] for i in sel]]
            yrs = [y for y in sub.columns if sub[y].notna().any()]
            full = sub[yrs].notna().all(axis=1).values
            ms = meta.loc[sel][full].copy(); sub = sub[full][yrs]
            ms["_o"] = np.where(ms["core"], 0, 1)
            order_ = ms.sort_values(["_o", "site_id", "buff_km"], kind="mergesort").index
            ms = ms.loc[order_]; sub = sub.loc[[Yw.index[i] for i in order_]]
            n1 = int(ms["core"].sum()); n0 = int((~ms["core"]).sum())
            yv = np.array([int(y) for y in yrs]); npost = int((yv >= g).sum()); npre = int((yv < g).sum())
            if not n1 or n0 < 2 or not npost or npre < 2: continue
            Ym = sub.values.T.astype(np.float64)                                   # years x series
            Dm = (ms["core"].values[None, :] & (yv[:, None] >= g)).astype(np.float64)
            cv_nobs = min(3, max(1, npre - 2)); min_t0 = max(1, min(5, npre - cv_nobs)); do_cv = npre >= 3
            rmax = min(4, max(0, npre - 2), max(0, n0 - 1))
            if rmax == 0: do_cv = False
            try:
                att, tune, tab = fect_fit(Ym, Dm, method, r_end=rmax, min_T0=min_t0, cv_nobs=cv_nobs, do_cv=do_cv,
                                          tuning=(None if method == "mc" else 0))
                se = _fect_boot_se(Ym, Dm, method, tune, nboots=nboots)
            except (InsufficientDataError, np.linalg.LinAlgError, ValueError) as e:
                info(f"{method}: the fit of season {s_}, cohort {g} failed -- {e} (left out of the average)"); continue
            if not np.isfinite(att):
                info(f"{method}: season {s_}, cohort {g} gave no finite estimate (left out of the average)"); continue
            rows.append({"Season": int(s_), "cohort": int(g), "n_treated": n1, "n_control": n0, "post_years": npost, "pre_years": npre,
                         "estimate": att, "se": se, "tuning": (float(tune) if tune is not None else np.nan), "cv_ran": bool(do_cv)})
    if not rows:
        raise InsufficientDataError(f"{method}: no cohort x season with a treated series, >= 2 same-season control series and >= 2 pre-period years")
    t = pd.DataFrame(rows); w = (t.n_treated * t.post_years).values.astype(float); w = w / w.sum(); t["weight"] = w
    est = float(np.sum(w * t.estimate)); se = float(np.sqrt(np.sum(w ** 2 * t.se ** 2))) if np.all(np.isfinite(t.se)) else float("nan")
    tn = t["tuning"].values
    tuning_txt = ("lambda " + ",".join(f"{x:.3g}" if np.isfinite(x) else "none (FE)" for x in tn)) if method == "mc" else ("r " + ",".join(str(int(x)) for x in tn))
    return {"att_avg": est, "se": se, "method": method, "fits": int(len(t)), "tuning": tuning_txt,
            "se_how": f"{len(t)} cohort x season fit(s), each a core series against the same season's ring series; each fit's SE by "
                      + ("gsynth's parametric bootstrap" if method == "gsynth" else "fect's nonparametric bootstrap")
                      + f" ({nboots} draws, the tuning fixed; R's own draws: L'Ecuyer-CMRG after set.seed(12345)"
                      + ("" if method == "gsynth" else ", doRNG's streams") + "), combined as independent",
            "engine": f"fect / gsynth ported ({'gsynth' if method == 'gsynth' else 'fect ' + method}; one fit per cohort x season)"}, t


# ====================== v20.57: DOUBLY-ROBUST DiD (Sant'Anna & Zhao 2020), the panel estimator done right ======================
# Found by validate_known_answers.py: M03 averaged its AIPW score over EVERY row -- pre-period rows (whose effect is zero) and
# rows of every season against the first row of the pixel -- so it reported +0.016 for a true +0.05. The estimator is defined on
# ONE change per unit: DeltaY = mean(post) - mean(pre) of each series (pixel x season), the covariates their pre-period means,
# the treated = core series of a cohort, the controls = never-treated ring series over the SAME calendar split (one 2x2 per
# cohort, aggregated by treated series -- the Callaway-Sant'Anna way for staggered starts).
def season_net(df, y_col, treat_col=None):
    """v20.58 (as R's season_net in lib/models_prebuilt.R): the outcome net of the CONTROL rows' mean in the same season and year (and
    sub-watershed; one shared year x season effect under POOLED_FE = "period" with several sub-watersheds) -- the year x season effect the
    design absorbs. Estimators that work on YEARS (Callaway-Sant'Anna, the doubly-robust DiD, Goodman-Bacon, ETWFE, diff-diff's staggered
    family) otherwise compare a Rabi series with rings of every season, whose year shocks differ: your fund timing starts Rabi a year
    before the other seasons (0.059 for a true 0.050 on the poison test). A fixed-effects model with year x season effects is unchanged by it."""
    tc = treat_col or ("treatment" if "treatment" in df.columns else "treat")
    y = pd.to_numeric(df[y_col], errors="coerce").values.astype(np.float64)
    if "Season" not in df.columns or "Year" not in df.columns or tc not in df.columns: return y
    ctrl = pd.to_numeric(df[tc], errors="coerce").values == 0
    ns = int(pd.to_numeric(df["site_id"], errors="coerce").fillna(0).astype(int).pipe(lambda x: x[x > 0]).nunique()) if "site_id" in df.columns else 1
    keys = ["Season", "Year"] if (ns > 1 and ACTIVE.get("pooled_fe", "period") == "period") or "site_id" not in df.columns else ["site_id", "Season", "Year"]
    k = [pd.to_numeric(df[c], errors="coerce").fillna(-1).astype(np.int64).values for c in keys]
    cm = pd.Series(np.where(ctrl, y, np.nan)).groupby(k).transform("mean").values
    out = y - cm
    out[~np.isfinite(out)] = np.nan
    return out

def dr_did_by_cohort(df, y_col, covariates, unit_col="pixel_id", time_col="Year"):
    """v20.57's engine M03 (kept: the per-cohort 2 x 2 table beside the headline): one doubly-robust 2 x 2 per cohort (traditional DR: a
    logistic propensity, OLS on the controls), aggregated by treated series."""
    unit = _unit_key(df, unit_col)
    covs = [c for c in (covariates or []) if c in df.columns]
    cols = list(dict.fromkeys([unit, time_col, "did_term", "treatment", y_col] + covs))
    d = df[cols].copy(); d[y_col] = season_net(df, y_col); d = d[np.isfinite(d[y_col].values)]   # v20.58: season-matched (as R's M03)
    coh = d[d["did_term"] == 1].groupby(unit)[time_col].min()
    treated_units = set(coh.index); never = set(d.loc[d["treatment"] == 0, unit].unique()) - treated_units
    if not treated_units or not never: raise InsufficientDataError("DR-DiD needs treated core series and never-treated ring series")
    rows = []; ifs = []
    for g in sorted(coh.unique()):
        T_ = coh.index[coh.values == g]
        s = d[d[unit].isin(set(T_) | never)]
        pre, post = s[s[time_col] < g], s[s[time_col] >= g]
        yp = pre.groupby(unit)[y_col].mean(); yq = post.groupby(unit)[y_col].mean()
        u = yp.index.intersection(yq.index)
        if len(u) < 4: continue
        dY = (yq[u] - yp[u]).values; D = np.isin(u, T_).astype(float)
        if D.sum() < 1 or (1 - D).sum() < 2: continue
        if covs:
            X = pre.groupby(unit)[covs].mean().reindex(u)
            X = X.fillna(X.mean()).values.astype(float); sd = X.std(axis=0); sd[sd == 0] = 1.0; X = (X - X.mean(axis=0)) / sd
        else:
            X = np.zeros((len(u), 0))
        Xb = np.column_stack([np.ones(len(u)), X])
        b = np.zeros(Xb.shape[1])
        for _ in range(100):                                      # logistic propensity (Newton)
            p = 1 / (1 + np.exp(-np.clip(Xb @ b, -30, 30))); W = p * (1 - p)
            H = (Xb * W[:, None]).T @ Xb + 1e-8 * np.eye(len(b)); step = np.linalg.solve(H, Xb.T @ (D - p)); b += step
            if np.max(np.abs(step)) < 1e-10: break
        p = np.clip(1 / (1 + np.exp(-np.clip(Xb @ b, -30, 30))), 1e-6, 1 - 1e-6)
        c = D == 0
        bo = np.linalg.lstsq(Xb[c], dY[c], rcond=None)[0]; m0 = Xb @ bo          # outcome regression on the controls
        w1 = D / D.mean(); w0 = (p * (1 - D) / (1 - p)); w0 = w0 / w0.mean()
        att = float(np.mean(w1 * (dY - m0)) - np.mean(w0 * (dY - m0)))
        psi = w1 * (dY - m0 - att) - w0 * (dY - m0) + w0 * 0                    # influence function (nuisance estimates taken as known)
        psi = psi - psi.mean()
        rows.append({"cohort": int(g), "ATT": att, "se": float(np.sqrt(np.mean(psi ** 2) / len(psi))), "n_treated_series": int(D.sum()),
                     "n_control_series": int((1 - D).sum())})
    if not rows: raise InsufficientDataError("no cohort with treated and control series observed before AND after its start")
    t = pd.DataFrame(rows); w = t.n_treated_series.values.astype(float)
    att = float(np.average(t.ATT, weights=w)); se = float(np.sqrt(np.sum((w / w.sum()) ** 2 * t.se.values ** 2)))
    return {"ATT": att, "se": se, "n_cohorts": len(t), "n_treated_series": int(w.sum()), "covariates": ",".join(covs),
            "design": "one DeltaY per series (pixel x season), controls = never-treated ring series over each cohort's split"}, t


# ====================== v20.58: THE ENGINE COMPUTES WHAT R's PACKAGE COMPUTES (M03, M04, M19, M28, M29, M31, M35) ======================
# The engine is the fallback: it runs when neither a verified Python package nor a verified R route can. Until v20.57 several engine models
# estimated a neighbouring quantity under the same name (validate_model_parity.py --engine: M03 +4e-5, M04 -3.3e-4, M19 +3.7e-4, M28 +5e-5,
# M29 +1e-4, M31 -2e-5, M35 +2.6e-3 against R). Each is now the SAME estimator as the R route, on R's frame, ported from the package source.
def unit_year_frame(df, y_col, covs=(), unit_col="pixel_id"):
    """R's unit_year (lib/models_prebuilt.R): one row per series (pixel x season) x Year -- the mean of the SEASON-MATCHED outcome
    (season_net), the core flag and the design's post flag (max), the covariates' means; gvar = the series' cohort (its first treated Year,
    first_treat_agri_year; 0 = never treated); cluster_id = the design's cluster (the sub-watershed with >= MIN_SWS_CLUSTERS of them, else the Year)."""
    unit = _unit_key(df, unit_col)
    covs = [c_ for c_ in (covs or []) if c_ in df.columns]
    tcol = "treatment" if "treatment" in df.columns else "treat"
    cl = _cluster_key(df, "subwshed_id")
    ft = pd.to_numeric(df["first_treat_agri_year"], errors="coerce").values.astype(np.float64) if "first_treat_agri_year" in df.columns else np.full(len(df), np.inf)
    d = pd.DataFrame({"unit": df[unit].values, "Year": pd.to_numeric(df["Year"], errors="coerce").values.astype(np.int64),
                      "cluster_id": (df[cl].astype(str).values if cl in df.columns else "1"),
                      "site_id": (pd.to_numeric(df["site_id"], errors="coerce").fillna(0).astype(np.int64).values if "site_id" in df.columns else 1),
                      "gvar": np.where(np.isfinite(ft), ft, 0.0),
                      "y": season_net(df, y_col, treat_col=tcol), "treat": pd.to_numeric(df[tcol], errors="coerce").values.astype(np.float64),
                      "post": pd.to_numeric(df["post"], errors="coerce").values.astype(np.float64),
                      **{c_: pd.to_numeric(df[c_], errors="coerce").values.astype(np.float64) for c_ in covs}})
    d = d[np.isfinite(d["y"].values)]
    if not len(d): raise InsufficientDataError("no row with a season-matched outcome (no control row in the same season and year)")
    agg = {"y": ("y", "mean"), "treat": ("treat", "max"), "post": ("post", "max"), **{c_: (c_, "mean") for c_ in covs}}
    return d.groupby(["unit", "Year", "cluster_id", "site_id", "gvar"], sort=True, observed=True).agg(**agg).reset_index()


def _drdid_imp_panel(dY, D, X=None, trim_level=0.995):
    """DRDID::drdid_imp_panel (Sant'Anna & Zhao 2020: the improved, locally efficient doubly-robust DiD for panel data), ported line by line
    from the package source: the propensity score by CALIBRATION (DRDID's pscore.cal: the logit fit as the start, then the strictly convex
    loss -mean(D x'g - (1 - D) exp(x'g)) minimised -- the weighted covariate means of the controls equal the treated's), ps capped at
    1 - 1e-6, controls with ps >= trim_level trimmed; the outcome regression by least squares on the controls with weights ps / (1 - ps)
    (wols.br.panel); ATT = mean(trim (1 - (1 - D) / (1 - ps)) (dY - m(x))) / mean(D); SE = sd(IF) sqrt(n - 1) / n.
    Returns (att, se, info). The fitted ps and m(x) do not depend on an affine change of the covariates (an intercept is in both models),
    so the columns are standardised for the solver."""
    D = np.asarray(D, np.float64); dY = np.asarray(dY, np.float64); n = len(D)
    if n < 3 or D.sum() < 1 or (1 - D).sum() < 2: raise InsufficientDataError("DR-DiD needs treated series and at least 2 control series")
    Z = np.ones((n, 1))
    if X is not None and np.size(X):
        Xa = np.asarray(X, np.float64).reshape(n, -1); sd_ = Xa.std(axis=0); keep = sd_ > 0
        if keep.any(): Z = np.column_stack([Z, (Xa[:, keep] - Xa[:, keep].mean(axis=0)) / sd_[keep]])
    g = np.zeros(Z.shape[1])
    for _ in range(500):                                                   # the logit fit (DRDID: fastglm) -- the starting value
        p = 1.0 / (1.0 + np.exp(-np.clip(Z @ g, -35, 35))); W = p * (1 - p)
        step = np.linalg.lstsq((Z * W[:, None]).T @ Z, Z.T @ (D - p), rcond=None)[0]; g = g + step
        if not np.all(np.isfinite(g)): g = np.zeros(Z.shape[1]); break
        if np.max(np.abs(step)) < 1e-12: break
    def _loss(gg):
        xi = Z @ gg; return float(-np.mean(np.where(D == 1, xi, -np.exp(np.minimum(xi, 700.0)))))
    conv = False
    for _ in range(2000):                                                  # the calibration (DRDID: trust on loss.ps.cal) -- Newton + backtracking
        xi = Z @ g; ex = np.exp(np.minimum(xi, 700.0))
        grad = -np.mean(np.where(D == 1, 1.0, -ex)[:, None] * Z, axis=0)
        H = (Z * ((1 - D) * ex)[:, None]).T @ Z / n
        step = -np.linalg.lstsq(H, grad, rcond=None)[0]
        f0 = _loss(g); t = 1.0
        while _loss(g + t * step) > f0 + 1e-4 * t * float(grad @ step) and t > 1e-14: t *= 0.5
        g = g + t * step
        if np.max(np.abs(grad)) < 1e-13 or np.max(np.abs(t * step)) < 1e-14 * max(1.0, float(np.max(np.abs(g)))): conv = True; break
    ps = np.minimum(1.0 / (1.0 + np.exp(-(Z @ g))), 1 - 1e-6)
    trim = np.ones(n, bool); trim[D == 0] = ps[D == 0] < trim_level
    c = D == 0; w = ps / (1 - ps)
    Zc = Z[c] * w[c][:, None]
    beta = np.linalg.lstsq(Zc.T @ Z[c], Zc.T @ dY[c], rcond=None)[0]
    out = Z @ beta
    summ = trim * (1 - (1 - D) / (1 - ps)) * (dY - out)
    att = float(np.mean(summ) / np.mean(D))
    inf = trim * (summ - D * att) / np.mean(D)
    se = float(np.std(inf, ddof=1) * np.sqrt(n - 1) / n)
    return att, se, {"calibration_converged": conv, "controls_trimmed": int((~trim).sum()), "ps_max_control": float(ps[c].max()) if c.any() else np.nan}


def dr_did(df, y_col, covariates, unit_col="pixel_id", time_col="Year"):
    """v20.58 -- M03 as R's m03_drdid (DRDID::drdid, estMethod "imp", panel): R's unit_year frame (series x Year, the season-matched outcome);
    each series' pre-period mean and post-period mean by the design's post flag (the 2-period panel DRDID wants; series seen in both periods),
    the covariates = their pre-period means; _drdid_imp_panel above. The per-cohort 2 x 2s of v20.57 stay as the table (dr_did_by_cohort)."""
    covs = [c_ for c_ in (covariates or []) if c_ in df.columns]
    uy = unit_year_frame(df, y_col, covs, unit_col)
    two = uy.groupby(["unit", "post"], observed=True).agg(y=("y", "mean"), treat=("treat", "max")).reset_index()
    nb = two.groupby("unit").size(); two = two[two["unit"].isin(nb.index[nb.values == 2])]
    w = two.pivot(index="unit", columns="post", values="y")
    tr_ = two.groupby("unit")["treat"].max().reindex(w.index)
    X = None
    if covs:
        xc = uy[uy["post"] == 0].groupby("unit")[covs].mean().reindex(w.index)
        ok_ = xc.notna().all(axis=1).values; w = w[ok_]; tr_ = tr_[ok_]; X = xc[ok_].values
    if 0.0 not in w.columns or 1.0 not in w.columns or not len(w): raise InsufficientDataError("no series is seen both before and after its start")
    dY = (w[1.0] - w[0.0]).values; D = tr_.values.astype(np.float64)
    att, se, inf = _drdid_imp_panel(dY, D, X)
    try:
        _, tbl = dr_did_by_cohort(df, y_col, covariates, unit_col=unit_col, time_col=time_col)
    except InsufficientDataError as e:
        tbl = pd.DataFrame([{"note": f"per-cohort 2 x 2 not identified: {e}"}])
    n_coh = int(uy.loc[(uy["treat"] == 1) & (uy["gvar"] > 0), "gvar"].nunique())
    return {"ATT": att, "se": se, "n_cohorts": n_coh, "n_treated_series": int(D.sum()), "n_control_series": int((1 - D).sum()),
            "covariates": ",".join(covs), **inf,
            "se_how": f"DRDID's improved doubly robust DiD (Sant'Anna & Zhao 2020, ported): the influence-function SE over the {len(D):,} pixel x season series (each series one draw; not clustered)",
            "design": "R's m03_drdid: one pre and one post mean per series (the design's post flag), the season-matched outcome, the covariates' pre-period means"}, tbl


def cic_qte(df, y_col, unit_col="pixel_id", iters=200, seed=12345):
    """v20.58 -- M04 as R's m04_cic (qte::CiC, panel, no covariates) on R's unit_year frame collapsed to one pre and one post mean per series:
    ATT = mean(treated post) - mean(Q0_post(F0_pre(treated pre))), F0_pre = the controls' pre-period ECDF, Q0_post = the controls' post-period
    quantile function of R's type 1 (the k-th order statistic, k = the treated value's rank among the controls' pre values; the smallest when
    k = 0) -- qte's compute.CiC line by line. SE: qte's panel bootstrap with R's OWN draws (v20.58, second pass): R's route runs it
    sequentially (qte's bootstrap uses the cores only on Linux / macOS, where its draws then depend on the number of cores; on Windows it is
    sequential) inside seeded() -- L'Ecuyer-CMRG after set.seed(12345); per draw sample(ids, n, TRUE) (the series in (pixel, season) order,
    R's integer ids) and sample(1:n, n) (qte's new ids), then compute.CiC; SE = sd of the 200 bootstrap ATTs."""
    uy = unit_year_frame(df, y_col, (), unit_col)
    two = uy.groupby(["unit", "post"], observed=True).agg(y=("y", "mean"), treat=("treat", "max")).reset_index()
    nb = two.groupby("unit").size(); two = two[two["unit"].isin(nb.index[nb.values == 2])]
    w = two.pivot(index="unit", columns="post", values="y"); tr_ = two.groupby("unit")["treat"].max().reindex(w.index).values == 1
    _uk = _unit_key(df, unit_col); _oc = [c_ for c_ in ("pixel_id", "Season") if c_ in df.columns]
    if _oc:                                                                  # R's uid: the series in (pixel, season) order
        _um = df[[_uk] + [c_ for c_ in _oc if c_ != _uk]].groupby(_uk, observed=True).min()
        _ord = _um.reindex(w.index).reset_index().sort_values([c_ if c_ in _um.columns else _uk for c_ in _oc], kind="mergesort").index.values
        w = w.iloc[_ord]; tr_ = tr_[_ord]
    if 0.0 not in w.columns or 1.0 not in w.columns: raise InsufficientDataError("no series is seen both before and after its start")
    y0, y1 = w[0.0].values, w[1.0].values
    if tr_.sum() < 1 or (~tr_).sum() < 2: raise InsufficientDataError("changes-in-changes needs treated series and >= 2 control series")
    def _q1(x_sorted, p):                                                    # R's quantile(type = 1), its floating point included:
        nn = len(x_sorted); nppm = nn * np.asarray(p, np.float64)            #   j = floor(n p + 4 eps), h = (n p > j) -- no fuzz in h, so
        j = np.floor(nppm + 4 * np.finfo(np.float64).eps).astype(np.int64)  #   n * (k / n) rounding above k takes the (k+1)-th value
        idx = np.where(nppm > j, j + 1, j)
        return x_sorted[np.clip(idx, 1, nn) - 1]
    def _att(y0_, y1_, t_):
        c0 = np.sort(y0_[~t_]); c1 = np.sort(y1_[~t_]); n0 = len(c0)
        k = np.searchsorted(c0, y0_[t_], side="right")                       # F0(v) = #(c0 <= v) / n0 (R's ecdf)
        cf = _q1(c1, k / float(n0))                                          # Q0_post(F0_pre(v)), type 1
        return float(np.mean(y1_[t_]) - np.mean(cf))
    att = _att(y0, y1, tr_)
    rr = _RRandom(seed, "L'Ecuyer-CMRG"); n = len(y0); bs = []
    for _ in range(int(iters)):                                              # qte:::bootiter (panel)
        i = np.asarray(rr.sample_int(n, n, True)) - 1; rr.sample_int(n, n)   #   ids <- sample(ids, n, TRUE); newids <- sample(seq(1, n), n)
        t_ = tr_[i]
        if t_.sum() >= 1 and (~t_).sum() >= 1: bs.append(_att(y0[i], y1[i], t_))
    se = float(np.std(bs, ddof=1)) if len(bs) > 1 else np.nan
    # the quantile effects (qte: probs 0.1 ... 0.9, type 1 on both sides)
    c0 = np.sort(y0[~tr_]); c1 = np.sort(y1[~tr_]); k = np.searchsorted(c0, y0[tr_], side="right"); cf = np.sort(_q1(c1, k / float(len(c0))))
    probs = 0.1 + np.arange(9) * 0.1                                         # R's seq(0.1, 0.9, 0.1): from + (0:8) * by, bit for bit
    qte = pd.DataFrame({"prob": probs, "QTE": _q1(np.sort(y1[tr_]), probs) - _q1(cf, probs)})
    return {"ATT_CiC": att, "se": se, "n_treated_series": int(tr_.sum()), "n_control_series": int((~tr_).sum()), "bootstrap_draws": len(bs),
            "se_how": f"the panel bootstrap of qte::CiC ({len(bs)} draws of the {n:,} pixel x season series, resampled with replacement; not clustered; "
                      f"R's own draws: L'Ecuyer-CMRG after set.seed(12345), sequential)",
            "design": "R's m04_cic: qte::CiC on one pre and one post mean per series (the season-matched outcome)"}, qte


def _event_code(df):
    """The design's event time per row with R's codes: the design's event time for the core's series (first_treat_agri_year finite), -1000
    for the never-treated series (R's did2s route: d[!is.finite(event_time), event_time := -1000])."""
    ft = pd.to_numeric(df["first_treat_agri_year"], errors="coerce").values.astype(np.float64)
    et = pd.to_numeric(df["event_time"], errors="coerce").values.astype(np.float64)
    return np.where(np.isfinite(ft) & np.isfinite(et), et, -1000.0)


def did2s_event(df, y_col, unit_col="pixel_id", time_col="time_fe_yearseason", treated_col="did_term"):
    """v20.58 -- M28 as R's m28_did2s (did2s::did2s, Gardner 2021): stage 1 = unit (pixel x season) + period (year x season) effects fitted
    on the UNTREATED rows (did = 0) -- first_stage = ~ 0 | unit + period; every row residualised; stage 2 = OLS of the residual on one dummy
    per event time (reference: -1 and the never-treated), with an intercept (fixest's default); the headline = the mean of the event-time
    coefficients e >= 0 (R's event_headline). Returns (headline dict, event-time table)."""
    unit = _unit_key(df, unit_col)
    d = df[np.isfinite(pd.to_numeric(df[y_col], errors="coerce").values)]
    y = pd.to_numeric(d[y_col], errors="coerce").values.astype(np.float64)
    u = pd.factorize(d[unit].values)[0]; t = pd.factorize(d[time_col].astype(str).values)[0]
    untr = pd.to_numeric(d[treated_col], errors="coerce").values == 0
    if untr.sum() < 3: raise InsufficientDataError("did2s needs untreated rows for its first stage")
    ua, ta = u[untr], t[untr]; y0 = y[untr]
    alp = np.zeros(u.max() + 1); gam = np.zeros(t.max() + 1)
    cu = np.bincount(ua, minlength=len(alp)); ct = np.bincount(ta, minlength=len(gam))
    for it in range(1_000_000):                                          # alternating projections on the untreated rows (exact, 1e-15)
        alp_n = np.where(cu > 0, np.bincount(ua, weights=y0 - gam[ta], minlength=len(alp)) / np.maximum(cu, 1), 0.0)
        gam_n = np.where(ct > 0, np.bincount(ta, weights=y0 - alp_n[ua], minlength=len(gam)) / np.maximum(ct, 1), 0.0)
        dlt = max(float(np.max(np.abs(alp_n - alp))), float(np.max(np.abs(gam_n - gam))))
        alp, gam = alp_n, gam_n
        if dlt < 1e-15 * max(1.0, float(np.max(np.abs(y0)))): break
    ok_ = (cu[u] > 0) & (ct[t] > 0)                                      # a row whose unit / period has no untreated row: not residualised (fixest drops it)
    r = np.where(ok_, y - alp[u] - gam[t], np.nan)
    ev = _event_code(d)
    m = np.isfinite(r)
    evs = sorted(set(np.unique(ev[m]).tolist()) - {-1.0, -1000.0})
    # did2s's second stage: feols(~ 0 + i(event_time, ref = c(-1, -1000))) -- NO intercept, exclusive dummies: each coefficient is the mean
    # residual of its event time (the reference rows enter with no dummy)
    rows_ = [(int(e), float(np.mean(r[m & (ev == e)])), int((m & (ev == e)).sum())) for e in evs]
    tab = pd.DataFrame(rows_, columns=["event_time", "beta", "n_rows"])
    post = tab[tab["event_time"] >= 0]
    if not len(post): raise InsufficientDataError("no post-period event time")
    est = float(post["beta"].mean())
    return {"ATT_gardner": est, "n_event_times_post": int(len(post)),
            "design": "R's m28_did2s: did2s first stage ~ 0 | unit + period on the untreated rows, second stage ~ 0 + i(event_time, ref = c(-1, -1000)); "
                      "the headline = the mean of the event-time effects e >= 0"}, tab


def exposure_twfe(df, y_col, unit_col="pixel_id", time_col="time_fe_yearseason", cluster_col="subwshed_id"):
    """v20.58 -- M29 as R's m29_exposure: exposure = event time + 1 on the core's post rows (0 elsewhere), feols(y ~ i(exposure, ref = 0) |
    unit + period, cluster = ~cluster_id) -- the dummies demeaned two-way with y, OLS, the CR1 covariance with fixest's small-sample factors;
    the headline = the equal-weighted mean of the exposure-year effects, its SE by the delta method, p from t with G - 1 df."""
    from scipy import stats as _st
    unit = _unit_key(df, unit_col); cl = _cluster_key(df, cluster_col)
    d = df[np.isfinite(pd.to_numeric(df[y_col], errors="coerce").values)]
    tr = pd.to_numeric(d["treatment"], errors="coerce").values == 1; po = pd.to_numeric(d["post"], errors="coerce").values == 1
    et = pd.to_numeric(d["event_time"], errors="coerce").values.astype(np.float64)
    expo = np.where(tr & po, np.maximum(et, 0) + 1, 0).astype(np.int64)
    levels = sorted(int(v) for v in np.unique(expo) if v > 0)
    if not levels: raise InsufficientDataError("no treated post-period row (no exposure)")
    f1 = pd.factorize(d[unit].values)[0]; f2 = pd.factorize(d[time_col].astype(str).values)[0]
    Xr = np.column_stack([(expo == k).astype(np.float64) for k in levels])
    y = pd.to_numeric(d[y_col], errors="coerce").values.astype(np.float64)
    M = demean_columns(np.column_stack([y, Xr]), f1, f2, tol=1e-14, max_iter=100000)
    yd, Xd = M[:, 0], M[:, 1:]
    keep = Xd.std(axis=0) > 1e-12
    Xd = Xd[:, keep]; levels = [lv for lv, k_ in zip(levels, keep) if k_]
    G_ = Xd.T @ Xd; beta = np.linalg.solve(G_, Xd.T @ yd); e = yd - Xd @ beta
    cid = pd.factorize(pd.Series(np.asarray(d[cl].values)).astype(str))[0]; G = int(cid.max()) + 1
    if G < 2: raise InsufficientDataError("one cluster: no cluster-robust SE")
    S = np.column_stack([np.bincount(cid, weights=Xd[:, j] * e, minlength=G) for j in range(Xd.shape[1])])
    n = len(yd); k = Xd.shape[1]; kfe = _k_fe_nonnested([f1, f2], cid)
    Gi = np.linalg.inv(G_); V = Gi @ (S.T @ S) @ Gi * (G / (G - 1)) * ((n - 1) / max(1, n - k - kfe))
    w = np.full(k, 1.0 / k); est = float(w @ beta); se = float(np.sqrt(w @ V @ w))
    p = float(2 * _st.t.sf(abs(est / se), max(1, G - 1))) if se > 0 else np.nan
    tab = pd.DataFrame({"event_time": [lv - 1 for lv in levels], "exposure": levels, "ATT_by_exposure": beta, "se": np.sqrt(np.diag(V)),
                        "p_value": [float(2 * _st.t.sf(abs(b_ / s_), max(1, G - 1))) if s_ > 0 else np.nan for b_, s_ in zip(beta, np.sqrt(np.diag(V)))]})
    return {"estimate": est, "se": se, "p_value": p, "n_exposure_years": k, "n_clusters": G,
            "se_how": f"the mean of the {k} exposure-year effects of the two-way FE fit (fixest's i(exposure)); its SE by the delta method on the CR1 covariance clustered by {cl} ({G} clusters)",
            "p_how": f"t with {max(1, G - 1)} df", "design": "R's m29_exposure: feols(y ~ i(exposure, ref = 0) | unit + period, cluster = ~cluster_id)"}, tab


def stacked_series(df, y_col, unit_col="pixel_id", window=(-3, 3)):
    """v20.58 -- M31 as R's m31_stacked: on R's unit_year frame (series x Year, the season-matched outcome), one stack per cohort g -- the
    cohort's series and the clean controls (never treated, or treated after g + 3), Years g - 3 ... g + 3 --, D = the cohort's series from g;
    feols(y ~ D | unit^stack + Year^stack, cluster = ~cluster_id): exact two-way demeaning, the CR1 covariance with fixest's small-sample factors."""
    from scipy import stats as _st
    uy = unit_year_frame(df, y_col, (), unit_col)
    cohorts = sorted(float(g) for g in uy.loc[uy["gvar"] > 0, "gvar"].unique())
    if not cohorts: raise InsufficientDataError("no treated cohort")
    parts = []
    for g in cohorts:
        s = uy[(uy["gvar"] == g) | (uy["gvar"] == 0) | (uy["gvar"] > g + window[1])]
        s = s[(s["Year"] >= g + window[0]) & (s["Year"] <= g + window[1])].copy()
        s["stack"] = g; s["D"] = ((s["gvar"] == g) & (s["Year"] >= g)).astype(np.float64); parts.append(s)
    st = pd.concat(parts, ignore_index=True)
    f1 = pd.factorize(st["unit"].astype(str) + "|" + st["stack"].astype(str))[0]; f2 = pd.factorize(st["Year"].astype(str) + "|" + st["stack"].astype(str))[0]
    M = demean_columns(np.column_stack([st["y"].values.astype(np.float64), st["D"].values]), f1, f2, tol=1e-14, max_iter=100000)
    yd, xd = M[:, 0], M[:, 1]
    if float(xd @ xd) < 1e-14: raise InsufficientDataError("D has no variation within the stacks")
    b = float((xd @ yd) / (xd @ xd)); e = yd - b * xd
    cid = pd.factorize(st["cluster_id"].astype(str))[0]; G = int(cid.max()) + 1
    if G < 2: raise InsufficientDataError("one cluster: no cluster-robust SE")
    s_g = np.bincount(cid, weights=xd * e, minlength=G); n = len(yd); kfe = _k_fe_nonnested([f1, f2], cid)
    se = float(np.sqrt((s_g @ s_g) / (xd @ xd) ** 2 * (G / (G - 1)) * ((n - 1) / max(1, n - 1 - kfe))))
    # the p as R's save_result: t with (the design's clusters on the model's sample) - 1 -- the stacks' window may hold fewer years than the sample
    _cl = _cluster_key(df, "subwshed_id"); Gd = int(pd.Series(np.asarray(df[_cl].values)).nunique()) if _cl in df.columns else G
    p = float(2 * _st.t.sf(abs(b / se), max(1, Gd - 1))) if se > 0 else np.nan
    return {"ATT_stacked": b, "se": se, "p_value": p, "n_sub_experiments": len(cohorts), "n_stacked_rows": int(n), "n_clusters": G, "n_clusters_design": Gd,
            "se_how": f"feols on the stacked series-years (unit x stack and Year x stack effects), CR1 clustered by {'sub-watershed' if 'site' in str(_cluster_key(df, 'subwshed_id')) else 'Year'} ({G} clusters)",
            "p_how": f"t with {max(1, Gd - 1)} df (the design's clusters - 1)", "design": "R's m31_stacked: clean controls, window -3 ... +3, feols(y ~ D | unit^stack + Year^stack)"}, st


def icc_reml(df, y_col, max_q2=5000):
    """v20.58 -- M19 as R's m19_icc: lme4::lmer(y ~ did + (1 | grp) + (1 | pixel_id)) by REML -- grp = the sub-watershed with >= 2 of them,
    else the Year; ICC = the grp component's share of the total variance (pixel + grp + residual). The profiled REML deviance of lme4
    (Bates et al. 2015, eq. 42: log|L|^2 + log|R_X|^2 + (n - p)(1 + log(2 pi r^2 / (n - p)))) is computed EXACTLY for the two crossed random
    intercepts: the pixel block of L L' = Lambda' Z' Z Lambda + I is diagonal and is eliminated in closed form, the rest (grp levels, the
    fixed effects, y) is a small dense Schur complement; theta = (sd_pixel, sd_grp) / sigma minimised with bounds theta >= 0 (lme4: bobyqa).
    y and did are centred (the intercept absorbs it: the REML deviance is unchanged). Returns (headline dict, variance table)."""
    from scipy.optimize import minimize
    ns = int(pd.to_numeric(df["site_id"], errors="coerce").fillna(0).astype(int).pipe(lambda x: x[x > 0]).nunique()) if "site_id" in df.columns else 1
    grp = "site_id" if ns >= 2 else "Year"
    y = pd.to_numeric(df[y_col], errors="coerce").values.astype(np.float64)
    dd = pd.to_numeric(df["did_term"], errors="coerce").values.astype(np.float64)
    ok_ = np.isfinite(y) & np.isfinite(dd)
    y, dd = y[ok_], dd[ok_]
    pix = pd.factorize(df["pixel_id"].values[ok_])[0]; gg = pd.factorize(df[grp].values[ok_])[0]
    n = len(y); q1 = int(pix.max()) + 1; q2 = int(gg.max()) + 1
    if q2 > max_q2: raise InsufficientDataError(f"{q2} levels of {grp}: too many for the dense grp block")
    if q2 < 2 or q1 < 2: raise InsufficientDataError(f"the ICC needs >= 2 levels of {grp} and of the pixels")
    yc = y - y.mean(); X = np.column_stack([np.ones(n), dd - dd.mean()]); p = X.shape[1]
    d1 = np.bincount(pix, minlength=q1).astype(np.float64); d2 = np.bincount(gg, minlength=q2).astype(np.float64)
    N12 = np.zeros((q1, q2)); np.add.at(N12, (pix, gg), 1.0)
    Z1R = np.column_stack([np.bincount(pix, weights=X[:, j], minlength=q1) for j in range(p)] + [np.bincount(pix, weights=yc, minlength=q1)])
    Z2R = np.column_stack([np.bincount(gg, weights=X[:, j], minlength=q2) for j in range(p)] + [np.bincount(gg, weights=yc, minlength=q2)])
    W = np.column_stack([X, yc]); RR = W.T @ W                               # [X y]' [X y]
    def _parts(th):
        t1, t2 = float(th[0]), float(th[1])
        a11 = t1 * t1 * d1 + 1.0
        M1r = np.column_stack([t1 * t2 * N12, t1 * Z1R])                    # the pixel rows of the augmented system (q1 x (q2 + p + 1))
        Mrr = np.zeros((q2 + p + 1, q2 + p + 1))
        Mrr[:q2, :q2] = np.diag(t2 * t2 * d2 + 1.0); Mrr[:q2, q2:] = t2 * Z2R; Mrr[q2:, :q2] = (t2 * Z2R).T; Mrr[q2:, q2:] = RR
        S = Mrr - (M1r / a11[:, None]).T @ M1r
        S22 = S[:q2, :q2]; L2 = np.linalg.cholesky(S22)
        S2r = S[:q2, q2:]; Srr = S[q2:, q2:] - S2r.T @ np.linalg.solve(S22, S2r)
        Sbb = Srr[:p, :p]; Lb = np.linalg.cholesky(Sbb); b = np.linalg.solve(Sbb, Srr[:p, p]); r2 = float(Srr[p, p] - Srr[:p, p] @ b)
        ld = float(np.sum(np.log(a11)) + 2 * np.sum(np.log(np.diag(L2))) + 2 * np.sum(np.log(np.diag(Lb))))
        return ld, r2
    def _dev(th):
        try:
            ld, r2 = _parts(th)
            return ld + (n - p) * (1.0 + np.log(2 * np.pi * r2 / (n - p))) if r2 > 0 else np.inf
        except np.linalg.LinAlgError:
            return np.inf
    best = None
    for x0 in ((1.0, 1.0), (0.5, 0.5), (2.0, 0.2)):                          # lme4 starts at theta = 1; two more starts guard the bounds
        r_ = minimize(_dev, np.array(x0), method="L-BFGS-B", bounds=[(0.0, None), (0.0, None)], options={"ftol": 1e-15, "gtol": 1e-11, "maxiter": 5000})
        if best is None or r_.fun < best.fun: best = r_
    r_ = minimize(_dev, best.x, method="Nelder-Mead", options={"xatol": 1e-12, "fatol": 1e-13, "maxiter": 20000})   # polish
    if r_.fun <= best.fun: best = r_
    th = np.maximum(best.x, 0.0); _, r2 = _parts(th); s2 = r2 / (n - p)
    comps = {"pixel_id": s2 * th[0] ** 2, grp: s2 * th[1] ** 2, "Residual": s2}
    tot = sum(comps.values())
    tab = pd.DataFrame([{"group": k, "variance": v, "share": v / tot} for k, v in comps.items()])
    return {"ICC": float(comps[grp] / tot), "grouping": grp, "reml_deviance": float(best.fun), "theta_pixel": float(th[0]), "theta_grp": float(th[1]),
            "n_obs": int(n), "n_pixels": int(q1), f"n_{grp}": int(q2),
            "se_note": f"the share of the outcome's variance between {'sub-watersheds' if grp == 'site_id' else 'years'} (REML variance components, as lme4): descriptive, it has no sampling SE",
            "design": "R's m19_icc: lmer(y ~ did + (1 | grp) + (1 | pixel_id)), REML"}, tab


def _rq_lp(X, y, tau):
    """The linear-programming quantile regression (Koenker & Bassett 1978): min tau sum(u+) + (1 - tau) sum(u-), X b + u+ - u- = y -- solved
    exactly by HiGHS (the optimum quantreg's interior point method converges to)."""
    from scipy.optimize import linprog
    from scipy import sparse as _sp
    n, k = X.shape
    A = _sp.hstack([_sp.csr_matrix(X), _sp.identity(n, format="csr"), -_sp.identity(n, format="csr")], format="csr")
    c = np.concatenate([np.zeros(k), np.full(n, tau), np.full(n, 1.0 - tau)])
    bounds = [(None, None)] * k + [(0, None)] * (2 * n)
    r = linprog(c, A_eq=A, b_eq=y, bounds=bounds, method="highs")
    if r.status != 0: raise InsufficientDataError(f"the quantile regression LP did not solve ({r.message})")
    return r.x[:k]


def _rq_fnb(X, yv, tau, beta=0.99995, eps=1e-6, maxit=500):
    """quantreg's rq(method = "fn") -- the Frisch-Newton interior point method of Portnoy & Koenker (1997), ported line by line from
    quantreg/src/rqfnb.f (lpfnb + stepy): the dual LP max c'x s.t. a x = b, 0 <= x <= 1 with a = X', c = -y, b = (1 - tau) X'1, Mehrotra's
    predictor-corrector steps (step factor beta = 0.99995), stopped when the duality gap < eps (1e-6); the coefficients = -(the dual y).
    When the median regression's optimum is NOT unique (a discrete design -- rq's "br" warns "Solution may be nonunique") the simplex and
    HiGHS return a vertex of the optimal face and this method a point inside it: R's route uses "fn", so the engine does too."""
    from scipy.linalg import cho_factor, cho_solve
    a = np.ascontiguousarray(np.asarray(X, np.float64).T); c = -np.asarray(yv, np.float64)
    p, n = a.shape
    if tau < eps or tau > 1 - eps: raise InsufficientDataError("no Frisch-Newton method for tau outside (0, 1)")
    b = (1.0 - tau) * a.sum(axis=1)
    u = np.ones(n); x = np.full(n, 1.0 - tau)
    def stepy(d_, rhs_):
        ada = (a * d_) @ a.T
        cf = cho_factor(ada, lower=False)
        return cho_solve(cf, rhs_), cf
    y, cf = stepy(np.ones(n), a @ c)
    s = c - a.T @ y
    small = np.abs(s) < eps
    z = np.maximum(s, 0.0) + np.where(small, eps, 0.0); w = np.maximum(-s, 0.0) + np.where(small, eps, 0.0)
    s = u - x
    gap = float(z @ x + w @ s); it = 0
    while gap > eps and it < maxit:
        it += 1
        d = 1.0 / (z / x + w / s); ds = z - w; dz = d * ds
        dy = b - a @ x + a @ dz
        rhs = dy.copy()
        dy, cf = stepy(d, dy)
        ds = a.T @ dy - ds
        dx = d * ds; ds = -dx
        dz = -z * (dx / x + 1.0); dw = -w * (ds / s + 1.0)
        def _steps(dx_, ds_, dz_, dw_):
            dp = min([1e20] + list((-x[dx_ < 0] / dx_[dx_ < 0])) + list((-s[ds_ < 0] / ds_[ds_ < 0])))
            dd = min([1e20] + list((-z[dz_ < 0] / dz_[dz_ < 0])) + list((-w[dw_ < 0] / dw_[dw_ < 0])))
            return min(beta * dp, 1.0), min(beta * dd, 1.0)
        deltap, deltad = _steps(dx, ds, dz, dw)
        if min(deltap, deltad) < 1.0:
            mu = float(x @ z + s @ w)
            g = (mu + deltap * float(dx @ z) + deltad * float(dz @ x) + deltap * deltad * float(dz @ dx)
                 + deltap * float(ds @ w) + deltad * float(dw @ s) + deltap * deltad * float(ds @ dw))
            mu = mu * ((g / mu) ** 3) / float(2 * n)
            dr = d * (mu * (1.0 / s - 1.0 / x) + dx * dz / x - ds * dw / s)
            dy = rhs + a @ dr                                                # dswap(rhs, dy); dy = a dr + dy
            dy = cho_solve(cf, dy)                                           # dpotrs with the factor of the last stepy
            uu = a.T @ dy
            dxdz = dx * dz; dsdw = ds * dw
            dx = d * (uu - z + w) - dr; ds = -dx
            dz = -z + (mu - z * dx - dxdz) / x
            dw = -w + (mu - w * ds - dsdw) / s
            deltap, deltad = _steps(dx, ds, dz, dw)
        x = x + deltap * dx; s = s + deltap * ds; y = y + deltad * dy; z = z + deltad * dz; w = w + deltad * dw
        gap = float(z @ x + w @ s)
    return -y


def _rq_cluster_se(X, r, tau, cl):
    """R's rq_cluster_se (Parente & Santos Silva 2016): V = A^-1 B A^-1 G / (G - 1), A = sum f_i x_i x_i' (Gaussian kernel at 0 with quantreg's
    Hall-Sheather bandwidth), B = sum_g s_g s_g', s_g = sum (tau - 1[r < 0]) x_i."""
    from scipy import stats as _st
    n = len(r)
    x0 = _st.norm.ppf(tau); f0 = _st.norm.pdf(x0)                            # quantreg::bandwidth.rq(tau, n, hs = TRUE)
    h = n ** (-1 / 3) * _st.norm.ppf(1 - 0.05 / 2) ** (2 / 3) * ((1.5 * f0 ** 2) / (2 * x0 ** 2 + 1)) ** (1 / 3)
    while (tau - h < 0) or (tau + h > 1): h /= 2
    q75, q25 = np.quantile(r, 0.75), np.quantile(r, 0.25)
    h = (_st.norm.ppf(tau + h) - _st.norm.ppf(tau - h)) * min(np.sqrt(np.var(r, ddof=1)), (q75 - q25) / 1.34)
    A = (X * np.sqrt(_st.norm.pdf(r / h) / h)[:, None]).T @ (X * np.sqrt(_st.norm.pdf(r / h) / h)[:, None])
    s = X * (tau - (r < 0).astype(np.float64))[:, None]
    codes = pd.factorize(pd.Series(np.asarray(cl)).astype(str))[0]; G = int(codes.max()) + 1
    if G < 2: raise InsufficientDataError("one cluster: no cluster-robust SE")
    S = np.column_stack([np.bincount(codes, weights=s[:, j], minlength=G) for j in range(X.shape[1])])
    Ai = np.linalg.inv(A)
    return np.sqrt(np.maximum(np.diag(Ai @ (S.T @ S) @ Ai) * G / (G - 1), 0.0))


def quantile_did_rq(df, y_col, taus=(0.1, 0.25, 0.5, 0.75, 0.9), unit_col="pixel_id", period_col="time_fe_yearseason"):
    """v20.58 -- M35 as R's m35_qdid: y_w = y minus its series' PRE-period mean; rq(y_w ~ did + period, tau) at each tau (period = one dummy
    per year x season); the SE of each quantile effect clustered as the design is (Parente & Santos Silva: R's rq_cluster_se) when the clusters
    are sub-watersheds -- with the YEARS as the clusters R leaves it out (the did scores of the pre years are 0) and the headline takes the
    design-based SE; the headline = tau 0.5. Returns (headline dict, table)."""
    from scipy import stats as _st
    unit = _unit_key(df, unit_col); cl = _cluster_key(df, "subwshed_id")
    d = df[np.isfinite(pd.to_numeric(df[y_col], errors="coerce").values)]
    y = pd.to_numeric(d[y_col], errors="coerce").values.astype(np.float64)
    po = pd.to_numeric(d["post"], errors="coerce").values == 0
    u = pd.factorize(d[unit].values)[0]
    pre_mean = np.bincount(u, weights=np.where(po, y, 0.0)) / np.maximum(np.bincount(u, weights=po.astype(np.float64)), 1)
    has_pre = np.bincount(u, weights=po.astype(np.float64)) > 0
    keep = has_pre[u]
    y_w = (y - pre_mean[u])[keep]
    per = pd.Categorical(d[period_col].astype(str).values[keep])
    P = pd.get_dummies(per, drop_first=True).values.astype(np.float64)       # R: factor(period), first level the reference
    X = np.column_stack([np.ones(int(keep.sum())), pd.to_numeric(d["did_term"], errors="coerce").values[keep].astype(np.float64), P])
    G = int(pd.Series(np.asarray(d[cl].values)[keep]).nunique()); yr_ = (cl == "Year")
    clv = np.asarray(d[cl].values)[keep]
    # YOUR 98 % RULE (as R's m35_qdid / m35_batches): every row at once when the interior point method's arrays fit below 98 % of the RAM
    # (X, its transpose, ~14 n-vectors); else batches of PIXELS (every row of a pixel in one batch, the treated spread evenly), the batch
    # coefficients averaged with the rows as weights, the SE the mean of the batch SEs (conservative: the batches share the year shocks)
    cap = rows_that_fit(8.0 * (3 * X.shape[1] + 16)) or len(y_w)
    if len(y_w) > cap:
        px = pd.factorize(np.asarray(d["pixel_id"].values)[keep])[0]; npx = int(px.max()) + 1; k = int(np.ceil(len(y_w) / cap))
        trp = np.bincount(px, weights=X[:, 1]) > 0; bpx = np.empty(npx, np.int64); rng = np.random.default_rng(1)
        for tv in (False, True):
            ii = np.flatnonzero(trp == tv); bpx[ii] = rng.permutation(np.resize(np.arange(k), len(ii)))
        bat = bpx[px]
        info(f"M35 quantile regression: {npx:,} pixels in {k} batches (all {len(y_w):,} rows at once would pass 98 % of the RAM); every row is used, none is sampled")
    else:
        bat = np.zeros(len(y_w), np.int64); k = 1
    rows = []
    for tau in taus:
        bs_, ses_, ns_ = [], [], []
        for j in range(k):
            mj = bat == j
            Xj = X[mj]; Xj = Xj[:, np.r_[True, True, Xj[:, 2:].std(axis=0) > 0]] if X.shape[1] > 2 else Xj   # a period absent from the batch
            b = _rq_fnb(Xj, y_w[mj], float(tau)); r = y_w[mj] - Xj @ b     # quantreg's "fn" (R's route); _rq_lp = the exact vertex
            se_j = np.nan
            if not yr_:
                try: se_j = float(_rq_cluster_se(Xj, r, float(tau), clv[mj])[1])
                except Exception as e: info(f"M35 tau {tau}: the cluster-robust SE failed -- {e}")
            bs_.append(float(b[1])); ses_.append(se_j); ns_.append(int(mj.sum()))
        b1 = float(np.average(bs_, weights=ns_)); se_c = float(np.mean(ses_)) if all(np.isfinite(ses_)) else np.nan
        rows.append({"quantile": float(tau), "QTE": b1, "se": se_c, "batches": k,
                     "p_value": float(2 * _st.t.sf(abs(b1 / se_c), max(1, G - 1))) if np.isfinite(se_c) and se_c > 0 else np.nan,
                     "clusters": G, "cluster_by": cl,
                     "se_note": ("the years are the clusters: the quantile regression's cluster-robust SE rests on the post years only (the did scores of the "
                                 "pre years are 0) -- not valid; the design-based SE is used") if yr_ else ""})
    tab = pd.DataFrame(rows); h = tab[np.isclose(tab["quantile"], 0.5)].iloc[0]
    return {"QTE": float(h["QTE"]), "se": float(h["se"]), "p_value": float(h["p_value"]), "se_note": str(h["se_note"]),
            "design": "R's m35_qdid: y minus its series' pre-period mean, rq(y_w ~ did + period, method = 'fn') -- quantreg's Frisch-Newton, ported"}, tab


def validate_ml(verbose=True):
    """Simulation validation for every ML/AI causal method above."""
    from sklearn.linear_model import LogisticRegression  # noqa
    def make(n=3000,seed=0,hetero=True):
        rng=np.random.default_rng(seed); X=rng.normal(0,1,(n,5))
        ps=1/(1+np.exp(-(0.9*X[:,0]+0.6*X[:,1])))
        D=(rng.uniform(size=n)<ps).astype(float)
        tau=2.0+(2.0*X[:,0] if hetero else 0.0)
        Y=1.5*X[:,0]+1.0*X[:,1]-0.7*X[:,2]+tau*D+rng.normal(0,0.5,n)
        return X,D,Y,tau
    res={}
    X,D,Y,_=make(hetero=False)
    naive=Y[D==1].mean()-Y[D==0].mean(); r=dml_ate(X,D,Y)
    res["dml"]= "PASS" if abs(r["theta_dml"]-2)<0.2<abs(naive-2) else f"FAIL {r}"
    X,D,Y,tau=make(hetero=True)
    for nm,fn in [("s_learner",s_learner),("t_learner",t_learner),("x_learner",x_learner),
                   ("bart_style",bart_style_causal)]:
        c=fn(X,D,Y); res[nm]="PASS" if np.corrcoef(c,tau)[0,1]>0.7 else f"FAIL corr={np.corrcoef(c,tau)[0,1]:.2f}"
    c,_=dr_learner(X,D,Y); res["dr_learner"]="PASS" if np.corrcoef(c,tau)[0,1]>0.7 else "FAIL"
    c,_=causal_forest(X,D,Y); res["causal_forest"]="PASS" if np.corrcoef(c,tau)[0,1]>0.7 else "FAIL"
    rng=np.random.default_rng(3); npre,npost=20,6
    tr_=np.cumsum(rng.normal(.3,.2,npre+npost))
    tp=tr_[:npre]+rng.normal(0,.3,npre); tq=tr_[npre:]+4.0+rng.normal(0,.3,npost)
    dn=np.array([tr_+rng.normal(0,2)+rng.normal(0,.3,npre+npost) if i<3
                 else rng.normal(0,3,npre+npost).cumsum()*0.1+rng.normal(0,2) for i in range(25)])
    r2,_=lasso_synthetic_control(tp,dn[:,:npre],tq,dn[:,npre:])
    res["lasso_sc"]="PASS" if abs(r2["ATT_lasso_sc"]-4.0)<1.5 else f"FAIL {r2}"
    if verbose:
        for k,v in res.items(): (ok if v=="PASS" else fail)(f"ML validation {k}: {v}")
    n=sum(1 for v in res.values() if v=="PASS")
    print(f"\n{'='*70}\nML VALIDATION SUMMARY: {n}/{len(res)} passed\n{'='*70}")
    return res

# ==========================================================================
# validate_all() -- run this ONCE after editing anything above.
# Deliberately NOT executed at import: notebooks stay fast to open and cannot
# be killed by a heavy validation running behind your back.
# ==========================================================================
def validate_all(verbose=True):
    results = {}
    def check(name, fn):
        try:
            fn(); results[name] = "PASS"
            if verbose: ok(f"validation {name}: PASS")
        except Exception as e:
            results[name] = f"FAIL: {e}"
            fail(f"validation {name}: {e}")

    def _mk(seed=11, n_per=40):
        rng = np.random.default_rng(seed); times = list(range(2018, 2027))
        coh = {}; uid = 0
        for g in [2021, 2023, np.inf]:
            for _ in range(n_per): coh[uid] = g; uid += 1
        ufe = {u: rng.normal(0, 2) for u in coh}; tfe = {t: rng.normal(0, 1) for t in times}
        eff = lambda g, t: 0.0 if g == np.inf else (0.6*(t-g+1) if g == 2021 else 1.8)
        rows, taus = [], []
        for u, g in coh.items():
            for t in times:
                dd = 1.0 if (g != np.inf and t >= g) else 0.0
                e = eff(g, t) if dd else 0.0
                if dd: taus.append(e)
                rows.append({"unit": u, "time": t, "y": ufe[u]+tfe[t]+e+rng.normal(0,0.3),
                             "d": dd, "cohort": g})
        return pd.DataFrame(rows), float(np.mean(taus))

    def v_stacked():
        df, true = _mk()
        naive, _ = estimate_twfe_did(df, "y", "d", "unit", "time", "unit")
        res, _ = stacked_did(df, "y", "unit", "time", "cohort")
        assert abs(res["ATT_stacked"]-true) < abs(naive-true)
    def v_etwfe():
        df, true = _mk()
        naive, _ = estimate_twfe_did(df, "y", "d", "unit", "time", "unit")
        res, _ = etwfe(df, "y", "unit", "time", "cohort")
        assert abs(res["ATT_etwfe"]-true) < abs(naive-true)
    def v_entropy():
        rng = np.random.default_rng(77); Xc = rng.normal(0, 1, (400, 2))
        w, ach = entropy_balance(Xc, np.array([0.8, 0.5]))
        assert np.max(np.abs(ach - np.array([0.8, 0.5]))) < 1e-5 and w.min() >= 0
    def v_honest():
        _, strong = honest_did_relative_magnitudes({-3:0.01,-2:-0.02,0:1.0},
                                                    {-3:0.05,-2:0.05,0:0.10}, [-3,-2], 0)
        _, weak = honest_did_relative_magnitudes({-3:0.30,-2:-0.35,0:0.40},
                                                  {-3:0.10,-2:0.10,0:0.15}, [-3,-2], 0)
        assert strong > 5*max(weak, 0.01) and weak < 0.6
    def v_quantile():
        rng = np.random.default_rng(5); base = rng.normal(10, 2, 4000)
        y00 = base; y01 = base+1.0+rng.normal(0,.2,4000); y10 = rng.normal(10,2,4000)
        y11 = y10+1.0+np.where(y10 < np.quantile(y10,.5), 3.0, 0.5)+rng.normal(0,.2,4000)
        q = quantile_did(y00, y01, y10, y11)
        assert q.iloc[0]["QTE"] > q.iloc[-1]["QTE"] + 1.0
    def _factor_data():
        rng = np.random.default_rng(5); N, T, r = 60, 12, 2
        lam = rng.normal(0,1,(N,r)); F = rng.normal(0,1,(r,T))
        D = np.zeros((N,T)); D[:30,6:] = 1.0
        return 2.0*D + lam@F + rng.normal(0,0.3,(N,T)), D, 2.0
    def v_ife():
        Y, D, true = _factor_data(); assert abs(interactive_fe(Y, D, r=2)-true) < 0.3
    def v_matcomp():
        Y, D, true = _factor_data(); assert abs(matrix_completion_did(Y, D)-true) < 0.6
    def v_gsc():
        Y, D, true = _factor_data(); assert abs(generalized_synthetic_control(Y, D, r=2)-true) < 0.6
    def v_mlcate():
        rng = np.random.default_rng(5); rows = []
        for u in range(400):
            x = rng.uniform(0,1); tr = 1 if u < 200 else 0; fe = rng.normal(0,1)
            te_true = 1.0 if x < 0.5 else 4.0
            for t in [0,1]:
                rows.append({"unit":u,"time":t,"x":x,"d":tr*t,
                             "y":fe+te_true*tr*t+rng.normal(0,0.3)})
        te, _ = ml_cate(pd.DataFrame(rows), "y", "d", ["x"], "unit", "time")
        assert te[te.x >= 0.5].cate.mean() > te[te.x < 0.5].cate.mean() + 1.0

    for n, f in [("stacked_did", v_stacked), ("etwfe", v_etwfe),
                 ("entropy_balance", v_entropy), ("honest_did", v_honest),
                 ("quantile_did", v_quantile), ("interactive_fe", v_ife),
                 ("matrix_completion", v_matcomp), ("generalized_synth_control", v_gsc),
                 ("ml_cate", v_mlcate)]:
        check(n, f)
    n_pass = sum(1 for v in results.values() if v == "PASS")
    print(f"\n{'='*70}\nVALIDATION SUMMARY: {n_pass}/{len(results)} passed\n{'='*70}")
    return results
