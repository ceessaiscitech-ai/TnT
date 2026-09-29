import sys, io, contextlib
sys.path.insert(0, '/home/claude/out/v111/tests111/mockee')
import ee
from run_mock import load
m = load('/home/claude/v107/artal_exporter_v107.py', '/home/claude/diag_w')
with contextlib.redirect_stdout(io.StringIO()):
    m.setup(authenticate=False)
print("### estimate_job(years=[2025,2026]) ###")
est = m.estimate_job(years=[2025, 2026])
print("returned:", est)
print("\n### chunk_status ###")
m.chunk_status()
print("\n### diagnose_window(2025,'Rabi') ###")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    m.diagnose_window(2025, 'Rabi')
print("\n".join(l for l in buf.getvalue().splitlines() if not l.startswith('   ✅') and 'LAI source' not in l and 'LandUse source' not in l))
print("\n### diagnose_window(2026,'Rabi') ###")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    m.diagnose_window(2026, 'Rabi')
print("\n".join(l for l in buf.getvalue().splitlines() if not l.startswith('   ✅') and 'LAI source' not in l and 'LandUse source' not in l and 'Sentinel' not in l))
print("\n### task_failure_report ###")
ee.OPERATIONS[:] = [
 {'name': 'a', 'metadata': {'description': 'CSV_Sirur_v107_2025_Rabi_tile3_sub1', 'state': 'FAILED'}, 'error': {'message': 'User memory limit exceeded.'}},
 {'name': 'b', 'metadata': {'description': 'CSV_Sirur_v107_2025_Rabi_tile3_sub2', 'state': 'SUCCEEDED'}},
 {'name': 'c', 'metadata': {'description': 'CSV_Sirur_2026_Rabi_tile0_sub0', 'state': 'SUCCEEDED'}},
]
m.task_failure_report()
