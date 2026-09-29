"""
_fragments.py -- v20.57, YOUR RULE: the MAJOR sub-watershed data are processed; smaller fragments of other sub-watersheds
-- treatment (core) or control (ring) rows alike -- are removed.

Where fragments come from: an export file of one sub-watershed also holds points that the shapefile overlay puts in ANOTHER
sub-watershed's polygon, or points outside every polygon that keep the (unreliable) SWSiD_All the exporter wrote. In v20.56
they stayed in the panel as a second sub-watershed: a single-sub-watershed run became a "pooled" run of 2 sub-watersheds
("years within each of 2 sub-watersheds", site x period fixed effects, a second cohort). The v20.55 OVERLAP_ROWS rule did
not touch them -- it only handles a pixel that is TREATED in one sub-watershed and a control in another.

Per export file (panel preparation writes the code into the panel's `fragment` column):
  0  the row belongs to its file's OWN sub-watershed -- the one holding MORE THAN HALF of the file's rows that lie inside a
     sub-watershed polygon -- or the file has no such majority (a genuine multi-sub-watershed export: every row kept)
  1  inside the polygon of ANOTHER sub-watershed than its file's own                               -> a fragment
  2  outside every polygon and carrying another sub-watershed's id than its file's own            -> a fragment
Across the panel (applied at the MODEL stage, so you can change it without rebuilding the panel):
  3  a sub-watershed whose kept (code 0) rows are fewer than FRAGMENT_MIN_SHARE x those of the largest sub-watershed is a
     fragment as a whole (a stray file of a neighbour)                                               -> a fragment
FRAGMENT_RULE (model stage, CELL 1 / the R model notebook): "drop" (default) leaves codes 1-3 out of every estimate |
"keep" keeps every row (the counts are reported either way).

A panel written before v20.57 has no `fragment` column: the SAME rule is applied at the model stage with the sub-watershed
id each input file carried (sws_id_export; R: sws_export) standing in for the file -- so the v20.56 panel does not have to be
rebuilt. R: lib/reward_design.R (fragment_* functions) does the same, row for row (validate_design_options.py).
"""
import numpy as np
import pandas as pd

IN_POLYGON = (0, 1, 2, 4)          # site_check: confirmed, corrected, assigned, not checked (no geometry: the indicated id stands)
OUTSIDE = 3
FILE_MAJORITY = 0.5                # the file's own sub-watershed holds MORE than this share of its in-polygon rows
FRAGMENT_MIN_SHARE = 0.05          # a sub-watershed with fewer kept rows than this share of the largest one is a fragment
CODE_TEXT = {0: "kept (the file's own sub-watershed)", 1: "inside ANOTHER sub-watershed's polygon than its file's own",
             2: "outside every polygon with another sub-watershed's id", 3: "a minor sub-watershed of the panel (stray file)"}


def _ints(x, fill=0):
    return pd.to_numeric(pd.Series(np.asarray(x)), errors="coerce").fillna(fill).astype(np.int64).values


def file_major(site_id, site_check, majority=None):
    """The sub-watershed holding more than `majority` of the in-polygon rows (None = no majority / no in-polygon rows)."""
    majority = FILE_MAJORITY if majority is None else float(majority)
    s = _ints(site_id); c = _ints(site_check, 4)
    inp = np.isin(c, IN_POLYGON)
    if not inp.any(): return None
    vals, cnt = np.unique(s[inp], return_counts=True)
    k = int(np.argmax(cnt))
    return int(vals[k]) if cnt[k] > majority * inp.sum() else None


def file_codes(site_id, site_check, majority=None):
    """Per-row fragment codes (0 / 1 / 2) of ONE export file, and the file's own sub-watershed (None = no majority)."""
    s = _ints(site_id); c = _ints(site_check, 4)
    codes = np.zeros(len(s), dtype=np.int8)
    major = file_major(s, c, majority)
    if major is not None:
        inp = np.isin(c, IN_POLYGON)
        codes[inp & (s != major)] = 1
        codes[(~inp) & (s != major)] = 2
    return codes, major


def group_codes(group_id, site_id, site_check, majority=None):
    """The fallback for a panel without `fragment`: file_codes applied within each group of rows that carried the same input
    sub-watershed id (sws_id_export) -- the file stands in by the id it wrote. Returns (codes, {group: major})."""
    g = _ints(group_id); s = _ints(site_id); c = _ints(site_check, 4)
    codes = np.zeros(len(s), dtype=np.int8); majors = {}
    t = pd.DataFrame({"g": g, "s": s, "c": c})
    for gid, idx in t.groupby("g", sort=True).groups.items():
        ii = np.asarray(idx)
        cd, mj = file_codes(s[ii], c[ii], majority)
        codes[ii] = cd; majors[int(gid)] = mj
    return codes, majors


def combo_table(counts, majority=None):
    """From counts over (sws_id_export, site_id, site_check) -> the code of each combination (the fallback, computed ONCE
    over the whole panel and applied to every chunk). counts: DataFrame g, s, c, n."""
    majority = FILE_MAJORITY if majority is None else float(majority)
    out = counts.copy(); out["code"] = 0
    for gid, t in counts.groupby("g", sort=True):
        inp = t["c"].isin(IN_POLYGON)
        if not inp.any(): continue
        by = t[inp].groupby("s")["n"].sum()
        top = int(by.idxmax())
        if by.max() <= majority * by.sum(): continue                      # no majority: a multi-sub-watershed group
        m1 = inp & (t["s"] != top); m2 = (~inp) & (t["s"] != top)
        out.loc[t.index[m1.values], "code"] = 1; out.loc[t.index[m2.values], "code"] = 2
    out["code"] = out["code"].astype(np.int8)
    return out


def minor_sites(site_counts, min_share=None):
    """Sub-watersheds (site_id; 0 = none) whose kept rows are fewer than min_share x the largest one's. site_counts: {site: n}."""
    min_share = FRAGMENT_MIN_SHARE if min_share is None else float(min_share)
    if not site_counts: return []
    top = max(site_counts.values())
    return sorted(int(s) for s, n in site_counts.items() if top > 0 and n < min_share * top)


def row_codes(frame, combos=None):
    """The fragment code of every row of a frame: its `fragment` column when present (a v20.57 panel), else the combination
    table of the fallback (sws_id_export, site_id, site_check), else 0 (nothing to go on)."""
    n = len(frame)
    if "fragment" in frame.columns:
        return _ints(frame["fragment"]).astype(np.int8)
    if combos is not None and len(combos) and {"sws_id_export", "site_id", "site_check"} <= set(frame.columns):
        key_t = (combos["g"].astype(np.int64) * 100000 + combos["s"].astype(np.int64)) * 10 + combos["c"].astype(np.int64)
        key_r = (_ints(frame["sws_id_export"]) * 100000 + _ints(frame["site_id"])) * 10 + _ints(frame["site_check"], 4)
        idx = pd.Index(key_t.values).get_indexer(key_r)
        out = np.zeros(n, dtype=np.int8)
        ok_ = idx >= 0
        out[ok_] = combos["code"].values[idx[ok_]]
        return out
    return np.zeros(n, dtype=np.int8)
