import sys, io, contextlib, traceback
sys.path.insert(0, '/home/claude/out/v111/tests111/mockee')
import ee
from run_mock import load, run_window
path, workdir, kind = sys.argv[1], sys.argv[2], sys.argv[3]
ee.ROI_KIND = kind
m = load(path, workdir)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    m.setup(authenticate=False)
print(f"[{kind}] setup:", " | ".join(l.strip() for l in buf.getvalue().splitlines() if 'ROI' in l or 'UID' in l))
try:
    with contextlib.redirect_stdout(io.StringIO()):
        grid = m.build_export_grid()
    print(f"[{kind}] build_export_grid: {len(grid)} chunks")
except Exception as ex:
    print(f"[{kind}] build_export_grid FAILED: {type(ex).__name__}: {ex}")
r = run_window(m, 2025, 'Rabi')
i = r['info'] or {}
print(f"[{kind}] 2025 Rabi: stack={r['stack']} valid={r['valid']} status={i.get('status')} optical={i.get('optical','')[:40]!r} landuse={i.get('landuse_source','')[:30]!r} err={r['err'][:90]}")
