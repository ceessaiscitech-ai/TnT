import sys, io, contextlib
sys.path.insert(0, '/home/claude/out/v111/tests111/mockee')
import ee
ee.ROI_KIND = 'collection'
from run_mock import load, run_window
m = load('/home/claude/v109/artal_exporter_v109.py', '/home/claude/w109p')
with contextlib.redirect_stdout(io.StringIO()):
    m.setup(authenticate=False)
print("export columns:", len(m.export_columns()), m.export_columns()[-3:])
bad = 0
for yr in range(m.START_YEAR, m.END_YEAR + 1):
    for se in ['Yearly'] + list(m.SEASONS.keys()):
        r = run_window(m, yr, se)
        i = r['info'] or {}
        if not r['stack'] or not r['valid'] or i.get('status') != 'ok':
            bad += 1
        core = m._core_subwindow(*m.season_window(yr, se), se)
        if yr in (2015, 2016, 2017, 2025, 2026):
            print(f"{yr} {se:7s} status={i.get('status')} cov={i.get('coverage')} optical={i.get('optical','')[:52]:52s} core={core} tiers={i.get('optical_tiers','')[:60]}")
        if r['bands'] is not None and len(r['bands']) != len(m.export_columns()):
            print("  BAND COUNT MISMATCH", yr, se, len(r['bands'])); bad += 1
print("windows with problems:", bad)
print("--- switches ---")
m.OPTICAL_PRIORITY = 'resolution_first'; m.USE_CORE_MONTHS_FIRST = False; m.ADD_OPTICAL_TIER_COL = False
print("export columns:", len(m.export_columns()))
for yr, se in [(2016,'Kharif'), (2025,'Rabi')]:
    r = run_window(m, yr, se); i = r['info'] or {}
    print(f"{yr} {se:7s} status={i.get('status')} optical={i.get('optical','')[:60]} bands={len(r['bands']) if r['bands'] else None}")
