import sys, io, contextlib
sys.path.insert(0, '/home/claude/out/v111/tests111/mockee')
import ee
from run_mock import load, run_window
m = load('/home/claude/v109/artal_exporter_v109.py', '/home/claude/roi9_x')
# _polygon_parts on a GeometryCollection with a stray point (3 polygon parts, 1 dropped)
gc = {'type': 'GeometryCollection', 'geometries': [
    {'type': 'Polygon', 'coordinates': [[[0,0],[1,0],[1,1],[0,0]]], 'geodesic': True},
    {'type': 'MultiPolygon', 'coordinates': [[[[2,2],[3,2],[3,3],[2,2]]], [[[4,4],[5,4],[5,5],[4,4]]]]},
    {'type': 'Point', 'coordinates': [9, 9]}]}
print("_polygon_parts:", m._polygon_parts(gc)[0].__len__(), "parts,", m._polygon_parts(gc)[1], "dropped")
# all-branches-errored path: poison the ROI after setup and build a window through main()
ee.ROI_KIND = 'collection'
with contextlib.redirect_stdout(io.StringIO()):
    m.setup(authenticate=False)
m.roiGeom = ee.Geometry({'type': 'GeometryCollection', 'geometries': []}, None, False)   # pre-v109 style pin
r = run_window(m, 2025, 'Rabi')
print("poisoned ROI -> build_stack:", r['err'][:160])
m.MIN_SUBMIT_INTERVAL_S = 0; m.TASK_POLL_INTERVAL = 0
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    try:
        m.main(authenticate=False, years=[2025], seasons=['Rabi'])
    except Exception as ex:
        print("main raised:", ex)
print("main():", " | ".join(l.strip()[:120] for l in buf.getvalue().splitlines() if 'ERROR' in l or 'queued' in l or 'raised' in l))
