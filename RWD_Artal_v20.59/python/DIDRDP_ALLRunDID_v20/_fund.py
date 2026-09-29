"""
_fund.py -- v20.57: YOUR FUND WORKBOOK AS EACH SUB-WATERSHED'S TREATMENT TIMING AND DOSE.

Input: Districtwise_Month_wise_Progress_with_DoseIntensity_and_SWS.xlsx (FUND_RELEASE_PATH in _paths.py), every layout
_prep_common.load_fund_progress reads (v3 "<SWS> SWS in <District>" + "Area in Hectare" rows -- your current file; v2
district + "SWS: <name>"; v1 district only, resolved through the crosswalk) and a flat table (SWS / Date / Progress [/ Area]).
The sub-watershed of every column is found by YOUR 80 % NAME RULE against the registry (data/sites/sites.csv).

Per sub-watershed and month (verified on your file: 20 sub-watersheds x 22 months, Oct 2024 - Jul 2026; the file's
Dose/Intensity = Progress / Target x 100 exactly; the Total column = the sum of the 20):
    amount_reported   the file's cumulative "Progress" (the amount released so far)
    amount            the CORRECTED cumulative amount: a later downward revision corrects the earlier reports, so the
                      amount at a month is the smallest amount reported at that month or any later month (running minimum
                      from the end). Your file has 30 such revisions (Murlapura -129.8 in one month); the v20.56 reader kept
                      the higher, revised-away amount for ever (a running maximum) and so over-stated later doses.
    dose per ha       amount / area_ha -- YOUR DEFINITION: the total amount divided by the total area of the treatment region
                      ("Area in Hectare (Cohort Size)" row = the core area in sites.csv; the registry area when absent)

TIMING -- every sub-watershed already had releases in the file's first month (Oct 2024), so the file cannot date the start
directly. FUND_START_RULE:
    "backcast"   (default) the releases before the file are extrapolated back at the rate observed right after it: the
                 start month = first month - ceil(amount at the first month / mean monthly release over the file's first
                 FUND_RATE_MONTHS months) + 1. A PROXY -- every report says so. On your file: Murlapura Oct 2023 ... Sirur Oct 2024.
    "share"      the first month the (back-cast / observed) amount reaches FUND_START_SHARE x Target
    "file_start" the file's first month (the same for all: a lower bound, not the start)
The treatment starts in the SEASON AFTER the start month (no anticipation). Seasons follow the exporter (artal_exporter
season_window): Zaid Y = Mar-May Y, Kharif Y = Jun-Sep Y, Rabi Y = Oct Y - Feb Y+1, the annual composite = Jan-Dec Y.
Per row, the first treated YEAR of its own series (the cohort the estimators read):
    seasonal row  = start year, + 1 when its season comes before the start season within that year
    annual row    = start year, + 1 when the treatment starts in Rabi (then only Oct-Dec of the start year is treated)
so post = Year >= cohort and event time = Year - cohort hold for every row. A year alone (registry / fixed timing) is the
start season Zaid of that year: every row's cohort = that year -- exactly the v20.56 rule.

DOSE per season = the amount released by the end of the PREVIOUS season (no anticipation) / area; 0 before the start; on
the back-cast line between the start and the file's first month (dose_estimated = 1; FUND_DOSE_BEFORE_FILE = "missing"
leaves those seasons out of the dose models); unknown after the file's last month. The annual row = the mean over its 12
calendar months of the dose in effect in each month.

The R pipeline (R/lib/reward_fund.R) computes the same tables; validate_r_parity.py compares them.
"""
import math, os, re
import numpy as np
import pandas as pd

FUND_START_RULE = "backcast"          # "backcast" | "share" | "file_start"
FUND_START_SHARE = 0.10               # "share": the start = the first month the amount reaches this share of the target
FUND_RATE_MONTHS = 12                 # "backcast": the rate = mean monthly release over the file's first 12 months
FUND_DOSE_BEFORE_FILE = "backcast"    # "backcast" (estimated, flagged) | "missing" (those seasons leave the dose models)

SEASON_RANK = {3: 0, 1: 1, 2: 2}      # Season code -> order within a Year (Zaid, Kharif, Rabi); 0 = the annual composite
RANK_SEASON = {0: 3, 1: 1, 2: 2}
SEASON_NAME = {0: "Yearly", 1: "Kharif", 2: "Rabi", 3: "Zaid"}


# ------------------------------------------------------------------ the export calendar (months as integers 12*y + m - 1)
def month_index(ts):
    ts = pd.Timestamp(ts); return int(ts.year) * 12 + int(ts.month) - 1

def month_label(mi):
    return f"{int(mi) // 12}-{int(mi) % 12 + 1:02d}"

def season_of_month(mi):
    """Season index q = 3 * Year + rank of the season that contains month mi."""
    y, m = divmod(int(mi), 12); m += 1
    if 3 <= m <= 5: return 3 * y
    if 6 <= m <= 9: return 3 * y + 1
    if m >= 10: return 3 * y + 2
    return 3 * (y - 1) + 2                                       # Jan / Feb: the tail of the previous year's Rabi

def last_month_of_season(q):
    y, r = divmod(int(q), 3)
    return {0: 12 * y + 4, 1: 12 * y + 8, 2: 12 * (y + 1) + 1}[r]

def q_of(year, season):
    return 3 * int(year) + SEASON_RANK[int(season)]


# ------------------------------------------------------------------ reading the workbook
def _registry():
    try:
        import _sites as _S
        r = _S.registry()
        return {int(k): str(v) for k, v in zip(r["SWSiD_All"], r["name"])}, \
               {int(k): float(v) for k, v in zip(r["SWSiD_All"], r.get("core_area", pd.Series([np.nan] * len(r))))}
    except Exception:
        return {}, {}

def match_site(name, names=None):
    """site_id for a sub-watershed name by the 80 % rule (None when no unambiguous match)."""
    import _names as _N
    names = names if names is not None else _registry()[0]
    if not names or name is None or (isinstance(name, float) and np.isnan(name)): return None
    cands = _N.programme_candidates(names.values())
    canon, _, _ = _N.best_match(str(name), cands)
    if canon is None: return None
    inv = {v: k for k, v in names.items()}
    return inv.get(canon)

def read_fund_monthly(path, crosswalk=None, verbose=True):
    """Long table: site_id, sws_name, district, area_ha, target, month (int), date, amount_reported."""
    import _prep_common as P
    names, core_area = _registry()
    flat = None
    try:
        t = pd.read_excel(path)
        low = {c: str(c).strip().lower() for c in t.columns}
        pick = lambda pat: next((c for c, l in low.items() if re.search(pat, l)), None)
        c_sws, c_date, c_prog = pick(r"sws|sub.?water"), pick(r"date|month"), pick(r"progress|release|amount")
        if c_sws is not None and c_date is not None and c_prog is not None and len({c_sws, c_date, c_prog}) == 3:
            dt_ = pd.to_datetime(t[c_date], errors="coerce")
            if dt_.notna().mean() >= 0.5:                                  # a FLAT table: one row per sub-watershed and date
                c_area, c_tgt = pick(r"area"), pick(r"target")
                flat = pd.DataFrame({"sws": t[c_sws].astype(str), "date": dt_,
                                     "amount_reported": pd.to_numeric(t[c_prog], errors="coerce"),
                                     "area_ha": pd.to_numeric(t[c_area], errors="coerce") if c_area is not None else np.nan,
                                     "target": pd.to_numeric(t[c_tgt], errors="coerce") if c_tgt is not None else np.nan, "district": ""})
    except Exception:
        flat = None
    if flat is not None and flat["date"].notna().any() and flat["sws"].str.len().gt(0).any():
        long = flat; layout = "flat table"
    else:
        w = P.load_fund_progress(path)
        layout = w.attrs.get("layout_version", "?")
        prog = next((c for c in w.columns if str(c).strip().lower().startswith("progress")), None)
        tgt = next((c for c in w.columns if str(c).strip().lower().startswith("target")), None)
        if prog is None: raise ValueError(f"fund file {path}: no 'Progress' metric (layout {layout})")
        sws = w["SWS"] if "SWS" in w.columns else pd.Series([np.nan] * len(w))
        if sws.isna().all() and crosswalk is not None:                        # v1: district only -> the crosswalk
            xw = dict(zip(crosswalk["District"].astype(str).str.strip().str.lower(), crosswalk["Sub Watershed Name"]))
            sws = w["District"].astype(str).str.strip().str.lower().map(xw)
        long = pd.DataFrame({"sws": sws.values, "district": w["District"].values, "date": pd.to_datetime(w["Date"]).values,
                             "amount_reported": pd.to_numeric(w[prog], errors="coerce").values,
                             "target": pd.to_numeric(w[tgt], errors="coerce").values if tgt is not None else np.nan,
                             "area_ha": pd.to_numeric(w.get("area_hectare", pd.Series([np.nan] * len(w))), errors="coerce").values})
    long = long[long["date"].notna()].copy()
    long["site_id"] = [match_site(s, names) for s in long["sws"]]
    unmatched = sorted(set(long.loc[long["site_id"].isna(), "sws"].astype(str)) - {"nan"})
    long = long[long["site_id"].notna()].copy()
    long["site_id"] = long["site_id"].astype(int)
    long["sws_name"] = long["site_id"].map(names)
    long["month"] = [month_index(d) for d in long["date"]]
    # area: the file's "Area in Hectare" of the treatment region; the registry's core area where the file has none
    a = long.groupby("site_id")["area_ha"].transform(lambda s: s.dropna().iloc[0] if s.notna().any() else np.nan)
    long["area_ha"] = a.fillna(long["site_id"].map(core_area))
    long["area_source"] = np.where(a.notna(), "fund file", "sites.csv core_area")
    long = long.sort_values(["site_id", "month"]).reset_index(drop=True)
    long.attrs.update({"layout": layout, "unmatched": unmatched})
    if verbose:
        P.ok(f"fund file ({layout}): {long.site_id.nunique()} sub-watersheds matched by the 80 % name rule, "
             f"{long.month.nunique()} months {month_label(long.month.min())} -> {month_label(long.month.max())}"
             + (f"; NOT matched: {unmatched}" if unmatched else ""))
    return long


# ------------------------------------------------------------------ series, timing, path, season dose
def fund_series(long):
    """Per site and month: the corrected cumulative amount, releases, revisions."""
    out = []
    for sid, g in long.groupby("site_id", sort=True):
        g = g.drop_duplicates("month", keep="last").sort_values("month").copy()
        rep = g["amount_reported"].astype(float).ffill().fillna(0.0).values
        corr = np.minimum.accumulate(rep[::-1])[::-1]                # later downward revisions correct the earlier reports
        g["amount"] = corr
        g["release"] = np.r_[corr[0], np.diff(corr)]
        g["revised_down_by"] = rep - corr
        g["share_of_target"] = g["amount"] / g["target"].where(g["target"] > 0)
        g["dose_per_ha"] = g["amount"] / g["area_ha"].where(g["area_ha"] > 0)
        out.append(g)
    return pd.concat(out, ignore_index=True) if out else long.assign(amount=np.nan)

def fund_timing(series, rule=None, share=None, rate_months=None):
    """One row per site: the start month by the rule, the first treated season and the cohort years."""
    rule = rule or FUND_START_RULE; share = FUND_START_SHARE if share is None else float(share)
    rate_months = int(rate_months or FUND_RATE_MONTHS)
    rows = []
    for sid, g in series.groupby("site_id", sort=True):
        g = g.sort_values("month"); mm = g["month"].values.astype(int); a = g["amount"].values.astype(float)
        m0, m1, a0 = int(mm[0]), int(mm[-1]), float(a[0])
        tgt = float(g["target"].dropna().iloc[0]) if g["target"].notna().any() else np.nan
        area = float(g["area_ha"].dropna().iloc[0]) if g["area_ha"].notna().any() else np.nan
        # the back-cast (always computed: it also gives the dose before the file)
        j = min(len(mm) - 1, rate_months - 1)
        rate = (a[j] - a[0]) / (mm[j] - mm[0]) if j > 0 and mm[j] > mm[0] else np.nan
        if a0 > 0 and np.isfinite(rate) and rate > 0:
            k = int(math.ceil(a0 / rate - 1e-9)); bc_start = m0 - k + 1; bc_note = f"back-cast at {rate:.4g} per month over the file's first {j + 1} months"
        elif a0 > 0:
            k = 1; bc_start = m0; bc_note = "no release after the first month to extrapolate: the file's first month (a lower bound)"
        else:
            pos = np.nonzero(a > 0)[0]; k = 0
            bc_start = int(mm[pos[0]]) if len(pos) else None; bc_note = "first release observed in the file"
        if rule == "share":
            thr = share * tgt if np.isfinite(tgt) else np.nan
            start = None; how = f"first month the amount reaches {share:.0%} of the target ({thr:.4g})"
            if np.isfinite(thr):
                if a0 >= thr and a0 > 0 and bc_start is not None and bc_start < m0 and k > 0:
                    # on the back-cast line: amount(m) = a0 * (m - bc_start + 1) / k
                    start = int(bc_start + max(0, math.ceil(thr / a0 * k - 1e-9) - 1)); how += " (on the back-cast line)"
                elif a0 >= thr:
                    start = m0
                else:
                    hit = np.nonzero(a >= thr)[0]; start = int(mm[hit[0]]) if len(hit) else None
        elif rule == "file_start":
            start = m0 if a0 > 0 else bc_start; how = "the file's first month (a lower bound of the start)"
        else:
            start = bc_start; how = bc_note
        rec = {"site_id": int(sid), "sws_name": g["sws_name"].iloc[0], "district": g["district"].iloc[0] if "district" in g else "",
               "area_ha": area, "area_source": g["area_source"].iloc[0] if "area_source" in g else "", "target": tgt,
               "first_month": month_label(m0), "last_month": month_label(m1), "amount_first_month": a0,
               "share_first_month": a0 / tgt if np.isfinite(tgt) and tgt > 0 else np.nan, "rate_per_month": rate,
               "months_before_file": k, "backcast_start": month_label(bc_start) if bc_start is not None else "",
               "backcast_start_index": bc_start, "start_rule": rule, "start_month": month_label(start) if start is not None else "",
               "start_index": start, "start_how": how, "censored": bool(a0 > 0 and rule != "backcast" and start == m0),
               "amount_last_month": float(a[-1]), "share_last_month": float(a[-1]) / tgt if np.isfinite(tgt) and tgt > 0 else np.nan,
               "revisions_down": int((g["revised_down_by"] > 1e-9).sum()), "largest_revision": float(g["revised_down_by"].max()),
               "file_first_index": m0, "file_last_index": m1}
        if start is not None:
            qs = season_of_month(start) + 1                               # the season AFTER the start month
            ys, rs = divmod(qs, 3)
            rec.update({"first_treated_year": int(ys), "first_treated_season": int(RANK_SEASON[rs]),
                        "first_treated_label": f"{SEASON_NAME[RANK_SEASON[rs]]} {ys}",
                        "cohort_annual": int(ys + (1 if rs == 2 else 0))})
        else:
            rec.update({"first_treated_year": None, "first_treated_season": None, "first_treated_label": "not reached in the file",
                        "cohort_annual": None})
        rows.append(rec)
    return pd.DataFrame(rows)

def amount_at(timing_row, series_site, mi, before_file=None):
    """(amount released by the END of month mi, estimated?) -- NaN when unknown."""
    before_file = before_file or FUND_DOSE_BEFORE_FILE
    m0, m1 = int(timing_row["file_first_index"]), int(timing_row["file_last_index"])
    if mi > m1: return np.nan, False
    if mi >= m0:
        s = series_site[series_site["month"] <= mi]
        return float(s["amount"].iloc[-1]), False
    bs, k, a0 = timing_row["backcast_start_index"], int(timing_row["months_before_file"]), float(timing_row["amount_first_month"])
    if bs is None or (isinstance(bs, float) and np.isnan(bs)) or k <= 0: return 0.0, False
    bs = int(bs)
    if mi < bs: return 0.0, False                                         # before any release: known zero
    if before_file == "missing": return np.nan, True
    return a0 * (mi - bs + 1) / k, True

def season_dose(series, timing, years, before_file=None):
    """site_id x Year x Season (0..3): dose_amount_sws, dose_intensity_per_ha, dose_share_of_target, dose_estimated."""
    rows = []
    for _, t in timing.iterrows():
        ss = series[series["site_id"] == t["site_id"]]
        area, tgt = t["area_ha"], t["target"]
        cache = {}
        _mm = ss["month"].values.astype(int); _am = ss["amount"].values.astype(float)     # v20.57: one sorted array per site
        def dose_q(q):
            if q not in cache:
                mi = last_month_of_season(q - 1)
                if int(t["file_first_index"]) <= mi <= int(t["file_last_index"]):      # inside the file: a binary search
                    j = int(np.searchsorted(_mm, mi, side="right")) - 1
                    cache[q] = (float(_am[j]), False) if j >= 0 else amount_at(t, ss, mi, before_file)
                else:
                    cache[q] = amount_at(t, ss, mi, before_file)
            return cache[q]
        for y in years:
            for code in (3, 1, 2):
                a, est = dose_q(q_of(y, code))
                rows.append((int(t["site_id"]), int(y), int(code), a, est))
            # the annual composite (Jan-Dec y): the mean over its 12 months of the dose in effect in each month
            vals, ests = [], []
            for m in range(1, 13):
                a, est = dose_q(season_of_month(12 * int(y) + m - 1))
                vals.append(a); ests.append(est)
            rows.append((int(t["site_id"]), int(y), 0, float(np.mean(vals)) if np.all(np.isfinite(vals)) else np.nan, bool(any(ests))))
    d = pd.DataFrame(rows, columns=["site_id", "Year", "Season", "dose_amount_sws", "dose_estimated"])
    d = d.merge(timing[["site_id", "area_ha", "target"]], on="site_id", how="left")
    d["dose_intensity_per_ha"] = d["dose_amount_sws"] / d["area_ha"].where(d["area_ha"] > 0)
    d["dose_share_of_target"] = d["dose_amount_sws"] / d["target"].where(d["target"] > 0)
    d["dose_estimated"] = d["dose_estimated"].astype("int8")
    return d.drop(columns=["area_ha", "target"])


# ------------------------------------------------------------------ the per-row cohort (first treated year of the row's series)
def site_start_from_timing(timing):
    """{site_id: [first treated year, its Season code]} for the sites the fund file dates."""
    t = timing.dropna(subset=["first_treated_year"])
    return {int(r.site_id): [int(r.first_treated_year), int(r.first_treated_season)] for r in t.itertuples()}

def row_cohort(site_ids, seasons, site_start, default_year):
    """Per row: the first Year in which THIS row's series (pixel x season) is treated. site_start: {site: [year, season]};
    a site without an entry starts in Zaid of default_year (a whole year: the v20.56 rule)."""
    sid = np.asarray(pd.to_numeric(pd.Series(site_ids), errors="coerce").fillna(0).astype(np.int64))
    se = np.asarray(pd.to_numeric(pd.Series(seasons), errors="coerce").fillna(0).astype(np.int64))
    ys = np.full(len(sid), int(default_year), dtype=np.int64); rs = np.zeros(len(sid), dtype=np.int64)
    for s, v in (site_start or {}).items():
        m = sid == int(s)
        if m.any():
            ys[m] = int(v[0]); rs[m] = SEASON_RANK.get(int(v[1]), 0)
    rank_row = np.vectorize(lambda c: SEASON_RANK.get(int(c), -1))(se) if len(se) else se
    later = np.where(se == 0, rs == 2, (rank_row >= 0) & (rank_row < rs))
    return ys + later.astype(np.int64)


# ------------------------------------------------------------------ v20.57: the tables AT THE MODEL STAGE (cached per workbook + rule)
_TABLES = {}

def file_identity(path):
    try: return (os.path.abspath(path), round(os.path.getmtime(path), 3), int(os.path.getsize(path)))
    except Exception: return (os.path.abspath(str(path)), None, None)

def fund_tables(path, years, rule=None, share=None, rate_months=None, before_file=None, crosswalk=None, verbose=True):
    """(timing, season_dose, series) for the rule in force -- read once per workbook version and rule, then served from RAM.
    Every model calls this when it runs (TREATMENT_TIMING = "fund", and for the dose of every timing), so a new start rule or
    a revised workbook takes effect without rebuilding the panel. None when the workbook is missing or unreadable."""
    rule = rule or FUND_START_RULE; share = FUND_START_SHARE if share is None else float(share)
    rate_months = int(rate_months or FUND_RATE_MONTHS); before_file = before_file or FUND_DOSE_BEFORE_FILE
    if rule not in ("backcast", "share", "file_start"): raise ValueError(f"FUND_START_RULE must be 'backcast', 'share' or 'file_start' (got {rule!r})")
    if before_file not in ("backcast", "missing"): raise ValueError(f"FUND_DOSE_BEFORE_FILE must be 'backcast' or 'missing' (got {before_file!r})")
    if not path or not os.path.exists(path): return None
    yrs = tuple(sorted({int(y) for y in years}))
    key = (file_identity(path), rule, round(share, 6), rate_months, before_file, yrs)
    if key in _TABLES: return _TABLES[key]
    long = read_fund_monthly(path, crosswalk=crosswalk, verbose=verbose)
    ser = fund_series(long); tim = fund_timing(ser, rule=rule, share=share, rate_months=rate_months)
    dose = season_dose(ser, tim, yrs, before_file=before_file)
    tim.attrs.update({"layout": long.attrs.get("layout"), "unmatched": long.attrs.get("unmatched", []), "path": path,
                      "rule": rule, "share": share, "rate_months": rate_months, "before_file": before_file})
    _TABLES.clear(); _TABLES[key] = (tim, dose, ser)
    return _TABLES[key]


# ------------------------------------------------------------------ one call: tables + reports
def build_fund_tables(path, years, out_dir=None, crosswalk=None, rule=None, verbose=True, share=None, rate_months=None, before_file=None):
    """Reads the workbook and writes FUND_TIMING.csv, FUND_SEASON_DOSE.csv, FUND_MONTHLY.csv and FUND_TIMING_AND_DOSE.md.
    Returns (timing, season_dose, series)."""
    import _prep_common as P
    got = fund_tables(path, years, rule=rule, share=share, rate_months=rate_months, before_file=before_file, crosswalk=crosswalk, verbose=verbose)
    if got is None: raise FileNotFoundError(f"fund workbook not found or unreadable: {path}")
    tim, dose, ser = got
    long = pd.DataFrame(); long.attrs.update({"layout": tim.attrs.get("layout"), "unmatched": tim.attrs.get("unmatched", [])})
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        tim.drop(columns=["backcast_start_index", "start_index", "file_first_index", "file_last_index"]).to_csv(os.path.join(out_dir, "FUND_TIMING.csv"), index=False)
        dose.to_csv(os.path.join(out_dir, "FUND_SEASON_DOSE.csv"), index=False)
        ser.assign(month=[month_label(m) for m in ser["month"]]).to_csv(os.path.join(out_dir, "FUND_MONTHLY.csv"), index=False)
        md = ["# Fund workbook -> treatment timing and dose (v20.57)", "",
              f"Source: `{path}` ({long.attrs.get('layout')}); {tim.site_id.nunique()} sub-watersheds by the 80 % name rule; "
              f"months {tim.first_month.min()} -> {tim.last_month.max()}. Start rule: **{tim.attrs.get('rule')}**"
              + (f" (share {tim.attrs.get('share'):.0%})" if tim.attrs.get('rule') == "share" else "")
              + f"; rate over the file's first {tim.attrs.get('rate_months')} months; dose before the file: {tim.attrs.get('before_file')}.", "",
              "Dose = the corrected cumulative amount released by the end of the previous season / the treatment area "
              "(the file's 'Area in Hectare' row). 'Start' is a PROXY when the file's first month already carries releases "
              "(every sub-watershed in your file): see `start_how`.", "",
              "| Sub-watershed | area (ha) | target | first month | amount then | share | back-cast rate / month | start | first treated season | annual cohort | share by last month | downward revisions |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in tim.sort_values("start_index", na_position="last").itertuples():
            md.append(f"| {r.sws_name} | {r.area_ha:,.1f} | {r.target:,.2f} | {r.first_month} | {r.amount_first_month:,.2f} | {r.share_first_month:.1%} | "
                      f"{r.rate_per_month:,.2f} | {r.start_month} | {r.first_treated_label} | {r.cohort_annual} | {r.share_last_month:.1%} | {r.revisions_down} |")
        if long.attrs.get("unmatched"): md += ["", f"Names NOT matched (no dose / timing for them): {long.attrs['unmatched']}"]
        open(os.path.join(out_dir, "FUND_TIMING_AND_DOSE.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
        if verbose: P.ok(f"fund timing and dose -> FUND_TIMING.csv, FUND_SEASON_DOSE.csv, FUND_TIMING_AND_DOSE.md in {out_dir}")
    return tim, dose, ser
