import sys, io, contextlib
sys.path.insert(0, '/home/claude/out/v111/tests111/mockee')
import ee
ee.ROI_KIND = 'collection'
from run_mock import load
m = load('/home/claude/out/v111/artal_exporter_v111.py', '/home/claude/out/v111/w111')
m.MIN_SUBMIT_INTERVAL_S = 0; m.TASK_POLL_INTERVAL = 0
with contextlib.redirect_stdout(io.StringIO()):
    m.setup(authenticate=False)
print("=== reference_crosscheck(2016,'Kharif') ===")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    st = m.reference_crosscheck(2016, 'Kharif')
print("\n".join(l for l in buf.getvalue().splitlines() if 'pipeline' in l or l.strip().startswith(('Rain','ESI','NDVI','Tmax','Tmin','Tmean','[')) and 'source' not in l)[:3000])
print("=== main(years=[2025], seasons=['Rabi']) with timestamps/bars ===")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    m.main(authenticate=False, years=[2025], seasons=['Rabi'])
lines = buf.getvalue().splitlines()
print("\n".join(l for l in lines if any(k in l for k in ('run started', 'queued', 'run finished', '▶ ', 'sweep'))))
print("timestamped lines:", sum(1 for l in lines if l.startswith('[20')), "of", len([l for l in lines if l.strip()]))
import csv
rows = list(csv.DictReader(open(m.MANIFEST_FILE)))
print("manifest built_at:", rows[0]['built_at'], "| cols:", len(rows[0]))
