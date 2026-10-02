"""
reward_ooc_engine.py -- v20.58: Dask and Apache Spark for the R pipeline's OUT-OF-CORE passes (lib/reward_outofcore.R).

Beyond 98 % of the RAM the R pipeline splits the panel into pixel partitions and runs one R task per partition
(Rscript lib/reward_ooc_task.R ...). This helper runs those tasks on Dask (a LocalCluster, every core) or on Spark
(local[cores]; Java 17+), as a SERVER for the R session: R writes a job file (the task commands), the helper runs them and
writes the results; it stops when R says so, when the R session ends, or after 2 hours without a job.

    python reward_ooc_engine.py --status <out.json>
    python reward_ooc_engine.py --serve <dir> --engine dask|spark --workers N --parent <R pid> [--memory B] [--spill D] [--log F]

Nothing here computes a number: the R code of each partition task is the same R code the R batches run in the session, so every
engine gives the same result (tests/run_all_tests.R scenario H).
"""
import os, sys, json, time, glob, shutil, subprocess, traceback


def _java():
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


def status():
    out = {}
    try:
        import dask, distributed
        out["dask"] = {"ok": True, "detail": f"dask {dask.__version__} / distributed {distributed.__version__} (Python {sys.version.split()[0]}: {sys.executable})"}
    except Exception as e:
        out["dask"] = {"ok": False, "detail": f"not installed in {sys.executable} ({type(e).__name__}: {str(e)[:80]}) -- pip install \"dask[distributed]\""}
    try:
        import pyspark
        j = _java()
        out["spark"] = ({"ok": True, "detail": f"pyspark {pyspark.__version__} (Java: {j})"} if j else
                        {"ok": False, "detail": f"pyspark {pyspark.__version__} is installed but no Java runtime was found (JAVA_HOME / PATH / pip install jdk4py)"})
    except Exception as e:
        out["spark"] = {"ok": False, "detail": f"not installed in {sys.executable} ({type(e).__name__}: {str(e)[:80]}) -- pip install pyspark"}
    return out


def run_cmd(item):
    """One partition task: its own R process. The result file is written by R; here only the exit status and the last output."""
    t0 = time.time()
    try:
        p = subprocess.run(item["cmd"], capture_output=True, text=True)
        return {"id": item["id"], "rc": p.returncode, "secs": time.time() - t0, "out": (p.stdout or "")[-3000:], "err": (p.stderr or "")[-3000:]}
    except Exception as e:
        return {"id": item["id"], "rc": -1, "secs": time.time() - t0, "out": "", "err": f"{type(e).__name__}: {e}"}


def _alive(pid):
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except Exception:
        pass
    if os.name == "nt":                                  # never os.kill(pid, 0) on Windows (it would TERMINATE the process)
        try:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
            if not h: return False
            code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code)); ctypes.windll.kernel32.CloseHandle(h)
            return code.value == 259                       # STILL_ACTIVE
        except Exception:
            return True
    try:
        os.kill(int(pid), 0); return True
    except Exception:
        return False


def _write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(obj, f)
    os.replace(tmp, path)


class Engine:
    def __init__(self, name, workers, memory, spill):
        self.name, self.workers = name, max(1, int(workers))
        self.memory = max(256 * 2 ** 20, int(float(memory or 0))) if memory else None
        self.spill = spill or os.path.join(os.getcwd(), f"{name}_spill")
        os.makedirs(self.spill, exist_ok=True)
        if name == "dask":
            import dask
            from dask.distributed import LocalCluster, Client
            dask.config.set({"distributed.worker.memory.terminate": False, "distributed.worker.memory.pause": False,
                             "distributed.scheduler.work-stealing": True, "distributed.comm.timeouts.connect": "60s"})
            kw = dict(n_workers=self.workers, threads_per_worker=1, processes=True, local_directory=self.spill,
                      dashboard_address=None, silence_logs=40)
            if self.memory: kw["memory_limit"] = self.memory
            self.cluster = LocalCluster(**kw); self.client = Client(self.cluster)
        elif name == "spark":
            j = _java()
            if not j: raise RuntimeError("no Java runtime for Spark")
            if not os.environ.get("JAVA_HOME"): os.environ["JAVA_HOME"] = os.path.dirname(os.path.dirname(os.path.realpath(j)))
            os.environ["PYSPARK_PYTHON"] = sys.executable; os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
            os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
            from pyspark.sql import SparkSession
            self.spark = (SparkSession.builder.master(f"local[{self.workers}]").appName("REWARD-R-out-of-core")
                          .config("spark.driver.memory", "1g").config("spark.local.dir", self.spill)
                          .config("spark.ui.enabled", "false").config("spark.ui.showConsoleProgress", "false")
                          .config("spark.python.worker.reuse", "true").config("spark.task.maxFailures", "1")
                          .config("spark.driver.maxResultSize", "0").getOrCreate())
            try: self.spark.sparkContext.setLogLevel("ERROR")
            except Exception: pass
        else:
            raise ValueError(f"unknown engine {name}")

    def map(self, items):
        if self.name == "dask":
            futs = self.client.map(run_cmd, items, pure=False)
            return self.client.gather(futs)
        sc = self.spark.sparkContext
        got = sc.parallelize(list(items), numSlices=max(1, len(items))).map(run_cmd).collect()
        by = {g["id"]: g for g in got}
        return [by[i["id"]] for i in items]

    def close(self):
        try:
            if self.name == "dask": self.client.close(); self.cluster.close()
            else: self.spark.stop()
        except Exception:
            pass


def serve(a):
    d = a["serve"]; os.makedirs(d, exist_ok=True)
    if a.get("log"):
        f = open(a["log"], "a", buffering=1); sys.stdout = f; sys.stderr = f
    try:
        eng = Engine(a["engine"], a.get("workers", 1), a.get("memory"), a.get("spill"))
    except Exception as e:
        _write(os.path.join(d, "failed.json"), {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-3000:]})
        return 1
    _write(os.path.join(d, "ready.json"), {"engine": a["engine"], "workers": eng.workers, "pid": os.getpid(), "python": sys.executable})
    parent = a.get("parent"); last = time.time(); beat = 0.0; why = "stopped by R"
    try:
        while True:
            now = time.time()
            if now - beat > 2:
                with open(os.path.join(d, "alive"), "w") as f: f.write(str(now))
                beat = now
            if os.path.exists(os.path.join(d, "stop")): break
            if parent and not _alive(parent): why = "the R session ended"; break
            if now - last > 7200: why = "2 hours without a job"; break
            jobs = sorted(glob.glob(os.path.join(d, "job_*.json")))
            jobs = [j for j in jobs if not j.endswith(".done.json")]
            if not jobs:
                time.sleep(0.05); continue
            for j in jobs:
                done = j[:-5] + ".done.json"
                try:
                    with open(j) as f: job = json.load(f)
                    os.remove(j)
                    t0 = time.time(); res = eng.map(job["items"])
                    _write(done, {"ok": True, "items": res, "seconds": time.time() - t0})
                except Exception as e:
                    _write(done, {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-3000:]})
                last = time.time()
    finally:
        eng.close()
        _write(os.path.join(d, "exited.json"), {"why": why})
    return 0


def main(argv):
    if len(argv) >= 2 and argv[0] == "--status":
        _write(argv[1], status()); return 0
    a = {}; i = 0
    while i < len(argv):
        k = argv[i]
        if k.startswith("--") and i + 1 < len(argv):
            a[k[2:]] = argv[i + 1]; i += 2
        else:
            i += 1
    if "serve" not in a:
        print(__doc__); return 2
    return serve(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
