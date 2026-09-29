"""
readiness.py -- WHICH OF THE 45 MODELS CAN RUN TO A COMPLETE RESULT ON THE PANEL YOU HAVE (v20.16)

    python readiness.py                      (uses the panel from _paths.py)
    python readiness.py path\\to\\did_panel_full.parquet

or, in a notebook:   C.model_readiness()

It streams the panel ONCE (never loads it whole), measures every prerequisite each model relies on, and writes
MODEL_READINESS.csv + prints the table. Statuses:
    RUN      every prerequisite met -- expect a complete result
    complete               every prerequisite is met on this panel
    limited                runs, but the result must be read with the stated panel-wide caveat
    incomplete-need data   a prerequisite is missing -- the model refuses, by design (DATA GAP), and the row says what
                           data would complete it  (v20.38: were RUN / LIMITED / BLOCKED)
The reasons are measured from the data, not assumed.
"""
import os, sys, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _common as C

OUTCOMES = ["NDVI", "SAVI", "EVI", "LAI", "LSWI", "NDWI", "NDMI", "NDRE", "AGB", "RUSLE",
            "ESI", "WSSI", "WSI", "SMDI", "VCI", "TCI", "VHI"]
WEATHER = ["Rain", "Tmax", "Tmean", "Tmin"]


def measure_panel(path=None, chunk_rows=None):
    """One streaming pass over the panel -> the facts every model's prerequisites depend on."""
    import pyarrow.parquet as pq
    path = path or C.PREPARED_PANEL
    pf = pq.ParquetFile(path)
    names = set(pf.schema_arrow.names)
    cols = [c for c in ["pixel_id", "Year", "Season", "buff_km", "subwshed_id", "site_id", "first_treat_agri_year",
                        "dose_per_subwshed", "LandUse", "latitude", "longitude"] + OUTCOMES + WEATHER if c in names]
    scn = C.ACTIVE
    cut = int(scn["post_cutoff"]); rings = set(int(r) for r in scn["control_zones"])
    F = {"path": path, "rows": 0, "years": set(), "seasons": set(), "cohorts": set(), "doses": set(),
         "landuse_treated": set(), "landuse_control": set(), "clusters": set(),
         "treated_pix_by_year": {}, "control_pix_by_year": {}, "treated_by_cluster": {},
         "usable": {o: {"seasonal": 0, "yearly": 0, "rows_seasonal": 0, "rows_yearly": 0} for o in OUTCOMES if o in names},
         "weather_usable_share": {w: [0, 0] for w in WEATHER if w in names},
         "has_coords": {"latitude", "longitude"} <= names, "has_cohort": "first_treat_agri_year" in names,
         "has_dose": "dose_per_subwshed" in names, "has_landuse": "LandUse" in names}
    switch_on = {}
    for i in range(pf.num_row_groups):
        d = pf.read_row_group(i, columns=cols).to_pandas()
        F["rows"] += len(d)
        yr = pd.to_numeric(d["Year"], errors="coerce"); se = pd.to_numeric(d["Season"], errors="coerce")
        bk = pd.to_numeric(d["buff_km"], errors="coerce")
        tr = (bk == C.TREAT_CORE_BUFFKM).values; ct = bk.isin(rings).values
        F["years"].update(int(y) for y in yr.dropna().unique()); F["seasons"].update(int(s) for s in se.dropna().unique())
        if "subwshed_id" in d: F["clusters"].update(map(str, d["subwshed_id"].dropna().unique()))
        if "site_id" in d: F.setdefault("sws", set()).update(int(x) for x in pd.to_numeric(d["site_id"], errors="coerce").dropna().unique())
        if "first_treat_agri_year" in d:
            F["cohorts"].update(int(x) for x in pd.to_numeric(d.loc[tr, "first_treat_agri_year"], errors="coerce").dropna().unique())
        if "dose_per_subwshed" in d:
            F["doses"].update(float(x) for x in pd.to_numeric(d.loc[tr, "dose_per_subwshed"], errors="coerce").dropna().round(6).unique())
        if "LandUse" in d:
            F["landuse_treated"].update(int(x) for x in pd.to_numeric(d.loc[tr, "LandUse"], errors="coerce").dropna().unique())
            F["landuse_control"].update(int(x) for x in pd.to_numeric(d.loc[ct, "LandUse"], errors="coerce").dropna().unique())
        seasonal = (se != 0).values
        # per-year pixel sets (treated / control), seasonal rows only
        ds = d[seasonal]; trs = tr[seasonal]; cts = ct[seasonal]; yrs = yr[seasonal].astype(int).values
        for y in np.unique(yrs):
            my = yrs == y
            F["treated_pix_by_year"].setdefault(int(y), set()).update(ds.loc[my & trs, "pixel_id"].values.tolist())
            F["control_pix_by_year"].setdefault(int(y), set()).update(ds.loc[my & cts, "pixel_id"].values.tolist())
        if "subwshed_id" in d:
            for cl, g in ds[trs].groupby("subwshed_id"):
                F["treated_by_cluster"].setdefault(str(cl), set()).update(g["pixel_id"].values.tolist())
        for o in F["usable"]:
            u = C._usable(d[o].values, o)
            F["usable"][o]["seasonal"] += int((u & seasonal).sum()); F["usable"][o]["rows_seasonal"] += int(seasonal.sum())
            F["usable"][o]["yearly"] += int((u & ~seasonal).sum()); F["usable"][o]["rows_yearly"] += int((~seasonal).sum())
        for w in F["weather_usable_share"]:
            u = C._usable(d[w].values, w); F["weather_usable_share"][w][0] += int(u.sum()); F["weather_usable_share"][w][1] += len(d)
        # switchers (v20.58): D = treated x post switches ON for a treated pixel seen before AND after the start (v20.57 asked whether the
        # GROUP (buff_km) changed over time -- it never does -- so M13 was never ready while R's DIDmultiplegtDYN computed it)
        _post = (yr.values >= cut)
        for p, t, q in zip(d["pixel_id"].values, tr, _post):
            if not t: continue
            a = switch_on.setdefault(p, [False, False]); a[int(bool(q))] = True
    try: pf.close()
    except Exception: pass
    F["n_switchers"] = sum(1 for v in switch_on.values() if v[0] and v[1])
    ys = sorted(F["years"]); F["pre_years"] = [y for y in ys if y < cut]; F["post_years"] = [y for y in ys if y >= cut]
    tp = {y: len(s) for y, s in F["treated_pix_by_year"].items()}; cp = {y: len(s) for y, s in F["control_pix_by_year"].items()}
    F["treated_pixels_by_year"] = tp; F["control_pixels_by_year"] = cp
    pre_tr = [tp.get(y, 0) for y in F["pre_years"]]; post_tr = [tp.get(y, 0) for y in F["post_years"]]
    F["treated_pre_min"] = min(pre_tr) if pre_tr else 0; F["treated_post_min"] = min(post_tr) if post_tr else 0
    F["treated_post_max"] = max(post_tr) if post_tr else 0
    ref = F["pre_years"][-1] if F["pre_years"] else None
    F["treated_stable_pixels"] = len(set.intersection(*[F["treated_pix_by_year"][y] for y in F["treated_pix_by_year"]])) if F["treated_pix_by_year"] else 0
    F["control_stable_pixels"] = len(set.intersection(*[F["control_pix_by_year"][y] for y in F["control_pix_by_year"]])) if F["control_pix_by_year"] else 0
    F["treated_clusters"] = {k: len(v) for k, v in F["treated_by_cluster"].items()}
    F["n_clusters"] = len(F["clusters"]); F["n_treated_clusters"] = sum(1 for v in F["treated_clusters"].values() if v > 0)
    F["n_sws"] = len(F.pop("sws", set()) or [])                                           # v20.38: sub-watersheds = clusters
    F["population_change"] = (F["treated_post_max"] > 5 * max(F["treated_pre_min"], 1))
    for k in ("treated_pix_by_year", "control_pix_by_year", "treated_by_cluster"): F.pop(k)
    return F


def assess(F):
    """Per-model verdicts from the measured facts."""
    pre, post = len(F["pre_years"]), len(F["post_years"])
    base_ok = F["treated_pre_min"] > 0 and F["treated_post_min"] > 0 and pre >= 1 and post >= 1
    pop = F["population_change"]
    pop_note = (f"treated population changes across periods ({F['treated_pre_min']:,} pre vs up to "
                f"{F['treated_post_max']:,} post pixels): restrict to the common footprint (BALANCED_PIXELS / POST_YEARS) "
                f"or reconcile the exports before reporting") if pop else ""
    few_cl = F["n_clusters"] < 6
    cl_note = (f"only {F['n_clusters']} clusters ({F['n_treated_clusters']} with treated pixels): use wild-cluster "
               f"bootstrap p (M23) / permutation (M25) for inference") if F["n_clusters"] < 12 else ""
    stab = F["treated_stable_pixels"]
    core_thin = stab < 1000
    thin_note = f"only {stab:,} treated pixels are observed in every year -- within-pixel identification rests on them" if core_thin else ""
    usable_out = [o for o, u in F["usable"].items() if u["seasonal"] > 0]
    yearly_only = [o for o, u in F["usable"].items() if u["seasonal"] == 0 and u["yearly"] > 0]
    absent = [o for o, u in F["usable"].items() if u["seasonal"] == 0 and u["yearly"] == 0]
    gt = os.path.exists(getattr(C, "GROUND_TRUTH_OUTCOMES_PATH", "")); inst = os.path.exists(getattr(C, "ROLLOUT_INSTRUMENT_PATH", ""))
    multi_cohort = len(F["cohorts"]) >= 2
    dose_var = len(F["doses"]) >= 2
    lu = len(F["landuse_treated"] & F["landuse_control"]) >= 2
    rows = []
    _LBL = {"RUN": "complete", "LIMITED": "limited", "BLOCKED": "incomplete-need data"}         # v20.38
    def add(mid, name, status, reason, unblock=""):
        rows.append({"model": mid, "name": name, "status": _LBL.get(status, status), "reason": reason,
                     "what_is_missing_or_would_complete_it": unblock})
    # v20.38: every caveat says WHAT is missing, WHY it matters and WHAT completes it
    sws_note = ""
    if F.get("n_sws", 0) == 1:
        sws_note = ("ONE sub-watershed -- MISSING: a second treated area. WHY: the sub-watershed is the cluster, and one "
                    "cluster cannot carry cluster-robust inference, so the engine clusters on years (each year's "
                    "core-vs-ring contrast is one independent draw; ~10 draws). FIX: the pooled 20-sub-watershed run "
                    "(20 clusters), then wild-bootstrap p-values (M23).")
    if pop_note: pop_note = ("treated population changes across periods -- MISSING: the same pixels in every year. WHY: "
                             "post-period rows on pixels with no pre-period history identify nothing (a later export on a "
                             "shifted grid or another footprint). FIX: P00 links shifted grids (PIXEL_OVERLAP_MIN 0.65); "
                             "otherwise re-export on the earlier grid. " + pop_note)
    if thin_note: thin_note = "few stable treated pixels -- MISSING: pixels seen in every year. WHY: " + thin_note + " FIX: re-export the missing years on the same footprint."
    if cl_note: cl_note = "few clusters -- MISSING: more sub-watersheds. WHY: " + cl_note + " FIX: run all 20 sub-watersheds together."
    panel_caveats = [x for x in (sws_note, pop_note, thin_note, cl_note) if x]
    def std(mid, name, extra_ok=True, extra_reason="", extra_unblock=""):
        if not base_ok: add(mid, name, "BLOCKED", "no treated (buff_km 0) or no control pixels in the pre or the post period", "check buff_km labelling / control rings / treatment year"); return
        if not extra_ok: add(mid, name, "BLOCKED", extra_reason, extra_unblock); return
        add(mid, name, "LIMITED" if panel_caveats else "RUN", "panel-wide caveats apply (see above)" if panel_caveats else "all prerequisites met", "")
    std("M01", "Canonical 2x2 TWFE")
    std("M02", "Event study", pre >= 2, "needs >= 2 pre-treatment years for leads", "widen PRE_YEARS")
    std("M03", "Doubly robust AIPW", all(F["weather_usable_share"][w][0] > 0 for w in F["weather_usable_share"]), "covariates all missing", "")
    std("M04", "Changes-in-changes")
    std("M05", "Callaway-Sant'Anna", multi_cohort, f"single treatment cohort ({sorted(F['cohorts'])}) -- ATT(g,t) collapses to the 2x2", "SITE_TREATMENT_YEARS with >= 2 cohorts (several sites pooled)")
    std("M06", "Continuous dose-response", dose_var, f"dose_per_subwshed takes {len(F['doses'])} distinct value(s) among treated pixels -- no dose variation", "a per-sub-watershed dose (fund release / works) that varies")
    std("M07", "Surrogate index", gt, "ground_truth_outcomes.csv not found", f"provide {getattr(C, 'GROUND_TRUTH_OUTCOMES_PATH', 'the ground-truth file')}")
    std("M08", "Instrumented DiD", inst, "rollout_instrument.csv not found", f"provide {getattr(C, 'ROLLOUT_INSTRUMENT_PATH', 'the instrument file')}")
    std("M09", "Sun-Abraham", multi_cohort, "single cohort -- interaction weights need >= 2 cohorts", "pool sites with different treatment years")
    std("M10", "Triple differences (DDD)", lu, "needs >= 2 land-use classes present in both treated and control pixels", "")
    std("M11", "Synthetic DiD", stab > 0, "no treated pixel observed in every period", "")
    std("M12", "Chained DiD (unbalanced)")
    std("M13", "Switcher DiD", F["n_switchers"] > 0, "no treated pixel is observed both before and after the start (the treatment never switches on in the window)", "widen PRE_YEARS / POST_YEARS")
    std("M14", "PS-matched DiD")
    std("M15", "Placebo false timing", pre >= 3, "needs >= 3 pre years to place a false treatment date", "widen PRE_YEARS")
    std("M16", "Joint pre-trends F-test", pre >= 2, "needs >= 2 pre years", "widen PRE_YEARS")
    std("M17", "Global Moran's I", F["has_coords"], "no coordinates in the panel", "")
    std("M18", "Local Moran / LISA", F["has_coords"], "no coordinates in the panel", "")
    std("M19", "Variance decomposition (ICC)", F["n_clusters"] >= 2, "needs >= 2 sub-watersheds", "")
    std("M20", "Spatial heterogeneity Q/I2", F["n_treated_clusters"] >= 2, f"treated pixels in only {F['n_treated_clusters']} sub-watershed(s) -- no between-cluster heterogeneity to test", "")
    std("M21", "Season-to-annual aggregation", len(F["seasons"] - {0}) >= 2, "needs >= 2 seasons", "")
    std("M22", "Goodman-Bacon decomposition", multi_cohort, "single cohort -- only one 2x2 comparison exists (nothing to decompose)", "pool sites with different treatment years")
    std("M23", "Wild-cluster bootstrap", F["n_clusters"] >= 4, f"only {F['n_clusters']} clusters (< 4)", "")
    std("M24", "Spillover ring gradient", F["control_stable_pixels"] > 0, "no ring pixels observed across periods", "")
    std("M25", "Permutation inference", F["n_clusters"] >= 4, f"only {F['n_clusters']} clusters", "")
    std("M26", "Treatment x covariate heterogeneity")
    std("M27", "BJS imputation", stab > 0, "no treated pixel observed in every period", "")
    std("M28", "Gardner two-stage")
    std("M29", "Exposure-duration heterogeneity", post >= 2, "needs >= 2 post years", "widen POST_YEARS")
    std("M30", "Cohort heterogeneity", multi_cohort, "single cohort", "pool sites with different treatment years")
    std("M31", "Stacked DiD", multi_cohort, "single cohort -- no clean-control stacks", "pool sites with different treatment years")
    std("M32", "Extended TWFE", multi_cohort or post >= 2, "single cohort and a single post period", "")
    std("M33", "Entropy balancing")
    std("M34", "Honest DiD sensitivity", pre >= 2, "needs >= 2 pre years", "widen PRE_YEARS")
    std("M35", "Quantile DiD")
    std("M36", "Interactive fixed effects", stab > 0, "needs pixels observed in every period", "")
    std("M37", "Matrix completion", stab > 0, "needs treated pixels observed in every period", "")
    std("M38", "Generalized synthetic control", F["n_treated_clusters"] >= 1 and F["n_clusters"] - F["n_treated_clusters"] >= 1,
        "needs at least one fully-control sub-watershed as a donor (treated pixels sit in every cluster)", "")
    for mid, name in (("M39", "ML CATE (forest-style)"), ("M40", "Double ML"), ("M41", "Meta-learners"), ("M42", "DR-learner"),
                      ("M43", "Honest causal forest"), ("M44", "BART-style")):
        std(mid, name, all(F["weather_usable_share"][w][0] > 0 for w in F["weather_usable_share"]), "no usable covariates", "")
    std("M45", "ML-selected synthetic control", stab > 0, "no treated pixel observed in every period", "")
    out = pd.DataFrame(rows)
    _pm = tuple(C.pipeline_models()) if hasattr(C, "pipeline_models") else ()     # v20.58: the project's models (_paths.PIPELINE_MODELS; all 45 = no filter)
    if _pm and len(out): out = out[out["model"].isin(_pm)].reset_index(drop=True)
    out.attrs["panel_caveats"] = panel_caveats
    facts = {
        "rows": F["rows"], "years": f"{min(F['years'])}-{max(F['years'])}" if F["years"] else "", "pre_years": F["pre_years"], "post_years": F["post_years"],
        "seasons": sorted(F["seasons"]), "clusters": F["n_clusters"], "treated_clusters": F["n_treated_clusters"],
        "treated_pixels_by_year": F["treated_pixels_by_year"], "control_pixels_by_year": F["control_pixels_by_year"],
        "treated_pixels_in_every_year": F["treated_stable_pixels"], "control_pixels_in_every_year": F["control_stable_pixels"],
        "cohorts": sorted(F["cohorts"]), "dose_values": len(F["doses"]), "switchers": F["n_switchers"],
        "outcomes_usable_seasonal": usable_out, "outcomes_yearly_only": yearly_only, "outcomes_absent": absent,
        "weather_usable_share": {w: round(v[0] / max(v[1], 1), 4) for w, v in F["weather_usable_share"].items()},
    }
    return out, facts


def model_readiness(path=None, save_dir=None, verbose=True):
    F = measure_panel(path)
    table, facts = assess(F)
    save_dir = save_dir or os.path.dirname(F["path"])
    try:
        table.to_csv(os.path.join(save_dir, "MODEL_READINESS.csv"), index=False)
        with open(os.path.join(save_dir, "MODEL_READINESS_facts.json"), "w", encoding="utf-8") as fh:
            json.dump(facts, fh, indent=1, default=str)
    except Exception:
        pass
    if verbose:
        print(f"PANEL FACTS (scenario {C.scenario_tag()}):")
        for k, v in facts.items(): print(f"  {k:32s} {v}")
        cav = table.attrs.get("panel_caveats", [])
        print("\nPANEL-WIDE CAVEATS (apply to every model marked 'limited') -- what is missing, why it matters, what fixes it:" if cav else "\nno panel-wide caveats")
        for i, c_ in enumerate(cav, 1): print(f"  {i}. {c_}")
        if facts["outcomes_yearly_only"]:
            print(f"  outcomes with values only in the annual composite -> run them with SEASONS = 'yearly': {facts['outcomes_yearly_only']}")
        if facts["outcomes_absent"]:
            print(f"  outcomes with no usable value anywhere (skip): {facts['outcomes_absent']}")
        print()
        pd.set_option("display.max_colwidth", 120)
        print(table.to_string(index=False))
        print(f"\n{(table.status == 'complete').sum()} complete | {(table.status == 'limited').sum()} limited | "
              f"{(table.status == 'incomplete-need data').sum()} incomplete-need data"
              f"  -> {os.path.join(save_dir, 'MODEL_READINESS.csv')}")
    return table, facts


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        C.load_scenario(verbose=False)
    except Exception:
        pass
    model_readiness(p)
