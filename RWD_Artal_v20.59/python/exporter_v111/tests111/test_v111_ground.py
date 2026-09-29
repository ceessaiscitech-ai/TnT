import sys, io, contextlib, os
sys.path.insert(0, '/home/claude/out/v111/tests111/mockee')
import ee
ee.ROI_KIND = 'collection'
from run_mock import load
m = load('/home/claude/out/v111/artal_exporter_v111.py', '/home/claude/out/v111/w111')
m.MIN_SUBMIT_INTERVAL_S = 0; m.TASK_POLL_INTERVAL = 0
with contextlib.redirect_stdout(io.StringIO()):
    m.setup(authenticate=False)
# mock gaps: Geometry.Polygon does not exist, sampleRegions drops input properties -> patch minimally for the test
ee.Geometry.Polygon = staticmethod(lambda *a, **k: ee.Geometry.Point())
_orig = ee.Image.sampleRegions
def _sr(self, collection=None, properties=None, scale=None, **k):
    out = _orig(self, collection=collection, scale=scale, **k)
    for f, src in zip(out._features, collection._features):
        f._props.update(src._props)
    return out
ee.Image.sampleRegions = _sr
m.GROUND_INPUTS_DIR = '/home/claude/out/REWARD_ground_inputs'
import shutil; shutil.copy('/home/claude/out/gee/gee_compositing_windows_by_district.csv', m.GROUND_INPUTS_DIR)
print("=== ground_season_key sanity ===")
from datetime import date
for d in (date(2023,6,15), date(2023,9,30), date(2023,10,1), date(2024,1,15), date(2024,2,28), date(2024,3,1), date(2024,5,31)):
    print(d, m.ground_season_key(d), "| window:", m.season_window(*m.ground_season_key(d)))
print("=== recommend_core_months('Raichur') ===")
print("suggestion:", m.recommend_core_months(district='Raichur'))
print("=== _core_subwindow with override ===")
print("default Kharif 2023:", m._core_subwindow(date(2023,6,1), date(2023,10,1), 'Kharif'))
m.CORE_MONTHS_OVERRIDE = {'Kharif': (7, 9)}
print("override Kharif 2023:", m._core_subwindow(date(2023,6,1), date(2023,10,1), 'Kharif'))
m.CORE_MONTHS_OVERRIDE = None
print("=== ground_crosscheck(2023,'Kharif') ===")
st = m.ground_crosscheck(2023, 'Kharif')
print("stats keys:", list(st.keys())[:4] if st else st)
print("=== ground_crosscheck(2025,'Rabi') (polygons) ===")
st = m.ground_crosscheck(2025, 'Rabi')
print("tasks started:", len(ee.STARTED_TASKS))
