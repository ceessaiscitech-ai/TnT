"""
validate_orchestrator.py (specs 1-3): the configuration file -> the same comparison report from orchestrator.py and orchestrator.R on a synthetic
panel with a known effect. Checks: a wrong configuration is refused (both languages); every spec of the report is estimated; the pre-flight
rows are written and pass; the pre-flight REFUSES a sample whose control pixels differ between pre and post (SAME_PIXELS off on a panel
with pixels seen on one side only); Python == R on beta, SE, p, the pre-trend p, n and clusters (1e-6); the CSVs are written.
    python validate_orchestrator.py
"""
import os, sys, json, shutil, subprocess, tempfile
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
import validate_design_options as V, _common as C, orchestrator as O
import pyarrow as pa, pyarrow.parquet as pq
ROWS = []
def check(name, ok, detail=""):
    ROWS.append({"check": name, "verdict": "PASS" if ok else "FAIL", "detail": str(detail)[:300]}); print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not ok else ""), flush=True)

def main():
    work = tempfile.mkdtemp(prefix="orchestrator_"); root = os.path.join(work, "data"); os.makedirs(os.path.join(root, V._out_sub()), exist_ok=True)
    fund = os.path.join(work, "fund_flat.xlsx"); V.write_fund(fund)
    full = V.make_panel("single"); panel = os.path.join(root, V._out_sub(), "did_panel_full.parquet")
    pq.write_table(pa.Table.from_pandas(full, preserve_index=False), panel, row_group_size=50000)
    C.set_paths(input_dir=root, fund_release=fund, verbose=False); C.clear_panel_cache(); C.SELECTED_OUTCOMES = ["NDVI"]
    cfg = O.load_config(os.path.join(HERE, "config", "analysis_config.yaml"))
    cfg.update({"SEASON_FILTER": "All", "SURROGATES": ["Rain", "Tmax"], "OUTCOME_SEASONS": [2, 3]})     # this synthetic panel: every season, weather proxies
    cfg_path = os.path.join(work, "cfg.json"); json.dump(cfg, open(cfg_path, "w"))
    # 1 a wrong configuration is refused
    for k, v in (("CONTROL_SELECTION_METHOD", "post_means"), ("SEASON_FILTER", "Monsoon"), ("DONUT_RINGS", [7]), ("ESTIMATOR", "OLS"), ("MIN_PIXEL_COVERAGE_PCT", 1.5), ("CLUSTER_VAR", "pixel")):
        try: O.validate_config(dict(cfg, **{k: v})); check(f"Python refuses {k} = {v!r}", False, "accepted")
        except C.InsufficientDataError as e: check(f"Python refuses {k} = {v!r}", k in str(e), str(e)[:120])
    # 2 the Python report
    py_dir = os.path.join(work, "py_out"); t = O.run_report(cfg, out_dir=py_dir)
    specs = ["canonical", "donut", "matched", "synthetic_did", "surrogate_index"]
    check("Python: every spec of the report estimated", list(t.spec) == specs and (t.estimator != "not estimated").all() and np.isfinite(t.beta).all(), t[["spec", "estimator"]].to_dict("records"))
    check("Python: the report CSV written with beta, se, p_value, pretrend_p, n, clusters", os.path.exists(os.path.join(py_dir, "SPEC_COMPARISON_NDVI.csv")) and {"beta", "se", "p_value", "pretrend_p", "n", "clusters"} <= set(t.columns))
    check("Python: every spec passed the pre-flight (panel integrity, singletons, range safety)", (t.preflight == "ok").all(), t.preflight.tolist())
    d_ = t.set_index("spec")
    check("donut spec: no ring-1 control, the Rabi-style donut tag", "1" not in str(d_.loc["donut", "rings"]).split("+") and "_donut1" in d_.loc["donut", "tag"], f"rings {d_.loc['donut', 'rings']}, tag {d_.loc['donut', 'tag']}")
    check("matched spec: exactly 2 control rings (pre_bias_min), tagged _ctrlPre2rL", len(str(d_.loc["matched", "rings"]).split("+")) == 2 and "_ctrlPre2rL" in d_.loc["matched", "tag"], f"rings {d_.loc['matched', 'rings']}, tag {d_.loc['matched', 'tag']}")
    check("canonical spec: rings 1-5, every season", d_.loc["canonical", "rings"] == "1+2+3+4+5" and d_.loc["canonical", "seasons"].count("+") == 3, f"{d_.loc['canonical', 'rings']} | {d_.loc['canonical', 'seasons']}")
    check("the TWFE specs recover the planted effect (+0.05 on the treated core from 2022) within 2 SE", all(abs(d_.loc[s, "beta"] - 0.05) < 2 * d_.loc[s, "se"] + 0.04 for s in ("canonical", "donut", "matched")), d_[["beta", "se"]].to_dict())
    # 3 the pre-flight refuses a sample whose control pixels differ between pre and post
    C.set_scenario(**O.scenario_kwargs(cfg, "canonical")); C.set_scenario(same_pixels="off", verbose=False); C._RESOLVED["key"] = None; C.resolve_design(verbose=False, force=True)
    df = C.build_treatment_columns(C.load_panel(columns=C.columns_for("NDVI")))
    ctrl_post = df[(df.in_analysis_sample == 1) & (df.treatment == 0) & (df.post == 1)].pixel_id.unique()[:3]
    df.loc[df.pixel_id.isin(ctrl_post) & (df.post == 1), "in_analysis_sample"] = 0                     # three control pixels seen in pre only
    try: O.preflight(df, "NDVI", cfg); check("the pre-flight refuses control pixels that differ between pre and post", False, "accepted")
    except C.InsufficientDataError as e: check("the pre-flight refuses control pixels that differ between pre and post", "control pixels are the same in pre and post" in str(e), str(e)[:160])
    df2 = df.copy(); df2.loc[df2.index[:5], "NDVI"] = -9999.0
    try: O.preflight(df2[df2.in_analysis_sample == 1].pipe(lambda x: x), "NDVI", cfg); check("the pre-flight refuses a no-data code in the outcome (range safety)", False, "accepted")
    except C.InsufficientDataError as e: check("the pre-flight refuses a no-data code in the outcome (range safety)", "range safety" in str(e), str(e)[:160])
    # 4 the R orchestrator on the same file
    rs = shutil.which("Rscript"); RHOME = os.path.dirname(os.path.dirname(C.r_bridge_script()))
    if not rs or not os.path.exists(os.path.join(RHOME, "orchestrator.R")):
        check("R orchestrator available (Rscript + orchestrator.R)", False, "Rscript or orchestrator.R not found: the R half is not checked here")
    else:
        env = dict(os.environ, REWARD_R_ROOT=root, REWARD_FUND_PATH=fund, REWARD_SITES_CSV=os.path.join(HERE, "data", "sites", "sites.csv"), REWARD_TEST_RUN="1", AUTO_INSTALL_PACKAGES="FALSE")
        bad_cfg = os.path.join(work, "bad.json"); json.dump(dict(cfg, CONTROL_SELECTION_METHOD="post_means"), open(bad_cfg, "w"))
        r0 = subprocess.run([rs, os.path.join(RHOME, "orchestrator.R"), bad_cfg, "dry_run"], capture_output=True, text=True, env=env, timeout=1800)
        check("R refuses CONTROL_SELECTION_METHOD = 'post_means'", r0.returncode != 0 and "configuration refused" in (r0.stdout + r0.stderr), (r0.stdout + r0.stderr)[-200:])
        r = subprocess.run([rs, os.path.join(RHOME, "orchestrator.R"), cfg_path], capture_output=True, text=True, env=env, timeout=3600)
        open(os.path.join(work, "R.log"), "w").write(r.stdout + r.stderr)
        rp = os.path.join(root, V._out_sub(), "results", "SPEC_COMPARISON_NDVI_R.csv")
        if r.returncode != 0 or not os.path.exists(rp): check("R orchestrator ran and wrote SPEC_COMPARISON_NDVI_R.csv", False, (r.stdout + r.stderr)[-400:])
        else:
            tr = pd.read_csv(rp); m = t.merge(tr, on="spec", suffixes=("_py", "_R"))
            check("R: every spec of the report estimated", list(tr.spec) == specs and (tr.estimator != "not estimated").all(), tr[["spec", "estimator"]].to_dict("records"))
            for c in ("beta", "se", "p_value", "pretrend_p"):
                gap = float(np.nanmax(np.abs(m[c + "_py"].values - m[c + "_R"].values)))
                check(f"Python == R on {c} for every spec (1e-6)", gap < 1e-6, f"max |py - R| = {gap:.3g}")
            for c in ("n", "clusters"):
                check(f"Python == R on {c} for every spec", (m[c + "_py"].values == m[c + "_R"].values).all(), m[["spec", c + "_py", c + "_R"]].to_dict("records"))
            check("R pre-flight rows written and passed", "pre-flight -- panel integrity: the control pixels are the same in pre and post" in r.stdout and "PRE-FLIGHT FAILED" not in r.stdout)
    tab = pd.DataFrame(ROWS); out = os.path.join(HERE, "ORCHESTRATOR_VALIDATION.csv"); tab.to_csv(out, index=False)     # the bundle's copy: docs/VALIDATION_ORCHESTRATOR_v20.59.csv
    n_fail = int((tab.verdict == "FAIL").sum()); print("=" * 90)
    print(f"ORCHESTRATOR: {'CLEAN' if not n_fail else f'{n_fail} FAIL'} -- {len(tab)} checks -> {out}  (work folder {work})")
    return 1 if n_fail else 0

if __name__ == "__main__":
    sys.exit(main())
