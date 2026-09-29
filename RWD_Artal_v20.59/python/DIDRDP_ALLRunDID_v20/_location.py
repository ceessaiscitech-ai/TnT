"""
_location.py -- v20.58, THE LOCATION RULE -- YOUR RULE: only the CURRENT sub-watershed's own data enter a DiD.

Every row's LOCATION is known from the shapefile overlay the panel preparation wrote (site_id = the sub-watershed whose polygon holds
the pixel, site_check = 0 confirmed / 1 corrected / 2 assigned / 3 OUTSIDE every polygon / 4 not checked). A DiD uses a row only when
its pixel lies in a polygon (core or ring) of a sub-watershed THIS RUN processes -- the processing set:
    SUB_WATERSHEDS = "data" (default)  every sub-watershed with at least FRAGMENT_MIN_SHARE (5 %) of the largest one's own rows: ONE
                                       export -> its own sub-watershed (the major one); a pooled panel -> every sub-watershed exported.
                                       A neighbour's piece or a stray file (a few % of the rows) is not processed.
                     "major"           the largest sub-watershed only  |  names or ids ("Koranahalli", [1, 7])
    SITE_FILTER (the MS01 loop over sub-watersheds) sets the processing set of each pass.
Row codes (identical in R: lib/reward_design.R location_codes_R):
    0  kept
    1  another sub-watershed's data -- its sub-watershed is not processed in this run (a neighbour, a stray file, no id)  FRAGMENT_RULE
    2  outside every sub-watershed polygon of the shapefile (site_check 3)                                              FRAGMENT_RULE
    3  overlap -- a control row of a pixel that is TREATED (core) in another processed sub-watershed; a pixel-year-season
       already in the sample for another processed sub-watershed (the row nearest its core stays); the smaller of two pixels
       whose footprints overlap >= PIXEL_OVERLAP_MIN                                                                    OVERLAP_ROWS
    4  the pixel's ring differs between its rows (the exports code it differently -- treated in one year, a control in another)
                                                                                                                         OVERLAP_ROWS
"drop" (the default of both) leaves them out of EVERY group -- treated and control, pre and post; "keep" keeps them (flagged).
Until v20.57 the rule looked at each export FILE (_fragments.py, now a report only): the rows OUTSIDE every polygon of a NAMED file
stayed in, and rows without a sub-watershed (site 0) counted as a SECOND sub-watershed in the design-based SE.
"""
import numpy as np
import pandas as pd

IN_POLYGON = (0, 1, 2, 4)
OUTSIDE = 3
TEXT = {1: "another sub-watershed's data (not processed in this run)", 2: "outside every sub-watershed polygon",
        3: "overlap (a pixel treated in another processed sub-watershed, repeated, or a near-duplicate)",
        4: "the pixel's ring differs between its rows"}


def _ints(x, fill=0):
    return pd.to_numeric(pd.Series(np.asarray(x)), errors="coerce").fillna(fill).astype(np.int64).values


def processing_set(own, setting="data", min_share=0.05, name_to_id=None, names=None):
    """(sorted site ids, how) -- own: {site_id: own rows (inside its polygons)}."""
    own = {int(k): float(v) for k, v in (own or {}).items() if int(k) > 0 and float(v) > 0}
    names = names or {}
    nm = lambda k: names.get(int(k), f"site {int(k)}")
    if not own:
        return [], "no sub-watershed id in the panel: the location rule has nothing to go on (every row is kept)"
    st = setting if isinstance(setting, (list, tuple, set, np.ndarray)) else [setting]
    st = [s for s in st if s is not None and str(s).strip() != ""] or ["data"]
    if len(st) == 1 and str(st[0]).strip().lower() in ("data", "recommended", "auto"):
        top = max(own.values()); s = sorted(k for k, v in own.items() if v >= float(min_share) * top)
        left = sorted(((k, v) for k, v in own.items() if v < float(min_share) * top), key=lambda kv: -kv[1])
        how = (f"data: every sub-watershed with >= {100 * float(min_share):g} % of the largest one's own rows -> "
               + ", ".join(f"{nm(k)} ({k})" for k in s)
               + ("; not processed: " + ", ".join(f"{nm(k)} ({int(v):,} rows, {100 * v / top:.1f} %)" for k, v in left) if left else ""))
        return s, how
    if len(st) == 1 and str(st[0]).strip().lower() == "major":
        k = sorted(own.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        return [int(k)], f"major: {nm(k)} ({k}), the largest"
    ids = []
    for x in st:
        try:
            ids.append(int(float(x))); continue
        except (TypeError, ValueError):
            pass
        sid = name_to_id(str(x)) if name_to_id is not None else None
        if sid is None:
            raise ValueError(f"SUB_WATERSHEDS: no sub-watershed matches {x!r} (your 80 % name rule)")
        ids.append(int(sid))
    miss = [k for k in ids if k not in own]
    if len(miss) == len(ids):
        raise ValueError(f"SUB_WATERSHEDS: none of {st} is in this panel (it holds {', '.join(nm(k) for k in sorted(own))})")
    s = sorted(set(k for k in ids if k in own))
    return s, "your setting: " + ", ".join(f"{nm(k)} ({k})" for k in s) + (f" ({', '.join(nm(k) for k in miss)} not in this panel)" if miss else "")


def row_codes(site_id, site_check, pixel_id, buff_km, year, season, S, ring_conflict=None, near_dup=None, pooled_checks=True):
    """The location code of every row (numpy int8). ring_conflict: set of (site_id, pixel_id); near_dup: set of losing pixel ids.
    pooled_checks: the whole-frame checks (a control row of a pixel treated in another processed sub-watershed; a repeated
    pixel-year-season) -- they need every row of the sample at once."""
    n = len(site_id)
    code = np.zeros(n, dtype=np.int8)
    if not n: return code
    sid = _ints(site_id); chk = _ints(site_check, 4) if site_check is not None else np.full(n, 4, np.int64)
    pid = np.asarray(pixel_id); bk = _ints(buff_km, -1)
    code[chk == OUTSIDE] = 2
    if S is not None and len(S):
        code[(code == 0) & ~np.isin(sid, np.asarray(list(S), dtype=np.int64))] = 1
    if ring_conflict:
        m = pd.MultiIndex.from_arrays([sid, pid]).isin(list(ring_conflict))
        code[(code == 0) & np.asarray(m)] = 4
    if near_dup:
        code[(code == 0) & pd.Series(pid).isin(near_dup).values] = 3
    if pooled_checks:
        k = np.flatnonzero(code == 0)
        if len(k):
            core = pd.DataFrame({"p": pid[k][bk[k] == 0], "cs": sid[k][bk[k] == 0]}).drop_duplicates()
            if len(core):
                cand = k[bk[k] > 0]
                if len(cand):
                    m = pd.DataFrame({"r": cand, "p": pid[cand], "s": sid[cand]}).merge(core, on="p", how="inner")
                    bad = m.loc[m["cs"].values != m["s"].values, "r"].unique()
                    if len(bad): code[bad] = 3
            k = np.flatnonzero(code == 0)
            if len(k):
                o = pd.DataFrame({"i": k, "p": pid[k], "y": _ints(year)[k], "q": _ints(season)[k], "b": bk[k], "s": sid[k]})
                o = o.sort_values(["p", "y", "q", "b", "s"], kind="mergesort")
                rep = o.loc[o.duplicated(["p", "y", "q"], keep="first"), "i"].values
                if len(rep): code[rep] = 3
    return code


def near_dup_losers(reg, pairs):
    """{loser pixel id: keeper pixel id} for pairs (i, j, overlap) of a registry (pixel_id, n_rows): the pixel with more rows stays
    (then the lower id) -- as R's location_table_R."""
    if pairs is None or not len(pairs): return {}
    a = reg.iloc[pairs["i"].values].reset_index(drop=True); b = reg.iloc[pairs["j"].values].reset_index(drop=True)
    a_wins = (a["n_rows"].values > b["n_rows"].values) | ((a["n_rows"].values == b["n_rows"].values) & (a["pixel_id"].values < b["pixel_id"].values))
    los = np.where(a_wins, b["pixel_id"].values, a["pixel_id"].values); kee = np.where(a_wins, a["pixel_id"].values, b["pixel_id"].values)
    out = {}
    for l_, k_ in zip(los.tolist(), kee.tolist()):
        out.setdefault(l_, k_)
    return out
