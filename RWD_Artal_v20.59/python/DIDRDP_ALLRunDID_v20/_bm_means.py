"""_bm_means.py -- v20.46: BENCHMARK (BM) SITES -> ONE REPRESENTATIVE VALUE PER SUB-WATERSHED.

Your rule: the BM files list sub-watersheds by name; each name has several rows (sites / points, visits, replicates)
and several variable columns. THE MEAN OF A SUB-WATERSHED'S BM SITES REPRESENTS THAT SUB-WATERSHED -- for every
sub-watershed (programme and control) and every variable.

How it is computed (nothing implicit):
  1. Variables are declared below -- file, column, name, physical bounds. No other column is ever averaged (IDs,
     coordinates, flags). A value outside its bounds is not a measurement and is dropped (counted in the audit).
  2. A site is a physical point: its median coordinates (lat_site, lon_site); without coordinates, institution +
     name + site number + micro-watershed.
  3. Names: spellings are unified ("Artal Sub Watershed" = "Artal Sub-Watershed", "Kandgul" = "Kandgula", ...).
     Every site is placed in the programme polygons (core / 1-5 km rings). A name whose sites lie >= 80 % inside ONE
     programme core IS that sub-watershed ("Koppal (4D4A2)" -> Murlapura; "Koranahalli and Haralahalli" -> Koranahalli);
     a blank name takes the programme core its site lies in, else the block name the file gives.
  4. A site counts for its sub-watershed only where its location agrees: a programme-named site in that sub-watershed's
     core or first 1-km ring; a control-named site anywhere EXCEPT inside a programme core. A site whose location
     contradicts its name is kept OUT of every mean and listed (BM_SITE_AUDIT.csv) -- never silently averaged in.
  5. Two stages, so every site counts once: (a) per site x Year x Season, the mean over its visits and replicates;
     (b) per sub-watershed x Year x Season, the mean over its sites (+ number of sites, spread between them).
"""
import os, re
import numpy as np
import pandas as pd

BM_VARIABLES = [   # (file, column, variable, lower, upper, lower_inclusive) -- physical bounds of a field measurement
    ("02_ground_ssm_long.csv", "ssm_mean_clean", "ssm_pct", 0.0, 60.0, False),          # volumetric %; 0 = oven-dry, not a field value
    ("03_ground_lai_long.csv", "lai_mean_clean", "lai", 0.0, 10.0, False),               # m2/m2; an exact 0 = all three replicates 0.0 = not measured (07 omits them)
    ("04_ground_gw_long.csv", "gw_depth_m", "gw_depth_m", 0.0, 300.0, True),             # metres below ground; < 0 is an entry error
    ("06_ground_tdr_rootzone_0_30cm_by_visit.csv", "moisture_pct", "tdr_rootzone_pct", 0.0, 60.0, False),  # 0-30 cm, harmonised layers
    ("06_ground_tdr_rootzone_0_30cm_by_visit.csv", "ec_ds_m", "tdr_rootzone_ec_ds_m", 0.0, 20.0, False),   # bulk EC, dS/m
    ("05_ground_tdr_long.csv", "soil_temp_c", "soil_temp_c", 0.0, 60.0, False),         # deg C (sparse)
]
SITE_NO_COLS = ("bm_site_no", "borewell_no", "probe_or_survey_no", "site_no", "survey_no")
from _names import PROGRAMME_ALIASES, norm_name, best_match, programme_candidates, cluster_names, NAME_MATCH_THRESHOLD   # v20.47: one rule
OTHER_CLUSTER_KM = 10.0                                                    # two >= 80 % similar control names must lie this close
NAME_BY_LOCATION_SHARE = 0.80
RING_TOLERANCE = 1                                                         # a programme-named site may sit up to 1 km outside

MEAN_COLUMNS = ["group", "site_id", "sws", "variable", "Year", "Season", "value", "sd_between_sites", "n_sites", "n_obs", "sws_shapefile"]
SITE_COLUMNS = ["file", "variable", "site_key", "sws_name", "block_name", "mws_name", "institution", "lat", "lon", "n_rows", "poly_id", "poly_ring",
                "poly_name", "name", "sws", "group", "site_id", "resolved_by", "decision", "reason"]

def _txt(col):
    """v20.49: text of a column, a blank cell written "nan" under EVERY pandas version. pandas 3 keeps a missing value
    missing through astype(str); the site key then became missing and groupby dropped the site (the ITGI control
    sub-watershed vanished under pandas 3 but not under pandas 2 -- 267 vs 275 rows)."""
    return col.astype(object).where(col.notna(), "nan").astype(str)

def _display(raw):
    n = norm_name(raw)
    if n in PROGRAMME_ALIASES: return PROGRAMME_ALIASES[n]
    raw = re.sub(r"\s*(sub[\s\-_]*watershed|\bsws\b)\s*", " ", str(raw), flags=re.I).strip()
    raw = re.sub(r"\(\s*control\s*\)", "", raw, flags=re.I).strip()          # v20.49: "ITGI (Control Sub-watershed)" -> "ITGI"
    return re.sub(r"\s+", " ", raw) if n else ""

def _locator():
    import _sws_geometry as G
    return G.SWSLocator.from_shapefile()

def _registry():
    import _sites as S
    reg = S.registry(); return {str(n): int(i) for n, i in zip(reg["name"], reg["SWSiD_All"])}

def load_bm_sites(ground_dir, variables=BM_VARIABLES):
    """Every BM value row, with a physical site key, its written name, its variable -- values outside bounds dropped."""
    rows, dropped = [], []
    for f, col, var, lo, hi, lo_inc in variables:
        p = os.path.join(ground_dir, f)
        if not os.path.exists(p): continue
        d = pd.read_csv(p, low_memory=False)
        if col not in d.columns: continue
        v = pd.to_numeric(d[col], errors="coerce")
        good = v.notna() & (v <= hi) & ((v >= lo) if lo_inc else (v > lo))
        dropped.append({"variable": var, "file": f, "column": col, "rows_with_value": int(v.notna().sum()),
                        "outside_bounds": int((v.notna() & ~good).sum()), "bounds": f"{'[' if lo_inc else '('}{lo}, {hi}]"})
        sn = next((c for c in SITE_NO_COLS if c in d.columns), None)
        lat = pd.to_numeric(d.get("lat_site"), errors="coerce") if "lat_site" in d.columns else pd.Series(np.nan, index=d.index)
        lon = pd.to_numeric(d.get("lon_site"), errors="coerce") if "lon_site" in d.columns else pd.Series(np.nan, index=d.index)
        name = d["sws_name"].fillna("").astype(str).str.strip()
        block = d["sws_name_block"].fillna("").astype(str).str.strip() if "sws_name_block" in d.columns else pd.Series("", index=d.index)
        key = np.where(lat.notna() & lon.notna(), f + "|" + lat.round(5).astype(str) + "," + lon.round(5).astype(str),
                       f + "|" + d.get("institution", pd.Series("", index=d.index)).fillna("").astype(str) + "|" + name + "|"
                       + (_txt(d[sn]) if sn else "") + "|" + d.get("mws_name", pd.Series("", index=d.index)).fillna("").astype(str))
        rows.append(pd.DataFrame({"variable": var, "file": f, "site_key": key, "sws_name": name, "block_name": block,
                                  "mws_name": d.get("mws_name", pd.Series("", index=d.index)).fillna("").astype(str),
                                  "institution": d.get("institution", pd.Series("", index=d.index)).fillna("").astype(str),
                                  "lat": lat, "lon": lon, "Year": pd.to_numeric(d["Year"], errors="coerce"),
                                  "Season": pd.to_numeric(d["Season"], errors="coerce"), "value": v.where(good)}))
    if not rows:                                        # no BM file found: an empty table with its columns
        return (pd.DataFrame(columns=["variable", "file", "site_key", "sws_name", "block_name", "mws_name", "institution", "lat", "lon", "Year", "Season", "value"]),
                pd.DataFrame(dropped, columns=["variable", "file", "column", "rows_with_value", "outside_bounds", "bounds"]))
    x = pd.concat(rows, ignore_index=True)
    x = x[x.value.notna() & x.Year.notna() & x.Season.notna()]
    return x, pd.DataFrame(dropped)

def _km(la1, lo1, la2, lo2):
    p = np.pi / 180; a = np.sin((la2 - la1) * p / 2) ** 2 + np.cos(la1 * p) * np.cos(la2 * p) * np.sin((lo2 - lo1) * p / 2) ** 2
    return 12742.0 * np.arcsin(np.sqrt(a))

def resolve_sites(x, locator=None, name_to_id=None):
    """One row per physical site: where it lies, what its name(s) say, which sub-watershed it counts for -- and why."""
    L = locator or _locator(); name_to_id = name_to_id or _registry(); id_to_name = {v: k for k, v in name_to_id.items()}
    s = (x.groupby(["file", "variable", "site_key"])
          .agg(sws_name=("sws_name", lambda v: next((a for a in v if a), "")), block_name=("block_name", lambda v: next((a for a in v if a), "")),
               mws_name=("mws_name", lambda v: next((a for a in v if a), "")), institution=("institution", "first"),
               lat=("lat", "first"), lon=("lon", "first"), n_rows=("value", "size")).reset_index())
    has = s.lat.notna() & s.lon.notna()
    s["poly_id"], s["poly_ring"] = 0, -1
    if has.any():
        sid, ring, _ = L.tag(s.loc[has, "lat"].values.astype(float), s.loc[has, "lon"].values.astype(float))
        s.loc[has, "poly_id"] = np.asarray(sid, dtype=int); s.loc[has, "poly_ring"] = np.asarray(ring, dtype=int)
    s.loc[s.poly_ring < 0, "poly_id"] = 0
    s["poly_name"] = s.poly_id.map(lambda i: id_to_name.get(int(i), "") if i else "")
    cands = programme_candidates(name_to_id.keys())
    raws = sorted(set(s.sws_name) | set(s.block_name) - {""})
    raws = [r for r in raws if r]
    prog_of, how_of = {}, {}
    for raw in raws:                                   # 1. programme names: known spellings; >= 80 % matches whose sites are in that core
        canon, sc, how = best_match(raw, cands)
        how_of[raw] = how
        if canon is None: continue
        if sc < 1.0:
            g = s[(s.sws_name == raw) & has]
            share = float(((g.poly_name == canon) & (g.poly_ring == 0)).mean()) if len(g) else None
            if share is not None and share < 0.5:
                how_of[raw] = f"{how}, but {1 - share:.0%} of its sites lie outside that core -- kept apart"; continue
        prog_of[raw] = canon
    for raw in raws:                                   # 2. a name whose sites lie >= 80 % in ONE programme core IS that sub-watershed
        if raw in prog_of: continue
        g = s[(s.sws_name == raw) & has]; core = g[g.poly_ring == 0].poly_name.value_counts()
        if len(g) and len(core) and core.iloc[0] >= NAME_BY_LOCATION_SHARE * len(g):
            prog_of[raw] = core.index[0]; how_of[raw] = f"its sites lie in the {core.index[0]} core"
    others = [r for r in raws if r not in prog_of]    # 3. other names: >= 80 % similar AND within 10 km -> one sub-watershed
    cen = {r: (s.loc[(s.sws_name == r) & has, "lat"].median(), s.loc[(s.sws_name == r) & has, "lon"].median()) for r in others}
    def near(a, b):
        (la, oa), (lb, ob) = cen[a], cen[b]
        if any(pd.isna(v) for v in (la, oa, lb, ob)): return True
        return _km(la, oa, lb, ob) <= OTHER_CLUSTER_KM
    other_of = {}
    for grp in cluster_names(others, allowed=near):
        disp = _display(max(grp, key=lambda r: int((s.sws_name == r).sum())))
        for r in grp:
            other_of[r] = disp
            if len(grp) > 1: how_of[r] = f">= 80 % similar to {', '.join(sorted(set(grp) - {r}))} and within {OTHER_CLUSTER_KM:.0f} km -> {disp}"
    eff = lambda r: prog_of.get(r) or other_of.get(r) or ""
    mws = {}                                           # micro-watershed -> sub-watershed where named rows say so unambiguously
    for m_, g in s[s.mws_name != ""].groupby(s.mws_name.map(norm_name)):
        nm = {eff(r) for r in list(g.sws_name) + list(g.block_name) if r and eff(r)}
        if len(nm) == 1: mws[m_] = nm.pop()
    out = []
    for r in s.itertuples():
        nm = eff(r.sws_name) if r.sws_name else ""
        how = how_of.get(r.sws_name, "name") if r.sws_name else ""
        if not nm:
            if r.poly_ring == 0: nm, how = r.poly_name, "no name: the site lies in this core"
            elif r.block_name and eff(r.block_name): nm, how = eff(r.block_name), "no name: the file's block name"
            elif norm_name(r.mws_name) in mws: nm, how = mws[norm_name(r.mws_name)], f"no name: micro-watershed '{r.mws_name}'"
        prog = nm in name_to_id
        if not nm: dec, why = "excluded", "no name, and the site lies in no programme core"
        elif prog:
            if r.poly_ring < 0 and not (pd.notna(r.lat) and pd.notna(r.lon)): dec, why = "counted", "no coordinates: by name"
            elif r.poly_name == nm and 0 <= r.poly_ring <= RING_TOLERANCE:
                dec, why = "counted", ("in the core" if r.poly_ring == 0 else f"{r.poly_ring} km ring (boundary tolerance)")
            else:
                where = (f"{r.poly_name} {'core' if r.poly_ring == 0 else f'ring {r.poly_ring}'}" if r.poly_name else "outside every programme sub-watershed")
                dec, why = "excluded", f"named {nm} but lies in {where}"
        else:
            if r.poly_ring == 0: dec, why = "excluded", f"a non-programme site inside the {r.poly_name} core (treated land)"
            else: dec, why = "counted", (f"near {r.poly_name} (ring {r.poly_ring})" if r.poly_name else "outside the programme polygons")
        out.append({"sws": nm, "group": "programme" if prog else ("control" if nm else ""), "site_id": name_to_id.get(nm, 0),
                    "resolved_by": how, "decision": dec, "reason": why})
    res = pd.concat([s, pd.DataFrame(out, index=s.index)], axis=1)
    res.attrs["name_rules"] = how_of
    return res

def bm_sws_means(ground_dir, locator=None, name_to_id=None):
    """(means, site_audit, bounds_report). means: one row per sub-watershed x variable x Year x Season."""
    x, bounds = load_bm_sites(ground_dir)
    if not len(x):                                      # no BM files / no valid values: empty tables WITH their columns
        means = pd.DataFrame(columns=MEAN_COLUMNS); means.attrs["name_table"] = pd.DataFrame(columns=["sws_name", "resolved_to", "how", "sites", "counted"])
        return means, pd.DataFrame(columns=SITE_COLUMNS), bounds if len(bounds) else pd.DataFrame(columns=["variable", "file", "column", "rows_with_value", "outside_bounds", "bounds"])
    sites = resolve_sites(x, locator, name_to_id)
    use = sites[sites.decision == "counted"][["file", "variable", "site_key", "sws", "group", "site_id"]]
    y = x.merge(use, on=["file", "variable", "site_key"], how="inner")
    st1 = (y.groupby(["group", "site_id", "sws", "variable", "site_key", "Year", "Season"])            # stage 1: within a site
             .agg(site_value=("value", "mean"), n_obs=("value", "size")).reset_index())
    means = (st1.groupby(["group", "site_id", "sws", "variable", "Year", "Season"])                    # stage 2: across its sites
               .agg(value=("site_value", "mean"), sd_between_sites=("site_value", "std"), n_sites=("site_key", "nunique"),
                    n_obs=("n_obs", "sum")).reset_index())
    means["Year"] = means.Year.astype(int); means["Season"] = means.Season.astype(int)
    means["sws_shapefile"] = np.where(means.group == "programme", means.sws, None)
    names = (sites.groupby("sws_name").agg(resolved_to=("sws", lambda v: "; ".join(sorted(set(a for a in v if a)))),
                                           how=("resolved_by", lambda v: next((a for a in v if a), "")), sites=("site_key", "nunique"),
                                           counted=("decision", lambda v: int((v == "counted").sum()))).reset_index())
    means.attrs["name_table"] = names
    return means, sites, bounds

def write_bm_reports(means, sites, bounds, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    if sites is None or not len(sites) or means is None or not len(means):
        open(os.path.join(out_dir, "BM_SWS_SUMMARY.md"), "w", encoding="utf-8").write(
            "# Benchmark sites -> one mean per sub-watershed\n\nNo BM value was found (REWARD_ground_inputs missing, or no valid values).\n")
        return
    sites.to_csv(os.path.join(out_dir, "BM_SITE_AUDIT.csv"), index=False)
    means.attrs.get("name_table", pd.DataFrame()).to_csv(os.path.join(out_dir, "ground_name_matching.csv"), index=False)
    ex = sites[sites.decision == "excluded"]
    md = ["# Benchmark sites -> one mean per sub-watershed", "",
          f"{sites.site_key.nunique()} physical sites x variables; {int((sites.decision == 'counted').sum())} counted, {len(ex)} excluded "
          "(location contradicts the name, or no name and no programme core). Each sub-watershed's value = the mean over its sites "
          "of each site's mean over visits and replicates (every site counts once).", "",
          "## Values outside physical bounds (not measurements)", "", "| variable | file | column | bounds | rows | dropped |", "|---|---|---|---|---|---|"]
    md += [f"| {r.variable} | {r.file} | {r.column} | {r.bounds} | {r.rows_with_value:,} | {r.outside_bounds:,} |" for r in bounds.itertuples()]
    md += ["", "## Sites per sub-watershed (counted)", "", "| sub-watershed | group | " + " | ".join(sorted(means.variable.unique())) + " |",
           "|---|---|" + "---|" * means.variable.nunique()]
    cnt = sites[sites.decision == "counted"].groupby(["sws", "group", "variable"]).site_key.nunique().unstack("variable").fillna(0).astype(int)
    for (sw, gr), r in cnt.iterrows(): md.append(f"| {sw} | {gr} | " + " | ".join(str(r.get(v, 0)) for v in sorted(means.variable.unique())) + " |")
    md += ["", "## Excluded sites (fix at source if the location or the name is wrong)", "", "| variable | name in file | site | reason |", "|---|---|---|---|"]
    md += [f"| {r.variable} | {r.sws_name or '(blank)'} | {r.lat:.5f}, {r.lon:.5f} | {r.reason} |" if pd.notna(r.lat) else
           f"| {r.variable} | {r.sws_name or '(blank)'} | (no coordinates) | {r.reason} |" for r in ex.sort_values(["reason", "variable"]).itertuples()]
    open(os.path.join(out_dir, "BM_SWS_SUMMARY.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
