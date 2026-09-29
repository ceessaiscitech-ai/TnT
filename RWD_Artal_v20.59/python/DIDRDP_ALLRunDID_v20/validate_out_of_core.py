"""
validate_out_of_core.py -- v20.58: PROOF that the OUT-OF-CORE path (beyond 98 % of the RAM: Dask, then Spark, then the built-in batches)
gives the in-memory numbers -- file by file, cell by cell -- and that the switch happens by itself at 98 %.

  known      the two synthetic panels of validate_known_answers (one sub-watershed; eight pooled, two cohorts): M01, M02, M16, M34 in memory
             (the engine) and out of core on Dask, Spark and the batches (5 pixel partitions) -- every file of every model identical
  layout     your Koranahalli layout of the poison test (fund timing, the location rule, fragments, overlaps, cloud gaps) through P00, then the
             four models in memory and out of core on each engine; the POISONED data out of core must give the clean numbers
  p00        P00's PASS A + PASS B with EVERY block out of core (pixel-range pieces on Dask, Spark, batches): the same panel, row for row
  switch     a RAM budget below the model's need (REWARD_RAM_BUDGET_BYTES -- this check only): run_mode chooses out of core BY ITSELF and
             the result equals the in-memory one
  streaming  the location table and the outcome identities computed row group by row group equal the all-at-once ones

    python validate_out_of_core.py                            (everything: ~30-40 min on 2 cores, minutes on your machine)
    python validate_out_of_core.py --only known,switch        (a subset)     --engines dask,batches   (some engines)

An engine that is not installed here (Spark without Java, say) is listed as NOT AVAILABLE with the reason -- never skipped silently; the
fall-back order then goes on to the next engine (OUT_OF_CORE in _paths.py).
"""
import os, sys, re, ast, json, glob, time, shutil, tempfile, subprocess
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
MODELS = ["M01", "M02", "M16", "M34"]
ENGINES = ["dask", "spark", "batches"]
RTOL = 1e-7
OOC_NOTE = re.compile(r" -- out of core: .*$")

KNOWN_RUNNER = r'''
import sys, os, json, glob, time
eng, kind, panel, results, models = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], json.loads(sys.argv[5])
sys.path.insert(0, eng); os.chdir(eng)
import _common as C, validate_all_models as VM, validate_known_answers as KA
coh = json.loads(sys.argv[6])
C.PREPARED_PANEL = panel; C.RESULTS_ROOT = results; C.ESTIMATOR_FILES_DIR = os.path.join(os.path.dirname(results), "ef_" + os.path.basename(results))
C.SELECTED_OUTCOMES = ["NDVI"]; C.GROUND_LINKS_PATH = os.path.join(results, "P08", "ground_links.parquet"); C.clear_panel_cache()
C.set_scenario(verbose=False, all_years=True)
kw = dict(control_zones="1-5", treatment_year=2022, seasons="all", unit_fe="pixel_season", covariates="all", overlap_rows="drop")
if kind == "single": C.set_scenario(verbose=False, cluster="site", pooled_fe="period", use_site_years=False, **kw)
else: C.set_scenario(verbose=False, cluster="site", pooled_fe="site_period", site_years={int(k): int(v) for k, v in coh.items()}, **kw)
C.save_scenario(verbose=False); C.PANEL_SCENARIO_OVERRIDES_CELL1 = True
for mid in models:
    nb = glob.glob(os.path.join(eng, "0*", mid + "_*.ipynb"))[0]
    t0 = time.time(); st, err, log = VM.run_notebook(nb)
    ooc = "OUT OF CORE" in log
    open(os.path.join(os.path.dirname(results), os.path.basename(results) + "_" + mid + ".log"), "w", encoding="utf-8").write(log)
    print(json.dumps({"model": mid, "status": st, "error": (err or "")[:300], "secs": round(time.time() - t0, 1), "out_of_core": ooc}), flush=True)
print("@@DONE@@")
'''

P00_RUNNER = r'''
import sys, os, json, time
eng, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, eng); os.chdir(eng)
import _prep_common as P
P.IN_MEMORY_BLOCKS = True
temp = os.path.join(out, "temp"); os.makedirs(temp, exist_ok=True)
t0 = time.time()
reg, unres, perr, dconf, shards = P.run_pass_a(P.INPUT_DIR, temp, out)
final = P.run_pass_b(shards, out)
print(json.dumps({"panel": final, "secs": round(time.time() - t0, 1)}))
print("@@DONE@@")
'''


def _run(args, env=None, cwd=HERE, timeout=6 * 3600):
    e = dict(os.environ); e.update(env or {})
    for k, v in list(e.items()):
        if v is None: e.pop(k)
    e["PYTHONPATH"] = os.pathsep.join(p for p in e.get("PYTHONPATH", "").split(os.pathsep) if p and os.path.abspath(p) != HERE)
    return subprocess.run([sys.executable] + args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=e)


def _status(r):
    return [json.loads(l) for l in r.stdout.splitlines() if l.startswith('{"model"')]


def compare(a, b, models=MODELS, numbers_only=False):
    """(files compared, [differences]) between two results folders: every csv of the models, every cell (numbers to 1e-7 relative)."""
    diffs = []
    fa = sorted(os.path.relpath(f, a) for m in models for f in glob.glob(os.path.join(a, m, "**", "*.csv"), recursive=True))
    fb = sorted(os.path.relpath(f, b) for m in models for f in glob.glob(os.path.join(b, m, "**", "*.csv"), recursive=True))
    n = 0
    for f in sorted(set(fa) | set(fb)):
        if f not in fa or f not in fb:
            diffs.append(f"only in {'memory' if f in fa else 'out of core'}: {f}"); continue
        x = pd.read_csv(os.path.join(a, f)); y = pd.read_csv(os.path.join(b, f)); n += 1
        if list(x.columns) != list(y.columns):
            diffs.append(f"{f}: columns differ ({sorted(set(x.columns) ^ set(y.columns)) or 'order'})")
        if x.shape[0] != y.shape[0]:
            diffs.append(f"{f}: {x.shape[0]} vs {y.shape[0]} rows"); continue
        for c in [c for c in x.columns if c in y.columns]:
            u, v = x[c], y[c]
            if c == "engine": u = u.astype(str).str.replace(OOC_NOTE, "", regex=True); v = v.astype(str).str.replace(OOC_NOTE, "", regex=True)
            if u.dtype == bool or v.dtype == bool: u = u.astype(str); v = v.astype(str)
            un = pd.to_numeric(u, errors="coerce").astype(float); vn = pd.to_numeric(v, errors="coerce").astype(float)
            if un.notna().sum() == u.notna().sum() and vn.notna().sum() == v.notna().sum() and u.notna().any():
                if (un.isna() != vn.isna()).any(): diffs.append(f"{f}:{c}: missing values differ"); continue
                m = un.notna().values
                d = np.abs(un.values[m] - vn.values[m]); tol = RTOL * np.maximum(np.abs(un.values[m]), 1e-12) + 1e-13
                inf = ~np.isfinite(un.values[m]) | ~np.isfinite(vn.values[m])
                if (inf & (un.values[m] != vn.values[m])).any() or ((d > tol) & ~inf).any():
                    i = int(np.argmax(np.where(inf, 0, d / tol))); diffs.append(f"{f}:{c}: {un.values[m][i]!r} vs {vn.values[m][i]!r}")
            elif not numbers_only:
                for p_, q_ in zip(u.astype(str).fillna(""), v.astype(str).fillna("")):
                    if p_ == q_: continue
                    try:
                        A, B = ast.literal_eval(p_), ast.literal_eval(q_)
                        if isinstance(A, dict) and isinstance(B, dict) and A.keys() == B.keys() and all(
                                abs(float(A[k]) - float(B[k])) <= RTOL * max(abs(float(A[k])), 1e-12) + 1e-13 for k in A):
                            continue
                    except Exception:
                        pass
                    diffs.append(f"{f}:{c}: {p_[:120]!r} vs {q_[:120]!r}"); break
    return n, diffs


def engines_available(want):
    import _outofcore as O
    out = {}
    for e in want:
        ok, why = O.engine_status(e); out[e] = (ok, why)
    return out


def check_known(base, engines, rows):
    import validate_known_answers as KA, pyarrow as pa, pyarrow.parquet as pq
    for kind in ("single", "staggered"):
        df, coh = KA.make_panel(kind)
        d = os.path.join(base, f"known_{kind}"); os.makedirs(d, exist_ok=True)
        panel = os.path.join(d, "panel.parquet"); pq.write_table(pa.Table.from_pandas(df, preserve_index=False), panel)
        mem = os.path.join(d, "memory")
        r = _run(["-c", KNOWN_RUNNER, HERE, kind, panel, mem, json.dumps(MODELS), json.dumps({str(k): v for k, v in coh.items()})],
                 env={"REWARD_PREBUILT_MODE": "off", "REWARD_FORCE_OUT_OF_CORE": None})
        sm = _status(r)
        if "@@DONE@@" not in r.stdout or any(s["status"] != "ok" or s["error"] for s in sm):
            rows.append({"check": f"known answers: {kind}", "engine": "memory", "files": 0, "differences": 1, "verdict": "FAILED",
                         "detail": (r.stdout + r.stderr)[-300:]}); continue
        for e in engines:
            out = os.path.join(d, f"ooc_{e}")
            t0 = time.time()
            r = _run(["-c", KNOWN_RUNNER, HERE, kind, panel, out, json.dumps(MODELS), json.dumps({str(k): v for k, v in coh.items()})],
                     env={"REWARD_PREBUILT_MODE": "off", "REWARD_FORCE_OUT_OF_CORE": e, "REWARD_OOC_PARTITIONS": "5"})
            st = _status(r)
            ran = "@@DONE@@" in r.stdout and all(s["status"] == "ok" and not s["error"] and s["out_of_core"] for s in st) and len(st) == len(MODELS)
            n, diffs = compare(mem, out) if ran else (0, [f"the out-of-core run failed: {(r.stdout + r.stderr)[-300:]}"])
            rows.append({"check": f"known answers: {kind}", "engine": e, "files": n, "differences": len(diffs),
                         "verdict": "IDENTICAL" if ran and not diffs else "FAILED", "detail": "; ".join(diffs[:3]) or f"{time.time() - t0:.0f} s, 5 pixel partitions"})
            print(f"[{'OK' if rows[-1]['verdict'] == 'IDENTICAL' else 'FAILED'}]  known {kind} {e}: {n} files, {len(diffs)} differences", flush=True)


def check_layout(base, engines, rows):
    import validate_location_poison as VP
    res = {}
    for key, poison in (("clean", False), ("poison", True)):
        root = os.path.join(base, f"layout_{key}"); fund = VP.make_exports(root, poison)
        env = {"REWARD_INPUT_DIR": root, "REWARD_FUND_PATH": fund, "REWARD_OUTCOME": "NDVI", "REWARD_PREBUILT_MODE": "off", "REWARD_FORCE_OUT_OF_CORE": None}
        nb = sorted(glob.glob(os.path.join(HERE, "01_Panel_Preparation", "P00_*.ipynb")))[0]
        r = _run(["-c", VP.NB_RUNNER, nb], env=env, cwd=os.path.dirname(nb), timeout=3600)
        if "@@DONE@@" not in r.stdout:
            rows.append({"check": f"your layout ({key}): P00", "engine": "", "files": 0, "differences": 1, "verdict": "FAILED", "detail": (r.stdout + r.stderr)[-300:]}); return
        results = os.path.join(root, VP._out_sub(), "results")
        modes = (["memory"] + list(engines)) if key == "clean" else [engines[0]]
        for mode in modes:
            logs = os.path.join(base, f"layout_{key}_{mode}_logs"); os.makedirs(logs, exist_ok=True)
            e2 = dict(env)
            if mode != "memory": e2.update({"REWARD_FORCE_OUT_OF_CORE": mode, "REWARD_OOC_PARTITIONS": "6"})
            r = _run(["-c", VP.MODELS_RUNNER, HERE, logs, json.dumps(MODELS), json.dumps(VP.SETTINGS)], env=e2)
            st = _status(r)
            dst = os.path.join(base, f"layout_{key}_{mode}")
            if os.path.isdir(results): shutil.move(results, dst)
            ok_ = "@@MODELS_DONE@@" in r.stdout and all(s["status"] == "ok" and not s["error"] for s in st) and len(st) == len(MODELS)
            res[(key, mode)] = dst if ok_ else None
            if not ok_:
                rows.append({"check": f"your layout ({key})", "engine": mode, "files": 0, "differences": 1, "verdict": "FAILED", "detail": (r.stdout + r.stderr)[-300:]})
    mem = res.get(("clean", "memory"))
    for e in engines:
        if mem and res.get(("clean", e)):
            n, diffs = compare(mem, res[("clean", e)])
            rows.append({"check": "your layout: fund timing, location rule, fragments, overlaps", "engine": e, "files": n, "differences": len(diffs),
                         "verdict": "IDENTICAL" if not diffs else "FAILED", "detail": "; ".join(diffs[:3]) or "6 pixel partitions"})
            print(f"[{'OK' if not diffs else 'FAILED'}]  layout {e}: {n} files, {len(diffs)} differences", flush=True)
    if res.get(("clean", engines[0])) and res.get(("poison", engines[0])):
        n, diffs = compare(res[("clean", engines[0])], res[("poison", engines[0])], numbers_only=True)   # the file names differ by construction
        rows.append({"check": "your layout POISONED, out of core (every excluded row +5): the clean numbers", "engine": engines[0], "files": n,
                     "differences": len(diffs), "verdict": "IDENTICAL" if not diffs else "FAILED", "detail": "; ".join(diffs[:3]) or "no excluded row reaches any model"})
        print(f"[{'OK' if not diffs else 'FAILED'}]  poisoned out of core: {n} files, {len(diffs)} differences", flush=True)
    return res


def check_p00(base, engines, rows):
    import validate_location_poison as VP, pyarrow.parquet as pq
    root = os.path.join(base, "p00_exports"); fund = VP.make_exports(root, False)
    env = {"REWARD_INPUT_DIR": root, "REWARD_FUND_PATH": fund, "REWARD_FORCE_OUT_OF_CORE": None}
    outs = {}
    for mode in ["memory"] + list(engines):
        out = os.path.join(base, f"p00_{mode}"); os.makedirs(out, exist_ok=True)
        e2 = dict(env)
        if mode != "memory": e2.update({"REWARD_FORCE_OUT_OF_CORE": mode, "REWARD_OOC_PARTITIONS": "3"})
        r = _run(["-c", P00_RUNNER, HERE, out], env=e2, timeout=3600)
        if "@@DONE@@" not in r.stdout:
            rows.append({"check": "P00 PASS A + PASS B, every block out of core", "engine": mode, "files": 0, "differences": 1, "verdict": "FAILED",
                         "detail": (r.stdout + r.stderr)[-300:]}); continue
        info = json.loads([l for l in r.stdout.splitlines() if l.startswith('{"panel"')][-1])
        outs[mode] = (info["panel"], out, "OUT OF CORE" in r.stdout)
    if "memory" not in outs: return
    t0 = pq.read_table(outs["memory"][0])
    for e in engines:
        if e not in outs: continue
        t1 = pq.read_table(outs[e][0])
        same = t0.schema.equals(t1.schema) and t0.num_rows == t1.num_rows and t0.equals(t1)
        det = []
        if not same:
            if t0.num_rows != t1.num_rows: det.append(f"{t0.num_rows:,} vs {t1.num_rows:,} rows")
            else:
                for c in t0.column_names:
                    if c not in t1.column_names or not t0[c].equals(t1[c]): det.append(f"column {c} differs"); break
        for rep in ("panel_design_check.csv", "panel_missingness_report.csv", "panel_balance_by_block.csv"):
            a_, b_ = os.path.join(outs["memory"][1], rep), os.path.join(outs[e][1], rep)
            if os.path.exists(a_) and os.path.exists(b_):
                x = pd.read_csv(a_); y = pd.read_csv(b_); keys = [c for c in x.columns if x[c].dtype == object or c in ("Year",)]
                x = x.sort_values(list(x.columns)).reset_index(drop=True); y = y.sort_values(list(y.columns)).reset_index(drop=True)
                if not x.equals(y): det.append(f"{rep} differs")
        rows.append({"check": "P00 PASS A + PASS B, every block out of core (pixel-range pieces)", "engine": e, "files": 1 + 3, "differences": len(det),
                     "verdict": "IDENTICAL" if not det and outs[e][2] else "FAILED",
                     "detail": "; ".join(det) or (f"the same panel: {t0.num_rows:,} rows x {t0.num_columns} columns, row for row" if outs[e][2] else "the out-of-core path did not run")})
        print(f"[{'OK' if rows[-1]['verdict'] == 'IDENTICAL' else 'FAILED'}]  P00 {e}: {rows[-1]['detail']}", flush=True)


def check_switch(base, rows):
    """The model's need above a (checks-only) RAM budget: run_mode must choose out of core by itself; the numbers must be the in-memory ones."""
    import validate_known_answers as KA, pyarrow as pa, pyarrow.parquet as pq
    df, coh = KA.make_panel("staggered")
    d = os.path.join(base, "switch"); os.makedirs(d, exist_ok=True)
    panel = os.path.join(d, "panel.parquet"); pq.write_table(pa.Table.from_pandas(df, preserve_index=False), panel)
    mem, ooc = os.path.join(d, "memory"), os.path.join(d, "budget")
    cj = json.dumps({str(k): v for k, v in coh.items()})
    r1 = _run(["-c", KNOWN_RUNNER, HERE, "staggered", panel, mem, json.dumps(["M01"]), cj], env={"REWARD_PREBUILT_MODE": "off", "REWARD_FORCE_OUT_OF_CORE": None})
    r2 = _run(["-c", KNOWN_RUNNER, HERE, "staggered", panel, ooc, json.dumps(["M01"]), cj],
              env={"REWARD_PREBUILT_MODE": "off", "REWARD_FORCE_OUT_OF_CORE": None, "REWARD_RAM_BUDGET_BYTES": str(12_000_000)})
    s2 = _status(r2)
    chose = bool(s2) and s2[0].get("out_of_core")
    n, diffs = compare(mem, ooc, ["M01"]) if chose else (0, ["run_mode did NOT switch to out of core under a budget below the need"])
    rows.append({"check": "the switch at 98 %: a budget below the need -> out of core by itself (M01)", "engine": "first available", "files": n,
                 "differences": len(diffs), "verdict": "IDENTICAL" if chose and not diffs else "FAILED", "detail": "; ".join(diffs[:3]) or "run_mode -> out_of_core; the in-memory numbers"})
    print(f"[{'OK' if rows[-1]['verdict'] == 'IDENTICAL' else 'FAILED'}]  switch: {rows[-1]['detail']}", flush=True)


STREAM_RUNNER = r'''
import sys, os, json
eng, panel = sys.argv[1], sys.argv[2]
sys.path.insert(0, eng); os.chdir(eng)
import _common as C
C.PREPARED_PANEL = panel
cf = C._location_cache_file(panel)
if os.path.exists(cf): os.remove(cf)
t = C.location_table(panel)
idc = os.path.join(os.path.dirname(panel), "OUTCOME_IDENTITIES.json")
if os.path.exists(idc): os.remove(idc)
C._IDENT_CACHE.clear(); C.RESULTS_ROOT = os.path.join(os.path.dirname(panel), "results_stream_" + sys.argv[3])
ids = C.outcome_identities(verbose=False)
print("@@OUT@@" + json.dumps({"own": {str(k): v for k, v in t["own"].items()}, "bsc": sorted(t["by_site_check"]), "rc": sorted(list(x) for x in t["ring_conflict"]),
                             "nd": sorted([int(a), int(b)] for a, b in t["near_dup"].items()), "npx": t["n_pixels"], "npairs": t["n_pairs"],
                             "ids": ids.values.tolist()}))
'''


def check_streaming(base, rows, layout_res):
    root = os.path.join(base, "layout_clean")
    import validate_location_poison as VP
    panel = os.path.join(root, VP._out_sub(), "did_panel_full.parquet")
    if not os.path.exists(panel):
        rows.append({"check": "streaming: location table + outcome identities", "engine": "", "files": 0, "differences": 1, "verdict": "FAILED",
                     "detail": "no panel (the layout check did not run)"}); return
    out = {}
    for mode in ("whole", "stream"):
        r = _run(["-c", STREAM_RUNNER, HERE, panel, mode], env={"REWARD_FORCE_OUT_OF_CORE": "batches" if mode == "stream" else None})
        got = [l for l in r.stdout.splitlines() if l.startswith("@@OUT@@")]
        out[mode] = json.loads(got[-1][7:]) if got else None
    a, b = out["whole"], out["stream"]
    det = []
    if a is None or b is None: det.append("a run failed")
    else:
        for k in ("own", "bsc", "rc", "nd", "npx", "npairs"):
            if a[k] != b[k]: det.append(f"location table: {k} differs")
        if len(a["ids"]) != len(b["ids"]) or any(x[0] != y[0] or x[1] != y[1] or abs(x[2] - y[2]) > 1e-9 or abs(x[3] - y[3]) > 1e-7 * max(1, abs(x[3]))
                                                   or abs(x[4] - y[4]) > 1e-7 * max(1, abs(x[4])) or x[5] != y[5] for x, y in zip(a["ids"], b["ids"])):
            det.append(f"outcome identities differ: {a['ids']} vs {b['ids']}")
    rows.append({"check": "streaming (row group by row group): the location table and the outcome identities", "engine": "batches", "files": 2,
                 "differences": len(det), "verdict": "IDENTICAL" if not det else "FAILED",
                 "detail": "; ".join(det) or f"{len(a['ids'])} identities, {a['npairs']} near-duplicate pairs, {len(a['rc'])} ring conflicts -- the same"})
    print(f"[{'OK' if not det else 'FAILED'}]  streaming: {rows[-1]['detail']}", flush=True)


def main(argv):
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else {"known", "layout", "p00", "switch", "streaming"}
    want = argv[argv.index("--engines") + 1].split(",") if "--engines" in argv else ENGINES
    av = engines_available(want)
    engines = [e for e in want if av[e][0]]
    rows = [{"check": "engine available", "engine": e, "files": 0, "differences": 0, "verdict": "AVAILABLE" if ok else "NOT AVAILABLE", "detail": why}
            for e, (ok, why) in av.items()]
    base = tempfile.mkdtemp(prefix="reward_ooc_"); print(f"[INFO]    working in {base}; engines: {engines}", flush=True)
    t0 = time.time()
    if "known" in only: check_known(base, engines, rows)
    lay = check_layout(base, engines, rows) if ("layout" in only or "streaming" in only) and engines else None
    if "p00" in only and engines: check_p00(base, engines, rows)
    if "switch" in only: check_switch(base, rows)
    if "streaming" in only: check_streaming(base, rows, lay)
    t = pd.DataFrame(rows)
    out = os.path.join(HERE, "VALIDATION_OUT_OF_CORE.csv"); t.to_csv(out, index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 110)
    print(t.to_string(index=False))
    bad = t[t.verdict == "FAILED"]; na = t[t.verdict == "NOT AVAILABLE"]
    print(f"report -> {out} ({(time.time() - t0) / 60:.1f} min)")
    print((f"CLEAN: the out-of-core path gives the in-memory numbers everywhere ({int((t.verdict == 'IDENTICAL').sum())} checks IDENTICAL)"
           + (f"; NOT AVAILABLE here: {', '.join(na.engine)} (the fall-back order goes on to the next engine)" if len(na) else ""))
          if not len(bad) else f"{len(bad)} PROBLEM(S): " + "; ".join(f"{r.check} [{r.engine}]: {r.detail[:120]}" for r in bad.itertuples()))
    return 1 if len(bad) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
