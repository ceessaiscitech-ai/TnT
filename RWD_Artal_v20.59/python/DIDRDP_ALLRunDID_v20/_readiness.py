"""
_readiness.py -- which models can give a COMPLETE result on the data you actually have (v20.16).

`model_readiness()` measures the prepared panel -- not the notebooks -- for the facts that decide whether each
of the 45 models is identified, and classifies every model as

    complete               complete result expected (v20.38: was READY / READY_SETTINGS -- any settings are listed)
    (settings)             when a setting is needed (year window, balanced
                     footprint, yearly outcomes, ...)
    LIMITED          runs, but the result answers a narrower question than the model name promises
    BLOCKED          cannot produce a result on this data (a documented data gap; the model refuses cleanly)

The facts measured (streamed from the per-variable files / the panel, never loaded whole):
    treated / control pixels per period, and how many treated pixels are observed in the reference period
    (the export-footprint problem); number of clusters; number of treatment cohorts among treated pixels and
    whether never-treated units exist; per-outcome seasonal vs annual coverage; presence of the external inputs
    (ground-truth file, instrument file, fund-release table, crosswalk); index-level jumps between years.

Usage (any notebook, after CELL 1):
    import _readiness as R
    R.model_readiness()                      # prints the matrix, writes results/MODEL_READINESS.csv and .md
    R.model_readiness(facts=R.FACTS_ARTAL)   # the assessment for a known dataset without re-measuring
"""
import os, json, math
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------- what each model needs
# requirement keys: treated_continuity (treated pixels seen in both pre and post), clusters (min), cohorts (min),
# never_treated, external (file), rings (>=2 distinct control rings), seasons (needs seasonal rows),
# dose (dose column with variation), switchers, landuse_groups (>=2), balanced_units (a treated UNIT at the
# cluster level), pre_periods (min), post_periods (min)
MODELS = {
 "M01": ("Canonical 2x2 TWFE",               dict(pre_periods=1, post_periods=1, clusters=2)),
 "M02": ("Event study",                       dict(pre_periods=2, post_periods=1, clusters=2)),
 "M03": ("Doubly robust AIPW",                dict(pre_periods=1, post_periods=1)),
 "M04": ("Changes-in-changes",                dict(pre_periods=1, post_periods=1)),
 "M05": ("Callaway-Sant'Anna",                dict(cohorts=2, never_treated=True)),
 "M06": ("Continuous dose-response",          dict(dose=True)),
 "M07": ("Surrogate index",                   dict(external="ground_truth", sws_seasons=6)),   # v20.58: the BM ground data enter as sub-watershed x
                                                  # season MEANS -- >= 6 of them (the model's own rule; one sub-watershed has 3 seasons)
 "M08": ("Instrumented DiD",                  dict(external="instrument")),
 "M09": ("Sun-Abraham",                       dict(cohorts=2, never_treated=True)),
 "M10": ("Triple differences",                dict(landuse_groups=2)),
 "M11": ("Synthetic DiD",                     dict(balanced_units=True, pre_periods=3)),
 "M12": ("Chained DiD",                       dict(pre_periods=2, post_periods=1)),
 "M13": ("Switcher DiD",                      dict(switchers=True)),
 "M14": ("PSM DiD",                           dict(pre_periods=1, post_periods=1)),
 "M15": ("Placebo false timing",              dict(pre_periods=3)),
 "M16": ("Joint pre-trends F",                dict(pre_periods=2)),
 "M17": ("Global Moran's I",                  dict()),
 "M18": ("Local Moran / LISA",                dict()),
 "M19": ("Variance decomposition ICC",        dict(clusters=2)),
 "M20": ("Spatial heterogeneity Q/I2",        dict(clusters=3, sws=2)),   # v20.58: heterogeneity ACROSS sub-watersheds: >= 2 of them
 "M21": ("Season-to-annual aggregation",      dict(seasons=True)),
 "M22": ("Goodman-Bacon",                     dict(cohorts=2)),
 "M23": ("Wild-cluster bootstrap",            dict(clusters=2)),
 "M24": ("Spillover ring gradient",           dict(rings=2)),
 "M25": ("Permutation inference",             dict(clusters=2)),
 "M26": ("Treatment x covariate",             dict(pre_periods=1, post_periods=1)),
 "M27": ("BJS imputation",                    dict(cohorts=1, never_treated=True)),
 "M28": ("Gardner two-stage",                 dict(cohorts=1, never_treated=True)),
 "M29": ("Exposure duration",                 dict(post_periods=2)),
 "M30": ("Cohort heterogeneity",              dict(cohorts=2)),
 "M31": ("Stacked DiD",                       dict(cohorts=2, never_treated=True)),
 "M32": ("Extended TWFE",                     dict(cohorts=1, never_treated=True)),
 "M33": ("Entropy balancing",                 dict(pre_periods=1, post_periods=1)),
 "M34": ("HonestDiD sensitivity",             dict(pre_periods=2, post_periods=1)),
 "M35": ("Quantile DiD",                      dict(pre_periods=1, post_periods=1)),
 "M36": ("Interactive FE (Bai)",              dict(pre_periods=3, balanced_units=True)),
 "M37": ("Matrix completion",                 dict(balanced_units=True, pre_periods=3)),
 "M38": ("Generalised synthetic control",     dict(balanced_units=True, pre_periods=3)),
 "M39": ("ML CATE (forest)",                  dict(pre_periods=1, post_periods=1)),
 "M40": ("Double ML",                         dict(pre_periods=1, post_periods=1)),
 "M41": ("Meta-learners",                     dict(pre_periods=1, post_periods=1)),
 "M42": ("DR-learner",                        dict(pre_periods=1, post_periods=1)),
 "M43": ("Honest causal forest",              dict(pre_periods=1, post_periods=1)),
 "M44": ("BART-style",                        dict(pre_periods=1, post_periods=1)),
 "M45": ("ML synthetic control",              dict(balanced_units=True, pre_periods=3)),   # v20.58: the ring series are the donors (the
                                                  # v20.57 design, as M11 / M36-M38): v20.40's ">= 3 never-programme sub-watersheds" is gone --
                                                  # it said "the data do not meet M45's requirements" and skipped the R route, then the engine
                                                  # estimated M45 anyway on the ring series
}
INFERENCE = {"M23", "M25"}                     # these are HOW to report M01, not separate effects
CORE_FOR_PAPER = ["M01", "M02", "M23", "M25", "M16", "M15", "M34", "M24", "M03", "M04"]

# ----------------------------------------------------------------------------- facts from your Artal logs
FACTS_ARTAL = {
    "source": "measured from your P01/PASS B/M01/M02 logs (TST_Artal extract, 2015-2025 panel, 101,137,115 rows)",
    "years": list(range(2015, 2026)), "treatment_year": 2022, "exclude_transition_year": False, "seasons_present": [0, 1, 2, 3],
    "clusters": 6, "control_rings": [1, 2, 3, 4, 5],
    # v20.18: AFTER the no-data rule (NaN and exact 0 = missing) only 548 core pixels carry usable NDVI in 2015-2024
    # (your M34 log of 20 Sep); before the rule the panel showed 4,438 core pixels present -- i.e. ~88 % of the
    # core rows in the 2015-2024 export are masked. 2025 (new export) has 465,714 usable core pixels.
    "treated_pixels_by_year": {y: 548 for y in range(2015, 2025)} | {2025: 465714},
    "treated_pixels_by_year_before_nodata_rule": {y: 4438 for y in range(2015, 2025)} | {2025: 881995},
    "control_pixels_by_year": {y: 1706081 for y in range(2015, 2025)} | {2025: 2875156},
    "treated_pixels_in_ref_by_year": {y: 548 for y in range(2015, 2026)},
    "core_nodata_share_2015_2024": 0.88,
    # v20.24: stated by you (22 Sep 2026): the ANNUAL composite (Season 0) is complete for every year; the seasonal
    # rows have gaps. Models estimate on the annual rows first (seasons = 'auto').
    "annual_composite_complete": True,
    "cohorts_among_treated": 1, "never_treated_units": False,
    "dose_variation": False, "landuse_groups": 2, "switchers": True,   # landuse_groups ASSUMED (2 classes) -- measure_panel() checks it
    "treated_cluster_units": 0,                                  # no sub-watershed is entirely treated
    "yearly_only_outcomes": ["ESI", "RUSLE", "WSI", "WSSI"],
    "external": {"ground_truth": False, "instrument": False, "fund_release": True, "crosswalk": True},
    "level_jump_years": {"NDVI": 2025},                          # 0.37-0.40 -> 0.58 in the 2025 export
    "_assumed": "landuse_groups ASSUMED",
    "covariates_flip_sign": True,                                 # measured on this extract (20 Sep)
}


# ----------------------------------------------------------------------------- v20.40: YOUR current panel, measured
_LVL25 = {o: 2025 for o in ("NDVI", "AGB", "LAI", "EVI", "SAVI", "VCI", "VHI")}
FACTS_HALIGERI = {
    "source": ("measured 23 Sep 2026 from your M01 effect-size diagnostics (effect_size_diagnostics_NDVI.csv and the "
               "_yearly files), site_id_mapping.csv and the P00 log -- Haligeri (SWS 7, Phase 1) staged in TST_Artal; "
               "scenario ctrl1-3_treat2022_all_nonneg_covMeanTempRain_yr2018-end"),
    "site": "Haligeri (SWS 7, Phase 1)",
    "years": list(range(2018, 2026)), "treatment_year": 2022, "exclude_transition_year": False, "seasons_present": [0, 1, 2, 3],
    "n_sws": 1, "clusters": 8, "cluster_kind": "years (one sub-watershed = one cluster; the engine clusters on the 8 years)",
    "control_rings": [1, 2, 3],
    "treated_pixels_by_year": {y: 619271 for y in range(2018, 2025)} | {2025: 621909},
    "control_pixels_by_year": {y: 1248914 for y in range(2018, 2025)} | {2025: 1252048},
    "treated_pixels_in_ref_by_year": {y: 619271 for y in range(2018, 2025)} | {2025: 313308},   # 50.4 % linked in 2025
    "cohorts_among_treated": 1, "never_treated_units": True,          # the control rings are never treated
    "dose_variation": False, "landuse_groups": 2, "switchers": True, "treated_cluster_units": 0,
    "yearly_only_outcomes": ["ESI", "RUSLE", "WSI", "WSSI"],
    "external": {"ground_truth": False, "instrument": False, "fund_release": True, "crosswalk": True},
    "level_jump_years": _LVL25,
    "implementation_year_source": "ASSUMED",                          # Phase 1: blank in data/sites/sites.csv
    "linkage_2025": 0.504, "overlap_needed_95": 0.70, "grid_shift_m": 3.0, "repeat_share": 0.0,
    "unusable_pre_outcomes": ["LSWI", "NDMI"], "fund_first_season": "Oct 2024 (file covers 2024-10 .. 2026-07)",
    "untreated_sws": 0,                                               # every sub-watershed is a programme area
    "results_before_v20_38": True,
    "_assumed": "landuse_groups ASSUMED (2 classes) -- measure_panel() checks it on your machine",
}

# ----------------------------------------------------------------------------- v20.40: the 20-sub-watershed run, PROJECTED
FACTS_POOLED_20 = dict(FACTS_HALIGERI) | {
    "source": ("PROJECTION (not measured): all 20 sub-watersheds pooled, Phase-1 implementation years filled in "
               "data/sites/sites.csv AND DIFFERENT from Phase 2's 2022 (two cohorts; if Phase 1 also began in 2022 the staggered "
               "models M05, M09, M22, M30, M31 stay as they are now), the panel rebuilt at PIXEL_OVERLAP_MIN 0.65 and "
               "2025 held out (POST_YEARS) or re-exported"),
    "site": "all 20 sub-watersheds (pooled)", "n_sws": 20, "clusters": 20, "cluster_kind": "sub-watersheds",
    "external": {"ground_truth": True, "instrument": False, "fund_release": True, "crosswalk": True},   # BM surrogates (P08b)
    "cohorts_among_treated": 2, "dose_variation": True, "treated_cluster_units": 20,
    "treated_pixels_in_ref_by_year": {y: 619271 for y in range(2018, 2025)} | {2025: 590814},  # ~95 % linked at 0.65
    "level_jump_years": {}, "implementation_year_source": "registry", "linkage_2025": 0.95, "results_before_v20_38": False,
}


# ----------------------------------------------------------------------------- measuring the panel
def measure_panel(C, outcomes=None, sample_rows=None):
    """Stream the facts from the per-variable files (or the panel). Returns a facts dict like FACTS_ARTAL."""
    import pyarrow.parquet as pq
    outcomes = outcomes or (C.SELECTED_OUTCOMES if getattr(C, "SELECTED_OUTCOMES", None) else ["NDVI"])
    first = outcomes[0]
    p = C.estimator_file_path(first) if hasattr(C, "estimator_file_path") else None
    if not p or not os.path.exists(p): p = C.PREPARED_PANEL
    pf = pq.ParquetFile(p)
    cols = [c for c in ("pixel_id", "Year", "Season", "buff_km", "subwshed_id", "site_id", "first_treat_agri_year",
                        "dose_per_subwshed", "dose_amount_sws", "LandUse", first) if c in pf.schema_arrow.names]
    cols = list(dict.fromkeys(cols))
    sws_set = set(); ymean = {}; dose_seen = []                                 # v20.40
    tr_year, ct_year, per_pix_years = {}, {}, {}
    clusters, cohorts, land, dose = set(), set(), set(), set()
    ring_set = set(); n_seen = 0; seasons = set()
    cluster_all_treated = {}
    try:
        for i in range(pf.num_row_groups):
            d = pf.read_row_group(i, columns=cols).to_pandas()
            if sample_rows and n_seen > sample_rows: break
            n_seen += len(d)
            bk = pd.to_numeric(d["buff_km"], errors="coerce")
            tr = (bk == C.TREAT_CORE_BUFFKM).values
            seasons.update(int(x) for x in pd.unique(d["Season"]))
            ring_set.update(int(x) for x in pd.unique(bk.dropna()) if x != C.TREAT_CORE_BUFFKM)
            if "subwshed_id" in d:
                clusters.update(d["subwshed_id"].astype(str).unique().tolist())
                g = d.groupby(d["subwshed_id"].astype(str))
                for k, sub in g:
                    a = cluster_all_treated.setdefault(k, [0, 0]); a[0] += int(tr[sub.index].sum()); a[1] += len(sub)
            if "first_treat_agri_year" in d:
                cohorts.update(pd.to_numeric(d.loc[tr, "first_treat_agri_year"], errors="coerce").dropna().astype(int).unique().tolist())
            if "LandUse" in d: land.update(pd.unique(d["LandUse"].dropna()).tolist())
            if "site_id" in d: sws_set.update(int(x) for x in pd.to_numeric(d["site_id"], errors="coerce").dropna().unique() if int(x) != 0)
            if first in d and "Season" in d:                                    # yearly means of the annual rows, by group
                a = d[pd.to_numeric(d["Season"], errors="coerce") == 0]
                v = pd.to_numeric(a[first], errors="coerce"); g = (pd.to_numeric(a["buff_km"], errors="coerce") == C.TREAT_CORE_BUFFKM)
                for (yy, gg), s_ in v.groupby([a["Year"].astype(int), g]).agg(["sum", "count"]).iterrows():
                    acc = ymean.setdefault((int(yy), bool(gg)), [0.0, 0]); acc[0] += float(s_["sum"]); acc[1] += int(s_["count"])
            if "dose_amount_sws" in d:
                q = d[pd.to_numeric(d["dose_amount_sws"], errors="coerce") > 0]
                if len(q): dose_seen.append(int(pd.to_numeric(q["Year"], errors="coerce").min()))
            if "dose_per_subwshed" in d: dose.update(np.round(pd.to_numeric(d["dose_per_subwshed"], errors="coerce").dropna(), 6).unique().tolist())
            for y, sub in d.groupby("Year"):
                y = int(y); t_ = tr[sub.index]
                tr_year.setdefault(y, set()).update(sub.loc[t_, "pixel_id"].unique().tolist())
                ct_year.setdefault(y, set()).update(sub.loc[~t_, "pixel_id"].unique().tolist())
    finally:
        try: pf.close()
        except Exception: pass
    years = sorted(tr_year)
    ref = int(C.ACTIVE["post_cutoff"]) - 1
    ref_tr = tr_year.get(ref, set())
    facts = {
        "source": f"measured from {p} ({n_seen:,} rows)", "years": years, "treatment_year": int(C.ACTIVE["treatment_year"]),
        "seasons_present": sorted(seasons), "clusters": len(clusters), "control_rings": sorted(ring_set),
        "treated_pixels_by_year": {y: len(tr_year[y]) for y in years},
        "control_pixels_by_year": {y: len(ct_year[y]) for y in years},
        "treated_pixels_in_ref_by_year": {y: len(tr_year[y] & ref_tr) for y in years},
        "cohorts_among_treated": len(cohorts), "never_treated_units": False,
        "dose_variation": len(dose) > 1, "landuse_groups": len(land), "switchers": False,   # measured just below (v20.58)
        "treated_cluster_units": sum(1 for k, (a, b) in cluster_all_treated.items() if b and a == b),
        "yearly_only_outcomes": [], "external": {}, "level_jump_years": {},
    }
    # v20.58: SWITCHERS (M13, de Chaisemartin & D'Haultfoeuille) = treated series observed before AND after the start: D = treated x post
    # switches ON. Until v20.57 this fact was hard-coded False ("a watershed programme never switches off" -- switching off is not needed),
    # so M13 was reported as a data gap on every panel while R's DIDmultiplegtDYN computed it.
    _cut = int(C.ACTIVE.get("post_cutoff") or C.ACTIVE.get("treatment_year") or 0)
    _pre_tr = set().union(*[v for y_, v in tr_year.items() if y_ < _cut]) if any(y_ < _cut for y_ in tr_year) else set()
    _post_tr = set().union(*[v for y_, v in tr_year.items() if y_ >= _cut]) if any(y_ >= _cut for y_ in tr_year) else set()
    facts["n_switchers"] = len(_pre_tr & _post_tr); facts["switchers"] = facts["n_switchers"] > 0
    # v20.40: the sub-watershed is the cluster; ONE sub-watershed -> the engine clusters on the years
    if not sws_set:                                   # the per-variable files may not carry site_id: ask the panel itself
        try:
            sws_set = {int(x) for x in C.sites_in_panel() if int(x) != 0}
        except Exception:
            pass
    facts["n_sws"] = len(sws_set) or 1                # no sub-watershed id at all = a single-site extract
    # cohorts = distinct implementation years among the treated sub-watersheds when the fund file gives none
    if facts["cohorts_among_treated"] == 0:
        try:
            if C.ACTIVE.get("use_site_years") and sws_set:
                facts["cohorts_among_treated"] = len({C.ACTIVE["site_years"].get(int(s), C.ACTIVE["treatment_year"]) for s in sws_set})
            else:
                facts["cohorts_among_treated"] = 1
        except Exception:
            facts["cohorts_among_treated"] = 1
    if facts["control_rings"]:                        # the control rings never receive the programme: a never-treated comparison
        facts["never_treated_units"] = True
    facts["untreated_sws"] = 0                                                  # the export holds programme sub-watersheds only
    facts["subwshed_units"] = facts["clusters"]
    _min = int(getattr(C, "MIN_SWS_CLUSTERS", 6))
    facts["clusters"] = facts["n_sws"] if facts["n_sws"] >= _min else len(years)
    facts["cluster_kind"] = ("sub-watersheds" if facts["n_sws"] >= _min else
                             f"years ({facts['n_sws']} sub-watershed(s): fewer than {_min} cannot be the clusters)")
    try:
        import _sites as _S
        src = {_S.treatment_year_source(s) for s in sws_set} if sws_set else set()
        facts["implementation_year_source"] = "ASSUMED" if "ASSUMED" in src else ("registry" if src else "unknown")
    except Exception:
        pass
    # a LEVEL JUMP: both groups move the same way by > 3x the typical year-to-year change (a processing change)
    try:
        yrs_ = sorted({k[0] for k in ymean})
        m = {g: [ymean[(y, g)][0] / ymean[(y, g)][1] if ymean.get((y, g), [0, 0])[1] else np.nan for y in yrs_] for g in (True, False)}
        dt, dc = np.diff(m[True]), np.diff(m[False])
        jumps = []
        for i in range(len(dt)):
            rest_t = np.delete(np.abs(dt), i); rest_c = np.delete(np.abs(dc), i)
            if len(rest_t) >= 2 and np.sign(dt[i]) == np.sign(dc[i]) and abs(dt[i]) > 3 * np.nanmedian(rest_t) and abs(dc[i]) > 3 * np.nanmedian(rest_c):
                jumps.append(int(yrs_[i + 1]))
        if jumps: facts["level_jump_years"] = {first: jumps}
    except Exception:
        pass
    if dose_seen: facts["fund_first_season"] = f"{min(dose_seen)} (first year with a dose on the treated area)"
    ref_tr_n = len(ref_tr)
    if years and tr_year.get(years[-1]):
        facts["linkage_2025"] = len(tr_year[years[-1]] & ref_tr) / max(1, len(tr_year[years[-1]]))
    # never-treated: any pixel whose first_treat is missing / inf among controls
    try:
        pf2 = pq.ParquetFile(p); d0 = pf2.read_row_group(0, columns=[c for c in ("first_treat_agri_year",) if c in pf2.schema_arrow.names]).to_pandas(); pf2.close()
        if "first_treat_agri_year" in d0:
            facts["never_treated_units"] = bool(d0["first_treat_agri_year"].isna().any())
    except Exception:
        pass
    # outcome coverage: seasonal vs yearly, and year-to-year level jumps
    for o in outcomes:
        try:
            cov = C.outcome_coverage(o, verbose=False)
            seas = cov[cov.Season_code != 0]; yr = cov[cov.Season_code == 0]
            if seas.finite.sum() == 0 and yr.finite.sum() > 0: facts["yearly_only_outcomes"].append(o)
            if "Year" in yr.columns:                                            # v20.40: a usable pre-period?
                pre_ok = yr[(pd.to_numeric(yr["Year"], errors="coerce") < facts["treatment_year"]) & (yr.finite > 0)]
                if pre_ok["Year"].nunique() < 2: facts.setdefault("unusable_pre_outcomes", []).append(o)
        except Exception:
            pass
    facts["external"] = {
        "ground_truth": any(v.startswith("GND_") for v in getattr(C, "DERIVED_VARIABLES", {})) or os.path.exists(os.path.join(C.RESULTS_ROOT, "P08", "ground_truth_outcomes.csv")) or
                        os.path.exists(os.path.join(os.path.dirname(C.PREPARED_PANEL), "ground_truth_outcomes.csv")),
        "instrument": os.path.exists(os.path.join(os.path.dirname(C.PREPARED_PANEL), "rollout_instrument.csv")),
        "fund_release": os.path.exists(getattr(C, "FUND_RELEASE_PATH", "")) if getattr(C, "FUND_RELEASE_PATH", "") else False,
        "crosswalk": os.path.exists(getattr(C, "SUBWSHED_CROSSWALK_PATH", "")) if getattr(C, "SUBWSHED_CROSSWALK_PATH", "") else False,
    }
    return facts


# ----------------------------------------------------------------------------- v20.40: PANEL-WIDE CAVEATS
def panel_caveats(facts):
    """Every panel-wide caveat as WHAT is missing, WHY it matters, WHAT fixes it and WHICH models it touches.
    `limits` = it turns an otherwise complete model into 'limited'."""
    ty = int(facts["treatment_year"]); out = []
    def add(cid, title, missing, why, fix, affects, limits):
        out.append({"id": cid, "caveat": title, "missing": missing, "why": why, "fix": fix, "affects": affects, "limits": limits})
    if facts.get("n_sws", 2) == 1:
        add("C1", "ONE sub-watershed", "other sub-watersheds (treated areas)",
            f"the sub-watershed is the cluster; one cluster cannot carry cluster-robust inference, so the engine clusters "
            f"on the {len(facts['years'])} years -- each year's core-vs-ring contrast is ONE independent draw. Standard "
            f"errors are honest but wide, and nothing separates the programme from anything else that hit this "
            f"sub-watershed's core and not its rings in the same years.",
            "the pooled 20-sub-watershed run (every model pools the sub-watersheds of its panel automatically -- v20.57: after the fragment rule)", "every model", True)
    if facts.get("implementation_year_source") == "ASSUMED":
        add("C2", "implementation year ASSUMED", "the Phase-1 implementation year (blank in data/sites/sites.csv)",
            f"{ty} is used. If works began earlier, the 'pre' years already hold treated years and every effect is "
            f"pulled toward zero; if later, 'post' years hold untreated years (same bias).",
            "date it: TREATMENT_TIMING = 'fund' (your fund workbook, the v20.57 default) or fill treatment_year for the Phase-1 rows of data/sites/sites.csv ('registry'); every model uses it when it runs", "every model", True)
    lj = sorted({y for v in facts.get("level_jump_years", {}).values() for y in ([v] if isinstance(v, int) else v)})
    tr = facts["treated_pixels_by_year"]; inref = facts["treated_pixels_in_ref_by_year"]
    weak = [y for y in facts["years"] if tr.get(y) and inref.get(y, 0) < 0.9 * tr[y]]
    if lj or weak:
        yrs = sorted(set(lj) | set(weak))
        add("C3", f"{', '.join(map(str, yrs))} is a different export", "one export for every year, on one pixel grid",
            (f"levels jump for BOTH groups in {lj} ({', '.join(sorted(facts.get('level_jump_years', {})))}) -- processing "
             f"changed; " if lj else "") +
            (f"only {facts.get('linkage_2025', 0):.0%} of the treated rows of {weak} have a pre-period history (grid "
             f"shifted ~{facts.get('grid_shift_m', 3):.0f} m); unlinked rows identify nothing and composition changes. "
             f"Your raw NDVI difference (+0.018) comes almost entirely from 2025; 2022-2024 on the same pixels: +0.003." if weak else ""),
            f"rebuild P00 at PIXEL_OVERLAP_MIN 0.65 (links ~95 %), report POST_YEARS to {max(y for y in facts['years'] if y not in yrs)} "
            f"as the main result and the full window as robustness -- or re-export {yrs} with the earlier processing",
            "every model using those years (event time +3 in M02 most)", True)
    if facts.get("unusable_pre_outcomes"):
        add("C4", "outcomes without a usable pre-period", f"pre-{ty} values of {facts['unusable_pre_outcomes']}",
            "their core-vs-ring gap is exactly 0 or missing before 2025 -- no baseline, no DiD",
            "re-export those indices for the pre-period, or leave them out of every model", "those outcomes only", False)
    if facts.get("fund_first_season"):
        add("C5", "fund releases before the file starts", f"releases from implementation ({ty}) to the file's start ({facts['fund_first_season']})",
            "the dose (amount released, intensity per ha) is unknown -- left missing, not 0 -- for the first post seasons",
            "a fund file from the programme start", "dose models (M06, M27, M30 and dose-intensity variants)", True)
    if not facts["external"].get("ground_truth"):
        add("C6", "ground data are post-period only", "benchmark-site (BM) values before 2022",
            "your BM data cover 2023-2024: no DiD on ground values alone. They enter as SURROGATE outcomes (GND_*): each "
            "sub-watershed's BM mean (the mean of its three sites) is mapped to the satellite indices of its treatment area, "
            "season by season, and predicted for every pixel and year -- which needs >= 6 sub-watershed x season means",
            "the pooled run over the sub-watersheds (P00 P08b fits the surrogates automatically)", "M07", False)
    if facts.get("external", {}).get("ground_truth") and facts.get("n_sws", 1) >= 2:
        add("C9", "ground outcomes are surrogates", "a measured ground baseline (the BM data start in 2023)",
            "GND_* outcomes are satellite indices re-expressed in ground units by a fitted mapping: their SE leaves out that "
            "first-stage error, and the mapping is learned after implementation only",
            "read M07 with its leave-one-out R2 (ground_surrogate_fit.csv) and its design-based SE; a pre-2022 ground survey would remove this",
            "M07", True)
    add("C7", "no structure-level data", "locations, amounts and completion dates of works inside each sub-watershed",
        "the dose is uniform over each treatment area; within-sub-watershed intensity and heterogeneity are not identified",
        "a structures table -> C.within_sws_dose() / WITHIN_SWS_DOSE_PATH (ready in the code)", "within-SWS dose and heterogeneity", False)
    if facts.get("results_before_v20_38"):
        add("C8", "results produced before v20.38", "valid standard errors in earlier result files",
            "they clustered on within-sub-watershed units that are not clusters; SEs of ~1e-5 understated the uncertainty "
            "(the year-to-year core-vs-ring gap varies by ~0.01)", "re-run the models with v20.38+", "every earlier result file", False)
    return out


# ----------------------------------------------------------------------------- the assessment
def assess(facts, treatment_year=None):
    ty = int(treatment_year or facts["treatment_year"]); ref = ty - 1
    years = facts["years"]; pre = [y for y in years if y < ty]
    post = [y for y in years if y >= ty + (1 if facts.get("exclude_transition_year") else 0)]   # v20.26: transition year out
    tr = facts["treated_pixels_by_year"]; ct = facts["control_pixels_by_year"]; inref = facts["treated_pixels_in_ref_by_year"]
    # footprint: periods whose treated population is mostly NOT the reference population
    bad_years = [y for y in years if tr.get(y, 0) and inref.get(y, 0) < 0.5 * tr[y]]
    jump_years = sorted({y for v in facts.get("level_jump_years", {}).values() for y in ([v] if isinstance(v, int) else v)})
    contaminated = sorted(set(bad_years) | set(jump_years))
    clean_post = [y for y in post if y not in contaminated]
    clean_pre = [y for y in pre if y not in contaminated]
    settings = []
    if contaminated:
        settings.append(f"POST_YEARS = {len(clean_post)} (post period {clean_post[0]}-{clean_post[-1]}; {contaminated} carry a different "
                        f"treated population / index level)" if clean_post else "no clean post year")
        settings.append("BALANCED_PIXELS = True in M02 (or C.common_pixel_mask) when the window includes " + str(contaminated))
    base_ok = bool(clean_pre) and bool(clean_post) and min(tr.get(y, 0) for y in clean_pre + clean_post) > 0
    rows = []
    try:                                                   # v20.58: the project's models only (_paths.PIPELINE_MODELS; None = all 45)
        import _paths as _PPr; _pm = tuple(getattr(_PPr, "PIPELINE_MODELS", None) or ())
    except Exception:
        _pm = ()
    for mid, (name, req) in MODELS.items():
        if _pm and mid not in _pm: continue
        status, why, extra = "complete", [], []
        if not base_ok:
            status, why = "incomplete-need data", ["no clean pre AND post period with treated pixels"]
        if req.get("pre_periods", 0) > len(clean_pre):
            status = "incomplete-need data"; why.append(f"needs {req['pre_periods']} pre periods, {len(clean_pre)} clean")
        if req.get("post_periods", 0) > len(clean_post):
            status = "incomplete-need data" if not clean_post else status; why.append(f"needs {req['post_periods']} post periods, {len(clean_post)} clean")
        if req.get("clusters", 0) > facts["clusters"]:
            status = "incomplete-need data"; why.append(f"needs {req['clusters']} clusters, panel has {facts['clusters']}")
        if req.get("cohorts", 0) >= 2 and facts["cohorts_among_treated"] < 2:
            status = "limited" if mid in ("M22",) else "incomplete-need data"
            why.append(f"needs >=2 treatment cohorts; treated pixels form {facts['cohorts_among_treated']} cohort"
                       + (" (single site) -- collapses to the 2x2 design M01 already gives" if mid in ("M05", "M09", "M30", "M31") else ""))
        if req.get("cohorts", 0) == 1 and req.get("never_treated") and not facts["never_treated_units"] and facts["cohorts_among_treated"] < 2:
            status = "limited"; why.append("imputation from never/not-yet-treated units: with one cohort and no never-treated flag it reduces to the 2x2 comparison")
        if req.get("never_treated") and facts["cohorts_among_treated"] >= 2 and not facts["never_treated_units"]:
            status = "limited"; why.append("no never-treated units: only not-yet-treated comparisons, late cohorts unidentified")
        if req.get("external"):
            if not facts["external"].get(req["external"], False):
                status = "incomplete-need data"; why.append({"ground_truth": "needs ground_truth_outcomes.csv (field survey / benchmark workbooks linked by P08)",
                                                 "instrument": "needs rollout_instrument.csv (no instrument for programme timing exists)"}[req["external"]])
        if req.get("dose") and not facts["dose_variation"]:
            status = "incomplete-need data"; why.append("dose_per_subwshed does not vary across treated units (one site, one dose)")
        if req.get("landuse_groups", 0) > facts["landuse_groups"]:
            status = "incomplete-need data"; why.append("needs >=2 land-use groups among treated pixels")
        elif req.get("landuse_groups") and "ASSUMED" in json.dumps(facts.get("_assumed", "")):
            extra.append("assumes LandUse varies among the treated pixels -- run R.model_readiness() on the machine to confirm")
        if req.get("untreated_units", 0) > facts.get("untreated_sws", 0):           # v20.40
            status = "incomplete-need data"; why.append(f"needs >= {req['untreated_units']} sub-watersheds never in the programme as donor units; "
                                                        f"all your sub-watersheds are programme areas (the control rings are the comparison in the other models)")
        if req.get("switchers") and not facts["switchers"]:
            status = "incomplete-need data"; why.append("needs treated series observed before AND after their start (the treatment switches on) -- none in this panel")
        if req.get("balanced_units"):                 # v20.58: the CORE-vs-RING SERIES design of M11 / M36-M38 / M45 (v20.57): the treated units
            _ns = max(1, len([s_ for s_ in facts["seasons_present"] if s_]))   # are the core series, the donors the ring series (never treated)
            if len(facts.get("control_rings", [])) * _ns < 2:
                status = "incomplete-need data"; why.append("needs >= 2 control ring series as donors (the core-vs-ring series design: a control "
                                                            "ring x season is one series)")
        if req.get("sws", 0) > int(facts.get("n_sws", 1) or 1):                   # v20.58
            status = "incomplete-need data"; why.append(f"needs >= {req['sws']} sub-watersheds, each with its own DiD (heterogeneity ACROSS "
                                                        f"sub-watersheds); this panel holds {int(facts.get('n_sws', 1) or 1)} -- the pooled run")
        if req.get("sws_seasons", 0):                                               # v20.58
            _nsm = int(facts.get("n_sws", 1) or 1) * max(1, len([s_ for s_ in facts["seasons_present"] if s_]))
            if req["sws_seasons"] > _nsm:
                status = "incomplete-need data"; why.append(f"needs >= {req['sws_seasons']} sub-watershed x season means of the ground data "
                                                            f"(this panel gives {_nsm}) -- the pooled run over the sub-watersheds")
        if req.get("rings", 0) > len(facts["control_rings"]):
            status = "incomplete-need data"; why.append("needs >=2 control rings")
        if req.get("seasons") and 0 in facts["seasons_present"] and len([s for s in facts["seasons_present"] if s]) < 2:
            status = "incomplete-need data"; why.append("needs seasonal rows")
        if status == "complete" and contaminated:
            status = "complete"
        if mid == "M02" and status in ("complete", "complete"):
            extra.append("2025 coefficient = footprint/level change, not an effect; read identification_note")
        if mid in INFERENCE and status in ("complete", "complete"):
            extra.append(f"report p_wild / permutation p instead of t-stats ({facts['clusters']} clusters)")
        if mid == "M01" and status in ("complete", "complete"):
            extra.append(f"treated group = {min(tr.get(y,0) for y in clean_pre+clean_post):,} pixels seen throughout"
                         + ("; weather covariates flip the raw sign -- report the covariate-adjusted estimate"
                            if facts.get("covariates_flip_sign") else ""))
        rows.append({"model": mid, "name": name, "status": status, "reason": "; ".join(why) if why else "identified on this panel",
                     "settings": "; ".join(settings) if status == "complete" else "", "notes": "; ".join(extra)})
    out = pd.DataFrame(rows)
    # v20.40: panel-wide caveats turn an otherwise complete model into 'limited'; every row says what is missing and
    # what would complete it
    cav = panel_caveats(facts); lim = [c for c in cav if c["limits"]]
    def _touch(c, mid):
        a = c["affects"]
        return a.startswith("every") or mid in a
    miss, comp, stat, own_miss, own_fix, cav_ids = [], [], [], [], [], []
    for rw in out.itertuples():
        st = rw.status; hits = [c for c in lim if _touch(c, rw.model)]
        if st == "complete" and hits: st = "limited"
        own_m = rw.reason if rw.status != "complete" else ""
        ids = [c["id"] for c in cav if _touch(c, rw.model) and (c["limits"] or c["id"] in ("C5", "C6"))]
        m_ = ([own_m] if own_m else []) + [f"{c['id']}: {c['missing']}" for c in cav if c["id"] in ids]
        f_ = []
        rs = rw.reason.lower()
        if "clusters" in rs or "cohort" in rs or "dose" in rs or "cluster (sub-watershed) level" in rs:
            f_.append("the pooled 20-sub-watershed run" + (" with Phase-1 years filled (two cohorts)" if "cohort" in rs else ""))
        if "ground_truth" in rs: f_.append("ground_truth_outcomes.csv (field outcomes per site x year)")
        if "instrument" in rs: f_.append("rollout_instrument.csv")
        if "switch" in rs: f_.append("nothing -- the programme never switches off (not applicable)")
        if "never in the programme" in rs: f_.append("exports for >= 3 comparable NON-programme sub-watersheds, processed like yours")
        if "land-use" in rs: f_.append("LandUse varying among treated pixels")
        own_f = list(dict.fromkeys(f_))
        f_ += [c["fix"] for c in cav if c["id"] in ids]
        stat.append(st); miss.append("; ".join(dict.fromkeys(m_)) or "nothing"); comp.append("; ".join(dict.fromkeys(f_)) or "complete as it stands")
        own_miss.append(own_m); own_fix.append("; ".join(own_f)); cav_ids.append(", ".join(ids))
    out["status"] = stat; out["what_is_missing"] = miss; out["what_completes_it"] = comp
    out["model_own_gap"] = own_miss; out["model_own_fix"] = own_fix; out["panel_caveats"] = cav_ids
    yearly = facts.get("yearly_only_outcomes", [])
    return out, {"treatment_year": ty, "clean_pre": clean_pre, "clean_post": clean_post, "contaminated": contaminated,
                 "yearly_only_outcomes": yearly, "settings": settings, "caveats": cav}


def model_readiness(C=None, facts=None, outcomes=None, write=True, verbose=True, compare=None, name=None):
    if facts is None:
        if C is None:
            import _common as C
        facts = measure_panel(C, outcomes=outcomes)
    table, ctx = assess(facts)
    out_dir = None
    if write and C is not None:
        try:
            out_dir = os.path.join(C.RESULTS_ROOT); os.makedirs(out_dir, exist_ok=True)
        except Exception:
            out_dir = None
    if out_dir is None and write:
        out_dir = HERE
    ctab = None
    if isinstance(compare, str) and compare == "auto":                          # one sub-watershed -> show the pooled projection
        compare = FACTS_POOLED_20 if facts.get("n_sws", 2) == 1 else None
    if compare is not None:                                                     # v20.40: the same models on another profile
        ctab, _ = assess(compare)
        table = table.merge(ctab[["model", "status"]].rename(columns={"status": "status_pooled_20_projected"}), on="model", how="left")
    md = render_markdown(table, ctx, facts, compare=compare)
    stem = "MODEL_READINESS" + (f"_{name}" if name else "")
    if write:
        table.to_csv(os.path.join(out_dir, stem + ".csv"), index=False)
        with open(os.path.join(out_dir, stem + ".md"), "w", encoding="utf-8") as fh: fh.write(md)
    if verbose:
        print(md)
        if write: print(f"[OK]      written -> {os.path.join(out_dir, stem + '.md')} (+ .csv)")
    return table, ctx


def render_markdown(table, ctx, facts, compare=None):
    """v20.40: the readiness report -- labels, the panel-wide caveats in full, and per model what is missing and what
    would complete it; with `compare`, the status each model would have on that (projected) profile."""
    counts = table.status.value_counts().to_dict(); tr = facts["treated_pixels_by_year"]; inref = facts["treated_pixels_in_ref_by_year"]
    lab = ["complete", "limited", "incomplete-need data"]
    L = ["# Model readiness -- complete / limited / incomplete-need data", "", f"_{facts['source']}_", "",
         "**complete** -- every prerequisite is met on this panel; **limited** -- the model runs, but a panel-wide caveat "
         "below bounds what its result can claim; **incomplete-need data** -- a prerequisite is missing: the model "
         "refuses by design (DATA GAP) and its row names the data that would complete it.", "",
         f"## Summary -- {facts.get('site', 'this panel')}", "",
         "| | complete | limited | incomplete-need data |", "|---|---|---|---|",
         f"| **as the data stand now** | {counts.get(lab[0], 0)} | {counts.get(lab[1], 0)} | {counts.get(lab[2], 0)} |"]
    if compare is not None and "status_pooled_20_projected" in table:
        cc = table["status_pooled_20_projected"].value_counts().to_dict()
        L.append(f"| **all 20 sub-watersheds, projected** | {cc.get(lab[0], 0)} | {cc.get(lab[1], 0)} | {cc.get(lab[2], 0)} |")
        L += ["", f"_Projection: {compare['source']}_"]
    L += ["", "## The panel", "",
          f"Implementation year **{ctx['treatment_year']}** ({facts.get('implementation_year_source', '?')}) | years {facts['years'][0]}-{facts['years'][-1]} "
          f"| clean pre {ctx['clean_pre'][0] if ctx['clean_pre'] else '-'}-{ctx['clean_pre'][-1] if ctx['clean_pre'] else '-'} "
          f"| clean post {ctx['clean_post'] or 'NONE'} | years to hold out: {ctx['contaminated'] or 'none'}", "",
          f"Sub-watersheds {facts.get('n_sws', '?')} | inference clusters {facts['clusters']} = {facts.get('cluster_kind', 'clusters')} "
          f"| control rings {facts['control_rings']} | cohorts among treated {facts['cohorts_among_treated']} "
          f"| never-treated comparison {facts['never_treated_units']} | seasons {facts['seasons_present']}", "",
          "| year | treated pixels | with a pre-period history | control pixels |", "|---|---|---|---|"]
    for y in facts["years"]:
        L.append(f"| {y} | {tr.get(y, 0):,} | {inref.get(y, 0):,} ({(inref.get(y, 0) / tr[y] if tr.get(y) else 0):.0%}) | {facts['control_pixels_by_year'].get(y, 0):,} |")
    cav = ctx.get("caveats") or panel_caveats(facts)
    L += ["", "## PANEL-WIDE CAVEATS -- what is missing, why it matters, what fixes it", ""]
    for c in cav:
        L += [f"### {c['id']} -- {c['caveat']}" + ("  *(turns complete models into limited)*" if c["limits"] else ""), "",
              f"- **Missing:** {c['missing']}", f"- **Why it matters:** {c['why']}", f"- **What fixes it:** {c['fix']}",
              f"- **Affects:** {c['affects']}", ""]
    if ctx.get("settings"):
        L += ["**Settings for the main result:** " + "; ".join(ctx["settings"]), ""]
    if ctx.get("yearly_only_outcomes"):
        L += [f"Yearly-only outcomes (no seasonal rows): {ctx['yearly_only_outcomes']} -- seasonal models skip them.", ""]
    L += ["## Model by model", ""]
    hdr = "| model | name | status now | what is missing | what completes it |" + (" all 20 (projected) |" if compare is not None else "")
    L += [hdr, "|" + "---|" * (hdr.count("|") - 1)]
    order = {k: i for i, k in enumerate(lab)}
    esc = lambda t: str(t).replace("|", "/")                                  # a '|' would open a new table cell
    for rw in table.sort_values(["status", "model"], key=lambda s: s.map(order) if s.name == "status" else s).itertuples():
        pc = getattr(rw, "panel_caveats", "")
        miss_ = "; ".join(x for x in (esc(getattr(rw, "model_own_gap", "")), (f"panel-wide {pc}" if pc else "")) if x) or "nothing"
        fix_ = "; ".join(x for x in (esc(getattr(rw, "model_own_fix", "")), (f"fix {pc} (above)" if pc else "")) if x) or "complete as it stands"
        row = f"| {rw.model} | {rw.name} | **{rw.status}** | {miss_} | {fix_} |"
        if compare is not None: row += f" {getattr(rw, 'status_pooled_20_projected', '')} |"
        L.append(row)
    notes = [f"- **{rw.model}**: {rw.notes}" for rw in table.itertuples() if isinstance(rw.notes, str) and rw.notes]
    if notes: L += ["", "## Notes on reading specific models", ""] + notes
    return "\n".join(L) + "\n"
