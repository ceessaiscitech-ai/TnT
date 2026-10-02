"""
validate_model_parity.py -- v20.58: EVERY model gives the same kind of answer in R and in Python, on the same exports (your rule: the R
pipeline structured exactly as the Python one).

The layout of validate_location_poison.py (your Koranahalli exports: named files + repeating tiles, pixels outside every polygon, a
neighbour's core, a flipping ring, a shifted grid, a fund workbook with a Rabi 2024 start; CONTROL_ZONES 1-3, PRE_YEARS 4, seasonal rows)
is written once. The Python P00 + every model notebook run on it; the R preparation (lib/reward_prep.R) + every R model run on a copy of
the SAME files. Per model the two headline rows are compared:
    the kind (effect / test / statistic / diagnostic) must be the same,
    IDENTICAL   |difference| <= 1e-6 x max(1, |estimate|)            (the same estimator on the same rows)
    CLOSE       |difference| <= max(0.25 x the larger SE, 1e-4)        (the same estimand, different implementations / seeds)
    CLOSE-ML    M39-M44 only: |difference| <= max(2 x the larger SE, 1e-4) -- the same estimand through DIFFERENT machine-learning
                implementations (grf / DoubleML-mlr3-ranger in R, econml / scikit-learn in Python): their forests and cross-fitting
                folds are not the same random objects, so the nuisance noise differs; both are held to the known answer separately
                (validate_known_answers.py, run_all_tests.R)
    DIFFERENT   anything else -- read the detail: a different estimand under one model name is a bug
The SEs are compared too (se_verdict): SAME (<= 1e-6 relative), CLOSE (<= 5 %), DIFFERS (read the detail -- two SE conventions for one
headline), and a missing SE on one side only.

    python validate_model_parity.py                       (all models; ~20-40 min)
    python validate_model_parity.py --from <poison run>/clean     (reuse the Python run of validate_location_poison.py)
    python validate_model_parity.py M13 M15               (a subset)
    python validate_model_parity.py --engine              (Python's OWN implementations: no pre-built package, no R route -- each
                                                            model's engine against R; without it a Python model whose verified primary
                                                            is an R route is R through the bridge on Python's data)
"""
import os as _os0, sys as _sys0
if not _os0.path.isdir(_os0.path.join(_os0.path.dirname(_os0.path.dirname(_os0.path.dirname(_os0.path.abspath(__file__)))), "R", "lib")):
    print("[INFO]    this validator compares R with Python; the R track is kept outside this module (R_separate_track/) -- nothing to compare here"); _sys0.exit(0)
import os, sys, json, glob, shutil, subprocess, tempfile
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
import validate_location_poison as VLP

RLIB = os.path.join(os.path.dirname(os.path.dirname(HERE)), "R", "lib")
R_SETTINGS = ('DESIGN_MODE <- "recommended"; TREATMENT_TIMING <- "fund"; CONTROL_RINGS <- 1:3; PRE_YEARS <- 4; POST_YEARS <- NA; '
              'SEASONS <- "seasonal"; OVERLAP_ROWS <- "drop"; FRAGMENT_RULE <- "drop"; POOLED_FE <- "site_period"; SUB_WATERSHEDS <- "data"; '
              'COVARIATES <- c("Rain", "Tmax", "Tmean", "Tmin"); UNIT_FE <- "pixel_season"')
R_SCRIPT = r'''
suppressPackageStartupMessages(library(data.table))
a <- commandArgs(trailingOnly = TRUE); ROOT_ <- a[1]; SITES_ <- a[2]; FUND_ <- a[3]; RHOME_ <- a[4]; OUT_ <- a[5]; MODELS_ <- if (nzchar(a[6])) strsplit(a[6], ",")[[1]] else character(0)
Sys.setenv(REWARD_R_ROOT = ROOT_, REWARD_SITES_CSV = SITES_, REWARD_FUND_PATH = FUND_, REWARD_TEST_RUN = "1")
R_HOME_DIR <- RHOME_
for (f in c("reward_paths.R", "reward_design.R", "reward_prep.R", "reward_models_core.R")) source(file.path(R_HOME_DIR, "lib", f))
run_prep(); invisible(prepare_design())
@@SETTINGS@@
d <- model_design(verbose = TRUE, force = TRUE)
ms <- if (length(MODELS_)) MODELS_ else names(MODEL_FUN)
for (m in ms) try(run_model_R(m, "NDVI", d))
fs <- list.files(RESULTS_DIR, pattern = "^M[0-9]{2}_NDVI(_DATA_GAP)?\\.csv$", recursive = TRUE, full.names = TRUE)
res <- rbindlist(lapply(fs, function(f) { x <- fread(f); x[, file := basename(f)]; x[, model := sub("_.*", "", basename(f))] }), fill = TRUE)
fwrite(res, OUT_); cat("@@R_DONE@@\n")
'''

def _rhome(base):
    """A throw-away R home: the bundle's R/lib, the shapefile and sites registry of this engine (the same files R ships)."""
    rh = os.path.join(base, "R_home"); os.makedirs(os.path.join(rh, "data", "ground"), exist_ok=True)
    shutil.copytree(RLIB, os.path.join(rh, "lib"), dirs_exist_ok=True)
    shutil.copytree(os.path.join(HERE, "data", "sites"), os.path.join(rh, "data", "sites"), dirs_exist_ok=True)
    return rh

def run_r(py_root, base, models, fund):
    """R on a COPY of the exports the Python run used (its panel is written next to the exports, as Python's)."""
    import _common as C
    rs = C.find_rscript()
    if not rs: raise RuntimeError("R not found (set R_SCRIPT in _common / P00_Settings) -- the parity check needs R")
    rroot = os.path.join(base, "R_run")
    shutil.rmtree(rroot, ignore_errors=True); os.makedirs(rroot)
    for sub in os.listdir(py_root):
        p = os.path.join(py_root, sub)
        if os.path.isdir(p) and sub not in ("output", _out_sub()): shutil.copytree(p, os.path.join(rroot, sub), copy_function=shutil.copy2)   # mtimes kept
    rh = _rhome(base); out = os.path.join(base, "R_headlines.csv"); sc = os.path.join(base, "parity_run.R")
    open(sc, "w", encoding="utf-8").write(R_SCRIPT.replace("@@SETTINGS@@", R_SETTINGS))
    r = subprocess.run([rs, sc, rroot, os.path.join(rh, "data", "sites", "sites.csv"), fund, rh, out, ",".join(models or [])],
                       capture_output=True, text=True, timeout=6 * 3600)
    open(os.path.join(base, "R_run.log"), "w", encoding="utf-8").write(r.stdout + r.stderr)
    if "@@R_DONE@@" not in r.stdout: raise RuntimeError(f"the R run did not finish -- {(r.stdout + r.stderr)[-1500:]}")
    return pd.read_csv(out)

def py_headlines(results):
    rows = []
    for f in sorted(glob.glob(os.path.join(results, "M*", "*", "HEADLINE_NDVI.csv"))):
        t = pd.read_csv(f)
        if len(t): rows.append({**t.iloc[0].to_dict(), "model": os.path.basename(os.path.dirname(os.path.dirname(f)))})
    for f in sorted(glob.glob(os.path.join(results, "M*", "*", "*_DATA_GAP*.csv"))):
        m = os.path.basename(os.path.dirname(os.path.dirname(f)))
        if not any(r["model"] == m for r in rows): rows.append({"model": m, "kind": "data gap"})
    return pd.DataFrame(rows)

ML_MODELS = {"M39", "M40", "M41", "M42", "M43", "M44"}   # machine learning (forests, learners, BART)

def _se_verdict(ps, rs_):
    if not np.isfinite(ps) and not np.isfinite(rs_): return "both none"
    if np.isfinite(ps) != np.isfinite(rs_): return "Python only" if np.isfinite(ps) else "R only"
    r_ = abs(ps - rs_) / max(abs(ps), abs(rs_), 1e-300)
    return "SAME" if r_ <= 1e-6 else ("CLOSE" if r_ <= 0.05 else "DIFFERS")

def compare(py, rr):
    fnum = lambda v: float(v) if v is not None and str(v) not in ("", "nan", "None") and np.isfinite(float(v)) else np.nan
    out = []
    for m in sorted(set(py.get("model", pd.Series(dtype=str))) | set(rr.get("model", pd.Series(dtype=str)))):
        p = py[py.model == m]; r = rr[(rr.model == m) & ~rr.file.astype(str).str.contains("DATA_GAP")]
        rg = rr[(rr.model == m) & rr.file.astype(str).str.contains("DATA_GAP")]
        pk = str(p["kind"].iloc[0]) if len(p) and "kind" in p else "absent"; rk = str(r["kind"].iloc[0]) if len(r) else ("data gap" if len(rg) else "absent")
        pe = fnum(p["estimate"].iloc[0]) if len(p) and "estimate" in p else np.nan; re_ = fnum(r["estimate"].iloc[0]) if len(r) else np.nan
        ps = fnum(p["se"].iloc[0]) if len(p) and "se" in p else np.nan; rs_ = fnum(r["se"].iloc[0]) if len(r) and "se" in r else np.nan
        if pk == "data gap" and rk == "data gap": v, det = "BOTH DATA GAP", str(rg["reason"].iloc[0])[:120] if len(rg) and "reason" in rg else ""
        elif pk != rk: v, det = "KIND DIFFERS", f"Python {pk} / R {rk}"
        elif not (np.isfinite(pe) and np.isfinite(re_)): v, det = "NO NUMBER", f"Python {pe} / R {re_}"
        else:
            d = abs(pe - re_); tol_c = max(0.25 * np.nanmax([ps, rs_, 0.0]), 1e-4)
            v = "IDENTICAL" if d <= 1e-6 * max(1.0, abs(pe)) else ("CLOSE" if d <= tol_c else
                 ("CLOSE-ML" if m in ML_MODELS and d <= max(2.0 * np.nanmax([ps, rs_, 0.0]), 1e-4) else "DIFFERENT"))
            det = f"Python {pe:.6g} (SE {ps:.3g}) | R {re_:.6g} (SE {rs_:.3g}) | difference {pe - re_:+.3g}"
        out.append({"model": m, "verdict": v, "se_verdict": _se_verdict(ps, rs_) if v not in ("BOTH DATA GAP", "KIND DIFFERS") else "",
                    "python_kind": pk, "r_kind": rk, "python_estimate": pe, "r_estimate": re_, "python_se": ps, "r_se": rs_,
                    "python_engine": str(p["engine"].iloc[0])[:80] if len(p) and "engine" in p else "", "r_engine": str(r["engine"].iloc[0])[:80] if len(r) and "engine" in r else "",
                    "detail": det})
    return pd.DataFrame(out)

def main(argv):
    models = [a for a in argv if a.startswith("M")]; frm = None
    if "--from" in argv: frm = argv[argv.index("--from") + 1]
    if "--engine" in argv:                                   # every Python model by its own implementation (PREBUILT_MODE "off")
        if frm: raise SystemExit("--engine runs the Python models itself: leave out --from")
        os.environ["REWARD_PREBUILT_MODE"] = "off"
    base = tempfile.mkdtemp(prefix="reward_parity_"); print(f"[INFO]    working in {base}")
    if frm:
        py_root = os.path.abspath(frm); results = os.path.join(py_root, _out_sub(), "results")
        fund = os.path.join(os.path.dirname(py_root), os.path.basename(py_root) + "_fund.xlsx")
    else:
        results, _ = VLP.run_variant("clean", False, models, base); py_root = os.path.join(base, "clean")
        fund = os.path.join(base, "clean_fund.xlsx")
    rr = run_r(py_root, base, models, fund)
    t = compare(py_headlines(results), rr)
    if models: t = t[t.model.isin(models)]
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 120)
    print(t[["model", "verdict", "se_verdict", "python_kind", "r_kind", "detail"]].to_string(index=False))
    t["python_side"] = "engine (PREBUILT_MODE off)" if os.environ.get("REWARD_PREBUILT_MODE") == "off" else "primary (verified packages / R routes first)"
    out_csv = os.path.join(HERE, "VALIDATION_MODEL_PARITY" + ("_ENGINE" if os.environ.get("REWARD_PREBUILT_MODE") == "off" else "") + ".csv")
    t.to_csv(out_csv, index=False)
    bad = t[t.verdict.isin(["DIFFERENT", "KIND DIFFERS", "NO NUMBER"])]
    sed = t[t.se_verdict == "DIFFERS"]
    print(f"\n{(t.verdict == 'IDENTICAL').sum()} IDENTICAL | {(t.verdict == 'CLOSE').sum()} CLOSE | {(t.verdict == 'CLOSE-ML').sum()} CLOSE-ML | "
          f"{(t.verdict == 'BOTH DATA GAP').sum()} both a data gap | {len(bad)} to read: {bad.model.tolist()} | SE conventions differ: {sed.model.tolist()}")
    print(f"report -> {out_csv}")
    return 0 if not len(bad) else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
