import sys, io, contextlib
sys.path.insert(0, '/home/claude/out/v111/tests111/mockee')
import ee
from run_mock import load, run_window
m = load('/home/claude/v107/artal_exporter_v107.py', '/home/claude/sw_w')
with contextlib.redirect_stdout(io.StringIO()):
    m.setup(authenticate=False)
print("--- GAPFILL_INCOMPLETE_WINDOWS = False ---")
m.GAPFILL_INCOMPLETE_WINDOWS = False
m._ANNUAL_RAIN_CACHE.clear()
print("export columns:", len(m.export_columns()))
for yr, se in [(2025,'Rabi'), (2026,'Rabi'), (2026,'Kharif')]:
    r = run_window(m, yr, se)
    i = r['info'] or {}
    print(f"  {yr} {se:7s} stack={r['stack']} status={i.get('status')} cov={i.get('coverage')} gap={i.get('gap_filled','')!r} note={i.get('note','')[:70]}")
    if not r['stack']: print("    ", r['err'])
print("--- ALLOW_PREVIOUS_YEAR_OUTCOME = True (gap-fill back on) ---")
m.GAPFILL_INCOMPLETE_WINDOWS = True
m.ALLOW_PREVIOUS_YEAR_OUTCOME = True
for yr, se in [(2026,'Rabi'), (2026,'Kharif')]:
    r = run_window(m, yr, se)
    i = r['info'] or {}
    print(f"  {yr} {se:7s} stack={r['stack']} status={i.get('status')} cov={i.get('coverage')} data_year={i.get('data_year')} subst={i.get('substituted')!r} gap={i.get('gap_filled','')!r} note={i.get('note','')[:90]}")
