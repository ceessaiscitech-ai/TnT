"""
selfcheck_4models.py -- validate the FOUR-MODEL bundle (RWD_4Models: P00 + M01, M02, M16, M34, Python and R) BEFORE running anything.

    python selfcheck_4models.py            (from inside python/DIDRDP_4Models_v20)

Part A -- THIS PROJECT: the files it carries (and only those), its configuration (_paths.PIPELINE_MODELS, OUTPUT_SUBDIR, the R lib's
PIPELINE_MODELS / OUTPUT_SUBDIR), its scope (the panel's columns, the packages, the pre-built routes, R's models), its P00 (12 steps, nothing for
another model), its notebooks (the design of each run in CELL 1, your location rules "drop"), your rules on small known answers (repeated rows
dropped whole, the sample-integrity guard, the fragment codes, the fund timing, the 98 % rule and the out-of-core engines beyond it, M34 = HonestDiD
on M02's event study) and the R side (every R file parses; R's models, packages and output folder are this project's).
Part B -- THE ENGINE: the checks of the full pipeline's selfcheck.py that concern the engine this bundle shares with it (the engine files are
the full pipeline's, byte for byte -- the four models' scope is configuration), copied from selfcheck.py of the same version and run HERE.
Exit code 0 = clean, 1 = problems (each printed with the file and the fix). Nothing is skipped silently: a check that cannot run says so.
"""
import os, sys, re, json, glob, ast, inspect, importlib, subprocess, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = os.path.dirname(os.path.dirname(HERE))
RHOME = os.path.join(BUNDLE, "R")
MODELS = ("M01", "M02", "M16", "M34")
OUT_SUB = "output_4Models"
PROBLEMS, NOTES = [], []
def bad(msg): PROBLEMS.append(msg); print(f"[FAILED]  {msg}")
def note(msg): NOTES.append(msg); print(f"[OK]      {msg}")
def warn(msg): print(f"[WARNING] {msg}")
def _ver(v): return tuple(int(x) for x in re.findall(r"\d+", str(v))) or (0,)
def _code(nb):
    return ["".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code"]
def _nb_text(nb):
    return "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"])
def _rscript():
    r = shutil.which("Rscript")
    if r: return r
    try:
        sys.path.insert(0, HERE); import _common as _C
        return _C.find_rscript()
    except Exception:
        return None

PY_NOTEBOOKS = {"01_Panel_Preparation/P00_RUN_ALL_Panel_Preparation.ipynb", "02_Core_DiD_Models/M01_Canonical_2x2_Static_TWFE.ipynb",
                "02_Core_DiD_Models/M02_Event_Study_dynamic_TWFE.ipynb", "02_Core_DiD_Models/M16_Formal_Joint_Pre_Trends_F_test.ipynb",
                "04_Advanced_Staggered_Robustness/M34_Honest_DiD_parallel_trends_sensitivity.ipynb", "06_Validation/V01_Results_Audit.ipynb",
                "08_Multisite_Runs/MS01_Multisite_Runs.ipynb"}
R_NOTEBOOKS = {"R_P00_Prepare_Panel", "R_M01", "R_M02", "R_M16", "R_M34", "R_RUN_ALL_MODELS", "R_V01_Results_Audit"}
R_LIB = {"model_names.R", "models_prebuilt.R", "reward_design.R", "reward_diagnostics.R", "reward_fund.R", "reward_models_core.R",
         "reward_packages.R", "reward_paths.R", "reward_prep.R", "run_one.R", "reward_outofcore.R", "reward_prep_ooc.R", "reward_ooc_task.R"}
MODEL_NB = {"M01": "02_Core_DiD_Models/M01_Canonical_2x2_Static_TWFE.ipynb", "M02": "02_Core_DiD_Models/M02_Event_Study_dynamic_TWFE.ipynb",
            "M16": "02_Core_DiD_Models/M16_Formal_Joint_Pre_Trends_F_test.ipynb", "M34": "04_Advanced_Staggered_Robustness/M34_Honest_DiD_parallel_trends_sensitivity.ipynb"}
LEFT_OUT_COLUMNS = {"District", "dose_per_subwshed", "dose_amount_sws", "dose_intensity_per_ha", "area_hectare", "first_treat_agri_year",
                    "first_treat_season", "LandUse", "LandUseDW"}


# ================================================================================================= A. THIS PROJECT
def s4_structure():
    """the bundle carries P00 + the four models (Python and R) and nothing of the other 41"""
    nbs = {os.path.relpath(p, HERE).replace(os.sep, "/") for p in glob.glob(os.path.join(HERE, "**", "*.ipynb"), recursive=True)
           if ".ipynb_checkpoints" not in p}
    if nbs != PY_NOTEBOOKS:
        bad(f"Python notebooks: missing {sorted(PY_NOTEBOOKS - nbs)}, not of this project {sorted(nbs - PY_NOTEBOOKS)}")
    else: note(f"Python notebooks: exactly this project's {len(nbs)} (P00, M01, M02, M16, M34, MS01, V01)")
    gone = [f for f in ("_ground_common.py", "ground_utils.py", "_bm_means.py", os.path.join("python_prebuilt", "ml_spatial_pipeline.py"),
                        "03_Spatial_Heterogeneity_Diagnostics", "05_Causal_AI_ML") if os.path.exists(os.path.join(HERE, f))]
    need = [f for f in ("_common.py", "_prep_common.py", "_paths.py", "_location.py", "_fragments.py", "_fund.py", "_sws_geometry.py", "_sites.py",
                        "_hardware.py", "_names.py", "_readiness.py", "_version.py", "readiness.py", "_outofcore.py", "_ooc_models.py",
                        "validate_out_of_core.py", os.path.join("python_prebuilt", "pf_pipeline.py"),
                        os.path.join("python_prebuilt", "dd_pipeline.py"), os.path.join("data", "sites", "SWSs20_KarnatakaAll5k.shp"),
                        os.path.join("data", "sites", "sites.csv")) if not os.path.exists(os.path.join(HERE, f))]
    if gone or need: bad(f"engine files: not of this project {gone}; missing {need}")
    else: note("engine: the full pipeline's modules (the out-of-core layer too: _outofcore.py, _ooc_models.py), the pre-built pyfixest / diff-diff "
               "layers, the shapefile and sites registry; no ground-data, benchmark-means or ML / spatial layer (no model of this project uses them)")
    if not os.path.isdir(RHOME): bad(f"R folder missing: {RHOME}"); return
    for sub, ext in (("rstudio", ".Rmd"), ("jupyter", ".ipynb")):
        got = {os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(RHOME, sub, "*" + ext))}
        if got != R_NOTEBOOKS: bad(f"R {sub}: missing {sorted(R_NOTEBOOKS - got)}, not of this project {sorted(got - R_NOTEBOOKS)}")
        else: note(f"R {sub}: exactly this project's {len(got)} notebooks (R_P00, R_M01, R_M02, R_M16, R_M34, R_RUN_ALL_MODELS, R_V01)")
    lib = {os.path.basename(p) for p in glob.glob(os.path.join(RHOME, "lib", "*.R"))}
    miss_r = [f for f in ("00_SETUP.R", "RWD_4Models.Rproj", os.path.join("tests", "run_all_tests.R"), os.path.join("tests", "selftest.R"),
                          os.path.join("lib", "reward_ooc_engine.py"),
                          os.path.join("data", "sites", "SWSs20_KarnatakaAll5k.shp"), os.path.join("data", "sites", "sites.csv")) if not os.path.exists(os.path.join(RHOME, f))]
    if lib != R_LIB or miss_r: bad(f"R lib {sorted(lib ^ R_LIB)} / missing {miss_r}")
    else: note("R: the full R pipeline's lib (also the Python bridge; the out-of-core layer: reward_outofcore.R, reward_prep_ooc.R, reward_ooc_task.R, "
               "reward_ooc_engine.py), 00_SETUP.R, the tests, the shapefile and sites registry")
    code = [p for p in glob.glob(os.path.join(BUNDLE, "**", "*"), recursive=True)            # the code and the notebooks (the docs tell its history)
            if os.path.isfile(p) and os.path.splitext(p)[1].lower() in (".py", ".ipynb", ".r", ".rmd", ".bat", ".sh")
            and os.path.basename(p) != os.path.basename(__file__)]
    old_copy = "artal" + "1"
    a1 = [os.path.relpath(p, BUNDLE) for p in code if old_copy in open(p, encoding="utf-8", errors="ignore").read().lower()]
    if a1: bad(f"code still refers to the retired second Python copy (RWD_Artal + 1): {a1[:5]}")
    else: note(f"no code or notebook refers to the retired second Python copy ({len(code)} files): one Python and one R pipeline")


def s4_config():
    """_paths.py and the R lib carry this project's scope and output folder; your paths intact"""
    sys.path.insert(0, HERE)
    import _paths as PA, _common as C, _prep_common as P
    miss = []
    if tuple(PA.PIPELINE_MODELS or ()) != MODELS: miss.append(f"_paths.PIPELINE_MODELS = {PA.PIPELINE_MODELS}")
    if PA.OUTPUT_SUBDIR != OUT_SUB: miss.append(f"_paths.OUTPUT_SUBDIR = {PA.OUTPUT_SUBDIR!r}")
    if tuple(C.pipeline_models()) != MODELS or C.in_pipeline("M05") or not C.in_pipeline("M16"): miss.append(f"_common.pipeline_models() = {C.pipeline_models()}")
    src = open(os.path.join(HERE, "_paths.py"), encoding="utf-8").read()
    for s_ in (r'r"D:\LKT\RWD_Artal\data"', r'r"D:\LKT\RWD_Sub_watershed_final_list.xlsx"',
               r'r"D:\LKT\Districtwise_Month_wise_Progress_with_DoseIntensity_and_SWS.xlsx"'):
        if s_ not in src: miss.append(f"_paths.py: your path {s_} changed")
    try:
        d = PA.derive(os.path.join(tempfile.gettempdir(), "s4_root"))
        od = d.get("OUTPUT_DIR") if isinstance(d, dict) else getattr(d, "OUTPUT_DIR", None)
        if not od or os.path.basename(os.path.normpath(od)) != OUT_SUB: miss.append(f"derive(): OUTPUT_DIR = {od}")
    except Exception as e:
        miss.append(f"_paths.derive failed: {type(e).__name__}: {e}")
    if os.path.basename(os.path.normpath(P.OUTPUT_DIR)) != OUT_SUB or os.path.basename(os.path.dirname(os.path.normpath(C.RESULTS_ROOT))) != OUT_SUB:
        miss.append(f"the engines write to {P.OUTPUT_DIR} / {C.RESULTS_ROOT}")
    rp = open(os.path.join(RHOME, "lib", "reward_paths.R"), encoding="utf-8").read()
    rk = open(os.path.join(RHOME, "lib", "reward_packages.R"), encoding="utf-8").read()
    su = open(os.path.join(RHOME, "00_SETUP.R"), encoding="utf-8").read()
    four_r = 'c("M01", "M02", "M16", "M34")'
    if f'if (!exists("PIPELINE_MODELS")) PIPELINE_MODELS <- {four_r}' not in rp: miss.append("R reward_paths.R: PIPELINE_MODELS")
    if f'if (!exists("PIPELINE_MODELS")) PIPELINE_MODELS <- {four_r}' not in rk: miss.append("R reward_packages.R: PIPELINE_MODELS")
    if f'OUTPUT_SUBDIR     <- "{OUT_SUB}"' not in rp or "OUTPUT_DIR        <- file.path(ROOT, OUTPUT_SUBDIR)" not in rp: miss.append("R: OUTPUT_SUBDIR / OUTPUT_DIR")
    for s_ in ('DEFAULT_ROOT      <- "D:/LKT/RWDR/data"', '"D:/LKT/RWD_Sub_watershed_final_list.xlsx"',
               '"D:/LKT/Districtwise_Month_wise_Progress_with_DoseIntensity_and_SWS.xlsx"'):
        if s_ not in rp: miss.append(f"R reward_paths.R: your path {s_} changed")
    i_pm = su.find(f"PIPELINE_MODELS <- {four_r}"); i_src = su.find('source(file.path(R_HOME_DIR, "lib", "reward_packages.R"))')
    if i_pm < 0 or i_src < 0 or i_pm > i_src or "intersect(REWARD_R_PACKAGES$package[REWARD_R_PACKAGES$source == \"CRAN\"], project_packages())" not in su:
        miss.append("R 00_SETUP.R does not install this project's packages only")
    if miss: bad("configuration: " + " | ".join(miss))
    else: note(f"configuration: PIPELINE_MODELS = {MODELS} and the output folder <data>\\{OUT_SUB} in Python (_paths.py) and R (lib/reward_paths.R, "
               "lib/reward_packages.R, 00_SETUP.R); your data, crosswalk and fund-workbook paths unchanged")


def s4_scope():
    """the panel holds what the four models read and nothing else; the packages and pre-built routes are theirs"""
    sys.path.insert(0, HERE)
    import _common as C, _prep_common as P
    miss = []
    lo = set(P.panel_columns_left_out())
    if lo != LEFT_OUT_COLUMNS: miss.append(f"columns left out of the panel {sorted(lo)} (expected {sorted(LEFT_OUT_COLUMNS)})")
    inside = sorted(set(P.FINAL_PANEL_COLUMNS) & LEFT_OUT_COLUMNS)
    if inside: miss.append(f"panel schema still holds {inside}")
    need = set()
    for o in ("NDVI", "EVI", "LAI"):
        try: need |= set(C.columns_for(o))
        except Exception as e: miss.append(f"columns_for({o}) raised {type(e).__name__}: {e}")
    lack = sorted(need - set(P.FINAL_PANEL_COLUMNS) - set(getattr(C, "OPTIONAL_READ_COLUMNS", ())))
    if lack: miss.append(f"the models read columns the panel does not hold: {lack}")
    try:
        st = C.ensure_python_packages(install=False, verbose=False)
        est = sorted(st.loc[st.kind == "estimator", "package"])
        if est != ["pyfixest"]: miss.append(f"Python estimator packages of this project {est} (expected ['pyfixest'])")
    except Exception as e:
        miss.append(f"ensure_python_packages raised {type(e).__name__}: {e}")
    m_layer = [m for m, s in C.PREBUILT_MODELS.items() if s.get("layer") == C._M and C.in_pipeline(m)]
    if m_layer: miss.append(f"model-layer package routes in this project: {m_layer}")
    for m in MODELS:
        if m not in C.PREBUILT_MODELS: miss.append(f"{m}: no pre-built route entry")
    if [C.PREBUILT_MODELS[m].get("package") for m in ("M01", "M02")] != ["pyfixest", "pyfixest"]: miss.append("M01 / M02: not pyfixest first")
    if C.R_ROUTES.get("M34") != ["HonestDiD", "fixest"]: miss.append(f"M34's R route {C.R_ROUTES.get('M34')}")
    if miss: bad("scope: " + " | ".join(miss))
    else: note(f"scope: the panel leaves out {len(LEFT_OUT_COLUMNS)} columns only other models read ({', '.join(sorted(LEFT_OUT_COLUMNS))}) and "
               f"holds every column M01 / M02 / M16 / M34 read; Python packages: pyfixest (+ the base libraries; Dask / Spark only beyond 98 %); pre-built "
               f"routes: pyfixest for M01 / M02, the engine's rank-safe joint test for M16, R HonestDiD on M02's event study for M34")


P00_ORDER = ["P00_Settings", "P01_File_Inventory_and_Audit", "P02_Column_Harmonization_Check", "P00_Validate_or_Skip",
             "P03_Ingest_Harmonize_and_Assign_Pixel_UIDs", "P05_Fund_Release_Treatment_Timing", "P04_Assemble_Ordered_Panel",
             "P06_Panel_Integrity_and_Readiness_Report", "P00_Design_for_Every_Model", "P09_Estimator_Variable_Files", "P10_Model_Readiness",
             "P12_Prebuilt_Packages_Verify"]
def s4_p00():
    """P00: the 12 steps of this project, in order, every code cell compiles, nothing for another model"""
    nb = os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb")
    code = _code(nb); txt = _nb_text(nb)
    steps = [re.match(r"# ===== (\S+?)(\.ipynb| --|\s)", c).group(1) for c in code if c.startswith("# ===== ")]
    miss = []
    if steps != P00_ORDER: miss.append(f"steps {steps}")
    for i, c in enumerate(code):
        src = "\n".join(l for l in c.split("\n") if not l.lstrip().startswith(("%", "!")))
        try: compile(src, f"P00 cell {i}", "exec")
        except SyntaxError as e: miss.append(f"code cell {i} does not compile: {e}")
    for w in ("ground_inputs_status", "RUN_GROUND", "RUN_DIAGNOSTICS", "RUN_SWS_AUDIT", "DOSE_VARIABLE", "_ground_common", "ground_utils", "_bm_means",
              "build_district_season_dose", "apply_subwshed_division", "P08_", "P13_", "P07_", "P02b", "45 models"):
        if w in txt: miss.append(f"still contains {w!r}")
    st = next((c for c in code if c.startswith("# ===== P00_Settings")), "")
    for v, val in (("P.DEDUP_FILL_FROM_DUPLICATES", "False"), ("P.DEDUP_PRIORITY", '"newer"'), ("OVERLAP_ROWS", '"drop"'), ("FRAGMENT_RULE", '"drop"'),
                   ("SEASONS", '"all"'), ("TREATMENT_TIMING", '"fund"'), ("P.NEAR_DUPLICATE_PIXELS", "True")):
        if len(re.findall(rf"(?m)^{re.escape(v)}\s*=\s*{re.escape(val)}", st)) != 1: miss.append(f"P00_Settings: {v} = {val} not set once")
    p05 = next((c for c in code if c.startswith("# ===== P05_")), "")
    if "dose_table=None; xw=None" not in p05 or "F.build_fund_tables(" not in p05: miss.append("P05: not the fund timing only")
    if miss: bad("P00: " + " | ".join(miss))
    else: note("P00: the 12 steps of this project in order (settings, inventory, harmonisation, validate-or-skip, PASS A, fund timing, PASS B, "
               "integrity, design defaults, estimator files, readiness, packages); every code cell compiles; no ground linkage, surrogates, dose, "
               "preview or diagnostics; repeated rows dropped whole, the location rules 'drop', seasons + years, the fund timing -- set once in P00_Settings")


DESIGN_KEYS = ("DESIGN_MODE", "TREATMENT_TIMING", "TREATMENT_YEAR", "FUND_START_RULE", "CONTROL_ZONES", "PRE_YEARS", "POST_YEARS", "SEASONS",
               "EXCLUDE_TRANSITION_YEAR", "UNIT_FE", "SUB_WATERSHEDS", "FRAGMENT_RULE", "OVERLAP_ROWS", "POOLED_FE", "EXCLUDE_GAPFILLED", "COVARIATES")
CALLS = {"M01": ("C.covariate_response(df", "C.ooc_model(MODEL_ID"), "M02": ("window=None, covariates=list(C.DEFAULT_COVARIATES)", "C.ooc_model(MODEL_ID"),
         "M16": ("covariates=list(C.DEFAULT_COVARIATES)", "C.ooc_model(MODEL_ID"),
         "M34": ("C.honest_did_summary(es, OUTCOME, df)", "C.estimate_event_study(df, OUTCOME", "C.ooc_model(MODEL_ID")}
def s4_models():
    """each model's CELL 1 sets the design of its run, your location rules 'drop'; it calls the validated estimator; R the same"""
    miss = []
    for m in MODELS:
        f = os.path.join(HERE, MODEL_NB[m]); code = _code(f)
        c1 = next((c for c in code if "# ---- CELL 1: setup ----" in c), "")
        lack = [k for k in DESIGN_KEYS if not re.search(rf"(?m)^{k}\s*=", c1)]
        sc = c1[c1.find("C.set_scenario("):]
        lack += [f"set_scenario({k.lower()}=...)" for k in ("timing", "fragment_rule", "overlap_rows", "sub_watersheds", "seasons", "control_zones", "covariates")
                 if f"{k}=" not in sc[:sc.find(")\n") + 1]]
        if not re.search(r'(?m)^FRAGMENT_RULE\s*=\s*"drop"', c1) or not re.search(r'(?m)^OVERLAP_ROWS\s*=\s*"drop"', c1): lack.append("FRAGMENT_RULE / OVERLAP_ROWS not 'drop'")
        if not re.search(r"(?m)^MAX_ROWS\s*=\s*None", c1): lack.append("MAX_ROWS not None")
        for w in ("DOSE_VARIABLE", "HET_COVARIATE", "CATE_COVARIATES", "N_PERM", "N_FACTORS", "MAX_SPATIAL_N"):
            if w in c1: lack.append(f"a setting of another model: {w}")
        body = "\n".join(code).replace('\\"', '"')
        lack += [f"does not call {p}" for p in CALLS[m] if p not in body]
        for i, c in enumerate(code):
            src = "\n".join(l for l in c.split("\n") if not l.lstrip().startswith(("%", "!")))
            try: compile(src, f"{m} cell {i}", "exec")
            except SyntaxError as e: lack.append(f"cell {i} does not compile: {e}")
        if lack: miss.append(f"{m}: {lack}")
    for k in ("R_M01", "R_M02", "R_M16", "R_M34", "R_RUN_ALL_MODELS"):
        for p in (os.path.join(RHOME, "rstudio", k + ".Rmd"), os.path.join(RHOME, "jupyter", k + ".ipynb")):
            s = _nb_text(p) if p.endswith(".ipynb") else open(p, encoding="utf-8").read()
            lk = [w for w in ("TREATMENT_TIMING <-", "CONTROL_RINGS", 'FRAGMENT_RULE    <- "drop"', 'OVERLAP_ROWS     <- "drop"', "SUB_WATERSHEDS",
                              "model_design()") if w not in s]
            if "DOSE_VARIABLE" in s: lk.append("DOSE_VARIABLE")
            if k != "R_RUN_ALL_MODELS" and f'run_model_R("{k[2:]}"' not in s: lk.append(f'run_model_R("{k[2:]}")')
            if lk: miss.append(f"{os.path.basename(p)}: {lk}")
    p00 = open(os.path.join(RHOME, "rstudio", "R_P00_Prepare_Panel.Rmd"), encoding="utf-8").read()
    if "CONTROL_RINGS  <-" in p00 or "TREATMENT_YEAR <-" in p00 or "run_prep()" not in p00: miss.append("R_P00 sets the design / does not build the panel")
    if miss: bad("model notebooks: " + " | ".join(miss))
    else: note(f"model notebooks: M01 / M02 / M16 / M34 (Python) and R_M01 / R_M02 / R_M16 / R_M34 / R_RUN_ALL_MODELS (RStudio and Jupyter) set the "
               f"design of the run ({len(DESIGN_KEYS)} options) and apply it when they run; FRAGMENT_RULE and OVERLAP_ROWS 'drop'; every row "
               "(MAX_ROWS None); no setting of another model; each calls the validated estimator in memory and ooc_model beyond 98 % (M34: HonestDiD "
               "on M02's event study)")


def s4_rules():
    """your rules on small known answers: repeated rows dropped whole, the integrity guard, the fragment codes, the fund timing, 98 %, M34"""
    sys.path.insert(0, HERE)
    import numpy as np, pandas as pd
    import _prep_common as P, _common as C, _hardware as H, _fragments as FR, _fund as F
    # 1. repeated rows: the newer export's row kept AS IT IS (its gap stays a gap), the other dropped whole; an empty newer row claims its key
    df = pd.DataFrame([dict(site_id=1, pixel_id=1, Year=2023, Season=1, NDVI=np.nan, LAI=1.0, src_file="new.csv", file_mtime=9.0),
                       dict(site_id=1, pixel_id=1, Year=2023, Season=1, NDVI=0.9, LAI=1.5, src_file="old.csv", file_mtime=1.0),
                       dict(site_id=1, pixel_id=2, Year=2023, Season=1, NDVI=0.5, LAI=1.1, src_file="old.csv", file_mtime=1.0)])
    out, _ = P.resolve_duplicates(df.copy(), conflict_log=[])
    o1 = out[out.pixel_id == 1]
    e_ = pd.DataFrame([dict(site_id=1, pixel_id=1, Year=2023, Season=1, NDVI=np.nan, LAI=np.nan, Rain=600.0, src_file="new.csv", file_mtime=9.0),
                       dict(site_id=1, pixel_id=1, Year=2023, Season=1, NDVI=0.9, LAI=1.5, Rain=610.0, src_file="old.csv", file_mtime=1.0)])
    e1, _ = P.apply_missing_policy(e_.copy(), drop_empty=False); e2, _ = P.resolve_duplicates(e1, conflict_log=[]); e3, _ = P.drop_rows_without_outcome(e2)
    if P.DEDUP_FILL_FROM_DUPLICATES is not False or len(out) != 2 or not np.isnan(o1.NDVI.iloc[0]) or o1.LAI.iloc[0] != 1.0 or len(e3) != 0:
        bad(f"repeated rows: a dropped row's value reached the panel ({o1.to_dict('records')}; empty-row case {len(e3)} row(s))")
    else: note("repeated rows: the newer export's row kept as it is (its gap stays a gap), the older one dropped WHOLE; a newer EMPTY row claims its "
               "pixel-year-season (the older row never takes its place)")
    # 2. the sample-integrity guard stops a model on any leak (the location rules "drop")
    saved = {k: (list(v) if isinstance(v, (list, tuple)) else (dict(v) if isinstance(v, dict) else v)) for k, v in C.ACTIVE.items()}
    try:
        C.set_scenario(verbose=False, all_years=True); C.set_scenario(verbose=False, control_zones="1-5", fragment_rule="drop", overlap_rows="drop", seasons="all")
        base = pd.DataFrame({"pixel_id": [1, 1, 2, 2], "Year": [2021, 2023, 2021, 2023], "Season": [1, 1, 1, 1], "buff_km": [0, 0, 3, 3],
                             "treatment": [1, 1, 0, 0], "site_id": [1, 1, 1, 1], "site_check": [0, 0, 0, 0]})
        base.attrs["synthetic"] = True
        caught = {}
        for name, frm in (("clean", base), ("a repeated pixel-year-season", pd.concat([base, base.iloc[[0]]])),
                          ("a pixel outside every polygon", base.assign(site_check=[0, 0, 0, 3])),
                          ("a pixel both treated and a control", pd.concat([base, pd.DataFrame({"pixel_id": [2], "Year": [2022], "Season": [1], "buff_km": [3],
                                                                                                "treatment": [1], "site_id": [1], "site_check": [0]})])),
                          ("a pixel in two rings", base.assign(buff_km=[0, 0, 3, 2]))):
            frm = frm.copy(); frm.attrs["synthetic"] = True
            try: C.sample_integrity(frm, label="selfcheck", verbose=False); caught[name] = False
            except C.InsufficientDataError: caught[name] = True
        ok_ = caught.pop("clean") is False and all(caught.values())
    except Exception as e:
        ok_, caught = False, {"error": f"{type(e).__name__}: {e}"}
    finally:
        C.ACTIVE.clear(); C.ACTIVE.update(saved); C._EXPLICIT_KEYS.clear()
    if not ok_: bad(f"sample integrity: a leak did not stop the model {caught}")
    else: note("sample integrity: a repeated pixel-year-season, a pixel outside every polygon, a pixel both treated and a control and a pixel in two "
               "rings each STOP the model under the 'drop' rules (nothing is estimated on a leaking sample); a clean sample passes")
    # 3. the fragment codes (a file's MAJOR sub-watershed kept; another one's rows -- core or ring -- and outside rows coded out)
    fc = FR.file_codes(np.array([1, 1, 1, 2, 1, 3]), np.array([0, 0, 0, 0, 3, 3]))
    codes = [int(x) for x in (fc[0] if isinstance(fc, tuple) else fc)]
    if codes != [0, 0, 0, 1, 0, 2] or C.ACTIVE.get("fragment_rule", "drop") != "drop": bad(f"fragment codes {codes} / rule {C.ACTIVE.get('fragment_rule')}")
    else: note("fragments: 0 the file's own sub-watershed, 1 inside another one's polygon, 2 outside with another id -- FRAGMENT_RULE 'drop' by default")
    # 4. the fund workbook as the timing: 40 in Oct 2024, +10 a month -> back-cast to July 2024 -> first treated Rabi 2024
    m0 = F.month_index(pd.Timestamp("2024-10-01"))
    long = pd.DataFrame({"site_id": 1, "sws_name": "Artal", "district": "X", "month": [m0 + i for i in range(22)],
                         "amount_reported": [40.0 + 10 * i for i in range(22)], "target": 500.0, "area_ha": 4632.33845007, "area_source": "file"})
    tim = F.fund_timing(F.fund_series(long), rule="backcast", rate_months=12); r_ = tim.iloc[0]
    try:
        C.set_scenario(verbose=False, timing="fund", site_start={1: [2024, 2]}, treatment_year=2024)
        f_ = pd.DataFrame({"site_id": [1] * 8, "buff_km": [0] * 4 + [3] * 4, "Year": [2024] * 4 + [2025] * 4, "Season": [0, 3, 1, 2] * 2,
                           "pixel_id": [1] * 4 + [2] * 4, "subwshed_id": "S1", "time_fe_yearseason": "x"})
        d_ = C.build_treatment_columns(f_.copy()); core = d_[d_.buff_km == 0].set_index("Season")["did_term"].to_dict()
    finally:
        C.ACTIVE.clear(); C.ACTIVE.update(saved); C._EXPLICIT_KEYS.clear()
    if r_["backcast_start"] != F.month_label(m0 - 3) or r_["first_treated_label"] != "Rabi 2024" or core != {0: 0, 3: 0, 1: 0, 2: 1}:
        bad(f"fund timing: start {r_['backcast_start']}, first treated {r_['first_treated_label']}, 2024 core rows treated {core}")
    else: note("fund timing: 40 in Oct 2024 at +10 a month back-casts to July 2024 -> first treated Rabi 2024; per row only the Rabi 2024 core rows are treated")
    # 5. the 98 % rule (RAM / VRAM / every core; nothing sampled or chunked below it; beyond it batches 5x larger, exact)
    caps = ("MAX_SPATIAL_N = 2_000_000", "n_max=4_000_000", "n_max=3_000_000", "nn_sample=2_000_000", "max(1, cores - 1)", "0.6 * p.total_memory",
            "b = 0.6 * free", "total_memory) * 0.7", "cpu_count() or 2) - 1")
    files = [os.path.join(HERE, f_) for f_ in ("_common.py", "_prep_common.py", "_hardware.py")] + glob.glob(os.path.join(HERE, "python_prebuilt", "*.py")) \
            + glob.glob(os.path.join(HERE, "02_Core_DiD_Models", "M*.ipynb"))
    hits = [f"{os.path.basename(f_)}: {c}" for f_ in files for c in caps if c in open(f_, encoding="utf-8").read()]
    rdes = open(os.path.join(RHOME, "lib", "reward_design.R"), encoding="utf-8").read(); rpath = open(os.path.join(RHOME, "lib", "reward_paths.R"), encoding="utf-8").read()
    if abs(float(H.MEMORY_CEILING) - 0.98) > 1e-12 or int(H.RESERVE_CORES) != 0 or float(C.MEMORY_HEADROOM) != 1.0 or hits or not getattr(C, "NO_CHUNKING", False) \
            or "MEMORY_CEILING <- 0.98" not in rdes or "N_MAX_UNITS         <- NULL; N_MAX_PIXELS_MIXED <- NULL; N_MAX_ML <- NULL; N_MAX_SPATIAL <- NULL" not in rpath \
            or "chunk_rows=2_500_000" not in inspect.getsource(C.estimate_twfe_did_streaming):
        bad(f"98 % rule: ceiling {H.MEMORY_CEILING}, reserved cores {H.RESERVE_CORES}, headroom {C.MEMORY_HEADROOM}, caps {hits[:4]}")
    else: note(f"98 % rule: RAM / VRAM usable to 98 % of the total, every core ({H.worker_cap()} workers here), every row in RAM (+ GPU) at once; "
               "only beyond 98 % OUT OF CORE -- Dask, Spark, the built-in batches; exact (Python and R)")
    # 6. M34 = HonestDiD on M02's event study (R HonestDiD first, through the bridge; the engine's bound as the fall-back): the effect assessed is the
    #    equal-weight mean of the post-period effects, the breakdown Mbar exact (never the grid's last value), the grid 0 ... 2 plus the breakdown row
    try:
        import contextlib, io
        r_ = np.random.default_rng(21); rows_ = []
        for px in range(1, 81):
            ring = 0 if px <= 16 else 1 + (px - 17) % 3; a = r_.normal(0, 0.03)
            for s_ in (1, 2, 3):
                for y in range(2016, 2025):
                    tr = int(ring == 0); po = int(y >= 2022)
                    rows_.append((px, s_, y, 1 if px % 2 else 2, ring, tr, po, tr * po,
                                  0.3 + a + {1: 0.05, 2: 0.0, 3: -0.04}[s_] + 0.004 * (y - 2016) + 0.05 * tr * po + r_.normal(0, 0.01)))
        A = pd.DataFrame(rows_, columns=["pixel_id", "Season", "Year", "site_id", "buff_km", "treat_core", "post", "did_term", "y"])
        A["event_time"] = np.where(A.treat_core == 1, A.Year - 2022, np.nan); A["time_fe_yearseason"] = A.Year.astype(str) + "_" + A.Season.astype(str)
        A["subwshed_id"] = "S" + A.site_id.astype(str)
        pm = C.PREBUILT_MODE; C.PREBUILT_MODE = "off"
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                es = C.estimate_event_study(A, "y", "treat_core", "event_time", "pixel_id", "time_fe_yearseason", "subwshed_id", ref_period=-1, window=None, covariates=None)
                h = C.honest_did_summary(es, "y", A)
        finally:
            C.PREBUILT_MODE = pm
        g = h.pop("grid"); post = es[(es.event_time >= 0) & es.identified.astype(bool)]
        bd = float(h["breakdown_Mbar"]); brow = g[g.breakdown_row.astype(bool)]
        ok6 = (abs(h["estimate"] - float(post.beta.mean())) < 1e-12 and abs(h["estimate"] - 0.05) < 0.005 and np.isfinite(bd) and bd > 2
               and set(np.round(g.M.values[:5], 6)) == {0.0, 0.5, 1.0, 1.5, 2.0} and len(brow) == 1 and abs(float(brow.M.iloc[0]) - bd) < 1e-12
               and min(abs(float(brow.ci_low.iloc[0])), abs(float(brow.ci_high.iloc[0]))) == 0.0 and not bool(brow.significant.iloc[0])
               and bool(g[~g.breakdown_row.astype(bool) & (g.M < bd)].significant.all()) and C.R_ROUTES.get("M34") == ["HonestDiD", "fixest"])
        if not ok6: bad(f"M34: effect {h['estimate']:.6f} (post mean {float(post.beta.mean()):.6f}), breakdown {bd}, grid {g.M.round(4).tolist()}")
        else: note(f"M34 = HonestDiD on M02's event study: the effect assessed {h['estimate']:.5f} = the mean of the post-period effects (truth 0.05); the "
                   f"breakdown Mbar {bd:.4g} exact (its interval touches 0), the grid 0 ... 2 plus the breakdown row; R HonestDiD first (the bridge)")
    except Exception as ex:
        bad(f"M34 check failed: {type(ex).__name__}: {ex}")
    rc = open(os.path.join(RHOME, "lib", "reward_models_core.R"), encoding="utf-8").read()
    if "m34_from_event <- function(e, is_year, dse)" not in rc or "l_vec = lv" not in rc or "ooc_m34 <- function" not in open(os.path.join(RHOME, "lib", "reward_outofcore.R"), encoding="utf-8").read():
        bad("R M34: not HonestDiD on M02's event study for the equal-weight post-period mean (in memory and out of core)")
    else: note("R M34: HonestDiD on M02's event study, the target the equal-weight post-period mean (l_vec), the same code in memory and out of core")


def s4_r():
    """every R file parses; R's models, packages, output folder and panel scope are this project's"""
    rs = _rscript()
    if not rs:
        R_STATE["ran"] = False
        warn("R NOT FOUND: the R checks of this bundle did NOT run here (R files parse, R's models / packages / output folder) -- run this "
             "file where R is installed; set R_SCRIPT in P00_Settings if R is installed but not found")
        if os.environ.get("REWARD_REQUIRE_R") == "1": bad("R checks not run (R not found) and REWARD_REQUIRE_R = 1")
        return
    R_STATE["ran"] = True
    files = [p for p in glob.glob(os.path.join(RHOME, "lib", "*.R")) + glob.glob(os.path.join(RHOME, "tests", "*.R")) + [os.path.join(RHOME, "00_SETUP.R")]]
    rmd_code = {}
    for p in glob.glob(os.path.join(RHOME, "rstudio", "*.Rmd")):
        rmd_code[p] = "\n".join(re.findall(r"```\{r[^}]*\}\n(.*?)```", open(p, encoding="utf-8").read(), re.S))
    for p in glob.glob(os.path.join(RHOME, "jupyter", "*.ipynb")):
        rmd_code[p] = "\n".join("".join(c["source"]) for c in json.load(open(p, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
    tmp = tempfile.mkdtemp(prefix="s4_r_")
    chunks = []
    for i, (p, code) in enumerate(rmd_code.items()):
        f = os.path.join(tmp, f"nb{i}.R"); open(f, "w", encoding="utf-8").write(code); chunks.append((p, f))
    allf = [(p, p) for p in files] + chunks
    sc = os.path.join(tmp, "parse.R")
    open(sc, "w", encoding="utf-8").write("a <- commandArgs(TRUE); for (f in a) { r <- tryCatch({ invisible(parse(file = f)); 'ok' }, error = function(e) conditionMessage(e)); "
                                          "cat(f, '\\t', gsub('\\n', ' ', r), '\\n', sep = '') }\n")
    r = subprocess.run([rs, "--vanilla", sc] + [f for _, f in allf], capture_output=True, text=True, timeout=600)
    res = dict(l.split("\t", 1) for l in r.stdout.splitlines() if "\t" in l)
    badp = [os.path.relpath(p, BUNDLE) + ": " + res.get(f, "no answer").strip()[:160] for p, f in allf if res.get(f, "").strip() != "ok"]
    if badp: bad(f"R files that do not parse: {badp[:5]}")
    else: note(f"R: every file parses ({len(files)} scripts, {len(chunks)} notebooks' code)")
    sc2 = os.path.join(tmp, "scope.R")
    open(sc2, "w", encoding="utf-8").write(
        'Sys.setenv(REWARD_TEST_RUN = "1", REWARD_R_ROOT = "' + tmp.replace("\\", "/") + '/root")\n'
        'R_HOME_DIR <- "' + RHOME.replace("\\", "/") + '"\n'
        'suppressMessages(for (f in c("reward_paths.R", "reward_design.R", "reward_prep.R", "reward_models_core.R")) source(file.path(R_HOME_DIR, "lib", f)))\n'
        'cat("MODELS=", paste(names(MODEL_FUN), collapse = ","), "\\n", sep = "")\n'
        'cat("PKGS=", paste(sort(project_packages()), collapse = ","), "\\n", sep = "")\n'
        'cat("OUT=", basename(OUTPUT_DIR), "\\n", sep = "")\n'
        'cat("LEFT=", paste(sort(panel_columns_left_out_R()), collapse = ","), "\\n", sep = "")\n'
        'cat("BM=", as.character(!exists("PIPELINE_MODELS") || !length(PIPELINE_MODELS) || "M07" %in% PIPELINE_MODELS), "\\n", sep = "")\n')
    r = subprocess.run([rs, "--vanilla", sc2], capture_output=True, text=True, timeout=600)
    kv = dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l and l.split("=", 1)[0] in ("MODELS", "PKGS", "OUT", "LEFT", "BM"))
    want_pk = "HonestDiD,RANN,arrow,data.table,dplyr,fixest,jsonlite,knitr,ps,readxl,remotes,rmarkdown,sf"
    got = {"MODELS": ",".join(sorted(kv.get("MODELS", "").strip().split(","))), "PKGS": ",".join(sorted(kv.get("PKGS", "").strip().split(","), key=str.lower)),
           "OUT": kv.get("OUT", "").strip(), "LEFT": kv.get("LEFT", "").strip(), "BM": kv.get("BM", "").strip()}
    want = {"MODELS": "M01,M02,M16,M34", "PKGS": ",".join(sorted(want_pk.split(","), key=str.lower)), "OUT": OUT_SUB, "LEFT": "LandUse,LandUseDW", "BM": "FALSE"}
    diff = {k: (got[k], want[k]) for k in want if got[k] != want[k]}
    if diff: bad(f"R scope: {diff} {(r.stderr or '')[-400:]}")
    else: note(f"R: MODEL_FUN = M01, M02, M16, M34; packages {want_pk.replace(',', ', ')}; output folder ROOT/{OUT_SUB}; the panel leaves out "
               "LandUse / LandUseDW; no benchmark-site means (M07's input)")
    shutil.rmtree(tmp, ignore_errors=True)


R_STATE = {"ran": None}
PROJECT_CHECKS = [s4_structure, s4_config, s4_scope, s4_p00, s4_models, s4_rules, s4_r]


# ================================================================================================= B. THE ENGINE (from selfcheck.py)
# The functions below are copied VERBATIM from selfcheck.py of the full pipeline v20.58 (they check the engine this bundle
# shares with it; a few name functions of the other models, which the engine still contains but this project never runs).

def check_engines():
    sys.path.insert(0, HERE)
    for m in ("_common", "_prep_common", "_ground_common", "_version"):
        sys.modules.pop(m, None)
    mods = {}
    for name in ("_common", "_prep_common"):
        try:
            mods[name] = importlib.import_module(name)
        except Exception as e:
            bad(f"{name}.py does not import: {type(e).__name__}: {e}"); return mods
    vers = {n: getattr(m, "ENGINE_VERSION", None) for n, m in mods.items()}
    dirs = {n: os.path.dirname(os.path.abspath(m.__file__)) for n, m in mods.items()}
    if len(set(vers.values())) != 1:
        bad(f"engine versions differ: {vers} -- both must read _version.py from their own folder")
    else:
        note(f"engine version {list(vers.values())[0]} in both engines")
    if len(set(dirs.values())) != 1:
        bad(f"split installation: {dirs}")
    else:
        note(f"single bundle at {list(dirs.values())[0]}")
    if not os.path.exists(os.path.join(HERE, "_version.py")):
        bad("_version.py missing (single source of truth for the engine version)")
    return mods

def check_notebook_locks(mods):
    eng = _ver(getattr(mods.get("_common"), "ENGINE_VERSION", "0"))
    worst = None
    for nb in sorted(glob.glob(os.path.join(HERE, "0*", "*.ipynb"))):
        d = json.load(open(nb, encoding="utf-8"))
        if d.get("metadata", {}).get("kernelspec", {}).get("name") == "ir": continue
        for c in d["cells"]:
            if c["cell_type"] != "code": continue
            for m in re.findall(r'require_engine\("([0-9.]+)"\)', "".join(c["source"])):
                if _ver(m) > eng:
                    bad(f"{os.path.basename(nb)} requires engine >= {m} but the engine is {'.'.join(map(str, eng))}")
                worst = m if (worst is None or _ver(m) > _ver(worst)) else worst
    if worst: note(f"all notebook locks satisfied (highest required: {worst})")

def check_syntax_and_calls(mods):
    C = mods.get("_common"); P = mods.get("_prep_common")
    sigs = {}
    for mod, alias in ((C, "C"), (P, "P")):
        if mod is None: continue
        for n, f in inspect.getmembers(mod, inspect.isfunction):
            try: sigs[f"{alias}.{n}"] = inspect.signature(f)
            except (ValueError, TypeError): pass
    n_cells = n_calls = 0
    for nb in sorted(glob.glob(os.path.join(HERE, "0*", "*.ipynb"))):
        d = json.load(open(nb, encoding="utf-8"))
        if d.get("metadata", {}).get("kernelspec", {}).get("name") == "ir": continue
        for k, c in enumerate([c for c in d["cells"] if c["cell_type"] == "code"], 1):
            src = "\n".join(l for l in "".join(c["source"]).split("\n") if not l.lstrip().startswith(("%", "!")))
            n_cells += 1
            try:
                tree = ast.parse(src)
            except SyntaxError as e:
                bad(f"{os.path.basename(nb)} cell {k}: SyntaxError {e.msg} (line {e.lineno})"); continue
            for node in ast.walk(tree):                      # keyword arguments that the engine does not accept
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute): continue
                if not isinstance(node.func.value, ast.Name) or node.func.value.id not in ("C", "P"): continue
                key = f"{node.func.value.id}.{node.func.attr}"
                sig = sigs.get(key)
                if sig is None: continue
                n_calls += 1
                params = sig.parameters
                if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()): continue
                for kw in node.keywords:
                    if kw.arg and kw.arg not in params:
                        bad(f"{os.path.basename(nb)} cell {k}: {key}(... {kw.arg}=...) -- the engine's signature is {key}{sig}")
    note(f"{n_cells} code cells parse; {n_calls} engine calls checked against live signatures")

def check_rules(mods):
    C = mods.get("_common")
    if C is None: return
    weather = set(getattr(C, "WEATHER_COVARIATES", []))
    if not weather:
        bad("WEATHER_COVARIATES missing from the engine"); return
    if weather & set(C.ALL_ESTIMATION_VARIABLES):
        bad(f"weather variables are in the OUTCOME list: {sorted(weather & set(C.ALL_ESTIMATION_VARIABLES))}")
    else:
        note(f"weather variables are covariates only: {sorted(weather)}")
    if not weather <= set(C.DEFAULT_COVARIATES):
        bad(f"DEFAULT_COVARIATES is missing {sorted(weather - set(C.DEFAULT_COVARIATES))}")
    else:
        note(f"DEFAULT_COVARIATES = {C.DEFAULT_COVARIATES}")
    if weather & set(getattr(C, "SELECTED_OUTCOMES", [])):
        bad("SELECTED_OUTCOMES contains a weather variable")
    for o in weather:
        try:
            C.columns_for(o); bad(f"columns_for('{o}') did not refuse a weather variable")
        except Exception:
            pass
    note(f"{len(C.SELECTED_OUTCOMES)} outcomes in SELECTED_OUTCOMES (each module loops through these)")
    for fn in ("set_scenario", "parse_control_zones", "scenario_tag", "results_dir", "apply_scenario",
               "scenario_years", "year_mask", "has_year_window",
               "run_other_outcomes", "run_model_notebook", "current_outcome", "build_estimator_files",
               "estimate_twfe_did_streaming", "assert_fits_in_memory", "trace"):
        if not hasattr(C, fn): bad(f"_common.{fn} missing")
    if hasattr(C, "estimate_twfe_did_streaming"):
        pr = inspect.signature(C.estimate_twfe_did_streaming).parameters
        for kw in ("covariates", "balanced_only"):
            if kw not in pr: bad(f"estimate_twfe_did_streaming has no '{kw}' parameter")
        if pr.get("balanced_only") and pr["balanced_only"].default is not False:
            bad("estimate_twfe_did_streaming(balanced_only=) should default to False (keep unbalanced pixels)")
    n_out = 0
    for nb in sorted(glob.glob(os.path.join(HERE, "0[2-5]*", "*.ipynb"))):
        code = "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
        if "current_outcome(" in code: n_out += 1
        elif re.search(r"^\s*OUTCOME\s*=", code, re.M):
            bad(f"{os.path.basename(nb)} sets OUTCOME directly -- the batch cannot inject an outcome into it")
    note(f"{n_out} model notebooks read their outcome through C.current_outcome()")
    n_loop = sum("run_other_outcomes" in "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
                 for nb in glob.glob(os.path.join(HERE, "0[2-5]*", "M*.ipynb")))
    note(f"{n_loop} model notebooks carry the outcome-loop cell (CELL 9)")
    n_scn = sum("set_scenario(" in "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
                and "C.results_dir(" in "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
                for nb in glob.glob(os.path.join(HERE, "0[2-5]*", "M*.ipynb")))
    note(f"{n_scn} model notebooks set the scenario and write to the scenario results folder")
    src_all = {nb: "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
               for nb in glob.glob(os.path.join(HERE, "0[2-5]*", "M*.ipynb"))}
    n_inh = sum("C.load_scenario()" in v for v in src_all.values())
    if n_inh != len(src_all):
        bad(f"only {n_inh} of {len(src_all)} model notebooks inherit a panel-level scenario (C.load_scenario)")
    else:
        note(f"{n_inh} model notebooks inherit the scenario saved at panel preparation")
    leaks = {os.path.basename(k): re.findall(r"C\.(TREATMENT_YEAR|POST_CUTOFF|DEFAULT_CONTROL_ZONES)", v)
             for k, v in src_all.items()}
    leaks = {k: set(v) for k, v in leaks.items() if v}
    if leaks:
        bad(f"model notebooks using the module CONSTANTS instead of the run scenario: {leaks}")
    else:
        note("no model reads TREATMENT_YEAR / POST_CUTOFF / DEFAULT_CONTROL_ZONES directly -- all use the scenario")
    for fn in ("save_scenario", "load_scenario", "scenario_banner"):
        if not hasattr(C, fn): bad(f"_common.{fn} missing (panel-level scenario inheritance)")
    if C is not None:
        try:
            assert C.parse_control_zones("1-3") == (1, 2, 3) and C.parse_control_zones("1") == (1,) and C.parse_control_zones((1, 3, 5)) == (1, 3, 5)
            note("control-ring parsing: '1', '1-3', (1,3,5) all read correctly")
            C.set_scenario(treatment_year=2023, pre_years=4, post_years=2, verbose=False)
            assert C.scenario_years() == (2019, 2024), C.scenario_years()
            C.set_scenario(treatment_year=2024, verbose=False)
            assert C.scenario_years() == (2020, 2025), "the year window must follow the treatment year"
            C.set_scenario(all_years=True, treatment_year=2023, verbose=False)
            assert C.scenario_years() == (None, None)
            note("year window: pre/post counts resolve correctly and follow the treatment year")
        except Exception as e:
            bad(f"parse_control_zones is wrong: {e}")
        src_ = inspect.getsource(C.set_scenario)
        if "OUTCOME_LOOP_STATE" not in src_ or "locked" not in src_:
            bad("set_scenario does not lock the scenario during the outcome loop -- the other variables would be "
                "estimated under the notebook's SAVED defaults instead of the scenario you set")
        else:
            note("the outcome loop keeps the scenario you set (CELL 1 of the saved file cannot override it)")
    if hasattr(C, "run_batch") or os.path.isdir(os.path.join(HERE, "00_Run_All")):
        bad("an across-models batch runner is still present -- v17.11 removed it deliberately")

def check_validation_report():
    p = os.path.join(HERE, "VALIDATION_ALL_MODELS.csv")
    if not os.path.exists(p):
        warn("VALIDATION_ALL_MODELS.csv not found -- run `python validate_all_models.py` to prove every model honours a scenario")
        return
    import pandas as _pd
    d = _pd.read_csv(p)
    fails = d[(d.status_A != "ok") | (d.status_B != "ok")]
    if len(fails): bad(f"models that ERROR under a scenario: {fails.model.tolist()}")
    unexplained = d[(d.honours_scenario.isin(["identical_results", "no_output", "one_scenario_only"]))]
    if len(unexplained): bad(f"models that ignore the scenario or write nothing without a documented reason: {unexplained.model.tolist()}")
    note(f"model validation report: {int((d.honours_scenario == 'yes').sum())} honour the scenario, "
         f"{int((d.honours_scenario == 'data_gap').sum())} blocked by documented data gaps, {len(d)} total")

def check_pixel_id_string_ops():
    """v20.5: pixel_id is int64 since v17.6. Any bare concatenation of it with a string raises UFuncTypeError at
    run time (it broke PASS A). Catch the pattern statically, in the engines and in every notebook."""
    import re as _re
    pat = _re.compile(r'\["pixel_id"\]\s*\+\s*["\']|\bpixel_id\b\s*\+\s*["\']')
    hits = []
    for f in ("_common.py", "_prep_common.py", "_ground_common.py"):
        p = os.path.join(HERE, f)
        if not os.path.exists(p): continue
        for i, l in enumerate(open(p, encoding="utf-8").read().split("\n"), 1):
            if pat.search(l) and ".astype(" not in l and "str(" not in l: hits.append(f"{f}:{i}")
    for nb in glob.glob(os.path.join(HERE, "0*", "*.ipynb")):
        d = json.load(open(nb, encoding="utf-8"))
        for k, c in enumerate([c for c in d["cells"] if c["cell_type"] == "code"], 1):
            for l in "".join(c["source"]).split("\n"):
                if pat.search(l) and ".astype(" not in l and "str(" not in l:
                    hits.append(f"{os.path.basename(nb)} cell {k}")
    if hits: bad(f"int64 pixel_id concatenated with a string (UFuncTypeError at run time): {hits[:5]}")
    else: note("no bare string concatenation of the int64 pixel_id")

def check_pass_b_parallel():
    """v20.6: PASS B must be parallel and must not repeat the expensive per-block steps."""
    import inspect as _i, sys as _s
    _s.path.insert(0, HERE)
    try:
        import _prep_common as _P
    except Exception as e:
        bad(f"_prep_common not importable: {e}"); return
    for fn in ("prepare_pass_b_block", "_pb_worker", "pass_b_worker_count"):
        if not hasattr(_P, fn): bad(f"_prep_common.{fn} missing (PASS B parallelism)")
    if hasattr(_P, "prepare_pass_b_block"):
        src = _i.getsource(_P.prepare_pass_b_block)
        for step in ("build_treatment_columns(", "finalize_panel_block("):
            n = src.count(step)
            if n > 1: bad(f"PASS B calls {step[:-1]} {n} times per block -- it must run once")
        if src.count("build_treatment_columns(") == 1 and src.count("finalize_panel_block(") == 1:
            note("PASS B does each expensive per-block step exactly once")
    if hasattr(_P, "run_pass_b") and "n_workers" not in _i.signature(_P.run_pass_b).parameters:
        bad("run_pass_b has no n_workers parameter -- it would run single-core")
    else:
        note("run_pass_b takes n_workers (autotuned from cores and free RAM)")

def check_full_machine():
    """v20.7: the preparation stages must be sized from the real machine, not a hard-coded cap, and workers must
    not oversubscribe BLAS. Verified against a SIMULATED 64-core / 512 GB Windows box so the numbers are checked
    even when this machine is small."""
    import types, inspect as _i
    p = os.path.join(HERE, "_hardware.py")
    if not os.path.exists(p): bad("_hardware.py missing (machine sizing)"); return
    sys.path.insert(0, HERE)
    import _hardware as H
    saved_ps, saved_cpu, saved_name, saved_lim = H._psutil, os.cpu_count, H.os.name, H.WINDOWS_POOL_LIMIT
    try:
        class _VM: total = 512 * 1024**3; available = 480 * 1024**3
        H._psutil = lambda: types.SimpleNamespace(cpu_count=lambda logical=True: 64 if logical else 32,
                                                  virtual_memory=lambda: _VM())
        os.cpu_count = lambda: 64; H.os.name = "nt"
        a = H.worker_cap(n_tasks=1449); b = H.worker_cap(n_tasks=44, bytes_per_worker=1_710_519 * 220)
        if a < 32: bad(f"PASS A would use only {a} workers on a 64-core box")
        elif a > 61: bad(f"PASS A would ask for {a} workers -- Windows pools fail above 61")
        else: note(f"simulated 64-core Windows box: PASS A {a} workers, PASS B {b} workers")
        if b != 44: bad(f"PASS B would use {b} workers for 44 blocks with 480 GB free (expected 44)")
    finally:
        H._psutil, os.cpu_count, H.os.name, H.WINDOWS_POOL_LIMIT = saved_ps, saved_cpu, saved_name, saved_lim
    prep = open(os.path.join(HERE, "_prep_common.py"), encoding="utf-8").read()
    if "min(32, (os.cpu_count() or 2) // 2)" in prep:
        bad("PASS A still caps the pool at 32 workers / half the cores")
    else:
        note("PASS A sizes its pool from the machine (no 32-worker cap)")
    if "worker_init_threads" not in prep: bad("workers do not pin BLAS to one thread -- N x cores thread oversubscription")
    else: note("worker processes run one BLAS thread each (no oversubscription)")

def check_atomic_panel_write():
    """v20.8: PASS B must publish the panel atomically, and the validator must quarantine an unreadable one."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _prep_common as _P
    src = _i.getsource(_P.run_pass_b)
    renames = ("os.replace(" in src) or ("publish_atomic(" in src)      # v20.10: the rename moved into publish_atomic
    if ".building" not in src or not renames:
        bad("run_pass_b does not write to a temporary file and rename -- an interrupted run would leave a corrupt panel")
    else:
        note("PASS B writes to <panel>.building and publishes only after the footer is closed")
    for fn in ("quarantine_file", "panel_file_report"):
        if not hasattr(_P, fn): bad(f"_prep_common.{fn} missing (corrupt-panel handling)")
    if "quarantine_file(path)" not in _i.getsource(_P.final_panel_is_valid):
        bad("final_panel_is_valid does not move an unreadable panel aside")
    else:
        note("an unreadable panel is quarantined, never silently overwritten")

def check_dedup_semantics():
    """v20.9: dedup must be WITHIN (pixel_id, Year, Season) only, must merge complementary values instead of
    dropping them, and must never compare rows across seasons or years."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _prep_common as _P
    src = _i.getsource(_P.resolve_duplicates)
    keys = tuple(getattr(_P, "DEDUP_KEYS", ()))
    if keys[-3:] != ("pixel_id", "Year", "Season") or (len(keys) == 4 and keys[0] != "site_id"):
        bad(f"dedup key is not (site_id,) pixel_id, Year, Season: {keys}")
    else:
        note("dedup key is (site_id, pixel_id, Year, Season) -- rows in different sites/seasons/years are never compared")
    if "complementary" not in src or ("g.first()" not in src and "n_filled" not in src):
        bad("dedup does not classify / count complementary values -- a second file's variables would be lost silently")
    else:
        note("dedup classifies complementary groups; the kept row's gaps are filled from the rows it drops only with "
             "DEDUP_FILL_FROM_DUPLICATES = True (v20.58 default: the repeated rows are dropped whole, the values not used are counted)")
    pb = _i.getsource(_P.run_pass_b)
    if "panel_balance_by_block.csv" not in pb:
        bad("PASS B does not write the panel balance report")
    else:
        note("PASS B reports pixels per Year x Season block and flags an unbalanced panel")

def check_file_handles():
    """v20.10: no metadata-only ParquetFile may be left open -- on Windows an open handle blocks the rename that
    publishes the panel ([WinError 5]). Also require the recovery helper."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _prep_common as _P
    for fn in ("pq_meta", "pq_is_readable", "publish_atomic", "finalize_pending_panel"):
        if not hasattr(_P, fn): bad(f"_prep_common.{fn} missing (Windows-safe publishing)")
    for name in ("final_panel_is_valid", "panel_file_report"):
        src = _i.getsource(getattr(_P, name))
        if "pq.ParquetFile(" in src and "close()" not in src and "pq_meta(" not in src:
            bad(f"{name} opens a ParquetFile without closing it -- this blocks publishing on Windows")
    if "publish_atomic(" not in _i.getsource(_P.run_pass_b):
        bad("run_pass_b does not use publish_atomic (no retry/gc on a locked destination)")
    else:
        note("panel is published with gc + retry and a recovery path (finalize_pending_panel)")
    note("metadata reads go through pq_meta(), which always closes the file")

def check_missing_value_policy():
    """v20.12: estimators must exclude non-finite rows, refuse degenerate fits, and every model must expose the
    seasons switch; dedup must not loop in Python over groups; build_manifest must define its reader."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P
    src = _i.getsource(_C.estimate_twfe_did)
    if "_finite_rows(" not in src: bad("estimate_twfe_did does not exclude missing outcome/covariate rows (NaN betas)")
    if "exactly zero" not in src: bad("estimate_twfe_did does not refuse a beta=0/se=0 degenerate fit")
    if "_finite_rows(" in src and "exactly zero" in src: note("2x2 estimator excludes missing rows and refuses degenerate fits")
    if "_finite_rows(" not in _i.getsource(_C.estimate_twfe_did_streaming):
        bad("the streaming estimator does not apply the missing-value policy")
    for fn in ("outcome_coverage", "season_rows"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing")
    dd = _i.getsource(_P.resolve_duplicates)
    if "for key, group in" in dd: bad("resolve_duplicates loops in Python over duplicate groups (hours on large blocks)")
    else: note("resolve_duplicates is vectorised")
    bm = _i.getsource(_P.build_manifest)
    if "pf = pq.ParquetFile(" not in bm: bad("build_manifest uses `pf` without defining it (NameError in v20.11)")
    else: note("build_manifest defines and closes its Parquet reader")
    nbs = glob.glob(os.path.join(HERE, "0[2-5]*", "M*.ipynb"))
    missing = [os.path.basename(nb) for nb in nbs if "seasons=SEASONS" not in
               "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")]
    if missing: bad(f"model notebooks without the seasons switch: {missing[:5]}")
    else: note(f"{len(nbs)} model notebooks expose SEASONS (seasonal / yearly / all)")

def check_universal_missing_policy():
    """v20.13: the missing-value policy lives in load_panel (every model passes through it), the event study
    has a solver fallback, a NaN GPU drift is a failure, and the CS aggregate skips unidentified cells."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C
    lp = _i.getsource(_C.load_panel)
    if "finite_only" not in lp or "_n_missing_dropped" not in lp:
        bad("load_panel does not exclude rows with a missing outcome/covariate -- NaN estimates would return")
    else:
        note("load_panel enforces the missing-value policy for every model")
    if "CURRENT_ESTIMATION_COLUMNS.update" not in _i.getsource(_C.columns_for):
        bad("columns_for no longer records the estimation columns (the load-time policy would be inert)")
    es = _i.getsource(_C.estimate_event_study)
    if "except np.linalg.LinAlgError" not in es: bad("event study can still die with 'SVD did not converge'")
    if "_finite_rows(" not in es: bad("event study does not exclude missing rows")
    if "except np.linalg.LinAlgError" in es and "_finite_rows(" in es: note("event study excludes missing rows and has a solver fallback")
    if "n_cells_identified" not in _i.getsource(_C.callaway_santanna_att):
        bad("Callaway-Sant'Anna aggregate averages NaN cells (blank event-time table)")
    else:
        note("Callaway-Sant'Anna aggregates only identified (g,t) cells")
    cc = _i.getsource(_C._gpu_crosscheck)
    if "np.isfinite(drift)" not in cc: bad("GPU cross-check treats a NaN drift as a pass")
    else: note("a NaN GPU drift is reported as a failure, not a pass")

def check_ingestion_and_paths():
    """v20.14: any format / any name ingestion, and one INPUT_DIR for both engines (no recursion)."""
    import inspect as _i, tempfile as _tf
    sys.path.insert(0, HERE)
    import _prep_common as _P, _common as _C
    for fn in ("discover_input_files", "_read_delimited", "_read_excel_export", "_read_parquet_export", "_read_feather_export"):
        if not hasattr(_P, fn): bad(f"_prep_common.{fn} missing (ingestion layer incomplete)")
    if "discover_input_files(" not in _i.getsource(_P.run_pass_a): bad("run_pass_a does not use discover_input_files")
    exts = set(getattr(_P, "INPUT_EXTENSIONS", ()))
    if not {".csv", ".csv.gz", ".tsv", ".parquet", ".xlsx", ".xls", ".xlsm", ".feather"} <= exts:
        bad(f"INPUT_EXTENSIONS incomplete: {sorted(exts)}")
    else: note("PASS A ingests csv / csv.gz / tsv / parquet / feather / xlsx / xlsm / xls")
    loose = _P.parse_filename("Artal 2022 rabi export (final v3).xlsx")
    if not loose or loose.get("Year") != 2022 or loose.get("Season") != 2: bad("loose file-name parsing is broken")
    if _P.parse_filename("export_no_key_in_name.csv") is not None: bad("a keyless name should return None (column fallback)")
    if "cannot determine {key}" not in _i.getsource(_P.load_and_harmonize): bad("load_and_harmonize lost the column fallback for Year/Season")
    else: note("file names parsed loosely; Year/Season fall back to the columns inside the file")
    if not os.path.exists(os.path.join(HERE, "_paths.py")): bad("_paths.py missing (single INPUT_DIR)")
    d = _tf.mkdtemp(); inp = os.path.join(d, "IN"); os.makedirs(inp)
    try:
        _P.set_paths(inp, verbose=False)                      # would recurse forever before v20.14b
        if _C.PREPARED_PANEL != _P.FINAL_PANEL or not _P.OUTPUT_DIR.startswith(inp):
            bad("set_paths does not put both engines on the same derived layout")
        else: note("one INPUT_DIR drives both engines: output/temp/panel/results derive from it")
    finally:
        try:
            import _paths as _PP; _P._apply_paths(_PP.derive())
        except Exception: pass
    for nb in glob.glob(os.path.join(HERE, "01_Panel_Preparation", "P0[0-2]*.ipynb")):
        src = "\n".join("".join(c["source"]) for c in json.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
        if 'glob.glob(os.path.join(P.INPUT_DIR,"**","*.csv")' in src: bad(f"{os.path.basename(nb)} still globs *.csv only")

def check_path_import_orders():
    """v20.14: a session override must survive importing the other engine, in either order, and the two engines
    must always agree. (The half-built version recursed forever, then silently reset a configured engine.)"""
    import subprocess as _sp, sys as _s
    code = r'''
import sys, os, tempfile; sys.path.insert(0, %r)
d = tempfile.mkdtemp(); a = os.path.join(d, "A"); os.makedirs(a)
import _prep_common as P; P.set_paths(a, verbose=False); import _common as C
r1 = C.PREPARED_PANEL == P.FINAL_PANEL and P.OUTPUT_DIR.startswith(a)
for m in ("_common", "_prep_common"): sys.modules.pop(m, None)
b = os.path.join(d, "B"); import _common as C2; C2.set_paths(b, verbose=False); import _prep_common as P2
r2 = P2.FINAL_PANEL == C2.PREPARED_PANEL and C2.RESULTS_ROOT.startswith(b)
print("OK" if (r1 and r2) else f"BAD {r1} {r2}")
''' % HERE
    try:
        out = _sp.run([_s.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=HERE,
                      env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "")})
        last = [l for l in out.stdout.splitlines() if l.strip()][-1] if out.stdout.strip() else out.stderr[-200:]
        if last.strip() == "OK": note("path layout survives either import order and both engines agree")
        else: bad(f"path layout is lost or split across engines depending on import order: {last[:160]}")
    except Exception as e:
        bad(f"import-order check could not run: {e}")

def check_demeaner_and_event_study():
    """v20.15: compact FE codes (no 0/0), GPU cross-check on identical input, event-study identification notes."""
    import inspect as _i, warnings as _w
    sys.path.insert(0, HERE)
    import _common as _C, numpy as _np, pandas as _pd
    _cat = _pd.Categorical(["a", "b", "c", "d"] * 5)[[i for i in range(20) if i % 4 != 2]]   # category 'c' now unused
    _cd = _C._codes(_cat)
    if int(_cd.max()) + 1 != len(set(_cd[_cd >= 0])) or int(_cd.max()) + 1 != 3:
        bad("_codes() leaves empty groups for a filtered categorical (divide warnings, GPU/CPU mismatch)")
    else: note("fixed-effect codes are contiguous on the rows given (no empty groups)")
    cc = _i.getsource(_C._gpu_crosscheck)
    if "_demean_gpu(T, y_sub" not in cc or "_demean_cpu(y_sub" not in cc:
        bad("GPU cross-check does not compare both implementations on the same input")
    else: note("GPU cross-check demeans the same rows on CPU and GPU and compares")
    es = _i.getsource(_C.estimate_event_study)
    for k in ("n_treated_pixels_also_in_ref", "identification_note", "not the same pixels across periods"):
        if k not in es: bad(f"event study lacks the identification diagnostic '{k}'")
    if all(k in es for k in ("n_treated_pixels_also_in_ref", "identification_note")):
        note("event study reports which treated pixels identify each coefficient")
    if not hasattr(_C, "common_pixel_mask"): bad("common_pixel_mask missing (balanced-footprint option)")
    rng = _np.random.default_rng(0); n = 20000
    pix = _pd.Categorical(rng.integers(0, 3000, n)); per = _pd.Categorical(rng.integers(0, 12, n)); y = rng.normal(size=n)
    keep = rng.random(n) < 0.3
    with _w.catch_warnings():
        _w.simplefilter("error")
        try:
            r = _C._demean_cpu(y[keep], [pix[keep], per[keep]], 1e-10, 200)
            ref = _C._demean_cpu_pandas(y[keep], [_np.asarray(pix)[keep], _np.asarray(per)[keep]], 1e-10, 200)
            if _np.max(_np.abs(r - ref)) > 1e-9: bad("CPU demeaner differs from the pandas reference on filtered categoricals")
            else: note("CPU demeaner on filtered categoricals: no warnings, matches the pandas reference")
        except Warning as w:
            bad(f"CPU demeaner raised a warning on filtered categoricals: {w}")

def check_zero_policy_and_readiness():
    """v20.16: NaN AND exact-zero cells are missing in preparation and in every model; readiness tool present."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _prep_common as _P, _common as _C
    if not hasattr(_P, "apply_missing_policy"): bad("_prep_common.apply_missing_policy missing")
    else:
        for fn in ("_pa_worker", "prepare_pass_b_block"):
            if "apply_missing_policy(" not in _i.getsource(getattr(_P, fn)): bad(f"{fn} does not apply the NaN/zero policy")
        note("PASS A and PASS B set NaN/zero cells to missing before dedup and drop rows without an outcome")
    if not hasattr(_C, "_usable") or "!= 0" not in _i.getsource(_C._usable): bad("_common._usable does not treat exact zeros as missing")
    if "_usable(" not in _i.getsource(_C._finite_rows): bad("estimators do not use the zero rule")
    if "_n_zero_dropped" not in _i.getsource(_C.load_panel): bad("load_panel does not apply/report the zero rule")
    if "policy_cols" not in _i.getsource(_C.estimate_twfe_did_streaming): bad("streaming estimator does not filter on the same policy columns as load_panel")
    else: note("every model excludes NaN and zero cells at load, and the streaming path uses the same sample")
    if not os.path.exists(os.path.join(HERE, "readiness.py")) or not hasattr(_C, "model_readiness"): bad("readiness tool missing")
    else: note("readiness.py / C.model_readiness() present")

def check_missingness_report():
    """v20.17: PASS B writes panel_missingness_report.csv and refuses a block where a zero survived the policy."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _prep_common as _P
    src = _i.getsource(_P.run_pass_b)
    if "panel_missingness_report.csv" not in src: bad("PASS B does not write panel_missingness_report.csv")
    if "survived the missing-value" not in src: bad("PASS B does not assert that no exact zero survives the policy")
    if "panel_missingness_report.csv" in src and "survived the missing-value" in src:
        note("PASS B reports missingness per block x variable and refuses a panel with a surviving zero")
    if "rows_dropped_zero" not in _i.getsource(__import__("_common").load_panel):
        bad("load_panel does not report rows dropped for exact zeros")
    else: note("load_panel reports rows dropped for NaN and for exact zeros separately")

def check_honest_and_group_missingness():
    """v20.18: HonestDiD states base significance; SEs never NaN through cancellation; missingness by group."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P
    src = open(os.path.join(HERE, "_common.py"), encoding="utf-8").read()
    if "invalid value encountered in sqrt" in src and "_neg = _dg < 0" not in src: bad("event-study SE can still go NaN in sqrt")
    if "_neg = _dg < 0" not in src: bad("event-study SE has no cancellation guard")
    else: note("event-study SEs: negative-through-cancellation diagonals are clipped and flagged, never NaN")
    hd = _i.getsource(_C.honest_did_relative_magnitudes)
    if "NOT SIGNIFICANT at M=0" not in hd: bad("HonestDiD does not distinguish 'no finding' from 'fragile'")
    else: note("HonestDiD verdict distinguishes not-significant-at-M0 from fragile from robust")
    if "finite_core" not in _i.getsource(_P.prepare_pass_b_block): bad("PASS B missingness is not split by treated core vs rings")
    else: note("PASS B measures no-data by treated core vs control rings and warns when the core is the masked side")

def check_pretrends_spec():
    """v20.19: the joint pre-trends test must anchor on the reference period and never call solve() on a
    possibly singular cluster-robust covariance."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C
    src = _i.getsource(_C.pretrends_joint_ftest)
    if "np.linalg.solve(vcov" in src: bad("pre-trends test inverts the covariance with solve() -- singular with few clusters / absorbed leads")
    if "max(hi, ref_period)" not in src: bad("pre-trends test sample excludes the reference period (exactly collinear leads)")
    if "matrix_rank(vcov" not in src: bad("pre-trends test does not cap the restrictions at the covariance rank")
    if all(k in src for k in ("max(hi, ref_period)", "matrix_rank(vcov")) and "np.linalg.solve(vcov" not in src:
        note("pre-trends F test: reference period anchored, absorbed leads dropped, rank-capped pseudo-inverse")

def check_no_placeholders():
    """v20.20: result files hold estimates only -- save_results refuses NaN-only estimates and placeholder tokens."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C
    src = _i.getsource(_C.save_results)
    if 'or "EMPTY_RESULT"' in src or '"status": "EMPTY_RESULT"' in src: bad("save_results still writes EMPTY_RESULT placeholder rows")
    if "_placeholder_cells(" not in src or "record_not_estimated(" not in src:
        bad("save_results does not refuse placeholders / record NOT_ESTIMATED")
    else: note("save_results refuses NaN-only estimates and placeholder tokens; refusals go to NOT_ESTIMATED.csv")
    import pandas as _pd, tempfile as _tf
    d = _tf.mkdtemp()
    for row, label in (({"outcome": "X", "beta": float("nan"), "se": float("nan")}, "NaN-only"),
                       ({"outcome": "X", "beta": 0.01, "se": 0.002, "note": "TBD"}, "placeholder token")):
        try:
            _C.LAST_FIT_INFO.clear(); _C.save_results(row, d, "t.csv"); bad(f"save_results wrote a {label} result")
        except _C.InsufficientDataError:
            pass
    if os.path.exists(os.path.join(d, "t.csv")): bad("a refused result file was still written")
    else: note("a NaN-only or placeholder result is refused and never written")

def check_frozen_guard():
    """v20.21: frozen-series detector and guards present in the three core estimators."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C
    for fn in ("within_pixel_variation", "_frozen_treated_guard"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing (frozen-series detection)")
    n = sum("_frozen_treated_guard(" in _i.getsource(getattr(_C, f)) for f in ("estimate_twfe_did", "estimate_event_study", "pretrends_joint_ftest"))
    if n < 3: bad(f"frozen-series guard present in only {n}/3 core estimators")
    else: note("frozen-series guard in the 2x2, the event study and the pre-trends test; P06 runs the detector")

def check_yearly_first():
    """v20.24: annual composite first -- per-outcome resolution, covariate fill, notebooks default to auto, old
    scenario files upgraded, guard works on annual windows, P00 reports the choice, M07/M08 paths derived."""
    import inspect as _i, json as _j, tempfile as _tf, re as _re
    sys.path.insert(0, HERE)
    import _common as _C
    for fn in ("seasons_mode", "yearly_outcome_available", "yearly_covariate_table", "fill_yearly_covariates", "season_choice_report"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing (yearly-first)")
    if _C.ACTIVE.get("seasons") != "all": bad(f"engine default seasons is {_C.ACTIVE.get('seasons')!r}, not 'all' (v20.29: all years and seasons)")
    if "outcome" not in str(_i.signature(_C.seasons_mode)): bad("seasons_mode does not resolve per outcome")
    if "fill_yearly_covariates(" not in _i.getsource(_C.load_panel): bad("load_panel does not fill annual-row covariates")
    if "fill_yearly_covariates(" not in _i.getsource(_C.estimate_twfe_did_streaming): bad("streaming estimator does not fill annual-row covariates")
    _fz = _i.getsource(_C._frozen_treated_guard) + (_i.getsource(_C._frozen_partial) if hasattr(_C, "_frozen_partial") else "")   # v20.58: partial + final
    if 's["count"] >= 2' not in _fz or ("_frozen_partial(" not in _i.getsource(_C._frozen_treated_guard) and hasattr(_C, "_frozen_partial")):
        bad("frozen-series guard still needs >= 3 rows (silent on annual windows)")
    else: note("yearly-first: per-outcome resolution, annual covariate fill in both estimators, guard works on annual windows")
    bad_nb = []
    for nb in glob.glob(os.path.join(HERE, "0*", "*.ipynb")):
        src = open(nb, encoding="utf-8").read()
        if _re.search(r'SEASONS\s*=\s*\\?"seasonal', src): bad_nb.append(os.path.basename(nb))
    if bad_nb: bad(f"notebooks still default SEASONS to seasonal: {bad_nb[:4]}")
    else: note("every notebook defaults SEASONS to 'auto' (annual composite first)")
    d = _tf.mkdtemp(); f = os.path.join(d, "did_scenario.json")
    _j.dump({"control_zones": [1, 2, 3, 4, 5], "treatment_year": 2023, "post_cutoff": 2023, "seasons": "seasonal"}, open(f, "w"))
    saved = _C.ACTIVE.get("seasons"); _C.load_scenario(path=f, verbose=False)
    if _C.ACTIVE.get("seasons") != saved: bad("a scenario file written before v20.29 overrides the all-years-and-seasons policy")
    _C.ACTIVE["seasons"] = saved
    p00 = open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8").read()
    if "season_choice_report" not in p00: bad("P00 does not report which rows the models will use")
    import _paths as _PP
    dv = _PP.derive(input_dir=d)
    if not dv.get("GROUND_TRUTH_OUTCOMES_PATH", "").startswith(d) or not dv.get("ROLLOUT_INSTRUMENT_PATH", "").startswith(d):
        bad("M07 / M08 input paths do not follow INPUT_DIR")
    else: note("M07 ground-truth and M08 instrument paths follow INPUT_DIR; P00 STEP 8 reports the season choice")
    if getattr(_C, "GROUND_LINK_SEASON", 1) is not None: bad("P08 enumerates pixels from one season only (GROUND_LINK_SEASON)")

def check_near_duplicate_pixels():
    """v20.25: >= 80 % overlapping pixels are one pixel; priority selectable; stale per-variable files unusable;
    a panel built without the merge is rebuilt."""
    import inspect as _i, numpy as _np, pandas as _pd, time as _t, tempfile as _tf
    sys.path.insert(0, HERE)
    import _prep_common as _P, _common as _C
    for fn in ("pixel_registry", "near_duplicate_pairs", "canonical_pixel_map", "build_pixel_overlap_map", "apply_pixel_map"):
        if not hasattr(_P, fn): bad(f"_prep_common.{fn} missing (near-duplicate pixels)")
    if "apply_pixel_map(" not in _i.getsource(_P.prepare_pass_b_block): bad("PASS B does not apply the pixel overlap map")
    if "build_pixel_overlap_map(" not in _i.getsource(_P.run_pass_b): bad("PASS B does not build the pixel overlap map")
    if 'DEDUP_PRIORITY == "complete"' not in _i.getsource(_P.resolve_duplicates): bad("duplicate resolution has no completeness-first option")
    lat0 = 16.44; mlat = 1 / 110574.0; mlon = 1 / (111320.0 * _np.cos(_np.radians(lat0)))
    def _reg(pts):
        r = _pd.DataFrame([{"pixel_id": p, "lat": lat0 + n_ * mlat, "lon": 75.17 + e * mlon, "mtime": t_, "n_rows": 10, "n_ok": int(10 * c_), "src": "x"}
                           for p, e, n_, t_, c_ in pts]).set_index("pixel_id"); r["completeness"] = r.n_ok / r.n_rows; return r
    def _map(pts, pr="newer"):
        r = _reg(pts); m = _P.canonical_pixel_map(r, _P.near_duplicate_pairs(r, 10.0, 0.80), pr); return dict(zip(m.pixel_id, m.canonical_pixel_id))
    cases = [(_map([(1, 0, 0, 1, 1), (2, 1.0, 0.6, 2, 1)]), {1: 2}, "1.0/0.6 m offset merges onto the newer pixel"),
             (_map([(1, 0, 0, 1, 1), (2, 3.0, 0, 2, 1)]), {}, "3 m offset (70 %) stays two pixels"),
             (_map([(1, 0, 0, 3, 1), (2, 1.5, 0, 2, 1), (3, 3.0, 0, 1, 1)]), {2: 1}, "no chaining"),
             (_map([(1, 0, 0, 1, 1.0), (2, 1.0, 0.5, 2, 0.4)], "complete"), {2: 1}, "completeness priority"),
             (_map([(k, (k % 5) * 10.0, (k // 5) * 10.0, 1, 1) for k in range(25)]), {}, "a regular 10 m grid never merges")]
    wrong = [label for got, want, label in cases if got != want]
    if wrong: bad(f"near-duplicate pixel rules broken: {wrong}")
    else: note("pixels overlapping >= 80 % are one pixel (newer or more complete wins); 3 m apart stay apart; no chaining")
    d = _tf.mkdtemp(); ef = os.path.join(d, "ef.parquet"); pn = os.path.join(d, "panel.parquet")
    open(ef, "w").write("x"); _t.sleep(1.2); open(pn, "w").write("y")
    if _C.estimator_file_is_fresh(ef, pn): bad("a per-variable file older than the panel is still treated as usable")
    else: note("per-variable files older than the panel are never read (P09 rebuilds them)")
    if "ACCEPT_PANEL_WITHOUT_PIXEL_MERGE" not in _i.getsource(_P.final_panel_is_valid):
        bad("a panel built without the near-duplicate merge would be reused silently")

def check_treatment_timing():
    """v20.26: works started 2022 (month unknown) -> 2022 is a transition year: out of the sample, pre < 2022,
    post >= 2023, in both engines, the streaming estimator and every notebook; old scenario files cannot pin the old split."""
    import numpy as _np, pandas as _pd, re as _re
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P
    import subprocess as _sp
    code = ("import sys; sys.path.insert(0, %r); import _common as C, _prep_common as P; "
            "a = C.ACTIVE; print(a['treatment_year'], a['post_cutoff'], a['exclude_transition_year'], P.TREATMENT_YEAR, P.POST_CUTOFF, P.EXCLUDE_TRANSITION_YEAR)") % HERE
    out = _sp.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env={**os.environ})
    last = [l for l in out.stdout.splitlines() if l.strip()][-1] if out.stdout.strip() else ""
    if last.split() != ["2022", "2022", "False", "2022", "2022", "False"]:
        bad(f"a fresh engine does not default to treatment year 2022 with post = Year >= 2022: {last or out.stderr[-200:]}")
    else:
        note("a fresh engine defaults to treatment year 2022: pre = Year < 2022, post = Year >= 2022 (both engines)")
    def _sim(seed):
        rng = _np.random.default_rng(seed); rows = []
        for p in range(300):
            b = 0 if p % 5 == 0 else p % 5; a = rng.normal(0, .05)
            for y in range(2016, 2026):
                eff = 0.05 if (b == 0 and y >= 2023) else (0.025 if (b == 0 and y == 2022) else 0.0)   # works start mid-2022
                rows.append((p, y, 0, b, "SW" + str(p % 6), 0.4 + a + eff + rng.normal(0, .01)))
        df_ = _pd.DataFrame(rows, columns=["pixel_id", "Year", "Season", "buff_km", "subwshed_id", "NDVI"]); df_["time_fe_yearseason"] = df_.Year.astype(str)
        return df_
    saved = dict(_C.ACTIVE)
    try:
        _C.set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, exclude_transition_year=True,
                        seasons="all", cohort_offset=0, use_site_years=False, cluster="subwshed", pooled_fe="period")
        bs = []; bad_bounds = False
        for seed in range(6):
            d = _C.build_treatment_columns(_sim(seed)); s = d[d.in_analysis_sample == 1]
            if (s.Year == 2022).any() or int(s.loc[s.post == 1, "Year"].min()) != 2023 or int(s.loc[s.pre == 1, "Year"].max()) != 2021:
                bad_bounds = True
            bs.append(_C.estimate_twfe_did(s, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id")[0])
        b = float(_np.mean(bs))
        if bad_bounds: bad("transition year not handled when switched on: 2022 still in the sample, or pre/post boundaries wrong")
        elif abs(b - 0.05) > 0.002: bad(f"transition-year design is biased: mean over 6 seeds {b:+.4f} vs +0.0500")
        else: note(f"robustness mode (2022 held out) still exact: pre 2015-2021 vs post 2023+; mean over 6 seeds {b:+.4f}")
        _C.set_scenario(verbose=False, exclude_transition_year=False)
        d = _C.build_treatment_columns(_sim(0))
        if not ((d.post == (d.Year >= 2022).astype(int)).all() and (d.pre == (d.Year < 2022).astype(int)).all()
                and (d.loc[d.Year == 2022, "in_analysis_sample"] == 1).any()):
            bad("default timing does not give pre = Year < 2022 and post = Year >= 2022 with 2022 in the sample")
    finally:
        _C.ACTIVE.clear(); _C.ACTIVE.update(saved)
    old = [os.path.basename(nb) for nb in glob.glob(os.path.join(HERE, "0*", "*.ipynb")) if _re.search(r"TREATMENT_YEAR\s*=\s*2023", open(nb, encoding="utf-8").read())]
    if old: bad(f"notebooks still set TREATMENT_YEAR = 2023: {old[:4]}")
    if "_trans_lo" not in open(os.path.join(HERE, "_common.py"), encoding="utf-8").read(): bad("streaming estimator ignores the transition year")
    if 'm.get("timing_policy") != "v20.27"' not in open(os.path.join(HERE, "_common.py"), encoding="utf-8").read():
        bad("an old scenario file could pin the pre-2022 timing")

def check_panel_design_rules():
    """v20.27: buffers recoded exactly; the export's Treat checked as a PERIOD flag; PASS B refuses a panel whose
    treatment/control/pre/post/did columns break the rules."""
    import inspect as _i, numpy as _np
    sys.path.insert(0, HERE)
    import _prep_common as _P
    vals = [0, 1.0, 2.0000001, "3", " 4 ", "5 km", "Buffer_1", "ring-2", 6, -1, "-1", 1.4, None, "core"]
    rec, _ = _P.recode_buff_km(vals)
    want = [0, 1, 2, 3, 4, 5, 1, 2, -1, -1, -1, -1, -1, -1]
    if list(map(int, rec)) != want: bad(f"buffer recode wrong: {list(map(int, rec))} vs {want}")
    else: note("buffer codes recoded exactly (0 / 1.0 / 2.0000001 / '5 km' / 'Buffer_1' -> 0..5; 6, 1.4, text without a number -> neither)")
    qc = _i.getsource(_P.data_qc)
    if "treat_period_mismatch_flag" not in qc or "== TREAT_CORE_BUFFKM).astype(\"int8\")\n    df[\"treat_buffkm" in qc:
        bad("the export's Treat is still compared with the treatment AREA instead of the period rule")
    lh = _i.getsource(_P.load_and_harmonize)
    if "recode_buff_km(" not in lh or lh.index("recode_buff_km(") > lh.index("for c in ESSENTIAL_COLS + OUTCOME_VARS"):
        bad("buffer codes are cast to numbers before being recoded (text codes like '1 km' would be lost)")
    if 'df["Treat"] = (pd.to_numeric(df["Year"]' not in lh: bad("an export without a Treat column would be rejected instead of derived from the rule")
    pb = _i.getsource(_P.prepare_pass_b_block)
    if "treatment_not_buffer0" not in pb or "did_not_treatment_x_post" not in pb: bad("PASS B has no design check")
    if "panel_design_check.csv" not in _i.getsource(_P.run_pass_b): bad("PASS B does not write panel_design_check.csv")
    else: note("PASS B checks every row (buffer 0 treatment, 1-5 control, pre < 2022, post >= 2022, did = treatment x post)")

def check_sws_geometry():
    """v20.28: the 20-SWS shapefile locates every pixel -- projection, point-in-polygon, names, PASS A order."""
    import inspect as _i, numpy as _np
    sys.path.insert(0, HERE)
    import _sws_geometry as _G, _prep_common as _P
    try:
        L = _G.SWSLocator.from_shapefile()
    except Exception as e:
        bad(f"the 20-SWS shapefile cannot be read: {e}"); return
    if len(L.sites) != 20 or len(L.polys) != 120 or L.prj.get("kind") != "utm": bad(f"shapefile structure unexpected: {len(L.sites)} sites, {len(L.polys)} polygons, {L.prj}")
    la = _np.linspace(11.5, 18.5, 15); lo = _np.linspace(74.0, 78.5, 15); la, lo = [a.ravel() for a in _np.meshgrid(la, lo)]
    x, y = _G.latlon_to_tm(la, lo); la2, lo2 = _G.tm_to_latlon(x, y)
    if max(_np.abs(la2 - la).max(), _np.abs(lo2 - lo).max()) > 1e-9 or abs(_G.latlon_to_tm(16.0, 75.0)[0] - 500000.0) > 1e-6:
        bad("UTM projection round trip / central meridian wrong")
    try:
        from matplotlib.path import Path as _MP
        rng = _np.random.default_rng(3); parts, bb = _G.read_shp_polygons(os.path.join(HERE, "data", "sites", "SWSs20_KarnatakaAll5k.shp"))[17]
        px = rng.uniform(bb[0], bb[2], 20000); py = rng.uniform(bb[1], bb[3], 20000)
        ref = _np.zeros(len(px), bool)
        for pt in parts: ref ^= _MP(pt).contains_points(_np.column_stack([px, py]))
        if (_G.PolygonIndex(parts).contains(px, py) != ref).any(): bad("point-in-polygon disagrees with matplotlib on a multi-part polygon")
        else: note("SWS geometry: UTM 43N projection exact, point-in-polygon identical to matplotlib on a 170-part polygon")
    except ImportError:
        note("SWS geometry: projection exact (matplotlib absent -- point-in-polygon cross-check skipped)")
    if L.site_id_for_name("Chhatrakodihalli sub-watershed") != 3 or L.site_id_for_name("Kodihalli") != 12 or L.site_id_for_name("Nilgunda") != 18:
        bad("SWS name matching is wrong (longest name must win)")
    m = _P.harmonize_columns(["Year", "Season", "SubwshedID", "SUBWSHED", "Treat", "latitude", "longitude", "buff_km"], fname="x", unresolved_log=[])
    if m.get("SUBWSHED") != "SWS_Name": bad("a SUBWSHED name column would be read as the numeric SubwshedID")
    wk = _i.getsource(_P._pa_worker)
    if "tag_sites(" not in wk or wk.index("tag_sites(") > wk.index("resolve_duplicates("): bad("PASS A de-duplicates before the SWS is known")
    for k in ("sws_name", "site_check"):
        if k not in _P.FINAL_PANEL_SCHEMA: bad(f"panel schema lacks {k}")
    for rel in ("_sws_geometry.py", "01_Panel_Preparation/P00_RUN_ALL_Panel_Preparation.ipynb"):
        if not os.path.exists(os.path.join(HERE, rel)): bad(f"missing {rel}")
    note("SWS tags: SUBWSHED read as a name, longest-name match, tagged before de-duplication, sws_name + site_check in the panel")

def check_v20_29():
    """v20.29: P09 writer, notebook import order, all years + seasons with pixel x season FE, covariate choice,
    fund-release calendar, R timing + unit, pre-built package routing."""
    import inspect as _i, numpy as _np, pandas as _pd, re as _re, json as _j
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P
    src = _i.getsource(_C.build_estimator_files)
    if 'astype("int16")' in src.split("first_treat_agri_year")[1][:300] if "first_treat_agri_year" in src else True:
        bad("P09 still decides first_treat_agri_year's type per chunk (the schema-mismatch failure)")
    if "tbl.select(writer.schema.names).cast(writer.schema)" not in src: bad("P09 writer does not cast every chunk to the file's schema")
    else: note("P09 writer: one fixed type for first_treat_agri_year, every chunk cast to the file's schema")
    late = []
    for nb in glob.glob(os.path.join(HERE, "0*", "*.ipynb")):
        d = _j.load(open(nb, encoding="utf-8")); code = "\n".join("".join(c["source"]) for c in d["cells"] if c["cell_type"] == "code")
        for name, pat in (("C", r"(import _common as C\b|\bC\s*=\s*[\w\.]*import_module\([\"']_common)"), ("P", r"(import _prep_common as P\b|\bP\s*=\s*[\w\.]*import_module\([\"']_prep_common)")):
            u = _re.search(r"(?<![\w\.])" + name + r"\.[A-Za-z_]", code)
            if u and not (_re.search(pat, code[:u.start()]) or _re.search(r'if "' + name + r'" not in globals', code[:u.start()])):
                late.append(f"{os.path.basename(nb)}:{name}")
    if late: bad(f"notebooks use the engine before importing it: {late[:5]}")
    else: note("every notebook imports C / P before first use (validate_notebooks_cold.py runs them from their own folders)")
    if not os.path.exists(os.path.join(HERE, "validate_notebooks_cold.py")): bad("cold-start notebook gate missing")
    if _C.ACTIVE.get("unit_fe") != "pixel_season": bad("default unit fixed effect is not pixel x season")
    rng = _np.random.default_rng(1); rows = []
    for u in range(120):
        b = 0 if u < 60 else 5; fe = rng.normal(0, 1)
        for yr in (2019, 2020, 2021, 2022, 2023):
            for sc in (0, 1, 2):
                rows.append({"pixel_id": f"P{u}", "Year": yr, "Season": sc, "buff_km": b, "time_fe_yearseason": f"{yr}_{sc}",
                             "subwshed_id": f"S{u % 6}", "y": fe + 0.2 * sc + 0.1 * (yr - 2019) + (0.5 if (b == 0 and yr >= 2022) else 0) + rng.normal(0, .05)})
    saved = dict(_C.ACTIVE); covs0 = list(_C.DEFAULT_COVARIATES)
    try:
        _C.set_scenario(verbose=False, all_years=True, treatment_year=2022, exclude_transition_year=False, seasons="all", unit_fe="pixel_season", covariates=[])
        dd = _C.build_treatment_columns(_pd.DataFrame(rows)); dd = dd[dd.in_analysis_sample == 1]
        b_, _ = _C.estimate_twfe_did(dd, "y", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id")
        if dd.unit_id.nunique() != 360 or abs(b_ - 0.5) > 0.03: bad(f"pixel x season units wrong: {dd.unit_id.nunique()} units, beta {b_:.3f}")
        else: note(f"all years + seasons with pixel x season and year x season FE: 360 units from text ids, beta {b_:.3f} (true 0.5)")
        ref = _C.DEFAULT_COVARIATES; _C.set_scenario(verbose=False, covariates=["Rain"])
        if ref is not _C.DEFAULT_COVARIATES or list(ref) != ["Rain"] or "covRain" not in _C.scenario_tag(): bad("covariate choice does not reach the shared list / result folder")
        try:
            _C.set_scenario(verbose=False, covariates=["NDVI"]); bad("an outcome was accepted as a covariate")
        except _C.InsufficientDataError:
            note("covariate choice: one shared list, own result folder, outcomes refused as covariates")
    finally:
        _C.ACTIVE.clear(); _C.ACTIVE.update(saved); _C.DEFAULT_COVARIATES[:] = covs0
    for d_, exp in (("2021-11-15", (2022, 3)), ("2022-04-10", (2022, 1)), ("2022-06-15", (2022, 2)), ("2023-01-20", (2023, 3))):
        if _P.next_season_after(_pd.Timestamp(d_)) != exp: bad(f"fund-release season rule wrong for {d_}: {_P.next_season_after(_pd.Timestamp(d_))} vs {exp}"); break
    else: note("fund-release -> next season follows the export calendar (never a past or year-late season)")
    _rlib = os.path.dirname(_C.r_bridge_script())                                   # v20.45: the R pipeline's library
    r = open(os.path.join(_rlib, "reward_prep.R"), encoding="utf-8").read()
    rall = "".join(open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(_rlib, "*.R")))
    # v20.57: the timing columns are built by the MODEL stage (reward_design.R design_columns), from each row's own cohort
    if ("post := as.integer(Year >= cohort_row)" not in rall or 'paste(pixel_id, Season, sep = "_")' not in rall
            or "pixel_id + period" in rall or "| unit + period" not in rall): bad("R side disagrees with Python (timing or unit fixed effect)")
    else: note("R engine and R pipelines: post = Year >= each row's cohort (the timing in force) and the same pixel x season unit as Python")
    if "unit" not in _C.PACKAGE_INPUT_COLUMNS: bad("package input lacks the unit fixed effect")
    for fn in ("verify_prebuilt_routes", "prebuilt_status", "_use_prebuilt", "_route_call"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing (pre-built packages)")
    if "verify_prebuilt_routes" not in open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8").read(): bad("P12 (package verification) is not in P00")
    st = _C.prebuilt_status(verbose=False)
    if not set(st.estimator) >= {"twfe", "event_study", "wild_bootstrap", "callaway_santanna"}: bad("pre-built routes incomplete")
    else: note("pre-built packages: used only once P12 verified them on this machine; engine otherwise, labelled per result")
    v00 = open(os.path.join(HERE, "06_Validation", "V00_RUN_ALL_VALIDATIONS.py"), encoding="utf-8").read()
    if 'D="DIDRDP_ALLRunDID_FINAL"' in v00: bad("V00 still hard-codes an old folder name")

def check_v20_30_gpu_and_barrier():
    """v20.30: every GPU demeaning verified on ALL rows (CPU result on rejection); no-data never floored to a fake 0;
    the barrier rebuilds the panel; tests never write into the bundle."""
    import inspect as _i, numpy as _np
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P
    for fn in ("_gpu_verify", "_fe_group_mean_max"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing (full-data GPU verification)")
    for disp in (_C.demean_multi_way, _C.demean_columns):
        if "_gpu_verify(" not in _i.getsource(disp): bad(f"{disp.__name__} returns GPU results without verifying them on all rows")
    rng = _np.random.default_rng(0); n = 40000
    u = rng.integers(0, 3000, n); p = rng.integers(0, 40, n); Y = _np.column_stack([rng.normal(0.4, .1, n), rng.normal(500, 50, n)])
    good = _C._demean_cpu_matrix(Y, [u, p], 1e-10, 200)
    saved = (_C.USE_GPU, dict(_C._GPU_TRUST), _C._torch_cuda, _C.gpu_capacity_rows, _C.GPU_MIN_ROWS, _C._demean_gpu_matrix)
    try:
        _C._torch_cuda = lambda: object(); _C.gpu_capacity_rows = lambda n_fe=2: 10**12; _C.GPU_MIN_ROWS = 1
        _C.USE_GPU = True; _C._GPU_TRUST.update({"matrix": True})
        def _bad(T, Y_, f, tol, mi):
            r = _C._demean_cpu_matrix(Y_, f, tol, mi); r[30000:, 0] += 1e-4; return r      # wrong only beyond row 30,000
        _C._demean_gpu_matrix = _bad
        out = _C.demean_columns(Y, u, p)
        if _C.USE_GPU or _np.abs(out - good).max() > 1e-9: bad("a GPU result wrong beyond the first rows was accepted")
        else: note("GPU demeaning verified on ALL rows every call (a 1e-4 error beyond row 30,000 in one column is rejected; CPU result used)")
    finally:
        _C.USE_GPU, trust, _C._torch_cuda, _C.gpu_capacity_rows, _C.GPU_MIN_ROWS, _C._demean_gpu_matrix = saved; _C._GPU_TRUST.update(trust)
    df = _P.pd.DataFrame({"Rain": [-0.4, -9999.0, 3.0], "Tmax": [-0.2, -10.0, 30.0], "NDVI": [-0.1, 0.3, 0.4], "buff_km": [0, 1, 2]})
    o, _ = _P.apply_missing_policy(df.copy(), stage="file")
    if not (o.Rain.tolist()[0] == 0.0 and _np.isnan(o.Rain.tolist()[1]) and o.Tmax.tolist()[0] == 0.0 and _np.isnan(o.Tmax.tolist()[1]) and o.NDVI.tolist()[0] == -0.1):
        bad(f"negative-covariate rule wrong: {o.to_dict('list')}")
    else: note("negative covariates -> 0; no-data (-9999) and the -10 C clamp -> missing (never a fake 0); outcomes untouched")
    if "negative_barrier" not in _i.getsource(_P.final_panel_is_valid): bad("a panel built with another negative barrier would be reused")
    if "REWARD_INPUT_DIR" not in open(os.path.join(HERE, "validate_notebooks_cold.py"), encoding="utf-8").read(): bad("cold-start gate could write into the bundle")
    if not os.path.exists(os.path.join(HERE, "validate_prep_notebooks.py")): bad("the end-to-end preparation-notebook gate is missing")
    if "treated_ids" not in _i.getsource(_P.streaming_panel_stats): bad("treated / control pixels are still estimated from a 1 % sample (false NOT VALID on small panels)")
    else: note("panel check counts treated / control pixels exactly (a 1 % sample declared small panels NOT VALID)")
    junk = [x for x in glob.glob(os.path.join(HERE, "**", "*"), recursive=True) if ":" in os.path.basename(x) or "\\" in os.path.basename(x)]
    if junk: bad(f"folders named like Windows paths inside the bundle (cannot be extracted on Windows): {junk[:2]}")

def check_v20_34():
    """v20.34: CELL 1 wins over the saved panel scenario; the negative filter follows the scenario everywhere
    (loop lock included); the pre-trends F is not reported as REJECT on an ill-conditioned covariance."""
    import os as _os, tempfile as _tf, numpy as _np, inspect as _i
    sys.path.insert(0, HERE)
    import _common as _C
    saved = dict(_C.ACTIVE)
    try:
        f = _os.path.join(_tf.mkdtemp(), "did_scenario.json")
        _C.set_scenario(verbose=False, control_zones="1-5", treatment_year=2022, seasons="all", nonnegative=False)
        _C.save_scenario(path=f, verbose=False)
        _C.set_scenario(verbose=False, control_zones="1-3", treatment_year=2022, seasons="auto", nonnegative=True)
        _C.load_scenario(path=f, verbose=False)
        ok_ = (_C.ACTIVE["control_zones"] == (1, 2, 3) and _C.ACTIVE["seasons"] == "auto" and _C.NONNEGATIVE_ESTIMATION
               and "ctrl1-3" in _C.scenario_tag() and "_nonneg" in _C.scenario_tag())
        if not ok_: bad(f"the saved panel scenario still overrides CELL 1 ({_C.scenario_tag()})")
        else: note("CELL 1's explicit settings win over the saved panel scenario (which fills only what CELL 1 leaves unset)")
        snap = dict(_C.ACTIVE); _C.OUTCOME_LOOP_STATE.update({"scenario": snap, "outcome": "SAVI"}); _C.NONNEGATIVE_ESTIMATION = False
        _C.set_scenario(verbose=False, control_zones="1-5", nonnegative=False)
        if not (_C.ACTIVE["control_zones"] == (1, 2, 3) and _C.NONNEGATIVE_ESTIMATION and "_nonneg" in _C.scenario_tag()):
            bad("the outcome loop runs a different design / filter than the first outcome")
        else: note("the outcome loop runs every outcome under the first outcome's design, filter and folder")
    finally:
        _C.OUTCOME_LOOP_STATE.clear(); _C.ACTIVE.clear(); _C.ACTIVE.update(saved); _C._force_negative_from_active()
    src = _i.getsource(_C.pretrends_joint_ftest)
    if "test_reliable" not in src or "INCONCLUSIVE" not in src: bad("the pre-trends F can still declare REJECT on a near-singular covariance")
    else: note("pre-trends F: only well-conditioned directions tested; an ill-conditioned covariance gives INCONCLUSIVE, not REJECT")

def check_v20_36():
    """v20.36: pixel counts + diagnostics beside the canonical result; all-variable baselines; a cell log per notebook."""
    import tempfile as _tf, numpy as _np, pandas as _pd, json as _j
    sys.path.insert(0, HERE)
    import _common as _C
    for fn in ("design_counts", "repeat_shares", "baseline_and_counts_all", "start_cell_log", "diagnose_effect_size"):
        if not hasattr(_C, fn): bad(f"_common.{fn} missing")
    rng = _np.random.default_rng(2); rows = []
    for p in range(600):
        b = 0 if p % 6 == 0 else 1 + p % 5; frz = p % 10 < 4; comp = rng.normal(0.35, 0.05)
        for y in range(2018, 2025):
            rows.append({"pixel_id": 10_000 + p, "Year": y, "Season": 0, "buff_km": b, "subwshed_id": f"S{(p // 6) % 6}",
                         "time_fe_yearseason": f"{y}_0", "NDVI": comp if (frz and y <= 2023) else comp + rng.normal(0, .03)})
    saved = dict(_C.ACTIVE)
    try:
        _C.set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, exclude_transition_year=False,
                        seasons="all", nonnegative=False, covariates=[])
        d = _C.build_treatment_columns(_pd.DataFrame(rows)); d = d[d.in_analysis_sample == 1]
        b_, s_ = _C.estimate_twfe_did(d, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id")
        od = _tf.mkdtemp(); _C.save_results({"outcome": "NDVI", "beta": b_, "se": s_}, od, "canonical_twfe_NDVI.csv")
        r = _pd.read_csv(os.path.join(od, "canonical_twfe_NDVI.csv")).iloc[0]; files = set(os.listdir(od))
        need = {"design_counts_NDVI.csv", "baseline_means_NDVI.csv", "effect_size_diagnostics_NDVI.csv"}
        if not need <= files or "n_pixels_treated_pre" not in r.index or not (0.3 < float(r.get("repeat_share_treated_pre", 0)) < 0.5):
            bad(f"the canonical result lacks its counts / baseline / diagnostics ({sorted(files)})")
        else: note("canonical result carries pixel counts per category, baseline, repeat shares and MDE; files saved beside it")
    finally:
        _C.ACTIVE.clear(); _C.ACTIVE.update(saved); _C._force_negative_from_active()
    nb_py = [f for f in glob.glob(os.path.join(HERE, "0*", "*.ipynb"))
             if (_j.load(open(f, encoding="utf-8")).get("metadata", {}).get("kernelspec", {}) or {}).get("language", "python").lower() == "python"]
    nolog = [os.path.basename(f) for f in nb_py if "start_cell_log" not in open(f, encoding="utf-8").read()]
    if nolog: bad(f"notebooks without a cell log: {nolog[:4]}")
    import inspect as _i2
    if "RESULTS_ROOT" not in _i2.getsource(_C.start_cell_log): bad("cell logs would fall back to the system temp folder instead of <OUTPUT_DIR>")
    else: note(f"all {len(nb_py)} Python notebooks write every cell's messages to <OUTPUT_DIR>/cell_logs")
    p9 = open(glob.glob(os.path.join(HERE, "01_Panel_Preparation", "P00_*.ipynb"))[0], encoding="utf-8").read()
    if "baseline_and_counts_all" not in p9: bad("P09 does not write the all-variable baseline and pixel-count files")

def check_v20_37():
    """v20.37: the cell-log hooks RUN inside IPython (a stand-in shell fires the same events -- the v20.36 hooks raised
    NameError on every cell and no test had executed them); OptTier is a known QC column; the id-correction report
    tells a renumbering from wrong ids."""
    import types as _ty, inspect as _i, pandas as _pd, importlib as _il
    sys.path.insert(0, HERE)
    class _Ev:
        def __init__(s): s.cb = {}
        def register(s, n, f): s.cb.setdefault(n, []).append(f)
        def trigger(s, n, *a):
            for f in s.cb.get(n, []): f(*a)
    class _Sh:
        def __init__(s): s.events = _Ev(); s.user_ns = {}
    sh = _Sh(); fake = _ty.ModuleType("IPython"); fake.get_ipython = lambda: sh
    real = sys.modules.get("IPython"); sys.modules["IPython"] = fake
    try:
        import _common as _C
        _C._CELL_LOG.update({"hooked": False})
        p = _C.start_cell_log("SELFCHECK_HOOKS")
        class _In: raw_cell = "x = 1"
        class _Re:
            def __init__(s, e=None): s.error_in_exec = e; s.error_before_exec = None
        try:
            sh.events.trigger("pre_run_cell", _In()); sh.events.trigger("post_run_cell", _Re())
            sh.events.trigger("pre_run_cell", _In()); sh.events.trigger("post_run_cell", _Re(ValueError("boom")))
            log = open(p, encoding="utf-8").read()
            if "finished ok" in log and "FAILED" in log and "boom" in log: note("cell-log hooks run inside IPython: per-cell headers, ok footers and full errors reach the log")
            else: bad("cell-log hooks ran but the log lacks headers / footers / errors")
        except Exception as e:
            bad(f"the cell-log hooks RAISE inside IPython ({type(e).__name__}: {e}) -- every cell would print an error")
    finally:
        if real is not None: sys.modules["IPython"] = real
        else: sys.modules.pop("IPython", None)
    import _prep_common as _P
    if "OptTier" not in _P.FINAL_PANEL_COLUMNS or "OptTier" not in _P.NEW_ONLY_COLS: bad("OptTier (exporter v111 QC column) is still 'unresolved'")
    m1, one = _P.site_id_mapping(_pd.DataFrame([{"id_pairs_all": "3>12:400;7>1:250;9>9:100"}]))      # consistent renumbering
    m2, two = _P.site_id_mapping(_pd.DataFrame([{"id_pairs_all": "12>12:300;13>12:100;7>7:50"}]))     # SWS 12 carries two ids
    if not one or two: bad("the id-correction report cannot tell a renumbering from wrong ids")
    else: note("id corrections: a consistent renumbering is reported as a relabel; the rows that changed ring or side are counted")

def check_v20_39():
    """v20.39: overlay id beside the file's id; per-sub-watershed validation; implementation years never silent;
    per-site runs cluster on the sub-watershed; P00 decides single / pooled from the panel; PASS A stops if nothing loads."""
    import json as _j, inspect as _i, pandas as _pd
    sys.path.insert(0, HERE)
    import _prep_common as _P, _sites as _S, _common as _C
    if "sws_id_export" not in _P.FINAL_PANEL_COLUMNS or 'df["sws_id_export"]' not in _i.getsource(_P.tag_sites):
        bad("the panel does not keep the id the input file carried (sws_id_export)")
    bys = _P.site_tagging_by_sws(_pd.DataFrame([{"id_pairs_all": "1>1:10;1>7:30"}]))
    if list(bys.site_id) != [1, 7] or float(bys.loc[bys.site_id == 7, "share_confirmed"].iloc[0]) != 0.0:
        bad("per-sub-watershed overlay summary wrong")
    if _S.treatment_year_source(7) != "ASSUMED" or _S.treatment_year_source(1) != "registry":
        bad("implementation-year source wrong (Haligeri must show ASSUMED until sites.csv has its year)")
    else: note("implementation years: registry / phase default / ASSUMED -- an assumed year is always announced")
    if 'cluster="site", pooled_fe="period"' not in _i.getsource(_C.run_sites): bad("per-site runs do not cluster on the sub-watershed")
    p00 = _j.load(open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8"))
    code = "\n".join("".join(c["source"]) for c in p00["cells"] if c["cell_type"] == "code")
    for v_ in ("TREATMENT_TIMING", "FRAGMENT_RULE"):                 # v20.57: SWS_MODE / YEARS_FROM_REGISTRY became the timing option
        if len(re.findall(rf"(?m)^{v_}\s*=", code)) != 1: bad(f"P00 must define {v_} once (P00_Settings)")
    if "POOLED design" not in code or "C.resolve_design(verbose=True, force=True)" not in code: bad("P00's design step does not decide single / pooled from the panel")
    else: note("P00 decides from the panel (after the fragment rule): one sub-watershed -> single design; several -> pooled, each its own cohort and cluster")
    if "PASS A produced NO pixels" not in _i.getsource(_P.run_pass_a): bad("PASS A does not stop when every file is rejected")
    if "TWO_SWS" not in open(os.path.join(HERE, "validate_prep_notebooks.py"), encoding="utf-8").read():
        bad("the notebook gate lacks the two-sub-watershed (pooled) P00 scenario")

def check_v20_43():
    """v20.43: every model -- a verified Python package, else a verified R package (R/run_one.R + models_prebuilt.R),
    else the existing implementation; the R library fixes found by review are in place."""
    import re as _re
    sys.path.insert(0, HERE)
    import _common as _C
    _rlib = os.path.dirname(_C.r_bridge_script())                                   # v20.45: FINAL/R/lib
    one = open(os.path.join(_rlib, "run_one.R"), encoding="utf-8").read()
    lib = open(os.path.join(_rlib, "models_prebuilt.R"), encoding="utf-8").read()
    r_side = set(_re.findall(r"\b(M\d\d) = ", one.split("R_PACKAGES <- list(")[1].split(")\n")[0]))
    if r_side != set(_C.R_ROUTES): bad(f"R routes differ between run_one.R and _common: {sorted(r_side ^ set(_C.R_ROUTES))}")
    strict = lib.split("run_model_strict <- function")[1].split("run_model <- function")[0]
    core = set(_re.findall(r'"(M\d\d)"', one.split("CORE_R <- c(")[1].split(")")[0])) if "CORE_R <- c(" in one else set()   # v20.58: R core models
    miss = [m for m in _C.R_ROUTES if f"{m} = " not in strict and m not in core]
    if miss: bad(f"run_model_strict lacks {miss}")
    fixes = {"M03 two-period panel": "unit %in% two[, .N, by = unit][N == 2, unit]", "M04 panel CiC": "panel = TRUE",
             "M17/M18 LISA returned": "list(global = g, lisa = lisa)", "M19 pixel sample": "N_MAX_PIXELS_MIXED",
             "M24 farthest ring present": "far <- max(d$buff_km)", "M28 never-treated coded": "event_time := -1000",
             "M36-38 site x ring units": "unit := paste(site_id, buff_km, Season, cohort", "ML sample": "N_MAX_ML", "M12": "m12_chained <- function",   # v20.58: + the season
             "M15": "m15_placebo <- function", "M41": "m41_learners <- function", "M42": "m42_dr <- function"}
    gone = [k for k, v in fixes.items() if v not in lib]
    if gone: bad(f"R library fixes missing: {gone}")
    for name, txt in (("run_one.R", one), ("models_prebuilt.R", lib)):
        txt = _re.sub(r"`\[\[?`", "", txt)                     # v20.58: R's `[[` / `[` passed as a function (vapply(rs, `[[`, ...)) is not a bracket
        for a, b in (("(", ")"), ("{", "}"), ("[", "]")):
            if txt.count(a) != txt.count(b): bad(f"{name}: unbalanced {a}{b}")
    J = _C._judge_r_known_answer
    if not (J("M03", {"estimate": 0.0501})[0] and not J("M03", {"estimate": 0.08})[0] and J("M15", {"estimate": 0.001})[0]
            and not J("M15", {"estimate": 0.03})[0] and J("M19", {"estimate": 0.3})[0]):
        bad("R known-answer rules must accept the truth and refuse a bias")
    old_rs = _C.R_SCRIPT
    try:
        _C.R_SCRIPT = None
        if not _C.find_rscript():
            _C.prebuilt_first("M03", "NDVI", verbose=False)
            if "R not installed" not in _C.LAST_ENGINE["M03"]["reason"]: bad("without R, M03 must say so")
    finally:
        _C.R_SCRIPT = old_rs
    p00 = open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8").read()
    if "C.verify_r_models()" not in p00 or ("C.install_r_packages()" not in p00 and "C.confirm_packages(" not in p00): bad("P00 P12 must install and verify the R routes")
    import tempfile as _tf                                 # v20.54: in a scratch results folder with an empty verification record,
    _keep = (_C.RESULTS_ROOT, _C.PREBUILT_FILE)            # never your results folder / your verified routes
    _C.RESULTS_ROOT = _tf.mkdtemp(prefix="sc_res_"); _C.PREBUILT_FILE = os.path.join(_C.RESULTS_ROOT, "prebuilt_verified.json")
    rp = os.path.join(_C.RESULTS_ROOT, "MODEL_READINESS.csv")
    try:                                                   # your rule: incomplete data -> the existing implementation, no package
        open(rp, "w", encoding="utf-8").write("model,status,reason,model_own_gap\nM13,incomplete-need data,no switchers,no switchers\n")
        _C.prebuilt_first("M13", "NDVI", verbose=False)
        if "do not meet" not in _C.LAST_ENGINE["M13"]["reason"]: bad("a model whose data are incomplete must not run a package")
    finally:
        _C.RESULTS_ROOT, _C.PREBUILT_FILE = _keep
    covered = {m for m, sp in _C.PREBUILT_MODELS.items() if sp["layer"] in ("function", "model")} | set(_C.R_ROUTES)
    rest = sorted(set(_C.PREBUILT_MODELS) - covered)
    note(f"pre-built first in Python or R: {len(covered)} of 45 models ({len(_C.R_ROUTES)} R routes); existing implementation only: {rest}")

def check_v20_44():
    """v20.44 (from the user's run): LandUse is a class, not a number, and not in the default covariates; singleton
    series are counted with their origin; pyfixest's singleton warning becomes a count; diff-diff's post-fit API."""
    import warnings as _w, inspect as _i, numpy as _np, pandas as _pd
    sys.path.insert(0, HERE)
    import _common as _C
    covs, lab = _C.resolve_covariates("all")
    if covs != ["Rain", "Tmax", "Tmean", "Tmin"] or lab != "all4" or "LandUse" in _C.DEFAULT_COVARIATES: bad("'all' must be the four weather covariates (tag covAll4)")
    if _C._expand_categorical_covariates(None, ["Rain", "LandUse"])[1] != ["Rain"]: bad("LandUse must never enter as a covariate")
    _cf = _C.columns_for("NDVI")
    if "LandUse" not in _cf or "LandUse" in _C.CURRENT_ESTIMATION_COLUMNS:          # M10 needs it as its GROUP
        bad("LandUse must be loaded (M10's land-use group) but never required as an estimation column")
    rng = _np.random.default_rng(2); rows = []
    for p in range(400):
        for y in range(2016, 2026):
            rows.append((p, y, 0, 0 if p % 2 == 0 else 1 + p % 5, "U1", 7, 1 + p % 3, 0.3 + (0.05 if p % 2 == 0 and y >= 2022 else 0) + rng.normal(0, 0.01)))
    rows += [(9000 + p, 2025, 0, 0 if p % 2 == 0 else 1, "U1", 7, 1, 0.3) for p in range(20)]
    d = _pd.DataFrame(rows, columns=["pixel_id", "Year", "Season", "buff_km", "subwshed_id", "site_id", "LandUse", "NDVI"])
    d["time_fe_yearseason"] = d.Year.astype(str) + "_0"
    _C.set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, exclude_transition_year=False, seasons="all", covariates=[])
    d = _C.build_treatment_columns(d); d = d[d.in_analysis_sample == 1]
    try:
        b, _ = _C.estimate_twfe_did(d, "NDVI", "did_term", "pixel_id", "time_fe_yearseason", "subwshed_id", covariates=["LandUse"])
        if not (abs(b - 0.05) < 0.01): bad(f"land-use classes as covariates give {b:.4f} on a +0.05 panel")
    except Exception as e:
        bad(f"a LandUse request must be dropped, not fail ({type(e).__name__}: {str(e)[:80]})")
    if _C.LAST_FIT_INFO.get("n_singleton_series") != 20: bad(f"singleton series miscounted: {_C.LAST_FIT_INFO.get('n_singleton_series')} (want 20)")
    _C._pf_quiet(lambda: _w.warn("123 singleton fixed effect(s) dropped from the model.", UserWarning))
    if _C.LAST_FIT_INFO.get("pyfixest_singletons_dropped") != 123: bad("pyfixest's singleton warning is not turned into a count")
    dd = open(os.path.join(HERE, "python_prebuilt", "dd_pipeline.py"), encoding="utf-8").read()
    if "def _cs_fit(" not in dd or "r.overall_att" in dd or "def _cs_event_study_table" not in _i.getsource(_C):
        bad("Callaway-Sant'Anna still uses diff-diff's deprecated fit(aggregate=)")
    else: note("covariates: weather by default, land use only as classes on request; singletons counted with their origin; diff-diff post-fit API")

def check_r_library():
    """v20.45: the R pipeline lives in the bundle's R/ folder; the Python bridge must find it there."""
    sys.path.insert(0, HERE)
    import _common as _C
    lib = os.path.dirname(_C.r_bridge_script())
    miss = [f for f in ("run_one.R", "models_prebuilt.R", "reward_prep.R", "reward_design.R", "reward_models_core.R", "reward_paths.R", "model_names.R")
            if not os.path.exists(os.path.join(lib, f))]
    if miss: bad(f"R library incomplete at {lib}: missing {miss}")
    else: note(f"R library found where the bridge looks: {os.path.relpath(lib, HERE)}")

def check_v20_54():
    """v20.54 (the regression audit against every earlier version): what it found, each under a test."""
    import inspect as _i, numpy as _np, pandas as _pd, tempfile as _tf, time as _t
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P, _hardware as _H, _paths as _Pp
    # 1. YOUR 98 % rule (v20.57; was 95 %) guards a package's copy of the panel (v20.52 had switched the check off)
    src = _i.getsource(_C._route_call)
    if "need > bud" not in src or "if False" in src: bad("package copies are not guarded by YOUR 98 % RAM rule")
    else: note("a package whose copy would not fit below 98 % RAM hands over to the engine; otherwise the package is used first")
    # 2. the data-rules version names the current rules (v20.52's Coverage <= 0 rule had not bumped it)
    if _ver(_C.DATA_RULES_VERSION) < (20, 54): bad(f"DATA_RULES_VERSION {_C.DATA_RULES_VERSION} predates the current data rules")
    # 3. package inputs: one per site set, and never reused after the panel was rebuilt
    try:
        import validate_all_models as _VM
        df_ = _VM.make_panel(n_pix=120)
    except Exception as e:
        bad(f"package-input freshness test could not build its panel: {type(e).__name__}: {e}"); df_ = None
    if df_ is not None:
        d_ = _tf.mkdtemp(prefix="sc_pkg_"); fp = os.path.join(d_, "panel.parquet"); df_.to_parquet(fp, index=False)
        keep = (_C.PREPARED_PANEL, _C.ESTIMATOR_FILES_DIR, _C.RESULTS_ROOT, dict(_C.ACTIVE), _C.SITE_FILTER)
        try:
            _C.PREPARED_PANEL = fp; _C.ESTIMATOR_FILES_DIR = os.path.join(d_, "ef"); _C.RESULTS_ROOT = os.path.join(d_, "res"); _C.clear_panel_cache()
            _C.set_scenario(verbose=False, all_years=True); _C.set_scenario(verbose=False, control_zones="1-5", treatment_year=2022)
            _C.SITE_FILTER = 1; s1 = _C.package_input_ready("NDVI"); a = _pd.read_parquet(s1 + ".parquet")
            _t1 = os.path.getmtime(s1 + ".json")
            for _sf in ([1], _np.array([1]), (1,)):                           # the same site written other ways: same file,
                _C.SITE_FILTER = _sf                                            # still fresh (no rebuild), no error
                if _C.package_input_ready("NDVI") != s1 or os.path.getmtime(s1 + ".json") != _t1:
                    bad(f"SITE_FILTER {_sf!r}: not recognised as the same site as 1 (rebuilt or renamed)")
            _C.SITE_FILTER = 2; s2 = _C.package_input_ready("NDVI"); b = _pd.read_parquet(s2 + ".parquet")
            _C.SITE_FILTER = None; s0 = _C.package_input_ready("NDVI"); m0 = float(_pd.read_parquet(s0 + ".parquet")["NDVI"].mean())
            _t.sleep(1.1); df2 = df_.copy(); df2.loc[df2["NDVI"] != 0, "NDVI"] += 1.0          # the rebuilt panel: same rows, NDVI + 1
            df2.to_parquet(fp, index=False); _C.clear_panel_cache()                             # (masked zeros stay masked)
            m1 = float(_pd.read_parquet(_C.package_input_ready("NDVI") + ".parquet")["NDVI"].mean())
            okay = s1 != s2 and set(a.site_id) == {1} and set(b.site_id) == {2} and abs(m1 - m0 - 1.0) < 1e-6
            if not okay: bad(f"package inputs are reused across sites ({sorted(set(b.site_id))} for site 2) or after a rebuild (NDVI mean {m0:.3f} -> {m1:.3f}, +1 expected)")
            else: note("package inputs: one per site set; a rebuilt panel (or other sites) makes them rebuilt, never reused (were reused before v20.54)")
        except Exception as e:
            bad(f"package-input freshness test raised {type(e).__name__}: {e}")
        finally:
            _C.PREPARED_PANEL, _C.ESTIMATOR_FILES_DIR, _C.RESULTS_ROOT = keep[0], keep[1], keep[2]
            _C.ACTIVE.clear(); _C.ACTIVE.update(keep[3]); _C.SITE_FILTER = keep[4]; _C.clear_panel_cache()
    # 4. your optional manual MEMORY_SHARE works again; by default nothing is capped
    saved = (_H.MEMORY_SHARE, _H.AUTO_SPLIT, dict(_H._SHARE_CACHE))
    try:
        _H.AUTO_SPLIT = False; _H.MEMORY_SHARE = 0.45; half = _H.memory_share(); _H.MEMORY_SHARE = 1.0; whole = _H.memory_share()
        if abs(half - 0.45) > 1e-12 or whole != 1.0: bad(f"MEMORY_SHARE ignored (0.45 -> {half}, 1.0 -> {whole})")
        else: note("MEMORY_SHARE (your optional manual setting) is honoured; the default 1.0 caps nothing")
    finally:
        _H.MEMORY_SHARE, _H.AUTO_SPLIT = saved[0], saved[1]; _H._SHARE_CACHE.clear(); _H._SHARE_CACHE.update(saved[2])
    # 5. the negative barrier switched off keeps real negatives but never a fill value
    sv = (_P.ALLOW_NEGATIVE_COVARIATES, dict(_P.NEGATIVE_COVARIATE_RULE))
    try:
        _P.ALLOW_NEGATIVE_COVARIATES = True
        f = _pd.DataFrame({"NDVI": [0.4, 0.4, 0.4], "Rain": [-1.5, -9999.0, 5.0], "Tmin": [-10.0, 18.0, -3.0]})
        g, _ = _P.apply_missing_policy(f.copy(), stage="file")
        if not (g.Rain.iloc[0] == -1.5 and _np.isnan(g.Rain.iloc[1]) and _np.isnan(g.Tmin.iloc[0]) and g.Tmin.iloc[2] == -3.0):
            bad(f"barrier OFF: fill values must stay missing, real negatives kept -- got Rain {g.Rain.tolist()}, Tmin {g.Tmin.tolist()}")
        else: note("barrier OFF (ALLOW_NEGATIVE_COVARIATES): real negatives kept, -9999 and the -10 C clamp still missing")
    finally:
        _P.ALLOW_NEGATIVE_COVARIATES, _P.NEGATIVE_COVARIATE_RULE = sv
    # 6. off Windows the projects keep separate data roots (both ended in ...\data since v20.50)
    if os.name != "nt":
        r1, r2, r0 = _Pp._portable(r"D:\LKT\RWD_Artal\data"), _Pp._portable(r"D:\LKT\RWDR\data"), _Pp._portable(r"D:\LKT\TST_Artal")   # v20.58: Artal1 dropped
        if r1 == r2 or not r0.endswith(os.path.join("REWARD_data", "TST_Artal")): bad(f"portable data roots collide: {r1} / {r2}")
        else: note("off Windows, D:\\LKT\\RWD_Artal\\data and D:\\LKT\\RWDR\\data map to separate folders")
    # 7. the R library: your negative-covariate switch and zero rule as in Python; MEMORY_SHARE honoured
    rl = os.path.dirname(_C.r_bridge_script())
    rp, rpr, rd = (open(os.path.join(rl, f_), encoding="utf-8").read() for f_ in ("reward_paths.R", "reward_prep.R", "reward_design.R"))
    if "ALLOW_NEGATIVE_COVARIATES <- FALSE" not in rp or "isTRUE(ALLOW_NEGATIVE_COVARIATES)" not in rpr: bad("R: no switch for the negative-covariate barrier")
    elif "x[x == 0] <- NA" not in rpr.split("apply_missing_policy <- function")[1].split("\n}")[0]: bad("R: an exported 0 of a covariate is not missing (Python's zero rule)")   # v20.55: in apply_missing_policy, as Python
    elif "return(sh)" not in rd.split("memory_share <- function")[1].split("\n}")[0]: bad("R: MEMORY_SHARE ignored")
    else: note("R: ALLOW_NEGATIVE_COVARIATES and the covariate zero rule as in Python; MEMORY_SHARE honoured")
    # 8. warnings you reported: pyfixest's raw singleton warning (pf_pipeline), R's coercion / qte notes
    pfp = open(os.path.join(HERE, "python_prebuilt", "pf_pipeline.py"), encoding="utf-8").read()
    body = pfp.split("def _feols(")[1].split("\ndef ")[0] if "def _feols(" in pfp else ""
    if not body or pfp.count("pf.feols(") != body.count("pf.feols(") or pfp.count("_feols(C, pf, ") < 4: bad("pf_pipeline calls pyfixest without the singleton-warning handler")
    mp = open(os.path.join(rl, "models_prebuilt.R"), encoding="utf-8").read()
    if 'as.integer(sub(".*::(-?[0-9]+).*", "\\\\1", term))' in mp or "muffleWarning" not in mp.split("m04_cic <- function")[1].split("\n}")[0]:
        bad("R: the event-time parse still warns 'NAs introduced by coercion', or qte's inapplicable notes are not handled")
    else: note("warnings: pyfixest singletons explained in one line everywhere; R event-time parsing and qte's two inapplicable notes silenced (results unchanged)")
    # 9. pandas 2: a categorical sub-watershed column with sub-watersheds NOT in the sample must not change M19's ICC
    import warnings as _w
    rng = _np.random.default_rng(1); g_ = _np.repeat(["SW1", "SW2"], 300); x_ = rng.normal(0, 1, 600) + _np.repeat([0.0, 0.8], 300)
    with _w.catch_warnings():
        _w.simplefilter("error", FutureWarning)                 # the engine must not rely on pandas' observed=False default
        try:
            a_ = _C.variance_decomposition(x_, _pd.Series(g_))
            b_ = _C.variance_decomposition(x_, _pd.Series(_pd.Categorical(g_, categories=[f"SW{i}" for i in range(1, 21)])))
            if abs(float(a_["ICC"]) - float(b_["ICC"])) > 1e-12: bad(f"ICC depends on unused categories: {float(a_['ICC']):.4f} vs {float(b_['ICC']):.4f}")
            else: note("M19's ICC is the same whether the sub-watershed column is text or a categorical with unused sub-watersheds (pandas 2 and 3)")
        except FutureWarning as e:
            bad(f"variance_decomposition relies on a pandas default that changes in pandas 3: {e}")

def check_v20_56():
    """v20.56: YOUR RULES -- no chunking (every regression on all rows in RAM + GPU at once); R packages pre-built first,
    a source build only when no binary exists and it can be built here (Rtools), never an unasked-for source build."""
    import inspect as _i, json as _j
    sys.path.insert(0, HERE)
    import _common as _C
    # 1. the in-RAM path is the only regression path
    if not getattr(_C, "NO_CHUNKING", False) or _C.MEMORY_POLICY != "raise": bad("NO_CHUNKING / MEMORY_POLICY: a regression could be thinned or streamed")
    else:
        try:
            m, why = _C.recommend_mode(["pixel_id", "Year", "Season", "NDVI"]) if os.path.exists(_C.PREPARED_PANEL) else ("memory", "no panel here")
        except Exception as e:
            m, why = "memory", f"(recommend_mode raised {type(e).__name__} without a panel: fine)"
        if m != "memory": bad(f"recommend_mode still chooses '{m}': {why}")
        else: note("no chunking: MEMORY_POLICY = raise, recommend_mode = memory -- every regression runs on all its rows in RAM (GPU when they fit below 98 % VRAM)")
    nb = os.path.join(HERE, "02_Core_DiD_Models", "M01_Canonical_2x2_Static_TWFE.ipynb")
    src = "\n".join("".join(c["source"]) for c in _j.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
    # v20.58 YOUR RULE (replaces v20.56's "no streaming at all"): every row in RAM + GPU at once whenever it fits below 98 %; ONLY beyond that
    # the exact two-pass streaming estimator, in batches 5x larger than v20.57's
    if ('M01_MODE   = "auto"' not in src or "RUN_MODE, _why = C.run_mode(MODEL_ID, cols)" not in src or "C.load_panel_ooc(cols)" not in src
            or 'if RUN_MODE == "out_of_core":' not in src or "C.ooc_model(MODEL_ID" not in src):
        bad("M01: not 'auto' (all rows at once below 98 %; out of core -- Dask, Spark, built-in batches -- only beyond)")
    else: note("M01: M01_MODE = 'auto' -- every row in RAM + GPU at once whenever it fits below 98 %; beyond it OUT OF CORE (pixel partitions on Dask -> Spark -> built-in batches; exact)")
    import glob as _g
    users = [os.path.basename(f_) for f_ in _g.glob(os.path.join(HERE, "0[2-5]_*", "M*.ipynb"))
             if "estimate_twfe_did_streaming(" in open(f_, encoding="utf-8").read() and "M01_" not in os.path.basename(f_)]
    if users: bad(f"model notebooks using the streaming estimator: {users}")
    gsrc = _i.getsource(_C._demean_gpu_matrix)
    if "range(0, n" in gsrc or "chunk" in gsrc.lower(): bad("the GPU demeaner processes the matrix in chunks")
    else: note("the GPU demeaner takes the whole matrix in one pass (the only loops are over fixed effects and iterations)")
    # 2. R packages: pre-built first; a source build only without a binary AND with the build tools; never the 'newer source' prompt
    rl = os.path.dirname(_C.r_bridge_script()); rpk = open(os.path.join(rl, "reward_packages.R"), encoding="utf-8").read()
    setup = None
    cand = os.path.join(rl, "..", "..", "..", "RWDR_v" + _C.ENGINE_VERSION, "00_SETUP.R")
    if os.path.exists(cand): setup = open(cand, encoding="utf-8").read()
    miss = []
    if 'install.packages.compile.from.source = "never"' not in rpk: miss.append("compile-from-source switched off")
    if 'type = "binary"' not in rpk or "binary_platform <- function" not in rpk: miss.append("binary first on Windows / macOS")
    if "has_build_tools <- function" not in rpk or "needs_compilation <- function" not in rpk or "RTOOLS_URL" not in rpk: miss.append("Rtools awareness")
    if "utils::install.packages(pkgs = " not in rpk: miss.append("explicit pkgs=")
    if setup is not None and ("UPDATE_PACKAGES <- FALSE" not in setup or "install.packages(upd" in setup): miss.append("00_SETUP.R: no unasked-for updates")
    if miss: bad("R package chain lacks: " + ", ".join(miss))
    else: note("R packages: pre-built binaries first (Windows / macOS), the source only when no binary exists and it can be built here (Rtools said otherwise), installed packages not updated unless asked")

def check_v20_58_out_of_core():
    """v20.58 YOUR RULE: beyond 98 % of the RAM (never before) M01 / M02 / M16 / M34 (and P00 / R_P00) go OUT OF CORE -- Dask, then Spark,
    then the built-in batches -- exact and never sampled; in Python AND in R. And one definition per function in the engine files."""
    import ast as _ast, json as _j, glob as _g
    sys.path.insert(0, HERE)
    miss = []
    for f in ("_outofcore.py", "_ooc_models.py", "validate_out_of_core.py"):
        if not os.path.exists(os.path.join(HERE, f)): miss.append(f)
    if miss: bad("out-of-core files missing: " + ", ".join(miss)); return
    import _outofcore as _O, _paths as _P
    if tuple(_O.OOC_MODELS) != ("M01", "M02", "M16", "M34"): bad(f"_outofcore.OOC_MODELS = {_O.OOC_MODELS}")
    order = tuple(getattr(_P, "OUT_OF_CORE", ()))
    if order != ("dask", "spark", "batches") or _O.engine_order()[-1] != "batches": bad(f"OUT_OF_CORE (_paths.py) = {order}: expected dask -> spark -> batches")
    else: note("out of core (Python): _paths.OUT_OF_CORE = dask -> spark -> batches; " + "; ".join(f"{e}: {'available' if _O.engine_status(e)[0] else 'NOT available'}" for e in _O.KNOWN_ENGINES))
    nbs = {"M01": "02_Core_DiD_Models/M01_Canonical_2x2_Static_TWFE.ipynb", "M02": "02_Core_DiD_Models/M02_Event_Study_dynamic_TWFE.ipynb",
           "M16": "02_Core_DiD_Models/M16_Formal_Joint_Pre_Trends_F_test.ipynb", "M34": "04_Advanced_Staggered_Robustness/M34_Honest_DiD_parallel_trends_sensitivity.ipynb"}
    lack = []
    for m, rel in nbs.items():
        fp = os.path.join(HERE, rel)
        if not os.path.exists(fp): continue                                   # a project without this model (PIPELINE_MODELS)
        src = "\n".join("".join(c["source"]) for c in _j.load(open(fp, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
        if "C.run_mode(MODEL_ID, cols)" not in src or "C.load_panel_ooc(cols)" not in src or "C.ooc_model(MODEL_ID" not in src: lack.append(m)
    if lack: bad(f"model notebooks without the out-of-core branch: {lack}")
    else: note("M01 / M02 / M16 / M34 notebooks: run_mode -> in memory below 98 %, out of core (ooc_model) beyond")
    # R: the same four models and R_P00, the same engines (R's own batches; Dask / Spark through lib/reward_ooc_engine.py)
    rl = os.path.join(os.path.dirname(os.path.dirname(HERE)), "R", "lib")
    if not os.path.isdir(rl):
        import _common as _C; rl = os.path.dirname(_C.r_bridge_script())
    need = ["reward_outofcore.R", "reward_prep_ooc.R", "reward_ooc_task.R", "reward_ooc_engine.py"]
    lr = [f for f in need if not os.path.exists(os.path.join(rl, f))]
    if lr: bad("R out-of-core files missing in " + rl + ": " + ", ".join(lr))
    else:
        core = open(os.path.join(rl, "reward_models_core.R"), encoding="utf-8").read(); prep = open(os.path.join(rl, "reward_prep.R"), encoding="utf-8").read()
        pth = open(os.path.join(rl, "reward_paths.R"), encoding="utf-8").read(); ooc = open(os.path.join(rl, "reward_outofcore.R"), encoding="utf-8").read()
        m2 = []
        if "rm_ <- run_mode_R(id, outcome, d)" not in core or "ooc_run_model_R(id, outcome, d" not in core: m2.append("run_model_R -> out of core")
        if "pm <- prep_mode_R(files)" not in prep or "run_prep_ooc(files" not in prep: m2.append("run_prep -> block by block")
        if 'OUT_OF_CORE         <- c("dask", "spark", "batches")' not in pth: m2.append("OUT_OF_CORE in reward_paths.R")
        if 'OOC_MODELS_R <- c("M01", "M02", "M16", "M34")' not in ooc: m2.append("OOC_MODELS_R")
        if m2: bad("R out of core: " + ", ".join(m2))
        else: note("out of core (R): M01 / M02 / M16 / M34 (run_model_R) and R_P00 (run_prep) beyond 98 % -- Dask -> Spark -> R batches, exact")
    # one definition per top-level function (a second definition silently replaces the first -- v20.58 found treatment_coverage twice)
    dup = []
    for f in ("_common.py", "_prep_common.py", "_outofcore.py", "_ooc_models.py", "_location.py", "_fund.py", "_hardware.py"):
        fp = os.path.join(HERE, f)
        if not os.path.exists(fp): continue
        names = [n.name for n in _ast.parse(open(fp, encoding="utf-8").read()).body if isinstance(n, (_ast.FunctionDef, _ast.ClassDef))]
        d_ = sorted({n for n in names if names.count(n) > 1})
        if d_: dup.append(f"{f}: {d_}")
    if dup: bad("functions defined twice (the second silently replaces the first): " + "; ".join(dup))
    else: note("one definition per function in the engine files (no silent replacement)")

def check_v20_58_repeated_rows():
    """v20.58 (second pass, found by the poison test with cloud gaps): P00 filled the kept row's gaps from the REPEATED rows it dropped (a cloud
    gap of the newer export took the older export's value of that pixel-period), so values of dropped rows reached every model. Now a repeated
    row is dropped WHOLE (DEDUP_FILL_FROM_DUPLICATES = False; True = the old fill, for exports split by variable), in Python and R; the setting
    is recorded in panel_build_settings.json and a panel built otherwise is rebuilt; every panel-building setting of P00 lives in P00_Settings
    (set in the PASS B cell, after the validate-or-skip step, a change was silently ignored while the old panel was kept)."""
    import inspect as _i, json as _j, re as _re
    sys.path.insert(0, HERE)
    import numpy as _np, pandas as _pd
    import _prep_common as _P, _common as _C
    miss = []
    if _P.DEDUP_FILL_FROM_DUPLICATES is not False: miss.append(f"DEDUP_FILL_FROM_DUPLICATES defaults to {_P.DEDUP_FILL_FROM_DUPLICATES!r}")
    df = _pd.DataFrame([dict(site_id=1, pixel_id=1, Year=2023, Season=1, NDVI=_np.nan, LAI=1.0, src_file="new.csv", file_mtime=9.0),
                        dict(site_id=1, pixel_id=1, Year=2023, Season=1, NDVI=0.9, LAI=1.5, src_file="old.csv", file_mtime=1.0),
                        dict(site_id=1, pixel_id=2, Year=2023, Season=1, NDVI=0.5, LAI=1.1, src_file="old.csv", file_mtime=1.0)])
    out, lg = _P.resolve_duplicates(df.copy(), conflict_log=[])
    o1 = out[out.pixel_id == 1]
    if len(out) != 2 or len(o1) != 1 or not _np.isnan(o1.NDVI.iloc[0]) or o1.LAI.iloc[0] != 1.0 or out.attrs.get("values_in_dropped_rows_not_used") != 1:
        miss.append(f"a repeated row's value reached the kept row: {o1.to_dict('records')} {out.attrs}")
    opt, _ = _P.resolve_duplicates(df.copy(), conflict_log=[], fill_from_duplicates=True)
    if opt[opt.pixel_id == 1].NDVI.iloc[0] != _np.float64(0.9) or opt.attrs.get("values_filled_from_duplicates") != 1:
        miss.append("DEDUP_FILL_FROM_DUPLICATES = True does not fill the kept row's gap")
    if "dedup_fill_from_duplicates" not in _i.getsource(_P.final_panel_is_valid) or '"dedup_fill_from_duplicates": bool(DEDUP_FILL_FROM_DUPLICATES)' not in _i.getsource(_P.run_pass_b):
        miss.append("the fill setting is not recorded in / compared with panel_build_settings.json")
    # v20.58: the workers receive EVERY setting (_settings_snapshot; the hand-picked lists missed ALLOW_NEGATIVE_COVARIATES / NEGATIVE_COVARIATE_RULE)
    if ("cfg = _settings_snapshot()" not in _i.getsource(_P.run_pass_b) or "cfg = _settings_snapshot()" not in _i.getsource(_P.run_pass_a)
            or _P._settings_snapshot().get("DEDUP_FILL_FROM_DUPLICATES", "missing") is not _P.DEDUP_FILL_FROM_DUPLICATES
            or "ALLOW_NEGATIVE_COVARIATES" not in _P._settings_snapshot()):
        miss.append("the PASS A / PASS B worker processes do not receive DEDUP_FILL_FROM_DUPLICATES (and every other setting)")
    nb = _j.load(open(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb"), encoding="utf-8"))
    code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    i_set = [k for k, c in enumerate(code) if c.startswith("# ===== P00_Settings")]; i_val = [k for k, c in enumerate(code) if c.startswith("# ===== P00_Validate_or_Skip")]
    for v_ in ("NEAR_DUPLICATE_PIXELS", "PIXEL_SIZE_M", "DEDUP_PRIORITY", "DEDUP_FILL_FROM_DUPLICATES", "NEGATIVE_COVARIATE_RULE", "ALLOW_NEGATIVE_COVARIATES", "PIXEL_OVERLAP_MIN"):
        where = [k for k, c in enumerate(code) if _re.search(rf"(?m)^\s*P\.{v_}\s*=", c)]
        if where != i_set or not i_val or i_set[0] > i_val[0]:
            miss.append(f"P00 sets P.{v_} in cells {where} (must be once, in P00_Settings, before P00_Validate_or_Skip)")
    rp = open(os.path.join(os.path.dirname(_C.r_bridge_script()), "reward_prep.R"), encoding="utf-8").read()
    if not _re.search(r"(?m)^DEDUP_FILL_FROM_DUPLICATES <- FALSE", rp) or "fill <- isTRUE(DEDUP_FILL_FROM_DUPLICATES)" not in rp \
            or "if (fill) { set(first, which(gap), v, first$.don[gap])" not in rp:
        miss.append("R resolve_duplicates still fills the kept row's gaps from the repeated rows")
    # the empty rows leave AFTER the cross-file dedup (a newer export's empty row claims its pixel-year-season; dropped per file before
    # the dedup, the older repeated row took its place -- the poison test with cloud gaps: M01 0.087 for the true 0.050)
    pa_ = _i.getsource(_P._pa_worker) + _i.getsource(_P.run_pass_a); pb_ = _i.getsource(_P.prepare_pass_b_block)
    if "apply_missing_policy(df, drop_empty=False)" not in pa_ or 'apply_missing_policy(block, stage="block", drop_empty=False)' not in pb_ \
            or pb_.index("resolve_duplicates(block") > pb_.index("drop_rows_without_outcome(block"):
        miss.append("Python P00 drops the rows without an outcome before the cross-file de-duplication")
    e_ = _pd.DataFrame([dict(site_id=1, pixel_id=1, Year=2023, Season=1, NDVI=_np.nan, LAI=_np.nan, Rain=600.0, src_file="new.csv", file_mtime=9.0),
                        dict(site_id=1, pixel_id=1, Year=2023, Season=1, NDVI=0.9, LAI=1.5, Rain=610.0, src_file="old.csv", file_mtime=1.0)])
    e1, _ = _P.apply_missing_policy(e_.copy(), drop_empty=False); e2, _ = _P.resolve_duplicates(e1, conflict_log=[]); e3, st_ = _P.drop_rows_without_outcome(e2)
    if len(e1) != 2 or len(e3) != 0 or st_.get("rows_dropped_no_outcome") != 1:
        miss.append(f"the newer export's empty row does not claim its pixel-year-season ({len(e3)} row(s) left, the older one must not be)")
    if "apply_missing_policy(dt, drop_empty = FALSE)" not in rp or rp.index("dt <- resolve_duplicates(dt)") > rp.index("n0 <- nrow(dt); dt <- drop_rows_without_outcome(dt)"):
        miss.append("R_P00 drops the rows without an outcome before resolve_duplicates")
    if miss: bad("v20.58 repeated rows dropped whole: " + "; ".join(miss))
    else: note("v20.58: a repeated row is dropped WHOLE at the panel (Python and R; its values never fill the kept row's gaps -- "
               "DEDUP_FILL_FROM_DUPLICATES = True is the option, recorded in the panel and rebuilt when changed; a newer export's EMPTY row still "
               "claims its pixel-year-season: the rows without an outcome leave after the de-duplication); every P00 panel setting in P00_Settings")

def check_v20_58_memory_batches():
    """v20.58 (found when a validation run was KILLED for memory): M25's permutations in batches were sized for 3 n-vectors per permutation
    while the peak was 5 (the demeaning's convergence test made two more n x k temporaries). The demeaning tests its convergence in place
    (the same numbers, bit for bit) and M25 counts 6 n-vectors, in Python and R; the permuted estimates do not depend on the batch size."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import numpy as _np, pandas as _pd
    import _common as _C
    miss = []
    if "np.subtract(R, prev, out=prev)" not in _i.getsource(_C._demean_cpu_matrix): miss.append("the demeaning's convergence test is not in place")
    if "48.0 * n" not in _i.getsource(_C._permutation_inference_impl): miss.append("Python M25 does not count 6 n-vectors per permutation")
    _rlib = os.path.dirname(_C.r_bridge_script())
    rp = open(os.path.join(_rlib, "models_prebuilt.R"), encoding="utf-8").read()
    if "unit_cap(8 * 6 * nrow(dt))" not in rp or "Md <- dm(M); rm(M)" not in rp: miss.append("R M25 does not count 6 n-vectors per permutation")
    # the demeaning: bit-identical to the v20.57 test (a copy of it here), with missing keys and very different column scales
    from scipy import sparse as _sp
    def _old(Y, fes, tol=1e-10, max_iter=200):
        R = _np.array(_np.asarray(Y, dtype=_np.float64), order="C"); n = R.shape[0]; ops = []
        for f in fes:
            cd = _C._codes(f); ok = cd >= 0; K = int(cd.max()) + 1 if ok.any() else 1
            cnt = _np.bincount(cd[ok], minlength=K).astype(_np.float64); cnt[cnt == 0] = 1.0
            ops.append((_sp.csr_matrix((1.0 / cnt[cd[ok]], (cd[ok], _np.nonzero(ok)[0])), shape=(K, n)), cd, ok, ok.all()))
        for _ in range(max_iter):
            prev = R.copy()
            for P_, cd, ok, allok in ops:
                means = P_ @ R
                if allok: R -= means[cd]
                else: R[ok] -= means[cd[ok]]
            if _np.max(_np.abs(R - prev)) < tol: break
        return R
    rng = _np.random.default_rng(7)
    for t in range(3):
        n = 6000; f1 = rng.integers(0, 400, n).astype(float); f2 = rng.integers(0, 30, n)
        if t: f1[rng.random(n) < 0.03] = _np.nan
        Y = rng.normal(size=(n, 5)); Y[:, 2] *= 1e5
        new = _C._demean_cpu_matrix(Y, [f1, f2], 1e-10, 200)
        if t == 0:      # complete keys: converges in 16 passes -- bit-identical to v20.57
            if not _np.array_equal(_old(Y, [f1, f2]), new, equal_nan=True): miss.append("the demeaning changed where v20.57 converged"); break
        else:           # 3 % of the rows without a unit key: v20.57 stopped after 200 passes ~1e-5 short; now converged (the extension)
            ref = _old(Y, [f1, f2], tol=1e-13, max_iter=100_000); sc_ = _np.maximum(1.0, _np.abs(ref).max(axis=0))
            e_new = float((_np.abs(new - ref).max(axis=0) / sc_).max()); e_old = float((_np.abs(_old(Y, [f1, f2]) - ref).max(axis=0) / sc_).max())
            if not (e_new < 1e-9 and e_old > 1e-7): miss.append(f"slow design (panel {t}): the demeaning is {e_new:.1e} from convergence (v20.57: {e_old:.1e})"); break
    old_cap = _C.FE_MAX_ITER; _C.FE_MAX_ITER = 4; _C._FE_CONV_SAID.clear(); said = []
    _w0 = _C.warn; _C.warn = lambda m, *a_, **k_: said.append(str(m))
    try: _C._demean_cpu(Y[:, 0].copy(), [f1, f2], 1e-10, 3)
    finally: _C.FE_MAX_ITER = old_cap; _C.warn = _w0; _C._FE_CONV_SAID.clear()
    if not any("did not reach" in m_ for m_ in said): miss.append("a demeaning that does not converge is not reported")
    # M25: all at once == in batches (a budget for 13 permutations per batch)
    rows = []
    for px in range(1, 61):
        ring = 0 if px <= 15 else 1 + (px - 16) % 3
        for s_ in (1, 2):
            for y in range(2017, 2024):
                rows.append((px, s_, y, int(ring == 0), int(y >= 2021), 0.3 + 0.001 * px + 0.05 * int(ring == 0) * int(y >= 2021) + rng.normal(0, 0.02)))
    A = _pd.DataFrame(rows, columns=["pixel_id", "Season", "Year", "treat", "post", "y"])
    A["unit"] = A.pixel_id.astype(str) + "_" + A.Season.astype(str); A["period"] = A.Year.astype(str) + "_" + A.Season.astype(str)
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        r1 = _C._permutation_inference_impl(A, "y", "treat", "post", "unit", "period", n_permutations=99)
        old_env = os.environ.get("REWARD_RAM_BUDGET_BYTES"); os.environ["REWARD_RAM_BUDGET_BYTES"] = str(48.0 * len(A) * 13)
        try:
            r2 = _C._permutation_inference_impl(A, "y", "treat", "post", "unit", "period", n_permutations=99)
        finally:
            if old_env is None: os.environ.pop("REWARD_RAM_BUDGET_BYTES", None)
            else: os.environ["REWARD_RAM_BUDGET_BYTES"] = old_env
    if not (r2["batch"] == 13 and r1["batch"] == 99 and r1["p_value_permutation"] == r2["p_value_permutation"]
            and abs(r1["se_permutation"] - r2["se_permutation"]) <= 1e-15):
        miss.append(f"M25 in batches ({r2['batch']}) differs from all at once ({r1['batch']}): p {r2['p_value_permutation']} vs {r1['p_value_permutation']}")
    if getattr(_C, "PYFIXEST_FIXEF_TOL", 1.0) > 1e-10 or "_pf_demeaner_kw(fn, kw)" not in _i.getsource(_C._pf_quiet):
        miss.append("pyfixest's demeaning is left at its default tolerance (1e-6: the SE's 8th digit then follows Python's string hashing)")
    if miss: bad("98 % rule, batch sizes: " + "; ".join(miss))
    else: note("98 % rule, batch sizes: M25 counts its true peak (6 n-vectors per permutation; Python and R), the demeaning tests convergence in "
               "place (bit-identical where v20.57 converged; a slow design is now iterated to convergence, one that cannot converge is "
               "reported), pyfixest converges to 1e-12, and M25's permutations in batches == all at once (the same draws in the same order)")

def check_v20_35_structure():
    """v20.35: gap-filled rows out of estimation, scenario-only rows loaded (M24 exempt), multi-site controls cleaned,
    per-variable files carry the QC flags, and every result records what was left out."""
    sys.path.insert(0, HERE)
    import _common as _C, inspect as _i
    if not (_C.EXCLUDE_GAPFILLED and _C.CLEAN_CONTROLS and _C.LOAD_SCENARIO_ROWS_ONLY): bad("a v20.35 structural default is off")
    if _C.MODELS_NEEDING_ALL_RINGS: bad(f"{sorted(_C.MODELS_NEEDING_ALL_RINGS)} load rings outside CONTROL_ZONES (v20.58 YOUR RULE: the rings you set are the rings every model uses)")
    if not {"GapFilled", "Coverage"} <= set(_C.ESTIMATOR_FILE_EXTRA): bad("P09 files do not carry the QC flags")
    if not {"GapFilled", "Coverage"} <= set(_C.columns_for("NDVI")): bad("models do not read the QC flags")
    src = _i.getsource(_C.load_panel)
    if "EXCLUDE_GAPFILLED" not in src or "LOAD_SCENARIO_ROWS_ONLY" not in src: bad("load_panel does not apply the v20.35 row rules")
    if "CLEAN_CONTROLS" not in _i.getsource(_C.build_treatment_columns): bad("multi-site contaminated controls are not cleaned")
    if not hasattr(_C, "diagnose_effect_size"): bad("the effect-size diagnostic is missing")
    import pandas as _pd, numpy as _np
    rows = []
    for p in range(120):
        b = 0 if p % 6 == 0 else 1 + p % 5; site = 1 if (p // 6) % 2 == 0 else 2
        for y in (2020, 2021, 2022, 2023):
            rows.append({"pixel_id": p, "Year": y, "Season": 0, "buff_km": b, "site_id": site, "subwshed_id": f"S{p % 6}",
                         "time_fe_yearseason": f"{y}_0", "NDVI": 0.4 + (0.05 if (b == 0 and y >= 2022) else 0)})
            if b == 0 and site == 2:
                rows.append({"pixel_id": p, "Year": y, "Season": 0, "buff_km": 2, "site_id": 1, "subwshed_id": f"S{p % 6}",
                             "time_fe_yearseason": f"{y}_0", "NDVI": 0.4 + (0.05 if y >= 2022 else 0)})
    saved = dict(_C.ACTIVE)
    try:
        _C.set_scenario(verbose=False, all_years=True, control_zones="1-5", treatment_year=2022, seasons="all", nonnegative=False)
        d = _C.build_treatment_columns(_pd.DataFrame(rows))
        if int(_C.LAST_DESIGN_INFO.get("contaminated_control_rows", 0)) == 0: bad("a treated pixel still serves as a control in another site")
        else: note("gap-filled rows out of estimation, only the scenario's rings loaded (every model: M24's gradient over your rings), treated pixels never controls across sites")
    finally:
        _C.ACTIVE.clear(); _C.ACTIVE.update(saved)

def check_v20_30():
    """v20.30: covariates per model (groups), negative covariates floored at panel level, memory first (95 % ceiling)."""
    import inspect as _i, numpy as _np, pandas as _pd, json as _j, tempfile as _tf
    sys.path.insert(0, HERE)
    import _common as _C, _prep_common as _P, _hardware as _H
    # covariates chosen per model
    if set(_C.COVARIATE_GROUPS) != {"all", "mean_temp_rain", "weather", "none"} or _C.resolve_covariates("mean_temp_rain")[0] != ["Tmean", "Rain"]:   # v20.45: no land-use group
        bad("covariate groups wrong")
    if "covariates" in _C.SCENARIO_KEYS: bad("covariates are still a panel-level scenario key (they must be chosen per model)")
    code = lambda nb: "\n".join("".join(c["source"]) for c in _j.load(open(nb, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
    prep_set = [os.path.basename(nb) for nb in glob.glob(os.path.join(HERE, "01_Panel_Preparation", "*.ipynb"))
                if "P11" not in nb and "covariates=COVARIATES" in code(nb)]
    models_missing = [os.path.basename(nb) for nb in glob.glob(os.path.join(HERE, "0[2-5]*", "*.ipynb")) if "covariates=COVARIATES" not in code(nb)]
    if prep_set: bad(f"panel preparation still sets covariates: {prep_set}")
    elif models_missing: bad(f"model notebooks without their own covariate choice: {models_missing[:4]}")
    else: note("covariates are chosen in each model (groups: all / mean_temp_rain / weather / none, or a list); preparation keeps every covariate")
    if "ALL_COVARIATE_COLUMNS" not in _i.getsource(_C.build_estimator_files): bad("P09 does not write every covariate column")
    # negatives floored at panel level, after the zero rule; floored zeros stay real downstream
    saved = (_P.ALLOW_NEGATIVE_COVARIATES, dict(_P.NEGATIVE_COVARIATE_RULE))
    try:
        _P.ALLOW_NEGATIVE_COVARIATES = False; _P.NEGATIVE_COVARIATE_RULE = {"Rain": "zero", "Tmax": "zero", "Tmean": "zero", "Tmin": "zero"}
        f = _pd.DataFrame({"NDVI": [0.4, 0.4, 0.4, -0.05], "Rain": [-1.5, 0.0, 5.0, 3.0], "Tmin": [-10.0, 18.0, 19.0, 20.0]})
        a, _ = _P.apply_missing_policy(f.copy(), stage="file")
        b, _ = _P.apply_missing_policy(a.copy(), stage="block")
        # v20.30: -10.0 C is the exporter's clamp on a MASKED cell -> missing, never a fake 0 C
        good = (a.Rain.iloc[0] == 0 and _np.isnan(a.Rain.iloc[1]) and _np.isnan(a.Tmin.iloc[0]) and b.Rain.iloc[0] == 0 and abs(b.NDVI.iloc[3] + 0.05) < 1e-9)
        if not good: bad(f"negative floor wrong: file {a.Rain.tolist()} {a.Tmin.tolist()} -> block {b.Rain.tolist()}")
        else: note("negative Rain / temperature floored to 0 at panel level (after the zero rule); floored zeros survive PASS B and the models")
    finally:
        _P.ALLOW_NEGATIVE_COVARIATES, _P.NEGATIVE_COVARIATE_RULE = saved
    if not (_C._usable([0.0], "Rain")[0] and not _C._usable([0.0], "NDVI")[0]): bad("load-time zero rule does not treat a floored 0 as real")
    if "FLOORED_COVARIATES" not in _i.getsource(_C.load_panel): bad("load_panel's own zero test ignores the floor")
    # memory first
    if getattr(_H, "MEMORY_CEILING", None) != 0.98 or not all(hasattr(_H, f_) for f_ in ("ram_budget_bytes", "gpu_budget_bytes", "fits", "memory_report")):
        bad("the 98 % memory governor is missing (v20.57: your rule, was 95 %)")
    _wc = _i.getsource(_H.worker_cap)
    if "every logical core" not in _wc.lower(): bad("worker pools are capped (v20.52: every logical core, your instruction)")
    if "ram_budget_bytes()" not in _wc: bad("worker pools are not sized by YOUR 98 % RAM rule (v20.52 had dropped it; v20.53 restored it)")
    if _C.GPU_MAX_ROWS is not None or "gpu_budget_bytes" not in _i.getsource(_C.gpu_capacity_rows): bad("GPU use is not decided by the 98 % VRAM ceiling")
    if not _C.LOAD_ALL_AT_ONCE or "_cached_or_read(" not in _i.getsource(_C.load_panel): bad("load_panel does not read the whole table at once")
    if _P.IN_MEMORY_BLOCKS or "MemBlock" not in _i.getsource(_P.run_pass_a) or "_block_frame(" not in _i.getsource(_P.prepare_pass_b_block):
        bad("PASS A -> PASS B in-RAM blocks are not wired (or are on by default where P03 -> P04 need shard files)")
    if "P.IN_MEMORY_BLOCKS = True" not in code(os.path.join(HERE, "01_Panel_Preparation", "P00_RUN_ALL_Panel_Preparation.ipynb")):
        bad("P00 does not keep PASS A blocks in RAM")
    rng = _np.random.default_rng(0); n = 4000
    _pix = rng.integers(1, 400, n).astype("int64")
    df_ = _pd.DataFrame({"pixel_id": _pix, "Year": rng.integers(2016, 2026, n).astype("int16"),
                         "Season": rng.integers(0, 4, n).astype("int8"), "buff_km": (_pix % 6).astype("int8"),     # v20.58: ONE ring per pixel (a pixel
                         "subwshed_id": "SW1", "NDVI": rng.uniform(0.1, 0.6, n).astype("float32"), "Rain": rng.uniform(0, 800, n).astype("float32"),   # whose ring
                         "Tmax": 33.0, "Tmean": 26.0, "Tmin": 19.0, "LandUse": 2, "site_id": 1, "first_treat_agri_year": 2022.0})               # differs leaves)
    df_ = df_.drop_duplicates(["pixel_id", "Year", "Season"]).reset_index(drop=True)                      # every pixel-year-season once
    import pyarrow as _pa, pyarrow.parquet as _pq
    d_ = _tf.mkdtemp(); fp = os.path.join(d_, "p.parquet"); _pq.write_table(_pa.Table.from_pandas(df_, preserve_index=False), fp, row_group_size=500)
    keep = (_C.PREPARED_PANEL, _C.ESTIMATOR_FILES_DIR, dict(_C.ACTIVE), list(_C.DEFAULT_COVARIATES))
    try:
        _C.PREPARED_PANEL = fp; _C.ESTIMATOR_FILES_DIR = os.path.join(d_, "none"); _C.clear_panel_cache()
        _C.set_scenario(verbose=False, all_years=True, seasons="all", covariates="weather")
        _C.LOAD_ALL_AT_ONCE = True; a_ = _C.load_panel(columns=_C.columns_for("NDVI"))
        _C.LOAD_ALL_AT_ONCE = False; b_ = _C.load_panel(columns=_C.columns_for("NDVI"))
        srt = lambda x: x.sort_values(["pixel_id", "Year", "Season", "NDVI"], kind="mergesort").reset_index(drop=True)
        if not srt(a_).equals(srt(b_)): bad("whole-table load differs from the row-group load")
        else: note("memory first: whole-table load == row-group load; RAM / VRAM used up to 98 % (v20.57), fallback beyond (PASS A -> B in RAM in P00)")
    finally:
        _C.LOAD_ALL_AT_ONCE = True; _C.PREPARED_PANEL, _C.ESTIMATOR_FILES_DIR = keep[0], keep[1]
        _C.ACTIVE.clear(); _C.ACTIVE.update(keep[2]); _C.DEFAULT_COVARIATES[:] = keep[3]; _C.clear_panel_cache()

def check_dedup_vectorised():
    """v20.11: resolve_duplicates must not loop in Python over duplicate groups (23M groups -> 9.5 h), and
    build_manifest must keep the handle it streams from."""
    import inspect as _i
    sys.path.insert(0, HERE)
    import _prep_common as _P
    src = _i.getsource(_P.resolve_duplicates)
    if "for key, group in" in src or ".groupby(list(group_keys)):" in src:
        bad("resolve_duplicates loops over duplicate groups in Python -- hours on millions of groups")
    else:
        note("resolve_duplicates is vectorised (one sort + groupby.first); log is a summary + sample")
    msrc = _i.getsource(_P.build_manifest)
    if "pf = pq.ParquetFile(final_path)" not in msrc or "pf.close()" not in msrc:
        bad("build_manifest lost its ParquetFile handle or does not close it")
    else:
        note("build_manifest streams from an open handle and closes it")
    csrc = open(os.path.join(HERE, "_common.py"), encoding="utf-8").read()
    for fn in ("def treatment_coverage", "def _result_is_empty", "def record_not_estimated"):
        if fn not in csrc: bad(f"_common.py missing {fn} (empty-coefficient diagnostics)")
    note("every model prints coverage after the scenario; a non-estimable outcome is refused and registered in NOT_ESTIMATED.csv")


ENGINE_CHECKS = [check_notebook_locks, check_syntax_and_calls, check_rules, check_validation_report, check_pixel_id_string_ops, check_pass_b_parallel, check_full_machine, check_atomic_panel_write, check_dedup_semantics, check_file_handles, check_missing_value_policy, check_universal_missing_policy, check_ingestion_and_paths, check_path_import_orders, check_demeaner_and_event_study, check_zero_policy_and_readiness, check_missingness_report, check_honest_and_group_missingness, check_pretrends_spec, check_no_placeholders, check_frozen_guard, check_yearly_first, check_near_duplicate_pixels, check_treatment_timing, check_panel_design_rules, check_sws_geometry, check_v20_29, check_v20_30_gpu_and_barrier, check_v20_34, check_v20_36, check_v20_37, check_v20_39, check_v20_43, check_v20_44, check_r_library, check_v20_54, check_v20_56, check_v20_58_out_of_core, check_v20_58_repeated_rows, check_v20_58_memory_batches, check_v20_35_structure, check_v20_30, check_dedup_vectorised]


def run():
    print(f"=== four-model bundle self-check: {HERE}")
    try:                                   # a private instance registry -- other pipelines on this machine must not change what is checked
        import _hardware as _Hh
        sys.path.insert(0, HERE); _Hh.INSTANCE_DIR = tempfile.mkdtemp(prefix="reward_selfcheck_instances_"); _Hh._SHARE_CACHE["v"] = None
    except Exception:
        pass
    print("--- A. this project (P00 + M01, M02, M16, M34; Python and R)")
    for f in PROJECT_CHECKS:
        try: f()
        except Exception as e: bad(f"{f.__name__} raised {type(e).__name__}: {e}")
    n_a = len(NOTES)
    print(f"--- B. the engine (the checks of the full pipeline's selfcheck.py on the engine this bundle shares with it)")
    mods = check_engines()
    for f in ENGINE_CHECKS:
        try: f(mods) if len(inspect.signature(f).parameters) else f()
        except Exception as e: bad(f"{f.__name__} raised {type(e).__name__}: {e}")
    print("=" * 70)
    if PROBLEMS:
        print(f"{len(PROBLEMS)} PROBLEM(S) -- fix these before running:")
        for p in PROBLEMS: print("  -", p)
        return 1
    print(f"CLEAN: {len(NOTES)} checks passed ({n_a} of this project, {len(NOTES) - n_a} of the engine). The four-model bundle is consistent."
          + ("" if R_STATE["ran"] else " -- the R checks did NOT run (R not found here): run this file where R is installed."))
    return 0

if __name__ == "__main__":
    sys.exit(run())
