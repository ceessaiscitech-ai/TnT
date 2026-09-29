import sys, os, io, contextlib, json
from datetime import date
sys.path.insert(0, '/home/claude/out/v111/tests111/mockee')
import ee
from run_mock import load

path, workdir, when = sys.argv[1], sys.argv[2], sys.argv[3]
years = [int(y) for y in sys.argv[4].split(',')] if len(sys.argv) > 4 else [2026]
seasons = sys.argv[5].split(',') if len(sys.argv) > 5 else ['Rabi']
frozen = date.fromisoformat(when)
ee.set_today(frozen)
m = load(path, workdir)


class FrozenDate(date):
    @classmethod
    def today(cls):
        return frozen


m.date = FrozenDate
m.MIN_SUBMIT_INTERVAL_S = 0
m.TASK_POLL_INTERVAL = 0
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    m.main(authenticate=False, years=years, seasons=seasons)
log = buf.getvalue()
queued = [l.strip() for l in log.splitlines() if 'queued' in l and '✅' in l]
refresh = [l.strip()[:150] for l in log.splitlines() if '🔁 This window' in l]
errors = [l.strip()[:150] for l in log.splitlines() if 'ERROR' in l or 'SKIP' in l]
reg = json.load(open(m.GAPFILLED_WINDOWS_FILE)) if os.path.exists(m.GAPFILLED_WINDOWS_FILE) else []
print(f"[{when}] started={len(ee.STARTED_TASKS):3d}  {queued}  refresh={refresh}  "
      f"errors={errors}  registry={reg}")
