"""
ground_tdr.py -- TDR profile soil moisture / EC by depth
=========================================================
Layout A (UAHS, UASB, UHSB): the sheet is a set of side-by-side SWS blocks (each ~25 columns).
Within a block, attribute rows ('SWS Name', 'MWS Name', 'Latitude', 'Longitude', 'Probe No.' /
'Sy. No.', 'BM Site no', 'Irrigation type', 'Crop', 'Date & Time' / 'Date') give one value per
probe-column pair (Moisture %, EC dS/m); a 'Soil depth(cm)' row starts the depth rows
('0-10', '10-20', ... -- sometimes mangled by Excel into a datetime, e.g. '10-20' -> 2023-10-20).
Visits are stacked vertically: the attribute rows repeat for each visit. UASB writes one probe
with many DATE columns instead (dates in the 'Date' row, one (Moisture, EC) pair per date).

Layout B (UASR): 'Sl.No | Soil Phase | MWS name | Survey no. | Moisture (depth cols 10..90) |
Temperature (depth cols) | Electric Conductivity (depth cols)', one block per visit date given in a
'Date: dd/mm/yyyy' row; survey numbers carry a replicate suffix '(01)','(02)'.

UASD and IISc TDR sheets are empty templates.
"""
import re, datetime as dt
import numpy as np
import pandas as pd
from ground_utils import to_float, parse_coord, parse_date_any, harmonize_crop, clean_name
from ground_parsers import read_rows, _s, FILE_MAX_DATE

ATTR = {"sws": r"^sws\s*name", "mws": r"^mws\s*name", "lat": r"^lat", "lon": r"^lon", "probe": r"^(probe|sy\.?\s*no)",
        "bm": r"^bm\s*site", "irr": r"^irrigation", "crop": r"^crop", "date": r"^date", "depth": r"^soil\s*depth"}

def _depth_label(v):
    """'0-10' -> (0,10); datetime 2023-10-20 (mangled '10-20') -> (10,20); 20.0 -> (None,20) [single number
    = lower depth]; '0-15' -> (0,15). Returns (top, bottom, raw)."""
    if v is None:
        return None
    if isinstance(v, (dt.datetime, dt.date)):
        # Excel turned 'a-b' into a date: month=a, day=b (e.g. 10-20 -> Oct 20) or day=a, month=b
        a, b = v.month, v.day
        if a < b:
            return (a, b, f"{v.month}-{v.day}(from date)")
        return (b, a, f"{v.day}-{v.month}(from date)")
    if isinstance(v, (int, float)):
        return (None, float(v), str(v))
    s = str(v).strip()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)", s)
    if m:
        return (float(m.group(1)), float(m.group(2)), s)
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(cm)?$", s)
    if m:
        return (None, float(m.group(1)), s)
    return None

def parse_tdr_blocks(rows, inst):
    """Layout A."""
    # 1. find the block column starts: columns whose cell in some row is 'SWS Name' / 'MWS Name'
    starts = set()
    for r in rows:
        for j, c in enumerate(r):
            if re.match(r"^\s*(sws|mws)\s*name", _s(c), re.I):
                starts.add(j)
    starts = sorted(starts)
    if not starts:
        return pd.DataFrame()
    blocks = [(s0, (starts[k + 1] if k + 1 < len(starts) else len(max(rows, key=len)))) for k, s0 in enumerate(starts)]
    recs = []
    for c0, c1 in blocks:
        attrs = {}          # attribute name -> {col: value}
        depth_mode = False
        visit_id = 0
        col_dates = {}      # for UASB layout: per column pair date
        for i, r in enumerate(rows):
            label = _s(r[c0]) if c0 < len(r) else ""
            # attribute rows
            hit = None
            for n, pat in ATTR.items():
                if re.match(pat, label, re.I):
                    hit = n; break
            if hit == "depth":
                depth_mode = True; visit_id += 1
                # value columns = those with 'moisture' in this header row (paired with EC to the right)
                vcols = [j for j in range(c0 + 1, min(c1, len(r))) if re.search(r"moist", _s(r[j]), re.I)]
                if not vcols:      # UASR-like or missing header: assume alternating pairs
                    vcols = list(range(c0 + 1, c1, 2))
                continue
            if hit is not None:
                depth_mode = False
                if hit == "sws":
                    vals = {j: r[j] for j in range(c0 + 1, min(c1, len(r))) if _s(r[j])}
                    sws = next(iter(vals.values()), None) if vals else attrs.get("_sws")
                    attrs["_sws"] = sws
                else:
                    attrs[hit] = {j: r[j] for j in range(c0 + 1, min(c1, len(r))) if _s(r[j])}
                continue
            if not depth_mode:
                continue
            dl = _depth_label(r[c0] if c0 < len(r) else None)
            if dl is None:
                if label:            # some other text: end of depth rows for this visit
                    depth_mode = False
                continue
            top, bottom, raw = dl
            for j in vcols:
                if j >= len(r):
                    continue
                moist = to_float(r[j]); ec = to_float(r[j + 1]) if j + 1 < len(r) else np.nan
                flag = "" if not np.isnan(moist) else _s(r[j])
                if np.isnan(moist) and not flag:
                    continue
                def a(n, jj=j):
                    d = attrs.get(n, {})
                    # attribute given for this column, else the nearest attribute column to the left within the pair
                    for cand in (jj, jj - 1, jj + 1):
                        if cand in d and _s(d[cand]):
                            return d[cand]
                    return None
                dcell = a("date")
                d, fl = parse_date_any(dcell)
                recs.append({"institution": inst, "source_sheet": "TDR", "source_row": i + 1, "block_col": c0,
                             "visit_id": visit_id, "sws_name": clean_name(attrs.get("_sws")), "mws_name": clean_name(a("mws")),
                             "bm_site_no": _s(a("bm")), "probe_or_survey_no": _s(a("probe")),
                             "latitude": parse_coord(a("lat"), "lat"), "longitude": parse_coord(a("lon"), "lon"),
                             "irrigation_type": _s(a("irr")), "crop_raw": _s(a("crop")), "crop": harmonize_crop(a("crop")),
                             "date": d, "date_flag": fl, "depth_top_cm": top, "depth_bottom_cm": bottom, "depth_label": raw,
                             "moisture_pct": moist, "ec_ds_m": ec, "value_flag": flag})
    return pd.DataFrame(recs)

def parse_tdr_uasr(rows, inst):
    """Layout B (UASR): depths in columns."""
    recs = []; cur_date = pd.NaT; cur_sws = ""; depth_cols = None; cols = {}
    for i, r in enumerate(rows):
        txt = " ".join(_s(c) for c in r if _s(c))
        m = re.search(r"date\s*[:\-]?\s*(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})", txt, re.I)
        if m:
            cur_date, _ = parse_date_any(m.group(1)); continue
        if re.search(r"(itgi|hunse|jantapur|control)", txt, re.I) and re.search(r"tdr", txt, re.I):
            cur_sws = "ITGI (Control Sub-watershed)" if re.search(r"itgi", txt, re.I) else ("Hunsehadagli" if re.search(r"huns", txt, re.I) else txt)
            m2 = re.search(r"(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})", txt)
            if m2:
                cur_date, _ = parse_date_any(m2.group(1))
            continue
        low = [_s(c).lower() for c in r]
        if any(re.fullmatch(r"moisture", c) for c in low):
            cols = {"sl": 0}
            for j, c in enumerate(low):
                if re.search(r"soil\s*phase", c): cols["soil"] = j
                elif re.search(r"mws", c): cols["mws"] = j
                elif re.search(r"survey", c): cols["survey"] = j
                elif re.fullmatch(r"moisture", c): cols["m0"] = j
                elif re.search(r"temperature", c): cols["t0"] = j
                elif re.search(r"conductivity", c): cols["e0"] = j
            depth_cols = None
            continue
        if cols and "m0" in cols and depth_cols is None and any(re.search(r"depth", c) for c in low):
            continue
        if cols and "m0" in cols and depth_cols is None:
            nums = [(j, to_float(c)) for j, c in enumerate(r) if not np.isnan(to_float(c))]
            if nums and all(v in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 15, 45, 75) for _, v in nums):
                depth_cols = {j: v for j, v in nums}
                continue
        if not cols or depth_cols is None:
            continue
        survey = _s(r[cols["survey"]]) if "survey" in cols and cols["survey"] < len(r) else ""
        mws = _s(r[cols["mws"]]) if "mws" in cols and cols["mws"] < len(r) else ""
        soil = _s(r[cols["soil"]]) if "soil" in cols and cols["soil"] < len(r) else ""
        if not survey and not mws:
            continue
        if not mws and recs:
            mws = recs[-1]["mws_name"]; soil = soil or recs[-1]["soil_phase"]
        rep = ""
        mrep = re.search(r"\((\d+)\)", survey)
        if mrep:
            rep = mrep.group(1); survey = survey[:mrep.start()].strip()
        m0 = cols["m0"]; t0 = cols.get("t0"); e0 = cols.get("e0")
        for j, depth in depth_cols.items():
            if j < m0 or (t0 is not None and j >= t0):
                continue
            k = j - m0
            moist = to_float(r[j]) if j < len(r) else np.nan
            if np.isnan(moist):
                continue
            temp = to_float(r[t0 + k]) if (t0 is not None and t0 + k < len(r)) else np.nan
            ec = to_float(r[e0 + k]) if (e0 is not None and e0 + k < len(r)) else np.nan
            recs.append({"institution": inst, "source_sheet": "TDR", "source_row": i + 1, "block_col": 0, "visit_id": 0,
                         "sws_name": cur_sws, "mws_name": clean_name(mws), "bm_site_no": "", "probe_or_survey_no": survey + (f" rep{rep}" if rep else ""),
                         "latitude": np.nan, "longitude": np.nan, "irrigation_type": "", "crop_raw": "", "crop": "unknown",
                         "date": cur_date, "date_flag": "" if pd.notna(cur_date) else "unparsed",
                         "depth_top_cm": depth - 10, "depth_bottom_cm": depth, "depth_label": str(depth),
                         "moisture_pct": moist, "ec_ds_m": ec, "soil_temp_c": temp, "value_flag": "", "soil_phase": soil})
    return pd.DataFrame(recs)

def parse_tdr(path, inst):
    rows = read_rows(path, "TDR")
    if inst == "UASR":
        return parse_tdr_uasr(rows, inst)
    df = parse_tdr_blocks(rows, inst)
    if len(df):
        from ground_utils import resolve_ddmm_by_sequence
        df["_row"] = df["source_row"] * 10000 + df["block_col"]
        key = ["institution", "block_col", "mws_name", "probe_or_survey_no", "bm_site_no", "depth_label"]
        df = resolve_ddmm_by_sequence(df, key, max_date=pd.Timestamp(FILE_MAX_DATE.get(inst, "2026-09-13")),
                                      min_date=pd.Timestamp("2023-03-01")).drop(columns="_row")
    return df
