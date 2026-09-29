import sys, os, io, json, contextlib, traceback
sys.path.insert(0, '/home/claude/out/v111/tests111/mockee')
import ee
ee.ROI_KIND = 'collection'
os.makedirs('/home/claude/out/v111/nb_run', exist_ok=True); os.chdir('/home/claude/out/v111/nb_run')
nb = json.load(open('/home/claude/out/v111/RWD_DP&D_FinalV111.ipynb'))
ns = {'__name__': 'nbtest'}
ok = fail = 0
for i, c in enumerate(nb['cells']):
    if c['cell_type'] != 'code': continue
    src = ''.join(c['source'])
    if src.startswith('!pip'): continue
    if src.startswith('import ee'): src = 'import ee\nprint("Earth Engine ready (mock)")'
    if 'run_download(authenticate=False)' in src and not src.startswith('#'):
        src = "DOWNLOAD_YEARS=[2025, 2026]; DOWNLOAD_SEASONS=['Rabi']\n" + src
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(src, f'cell{i}', 'exec'), ns)
            if 'MIN_SUBMIT_INTERVAL_S' in ns: ns['MIN_SUBMIT_INTERVAL_S'] = 0; ns['TASK_POLL_INTERVAL'] = 0
        ok += 1
        out = buf.getvalue()
        key = [l for l in out.splitlines() if any(k in l for k in ('queued', 'PROJECT', 'SKIP', 'decision', 'ℹ️', 'Counter', 'Final task', 'TOTAL EXPORT', 'usable windows', 'Cross-validation', 'GEDI', 'Could not read', '🚫', 'ERROR'))]
        print(f"cell {i:2d} OK  :: {src.strip().splitlines()[0][:60]}")
        for l in key[:6]: print("        ", l.strip()[:150])
    except Exception as ex:
        fail += 1
        print(f"cell {i:2d} FAIL :: {src.strip().splitlines()[0][:60]} -> {type(ex).__name__}: {ex}")
        print(traceback.format_exc()[-800:])
print(f"\ncells executed OK={ok} FAIL={fail}; tasks started={len(ee.STARTED_TASKS)}")
