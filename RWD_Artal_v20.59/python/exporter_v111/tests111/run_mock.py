import sys, os, importlib.util, io, contextlib, traceback, json
from datetime import date
sys.path.insert(0, '/home/claude/out/v111/tests111/mockee')
import ee  # mock

def load(path, workdir):
    os.makedirs(workdir, exist_ok=True)
    os.chdir(workdir)
    spec = importlib.util.spec_from_file_location("exp", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def run_window(m, yr, season, quiet=True):
    buf = io.StringIO()
    ctx = contextlib.redirect_stdout(buf) if quiet else contextlib.nullcontext()
    try:
        with ctx:
            stack, info = m.build_stack(yr, season)
        ok, err = (True, '') if stack is None else m.validate_window(stack, yr, season)
        bands = stack.bands if stack is not None else None
        return {'stack': stack is not None, 'valid': ok, 'err': err, 'info': info,
                'bands': bands, 'log': buf.getvalue()}
    except Exception as ex:
        return {'stack': False, 'valid': False, 'err': f"EXC {type(ex).__name__}: {ex}",
                'info': None, 'bands': None, 'log': buf.getvalue(),
                'tb': traceback.format_exc()}

if __name__ == '__main__':
    path = sys.argv[1]
    workdir = sys.argv[2]
    windows = sys.argv[3] if len(sys.argv) > 3 else 'rabi'
    if len(sys.argv) > 4:
        ee.set_today(date.fromisoformat(sys.argv[4]))
    m = load(path, workdir)
    if len(sys.argv) > 4:
        frozen = date.fromisoformat(sys.argv[4])

        class FrozenDate(date):
            @classmethod
            def today(cls):
                return frozen
        m.date = FrozenDate
    with contextlib.redirect_stdout(io.StringIO()):
        m.setup(authenticate=False)
    print(f"today = {ee.today()}   exporter = {os.path.basename(path)}")
    if windows == 'rabi':
        targets = [(2025, 'Rabi'), (2026, 'Rabi')]
    else:
        targets = [(y, s) for y in range(m.START_YEAR, m.END_YEAR + 1)
                   for s in ['Yearly'] + list(m.SEASONS.keys())]
    for yr, se in targets:
        r = run_window(m, yr, se)
        status = (r['info'] or {}).get('status', '?') if r['info'] else '?'
        note = (r['info'] or {}).get('note', '') if r['info'] else ''
        print(f"{yr} {se:7s} stack={str(r['stack']):5s} valid={str(r['valid']):5s} "
              f"status={status:8s} cov={(r['info'] or {}).get('coverage','?')} "
              f"gap={(r['info'] or {}).get('gap_filled','')!s:3s} {r['err'][:120]} | {note[:140]}")
        if 'tb' in r:
            print(r['tb'])
        if r['bands'] is not None and windows == 'rabi':
            print("   bands:", r['bands'])
        if windows == 'rabi':
            print("   --- log ---")
            print("   " + r['log'].replace("\n", "\n   "))
