"""
validate_all_models.py -- production gate (v20.3)

Runs EVERY model notebook on a small synthetic panel under two different scenarios and checks that each one
actually honoured the run's choices:

    scenario A: rings 1-5, treatment 2023, all years
    scenario B: rings 1-2, treatment 2022, pre 3 / post 2  (and, with --cohorts, a cohort offset)

For each model it records: status, the results folder it wrote to, and whether the two runs produced DIFFERENT
folders and different numbers. A model that ignores the scenario writes to the wrong folder or produces identical
results under both scenarios -- both are reported as failures.

    python validate_all_models.py              (all models)
    python validate_all_models.py M01 M02      (a subset)
"""
import os, sys, json, glob, time, tempfile, traceback, contextlib, io
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _common as C


def make_panel(n_pix=420, years=range(2015, 2027), seasons=(1, 2, 3), seed=7):
    rng = np.random.default_rng(seed)
    pix = pd.DataFrame({"pixel_id": np.arange(1, n_pix + 1) * 7919, "buff_km": rng.integers(0, 6, n_pix)})
    pix["subwshed_id"] = "SW" + rng.integers(0, 6, n_pix).astype(str)
    alpha = rng.normal(0, 1, n_pix); rows = []
    for j, r in pix.iterrows():
        cohort = 2022 + int(r.pixel_id % 3)              # staggered cohorts for M05/M27/M30/...
        for y in years:
            for s in seasons:
                eff = 0.05 if (r.buff_km == 0 and y >= 2023) else 0.0
                base = 0.40 + alpha[j] * 0.05 + eff + rng.normal(0, 0.03)
                rows.append((r.pixel_id, y, s, int(r.buff_km), r.subwshed_id, base, base * 3 + rng.normal(0, .05),
                             base * 0.5, base * 0.9 + rng.normal(0, .02), base * 1.1 + rng.normal(0, .02),
                             base * 20 + rng.normal(0, 1), base * 0.8 + rng.normal(0, .02),
                             600 + rng.normal(0, 60), 33 + rng.normal(0, 1.5), 26 + rng.normal(0, 1.2),
                             19 + rng.normal(0, 1.2), cohort, 40.0 + 10 * (r.pixel_id % 4),
                             16.4 + (r.pixel_id % 50) * 1e-3, 75.1 + (r.pixel_id % 40) * 1e-3,
                             int(2 if r.pixel_id % 5 else 1)))
    df = pd.DataFrame(rows, columns=["pixel_id", "Year", "Season", "buff_km", "subwshed_id", "NDVI", "LAI", "SMDI",
                                     "SAVI", "EVI", "AGB", "LSWI", "Rain", "Tmax", "Tmean", "Tmin",
                                     "first_treat_agri_year", "dose_per_subwshed", "latitude", "longitude", "LandUse"])
    df["time_fe_yearseason"] = df.Year.astype(str) + "_" + df.Season.map({1: "Kharif", 2: "Rabi", 3: "Zaid"})
    df["time_fe_year"] = df.Year.astype(str); df["time_fe_season"] = df.Season.map({1: "Kharif", 2: "Rabi", 3: "Zaid"})
    df["season_sort_rank"] = df.Season; df["Coverage"] = 1.0
    df["dose_intensity_per_ha"] = df["dose_per_subwshed"] / 100.0; df["dose_amount_sws"] = df["dose_per_subwshed"] * 10.0   # v20.57: as P00 writes them
    df["site_id"] = (df.pixel_id % 3 + 1).astype("int16")           # v20.22: three sites (SWSiD_All 1..3)
    # v20.24: the ANNUAL composite (Season 0) = the mean of the seasons per pixel-year, complete for every year
    num = [c for c in df.columns if c not in ("pixel_id", "Year", "Season", "subwshed_id", "time_fe_yearseason", "time_fe_year", "time_fe_season", "season_sort_rank", "buff_km", "site_id", "LandUse", "first_treat_agri_year", "dose_per_subwshed", "latitude", "longitude")]
    y0 = df.groupby(["pixel_id", "Year"], as_index=False).agg({**{c: "mean" for c in num}, **{c: "first" for c in ("subwshed_id", "buff_km", "site_id", "LandUse", "first_treat_agri_year", "dose_per_subwshed", "latitude", "longitude") if c in df.columns}})
    y0["Season"] = 0; y0["time_fe_yearseason"] = y0.Year.astype(str) + "_Yearly"; y0["time_fe_year"] = y0.Year.astype(str); y0["time_fe_season"] = "Yearly"; y0["season_sort_rank"] = 0
    for _c in ("Rain", "Tmax", "Tmean", "Tmin"):          # v20.24: the realistic case -- the annual composite carries no
        if _c in y0.columns: y0[_c] = np.nan              # weather; load_panel fills it from the pixel-year seasonal mean
    df = pd.concat([df, y0[df.columns]], ignore_index=True)
    # v20.13: real exports have gaps. 8% of NDVI and 5% of Rain are missing at random -- every model must still run
    # and produce finite numbers, because load_panel excludes those rows before any estimator sees them.
    _r = np.random.default_rng(11)
    df.loc[_r.random(len(df)) < 0.08, "NDVI"] = np.nan
    df.loc[_r.random(len(df)) < 0.05, "Rain"] = np.nan
    df.loc[_r.random(len(df)) < 0.04, "NDVI"] = 0.0          # v20.16: masked cells exported as exact zeros
    df.loc[_r.random(len(df)) < 0.03, "Tmax"] = np.nan      # v20.30: a masked covariate cell, as preparation leaves it
                                                            # (exact zeros become missing BEFORE the floor at 0)
    return df


def run_notebook(nb_path, quiet=True):
    import _prep_common as P
    # the harness skips the notebooks' path-searching bootstrap and injects the engines directly, so a cell that
    # references C / P works exactly as it does in Jupyter after CELL 1 has run
    ns = {"__name__": "__main__", "os": os, "json": json, "C": C, "P": P, "np": np, "pd": pd}
    buf = io.StringIO()
    try:
        with (contextlib.redirect_stdout(buf) if quiet else contextlib.nullcontext()):
            for c in json.load(open(nb_path, encoding="utf-8"))["cells"]:
                if c["cell_type"] != "code": continue
                src = "".join(c["source"])
                if src.lstrip().startswith("# ---- CELL 0") or "run_other_outcomes" in src: continue
                if "ROBUST IMPORT BOOTSTRAP" in src: src = src[src.index("# ---- CELL 1"):]
                src = "\n".join(l for l in src.split("\n") if not l.lstrip().startswith(("%", "!")))
                src = (src.replace("C.system_report()", "pass").replace("C.autotune()", "pass")
                          .replace("C.gpu_selftest(n=2_000_000)", "None"))
                exec(compile(src, nb_path, "exec"), ns)
        return "ok", "", buf.getvalue()
    except SystemExit:
        return "ok", "", buf.getvalue()
    except Exception as e:
        return "failed", f"{type(e).__name__}: {str(e)[:160]}", buf.getvalue() + traceback.format_exc(limit=2)


def result_fingerprint(folder):
    """Every number written for this scenario, rounded -- two scenarios must not produce the same fingerprint."""
    vals = []
    for f in sorted(glob.glob(os.path.join(folder, "*.csv"))):
        try:
            t = pd.read_csv(f)
        except Exception:
            continue
        num = t.select_dtypes("number")
        vals.append((os.path.basename(f), tuple(np.round(num.values.ravel()[:40].astype(float), 6)) if len(num) else ()))
    return tuple(vals)


def main(only=None, cohorts=False):
    tmp = tempfile.mkdtemp()
    df = make_panel()
    try:
        import pyarrow as pa, pyarrow.parquet as pq
        panel = os.path.join(tmp, "panel.parquet")
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), panel, row_group_size=20000)
    except Exception as e:
        print(f"[FAILED]  could not write the test panel ({e})"); return 1
    C.PREPARED_PANEL = panel; C.RESULTS_ROOT = os.path.join(tmp, "results")
    C.ESTIMATOR_FILES_DIR = os.path.join(tmp, "ef"); C.SELECTED_OUTCOMES = ["NDVI"]
    C.GROUND_LINKS_PATH = os.path.join(tmp, "results", "P08", "ground_links.parquet")

    scenarios = [
        ("A", dict(control_zones="1-5", treatment_year=2023, all_years=True)),
        ("B", dict(control_zones="1-2", treatment_year=2022, pre_years=3, post_years=2,
                   **({"cohort_offset": 1} if cohorts else {}))),
    ]
    all_tags = []
    for _t, _kw in scenarios:
        C.set_scenario(verbose=False, all_years=True); C.set_scenario(verbose=False, **_kw); all_tags.append(C.scenario_tag())
    nbs = sorted(glob.glob(os.path.join(HERE, "0[2-5]*", "M*.ipynb")))
    if only: nbs = [n for n in nbs if os.path.basename(n).split("_")[0] in only]
    rows = []
    for nb in nbs:
        mid = os.path.basename(nb).split("_")[0]
        rec = {"model": mid}
        for tag, kw in scenarios:
            C.set_scenario(verbose=False, all_years=True)          # clear any leftover window
            C.set_scenario(verbose=False, **kw)
            C.save_scenario(verbose=False)   # panel-level choice: every notebook inherits it via C.load_scenario()
            C.PANEL_SCENARIO_OVERRIDES_CELL1 = True    # v20.34: the gate FORCES its scenario over the notebooks' CELL 1
            # the scenario a model must honour, whatever it does internally
            expect_dir = C.results_dir(mid, make=False); expect_tag = C.scenario_tag()
            t0 = time.time()
            status, err, log = run_notebook(nb)
            rec[f"status_{tag}"] = status; rec[f"secs_{tag}"] = round(time.time() - t0, 1)
            rec[f"err_{tag}"] = err
            rec[f"dir_{tag}"] = expect_tag if os.path.isdir(expect_dir) and glob.glob(os.path.join(expect_dir, "*.csv")) else ""
            rec[f"fp_{tag}"] = result_fingerprint(expect_dir) if rec[f"dir_{tag}"] else ()
            # did it write anywhere ELSE? (a model that ignored the scenario writes to another tag)
            known = {C.scenario_tag({**C.ACTIVE, **dict(k2)}) for _, k2 in []} | set(all_tags)
            others = [os.path.basename(d) for d in glob.glob(os.path.join(C.RESULTS_ROOT, mid, "*"))
                      if os.path.isdir(d) and os.path.basename(d) not in known and glob.glob(os.path.join(d, "*.csv"))]
            rec[f"stray_{tag}"] = ";".join(sorted(others))
            if status == "ok" and not rec[f"dir_{tag}"]:
                gap = [l.strip()[:110] for l in log.split("\n")
                       if any(w in l for w in ("DATA GAP", "InsufficientDataError", "NO result", "not available", "requires"))]
                rec[f"reason_{tag}"] = gap[-1] if gap else "no result file and no reason printed"
        # v20.20: NO PLACEHOLDERS anywhere in any result file this model wrote (any scenario)
        for tag in ("A", "B"):
            if rec.get(f"dir_{tag}"):
                d_ = os.path.join(C.RESULTS_ROOT, mid, rec[f"dir_{tag}"])
                for f in glob.glob(os.path.join(d_, "*.csv")):
                    if os.path.basename(f) == "NOT_ESTIMATED.csv": continue
                    try:
                        t_ = pd.read_csv(f)
                    except Exception:
                        rec[f"placeholders_{tag}"] = (rec.get(f"placeholders_{tag}", "") + f"{os.path.basename(f)}:unreadable;"); continue
                    if len(t_) == 0:
                        rec[f"placeholders_{tag}"] = (rec.get(f"placeholders_{tag}", "") + f"{os.path.basename(f)}:empty;"); continue
                    ph = C._placeholder_cells(t_)
                    if ph: rec[f"placeholders_{tag}"] = (rec.get(f"placeholders_{tag}", "") + f"{os.path.basename(f)}:{ph[0]};")
                    if "status" in t_.columns and (t_["status"].astype(str) == "EMPTY_RESULT").any():
                        rec[f"placeholders_{tag}"] = (rec.get(f"placeholders_{tag}", "") + f"{os.path.basename(f)}:EMPTY_RESULT;")
        # v20.13: a result file whose coefficient columns are all NaN is a failure, not a result
        for tag in ("A", "B"):
            if rec[f"dir_{tag}"]:
                d_ = os.path.join(C.RESULTS_ROOT, mid, rec[f"dir_{tag}"])
                nan_files = []
                for f in glob.glob(os.path.join(d_, "*.csv")):
                    try:
                        t_ = pd.read_csv(f); num = t_.select_dtypes("number")
                        coef = [c for c in num.columns if any(c.lower().startswith(k) for k in ("beta", "att", "coef", "estimate", "effect"))]
                        if coef and num[coef].isna().all().all(): nan_files.append(os.path.basename(f))
                    except Exception:
                        pass
                rec[f"nan_results_{tag}"] = ";".join(nan_files)
        wrote_both = bool(rec["dir_A"]) and bool(rec["dir_B"])
        rec["honours_scenario"] = ("yes" if wrote_both and rec["fp_A"] != rec["fp_B"] else
                                   ("identical_results" if wrote_both else
                                    ("no_output" if not (rec["dir_A"] or rec["dir_B"]) else "one_scenario_only")))
        rec.pop("fp_A"); rec.pop("fp_B")
        rows.append(rec)
        print(f"{mid:4s} A:{rec['status_A']:7s}({rec['secs_A']:5.1f}s) B:{rec['status_B']:7s}({rec['secs_B']:5.1f}s) "
              f"-> {rec['honours_scenario']}" + (f"  [A] {rec['err_A'][:70]}" if rec["err_A"] else "")
              + (f"  [B] {rec['err_B'][:70]}" if rec["err_B"] and rec["err_B"] != rec["err_A"] else "")
              + (f"  reason: {rec.get('reason_A') or rec.get('reason_B')}" if rec["honours_scenario"] in ("no_output", "one_scenario_only") else ""))
    # a model that writes nothing because the DATA it needs is absent is NOT a scenario failure -- label it
    KNOWN = {
    "M36": "v20.38: the sub-watershed is the unit -- matrix completion needs >= N_FACTORS+2 sub-watersheds (the pooled run; CLUSTER='subwshed' restores within-SWS units once defined)",
    "M45": "v20.38: the sub-watershed is the unit -- a synthetic control needs >= 3 UNTREATED donor sub-watersheds","M07": "needs ground_truth_outcomes.csv (external survey file)",
             "M08": "needs rollout_instrument.csv (no instrument exists)",
             "M16": "pre-trends F-test needs >=2 pre periods in the window",
             "M31": "stacked DiD needs cohorts with clean controls",
             "M37": "matrix completion needs treated cells inside the window",
             "M38": "gsynth needs a treated UNIT at the clustering level"}
    for r in rows:
        if r["honours_scenario"] != "yes" and r["model"] in KNOWN:
            r["honours_scenario"] = "data_gap"; r["data_gap"] = KNOWN[r["model"]]
    # v20.16: the readiness tool must run on the same panel and classify every model
    try:
        import readiness as R
        C.set_scenario(verbose=False, all_years=True); C.set_scenario(verbose=False, control_zones="1-5", treatment_year=2023)
        rt, rf = R.model_readiness(panel, save_dir=tmp, verbose=False)
        # v20.58: every model OF THIS PROJECT (_paths.PIPELINE_MODELS: all 45 in RWD_Artal, four in RWD_4Models), each classified
        assert len(rt) == len(C.pipeline_models()) and set(rt.model) == set(C.pipeline_models()) and set(rt.status) <= {"complete", "limited", "incomplete-need data"}, \
            f"readiness classified {len(rt)} model(s) {sorted(rt.model)[:6]}..., the project carries {len(C.pipeline_models())}"
        print(f"readiness on the gate panel: {(rt.status=='complete').sum()} complete / {(rt.status=='limited').sum()} limited / {(rt.status=='incomplete-need data').sum()} incomplete-need data")
    except Exception as e:
        print(f"[FAILED]  readiness tool failed on the gate panel: {type(e).__name__}: {e}")
        rows.append({"model": "READINESS", "status_A": "failed", "status_B": "failed", "honours_scenario": "no_output", "err_A": str(e)})
    # v20.22: multi-site -- per-site and pooled runs of the 2x2 through run_sites, and the package-input export
    import _sites as _S
    _S.PHASE_TREATMENT_YEAR = {1: 2022, 2: 2023}; _S.registry(refresh=True)
    C.set_scenario(verbose=False, all_years=True); C.set_scenario(verbose=False, control_zones="1-5", treatment_year=2023)
    def _m01(where):
        d_ = C.load_panel(columns=C.columns_for("NDVI")); d_ = C.build_treatment_columns(d_); d_ = d_[d_.in_analysis_sample == 1]
        return C.estimate_twfe_did(d_, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id")[0]
    ms = C.run_sites(_m01, sites=[1, 2, 3], label="gate")
    ok_sites = int((ms.status == "ok").sum())
    pooled_ok = bool((ms[ms.site == "pooled"].status == "ok").any()) if "site" in ms.columns else False
    files_, meta_ = C.export_for_packages("NDVI")
    pi_ = pd.read_csv([f for f in files_ if f.endswith(".csv")][0])
    inv = bool((pi_.did == pi_.treat * pi_.post).all()) and pi_.NDVI.notna().all() and (pi_.NDVI != 0).all() and set(C.PACKAGE_INPUT_COLUMNS) <= set(pi_.columns)
    st_ = C.site_design_table(verbose=False)                          # v20.28: per-site design table
    inv = inv and len(st_) == 3 and (st_.treated_pixels > 0).all() and (st_.control_pixels > 0).all()
    print(f"multi-site: {ok_sites}/4 runs ok (3 sites + pooled) | pooled ok {pooled_ok} | package input: {len(pi_):,} rows, invariants {inv} | site table {len(st_)} sites")
    if ok_sites < 4 or not inv:
        for r in rows: r["honours_scenario"] = "multisite_gate_failed"
    C.set_scenario(verbose=False, use_site_years=False, cluster="subwshed", pooled_fe="period")
    # v20.21: a frozen outcome (same value every year within a pixel) must be REFUSED by the core estimators
    C.set_scenario(verbose=False, all_years=True); C.set_scenario(verbose=False, control_zones="1-5", treatment_year=2023)
    fr_ = C.load_panel(columns=C.columns_for("NDVI")).copy()
    base = fr_.groupby("pixel_id")["NDVI"].transform("mean"); fr_["NDVI"] = np.where(fr_["Year"] < 2025, base, fr_["NDVI"])
    dd = C.build_treatment_columns(fr_); dd = dd[dd.in_analysis_sample == 1]
    refused = 0
    for fn in (lambda: C.estimate_twfe_did(dd, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id"),
               lambda: C.estimate_event_study(dd, "NDVI", "treat_core", "event_time", "pixel_id", "time_fe_yearseason", "subwshed_id"),
               lambda: C.pretrends_joint_ftest(dd, "NDVI", "treat_core", "event_time", "pixel_id", "time_fe_yearseason", "subwshed_id")):
        try: fn()
        except C.InsufficientDataError as e: refused += ("FROZEN SERIES" in str(e))
        except Exception as e: print("frozen-series probe raised", type(e).__name__, str(e)[:80])
    print(f"frozen-series guard: {refused}/3 core estimators refused a panel whose pre-2025 values never change within a pixel")
    # v20.29: ALL years and ALL row types (annual + Kharif/Rabi/Zaid), pixel x season FE, annual covariates filled
    _d = C.load_panel(columns=C.columns_for("NDVI")); _li = dict(C.LAST_LOAD_INFO); _d = C.build_treatment_columns(_d)
    _seas = sorted(int(x) for x in _d["Season"].unique()); _yrs = sorted(int(x) for x in _d["Year"].unique())
    _units_ok = bool(("unit_id" in _d.columns) and (_d.groupby("unit_id")["Season"].nunique().max() == 1))
    print(f"all years + seasons: NDVI uses seasons {_seas}, years {_yrs[0]}-{_yrs[-1]}; one season per unit FE: {_units_ok}; "
          f"annual covariate values filled from seasons: {_li.get('yearly_covariates_filled', 0):,}")
    if _seas != [0, 1, 2, 3] or not _units_ok or not _li.get("yearly_covariates_filled"):
        for r in rows: r["honours_scenario"] = "all_years_seasons_not_applied"
    if refused < 3:
        for r in rows: r["honours_scenario"] = "frozen_guard_missing"
    # v20.17: the frame every model receives from load_panel must be free of NaN AND exact zeros in the columns
    # it estimates on (outcome + covariates), and the counts must be reported -- the guarantee behind all 45 models
    C.set_scenario(verbose=False, all_years=True); C.set_scenario(verbose=False, control_zones="1-5", treatment_year=2023)
    fr = C.load_panel(columns=C.columns_for("NDVI"))
    est = [c for c in C.CURRENT_ESTIMATION_COLUMNS if c in fr.columns and c != "LandUse"]
    n_nan = int(sum(pd.to_numeric(fr[c], errors="coerce").isna().sum() for c in est))
    n_zero = int(sum((pd.to_numeric(fr[c], errors="coerce") == 0).sum() for c in est if c not in C.FLOORED_COVARIATES))   # v20.30: a floored 0 is real
    li = dict(C.LAST_LOAD_INFO)
    print(f"load_panel guarantee: NaN cells {n_nan}, exact-zero cells {n_zero} in {est}; "
          f"dropped {li.get('rows_dropped_missing', 0):,} rows (of which {li.get('rows_dropped_zero', 0):,} for zeros) of {li.get('rows_seen', 0):,}")
    if n_nan or n_zero or not li.get("rows_dropped_zero"):
        print("MISSING-VALUE GUARANTEE VIOLATED: models could receive NaN/zero cells (or the zero count was not reported)")
        for r in rows: r["honours_scenario"] = "guarantee_violated"
    out = pd.DataFrame(rows)
    p = os.path.join(HERE, "VALIDATION_ALL_MODELS.csv"); out.to_csv(p, index=False)
    print("\n" + "=" * 78)
    print(out["honours_scenario"].value_counts().to_string())
    print(f"status A: {out.status_A.value_counts().to_dict()} | status B: {out.status_B.value_counts().to_dict()}")
    for col in ("placeholders_A", "placeholders_B"):
        if col not in out.columns: out[col] = ""
    phres = out[(out["placeholders_A"].fillna("") != "") | (out["placeholders_B"].fillna("") != "")]
    if len(phres): print("MODELS WRITING PLACEHOLDER VALUES:", phres[["model", "placeholders_A", "placeholders_B"]].to_dict("records"))
    else: print("no result file contains a placeholder value or an EMPTY_RESULT row")
    nanres = out[(out.get("nan_results_A", pd.Series("", index=out.index)).fillna("") != "") | (out.get("nan_results_B", pd.Series("", index=out.index)).fillna("") != "")]
    if len(nanres): print("MODELS WRITING ALL-NaN COEFFICIENTS:", nanres[["model", "nan_results_A", "nan_results_B"]].to_dict("records"))
    else: print("no model wrote an all-NaN coefficient file")
    stray = out[(out.stray_A != "") | (out.stray_B != "")]
    if len(stray): print("MODELS WRITING OUTSIDE THEIR SCENARIO FOLDER:", stray[["model", "stray_A", "stray_B"]].to_dict("records"))
    print(f"report -> {p}")
    # v20.58: NO SILENT PASS -- the gate fails when any model does not honour the scenario (a known data gap excepted), writes a
    # placeholder, an all-NaN coefficient file or a file outside its scenario folder, or a check above failed (until v20.57 it returned 0)
    bad = out[~out.honours_scenario.isin(["yes", "data_gap"])]
    bad_models = sorted(set(bad.model) | set(phres.model) | set(nanres.model) | set(stray.model))
    print("CLEAN: every model honours the scenario; no placeholder, no all-NaN file, nothing written outside its folder."
          if not bad_models else f"{len(bad_models)} PROBLEM(S): " + ", ".join(f"{m} ({out.loc[out.model == m, 'honours_scenario'].iloc[0]})" for m in bad_models))
    return 1 if bad_models else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(main(only=set(args) or None, cohorts="--cohorts" in sys.argv))
