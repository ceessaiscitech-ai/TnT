"""
_hardware.py -- one place that decides how much of the machine to use (v20.7).

Written for a box like yours (Dell PowerEdge R7525: 2 AMD EPYC sockets, 64 logical cores, 512 GB RAM,
Windows Server 2022), but everything is measured at run time, so it is correct on any machine.

Two rules it enforces:

1. USE THE WHOLE MACHINE for the embarrassingly-parallel stages (PASS A: one file per worker;
   PASS B: one Year x Season block per worker), bounded only by cores, by the work available, and by free RAM.
2. DO NOT OVERSUBSCRIBE. numpy/BLAS spawns one thread per core by default; N worker processes each doing that
   gives N x cores threads fighting for 64 cores, which is SLOWER than single-threaded workers. So worker
   processes get BLAS_THREADS = 1, while the parent process (where the single-run estimators live) gets all of them.

Windows note: concurrent.futures.ProcessPoolExecutor cannot exceed 61 workers on Windows
(WaitForMultipleObjects); asking for more raises ValueError. worker_cap() applies that limit.
"""
import os, sys, math

WINDOWS_POOL_LIMIT = 60          # 61 is the hard limit; leave one slot of headroom
RESERVE_CORES = 0                # v20.57 (your 98 % rule): no core is held back -- every logical core works

def _psutil():
    try:
        import psutil; return psutil
    except Exception:
        return None

def machine_profile():
    ps = _psutil()
    logical = os.cpu_count() or 1
    physical = None
    try:
        physical = ps.cpu_count(logical=False) if ps else None
    except Exception:
        pass
    total = free = None
    if ps:
        try:
            vm = ps.virtual_memory(); total, free = vm.total, vm.available
        except Exception:
            pass
    return {"logical_cores": logical, "physical_cores": physical or logical,
            "smt": bool(physical and logical > physical),
            "ram_total": total, "ram_free": free, "windows": os.name == "nt",
            "pool_limit": WINDOWS_POOL_LIMIT if os.name == "nt" else max(1, logical)}

def _memory_share():                        # v20.45: _paths.MEMORY_SHARE (0.45 each when two pipelines run at once)
    try:
        if os.environ.get("REWARD_MEMORY_SHARE"): return min(1.0, max(0.05, float(os.environ["REWARD_MEMORY_SHARE"])))
        import _paths as _Pm
        return min(1.0, max(0.05, float(getattr(_Pm, "MEMORY_SHARE", 1.0))))
    except Exception:
        return 1.0
MEMORY_SHARE = _memory_share()                # the CONFIGURED cap (1.0 = the whole machine)

# ---- v20.47: several pipelines on one machine SPLIT it automatically -- 50 % each for two data folders -------------
# Every engine registers (process id + data folder) in a machine-wide folder; its RAM, GPU and CPU budgets are divided by
# the number of DISTINCT data folders being processed right now (two notebooks of the same pipeline do not split). When
# one pipeline ends, the other gets the whole machine back. Liveness: psutil; never os.kill on Windows (it terminates).
import json as _json, time as _time, tempfile as _tempfile, atexit as _atexit
INSTANCE_DIR = os.path.join(_tempfile.gettempdir(), "reward_instances")
INSTANCE_STALE_S = 3600
_SHARE_CACHE = {"t": 0.0, "v": None, "n": 1}

def _this_root():
    try:
        import _paths as _Pr
        r = str(os.environ.get("REWARD_INPUT_DIR") or getattr(_Pr, "INPUT_DIR", ""))
        if hasattr(_Pr, "_resolve_input"): r = _Pr._resolve_input(r)            # v20.50: the folder actually used
        return os.path.normcase(os.path.abspath(_Pr._portable(r) if hasattr(_Pr, "_portable") else r))
    except Exception:
        return ""

def _create_time(pid=None):
    ps = _psutil()
    try: return float(ps.Process(pid or os.getpid()).create_time()) if ps is not None else None
    except Exception: return None

def _alive(pid, created=None):
    """v20.49: a process id that exists but belongs to ANOTHER process (Windows re-uses ids) is not alive -- its start
    time differs from the one registered. A stale file from a finished pipeline used to halve the machine."""
    ps = _psutil()
    if ps is not None:
        try:
            if not ps.pid_exists(pid): return False
            if created is not None:
                ct = _create_time(pid)
                if ct is not None and abs(ct - float(created)) > 2.0: return False
            return True
        except Exception: return True
    if os.name == "nt": return None                    # unknown: the heartbeat decides
    try:
        os.kill(pid, 0); return True
    except OSError:
        return False

def register_instance():
    try:
        os.makedirs(INSTANCE_DIR, exist_ok=True)
        with open(os.path.join(INSTANCE_DIR, f"{os.getpid()}.json"), "w") as f:
            _json.dump({"pid": os.getpid(), "root": _this_root(), "heartbeat": _time.time(), "created": _create_time(), "lang": "Python"}, f)
    except Exception:
        pass

def _unregister_instance():
    try: os.remove(os.path.join(INSTANCE_DIR, f"{os.getpid()}.json"))
    except Exception: pass

def live_roots():
    roots = {_this_root()}
    try:
        for fn in os.listdir(INSTANCE_DIR):
            p = os.path.join(INSTANCE_DIR, fn)
            try:
                with open(p) as f: d = _json.load(f)
            except Exception:
                continue
            a = _alive(int(d.get("pid", -1)), d.get("created"))
            if a is False or (a is None and _time.time() - float(d.get("heartbeat", 0)) > INSTANCE_STALE_S):
                try: os.remove(p)
                except Exception: pass
                continue
            roots.add(d.get("root", ""))
    except Exception:
        pass
    return roots

AUTO_SPLIT = False   # v20.52 (your instruction): NO cap -- every pipeline uses the whole machine (all cores, all RAM, the whole
                     # GPU) even when several run at once. True restores the v20.47 automatic split (1 / folders running).
def memory_share():
    """1.0 (the whole machine). With AUTO_SPLIT: min(the configured share, 1 / data folders being processed now).
    v20.54: without AUTO_SPLIT the share is _paths.MEMORY_SHARE -- 1.0 by default (no cap). v20.52 returned 1.0 here
    whatever MEMORY_SHARE said, so the optional manual setting documented in _paths.py had silently stopped working."""
    if not AUTO_SPLIT:
        return MEMORY_SHARE
    now = _time.time()
    if _SHARE_CACHE["v"] is not None and now - _SHARE_CACHE["t"] < 30: return _SHARE_CACHE["v"]
    register_instance()                                # also the heartbeat
    n = max(1, len(live_roots())); v = min(MEMORY_SHARE, 1.0 / n)
    if n != _SHARE_CACHE["n"]:
        print(f"[INFO]    {n} REWARD pipeline(s) on different data folders are running: this one uses {v:.0%} of RAM, GPU memory and CPU"
              if n > 1 else f"[INFO]    this is the only REWARD pipeline running: it uses {v:.0%} of the machine")
    _SHARE_CACHE.update(t=now, v=v, n=n)
    return v

def cpu_budget():
    """Cores this pipeline may use: all of them alone, half of them when two data folders are processed at once."""
    return max(1, int((os.cpu_count() or 2) * memory_share()))

register_instance(); _atexit.register(_unregister_instance)
MEMORY_CEILING = 0.98   # v20.57 -- YOUR RULE: no limit on loading data until the RAM / GPU memory reaches 98 % of its TOTAL
                        # (v20.30-v20.56: 95 %); only there does a stage stop with a message (regressions: never chunked)

def own_ram_bytes():
    """RAM held by this pipeline: this process and its worker processes."""
    ps = _psutil()
    if ps is None: return 0.0
    try:
        me = ps.Process(); tot = float(me.memory_info().rss)
        for c in me.children(recursive=True):
            try: tot += float(c.memory_info().rss)
            except Exception: pass
        return tot
    except Exception:
        return 0.0

def ram_budget_bytes():
    """Bytes this pipeline can still take. Alone: up to MEMORY_CEILING (98 %) of the RAM. With other pipelines on other
    data folders: its SHARE of the machine -- share x 98 % of the total, minus what it already holds -- and never more
    than is actually free. (v20.47 gave it a share of what was FREE, so the second pipeline got half of what the first
    had left: 50 / 50 only on paper.) None if unknown."""
    p = machine_profile()
    if not p.get("ram_total") or p.get("ram_free") is None: return None
    free_ok = float(p["ram_free"]) - (1.0 - MEMORY_CEILING) * float(p["ram_total"])
    sh = memory_share()
    b = max(0.0, free_ok) if sh >= 1.0 else max(0.0, min(free_ok, sh * MEMORY_CEILING * float(p["ram_total"]) - own_ram_bytes()))
    ovr = os.environ.get("REWARD_RAM_BUDGET_BYTES")          # v20.58: the checks only -- a SMALLER budget, to prove what happens beyond 98 %
    if ovr:                                                    #   (validate_out_of_core.py); never set it for a real run
        try: b = min(b, float(ovr))
        except Exception: pass
    return b

def gpu_budget_bytes():
    """The same for the GPU (None without a CUDA device)."""
    try:
        import torch
        if not torch.cuda.is_available(): return None
        free, total = torch.cuda.mem_get_info()
        free_ok = float(free) - (1.0 - MEMORY_CEILING) * float(total); sh = memory_share()
        if sh >= 1.0: return max(0.0, free_ok)
        own = float(torch.cuda.memory_reserved())                     # v20.49: the GPU is split like the RAM
        return max(0.0, min(free_ok, sh * MEMORY_CEILING * float(total) - own))
    except Exception:
        return None

def fits(nbytes, device="ram"):
    """True when taking `nbytes` more keeps the device at or below MEMORY_CEILING of its total."""
    b = ram_budget_bytes() if device == "ram" else gpu_budget_bytes()
    return b is not None and float(nbytes) <= b

def memory_report():
    """One line: RAM and GPU in use / total and what the 98 % ceiling still allows."""
    p = machine_profile(); rb = ram_budget_bytes(); gb = gpu_budget_bytes()
    s = (f"RAM {((p['ram_total'] - p['ram_free']) / 1e9):.0f}/{p['ram_total'] / 1e9:.0f} GB in use, {rb / 1e9:.0f} GB usable below "
         f"the {MEMORY_CEILING:.0%} ceiling" if p.get("ram_total") else "RAM unknown")
    return s + (f" | GPU {gb / 1e9:.1f} GB usable below the ceiling" if gb is not None else " | no GPU")

def worker_cap(n_tasks=None, bytes_per_worker=None, reserve=RESERVE_CORES, ram_fraction=None):
    """How many worker PROCESSES to start: EVERY logical core (v20.57: no reserve), fewer only when there are fewer tasks,
    when that many workers would not fit below 98 % of the RAM (bytes_per_worker given), or above the platform's pool
    limit (61 on Windows). `reserve` and `ram_fraction` are accepted for old callers and ignored (the 98 % rule decides)."""
    p = machine_profile()
    n = max(1, int(p["logical_cores"]))                           # v20.52: EVERY logical core (no reserve, no split)
    n = min(n, p["pool_limit"])                                    # bounded only by the platform's own pool limit, the
    if n_tasks: n = min(n, int(n_tasks))                           # number of tasks -- and (v20.57) YOUR 98 % rule: fewer
    if bytes_per_worker:                                           # workers ONLY when that many would not fit below 98 % of
        _b = ram_budget_bytes()                                    # the RAM (v20.52 dropped this too: 64 workers x a block
        if _b is not None:                                         # each could exhaust memory and kill the kernel)
            n = min(n, max(1, int(_b / float(bytes_per_worker))))
    return max(1, int(n))

_BLAS_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
              "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS")

def set_blas_threads(n):
    """Set every BLAS/OpenMP thread-count variable. In a worker: 1. In the parent: all cores."""
    n = max(1, int(n))
    for v in _BLAS_VARS:
        os.environ[v] = str(n)
    try:                                     # also retune an already-loaded BLAS, when possible
        from threadpoolctl import threadpool_limits
        threadpool_limits(n)
    except Exception:
        pass
    return n

def use_full_machine(verbose=True):
    """Parent process: let numpy/BLAS use every core (the single-run estimators are one process)."""
    p = machine_profile()
    n = set_blas_threads(min(p["logical_cores"], cpu_budget()))   # v20.47: this pipeline's share of the cores
    if verbose:
        ram = f"{p['ram_total']/1e9:.0f} GB total, {p['ram_free']/1e9:.0f} GB free" if p["ram_total"] else "RAM unknown"
        print(f"[INFO]    machine: {p['logical_cores']} logical cores"
              + (f" ({p['physical_cores']} physical, SMT on)" if p["smt"] else "")
              + f" | {ram} | BLAS threads={n}"
              + (f" | Windows pool limit {p['pool_limit']}" if p["windows"] else ""))
    return p

def worker_init_threads():
    """Worker process: exactly one BLAS thread, so N workers do not start N x cores threads."""
    set_blas_threads(1)

def describe_plan(n_files=None, n_blocks=None, block_rows=None, block_bytes_per_row=220.0):
    """Human-readable plan for the preparation stage, printed before the long passes."""
    p = machine_profile()
    a = worker_cap(n_tasks=n_files)
    b = worker_cap(n_tasks=n_blocks, bytes_per_worker=(block_rows * block_bytes_per_row) if block_rows else None)
    lines = [f"cores {p['logical_cores']} (all used; v20.52), free RAM "          # v20.54: said "reserve 1", none is kept
             f"{p['ram_free']/1e9:.0f} GB" if p["ram_free"] else f"cores {p['logical_cores']}"]
    if n_files: lines.append(f"PASS A: {n_files} files on {a} worker processes (1 BLAS thread each)")
    if n_blocks: lines.append(f"PASS B: {n_blocks} blocks on {b} worker processes"
                              + (f", ~{block_rows*block_bytes_per_row/1e9:.1f} GB each" if block_rows else ""))
    return " | ".join(lines)
