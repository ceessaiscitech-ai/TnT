"""
Spec 3 -- the orchestrator: one configuration file (config/analysis_config.yaml | .json) -> the design set on the engine, the PRE-FLIGHT checks
(panel integrity, the singleton pre-flight, floating-point range safety), the estimators, and the comparison report.

    python orchestrator.py --config config/analysis_config.yaml [--only canonical,donut] [--panel <parquet>] [--results <dir>] [--dry-run]

Specs of the report (REPORT_SPECS): canonical (TWFE, every ring, every season the config allows), donut (TWFE, SEASON_FILTER, the donut rings out),
matched (TWFE on the pre-period-chosen control rings, CONTROL_SELECTION_METHOD), synthetic_did (the two-level synthetic DiD), surrogate_index (the
in-panel surrogate index). Every row: beta, se, p, the pre-trend p (a differential pre-period slope, clustered), n, clusters, the sample tag.
The R twin (orchestrator.R) reads the same file and writes SPEC_COMPARISON_<outcome>_R.csv.
"""
import os, sys, json, argparse, time
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import _common as C
import surrogate_did_estimator as SD

DEFAULTS = {"ANALYSIS_VARIABLE": "NDVI", "SEASON_FILTER": "Rabi", "DONUT_RINGS": [1], "CONTROL_RINGS": "data", "CONTROL_SELECTION_METHOD": "pre_bias_min", "CONTROL_SELECT_ON": "level",
            "PRECISION_TOLERANCE": 1e-6, "MIN_PIXEL_COVERAGE_PCT": 0.70, "CLUSTER_VAR": "subwshed_id", "ESTIMATOR": "SURROGATE_DID", "LANDUSE_KEEP": "all", "BASELINE_NDVI_MIN": None,
            "SAME_PIXELS": "pre_post", "DROP_SINGLETONS": True, "TREATMENT_TIMING": "fixed", "TREATMENT_YEAR": 2022, "PRE_YEARS": "data", "POST_YEARS": "data", "DESIGN_SOURCE": "model", "EXCLUDE_TRANSITION_YEAR": False,
            "OUTCOME_SCREEN": "drop", "EXCLUDE_GAPFILLED": True, "COVARIATES": ["Rain", "Tmax", "Tmean", "Tmin"], "SURROGATES": ["NDWI", "LSWI", "NDMI", "Rain"], "SURROGATE_SEASON": 1,
            "OUTCOME_SEASONS": [2, 3], "REPORT_SPECS": ["canonical", "donut", "matched", "synthetic_did", "surrogate_index"]}
SEASONS = {"rabi": "Rabi", "kharif": "Kharif", "zaid": "Zaid", "yearly": "yearly", "all": "all"}
METHODS = {"all": ("rings", 2), "pre_bias_min": ("pre_rings", 2), "closest_1": ("pre_rings", 1), "closest_2": ("pre_rings", 2)}
CLUSTERS = {"subwshed_id": "site", "site": "site", "year": "year", "block": "block"}
ESTIMATORS = ("TWFE_CANONICAL", "SYNTHETIC_DID", "SURROGATE_INDEX", "SURROGATE_DID")

def load_config(path):
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh) if path.lower().endswith(".json") else __import__("yaml").safe_load(fh)
    out = dict(DEFAULTS); out.update({k: v for k, v in (cfg or {}).items()}); return validate_config(out)

def validate_config(cfg):
    """Every value against its allowed set -- an error names the key and what is allowed (nothing runs on a wrong configuration)."""
    bad = []
    if str(cfg["SEASON_FILTER"]).lower() not in SEASONS: bad.append(f"SEASON_FILTER {cfg['SEASON_FILTER']!r}: Rabi | Kharif | Zaid | Yearly | All")
    if str(cfg["CONTROL_SELECTION_METHOD"]).lower() not in METHODS: bad.append(f"CONTROL_SELECTION_METHOD {cfg['CONTROL_SELECTION_METHOD']!r}: all | pre_bias_min | closest_1 | closest_2")
    if str(cfg["CLUSTER_VAR"]).lower() not in CLUSTERS: bad.append(f"CLUSTER_VAR {cfg['CLUSTER_VAR']!r}: subwshed_id | year | block")
    if str(cfg["ESTIMATOR"]).upper() not in ESTIMATORS: bad.append(f"ESTIMATOR {cfg['ESTIMATOR']!r}: {' | '.join(ESTIMATORS)}")
    if not (0 <= float(cfg["PRECISION_TOLERANCE"]) <= 1e-2): bad.append("PRECISION_TOLERANCE must be in [0, 1e-2]")
    if not (0 <= float(cfg["MIN_PIXEL_COVERAGE_PCT"]) < 1): bad.append("MIN_PIXEL_COVERAGE_PCT must be in [0, 1)")
    dn = cfg.get("DONUT_RINGS") or []
    if any(int(x) < 1 or int(x) > 5 for x in dn): bad.append("DONUT_RINGS must name rings 1..5")
    if str(cfg["CONTROL_SELECT_ON"]).lower() not in ("level", "rmse", "trend", "both"): bad.append("CONTROL_SELECT_ON: level | rmse | trend | both")
    if str(cfg["SAME_PIXELS"]).lower() not in ("pre_post", "all", "off"): bad.append("SAME_PIXELS: pre_post | all | off")
    if str(cfg["TREATMENT_TIMING"]).lower() not in ("fund", "registry", "fixed"): bad.append("TREATMENT_TIMING: fund | registry | fixed")
    if str(cfg["DESIGN_SOURCE"]).lower() not in ("panel", "model"): bad.append("DESIGN_SOURCE: panel | model")
    for k in ("PRE_YEARS", "POST_YEARS"):
        v = cfg[k]
        if not (v is None or (isinstance(v, str) and v.lower() in ("data", "all")) or (isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 1)): bad.append(f"{k}: data | all | a count of years | a calendar year")
    unknown = [s for s in cfg["REPORT_SPECS"] if s not in ("canonical", "donut", "matched", "synthetic_did", "surrogate_index")]
    if unknown: bad.append(f"REPORT_SPECS unknown: {unknown}")
    if bad: raise C.InsufficientDataError("configuration refused: " + "; ".join(bad))
    return cfg

def scenario_kwargs(cfg, spec="config"):
    """The engine's set_scenario arguments for a spec of the report; 'config' = the configuration as it stands."""
    method, k = METHODS[str(cfg["CONTROL_SELECTION_METHOD"]).lower()]
    yrs = lambda v: "all" if v is None else (v.lower() if isinstance(v, str) else int(v))
    kw = dict(timing=cfg["TREATMENT_TIMING"], treatment_year=int(cfg["TREATMENT_YEAR"]), pre_years=yrs(cfg["PRE_YEARS"]), post_years=yrs(cfg["POST_YEARS"]), design_source=cfg["DESIGN_SOURCE"], exclude_transition_year=bool(cfg["EXCLUDE_TRANSITION_YEAR"]),
              outcome_screen=cfg["OUTCOME_SCREEN"], exclude_gapfilled=bool(cfg["EXCLUDE_GAPFILLED"]), covariates=(list(cfg["COVARIATES"]) if cfg["COVARIATES"] else "none"),
              control_zones=(cfg["CONTROL_RINGS"] if isinstance(cfg["CONTROL_RINGS"], str) else tuple(int(x) for x in cfg["CONTROL_RINGS"])),
              seasons=SEASONS[str(cfg["SEASON_FILTER"]).lower()], donut_rings=[int(x) for x in (cfg.get("DONUT_RINGS") or [])],
              control_selection=method, control_select_k=k, control_select_on=cfg["CONTROL_SELECT_ON"], cluster=CLUSTERS[str(cfg["CLUSTER_VAR"]).lower()],
              landuse_keep=cfg["LANDUSE_KEEP"], baseline_ndvi_min=cfg["BASELINE_NDVI_MIN"], min_pixel_coverage_pct=float(cfg["MIN_PIXEL_COVERAGE_PCT"]),
              drop_singletons=bool(cfg["DROP_SINGLETONS"]), precision_tolerance=float(cfg["PRECISION_TOLERANCE"]), same_pixels=cfg["SAME_PIXELS"], verbose=False)
    if spec == "canonical": kw.update(seasons="all", donut_rings=[], control_selection="rings")            # every ring 1-5, every season
    elif spec == "donut": kw.update(control_selection="rings")                                             # the season filter + the donut, every remaining ring
    elif spec == "matched": kw.update(control_selection=method if method != "rings" else "pre_rings")     # the pre-period-chosen rings
    return kw

def apply_config(cfg, spec="config"):
    C.set_scenario(**scenario_kwargs(cfg, spec)); C._RESOLVED["key"] = None
    C.resolve_design(verbose=False, force=True); return C.scenario_tag()

# ---------------------------------------------------------------- the pre-flight checks
def preflight(df, outcome, cfg):
    """(1) Panel integrity: the treated and the control pixel sets are the same before and after treatment. (2) The singleton pre-flight: series
    seen once (dropped by the engine when DROP_SINGLETONS). (3) Range safety: the outcome within its physical bounds, no no-data code, the
    zero-padding counted. Refuses on (1) or (3)."""
    d = df[df["in_analysis_sample"] == 1]; rows = []
    pre = d["post"].values == 0; tr = d["treatment"].values == 1
    for lab, m in (("treated", tr), ("control", ~tr)):
        a = set(d["pixel_id"].values[m & pre]); b = set(d["pixel_id"].values[m & ~pre])
        rows.append({"check": f"panel integrity: the {lab} pixels are the same in pre and post", "ok": a == b, "detail": f"{len(a):,} pre / {len(b):,} post pixels, {len(a ^ b):,} differ", "strict": True})
    u = C._unit_key(d, "pixel_id"); cnt = d.groupby(u, observed=True).size(); n1 = int((cnt == 1).sum())
    rows.append({"check": "singleton pre-flight: series seen once", "ok": n1 == 0 or bool(cfg["DROP_SINGLETONS"]), "detail": f"{n1:,} of {len(cnt):,} series seen once" + (" -- dropped before the demeaning (DROP_SINGLETONS)" if n1 and cfg["DROP_SINGLETONS"] else ""), "strict": False})
    rc = C.outcome_range_check(d, outcome, say=False) or {}
    rows.append({"check": "range safety: the outcome within its bounds, no no-data code", "ok": bool(rc.get("ok", True)), "detail": f"[{rc.get('vmin')}, {rc.get('vmax')}] against {rc.get('bounds')}; {rc.get('n_outside_bounds', 0):,} outside, {rc.get('n_nodata_codes', 0):,} no-data codes, {rc.get('n_zero_padding', 0):,} within the tolerance of zero", "strict": True})
    tab = pd.DataFrame(rows); tab.insert(0, "outcome", outcome)
    for r in tab.itertuples(): (C.ok if r.ok else C.warn)(f"pre-flight -- {r.check}: {r.detail}")
    bad = tab[~tab.ok & tab.strict]
    if len(bad): raise C.InsufficientDataError("PRE-FLIGHT FAILED: " + " | ".join(f"{r.check} ({r.detail})" for r in bad.itertuples()))
    return tab

def pretrend_p(d, outcome, cluster="subwshed_id"):
    """The differential pre-period slope (treated x centred year on the pre rows, unit and period FE, clustered): its p-value."""
    pre = d[d["post"].values == 0].copy()
    if pre["Year"].nunique() < 3 or (pre["treatment"] == 1).sum() == 0: return float("nan")
    yc = pd.to_numeric(pre["Year"], errors="coerce").values; pre["pretrend_term"] = (pre["treatment"].values == 1) * (yc - yc.mean())
    try:
        b, se = C.estimate_twfe_did(pre, outcome, "pretrend_term", "pixel_id", "time_fe_yearseason", cluster)
        return float(C.LAST_FIT_INFO.get("p_t_G1", np.nan)) if np.isfinite(se) and se > 0 else float("nan")
    except Exception: return float("nan")

# ---------------------------------------------------------------- the specs of the report
def run_spec(spec, cfg, panel_cols_extra=()):
    outcome = cfg["ANALYSIS_VARIABLE"]; t0 = time.time()
    tag = apply_config(cfg, spec if spec in ("canonical", "donut", "matched") else "config")
    C.CURRENT_MODEL_ID = {"canonical": "M01", "donut": "M01", "matched": "M01", "synthetic_did": "M11", "surrogate_index": "M07"}[spec]
    extra = [s for s in cfg["SURROGATES"] if s != outcome] if spec == "surrogate_index" else list(panel_cols_extra)
    df = C.build_treatment_columns(C.load_panel(columns=C.columns_for(outcome, extra)))
    pf = preflight(df, outcome, cfg); d = df[df["in_analysis_sample"] == 1]
    row = {"spec": spec, "outcome": outcome, "tag": tag, "n": int(len(d)), "pixels": int(d["pixel_id"].nunique()), "rings": "+".join(str(int(x)) for x in sorted(d.loc[d.treatment == 0, "buff_km"].unique())),
           "seasons": "+".join(C.SEASON_LABEL.get(int(x), str(x)) for x in sorted(d["Season"].unique())), "pretrend_p": pretrend_p(d, outcome)}
    if spec in ("canonical", "donut", "matched"):
        b, se = C.estimate_twfe_did(d, outcome, "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id")
        row.update({"estimator": "TWFE (two-way FE, CR1)", "beta": b, "se": se, "p_value": C.LAST_FIT_INFO.get("p_t_G1"), "clusters": C.LAST_FIT_INFO.get("n_clusters"), "cluster": C.LAST_CLUSTER_USED.get("value")})
    elif spec == "synthetic_did":
        r = SD.synthetic_did_two_level(d, outcome, season=None, pixel_level=True, cluster_col="subwshed_id"); SD.save_outputs(r, C.results_dir("M11"), outcome)
        row.update({"estimator": "synthetic DiD (two-level; pixel WLS beside)", "beta": r["att"], "se": r["se"], "p_value": r["p_value"], "pre_rmspe": r["pre_rmspe"], "clusters": r["pixel_wls"]["n_clusters"],
                    "cluster": r["pixel_wls"]["cluster"], "pixel_wls_beta": r["pixel_wls"]["beta"], "pixel_wls_se": r["pixel_wls"]["se"]})
    elif spec == "surrogate_index":
        r = SD.surrogate_index_did(d, outcome, cfg["SURROGATES"], outcome_seasons=tuple(int(x) for x in cfg["OUTCOME_SEASONS"]), surrogate_season=int(cfg["SURROGATE_SEASON"]), cluster_col="subwshed_id")
        SD.save_outputs(r, C.results_dir("M07"), outcome)
        row.update({"estimator": f"surrogate index ({'+'.join(r['surrogates'])})", "beta": r["att"], "se": r["se"], "p_value": r["p_value"], "pre_rmspe": r["pre_rmspe"], "clusters": r["n_clusters"], "cluster": r["cluster"]})
    row["seconds"] = round(time.time() - t0, 1); row["preflight"] = "ok" if pf.ok.all() else "warned"
    C.info(f"spec {spec}: beta {row['beta']:+.6f} se {row['se']:.6f} p {row.get('p_value', float('nan')):.3g} | pre-trend p {row['pretrend_p']:.3g} | n {row['n']:,} | {tag}")
    return row

def run_report(cfg, only=None, out_dir=None):
    est = str(cfg["ESTIMATOR"]).upper()
    specs = [s for s in cfg["REPORT_SPECS"] if (only is None or s in only)]
    if est == "TWFE_CANONICAL": specs = [s for s in specs if s in ("canonical", "donut", "matched")]
    elif est == "SYNTHETIC_DID": specs = [s for s in specs if s != "surrogate_index"]
    elif est == "SURROGATE_INDEX": specs = [s for s in specs if s != "synthetic_did"]
    rows = []
    for s in specs:
        try: rows.append(run_spec(s, cfg))
        except C.InsufficientDataError as e:
            C.warn(f"spec {s}: not estimated -- {str(e)[:300]}"); rows.append({"spec": s, "outcome": cfg["ANALYSIS_VARIABLE"], "estimator": "not estimated", "note": str(e)[:300]})
    t = pd.DataFrame(rows); cols = [c for c in ("spec", "estimator", "beta", "se", "p_value", "pretrend_p", "pre_rmspe", "n", "pixels", "clusters", "cluster", "rings", "seasons", "tag", "note") if c in t.columns]
    t = t[cols + [c for c in t.columns if c not in cols]]
    out_dir = out_dir or C.RESULTS_ROOT; os.makedirs(out_dir, exist_ok=True); p = os.path.join(out_dir, f"SPEC_COMPARISON_{cfg['ANALYSIS_VARIABLE']}.csv"); t.to_csv(p, index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
    print("\n" + "=" * 100 + f"\nSPEC COMPARISON -- {cfg['ANALYSIS_VARIABLE']} (config: season {cfg['SEASON_FILTER']}, donut {cfg['DONUT_RINGS']}, controls {cfg['CONTROL_SELECTION_METHOD']}, cluster {cfg['CLUSTER_VAR']})\n" + "=" * 100)
    print(t[[c for c in ("spec", "estimator", "beta", "se", "p_value", "pretrend_p", "n", "clusters") if c in t.columns]].to_string(index=False)); print(f"-> {p}")
    return t

def main(argv=None):
    ap = argparse.ArgumentParser(description="REWARD DiD orchestrator (spec 3)")
    ap.add_argument("--config", default=os.path.join(HERE, "config", "analysis_config.yaml")); ap.add_argument("--only", default=None); ap.add_argument("--panel", default=None)
    ap.add_argument("--results", default=None); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    if a.panel: C.PREPARED_PANEL = a.panel; C.clear_panel_cache()
    if a.results: C.RESULTS_ROOT = a.results; C.ESTIMATOR_FILES_DIR = os.path.join(a.results, "ef")
    print(f"[INFO]    configuration {a.config}: " + ", ".join(f"{k}={cfg[k]}" for k in ("ANALYSIS_VARIABLE", "SEASON_FILTER", "DONUT_RINGS", "CONTROL_SELECTION_METHOD", "CLUSTER_VAR", "ESTIMATOR", "SAME_PIXELS", "DROP_SINGLETONS")))
    if a.dry_run:
        for s in cfg["REPORT_SPECS"]: print(f"[INFO]    {s}: {apply_config(cfg, s if s in ('canonical', 'donut', 'matched') else 'config')}")
        return 0
    t = run_report(cfg, only=(a.only.split(",") if a.only else None)); return 0 if len(t) and t.get("estimator", pd.Series(dtype=str)).ne("not estimated").any() else 1

if __name__ == "__main__":
    sys.exit(main())
