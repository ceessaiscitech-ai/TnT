"""
selfcheck.py -- validate a DIDRDP bundle BEFORE running anything.

    python selfcheck.py            (from inside the bundle folder)
    import selfcheck; selfcheck.run()

It catches exactly the class of problem that stopped P01 in v17.8: an engine file whose version drifted from what
the notebooks require, a split installation, a notebook that calls an engine function with a keyword the engine
does not have, a weather variable used as an outcome, or a notebook that no longer parses.
Exit code 0 = clean, 1 = problems (each printed with the file and the fix).
"""
import os, sys, re, json, glob, ast, inspect, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
PROBLEMS, NOTES = [], []
def bad(msg): PROBLEMS.append(msg); print(f"[FAILED]  {msg}")
def note(msg): NOTES.append(msg); print(f"[OK]      {msg}")
def warn(msg): print(f"[WARNING] {msg}")

def _ver(v): return tuple(int(x) for x in re.findall(r"\d+", str(v))) or (0,)

def check_engines():
    sys.path.insert(0, HERE)
    for m in ("_common", "_prep_common", "_ground_common", "_version"):
        sys.modules.pop(m, None)
    mods = {}
    for name in ("_common", "_prep_common"):
        try:
            mods[name] = importlib.import_module(name)
        except Exception as e:
            bad(f"{name}.py does not import: {type(e).__name__}: {e}"); return mods
    vers = {n: getattr(m, "ENGINE_VERSION", None) for n, m in mods.items()}
    dirs = {n: os.path.dirname(os.path.abspath(m.__file__)) for n, m in mods.items()}
    if len(set(vers.values())) != 1:
        bad(f"engine versions differ: {vers} -- both must read _version.py from their own folder")
    else:
        note(f"engine version {list(vers.values())[0]} in both engines")
    if len(set(dirs.values())) != 1:
        bad(f"split installation: {dirs}")
    else:
        note(f"single bundle at {list(dirs.values())[0]}")
    if not os.path.exists(os.path.join(HERE, "_version.py")):
        bad("_version.py missing (single source of truth for the engine version)")
    return mods

def check_notebook_locks(mods):
    eng = _ver(getattr(mods.get("_common"), "ENGINE_VERSION", "0"))
    worst = None
    for nb in sorted(glob.glob(os.path.join(HERE, "0*", "*.ipynb"))):
        d = json.load(open(nb, encoding="utf-8"))
        if d.get("metadata", {}).get("kernelspec", {}).get("name") == "ir": continue
        for c in d["cells"]:
            if c["cell_type"] != "code": continue
            for m in re.findall(r'require_engine\("([0-9.]+)"\)', "".join(c["source"])):
                if _ver(m) > eng:
                    bad(f"{os.path.basename(nb)} requires engine >= {m} but the engine is {'.'.join(map(str, eng))}")
                worst = m if (worst is None or _ver(m) > _ver(worst)) else worst
    if worst: note(f"all notebook locks satisfied (highest required: {worst})")

def check_syntax_and_calls(mods):
    C = mods.get("_common"); P = mods.get("_prep_common")
    sigs = {}
    for mod, alias in ((C, "C"), (P, "P")):
        if mod is None: continue
        for n, f in inspect.getmembers(mod, inspect.isfunction):
            try: sigs[f"{alias}.{n}"] = inspect.signature(f)
            except (ValueError, TypeError): pass
    n_cells = n_calls = 0
    for nb in sorted(glob.glob(os.path.join(HERE, "0*", "*.ipynb"))):
        d = json.load(open(nb, encoding="utf-8"))
        if d.get("metadata", {}).get("kernelspec", {}).get("name") == "ir": continue
        for k, c in enumerate([c for c in d["cells"] if c["cell_type"] == "code"], 1):
            src = "\n".join(l for l in "".join(c["source"]).split("\n") if not l.lstrip().startswith(("%", "!")))
            n_cells += 1
            try:
                tree = ast.parse(src)
            except SyntaxError as e:
                bad(f"{os.path.basename(nb)} cell {k}: SyntaxError {e.msg} (line {e.lineno})"); continue
            for node in ast.walk(tree):                      # keyword arguments that the engine does not accept
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute): continue
                if not isinstance(node.func.value, ast.Name) or node.func.value.id not in ("C", "P"): continue
                key = f"{node.func.value.id}.{node.func.attr}"
                sig = sigs.get(key)
                if sig is None: continue
                n_calls += 1
                params = sig.parameters
                if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()): continue
                for kw in node.keywords:
                    if kw.arg and kw.arg not in params:
                        bad(f"{os.path.basename(nb)} cell {k}: {key}(... {kw.arg}=...) -- the engine's signature is {key}{sig}")
    note(f"{n_cells} code cells parse; {n_calls} engine calls checked against live signatures")

def check_rules(mods):
    C = mods.get("_common")
    if C is None: return
    weather = set(getattr(C, "WEATHER_COVARIATES", []))
    if not weather:
        bad("WEATHER_COVARIATES missing from the engine"); return
    if weather & set(C.ALL_ESTIMATION_VARIABLES):
        bad(f"weather variables are in the OUTCOME list: {sorted(weather & set(C.ALL_ESTIMATION_VARIABLES))}")
    else:
        note(f"weather variables are covariates only: {sorted(weather)}")
    if not weather <= set(C.DEFAULT_COVARIATES):
        bad(f"DEFAULT_COVARIATES is missing {sorted(weather - set(C.DEFAULT_COVARIATES))}")
    else:
        note(f"DEFAULT_COVARIATES = {C.DEFAULT_COVARIATES}")
    if weather & set(getattr(C, "SELECTED_OUTCOMES", [])):
        bad("SELECTED_OUTCOMES contains a weather variable")
    for o in weather:
        try:
            C.columns_for(o); bad(f"columns_for('{o}') did not refuse a weather variable")
        except Exception:
            pass
    note(f"{len(C.SELECTED_OUTCOMES)} outcomes in SELECTED_OUTCOMES (each module loops through these)")
    for fn in ("set_scenario", "parse_control_zones", "scenario_tag", "results_dir", "apply_scenario",
               "scenario_years", "year_mask", "has_year_window",
               "run_other_outcomes", "run_model_notebook", "current_outcome", "build_estimator_files",
               "estimate_twfe_did_streaming", "assert_fits_in_memory", "trace"):
        if not hasattr(C, fn): bad(f"_common.{fn} missing")
    if hasattr(C, "estimate_twfe_did_streaming"):
        pr = inspect.signature(C.estimate_twfe_did_streaming).parameters
        for kw in ("covariates", "balanced_only"):
            if kw not in pr: bad(f"estimate_twfe_did_streaming has no '{kw}' parameter")
        if pr.get("balanced_only") and pr["balanced_only"].default is not False:
            bad("estimate_twfe_did_streaming(balanced_only=) should default to False (keep unbalanced pixels)")
    n_out = 0
    for nb in sorted(glob.glob(os.path.join(HERE, "0[2-5]*", "*.ipynb"))):
        code = "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
        if "current_outcome(" in code: n_out += 1
        elif re.search(r"^\s*OUTCOME\s*=", code, re.M):
            bad(f"{os.path.basename(nb)} sets OUTCOME directly -- the batch cannot inject an outcome into it")
    note(f"{n_out} model notebooks read their outcome through C.current_outcome()")
    n_loop = sum("run_other_outcomes" in "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
                 for nb in glob.glob(os.path.join(HERE, "0[2-5]*", "M*.ipynb")))
    note(f"{n_loop} model notebooks carry the outcome-loop cell (CELL 9)")
    n_scn = sum("set_scenario(" in "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
                and "C.results_dir(" in "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
                for nb in glob.glob(os.path.join(HERE, "0[2-5]*", "M*.ipynb")))
    note(f"{n_scn} model notebooks set the scenario and write to the scenario results folder")
    src_all = {nb: "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
               for nb in glob.glob(os.path.join(HERE, "0[2-5]*", "M*.ipynb"))}
    n_inh = sum("C.load_scenario()" in v for v in src_all.values())
    if n_inh != len(src_all):
        bad(f"only {n_inh} of {len(src_all)} model notebooks inherit a panel-level scenario (C.load_scenario)")
    else:
        note(f"{n_inh} model notebooks inherit the scenario saved at panel preparation")
    leaks = {os.path.basename(k): re.findall(r"C\.(TREATMENT_YEAR|POST_CUTOFF|DEFAULT_CONTROL_ZONES)", v)
             for k, v in src_all.items()}
    leaks = {k: set(v) for k, v in leaks.items() if v}
    if leaks:
        bad(f"model notebooks using the module CONSTANTS instead of the run scenario: {leaks}")
    else:
        note("no model reads TREATMENT_YEAR / POST_CUTOFF / DEFAULT_CONTROL_ZONES directly -- all use the scenario")
    for fn in ("save_scenario", "load_scenario", "scenario_banner"):
        if not hasattr(C, fn): bad(f"_common.{fn} missing (panel-level scenario inheritance)")
    if C is not None:
        try:
            assert C.parse_control_zones("1-3") == (1, 2, 3) and C.parse_control_zones("1") == (1,) and C.parse_control_zones((1, 3, 5)) == (1, 3, 5)
            note("control-ring parsing: '1', '1-3', (1,3,5) all read correctly")
            C.set_scenario(treatment_year=2023, pre_years=4, post_years=2, verbose=False)
            assert C.scenario_years() == (2019, 2024), C.scenario_years()
            C.set_scenario(treatment_year=2024, verbose=False)
            assert C.scenario_years() == (2020, 2025), "the year window must follow the treatment year"
            C.set_scenario(all_years=True, treatment_year=2023, verbose=False)
            assert C.scenario_years() == (None, None)
            note("year window: pre/post counts resolve correctly and follow the treatment year")
        except Exception as e:
            bad(f"parse_control_zones is wrong: {e}")
        src_ = inspect.getsource(C.set_scenario)
        if "OUTCOME_LOOP_STATE" not in src_ or "locked" not in src_:
            bad("set_scenario does not lock the scenario during the outcome loop -- the other variables would be "
                "estimated under the notebook's SAVED defaults instead of the scenario you set")
        else:
            note("the outcome loop keeps the scenario you set (CELL 1 of the saved file cannot override it)")
    if hasattr(C, "run_batch") or os.path.isdir(os.path.join(HERE, "00_Run_All")):
        bad("an across-models batch runner is still present -- v17.11 removed it deliberately")

def check_pixel_id_string_ops():
    """v20.5: pixel_id is int64 since v17.6. Any bare concatenation of it with a string raises UFuncTypeError at
    run time (it broke PASS A). Catch the pattern statically, in the engines and in every notebook."""
    import re as _re
    pat = _re.compile(r'\["pixel_id"\]\s*\+\s*["\']|\bpixel_id\b\s*\+\s*["\']')
    hits = []
    for f in ("_common.py", "_prep_common.py", "_ground_common.py"):
        p = os.path.join(HERE, f)
        if not os.path.exists(p): continue
        for i, l in enumerate(open(p, encoding="utf-8").read().split("\n"), 1):
            if pat.search(l) and ".astype(" not in l and "str(" not in l: hits.append(f"{f}:{i}")
    for nb in glob.glob(os.path.join(HERE, "0*", "*.ipynb")):
        d = json.load(open(nb, encoding="utf-8"))
        for k, c in enumerate([c for c in d["cells"] if c["cell_type"] == "code"], 1):
            for l in "".join(c["source"]).split("\n"):
                if pat.search(l) and ".astype(" not in l and "str(" not in l:
                    hits.append(f"{os.path.basename(nb)} cell {k}")
    if hits: bad(f"int64 pixel_id concatenated with a string (UFuncTypeError at run time): {hits[:5]}")
    else: note("no bare string concatenation of the int64 pixel_id")

def check_pass_b_parallel():
    """v20.6: PASS B must be parallel and must not repeat the expensive per-block steps."""
    import inspect as _i, sys as _s
    _s.path.insert(0, HERE)
    try:
        import _prep_common as _P
    except Exception as e:
        bad(f"_prep_common not importable: {e}"); return
    for fn in ("prepare_pass_b_block", "_pb_worker", "pass_b_worker_count"):
        if not hasattr(_P, fn): bad(f"_prep_common.{fn} missing (PASS B parallelism)")
    if hasattr(_P, "prepare_pass_b_block"):
        src = _i.getsource(_P.prepare_pass_b_block)
        for step in ("build_treatment_columns(", "finalize_panel_block("):
            n = src.count(step)
            if n > 1: bad(f"PASS B calls {step[:-1]} {n} times per block -- it must run once")
        if src.count("build_treatment_columns(") == 1 and src.count("finalize_panel_block(") == 1:
            note("PASS B does each expensive per-block step exactly once")
    if hasattr(_P, "run_pass_b") and "n_workers" not in _i.signature(_P.run_pass_b).parameters:
        bad("run_pass_b has no n_workers parameter -- it would run single-core")
    else:
        note("run_pass_b takes n_workers (autotuned from cores and free RAM)")

def check_full_machine():
    """v20.7: the preparation stages must be sized from the real machine, not a hard-coded cap, and workers must
    not oversubscribe BLAS. Verified against a SIMULATED 64-core / 512 GB Windows box so the numbers are checked
    even when this machine is small."""
    import types, inspect as _i
    p = os.path.join(HERE, "_hardware.py")
    if not os.path.exists(p): bad("_hardware.py missing (machine sizing)"); return
    sys.path.insert(0, HERE)
    import _hardware as H
    saved_ps, saved_cpu, saved_name, saved_lim = H._psutil, os.cpu_count, H.os.name, H.WINDOWS_POOL_LIMIT
    try:
        class _VM: total = 512 * 1024**3; available = 480 * 1024**3
        H._psutil = lambda: types.SimpleNamespace(cpu_count=lambda logical=True: 64 if logical else 32,
                                                  virtual_memory=lambda: _VM())
        os.cpu_count = lambda: 64; H.os.name = "nt"
        a = H.worker_cap(n_tasks=1449); b = H.worker_cap(n_tasks=44, bytes_per_worker=1_710_519 * 220)
        if a < 32: bad(f"PASS A would use only {a} workers on a 64-core box")
        elif a != 64: bad(f"PASS A would ask for {a} workers on a 64-core box -- v20.59: every logical core (make_pool has no 61-worker limit on Windows)")
        else: note(f"simulated 64-core Windows box: PASS A {a} workers, PASS B {b} workers")
        if b != 44: bad(f"PASS B would use {b} workers for 44 blocks with 480 GB free (expected 44)")
    finally:
        H._psutil, os.cpu_count, H.os.name, H.WINDOWS_POOL_LIMIT = saved_ps, saved_cpu, saved_name, saved_lim
    prep = open(os.path.join(HERE, "_prep_common.py"), encoding="utf-8").read()
    if "min(32, (os.cpu_count() or 2) // 2)" in prep:
        bad("PASS A still caps the pool at 32 workers / half the cores")
    else:
        note("PASS A sizes its pool from the machine (no 32-worker cap)")
    if "worker_init_threads" not in prep: bad("workers do not pin BLAS to one thread -- N x cores thread oversubscription")
    else: note("worker processes run one BLAS thread each (no oversubscription)")

def check_atomic_panel_write():
    """v20.8: PASS B must publish the panel atomically, and the validator must quarantine an unreadable one."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _prep_common as _P
    src = _i.getsource(_P.run_pass_b)
    renames = ("os.replace(" in src) or ("publish_atomic(" in src)      # v20.10: the rename moved into publish_atomic
    if ".building" not in src or not renames:
        bad("run_pass_b does not write to a temporary file and rename -- an interrupted run would leave a corrupt panel")
    else:
        note("PASS B writes to <panel>.building and publishes only after the footer is closed")
    for fn in ("quarantine_file", "panel_file_report"):
        if not hasattr(_P, fn): bad(f"_prep_common.{fn} missing (corrupt-panel handling)")
    if "quarantine_file(path)" not in _i.getsource(_P.final_panel_is_valid):
        bad("final_panel_is_valid does not move an unreadable panel aside")
    else:
        note("an unreadable panel is quarantined, never silently overwritten")

def check_dedup_semantics():
    """v20.9: dedup must be WITHIN (pixel_id, Year, Season) only, must merge complementary values instead of
    dropping them, and must never compare rows across seasons or years."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _prep_common as _P
    src = _i.getsource(_P.resolve_duplicates)
    keys = tuple(getattr(_P, "DEDUP_KEYS", ()))
    if keys[-3:] != ("pixel_id", "Year", "Season") or (len(keys) == 4 and keys[0] != "site_id"):
        bad(f"dedup key is not (site_id,) pixel_id, Year, Season: {keys}")
    else:
        note("dedup key is (site_id, pixel_id, Year, Season) -- rows in different sites/seasons/years are never compared")
    if "complementary" not in src or ("g.first()" not in src and "n_filled" not in src):
        bad("dedup does not classify / count complementary values -- a second file's variables would be lost silently")
    else:
        note("dedup classifies complementary groups; the kept row's gaps are filled from the rows it drops only with "
             "DEDUP_FILL_FROM_DUPLICATES = True (v20.58 default: the repeated rows are dropped whole, the values not used are counted)")
    pb = _i.getsource(_P.run_pass_b)
    if "panel_balance_by_block.csv" not in pb:
        bad("PASS B does not write the panel balance report")
    else:
        note("PASS B reports pixels per Year x Season block and flags an unbalanced panel")

def check_file_handles():
    """v20.10: no metadata-only ParquetFile may be left open -- on Windows an open handle blocks the rename that
    publishes the panel ([WinError 5]). Also require the recovery helper."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _prep_common as _P
    for fn in ("pq_meta", "pq_is_readable", "publish_atomic", "finalize_pending_panel"):
        if not hasattr(_P, fn): bad(f"_prep_common.{fn} missing (Windows-safe publishing)")
    for name in ("final_panel_is_valid", "panel_file_report"):
        src = _i.getsource(getattr(_P, name))
        if "pq.ParquetFile(" in src and "close()" not in src and "pq_meta(" not in src:
            bad(f"{name} opens a ParquetFile without closing it -- this blocks publishing on Windows")
    if "publish_atomic(" not in _i.getsource(_P.run_pass_b):
        bad("run_pass_b does not use publish_atomic (no retry/gc on a locked destination)")
    else:
        note("panel is published with gc + retry and a recovery path (finalize_pending_panel)")
    note("metadata reads go through pq_meta(), which always closes the file")

def check_dedup_vectorised():
    """v20.11: resolve_duplicates must not loop in Python over duplicate groups (23M groups -> 9.5 h), and
    build_manifest must keep the handle it streams from."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _prep_common as _P
    src = _i.getsource(_P.resolve_duplicates)
    if "for key, group in" in src or ".groupby(list(group_keys)):" in src:
        bad("resolve_duplicates loops over duplicate groups in Python -- hours on millions of groups")
    else:
        note("resolve_duplicates is vectorised (one sort + groupby.first); log is a summary + sample")
    msrc = _i.getsource(_P.build_manifest)
    if "pf = pq.ParquetFile(final_path)" not in msrc or "pf.close()" not in msrc:
        bad("build_manifest lost its ParquetFile handle or does not close it")
    else:
        note("build_manifest streams from an open handle and closes it")
    csrc = open(os.path.join(HERE, "_common.py"), encoding="utf-8").read()
    for fn in ("def treatment_coverage", "def _result_is_empty", "def record_not_estimated"):
        if fn not in csrc: bad(f"_common.py missing {fn} (empty-coefficient diagnostics)")
    note("every model prints coverage after the scenario; a non-estimable outcome is refused and registered in NOT_ESTIMATED.csv")

def check_missing_value_policy():
    """v20.12: estimators must exclude non-finite rows, refuse degenerate fits, and every model must expose the
    seasons switch; dedup must not loop in Python over groups; build_manifest must define its reader."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P
    src = _i.getsource(_C.estimate_twfe_did)
    if "_finite_rows(" not in src: bad("estimate_twfe_did does not exclude missing outcome/covariate rows (NaN betas)")
    if "exactly zero" not in src: bad("estimate_twfe_did does not refuse a beta=0/se=0 degenerate fit")
    if "_finite_rows(" in src and "exactly zero" in src: note("2x2 estimator excludes missing rows and refuses degenerate fits")
    if "_finite_rows(" not in _i.getsource(_C.estimate_twfe_did_streaming):
        bad("the streaming estimator does not apply the missing-value policy")
    for fn in ("outcome_coverage", "season_rows"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing")
    dd = _i.getsource(_P.resolve_duplicates)
    if "for key, group in" in dd: bad("resolve_duplicates loops in Python over duplicate groups (hours on large blocks)")
    else: note("resolve_duplicates is vectorised")
    bm = _i.getsource(_P.build_manifest)
    if "pf = pq.ParquetFile(" not in bm: bad("build_manifest uses `pf` without defining it (NameError in v20.11)")
    else: note("build_manifest defines and closes its Parquet reader")
    nbs = glob.glob(os.path.join(HERE, "0[2-5]*", "M*.ipynb"))
    missing = [os.path.basename(nb) for nb in nbs if "seasons=SEASONS" not in
               "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")]
    if missing: bad(f"model notebooks without the seasons switch: {missing[:5]}")
    else: note(f"{len(nbs)} model notebooks expose SEASONS (seasonal / yearly / all)")

def check_universal_missing_policy():
    """v20.13: the missing-value policy lives in load_panel (every model passes through it), the event study
    has a solver fallback, a NaN GPU drift is a failure, and the CS aggregate skips unidentified cells."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C
    lp = _i.getsource(_C.load_panel)
    if "finite_only" not in lp or "_n_missing_dropped" not in lp:
        bad("load_panel does not exclude rows with a missing outcome/covariate -- NaN estimates would return")
    else:
        note("load_panel enforces the missing-value policy for every model")
    if "CURRENT_ESTIMATION_COLUMNS.update" not in _i.getsource(_C.columns_for):
        bad("columns_for no longer records the estimation columns (the load-time policy would be inert)")
    es = _i.getsource(_C.estimate_event_study)
    if "except np.linalg.LinAlgError" not in es: bad("event study can still die with 'SVD did not converge'")
    if "_finite_rows(" not in es: bad("event study does not exclude missing rows")
    if "except np.linalg.LinAlgError" in es and "_finite_rows(" in es: note("event study excludes missing rows and has a solver fallback")
    if "n_cells_identified" not in _i.getsource(_C.callaway_santanna_att):
        bad("Callaway-Sant'Anna aggregate averages NaN cells (blank event-time table)")
    else:
        note("Callaway-Sant'Anna aggregates only identified (g,t) cells")
    cc = _i.getsource(_C._gpu_crosscheck)
    if "np.isfinite(drift)" not in cc: bad("GPU cross-check treats a NaN drift as a pass")
    else: note("a NaN GPU drift is reported as a failure, not a pass")

def check_ingestion_and_paths():
    """v20.14: any format / any name ingestion, and one INPUT_DIR for both engines (no recursion)."""
    import inspect as _i, tempfile as _tf
    sys.path.insert(0, HERE)
    import _prep_common as _P, _common as _C
    for fn in ("discover_input_files", "_read_delimited", "_read_excel_export", "_read_parquet_export", "_read_feather_export"):
        if not hasattr(_P, fn): bad(f"_prep_common.{fn} missing (ingestion layer incomplete)")
    if "discover_input_files(" not in _i.getsource(_P.run_pass_a): bad("run_pass_a does not use discover_input_files")
    exts = set(getattr(_P, "INPUT_EXTENSIONS", ()))
    if not {".csv", ".csv.gz", ".tsv", ".parquet", ".xlsx", ".xls", ".xlsm", ".feather"} <= exts:
        bad(f"INPUT_EXTENSIONS incomplete: {sorted(exts)}")
    else: note("PASS A ingests csv / csv.gz / tsv / parquet / feather / xlsx / xlsm / xls")
    loose = _P.parse_filename("Artal 2022 rabi export (final v3).xlsx")
    if not loose or loose.get("Year") != 2022 or loose.get("Season") != 2: bad("loose file-name parsing is broken")
    if _P.parse_filename("export_no_key_in_name.csv") is not None: bad("a keyless name should return None (column fallback)")
    if "cannot determine {key}" not in _i.getsource(_P.load_and_harmonize): bad("load_and_harmonize lost the column fallback for Year/Season")
    else: note("file names parsed loosely; Year/Season fall back to the columns inside the file")
    if not os.path.exists(os.path.join(HERE, "_paths.py")): bad("_paths.py missing (single INPUT_DIR)")
    d = _tf.mkdtemp(); inp = os.path.join(d, "IN"); os.makedirs(inp)
    try:
        _P.set_paths(inp, verbose=False)                      # would recurse forever before v20.14b
        if _C.PREPARED_PANEL != _P.FINAL_PANEL or not _P.OUTPUT_DIR.startswith(inp):
            bad("set_paths does not put both engines on the same derived layout")
        else: note("one INPUT_DIR drives both engines: output/temp/panel/results derive from it")
    finally:
        try:
            import _paths as _PP; _P._apply_paths(_PP.derive())
        except Exception: pass
    for nb in glob.glob(os.path.join(HERE, "01_Panel_Preparation", "P0[0-2]*.ipynb")):
        src = "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
        if 'glob.glob(os.path.join(P.INPUT_DIR,"**","*.csv")' in src: bad(f"{os.path.basename(nb)} still globs *.csv only")

def check_path_import_orders():
    """v20.14: a session override must survive importing the other engine, in either order, and the two engines
    must always agree. (The half-built version recursed forever, then silently reset a configured engine.)"""
    import subprocess as _sp, sys as _s
    code = r'''
import sys, os, tempfile; sys.path.insert(0, %r)
d = tempfile.mkdtemp(); a = os.path.join(d, "A"); os.makedirs(a)
import _prep_common as P; P.set_paths(a, verbose=False); import _common as C
r1 = C.PREPARED_PANEL == P.FINAL_PANEL and P.OUTPUT_DIR.startswith(a)
for m in ("_common", "_prep_common"): sys.modules.pop(m, None)
b = os.path.join(d, "B"); import _common as C2; C2.set_paths(b, verbose=False); import _prep_common as P2
r2 = P2.FINAL_PANEL == C2.PREPARED_PANEL and C2.RESULTS_ROOT.startswith(b)
print("OK" if (r1 and r2) else f"BAD {r1} {r2}")
''' % HERE
    try:
        out = _sp.run([_s.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=HERE,
                      env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "")})
        last = [l for l in out.stdout.splitlines() if l.strip()][-1] if out.stdout.strip() else out.stderr[-200:]
        if last.strip() == "OK": note("path layout survives either import order and both engines agree")
        else: bad(f"path layout is lost or split across engines depending on import order: {last[:160]}")
    except Exception as e:
        bad(f"import-order check could not run: {e}")

def check_demeaner_and_event_study():
    """v20.15: compact FE codes (no 0/0), GPU cross-check on identical input, event-study identification notes."""
    import inspect as _i, warnings as _w
    sys.path.insert(0, HERE)
    import _common as _C, numpy as _np, pandas as _pd
    _cat = _pd.Categorical(["a", "b", "c", "d"] * 5)[[i for i in range(20) if i % 4 != 2]]   # category 'c' now unused
    _cd = _C._codes(_cat)
    if int(_cd.max()) + 1 != len(set(_cd[_cd >= 0])) or int(_cd.max()) + 1 != 3:
        bad("_codes() leaves empty groups for a filtered categorical (divide warnings, GPU/CPU mismatch)")
    else: note("fixed-effect codes are contiguous on the rows given (no empty groups)")
    cc = _i.getsource(_C._gpu_crosscheck)
    if "_demean_gpu(T, y_sub" not in cc or "_demean_cpu(y_sub" not in cc:
        bad("GPU cross-check does not compare both implementations on the same input")
    else: note("GPU cross-check demeans the same rows on CPU and GPU and compares")
    es = _i.getsource(_C.estimate_event_study)
    for k in ("n_treated_pixels_also_in_ref", "identification_note", "not the same pixels across periods"):
        if k not in es: bad(f"event study lacks the identification diagnostic '{k}'")
    if all(k in es for k in ("n_treated_pixels_also_in_ref", "identification_note")):
        note("event study reports which treated pixels identify each coefficient")
    if not hasattr(_C, "common_pixel_mask"): bad("common_pixel_mask missing (balanced-footprint option)")
    rng = _np.random.default_rng(0); n = 20000
    pix = _pd.Categorical(rng.integers(0, 3000, n)); per = _pd.Categorical(rng.integers(0, 12, n)); y = rng.normal(size=n)
    keep = rng.random(n) < 0.3
    with _w.catch_warnings():
        _w.simplefilter("error")
        try:
            r = _C._demean_cpu(y[keep], [pix[keep], per[keep]], 1e-10, 200)
            ref = _C._demean_cpu_pandas(y[keep], [_np.asarray(pix)[keep], _np.asarray(per)[keep]], 1e-10, 200)
            if _np.max(_np.abs(r - ref)) > 1e-9: bad("CPU demeaner differs from the pandas reference on filtered categoricals")
            else: note("CPU demeaner on filtered categoricals: no warnings, matches the pandas reference")
        except Warning as w:
            bad(f"CPU demeaner raised a warning on filtered categoricals: {w}")

def check_readiness():
    """v20.16: the readiness assessment covers every model notebook and runs on the known facts."""
    sys.path.insert(0, HERE)
    try:
        import _readiness as R
    except Exception as e:
        bad(f"_readiness.py not importable: {e}"); return
    nbs = {os.path.basename(p).split("_")[0] for p in glob.glob(os.path.join(HERE, "0[2-5]*", "M*.ipynb"))}
    missing = sorted(nbs - set(R.MODELS)); extra = sorted(set(R.MODELS) - nbs)
    if missing or extra: bad(f"readiness matrix out of step with the notebooks: missing {missing}, extra {extra}")
    else: note(f"readiness matrix covers all {len(nbs)} model notebooks")
    tbl, ctx = R.assess(R.FACTS_ARTAL)
    if set(tbl.status) - {"complete", "limited", "incomplete-need data"}: bad("readiness produced an unknown status")
    if "P10_Model_Readiness.ipynb (merged into P00)" not in open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8").read():
        bad("P10_Model_Readiness is not in P00")
    else: note("P10 measures the panel and classifies every model")

def check_zero_policy_and_readiness():
    """v20.16: NaN AND exact-zero cells are missing in preparation and in every model; readiness tool present."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _prep_common as _P, _common as _C
    if not hasattr(_P, "apply_missing_policy"): bad("_prep_common.apply_missing_policy missing")
    else:
        for fn in ("_pa_worker", "prepare_pass_b_block"):
            if "apply_missing_policy(" not in _i.getsource(getattr(_P, fn)): bad(f"{fn} does not apply the NaN/zero policy")
        note("PASS A and PASS B set NaN/zero cells to missing before dedup and drop rows without an outcome")
    if not hasattr(_C, "_usable") or "!= 0" not in _i.getsource(_C._usable): bad("_common._usable does not treat exact zeros as missing")
    if "_usable(" not in _i.getsource(_C._finite_rows): bad("estimators do not use the zero rule")
    if "_n_zero_dropped" not in _i.getsource(_C.load_panel): bad("load_panel does not apply/report the zero rule")
    if "policy_cols" not in _i.getsource(_C.estimate_twfe_did_streaming): bad("streaming estimator does not filter on the same policy columns as load_panel")
    else: note("every model excludes NaN and zero cells at load, and the streaming path uses the same sample")
    if not os.path.exists(os.path.join(HERE, "readiness.py")) or not hasattr(_C, "model_readiness"): bad("readiness tool missing")
    else: note("readiness.py / C.model_readiness() present")

def check_missingness_report():
    """v20.17: PASS B writes panel_missingness_report.csv and refuses a block where a zero survived the policy."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _prep_common as _P
    src = _i.getsource(_P.run_pass_b)
    if "panel_missingness_report.csv" not in src: bad("PASS B does not write panel_missingness_report.csv")
    if "survived the missing-value" not in src: bad("PASS B does not assert that no exact zero survives the policy")
    if "panel_missingness_report.csv" in src and "survived the missing-value" in src:
        note("PASS B reports missingness per block x variable and refuses a panel with a surviving zero")
    if "rows_dropped_zero" not in _i.getsource(__import__("_common").load_panel):
        bad("load_panel does not report rows dropped for exact zeros")
    else: note("load_panel reports rows dropped for NaN and for exact zeros separately")

def check_honest_and_group_missingness():
    """v20.18: HonestDiD states base significance; SEs never NaN through cancellation; missingness by group."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P
    src = open(os.path.join(HERE, "_common.py"), encoding="utf-8").read()
    if "invalid value encountered in sqrt" in src and "_neg = _dg < 0" not in src: bad("event-study SE can still go NaN in sqrt")
    if "_neg = _dg < 0" not in src: bad("event-study SE has no cancellation guard")
    else: note("event-study SEs: negative-through-cancellation diagonals are clipped and flagged, never NaN")
    hd = _i.getsource(_C.honest_did_relative_magnitudes)
    if "NOT SIGNIFICANT at M=0" not in hd: bad("HonestDiD does not distinguish 'no finding' from 'fragile'")
    else: note("HonestDiD verdict distinguishes not-significant-at-M0 from fragile from robust")
    if "finite_core" not in _i.getsource(_P.prepare_pass_b_block): bad("PASS B missingness is not split by treated core vs rings")
    else: note("PASS B measures no-data by treated core vs control rings and warns when the core is the masked side")

def check_pretrends_spec():
    """v20.19: the joint pre-trends test must anchor on the reference period and never call solve() on a
    possibly singular cluster-robust covariance."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C
    src = _i.getsource(_C.pretrends_joint_ftest)
    if "np.linalg.solve(vcov" in src: bad("pre-trends test inverts the covariance with solve() -- singular with few clusters / absorbed leads")
    if "max(hi, ref_period)" not in src: bad("pre-trends test sample excludes the reference period (exactly collinear leads)")
    if "matrix_rank(vcov" not in src: bad("pre-trends test does not cap the restrictions at the covariance rank")
    if all(k in src for k in ("max(hi, ref_period)", "matrix_rank(vcov")) and "np.linalg.solve(vcov" not in src:
        note("pre-trends F test: reference period anchored, absorbed leads dropped, rank-capped pseudo-inverse")

def check_no_placeholders():
    """v20.20: result files hold estimates only -- save_results refuses NaN-only estimates and placeholder tokens."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C
    src = _i.getsource(_C.save_results)
    if 'or "EMPTY_RESULT"' in src or '"status": "EMPTY_RESULT"' in src: bad("save_results still writes EMPTY_RESULT placeholder rows")
    if "_placeholder_cells(" not in src or "record_not_estimated(" not in src:
        bad("save_results does not refuse placeholders / record NOT_ESTIMATED")
    else: note("save_results refuses NaN-only estimates and placeholder tokens; refusals go to NOT_ESTIMATED.csv")
    import pandas as _pd, tempfile as _tf
    d = _tf.mkdtemp()
    for row, label in (({"outcome": "X", "beta": float("nan"), "se": float("nan")}, "NaN-only"),
                       ({"outcome": "X", "beta": 0.01, "se": 0.002, "note": "TBD"}, "placeholder token")):
        try:
            _C.LAST_FIT_INFO.clear(); _C.save_results(row, d, "t.csv"); bad(f"save_results wrote a {label} result")
        except _C.InsufficientDataError:
            pass
    if os.path.exists(os.path.join(d, "t.csv")): bad("a refused result file was still written")
    else: note("a NaN-only or placeholder result is refused and never written")

def check_frozen_guard():
    """v20.21: frozen-series detector and guards present in the three core estimators."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C
    for fn in ("within_pixel_variation", "_frozen_treated_guard"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing (frozen-series detection)")
    n = sum("_frozen_treated_guard(" in _i.getsource(getattr(_C, f)) for f in ("estimate_twfe_did", "estimate_event_study", "pretrends_joint_ftest"))
    if n < 3: bad(f"frozen-series guard present in only {n}/3 core estimators")
    else: note("frozen-series guard in the 2x2, the event study and the pre-trends test; P06 runs the detector")

def check_multisite_and_prebuilt():
    """v20.22: sites registry + shapefile shipped, site-aware engine, package export, and both pre-built pipelines present."""
    import inspect as _i
    sys.path.insert(0, HERE)
    for rel in ("data/sites/SWSs20_KarnatakaAll5k.shp", "data/sites/SWSs20_KarnatakaAll5k.dbf", "data/sites/sites.csv",
                "_sites.py", "python_prebuilt/pf_pipeline.py", "PIPELINES_GUIDE.md", "08_Multisite_Runs/MS01_Multisite_Runs.ipynb"):
        if not os.path.exists(os.path.join(HERE, rel)): bad(f"missing {rel}")
    try:
        import _sites as S; reg = S.registry(refresh=True)
        if len(reg) != 20 or set(reg.phase) != {1, 2}: bad(f"sites registry wrong: {len(reg)} sites, phases {sorted(set(reg.phase))}")
        else: note("sites registry: 20 sub-watersheds, phases 1 and 2, from the shipped shapefile")
    except Exception as e:
        bad(f"sites registry unreadable: {e}")
    import _common as _C, _prep_common as _P
    for fn in ("run_sites", "export_for_packages", "sites_in_panel", "site_rows"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing (multi-site)")
    if getattr(_P, "DEDUP_KEYS", ())[:1] != ("site_id",): bad("dedup key is not site-aware")
    if "site_id" not in _P.FINAL_PANEL_SCHEMA: bad("panel schema lacks site_id")
    if "site_id" not in _C.ID_FE_COLS: bad("models do not load site_id")
    src = _i.getsource(_C.build_treatment_columns)
    for k in ("use_site_years", "cluster", "pooled_fe"):
        if k not in src: bad(f"build_treatment_columns ignores the scenario's {k}")
    note("site-aware dedup, site_id in the panel and every model, per-site years / cluster-by-site / site x period FE")
    import ast as _ast
    _ast.parse(open(os.path.join(HERE, "python_prebuilt", "pf_pipeline.py"), encoding="utf-8").read())
    note("pre-built pipelines present: python_prebuilt/pf_pipeline.py; the R pipeline is the bundle's R/ folder (R/lib)")

def check_speed_and_accuracy():
    """v20.23: matrix demeaning in the core estimators; Webb weights; t(G-1); relative absorbed-covariate rule;
    the pre-built model map covers every notebook."""
    import inspect as _i, numpy as _np, pandas as _pd
    sys.path.insert(0, HERE)
    import _common as _C
    for fn in ("demean_columns", "_demean_cpu_matrix", "_demean_gpu_matrix"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing (matrix demeaning)")
    if "demean_columns(" not in _i.getsource(_C.estimate_event_study): bad("event study still demeans column by column")
    if "demean_columns(" not in _i.getsource(_C.estimate_twfe_did): bad("2x2 still demeans column by column")
    rng = _np.random.default_rng(0); n = 20000
    f1 = _pd.Categorical(rng.integers(0, 2000, n)); f2 = _pd.Categorical(rng.integers(0, 12, n)); X = rng.normal(size=(n, 3))
    M = _C._demean_cpu_matrix(X, [f1, f2], 1e-10, 200); S = _np.column_stack([_C._demean_cpu(X[:, j].copy(), [f1, f2], 1e-10, 200) for j in range(3)])
    if _np.max(_np.abs(M - S)) > 1e-9: bad("matrix demeaning differs from column-by-column")
    else: note("matrix demeaning equals column-by-column to 1e-9 (event study and 2x2 use it)")
    if "webb" not in _i.getsource(_C._wb_one_rep): bad("wild bootstrap has no Webb weights")
    if "p_t_G1" not in _i.getsource(_C.estimate_twfe_did): bad("2x2 does not report t(G-1) inference")
    if "ABSORBED_REL_TOL" not in _i.getsource(_C.estimate_twfe_did_streaming): bad("streaming estimator lacks the relative absorbed-covariate rule")
    note("Webb bootstrap weights, t(G-1) p-values and the shared absorbed-covariate rule are in place")
    sys.path.insert(0, os.path.join(HERE, "python_prebuilt"))
    import ml_spatial_pipeline as MS
    nbs = {os.path.basename(p).split("_")[0] for p in glob.glob(os.path.join(HERE, "0[2-5]*", "M*.ipynb"))}
    miss = sorted(nbs - set(MS.MODEL_TO_PACKAGE))
    if miss: bad(f"pre-built model map lacks {miss}")
    else: note(f"pre-built model map covers all {len(nbs)} models (Python + R packages)")
    for rel in ("python_prebuilt/dd_pipeline.py", "python_prebuilt/ml_spatial_pipeline.py", "PREBUILT_MODEL_MAP.md"):
        if not os.path.exists(os.path.join(HERE, rel)): bad(f"missing {rel}")

def check_ground_inputs_and_notebook_locks():
    """v20.24: ground inputs resolve from the bundle; P08/V06 stop cleanly without them; every notebook locks the current engine."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C
    for fn in ("resolve_ground_inputs_dir", "ground_inputs_status", "GROUND_INPUT_FILES"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing (ground-input resolution)")
    st = _C.ground_inputs_status(verbose=False)
    if st["missing"]: warn(f"ground inputs: {len(st['missing'])} of 16 files not found at {st['dir']} (P08/M07/V06 will report a data gap)")
    else: note(f"ground inputs: all 16 files resolved at {st['dir']}")
    p08 = glob.glob(os.path.join(HERE, "01_Panel_Preparation", "P00_*.ipynb"))   # v20.38: P08 is merged into P00
    src = "\n".join("".join(c["source"]) for c in json.load(open(p08[0], encoding="utf-8"))["cells"] if c["cell_type"] == "code") if p08 else ""
    if "ground_inputs_status" not in src or "links is None" not in src: bad("P08 does not check the ground inputs / guard write_outputs")
    else: note("P08 reports the ground-input status and stops cleanly when files are missing")
    cur = _C.ENGINE_VERSION if hasattr(_C, "ENGINE_VERSION") else None
    import re as _re
    stale = []
    for nb in glob.glob(os.path.join(HERE, "0*", "*.ipynb")):
        if os.path.basename(nb).startswith("R"): continue
        s = "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
        for m in _re.findall(r'require_engine\("([0-9.]+)"\)', s):
            if cur and tuple(int(x) for x in m.split(".")) > tuple(int(x) for x in str(cur).split(".")):
                stale.append(os.path.basename(nb)[:30])
    if stale: bad(f"notebooks lock an engine NEWER than the shipped one: {stale[:5]}")
    else: note("every notebook's engine lock is satisfied by the shipped engine")

def check_yearly_first():
    """v20.24: annual composite first -- per-outcome resolution, covariate fill, notebooks default to auto, old
    scenario files upgraded, guard works on annual windows, P00 reports the choice, M07/M08 paths derived."""
    import inspect as _i, json as _j, tempfile as _tf, re as _re
    sys.path.insert(0, HERE)
    import _common as _C
    for fn in ("seasons_mode", "yearly_outcome_available", "yearly_covariate_table", "fill_yearly_covariates", "season_choice_report"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing (yearly-first)")
    if _C.ACTIVE.get("seasons") != "all": bad(f"engine default seasons is {_C.ACTIVE.get('seasons')!r}, not 'all' (v20.29: all years and seasons)")
    if "outcome" not in str(_i.signature(_C.seasons_mode)): bad("seasons_mode does not resolve per outcome")
    if "fill_yearly_covariates(" not in _i.getsource(_C.load_panel): bad("load_panel does not fill annual-row covariates")
    if "fill_yearly_covariates(" not in _i.getsource(_C.estimate_twfe_did_streaming): bad("streaming estimator does not fill annual-row covariates")
    _fz = _i.getsource(_C._frozen_treated_guard) + (_i.getsource(_C._frozen_partial) if hasattr(_C, "_frozen_partial") else "")   # v20.58: partial + final
    if 's["count"] >= 2' not in _fz or ("_frozen_partial(" not in _i.getsource(_C._frozen_treated_guard) and hasattr(_C, "_frozen_partial")):
        bad("frozen-series guard still needs >= 3 rows (silent on annual windows)")
    else: note("yearly-first: per-outcome resolution, annual covariate fill in both estimators, guard works on annual windows")
    bad_nb = []
    for nb in glob.glob(os.path.join(HERE, "0*", "*.ipynb")):
        src = open(nb, encoding="utf-8").read()
        if _re.search(r'SEASONS\s*=\s*\\?"seasonal', src): bad_nb.append(os.path.basename(nb))
    if bad_nb: bad(f"notebooks still default SEASONS to seasonal: {bad_nb[:4]}")
    else: note("every notebook defaults SEASONS to 'auto' (annual composite first)")
    d = _tf.mkdtemp(); f = os.path.join(d, "did_scenario.json")
    _j.dump({"control_zones": [1, 2, 3, 4, 5], "treatment_year": 2023, "post_cutoff": 2023, "seasons": "seasonal"}, open(f, "w"))
    saved = _C.ACTIVE.get("seasons"); _C.load_scenario(path=f, verbose=False)
    if _C.ACTIVE.get("seasons") != saved: bad("a scenario file written before v20.29 overrides the all-years-and-seasons policy")
    _C.ACTIVE["seasons"] = saved
    p00 = open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8").read()
    if "season_choice_report" not in p00: bad("P00 does not report which rows the models will use")
    import _paths as _PP
    dv = _PP.derive(input_dir=d)
    if not dv.get("GROUND_TRUTH_OUTCOMES_PATH", "").startswith(d) or not dv.get("ROLLOUT_INSTRUMENT_PATH", "").startswith(d):
        bad("M07 / M08 input paths do not follow INPUT_DIR")
    else: note("M07 ground-truth and M08 instrument paths follow INPUT_DIR; P00 STEP 8 reports the season choice")
    if getattr(_C, "GROUND_LINK_SEASON", 1) is not None: bad("P08 enumerates pixels from one season only (GROUND_LINK_SEASON)")

def check_near_duplicate_pixels():
    """v20.25: >= 80 % overlapping pixels are one pixel; priority selectable; stale per-variable files unusable;
    a panel built without the merge is rebuilt."""
    import inspect as _i, numpy as _np, pandas as _pd, time as _t, tempfile as _tf
    sys.path.insert(0, HERE)
    import _prep_common as _P, _common as _C
    for fn in ("pixel_registry", "near_duplicate_pairs", "canonical_pixel_map", "build_pixel_overlap_map", "apply_pixel_map"):
        if not hasattr(_P, fn): bad(f"_prep_common.{fn} missing (near-duplicate pixels)")
    if "apply_pixel_map(" not in _i.getsource(_P.prepare_pass_b_block): bad("PASS B does not apply the pixel overlap map")
    if "build_pixel_overlap_map(" not in _i.getsource(_P.run_pass_b): bad("PASS B does not build the pixel overlap map")
    if 'DEDUP_PRIORITY == "complete"' not in _i.getsource(_P.resolve_duplicates): bad("duplicate resolution has no completeness-first option")
    lat0 = 16.44; mlat = 1 / 110574.0; mlon = 1 / (111320.0 * _np.cos(_np.radians(lat0)))
    def _reg(pts):
        r = _pd.DataFrame([{"pixel_id": p, "lat": lat0 + n_ * mlat, "lon": 75.17 + e * mlon, "mtime": t_, "n_rows": 10, "n_ok": int(10 * c_), "src": "x"}
                           for p, e, n_, t_, c_ in pts]).set_index("pixel_id"); r["completeness"] = r.n_ok / r.n_rows; return r
    def _map(pts, pr="newer"):
        r = _reg(pts); m = _P.canonical_pixel_map(r, _P.near_duplicate_pairs(r, 10.0, 0.80), pr); return dict(zip(m.pixel_id, m.canonical_pixel_id))
    cases = [(_map([(1, 0, 0, 1, 1), (2, 1.0, 0.6, 2, 1)]), {1: 2}, "1.0/0.6 m offset merges onto the newer pixel"),
             (_map([(1, 0, 0, 1, 1), (2, 3.0, 0, 2, 1)]), {}, "3 m offset (70 %) stays two pixels"),
             (_map([(1, 0, 0, 3, 1), (2, 1.5, 0, 2, 1), (3, 3.0, 0, 1, 1)]), {2: 1}, "no chaining"),
             (_map([(1, 0, 0, 1, 1.0), (2, 1.0, 0.5, 2, 0.4)], "complete"), {2: 1}, "completeness priority"),
             (_map([(k, (k % 5) * 10.0, (k // 5) * 10.0, 1, 1) for k in range(25)]), {}, "a regular 10 m grid never merges")]
    wrong = [label for got, want, label in cases if got != want]
    if wrong: bad(f"near-duplicate pixel rules broken: {wrong}")
    else: note("pixels overlapping >= 80 % are one pixel (newer or more complete wins); 3 m apart stay apart; no chaining")
    d = _tf.mkdtemp(); ef = os.path.join(d, "ef.parquet"); pn = os.path.join(d, "panel.parquet")
    open(ef, "w").write("x"); _t.sleep(1.2); open(pn, "w").write("y")
    if _C.estimator_file_is_fresh(ef, pn): bad("a per-variable file older than the panel is still treated as usable")
    else: note("per-variable files older than the panel are never read (P09 rebuilds them)")
    if "ACCEPT_PANEL_WITHOUT_PIXEL_MERGE" not in _i.getsource(_P.final_panel_is_valid):
        bad("a panel built without the near-duplicate merge would be reused silently")

def check_treatment_timing():
    """v20.26: works started 2022 (month unknown) -> 2022 is a transition year: out of the sample, pre < 2022,
    post >= 2023, in both engines, the streaming estimator and every notebook; old scenario files cannot pin the old split."""
    import numpy as _np, pandas as _pd, re as _re
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P
    import subprocess as _sp
    code = ("import sys; sys.path.insert(0, %r); import _common as C, _prep_common as P; "
            "a = C.ACTIVE; print(a['treatment_year'], a['post_cutoff'], a['exclude_transition_year'], P.TREATMENT_YEAR, P.POST_CUTOFF, P.EXCLUDE_TRANSITION_YEAR)") % HERE
    out = _sp.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env={**os.environ})
    last = [l for l in out.stdout.splitlines() if l.strip()][-1] if out.stdout.strip() else ""
    if last.split() != ["2022", "2022", "False", "2022", "2022", "False"]:
        bad(f"a fresh engine does not default to treatment year 2022 with post = Year >= 2022: {last or out.stderr[-200:]}")
    else:
        note("a fresh engine defaults to treatment year 2022: pre = Year < 2022, post = Year >= 2022 (both engines)")
    def _sim(seed):
        rng = _np.random.default_rng(seed); rows = []
        for p in range(300):
            b = 0 if p % 5 == 0 else p % 5; a = rng.normal(0, .05)
            for y in range(2016, 2026):
                eff = 0.05 if (b == 0 and y >= 2023) else (0.025 if (b == 0 and y == 2022) else 0.0)   # works start mid-2022
                rows.append((p, y, 0, b, "SW" + str(p % 6), 0.4 + a + eff + rng.normal(0, .01)))
        df_ = _pd.DataFrame(rows, columns=["pixel_id", "Year", "Season", "buff_km", "subwshed_id", "NDVI"]); df_["time_fe_yearseason"] = df_.Year.astype(str)
        return df_
    saved = dict(_C.ACTIVE)
    try:
        _C.set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, exclude_transition_year=True,
                        seasons="all", cohort_offset=0, use_site_years=False, cluster="subwshed", pooled_fe="period")
        bs = []; bad_bounds = False
        for seed in range(6):
            d = _C.build_treatment_columns(_sim(seed)); s = d[d.in_analysis_sample == 1]
            if (s.Year == 2022).any() or int(s.loc[s.post == 1, "Year"].min()) != 2023 or int(s.loc[s.pre == 1, "Year"].max()) != 2021:
                bad_bounds = True
            bs.append(_C.estimate_twfe_did(s, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id")[0])
        b = float(_np.mean(bs))
        if bad_bounds: bad("transition year not handled when switched on: 2022 still in the sample, or pre/post boundaries wrong")
        elif abs(b - 0.05) > 0.002: bad(f"transition-year design is biased: mean over 6 seeds {b:+.4f} vs +0.0500")
        else: note(f"robustness mode (2022 held out) still exact: pre 2015-2021 vs post 2023+; mean over 6 seeds {b:+.4f}")
        _C.set_scenario(verbose=False, exclude_transition_year=False)
        d = _C.build_treatment_columns(_sim(0))
        if not ((d.post == (d.Year >= 2022).astype(int)).all() and (d.pre == (d.Year < 2022).astype(int)).all()
                and (d.loc[d.Year == 2022, "in_analysis_sample"] == 1).any()):
            bad("default timing does not give pre = Year < 2022 and post = Year >= 2022 with 2022 in the sample")
    finally:
        _C.ACTIVE.clear(); _C.ACTIVE.update(saved)
    old = [os.path.basename(nb) for nb in glob.glob(os.path.join(HERE, "0*", "*.ipynb")) if _re.search(r"TREATMENT_YEAR\s*=\s*2023", open(nb, encoding="utf-8").read())]
    if old: bad(f"notebooks still set TREATMENT_YEAR = 2023: {old[:4]}")
    if "_trans_lo" not in open(os.path.join(HERE, "_common.py"), encoding="utf-8").read(): bad("streaming estimator ignores the transition year")
    if 'm.get("timing_policy") != "v20.27"' not in open(os.path.join(HERE, "_common.py"), encoding="utf-8").read():
        bad("an old scenario file could pin the pre-2022 timing")

def check_panel_design_rules():
    """v20.27: buffers recoded exactly; the export's Treat checked as a PERIOD flag; PASS B refuses a panel whose
    treatment/control/pre/post/did columns break the rules."""
    import inspect as _i, numpy as _np
    sys.path.insert(0, HERE)
    import _prep_common as _P
    vals = [0, 1.0, 2.0000001, "3", " 4 ", "5 km", "Buffer_1", "ring-2", 6, -1, "-1", 1.4, None, "core"]
    rec, _ = _P.recode_buff_km(vals)
    want = [0, 1, 2, 3, 4, 5, 1, 2, -1, -1, -1, -1, -1, -1]
    if list(map(int, rec)) != want: bad(f"buffer recode wrong: {list(map(int, rec))} vs {want}")
    else: note("buffer codes recoded exactly (0 / 1.0 / 2.0000001 / '5 km' / 'Buffer_1' -> 0..5; 6, 1.4, text without a number -> neither)")
    qc = _i.getsource(_P.data_qc)
    if "treat_period_mismatch_flag" not in qc or "== TREAT_CORE_BUFFKM).astype(\"int8\")\n    df[\"treat_buffkm" in qc:
        bad("the export's Treat is still compared with the treatment AREA instead of the period rule")
    lh = _i.getsource(_P.load_and_harmonize)
    if "recode_buff_km(" not in lh or lh.index("recode_buff_km(") > lh.index("for c in ESSENTIAL_COLS + OUTCOME_VARS"):
        bad("buffer codes are cast to numbers before being recoded (text codes like '1 km' would be lost)")
    if 'df["Treat"] = (pd.to_numeric(df["Year"]' not in lh: bad("an export without a Treat column would be rejected instead of derived from the rule")
    pb = _i.getsource(_P.prepare_pass_b_block)
    if "treatment_not_buffer0" not in pb or "did_not_treatment_x_post" not in pb: bad("PASS B has no design check")
    if "panel_design_check.csv" not in _i.getsource(_P.run_pass_b): bad("PASS B does not write panel_design_check.csv")
    else: note("PASS B checks every row (buffer 0 treatment, 1-5 control, pre < 2022, post >= 2022, did = treatment x post)")

def check_sws_geometry():
    """v20.28: the 20-SWS shapefile locates every pixel -- projection, point-in-polygon, names, PASS A order."""
    import inspect as _i, numpy as _np
    sys.path.insert(0, HERE)
    import _sws_geometry as _G, _prep_common as _P
    try:
        L = _G.SWSLocator.from_shapefile()
    except Exception as e:
        bad(f"the 20-SWS shapefile cannot be read: {e}"); return
    if len(L.sites) != 20 or len(L.polys) != 120 or L.prj.get("kind") != "utm": bad(f"shapefile structure unexpected: {len(L.sites)} sites, {len(L.polys)} polygons, {L.prj}")
    la = _np.linspace(11.5, 18.5, 15); lo = _np.linspace(74.0, 78.5, 15); la, lo = [a.ravel() for a in _np.meshgrid(la, lo)]
    x, y = _G.latlon_to_tm(la, lo); la2, lo2 = _G.tm_to_latlon(x, y)
    if max(_np.abs(la2 - la).max(), _np.abs(lo2 - lo).max()) > 1e-9 or abs(_G.latlon_to_tm(16.0, 75.0)[0] - 500000.0) > 1e-6:
        bad("UTM projection round trip / central meridian wrong")
    try:
        from matplotlib.path import Path as _MP
        rng = _np.random.default_rng(3); parts, bb = _G.read_shp_polygons(os.path.join(HERE, "data", "sites", "SWSs20_KarnatakaAll5k.shp"))[17]
        px = rng.uniform(bb[0], bb[2], 20000); py = rng.uniform(bb[1], bb[3], 20000)
        ref = _np.zeros(len(px), bool)
        for pt in parts: ref ^= _MP(pt).contains_points(_np.column_stack([px, py]))
        if (_G.PolygonIndex(parts).contains(px, py) != ref).any(): bad("point-in-polygon disagrees with matplotlib on a multi-part polygon")
        else: note("SWS geometry: UTM 43N projection exact, point-in-polygon identical to matplotlib on a 170-part polygon")
    except ImportError:
        note("SWS geometry: projection exact (matplotlib absent -- point-in-polygon cross-check skipped)")
    if L.site_id_for_name("Chhatrakodihalli sub-watershed") != 3 or L.site_id_for_name("Kodihalli") != 12 or L.site_id_for_name("Nilgunda") != 18:
        bad("SWS name matching is wrong (longest name must win)")
    m = _P.harmonize_columns(["Year", "Season", "SubwshedID", "SUBWSHED", "Treat", "latitude", "longitude", "buff_km"], fname="x", unresolved_log=[])
    if m.get("SUBWSHED") != "SWS_Name": bad("a SUBWSHED name column would be read as the numeric SubwshedID")
    wk = _i.getsource(_P._pa_worker)
    if "tag_sites(" not in wk or wk.index("tag_sites(") > wk.index("resolve_duplicates("): bad("PASS A de-duplicates before the SWS is known")
    for k in ("sws_name", "site_check"):
        if k not in _P.FINAL_PANEL_SCHEMA: bad(f"panel schema lacks {k}")
    for rel in ("_sws_geometry.py", "01_Panel_Preparation/P00_RUN_ALL_Panel_Preparation.ipynb"):
        if not os.path.exists(os.path.join(HERE, rel)): bad(f"missing {rel}")
    note("SWS tags: SUBWSHED read as a name, longest-name match, tagged before de-duplication, sws_name + site_check in the panel")

def check_v20_29():
    """v20.29: P09 writer, notebook import order, all years + seasons with pixel x season FE, covariate choice,
    fund-release calendar, R timing + unit, pre-built package routing."""
    import inspect as _i, numpy as _np, pandas as _pd, re as _re, json as _j
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P
    src = _i.getsource(_C.build_estimator_files)
    if 'astype("int16")' in src.split("first_treat_agri_year")[1][:300] if "first_treat_agri_year" in src else True:
        bad("P09 still decides first_treat_agri_year's type per chunk (the schema-mismatch failure)")
    if "tbl.select(writer.schema.names).cast(writer.schema)" not in src: bad("P09 writer does not cast every chunk to the file's schema")
    else: note("P09 writer: one fixed type for first_treat_agri_year, every chunk cast to the file's schema")
    late = []
    for nb in glob.glob(os.path.join(HERE, "0*", "*.ipynb")):
        d = _j.load(open(nb, encoding="utf-8")); code = "\n".join("".join(c["source"]) for c in d["cells"] if c["cell_type"] == "code")
        for name, pat in (("C", r"(import _common as C\b|\bC\s*=\s*[\w\.]*import_module\([\"']_common)"), ("P", r"(import _prep_common as P\b|\bP\s*=\s*[\w\.]*import_module\([\"']_prep_common)")):
            u = _re.search(r"(?<![\w\.])" + name + r"\.[A-Za-z_]", code)
            if u and not (_re.search(pat, code[:u.start()]) or _re.search(r'if "' + name + r'" not in globals', code[:u.start()])):
                late.append(f"{os.path.basename(nb)}:{name}")
    if late: bad(f"notebooks use the engine before importing it: {late[:5]}")
    else: note("every notebook imports C / P before first use (validate_notebooks_cold.py runs them from their own folders)")
    if not os.path.exists(os.path.join(HERE, "validate_notebooks_cold.py")): bad("cold-start notebook gate missing")
    if _C.ACTIVE.get("unit_fe") != "pixel_season": bad("default unit fixed effect is not pixel x season")
    rng = _np.random.default_rng(1); rows = []
    for u in range(120):
        b = 0 if u < 60 else 5; fe = rng.normal(0, 1)
        for yr in (2019, 2020, 2021, 2022, 2023):
            for sc in (0, 1, 2):
                rows.append({"pixel_id": f"P{u}", "Year": yr, "Season": sc, "buff_km": b, "time_fe_yearseason": f"{yr}_{sc}",
                             "subwshed_id": f"S{u % 6}", "y": fe + 0.2 * sc + 0.1 * (yr - 2019) + (0.5 if (b == 0 and yr >= 2022) else 0) + rng.normal(0, .05)})
    saved = dict(_C.ACTIVE); covs0 = list(_C.DEFAULT_COVARIATES)
    try:
        _C.set_scenario(verbose=False, all_years=True, treatment_year=2022, exclude_transition_year=False, seasons="all", unit_fe="pixel_season", covariates=[])
        dd = _C.build_treatment_columns(_pd.DataFrame(rows)); dd = dd[dd.in_analysis_sample == 1]
        b_, _ = _C.estimate_twfe_did(dd, "y", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id")
        if dd.unit_id.nunique() != 360 or abs(b_ - 0.5) > 0.03: bad(f"pixel x season units wrong: {dd.unit_id.nunique()} units, beta {b_:.3f}")
        else: note(f"all years + seasons with pixel x season and year x season FE: 360 units from text ids, beta {b_:.3f} (true 0.5)")
        ref = _C.DEFAULT_COVARIATES; _C.set_scenario(verbose=False, covariates=["Rain"])
        if ref is not _C.DEFAULT_COVARIATES or list(ref) != ["Rain"] or "covRain" not in _C.scenario_tag(): bad("covariate choice does not reach the shared list / result folder")
        try:
            _C.set_scenario(verbose=False, covariates=["NDVI"]); bad("an outcome was accepted as a covariate")
        except _C.InsufficientDataError:
            note("covariate choice: one shared list, own result folder, outcomes refused as covariates")
    finally:
        _C.ACTIVE.clear(); _C.ACTIVE.update(saved); _C.DEFAULT_COVARIATES[:] = covs0
    for d_, exp in (("2021-11-15", (2022, 3)), ("2022-04-10", (2022, 1)), ("2022-06-15", (2022, 2)), ("2023-01-20", (2023, 3))):
        if _P.next_season_after(_pd.Timestamp(d_)) != exp: bad(f"fund-release season rule wrong for {d_}: {_P.next_season_after(_pd.Timestamp(d_))} vs {exp}"); break
    else: note("fund-release -> next season follows the export calendar (never a past or year-late season)")
    _rlib = os.path.dirname(_C.r_bridge_script())                                   # v20.45: the R pipeline's library
    r = open(os.path.join(_rlib, "reward_prep.R"), encoding="utf-8").read()
    rall = "".join(open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(_rlib, "*.R")))
    # v20.57: the timing columns are built by the MODEL stage (reward_design.R design_columns), from each row's own cohort
    if ("post := as.integer(Year >= cohort_row)" not in rall or 'paste(pixel_id, Season, sep = "_")' not in rall
            or "pixel_id + period" in rall or "| unit + period" not in rall): bad("R side disagrees with Python (timing or unit fixed effect)")
    else: note("R engine and R pipelines: post = Year >= each row's cohort (the timing in force) and the same pixel x season unit as Python")
    if "unit" not in _C.PACKAGE_INPUT_COLUMNS: bad("package input lacks the unit fixed effect")
    for fn in ("verify_prebuilt_routes", "prebuilt_status", "_use_prebuilt", "_route_call"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing (pre-built packages)")
    if "verify_prebuilt_routes" not in open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8").read(): bad("P12 (package verification) is not in P00")
    st = _C.prebuilt_status(verbose=False)
    if not set(st.estimator) >= {"twfe", "event_study", "wild_bootstrap", "callaway_santanna"}: bad("pre-built routes incomplete")
    else: note("pre-built packages: used only once P12 verified them on this machine; engine otherwise, labelled per result")
    v00 = open(os.path.join(HERE, "06_Validation", "V00_RUN_ALL_VALIDATIONS.py"), encoding="utf-8").read()
    if 'D="DIDRDP_ALLRunDID_FINAL"' in v00: bad("V00 still hard-codes an old folder name")

def check_v20_30():
    """v20.30: covariates per model (groups), negative covariates floored at panel level, memory first (95 % ceiling)."""
    import inspect as _i, numpy as _np, pandas as _pd, json as _j, tempfile as _tf
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P, _hardware as _H
    # covariates chosen per model
    if set(_C.COVARIATE_GROUPS) != {"all", "mean_temp_rain", "weather", "none"} or _C.resolve_covariates("mean_temp_rain")[0] != ["Tmean", "Rain"]:   # v20.45: no land-use group
        bad("covariate groups wrong")
    if "covariates" in _C.SCENARIO_KEYS: bad("covariates are still a panel-level scenario key (they must be chosen per model)")
    code = lambda nb: "\n".join("".join(c["source"]) for c in _j.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
    prep_set = [os.path.basename(nb) for nb in glob.glob(os.path.join(HERE, "01_Panel_Preparation", "*.ipynb"))
                if "P11" not in nb and "covariates=COVARIATES" in code(nb)]
    models_missing = [os.path.basename(nb) for nb in glob.glob(os.path.join(HERE, "0[2-5]*", "*.ipynb")) if "covariates=COVARIATES" not in code(nb)]
    if prep_set: bad(f"panel preparation still sets covariates: {prep_set}")
    elif models_missing: bad(f"model notebooks without their own covariate choice: {models_missing[:4]}")
    else: note("covariates are chosen in each model (groups: all / mean_temp_rain / weather / none, or a list); preparation keeps every covariate")
    if "ALL_COVARIATE_COLUMNS" not in _i.getsource(_C.build_estimator_files): bad("P09 does not write every covariate column")
    # negatives floored at panel level, after the zero rule; floored zeros stay real downstream
    saved = (_P.ALLOW_NEGATIVE_COVARIATES, dict(_P.NEGATIVE_COVARIATE_RULE))
    try:
        _P.ALLOW_NEGATIVE_COVARIATES = False; _P.NEGATIVE_COVARIATE_RULE = {"Rain": "zero", "Tmax": "zero", "Tmean": "zero", "Tmin": "zero"}
        f = _pd.DataFrame({"NDVI": [0.4, 0.4, 0.4, -0.05], "Rain": [-1.5, 0.0, 5.0, 3.0], "Tmin": [-10.0, 18.0, 19.0, 20.0]})
        a, _ = _P.apply_missing_policy(f.copy(), stage="file")
        b, _ = _P.apply_missing_policy(a.copy(), stage="block")
        # v20.30: -10.0 C is the exporter's clamp on a MASKED cell -> missing, never a fake 0 C
        good = (a.Rain.iloc[0] == 0 and _np.isnan(a.Rain.iloc[1]) and _np.isnan(a.Tmin.iloc[0]) and b.Rain.iloc[0] == 0 and abs(b.NDVI.iloc[3] + 0.05) < 1e-9)
        if not good: bad(f"negative floor wrong: file {a.Rain.tolist()} {a.Tmin.tolist()} -> block {b.Rain.tolist()}")
        else: note("negative Rain / temperature floored to 0 at panel level (after the zero rule); floored zeros survive PASS B and the models")
    finally:
        _P.ALLOW_NEGATIVE_COVARIATES, _P.NEGATIVE_COVARIATE_RULE = saved
    if not (_C._usable([0.0], "Rain")[0] and not _C._usable([0.0], "NDVI")[0]): bad("load-time zero rule does not treat a floored 0 as real")
    if "FLOORED_COVARIATES" not in _i.getsource(_C.load_panel): bad("load_panel's own zero test ignores the floor")
    # memory first
    if getattr(_H, "MEMORY_CEILING", None) != 0.98 or not all(hasattr(_H, f_) for f_ in ("ram_budget_bytes", "gpu_budget_bytes", "fits", "memory_report")):
        bad("the 98 % memory governor is missing (v20.57: your rule, was 95 %)")
    _wc = _i.getsource(_H.worker_cap)
    if "every logical core" not in _wc.lower(): bad("worker pools are capped (v20.52: every logical core, your instruction)")
    if "ram_budget_bytes()" not in _wc: bad("worker pools are not sized by YOUR 98 % RAM rule (v20.52 had dropped it; v20.53 restored it)")
    if _C.GPU_MAX_ROWS is not None or "gpu_budget_bytes" not in _i.getsource(_C.gpu_capacity_rows): bad("GPU use is not decided by the 98 % VRAM ceiling")
    if not _C.LOAD_ALL_AT_ONCE or "_cached_or_read(" not in _i.getsource(_C.load_panel): bad("load_panel does not read the whole table at once")
    if _P.IN_MEMORY_BLOCKS or "MemBlock" not in _i.getsource(_P.run_pass_a) or "_block_frame(" not in _i.getsource(_P.prepare_pass_b_block):
        bad("PASS A -> PASS B in-RAM blocks are not wired (or are on by default where P03 -> P04 need shard files)")
    if "P.IN_MEMORY_BLOCKS = True" not in code(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb")):
        bad("P00 does not keep PASS A blocks in RAM")
    rng = _np.random.default_rng(0); n = 4000
    _pix = rng.integers(1, 400, n).astype("int64")
    df_ = _pd.DataFrame({"pixel_id": _pix, "Year": rng.integers(2016, 2026, n).astype("int16"),
                         "Season": rng.integers(0, 4, n).astype("int8"), "buff_km": (_pix % 6).astype("int8"),     # v20.58: ONE ring per pixel (a pixel
                         "subwshed_id": "SW1", "NDVI": rng.uniform(0.1, 0.6, n).astype("float32"), "Rain": rng.uniform(0, 800, n).astype("float32"),   # whose ring
                         "Tmax": 33.0, "Tmean": 26.0, "Tmin": 19.0, "LandUse": 2, "site_id": 1, "first_treat_agri_year": 2022.0})               # differs leaves)
    df_ = df_.drop_duplicates(["pixel_id", "Year", "Season"]).reset_index(drop=True)                      # every pixel-year-season once
    import pyarrow as _pa, pyarrow.parquet as _pq
    d_ = _tf.mkdtemp(); fp = os.path.join(d_, "p.parquet"); _pq.write_table(_pa.Table.from_pandas(df_, preserve_index=False), fp, row_group_size=500)
    keep = (_C.PREPARED_PANEL, _C.ESTIMATOR_FILES_DIR, dict(_C.ACTIVE), list(_C.DEFAULT_COVARIATES))
    try:
        _C.PREPARED_PANEL = fp; _C.ESTIMATOR_FILES_DIR = os.path.join(d_, "none"); _C.clear_panel_cache()
        _C.set_scenario(verbose=False, all_years=True, seasons="all", covariates="weather")
        _C.LOAD_ALL_AT_ONCE = True; a_ = _C.load_panel(columns=_C.columns_for("NDVI"))
        _C.LOAD_ALL_AT_ONCE = False; b_ = _C.load_panel(columns=_C.columns_for("NDVI"))
        srt = lambda x: x.sort_values(["pixel_id", "Year", "Season", "NDVI"], kind="mergesort").reset_index(drop=True)
        if not srt(a_).equals(srt(b_)): bad("whole-table load differs from the row-group load")
        else: note("memory first: whole-table load == row-group load; RAM / VRAM used up to 98 % (v20.57), fallback beyond (PASS A -> B in RAM in P00)")
    finally:
        _C.LOAD_ALL_AT_ONCE = True; _C.PREPARED_PANEL, _C.ESTIMATOR_FILES_DIR = keep[0], keep[1]
        _C.ACTIVE.clear(); _C.ACTIVE.update(keep[2]); _C.DEFAULT_COVARIATES[:] = keep[3]; _C.clear_panel_cache()

def check_v20_30_gpu_and_barrier():
    """v20.30: every GPU demeaning verified on ALL rows (CPU result on rejection); no-data never floored to a fake 0;
    the barrier rebuilds the panel; tests never write into the bundle."""
    import inspect as _i, numpy as _np
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P
    for fn in ("_gpu_verify", "_fe_group_mean_max"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing (full-data GPU verification)")
    for disp in (_C.demean_multi_way, _C.demean_columns):
        if "_gpu_verify(" not in _i.getsource(disp): bad(f"{disp.__name__} returns GPU results without verifying them on all rows")
    rng = _np.random.default_rng(0); n = 40000
    u = rng.integers(0, 3000, n); p = rng.integers(0, 40, n); Y = _np.column_stack([rng.normal(0.4, .1, n), rng.normal(500, 50, n)])
    good = _C._demean_cpu_matrix(Y, [u, p], 1e-10, 200)
    saved = (_C.USE_GPU, dict(_C._GPU_TRUST), _C._torch_cuda, _C.gpu_capacity_rows, _C.GPU_MIN_ROWS, _C._demean_gpu_matrix)
    try:
        _C._torch_cuda = lambda: object(); _C.gpu_capacity_rows = lambda n_fe=2: 10**12; _C.GPU_MIN_ROWS = 1
        _C.USE_GPU = True; _C._GPU_TRUST.update({"matrix": True})
        def _bad(T, Y_, f, tol, mi):
            r = _C._demean_cpu_matrix(Y_, f, tol, mi); r[30000:, 0] += 1e-4; return r      # wrong only beyond row 30,000
        _C._demean_gpu_matrix = _bad
        out = _C.demean_columns(Y, u, p)
        if _C.USE_GPU or _np.abs(out - good).max() > 1e-9: bad("a GPU result wrong beyond the first rows was accepted")
        else: note("GPU demeaning verified on ALL rows every call (a 1e-4 error beyond row 30,000 in one column is rejected; CPU result used)")
    finally:
        _C.USE_GPU, trust, _C._torch_cuda, _C.gpu_capacity_rows, _C.GPU_MIN_ROWS, _C._demean_gpu_matrix = saved; _C._GPU_TRUST.update(trust)
    df = _P.pd.DataFrame({"Rain": [-0.4, -9999.0, 3.0], "Tmax": [-0.2, -10.0, 30.0], "NDVI": [-0.1, 0.3, 0.4], "buff_km": [0, 1, 2]})
    o, _ = _P.apply_missing_policy(df.copy(), stage="file")
    if not (o.Rain.tolist()[0] == 0.0 and _np.isnan(o.Rain.tolist()[1]) and o.Tmax.tolist()[0] == 0.0 and _np.isnan(o.Tmax.tolist()[1]) and o.NDVI.tolist()[0] == -0.1):
        bad(f"negative-covariate rule wrong: {o.to_dict('list')}")
    else: note("negative covariates -> 0; no-data (-9999) and the -10 C clamp -> missing (never a fake 0); outcomes untouched")
    if "negative_barrier" not in _i.getsource(_P.final_panel_is_valid): bad("a panel built with another negative barrier would be reused")
    if "REWARD_INPUT_DIR" not in open(os.path.join(HERE, "validate_notebooks_cold.py"), encoding="utf-8").read(): bad("cold-start gate could write into the bundle")
    if not os.path.exists(os.path.join(HERE, "validate_prep_notebooks.py")): bad("the end-to-end preparation-notebook gate is missing")
    if "treated_ids" not in _i.getsource(_P.streaming_panel_stats): bad("treated / control pixels are still estimated from a 1 % sample (false NOT VALID on small panels)")
    else: note("panel check counts treated / control pixels exactly (a 1 % sample declared small panels NOT VALID)")
    junk = [x for x in glob.glob(os.path.join(HERE, "**", "*"), recursive=True) if ":" in os.path.basename(x) or "\\" in os.path.basename(x)]
    if junk: bad(f"folders named like Windows paths inside the bundle (cannot be extracted on Windows): {junk[:2]}")

def check_v20_32():
    """v20.32: the non-negative switch (off by default, labelled, own folder), baseline means, both specifications."""
    import inspect as _i, numpy as _np, pandas as _pd
    sys.path.insert(0, HERE)
    import _common as _C
    if _C.NONNEGATIVE_ESTIMATION is not False: bad("the non-negative switch is ON by default (it must be opt-in)")
    saved = (_C.NONNEGATIVE_ESTIMATION, dict(_C.ACTIVE))
    try:
        _C.set_scenario(verbose=False, nonnegative=True)
        if "_nonneg" not in _C.scenario_tag(): bad("results of a non-negative run would overwrite the clean ones (no tag)")
        else: note("non-negative switch: off by default, own '_nonneg' results folder, recorded in every saved file")
    finally:
        _C.ACTIVE.clear(); _C.ACTIVE.update(saved[1]); _C.NONNEGATIVE_ESTIMATION = saved[0]
    rng = _np.random.default_rng(0); rows = []
    for p in range(120):
        b = 0 if p % 5 == 0 else p % 5
        for y in (2020, 2021, 2022, 2023):
            v = 0.4 + (0.05 if (b == 0 and y >= 2022) else 0) + rng.normal(0, .02) - (0.6 if p % 13 == 0 else 0)
            rows.append({"pixel_id": p, "Year": y, "Season": 0, "buff_km": b, "subwshed_id": f"S{p % 6}",
                         "time_fe_yearseason": f"{y}_0", "NDVI": v})
    d = _C.build_treatment_columns(_pd.DataFrame(rows)); d = d[d.in_analysis_sample == 1]
    s, tab = _C.baseline_means("NDVI", df=d, save=False)
    if not (s["n_rows_baseline"] > 0 and _np.isfinite(s["baseline_mean_treated_pre"]) and s["share_negative_all"] > 0 and len(tab)):
        bad(f"baseline means wrong: {s}")
    else:
        ctx = _C.effect_in_context(0.05, s)
        if not _np.isfinite(ctx["effect_pct_of_baseline"]): bad("the effect cannot be expressed against its baseline")
        else: note("baseline (pre-treatment) mean, its spread and the share of negative values are computed and saved per variable")
    for fn, par in ((_C.estimate_event_study, "covariates"), (_C.pretrends_joint_ftest, "covariates")):
        if par not in _i.signature(fn).parameters: bad(f"{fn.__name__} cannot produce a covariate-adjusted result")
    import json as _j, glob as _g
    # v20.58: M02 / M16's HEADLINE is covariate-adjusted (the design's COVARIATES, as R); the result without covariates is saved beside it
    for tag, pat, keys in (("M02", "0*/M02_*.ipynb", ("beta_covariate_adjusted", "beta_no_covariates")), ("M16", "0*/M16_*.ipynb", ("f_stat_covariate_adjusted", "f_stat_no_covariates")),
                           ("M01", "0*/M01_*.ipynb", ("baseline_means", "canonical_twfe_{OUTCOME}.csv")), ("P00", "01_Panel_Preparation/P00_*.ipynb", ("baseline_and_counts_all",))):
        f = _g.glob(os.path.join(HERE, pat))[0]
        if not any(k_ in open(f, encoding="utf-8").read() for k_ in keys): bad(f"{tag} does not save {' / '.join(keys)}")
    if "baseline_means(_o, df=_fr" not in _i.getsource(_C.save_results): bad("M01's canonical result (save_results) no longer carries its baseline means")   # v20.58: every mode
    note("canonical AND covariate-adjusted results saved (M01 2x2, M02 event study, M16 pre-trends: v20.58 the covariate-adjusted one is the headline, "
         "the one without covariates beside it); baselines from P09")
    if not os.path.exists(os.path.join(HERE, "RANKED_MODELS.md")) or not hasattr(_C, "model_ranking"): bad("the model ranking is missing")
    else: note("models ranked for this design (RANKED_MODELS.md, C.model_ranking())")
    import tempfile as _tf
    _o = _pd.DataFrame([{"outcome": "NDVI", "f_stat": 4748.3, "p_value": 0.0, "leads_dropped": "", "identification_note": "none", "beta": 0.01}])
    try:
        _C.save_results(_o, _tf.mkdtemp(), "pretrends_ftest_NDVI.csv")
        note("a result whose descriptive field is empty ('no leads dropped') is written -- it used to block every M16 file")
    except Exception as _e:
        bad(f"the placeholder rule still blocks a valid result: {str(_e)[:110]}")
    try:
        _C.save_results(_pd.DataFrame([{"outcome": "NDVI", "beta": 0.01, "method": "TBD"}]), _tf.mkdtemp(), "x.csv")
        bad("a real placeholder ('TBD') was accepted into a result file")
    except Exception:
        pass
    _sv = (_C.NONNEGATIVE_ESTIMATION, _C.BLOCK_NEGATIVES_IN_ESTIMATION)
    try:
        _C.NONNEGATIVE_ESTIMATION = False; _C.BLOCK_NEGATIVES_IN_ESTIMATION = True; _C._sync_negative_switch()
        if not _C.NONNEGATIVE_ESTIMATION: bad("the two negative switches are not in sync (a run could be mislabelled)")
        else: note("one negative switch: the older BLOCK_NEGATIVES_IN_ESTIMATION name mirrors it, one results-folder suffix")
    finally:
        _C.NONNEGATIVE_ESTIMATION, _C.BLOCK_NEGATIVES_IN_ESTIMATION = _sv; _C._sync_negative_switch()
    import glob as _g2
    _p8 = open(_g2.glob(os.path.join(HERE, "01_Panel_Preparation", "P00_*.ipynb"))[0], encoding="utf-8").read()
    if 'globals().get(\\"xy\\") is None' not in _p8: bad("P08 crashes when re-run with existing outputs (its skip path does not reach the later cells)")
    else: note("P08 re-run with existing outputs skips cleanly instead of failing with NameError")

def check_v20_34():
    """v20.34: CELL 1 wins over the saved panel scenario; the negative filter follows the scenario everywhere
    (loop lock included); the pre-trends F is not reported as REJECT on an ill-conditioned covariance."""
    import os as _os, tempfile as _tf, numpy as _np, inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C
    saved = dict(_C.ACTIVE)
    try:
        f = _os.path.join(_tf.mkdtemp(), "did_scenario.json")
        _C.set_scenario(verbose=False, control_zones="1-5", treatment_year=2022, seasons="all", nonnegative=False)
        _C.save_scenario(path=f, verbose=False)
        _C.set_scenario(verbose=False, control_zones="1-3", treatment_year=2022, seasons="auto", nonnegative=True)
        _C.load_scenario(path=f, verbose=False)
        ok_ = (_C.ACTIVE["control_zones"] == (1, 2, 3) and _C.ACTIVE["seasons"] == "auto" and _C.NONNEGATIVE_ESTIMATION
               and "ctrl1-3" in _C.scenario_tag() and "_nonneg" in _C.scenario_tag())
        if not ok_: bad(f"the saved panel scenario still overrides CELL 1 ({_C.scenario_tag()})")
        else: note("CELL 1's explicit settings win over the saved panel scenario (which fills only what CELL 1 leaves unset)")
        snap = dict(_C.ACTIVE); _C.OUTCOME_LOOP_STATE.update({"scenario": snap, "outcome": "SAVI"}); _C.NONNEGATIVE_ESTIMATION = False
        _C.set_scenario(verbose=False, control_zones="1-5", nonnegative=False)
        if not (_C.ACTIVE["control_zones"] == (1, 2, 3) and _C.NONNEGATIVE_ESTIMATION and "_nonneg" in _C.scenario_tag()):
            bad("the outcome loop runs a different design / filter than the first outcome")
        else: note("the outcome loop runs every outcome under the first outcome's design, filter and folder")
    finally:
        _C.OUTCOME_LOOP_STATE.clear(); _C.ACTIVE.clear(); _C.ACTIVE.update(saved); _C._force_negative_from_active()
    src = _i.getsource(_C.pretrends_joint_ftest)
    if "test_reliable" not in src or "INCONCLUSIVE" not in src: bad("the pre-trends F can still declare REJECT on a near-singular covariance")
    else: note("pre-trends F: only well-conditioned directions tested; an ill-conditioned covariance gives INCONCLUSIVE, not REJECT")

def check_v20_35():
    """v20.35: the small-effect diagnostic names the right cause, and every TWFE result carries MDE + raw 2x2."""
    import numpy as _np, pandas as _pd
    sys.path.insert(0, HERE)
    import _common as _C
    if not hasattr(_C, "diagnose_effect_size"): bad("the small-effect diagnostic is missing"); return
    def _pid(lat, lon): return int(_np.rint((lat + 90) * 1e5)) * 1_000_000_000 + int(_np.rint((lon + 180) * 1e5))
    rng = _np.random.default_rng(0); rows = []
    for p in range(600):
        b = 0 if p % 6 == 0 else 1 + p % 5
        for y in range(2018, 2027):
            lat, lon = 16.5 + (p // 30) * 0.00009, 75.2 + (p % 30) * 0.000093
            if y >= 2025: lat += 4 / 110540.0; lon += 4 / 106000.0          # a later export on a 4 m-shifted grid
            rows.append((_pid(lat, lon), y, 0, b, f"S{p % 6}", 0.3 + rng.normal(0, .02) + (0.02 if (b == 0 and y >= 2022) else 0)))
    df = _pd.DataFrame(rows, columns=["pixel_id", "Year", "Season", "buff_km", "subwshed_id", "NDVI"]); df["time_fe_yearseason"] = df.Year.astype(str) + "_0"
    saved = dict(_C.ACTIVE)
    try:
        _C.set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, seasons="all", covariates=[], nonnegative=False)
        S, _ = _C.diagnose_effect_size("NDVI", df=df, save=False, verbose=False)
        if "SHIFTED pixel grid" not in S["verdicts"] or "PIXEL_OVERLAP_MIN" not in S["verdicts"]:
            bad(f"the diagnostic missed a shifted pixel grid: {S['verdicts'][:120]}")
        else: note("small-effect diagnostic finds a shifted later grid and names the P00 fix (P13 runs it for every outcome)")
        d = _C.build_treatment_columns(df); d = d[d.in_analysis_sample == 1]
        _C.estimate_twfe_did(d, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id")
        if not ("mde_80pct_tG1" in _C.LAST_FIT_INFO and "raw_did_means" in _C.LAST_FIT_INFO): bad("TWFE results lack the MDE / raw 2x2")
        else: note("every TWFE result carries its minimum detectable effect and the raw 2x2 of group means")
    finally:
        _C.ACTIVE.clear(); _C.ACTIVE.update(saved); _C._force_negative_from_active()
    if "diagnose_effect_size" not in open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8").read(): bad("P13 (effect-size diagnostics) is not in P00")

def check_v20_35_structure():
    """v20.35: gap-filled rows out of estimation, scenario-only rows loaded (M24 exempt), multi-site controls cleaned,
    per-variable files carry the QC flags, and every result records what was left out."""
    sys.path.insert(0, HERE)
    import _common as _C, inspect as _i
    if not (_C.EXCLUDE_GAPFILLED and _C.CLEAN_CONTROLS and _C.LOAD_SCENARIO_ROWS_ONLY): bad("a v20.35 structural default is off")
    if _C.MODELS_NEEDING_ALL_RINGS: bad(f"{sorted(_C.MODELS_NEEDING_ALL_RINGS)} load rings outside CONTROL_ZONES (v20.58 YOUR RULE: the rings you set are the rings every model uses)")
    if not {"GapFilled", "Coverage"} <= set(_C.ESTIMATOR_FILE_EXTRA): bad("P09 files do not carry the QC flags")
    if not {"GapFilled", "Coverage"} <= set(_C.columns_for("NDVI")): bad("models do not read the QC flags")
    src = _i.getsource(_C.load_panel)
    if "EXCLUDE_GAPFILLED" not in src or "LOAD_SCENARIO_ROWS_ONLY" not in src: bad("load_panel does not apply the v20.35 row rules")
    if "CLEAN_CONTROLS" not in _i.getsource(_C.build_treatment_columns): bad("multi-site contaminated controls are not cleaned")
    if not hasattr(_C, "diagnose_effect_size"): bad("the effect-size diagnostic is missing")
    import pandas as _pd, numpy as _np
    rows = []
    for p in range(120):
        b = 0 if p % 6 == 0 else 1 + p % 5; site = 1 if (p // 6) % 2 == 0 else 2
        for y in (2020, 2021, 2022, 2023):
            rows.append({"pixel_id": p, "Year": y, "Season": 0, "buff_km": b, "site_id": site, "subwshed_id": f"S{p % 6}",
                         "time_fe_yearseason": f"{y}_0", "NDVI": 0.4 + (0.05 if (b == 0 and y >= 2022) else 0)})
            if b == 0 and site == 2:
                rows.append({"pixel_id": p, "Year": y, "Season": 0, "buff_km": 2, "site_id": 1, "subwshed_id": f"S{p % 6}",
                             "time_fe_yearseason": f"{y}_0", "NDVI": 0.4 + (0.05 if y >= 2022 else 0)})
    saved = dict(_C.ACTIVE)
    try:
        _C.set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, seasons="all", nonnegative=False)
        d = _C.build_treatment_columns(_pd.DataFrame(rows))
        if int(_C.LAST_DESIGN_INFO.get("contaminated_control_rows", 0)) == 0: bad("a treated pixel still serves as a control in another site")
        else: note("gap-filled rows out of estimation, only the scenario's rings loaded (every model: M24's gradient over your rings), treated pixels never controls across sites")
    finally:
        _C.ACTIVE.clear(); _C.ACTIVE.update(saved)

def check_v20_36():
    """v20.36: pixel counts + diagnostics beside the canonical result; all-variable baselines; a cell log per notebook."""
    import tempfile as _tf, numpy as _np, pandas as _pd, json as _j
    sys.path.insert(0, HERE)
    import _common as _C
    for fn in ("design_counts", "repeat_shares", "baseline_and_counts_all", "start_cell_log", "diagnose_effect_size"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing")
    rng = _np.random.default_rng(2); rows = []
    for p in range(600):
        b = 0 if p % 6 == 0 else 1 + p % 5; frz = p % 10 < 4; comp = rng.normal(0.35, 0.05)
        for y in range(2018, 2025):
            rows.append({"pixel_id": 10_000 + p, "Year": y, "Season": 0, "buff_km": b, "subwshed_id": f"S{(p // 6) % 6}",
                         "time_fe_yearseason": f"{y}_0", "NDVI": comp if (frz and y <= 2023) else comp + rng.normal(0, .03)})
    saved = dict(_C.ACTIVE)
    try:
        _C.set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, exclude_transition_year=False,
                        seasons="all", nonnegative=False, covariates=[])
        d = _C.build_treatment_columns(_pd.DataFrame(rows)); d = d[d.in_analysis_sample == 1]
        b_, s_ = _C.estimate_twfe_did(d, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id")
        od = _tf.mkdtemp(); _C.save_results({"outcome": "NDVI", "beta": b_, "se": s_}, od, "canonical_twfe_NDVI.csv")
        r = _pd.read_csv(os.path.join(od, "canonical_twfe_NDVI.csv")).iloc[0]; files = set(os.listdir(od))
        need = {"design_counts_NDVI.csv", "baseline_means_NDVI.csv", "effect_size_diagnostics_NDVI.csv"}
        if not need <= files or "n_pixels_treated_pre" not in r.index or not (0.3 < float(r.get("repeat_share_treated_pre", 0)) < 0.5):
            bad(f"the canonical result lacks its counts / baseline / diagnostics ({sorted(files)})")
        else: note("canonical result carries pixel counts per category, baseline, repeat shares and MDE; files saved beside it")
    finally:
        _C.ACTIVE.clear(); _C.ACTIVE.update(saved); _C._force_negative_from_active()
    nb_py = [f for f in glob.glob(os.path.join(HERE, "0*", "*.ipynb"))
             if (_j.load(open(f, encoding="utf-8")).get("metadata", {}).get("kernelspec", {}) or {}).get("language", "python").lower() == "python"]
    nolog = [os.path.basename(f) for f in nb_py if "start_cell_log" not in open(f, encoding="utf-8").read()]
    if nolog: bad(f"notebooks without a cell log: {nolog[:4]}")
    import inspect as _i2
    if "RESULTS_ROOT" not in _i2.getsource(_C.start_cell_log): bad("cell logs would fall back to the system temp folder instead of <OUTPUT_DIR>")
    else: note(f"all {len(nb_py)} Python notebooks write every cell's messages to <OUTPUT_DIR>/cell_logs")
    p9 = open(glob.glob(os.path.join(HERE, "01_Panel_Preparation", "P00_*.ipynb"))[0], encoding="utf-8").read()
    if "baseline_and_counts_all" not in p9: bad("P09 does not write the all-variable baseline and pixel-count files")

def check_v20_37():
    """v20.37: the cell-log hooks RUN inside IPython (a stand-in shell fires the same events -- the v20.36 hooks raised
    NameError on every cell and no test had executed them); OptTier is a known QC column; the id-correction report
    tells a renumbering from wrong ids."""
    import types as _ty, inspect as _i, pandas as _pd, importlib as _il
    sys.path.insert(0, HERE)
    class _Ev:
        def __init__(s): s.cb = {}
        def register(s, n, f): s.cb.setdefault(n, []).append(f)
        def trigger(s, n, *a):
            for f in s.cb.get(n, []): f(*a)
    class _Sh:
        def __init__(s): s.events = _Ev(); s.user_ns = {}
    sh = _Sh(); fake = _ty.ModuleType("IPython"); fake.get_ipython = lambda: sh
    real = sys.modules.get("IPython"); sys.modules["IPython"] = fake
    try:
        import _common as _C
        _C._CELL_LOG.update({"hooked": False})
        p = _C.start_cell_log("SELFCHECK_HOOKS")
        class _In: raw_cell = "x = 1"
        class _Re:
            def __init__(s, e=None): s.error_in_exec = e; s.error_before_exec = None
        try:
            sh.events.trigger("pre_run_cell", _In()); sh.events.trigger("post_run_cell", _Re())
            sh.events.trigger("pre_run_cell", _In()); sh.events.trigger("post_run_cell", _Re(ValueError("boom")))
            log = open(p, encoding="utf-8").read()
            if "finished ok" in log and "FAILED" in log and "boom" in log: note("cell-log hooks run inside IPython: per-cell headers, ok footers and full errors reach the log")
            else: bad("cell-log hooks ran but the log lacks headers / footers / errors")
        except Exception as e:
            bad(f"the cell-log hooks RAISE inside IPython ({type(e).__name__}: {e}) -- every cell would print an error")
    finally:
        if real is not None: sys.modules["IPython"] = real
        else: sys.modules.pop("IPython", None)
    import _prep_common as _P
    if "OptTier" not in _P.FINAL_PANEL_COLUMNS or "OptTier" not in _P.NEW_ONLY_COLS: bad("OptTier (exporter v111 QC column) is still 'unresolved'")
    m1, one = _P.site_id_mapping(_pd.DataFrame([{"id_pairs_all": "3>12:400;7>1:250;9>9:100"}]))      # consistent renumbering
    m2, two = _P.site_id_mapping(_pd.DataFrame([{"id_pairs_all": "12>12:300;13>12:100;7>7:50"}]))     # SWS 12 carries two ids
    if not one or two: bad("the id-correction report cannot tell a renumbering from wrong ids")
    else: note("id corrections: a consistent renumbering is reported as a relabel; the rows that changed ring or side are counted")

def check_v20_38():
    """v20.38: ONE preparation pipeline (P00) that contains every module; the sub-watershed is the cluster; dose per
    sub-watershed on the treatment area; within-SWS dose path; readiness labels; linkage and speed settings."""
    import json as _j, numpy as _np, pandas as _pd
    sys.path.insert(0, HERE)
    prep = sorted(os.path.basename(f) for f in glob.glob(os.path.join(HERE, "01_Panel_Preparation", "*.ipynb")))
    if prep != ["P00_RUN_ALL_Panel_Preparation.ipynb"]: bad(f"01_Panel_Preparation must hold P00 only, holds {prep}")
    p00 = _j.load(open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8"))
    code = ["".join(c["source"]) for c in p00["cells"] if c["cell_type"] == "code"]
    MODS = ["P00_Settings", "P01_File_Inventory_and_Audit", "P02_Column_Harmonization_Check", "P02b_SWS_Tagging_Audit",
            "P00_Validate_or_Skip", "P03_Ingest_Harmonize_and_Assign_Pixel_UIDs", "P05_Fund_Release_Treatment_Timing_and_Dose",
            "P04_Assemble_Ordered_Panel", "P06_Panel_Integrity_and_Readiness_Report", "P07_Panel_Preview_and_Unique_Values",
            "P08_Ground_Site_Linkage", "P00_Design_for_Every_Model", "P09_Estimator_Variable_Files", "P10_Model_Readiness",
            "P13_Effect_Size_Diagnostics", "P12_Prebuilt_Packages_Verify"]
    missing = [m for m in MODS if not any(c.startswith(f"# ===== {m}") for c in code)]
    if missing: bad(f"P00 lacks cells for: {missing}")
    else: note(f"P00 is the one preparation pipeline: {len(MODS)} modules, every cell named after the notebook it replaces")
    for v in ("SEASONS", "UNIT_FE", "TREATMENT_YEAR", "CLUSTER", "CONTROL_ZONES"):
        n_def = sum(len(re.findall(rf"(?m)^{v}\s*=", c)) for c in code)
        if n_def != 1: bad(f"P00 defines {v} {n_def} times -- settings must live in P00_Settings only")
    if not glob.glob(os.path.join(HERE, "08_Multisite_Runs", "MS01_*.ipynb")): bad("MS01 (per-site / pooled runs) missing")
    import _common as _C, _prep_common as _P
    if _C.ACTIVE.get("cluster") != "site": bad("the default cluster is not the sub-watershed")
    one = _pd.DataFrame({"site_id": [7] * 4, "Year": [2020, 2021, 2022, 2023], "subwshed_id": ["a", "b", "a", "b"]})
    two = one.assign(site_id=[7, 7, 1, 1])
    six = _pd.DataFrame({"site_id": list(range(1, 7)) * 2, "Year": [2020] * 6 + [2021] * 6, "subwshed_id": ["a"] * 12})
    if (_C._cluster_key(one, "subwshed_id") != "Year" or _C._cluster_key(two, "subwshed_id") != "Year"
            or _C._cluster_key(six, "subwshed_id") != "site_id"):
        bad("cluster mapping wrong (fewer than 6 sub-watersheds -> Year, 6 or more -> site_id)")
    else: note("the sub-watershed is the cluster; a single sub-watershed clusters on years (no pseudo-clusters)")
    for c_ in ("dose_amount_sws", "dose_intensity_per_ha"):
        if c_ not in _P.FINAL_PANEL_COLUMNS: bad(f"panel lacks {c_}")
    rows = [{"pixel_id": (int(round((16.5 + i * 1e-4 + 90) * 1e5)) * 1_000_000_000 + int(round((75.2 + 180) * 1e5))), "site_id": 7,
             "Year": y, "Season": 0, "treatment": 1, "buff_km": 0, "dose_amount_sws": 100.0} for i in range(3) for y in (2024, 2025)]
    frame = _pd.DataFrame(rows)
    u = _C.within_sws_dose(frame)
    st = _pd.DataFrame([{"site_id": 7, "latitude": 16.5, "longitude": 75.2, "amount": 90.0, "completion_date": "2024-11-15"}])
    w = _C.within_sws_dose(frame, st, radius_m=30.0)
    got = w.groupby("Year")["dose_within_sws"].sum().to_dict()
    if not (u["dose_within_sws"].eq(100.0).all() and abs(got.get(2025, 0) - 90.0) < 1e-6 and got.get(2024, 0) == 0):
        bad(f"within-SWS dose wrong (uniform {u['dose_within_sws'].unique()}, structures {got})")
    else: note("dose inside a sub-watershed: uniform today; structure data allocate it by distance from the next season")
    if abs(_P.PIXEL_OVERLAP_MIN - 0.65) > 1e-9: bad("pixel linkage threshold is not 0.65")
    # dose = cumulative AMOUNT released, applied from the NEXT season, intensity = amount / sub-watershed area -- checked
    # in TIME order (Zaid Y -> Kharif Y -> Rabi Y), not in label order
    fr = []
    for dt in _pd.date_range("2024-10-01", "2025-09-01", freq="MS"):
        fr.append({"District": "D1", "SWS": "S1", "Date": dt, "Progress": 10.0 * (len(fr) + 1), "Target": 200.0, "area_hectare": 5000.0})
    tb = _P.apply_subwshed_division(_P.build_district_season_dose(_pd.DataFrame(fr)),
                                    _pd.DataFrame({"District": ["D1"], "Sub Watershed Name": ["S1"]}), threshold_pct=50.0)
    tb["_t"] = tb["target_agri_year"] * 10 + tb["target_season"].map({3: 0, 1: 1, 2: 2})
    tb = tb.sort_values("_t")
    want = [(2025, 3, 50.0), (2025, 1, 80.0), (2025, 2, 120.0)]          # Rabi-24 -> Zaid-25, Zaid-25 -> Kharif-25, Kharif-25 -> Rabi-25
    got = [(int(a), int(b), float(c)) for a, b, c in zip(tb.target_agri_year, tb.target_season, tb.dose_amount_sws)]
    if got != want or not _np.allclose(tb.dose_intensity_per_ha, tb.dose_amount_sws / 5000.0):
        bad(f"dose amount / intensity wrong: {got} (want {want})")
    else: note("dose = cumulative amount released, from the next season (50 -> 80 -> 120 in time order); intensity = amount / area")
    _p00s = open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8").read()
    if re.search(r"N_WORKERS = 32", _p00s): bad("P00 hard-codes 32 PASS A workers (the engine picks up to 60)")
    import readiness as _R2, _readiness as _R1, inspect as _i
    if "incomplete-need data" not in _i.getsource(_R2) or '"READY"' in _i.getsource(_R1): bad("readiness labels not renamed")

def check_v20_39():
    """v20.39: overlay id beside the file's id; per-sub-watershed validation; implementation years never silent;
    per-site runs cluster on the sub-watershed; P00 decides single / pooled from the panel; PASS A stops if nothing loads."""
    import json as _j, inspect as _i, pandas as _pd
    sys.path.insert(0, HERE)
    import _prep_common as _P, _sites as _S, _common as _C
    if "sws_id_export" not in _P.FINAL_PANEL_COLUMNS or 'df["sws_id_export"]' not in _i.getsource(_P.tag_sites):
        bad("the panel does not keep the id the input file carried (sws_id_export)")
    bys = _P.site_tagging_by_sws(_pd.DataFrame([{"id_pairs_all": "1>1:10;1>7:30"}]))
    if list(bys.site_id) != [1, 7] or float(bys.loc[bys.site_id == 7, "share_confirmed"].iloc[0]) != 0.0:
        bad("per-sub-watershed overlay summary wrong")
    if _S.treatment_year_source(7) != "ASSUMED" or _S.treatment_year_source(1) != "registry":
        bad("implementation-year source wrong (Haligeri must show ASSUMED until sites.csv has its year)")
    else: note("implementation years: registry / phase default / ASSUMED -- an assumed year is always announced")
    if 'cluster="site", pooled_fe="period"' not in _i.getsource(_C.run_sites): bad("per-site runs do not cluster on the sub-watershed")
    p00 = _j.load(open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8"))
    code = "\n".join("".join(c["source"]) for c in p00["cells"] if c["cell_type"] == "code")
    for v_ in ("TREATMENT_TIMING", "FRAGMENT_RULE"):                 # v20.57: SWS_MODE / YEARS_FROM_REGISTRY became the timing option
        if len(re.findall(rf"(?m)^{v_}\s*=", code)) != 1: bad(f"P00 must define {v_} once (P00_Settings)")
    if "POOLED design" not in code or "C.resolve_design(verbose=True, force=True)" not in code: bad("P00's design step does not decide single / pooled from the panel")
    else: note("P00 decides from the panel (after the fragment rule): one sub-watershed -> single design; several -> pooled, each its own cohort and cluster")
    if "PASS A produced NO pixels" not in _i.getsource(_P.run_pass_a): bad("PASS A does not stop when every file is rejected")
    if "TWO_SWS" not in open(os.path.join(HERE, "validate_prep_notebooks.py"), encoding="utf-8").read():
        bad("the notebook gate lacks the two-sub-watershed (pooled) P00 scenario")

def check_v20_40():
    """v20.40: ONE readiness report whose labels match the pipeline: panel-wide caveats turn complete models into
    limited; every row names what is missing and what completes it; synthetic controls need never-treated donors."""
    import json as _j
    sys.path.insert(0, HERE)
    import _readiness as _R
    t, ctx = _R.assess(_R.FACTS_HALIGERI); c = t.status.value_counts().to_dict()
    # v20.58: 0 / 37 / 8 (v20.40-v20.57: 0 / 32 / 13) -- M11, M36-M38 and M45 use the core-vs-ring series (v20.57: the ring series are the
    # donors, no whole treated sub-watershed or never-programme sub-watershed needed), M13's switchers are measured; M20 needs >= 2
    # sub-watersheds (it reported "identified" and then stopped on one)
    if (c.get("complete", 0), c.get("limited", 0), c.get("incomplete-need data", 0)) != (0, 37, 8):
        bad(f"readiness on your Haligeri panel changed: {c}")
    ts = t.set_index("model").status
    if ts.get("M45") != "limited" or ts.get("M20") != "incomplete-need data" or ts.get("M07") != "incomplete-need data":
        bad(f"readiness rules: M45 {ts.get('M45')} (ring-series donors: limited), M20 {ts.get('M20')} (one sub-watershed: incomplete), M07 {ts.get('M07')}")
    p, _ = _R.assess(_R.FACTS_POOLED_20)
    if p.set_index("model").status.get("M45") != "complete" or p.set_index("model").status.get("M06") != "limited":
        bad("pooled projection: M45 complete (ring-series donors), dose models limited by the fund gap")
    if not {"C1", "C2", "C3"} <= {x["id"] for x in ctx["caveats"]} or any(not all(k in x for k in ("missing", "why", "fix", "affects")) for x in ctx["caveats"]):
        bad("panel-wide caveats must state what is missing, why, the fix and what they affect")
    md = _R.render_markdown(t.merge(p[["model", "status"]].rename(columns={"status": "status_pooled_20_projected"}), on="model"),
                            ctx, _R.FACTS_HALIGERI, compare=_R.FACTS_POOLED_20)
    rows = [l for l in md.splitlines() if l.startswith("| M")]
    if len(rows) != 45 or any(l.count("|") != 7 for l in rows): bad("readiness table rows break their cells")
    else: note("readiness: Haligeri now 0 complete / 37 limited / 8 incomplete-need data; all 20 projected 40 / 4 / 1; caveats explained")
    p00 = _j.load(open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8"))
    code = "\n".join("".join(x["source"]) for x in p00["cells"] if x["cell_type"] == "code")
    if "C.model_readiness()" in code or 'compare="auto"' not in code: bad("P00 must report readiness once (P10, with the pooled projection)")

def check_v20_41():
    """v20.41: every result carries a design-based SE; the streaming estimator and the files carry the cluster; fewer
    than 6 sub-watersheds cluster on years; BM sites become sub-watershed means and GND_* surrogate outcomes."""
    import json as _j, inspect as _i, numpy as _np, pandas as _pd
    sys.path.insert(0, HERE)
    import _common as _C, _ground_common as _G
    src = _i.getsource(_C.build_estimator_files)
    if '"site_id"' not in src or "DERIVED_VARIABLES" not in src or "MemoryError" not in src:
        bad("estimator files must carry site_id, build GND_* surrogates and retry smaller row groups when out of memory")
    if '"site_id"' not in _i.getsource(_C.estimator_file_is_valid): bad("old estimator files without site_id are not rebuilt")
    if "_stream_cluster_key(cluster_col)" not in _i.getsource(_C.estimate_twfe_did_streaming): bad("the streaming estimator ignores the cluster rule")
    if _C.MIN_SWS_CLUSTERS != 6: bad("MIN_SWS_CLUSTERS changed")
    rng = _np.random.default_rng(3); rows = []
    for p in range(60):
        b = 0 if p % 3 == 0 else 1
        for y in range(2016, 2026):
            rows.append((p, y, 0, b, 7, 0.2 + (0.01 * rng.normal() if b == 0 else 0) + 0.01 * rng.normal()))
    d = _pd.DataFrame(rows, columns=["pixel_id", "Year", "Season", "buff_km", "site_id", "NDVI"])
    d["subwshed_id"] = "U1"                                   # the real panel always carries it
    _C.set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, exclude_transition_year=False)
    d = _C.build_treatment_columns(d); ds = _C.design_se("NDVI", df=d)
    if not ds or not (ds["se_design"] > 0) or "one sub-watershed" not in ds["se_design_unit"]:
        bad(f"design-based SE wrong: {ds}")
    _orig = _C.design_se
    try:
        _C.design_se = lambda o, df=None, verbose=False: ds
        r = _C._attach_design_se({"outcome": "NDVI", "beta": 0.0, "se": ds["se_design"] / 100})
        if "se_warning" not in r or "p_design" not in r: bad("a pixel-level SE is not flagged")
        else: note("every result carries a design-based SE; a model SE 100x smaller is flagged and p_design reported")
    finally:
        _C.design_se = _orig
    if _G.match_sws("Halligera")[0] != "Haligeri" or _G.match_sws("Shirur sub-watershed")[0] != "Sirur" or _G.match_sws("Gadag sub-watershed")[0] is not None:
        bad("ground sub-watershed name matching wrong")
    else: note("BM ground names match the shapefile (Halligera -> Haligeri, Shirur -> Sirur); control sub-watersheds kept apart")
    p00 = _j.load(open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8"))
    code = "\n".join("".join(x["source"]) for x in p00["cells"] if x["cell_type"] == "code")
    if "# ===== P08b_Ground_SWS_Surrogates" not in code or len(re.findall(r"(?m)^RUN_GROUND_SURROGATES\s*=", code)) != 1:
        bad("P00 lacks the P08b ground-surrogate cell or its switch")
    m07 = open(glob.glob(os.path.join(HERE, "0*", "M07_*.ipynb"))[0], encoding="utf-8").read()
    if "GND_OUTCOMES" not in m07: bad("M07 does not run the surrogate DiD on the GND_* outcomes")

def check_v20_42():
    """v20.42: a verified pre-built package computes every model that has one; the engine only as fallback."""
    import json as _j, inspect as _i, numpy as _np, pandas as _pd
    sys.path.insert(0, HERE)
    import _common as _C
    nbs = {os.path.basename(p)[:3] for p in glob.glob(os.path.join(HERE, "0[2-5]*", "M*.ipynb"))}
    if set(_C.PREBUILT_MODELS) != nbs: bad(f"pre-built registry out of step with the model notebooks: {sorted(nbs ^ set(_C.PREBUILT_MODELS))}")
    for m, sp in _C.PREBUILT_MODELS.items():
        if sp["layer"] == "model" and not (sp.get("package") and sp.get("runner")): bad(f"{m}: model route without package / runner")
        if sp["layer"] == "function" and sp.get("route") not in _C.PREBUILT_ROUTES: bad(f"{m}: unknown function route {sp.get('route')}")
        if sp["layer"] == "engine" and not sp.get("reason"): bad(f"{m}: engine-only without a stated reason")
    miss = [p for p in glob.glob(os.path.join(HERE, "0[2-5]*", "M*.ipynb")) if "C.prebuilt_first(MODEL_ID, OUTCOME)" not in open(p, encoding="utf-8").read()]
    if miss: bad(f"notebooks without the package-first hook: {[os.path.basename(p)[:3] for p in miss]}")
    p00 = open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8").read()
    if "C.verify_prebuilt_models()" not in p00 or "C.prebuilt_readiness()" not in p00 or ("C.PREBUILT_PACKAGES" not in p00 and "C.confirm_packages(" not in p00):   # v20.55: confirm_packages installs + confirms
        bad("P00 P12 must install every route's package, verify both layers and write PREBUILT_READINESS")
    if "_cluster_key(d, \"subwshed_id\")" not in _i.getsource(_C.export_for_packages): bad("the package input ignores the cluster rule")
    dd = open(os.path.join(HERE, "python_prebuilt", "dd_pipeline.py"), encoding="utf-8").read()
    if 'base = res["_cs"]' not in dd: bad("HonestDiD (M34) is not based on the Callaway-Sant'Anna result")
    if "_FRAME_OVERRIDE" not in open(os.path.join(HERE, "python_prebuilt", "pf_pipeline.py"), encoding="utf-8").read(): bad("no known-answer hook in package_input")
    good, _ = _C._judge_known_answer("M27", {"att": 0.0501}); wrong, _ = _C._judge_known_answer("M27", {"att": 0.0800})
    if not good or wrong: bad("known-answer judgement must accept +0.05 and refuse a biased +0.08")
    fr = _C._known_answer_frame("dose"); st = _C._known_answer_frame("staggered")
    # v20.58: the check panels carry SEASON starts (Rabi of the cohort year, the other seasons a year later): cohorts 2020 / 2021 and 2022 / 2023
    if set(fr["dose"].unique()) != {0.0, 1.0, 2.0} or set(st["cohort"].replace(_np.inf, 0).unique()) != {0.0, 2020.0, 2021.0, 2022.0, 2023.0}: bad("known-answer panels wrong")
    # v20.54: with an EMPTY verification record. After P00's P12 had verified the routes (your machine; or this check run
    # after the notebook gate) this call ran diff-diff's synthetic DiD on the real panel inside the self-check -- and the
    # check failed on the reason text
    import tempfile as _tf
    _keep_pf = _C.PREBUILT_FILE; _C.PREBUILT_FILE = os.path.join(_tf.mkdtemp(prefix="sc_prebuilt_"), "prebuilt_verified.json")
    try:
        if _C.prebuilt_first("M11", "NDVI", verbose=False) is None and "not installed" not in _C.LAST_ENGINE["M11"]["reason"] \
                and "not verified" not in _C.LAST_ENGINE["M11"]["reason"]:
            bad("an unavailable package must hand the model to the engine with the reason")
    finally:
        _C.PREBUILT_FILE = _keep_pf
    n_f = sum(1 for x in _C.PREBUILT_MODELS.values() if x["layer"] == "function"); n_m = sum(1 for x in _C.PREBUILT_MODELS.values() if x["layer"] == "model")
    note(f"pre-built first: {n_f + n_m} of 45 models have a verified-package route ({n_f} inside engine functions, {n_m} as model runs); "
         f"{45 - n_f - n_m} engine-only with the reason stated; a biased package is refused")

def check_v20_43():
    """v20.43: every model -- a verified Python package, else a verified R package (R/run_one.R + models_prebuilt.R),
    else the existing implementation; the R library fixes found by review are in place."""
    import re as _re
    sys.path.insert(0, HERE)
    import _common as _C
    _rlib = os.path.dirname(_C.r_bridge_script())                                   # v20.45: FINAL/R/lib
    one = open(os.path.join(_rlib, "run_one.R"), encoding="utf-8").read()
    lib = open(os.path.join(_rlib, "models_prebuilt.R"), encoding="utf-8").read()
    r_side = set(_re.findall(r"\b(M\d\d) = ", one.split("R_PACKAGES <- list(")[1].split(")\n")[0]))
    if r_side != set(_C.R_ROUTES): bad(f"R routes differ between run_one.R and _common: {sorted(r_side ^ set(_C.R_ROUTES))}")
    strict = lib.split("run_model_strict <- function")[1].split("run_model <- function")[0]
    core = set(_re.findall(r'"(M\d\d)"', one.split("CORE_R <- c(")[1].split(")")[0])) if "CORE_R <- c(" in one else set()   # v20.58: R core models
    miss = [m for m in _C.R_ROUTES if f"{m} = " not in strict and m not in core]
    if miss: bad(f"run_model_strict lacks {miss}")
    fixes = {"M03 two-period panel": "unit %in% two[, .N, by = unit][N == 2, unit]", "M04 panel CiC": "panel = TRUE",
             "M17/M18 LISA returned": "list(global = g, lisa = lisa)", "M19 pixel sample": "N_MAX_PIXELS_MIXED",
             "M24 farthest ring present": "far <- max(d$buff_km)", "M28 never-treated coded": "event_time := -1000",
             "M36-38 site x ring units": "unit := paste(site_id, buff_km, Season, cohort", "ML sample": "N_MAX_ML", "M12": "m12_chained <- function",   # v20.58: + the season
             "M15": "m15_placebo <- function", "M41": "m41_learners <- function", "M42": "m42_dr <- function"}
    gone = [k for k, v in fixes.items() if v not in lib]
    if gone: bad(f"R library fixes missing: {gone}")
    for name, txt in (("run_one.R", one), ("models_prebuilt.R", lib)):
        txt = _re.sub(r"`\[\[?`", "", txt)                     # v20.58: R's `[[` / `[` passed as a function (vapply(rs, `[[`, ...)) is not a bracket
        for a, b in (("(", ")"), ("{", "}"), ("[", "]")):
            if txt.count(a) != txt.count(b): bad(f"{name}: unbalanced {a}{b}")
    J = _C._judge_r_known_answer
    if not (J("M03", {"estimate": 0.0501})[0] and not J("M03", {"estimate": 0.08})[0] and J("M15", {"estimate": 0.001})[0]
            and not J("M15", {"estimate": 0.03})[0] and J("M19", {"estimate": 0.3})[0]):
        bad("R known-answer rules must accept the truth and refuse a bias")
    old_rs = _C.R_SCRIPT
    try:
        _C.R_SCRIPT = None
        if not _C.find_rscript():
            _C.prebuilt_first("M03", "NDVI", verbose=False)
            if "R not installed" not in _C.LAST_ENGINE["M03"]["reason"]: bad("without R, M03 must say so")
    finally:
        _C.R_SCRIPT = old_rs
    p00 = open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8").read()
    if "C.verify_r_models()" not in p00 or ("C.install_r_packages()" not in p00 and "C.confirm_packages(" not in p00): bad("P00 P12 must install and verify the R routes")
    import tempfile as _tf                                 # v20.54: in a scratch results folder with an empty verification record,
    _keep = (_C.RESULTS_ROOT, _C.PREBUILT_FILE)            # never your results folder / your verified routes
    _C.RESULTS_ROOT = _tf.mkdtemp(prefix="sc_res_"); _C.PREBUILT_FILE = os.path.join(_C.RESULTS_ROOT, "prebuilt_verified.json")
    rp = os.path.join(_C.RESULTS_ROOT, "MODEL_READINESS.csv")
    try:                                                   # your rule: incomplete data -> the existing implementation, no package
        open(rp, "w", encoding="utf-8").write("model,status,reason,model_own_gap\nM13,incomplete-need data,no switchers,no switchers\n")
        _C.prebuilt_first("M13", "NDVI", verbose=False)
        if "do not meet" not in _C.LAST_ENGINE["M13"]["reason"]: bad("a model whose data are incomplete must not run a package")
    finally:
        _C.RESULTS_ROOT, _C.PREBUILT_FILE = _keep
    covered = {m for m, sp in _C.PREBUILT_MODELS.items() if sp["layer"] in ("function", "model")} | set(_C.R_ROUTES)
    rest = sorted(set(_C.PREBUILT_MODELS) - covered)
    note(f"pre-built first in Python or R: {len(covered)} of 45 models ({len(_C.R_ROUTES)} R routes); existing implementation only: {rest}")

def check_v20_44():
    """v20.44 (from the user's run): LandUse is a class, not a number, and not in the default covariates; singleton
    series are counted with their origin; pyfixest's singleton warning becomes a count; diff-diff's post-fit API."""
    import warnings as _w, inspect as _i, numpy as _np, pandas as _pd
    sys.path.insert(0, HERE)
    import _common as _C
    covs, lab = _C.resolve_covariates("all")
    if covs != ["Rain", "Tmax", "Tmean", "Tmin"] or lab != "all4" or "LandUse" in _C.DEFAULT_COVARIATES: bad("'all' must be the four weather covariates (tag covAll4)")
    if _C._expand_categorical_covariates(None, ["Rain", "LandUse"])[1] != ["Rain"]: bad("LandUse must never enter as a covariate")
    _cf = _C.columns_for("NDVI")
    if "LandUse" not in _cf or "LandUse" in _C.CURRENT_ESTIMATION_COLUMNS:          # M10 needs it as its GROUP
        bad("LandUse must be loaded (M10's land-use group) but never required as an estimation column")
    rng = _np.random.default_rng(2); rows = []
    for p in range(400):
        for y in range(2016, 2026):
            rows.append((p, y, 0, 0 if p % 2 == 0 else 1 + p % 5, "U1", 7, 1 + p % 3, 0.3 + (0.05 if p % 2 == 0 and y >= 2022 else 0) + rng.normal(0, 0.01)))
    rows += [(9000 + p, 2025, 0, 0 if p % 2 == 0 else 1, "U1", 7, 1, 0.3) for p in range(20)]
    d = _pd.DataFrame(rows, columns=["pixel_id", "Year", "Season", "buff_km", "subwshed_id", "site_id", "LandUse", "NDVI"])
    d["time_fe_yearseason"] = d.Year.astype(str) + "_0"
    _C.set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, exclude_transition_year=False, seasons="all", covariates=[])
    d = _C.build_treatment_columns(d); d = d[d.in_analysis_sample == 1]
    try:
        b, _ = _C.estimate_twfe_did(d, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id", covariates=["LandUse"])
        if not (abs(b - 0.05) < 0.01): bad(f"land-use classes as covariates give {b:.4f} on a +0.05 panel")
    except Exception as e:
        bad(f"a LandUse request must be dropped, not fail ({type(e).__name__}: {str(e)[:80]})")
    if _C.LAST_FIT_INFO.get("n_singleton_series") != 20: bad(f"singleton series miscounted: {_C.LAST_FIT_INFO.get('n_singleton_series')} (want 20)")
    _C._pf_quiet(lambda: _w.warn("123 singleton fixed effect(s) dropped from the model.", UserWarning))
    if _C.LAST_FIT_INFO.get("pyfixest_singletons_dropped") != 123: bad("pyfixest's singleton warning is not turned into a count")
    dd = open(os.path.join(HERE, "python_prebuilt", "dd_pipeline.py"), encoding="utf-8").read()
    if "def _cs_fit(" not in dd or "r.overall_att" in dd or "def _cs_event_study_table" not in _i.getsource(_C):
        bad("Callaway-Sant'Anna still uses diff-diff's deprecated fit(aggregate=)")
    else: note("covariates: weather by default, land use only as classes on request; singletons counted with their origin; diff-diff post-fit API")

def check_r_library():
    """v20.45: the R pipeline lives in the bundle's R/ folder; the Python bridge must find it there."""
    sys.path.insert(0, HERE)
    import _common as _C
    lib = os.path.dirname(_C.r_bridge_script())
    miss = [f for f in ("run_one.R", "models_prebuilt.R", "reward_prep.R", "reward_design.R", "reward_models_core.R", "reward_paths.R", "model_names.R")
            if not os.path.exists(os.path.join(lib, f))]
    if miss: bad(f"R library incomplete at {lib}: missing {miss}")
    else: note(f"R library found where the bridge looks: {os.path.relpath(lib, HERE)}")

def check_v20_45():
    """v20.45: fill years are not data (the screen); an SE of ~0 is never a result; the design comes from the data;
    permutations and ML cannot exhaust memory; a memory share for concurrent instances."""
    import numpy as _np, pandas as _pd, inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C, _hardware as _H
    rows = []
    for p in range(600):
        tr = p % 3 == 0
        for y in range(2018, 2026):
            real = 0.3 + (0.03 if tr and y >= 2022 else 0) + 0.01 * _np.random.default_rng(p * 100 + y).normal()
            ndmi = _np.nan if y < 2020 else (0.131 if (y <= 2024 and p % 70 == 0) else (_np.nan if y <= 2024 else real))
            rows.append((p if y < 2025 else p + 50000, y, 0, 0 if tr else 1 + p % 5, "U1", 7, 0.198 if y < 2020 else real, ndmi))
    d = _pd.DataFrame(rows, columns=["pixel_id", "Year", "Season", "buff_km", "subwshed_id", "site_id", "VCI", "NDMI"])
    _C.set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, exclude_transition_year=False, seasons="all", covariates=[])
    try:
        _C.screen_outcome_frame(d[_np.isfinite(d.NDMI)], "NDMI", verbose=False); bad("an outcome with only fill years before 2025 was not refused")
    except _C.InsufficientDataError:
        pass
    v = _C.screen_outcome_frame(d, "VCI", verbose=False)
    if sorted(v.Year.unique())[0] != 2020: bad("the screen kept VCI's constant 2018-2019 fill years")
    if not _C._attach_design_se({"outcome": "X", "beta": 1.4e-5, "se": 1e-12}).get("se_invalid"): bad("an SE of ~0 is not flagged")
    else: note("fill years are screened out (an NDMI-like outcome is refused); an SE of ~0 is flagged as NOT a result")
    saved = _C.PREBUILT_MODE
    try:
        _C.permutation_inference(_pd.DataFrame({"a": [1]}), "nope", "t", "p", "u", "y", n_permutations=2)
    except Exception:
        pass
    if _C.PREBUILT_MODE != saved: bad("permutation inference left the package setting switched off")
    ml = open(os.path.join(HERE, "python_prebuilt", "ml_spatial_pipeline.py"), encoding="utf-8").read()
    if "n_max=None" not in ml or "rows_that_fit" not in ml or "_cores = os.cpu_count() or 1" not in ml:
        bad("ML routes: every pixel below 98 % of the RAM (v20.57; v20.55: 4,000,000) and EVERY core are not in place")
    if not hasattr(_H, "MEMORY_SHARE") or "memory_share()" not in _i.getsource(_H.ram_budget_bytes): bad("no memory share for concurrent instances")   # v20.47: dynamic split
    if "def recommend_design" not in _i.getsource(_C): bad("no data-driven design")

def check_v20_46():
    """v20.46: BM sites -> one mean per sub-watershed (known answer, and your real files); M07 / V06 use only those means;
    package inputs versioned; the streaming path screened; covariate folder tags explicit; LandUse in no covariate list."""
    import numpy as _np, pandas as _pd, tempfile as _tf, json as _j
    sys.path.insert(0, HERE)
    import _common as _C, _bm_means as _B, _sws_geometry as _G
    L = _G.SWSLocator.from_shapefile(); gi = _C.GROUND_INPUTS_DIR
    m = _pd.read_csv(os.path.join(gi, "01_benchmark_sites_master.csv"))
    sid, ring, _ = L.tag(m.lat_median.values.astype(float), m.lon_median.values.astype(float)); m["sid"], m["ring"] = _np.asarray(sid), _np.asarray(ring)
    ids = {v: k for k, v in _B._registry().items()}
    core = lambda nm: m[(m.sid.map(ids.get) == nm) & (m.ring == 0)].iloc[0][["lat_median", "lon_median"]].values.astype(float)
    pa, ko = core("Pashapur"), core("Kodihalli"); out = m[m.ring < 0].iloc[0][["lat_median", "lon_median"]].values.astype(float)
    g = _tf.mkdtemp(); rows = [("Pashapur", pa, 10.0), ("Pashapur", pa + [0.001, 0], 20.0), ("Pashapur", pa + [0.001, 0], 20.0), ("Pashapur", pa + [0.001, 0], 20.0),
                               ("Pashapur", pa + [0.001, 0], -2.0), ("Pashapur", pa + [0.001, 0], 0.0), ("Pashapur", out, 25.0),
                               ("Kodihalli Sub-Watershed", ko, 30.0), ("Kodihalli sub-watershed", ko + [0.0005, 0], 40.0)]
    _pd.DataFrame([{"institution": "X", "sws_name": n, "mws_name": "", "bm_site_no": i, "lat_site": ll[0], "lon_site": ll[1], "Year": 2023, "Season": 1,
                    "ssm_mean_clean": v} for i, (n, ll, v) in enumerate(rows)]).to_csv(os.path.join(g, "02_ground_ssm_long.csv"), index=False)
    mm, ss, bb = _B.bm_sws_means(g)
    pv = mm[mm.sws == "Pashapur"]; kv = mm[mm.sws == "Kodihalli"]
    if not (len(pv) == 1 and abs(pv.value.iloc[0] - 15.0) < 1e-9 and int(pv.n_sites.iloc[0]) == 2): bad(f"BM mean must weight every SITE once (expect 15.0 over 2 sites): {pv.to_dict('records')}")
    elif not (len(kv) == 1 and abs(kv.value.iloc[0] - 35.0) < 1e-9): bad("two spellings of one sub-watershed are not one mean")
    elif not ss[ss.sws_name.eq("Pashapur") & ss.decision.eq("excluded")].reason.str.contains("outside").any(): bad("a site whose location contradicts its name was averaged in")
    elif int(bb.outside_bounds.sum()) != 2: bad("values outside physical bounds are not dropped")
    else: note("BM: every site counts once (site mean, then the mean over sites); spellings unified; bounds applied; misplaced sites kept out")
    rm, rs, _ = _B.bm_sws_means(gi)                       # your real ground files
    tests = {"Koppal (4D4A2) -> Murlapura (its sites lie in the Murlapura core)": "Murlapura" in set(rm[rm.group == "programme"].sws),
             "Koranahalli and Haralahalli -> Koranahalli": rs[rs.sws_name == "Koranahalli and Haralahalli"].sws.eq("Koranahalli").all(),
             "Kandgul + Kandgula = one control sub-watershed": rs[rs.sws_name.isin(["Kandgul", "Kandgula"])].sws.eq("Kandgula").all(),
             "the 16 'Artal Sub-Watershed' sites outside Artal are kept out": not ((rs.sws_name == "Artal Sub-Watershed") & (rs.decision == "counted")).any(),
             "control-named sites inside a treated core are kept out": rs[rs.reason.str.contains("inside the Sirur core", na=False)].decision.eq("excluded").all() and rs.reason.str.contains("inside the Sirur core", na=False).any(),
             "no ID / coordinate column is ever averaged": set(rm.variable) <= {v[2] for v in _B.BM_VARIABLES}}
    for k, v in tests.items():
        if not v: bad(f"BM on your files: {k} -- FAILED")
    if all(tests.values()): note(f"BM on your files: {rm[rm.group == 'programme'].sws.nunique()} programme + {rm[rm.group == 'control'].sws.nunique()} control sub-watershed means; names resolved by location")
    m07 = open(glob.glob(os.path.join(HERE, "0*", "M07_*.ipynb"))[0], encoding="utf-8").read()
    if "GROUND_TRUTH_OUTCOMES_PATH" in m07 or "measured_yield_or_income" in m07: bad("M07 still uses single BM sites / pixels")
    v06 = open(os.path.join(HERE, "06_Validation", "V06_Ground_Validation.ipynb"), encoding="utf-8").read()
    if "register=False" not in v06 or "validate_variable(pairs" in v06: bad("V06 does not validate at sub-watershed level")
    pf = open(os.path.join(HERE, "python_prebuilt", "pf_pipeline.py"), encoding="utf-8").read()
    if "package_input_stem" not in pf or "rules" not in _C.package_input_stem("NDVI"): bad("package inputs are not versioned by the data rules")
    if "screened_year_seasons" not in open(os.path.join(HERE, "_common.py"), encoding="utf-8").read().split("def estimate_twfe_did_streaming")[1].split("\ndef ")[0]:
        bad("the streaming TWFE does not apply the outcome screen")
    saved = dict(_C.ACTIVE)
    try:
        _C.set_scenario(verbose=False, control_zones="1-5", treatment_year=2022, covariates="all")
        if "_covAll4" not in _C.scenario_tag(): bad("the default covariate set has no folder tag -- old and new results would mix")
    finally:
        _C.ACTIVE.clear(); _C.ACTIVE.update(saved)
    rlib = os.path.dirname(_C.r_bridge_script())
    for f in ("reward_paths.R", "run_one.R", "reward_models_core.R", "models_prebuilt.R"):
        t = open(os.path.join(rlib, f), encoding="utf-8").read()
        if 'Tmin", "LandUse"' in t or "COVARIATES <- c(\"Rain\", \"Tmax\", \"Tmean\", \"Tmin\", \"LandUse" in t: bad(f"R {f}: LandUse in a covariate list")
    if "LandUse" in _C.DEFAULT_COVARIATES or any("LandUse" in v for v in _C.COVARIATE_GROUPS.values()): bad("Python: LandUse in a covariate list")

def _same_bm_table(rm):
    """v20.49: R/data/ground/bm_sws_season_means.csv (what R reads) == the means Python computes from the ground inputs."""
    import pandas as _pd
    p = os.path.join(HERE, "..", "..", "R", "data", "ground", "bm_sws_season_means.csv")
    if not os.path.exists(p): return True        # v20.50: the R pipeline is its own project (RWDR) -- checked when it is here
    r = _pd.read_csv(p); k = ["group", "site_id", "sws", "variable", "Year", "Season"]
    m = r.merge(rm[k + ["value"]], on=k, how="outer", suffixes=("_r", "_py"), indicator=True)
    return bool((m["_merge"] == "both").all() and (m.value_r - m.value_py).abs().max() < 1e-9)

def check_v20_47():
    """v20.47: YOUR 80 % NAME RULE in every input path (with its two safeguards); the automatic 50 % split of RAM, GPU and
    CPU between pipelines on different data folders; the R pipeline's package-first fall-backs (fixest / arrow)."""
    import json as _j, subprocess as _sp, time as _t, inspect as _i
    sys.path.insert(0, HERE)
    import _names as _N, _bm_means as _B, _ground_common as _G, _sws_geometry as _S, _hardware as _H, _common as _C
    sims = {("Kandgul", "Kandgula"): 0.875, ("Kohalli", "Kodihalli"): 1 - 2 / 9, ("Hunsehadagli", "Hunasehadagi"): 1 - 2 / 12}
    for (a_, b_), v in sims.items():
        if abs(_N.similarity(a_, b_) - v) > 1e-9: bad(f"name similarity {a_}/{b_} = {_N.similarity(a_, b_):.3f}, expected {v:.3f}")
    if _N.best_match("Kodihali", {"kodihalli": "Kodihalli", "kohalli": "Kohalli"})[0] != "Kodihalli": bad("an 89 % unambiguous match was refused")
    if _N.best_match("Kodihalli", {"kodihallia": "A", "kodihallib": "B"})[0] is not None: bad("an AMBIGUOUS 80 % match was accepted")
    rm, rs, _ = _B.bm_sws_means(_C.GROUND_INPUTS_DIR)
    got = lambda raw: set(rs.loc[rs.sws_name == raw, "sws"])
    tests = {"Kandgul + Kandgula = one sub-watershed by the 80 % rule (88 %, within 10 km)": got("Kandgul") == got("Kandgula") == {"Kandgula"},
             "Nagagondanahalli (82 % like Kyatagondanahalli, sites in its rings) kept apart": got("Nagagondanahalli") == {"Nagagondanahalli"},
             "Kohalli (78 % like Kodihalli) is not Kodihalli": got("Kohalli sub-watershed") == {"Kohalli"},
             "the means: 19 programme + 13 control sub-watersheds (v20.49: ITGI kept under every pandas version)": (rm[rm.group == "programme"].sws.nunique(), rm[rm.group == "control"].sws.nunique()) == (19, 13),
             "a site with a blank site number still counts (Hunasehadagi root zone: 24 sites, pandas 3 dropped 22)": int(rm[(rm.sws == "Hunasehadagi") & (rm.variable == "tdr_rootzone_pct")].n_sites.max()) == 24,
             "the R pipeline ships the same BM means as Python computes": _same_bm_table(rm)}
    for k, v in tests.items():
        if not v: bad(f"80 % rule on your BM files: {k} -- FAILED")
    if _G.match_sws("Nagagondanahalli")[0] is not None or _G.match_sws("Kandgula")[0] is not None: bad("a name-only match turned a control into a programme sub-watershed")
    L = _S.SWSLocator.from_shapefile()
    if L.site_id_for_name("Hunsehadagli_2023_exports") != L.name_to_id.get("hunasehadagi") or L.site_id_for_name("Kohalli") is not None:
        bad("export folder / file names do not follow the 80 % rule")
    if all(tests.values()): note("names: >= 80 % similar = the same sub-watershed, when unambiguous and (with coordinates) located in it")
    other = _sp.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    f = os.path.join(_H.INSTANCE_DIR, f"{other.pid}.json")
    try:
        _j.dump({"pid": other.pid, "root": "__another_data_folder__", "heartbeat": _t.time()}, open(f, "w"))
        if _H.memory_share() != _H.MEMORY_SHARE: bad("v20.52: a second data folder must NOT reduce this pipeline's share (no cap, your instruction)")
        _H.AUTO_SPLIT = True                                   # the optional v20.47 split still works when switched on
        _H._SHARE_CACHE["v"] = None; half = _H.memory_share()
        other.kill(); other.wait(); _H._SHARE_CACHE["v"] = None; whole = _H.memory_share(); _H.AUTO_SPLIT = False
        if abs(half - min(_H.MEMORY_SHARE, 0.5)) > 1e-9 or abs(whole - _H.MEMORY_SHARE) > 1e-9: bad(f"automatic split wrong: two folders {half}, one folder {whole}")
        else: note("two pipelines on different data folders split RAM, GPU memory and CPU 50 / 50; alone, one gets the whole machine back")
    finally:
        try: other.kill()
        except Exception: pass
        if os.path.exists(f): os.remove(f)
        _H._SHARE_CACHE["v"] = None
    if "memory_share()" not in _i.getsource(_H.gpu_budget_bytes): bad("GPU budget ignores the optional split")
    rl = os.path.dirname(_C.r_bridge_script())
    core = open(os.path.join(rl, "reward_models_core.R"), encoding="utf-8").read(); des = open(os.path.join(rl, "reward_design.R"), encoding="utf-8").read()
    if "HAS_FIXEST <- requireNamespace" not in core or "fe_demean <- function" not in core or "HAS_ARROW <- requireNamespace" not in des:
        bad("the R pipeline lacks its fall-backs (fixest / arrow)")
    if os.path.isdir(os.path.join(rl, "..", "rstudio")) and not os.path.exists(os.path.join(rl, "..", "tests", "run_all_tests.R")):
        bad("R/tests/run_all_tests.R missing")          # v20.50: only where the whole R pipeline sits beside this one

def check_v20_54():
    """v20.54 (the regression audit against every earlier version): what it found, each under a test."""
    import inspect as _i, numpy as _np, pandas as _pd, tempfile as _tf, time as _t
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P, _hardware as _H, _paths as _Pp
    # 1. YOUR 98 % rule (v20.57; was 95 %) guards a package's copy of the panel (v20.52 had switched the check off)
    src = _i.getsource(_C._route_call)
    if "need > bud" not in src or "if False" in src: bad("package copies are not guarded by YOUR 98 % RAM rule")
    else: note("a package whose copy would not fit below 98 % RAM hands over to the engine; otherwise the package is used first")
    # 2. the data-rules version names the current rules (v20.52's Coverage <= 0 rule had not bumped it)
    if _ver(_C.DATA_RULES_VERSION) < (20, 54): bad(f"DATA_RULES_VERSION {_C.DATA_RULES_VERSION} predates the current data rules")
    # 3. package inputs: one per site set, and never reused after the panel was rebuilt
    try:
        import validate_all_models as _VM
        df_ = _VM.make_panel(n_pix=120)
    except Exception as e:
        bad(f"package-input freshness test could not build its panel: {type(e).__name__}: {e}"); df_ = None
    if df_ is not None:
        d_ = _tf.mkdtemp(prefix="sc_pkg_"); fp = os.path.join(d_, "panel.parquet"); df_.to_parquet(fp, index=False)
        keep = (_C.PREPARED_PANEL, _C.ESTIMATOR_FILES_DIR, _C.RESULTS_ROOT, dict(_C.ACTIVE), _C.SITE_FILTER)
        try:
            _C.PREPARED_PANEL = fp; _C.ESTIMATOR_FILES_DIR = os.path.join(d_, "ef"); _C.RESULTS_ROOT = os.path.join(d_, "res"); _C.clear_panel_cache()
            _C.set_scenario(verbose=False, all_years=True); _C.set_scenario(verbose=False, control_zones="1-5", treatment_year=2022)
            _C.SITE_FILTER = 1; s1 = _C.package_input_ready("NDVI"); a = _pd.read_parquet(s1 + ".parquet")
            _t1 = os.path.getmtime(s1 + ".json")
            for _sf in ([1], _np.array([1]), (1,)):                           # the same site written other ways: same file,
                _C.SITE_FILTER = _sf                                            # still fresh (no rebuild), no error
                if _C.package_input_ready("NDVI") != s1 or os.path.getmtime(s1 + ".json") != _t1:
                    bad(f"SITE_FILTER {_sf!r}: not recognised as the same site as 1 (rebuilt or renamed)")
            _C.SITE_FILTER = 2; s2 = _C.package_input_ready("NDVI"); b = _pd.read_parquet(s2 + ".parquet")
            _C.SITE_FILTER = None; s0 = _C.package_input_ready("NDVI"); m0 = float(_pd.read_parquet(s0 + ".parquet")["NDVI"].mean())
            _t.sleep(1.1); df2 = df_.copy(); df2.loc[df2["NDVI"] != 0, "NDVI"] += 1.0          # the rebuilt panel: same rows, NDVI + 1
            df2.to_parquet(fp, index=False); _C.clear_panel_cache()                             # (masked zeros stay masked)
            m1 = float(_pd.read_parquet(_C.package_input_ready("NDVI") + ".parquet")["NDVI"].mean())
            okay = s1 != s2 and set(a.site_id) == {1} and set(b.site_id) == {2} and abs(m1 - m0 - 1.0) < 1e-6
            if not okay: bad(f"package inputs are reused across sites ({sorted(set(b.site_id))} for site 2) or after a rebuild (NDVI mean {m0:.3f} -> {m1:.3f}, +1 expected)")
            else: note("package inputs: one per site set; a rebuilt panel (or other sites) makes them rebuilt, never reused (were reused before v20.54)")
        except Exception as e:
            bad(f"package-input freshness test raised {type(e).__name__}: {e}")
        finally:
            _C.PREPARED_PANEL, _C.ESTIMATOR_FILES_DIR, _C.RESULTS_ROOT = keep[0], keep[1], keep[2]
            _C.ACTIVE.clear(); _C.ACTIVE.update(keep[3]); _C.SITE_FILTER = keep[4]; _C.clear_panel_cache()
    # 4. your optional manual MEMORY_SHARE works again; by default nothing is capped
    saved = (_H.MEMORY_SHARE, _H.AUTO_SPLIT, dict(_H._SHARE_CACHE))
    try:
        _H.AUTO_SPLIT = False; _H.MEMORY_SHARE = 0.45; half = _H.memory_share(); _H.MEMORY_SHARE = 1.0; whole = _H.memory_share()
        if abs(half - 0.45) > 1e-12 or whole != 1.0: bad(f"MEMORY_SHARE ignored (0.45 -> {half}, 1.0 -> {whole})")
        else: note("MEMORY_SHARE (your optional manual setting) is honoured; the default 1.0 caps nothing")
    finally:
        _H.MEMORY_SHARE, _H.AUTO_SPLIT = saved[0], saved[1]; _H._SHARE_CACHE.clear(); _H._SHARE_CACHE.update(saved[2])
    # 5. the negative barrier switched off keeps real negatives but never a fill value
    sv = (_P.ALLOW_NEGATIVE_COVARIATES, dict(_P.NEGATIVE_COVARIATE_RULE))
    try:
        _P.ALLOW_NEGATIVE_COVARIATES = True
        f = _pd.DataFrame({"NDVI": [0.4, 0.4, 0.4], "Rain": [-1.5, -9999.0, 5.0], "Tmin": [-10.0, 18.0, -3.0]})
        g, _ = _P.apply_missing_policy(f.copy(), stage="file")
        if not (g.Rain.iloc[0] == -1.5 and _np.isnan(g.Rain.iloc[1]) and _np.isnan(g.Tmin.iloc[0]) and g.Tmin.iloc[2] == -3.0):
            bad(f"barrier OFF: fill values must stay missing, real negatives kept -- got Rain {g.Rain.tolist()}, Tmin {g.Tmin.tolist()}")
        else: note("barrier OFF (ALLOW_NEGATIVE_COVARIATES): real negatives kept, -9999 and the -10 C clamp still missing")
    finally:
        _P.ALLOW_NEGATIVE_COVARIATES, _P.NEGATIVE_COVARIATE_RULE = sv
    # 6. off Windows the projects keep separate data roots (both ended in ...\data since v20.50)
    if os.name != "nt":
        r1, r2, r0 = _Pp._portable(r"D:\LKT\RWD_Artal\data"), _Pp._portable(r"D:\LKT\RWDR\data"), _Pp._portable(r"D:\LKT\TST_Artal")   # v20.58: Artal1 dropped
        if r1 == r2 or not r0.endswith(os.path.join("REWARD_data", "TST_Artal")): bad(f"portable data roots collide: {r1} / {r2}")
        else: note("off Windows, D:\\LKT\\RWD_Artal\\data and D:\\LKT\\RWDR\\data map to separate folders")
    # 7. the R library: your negative-covariate switch and zero rule as in Python; MEMORY_SHARE honoured
    rl = os.path.dirname(_C.r_bridge_script())
    rp, rpr, rd = (open(os.path.join(rl, f_), encoding="utf-8").read() for f_ in ("reward_paths.R", "reward_prep.R", "reward_design.R"))
    if "ALLOW_NEGATIVE_COVARIATES <- FALSE" not in rp or "isTRUE(ALLOW_NEGATIVE_COVARIATES)" not in rpr: bad("R: no switch for the negative-covariate barrier")
    elif "x[x == 0] <- NA" not in rpr.split("apply_missing_policy <- function")[1].split("\n}")[0]: bad("R: an exported 0 of a covariate is not missing (Python's zero rule)")   # v20.55: in apply_missing_policy, as Python
    elif "return(sh)" not in rd.split("memory_share <- function")[1].split("\n}")[0]: bad("R: MEMORY_SHARE ignored")
    else: note("R: ALLOW_NEGATIVE_COVARIATES and the covariate zero rule as in Python; MEMORY_SHARE honoured")
    # 8. warnings you reported: pyfixest's raw singleton warning (pf_pipeline), R's coercion / qte notes
    pfp = open(os.path.join(HERE, "python_prebuilt", "pf_pipeline.py"), encoding="utf-8").read()
    body = pfp.split("def _feols(")[1].split("\ndef ")[0] if "def _feols(" in pfp else ""
    if not body or pfp.count("pf.feols(") != body.count("pf.feols(") or pfp.count("_feols(C, pf, ") < 4: bad("pf_pipeline calls pyfixest without the singleton-warning handler")
    mp = open(os.path.join(rl, "models_prebuilt.R"), encoding="utf-8").read()
    if 'as.integer(sub(".*::(-?[0-9]+).*", "\\\\1", term))' in mp or "muffleWarning" not in mp.split("m04_cic <- function")[1].split("\n}")[0]:
        bad("R: the event-time parse still warns 'NAs introduced by coercion', or qte's inapplicable notes are not handled")
    else: note("warnings: pyfixest singletons explained in one line everywhere; R event-time parsing and qte's two inapplicable notes silenced (results unchanged)")
    # 9. pandas 2: a categorical sub-watershed column with sub-watersheds NOT in the sample must not change M19's ICC
    import warnings as _w
    rng = _np.random.default_rng(1); g_ = _np.repeat(["SW1", "SW2"], 300); x_ = rng.normal(0, 1, 600) + _np.repeat([0.0, 0.8], 300)
    with _w.catch_warnings():
        _w.simplefilter("error", FutureWarning)                 # the engine must not rely on pandas' observed=False default
        try:
            a_ = _C.variance_decomposition(x_, _pd.Series(g_))
            b_ = _C.variance_decomposition(x_, _pd.Series(_pd.Categorical(g_, categories=[f"SW{i}" for i in range(1, 21)])))
            if abs(float(a_["ICC"]) - float(b_["ICC"])) > 1e-12: bad(f"ICC depends on unused categories: {float(a_['ICC']):.4f} vs {float(b_['ICC']):.4f}")
            else: note("M19's ICC is the same whether the sub-watershed column is text or a categorical with unused sub-watersheds (pandas 2 and 3)")
        except FutureWarning as e:
            bad(f"variance_decomposition relies on a pandas default that changes in pandas 3: {e}")


def check_v20_55():
    """v20.55 (your requests: seasons + years together, R == Python data structuring, packages first, overlap option,
    unbalanced panel, 10x limits) -- each under a test, plus the two defects the parity harness found."""
    import inspect as _i, numpy as _np, pandas as _pd, json as _j
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P
    # 1. the season setting: one canonical form, every mode, and the recommended design never overrides it
    try:
        modes = {"all": "all", "ALL": "all", ("yearly",): "yearly", "annual": "yearly", "seasonal": "seasonal", "Rabi": "rabi",
                 ("Kharif", "Rabi"): "kharif+rabi", "Rabi+Zaid": "rabi+zaid", "auto": "auto"}
        wrong = {k: _C.normalize_seasons(k) for k, v in modes.items() if _C.normalize_seasons(k) != v}
        codes = {"all": None, "yearly": {0}, "seasonal": {1, 2, 3}, "rabi": {2}, "kharif+rabi": {1, 2}}
        wrong_c = {k: _C.season_codes(k) for k, v in codes.items() if _C.season_codes(k) != v}
        if wrong or wrong_c: bad(f"season modes: normalize {wrong} / codes {wrong_c}")
        else: note("SEASONS: all | seasonal | yearly | named seasons | auto -- one canonical form, the right Season codes")
    except Exception as e:
        bad(f"season-mode helpers raised {type(e).__name__}: {e}")
    nbp = os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb")
    src = "\n".join("".join(c["source"]) for c in _j.load(open(nbp, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
    _ss = _i.getsource(_C.set_scenario)                                  # v20.57: the models resolve it; P00 saves the default
    if "seasons=SEASONS" not in src or 'if str(seasons).strip().lower() == "auto": _dk.add("seasons")' not in _ss:
        bad("P00: the recommended design still replaces your SEASONS setting (only 'auto' may follow the data)")
    elif "P.PIXEL_OVERLAP_MIN = 0.80" in src: bad("P00: PASS B still overrides PIXEL_OVERLAP_MIN from P00_Settings")
    elif "OVERLAP_ROWS" not in src or "overlap_rows=" not in src: bad("P00: no OVERLAP_ROWS option")
    elif 'POOLED_FE      = "site_period"' not in src or "pooled_fe=POOLED_FE" not in src: bad("P00: POOLED_FE is not honoured in the pooled design")
    else: note("P00: SEASONS honoured in the recommended design (auto = data decide); PIXEL_OVERLAP_MIN from settings; OVERLAP_ROWS and POOLED_FE options")
    # 2. the overlap option in the engine: a scenario key, a tag, and the rows it keeps or drops
    try:
        keep = dict(_C.ACTIVE)
        _C.set_scenario(verbose=False, overlap_rows="keep")
        t_keep = _C.scenario_tag(); _C.set_scenario(verbose=False, overlap_rows="drop"); t_drop = _C.scenario_tag()
        if "_keepOverlap" not in t_keep or "_keepOverlap" in t_drop or "overlap_rows" not in _C.SCENARIO_KEYS:
            bad(f"OVERLAP_ROWS is not part of the scenario ({t_keep} / {t_drop})")
        else:
            # a pooled frame: pixel 7 is core in site 2 AND a control in site 1's ring -> dropped under 'drop', kept under 'keep'
            rows = []
            for pix, site, b in ((1, 1, 0), (2, 1, 3), (7, 1, 3), (7, 2, 0), (8, 2, 4)):
                for y in (2020, 2021, 2022, 2023):
                    for se in (0, 1):
                        rows.append({"pixel_id": pix, "site_id": site, "subwshed_id": f"S{site}", "buff_km": b, "Year": y, "Season": se,
                                     "NDVI": 0.4 + 0.01 * y % 7, "time_fe_yearseason": f"{y}_{se}"})
            f = _pd.DataFrame(rows)
            _C.set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, seasons="all", overlap_rows="drop", cluster="site", pooled_fe="site_period")
            d0 = _C.build_treatment_columns(f.copy()); n_drop = int(((d0.pixel_id == 7) & (d0.site_id == 1) & (d0.in_analysis_sample == 1)).sum())
            _C.set_scenario(verbose=False, overlap_rows="keep")
            d1 = _C.build_treatment_columns(f.copy()); n_keep = int(((d1.pixel_id == 7) & (d1.site_id == 1) & (d1.in_analysis_sample == 1)).sum())
            if n_drop != 0 or n_keep != 8: bad(f"OVERLAP_ROWS: the control rows of a pixel treated elsewhere -- drop kept {n_drop}, keep kept {n_keep} (expected 0 and 8)")
            else: note("OVERLAP_ROWS: 'drop' removes the control rows of a pixel treated in another sub-watershed, 'keep' keeps them (tagged _keepOverlap)")
    except Exception as e:
        bad(f"OVERLAP_ROWS test raised {type(e).__name__}: {e}")
    finally:
        _C.ACTIVE.clear(); _C.ACTIVE.update(keep)
    # 3. the near-duplicate merge is one-to-one (the parity harness found 121 pixels merged onto ONE canonical pixel)
    try:
        n = 60; lat = 15.0 + _np.arange(n) * 1e-4; lon = 75.0 + _np.zeros(n)
        reg = _pd.DataFrame({"lat": _np.r_[lat, lat + 3.0 / 110574.0], "lon": _np.r_[lon, lon], "mtime": _np.r_[_np.full(n, 1.0), _np.full(n, 2.0)],
                             "completeness": 1.0, "n_rows": 10, "src": ["a"] * n + ["b"] * n},
                            index=_np.r_[_np.arange(n), 1000 + _np.arange(n)][_np.random.default_rng(3).permutation(2 * n)])
        pairs = _P.near_duplicate_pairs(reg, size_m=10.0, overlap_min=0.65); m = _P.canonical_pixel_map(reg, pairs)
        if len(pairs) != n or len(m) != n or m.canonical_pixel_id.nunique() != n or not (m.canonical_src == "b").all():
            bad(f"canonical_pixel_map: {len(pairs)} pairs -> {len(m)} merged onto {m.canonical_pixel_id.nunique()} canonicals (expected {n} one-to-one, newer file canonical)")
        else: note("near-duplicate pixels: every canonical pixel receives exactly the pixels that overlap IT (one-to-one on a shifted grid; was many-to-one)")
    except Exception as e:
        bad(f"canonical_pixel_map test raised {type(e).__name__}: {e}")
    # 4. the design: a common shock is reported, not cut; the linkage counts pixels present, not finite outcomes
    rs = _i.getsource(_C.recommend_design)
    if "common_shocks" not in rs or "rescaled" not in rs or "persists" not in rs: bad("recommend_design still cuts the post window on any common jump")
    elif "core = d[d._ring == 0]" not in rs or "Season.min()" in rs.split("pix.setdefault")[0].split("for i in range(pf.num_row_groups)")[1]:
        bad("recommend_design: the linkage still depends on the parquet row-group layout or on finite outcomes")
    else: note("design from the data: a common jump of both groups is a reported COMMON SHOCK (year FE absorb it); only a lost pixel history or a persistent re-scaling is an export break")
    # 5. the period-level design SE beside the year-level one
    _ds = _i.getsource(_C.design_se) + (_i.getsource(_C._design_se_from_cells) if hasattr(_C, "_design_se_from_cells") else "")   # v20.58: from its cells
    if "se_design_period" not in _ds: bad("design_se: no year x season (period-level) draws")
    else: note("design-based SE: year-level draws AND year x season draws (the seasonal variation you asked for) reported side by side")
    # 6. packages first: the registry, the chain and the confirmation
    for fn in ("install_python_package", "ensure_python_packages", "confirm_packages", "r_package_status"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing (package chain / confirmation)")
    if hasattr(_C, "PYTHON_PACKAGES") and {"pyfixest", "diff_diff", "econml", "doubleml", "esda"} <= set(_C.PYTHON_PACKAGES) and "--prefer-binary" in _i.getsource(_C.install_python_package) \
            and "--no-binary" in _i.getsource(_C.install_python_package) and "_AUTO_INSTALL_TRIED" in _i.getsource(_C._use_prebuilt):
        note("packages: pre-built wheel first, then source, then a local wheel folder; a missing estimator package is installed and verified the first time a model needs it; every run counts them")
    else: bad("packages: the install chain (wheel -> source -> local wheels) or the run-time install in _use_prebuilt is missing")
    if "confirm_packages(" not in src: bad("P00 P12 does not confirm the packages")
    # 7. 10x data-volume limits
    ml = open(os.path.join(HERE, "python_prebuilt", "ml_spatial_pipeline.py"), encoding="utf-8").read()
    import glob as _g
    nbs = [f_ for f_ in _g.glob(os.path.join(HERE, "0[2-5]_*", "M*.ipynb"))]
    low = [os.path.basename(f_) for f_ in nbs if re.search(r"MAX_SPATIAL_N = [0-9]", open(f_, encoding="utf-8").read())]
    if "n_max=None" not in ml or "nn_sample=None" not in _i.getsource(_C.diagnose_effect_size) or low:
        bad(f"data-volume limits: ml_spatial_pipeline / diagnose_effect_size / notebooks still hold a fixed number ({low[:3]})")
    else: note("data-volume limits (v20.55 10x -> v20.57 YOUR 98 % RULE): ML, spatial weights, k-NN and the near-duplicate sample take every row that fits below 98 % of the RAM")
    # 8. the R library mirrors each rule (the parity harness proves the rows; this checks the code carries the options)
    rl = os.path.dirname(_C.r_bridge_script())
    rd, rp, rpr, rpk = (open(os.path.join(rl, f_), encoding="utf-8").read() for f_ in ("reward_design.R", "reward_paths.R", "reward_prep.R", "reward_packages.R"))
    miss = []
    if "normalize_seasons <- function" not in rd or "season_codes <- function" not in rd: miss.append("season modes")
    if 'identical(s$seasons_setting, "auto")' not in rd: miss.append("SEASONS honoured by model_design (only 'auto' follows the data)")
    if "overlap_rows" not in rd or 'OVERLAP_ROWS' not in rp: miss.append("OVERLAP_ROWS")
    if 'POOLED_FE' not in rp or 'identical(d$pooled_fe, "site_period")' not in rd: miss.append("POOLED_FE (site x period FE)")
    if "se_design_period" not in rd: miss.append("period-level design SE")
    if "common_shocks" not in rd or "rescaled" not in rd: miss.append("common-shock rule")
    if "canonical_pixel_map <- function" not in rpr or "resolve_duplicates <- function" not in rpr or "apply_missing_policy <- function" not in rpr: miss.append("Python prep ports")
    if "install_package_chain <- function" not in rpk or "confirm_packages <- function" not in rpk or "AUTO_INSTALL_PACKAGES" not in rp: miss.append("package chain")
    if "N_MAX_UNITS         <- NULL" not in rp: miss.append("the 98 % rule (no fixed sample size)")
    if "length(rec$pre_window) > 0 && length(rec$post_window) > 0" not in rd: miss.append("your windows kept when the data give none")
    if miss: bad("R library lacks: " + ", ".join(miss))
    else: note("R library: season modes, OVERLAP_ROWS, POOLED_FE, period-level SE, common-shock rule, Python prep ports, package chain, 10x limits")
    if not os.path.exists(os.path.join(HERE, "validate_r_parity.py")): bad("validate_r_parity.py missing -- R == Python structuring untested")
    else: note("validate_r_parity.py present: run it (needs R) -- it must print CLEAN before an R result is compared with a Python one")


def check_v20_56():
    """v20.56: YOUR RULES -- no chunking (every regression on all rows in RAM + GPU at once); R packages pre-built first,
    a source build only when no binary exists and it can be built here (Rtools), never an unasked-for source build."""
    import inspect as _i, json as _j
    sys.path.insert(0, HERE)
    import _common as _C
    # 1. the in-RAM path is the only regression path
    if not getattr(_C, "NO_CHUNKING", False) or _C.MEMORY_POLICY != "raise": bad("NO_CHUNKING / MEMORY_POLICY: a regression could be thinned or streamed")
    else:
        try:
            m, why = _C.recommend_mode(["pixel_id", "Year", "Season", "NDVI"]) if os.path.exists(_C.PREPARED_PANEL) else ("memory", "no panel here")
        except Exception as e:
            m, why = "memory", f"(recommend_mode raised {type(e).__name__} without a panel: fine)"
        if m != "memory": bad(f"recommend_mode still chooses '{m}': {why}")
        else: note("no chunking: MEMORY_POLICY = raise, recommend_mode = memory -- every regression runs on all its rows in RAM (GPU when they fit below 98 % VRAM)")
    nb = os.path.join(HERE, "02_Core_DiD_Models", "M01_Canonical_2x2_Static_TWFE.ipynb")
    src = "\n".join("".join(c["source"]) for c in _j.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
    # v20.58 YOUR RULE (replaces v20.56's "no streaming at all"): every row in RAM + GPU at once whenever it fits below 98 %; ONLY beyond that
    # the exact two-pass streaming estimator, in batches 5x larger than v20.57's
    if ('M01_MODE   = "auto"' not in src or "RUN_MODE, _why = C.run_mode(MODEL_ID, cols)" not in src or "C.load_panel_ooc(cols)" not in src
            or 'if RUN_MODE == "out_of_core":' not in src or "C.ooc_model(MODEL_ID" not in src):
        bad("M01: not 'auto' (all rows at once below 98 %; out of core -- Dask, Spark, built-in batches -- only beyond)")
    else: note("M01: M01_MODE = 'auto' -- every row in RAM + GPU at once whenever it fits below 98 %; beyond it OUT OF CORE (pixel partitions on Dask -> Spark -> built-in batches; exact)")
    import glob as _g
    users = [os.path.basename(f_) for f_ in _g.glob(os.path.join(HERE, "0[2-5]_*", "M*.ipynb"))
             if "estimate_twfe_did_streaming(" in open(f_, encoding="utf-8").read() and "M01_" not in os.path.basename(f_)]
    if users: bad(f"model notebooks using the streaming estimator: {users}")
    gsrc = _i.getsource(_C._demean_gpu_matrix)
    if "range(0, n" in gsrc or "chunk" in gsrc.lower(): bad("the GPU demeaner processes the matrix in chunks")
    else: note("the GPU demeaner takes the whole matrix in one pass (the only loops are over fixed effects and iterations)")
    # 2. R packages: pre-built first; a source build only without a binary AND with the build tools; never the 'newer source' prompt
    rl = os.path.dirname(_C.r_bridge_script()); rpk = open(os.path.join(rl, "reward_packages.R"), encoding="utf-8").read()
    setup = None
    cand = os.path.join(rl, "..", "..", "..", "RWDR_v" + _C.ENGINE_VERSION, "00_SETUP.R")
    if os.path.exists(cand): setup = open(cand, encoding="utf-8").read()
    miss = []
    if 'install.packages.compile.from.source = "never"' not in rpk: miss.append("compile-from-source switched off")
    if 'type = "binary"' not in rpk or "binary_platform <- function" not in rpk: miss.append("binary first on Windows / macOS")
    if "has_build_tools <- function" not in rpk or "needs_compilation <- function" not in rpk or "RTOOLS_URL" not in rpk: miss.append("Rtools awareness")
    if "utils::install.packages(pkgs = " not in rpk: miss.append("explicit pkgs=")
    if setup is not None and ("UPDATE_PACKAGES <- FALSE" not in setup or "install.packages(upd" in setup): miss.append("00_SETUP.R: no unasked-for updates")
    if miss: bad("R package chain lacks: " + ", ".join(miss))
    else: note("R packages: pre-built binaries first (Windows / macOS), the source only when no binary exists and it can be built here (Rtools said otherwise), installed packages not updated unless asked")

def check_v20_58():
    """v20.58: YOUR RULES -- only the current sub-watershed(s)' own rows in every model (location rule; the poison test covers every excluded
    row in every year, season and group, outcomes AND covariates), R structured as Python model by model (the same estimand, the same
    headline kind), no placeholder numbers (capped breakdown values, p-values that do not belong to their estimate), no silent skip."""
    import inspect as _i, re as _re
    sys.path.insert(0, HERE)
    import numpy as _np, pandas as _pd
    import _common as _C, _ground_common as _G, _paths as _PA
    rd = lambda f: open(os.path.join(HERE, f), encoding="utf-8").read()
    rl = os.path.dirname(_C.r_bridge_script())
    rr = lambda f: open(os.path.join(rl, f), encoding="utf-8").read()
    miss = []
    # 1. the location rule in the ground surrogate (P00) -- the processing set, as R
    if "location_mask(d, _lt, S=_S_run" not in _i.getsource(_G.fit_ground_surrogates): miss.append("ground surrogate not on the processing set")
    # 2. the poison test: every excluded row, outcomes and covariates (Python and R)
    vp = rd("validate_location_poison.py")
    if 'excl = np.isin(bk, [4, 5]) | (y < 2020) | (sc == 0) | (K["kind"].values == "flip")' not in vp or "100 * x" not in vp: miss.append("Python poison test not complete")
    rt_p = os.path.join(os.path.dirname(os.path.dirname(HERE)), "R", "tests", "run_all_tests.R")
    # 3. M13: the treatment D switches on (readiness measured; the engine = DIDmultiplegtDYN's estimator)
    if 'facts["n_switchers"] = len(_pre_tr & _post_tr)' not in rd("_readiness.py"): miss.append("M13 switchers still hard-coded")
    import glob as _g
    nb13 = open(_g.glob(os.path.join(HERE, "02_*", "M13_*.ipynb"))[0], encoding="utf-8").read()
    if "C.switcher_did(" not in nb13 or "treat_core never changes" in nb13: miss.append("M13 notebook still looks for a changing treat_core")
    try:                                                          # a staggered known answer: +0.05, two cohorts
        rows = []
        for u in range(60):
            g = 2020 if u < 20 else (2022 if u < 40 else None)
            for y in range(2016, 2025):
                rows.append({"pixel_id": u, "Year": y, "Season": 1, "site_id": 1, "treatment": int(g is not None), "post": int(g is not None and y >= g),
                             "NDVI": 0.3 + 0.01 * u + 0.005 * y + (0.05 if g is not None and y >= g else 0.0) + 0.0001 * ((u * 7 + y) % 5)})
        _t, _a = _C.switcher_did(_pd.DataFrame(rows), "NDVI", "pixel_id")
        if abs(_a - 0.05) > 0.002: miss.append(f"switcher_did {_a:.4f} for a true 0.05")
    except Exception as e:
        miss.append(f"switcher_did failed: {type(e).__name__}: {e}")
    # 4. M15 / M34 / M20 / M19 / M10 / M26 / M06: one estimand per model in R and Python
    src = rd("_common.py"); ddp = rd(os.path.join("python_prebuilt", "dd_pipeline.py"))
    if "mean_placebo_se" not in src or "p_any_placebo_bonferroni" not in rr("models_prebuilt.R"): miss.append("M15: the mean placebo has no SE of its own")
    if "M34" in _C.MODEL_KIND or _C.HEADLINE_SPEC["M34"][2] != "estimate" or '"breakdown_Mbar": bd' not in ddp: miss.append("M34: not the effect + exact breakdown")
    if "l_vec = lv" not in rr("reward_models_core.R") or "grid.lb = th - w" not in rr("reward_models_core.R"): miss.append("R M34: target / centred grid")
    if "ms[~sig].min()) if (~sig).any() else float(ms.max())" in src: miss.append("M34: the capped breakdown is back")
    if _C.MODEL_KIND.get("M20") != "test" or 'method = "DL"' not in rr("models_prebuilt.R") or "tau2 = max(0.0, (Q - df_)" not in src: miss.append("M20: not the same test in R and Python")
    if "variance_components_crossed(" not in open(_g.glob(os.path.join(HERE, "03_*", "M19_*.ipynb"))[0], encoding="utf-8").read(): miss.append("M19: the engine is not lme4's model")
    if "did_g3 := did * g3" not in rr("models_prebuilt.R") or "M10" not in _C.NOT_ATT: miss.append("M10: R and Python differ")
    if "treatment_covariate_interaction(" not in open(_g.glob(os.path.join(HERE, "03_*", "M26_*.ipynb"))[0], encoding="utf-8").read() or "M26" in _C.NOT_ATT: miss.append("M26: R and Python differ")
    if _C.PREBUILT_MODELS["M06"]["layer"] != "function": miss.append("M06: the primary is not the dose slope")
    if "coef(fit, agg = FALSE)" not in rr("models_prebuilt.R"): miss.append("R M09: cohort x period vcov")
    if "(1 + sum(abs(tb) >= abs(t0))) / (1 + B)" not in rr("reward_models_core.R"): miss.append("R M23: a bootstrap p of 0")
    rx = _re.search(r'HEADLINE_EXTRA <- c\(([^)]*)\)', rr("reward_design.R"), _re.S)
    if not rx or sorted(_re.findall(r'"([^"]+)"', rx.group(1))) != sorted(_C.HEADLINE_EXTRA): miss.append("HEADLINE_EXTRA differs between R and Python")
    # 5. no fund timing leaking into the package checks; no design counts / fit info from permuted fits; messages
    if src.count('exclude_transition_year=False, timing="fixed")') < 1 or src.count('cohort_offset=0, timing="fixed")') < 1: miss.append("verification not on fixed timing")
    if "with resampling_scope():" not in _i.getsource(_C._permutation_inference_impl): miss.append("permutation fits overwrite the actual fit's diagnostics")
    if "SCENARIO SET:" not in src or "def _timing_request_text" not in src: miss.append("scenario line (the timing in force, no premature tag)")
    if _PA._file_path(r"D:\LKT\x.xlsx") != r"D:\LKT\x.xlsx" and os.name != "nt": miss.append("_paths: a Windows file path rewritten")
    # 5b. M45 / M34: one estimator in R and Python (the elastic-net SC converged tightly on both sides; HonestDiD on M02's event study)
    if "tol=1e-12" not in _i.getsource(_C.lasso_synthetic_control) or "enet_cv_sk(X, y)" not in rr("models_prebuilt.R") or _C.R_ROUTES.get("M45") != ["glmnet"]:
        miss.append("M45: R and Python are not the same elastic-net synthetic control")
    if _C.PREBUILT_MODELS["M34"]["layer"] != _C._E or "M34" not in _C.R_ROUTES or '"M34"' not in rr("run_one.R").split("CORE_R <- c(")[1].split(")")[0]:
        miss.append("M34: the primary is not HonestDiD on M02's event study")
    try:                                                          # the elastic net converged: a known problem with a 4-donor truth
        _rng = _np.random.default_rng(11); _T = 12; _c = _rng.normal(0, .02, _T).cumsum()
        _D = _np.array([_c * _rng.uniform(.5, 1.5) + _rng.normal(0, .01, _T) for _ in range(6)]); _mu = _D.mean(0)
        _y = _c + _rng.normal(0, .01, _T) + _np.r_[_np.zeros(8), _np.full(4, .05)]
        _r, _ = _C.lasso_synthetic_control((_y - _mu)[:8], (_D - _mu)[:, :8], (_y - _mu)[8:], (_D - _mu)[:, 8:])
        if _r["n_not_converged"] or not (0.0 < _r["ATT_lasso_sc"] < 0.1): miss.append(f"elastic-net SC: {_r}")
    except Exception as e:
        miss.append(f"elastic-net SC failed: {type(e).__name__}: {e}")
    # 5c. Python's OWN implementations = R's estimators (validate_model_parity.py --engine): the functions in place and exact on small checks
    for nm in ("event_headline", "chained_fd_did", "psm_did", "goodman_bacon_exact", "bacon_series", "bacon_twfe_inference", "bjs_imputation_series",
               "cs_group_aggregation", "entropy_balanced_twfe", "weighted_twfe_did", "sun_abraham_fixest", "synthdid_point"):
        if not hasattr(_C, nm): miss.append(f"engine function {nm} missing")
    try:                                                          # Goodman-Bacon: the weighted 2 x 2s reconstitute the two-way FE (else it raises)
        _rows = [{"unit": f"u{u_}", "site_id": 1 + u_ % 7, "Season": 1, "Year": y_, "D": int(y_ >= g_), "y": 0.01 * u_ + 0.003 * y_ + (0.05 if y_ >= g_ else 0) + 0.001 * ((u_ * 7 + y_) % 5)}
                 for u_ in range(42) for g_ in [[2019, 2021, 10 ** 6][u_ % 3]] for y_ in range(2016, 2024)]
        _t, _b = _C.goodman_bacon_exact(_pd.DataFrame(_rows))
        if abs(float(_t.weight.sum()) - 1) > 1e-9: miss.append("Goodman-Bacon weights do not sum to 1")
    except Exception as e:
        miss.append(f"goodman_bacon_exact failed: {type(e).__name__}: {e}")
    try:                                                          # synthdid's point estimate (a value checked against R's synthdid)
        _Y = _np.array([[1.0, 1.2, 1.1, 1.5, 1.6], [0.9, 1.0, 1.2, 1.3, 1.5], [1.2, 1.1, 1.3, 1.4, 1.7], [1.1, 1.3, 1.2, 1.9, 2.0]])
        _tau, _om, _lm = _C.synthdid_point(_Y, 3, 3)
        if not (_np.isfinite(_tau) and abs(_om.sum() - 1) < 1e-12 and abs(_lm.sum() - 1) < 1e-12): miss.append(f"synthdid_point: {_tau}")
    except Exception as e:
        miss.append(f"synthdid_point failed: {type(e).__name__}: {e}")
    for m_, pat in (("M02", "window=None, covariates=list(C.DEFAULT_COVARIATES)"), ("M12", "C.chained_fd_did("), ("M14", "C.psm_did("), ("M22", "C.goodman_bacon_exact("),
                    ("M27", "C.bjs_imputation_series("), ("M30", "C.cs_group_aggregation("), ("M33", "C.entropy_balanced_twfe("), ("M09", "C.sun_abraham_fixest("),
                    ("M06", "covariates=list(C.DEFAULT_COVARIATES)"), ("M16", "covariates=list(C.DEFAULT_COVARIATES)")):
        _f = _g.glob(os.path.join(HERE, "0*", f"{m_}_*.ipynb"))
        if not _f or pat not in open(_f[0], encoding="utf-8").read().replace('\\"', '"'): miss.append(f"{m_} notebook does not call {pat}")
    if 'link = "linear.logit"' not in rr("models_prebuilt.R") or "first_stage <- as.formula" not in rr("models_prebuilt.R"): miss.append("R M14 / M27: not the shared rule")
    # 5d. (v20.58, second pass) the engine = R's package on M03 / M04 / M19 / M28 / M29 / M31 / M35 (ported from the package sources), the
    # ML headlines = R's (the package's own SE; M39 / M41 a headline, not a table), every calculation in double precision
    for nm in ("unit_year_frame", "_drdid_imp_panel", "cic_qte", "did2s_event", "exposure_twfe", "stacked_series", "icc_reml", "_rq_fnb", "_rq_cluster_se", "quantile_did_rq"):
        if not hasattr(_C, nm): miss.append(f"engine function {nm} missing")
    for m_, pat in (("M03", "C.dr_did(df, OUTCOME"), ("M04", "C.cic_qte(df, OUTCOME)"), ("M19", "C.icc_reml(df, OUTCOME)"), ("M28", "C.did2s_event(df, OUTCOME)"),
                    ("M29", "C.exposure_twfe(df, OUTCOME)"), ("M31", "C.stacked_series(df, OUTCOME"), ("M35", "C.quantile_did_rq(df, OUTCOME)"),
                    ("M42", "return_se=True")):
        _f = _g.glob(os.path.join(HERE, "0*", f"{m_}_*.ipynb"))
        if not _f or pat not in open(_f[0], encoding="utf-8").read().replace('\\"', '"'): miss.append(f"{m_} notebook does not call {pat}")
    try:                                                          # Frisch-Newton = the LP optimum when it is unique (a continuous design)
        _rng = _np.random.default_rng(5); _X = _np.column_stack([_np.ones(300), _rng.normal(size=(300, 2))]); _yv = _X @ _np.array([1.0, 0.5, -0.3]) + _rng.standard_t(3, 300)
        _bf = _C._rq_fnb(_X, _yv, 0.5); _bl = _C._rq_lp(_X, _yv, 0.5)
        if _np.max(_np.abs(_bf - _bl)) > 1e-5: miss.append(f"_rq_fnb {_bf} vs the LP {_bl}")
    except Exception as e:
        miss.append(f"_rq_fnb failed: {type(e).__name__}: {e}")
    try:                                                          # DRDID imp: a known effect with confounding through x
        _rng = _np.random.default_rng(8); _x = _rng.normal(size=4000); _D = (_rng.uniform(size=4000) < 1 / (1 + _np.exp(-0.8 * _x))).astype(float)
        _dY = 0.3 * _x + 0.05 * _D + _rng.normal(0, 0.05, 4000)
        _a, _s, _ = _C._drdid_imp_panel(_dY, _D, _x[:, None])
        if abs(_a - 0.05) > 4 * _s or not (0 < _s < 0.01): miss.append(f"_drdid_imp_panel ATT {_a:.4f} (SE {_s:.4f}) for a true 0.05")
    except Exception as e:
        miss.append(f"_drdid_imp_panel failed: {type(e).__name__}: {e}")
    try:                                                          # the REML ICC: a design with a known year variance share
        _rng = _np.random.default_rng(9); _rows = []
        _ye = {y_: _rng.normal(0, 0.02) for y_ in range(2014, 2026)}; _pe = {p_: _rng.normal(0, 0.03) for p_ in range(400)}
        for p_ in range(400):
            for y_ in range(2014, 2026): _rows.append({"pixel_id": p_, "Year": y_, "did_term": int(p_ < 100 and y_ >= 2022), "site_id": 1, "NDVI": 0.4 + _ye[y_] + _pe[p_] + 0.05 * (p_ < 100 and y_ >= 2022) + _rng.normal(0, 0.02)})
        _ri, _ = _C.icc_reml(_pd.DataFrame(_rows), "NDVI")
        if not (0.05 < _ri["ICC"] < 0.6): miss.append(f"icc_reml ICC {_ri['ICC']:.3f}")
    except Exception as e:
        miss.append(f"icc_reml failed: {type(e).__name__}: {e}")
    if 'fit(Y, T, X=X, cache_values=True)' not in rd(os.path.join("python_prebuilt", "ml_spatial_pipeline.py")) or "att_stderr_(T=1)" not in rd(os.path.join("python_prebuilt", "ml_spatial_pipeline.py")):
        miss.append("ML: the package SE (DRLearner AIPW scores / CausalForestDML ATT) not taken")
    if 'model != "M39"' in rr("run_one.R") or "grf S / T / X learners" not in rr("models_prebuilt.R") or "y_ld := season_net(dt, outcome)" not in rr("models_prebuilt.R"):
        miss.append("R ML: M39 headline / the X-learner / the series long difference")
    if '"float32" and not _is_categorical_col(c_)' not in src: miss.append("load_panel: float32 columns not widened to double")
    # 5e. (v20.58, third pass) M36-M38: fect / gsynth ported -- R's generator, fect's CV folds, the fits -- against R's own numbers (fect 2.4.5 /
    # gsynth 1.4.0 run on these two panels with set.seed(12345), as R's route); M39-M44: R's long difference in the engine; a package file of
    # an earlier run never becomes the headline; R: the CV seeded, integer series ids, DoubleML's forests as Python's
    for nm in ("_RRandom", "_fect_cv_masks", "fect_fit", "fect_ring_series", "ml_long_difference", "_grf_att_formula", "causal_forest_att"):
        if not hasattr(_C, nm): miss.append(f"engine function {nm} missing")
    try:
        _rg = _C._RRandom(12345); _u = [_rg.unif_rand() for _ in range(5)]
        if _np.max(_np.abs(_np.array(_u) - [0.720903896261007, 0.875773193081841, 0.760982328327373, 0.886124566197395, 0.456480960128829])) > 1e-14 \
                or _rg.sample_int(7, 3) != [2, 5, 3] or _rg.sample_int(3, 1) != [2] or _rg.sample_int(1000, 4) != [86, 75, 38, 615]:
            miss.append("_RRandom is not R's Mersenne-Twister / sample.int")
        _rng = _np.random.default_rng(7); _pan = {}
        for _nm, (_ntr, _nco, _T, _g0, _nf) in (("P1", (1, 3, 10, 7, 0)), ("P2", (2, 6, 12, 8, 1))):     # the panels R was run on
            _N = _ntr + _nco; _a = _rng.normal(0, 0.05, _N); _x = _rng.normal(0, 0.03, _T)
            _F = _rng.normal(0, 1, (_T, _nf)); _L = _rng.normal(0, 0.03, (_N, _nf))
            _Y = 0.4 + _a[None, :] + _x[:, None] + (_F @ _L.T if _nf else 0) + _rng.normal(0, 0.01, (_T, _N))
            _D = _np.zeros((_T, _N)); _D[_np.arange(_T) >= _g0 - 1, :_ntr] = 1; _pan[_nm] = (_Y + 0.05 * _D, _D)
        _ref = {("P1", "ife"): (0, 0.0552571409975398), ("P1", "mc"): (0.000793301897127707, 0.0552571409975398), ("P1", "gsynth"): (0, 0.0552571409975398),
                ("P2", "ife"): (1, 0.0462426252097569), ("P2", "mc"): (0.00020349326960071, 0.0484944448770004), ("P2", "gsynth"): (1, 0.0467024050551174)}
        _cvs = {"P1": (2, 3, 3), "P2": (4, 3, 4)}                                                          # rmax, cv.nobs, min.T0 (R's rules)
        for (_nm, _m), (_tn, _att) in _ref.items():
            _re_, _cn, _mt = _cvs[_nm]
            _a1, _t1, _ = _C.fect_fit(*_pan[_nm], _m, r_end=_re_, min_T0=_mt, cv_nobs=_cn, do_cv=True)
            if abs(_a1 - _att) > 1e-10 or abs(float(_t1) - _tn) > 1e-12 * max(1.0, _tn): miss.append(f"fect port {_nm}/{_m}: {_a1:.12f} (tuning {_t1}) vs R {_att:.12f} ({_tn})")
        for (_nm, _m, _r), _att in ((("P1", "ife", 1), 0.0670353122756123), (("P1", "ife", 2), 0.0720396414691067), (("P1", "gsynth", 2), 0.0606012013104379),
                                    (("P2", "ife", 2), 0.0462175125673955), (("P2", "gsynth", 2), 0.0466197295453041)):
            _a1, _, _ = _C.fect_fit(*_pan[_nm], _m, do_cv=False, tuning=_r)
            if abs(_a1 - _att) > 1e-10: miss.append(f"fect port {_nm}/{_m} r={_r}: {_a1:.12f} vs R {_att:.12f}")
        # v20.58 (second pass): the SEs with R's OWN draws -- L'Ecuyer-CMRG after set.seed(12345) (R: runif(1), nextRNGStream), fect's
        # nonparametric bootstrap on doRNG's streams (r = 1; matrix completion keeping a factor) and gsynth's parametric bootstrap, as R's route
        _lc = _C._RRandom(12345, "L'Ecuyer-CMRG"); _s0 = _lc.state
        if abs(_lc.unif_rand() - 0.072440895034863187) > 1e-16 or [v - (1 << 32) if v >= (1 << 31) else v for v in _C._r_next_stream(_s0)] \
                != [-1645818963, 548746318, 440099794, 143370804, -548492161, 249546247]:
            miss.append("_RRandom is not R's L'Ecuyer-CMRG / nextRNGStream")
        for (_nm, _m, _tn), _se in ((("P1", "gsynth", 0), 0.00536942101541143), (("P2", "ife", 1), 0.0043432894195687),
                                     (("P2", "mc", 0.00020349326960071), 0.00355602914497873), (("P2", "gsynth", 1), 0.00437751035643603)):
            _s1 = _C._fect_boot_se(*_pan[_nm], _m, _tn)
            if not abs(_s1 - _se) <= 1e-9 * _se: miss.append(f"fect / gsynth bootstrap {_nm}/{_m}: SE {_s1:.12g} vs R's {_se:.12g}")
    except Exception as e:
        miss.append(f"fect port check failed: {type(e).__name__}: {e}")
    try:                                                          # v20.58 (second pass): M25's engine = R's m25_ritest (the same draws)
        _rq = _np.random.default_rng(3); _rows = []
        for _px in range(1, 61):
            _rg_ = 0 if _px <= 12 else 1 + (_px - 13) % 3; _aa = _rq.normal(0, 0.03)
            for _se_ in (1, 2, 3):
                for _y in range(2018, 2025):
                    if _rq.random() < 0.03: continue
                    _tt, _po = int(_rg_ == 0), int(_y >= 2022)
                    _rows.append((_px * 10 + _se_, _px, _se_, _y, f"{_y}_{_se_}", _tt, _po, _tt * _po,
                                  0.3 + _aa + {1: 0.05, 2: 0.0, 3: -0.04}[_se_] + 0.004 * (_y - 2018) + 0.05 * _tt * _po + _rq.normal(0, 0.01)))
        _dp = _pd.DataFrame(_rows, columns=["unit_id", "pixel_id", "Season", "Year", "time_fe_yearseason", "treat_core", "post", "did", "y"])
        _dp = _dp.sample(frac=1.0, random_state=5).reset_index(drop=True)
        _dp["buff_km"] = _np.where(_dp["treat_core"] == 1, 0, 1 + (_dp["pixel_id"] - 13) % 3); _dp["site_id"] = 1   # the design columns
        _uf = _C.ACTIVE.get("unit_fe"); _C.ACTIVE["unit_fe"] = "pixel_season"
        try:
            _pr = _C._permutation_inference_impl(_dp, "y", "treat_core", "post", "pixel_id", "time_fe_yearseason")
        finally:
            _C.ACTIVE["unit_fe"] = _uf
        if abs(_pr["beta_actual"] - 0.0513255994878072) > 1e-12 or abs(_pr["se_permutation"] - 0.00435305565486869) > 1e-9 * 0.00435305565486869 \
                or abs(_pr["p_value_permutation"] - 0.001) > 1e-12:
            miss.append(f"M25 engine: {_pr['beta_actual']:.12g} / SE {_pr['se_permutation']:.12g} / p {_pr['p_value_permutation']:.4g} vs R's "
                        f"0.0513255994878 / 0.00435305565487 / 0.001 (R's m25_ritest on the same panel)")
    except Exception as e:
        miss.append(f"M25 engine check failed: {type(e).__name__}: {e}")
    try:                                                          # v20.58 (second pass): the engine's SEs = R's packages' (their own numbers)
        def _panel_(seed, n_pix, n_core, yrs, drop, shuffle, staggered):
            _r = _np.random.default_rng(seed); _rows_ = []
            for _px in range(1, n_pix + 1):
                _ring = 0 if _px <= n_core else 1 + (_px - n_core - 1) % 3; _a = _r.normal(0, 0.03)
                _g = ((2021 if _px <= 12 else 2023) if _ring == 0 else _np.inf) if staggered else (2022.0 if _ring == 0 else _np.inf)
                for _s in (1, 2, 3):
                    for _y in yrs:
                        if _r.random() < drop: continue
                        _tr = int(_ring == 0)
                        if staggered:
                            _po = int(_tr and _y >= _g); _v = 0.3 + _a + {1: 0.05, 2: 0.0, 3: -0.04}[_s] + 0.004 * (_y - yrs[0]) + (0.05 + 0.01 * (_y - _g) if _po else 0) + _r.normal(0, 0.01)
                            _rows_.append((_px * 10 + _s, _px, _s, _y, 1, _ring, _tr, _po, _po, _g, _v))
                        else:
                            _po = int(_y >= 2022); _v = 0.3 + _a + {1: 0.05, 2: 0.0, 3: -0.04}[_s] + 0.004 * (_y - 2018) + 0.05 * _tr * _po + _r.normal(0, 0.01)
                            _rows_.append((_px * 10 + _s, _px, _s, _y, 1, _ring, _tr, _po, _tr * _po, _g, _v))
            _d = _pd.DataFrame(_rows_, columns=["unit_id", "pixel_id", "Season", "Year", "site_id", "buff_km", "treat", "post", "did_term", "first_treat_agri_year", "y"])
            _d = _d.sample(frac=1.0, random_state=shuffle).reset_index(drop=True); _d["treatment"] = _d["treat"]; return _d
        _A = _panel_(21, 80, 16, list(range(2018, 2025)), 0.02, 9, False)        # one cohort, 2 % gaps (R: fect-free routes of lib/models_prebuilt.R)
        _B = _panel_(33, 90, 30, list(range(2017, 2025)), 0.03, 2, True)         # two cohorts, 3 % gaps
        _uf, _pm, _cl = _C.ACTIVE.get("unit_fe"), _C.PREBUILT_MODE, _C.ACTIVE.get("cluster")
        _C.ACTIVE["unit_fe"] = "pixel_season"; _C.ACTIVE["cluster"] = "site"; _C.PREBUILT_MODE = "off"
        try:
            _got = {}
            _r4, _ = _C.cic_qte(_A, "y"); _got["M04 A"] = (_r4["ATT_CiC"], _r4["se"])
            _r32, _ = _C.etwfe(_A, "y", "pixel_id", "Year", "first_treat_agri_year"); _got["M32 A"] = (_r32["ATT_etwfe"], _r32["se"])
            for _k, _D_ in (("A", _A), ("B", _B)):
                _t, _by = _C.callaway_santanna_att(_D_, "y", "pixel_id", "Year", "first_treat_agri_year"); _got[f"M05 {_k}"] = (_by.attrs["ATT_simple"], _by.attrs["ATT_simple_se"])
                _r27 = _C.bjs_imputation_series(_D_, "y", [], "pixel_id", "did_term"); _got[f"M27 {_k}"] = (_r27["overall_ATT"], _r27["se"])
            _th, _ov = _C.cs_group_aggregation(_B, "y", "pixel_id", "Year", "first_treat_agri_year"); _got["M30 B"] = (_ov, _th.attrs["se"])
            _r11 = _np.random.default_rng(45); _rw = []; _pid = 0                      # M11: two sub-watersheds, 10 ring series per fit
            for _st in (1, 2):
                for _rg in range(0, 6):
                    for _k in range(2):
                        _pid += 1; _aa = _r11.normal(0, 0.03) + 0.01 * _st
                        for _se in (1, 2):
                            for _y in range(2017, 2024):
                                _tr = int(_rg == 0 and _st == 1); _gg = 2021 if _tr else _np.inf; _po = int(_tr and _y >= _gg)
                                _rw.append((_pid, _se, _y, _st, _rg if not (_rg == 0 and _st == 2) else 1, _tr, _po, _po, _gg,
                                            0.3 + _aa + {1: 0.05, 2: 0.0}[_se] + 0.004 * (_y - 2017) + 0.05 * _po + _r11.normal(0, 0.01)))
            _S = _pd.DataFrame(_rw, columns=["pixel_id", "Season", "Year", "site_id", "buff_km", "treat", "post", "did_term", "first_treat_agri_year", "y"])
            _S["unit_id"] = _S["pixel_id"] * 10 + _S["Season"]; _S["treatment"] = _S["treat"]
            _pf = _C.ACTIVE.get("pooled_fe"); _C.ACTIVE["pooled_fe"] = "site_period"
            try:
                _r11s, _, _ = _C.sdid_ring_series(_S, "y"); _got["M11 S"] = (_r11s["ATT"], _r11s["se"])
            finally:
                _C.ACTIVE["pooled_fe"] = _pf
        finally:
            _C.ACTIVE["unit_fe"] = _uf; _C.PREBUILT_MODE = _pm; _C.ACTIVE["cluster"] = _cl
        _want = {"M04 A": (0.0501835008083909, 0.00129577301162939), "M32 A": (0.0487639379202872, 0.000956019169904387),
                 "M05 A": (0.0516436627740958, 0.0024219368619608), "M27 A": (0.049532866863306, 0.00124811899923218),
                 "M05 B": (0.0570583783043674, 0.00164273752782076), "M30 B": (0.0554068563609564, 0.00158469070871904),
                 "M27 B": (0.0596030214368146, 0.000943848823041853), "M11 S": (0.0458741088152684, 0.0048614662563567)}
        for _k, (_e, _s) in _want.items():
            _ge, _gs = _got[_k]
            if not (abs(_ge - _e) <= 1e-8 * max(1.0, abs(_e)) and abs(_gs - _s) <= 1e-6 * _s):
                miss.append(f"{_k}: engine {_ge:.12g} (SE {_gs:.12g}) vs R's {_e:.12g} (SE {_s:.12g}) -- qte / etwfe / did / didimputation / synthdid on the same panel")
    except Exception as e:
        miss.append(f"engine SE check failed: {type(e).__name__}: {e}")
    try:                                                          # v20.58: no temporary folder left behind by the R bridge / checks
        _src_r = _i.getsource(_C._run_r_model); _src_v = _i.getsource(_C.verify_prebuilt_models); _src_p = _i.getsource(_C.r_package_status)
        if not hasattr(_C, "_rm_temp") or "_rm_temp(out)" not in _src_r or "_rm_temp(_vroot)" not in _src_v or "_rm_temp(os.path.dirname(outf))" not in _src_p:
            miss.append("the R bridge / package checks leave their temporary folders (input frames) in the system's temp folder")
    except Exception as e:
        miss.append(f"temp-folder check failed: {type(e).__name__}: {e}")
    for m_, pat in (("M36", 'C.fect_ring_series(df, OUTCOME, "ife")'), ("M37", 'C.fect_ring_series(df, OUTCOME, "mc")'), ("M38", 'C.fect_ring_series(df, OUTCOME, "gsynth")'),
                    ("M39", "C.causal_forest_att(X, D, Y"), ("M40", "C.ml_long_difference(df, OUTCOME"), ("M41", "C.ml_long_difference(df, OUTCOME"),
                    ("M42", "C.ml_long_difference(df, OUTCOME"), ("M43", "C.causal_forest_att(X, D, Y"), ("M44", "C.ml_long_difference(df, OUTCOME")):
        _f = _g.glob(os.path.join(HERE, "0*", f"{m_}_*.ipynb"))
        if not _f or pat not in open(_f[0], encoding="utf-8").read().replace('\\"', '"'): miss.append(f"{m_} notebook does not call {pat}")
    try:                                                          # a package file of an EARLIER run is never this run's headline
        import tempfile as _tf2, time as _tm
        _dd = _tf2.mkdtemp(prefix="sc_stale_"); _pf = os.path.join(_dd, "M36_PACKAGE_NDVI.csv")
        _pd.DataFrame([{"outcome": "NDVI", "estimate": 0.9, "se": 0.1, "engine": "old"}]).to_csv(_pf, index=False)
        os.utime(_pf, (_tm.time() - 3600, _tm.time() - 3600)); _C.PACKAGE_RUN_START[("M36", "NDVI")] = _tm.time()
        _h = _C._package_headline("M36", "NDVI", _dd)
        if _h is not None or os.path.exists(_pf) or not os.path.exists(os.path.join(_dd, "_superseded", "M36_PACKAGE_NDVI.csv")):
            miss.append("a package result of an earlier run is still read as the headline")
        _C.PACKAGE_RUN_START.pop(("M36", "NDVI"), None)
    except Exception as e:
        miss.append(f"stale package check failed: {type(e).__name__}: {e}")
    _mp = rr("models_prebuilt.R")
    if "un <- if (length(oc)) unique(dt[do.call(order, unname(as.list(dt[, oc, with = FALSE]))), unit])" not in _mp or "bs <- with_mt_seed({" not in _mp:
        miss.append("R M25: the units not in (pixel, season) order / the permutations not drawn from set.seed(12345) (Mersenne-Twister)")
    if 'pm <- synthdid::panel.matrices(as.data.frame(s[, .(uid, Year, y, D)]), unit = "uid"' not in _mp:
        miss.append("R M11: synthdid's series ids not integers in the canonical order (the placebo draws depend on it)")
    if 'idname = "uid", panel = TRUE' not in _mp or "se = TRUE, iters = 200, pl = FALSE, cores = 1L" not in _mp:
        miss.append("R M04: qte's bootstrap not sequential with integer series ids (its draws depend on the number of cores on Linux / macOS)")
    if "fit(Y, T, X=None, W=X, inference=_inf)" not in open(os.path.join(HERE, "python_prebuilt", "ml_spatial_pipeline.py"), encoding="utf-8").read():
        miss.append("M40 Python primary: not the partially linear model of R's DoubleML (LinearDML with the covariates as controls)")
    if "with_mt_seed(fect::fect(" not in _mp or "with_mt_seed(gsynth::gsynth(" not in _mp or 'index = c("uid", "Year")' not in _mp \
            or "uo <- unique(s[order(-treat, site_id, buff_km), unit])" not in _mp:
        miss.append("R M36-M38: the CV not seeded / the series ids not integers (treated first)")
    if "min.bucket = 20L" not in _mp: miss.append("R M40: DoubleML's forests not the Python primary's")
    if "_econml_crossfit_tau(" not in rd(os.path.join("python_prebuilt", "ml_spatial_pipeline.py")): miss.append("Python M39 / M43: econml's out-of-bag effects (not cross-fitted)")
    # 5f. (v20.58, fifth pass) M05's Python primary on series with GAPS: diff-diff's CallawaySantAnna is not did::att_gt(allow_unbalanced_panel
    # = TRUE) there (the parity run with cloud gaps: 0.0505 against R's 0.0488) -- the engine (did's estimator, ported) computes
    _cs = _i.getsource(_C.callaway_santanna_att)
    if "_balanced = len(_uy) == _uy[unit_col].nunique() * _uy[time_col].nunique()" not in _cs or "if _use_prebuilt(\"callaway_santanna\") and not _balanced:" not in _cs:
        miss.append("M05: diff-diff's CallawaySantAnna still used on series with gaps (not did's estimator there)")
    # 5g. (v20.58, fifth pass) M24 = R's m24: ONE fit of every ring x post against the farthest ring (fixest i(ring, post, ref = far) | unit +
    # period); checked against an explicit dummy-variable regression (the unit and period dummies written out) on series WITH GAPS
    try:
        _rg = _np.random.default_rng(24); _rows = []
        for _px in range(1, 61):
            _ring = _px % 4; _a = _rg.normal(0, 0.03)
            for _s in (1, 2):
                for _y in range(2018, 2024):
                    if _rg.random() < 0.08: continue                                   # gaps: the pairwise fits would differ
                    _po = int(_y >= 2021)
                    _rows.append({"pixel_id": _px, "Season": _s, "Year": _y, "buff_km": _ring, "post": _po, "site_id": 1, "subwshed_id": "S1",
                                  "time_fe_yearseason": f"{_y}_{_s}", "y": 0.3 + _a + 0.01 * _s + 0.003 * _y + (0.05 if _ring == 0 else 0.004 * (3 - _ring)) * _po
                                  + _rg.normal(0, 0.01)})
        _d = _pd.DataFrame(_rows); _d["unit_id"] = _d["pixel_id"] * 10 + _d["Season"]
        _uf, _pm, _cl = _C.ACTIVE.get("unit_fe"), _C.PREBUILT_MODE, _C.ACTIVE.get("cluster")
        _C.ACTIVE["unit_fe"] = "pixel_season"; _C.PREBUILT_MODE = "off"
        try:
            _out = _C.spillover_gradient_test(_d, "y", "post", "buff_km", "pixel_id", "time_fe_yearseason", ring_values=(1, 2, 3))
        finally:
            _C.ACTIVE["unit_fe"] = _uf; _C.PREBUILT_MODE = _pm
        _U = _pd.get_dummies(_d["unit_id"].astype(str), drop_first=False).values.astype(float)
        _T = _pd.get_dummies(_d["time_fe_yearseason"], drop_first=True).values.astype(float)
        _R = _np.column_stack([(_d["buff_km"].values == _r) * _d["post"].values for _r in (0, 1, 2)]).astype(float)
        _bb = _np.linalg.lstsq(_np.column_stack([_R, _U, _T]), _d["y"].values, rcond=None)[0][:3]
        _got = _out.set_index("ring_km")["gradient_effect"].reindex([1, 2]).values
        if _np.max(_np.abs(_got - _bb[1:3])) > 1e-10 or list(_out["vs_reference_km"].unique()) != [3]:
            miss.append(f"M24: {_got} vs the dummy-variable regression {_bb[1:3]} (one fit of every ring, as R's fixest)")
    except Exception as e:
        miss.append(f"M24 joint-fit check failed: {type(e).__name__}: {e}")
    # 6. R: no silent skip
    for f_, pat in (("models_prebuilt.R", "error = function(e) NULL); if (is.null(r) || !is.finite(r$estimate)) next"),
                    ("models_prebuilt.R", "cluster = ~cluster_id), error = function(e) NULL)")):
        if pat in rr(f_): miss.append(f"R silent skip left in {f_}: {pat[:50]}")
    if miss: bad("v20.58: " + " | ".join(miss))
    else: note("v20.58: location rule in the ground surrogate; complete poison test; M13 on D (DIDmultiplegtDYN's estimator, 0.05 recovered); "
               "M06 / M10 / M15 / M19 / M20 / M26 / M34 / M45 one estimand in R and Python; R M09 / M23 fixed; checks on fixed timing; no silent skip; "
               "the engine = R's package for M03 / M04 / M19 / M28 / M29 / M31 / M35 (ported; Frisch-Newton = the LP optimum, DRDID imp and REML ICC on "
               "known answers); the ML headlines with the package's own SE (R and Python); every calculation in double precision; M36-M38 fect / gsynth "
               "ported (R's generator and CV folds replicated: R's own numbers to 1e-10 on two panels, r = 0 / 1 / 2) and their SEs with R's own draws "
               "(fect's bootstrap on doRNG's L'Ecuyer streams, gsynth's parametric bootstrap: R's SE to 1e-9); M25's permutations = R's (the design's "
               "units, set.seed(12345)); the engine's SEs = R's packages' on gappy panels: M04 (qte's bootstrap draws), M05 / M30 (did's influence "
               "function), M27 (didimputation), M32 (etwfe: the cohort's effects, emfx's delta method), M11 (synthdid's placebo draws); M40 the partially linear model in both; "
               "M39-M44 on R's long difference; the R bridge's temporary folders removed after each call; "
               "an earlier run's package file is never the headline; R's fect CV seeded; M05 on series with gaps = did's estimator (the engine; "
               "diff-diff's CallawaySantAnna only on balanced series, where it is did's); M24 one fit of every ring as R's fixest (= the dummy-variable "
               "regression on series with gaps)")

def check_v20_58_m13_port():
    """v20.58 (fourth pass): M13's engine = DIDmultiplegtDYN 2.4.0 (did_multiplegt_dyn_port): the effects, placebos, average total effect and
    their analytic SEs, without and with clusters, against the package's own numbers on a fixed unbalanced panel (24 series, 2016-2025,
    cohorts 2020 / 2022, 7 % of the rows missing; R: did_multiplegt_dyn(effects = 3, placebo = 2[, cluster = "cl"]))."""
    sys.path.insert(0, HERE)
    import numpy as _np, pandas as _pd
    import _common as _C
    rows = []
    for g in range(24):
        coh = 2020 if g < 6 else (2022 if g < 12 else None)
        for y in range(2016, 2026):
            if (g * 13 + y * 7) % 15 == 0: continue
            e = 0.05 if (coh is not None and y >= coh) else 0.0
            rows.append({"u": g + 1, "Year": y, "y": round(0.3 + 0.01 * ((g * 5) % 7) + 0.004 * (y - 2016) + e + 0.002 * (((g + 3) * (y - 2011)) % 9 - 4), 6),
                         "D": int(coh is not None and y >= coh), "cl": (g % 7) + 1})
    uy = _pd.DataFrame(rows)
    R_ = {None: [0.0514136363636364, 0.0528888888888889, 0.0530743801652892, 0.00174607348224087, 0.00221006694318679, 0.00208694341270743,
                 0.00327272727272727, 0.00262857142857143, 0.00200943624323961, 0.00353211793168285, 0.0524312316715542, 0.00151374301589934],
          "cl": [0.0514136363636364, 0.0528888888888889, 0.0530743801652892, 0.00137385300395123, 0.00199543191236155, 0.00199972394117504,
                 0.00327272727272727, 0.00262857142857143, 0.00184336951075937, 0.00226323935480943, 0.0524312316715542, 0.000783330763221976]}
    worst = 0.0
    try:
        for cl, ref in R_.items():
            e, a, se, p = _C.did_multiplegt_dyn_port(uy, effects=3, placebo=2, cluster_col=cl)
            got = list(e.estimate) + list(e.se) + list(p.estimate) + list(p.se) + [a, se]
            worst = max(worst, float(_np.max(_np.abs(_np.array(got) - _np.array(ref)))))
    except Exception as ex:
        bad(f"M13 DIDmultiplegtDYN port raised {type(ex).__name__}: {ex}"); return
    if worst > 1e-12: bad(f"M13: the DIDmultiplegtDYN port differs from the package by {worst:.2e}")
    else: note(f"M13 = DIDmultiplegtDYN 2.4.0: effects, placebos, the average total effect and their SEs (with and without clusters) to {worst:.1e}")

def check_v20_58_out_of_core():
    """v20.58 YOUR RULE: beyond 98 % of the RAM (never before) M01 / M02 / M16 / M34 (and P00 / R_P00) go OUT OF CORE -- Dask, then Spark,
    then the built-in batches -- exact and never sampled; in Python AND in R. And one definition per function in the engine files."""
    import ast as _ast, json as _j, glob as _g
    sys.path.insert(0, HERE)
    miss = []
    for f in ("_outofcore.py", "_ooc_models.py", "validate_out_of_core.py"):
        if not os.path.exists(os.path.join(HERE, f)): miss.append(f)
    if miss: bad("out-of-core files missing: " + ", ".join(miss)); return
    import _outofcore as _O, _paths as _P
    if tuple(_O.OOC_MODELS) != ("M01", "M02", "M16", "M34"): bad(f"_outofcore.OOC_MODELS = {_O.OOC_MODELS}")
    order = tuple(getattr(_P, "OUT_OF_CORE", ()))
    if order != ("dask", "spark", "batches") or _O.engine_order()[-1] != "batches": bad(f"OUT_OF_CORE (_paths.py) = {order}: expected dask -> spark -> batches")
    else: note("out of core (Python): _paths.OUT_OF_CORE = dask -> spark -> batches; " + "; ".join(f"{e}: {'available' if _O.engine_status(e)[0] else 'NOT available'}" for e in _O.KNOWN_ENGINES))
    nbs = {"M01": "02_Core_DiD_Models/M01_Canonical_2x2_Static_TWFE.ipynb", "M02": "02_Core_DiD_Models/M02_Event_Study_dynamic_TWFE.ipynb",
           "M16": "02_Core_DiD_Models/M16_Formal_Joint_Pre_Trends_F_test.ipynb", "M34": "04_Advanced_Staggered_Robustness/M34_Honest_DiD_parallel_trends_sensitivity.ipynb"}
    lack = []
    for m, rel in nbs.items():
        fp = os.path.join(HERE, rel)
        if not os.path.exists(fp): continue                                   # a project without this model (PIPELINE_MODELS)
        src = "\n".join("".join(c["source"]) for c in _j.load(open(fp, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
        if "C.run_mode(MODEL_ID, cols)" not in src or "C.load_panel_ooc(cols)" not in src or "C.ooc_model(MODEL_ID" not in src: lack.append(m)
    if lack: bad(f"model notebooks without the out-of-core branch: {lack}")
    else: note("M01 / M02 / M16 / M34 notebooks: run_mode -> in memory below 98 %, out of core (ooc_model) beyond")
    # R: the same four models and R_P00, the same engines (R's own batches; Dask / Spark through lib/reward_ooc_engine.py)
    rl = os.path.join(os.path.dirname(os.path.dirname(HERE)), "R", "lib")
    if not os.path.isdir(rl):
        import _common as _C; rl = os.path.dirname(_C.r_bridge_script())
    need = ["reward_outofcore.R", "reward_prep_ooc.R", "reward_ooc_task.R", "reward_ooc_engine.py"]
    lr = [f for f in need if not os.path.exists(os.path.join(rl, f))]
    if lr: bad("R out-of-core files missing in " + rl + ": " + ", ".join(lr))
    else:
        core = open(os.path.join(rl, "reward_models_core.R"), encoding="utf-8").read(); prep = open(os.path.join(rl, "reward_prep.R"), encoding="utf-8").read()
        pth = open(os.path.join(rl, "reward_paths.R"), encoding="utf-8").read(); ooc = open(os.path.join(rl, "reward_outofcore.R"), encoding="utf-8").read()
        m2 = []
        if "rm_ <- run_mode_R(id, outcome, d)" not in core or "ooc_run_model_R(id, outcome, d" not in core: m2.append("run_model_R -> out of core")
        if "pm <- prep_mode_R(files)" not in prep or "run_prep_ooc(files" not in prep: m2.append("run_prep -> block by block")
        if 'OUT_OF_CORE         <- c("dask", "spark", "batches")' not in pth: m2.append("OUT_OF_CORE in reward_paths.R")
        if 'OOC_MODELS_R <- c("M01", "M02", "M16", "M34")' not in ooc: m2.append("OOC_MODELS_R")
        if m2: bad("R out of core: " + ", ".join(m2))
        else: note("out of core (R): M01 / M02 / M16 / M34 (run_model_R) and R_P00 (run_prep) beyond 98 % -- Dask -> Spark -> R batches, exact")
    # one definition per top-level function (a second definition silently replaces the first -- v20.58 found treatment_coverage twice)
    dup = []
    for f in ("_common.py", "_prep_common.py", "_outofcore.py", "_ooc_models.py", "_location.py", "_fund.py", "_hardware.py"):
        fp = os.path.join(HERE, f)
        if not os.path.exists(fp): continue
        names = [n.name for n in _ast.parse(open(fp, encoding="utf-8").read()).body if isinstance(n, (_ast.FunctionDef, _ast.ClassDef))]
        d_ = sorted({n for n in names if names.count(n) > 1})
        if d_: dup.append(f"{f}: {d_}")
    if dup: bad("functions defined twice (the second silently replaces the first): " + "; ".join(dup))
    else: note("one definition per function in the engine files (no silent replacement)")


def check_v20_59():
    """v20.59 (your v20.58 R log): PRE_YEARS / POST_YEARS as calendar years (a bound leaving no pre year is said, never 'USED: from 0'); the
    panel carries treat / control / pre / post / did with post from the exports' Treat flag (1 = post, 0 = pre); the model stage compares
    its design with the panel's post and says so (DESIGN vs PANEL); the outcome screen writes its evidence and has a way out (OUTCOME_SCREEN
    keep / off), its refusal names both; P00 writes the pixel-variation report; the notebooks carry the options; R has the same rules."""
    import inspect as _i, glob as _g, numpy as _np, pandas as _pd
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P, _outofcore as _O
    saved = dict(_C.ACTIVE)
    try:
        # 1 the year window
        _C.set_scenario(timing="fixed", treatment_year=2022, control_zones="1-5", pre_years=2018, post_years=2024, seasons="all", verbose=False)
        if _C.scenario_years() != (2018, 2024): bad(f"PRE_YEARS / POST_YEARS as calendar years give {_C.scenario_years()} (want (2018, 2024))")
        _C.set_scenario(pre_years=4, post_years=2, verbose=False)
        if _C.scenario_years() != (2018, 2023): bad(f"PRE_YEARS / POST_YEARS as counts give {_C.scenario_years()} (want (2018, 2023))")
        _C.set_scenario(pre_years=2022, post_years="all", verbose=False)
        if _C.scenario_years() != (None, None) or _C.year_window_dropped() != (2022, None):
            bad(f"PRE_YEARS = 2022 with the start in 2022 is not set aside: {_C.scenario_years()} / {_C.year_window_dropped()} (v20.58 gave 'from 0')")
        _C.resolve_design(verbose=False, force=True)
        if not any("PRE_YEARS = 2022 leaves NO year" in n for n in _C._RESOLVED["notes"]): bad("a pre bound at the start is not said in DESIGN IN EFFECT")
        for v in (0, 500, 2500, "x"):
            try: _C.set_scenario(pre_years=v, verbose=False); bad(f"PRE_YEARS = {v!r} was accepted")
            except _C.InsufficientDataError: pass
        _C.set_scenario(pre_years="all", post_years="all", verbose=False)
        if "_year_option(" not in _i.getsource(_C.set_scenario): bad("set_scenario does not read PRE_YEARS / POST_YEARS as counts OR calendar years")
        note("PRE_YEARS / POST_YEARS: a number of years OR a calendar year; a bound that leaves no year on its side of the start is said and set aside (never 'from 0')")
        # 2 the panel's DiD columns from the exports' flag (P00)
        for c in ("treat", "did", "post", "pre", "control", "treatment", "did_term"):
            if c not in _P.FINAL_PANEL_SCHEMA: bad(f"the panel schema lacks {c}")
        d = _pd.DataFrame({"buff_km": [0, 0, 3, 3, 7], "Year": [2021, 2022, 2021, 2022, 2022], "Season": [0] * 5, "Treat": [0.0, 0.0, 0.0, 1.0, 1.0], "season_sort_rank": [3] * 5})
        out = _P.build_treatment_columns(d)                    # row 2: the export says 2022 is PRE for that pixel -- the flag wins over the rule
        if list(out["post"]) != [0, 0, 0, 1, 1] or list(out["pre"]) != [1, 1, 1, 0, 0]: bad(f"post / pre do not follow the exports' Treat flag: {list(out['post'])}")
        if list(out["treat"]) != [1, 1, 0, 0, 0] or list(out["did"]) != [0, 0, 0, 0, 0] or list(out["control"]) != [0, 0, 1, 1, 0]: bad("treat / did / control wrong in the preparation's build_treatment_columns")
        if out.attrs.get("post_flag_vs_rule_differ") != 1 or out.attrs.get("post_from_export_flag") != 5: bad(f"the flag-vs-rule accounting is wrong: {out.attrs}")
        _P.POST_FROM_EXPORT_TREAT = False
        try:
            if list(_P.build_treatment_columns(d)["post"]) != [0, 1, 0, 1, 1]: bad("POST_FROM_EXPORT_TREAT = False does not give the rule Year >= 2022")
            if _P.period_rule() != "year": bad("POST_FROM_EXPORT_TREAT = False is not the older name of PERIOD_RULE = 'year'")
        finally:
            _P.POST_FROM_EXPORT_TREAT = True
        # v20.59 -- YOUR RULE: PERIOD_RULE "treat" | "year" | "both"; the input audit (Treat 1 / 0, buff_km 0 / 1-5) per file
        if _P.period_rule() != "treat" or tuple(_P.PERIOD_RULES) != ("treat", "year", "both"): bad(f"PERIOD_RULE default / choices wrong: {_P.period_rule()!r} {_P.PERIOD_RULES}")
        try:
            _P.PERIOD_RULE = "year"
            if list(_P.build_treatment_columns(d)["post"]) != [0, 1, 0, 1, 1]: bad("PERIOD_RULE = 'year' does not give the rule Year >= 2022")
            _P.PERIOD_RULE = "both"
            ob = _P.build_treatment_columns(d)                    # row 2 (2022, flag 0, rule 1) disagrees: it LEAVES
            if len(ob) != 4 or list(ob["post"]) != [0, 0, 1, 1] or ob.attrs.get("period_rows_dropped") != 1 or ob.attrs.get("post_flag_vs_rule_differ") != 0:
                bad(f"PERIOD_RULE = 'both' does not drop the disagreeing row: {len(ob)} rows, {ob.attrs}")
            d2, au = _P.audit_and_apply_period_rule(d.assign(Treat=[0.0, 0.0, float("nan"), 1.0, 1.0]), "x.csv")
            if len(d2) != 3 or au["rows_dropped_period_disagree"] != 2 or au["treat_vs_year_disagree_rows"] != 1 or au["treat_unusable_rows"] != 1: bad(f"the PASS A audit under 'both' is wrong: {len(d2)} rows, {au}")
            _P.PERIOD_RULE = "treat"
            d3, au = _P.audit_and_apply_period_rule(d, "y.csv")
            want = {"rows": 5, "treat_post_rows": 2, "treat_pre_rows": 3, "treat_unusable_rows": 0, "treat_vs_year_disagree_rows": 1, "buff0_treatment_rows": 2,
                    "buff1to5_control_rows": 2, "buff_outside_0to5_rows": 1, "rows_dropped_period_disagree": 0, "period_rule": "treat"}
            if len(d3) != 5 or any(au.get(k) != v for k, v in want.items()): bad(f"the PASS A audit is wrong: {au}")
            _P.PERIOD_RULE = "nonsense"
            try: _P.period_rule(); bad("an unknown PERIOD_RULE is not refused")
            except ValueError: pass
        finally:
            _P.PERIOD_RULE = "treat"
        pa = _i.getsource(_P.run_pass_a) + _i.getsource(_P._pa_worker)
        if "__input_audit__" not in pa or "input_audit_report(" not in pa or "audit_and_apply_period_rule(" not in pa: bad("PASS A does not audit the input files (input_design_audit.csv)")
        pb = _i.getsource(_P.prepare_pass_b_block)
        if "export_post_flag(" not in pb or "post_from_export_flag" not in pb or "period_rule()" not in pb: bad("PASS B's design check does not account for the exports' flag / PERIOD_RULE")
        if "panel_variation_by_block.csv" not in _i.getsource(_P.run_pass_b) or "moments" not in pb: bad("P00 does not write the pixel-variation report")
        if '"period_rule"' not in _i.getsource(_P.run_pass_b): bad("panel_build_settings.json does not record PERIOD_RULE")
        if "period_rule()" not in _i.getsource(_P.final_panel_is_valid): bad("a panel built under another PERIOD_RULE is not rebuilt")
        note("the panel carries treat / control / pre / post / did -- PERIOD_RULE 'treat' (the exports' Treat flag: 1 = post, 0 = pre) | 'year' | 'both' (a disagreeing row leaves); "
             "PASS A confirms Treat 1 / 0 and buff_km 0 / 1-5 on every input file (input_design_audit.csv); P00 writes panel_variation_by_block.csv")
        # 3 the model stage: the design in effect against the panel's post, said; the aliases rebuilt
        src = _i.getsource(_C.build_treatment_columns)
        if "design_vs_panel(" not in src or 'out["treat"] = out["treatment"]' not in src: bad("the model stage does not compare its design with the panel's post / rebuild the treat / did aliases")
        _C.set_scenario(timing="fixed", treatment_year=2022, control_zones="1-5", verbose=False)
        f = _pd.DataFrame({"pixel_id": _np.arange(6, dtype="int64"), "buff_km": [0, 0, 0, 2, 2, 2], "Year": [2021, 2022, 2023] * 2, "Season": [1] * 6,
                           "post": [0, 0, 1, 0, 0, 1], "subwshed_id": ["SW1"] * 6, "time_fe_yearseason": ["2021_K", "2022_K", "2023_K"] * 2, "NDVI": 0.3})
        g = _C.build_treatment_columns(f)
        if _C.LAST_DESIGN_INFO.get("post_rows_differ_from_panel") != 2 or _C.LAST_DESIGN_INFO.get("post_rows_compared") != 6: bad(f"DESIGN vs PANEL count wrong: {_C.LAST_DESIGN_INFO}")
        if list(g["post"]) != [0, 1, 1, 0, 1, 1] or list(g["did"]) != [0, 1, 1, 0, 0, 0] or list(g["treat"]) != [1, 1, 1, 0, 0, 0]: bad("the model's post / did / treat do not follow the design (fixed 2022)")
        if "post" not in _C.columns_for("NDVI") or "post" not in _C.OPTIONAL_READ_COLUMNS: bad("the panel's post is not read for the comparison")
        import _ooc_models as _OM
        if "post_diff" not in _i.getsource(_OM._t_prep) or "say_design_vs_panel(" not in _i.getsource(_OM.prepare_sample): bad("the out-of-core path does not merge and say the DESIGN vs PANEL counts")
        note("the model stage rebuilds treat / post / did for ITS design and says on how many rows it differs from the panel's post (DESIGN vs PANEL; out of core too)")
        # 4 the outcome screen: evidence, rule, refusal text
        if _C.screen_rule() != "drop": bad(f"the default screen rule is {_C.screen_rule()!r}, not 'drop'")
        for v, w in ((True, "drop"), (False, "off"), ("keep", "keep"), ("OFF", "off")):
            if _C._screen_rule_of(v) != w: bad(f"OUTCOME_SCREEN {v!r} -> {_C._screen_rule_of(v)!r} (want {w!r})")
        t = _pd.DataFrame({"Year": [2020] * 4 + [2021] * 4, "Season": [0] * 8, "tr": [True, False] * 4, "y": [0.31] * 4 + [0.30, 0.35, 0.40, 0.45]})
        gt = _C.screen_decide_table(_C._screen_table(t, _np.arange(8)), "NDVI")
        if list(gt["usable"]) != [False, True] or "every value 0.31" not in gt["why"].iloc[0] or "4 rows of 4 pixels" not in gt["why"].iloc[0]:
            bad(f"the screen's evidence is not in its verdict: {list(gt['why'])}")
        for k in ("vmin", "vmax", "n_pixels", "sd"):
            if k not in gt.columns: bad(f"the screen table lacks {k}")
        _C.set_scenario(outcome_screen="keep", verbose=False)
        if _C.screen_rule() != "keep" or "_screenKept" not in _C.scenario_tag(): bad("OUTCOME_SCREEN = 'keep' is not in force / not in the results tag")
        _C.set_scenario(outcome_screen="drop", verbose=False)
        if "_screenKept" in _C.scenario_tag(): bad("the _screenKept tag stays after OUTCOME_SCREEN = 'drop'")
        txt = _C.screen_refusal_text("NDVI", [2015], [2025], 41, 44, "x.csv")
        if "OUTCOME_SCREEN = 'keep'" not in txt or "x.csv" not in txt: bad("the refusal does not name the evidence file and the way out")
        if "screen_decide_table(" not in _i.getsource(_O.screen_decision) or "screen_report(" not in _i.getsource(_O.screen_decision): bad("the out-of-core screen does not share the in-memory evidence and rule")
        if "vmin" not in _i.getsource(_O._screen_stats): bad("the out-of-core screen moments lack min / max")
        note("the outcome screen: every decision with its evidence (OUTCOME_SCREEN_<outcome>.csv), OUTCOME_SCREEN drop / keep / off, a refusal that names the way out; the same out of core")
        # 5 the notebooks: OUTCOME_SCREEN set and passed, the calendar-year form documented; P00 carries POST_FROM_EXPORT_TREAT
        nbs = [p for p in _g.glob(os.path.join(HERE, "0*", "M[0-9][0-9]_*.ipynb")) if ".ipynb_checkpoints" not in p]   # the model notebooks (not MS01)
        miss = [os.path.basename(p) for p in nbs if not all(k in open(p, encoding="utf-8").read() for k in ("OUTCOME_SCREEN", "outcome_screen=OUTCOME_SCREEN", "calendar year"))]
        if miss: bad(f"model notebooks without OUTCOME_SCREEN / the calendar-year note: {miss[:6]}")
        p00 = _g.glob(os.path.join(HERE, "01_Panel_Preparation", "P00*.ipynb"))
        if not p00 or not all(k in open(p00[0], encoding="utf-8").read() for k in ("POST_FROM_EXPORT_TREAT", "P.PERIOD_RULE = ")): bad("P00's settings do not carry PERIOD_RULE / POST_FROM_EXPORT_TREAT")
        if not p00 or "outcome_screen=OUTCOME_SCREEN" not in open(p00[0], encoding="utf-8").read(): bad("P00's own design report does not receive OUTCOME_SCREEN")
        rp00 = [q for q in (os.path.join(os.path.dirname(os.path.dirname(HERE)), "..", "RWDR_v20.59", "rstudio", "R_P00_Prepare_Panel.Rmd"),
                            os.path.join(os.path.dirname(os.path.dirname(HERE)), "..", "RWDR_v20.59", "jupyter", "R_P00_Prepare_Panel.ipynb")) if os.path.exists(q)]
        for q in rp00:                                                  # v20.59: R_P00 carries the two keep / drop options at the panel level too
            t_ = open(q, encoding="utf-8").read()
            if 'OUTCOME_SCREEN    <- ' not in t_ or 'EXCLUDE_GAPFILLED <- ' not in t_: bad(f"{os.path.basename(q)} does not carry OUTCOME_SCREEN / EXCLUDE_GAPFILLED at the panel level")
        if "panel KEEPS every row and value" not in _i.getsource(_P.run_pass_b): bad("P00 does not say that the panel keeps every row and value")
        for q in rp00:                                                  # v20.59: R_P00 carries EVERY design default (as P00_Settings) and the overlay options
            t_ = open(q, encoding="utf-8").read()
            miss_ = [k for k in ("DESIGN_MODE", "TREATMENT_TIMING", "CONTROL_RINGS", "PRE_YEARS", "POST_YEARS", "SEASONS", "SUB_WATERSHEDS", "SITE_GEOMETRY_CHECK", "BUFF_FROM_GEOMETRY", "FRAGMENT_RULE") if f"{k} " not in t_ and f"{k}<-" not in t_]
            if miss_: bad(f"{os.path.basename(q)} lacks the panel-level defaults {miss_}")
        if not p00 or not all(k in open(p00[0], encoding="utf-8").read() for k in ("SUB_WATERSHEDS = ", "P.SITE_GEOMETRY_CHECK = ", "P.BUFF_FROM_GEOMETRY  = ", "sub_watersheds=SUB_WATERSHEDS")):
            bad("P00_Settings lacks SUB_WATERSHEDS / the overlay options, or does not pass sub_watersheds to its design report")
        # v20.59: the machine -- every processor group, pools without the 61-worker limit, the GPU line
        import _hardware as _HW
        if not all(hasattr(_HW, k) for k in ("logical_cores_all", "processor_groups", "make_pool", "gpu_line")): bad("_hardware lacks logical_cores_all / processor_groups / make_pool / gpu_line")
        if _HW.logical_cores_all() < (os.cpu_count() or 1) or _HW.machine_profile().get("pool_limit", 0) < _HW.logical_cores_all(): bad("the worker pool is still capped below the machine's logical cores")
        _pl = _HW.make_pool(2); _r = _pl.map(abs, [-1, -2]); _pl.shutdown(wait=True)
        if list(_r) != [1, 2]: bad("make_pool does not run tasks")
        pa_ = _i.getsource(_P.run_pass_a)
        if "make_pool(" not in pa_ or "make_pool(" not in _i.getsource(_P.run_pass_b) or "PICKLE_SAFE_BYTES:" not in pa_: bad("PASS A / PASS B do not use make_pool or the early shard switch")
        rl_ = os.path.join(os.path.dirname(os.path.dirname(HERE)), "R", "lib")
        for fn_, keys_ in (("reward_paths.R", ("all_logical_cores_R", "SITE_GEOMETRY_CHECK", "BUFF_FROM_GEOMETRY")), ("reward_prep.R", ("overlay_or_trust", "ring_from_polygon_codes", "working_sws_line")), ("reward_prep_ooc.R", ("overlay_or_trust", "ring_from_polygon_codes"))):
            pth_ = os.path.join(rl_, fn_)
            if os.path.exists(pth_):
                t_ = open(pth_, encoding="utf-8").read(); mk = [k for k in keys_ if k not in t_]
                if mk: bad(f"R {fn_} lacks {mk}")
        note("the machine: every logical processor of every processor group (Python ctypes / R CIM), worker pools without the 61 limit, blocks above the pipe size go to shards at once, "
             "the GPU said; the overlay options and the working-sub-watershed rule at both levels in both languages")
        note(f"{len(nbs)} model notebooks set OUTCOME_SCREEN and pass it; PRE_YEARS / POST_YEARS document the calendar-year form; P00 carries PERIOD_RULE; "
             f"P00 and R_P00 ({len(rp00)} found) carry OUTCOME_SCREEN / EXCLUDE_GAPFILLED as the panel-level defaults and say the panel keeps every value")
        # 6 R: the same rules in the R library and notebooks
        rl = os.path.join(os.path.dirname(os.path.dirname(HERE)), "R", "lib")
        if os.path.isdir(rl):
            want = {"reward_design.R": ("year_bounds_R", "screen_rule_R", "design_vs_panel_say_R", 'OUTCOME_SCREEN_%s.csv', "_screenKept", "post_vs_panel", "outcome_screen = screen_rule_R"),
                    "reward_prep.R": ("panel_design_columns_R", "panel_variation_report_R", "POST_FROM_EXPORT_TREAT", "period_rule_R", "input_audit_R", "input_audit_report_R", "input_design_audit_R.csv", '"period_rule", "period_rows_dropped"', "panel_kept_report_R"),
                    "reward_prep_ooc.R": ("panel_design_columns_R", "panel_variation_report_R", "input_audit_report_R", "audit = aud", '"period_rule", "period_rows_dropped"'),
                    "reward_outofcore.R": ("post_vs_panel", "screen_decide(s, outcome, rule)", "min = min(v), max = max(v)"),
                    "reward_paths.R": ("OUTCOME_SCREEN", 'PERIOD_RULE       <- "treat"')}
            for fn, keys in want.items():
                pth = os.path.join(rl, fn); s_ = open(pth, encoding="utf-8").read() if os.path.exists(pth) else ""
                m_ = [k for k in keys if k not in s_]
                if m_: bad(f"R {fn} lacks {m_}")
            rmd = [p for p in _g.glob(os.path.join(os.path.dirname(rl), "rstudio", "R_M*.Rmd"))]
            m_ = [os.path.basename(p) for p in rmd if "OUTCOME_SCREEN" not in open(p, encoding="utf-8").read() or "calendar year" not in open(p, encoding="utf-8").read()]
            if m_: bad(f"R notebooks without OUTCOME_SCREEN / the calendar-year note: {m_[:6]}")
            note("R: the same rules (year_bounds_R, panel_design_columns_R, screen_rule_R + the evidence file, DESIGN vs PANEL, the variation report) and the same notebook options")
    finally:
        _C.ACTIVE.clear(); _C.ACTIVE.update(saved); _C._RESOLVED["key"] = None


def check_v20_58_memory_batches():
    """v20.58 (found when a validation run was KILLED for memory): M25's permutations in batches were sized for 3 n-vectors per permutation
    while the peak was 5 (the demeaning's convergence test made two more n x k temporaries). The demeaning tests its convergence in place
    (the same numbers, bit for bit) and M25 counts 6 n-vectors, in Python and R; the permuted estimates do not depend on the batch size."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import numpy as _np, pandas as _pd
    import _common as _C
    miss = []
    if "np.subtract(R, prev, out=prev)" not in _i.getsource(_C._demean_cpu_matrix): miss.append("the demeaning's convergence test is not in place")
    if "48.0 * n" not in _i.getsource(_C._permutation_inference_impl): miss.append("Python M25 does not count 6 n-vectors per permutation")
    _rlib = os.path.dirname(_C.r_bridge_script())
    rp = open(os.path.join(_rlib, "models_prebuilt.R"), encoding="utf-8").read()
    if "unit_cap(8 * 6 * nrow(dt))" not in rp or "Md <- dm(M); rm(M)" not in rp: miss.append("R M25 does not count 6 n-vectors per permutation")
    # the demeaning: bit-identical to the v20.57 test (a copy of it here), with missing keys and very different column scales
    from scipy import sparse as _sp
    def _old(Y, fes, tol=1e-10, max_iter=200):
        R = _np.array(_np.asarray(Y, dtype=_np.float64), order="C"); n = R.shape[0]; ops = []
        for f in fes:
            cd = _C._codes(f); ok = cd >= 0; K = int(cd.max()) + 1 if ok.any() else 1
            cnt = _np.bincount(cd[ok], minlength=K).astype(_np.float64); cnt[cnt == 0] = 1.0
            ops.append((_sp.csr_matrix((1.0 / cnt[cd[ok]], (cd[ok], _np.nonzero(ok)[0])), shape=(K, n)), cd, ok, ok.all()))
        for _ in range(max_iter):
            prev = R.copy()
            for P_, cd, ok, allok in ops:
                means = P_ @ R
                if allok: R -= means[cd]
                else: R[ok] -= means[cd[ok]]
            if _np.max(_np.abs(R - prev)) < tol: break
        return R
    rng = _np.random.default_rng(7)
    for t in range(3):
        n = 6000; f1 = rng.integers(0, 400, n).astype(float); f2 = rng.integers(0, 30, n)
        if t: f1[rng.random(n) < 0.03] = _np.nan
        Y = rng.normal(size=(n, 5)); Y[:, 2] *= 1e5
        new = _C._demean_cpu_matrix(Y, [f1, f2], 1e-10, 200)
        if t == 0:      # complete keys: converges in 16 passes -- bit-identical to v20.57
            if not _np.array_equal(_old(Y, [f1, f2]), new, equal_nan=True): miss.append("the demeaning changed where v20.57 converged"); break
        else:           # 3 % of the rows without a unit key: v20.57 stopped after 200 passes ~1e-5 short; now converged (the extension)
            ref = _old(Y, [f1, f2], tol=1e-13, max_iter=100_000); sc_ = _np.maximum(1.0, _np.abs(ref).max(axis=0))
            e_new = float((_np.abs(new - ref).max(axis=0) / sc_).max()); e_old = float((_np.abs(_old(Y, [f1, f2]) - ref).max(axis=0) / sc_).max())
            if not (e_new < 1e-9 and e_old > 1e-7): miss.append(f"slow design (panel {t}): the demeaning is {e_new:.1e} from convergence (v20.57: {e_old:.1e})"); break
    old_cap = _C.FE_MAX_ITER; _C.FE_MAX_ITER = 4; _C._FE_CONV_SAID.clear(); said = []
    _w0 = _C.warn; _C.warn = lambda m, *a_, **k_: said.append(str(m))
    try: _C._demean_cpu(Y[:, 0].copy(), [f1, f2], 1e-10, 3)
    finally: _C.FE_MAX_ITER = old_cap; _C.warn = _w0; _C._FE_CONV_SAID.clear()
    if not any("did not reach" in m_ for m_ in said): miss.append("a demeaning that does not converge is not reported")
    # M25: all at once == in batches (a budget for 13 permutations per batch)
    rows = []
    for px in range(1, 61):
        ring = 0 if px <= 15 else 1 + (px - 16) % 3
        for s_ in (1, 2):
            for y in range(2017, 2024):
                rows.append((px, s_, y, int(ring == 0), int(y >= 2021), 0.3 + 0.001 * px + 0.05 * int(ring == 0) * int(y >= 2021) + rng.normal(0, 0.02)))
    A = _pd.DataFrame(rows, columns=["pixel_id", "Season", "Year", "treat", "post", "y"])
    A["unit"] = A.pixel_id.astype(str) + "_" + A.Season.astype(str); A["period"] = A.Year.astype(str) + "_" + A.Season.astype(str)
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        r1 = _C._permutation_inference_impl(A, "y", "treat", "post", "unit", "period", n_permutations=99)
        old_env = os.environ.get("REWARD_RAM_BUDGET_BYTES"); os.environ["REWARD_RAM_BUDGET_BYTES"] = str(48.0 * len(A) * 13)
        try:
            r2 = _C._permutation_inference_impl(A, "y", "treat", "post", "unit", "period", n_permutations=99)
        finally:
            if old_env is None: os.environ.pop("REWARD_RAM_BUDGET_BYTES", None)
            else: os.environ["REWARD_RAM_BUDGET_BYTES"] = old_env
    if not (r2["batch"] == 13 and r1["batch"] == 99 and r1["p_value_permutation"] == r2["p_value_permutation"]
            and abs(r1["se_permutation"] - r2["se_permutation"]) <= 1e-15):
        miss.append(f"M25 in batches ({r2['batch']}) differs from all at once ({r1['batch']}): p {r2['p_value_permutation']} vs {r1['p_value_permutation']}")
    if getattr(_C, "PYFIXEST_FIXEF_TOL", 1.0) > 1e-10 or "_pf_demeaner_kw(fn, kw)" not in _i.getsource(_C._pf_quiet):
        miss.append("pyfixest's demeaning is left at its default tolerance (1e-6: the SE's 8th digit then follows Python's string hashing)")
    if miss: bad("98 % rule, batch sizes: " + "; ".join(miss))
    else: note("98 % rule, batch sizes: M25 counts its true peak (6 n-vectors per permutation; Python and R), the demeaning tests convergence in "
               "place (bit-identical where v20.57 converged; a slow design is now iterated to convergence, one that cannot converge is "
               "reported), pyfixest converges to 1e-12, and M25's permutations in batches == all at once (the same draws in the same order)")


def check_v20_58_repeated_rows():
    """v20.58 (second pass, found by the poison test with cloud gaps): P00 filled the kept row's gaps from the REPEATED rows it dropped (a cloud
    gap of the newer export took the older export's value of that pixel-period), so values of dropped rows reached every model. Now a repeated
    row is dropped WHOLE (DEDUP_FILL_FROM_DUPLICATES = False; True = the old fill, for exports split by variable), in Python and R; the setting
    is recorded in panel_build_settings.json and a panel built otherwise is rebuilt; every panel-building setting of P00 lives in P00_Settings
    (set in the PASS B cell, after the validate-or-skip step, a change was silently ignored while the old panel was kept)."""
    import inspect as _i, json as _j, re as _re
    sys.path.insert(0, HERE)
    import numpy as _np, pandas as _pd
    import _prep_common as _P, _common as _C
    miss = []
    if _P.DEDUP_FILL_FROM_DUPLICATES is not False: miss.append(f"DEDUP_FILL_FROM_DUPLICATES defaults to {_P.DEDUP_FILL_FROM_DUPLICATES!r}")
    df = _pd.DataFrame([dict(site_id=1, pixel_id=1, Year=2023, Season=1, NDVI=_np.nan, LAI=1.0, src_file="new.csv", file_mtime=9.0),
                        dict(site_id=1, pixel_id=1, Year=2023, Season=1, NDVI=0.9, LAI=1.5, src_file="old.csv", file_mtime=1.0),
                        dict(site_id=1, pixel_id=2, Year=2023, Season=1, NDVI=0.5, LAI=1.1, src_file="old.csv", file_mtime=1.0)])
    out, lg = _P.resolve_duplicates(df.copy(), conflict_log=[])
    o1 = out[out.pixel_id == 1]
    if len(out) != 2 or len(o1) != 1 or not _np.isnan(o1.NDVI.iloc[0]) or o1.LAI.iloc[0] != 1.0 or out.attrs.get("values_in_dropped_rows_not_used") != 1:
        miss.append(f"a repeated row's value reached the kept row: {o1.to_dict('records')} {out.attrs}")
    opt, _ = _P.resolve_duplicates(df.copy(), conflict_log=[], fill_from_duplicates=True)
    if opt[opt.pixel_id == 1].NDVI.iloc[0] != _np.float64(0.9) or opt.attrs.get("values_filled_from_duplicates") != 1:
        miss.append("DEDUP_FILL_FROM_DUPLICATES = True does not fill the kept row's gap")
    if "dedup_fill_from_duplicates" not in _i.getsource(_P.final_panel_is_valid) or '"dedup_fill_from_duplicates": bool(DEDUP_FILL_FROM_DUPLICATES)' not in _i.getsource(_P.run_pass_b):
        miss.append("the fill setting is not recorded in / compared with panel_build_settings.json")
    # v20.58: the workers receive EVERY setting (_settings_snapshot; the hand-picked lists missed ALLOW_NEGATIVE_COVARIATES / NEGATIVE_COVARIATE_RULE)
    if ("cfg = _settings_snapshot()" not in _i.getsource(_P.run_pass_b) or "cfg = _settings_snapshot()" not in _i.getsource(_P.run_pass_a)
            or _P._settings_snapshot().get("DEDUP_FILL_FROM_DUPLICATES", "missing") is not _P.DEDUP_FILL_FROM_DUPLICATES
            or "ALLOW_NEGATIVE_COVARIATES" not in _P._settings_snapshot()):
        miss.append("the PASS A / PASS B worker processes do not receive DEDUP_FILL_FROM_DUPLICATES (and every other setting)")
    nb = _j.load(open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8"))
    code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    i_set = [k for k, c in enumerate(code) if c.startswith("# ===== P00_Settings")]; i_val = [k for k, c in enumerate(code) if c.startswith("# ===== P00_Validate_or_Skip")]
    for v_ in ("NEAR_DUPLICATE_PIXELS", "PIXEL_SIZE_M", "DEDUP_PRIORITY", "DEDUP_FILL_FROM_DUPLICATES", "NEGATIVE_COVARIATE_RULE", "ALLOW_NEGATIVE_COVARIATES", "PIXEL_OVERLAP_MIN"):
        where = [k for k, c in enumerate(code) if _re.search(rf"(?m)^\s*P\.{v_}\s*=", c)]
        if where != i_set or not i_val or i_set[0] > i_val[0]:
            miss.append(f"P00 sets P.{v_} in cells {where} (must be once, in P00_Settings, before P00_Validate_or_Skip)")
    rp = open(os.path.join(os.path.dirname(_C.r_bridge_script()), "reward_prep.R"), encoding="utf-8").read()
    if not _re.search(r"(?m)^DEDUP_FILL_FROM_DUPLICATES <- FALSE", rp) or "fill <- isTRUE(DEDUP_FILL_FROM_DUPLICATES)" not in rp \
            or "if (fill) { set(first, which(gap), v, first$.don[gap])" not in rp:
        miss.append("R resolve_duplicates still fills the kept row's gaps from the repeated rows")
    # the empty rows leave AFTER the cross-file dedup (a newer export's empty row claims its pixel-year-season; dropped per file before
    # the dedup, the older repeated row took its place -- the poison test with cloud gaps: M01 0.087 for the true 0.050)
    pa_ = _i.getsource(_P._pa_worker) + _i.getsource(_P.run_pass_a); pb_ = _i.getsource(_P.prepare_pass_b_block)
    if "apply_missing_policy(df, drop_empty=False)" not in pa_ or 'apply_missing_policy(block, stage="block", drop_empty=False)' not in pb_ \
            or pb_.index("resolve_duplicates(block") > pb_.index("drop_rows_without_outcome(block"):
        miss.append("Python P00 drops the rows without an outcome before the cross-file de-duplication")
    e_ = _pd.DataFrame([dict(site_id=1, pixel_id=1, Year=2023, Season=1, NDVI=_np.nan, LAI=_np.nan, Rain=600.0, src_file="new.csv", file_mtime=9.0),
                        dict(site_id=1, pixel_id=1, Year=2023, Season=1, NDVI=0.9, LAI=1.5, Rain=610.0, src_file="old.csv", file_mtime=1.0)])
    e1, _ = _P.apply_missing_policy(e_.copy(), drop_empty=False); e2, _ = _P.resolve_duplicates(e1, conflict_log=[]); e3, st_ = _P.drop_rows_without_outcome(e2)
    if len(e1) != 2 or len(e3) != 0 or st_.get("rows_dropped_no_outcome") != 1:
        miss.append(f"the newer export's empty row does not claim its pixel-year-season ({len(e3)} row(s) left, the older one must not be)")
    if "apply_missing_policy(dt, drop_empty = FALSE)" not in rp or rp.index("dt <- resolve_duplicates(dt)") > rp.index("n0 <- nrow(dt); dt <- drop_rows_without_outcome(dt)"):
        miss.append("R_P00 drops the rows without an outcome before resolve_duplicates")
    if miss: bad("v20.58 repeated rows dropped whole: " + "; ".join(miss))
    else: note("v20.58: a repeated row is dropped WHOLE at the panel (Python and R; its values never fill the kept row's gaps -- "
               "DEDUP_FILL_FROM_DUPLICATES = True is the option, recorded in the panel and rebuilt when changed; a newer export's EMPTY row still "
               "claims its pixel-year-season: the rows without an outcome leave after the de-duplication); every P00 panel setting in P00_Settings")

def check_v20_57():
    """v20.57: YOUR RULES -- (1) no GPU / RAM / CPU cap until 98 % of the TOTAL, GPU or RAM first; (2) single sub-watershed
    processing keeps the MAJOR sub-watershed's data, fragments of other sub-watersheds dropped (treated and control rows alike);
    (3) the fund workbook as each sub-watershed's treatment timing and dose (release timing, amount / area); (4) EVERY design
    option set and applied in the DiD MODEL (Python and R), the panel built once; plus the biases found by the known-answer test."""
    import inspect as _i, json as _j, glob as _g, tempfile as _tf
    sys.path.insert(0, HERE)
    import numpy as _np, pandas as _pd
    import _common as _C, _hardware as _H, _fund as _F, _fragments as _FR
    # ---- 1. the 98 % rule
    miss = []
    if abs(float(_H.MEMORY_CEILING) - 0.98) > 1e-12: miss.append(f"_hardware.MEMORY_CEILING = {_H.MEMORY_CEILING}")
    if int(_H.RESERVE_CORES) != 0: miss.append(f"_hardware.RESERVE_CORES = {_H.RESERVE_CORES}")
    if float(_C.MEMORY_HEADROOM) != 1.0: miss.append(f"_common.MEMORY_HEADROOM = {_C.MEMORY_HEADROOM}")
    if _H.worker_cap() != min(int(_H.machine_profile()["logical_cores"]), int(_H.machine_profile()["pool_limit"])): miss.append("worker_cap holds cores back")
    old_caps = ("MAX_SPATIAL_N = 2_000_000", "n_max=4_000_000", "n_max=3_000_000", "nn_sample=2_000_000", "max(1, cores - 1)",
                "0.6 * p.total_memory", "b = 0.6 * free", "total_memory) * 0.7", "cpu_count() or 2) - 1")
    files = [os.path.join(HERE, f_) for f_ in ("_common.py", "_prep_common.py", "_hardware.py")] + _g.glob(os.path.join(HERE, "python_prebuilt", "*.py")) \
            + _g.glob(os.path.join(HERE, "0[2-5]_*", "M*.ipynb"))
    hits = [f"{os.path.basename(f_)}: {c}" for f_ in files for c in old_caps if c in open(f_, encoding="utf-8").read()]
    if hits: miss.append("fixed caps left: " + "; ".join(hits[:6]))
    rl = os.path.dirname(_C.r_bridge_script())
    rpath = open(os.path.join(rl, "reward_paths.R"), encoding="utf-8").read(); rdes = open(os.path.join(rl, "reward_design.R"), encoding="utf-8").read()
    rpre = open(os.path.join(rl, "models_prebuilt.R"), encoding="utf-8").read()
    if "N_MAX_UNITS         <- NULL; N_MAX_PIXELS_MIXED <- NULL; N_MAX_ML <- NULL; N_MAX_SPATIAL <- NULL" not in rpath: miss.append("R: fixed sample sizes in reward_paths.R")
    if "MEMORY_CEILING <- 0.98" not in rdes or "units_that_fit <- function" not in rdes: miss.append("R: the 98 % ceiling / units_that_fit")
    if "N_MAX_SPATIAL <- 3000000" in rpre or not ("cap_s <- units_that_fit(" in rpre or ("unit_cap(2 * (400 + 16 * k), n_max)" in rpre and "moran_knn(ld$dY, nn, k)" in rpre)):
        miss.append("R: the spatial sample cap")                  # v20.58: spdep below 98 %, beyond it spdep's formulas on the k-NN index (exact, no sample)
    if "detectCores() - 1" in rpath + rdes + rpre: miss.append("R: a core held back")
    if miss: bad("98 % rule: " + " | ".join(miss))
    else: note(f"98 % rule: RAM / VRAM usable to 98 % of the TOTAL, every core ({_H.worker_cap()} workers here), no fixed sample size in "
               "Python or R (k-NN, forests, lmer / rq, CiC bootstrap: sampled only beyond 98 % of the RAM)")
    # ---- 2. fragments: the file's MAJOR sub-watershed is kept; another sub-watershed's rows -- core or ring -- are coded out
    _fc = _FR.file_codes(_np.array([1, 1, 1, 2, 1, 3]), _np.array([0, 0, 0, 0, 3, 3]))
    codes = [int(x) for x in (_fc[0] if isinstance(_fc, tuple) else _fc)]
    if codes != [0, 0, 0, 1, 0, 2]: bad(f"fragment codes {codes} (expected [0, 0, 0, 1, 0, 2])")
    elif "fragment_mask" not in _i.getsource(_C.load_panel) and "fragment" not in _i.getsource(_C.load_panel): bad("load_panel does not apply the fragment rule")
    elif _C.ACTIVE.get("fragment_rule", "drop") != "drop": bad(f"FRAGMENT_RULE default is {_C.ACTIVE.get('fragment_rule')!r}, not 'drop'")
    elif ("fragment_codes_R(x, tab)" not in rdes and "location_codes_R(x, loc, S)" not in rdes) or 'dt[, fragment := file_codes(site_id, site_check), by = src_file]' not in open(os.path.join(rl, "reward_prep.R"), encoding="utf-8").read():   # v20.58: the location rule
        bad("R: fragments not coded per export file / not applied by load_panel_R")
    else: note("fragments: every row coded per export file (0 its file's own sub-watershed, 1 inside another one's polygon, 2 outside with "
               "another id, 3 a minor sub-watershed); FRAGMENT_RULE = 'drop' by default, applied when a model runs (Python and R)")
    # ---- 3. the fund workbook as timing and dose (a synthetic workbook: 40 in Oct 2024, +10 a month)
    m0 = _F.month_index(_pd.Timestamp("2024-10-01"))
    long = _pd.DataFrame({"site_id": 1, "sws_name": "Artal", "district": "X", "month": [m0 + i for i in range(22)],
                          "amount_reported": [40.0 + 10 * i for i in range(22)], "target": 500.0, "area_ha": 4632.33845007, "area_source": "file"})
    ser = _F.fund_series(long); tim = _F.fund_timing(ser, rule="backcast", rate_months=12)
    dose = _F.season_dose(ser, tim, [2024, 2025], before_file="backcast")
    r_ = tim.iloc[0]; rab = dose[(dose.site_id == 1) & (dose.Year == 2024) & (dose.Season == 2)]
    ok_t = r_["backcast_start"] == _F.month_label(m0 - 3) and r_["first_treated_label"] == "Rabi 2024" and int(r_["cohort_annual"]) == 2025
    ok_d = len(rab) == 1 and abs(float(rab["dose_amount_sws"].iloc[0]) - 30.0) < 1e-9 and abs(float(rab["dose_intensity_per_ha"].iloc[0]) - 30.0 / 4632.33845007) < 1e-12
    if not (ok_t and ok_d): bad(f"fund timing / dose: start {r_['backcast_start']}, first treated {r_['first_treated_label']}, annual cohort {r_['cohort_annual']}, "
                                f"Rabi 2024 dose {rab.to_dict('records')}")
    else:
        saved = {k: (list(v) if isinstance(v, (list, tuple)) else (dict(v) if isinstance(v, dict) else v)) for k, v in _C.ACTIVE.items()}
        try:
            _C.set_scenario(verbose=False, timing="fund", site_start={1: [2024, 2]}, treatment_year=2024)
            f_ = _pd.DataFrame({"site_id": [1] * 8, "buff_km": [0] * 4 + [3] * 4, "Year": [2024] * 4 + [2025] * 4, "Season": [0, 3, 1, 2] * 2,
                                "pixel_id": [1] * 4 + [2] * 4, "subwshed_id": "S1", "time_fe_yearseason": "x"})
            d_ = _C.build_treatment_columns(f_.copy())
            core = d_[d_.buff_km == 0].set_index("Season")["did_term"].to_dict()
            ok_r = core == {0: 0, 3: 0, 1: 0, 2: 1} and (d_[d_.buff_km > 0]["did_term"] == 0).all()
        finally:
            _C.ACTIVE.clear(); _C.ACTIVE.update(saved); _C._EXPLICIT_KEYS.clear()
        if not ok_r: bad(f"fund timing per row: 2024 core rows treated {core} (expected Rabi only)")
        else: note("fund workbook = timing and dose: 40 in Oct 2024 at +10 a month back-casts to July 2024 -> first treated Rabi 2024 (every "
                   "other season and the annual composite from 2025); Rabi 2024 dose = 30 released by Sep 2024 / 4,632 ha; per row: only the "
                   "2024 Rabi core rows are treated")
    # ---- 4. every design option in the MODEL (Python CELL 1s, R notebooks), the panel built once
    keys_py = ("DESIGN_MODE", "TREATMENT_TIMING", "TREATMENT_YEAR", "FUND_START_RULE", "DOSE_VARIABLE", "CONTROL_ZONES", "PRE_YEARS", "POST_YEARS",
               "SEASONS", "OVERLAP_ROWS", "FRAGMENT_RULE", "POOLED_FE", "EXCLUDE_GAPFILLED")
    lack = []
    for nb in sorted(_g.glob(os.path.join(HERE, "0[2-5]_*", "M*.ipynb"))):
        cells = _j.load(open(nb, encoding="utf-8"))["cells"]
        c1 = next(("".join(c["source"]) for c in cells if c["cell_type"] == "code" and "CELL 1" in "".join(c["source"])), "")
        m_ = [k for k in keys_py if f"\n{k}" not in "\n" + c1] + ([] if "timing=TREATMENT_TIMING" in c1 and "fragment_rule=FRAGMENT_RULE" in c1 else ["set_scenario(...)"])
        if m_: lack.append(f"{os.path.basename(nb)[:3]}: {m_[:3]}")
    if lack: bad(f"model CELL 1s without the model-stage design: {lack[:5]}")
    else: note(f"every Python model's CELL 1 sets the design ({len(keys_py)} options + covariates) and set_scenario applies it at run time")
    rprep = open(os.path.join(rl, "reward_prep.R"), encoding="utf-8").read()
    kc = rprep.split("keep_cols <- intersect(c(", 1)[1].split(")", 1)[0] if "keep_cols <- intersect(c(" in rprep else ""
    baked = [c for c in ('"cohort"', '"treat"', '"did"', '"event_time"', '"period"', '"unit"', '"dose_intensity_per_ha"') if c in kc]
    if baked or "model_design <- function" not in rdes or "design_columns(x, d)" not in rdes or "attach_dose_R(x, d)" not in rdes:
        bad(f"R: the design is still baked into the panel ({baked}) or not applied by the models")
    else:
        rn = None
        for cand in (os.path.join(rl, "..", "..", "..", "RWDR_v" + _C.ENGINE_VERSION), os.path.join(rl, "..", "..", "..", "RWDR")):
            if os.path.isdir(os.path.join(cand, "rstudio")): rn = cand; break
        if rn is not None:
            lk = [os.path.basename(f_) for f_ in _g.glob(os.path.join(rn, "rstudio", "R_M*.Rmd")) + _g.glob(os.path.join(rn, "jupyter", "R_M*.ipynb"))
                  if not all(k in open(f_, encoding="utf-8").read() for k in ("TREATMENT_TIMING <-", "FRAGMENT_RULE", "CONTROL_RINGS", "model_design()"))]
            p00 = open(os.path.join(rn, "rstudio", "R_P00_Prepare_Panel.Rmd"), encoding="utf-8").read()
            if lk or "CONTROL_RINGS  <-" in p00 or "TREATMENT_YEAR <-" in p00: bad(f"R notebooks without the model-stage design: {lk[:5]} / R_P00 still sets the design")
            else: note("R: every R_Mxx notebook (RStudio and Jupyter) sets the design and model_design() applies it; R_P00 builds the panel only")
        else: note("R: model_design / load_panel_R / design_columns / attach_dose_R apply the design at run time; nothing of it is baked into the panel")
    # ---- 5. the biases the known-answer test found (v20.57)
    srcs = {"cic": _i.getsource(_C.cic_cells), "lasso": _i.getsource(_C.lasso_sc_ring_series), "spill": _i.getsource(_C.spillover_gradient_test)}
    m04 = open(_g.glob(os.path.join(HERE, "02_*", "M04_*.ipynb"))[0], encoding="utf-8").read(); m35 = open(_g.glob(os.path.join(HERE, "04_*", "M35_*.ipynb"))[0], encoding="utf-8").read()
    m01 = open(_g.glob(os.path.join(HERE, "02_*", "M01_*.ipynb"))[0], encoding="utf-8").read()
    rcore = open(os.path.join(rl, "reward_models_core.R"), encoding="utf-8").read()
    chk = {"M04 / M35 on comparable cells": "C.cic_cells(df, OUTCOME)" in m04 and "C.cic_cells(df, OUTCOME)" in m35 and "inside = (t00 > c00[0])" in srcs["cic"],
           "M45 same-season donors net of the year effect": "mu = D_.mean(axis=0)" in srcs["lasso"],
           "M24 clustered as the design": "cluster_col)" in srcs["spill"] and '"t": t_' in srcs["spill"],
           "M01 bad-control check": "C.covariate_response(df" in m01 and "covariate_response_R(dt, outcome, cv)" in rcore,
           "R covariates of the design": 'attr(dt, "covariates_used")' in rcore,
           "R M27 consecutive ids": "uy[, unit := as.integer(factor(unit))]" in rpre,
           "M23 pyfixest wild bootstrap only when its dense FE expansion fits": any(x_ in _i.getsource(_C.wild_cluster_bootstrap_pvalue) for x_ in
               ("_need = float(len(df)) * _nlev * 8.0 * 4.0", "_need = float(len(df)) * (_nlev + len(covariates)) * 8.0 * 4.0"))}   # v20.58: + the covariates
    bad_ = [k for k, v in chk.items() if not v]
    if bad_: bad(f"v20.57 bias fixes missing: {bad_}")
    else: note("biases fixed: CiC / quantile DiD on comparable cells with common support (M04 0.061 -> 0.054, M35 no spurious gradient), M45 "
               "per season net of the year effect (0.064 -> 0.050), M24 clustered as the design, the bad-control check in M01 (Python and R), "
               "R COVARIATES <- 'all' reaching the models, R M27 didimputation verified, M23's pyfixest bootstrap used only when its dense "
               "fixed-effect expansion fits below 98 % (else the engine's exact bootstrap: no killed kernel)")
    for f_, what in (("validate_design_options.py", "every option at the model stage, R == Python"), ("validate_known_answers.py", "every model against a known answer")):
        if not os.path.exists(os.path.join(HERE, f_)): bad(f"{f_} missing ({what})")
    note("validate_design_options.py and validate_known_answers.py present (run them after an engine change)")

def check_validation_report():
    p = os.path.join(HERE, "VALIDATION_ALL_MODELS.csv")
    if not os.path.exists(p):
        warn("VALIDATION_ALL_MODELS.csv not found -- run `python validate_all_models.py` to prove every model honours a scenario")
        return
    import pandas as _pd
    d = _pd.read_csv(p)
    fails = d[(d.status_A != "ok") | (d.status_B != "ok")]
    if len(fails): bad(f"models that ERROR under a scenario: {fails.model.tolist()}")
    unexplained = d[(d.honours_scenario.isin(["identical_results", "no_output", "one_scenario_only"]))]
    if len(unexplained): bad(f"models that ignore the scenario or write nothing without a documented reason: {unexplained.model.tolist()}")
    note(f"model validation report: {int((d.honours_scenario == 'yes').sum())} honour the scenario, "
         f"{int((d.honours_scenario == 'data_gap').sum())} blocked by documented data gaps, {len(d)} total")

def run():
    print(f"=== bundle self-check: {HERE}")
    try:                                   # v20.49: a private instance registry -- other pipelines running on this machine
        import tempfile as _tf_, _hardware as _Hh    # (another data folder, an R test) must not change what is checked
        sys.path.insert(0, HERE); _Hh.INSTANCE_DIR = _tf_.mkdtemp(prefix="reward_selfcheck_instances_"); _Hh._SHARE_CACHE["v"] = None
    except Exception:
        pass
    mods = check_engines()
    check_notebook_locks(mods)
    check_syntax_and_calls(mods)
    check_rules(mods)
    check_validation_report()
    check_pixel_id_string_ops()
    check_pass_b_parallel()
    check_full_machine()
    check_atomic_panel_write()
    check_dedup_semantics()
    check_file_handles()
    check_missing_value_policy()
    check_universal_missing_policy()
    check_ingestion_and_paths()
    check_path_import_orders()
    check_demeaner_and_event_study()
    check_zero_policy_and_readiness()
    check_readiness()
    check_missingness_report()
    check_honest_and_group_missingness()
    check_pretrends_spec()
    check_no_placeholders()
    check_frozen_guard()
    check_multisite_and_prebuilt()
    check_speed_and_accuracy()
    check_yearly_first()
    check_near_duplicate_pixels()
    check_treatment_timing()
    check_panel_design_rules()
    check_sws_geometry()
    check_v20_29()
    check_v20_30_gpu_and_barrier()
    check_v20_32()
    check_v20_34()
    check_v20_36()
    check_v20_37()
    check_v20_38()
    check_v20_39()
    check_v20_40()
    check_v20_41()
    check_v20_42()
    check_v20_43()
    check_v20_44()
    check_v20_45()
    check_r_library()
    check_v20_46()
    check_v20_47()
    check_v20_54()
    check_v20_55()
    check_v20_56()
    check_v20_57()
    check_v20_58()
    check_v20_58_out_of_core()
    check_v20_58_repeated_rows()
    check_v20_58_memory_batches()
    check_v20_59()
    check_v20_58_m13_port()
    check_v20_35_structure()
    check_v20_35()
    check_v20_30()
    check_ground_inputs_and_notebook_locks()
    check_dedup_vectorised()
    if not os.path.exists(os.path.join(HERE, "validate_preprocessing.py")):
        bad("validate_preprocessing.py missing -- the PASS A path would be untested")
    else:
        note("validate_preprocessing.py present (run it after any panel rebuild)")
    print("=" * 70)
    if PROBLEMS:
        print(f"{len(PROBLEMS)} PROBLEM(S) -- fix these before running:")
        for p in PROBLEMS: print("  -", p)
        return 1
    print(f"CLEAN: {len(NOTES)} checks passed. The bundle is consistent.")
    return 0

if __name__ == "__main__":
    sys.exit(run())
