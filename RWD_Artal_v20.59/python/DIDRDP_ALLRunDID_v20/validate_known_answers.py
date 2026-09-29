"""
validate_known_answers.py -- v20.57: every Python model against a KNOWN ANSWER (the R test has done this since v20.49;
the Python gate validate_all_models.py only checks that a model honours the scenario, not that its number is right).

Two synthetic panels with the structure of your exports -- a core (buff_km 0) and rings 1-5, the annual composite AND
Kharif / Rabi / Zaid rows, pixel levels that differ by season, core-vs-ring LEVEL differences, year x season shocks common to
all, weather covariates unrelated to the treatment, a few missing cells -- and a true effect of +0.05 NDVI on the core:
    single   ONE sub-watershed (as RWD_Artal), implementation 2022
    staggered EIGHT sub-watersheds pooled, implementation 2020 (four) and 2022 (four) -- each its own cohort
Every model notebook runs on each (as validate_all_models.py runs them: CELL 1 onwards, the engine injected), its headline
estimate is read from the results it wrote, and judged:
    ATT models              |estimate - 0.05| <= 0.01            (their target is the effect)
    ML / distributional     |estimate - 0.05| <= 0.02
    placebo (M15)           |estimate| <= 0.01                    (no effect before the start)
    pre-trend test (M16)    p > 0.001                             (no pre-trend was simulated)
    Moran / ICC / Q         inside their range
A model with no known answer on these data (M07 needs ground data, M08 an instrument ...) must say why; M19 / M20
need >= 2 sub-watersheds -- on the single panel their DATA GAP is the right answer, accepted only with exactly that reason.

    python validate_known_answers.py            (both panels, every model)
    python validate_known_answers.py M01 M05    (a subset)
"""
import os, sys, json, glob, time, tempfile, re
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _common as C
import validate_all_models as VM

TRUE = 0.05
ATT = {"M01", "M02", "M03", "M05", "M06", "M09", "M10", "M11", "M12", "M14", "M21", "M22", "M23", "M24", "M26", "M27", "M28", "M29",
       "M30", "M31", "M32", "M33", "M34"}
ATT_LOOSE = {"M04", "M13", "M35", "M36", "M37", "M38", "M39", "M40", "M41", "M42", "M43", "M44", "M45"}   # v20.58: M13 computed (D switches on)
NO_ANSWER = {"M07": "needs the BM ground-truth file", "M08": "needs an instrument"}
# a DATA GAP that is the right answer on ONE sub-watershed -- accepted only with exactly this reason in the model's log
EXPECTED_GAP = {("single", "M19"): "Need at least 2 sub-watersheds", ("single", "M20"): "needs >= 2 sub-watersheds"}   # v20.58: M20's reason as R's
_UNUSED = {
             "M17": "Moran's I: a range check", "M18": "LISA: a range check", "M19": "ICC: a range check", "M20": "Cochran Q: a range check",
             "M25": "randomisation p-value", "M15": "placebo: truth 0", "M16": "pre-trend test"}


def make_panel(kind="single", seed=3, n_ring=36, years=range(2016, 2026)):
    rng = np.random.default_rng(seed)
    sites = [1] if kind == "single" else [1, 2, 3, 4, 5, 6, 7, 8]
    cohort = {s: (2022 if kind == "single" or s > 4 else 2020) for s in sites}
    rows = []
    shock = {(y, s): rng.normal(0, 0.02) for y in years for s in (1, 2, 3)}
    site_shock = {(k, y, s): rng.normal(0, 0.005) for k in sites for y in years for s in (1, 2, 3)}
    pid = 0
    for k in sites:
        for b in range(6):
            for i in range(n_ring):
                pid += 1
                lvl = 0.35 + (0.06 if b == 0 else 0.0) - 0.004 * b + rng.normal(0, 0.04)     # the core is GREENER to begin with
                sea = {1: 0.08 + rng.normal(0, 0.01), 2: 0.02 + rng.normal(0, 0.01), 3: -0.05 + rng.normal(0, 0.01)}
                lat = 15.0 + k * 0.5 + b * 0.01 + i * 1e-4; lon = 75.0 + k * 0.5 + i * 1e-4
                for y in years:
                    for s in (1, 2, 3):
                        eff = TRUE if (b == 0 and y >= cohort[k]) else 0.0
                        v = lvl + sea[s] + 0.004 * (y - 2016) + shock[(y, s)] + site_shock[(k, y, s)] + eff + rng.normal(0, 0.01)
                        rows.append((pid * 7919, k, b, y, s, v, 600 + rng.normal(0, 40), 33 + rng.normal(0, 1), 26 + rng.normal(0, 1),
                                     19 + rng.normal(0, 1), cohort[k], lat, lon, 1 + (i % 3)))
    df = pd.DataFrame(rows, columns=["pixel_id", "site_id", "buff_km", "Year", "Season", "NDVI", "Rain", "Tmax", "Tmean", "Tmin",
                                     "first_treat_agri_year", "latitude", "longitude", "LandUse"])
    for c, f in (("EVI", 0.8), ("SAVI", 0.9), ("LAI", 3.0)):
        df[c] = df["NDVI"] * f + rng.normal(0, 0.005, len(df))
    ann = df.groupby(["pixel_id", "Year"], as_index=False).agg({**{c: "mean" for c in ("NDVI", "EVI", "SAVI", "LAI")},
                                                                  **{c: "first" for c in ("site_id", "buff_km", "first_treat_agri_year", "latitude", "longitude", "LandUse")}})
    ann["Season"] = 0
    for c in ("Rain", "Tmax", "Tmean", "Tmin"): ann[c] = np.nan                  # as your annual composite: no weather (filled from the seasons)
    df = pd.concat([df, ann[df.columns]], ignore_index=True)
    lab = {0: "Yearly", 1: "Kharif", 2: "Rabi", 3: "Zaid"}
    df["time_fe_yearseason"] = df.Year.astype(str) + "_" + df.Season.map(lab); df["time_fe_year"] = df.Year.astype(str)
    df["time_fe_season"] = df.Season.map(lab); df["season_sort_rank"] = df.Season
    df["first_treat_agri_year"] = np.where(df.buff_km == 0, df.first_treat_agri_year, np.inf)   # never treated: the rings
    df["subwshed_id"] = "S" + df.site_id.astype(str); df["Coverage"] = 1.0; df["sws_name"] = df.site_id.map(lambda s: f"SWS{s}")
    df["dose_intensity_per_ha"] = np.where((df.buff_km == 0) & (df.Year >= df.first_treat_agri_year), 1.0, 0.0)   # the effect per unit of dose = 0.05
    df["dose_amount_sws"] = df["dose_intensity_per_ha"] * 1000.0; df["dose_per_subwshed"] = df["dose_intensity_per_ha"] * 100.0
    df["dose_share_of_target"] = df["dose_intensity_per_ha"]; df["dose_estimated"] = 0
    r2 = np.random.default_rng(seed + 100)
    df.loc[r2.random(len(df)) < 0.02, "NDVI"] = np.nan                       # an unbalanced panel
    return df, cohort


# the headline of each model: (file stem, how to read it). "col" = the 1-row column; "post_mean" = the mean of the rows with
# event time >= 0; "rows" = every row of that column must meet the rule; "dose" = the dose-response slope x the dose on the
# treated post rows (1.0 here; the v20.56 M06 used the completion percent: 100)
HEADLINE = {
    "M01": ("canonical_twfe", "col", "beta"), "M02": ("event_study_headline", "col", "estimate"), "M03": ("doubly_robust", "col", "ATT"),
    "M04": ("changes_in_changes", "col", "ATT_CiC"), "M05": ("cs_overall", "col", "ATT_simple"), "M06": ("dose_response", "dose", None),
    "M09": ("sun_abraham_headline", "col", "estimate"), "M10": ("ddd", "zero", "DDD"), "M11": ("synthetic_did", "col", "ATT"),
    "M12": ("chained_did", "col", "beta"), "M14": ("psm_did", "col", "PSM_DID"), "M15": ("placebo_timing", "rows_zero", "placebo_beta"),
    "M16": ("pretrends_ftest", "p", "p_value"), "M17": ("morans_i", "range_pm1", "morans_I"), "M19": ("variance_decomposition", "range_01", "ICC"),
    "M20": ("treatment_heterogeneity", "range_pos", "Q"), "M21": ("aggregation_bias", "col", "naive_annual"), "M22": ("goodman_bacon_summary", "col", "estimate"),
    "M23": ("wild_bootstrap", "col", "beta"), "M24": ("spillover_gradient", "rows_zero", "gradient_effect"), "M25": ("permutation", "col", "beta_actual"),
    "M26": ("treatment_x_Rain", "col", "beta_at_mean"), "M27": ("bjs", "col", "ATT_bjs"), "M28": ("gardner", "col", "ATT_gardner"),
    "M29": ("exposure_headline", "col", "estimate"), "M30": ("cohort_group_att", "col", "estimate"), "M31": ("stacked_did", "col", "ATT_stacked"),
    "M32": ("etwfe", "col", "ATT_etwfe"), "M33": ("entropy_balanced", "col", "ATT_entropy_balanced"), "M34": ("honest_did", "col", "estimate"), "M13": ("switcher_overall", "col", "estimate"),
    "M35": ("quantile_did", "rows_loose", "QTE"), "M36": ("fect_ife", "col", "att_avg"), "M37": ("fect_mc", "col", "att_avg"),     # v20.58: fect / gsynth ported
    "M38": ("gsynth", "col", "att_avg"), "M39": ("causal_forest_cate", "col", "ATT"), "M40": ("dml", "col", "theta_dml"), "M41": ("meta_learners", "rows_loose", "mean_CATE"),
    "M42": ("dr_learner", "col", "ATE_dr"), "M43": ("causal_forest_att", "col", "ATT"), "M44": ("bart_style", "col", "ATT_bart_style"),   # v20.58: R's long difference
    "M45": ("lasso_sc", "col", "ATT_lasso_sc"), "M18": ("lisa", "finite", "local_I")}

def headline(model, folder):
    """(file, value or list of values, how) from the files the model wrote; None when the file is absent."""
    spec = HEADLINE.get(model)
    if spec is None or not os.path.isdir(folder): return None
    stem, how, col = spec
    fs = sorted(glob.glob(os.path.join(folder, f"{stem}_NDVI.csv"))) or sorted(f for f in glob.glob(os.path.join(folder, f"{stem}*.csv")) if "PACKAGE" not in f)
    if not fs: return None
    f = fs[0]; t = pd.read_csv(f)
    if how == "dose":
        c = next((c for c in t.columns if c.startswith("beta")), None)
        if c is None: return (os.path.basename(f), None, how)
        scale = 100.0 if "pct" in c else 1.0
        return (os.path.basename(f), float(t[c].iloc[0]) * scale, how)
    if col not in t.columns: return (os.path.basename(f), None, how)
    v = pd.to_numeric(t[col], errors="coerce")
    if how in ("col", "zero", "p", "range_pm1", "range_01", "range_pos"): return (os.path.basename(f), float(v.iloc[0]), how)
    if how == "post_mean":
        et = pd.to_numeric(t[next(c for c in ("event_time", "rel_time") if c in t.columns)], errors="coerce")
        return (os.path.basename(f), float(v[(et >= 0) & v.notna()].mean()), how)
    if how == "chained":
        return (os.path.basename(f), float(t["cumulative"].iloc[-1]) if "cumulative" in t.columns else None, how)
    if how == "weighted":
        w = pd.to_numeric(t.get("approx_weight_by_n_obs", pd.Series([1.0] * len(t))), errors="coerce")
        return (os.path.basename(f), float(np.nansum(v * w) / np.nansum(w)), how)
    if how == "mean": return (os.path.basename(f), float(v.mean()), how)
    if how == "flag": return (os.path.basename(f), bool(str(t[col].iloc[0]).lower() in ("true", "1")), how)
    if how == "finite": return (os.path.basename(f), float(np.isfinite(v).mean()), how)
    return (os.path.basename(f), [float(x) for x in v.dropna()], how)


def judge(model, h, panel="single"):
    if h is None: return "NO RESULT", ""
    f, v, how = h
    if v is None: return "FAIL", f"{f}: the headline column is missing"
    tol = 0.02 if model in ATT_LOOSE or how in ("rows_loose",) else 0.01
    if how in ("col", "post_mean", "dose", "weighted", "mean", "chained") and model not in ("M21",):
        ok = np.isfinite(v) and abs(v - TRUE) <= tol
        return ("PASS" if ok else "FAIL"), f"{v:.4f} (truth {TRUE} +- {tol})"
    if model == "M21":                                                  # the naive annual TWFE: the effect on annual rows
        ok = np.isfinite(v) and abs(v - TRUE) <= tol; return ("PASS" if ok else "FAIL"), f"{v:.4f} (truth {TRUE} +- {tol})"
    if how == "zero": return ("PASS" if abs(v) <= 0.01 else "FAIL"), f"{v:.4f} (truth 0: no heterogeneity simulated)"
    if how == "rows_zero": return ("PASS" if all(abs(x) <= 0.01 for x in v) else "FAIL"), f"{[round(x, 4) for x in v]} (truth 0)"
    if how in ("rows", "rows_loose"): return ("PASS" if v and all(abs(x - TRUE) <= tol for x in v) else "FAIL"), f"{[round(x, 4) for x in v]} (truth {TRUE} +- {tol})"
    if how == "p": return ("PASS" if v > 0.001 else "FAIL"), f"p {v:.4g} (no pre-trend simulated)"
    if how == "range_pm1": return ("PASS" if -1 <= v <= 1 else "FAIL"), f"{v:.4f} in [-1, 1]"
    if how == "range_01": return ("PASS" if 0 <= v <= 1 else "FAIL"), f"{v:.4f} in [0, 1]"
    if how == "range_pos": return ("PASS" if v >= 0 else "FAIL"), f"{v:.4g} >= 0"
    if how == "flag": return ("PASS" if v else "FAIL"), f"significant at M = 0: {v}"
    if how == "finite": return ("PASS" if v == 1.0 else "FAIL"), f"share finite {v:.3f}"
    return "RANGE", str(v)


def main(only=None):
    rows = []
    for kind in ("single", "staggered"):
        tmp = tempfile.mkdtemp(prefix=f"known_{kind}_")
        df, coh = make_panel(kind)
        import pyarrow as pa, pyarrow.parquet as pq
        panel = os.path.join(tmp, "panel.parquet"); pq.write_table(pa.Table.from_pandas(df, preserve_index=False), panel)
        C.PREPARED_PANEL = panel; C.RESULTS_ROOT = os.path.join(tmp, "results"); C.ESTIMATOR_FILES_DIR = os.path.join(tmp, "ef")
        C.SELECTED_OUTCOMES = ["NDVI"]; C.GROUND_LINKS_PATH = os.path.join(tmp, "results", "P08", "ground_links.parquet"); C.clear_panel_cache()
        C.set_scenario(verbose=False, all_years=True)
        kw = dict(control_zones="1-5", treatment_year=2022, seasons="all", unit_fe="pixel_season", covariates="all", overlap_rows="drop")
        if kind == "single":
            C.set_scenario(verbose=False, cluster="site", pooled_fe="period", use_site_years=False, **kw)
        else:
            C.set_scenario(verbose=False, cluster="site", pooled_fe="site_period", site_years={k: v for k, v in coh.items()}, **kw)
        C.save_scenario(verbose=False); C.PANEL_SCENARIO_OVERRIDES_CELL1 = True
        nbs = sorted(glob.glob(os.path.join(HERE, "0[2-5]*", "M*.ipynb")))
        if only: nbs = [n for n in nbs if os.path.basename(n).split("_")[0] in only]
        for nb in nbs:
            mid = os.path.basename(nb).split("_")[0]
            t0 = time.time(); status, err, log = VM.run_notebook(nb)
            folder = C.results_dir(mid, make=False)
            h = headline(mid, folder)
            verdict, detail = judge(mid, h, kind)
            if verdict == "NO RESULT" and mid in NO_ANSWER: verdict, detail = "NO ANSWER", NO_ANSWER[mid]
            if verdict == "NO RESULT" and (kind, mid) in EXPECTED_GAP and EXPECTED_GAP[(kind, mid)] in log:
                verdict, detail = "DATA GAP", "expected on one sub-watershed: " + next(l.strip() for l in log.split("\n") if EXPECTED_GAP[(kind, mid)] in l)[:140]
            if verdict == "NO RESULT":
                gap = [l.strip()[:150] for l in log.split("\n") if any(w in l for w in ("DATA GAP", "InsufficientDataError", "NO result", "requires"))]
                detail = (gap[-1] if gap else err or "no result and no reason")
            rows.append({"panel": kind, "model": mid, "verdict": verdict, "detail": detail, "file": h[0] if h else "", "status": status,
                         "secs": round(time.time() - t0, 1)})
            print(f"{kind:9s} {mid}  {verdict:9s} {detail[:120]}  [{h[0] if h else ''}]", flush=True)
    t = pd.DataFrame(rows)
    out = os.path.join(HERE, "VALIDATION_KNOWN_ANSWERS.csv" if not only else "VALIDATION_KNOWN_ANSWERS_SUBSET.csv")   # a subset never replaces the full report
    t.to_csv(out, index=False)
    bad = t[t.verdict.isin(["FAIL"]) | (t.verdict == "NO RESULT")]
    print("=" * 100)
    print(t.groupby(["panel", "verdict"]).size().to_string())
    print(f"report -> {out}")
    print("CLEAN: every model with a known answer meets it." if not len(bad) else f"{len(bad)} PROBLEM(S): " + ", ".join(f"{r.panel}/{r.model}" for r in bad.itertuples()))
    return 1 if len(bad) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
