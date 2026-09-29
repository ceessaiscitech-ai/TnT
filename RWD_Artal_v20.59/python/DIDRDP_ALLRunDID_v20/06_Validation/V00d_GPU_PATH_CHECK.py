"""V00d_GPU_PATH_CHECK.py -- v20.49: the engine's GPU code, tested on ANY machine.

The GPU paths (fixed-effects demeaning for every TWFE model, the matrix demeaning, the k-NN pixel matching) are
written for CUDA. On a machine without an NVIDIA GPU they never run, so no gate had exercised them. This check runs
the SAME code on the CPU through a stand-in CUDA device (torch tensors on the CPU, `device="cuda"` mapped to the CPU)
and compares every result with the CPU path on the full data -- the arithmetic of the GPU code is proven; only the
CUDA driver itself is not (on your GPU machine `C.gpu_selftest()` compares the real device the same way).

    python 06_Validation/V00d_GPU_PATH_CHECK.py          (needs torch; the CPU build is enough)
Exit code 0 = every comparison agrees.
"""
import os, sys, types
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
try:
    import torch
except Exception:
    print("[INFO]    torch is not installed -- nothing to check here (pip install torch; the CPU build is enough)"); sys.exit(0)


class _FakeCuda:
    """torch.cuda as the engine uses it, backed by the CPU."""
    def is_available(self): return True
    def synchronize(self): pass
    def empty_cache(self): pass
    def mem_get_info(self): return (8 * 2**30, 16 * 2**30)
    def memory_reserved(self): return 0
    def get_device_properties(self, i): return types.SimpleNamespace(name="stand-in CUDA device (CPU)", total_memory=16 * 2**30)


class _FakeTorch:
    """The torch module with every device="cuda" sent to the CPU."""
    def __init__(self, t): self._t = t; self.cuda = _FakeCuda()
    def device(self, *a, **k): return self._t.device("cpu")
    def __getattr__(self, name):
        obj = getattr(self._t, name)
        if callable(obj) and not isinstance(obj, type):
            def wrap(*a, **k):
                if "device" in k: k["device"] = "cpu"
                return obj(*a, **k)
            return wrap
        return obj


import _common as C
REAL_GPU = bool(torch.cuda.is_available())      # v20.50: on your A40 the checks run on the REAL device
FT = torch if REAL_GPU else _FakeTorch(torch)
print(f"[INFO]    device: {torch.cuda.get_device_name(0) if REAL_GPU else 'stand-in CUDA device (CPU tensors)'}")
R = {}
def chk(name, f):
    try:
        msg = f(); R[name] = ("PASS", msg or "")
    except Exception as e:
        R[name] = ("FAIL", f"{type(e).__name__}: {str(e)[:200]}")

rng = np.random.default_rng(11)
n = 60_000
y = rng.normal(0, 1, n); f1 = rng.integers(0, 3_000, n); f2 = rng.integers(0, 40, n); f3 = rng.integers(0, 4, n)

def t1():
    a = C._demean_cpu(y, (f1, f2, f3), 1e-12, 500); b = C._demean_gpu(FT, y, (f1, f2, f3), 1e-12, 500)
    d = float(np.max(np.abs(a - b))); assert d < 1e-8, f"GPU vector demeaning differs from CPU by {d:.2e}"
    return f"vector demeaning (3 fixed effects, {n:,} rows): max |GPU - CPU| = {d:.1e}"
chk("G1 _demean_gpu == _demean_cpu", t1)

def t2():
    Y = np.column_stack([y, rng.normal(0, 1, n), rng.normal(0, 1, n)])
    a = np.column_stack([C._demean_cpu(Y[:, j], (f1, f2), 1e-12, 500) for j in range(3)])
    b = C._demean_gpu_matrix(FT, Y, (f1, f2), 1e-12, 500)
    d = float(np.max(np.abs(a - b))); assert d < 1e-8, f"GPU matrix demeaning differs from CPU by {d:.2e}"
    return f"matrix demeaning (3 columns in one kernel): max |GPU - CPU| = {d:.1e}"
chk("G2 _demean_gpu_matrix == column-wise CPU", t2)

def t3():
    saved = (C._torch, C.USE_GPU, C.GPU_MIN_ROWS)
    try:
        C._torch = FT; C.USE_GPU = True; C.GPU_MIN_ROWS = 0
        out = C.demean_multi_way(y, f1, f2)                  # the production entry point, with its full-data cross-check
        ref = C._demean_cpu(y, (f1, f2), 1e-10, 200)
        d = float(np.max(np.abs(out - ref))); assert d < 1e-7, f"routed GPU result differs by {d:.2e}"
        assert C.USE_GPU, "the GPU path was switched off by its own verification"
        return f"demean_multi_way on the GPU path (verified on ALL rows by _gpu_verify): max diff {d:.1e}"
    finally:
        C._torch, C.USE_GPU, C.GPU_MIN_ROWS = saved
chk("G3 production demeaning takes the GPU path and passes its full-data verification", t3)

def t4():
    rows = []
    for i in range(1_500):
        core = i < 300; a_ = rng.normal(0, 0.03)
        for yr in range(2016, 2026):
            rows.append((f"P{i}", yr, f"{yr}_0", int(core), int(yr >= 2022), int(core and yr >= 2022),
                         0.3 + a_ + 0.01 * (yr - 2016) + (0.05 if core and yr >= 2022 else 0) + rng.normal(0, 0.01), 7))
    df = pd.DataFrame(rows, columns=["pixel_id", "Year", "time_fe_yearseason", "treat_core", "post", "did", "NDVI", "site_id"])
    saved = (C._torch, C.USE_GPU, C.GPU_MIN_ROWS, C.PREBUILT_MODE)
    try:
        C.PREBUILT_MODE = "off"                              # the engine's own TWFE (the package route has no GPU code)
        C._torch = None; C.USE_GPU = False
        b_cpu, s_cpu = C.estimate_twfe_did(df, "NDVI", "did", "pixel_id", "time_fe_yearseason", "Year")
        C._torch = FT; C.USE_GPU = True; C.GPU_MIN_ROWS = 0
        b_gpu, s_gpu = C.estimate_twfe_did(df, "NDVI", "did", "pixel_id", "time_fe_yearseason", "Year")
    finally:
        C._torch, C.USE_GPU, C.GPU_MIN_ROWS, C.PREBUILT_MODE = saved
    assert abs(b_cpu - b_gpu) < 1e-9 and abs(s_cpu - s_gpu) < 1e-9, f"TWFE differs: CPU {b_cpu}/{s_cpu} vs GPU {b_gpu}/{s_gpu}"
    assert abs(b_gpu - 0.05) < 0.005, f"TWFE on the GPU path misses the known effect: {b_gpu}"
    return f"TWFE DiD: GPU path {b_gpu:.6f} (SE {s_gpu:.2e}) == CPU path {b_cpu:.6f}; truth 0.05"
chk("G4 a whole TWFE model gives the same estimate and SE on the GPU path", t4)

def t5():
    from scipy.spatial import cKDTree
    reg = rng.uniform(0, 5_000, (20_000, 2)); q = reg[rng.integers(0, len(reg), 3_000)] + rng.normal(0, 1.0, (3_000, 2))
    saved = C.torch if hasattr(C, "torch") else None
    had = hasattr(C, "torch"); C.torch = FT
    try:
        d_g, i_g = C._nn_match_torch_chunked(q, reg, query_chunk=700, registry_chunk=5_000)
    finally:
        if had: C.torch = saved
        else: del C.torch
    d_c, i_c = cKDTree(reg).query(q, k=1)
    agree = float(np.mean(np.asarray(i_g) == i_c)); dd = float(np.max(np.abs(np.asarray(d_g) - d_c)))
    assert agree == 1.0 and dd < 1e-2, f"k-NN: {agree:.4%} same neighbour, max distance error {dd:.2e} m"
    return f"k-NN pixel matching (chunked): 100 % same neighbour as scipy's k-d tree, max distance error {dd:.1e} m"
chk("G5 GPU k-NN pixel matching == scipy cKDTree", t5)

bad = 0
for k, (st, msg) in R.items():
    print(f"  {st}  {k}" + (f"\n        {msg}" if msg else "")); bad += st != "PASS"
print(f"{len(R) - bad}/{len(R)} GPU-path checks passed (torch {torch.__version__}, " + (f"on {torch.cuda.get_device_name(0)})" if REAL_GPU else "run on the CPU through a stand-in CUDA device)"))
sys.exit(1 if bad else 0)
