"""
_ooc_models.py -- v20.58: M01, M02, M16 and M34 OUT OF CORE (beyond 98 % of the RAM -- see _outofcore.py).

Each runner computes what the model's in-memory CELL 3 computes -- the same estimator, the same diagnostics, the same files -- from the
pixel partitions:
  * the two-way fixed-effects fits EXACTLY: inside each partition the unit (pixel x season series) effects are removed (every row of a
    unit is in one partition); the period effects are estimated jointly from the partitions' cross-products (Frisch-Waugh-Lovell: the
    period dummies, unit-demeaned, enter the normal equations -- their block D'MD = diag(n_p) - sum_u n_u. n_u.' / n_u is summed over
    the partitions, one reference period per connected set of periods); the CR1 sandwich from the per-cluster score sums, with the
    engine's own small-sample factor (n - 1) / (n - k - k_fe) and G / (G - 1);
  * every frame-level diagnostic (design counts, baseline means, repeat shares, effect-size diagnostics, the frozen-series guard, the
    design-based SE, the sample integrity) with the engine's own partial + final functions -- the in-memory path is the same final on
    ONE partition.
validate_out_of_core.py compares every number of every file with the in-memory run (Dask, Spark and the batches).
"""
import os, math, time
import numpy as np
import pandas as pd
import _outofcore as O


def _C():
    import _common as C
    return C


# ============================================================ the analysis sample, out of core
class OOCSample:
    """The model's analysis sample (build_treatment_columns + in_analysis_sample == 1) in pixel partitions on disk."""
    _ooc = True

    def __init__(self, **kw):
        self.__dict__.update(kw)

    @property
    def columns(self): return list(self.cols)

    def __len__(self): return int(self.rows)

    def design_cells(self): return self.cells

    def design_event_parts(self): return _C()._design_event_from_cells(self.cells)

    def __repr__(self):
        return f"OOCSample({self.model}/{self.outcome}: {self.rows:,} rows, {self.pixels:,} pixels, {len(self.paths)} partitions)"


def _read(path):
    import pyarrow.parquet as pq
    d = pq.read_table(path).to_pandas()
    d.attrs["location_rule_applied"] = True
    return d


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _integrity_part(d):
    C = _C()
    r = {"rows": int(len(d)), "cols": list(d.columns)}
    r["sid"] = sorted(set(_num(d["site_id"]).fillna(0).astype(int).tolist())) if "site_id" in d.columns else [0]
    if "site_check" in d.columns: r["n3"] = int((_num(d["site_check"]).values == 3).sum())
    keys = [k for k in ("pixel_id", "Year", "Season") if k in d.columns]
    r["nd"] = int(d.duplicated(subset=keys).sum()) if len(keys) == 3 else 0
    if {"site_id", "pixel_id", "buff_km"} <= set(d.columns):
        nr = d.groupby(["site_id", "pixel_id"], observed=True)["buff_km"].nunique(); r["nr"] = int((nr > 1).sum())
    if {"treatment", "pixel_id"} <= set(d.columns):
        tp = set(d.loc[d["treatment"].values == 1, "pixel_id"].tolist()); cp = set(d.loc[d["treatment"].values == 0, "pixel_id"].tolist())
        r["nboth"] = len(tp & cp)
    r["rg"] = sorted(int(x) for x in pd.unique(_num(d["buff_km"]).dropna())) if "buff_km" in d.columns else []
    if "Year" in d.columns and len(d):
        yr = _num(d["Year"]).values
        r["ymin"], r["ymax"] = float(yr.min()), float(yr.max())
        r["ydrop"] = bool(np.isin(yr, C.ACTIVE.get("drop_years") or []).any())
    if "Season" in d.columns and len(d): r["ss"] = sorted(int(x) for x in pd.unique(d["Season"]))
    r["pixels"] = int(d["pixel_id"].nunique()) if "pixel_id" in d.columns else 0
    _spx = C.opt("same_pixels")                                                                           # v20.59: pixel partitions -- a pixel's rows are
    if _spx != "off" and {"pixel_id", "post"} <= set(d.columns):                                          #   all here, so the count adds exactly
        _o = C.CURRENT_OUTCOME; _fin = np.isfinite(_num(d[_o]).values) if _o and _o in d.columns else np.ones(len(d), bool)
        r["one_side"] = int(C._pixels_one_side(d[_fin], _spx))
    return r


def integrity_final(parts, control_zones=None, label=None, verbose=True):
    """sample_integrity of the WHOLE sample from its partitions' pieces -- the same checks, texts, stop and file as in memory."""
    C = _C()
    cols = set(parts[0]["cols"]) if parts else set()
    strict_f = C.ACTIVE.get("fragment_rule", "drop") == "drop"; strict_o = C.ACTIVE.get("overlap_rows", "drop") == "drop"
    rows = []
    def add(what, ok_, detail, strict=True): rows.append({"check": what, "ok": bool(ok_), "detail": detail, "strict": bool(strict)})
    has_site = "site_id" in cols
    S = C.processing_sites()[0] if has_site and C.location_table().get("mode") != "none" else []
    st = sorted(set().union(*[set(p["sid"]) for p in parts])) if parts else []
    n = int(sum(p["rows"] for p in parts))
    if has_site:
        add("only the processed sub-watersheds", (not S) or set(st) <= set(S), f"in the sample: {st} | processed: {S or 'all (no ids)'}", strict_f)
    else:
        add("only the processed sub-watersheds", True, "this frame carries no sub-watershed id (a synthetic check panel): the location rule does not apply", False)
    if "site_check" in cols:
        n3 = int(sum(p.get("n3", 0) for p in parts)); add("nothing outside every polygon", n3 == 0, f"{n3} rows outside", strict_f)
    nd = int(sum(p["nd"] for p in parts))
    add("no repeated pixel-year-season", nd == 0, f"{n:,} rows, every (pixel, year, season) once" if nd == 0 else f"{nd:,} repeated rows", strict_o)
    if {"site_id", "pixel_id", "buff_km"} <= cols:
        nr = int(sum(p.get("nr", 0) for p in parts)); add("one ring per pixel", nr == 0, f"{nr} pixel(s) with more than one ring", strict_o)
    if {"treatment", "pixel_id"} <= cols:
        nb = int(sum(p.get("nboth", 0) for p in parts)); add("no pixel both treated and a control", not nb, f"{nb} pixel(s) on both sides", strict_o)
    _spx = C.opt("same_pixels")
    if _spx != "off" and any("one_side" in p for p in parts):
        _one = int(sum(p.get("one_side", 0) for p in parts))
        add("the same pixels in pre and post" if _spx == "pre_post" else "the same pixels in every year-season", _one == 0,
            f"{_one} pixel(s) observed " + ("on one side only" if _spx == "pre_post" else "in some year-seasons only"), True)
    cz = tuple(control_zones) if control_zones is not None else tuple(C.ACTIVE["control_zones"])
    rg = sorted(set().union(*[set(p["rg"]) for p in parts])) if parts else []
    add("the rings of the design", set(rg) <= ({0} | set(int(x) for x in cz)) and 0 in rg and any(r > 0 for r in rg),
        f"rings in the sample {rg} | design {[0] + sorted(int(x) for x in cz)}")
    ymin = ymax = None
    if "Year" in cols and n:
        ymin = min(p["ymin"] for p in parts if "ymin" in p); ymax = max(p["ymax"] for p in parts if "ymax" in p)
        lo_, hi_ = C.scenario_years()
        ok_y = (lo_ is None or ymin >= lo_) and (hi_ is None or ymax <= hi_) and not any(p.get("ydrop") for p in parts)
        add("the years of the design", ok_y, f"years {int(ymin)}-{int(ymax)} | window {lo_ or 'start'}-{hi_ or 'end'}")
    ss = sorted(set().union(*[set(p.get("ss", [])) for p in parts])) if parts else []
    if "Season" in cols and n:
        sc = C.season_codes(C.seasons_mode(verbose=False))
        add("the seasons of the design", sc is None or set(ss) <= set(sc), f"seasons {[C.SEASON_LABEL.get(x, x) for x in ss]} | {C.seasons_mode(verbose=False)}")
    tab = pd.DataFrame(rows); tab["outcome"] = label or C.CURRENT_OUTCOME or ""; tab["rows"] = n
    pixels = int(sum(p["pixels"] for p in parts)); tab["pixels"] = pixels
    C.LAST_INTEGRITY[:] = rows
    bad = tab[~tab.ok]
    if len(bad[bad.strict]):
        raise C.InsufficientDataError("SAMPLE INTEGRITY FAILED for " + str(label or C.CURRENT_OUTCOME) + " -- " +
                                      " | ".join(f"{r.check}: {r.detail}" for r in bad[bad.strict].itertuples()) + ". Nothing was estimated (a leak would bias every model).")
    if len(bad): C.warn("sample integrity: " + " | ".join(f"{r.check}: {r.detail}" for r in bad.itertuples()) + " -- your option keeps these rows")
    if verbose:
        C.ok(f"sample integrity ({label or C.CURRENT_OUTCOME}): {n:,} rows, {pixels:,} pixels | sub-watershed(s) {st} | rings {rg} | "
             + (f"years {int(ymin)}-{int(ymax)} | " if ymin is not None else "")
             + (f"seasons {[C.SEASON_LABEL.get(int(x), x) for x in ss]} | " if ss else "")
             + "CONFIRMED: every (pixel, year, season) once, one ring per pixel, no pixel both treated and a control, nothing outside the processed sub-watershed(s)"
             + " (out of core: every pixel partition checked, the checks summed)")
    return tab


def _design_part(d, o):
    """_design_frame's cells of one partition, for both readings of the site rule (the WHOLE sample decides which applies)."""
    C = _C()
    y = _num(d[o]).values.astype(np.float64); ok_ = np.isfinite(y)
    site = _num(d["site_id"]).fillna(0).astype(np.int64).values if "site_id" in d.columns else np.zeros(len(d), np.int64)
    tr = (_num(d["treatment"]).values == 1) if "treatment" in d.columns else (_num(d["buff_km"]).values == C.TREAT_CORE_BUFFKM)
    unit = d["unit_id"].values if "unit_id" in d.columns else d["pixel_id"].values
    yr = _num(d["Year"]).values; ss = _num(d["Season"]).values if "Season" in d.columns else np.zeros(len(d))
    post = (_num(d["post"]).values == 1).astype(int)
    out = {"any_pos": bool((site[ok_] > 0).any())}
    for key, m in (("all", ok_), ("pos", ok_ & (site > 0))):
        t = pd.DataFrame({"site": site[m], "Year": yr[m].astype(int), "Season": ss[m].astype(int) if "Season" in d.columns else 0,
                          "tr": tr[m], "post": post[m], "u": unit[m], "y": y[m]})
        if len(t): t["y"] = t["y"] - t.groupby("u")["y"].transform("mean")
        cells = t.groupby(["site", "Year", "Season", "tr"])["y"].agg(["sum", "count"]).reset_index()
        pp = t.groupby(["site", "Year", "Season"])["post"].agg(["max", "min"]).reset_index()
        out[key] = {"cells": cells, "pp": pp, "seasons": sorted(set(int(x) for x in t["Season"].tolist()))}
    return out


def design_cells_final(parts):
    use = "pos" if any(p["any_pos"] for p in parts) else "all"
    cl = [p[use]["cells"] for p in parts if len(p[use]["cells"])]
    if not cl:
        return {"g": pd.DataFrame(), "pp": pd.DataFrame(columns=["site", "Year", "Season", "post", "_pmin"]), "n_seasons": 0}
    c = pd.concat(cl, ignore_index=True).groupby(["site", "Year", "Season", "tr"])[["sum", "count"]].sum()
    c["y"] = c["sum"] / c["count"]
    g = c["y"].unstack("tr")
    pp = pd.concat([p[use]["pp"] for p in parts if len(p[use]["pp"])], ignore_index=True).groupby(["site", "Year", "Season"]).agg(
        post=("max", "max"), _pmin=("min", "min")).reset_index()
    return {"g": g, "pp": pp, "n_seasons": len(set().union(*[set(p[use]["seasons"]) for p in parts]))}


def _event_part(d, o, p):
    """The event study's pieces computed on the whole event sample once (M02 / M34): its size, the event-time range of the treated rows,
    per event time the rows and units of each group and those also seen at the reference period, and the frozen-series pieces."""
    C = _C()
    if p["model"] not in ("M02", "M34"): return None
    n0 = len(d)
    d = d[C._finite_rows(d, o, None, [])]
    fe1 = C._unit_key(d, "pixel_id")
    etv = _num(d["event_time"]).values; trv = _num(d["treat_core"]).values == 1
    fin = np.isfinite(etv) & trv
    out = {"n0": n0, "n": int(len(d)), "lo": float(np.nanmin(etv[fin])) if fin.any() else None, "hi": float(np.nanmax(etv[fin])) if fin.any() else None, "cov": {}}
    ref = p["ref"]
    et = d["event_time"].values; tr = d["treat_core"].values.astype(bool); pix = d[fe1].values
    ref_tr = set(pd.unique(pix[(et == ref) & tr])); ref_ct = set(pd.unique(pix[(et == ref) & ~tr]))
    for k in sorted(set(int(x) for x in pd.unique(etv[np.isfinite(etv)]))):
        m = et == k
        tp = pd.unique(pix[m & tr]); cp = pd.unique(pix[m & ~tr])
        out["cov"][k] = (int((m & tr).sum()), int((m & ~tr).sum()), int(len(tp)), int(len(cp)),
                         int(sum(1 for q in tp if q in ref_tr)) if k != ref else int(len(tp)), int(sum(1 for q in cp if q in ref_ct)) if k != ref else int(len(cp)))
    out["frozen"] = C._frozen_partial(d[o].values, d[fe1].values, tr, et <= ref)
    return out


def _m16_part(d, o, p):
    """M16's pieces of the whole sample: the years of the treated pre rows in the lead window (the controls of the same years enter the
    test) and the core / control means per sub-watershed x pre-period year (the design-based test when the years are the clusters)."""
    if p["model"] != "M16": return None
    lo, hi = p["pre_window"]; ref = p["ref"]
    et_all = _num(d["event_time"]).values
    yrs = None
    if "post" in d.columns:
        _pre = _num(d["post"]).values == 0; _trv = _num(d["treat_core"]).fillna(0).values == 1
        _tsel = _pre & _trv & (et_all >= lo) & (et_all <= max(hi, ref))
        yrs = sorted(set(_num(d.loc[_tsel, "Year"]).dropna().astype(int).tolist())) if "Year" in d.columns else []
    y = _num(d[o])
    m = ((_num(d["post"]) == 0) if "post" in d.columns else (pd.Series(et_all, index=d.index) <= ref)) & np.isfinite(y)
    site = d["site_id"] if "site_id" in d.columns else pd.Series(1, index=d.index)
    g = pd.DataFrame({"s": site[m].values, "yr": _num(d.loc[m, "Year"]).values, "t": _num(d.loc[m, "treat_core"]).values, "y": y[m].values})
    cells = g.groupby(["s", "yr", "t"])["y"].agg(["sum", "count"]).reset_index()
    return {"yrs": yrs, "dp": cells}


def _cf_part(d, o, p):
    if p["model"] != "M01": return None
    m = d["treat_core"] == 1
    t = pd.DataFrame({"Year": d.loc[m, "Year"].values, "y": _num(d.loc[m, o]).values, "did": _num(d.loc[m, "did_term"]).values})
    t = t[np.isfinite(t["y"].values)]
    return t.groupby("Year").agg(sy=("y", "sum"), sd=("did", "sum"), n=("y", "size")).reset_index()


def _t_prep(p):
    """One partition: the design columns of THIS run (build_treatment_columns, the in-memory call) and the analysis sample."""
    import pyarrow as pa, pyarrow.parquet as pq
    C = _C()
    d = O.read_part(p["path"], p["bad"])
    res = {"rows": 0, "path": None}
    if not len(d): return res
    d = C.build_treatment_columns(d, control_zones=p["control_zones"])
    res["post_diff"] = C.LAST_DESIGN_INFO.get("post_rows_differ_from_panel"); res["post_n"] = int(C.LAST_DESIGN_INFO.get("post_rows_compared", 0) or 0)   # v20.59
    res["same_out"] = C.LAST_DESIGN_INFO.get("same_pixels")                                                                                                # v20.59
    if C.ACTIVE.get("cluster") == "block" and "pixel_id" in d.columns: d["block_id"] = C.block_ids(d)   # v20.59
    d = d[d["in_analysis_sample"] == 1]
    if p.get("dropna") and p["outcome"] in d.columns: d = d.dropna(subset=[p["outcome"]])
    if not len(d): return res
    o = p["outcome"]
    integ, design = _integrity_part(d), _design_part(d, o)              # build_treatment_columns checks the sample BEFORE a model's own filter
    if p.get("balanced_n_per"):                                         # M02 BALANCED_PIXELS: common_pixel_mask(df, 'pixel_id', 'Year')
        cnt = d.assign(_p=_num(d["Year"])).groupby("pixel_id")["_p"].nunique()
        res["balanced"] = (int((cnt.values >= p["balanced_n_per"]).sum()), int(len(cnt)), int(len(d)))
        d = d[d["pixel_id"].isin(cnt.index[cnt.values >= p["balanced_n_per"]]).values]
        res["balanced"] = res["balanced"] + (int(len(d)),)
        if not len(d): return {**res, "rows": 0, "path": None, "integrity": integ, "design": design}
    out = p["path"].replace("loaded_", f"ana_{p['model']}_")
    pq.write_table(pa.Table.from_pandas(d, preserve_index=False), out, compression="zstd")
    res.update({"rows": int(len(d)), "path": out, "cols": list(d.columns), "integrity": integ, "design": design,
                "sites": sorted(set(_num(d["site_id"]).dropna().tolist())) if "site_id" in d.columns else None,
                "seasons": sorted(set(pd.unique(d["Season"]).tolist())) if "Season" in d.columns else [],
                "years": sorted(set(int(x) for x in _num(d["Year"]).dropna().unique())),
                "event": _event_part(d, o, p), "m16": _m16_part(d, o, p), "cf": _cf_part(d, o, p)})
    return res


O.register("prep", _t_prep)


def _t_presel(p):
    """v20.59: one partition's PRE-period facts for CONTROL_SELECTION (the design columns of this run first, the selection itself OFF so
    that every control row is counted); the parent merges the sums exactly and decides once for the whole sample."""
    C = _C()
    d = O.read_part(p["path"], p["bad"])
    if not len(d): return {"empty": True}
    saved = C.ACTIVE.get("use_control_selection"); C.ACTIVE["use_control_selection"] = False     # the selection OFF: every control row counted
    try: d = C.build_treatment_columns(d, control_zones=p["control_zones"])
    finally: C.ACTIVE["use_control_selection"] = saved
    f = C.control_selection_aggregates(d, d["in_analysis_sample"].values == 1, p["outcome"])
    return {"agg_t": f["agg_t"].to_dict("list"), "t_pixels": f["t_pixels"], "agg_c": f["agg_c"].to_dict("list"), "pix_c": f["pix_c"].to_dict("list"), "mode": f["mode"]}


O.register("presel", _t_presel)


def decide_controls_ooc(pool, pay, outcome):
    """v20.59: the parent's decision under CONTROL_SELECTION from every partition's pre-period facts (pixel partitions: the pixel counts add
    exactly); kept in ACTIVE so that the 'prep' workers apply the same fixed set."""
    C = _C()
    if C.opt("control_selection") == "rings": return None
    sel = C.ACTIVE.get("control_selected")
    if isinstance(sel, dict) and sel.get("outcome") == outcome and sel.get("mode") == C.opt("control_selection") and sel.get("key") == C._control_selection_key(): return sel
    got = pool.map("presel", pay)
    parts = [g["result"] for g in got if g["result"] and not g["result"].get("empty")]
    if not parts: raise C.InsufficientDataError(f"CONTROL_SELECTION: no pre-period rows of {outcome} in any partition")
    facts = {"agg_t": pd.concat([pd.DataFrame(r["agg_t"]) for r in parts], ignore_index=True), "t_pixels": int(sum(r["t_pixels"] for r in parts)),
             "agg_c": pd.concat([pd.DataFrame(r["agg_c"]) for r in parts], ignore_index=True), "pix_c": pd.concat([pd.DataFrame(r["pix_c"]) for r in parts], ignore_index=True),
             "mode": parts[0]["mode"]}
    tab, chosen = C.control_selection_decide(facts, outcome)
    return C.record_control_selection(tab, chosen, outcome)


def _cluster_key_ooc(cols, sites, col="subwshed_id"):
    """_cluster_key on the whole sample (its sub-watershed count), with the same side effects (LAST_CLUSTER_USED, the message once)."""
    C = _C()
    if col not in ("subwshed_id", "site_id", "cluster_id"):
        C.LAST_CLUSTER_USED["value"] = col; return col
    mode = C.ACTIVE.get("cluster", "site")
    if mode == "year" and "Year" in cols:
        C.LAST_CLUSTER_USED["value"] = "Year"; return "Year"
    if mode == "subwshed" and col in cols:
        C.LAST_CLUSTER_USED["value"] = col; return col
    if mode == "block" and "block_id" in cols:                                                     # v20.59
        C.LAST_CLUSTER_USED["value"] = "block_id"; return "block_id"
    if "site_id" in cols:
        n_ = len(sites or [])
        if n_ >= C.MIN_SWS_CLUSTERS:
            C.LAST_CLUSTER_USED["value"] = "site_id"; return "site_id"
        if "Year" in cols:
            if C._CLUSTER_SAID["n"] < 1:
                C.info(f"{n_} sub-watershed(s) in this sample: the sub-watershed is the cluster, but fewer than "
                       f"{C.MIN_SWS_CLUSTERS} clusters cannot carry cluster-robust inference -- clustering on Year instead "
                       f"(each year's core-vs-ring contrast is one independent draw). With >= {C.MIN_SWS_CLUSTERS} sub-watersheds "
                       f"the pooled run clusters on them.")
                C._CLUSTER_SAID["n"] += 1
            C.LAST_CLUSTER_USED["value"] = f"Year ({n_} sub-watershed{'s' if n_ != 1 else ''})"; return "Year"
    C.LAST_CLUSTER_USED["value"] = col if col in cols else None
    return col


def prepare_sample(panel, model, control_zones=None, ref=-1, pre_window=(-4, -2), balanced=False):
    """The model's analysis sample out of core, with what build_treatment_columns confirms on it in memory: the sample integrity (a leak
    stops the model), the design-based SE of the sample, its cluster count."""
    C = _C()
    t0 = time.time()
    C._ensure_resolved()
    cz = C.parse_control_zones(control_zones) if control_zones is not None else tuple(C.ACTIVE["control_zones"])
    pool = O.Pool(panel.engine)
    pay = [{"path": p, "bad": sorted(panel.screen_bad), "control_zones": cz, "model": model, "outcome": panel.outcome,
            "dropna": model in ("M16", "M34"), "ref": ref, "pre_window": tuple(pre_window)} for p in panel.paths]
    decide_controls_ooc(pool, pay, panel.outcome)                        # v20.59: CONTROL_SELECTION decided once by the parent, applied by every worker
    got = pool.map("prep", pay)
    res = [g["result"] for g in got if g["result"]["rows"]]
    if balanced and res:                                                # the periods of the WHOLE sample, then the pixels observed in all
        n_per = len(set().union(*[set(r["years"]) for r in res]))
        for q in pay: q["balanced_n_per"] = n_per
        got = pool.map("prep", pay)
        b = [g["result"]["balanced"] for g in got if g["result"].get("balanced")]
        integ_all = [g["result"]["integrity"] for g in got if g["result"].get("integrity")]
        design_all = [g["result"]["design"] for g in got if g["result"].get("design")]
        C.info(f"balanced footprint: {sum(x[0] for x in b):,} of {sum(x[1] for x in b):,} pixels are observed in all {n_per} "
               f"periods -> keeping {sum(x[3] for x in b):,} of {sum(x[2] for x in b):,} rows")
        res = [g["result"] for g in got if g["result"]["rows"]]
    else:
        integ_all = [r["integrity"] for r in res]; design_all = [r["design"] for r in res]
    o = panel.outcome
    lr = C.LAST_LOAD_INFO.get("location_rows", {}) or {}
    C.LAST_DESIGN_INFO.clear()
    C.LAST_DESIGN_INFO.update({"contaminated_control_rows": int(sum(v for k, v in lr.items() if str(k).startswith("3|0|"))),
                               "duplicate_rows_across_sites": int(sum(v for k, v in lr.items() if str(k).startswith("3|1|"))),
                               "location_rows": dict(lr)})
    _pv = [r for r in [g["result"] for g in got] if r.get("post_diff") is not None]     # v20.59: the design-vs-panel counts of every partition, said once
    if _pv: C.say_design_vs_panel(sum(int(r["post_diff"]) for r in _pv), sum(int(r["post_n"]) for r in _pv))
    _sp = [r["same_out"] for r in [g["result"] for g in got] if r.get("same_out")]                        # v20.59: SAME_PIXELS, summed over the partitions
    if _sp and sum(int(r["pixels_left_out"]) for r in _sp):
        C.info(f"SAME_PIXELS = '{_sp[0]['rule']}' ({o}): {sum(int(r['pixels_left_out']) for r in _sp):,} pixel(s) / {sum(int(r['rows_left_out']) for r in _sp):,} rows leave -- observed "
               + ("only before or only after treatment" if _sp[0]["rule"] == "pre_post" else "in some year-seasons only") + f"; the treated and control groups are the same {sum(int(r['pixels_kept']) for r in _sp):,} pixels")
    cols = res[0]["cols"] if res else list(panel.cols)
    sites = sorted(set().union(*[set(r["sites"]) for r in res])) if res and res[0]["sites"] is not None else None
    rows = int(sum(r["rows"] for r in res))
    s = OOCSample(model=model, outcome=o, paths=[r["path"] for r in res], cols=cols, rows=rows, engine=panel.engine, panel=panel,
                  pixels=0, sites=sites, seasons=sorted(set().union(*[set(r["seasons"]) for r in res])) if res else [],
                  years=sorted(set().union(*[set(r["years"]) for r in res])) if res else [], control_zones=cz, ref=ref, pre_window=tuple(pre_window),
                  prep=res, cells=None)
    if not res:
        return s
    if not getattr(C, "_OOC_WORKER", False):
        tab = integrity_final(integ_all, cz)
        C._INTEGRITY_SEEN[(C.CURRENT_MODEL_ID, C.CURRENT_OUTCOME, rows, tuple(cz))] = tab
        s.pixels = int(tab["pixels"].iloc[0])
    s.cells = design_cells_final(design_all)
    try:
        ds = C._design_se_from_cells(o, s.cells) or {}
        ev = C._design_event_from_cells(s.cells)
        cc = _cluster_key_ooc(cols, sites, "subwshed_id")
        G = (len(sites) if cc == "site_id" else len(s.years) if cc == "Year" else None) if cc in cols else None
        key = (C.CURRENT_MODEL_ID, o, rows, C.scenario_tag())
        C.LAST_DESIGN_SE[o] = {**ds, "_event": ev, "_key": key, "_n_clusters": G}
    except Exception as e:
        C.LAST_DESIGN_SE[o] = {"se_design_unit": f"design SE failed: {type(e).__name__}: {str(e)[:80]}"}
    C.info(f"{model} / {o}: analysis sample prepared out of core -- {rows:,} rows in {len(s.paths)} pixel partitions "
           f"({O.ENGINE_LABEL[panel.engine]}, {time.time() - t0:.1f} s)")
    return s


# ============================================================ the exact two-way fixed-effects core
def _apply_filters(d, filters, stop_before_usable=False):
    C = _C()
    for f in filters:
        kind = f[0]
        if kind == "usable":
            if stop_before_usable: break
            d = d[C._finite_rows(d, f[1], f[2], f[3])]
        elif kind == "finite":
            d = d[np.isfinite(_num(d[f[1]]).values)]
        elif kind == "season":
            d = d[d["Season"] == f[1]]
        elif kind == "m16pre":
            lo, hi, ref, yrs = f[1], f[2], f[3], f[4]
            et_all = _num(d["event_time"]).values
            if "post" in d.columns:
                _pre = _num(d["post"]).values == 0; _trv = _num(d["treat_core"]).fillna(0).values == 1
                _tsel = _pre & _trv & (et_all >= lo) & (et_all <= max(hi, ref))
                _csel = _pre & ~_trv & (_num(d["Year"]).isin(set(yrs or [])).values if "Year" in d.columns else True)
                d = d[_tsel | _csel]
            else:
                d = d[(et_all >= lo) & (et_all <= max(hi, ref))]
        elif kind == "balanced":
            per = _num(d[f[2]]); cnt = d.assign(_p=per).groupby(f[1])["_p"].nunique()
            d = d[d[f[1]].isin(cnt.index[cnt.values >= f[3]]).values]
    return d


def _xcols(d, xs):
    cols = []
    for x in xs:
        if x[0] == "col":
            cols.append(_num(d[x[1]]).values.astype(np.float64))
        elif x[0] == "prod":
            cols.append(_num(d[x[1]]).values.astype(np.float64) * _num(d[x[2]]).values.astype(np.float64))
        elif x[0] == "evt":                                   # estimate_event_study: treat_core x 1{event_time == k}
            cols.append((d[x[2]].values.astype(float) * (d[x[3]].values == x[1])).astype(np.float64))
        elif x[0] == "lead":                                  # pretrends_joint_ftest: the same with its numeric coercion
            tr = _num(d[x[2]]).fillna(0).values.astype(float); et = _num(d[x[3]]).values
            cols.append((tr * (et == x[1])).astype(float))
    return np.column_stack(cols) if cols else np.zeros((len(d), 0))


def _fe_partial(d_all, spec):
    """Pass 1 of one fit on one partition: the unit-demeaned cross-products, the period blocks, the cluster facts, the diagnostics."""
    from scipy import sparse
    C = _C()
    d1 = _apply_filters(d_all, spec["filters"], stop_before_usable=True)
    d = _apply_filters(d_all, spec["filters"])
    res = {"name": spec["name"], "n0": int(len(d1)), "n": int(len(d)), "k": len(spec["x"]), "U": 0, "labels": [], "diag": {}}
    if spec.get("sd_col"): res["sd_col"] = C._moments(_num(d1[spec["sd_col"]]).values)
    if spec.get("site_col") and spec["site_col"] in d1.columns:
        res["sites"] = sorted(set(_num(d1[spec["site_col"]]).dropna().tolist()))
    for kind in spec.get("diag", ()):
        res["diag"][kind] = _diag_part(kind, d, spec, d1)
    if not len(d): return res
    y = _num(d[spec["y"]]).values.astype(np.float64); X = _xcols(d, spec["x"])
    u, uu = pd.factorize(d[spec["unit"]].values); lab = d[spec["period"]].astype(str).values; lc, lu = pd.factorize(lab)
    n, k, L, U = len(d), X.shape[1], len(lu), len(uu)
    nu = np.bincount(u, minlength=U).astype(np.float64)
    yt = y - (np.bincount(u, y, minlength=U) / nu)[u]
    Xt = X - np.column_stack([np.bincount(u, X[:, j], minlength=U) / nu for j in range(k)])[u] if k else X
    N = sparse.csr_matrix((np.ones(n), (u, lc)), shape=(U, L))
    Cm = (N.T @ sparse.diags(1.0 / nu) @ N).tocoo()
    res.update({"U": int(U), "labels": [str(x) for x in lu], "n_p": np.bincount(lc, minlength=L).astype(np.float64),
                "DZ": np.column_stack([np.bincount(lc, Xt[:, j], minlength=L) for j in range(k)]) if k else np.zeros((L, 0)),
                "Dy": np.bincount(lc, yt, minlength=L), "C": (Cm.row.astype(np.int64), Cm.col.astype(np.int64), Cm.data),
                "ZZ": Xt.T @ Xt, "Zy": Xt.T @ yt, "yy": float(yt @ yt), "sx": X.sum(axis=0), "sxx": (X * X).sum(axis=0),
                "nsingle": int((nu == 1).sum())})
    if res["nsingle"]:
        one = (nu == 1)[u]
        res["single_where"] = {c: pd.Series(d[c].values[one]).value_counts().to_dict() for c in ("Season", "Year") if c in d.columns}
    cl = {}
    for c in spec["clusters"]:
        if c not in d.columns: continue
        v = d[c].astype(str).values
        uv = pd.DataFrame({"u": u, "v": v}).drop_duplicates()
        lv = pd.DataFrame({"l": lc, "v": v}).drop_duplicates()
        cl[c] = {"vals": sorted(set(v.tolist())), "nested_u": bool(not uv["u"].duplicated().any()),
                 "pairs": [(res["labels"][a], b) for a, b in zip(lv["l"].values, lv["v"].values)]}
    res["clusters"] = cl
    return res


def _diag_part(kind, d, spec, d1=None):
    C = _C()
    y = spec["y"]
    if kind == "twfe":
        tv = _num(d[spec["treat"]]).values.astype(np.float64) if len(d) else np.zeros(0)
        out = {"n_tp": int((tv != 0).sum())}
        if {"treatment", "post"} <= set(d.columns) and len(d):
            yv = _num(d[y]).values; tt = d["treatment"].values == 1; pp = d["post"].values == 1
            out["raw"] = {k_: (float(np.nansum(yv[m_])), int(np.isfinite(yv[m_]).sum()), int(m_.sum()))
                          for k_, m_ in (("tp", tt & pp), ("tn", tt & ~pp), ("cp", ~tt & pp), ("cn", ~tt & ~pp))}
        trp = (_num(d["treatment"]).values == 1) if "treatment" in d.columns else (_num(d[spec["treat"]]).values != 0)
        pre = (_num(d["pre"]).values == 1) if "pre" in d.columns else None
        out["frozen"] = C._frozen_partial(_num(d[y]).values, d[spec["unit"]].values, trp, pre)
        return out
    if kind == "dcounts": return C._design_counts_partial(d, y)
    if kind == "effect": return C._effect_partial(spec["outcome"], d)
    if kind == "repeat": return C._repeat_partial(d, spec["outcome"])
    if kind == "baseline": return C._baseline_partial(d, spec["outcome"])
    if kind == "evt_frozen":
        tr = d["treat_core"].values.astype(bool); et = d["event_time"].values
        return C._frozen_partial(d[y].values, d[spec["unit"]].values, tr, et <= spec["ref"])
    if kind == "m16":
        et = _num(d["event_time"]).values; tr = _num(d["treat_core"]).fillna(0).values.astype(float)
        pix = d[spec["unit"]].values; ref = spec["ref"]
        ref_pix = set(pd.unique(pix[(et == ref) & (tr == 1)]))
        leads = {}
        for kk in spec["leads"]:
            m = (et == kk) & (tr == 1)
            leads[kk] = (int(m.sum()), int(len(set(pd.unique(pix[m])) & ref_pix)))
        et1 = _num(d1["event_time"]).values; tr1 = _num(d1["treat_core"]).fillna(0).values.astype(float)
        return {"ref_rows_pre": int(((et1 == ref) & (tr1 == 1)).sum()), "ref_pix": int(len(ref_pix)), "leads": leads,
                "frozen": C._frozen_partial(d[y].values, pix, tr == 1, et <= ref)}
    raise ValueError(kind)


def _t_fits(p):
    d = _read(p["path"])
    return [_fe_partial(d, sp) for sp in p["specs"]]


def _t_scores(p):
    d = _read(p["path"])
    out = []
    for sp in p["specs"]:
        sol = p["sols"].get(sp["name"])
        out.append(_fe_scores(d, sp, sol) if sol is not None else None)
    return out


O.register("fits", _t_fits)
O.register("scores", _t_scores)


def _fe_scores(d_all, spec, sol):
    """Pass 2: the two-way residuals and the per-cluster score sums sum_i x_i e_i (x two-way demeaned) of one partition."""
    d = _apply_filters(d_all, spec["filters"])
    if not len(d): return {"vals": [], "S": np.zeros((0, len(sol["sel"]))), "n": 0}
    y = _num(d[spec["y"]]).values.astype(np.float64); X = _xcols(d, spec["x"])[:, sol["sel"]]
    u, uu = pd.factorize(d[spec["unit"]].values); U = len(uu)
    nu = np.bincount(u, minlength=U).astype(np.float64)
    idx = sol["index"]; gi = np.array([idx.get(str(x), -1) for x in d[spec["period"]].astype(str).values], dtype=np.int64)
    if (gi < 0).any(): raise RuntimeError("a period label of this partition is not in the solved set -- internal inconsistency")
    k = X.shape[1]
    yt = y - (np.bincount(u, y, minlength=U) / nu)[u]
    Xt = X - np.column_stack([np.bincount(u, X[:, j], minlength=U) / nu for j in range(k)])[u] if k else X
    Gam = sol["Gamma"][gi] if k else np.zeros((len(d), 0))
    Gu = np.column_stack([np.bincount(u, Gam[:, j], minlength=U) / nu for j in range(k)])[u] if k else Gam
    Xtt = Xt - Gam + Gu
    gr = sol["gamma"][gi]; gu = (np.bincount(u, gr, minlength=U) / nu)[u]
    e = yt - (Xt @ sol["beta"] if k else 0.0) - (gr - gu)
    cv = d[sol["cluster"]].astype(str).values; cc, cu = pd.factorize(cv)
    S = np.column_stack([np.bincount(cc, Xtt[:, j] * e, minlength=len(cu)) for j in range(k)]) if k else np.zeros((len(cu), 0))
    return {"vals": [str(x) for x in cu], "S": S, "n": int(len(d)), "ee": float(e @ e)}


class Fit:
    """One two-way fixed-effects fit over the partitions: the merged pass-1 pieces, the solve, the scores -> V."""

    def __init__(self, spec, parts):
        from scipy import sparse
        self.spec, self.parts = spec, [p for p in parts]
        self.n0 = int(sum(p["n0"] for p in parts)); self.n = int(sum(p["n"] for p in parts)); self.k = spec and len(spec["x"])
        self.diag = {kd: [p["diag"][kd] for p in parts if kd in p["diag"]] for kd in spec.get("diag", ())}
        self.sites = sorted(set().union(*[set(p.get("sites") or []) for p in parts])) if spec.get("site_col") else None
        self.sd_col = C_merge_moments([p["sd_col"] for p in parts if "sd_col" in p]) if spec.get("sd_col") else None
        live = [p for p in parts if p["n"]]
        self.labels = sorted(set().union(*[set(p["labels"]) for p in live])) if live else []
        L = len(self.labels); self.index = {l: i for i, l in enumerate(self.labels)}; k = self.k
        self.U = int(sum(p["U"] for p in live)); self.nsingle = int(sum(p.get("nsingle", 0) for p in live))
        self.single_where = {}
        for p in live:
            for c, vc in (p.get("single_where") or {}).items():
                a = self.single_where.setdefault(c, {})
                for kk, vv in vc.items(): a[kk] = a.get(kk, 0) + int(vv)
        n_p = np.zeros(L); A_DZ = np.zeros((L, k)); b_D = np.zeros(L); ZZ = np.zeros((k, k)); Zy = np.zeros(k); yy = 0.0
        sx = np.zeros(k); sxx = np.zeros(k); rr, cc_, vv_ = [], [], []
        for p in live:
            m = np.array([self.index[l] for l in p["labels"]], dtype=np.int64)
            n_p[m] += p["n_p"]; A_DZ[m] += p["DZ"]; b_D[m] += p["Dy"]; ZZ += p["ZZ"]; Zy += p["Zy"]; yy += p["yy"]
            sx += p["sx"]; sxx += p["sxx"]
            r_, c_, v_ = p["C"]; rr.append(m[r_]); cc_.append(m[c_]); vv_.append(v_)
        self.sx, self.sxx = sx, sxx
        self.cl = {}
        for c in spec["clusters"]:
            ps = [p["clusters"][c] for p in live if c in p.get("clusters", {})]
            if not ps: continue
            pairs = set()
            for q in ps: pairs.update((a, b) for a, b in q["pairs"])
            self.cl[c] = {"vals": sorted(set().union(*[set(q["vals"]) for q in ps])), "nested_u": all(q["nested_u"] for q in ps), "pairs": pairs}
        if L:
            Cs = sparse.coo_matrix((np.concatenate(vv_), (np.concatenate(rr), np.concatenate(cc_))), shape=(L, L)).tocsr()
            ADD = (sparse.diags(n_p) - Cs).tocsr()
            from scipy.sparse.csgraph import connected_components
            nc, comp = connected_components(Cs, directed=False)
            first = {}
            for i, c in enumerate(comp):
                if c not in first: first[c] = i
            keep = np.array([i for i in range(L) if first[comp[i]] != i], dtype=np.int64)
        else:
            keep = np.zeros(0, np.int64); ADD = None
        self.keep = keep
        if len(keep):
            S = ADD[keep][:, keep]
            Adz, bd = A_DZ[keep], b_D[keep]
            if len(keep) <= 6000:
                import scipy.linalg as sla
                Sd = S.toarray()
                try:
                    cho = sla.cho_factor(Sd, lower=False, check_finite=False)
                    WZ = sla.cho_solve(cho, Adz) if k else np.zeros((len(keep), 0)); Wy = sla.cho_solve(cho, bd)
                except Exception:
                    Pi = np.linalg.pinv(Sd, rcond=1e-12); WZ = Pi @ Adz if k else np.zeros((len(keep), 0)); Wy = Pi @ bd
            else:
                from scipy.sparse.linalg import splu
                lu = splu(S.tocsc()); WZ = lu.solve(Adz) if k else np.zeros((len(keep), 0)); Wy = lu.solve(bd)
            self.M = ZZ - Adz.T @ WZ; self.r = Zy - Adz.T @ Wy; self.yy2 = float(yy - bd @ Wy)
        else:
            WZ = np.zeros((0, k)); Wy = np.zeros(0); self.M, self.r, self.yy2 = ZZ, Zy, float(yy)
        self.WZ, self.Wy = WZ, Wy
        self.M = 0.5 * (self.M + self.M.T)

    # -- the numbers the in-memory code takes from its demeaned arrays
    def sd_dm(self, j):
        """np.std of the two-way demeaned column j (its mean is 0: the unit effects are in the model)."""
        return float(np.sqrt(max(self.M[j, j], 0.0) / self.n)) if self.n else 0.0

    def sd_y(self):
        return float(np.sqrt(max(self.yy2, 0.0) / self.n)) if self.n else 0.0

    def raw_sd(self, j):
        if not self.n: return 0.0
        m = self.sx[j] / self.n; return float(np.sqrt(max(self.sxx[j] / self.n - m * m, 0.0)))

    def solution(self, sel, beta, cluster):
        """What pass 2 needs: the period coefficients of the selected columns (Gamma) and of y given beta (gamma), 0 on the references."""
        L = len(self.labels); sel = list(sel)
        Gam = np.zeros((L, len(sel))); gam = np.zeros(L)
        if len(self.keep):
            Gam[self.keep] = self.WZ[:, sel]
            gam[self.keep] = self.Wy - self.WZ[:, sel] @ np.asarray(beta, dtype=np.float64)
        return {"sel": sel, "beta": np.asarray(beta, dtype=np.float64), "Gamma": Gam, "gamma": gam, "index": dict(self.index), "cluster": cluster}

    def k_fe(self, cluster):
        """_k_fe_nonnested([units, periods], clusters) of this fit's rows."""
        c = self.cl.get(cluster)
        if c is None: return int(self.U + len(self.labels) - 1)
        per = {}
        for l, v in c["pairs"]: per.setdefault(l, set()).add(v)
        L_ = [self.U, len(self.labels)]; nested = [bool(c["nested_u"]), bool(all(len(v) == 1 for v in per.values()))]
        k_adj = sum(L_) - (len(L_) - 1)
        k_nest = sum(l_ for l_, n_ in zip(L_, nested) if n_)
        return int(k_adj - k_nest + sum(nested)) if k_nest else int(k_adj)

    def n_clusters(self, cluster):
        c = self.cl.get(cluster); return len(c["vals"]) if c else 0

    def scores(self, results, sel):
        S = {}
        for r in results:
            if r is None: continue
            for v, row in zip(r["vals"], r["S"]):
                a = S.get(v)
                S[v] = row.copy() if a is None else a + row
        vals = sorted(S)
        return np.array([S[v] for v in vals]).reshape(len(vals), len(sel)), vals


def C_merge_moments(parts):
    return _C()._merge_moments(parts)


def run_fits(sample, specs):
    """Pass 1 of every fit of the model over the partitions -> {name: Fit}."""
    pool = O.Pool(sample.engine)
    got = pool.map("fits", [{"path": p, "specs": specs} for p in sample.paths])
    per = {sp["name"]: [g["result"][i] for g in got] for i, sp in enumerate(specs)}
    return {sp["name"]: Fit(sp, per[sp["name"]]) for sp in specs}


def run_scores(sample, specs, sols):
    """Pass 2 of the fits with a solution -> {name: [per-partition score pieces]}."""
    use = [sp for sp in specs if sp["name"] in sols]
    if not use: return {}
    pool = O.Pool(sample.engine)
    got = pool.map("scores", [{"path": p, "specs": use, "sols": sols} for p in sample.paths])
    return {sp["name"]: [g["result"][i] for g in got] for i, sp in enumerate(use)}


def _unit_col(sample):
    C = _C()
    return "unit_id" if ("unit_id" in sample.cols and C.ACTIVE.get("unit_fe", "pixel_season") == "pixel_season") else "pixel_id"


def _clusters(sample):
    return [c for c in ("site_id", "Year", "subwshed_id", "block_id") if c in sample.cols]     # v20.59: the ~1 km blocks (CLUSTER = 'block')


# ============================================================ the two-way FE DiD (estimate_twfe_did, the engine path)
class TwfeFit:
    """estimate_twfe_did out of core: stage_a (after pass 1) decides the design and beta; finish (after pass 2) the SE and the fit info."""

    def __init__(self, sample, fit, y_col, treat_col, covariates, cluster_col="subwshed_id"):
        self.s, self.f, self.y, self.t = sample, fit, y_col, treat_col
        self.covs_in = list(covariates or [])
        self.cluster_arg = cluster_col

    def stage_a(self):
        C = _C(); f = self.f
        self.cluster = _cluster_key_ooc(self.s.cols, f.sites, self.cluster_arg)
        self.cluster_value = C.LAST_CLUSTER_USED.get("value")
        if f.n0 == 0:
            raise C.InsufficientDataError(f"Empty dataframe for outcome '{self.y}' -- nothing to estimate.")
        n_drop = f.n0 - f.n
        if n_drop:
            share = n_drop / f.n0
            (C.warn if share > 0.25 else C.info)(f"'{self.y}': {n_drop:,} of {f.n0:,} rows ({share:.1%}) have a missing (NaN or zero) "
                                                  f"outcome or covariate and are excluded from the regression")
        self.n_drop = n_drop
        if f.n == 0:
            raise C.InsufficientDataError(
                f"'{self.y}' has NO finite values in the analysis sample -- nothing to estimate. If this variable exists "
                f"only in the annual composite (Season 0 'Yearly'), run it with C.set_scenario(seasons='yearly'). "
                f"C.outcome_coverage('{self.y}') shows where it has values.")
        tw = f.diag.get("twfe", [])
        self.n_tp = int(sum(p["n_tp"] for p in tw))
        if self.n_tp == 0:
            raise C.InsufficientDataError(f"'{self.y}': the treatment term '{self.t}' is zero on every row with a finite "
                                          f"outcome -- the effect is not identified. See C.outcome_coverage('{self.y}').")
        _fr = [p["frozen"] for p in tw]
        C._frozen_final(_fr, self.y)
        covs = [c for c in self.covs_in if c in self.s.cols]
        names = [self.t] + covs + [f"{c}_x_post" for c in covs] if self.spec_by_post() else [self.t] + covs
        self.all_names = names
        if covs:
            keep, keep_idx = [], []
            for j, c in enumerate(names[1:], start=1):
                if f.sd_dm(j) <= C.ABSORBED_REL_TOL * max(f.raw_sd(j), 1e-300):
                    C.warn(f"covariate '{c}' has no variation within pixel x period -- dropped (it is absorbed by the fixed effects)")
                else:
                    keep.append(c); keep_idx.append(j)
            self.covs = keep; self.sel = [0] + keep_idx
        else:
            self.covs = []; self.sel = [0]
        self.kfe = f.k_fe(self.cluster)
        if f.sd_dm(0) < 1e-10:
            raise C.InsufficientDataError("Treatment x post has no within-pixel/period variation (all units treated or all control, or no unit spans the cutoff)")
        Msel = f.M[np.ix_(self.sel, self.sel)]; rsel = f.r[self.sel]
        self.beta, self.Ginv = C._solve_normal(Msel, rsel, [self.t] + self.covs)
        return f.solution(self.sel, self.beta, self.cluster)

    def spec_by_post(self):
        return any(x[0] == "prod" for x in self.f.spec["x"])

    def finish(self, score_parts, return_all=False):
        C = _C(); f = self.f
        from scipy import stats as _st
        C.LAST_CLUSTER_USED["value"] = self.cluster_value
        C.LAST_FIT_INFO.clear()
        C.LAST_FIT_INFO.update({"n_obs": int(f.n), "n_dropped_missing": int(self.n_drop), "n_treated_post": int(self.n_tp)})
        if C.DESIGN_COUNTS and not C._RESAMPLING["depth"] and f.diag.get("dcounts"):
            _dc, _tab = C._design_counts_final(f.diag["dcounts"], self.y)
            C.LAST_FIT_INFO.update(_dc); C.LAST_DESIGN_COUNTS.update({"table": _tab, "outcome": self.y})
            C.LAST_ANALYSIS.update({"frame": None, "outcome": self.y,
                                    "ooc": {k_: f.diag[k_] for k_ in ("effect", "repeat", "baseline") if f.diag.get(k_)} or None})
            if C.LAST_ANALYSIS["ooc"] is not None and len(C.LAST_ANALYSIS["ooc"]) < 3: C.LAST_ANALYSIS["ooc"] = None
        C.LAST_FIT_INFO["n_singleton_series"] = int(f.nsingle)
        if f.nsingle:
            _by = []
            for _col, _lab in (("Season", "season"), ("Year", "year")):
                if _col in f.single_where:
                    _vc = pd.Series(f.single_where[_col]).sort_values(ascending=False, kind="stable").head(4)
                    _by.append(f"{_lab} " + ", ".join(f"{(C.SEASON_LABEL.get(int(k), k) if _col == 'Season' else int(k))}: {int(v):,}" for k, v in _vc.items()))
            C.LAST_FIT_INFO["singleton_rows_where"] = "; ".join(_by)
            (C.info if f.nsingle > 0.01 * f.n else C.trace)(
                f"{self.y}: {f.nsingle:,} unit series are seen ONCE in this sample ({f.nsingle / f.n:.1%} of rows) -- they identify nothing "
                f"(pyfixest drops them as 'singleton fixed effects'; the estimate is the same). Where: {C.LAST_FIT_INFO['singleton_rows_where']}")
        C.LAST_ENGINE["twfe"] = "engine"
        C.LAST_FIT_INFO["engine"] = "engine"
        S, vals = f.scores(score_parts, self.sel)
        G = len(vals)
        if G < 2:
            raise C.InsufficientDataError("Only 1 distinct cluster -- cluster-robust SEs are undefined (need >= 2 values of the clustering variable)")
        k = len(self.sel); n = f.n
        V = self.Ginv @ (S.T @ S) @ self.Ginv * (G / (G - 1)) * ((n - 1) / max(1, n - k - self.kfe))
        se = np.sqrt(np.diag(V)); beta = self.beta
        C.LAST_FIT_INFO["n_clusters"] = int(G); C.LAST_FIT_INFO["k_fe_in_ssc"] = int(self.kfe)
        try:
            C.LAST_FIT_INFO["mde_80pct_tG1"] = float((_st.t.ppf(0.975, max(int(G) - 1, 1)) + _st.t.ppf(0.80, max(int(G) - 1, 1))) * float(se[0]))
        except Exception:
            pass
        raw = [p.get("raw") for p in f.diag.get("twfe", []) if p.get("raw")]
        if raw:
            def _m(k_):
                s_ = sum(r[k_][0] for r in raw); nf = sum(r[k_][1] for r in raw); nall = sum(r[k_][2] for r in raw)
                return float(s_ / nf) if nall and nf else np.nan
            C.LAST_FIT_INFO["raw_did_means"] = (_m("tp") - _m("tn")) - (_m("cp") - _m("cn"))
        try:
            _t = beta[0] / se[0] if se[0] > 0 else np.nan
            C.LAST_FIT_INFO["p_t_G1"] = float(2 * _st.t.sf(abs(_t), max(int(G) - 1, 1))) if np.isfinite(_t) else np.nan
            C.LAST_FIT_INFO["ci95_low_tG1"] = float(beta[0] - _st.t.ppf(0.975, max(int(G) - 1, 1)) * se[0])
            C.LAST_FIT_INFO["ci95_high_tG1"] = float(beta[0] + _st.t.ppf(0.975, max(int(G) - 1, 1)) * se[0])
        except Exception:
            pass
        if not (np.isfinite(beta[0]) and np.isfinite(se[0])):
            raise C.InsufficientDataError(f"'{self.y}': the fit produced a non-finite estimate (beta={beta[0]}, se={se[0]}) "
                                          f"after excluding missing rows -- the design is singular; see C.outcome_coverage('{self.y}')")
        if abs(beta[0]) < 1e-300 and se[0] < 1e-300:
            raise C.InsufficientDataError(f"'{self.y}': beta and its SE are both exactly zero -- the outcome has no within "
                                          f"pixel x period variation on the estimation sample (a constant or a fully absorbed "
                                          f"series), not a genuine null effect")
        C.LAST_FIT_INFO["_beta"] = float(beta[0])
        if return_all:
            names = [self.t] + self.covs
            return {"beta": float(beta[0]), "se": float(se[0]), "coef": dict(zip(names, map(float, beta))),
                    "se_all": dict(zip(names, map(float, se))), "n": n, "k": k, "n_clusters": G}
        return float(beta[0]), float(se[0])


def twfe_spec(name, sample, y, treat, covs, extra_filters=(), diag=(), outcome=None, sd_col=None, by_post=False):
    C = _C()
    covs = [c for c in (covs or []) if c in sample.cols]
    x = [("col", treat)] + [("col", c) for c in covs] + ([("prod", c, "post") for c in covs] if by_post and covs and "post" in sample.cols else [])
    return {"name": name, "filters": list(extra_filters) + [("usable", y, treat, covs)], "y": y, "x": x, "unit": _unit_col(sample),
            "period": "time_fe_yearseason", "clusters": _clusters(sample), "treat": treat, "diag": list(diag), "outcome": outcome or y,
            "site_col": "site_id" if "site_id" in sample.cols else None, "sd_col": sd_col}


# ============================================================ the event study (estimate_event_study, the engine path)
class EventFit:
    def __init__(self, sample, fit, y_col, periods, covariates, ref=-1, min_share=1e-4, cluster_col="subwshed_id", lo=None, hi=None, cov=None):
        self.s, self.f, self.y, self.periods, self.cv_in, self.ref, self.min_share = sample, fit, y_col, list(periods), list(covariates or []), ref, min_share
        self.cluster_arg, self.lo, self.hi, self.cov = cluster_col, lo, hi, cov

    def stage_a(self):
        C = _C(); f = self.f
        self.cluster = _cluster_key_ooc(self.s.cols, self.s.sites, self.cluster_arg)
        self.cluster_value = C.LAST_CLUSTER_USED.get("value")
        sd_y = f.sd_y(); self.sd_y = sd_y
        C._frozen_final(f.diag.get("evt_frozen", []), self.y)
        if sd_y < 1e-9:
            raise C.InsufficientDataError(
                f"the outcome has NO variation left after removing pixel and period fixed effects (sd={sd_y:.2e}). "
                f"Almost every pixel is observed in a single period in this window, so nothing is identified. "
                f"Run C.treatment_coverage() and check how many periods each pixel actually has.")
        nk = len(self.periods); cv = [c for c in self.cv_in if c in self.s.cols]
        cv_idx = list(range(nk, nk + len(cv)))
        if cv:
            csd = np.array([f.sd_dm(j) for j in cv_idx]); craw = np.array([f.raw_sd(j) for j in cv_idx])
            keep = csd > 1e-8 * np.maximum(craw, 1e-12)
            if not keep.all():
                C.info(f"event study: covariates {[c for c, k_ in zip(cv, keep) if not k_]} are absorbed by the fixed effects -- dropped")
                cv_idx = [j for j, k_ in zip(cv_idx, keep) if k_]; cv = [c for c, k_ in zip(cv, keep) if k_]
        self.cv = cv
        sds = np.array([f.sd_dm(j) for j in range(nk)])
        ref_sd = np.nanmax(sds) if np.isfinite(sds).any() else 0.0
        identified = (sds > max(1e-10, self.min_share * ref_sd))
        if not identified.any():
            raise C.InsufficientDataError(
                "every lead/lag dummy is absorbed by the fixed effects -- in each relative period only ONE group is "
                "observed (or each pixel appears once). This is a data-coverage failure, not an estimation failure.")
        if not identified.all():
            C.warn(f"event times {[self.periods[i] for i in np.where(~identified)[0]]} are numerically absorbed "
                   f"(sd after demeaning <= {self.min_share:g} x the largest): their coefficients are noise and are flagged "
                   f"identified=False in the output")
        self.sds, self.identified = sds, identified
        self.sel = [i for i in range(nk) if identified[i]] + cv_idx
        Msel = f.M[np.ix_(self.sel, self.sel)]; rsel = f.r[self.sel]
        try:
            self.b = np.linalg.lstsq(Msel, rsel, rcond=None)[0]
        except np.linalg.LinAlgError:
            C.warn("event-study least squares did not converge (a non-finite or collinear column); solving the normal "
                   "equations with a pseudo-inverse instead")
            self.b = np.linalg.pinv(Msel, rcond=1e-12) @ rsel
        self.Msel = Msel
        self.kfe = f.k_fe(self.cluster)
        return f.solution(self.sel, self.b, self.cluster)

    def finish(self, score_parts):
        C = _C(); f = self.f
        C.LAST_CLUSTER_USED["value"] = self.cluster_value
        S, vals = f.scores(score_parts, self.sel)
        G = len(vals); n = f.n; k = len(self.sel)
        if G < 2:
            raise C.InsufficientDataError(
                f"Only {G} distinct cluster(s) -- cluster-robust SEs are undefined with fewer "
                f"than 2 clusters (the standard CR1 finite-sample correction divides by G-1). "
                f"This is a genuine data limitation, not a code bug: you need at least 2 "
                f"distinct values of the clustering variable in this sample.")
        XtX_inv = np.linalg.inv(self.Msel)
        dfc = (G / (G - 1)) * ((n - 1) / max(1, n - k - int(self.kfe)))
        _V = dfc * XtX_inv @ (S.T @ S) @ XtX_inv
        identified = self.identified.copy(); periods = self.periods
        _n_id = int(identified.sum())
        _vc_et = [periods[i] for i in np.flatnonzero(identified)]; _vc = np.asarray(_V[:_n_id, :_n_id], dtype=np.float64).copy()
        _vc_G = int(G)
        _dg = np.diag(_V).astype(np.float64)
        _neg = _dg < 0
        if _neg.any():
            _dg = np.where(_neg, 0.0, _dg)
            C.info(f"{int(_neg.sum())} event-time SE(s) came out non-positive through cancellation (absorbed regressor) -> marked not identified")
        s_ = np.sqrt(_dg)
        beta = np.full(len(periods), np.nan); se = np.full(len(periods), np.nan)
        beta[identified] = self.b[:_n_id]; se[identified] = s_[:_n_id]
        _dg = _dg[:_n_id]; _neg = _neg[:_n_id]
        if _neg.any():
            identified[np.flatnonzero(identified)[_neg]] = False
        out = pd.DataFrame({"event_time": periods, "beta": beta, "se": se, "sd_after_demeaning": self.sds, "identified": identified})
        cov = self.cov
        out = cov.merge(out, on="event_time", how="left").sort_values("event_time").reset_index(drop=True)
        out = out[["event_time", "beta", "se", "sd_after_demeaning", "identified"] + [c_ for c_ in cov.columns if c_ != "event_time"]]
        out["identified"] = pd.Series([bool(v) if pd.notna(v) else False for v in out["identified"]], index=out.index)
        out.attrs["sd_outcome_after_demeaning"] = self.sd_y
        C.LAST_EVENT_VCOV.clear(); C.LAST_EVENT_VCOV.update({"vcov": _vc, "event_times": list(_vc_et), "n_clusters": _vc_G,
                                                             "cluster_used": str(C.LAST_CLUSTER_USED.get("value") or ""),
                                                             "outcome": self.y, "n_rows": int(n)})
        out.attrs.update({"n_clusters": _vc_G, "cluster_used": str(C.LAST_CLUSTER_USED.get("value") or "")})
        out["engine"] = "engine"; out["covariates"] = ";".join(self.cv) if self.cv else ""
        C.LAST_ENGINE["event_study"] = "engine"
        try:
            if str(C.LAST_CLUSTER_USED.get("value", "")).startswith("Year"):
                _lead = pd.to_numeric(out.loc[(out["event_time"] < self.ref) & out["beta"].notna(), "beta"], errors="coerce").dropna()
                if len(_lead) >= 2:
                    out["se_design"] = float(_lead.std(ddof=1))
                    out["se_note"] = "cluster = Year: the per-year cluster SEs are not valid; se_design = SD of the pre-period leads"
        except Exception:
            pass
        return out


def event_coverage(sample, ref=-1):
    """estimate_event_study's coverage table, messages and event-time range from the partitions' pieces (window None: every event time
    of the design's window)."""
    C = _C()
    parts = [r["event"] for r in sample.prep if r.get("event")]
    n0 = sum(p["n0"] for p in parts); n = sum(p["n"] for p in parts)
    if n0 > n: C.info(f"event study: excluding {n0 - n:,} rows with a missing outcome/covariate")
    if n == 0:
        raise C.InsufficientDataError(f"'{sample.outcome}': no finite values in the event-study sample -- see C.outcome_coverage('{sample.outcome}')")
    los = [p["lo"] for p in parts if p["lo"] is not None]; his = [p["hi"] for p in parts if p["hi"] is not None]
    if not los: raise C.InsufficientDataError("no treated row with an event time in this sample")
    lo, hi = int(min(los)), int(max(his))
    acc = {}
    for p in parts:
        for k, v in p["cov"].items():
            a = acc.setdefault(int(k), [0, 0, 0, 0, 0, 0])
            for i in range(6): a[i] += v[i]
    cov = []
    for k in range(lo, hi + 1):
        a = acc.get(k, [0, 0, 0, 0, 0, 0])
        cov.append({"event_time": k, "n_rows_treated": int(a[0]), "n_rows_control": int(a[1]), "n_pixels_treated": int(a[2]), "n_pixels_control": int(a[3]),
                    "n_treated_pixels_also_in_ref": int(a[4]), "n_control_pixels_also_in_ref": int(a[5])})
    cov = pd.DataFrame(cov)
    cov["share_treated"] = cov["n_rows_treated"] / (cov["n_rows_treated"] + cov["n_rows_control"]).replace(0, np.nan)
    cov["share_treated_pixels_also_in_ref"] = (cov["n_treated_pixels_also_in_ref"] / cov["n_pixels_treated"].replace(0, np.nan)).round(4)
    def _note(r):
        if r.event_time == ref: return "reference period"
        if r.n_rows_treated == 0 and r.n_rows_control == 0: return "no rows in the panel for this period -- not estimated"
        if r.n_rows_treated == 0: return "no treated rows -- not identified"
        if r.n_rows_control == 0: return "no control rows -- not identified"
        if r.n_treated_pixels_also_in_ref == 0:
            return "NONE of the treated pixels here are observed in the reference period -- coefficient not identified from within-pixel change"
        if r.share_treated_pixels_also_in_ref < 0.5:
            return (f"identified from {int(r.n_treated_pixels_also_in_ref):,} treated pixels also seen in the reference period; "
                    f"the other {int(r.n_pixels_treated - r.n_treated_pixels_also_in_ref):,} treated pixels appear here but not there (different population)")
        return f"identified from {int(r.n_treated_pixels_also_in_ref):,} treated pixels observed in both periods"
    cov["identification_note"] = cov.apply(_note, axis=1)
    no_rows = cov[(cov.n_rows_treated == 0) & (cov.n_rows_control == 0)]
    if len(no_rows):
        C.info(f"event times {no_rows.event_time.tolist()} have no rows in the panel window (year "
               f"{[int(C.ACTIVE['treatment_year']) + int(k) for k in no_rows.event_time]}) -- not estimated, listed with a note")
    empty = cov[((cov.n_rows_treated == 0) | (cov.n_rows_control == 0)) & ~((cov.n_rows_treated == 0) & (cov.n_rows_control == 0))]
    if len(empty):
        C.warn(f"event times {empty.event_time.tolist()} have no treated OR no control rows -- their coefficients cannot "
               f"be identified; see identification_note")
    est_tr = cov[(cov.event_time != ref) & (cov.n_pixels_treated > 0)]
    if len(est_tr) and est_tr.n_pixels_treated.max() > 5 * max(est_tr.n_pixels_treated.min(), 1):
        C.warn(f"the TREATED population is not the same pixels across periods: {int(est_tr.n_pixels_treated.min()):,} treated "
               f"pixels in some periods vs {int(est_tr.n_pixels_treated.max()):,} in others. The coefficients therefore "
               f"compare different pixel populations, and a period-specific jump (a new export footprint, a "
               f"re-labelled buff_km, a different index scale) will show up as an 'effect'. See "
               f"panel_balance_by_block.csv, C.treatment_coverage() and the identification_note column.")
    thin = cov[(cov.event_time != ref) & (cov.n_pixels_treated > 0) & (cov.n_treated_pixels_also_in_ref < 0.5 * cov.n_pixels_treated)]
    if len(thin):
        C.warn(f"at event times {thin.event_time.tolist()} fewer than half of the treated pixels are observed in the "
               f"reference period ({ref}); those coefficients rest on the minority that is")
    present = set(cov.loc[(cov.n_rows_treated > 0) | (cov.n_rows_control > 0), "event_time"].tolist())
    periods = [k for k in range(lo, hi + 1) if k != ref and k in present]
    if not periods:
        raise C.InsufficientDataError("window collapses to only the reference period; nothing to estimate.")
    return cov, periods, lo, hi


def event_spec(name, sample, y, periods, covs, ref=-1):
    cv = [c for c in (covs or []) if c in sample.cols]
    return {"name": name, "filters": [("usable", y, None, [])], "y": y,
            "x": [("evt", k, "treat_core", "event_time") for k in periods] + [("col", c) for c in cv],
            "unit": _unit_col(sample), "period": "time_fe_yearseason", "clusters": _clusters(sample), "diag": ["evt_frozen"],
            "ref": ref, "outcome": y}


# ============================================================ the joint pre-trends test (pretrends_joint_ftest)
class PretrendFit:
    def __init__(self, sample, fit, y_col, covs, pre_window=(-4, -2), ref=-1, cluster_col="subwshed_id"):
        self.s, self.f, self.y, self.cv_in, self.pw, self.ref, self.cluster_arg = sample, fit, y_col, list(covs or []), tuple(pre_window), ref, cluster_col

    def stage_a(self):
        C = _C(); f = self.f
        self.cluster = _cluster_key_ooc(self.s.cols, self.s.sites, self.cluster_arg)
        self.cluster_value = C.LAST_CLUSTER_USED.get("value")
        lo, hi = self.pw
        if f.n0 == 0:
            raise C.InsufficientDataError(
                f"No rows with event_time in [{lo},{max(hi, self.ref)}] -- this sample's years don't reach the "
                f"pre-trends test window relative to the treatment year. A DATA COVERAGE gap, not a code bug: check "
                f"event_time = Year - TREATMENT_YEAR against what years you actually have.")
        m16 = f.diag.get("m16", [])
        if not sum(p["ref_rows_pre"] for p in m16):
            raise C.InsufficientDataError(
                f"the reference period (event time {self.ref}) has no treated rows -- the leads cannot be anchored. "
                f"See C.outcome_coverage('{self.y}') / C.treatment_coverage().")
        sd_y = f.sd_y() if f.n else 0.0
        C._frozen_final([p["frozen"] for p in m16], self.y)
        self.ref_pix = int(sum(p["ref_pix"] for p in m16))
        pre_periods = [k for k in range(lo, hi + 1) if k != self.ref]
        kept, dropped, idx = [], {}, []
        for j, k in enumerate(pre_periods):
            rows_k = sum(p["leads"][k][0] for p in m16); inref = sum(p["leads"][k][1] for p in m16)
            if not rows_k:
                dropped[k] = "no treated rows at this lead"; continue
            if inref == 0:
                dropped[k] = "none of the treated pixels at this lead are observed in the reference period (absorbed)"; continue
            if f.sd_dm(j) <= 1e-4 * max(sd_y, 1e-12):
                dropped[k] = "no within-pixel variation after the fixed effects (absorbed)"; continue
            kept.append(k); idx.append(j)
        if not kept:
            raise C.InsufficientDataError(
                f"none of the leads {pre_periods} is identified on this sample ({dropped}) -- the pre-trends test has "
                f"nothing to test. This is a coverage gap (treated pixels not observed across the pre-period), not a bug.")
        if dropped:
            C.warn(f"pre-trends test: leads {sorted(dropped)} dropped -- " + "; ".join(f"{k}: {v}" for k, v in dropped.items()))
        self.kept, self.dropped, self.q = kept, dropped, len(kept)
        cv = [c for c in self.cv_in if c in self.s.cols]
        for i, c in enumerate(cv):
            j = len(pre_periods) + i
            if f.sd_dm(j) > 1e-10: idx.append(j)
        self.sel = idx
        Msel = f.M[np.ix_(idx, idx)]; rsel = f.r[idx]
        self.b = np.linalg.lstsq(Msel, rsel, rcond=None)[0]
        self.Msel = Msel; self.kfe = f.k_fe(self.cluster)
        return f.solution(self.sel, self.b, self.cluster)

    def finish(self, score_parts):
        from scipy import stats as sstats
        C = _C(); f = self.f
        C.LAST_CLUSTER_USED["value"] = self.cluster_value
        S, vals = f.scores(score_parts, self.sel)
        G = len(vals); n = f.n; k = len(self.sel)
        XtX_inv = np.linalg.inv(self.Msel)
        dfc = (G / (G - 1)) * ((n - 1) / max(1, n - k - int(self.kfe)))
        vcov_all = dfc * XtX_inv @ (S.T @ S) @ XtX_inv
        q = self.q; beta = self.b[:q]; vcov = vcov_all[:q, :q]; vcov = 0.5 * (vcov + vcov.T)
        rank = int(np.linalg.matrix_rank(vcov, tol=1e-12 * max(float(np.max(np.abs(vcov))), 1e-300)))
        if rank < q:
            C.warn(f"pre-trends test: the cluster-robust covariance of {q} lead(s) has rank {rank} "
                   f"({G} clusters allow at most {G - 1} restrictions); testing {rank} restriction(s) with a pseudo-inverse")
        if q > G - 1:
            C.warn(f"pre-trends test: {q} leads but only {G} clusters -- the joint test can have at most {G - 1} degrees of "
                   f"freedom; prefer fewer leads (pre_window) or the 1-df linear-trend test")
        kept = self.kept
        if str(self.cluster) == "Year":
            dz = design_pretrend_ooc(self.s)
            se_lead = float(np.std(beta, ddof=1)) if len(beta) > 1 else float("nan")
            return {"q_leads_tested": q, "leads_tested": kept, "leads_dropped": self.dropped, "vcov_rank": int(np.linalg.matrix_rank(vcov)) if vcov.size else 0,
                    "f_stat": dz["F"], "df1": 1, "df2": dz["df"], "p_value": dz["p"], "n_clusters": int(G),
                    "reject_parallel_trends_at_5pct": bool(dz["p"] < 0.05), "test_reliable": bool(np.isfinite(dz["p"])),
                    "vcov_condition_number": float("nan"), "method": "design-based linear pre-trend of the core-minus-control gap (years as draws)",
                    "slope_per_year": dz["slope"], "slope_se": dz["se"], "pre_years": dz["n_years"], "sub_watersheds": dz["n_sws"],
                    "cluster_wald_note": f"not applicable: {G} year clusters, one lead per year -- its cluster covariance is degenerate",
                    "verdict": ("REJECT: the core-minus-control gap trends before implementation" if dz["p"] < 0.05 else
                                "no evidence against parallel pre-trends"),
                    "lead_coefficients": dict(zip(kept, beta)), "lead_se": {k_: se_lead for k_ in kept},
                    "n_obs": int(n), "n_treated_pixels_in_ref": int(self.ref_pix)}
        _w, _U = np.linalg.eigh(vcov)
        _wmax = float(np.max(_w)) if _w.size else 0.0
        _keep = _w > max(1e-7 * _wmax, 1e-300)
        _cond = float(_wmax / np.min(_w[_keep])) if _keep.any() else float("inf")
        _z = _U[:, _keep].T @ beta
        wald_stat = float(np.sum(_z ** 2 / _w[_keep])) if _keep.any() else float("nan")
        rank = int(_keep.sum())
        df1 = max(rank, 1); df2 = max(G - 1, 1)
        f_stat = wald_stat / df1
        _reliable = bool(_keep.any() and rank == q and q <= G - 1 and _cond < 1e6)
        p_value = float(1 - sstats.f.cdf(f_stat, df1, df2))
        se = np.sqrt(np.clip(np.diag(vcov), 0, None))
        return {"q_leads_tested": q, "leads_tested": kept, "leads_dropped": self.dropped, "vcov_rank": rank,
                "f_stat": f_stat, "df1": df1, "df2": df2, "p_value": p_value, "n_clusters": int(G),
                "reject_parallel_trends_at_5pct": bool(p_value < 0.05) if _reliable else False,
                "test_reliable": _reliable, "vcov_condition_number": _cond,
                "verdict": ("REJECT parallel trends" if (_reliable and p_value < 0.05) else
                            "no evidence against parallel trends" if _reliable else
                            f"INCONCLUSIVE: the cluster covariance of the leads is ill-conditioned ({G} clusters, condition "
                            f"number {_cond:.1e}) -- read the event-study leads (M02) and HonestDiD (M34) instead"),
                "lead_coefficients": dict(zip(kept, beta)), "lead_se": dict(zip(kept, se)),
                "n_obs": int(n), "n_treated_pixels_in_ref": int(self.ref_pix)}


def design_pretrend_ooc(sample):
    """_design_pretrend_test from the partitions' core / control sums per sub-watershed x pre-period year."""
    from scipy import stats as _st
    C = _C()
    cl = [r["m16"]["dp"] for r in sample.prep if r.get("m16") and len(r["m16"]["dp"])]
    if not cl: raise C.InsufficientDataError("the pre-period has no year with both core and control pixels -- no pre-trend test")
    c = pd.concat(cl, ignore_index=True).groupby(["s", "yr", "t"])[["sum", "count"]].sum()
    w = (c["sum"] / c["count"]).unstack("t")
    if 0 not in w.columns or 1 not in w.columns:
        raise C.InsufficientDataError("the pre-period has no year with both core and control pixels -- no pre-trend test")
    gap = (w[1] - w[0]).dropna().reset_index(); gap.columns = ["s", "yr", "gap"]
    S = gap["s"].nunique(); X = [np.ones(len(gap)), gap["yr"].values.astype(float)]
    for s_ in sorted(gap["s"].unique())[1:]: X.append((gap["s"].values == s_).astype(float))
    X = np.column_stack(X); dfree = len(gap) - X.shape[1]
    if dfree < 1:
        raise C.InsufficientDataError(f"the pre-trend test needs >= 3 pre-period years per sub-watershed (have {len(gap)} gap(s) for {S})")
    b, *_ = np.linalg.lstsq(X, gap["gap"].values, rcond=None); e = gap["gap"].values - X @ b
    se = float(np.sqrt((e @ e) / dfree * np.linalg.inv(X.T @ X)[1, 1])); t = float(b[1] / se) if se > 0 else float("nan")
    return {"F": t * t, "p": float(2 * _st.t.sf(abs(t), dfree)) if np.isfinite(t) else float("nan"), "slope": float(b[1]), "se": se,
            "df": int(dfree), "n_years": int(gap["yr"].nunique()), "n_sws": int(S)}


def pretrend_spec(name, sample, y, covs, yrs, pre_window=(-4, -2), ref=-1):
    lo, hi = pre_window
    pre_periods = [k for k in range(lo, hi + 1) if k != ref]
    cv = [c for c in (covs or []) if c in sample.cols]
    return {"name": name, "filters": [("m16pre", lo, hi, ref, list(yrs or [])), ("usable", y, None, None)], "y": y,
            "x": [("lead", k, "treat_core", "event_time") for k in pre_periods] + [("col", c) for c in cv],
            "unit": _unit_col(sample), "period": "time_fe_yearseason", "clusters": _clusters(sample), "diag": ["m16"],
            "ref": ref, "leads": pre_periods, "outcome": y}


# ============================================================ the models
def _headline_note(sample):
    return f"out of core: {O.ENGINE_LABEL[sample.engine]}, {len(sample.paths)} pixel partitions"


def run_m01(sample, outcome, results_dir, covariates=(), use_covariates=True):
    """M01's CELL 3 (the canonical 2x2 two-way FE, with and without the covariates; the bad-control check; the by-season table; the
    counterfactual) out of core."""
    C = _C()
    from scipy import stats as _st
    C.info(f"analysis sample: {sample.rows:,} rows, {sample.pixels:,} pixels (out of core: {len(sample.paths)} pixel partitions)")
    covs = [c for c in (list(covariates) if use_covariates else []) if c in sample.cols]
    by_post = bool(C.COVARIATES_BY_POST)
    diag_main = ["twfe", "dcounts", "effect", "repeat", "baseline"]
    specs = [twfe_spec("F0", sample, outcome, "did_term", [], diag=["twfe", "dcounts"] + (diag_main[2:] if not covs else []), outcome=outcome)]
    if covs:
        specs.append(twfe_spec("F1", sample, outcome, "did_term", covs, diag=diag_main, outcome=outcome, by_post=by_post))
        for c in covs:
            specs.append(twfe_spec(f"CR_{c}", sample, c, "did_term", [], extra_filters=[("finite", c)], diag=["twfe"], outcome=outcome, sd_col=c))
    seasons = sorted(sample.seasons) if len(sample.seasons) >= 2 else []
    for s_ in seasons:
        specs.append(twfe_spec(f"BS_{s_}", sample, outcome, "did_term", covs, extra_filters=[("season", s_)], diag=["twfe"], outcome=outcome, by_post=by_post))
        sw = twfe_spec(f"BW_{s_}", sample, "did_term", "did_term", [], extra_filters=[("season", s_)], diag=[], outcome=outcome)
        sw["filters"] = [("season", s_)]; specs.append(sw)
    fits = run_fits(sample, specs)
    tw, sols, errs = {}, {}, {}
    for sp in specs:
        if sp["name"].startswith("BW_"): continue
        t = TwfeFit(sample, fits[sp["name"]], sp["y"], "did_term", [x[1] for x in sp["x"][1:] if x[0] == "col"])
        try:
            sols[sp["name"]] = t.stage_a(); tw[sp["name"]] = t
        except Exception as e:
            if sp["name"] in ("F0", "F1"): raise
            errs[sp["name"]] = e
    scores = run_scores(sample, specs, sols)
    b0, s0 = tw["F0"].finish(scores["F0"])
    if covs:
        full = tw["F1"].finish(scores["F1"], return_all=True)
        beta, se = full["beta"], full["se"]
        C.info(f"canonical beta={b0:.6f} (se {s0:.6f}) | covariate-adjusted beta={beta:.6f} (se {se:.6f}) | controls: {full['coef']}")
        with C.resampling_scope():                          # as the in-memory M01: the bad-control fits leave the canonical fit's diagnostics alone
            rows = []
            for c in covs:
                nm = f"CR_{c}"
                try:
                    if nm in errs: raise errs[nm]
                    b, s_ = tw[nm].finish(scores[nm])
                    t = b / s_ if s_ else float("nan")
                    n_, m_, m2_ = fits[nm].sd_col
                    rows.append({"covariate": c, "did_on_covariate": float(b), "se": float(s_), "t": float(t),
                                 "moves_with_treatment": bool(np.isfinite(t) and abs(t) > 3.0),
                                 "sd_covariate": float(np.sqrt(m2_ / (n_ - 1))) if n_ > 1 else float("nan")})
                except Exception as e:
                    rows.append({"covariate": c, "did_on_covariate": float("nan"), "se": float("nan"), "t": float("nan"),
                                 "moves_with_treatment": None, "note": f"{type(e).__name__}: {str(e)[:120]}"})
            _cr = pd.DataFrame(rows); _cr.insert(0, "outcome", outcome)
            bad = _cr[_cr["moves_with_treatment"] == True]
            if len(bad):
                C.warn("BAD-CONTROL CHECK: " + ", ".join(f"{r.covariate} (t = {r.t:.1f})" for r in bad.itertuples()) + " move(s) with the treatment -- "
                       "a covariate the programme changes (e.g. land-SURFACE temperature, MODIS LST) absorbs part of the effect: read the "
                       "estimate WITHOUT covariates (beta_no_covariates)")
            else:
                C.info(f"bad-control check: no covariate moves with the treatment (|t| <= 3 for {', '.join(_cr['covariate'])})")
        C.save_results(_cr, results_dir, f"covariate_response_{outcome}.csv")
    else:
        beta, se, full = b0, s0, None
    res = {"outcome": outcome, "beta": beta, "se": se, "beta_no_covariates": b0, "se_no_covariates": s0,
           "covariates": str(list(covariates)) if use_covariates else "", "coef_all": str(full["coef"]) if full else "",
           "se_all": str(full["se_all"]) if full else "", "t_stat": beta / se if se else float("nan"), "control_zones": str(sample.control_zones_arg)}
    C.info(f"beta={beta:.6f}  se={se:.6f}  t={res['t_stat']:.2f}")
    C.save_results(res, results_dir, f"canonical_twfe_{outcome}.csv")
    if seasons:
        with C.resampling_scope():
            rows = []
            for s_ in seasons:
                nm = f"BS_{s_}"
                try:
                    if nm in errs: raise errs[nm]
                    b, s2 = tw[nm].finish(scores[nm])
                    G_ = int(C.LAST_FIT_INFO.get("n_clusters") or 2); p_ = float(2 * _st.t.sf(abs(b / s2), max(1, G_ - 1))) if s2 > 0 else np.nan
                    rows.append({"season": C.SEASON_LABEL.get(int(s_), s_), "estimate": b, "se": s2, "p_value": p_, "clusters": G_,
                                 "rows": int(fits[f"BW_{s_}"].n), "weight": float(max(fits[f"BW_{s_}"].M[0, 0], 0.0))})
                except Exception as e:
                    rows.append({"season": C.SEASON_LABEL.get(int(s_), s_), "estimate": np.nan, "se": np.nan, "p_value": np.nan, "clusters": np.nan,
                                 "rows": int(fits[f"BW_{s_}"].n), "weight": np.nan, "note": f"{type(e).__name__}: {str(e)[:80]}"})
            _bs = pd.DataFrame(rows); w = _bs["weight"].values
            _bs["weight"] = w / np.nansum(w) if np.nansum(w) > 0 else np.nan; _bs.insert(0, "outcome", outcome)
            C.info(f"{outcome} by season -- the pooled estimate is their weighted mean (weight = the treatment variation each season holds): "
                   + "; ".join(f"{r_.season} {r_.estimate:.4g} (SE {r_.se:.2g}, weight {100 * r_.weight:.0f} %)" for r_ in _bs.itertuples()))
        C.save_results(_bs, results_dir, f"by_season_{outcome}.csv")
    cl = [r["cf"] for r in sample.prep if r.get("cf") is not None and len(r["cf"])]
    c = pd.concat(cl, ignore_index=True).groupby("Year")[["sy", "sd", "n"]].sum().reset_index()
    cfs = pd.DataFrame({"Year": c["Year"].values, outcome: (c["sy"] / c["n"]).values, "Y_counterfactual": ((c["sy"] - beta * c["sd"]) / c["n"]).values})
    C.save_results(cfs, results_dir, f"counterfactual_{outcome}.csv")
    return res


def run_m02(sample, outcome, results_dir, balanced=False):
    C = _C()
    cov, periods, lo, hi = event_coverage(sample, -1)
    covs = list(C.DEFAULT_COVARIATES)
    specs = [event_spec("ES1", sample, outcome, periods, covs)]
    if covs: specs.insert(0, event_spec("ES0", sample, outcome, periods, []))
    fits = run_fits(sample, specs)
    evs, sols = {}, {}
    for sp in specs:
        e = EventFit(sample, fits[sp["name"]], outcome, periods, [x[1] for x in sp["x"] if x[0] == "col"], ref=-1, lo=lo, hi=hi, cov=cov)
        sols[sp["name"]] = e.stage_a(); evs[sp["name"]] = e
    scores = run_scores(sample, specs, sols)
    _es0 = evs["ES0"].finish(scores["ES0"]) if covs else None
    es = evs["ES1"].finish(scores["ES1"])
    h = C.event_headline(es, outcome, sample)
    if _es0 is not None:
        es = es.merge(_es0[["event_time", "beta", "se"]].rename(columns={"beta": "beta_no_covariates", "se": "se_no_covariates"}), on="event_time", how="left")
        es["covariates"] = ";".join(C.DEFAULT_COVARIATES)
    C.info(f"{len(es)} event-time coefficients | headline {h['estimate']:.6f} (SE {h['se']:.3g}, p {h['p_value']:.3g}; {h['se_how']})"); print(es.to_string(index=False))
    C.save_results(es, results_dir, f"event_study_{outcome}.csv")
    C.save_results(h, results_dir, f"event_study_headline_{outcome}.csv")
    return h


def run_m16(sample, outcome, results_dir):
    C = _C()
    yrs = sorted(set().union(*[set(r["m16"]["yrs"] or []) for r in sample.prep if r.get("m16")]))
    covs = list(C.DEFAULT_COVARIATES)
    specs = [pretrend_spec("PT1", sample, outcome, covs, yrs)]
    if covs: specs.append(pretrend_spec("PT0", sample, outcome, [], yrs))
    fits = run_fits(sample, specs)
    pts, sols = {}, {}
    for sp in specs:
        t = PretrendFit(sample, fits[sp["name"]], outcome, [x[1] for x in sp["x"] if x[0] == "col"])
        sols[sp["name"]] = t.stage_a(); pts[sp["name"]] = t
    scores = run_scores(sample, specs, sols)
    r = pts["PT1"].finish(scores["PT1"])
    if covs:
        _r0 = pts["PT0"].finish(scores["PT0"])
        r["f_stat_no_covariates"] = _r0.get("f_stat"); r["p_value_no_covariates"] = _r0.get("p_value")
        r["covariates"] = ";".join(C.DEFAULT_COVARIATES)
    (C.warn if (r["reject_parallel_trends_at_5pct"] or not r.get("test_reliable", True)) else C.ok)(
        f"F={r['f_stat']:.3f} p={r['p_value']:.4f} -> {r.get('verdict', 'see p-value')}")
    C.info(f"leads tested {r['leads_tested']} (df {r['df1']},{r['df2']}; covariance rank {r['vcov_rank']}, {r['n_clusters']} clusters)"
           + (f"; dropped {r['leads_dropped']}" if r["leads_dropped"] else "")
           + f"; leads: " + ", ".join(f"{k}: {b:+.4f} (se {r['lead_se'][k]:.4f})" for k, b in r["lead_coefficients"].items()))
    flat = {k: v for k, v in r.items() if k not in ("lead_coefficients", "lead_se", "leads_dropped", "leads_tested")}
    flat["leads_tested"] = ";".join(str(k) for k in r["leads_tested"]); flat["leads_dropped"] = ";".join(f"{k}:{v}" for k, v in r["leads_dropped"].items())
    for k, b in r["lead_coefficients"].items(): flat[f"beta_lead_{k}"] = b; flat[f"se_lead_{k}"] = r["lead_se"][k]
    C.save_results(flat, results_dir, f"pretrends_ftest_{outcome}.csv")
    return flat


def run_m34(sample, outcome, results_dir):
    C = _C()
    cov, periods, lo, hi = event_coverage(sample, -1)
    covs = list(C.DEFAULT_COVARIATES)
    specs = [event_spec("ES1", sample, outcome, periods, covs)]
    fits = run_fits(sample, specs)
    e = EventFit(sample, fits["ES1"], outcome, periods, [x[1] for x in specs[0]["x"] if x[0] == "col"], ref=-1, lo=lo, hi=hi, cov=cov)
    sols = {"ES1": e.stage_a()}
    scores = run_scores(sample, specs, sols)
    es = e.finish(scores["ES1"])
    r = C.honest_did_summary(es, outcome, sample)
    g = r.pop("grid")
    C.info(f"effect assessed {r['estimate']:.5f} (SE {r['se']:.3g}, p {r['p_value']:.3g}) | breakdown Mbar = {r['breakdown_Mbar']:.4g} -- {r['breakdown_how']}")
    C.save_results(g, results_dir, f"honest_did_grid_{outcome}.csv")
    C.save_results(r, results_dir, f"honest_did_{outcome}.csv")
    return r


RUNNERS = {"M01": run_m01, "M02": run_m02, "M16": run_m16, "M34": run_m34}


def ooc_model(model_id, outcome, panel, results_dir, control_zones=None, covariates=None, use_covariates=True, balanced=False):
    """The model's CELL 3 out of core. Returns the result the in-memory CELL 3 returns; writes the same files."""
    C = _C()
    if model_id not in RUNNERS:
        raise C.InsufficientDataError(f"{model_id} has no out-of-core path (the models with one: {', '.join(RUNNERS)}) -- beyond 98 % of the "
                                      f"RAM run it one sub-watershed at a time (08_Multisite_Runs/MS01)")
    t0 = time.time()
    try:
        sample = prepare_sample(panel, model_id, control_zones, ref=-1, pre_window=(-4, -2), balanced=bool(balanced and model_id == "M02"))
        sample.control_zones_arg = control_zones
        C.OOC_RUN["note"] = _headline_note(sample)
        if model_id == "M01":
            out = run_m01(sample, outcome, results_dir, covariates=covariates or (), use_covariates=use_covariates)
        elif model_id == "M02":
            out = run_m02(sample, outcome, results_dir, balanced=balanced)
        elif model_id == "M16":
            out = run_m16(sample, outcome, results_dir)
        else:
            out = run_m34(sample, outcome, results_dir)
        C.ok(f"{model_id} x {outcome}: estimated OUT OF CORE on {O.ENGINE_LABEL[panel.engine]} ({len(sample.paths)} pixel partitions, "
             f"{time.time() - t0:.1f} s) -- the same estimator and numbers as in memory (validate_out_of_core.py)")
        return out
    finally:
        if os.environ.get("REWARD_OOC_KEEP_PARTS") != "1": O.cleanup(panel)
