"""
validate_notebooks_cold.py -- run every notebook the way the user does (v20.29).

The other gates inject C / P into the notebooks and skip their path-finding cells, which is fast but blind to a
notebook that never imports the engine (P10 / P11 / P02b failed on the user's machine with "NameError: name 'C' is not
defined" although every gate passed). This gate starts a FRESH Python process per notebook, with the notebook's own
folder as the working directory and the engine NOT on sys.path, and executes its code cells in order -- the
bootstrap must find and import the engine itself -- through the first cell that uses C. or P. (the setup cell).
A NameError / ImportError / ModuleNotFoundError / AttributeError is a failure; a missing panel or data gap is not
(this gate checks that notebooks START, the other gates check what they compute).

    python validate_notebooks_cold.py            # all notebooks, parallel
"""
import os, sys, json, glob, re, subprocess, concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = r'''
import sys, os, json, re, traceback
nb = sys.argv[1]
cells = ["".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code"]
ns = {"__name__": "__main__"}
use = re.compile(r"(?<![\w\.])(C|P)\.[A-Za-z_]")
stop = next((i for i, s in enumerate(cells) if use.search(s)), len(cells) - 1)
for i, src in enumerate(cells[:stop + 1]):
    src = "\n".join(l for l in src.split("\n") if not l.lstrip().startswith(("%", "!")))
    try:
        exec(compile(src, f"{os.path.basename(nb)} cell {i}", "exec"), ns)
    except SystemExit:
        pass
    except Exception as e:
        name = type(e).__name__
        data_state = name in ("InsufficientDataError", "FileNotFoundError") or "no panel" in str(e).lower()
        print(json.dumps({"cell": i, "error": name, "msg": str(e)[:240], "data_state": data_state}))
        sys.exit(0 if data_state else 3)
missing = [k for k in ("C", "P") if use.search(cells[stop]) and re.search(rf"(?<![\w\.]){k}\.[A-Za-z_]", cells[stop]) and k not in ns]
print(json.dumps({"cell": stop, "ok": not missing, "missing": missing, "engine": getattr(ns.get("C"), "ENGINE_VERSION", None)}))
sys.exit(0 if not missing else 4)
'''


def is_python(nb):
    try:
        md = json.load(open(nb, encoding="utf-8")).get("metadata", {})
        lang = (md.get("kernelspec", {}) or {}).get("language") or (md.get("language_info", {}) or {}).get("name") or "python"
        return str(lang).lower().startswith("python")
    except Exception:
        return False


def run_one(nb, timeout=240):
    env = {k: v for k, v in os.environ.items()}
    # the engine must NOT be importable from outside -- the notebook's own bootstrap has to find it
    env["PYTHONPATH"] = os.pathsep.join(p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p and os.path.abspath(p) != HERE)
    import tempfile as _tf   # v20.30: never let a notebook write into the bundle (the Windows default path is RELATIVE on Linux)
    env["REWARD_INPUT_DIR"] = env.get("REWARD_INPUT_DIR") or _tf.mkdtemp(prefix="reward_cold_")
    r = subprocess.run([sys.executable, "-c", RUNNER, nb], cwd=os.path.dirname(nb), capture_output=True, text=True,
                       timeout=timeout, env=env)
    last = [l for l in r.stdout.splitlines() if l.startswith("{")]
    info = json.loads(last[-1]) if last else {"error": "no result", "msg": (r.stderr or r.stdout)[-240:]}
    return os.path.relpath(nb, HERE), r.returncode, info


def main():
    nbs = [nb for nb in sorted(glob.glob(os.path.join(HERE, "0*", "*.ipynb"))) if is_python(nb)]
    bad, data = [], []
    with cf.ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as ex:
        for rel, code, info in ex.map(run_one, nbs):
            if code != 0: bad.append((rel, info))
            elif info.get("data_state"): data.append(rel)
    print("=" * 74)
    print(f"cold start: {len(nbs)} Python notebooks started from their own folders with nothing injected")
    if data: print(f"  {len(data)} stopped at a data gap (no panel here) AFTER importing the engine -- fine")
    for rel, info in bad:
        print(f"[FAILED]  {rel}: cell {info.get('cell')} {info.get('error', '')} {info.get('msg', '')} {info.get('missing', '')}")
    if bad:
        print(f"{len(bad)} PROBLEM(S)"); sys.exit(1)
    junk = [p for p in glob.glob(os.path.join(HERE, "**", "*"), recursive=True) if ":" in os.path.basename(p) or "\\" in os.path.basename(p)]
    if junk:
        print(f"[FAILED]  a notebook wrote into the bundle: {junk[:3]}"); sys.exit(1)
    print("CLEAN: every notebook finds and imports the engine on its own.")


if __name__ == "__main__":
    main()
