"""
_outofcore.py -- v20.58: WHEN THE DATA DO NOT FIT (YOUR RULE: beyond 98 % of the RAM / GPU memory -- never before).

Below 98 % every row is in RAM (and on the GPU) at once, one regression, no chunking. Beyond it the work does NOT stop and
is NEVER sampled: it goes OUT OF CORE, to the first engine of OUT_OF_CORE (_paths.py) that is installed:

    "dask"     Dask (dask.distributed LocalCluster): keeps the familiar PyData stack (pandas / numpy), no Java -- the default
    "spark"    Apache Spark (pyspark, local[all cores]): the enterprise engine for SQL-like heavy pipelines; needs Java 17+
    "batches"  the built-in batches: one partition after another in this process (always available -- the last resort)

EXACT, not approximate. The rows are split into PIXEL PARTITIONS (every row of a pixel -- all its years, seasons and series -- in one
partition, by a hash of pixel_id). Each partition runs the SAME code as the in-memory path (load_panel, build_treatment_columns, the
location rule, the missing-value policy ...); only ADDITIVE statistics cross between partitions: counts, sums, per-cell means, the
fixed-effects cross-products, the per-cluster score sums. The two-way fixed-effects estimators are solved EXACTLY from them (the unit
effects removed inside each partition, the period effects estimated jointly -- Frisch-Waugh-Lovell; the CR1 sandwich from the per-cluster
scores), so every number equals the in-memory number (validate_out_of_core.py proves it: in memory vs Dask vs Spark vs batches).

Which models run out of core: OOC_MODELS below (M01, M02, M16, M34 -- the four-model pipeline, and the same four in the full pipeline).
Every other model keeps the in-memory path; beyond 98 % it stops with a readable message naming the per-sub-watershed route (MS01).
"""
import os, sys, io, json, time, math, glob, shutil, contextlib, traceback, pickle, hashlib
import numpy as np
import pandas as pd

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWN_ENGINES = ("dask", "spark", "batches")
OOC_MODELS = ("M01", "M02", "M16", "M34")
ENGINE_LABEL = {"dask": "Dask", "spark": "Apache Spark", "batches": "built-in batches"}
_POOLS = {}
_WORKER_STATE_KEY = [None]


def _C():
    import _common as C
    return C


def _say(kind, msg):
    try:
        getattr(_C(), kind)(msg)
    except Exception:
        print(f"[{kind.upper()}] {msg}")


# ============================================================ configuration: which engine, and is the path forced
def engine_order():
    """The engines in YOUR order (OUT_OF_CORE in _paths.py); the built-in batches are always the last resort. A forced engine
    (REWARD_FORCE_OUT_OF_CORE, the checks only) goes first."""
    try:
        import _paths as _P
        order = [str(x).strip().lower() for x in (getattr(_P, "OUT_OF_CORE", KNOWN_ENGINES) or KNOWN_ENGINES)]
    except Exception:
        order = list(KNOWN_ENGINES)
    order = [e for e in order if e in KNOWN_ENGINES] or list(KNOWN_ENGINES)
    if "batches" not in order: order.append("batches")
    f = forced()
    if f in KNOWN_ENGINES: order = [f] + [e for e in order if e != f]
    return list(dict.fromkeys(order))


def forced():
    """REWARD_FORCE_OUT_OF_CORE = dask | spark | batches | auto (the checks: the out-of-core path on data that would fit)."""
    v = str(os.environ.get("REWARD_FORCE_OUT_OF_CORE", "") or "").strip().lower()
    if not v or v in ("0", "false", "no", "off"): return None
    return v if v in KNOWN_ENGINES else "auto"


def _java():
    """A Java runtime for Spark: JAVA_HOME, then PATH, then the jdk4py wheel (a JRE in a pip package)."""
    jh = os.environ.get("JAVA_HOME")
    if jh:
        for c in (os.path.join(jh, "bin", "java.exe"), os.path.join(jh, "bin", "java")):
            if os.path.exists(c): return c
    j = shutil.which("java")
    if j: return j
    try:
        import jdk4py
        return str(jdk4py.JAVA)
    except Exception:
        return None


def engine_status(name):
    """(available, detail) of one engine."""
    try:
        if name == "dask":
            import dask, distributed
            return True, f"dask {dask.__version__} / distributed {distributed.__version__}"
        if name == "spark":
            import pyspark
            j = _java()
            if not j: return False, f"pyspark {pyspark.__version__} is installed but no Java runtime was found (JAVA_HOME / PATH / pip install jdk4py)"
            return True, f"pyspark {pyspark.__version__} (Java: {j})"
        if name == "batches":
            return True, "built-in (one partition after another, in this process)"
    except Exception as e:
        return False, f"not installed ({type(e).__name__}: {str(e)[:80]}) -- P12 / the package list installs it"
    return False, "unknown engine"


def choose_engine(verbose=True):
    """The first available engine of engine_order(); every engine skipped is named with the reason."""
    skipped = []
    for e in engine_order():
        ok_, why = engine_status(e)
        if ok_:
            if verbose:
                _say("info", f"out of core: {ENGINE_LABEL[e]} ({why})" + (f"; skipped: " + "; ".join(skipped) if skipped else ""))
            return e
        skipped.append(f"{ENGINE_LABEL[e]}: {why}")
    return "batches"


def status_table(verbose=True):
    """The three engines on this machine (P12 prints it)."""
    rows = []
    for e in KNOWN_ENGINES:
        ok_, why = engine_status(e)
        rows.append({"engine": e, "available": ok_, "detail": why, "order": engine_order().index(e) + 1 if e in engine_order() else None})
    t = pd.DataFrame(rows)
    if verbose:
        _say("info", "out-of-core engines (used only beyond 98 % of the RAM, in this order: " + " -> ".join(engine_order()) + "):")
        print(t.to_string(index=False))
    return t


# ============================================================ the budget: 98 % of the RAM, split over the workers
def _budget():
    try:
        import _hardware as _H
        b = _H.ram_budget_bytes()
        if b is not None: return float(b)
    except Exception:
        pass
    try:
        import psutil
        vm = psutil.virtual_memory(); return max(0.0, vm.available - 0.02 * vm.total)
    except Exception:
        return 4e9


def _cores():
    try:
        import _hardware as _H
        return max(1, int(_H.machine_profile()["logical_cores"]))
    except Exception:
        return max(1, os.cpu_count() or 1)


def spill_dir(sub=""):
    """Where the partitions and the engines' spill files go: OUT_OF_CORE_SPILL_DIR (_paths.py), else <OUTPUT_DIR>/_out_of_core."""
    d = None
    try:
        import _paths as _P
        d = getattr(_P, "OUT_OF_CORE_SPILL_DIR", None)
    except Exception:
        pass
    if not d:
        C = _C()
        base = os.path.dirname(os.path.abspath(C.PREPARED_PANEL)) if getattr(C, "PREPARED_PANEL", None) else os.getcwd()
        d = os.path.join(base, "_out_of_core")
    d = os.path.join(d, sub) if sub else d
    os.makedirs(d, exist_ok=True)
    return d


# ============================================================ the state a worker needs: the design of THIS run
_PLAIN = (type(None), bool, int, float, str, np.integer, np.floating, np.bool_)
PRIVATE_STATE = ("_RESOLVED", "_SEASON_CHOICE", "_SEASON_SCAN", "_YEARLY_OUTCOME_SCAN", "_LOC_CACHE", "_CLUSTER_SAID", "_EXPLICIT_KEYS",
                 "CURRENT_OUTCOME", "CURRENT_MODEL_ID", "CURRENT_ESTIMATION_COLUMNS", "SITE_FILTER", "OUTCOME_LOOP_STATE")


def _is_plain(v, depth=0):
    if depth > 8: return False
    if isinstance(v, _PLAIN): return True
    if isinstance(v, (list, tuple, set, frozenset)): return all(_is_plain(x, depth + 1) for x in v)
    if isinstance(v, dict): return all(_is_plain(k, depth + 1) and _is_plain(x, depth + 1) for k, x in v.items())
    return False


def snapshot_state():
    """The engine's settings and the resolved design of this run, as plain data (every UPPER-CASE setting of _common and the caches
    of the design); the LAST_* results of the session are not state and are never sent."""
    C = _C(); st = {}
    for k, v in vars(C).items():
        if k.startswith("__") or k.startswith("LAST_"): continue
        if not (k.isupper() or k in PRIVATE_STATE): continue
        if callable(v) or isinstance(v, type(sys)): continue
        if _is_plain(v):
            st[k] = v
    try:
        import _hardware as _H
        st["__hardware__"] = {k: getattr(_H, k) for k in ("MEMORY_CEILING",) if hasattr(_H, k)}
    except Exception:
        pass
    blob = pickle.dumps(st)
    st["__key__"] = hashlib.sha1(blob).hexdigest()
    return st


def restore_state(st):
    """In a worker process: the parent's settings and design, in place (objects other modules hold stay the same objects)."""
    if not st or _WORKER_STATE_KEY[0] == st.get("__key__"): return
    C = _C()
    for k, v in st.items():
        if k.startswith("__"): continue
        cur = getattr(C, k, None)
        if isinstance(cur, dict) and isinstance(v, dict): cur.clear(); cur.update(v)
        elif isinstance(cur, set) and isinstance(v, (set, frozenset)): cur.clear(); cur.update(v)
        elif isinstance(cur, list) and isinstance(v, list): cur[:] = v
        else: setattr(C, k, v)
    try:
        import _hardware as _H
        for k, v in (st.get("__hardware__") or {}).items(): setattr(_H, k, v)
    except Exception:
        pass
    _WORKER_STATE_KEY[0] = st.get("__key__")


@contextlib.contextmanager
def _worker_scope():
    """Inside a task: the out-of-core flag on (no per-partition integrity stop, no per-partition design SE), no progress bars."""
    C = _C()
    old = (getattr(C, "_OOC_WORKER", False), getattr(C, "PROGRESS_STYLE", "text"))
    C._OOC_WORKER = True
    try:
        yield
    finally:
        C._OOC_WORKER = old[0]


def run_task(item):
    """The function every engine calls: (task name, payload, state) -> {ok, result, log, error}. Messages are captured (the parent
    prints the merged ones); an error is returned with its traceback, never swallowed."""
    name, payload, state, in_process = item
    buf = io.StringIO(); t0 = time.time()
    try:
        if not in_process:
            if ENGINE_DIR not in sys.path: sys.path.insert(0, ENGINE_DIR)
            try:
                import _hardware as _H
                _H.set_blas_threads(1)
            except Exception:
                pass
            restore_state(state)
        if name not in TASKS:                       # the model tasks live in _ooc_models (registered on import, in every worker)
            import _ooc_models  # noqa: F401
        fn = TASKS[name]
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf), _worker_scope():
            res = fn(payload)
        return {"ok": True, "result": res, "log": buf.getvalue()[-20000:], "seconds": time.time() - t0, "pid": os.getpid()}
    except BaseException as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-4000:], "log": buf.getvalue()[-8000:],
                "seconds": time.time() - t0, "pid": os.getpid(), "insufficient": type(e).__name__ == "InsufficientDataError"}


def _spark_run(kv):
    import sys as _s
    if ENGINE_DIR not in _s.path: _s.path.insert(0, ENGINE_DIR)
    import _outofcore as _O
    return kv[0], _O.run_task(kv[1])


# ============================================================ the pool: Dask, Spark or batches -- one interface
class Pool:
    """`with Pool() as p: results = p.map("task", payloads)`. The engine is started once per session and reused."""

    def __init__(self, engine=None, n_workers=None, bytes_per_task=None, label=""):
        self.engine = engine or choose_engine(verbose=False)
        B = _budget(); W = n_workers or _cores()
        if bytes_per_task:
            W = max(1, min(W, int(B / max(float(bytes_per_task), 1.0))))
        self.n_workers = max(1, int(W)); self.label = label
        self.mem_per_worker = max(256 * 2 ** 20, int(B / self.n_workers))

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def _dask(self):
        key = ("dask", self.n_workers)
        if key in _POOLS: return _POOLS[key]
        for k in [k for k in _POOLS if k[0] == "dask"]: shutdown_engine(k)
        import dask
        from dask.distributed import LocalCluster, Client
        os.environ["PYTHONPATH"] = ENGINE_DIR + os.pathsep + os.environ.get("PYTHONPATH", "")
        dask.config.set({"distributed.worker.memory.terminate": False, "distributed.worker.memory.pause": False,
                         "distributed.worker.memory.spill": 0.9, "distributed.worker.memory.target": 0.85,
                         "distributed.scheduler.work-stealing": True, "distributed.comm.timeouts.connect": "60s"})
        cl = LocalCluster(n_workers=self.n_workers, threads_per_worker=1, processes=True, memory_limit=self.mem_per_worker,
                          local_directory=spill_dir("dask_spill"), dashboard_address=None, silence_logs=40)
        c = Client(cl)
        try: c.run(lambda d: sys.path.insert(0, d) if d not in sys.path else None, ENGINE_DIR)
        except Exception: pass
        _POOLS[key] = (cl, c)
        return _POOLS[key]

    def _spark(self):
        key = ("spark", self.n_workers)
        if key in _POOLS: return _POOLS[key]
        for k in [k for k in _POOLS if k[0] == "spark"]: shutdown_engine(k)
        j = _java()
        if j and not os.environ.get("JAVA_HOME"): os.environ["JAVA_HOME"] = os.path.dirname(os.path.dirname(os.path.realpath(j)))
        os.environ["PYSPARK_PYTHON"] = sys.executable; os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
        os.environ["PYTHONPATH"] = ENGINE_DIR + os.pathsep + os.environ.get("PYTHONPATH", "")
        os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
        from pyspark.sql import SparkSession
        drv = max(512, int(min(self.mem_per_worker * self.n_workers, _budget()) / 2 ** 20 * 0.25))
        sp = (SparkSession.builder.master(f"local[{self.n_workers}]").appName("REWARD-out-of-core")
              .config("spark.driver.memory", f"{drv}m").config("spark.local.dir", spill_dir("spark_spill"))
              .config("spark.ui.enabled", "false").config("spark.ui.showConsoleProgress", "false")
              .config("spark.python.worker.reuse", "true").config("spark.task.maxFailures", "1")
              .config("spark.driver.maxResultSize", "0").config("spark.executorEnv.PYTHONPATH", os.environ["PYTHONPATH"])
              .getOrCreate())
        try: sp.sparkContext.setLogLevel("ERROR")
        except Exception: pass
        _POOLS[key] = (sp, sp.sparkContext)
        return _POOLS[key]

    def map(self, name, payloads, what=""):
        """Run TASKS[name] on every payload; results in payload order. A failed task stops the step with its reason and traceback."""
        items = list(payloads)
        if not items: return []
        C = _C(); state = snapshot_state() if self.engine != "batches" else None
        t0 = time.time()
        if self.engine == "dask":
            cl, c = self._dask()
            futs = c.map(run_task, [(name, p, state, False) for p in items], pure=False)
            out = c.gather(futs)
        elif self.engine == "spark":
            sp, sc = self._spark()
            rdd = sc.parallelize(list(enumerate([(name, p, state, False) for p in items])), numSlices=len(items))
            got = dict(rdd.map(_spark_run).collect())
            out = [got[i] for i in range(len(items))]
        else:
            out = []
            for i, p in enumerate(items):
                snap = _batch_snapshot()
                try:
                    out.append(run_task((name, p, None, True)))
                finally:
                    _batch_restore(snap)
        bad = [r for r in out if not r.get("ok")]
        if bad:
            r = bad[0]
            _say("fail", f"out of core ({ENGINE_LABEL[self.engine]}): {len(bad)} of {len(items)} task(s) of '{name}' failed -- first: {r.get('error')}")
            if r.get("log"): print(r["log"][-3000:])
            print(r.get("trace", ""))
            exc = C.InsufficientDataError if r.get("insufficient") else RuntimeError
            raise exc(f"out-of-core step '{name}' failed on {ENGINE_LABEL[self.engine]}: {r.get('error')}")
        C.trace(f"out of core: {len(items)} x {name} on {ENGINE_LABEL[self.engine]} in {time.time() - t0:.1f} s")
        return out


# in-process batches: a task must not leave the partition's LAST_* results or caches in the parent
_BATCH_KEYS = ("LAST_LOAD_INFO", "LAST_DESIGN_INFO", "LAST_FIT_INFO", "LAST_CLUSTER_USED", "LAST_INTEGRITY", "LAST_ENGINE", "LAST_DESIGN_SE",
               "LAST_DESIGN_COUNTS", "LAST_ANALYSIS", "LAST_EVENT_VCOV", "SCREEN_REPORT", "_INTEGRITY_SEEN")


def _batch_snapshot():
    import copy as _cp
    C = _C(); snap = {}
    for k in _BATCH_KEYS:
        v = getattr(C, k, None)
        if isinstance(v, dict): snap[k] = dict(v)
        elif isinstance(v, list): snap[k] = list(v)
    return snap


def _batch_restore(snap):
    C = _C()
    for k, v in snap.items():
        cur = getattr(C, k, None)
        if isinstance(cur, dict): cur.clear(); cur.update(v)
        elif isinstance(cur, list): cur[:] = v


def shutdown_engine(key=None):
    for k in ([key] if key else list(_POOLS)):
        obj = _POOLS.pop(k, None)
        if obj is None: continue
        try:
            if k[0] == "dask": obj[1].close(); obj[0].close()
            elif k[0] == "spark": obj[0].stop()
        except Exception:
            pass


# ============================================================ pixel partitions
def pixel_partition(pixel_ids, K):
    """The partition (0..K-1) of each row: a hash of pixel_id -- every row of a pixel lands in the same partition, and the pixels of
    one area are spread over all partitions (splitmix64 on the integer ids; pandas' stable hash on any other id)."""
    v = np.asarray(pixel_ids)
    if v.dtype.kind in "iu":
        with np.errstate(over="ignore"):
            z = v.astype(np.uint64) + np.uint64(0x9E3779B97F4A7C15)
            z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
            z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
            z = z ^ (z >> np.uint64(31))
        return (z % np.uint64(K)).astype(np.int64)
    h = pd.util.hash_array(pd.Series(v).astype(str).values.astype(object))
    return (h % np.uint64(K)).astype(np.int64)


def _read_columns(columns, path, season_rule=True):
    """The columns load_panel reads for `columns` from `path` (the same rules: Season, the derivable time columns, the optional and
    the location columns)."""
    import pyarrow.parquet as pq
    C = _C()
    names = set(pq.ParquetFile(path).schema_arrow.names)
    need = set(columns) if columns else set(names)
    if season_rule: need.add("Season")
    DER = {"time_fe_year", "time_fe_season", "time_fe_yearseason", "season_sort_rank"}
    der = (need & DER) - names
    if der: need = (need - der) | {"Year", "Season"}
    need -= (need & set(C.OPTIONAL_READ_COLUMNS)) - names
    need |= {c for c in C.LOCATION_COLUMNS if c in names}
    need |= {c for c in ("pixel_id",) if c in names}
    miss = sorted(need - names)
    if miss:
        raise C.InsufficientDataError(f"panel lacks required columns {miss}")
    return sorted(need)


def _bytes_per_row(path, cols):
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    try:
        if not pf.num_row_groups: return 64.0, 0
        t = pf.read_row_group(0, columns=cols)
        n = max(t.num_rows, 1)
        return float(t.to_pandas().memory_usage(deep=True).sum()) / n, int(pf.metadata.num_rows)
    finally:
        try: pf.close()
        except Exception: pass


def plan_partitions(source, cols, copies=None, n_workers=None):
    """How many pixel partitions: each one, with the working copies the models make of it (MEMORY_COPIES + 2), fits in its worker's
    share of the RAM below 98 %. REWARD_OOC_PARTITIONS (the checks) sets the number."""
    C = _C()
    bpr, n = _bytes_per_row(source, cols)
    copies = float(copies or (float(C.MEMORY_COPIES) + 2.0))
    W = int(n_workers or _cores())
    B = _budget()
    per_worker = max(64 * 2 ** 20, B / max(W, 1))
    rows_per_part = max(10_000, int(per_worker / max(bpr * copies, 1.0)))
    K = max(1, int(math.ceil(n / rows_per_part)))
    env = os.environ.get("REWARD_OOC_PARTITIONS")
    if env:
        try: K = max(1, int(env))
        except Exception: pass
    elif forced():
        K = max(K, 4)
    return {"K": int(K), "rows": int(n), "bytes_per_row": bpr, "copies": copies, "workers": W, "budget": B,
            "need_in_memory": bpr * n * float(C.MEMORY_COPIES)}


# ============================================================ tasks (run in the workers; module-level so every engine can call them)
def _t_shuffle(p):
    """Rows of row groups [a, b) of the source -> one file per pixel partition (the source's order kept inside each partition)."""
    import pyarrow as pa, pyarrow.parquet as pq
    pf = pq.ParquetFile(p["source"])
    counts = np.zeros(p["K"], np.int64); written = []
    try:
        tabs = [pf.read_row_group(i, columns=p["cols"]) for i in range(p["a"], p["b"])]
    finally:
        try: pf.close()
        except Exception: pass
    tabs = [t for t in tabs if t.num_rows]
    if not tabs: return {"counts": counts.tolist(), "written": written}
    t = pa.concat_tables(tabs) if len(tabs) > 1 else tabs[0]
    part = pixel_partition(t["pixel_id"].to_numpy(zero_copy_only=False), p["K"])
    order = np.argsort(part, kind="stable")
    ps = part[order]
    cuts = np.flatnonzero(np.diff(ps)) + 1
    starts = np.concatenate([[0], cuts]); ends = np.concatenate([cuts, [len(ps)]])
    for s_, e_ in zip(starts, ends):
        k = int(ps[s_]); idx = order[s_:e_]
        sub = t.take(pa.array(idx))
        d = os.path.join(p["out"], f"p{k:05d}"); os.makedirs(d, exist_ok=True)
        f = os.path.join(d, f"t{p['task']:06d}.parquet")
        pq.write_table(sub, f, compression="zstd"); written.append(f); counts[k] += sub.num_rows
    return {"counts": counts.tolist(), "written": written}


def _merge_partition(folder, dest):
    import pyarrow as pa, pyarrow.parquet as pq
    files = sorted(glob.glob(os.path.join(folder, "t*.parquet")))
    if not files: return 0
    tabs = [pq.read_table(f) for f in files]
    schema = tabs[0].schema
    try:
        t = pa.concat_tables(tabs, promote_options="permissive")
    except TypeError:
        t = pa.concat_tables(tabs)
    t = t.replace_schema_metadata(schema.metadata)
    pq.write_table(t, dest, compression="zstd", row_group_size=max(1, min(t.num_rows, 1_000_000)))
    return t.num_rows


def _screen_stats(df, outcome):
    """The outcome screen's pieces of one partition: per Year x Season n, mean, M2 (for the SD across pixels), treated / control rows."""
    C = _C()
    if outcome not in df.columns or "Year" not in df.columns or not len(df): return []
    y = pd.to_numeric(df[outcome], errors="coerce").values.astype("float64"); fin = np.isfinite(y)
    season = df["Season"].values if "Season" in df.columns else np.zeros(len(df), int)
    tr = (pd.to_numeric(df["buff_km"], errors="coerce").values == C.TREAT_CORE_BUFFKM) if "buff_km" in df.columns else np.zeros(len(df), bool)
    t = pd.DataFrame({"Year": pd.to_numeric(df["Year"], errors="coerce").values, "Season": season, "tr": tr, "y": y})[fin]
    if not len(t): return []
    g = t.groupby(["Year", "Season"]).agg(n=("y", "size"), mean=("y", "mean"), var=("y", "var"), nt=("tr", "sum"), vmin=("y", "min"), vmax=("y", "max"))
    g["var"] = g["var"].fillna(0.0)
    return [(float(Y), int(S), int(r["n"]), float(r["mean"]), float(r["var"] * (r["n"] - 1)), int(r["nt"]), int(r["n"] - r["nt"]), float(r["vmin"]), float(r["vmax"]))   # v20.59: + min, max
            for (Y, S), r in g.iterrows()]


def _t_load(p):
    """One pixel partition through load_panel (the loader every model uses), the outcome screen left for the whole panel."""
    import pyarrow as pa, pyarrow.parquet as pq
    C = _C()
    src = os.path.join(p["dir"], f"p{p['k']:05d}.parquet")
    n0 = _merge_partition(os.path.join(p["dir"], f"p{p['k']:05d}"), src) if not os.path.exists(src) else pq.ParquetFile(src).metadata.num_rows
    out = os.path.join(p["dir"], f"loaded_{p['k']:05d}.parquet")
    if not n0:
        return {"k": p["k"], "rows": 0, "scanned": 0, "info": {}, "screen": [], "path": None}
    o = p["outcome"]
    if o:                                                   # the seasons rule of the WHOLE panel (a partition may lack the annual rows)
        C._SEASON_CHOICE[(src, o)] = p["season_mode"]
        C._YEARLY_OUTCOME_SCAN[(src, o)] = p["season_mode"] == "yearly"
    C._SEASON_SCAN[src] = bool(p["has_yearly"])
    try:
        df = C.load_panel(columns=p["columns"], path=src, finite_only=p.get("finite_only", True), screen=False)
    except C.InsufficientDataError as e:
        if "no rows survived" in str(e):
            return {"k": p["k"], "rows": 0, "scanned": int(n0), "info": dict(C.LAST_LOAD_INFO), "screen": [], "path": None, "empty": str(e)}
        raise
    info = dict(C.LAST_LOAD_INFO)
    scr = _screen_stats(df, o) if o else []
    tab = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(tab, out, compression="zstd")
    return {"k": p["k"], "rows": int(len(df)), "scanned": int(n0), "info": info, "screen": scr, "path": out,
            "cols": list(df.columns), "yearly_filled": int(info.get("yearly_covariates_filled", 0) or 0)}


# ============================================================ the panel of one outcome, out of core
class OOCPanel:
    """What load_panel returns out of core: the panel of THIS outcome in K pixel partitions on disk (each loaded by load_panel itself),
    the load report of the whole panel, and the outcome screen decided on the whole panel."""
    _ooc = True

    def __init__(self, **kw):
        self.__dict__.update(kw)

    @property
    def columns(self): return list(self.cols)

    def __len__(self): return int(self.rows)

    def __repr__(self):
        return f"OOCPanel({self.outcome}: {self.rows:,} rows in {len(self.paths)} pixel partitions, {ENGINE_LABEL[self.engine]})"


def load_panel_ooc(columns, finite_only=True, engine=None, verbose=True):
    """load_panel beyond 98 % of the RAM: the same rows, in pixel partitions. Returns an OOCPanel."""
    import pyarrow.parquet as pq
    C = _C()
    t0 = time.time()
    C._ensure_resolved()
    o = C.CURRENT_OUTCOME
    ef = C.estimator_file_for(columns)
    source = ef or C.PREPARED_PANEL
    if not os.path.exists(source):
        raise C.InsufficientDataError(f"Prepared panel not found at {source}. Run 01_Panel_Preparation/P00_RUN_ALL first.")
    C.panel_dedup_note()
    if ef: _say("info", f"reading the per-variable estimator file {os.path.basename(ef)} (out of core)")
    cols = _read_columns(columns, source)
    eng = engine or (forced() if forced() in KNOWN_ENGINES else None) or choose_engine(verbose=False)
    plan = plan_partitions(source, cols)
    K = plan["K"]
    tag = hashlib.sha1(json.dumps([source, os.path.getmtime(source), cols, K, C.scenario_tag(), o, time.time()], default=str).encode()).hexdigest()[:10]
    root = spill_dir(f"panel_{o or 'x'}_{tag}")
    _say("info", f"{o or 'panel'}: every row needs ~{plan['need_in_memory'] / 1e9:.2f} GB in RAM ({plan['rows']:,} rows x "
                 f"{plan['bytes_per_row']:.0f} B x {C.MEMORY_COPIES:g} copies) -- " + ("the out-of-core path is FORCED (a check)" if forced() else
                 f"above 98 % of the RAM ({plan['budget'] / 1e9:.1f} GB left)") + f": OUT OF CORE on {ENGINE_LABEL[eng]}, {K} pixel partitions "
                 f"(every row of a pixel in one partition; nothing is sampled) -> {root}")
    pf = pq.ParquetFile(source)
    try:
        nrg = pf.num_row_groups
        rg_bytes = [pf.metadata.row_group(i).total_byte_size for i in range(nrg)]
    finally:
        try: pf.close()
        except Exception: pass
    per_task = max(1, int(plan["budget"] / max(plan["workers"], 1) / 4))
    tasks, a, acc = [], 0, 0
    for i in range(nrg):
        acc += rg_bytes[i] * 3
        if acc >= per_task and i + 1 > a:
            tasks.append((a, i + 1)); a, acc = i + 1, 0
    if a < nrg: tasks.append((a, nrg))
    pool = Pool(eng, label="load")
    got = pool.map("shuffle", [{"source": source, "cols": cols, "K": K, "a": a_, "b": b_, "out": root, "task": j}
                              for j, (a_, b_) in enumerate(tasks)])
    counts = np.sum([np.asarray(g["result"]["counts"]) for g in got], axis=0) if got else np.zeros(K, int)
    has_yearly = C.panel_has_yearly(source)
    mode = C.seasons_mode(path=source, verbose=False) if o else None
    parts = [k for k in range(K) if counts[k] > 0]
    loaded = pool.map("load", [{"dir": root, "k": k, "columns": list(columns), "outcome": o, "season_mode": mode, "has_yearly": has_yearly,
                                "finite_only": finite_only} for k in parts])
    res = [g["result"] for g in loaded]
    paths = [r["path"] for r in res if r.get("path")]
    if not paths:
        raise C.InsufficientDataError("no rows survived the filters -- the location rule (every row of the processed sub-watershed(s) must lie "
                                      "inside its own polygon: FRAGMENT_RULE / OVERLAP_ROWS), SUB_WATERSHEDS / the sub-watershed filter, or the Season rule")
    info = merge_load_info([r["info"] for r in res])
    C.LAST_LOAD_INFO.clear(); C.LAST_LOAD_INFO.update(info)
    _report_load(info, o)
    rows = int(sum(r["rows"] for r in res)); scanned = int(sum(r["scanned"] for r in res))
    bad, rep = screen_decision([x for r in res for x in r["screen"]], o) if o else (set(), [])
    cols_out = next((r["cols"] for r in res if r.get("cols")), [])
    _say("ok", f"kept {rows:,} of {scanned:,} scanned rows x {len(cols_out)} cols -- out of core, {len(paths)} pixel partitions "
               f"({ENGINE_LABEL[eng]}, {time.time() - t0:.1f} s)")
    return OOCPanel(outcome=o, columns_requested=list(columns), cols=cols_out, paths=paths, root=root, engine=eng, K=K, rows=rows,
                    scanned=scanned, screen_bad=bad, screen_report=rep, source=source, load_info=info, plan=plan)


def merge_load_info(infos):
    """LAST_LOAD_INFO of the whole panel from the partitions' (counts add; the settings are the same in every partition)."""
    out = {}
    for inf in infos:
        for k, v in (inf or {}).items():
            if k in ("location_rows", "gapfilled_by_group"):
                d = out.setdefault(k, {})
                for kk, vv in (v or {}).items(): d[kk] = d.get(kk, 0) + int(vv)
            elif isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, float, np.integer, np.floating)):
                out.setdefault(k, v)
            else:
                out[k] = out.get(k, 0) + v
    C = _C()
    out["fragment_rows_dropped"] = int(sum(v for k, v in (out.get("location_rows") or {}).items() if int(str(k).split("|")[0]) in C.location_drop_codes()))
    return out


def _report_load(info, o):
    """The messages load_panel prints, once, for the whole panel."""
    C = _C()
    lr = info.get("location_rows") or {}
    if lr:
        C.location_report_lines({(int(k.split("|")[0]), bool(int(k.split("|")[1])), bool(int(k.split("|")[2]))): int(v) for k, v in lr.items()},
                                label=f"{o or 'panel'}: ")
    if info.get("yearly_covariates_filled"):
        _say("info", f"annual rows: {int(info['yearly_covariates_filled']):,} covariate values the annual composite lacks were filled with the same "
                     f"pixel-year's seasonal mean (yearly-first keeps its weather adjustment)")
    if info.get("gapfilled_rows_excluded"):
        gb = info.get("gapfilled_by_group") or {}
        _say("info", f"gap-filled rows left out: {int(info['gapfilled_rows_excluded']):,} (" + ", ".join(f"{k} {v:,}" for k, v in gb.items() if v)
                     + ") -- the exporter blended their unpublished days with the 3-year historical mean (EXCLUDE_GAPFILLED)")
    if info.get("ring_rows_not_loaded"):
        _say("info", f"{int(info['ring_rows_not_loaded']):,} rows outside this scenario's rings were not loaded (control rings {tuple(C.ACTIVE['control_zones'])})")
    nm, ns = int(info.get("rows_dropped_missing", 0) or 0), int(info.get("rows_seen", 0) or 0)
    if nm:
        share = nm / max(ns, 1)
        _say("warn" if share > 0.25 else "info", f"missing-value policy: excluded {nm:,} of {ns:,} rows ({share:.1%}) where "
             f"{info.get('estimation_columns')} is NaN or exactly zero ({int(info.get('rows_dropped_zero', 0) or 0):,} of them zero-valued) -- they cannot enter a regression")


def screen_decision(stats, outcome, refuse=True):
    """screen_outcome_frame on the whole panel from the partitions' pieces: (the Year x Season cells left out, the report rows).
    v20.59: the same decisions, evidence file (OUTCOME_SCREEN_<outcome>.csv), rule (drop / keep / off) and refusal text as in memory."""
    C = _C()
    rule = C.screen_rule()
    if rule == "off" or not stats: return set(), []
    acc = {}
    for Y, S, n, mean, m2, nt, nc, vmin, vmax in stats:
        a = acc.get((Y, S))
        if a is None: acc[(Y, S)] = [n, mean, m2, nt, nc, vmin, vmax]; continue
        n1, m1, q1 = a[0], a[1], a[2]; N = n1 + n; dlt = mean - m1
        a[1] = m1 + dlt * n / N; a[2] = q1 + m2 + dlt * dlt * n1 * n / N; a[0] = N; a[3] += nt; a[4] += nc
        a[5] = min(a[5], vmin); a[6] = max(a[6], vmax)
    keys = sorted(acc)
    g = pd.DataFrame([{"Year": k[0], "Season": k[1], "n": a[0], "mean": a[1], "sd": (math.sqrt(a[2] / (a[0] - 1)) if a[0] > 1 else np.nan),
                       "vmin": a[5], "vmax": a[6], "n_treated": a[3], "n_control": a[4], "n_pixels": np.nan} for k, a in zip(keys, [acc[k] for k in keys])]).set_index(["Year", "Season"])
    g = C.screen_decide_table(g, outcome)
    badset, rep, path = C.screen_report(g, outcome, rule, verbose=True)
    yrs = sorted(set(int(k[0]) for k in keys if (int(k[0]), int(k[1])) not in badset))
    C.screen_refuse_years(outcome, yrs, len(rep), len(g), path, refuse=refuse)
    return badset, rep


# ============================================================ the model's analysis sample, out of core
def read_part(path, bad=None):
    """One loaded partition as load_panel returned it (its location rule applied), the outcome screen of the whole panel applied."""
    import pyarrow.parquet as pq
    d = pq.read_table(path).to_pandas()
    d.attrs["location_rule_applied"] = True
    if bad and len(d):
        yy = pd.to_numeric(d["Year"], errors="coerce").fillna(-1).astype("int64").values
        ss = pd.to_numeric(d["Season"], errors="coerce").fillna(-1).astype("int64").values if "Season" in d.columns else np.zeros(len(d), np.int64)
        m = pd.MultiIndex.from_arrays([yy, ss]).isin([(int(a), int(b)) for a, b in bad])
        if m.any(): d = d[~m]
    return d


def _t_pass_b_piece(p):
    """P00 PASS B out of core: one pixel-range piece of a block through prepare_pass_b_block (the settings of P00 in force), its rows
    written one file per sub-watershed (the parent writes the block in the panel's order)."""
    import importlib, pyarrow as pa, pyarrow.parquet as pq
    m = importlib.import_module("_prep_common")
    for k, v in (p.get("cfg") or {}).items(): setattr(m, k, v)
    m.KNOWN_SUBWSHED_NAMES = list(p.get("known") or m.KNOWN_SUBWSHED_NAMES)
    yr, se = int(p["key"][0]), int(p["key"][1])
    src = m.ShardParts(p["files"]) if len(p["files"]) > 1 else p["files"][0]
    dose = pd.DataFrame(p["dose"]) if p.get("dose") is not None else None
    cw = pd.DataFrame(p["cw"]) if p.get("cw") is not None else None
    block, dup_log, removed, kinds, filled, n_pix, mp = m.prepare_pass_b_block(yr, se, src, dose, cw)
    sv = block["subwshed_id"].astype(str).values; outs = {}
    for i, s_ in enumerate(pd.unique(sv)):
        f = f"{p['out']}_{i:04d}.parquet"
        pq.write_table(pa.Table.from_pandas(block[sv == s_], preserve_index=False), f, compression="zstd"); outs[str(s_)] = f
    return {"outs": outs, "rows": int(len(block)), "dup_log": dup_log, "removed": int(removed), "kinds": dict(kinds or {}), "filled": int(filled or 0),
            "n_pix": int(n_pix), "mp": mp}


TASKS = {"shuffle": _t_shuffle, "load": _t_load, "pass_b_piece": _t_pass_b_piece}


def register(name, fn):
    TASKS[name] = fn
    return fn


def cleanup(obj):
    """Remove the partitions of an OOCPanel (temporary files under the spill folder -- nothing else is ever removed)."""
    try:
        root = os.path.abspath(getattr(obj, "root", "") or "")
        base = os.path.abspath(spill_dir())
        if root and os.path.isdir(root) and os.path.dirname(root) == base and os.path.basename(root).startswith("panel_"):
            shutil.rmtree(root, ignore_errors=True)
    except Exception:
        pass
