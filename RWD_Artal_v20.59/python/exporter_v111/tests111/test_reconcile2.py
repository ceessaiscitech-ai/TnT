import sys, os, io, contextlib
sys.path.insert(0, '/home/claude/out/v111/tests111/mockee')
import ee
from run_mock import load
path, workdir, adopt = sys.argv[1], sys.argv[2], sys.argv[3] == '1'
m = load(path, workdir)
m.MIN_SUBMIT_INTERVAL_S = 0; m.TASK_POLL_INTERVAL = 0
m.ADOPT_PRIOR_VERSION_TASKS = adopt
with contextlib.redirect_stdout(io.StringIO()):
    m.setup(authenticate=False); grid = m.build_export_grid()
ee.OPERATIONS.clear()
for yr in (2025, 2026):
    for tname, box in grid:      # v106-style names: no version tag
        ee.OPERATIONS.append({'name': f"projects/x/operations/OLD{yr}{tname}",
                              'metadata': {'description': f"CSV_{m.ROI_ID}_{yr}_Rabi_{tname}", 'state': 'SUCCEEDED'}})
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    m.main(authenticate=False, years=[2025, 2026], seasons=['Rabi'])
for line in buf.getvalue().splitlines():
    if 'queued' in line or 'ℹ️' in line or 'Final task' in line:
        print("  ", line.strip()[:260])
print(f"ADOPT_PRIOR_VERSION_TASKS={adopt}: tasks started this run = {len(ee.STARTED_TASKS)}")
if ee.STARTED_TASKS:
    t = ee.STARTED_TASKS[0].config
    print("   example task ->", t['description'], "| file:", t['fileNamePrefix'], "| folder:", t['folder'])
