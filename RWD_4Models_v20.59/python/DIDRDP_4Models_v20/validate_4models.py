"""
validate_4models.py -- THE GATE of the four-model bundle (RWD_4Models: P00 + M01, M02, M16, M34, Python and R). Every validator of the full
pipeline, run on THIS bundle (each one covers exactly this project's notebooks and models: _paths.PIPELINE_MODELS), one after another, then one
table: gate, verdict, the validator's own last line, minutes. Exit code 0 only when EVERY gate is clean -- a gate that cannot run (no R) FAILS
unless you allow it with --no-r (then it says so in the table; nothing is skipped silently).

    python validate_4models.py                 (everything: ~1-2 h on 2 cores, less on your machine)
    python validate_4models.py --only poison,parity_primary      (a subset, by the names in the table)
    python validate_4models.py --no-r          (a machine without R: the R gates are listed as NOT RUN)

The gates (what each proves):
  selfcheck           the bundle, its configuration and scope, your rules on small known answers, the engine checks (selfcheck_4models.py)
  known_answers       every model on two synthetic panels with a KNOWN effect (+0.05): one sub-watershed and eight pooled (2 cohorts)
  poison              your Koranahalli layout written CLEAN and POISONED (every row the design must leave out +5 on the outcomes, +100 mm /
                      +5 C on the covariates -- repeated tiles, other sub-watersheds, outside pixels, rings 4-5, pre-window years, the annual
                      composite, flipping pixels, cloud gaps in the newer exports): every number identical in the two runs; effects at the truth
  parity_primary      R vs Python on the same exports, the routes that run by default (M01 / M02 pyfixest, M16 the engine, M34 R HonestDiD)
  parity_engine       R vs Python, Python's own implementations (no package, no R route)
  r_parity            the R preparation structures the data exactly as the Python P00 (row for row), the design, the samples, M01
  design_options      every design option applied at the model stage, R == Python, on one panel never rebuilt
  all_models          every model honours two scenarios, no placeholder / all-NaN / stray file, readiness of the four, multi-site, guards
  preprocessing       the preparation path on synthetic exports (PASS A / B, dedup, zero policy, spill-to-disk, 80 % name rule ...)
  inference           a Monte Carlo on M01: unbiased, the design-based SE covers the truth at 95 %
  prep_notebooks      P00 (and MS01, and a two-sub-watershed P00) run end to end as you run them
  notebooks_cold      every notebook finds and imports the engine from its own folder
  V00                 the streaming / parallel PASS A / GPU path checks
  out_of_core         beyond 98 % of the RAM: the four models and P00 on pixel partitions on Dask, Spark and the built-in batches == in memory
  r_tests             R/tests/run_all_tests.R: the R pipeline's known answers, rules, poison test, out of core (scenario H), notebooks (Knit + Jupyter)
"""
import os, sys, re, time, glob, shutil, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
RHOME = os.path.join(os.path.dirname(os.path.dirname(HERE)), "R")
PY = sys.executable
LOGS = os.path.join(HERE, "VALIDATION_4MODELS_LOGS")

def _rscript():
    r = shutil.which("Rscript")
    if r: return r
    try:
        sys.path.insert(0, HERE); import _common as C
        return C.find_rscript()
    except Exception:
        return None

def gates(poison_dir):
    g = [("selfcheck", [PY, "selfcheck_4models.py"], HERE, False),
         ("known_answers", [PY, "validate_known_answers.py"], HERE, False),
         ("poison", [PY, "validate_location_poison.py"], HERE, False),
         ("parity_primary", [PY, "validate_model_parity.py"] + (["--from", os.path.join(poison_dir, "clean")] if poison_dir else []), HERE, True),
         ("parity_engine", [PY, "validate_model_parity.py", "--engine"], HERE, True),
         ("r_parity", [PY, "validate_r_parity.py"], HERE, True),
         ("design_options", [PY, "validate_design_options.py"], HERE, True),
         ("all_models", [PY, "validate_all_models.py"], HERE, False),
         ("preprocessing", [PY, "validate_preprocessing.py"], HERE, False),
         ("inference", [PY, "validate_inference.py"], HERE, False),
         ("prep_notebooks", [PY, "validate_prep_notebooks.py"], HERE, False),
         ("notebooks_cold", [PY, "validate_notebooks_cold.py"], HERE, False),
         ("V00", [PY, "V00_RUN_ALL_VALIDATIONS.py"], os.path.join(HERE, "06_Validation"), False),
         ("out_of_core", [PY, "validate_out_of_core.py"], HERE, False)]
    rs = _rscript()
    g.append(("r_tests", [rs or "Rscript", os.path.join("tests", "run_all_tests.R")], RHOME, True))
    return g

VERDICT_LINE = re.compile(r"^(CLEAN|RESULT|\d+ PROBLEM|\d+ DIFFERENCE|PROBLEMS|NOTHING|\d+/\d+ PASSED|\d+ IDENTICAL|.*PROBLEM\(S\)|.*FAIL)", re.I)

def main(argv):
    only = None
    if "--only" in argv: only = set(argv[argv.index("--only") + 1].split(","))
    no_r = "--no-r" in argv
    os.makedirs(LOGS, exist_ok=True)
    env = dict(os.environ); env["PATH"] = os.path.dirname(PY) + os.pathsep + env.get("PATH", "")
    rows, poison_dir = [], None
    for name, cmd, cwd, needs_r in gates(None):
        if only and name not in only: continue
        if name == "parity_primary":
            cmd = [c for c in gates(poison_dir) if c[0] == name][0][1]
        if needs_r and not _rscript():
            rows.append((name, "NOT RUN" if no_r else "FAILED", "R not found" + (" (--no-r)" if no_r else " -- install R, or run with --no-r on a machine without R"), 0.0))
            print(f"[{'INFO' if no_r else 'FAILED'}]  {name}: R not found", flush=True); continue
        t0 = time.time(); log = os.path.join(LOGS, f"{name}.log")
        print(f"[INFO]    {name}: {' '.join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd))}  (log: {log})", flush=True)
        with open(log, "w", encoding="utf-8") as fh:
            r = subprocess.run(cmd, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT, env=env)
        out = open(log, encoding="utf-8", errors="ignore").read()
        if name == "poison":
            m_ = re.search(r"working in (\S+)", out); poison_dir = m_.group(1) if m_ else None
        last = [l.strip() for l in out.splitlines() if VERDICT_LINE.match(l.strip())]
        verdict = "PASS" if r.returncode == 0 else "FAILED"
        if name == "r_tests" and "RESULT: PASS" not in out: verdict = "FAILED"
        rows.append((name, verdict, (last[-1] if last else out.strip().splitlines()[-1] if out.strip() else "no output")[:150], (time.time() - t0) / 60))
        print(f"[{'OK' if verdict == 'PASS' else 'FAILED'}]{'      ' if verdict == 'PASS' else '  '}{name} ({rows[-1][3]:.1f} min): {rows[-1][2]}", flush=True)
    print("=" * 120)
    print(f"{'gate':16s} {'verdict':8s} {'min':>6s}  the validator's last line")
    for n, v, l, m in rows: print(f"{n:16s} {v:8s} {m:6.1f}  {l}")
    bad = [n for n, v, _, _ in rows if v == "FAILED"]
    nr = [n for n, v, _, _ in rows if v == "NOT RUN"]
    print("=" * 120)
    print((f"CLEAN: every gate of the four-model bundle passed ({len(rows) - len(nr)} gates)" + (f"; NOT RUN (no R, --no-r): {', '.join(nr)}" if nr else ""))
          if not bad else f"{len(bad)} GATE(S) FAILED: {', '.join(bad)} -- the logs are in {LOGS}")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
