import sys, os, io, json, contextlib, shutil
sys.path.insert(0, '/home/claude/out/v111/tests111/mockee')
import ee
os.makedirs('/home/claude/sec_run', exist_ok=True); os.chdir('/home/claude/sec_run')
shutil.copy('/home/claude/v108/artal_exporter_v108.py', 'artal_exporter_v108.py')
nb = json.load(open('/home/claude/v108/RWD_DP&D_FinalV108.ipynb'))
cells = [(i, ''.join(c['source'])) for i, c in enumerate(nb['cells']) if c['cell_type']=='code']
def run(src, ns):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(src, 'cell', 'exec'), ns)
    return buf.getvalue()
# --- A: fresh session, every definition section EXCEPT Section 10 (Setup) ran, then run_download()
ns = {'__name__': 'nb'}
setup_cell = next(i for i, s in cells if s.startswith('# ---------------- SETUP'))
for i, s in cells:
    if s.startswith('!pip') or i >= 33: continue
    if s.startswith('import ee'): s = 'import ee'
    if i == setup_cell or "_PIPE = 'artal_exporter_v108.py'" in s: continue
    run(s, ns)
out = run("run_download(authenticate=False)", ns)
print("A) fresh session missing Section 10 ->")
print("   " + "\n   ".join(l for l in out.splitlines() if l.strip())[:900])
# --- B: Section 0b loader alone, then run main
ns2 = {'__name__': 'nb'}
run('import ee', ns2)
loader = next(s for i, s in cells if "_PIPE = 'artal_exporter_v108.py'" in s)
print("\nB) Section 0b:", run(loader, ns2).strip())
ns2['MIN_SUBMIT_INTERVAL_S'] = 0; ns2['TASK_POLL_INTERVAL'] = 0
out = run("main(authenticate=False, years=[2025], seasons=['Rabi'])", ns2)
print("   " + "\n   ".join(l for l in out.splitlines() if 'queued' in l or 'ERROR' in l))
