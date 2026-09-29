"""
_paths.py -- THE ONLY PLACE YOU SET A PATH (v20.14).

Edit INPUT_DIR. Everything else is derived from it and shared by BOTH engines (_prep_common for the P-notebooks,
_common for the models: here M01, M02, M16, M34), so the preparation and the estimation always look at the same folders:

    INPUT_DIR                     your exports (csv / parquet / xlsx / xlsm / xls, any depth of sub-folders)
    OUTPUT_DIR  = INPUT_DIR/output_4Models    everything this project writes (the full pipeline RWD_Artal: INPUT_DIR/output)
    TEMP_DIR    = OUTPUT_DIR/_tmp_shards      PASS A shards, PASS B parts (never re-ingested)
    FINAL_PANEL = OUTPUT_DIR/did_panel_full.parquet
    RESULTS_ROOT = OUTPUT_DIR/results          <model>/<scenario tag>/...
    ESTIMATOR_FILES_DIR = OUTPUT_DIR/estimator_files

Set OUTPUT_DIR / TEMP_DIR below only if you want them somewhere else. At run time, `P.set_paths(...)` or
`C.set_paths(...)` overrides for one session and keeps both engines in step. The active layout is written to
OUTPUT_DIR/reward_paths.json so a later session (or a colleague) can see exactly where everything is.
"""
import os, json

# ======================= EDIT THIS =======================
GROUND_TRUTH_OUTCOMES_PATH = None   # v20.24: None = <results>/P08/ground_truth_outcomes.csv (written by P08, read by M07)
ROLLOUT_INSTRUMENT_PATH = None      # v20.24: None = <INPUT_DIR>/rollout_instrument.csv (M08; you provide it)
GROUND_INPUTS_DIR = None     # v20.24: None = the bundle's REWARD_ground_inputs/ (shipped); or r"D:\path\to\REWARD_ground_inputs"
INPUT_DIR = os.environ.get("REWARD_INPUT_DIR") or r"D:\LKT\RWD_Artal\data"   # THIS project's data root (v20.50; the env var is for tests)
LEGACY_INPUT_DIR = r"D:\LKT\TST_Artal"   # v20.50: the data root before MIGRATE_DATA.bat -- used (and said) until the data are moved
MEMORY_SHARE = 1.0   # v20.45: share of RAM / GPU memory this copy may use -- set 0.45 in BOTH copies when two pipelines run at once
PIPELINE_MODELS = ("M01", "M02", "M16", "M34")   # v20.58: the models THIS project (RWD_4Models) carries: its P00 prepares only what
                                                 #   they need, and every check covers only them (None = all 45: the full pipeline RWD_Artal)
# v20.58 -- BEYOND 98 % OF THE RAM (never before): M01, M02, M16, M34 and P00's PASS B go OUT OF CORE instead of stopping -- exact, never
# sampled (_outofcore.py: pixel partitions, the same code per partition, the two-way FE solved from their cross-products). The engines in
# YOUR order; one that is not installed is named with the reason and the next is used; the built-in batches are always the last resort:
#   "dask"     Dask (dask.distributed): keeps the familiar PyData ecosystem (pandas / numpy), no Java/Scala -- the default
#   "spark"    Apache Spark (pyspark, local[all cores]; Java 17+): the enterprise engine, optimised for heavy SQL-like warehousing pipelines
#   "batches"  the built-in batches: one partition after another in this process (always available)
OUT_OF_CORE = ("dask", "spark", "batches")
OUT_OF_CORE_SPILL_DIR = None   # where the partitions and the engines' spill files go: None = <the panel's folder>/_out_of_core
# ---- optional overrides: None = derived from INPUT_DIR as documented above ----
OUTPUT_DIR = None
TEMP_DIR = None
SUBWSHED_CROSSWALK_PATH = r"D:\LKT\RWD_Sub_watershed_final_list.xlsx"
FUND_RELEASE_PATH = r"D:\LKT\Districtwise_Month_wise_Progress_with_DoseIntensity_and_SWS.xlsx"
# =========================================================

OUTPUT_SUBDIR = "output_4Models"   # v20.58: THIS project's output folder inside the data root (the full pipeline RWD_Artal: "output")
PATHS_FILE = "reward_paths.json"


_SAID = set()
def _portable(p):
    """v20.49: a Windows drive path (D:\\LKT\\...) on Linux / macOS (Colab, a test machine) is not a path there -- it was
    created as a RELATIVE folder literally named "D:\\LKT\\TST_Artal" inside the bundle. There it becomes
    ~/REWARD_data/<its last folder> (and says so). Windows is unchanged.
    v20.54: when the last folder is a generic name ("data", as in D:\\LKT\\RWD_Artal\\data since v20.50) its parent is kept
    too -- ~/REWARD_data/RWD_Artal/data -- so the two Python projects do not share one data root there."""
    import re as _re
    if p and os.name != "nt" and _re.match(r"^[A-Za-z]:[\\/]", str(p)):
        parts = [x for x in _re.split(r"[\\/]", str(p).rstrip("\\/"))[1:] if x]
        keep = parts[-2:] if len(parts) >= 2 and parts[-1].lower() in ("data", "input", "inputs", "exports", "output") else parts[-1:]
        q = os.path.join(os.path.expanduser("~"), "REWARD_data", *keep)
        if p not in _SAID:
            _SAID.add(p); print(f"[INFO]    {p} is a Windows path; on this system the data root is {q} (set INPUT_DIR / REWARD_INPUT_DIR to change it)")
        return q
    return p

def _file_path(p):
    """v20.58: a FILE path as you set it -- absolute where it is a path on this system; a Windows drive path on Linux / macOS stays exactly
    as written (os.path.abspath made "D:\\LKT\\x.xlsx" into "<current folder>/D:\\LKT\\x.xlsx" in the messages there). Windows unchanged."""
    import re as _re
    if p and os.name != "nt" and _re.match(r"^[A-Za-z]:[\\/]", str(p)): return str(p)
    return os.path.abspath(p) if p else p

def _resolve_input(p):
    """v20.50: the project's data folder once the data are moved (MIGRATE_DATA.bat); until then the old one, said once."""
    if (p == INPUT_DIR and not os.environ.get("REWARD_INPUT_DIR") and LEGACY_INPUT_DIR
            and not os.path.isdir(_portable(p)) and os.path.isdir(_portable(LEGACY_INPUT_DIR))):
        if "legacy" not in _SAID:
            _SAID.add("legacy"); print(f"[INFO]    {p} does not exist yet -- using the old data folder {LEGACY_INPUT_DIR} (run MIGRATE_DATA.bat to move it)")
        return LEGACY_INPUT_DIR
    return p

def derive(input_dir=None, output_dir=None, temp_dir=None, crosswalk=None, fund_release=None):
    """The one derivation rule. Returns a dict with every path the pipeline uses."""
    inp = os.path.abspath(_portable(_resolve_input(input_dir or INPUT_DIR)))
    out = os.path.abspath(output_dir or OUTPUT_DIR or os.path.join(inp, OUTPUT_SUBDIR))
    tmp = os.path.abspath(temp_dir or TEMP_DIR or os.path.join(out, "_tmp_shards"))
    results = os.path.join(out, "results")
    return {
        "INPUT_DIR": inp, "OUTPUT_DIR": out, "TEMP_DIR": tmp,
        "FINAL_PANEL": os.path.join(out, "did_panel_full.parquet"),
        "RESULTS_ROOT": results,
        "ESTIMATOR_FILES_DIR": os.path.join(out, "estimator_files"),
        "GROUND_LINKS_PATH": os.path.join(results, "P08", "ground_links.parquet"),
        # v20.24: the M07 ground-truth file is WRITTEN by P08 next to the ground links; the M08 instrument is an
        # input you provide -- both follow INPUT_DIR like everything else (override below if they live elsewhere)
        "GROUND_TRUTH_OUTCOMES_PATH": _file_path(GROUND_TRUTH_OUTCOMES_PATH) if GROUND_TRUTH_OUTCOMES_PATH else os.path.join(results, "P08", "ground_truth_outcomes.csv"),
        "ROLLOUT_INSTRUMENT_PATH": _file_path(ROLLOUT_INSTRUMENT_PATH) if ROLLOUT_INSTRUMENT_PATH else os.path.join(inp, "rollout_instrument.csv"),
        "SUBWSHED_CROSSWALK_PATH": _file_path(crosswalk or SUBWSHED_CROSSWALK_PATH),
        "FUND_RELEASE_PATH": _file_path(fund_release or os.environ.get("REWARD_FUND_PATH") or FUND_RELEASE_PATH),   # the env var is for tests
    }


def save(paths):
    """Record the active layout next to the outputs (best effort -- never fails a run)."""
    try:
        os.makedirs(paths["OUTPUT_DIR"], exist_ok=True)
        with open(os.path.join(paths["OUTPUT_DIR"], PATHS_FILE), "w", encoding="utf-8") as fh:
            json.dump(paths, fh, indent=1)
    except Exception:
        pass


def load(output_dir):
    p = os.path.join(output_dir, PATHS_FILE)
    if not os.path.exists(p): return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def is_output_path(path, paths):
    """True when `path` lives under OUTPUT_DIR or TEMP_DIR -- a generated file, never source data."""
    a = os.path.abspath(path)
    return any(a.startswith(os.path.abspath(paths[k]) + os.sep) or a == os.path.abspath(paths[k])
               for k in ("OUTPUT_DIR", "TEMP_DIR"))


def describe(paths):
    return "\n".join(f"  {k:24s} {v}" for k, v in paths.items())
