"""
pf_pipeline.py -- the PRE-BUILT-MODEL pipeline in Python (pyfixest + wildboottest), v20.22.

Reads the tidy tables written by  C.export_for_packages(outcome)  (estimator_files/package_input/) and runs the
same headline models as the custom engine with peer-reviewed implementations:

    twfe_2x2          feols(y ~ did [+ covariates] | unit + period, cluster = cluster_id)        <-> M01
    event_study       feols(y ~ i(event_time, treat, ref=-1) [+ covariates] | unit + period)     <-> M02
    pretrends_wald    joint Wald test of the leads (event_time < -1) on the event-study fit           <-> M16
    wild_bootstrap    wildboottest on `did` (Webb weights for < 12 clusters, Rademacher otherwise)    <-> M23
    pooled_multisite  the 2x2 on every site with site x period FE and site clusters                  <-> pooled run

Results go to <RESULTS_ROOT>/prebuilt_pyfixest/<model>/<scenario>/<file>_<outcome>.csv, the same layout as the
custom engine, and `compare(outcome)` prints both side by side with the difference.

    pip install pyfixest wildboottest pyarrow          (pyfixest >= 0.25 recommended)
    python pf_pipeline.py NDVI                        # everything for one outcome
    python pf_pipeline.py NDVI --smoke                # the smoke test: pyfixest vs the custom engine on a subsample

Written against pyfixest's public API (feols, i(), vcov={"CRV1": ...}, .coef()/.se()/.pvalue(), .wald_test(),
.wildboottest()). It has NOT been executed in the environment that produced this bundle (no network there):
run --smoke first; it stops at the first disagreement it finds.
"""
import os, sys, json, glob, re
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, ENGINE_DIR)


def _engine():
    import _common as C
    return C


_FRAME_OVERRIDE = {}      # v20.42: verification hands a known-answer panel in here (never used in a normal run)

def package_input(outcome, C=None):
    """The package-input table for the scenario in force (written by C.export_for_packages if missing)."""
    if outcome in _FRAME_OVERRIDE:
        return _FRAME_OVERRIDE[outcome].copy()
    C = C or _engine()
    if hasattr(C, "package_input_ready"):                 # v20.54: rebuilt when cut from an older panel or other sites
        stem = C.package_input_ready(outcome)
    else:
        stem = C.package_input_stem(outcome)              # v20.46: carries the data-rules version
        if not os.path.exists(stem + ".parquet") and not os.path.exists(stem + ".csv"):
            C.export_for_packages(outcome)
    if os.path.exists(stem + ".parquet"):
        try:
            return pd.read_parquet(stem + ".parquet")
        except Exception:
            pass
    return pd.read_csv(stem + ".csv")


def out_dir(model, C=None):
    C = C or _engine()
    d = os.path.join(C.RESULTS_ROOT, "prebuilt_pyfixest", model, C.scenario_tag()); os.makedirs(d, exist_ok=True)
    return d


def _pf():
    try:
        import pyfixest as pf
    except ImportError as e:
        raise SystemExit("pyfixest is not installed: pip install pyfixest wildboottest") from e
    return pf


def _feols(C, pf, *a, **kw):
    """v20.54: every pyfixest fit here goes through the engine's handler, so the "N singleton fixed effect(s) dropped"
    warning becomes the same one explained line (and recorded count) as in the model notebooks -- this script printed
    pyfixest's raw UserWarning (your run, 2,031,153 singletons)."""
    q = getattr(C, "_pf_quiet", None)
    return q(pf.feols, *a, **kw) if q is not None else pf.feols(*a, **kw)


# v20.54: the defaults below are YOUR four weather covariates -- LandUse had stayed in them from before v20.45 (it is a class,
# never a covariate; the package inputs never carried it, so no result changed)
def twfe_2x2(outcome, covariates=("Rain", "Tmax", "Tmean", "Tmin"), df=None, C=None, write=True):
    C = C or _engine(); pf = _pf()
    df = package_input(outcome, C) if df is None else df
    covs = [c for c in covariates if c in df.columns]
    f0 = _feols(C, pf, f"{outcome} ~ did | unit + period", data=df, vcov={"CRV1": "cluster_id"})
    f1 = _feols(C, pf, f"{outcome} ~ did + {' + '.join(covs)} | unit + period", data=df, vcov={"CRV1": "cluster_id"}) if covs else f0
    row = {"outcome": outcome, "beta": float(f1.coef()["did"]), "se": float(f1.se()["did"]), "p_value": float(f1.pvalue()["did"]),
           "beta_no_covariates": float(f0.coef()["did"]), "se_no_covariates": float(f0.se()["did"]),
           "covariates": covs, "n_obs": int(f1._N), "n_clusters": int(df.cluster_id.nunique()), "engine": "pyfixest", "status": "ok"}
    if write:
        pd.DataFrame([row]).to_csv(os.path.join(out_dir("twfe_2x2", C), f"canonical_twfe_{outcome}.csv"), index=False)
    return row, f1


def event_study(outcome, covariates=("Rain", "Tmax", "Tmean", "Tmin"), df=None, C=None, write=True):
    C = C or _engine(); pf = _pf()
    df = package_input(outcome, C) if df is None else df
    covs = [c for c in covariates if c in df.columns]
    rhs = "i(event_time, treat, ref=-1)" + (" + " + " + ".join(covs) if covs else "")
    df = df.copy(); df["event_time"] = pd.to_numeric(df["event_time"], errors="coerce").fillna(-1)   # v20.58: never-treated rows carry no event
    fit = _feols(C, pf, f"{outcome} ~ {rhs} | unit + period", data=df, vcov={"CRV1": "cluster_id"})   #   time (as R): the reference level (treat = 0 there)
    tidy = fit.tidy().reset_index()
    tidy = tidy[tidy["Coefficient"].str.contains("event_time")].copy()
    tidy["event_time"] = tidy["Coefficient"].str.extract(r"\[T\.(-?\d+)\]").astype(float).fillna(
        tidy["Coefficient"].str.extract(r"::(-?\d+)")[0].astype(float))
    out = pd.DataFrame({"event_time": tidy["event_time"].astype(int), "beta": tidy["Estimate"].values, "se": tidy["Std. Error"].values,
                        "p_value": tidy["Pr(>|t|)"].values, "engine": "pyfixest"})
    out = pd.concat([out, pd.DataFrame([{"event_time": -1, "beta": 0.0, "se": 0.0, "p_value": np.nan, "engine": "pyfixest (reference)"}])]).sort_values("event_time")
    if write:
        out.to_csv(os.path.join(out_dir("event_study", C), f"event_study_{outcome}.csv"), index=False)
    return out, fit


def pretrends_wald(outcome, fit=None, df=None, C=None, write=True):
    """Joint test that all leads (event_time < -1) are zero, on the event-study fit's cluster-robust covariance."""
    C = C or _engine()
    if fit is None: _, fit = event_study(outcome, df=df, C=C, write=False)
    names = list(fit.coef().index)
    leads = [n for n in names if re.search(r"event_time.*(\[T\.|::)-(\d+)", n) and int(re.search(r"-(\d+)", n).group(1)) >= 2]
    if not leads: raise RuntimeError("no lead coefficients in the event-study fit")
    R = np.zeros((len(leads), len(names)))
    for i, n in enumerate(leads): R[i, names.index(n)] = 1.0
    b = fit.coef().values; V = fit._vcov
    Rb = R @ b; RVR = R @ V @ R.T
    wald = float(Rb @ np.linalg.pinv(RVR) @ Rb)
    q = int(np.linalg.matrix_rank(RVR)); G = int(fit._G if hasattr(fit, "_G") else np.nan)
    from scipy import stats as sstats
    f_stat = wald / max(q, 1); p = float(1 - sstats.f.cdf(f_stat, max(q, 1), max(G - 1, 1))) if G == G else float(1 - sstats.chi2.cdf(wald, max(q, 1)))
    row = {"outcome": outcome, "leads": ";".join(leads), "q": q, "f_stat": f_stat, "p_value": p, "n_clusters": G, "engine": "pyfixest"}
    if write:
        pd.DataFrame([row]).to_csv(os.path.join(out_dir("pretrends_wald", C), f"pretrends_ftest_{outcome}.csv"), index=False)
    return row


def wild_bootstrap(outcome, fit=None, df=None, reps=999, C=None, write=True):
    """Wild-cluster bootstrap p-value for `did`. Webb weights when the number of clusters is small (< 12): with 6-7
    clusters Rademacher weights give only 2^G distinct draws."""
    C = C or _engine()
    if fit is None: _, fit = twfe_2x2(outcome, df=df, C=C, write=False)
    G = int(fit._G) if hasattr(fit, "_G") else None
    weights = "webb" if (G is not None and G < 12) else "rademacher"
    try:
        res = fit.wildboottest(param="did", reps=reps, weights_type=weights, seed=12345)
        p = float(res["Pr(>|t|)"].iloc[0]) if hasattr(res, "iloc") else float(res)
    except Exception as e:
        raise SystemExit(f"wildboottest failed ({e}); pip install wildboottest") from e
    row = {"outcome": outcome, "beta": float(fit.coef()["did"]), "p_wild": p, "reps": reps, "weights": weights, "n_clusters": G, "engine": "pyfixest+wildboottest"}
    if write:
        pd.DataFrame([row]).to_csv(os.path.join(out_dir("wild_bootstrap", C), f"wild_bootstrap_{outcome}.csv"), index=False)
    return row


def pooled_multisite(outcome, covariates=("Rain", "Tmax", "Tmean", "Tmin"), df=None, C=None, write=True):
    """All sites at once: site x period fixed effects and clusters by site (the scenario cluster='site',
    pooled_fe='site_period' produces exactly these columns in the package input)."""
    C = C or _engine(); pf = _pf()
    df = package_input(outcome, C) if df is None else df
    if df.site_id.nunique() < 2: raise RuntimeError("pooled model needs >= 2 sites in the package input")
    df = df.copy(); df["site_period"] = df.site_id.astype(str) + "|" + df.period.astype(str)
    covs = [c for c in covariates if c in df.columns]
    fit = _feols(C, pf, f"{outcome} ~ did{' + ' + ' + '.join(covs) if covs else ''} | unit + site_period", data=df, vcov={"CRV1": "site_id"})
    row = {"outcome": outcome, "beta": float(fit.coef()["did"]), "se": float(fit.se()["did"]), "p_value": float(fit.pvalue()["did"]),
           "n_sites": int(df.site_id.nunique()), "n_obs": int(fit._N), "fe": "pixel + site x period", "cluster": "site", "engine": "pyfixest"}
    if write:
        pd.DataFrame([row]).to_csv(os.path.join(out_dir("pooled_multisite", C), f"pooled_twfe_{outcome}.csv"), index=False)
    return row, fit


def compare(outcome, C=None, tol=1e-6):
    """Custom engine vs pyfixest on the same package input. Point estimates must agree to `tol`; SEs to a few
    percent (the small-sample corrections differ slightly: fixest counts fixed-effect parameters in K)."""
    C = C or _engine()
    df = package_input(outcome, C)
    row, _ = twfe_2x2(outcome, df=df, C=C, write=False)
    # the custom engine on the very same rows
    d = df.rename(columns={"period": "time_fe_yearseason", "did": "did_term", "cluster_id": "subwshed_id"})
    # the SAME unit fixed effect as pyfixest (the exported `unit`), so the comparison is like for like
    b, se = C.estimate_twfe_did(d, outcome, "did_term", "unit" if "unit" in d.columns else "pixel_id", "time_fe_yearseason", "subwshed_id", covariates=row["covariates"])
    print(f"{outcome}: beta engine {b:+.8f} vs pyfixest {row['beta']:+.8f} (diff {abs(b-row['beta']):.1e}) | "
          f"se engine {se:.6f} vs pyfixest {row['se']:.6f} (ratio {row['se']/se if se else float('nan'):.4f})")
    if abs(b - row["beta"]) > tol * max(1.0, abs(b)):
        raise SystemExit("POINT ESTIMATES DISAGREE -- stop and investigate before using either number")
    return b, row


def run_all(outcome, smoke=False, C=None):
    C = C or _engine()
    if smoke:
        compare(outcome, C); print("[OK] smoke test passed: pyfixest and the custom engine agree on the point estimate"); return
    df = package_input(outcome, C)
    r1, f1 = twfe_2x2(outcome, df=df, C=C); print("2x2:", {k: r1[k] for k in ("beta", "se", "p_value", "n_clusters")})
    es, fes = event_study(outcome, df=df, C=C); print("event study:", es[["event_time", "beta", "se"]].round(5).to_dict("records"))
    print("pre-trends:", pretrends_wald(outcome, fit=fes, C=C))
    print("wild bootstrap:", wild_bootstrap(outcome, fit=f1, C=C))
    if df.site_id.nunique() > 1: print("pooled:", pooled_multisite(outcome, df=df, C=C)[0])


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run_all(args[0] if args else "NDVI", smoke="--smoke" in sys.argv)
