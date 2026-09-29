"""
ground_parsers.py -- read the five institutions' 'Bench marks sites hydrology data' workbooks
==========================================================================================
Every institution laid its sheets out differently (long, wide-by-date, side-by-side blocks,
block-per-date). These parsers locate header rows by their column NAMES ('SSM1', 'LAI1',
'Borewell number', 'GW Depth', ...) rather than by fixed positions, so a re-export with a few
extra rows still parses. Every output row carries: institution, source_sheet, source_row,
and a date_flag / value_flag so nothing is silently guessed.

Outputs (long format, one measurement per row):
    parse_ssm(path, inst)  -> surface soil moisture (3 replicates + mean)
    parse_lai(path, inst)  -> leaf area index (3 replicates + mean)
    parse_gw(path, inst)   -> manual groundwater depth (monthly, m below ground level)
"""
import re, datetime as dt
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from ground_utils import (to_float, text_flag, parse_coord, parse_date_any, harmonize_crop,
                          clean_name, resolve_ddmm_by_sequence)
import datetime as dt

def read_rows(path, sheet):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    return [list(r) for r in ws.iter_rows(values_only=True)]

def _s(v):
    return "" if v is None else str(v).strip()

def _find_cols(header, patterns, start, end):
    """Return {name: col_index} for the NEAREST header cell before `end` (searching backwards to
    `start`) matching each pattern -- so a block picks up its own Date/Crop column, not an earlier one."""
    out = {}
    for name, pat in patterns.items():
        for j in range(end - 1, start - 1, -1):
            h = _s(header[j]).lower() if j < len(header) else ""
            if h and re.search(pat, h):
                out[name] = j
                break
    return out

SITE_PATTERNS = {
    "sws": r"^sws\s*name", "mws": r"^mws\s*name", "bm": r"^bm\s*site", "district": r"^district",
    "date": r"^date", "time": r"^time", "lat": r"^lat", "lon": r"^lon", "survey": r"^(survey|sy)",
    "soil": r"^soil\s*(phase|type|texture)", "crop": r"(type\s*of\s*crop|^crop\s*name|^crop$|^crop\b(?!\s*ht))",
    "area": r"^area", "texture": r"^soil\s*texture", "bench": r"^benchmark\s*site",
}

# ============================================================== SSM & LAI (generic block parser)
def _build_blocks(header, above, val_prefix):
    v1_cols = [j for j, c in enumerate(header) if re.fullmatch(rf"{val_prefix}\s*1", _s(c).lower())]
    v3_only = [j - 2 for j, c in enumerate(header) if re.fullmatch(rf"{val_prefix}\s*3", _s(c).lower())
               and not any(re.fullmatch(rf"{val_prefix}\s*[12]", _s(header[jj]).lower()) for jj in (j - 1, j - 2) if 0 <= jj < len(header))]
    anchors = sorted([(j, True) for j in v1_cols] + [(j, False) for j in v3_only])
    blocks = []
    prev_end = 0
    first_site = None
    for k, (j, has12) in enumerate(anchors):
        cols = _find_cols(header, SITE_PATTERNS, prev_end, j + (0 if has12 else 2))
        if has12:
            cols["v1"], cols["v2"], cols["v3"] = j, j + 1, j + 2
        else:
            cols["v1"], cols["v2"], cols["v3"] = None, None, j + 2
        end = j + 3
        for jj in range(j + 3, min(j + 7, len(header))):
            hh = _s(header[jj]).lower()
            if re.search(r"avg|average|mean", hh):
                cols["avg"] = jj; end = jj + 1
            elif re.search(r"remark", hh):
                cols["remark"] = jj; end = jj + 1
            else:
                break
        cols.update(_find_cols(header, {"crop_ht": r"^crop\s*ht", "das": r"^das$"}, prev_end, j))
        blk_date = pd.NaT
        for jj in range(max(prev_end, 0), j + 3):
            if jj < len(above) and re.match(r"^\s*date", _s(above[jj]), re.I):
                blk_date, _ = parse_date_any(_s(above[jj]))
                if pd.notna(blk_date):
                    break
        cols["_blk_date"] = blk_date
        if first_site is None:
            first_site = {n: cols[n] for n in ("sws", "mws", "bm", "district", "lat", "lon", "survey", "soil", "area", "texture", "bench") if n in cols}
            cols["_inherits"] = False
        elif not any(n in cols for n in ("lat", "lon", "sws", "mws")):
            cols = {**first_site, **cols}; cols["_inherits"] = True
        else:
            cols["_inherits"] = False
        blocks.append(cols)
        prev_end = end
    return blocks

def _header_fit(blocks, row):
    """How many blocks' date cells parse as dates AND whose V3 cell is numeric on a given data row."""
    n = 0
    for cols in blocks:
        jd = cols.get("date"); jv = cols.get("v3")
        if jd is None or jv is None or jd >= len(row) or jv >= len(row):
            continue
        d, _ = parse_date_any(row[jd])
        if pd.notna(d) and not np.isnan(to_float(row[jv])):
            n += 1
    return n

def _parse_replicate_sheet(rows, inst, sheet, var, val_prefix, extra_val_patterns=None):
    """Generic parser for sheets whose header row(s) contain <val_prefix>1, <val_prefix>2, <val_prefix>3.
    Handles: long format (one record per row), side-by-side blocks (UHSB), and repeated
    (Date, Crop, V1, V2, V3, Avg) blocks sharing the site columns of the first block (UASD)."""
    hdr_rows = [i for i, r in enumerate(rows)
                if any(re.fullmatch(rf"{val_prefix}\s*1", _s(c).lower()) for c in r)]
    recs = []
    for hi, h in enumerate(hdr_rows):
        header = rows[h]
        nxt = hdr_rows[hi + 1] if hi + 1 < len(hdr_rows) else len(rows)
        # a 'Date: 27.1.2024' style row directly above the header (UASB LAI)
        above = rows[h - 1] if h > 0 else []
        blocks = _build_blocks(header, above, val_prefix)
        # a header row can be mis-aligned with the rows below it (UASD: the 'Artal' section header lost two
        # cells). Score this header and the previous one against the first data row; keep the better fit.
        first_data = next((rows[i] for i in range(h + 1, nxt) if not all(c is None or _s(c) == "" for c in rows[i])), None)
        if hi > 0 and first_data is not None:
            prev_blocks = _build_blocks(rows[hdr_rows[hi - 1]], rows[hdr_rows[hi - 1] - 1] if hdr_rows[hi - 1] > 0 else [], val_prefix)
            if _header_fit(prev_blocks, first_data) > _header_fit(blocks, first_data):
                blocks = prev_blocks; header_note = f"header row {h+1} mis-aligned; used header row {hdr_rows[hi-1]+1}"
            else:
                header_note = ""
        else:
            header_note = ""
        # data rows
        carry = [{} for _ in blocks]   # per-block forward-fill of date / site fields
        for i in range(h + 1, nxt):
            r = rows[i]
            if all(c is None or _s(c) == "" for c in r):
                continue
            for b, cols in enumerate(blocks):
                def g(name):
                    j = cols.get(name)
                    return r[j] if (j is not None and j < len(r)) else None
                vals = [to_float(g("v1")), to_float(g("v2")), to_float(g("v3"))]
                avg_cell = g("avg") if "avg" in cols else None
                avg = to_float(avg_cell)
                remark = _s(g("remark")) if "remark" in cols else ""
                if "remark" not in cols and isinstance(g("v1"), str) and not re.search(r"\d", _s(g("v1"))):
                    remark = _s(g("v1"))          # e.g. 'Crop harvested' written into LAI1
                if vals == [1.0, 2.0, 3.0] and np.isnan(avg):
                    continue        # replicate-number sub-header row (1 | 2 | 3), not data
                if all(np.isnan(x) for x in vals) and np.isnan(avg) and not remark:
                    # still allow carrying site info forward (UHSB writes site once per date block)
                    if _s(g("date")):
                        d, fl = parse_date_any(g("date"))
                        if pd.notna(d):
                            carry[b]["date"], carry[b]["date_flag"] = d, fl
                    for n in ("sws", "mws", "bm", "lat", "lon", "survey", "soil", "district"):
                        if _s(g(n)):
                            carry[b][n] = g(n)
                    continue
                # date: cell -> forward-filled cell -> block date
                dcell = g("date")
                if _s(dcell):
                    d, fl = parse_date_any(dcell)
                    if pd.notna(d):
                        carry[b]["date"], carry[b]["date_flag"] = d, fl
                    else:
                        d, fl = pd.NaT, "unparsed"
                d = carry[b].get("date", pd.NaT); fl = carry[b].get("date_flag", "unparsed")
                if pd.isna(d) and pd.notna(cols["_blk_date"]):
                    d, fl = cols["_blk_date"], "block_header_date"
                # site fields with forward fill (UHSB, UASB write them once per group)
                site = {}
                for n in ("sws", "mws", "bm", "lat", "lon", "survey", "soil", "district", "crop", "area", "texture", "bench"):
                    v = g(n)
                    if _s(v):
                        site[n] = v
                        if n != "crop":
                            carry[b][n] = v
                    else:
                        site[n] = carry[b].get(n) if n != "crop" else None
                lat = parse_coord(site.get("lat"), "lat"); lon = parse_coord(site.get("lon"), "lon")
                crop_src = ""
                if not _s(site.get("crop")):
                    if remark and not harmonize_crop(remark).startswith("other:") and harmonize_crop(remark) != "unknown":
                        site["crop"] = remark; crop_src = "remark_column"
                    elif b > 0 and cols["_inherits"] and blocks[0].get("crop") is not None and blocks[0]["crop"] < len(r) and _s(r[blocks[0]["crop"]]):
                        site["crop"] = r[blocks[0]["crop"]]; crop_src = "first_block_of_row"
                nrep = int(sum(~np.isnan(x) for x in vals))
                mean3 = float(np.nanmean(vals)) if nrep else np.nan
                if np.isnan(avg) and nrep:
                    avg = mean3
                recs.append({
                    "institution": inst, "source_sheet": sheet, "source_row": i + 1, "block": b,
                    "sws_name": clean_name(site.get("sws")), "mws_name": clean_name(site.get("mws")),
                    "district": clean_name(site.get("district")),
                    "bm_site_no": _s(site.get("bm")), "survey_no": _s(site.get("survey")),
                    "soil_phase": _s(site.get("soil")), "latitude": lat, "longitude": lon,
                    "date": d, "date_flag": fl,
                    "crop_raw": _s(site.get("crop")), "crop": harmonize_crop(site.get("crop")),
                    f"{var}1": vals[0], f"{var}2": vals[1], f"{var}3": vals[2],
                    f"{var}_mean": avg, "n_replicates": nrep,
                    "reported_avg_minus_mean3": (avg - mean3) if (nrep and not np.isnan(avg)) else np.nan,
                    "remark": remark, "crop_source": crop_src,
                    "crop_height_cm": to_float(g("crop_ht")) if "crop_ht" in cols else np.nan,
                    "days_after_sowing": to_float(g("das")) if "das" in cols else np.nan,
                    "site_cols_inherited": cols["_inherits"], "header_note": header_note,
                })
    return pd.DataFrame(recs)

# ------------------------------------------------------------------ UASR special layouts
def _parse_uasr_ssm(rows, inst, sheet):
    """UASR SSM: blocks headed 'DATE dd-mm-yyyy' (or a 'Date | <dt> | <dt>' row), a header row with
    'soil moisture' spanning 3 sub-columns (1,2,3) and 'soil temperature' spanning 3; rows give
    Soil Phase, MWS name, survey no (with (A)/(B) replicate plots). No coordinates in this sheet."""
    recs = []
    cur_dates = []; cur_sws = ""; hdr = None
    for i, r in enumerate(rows):
        txt = " ".join(_s(c) for c in r if _s(c))
        m = re.search(r"date\s*[:\-]?\s*(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})", txt, re.I)
        if m and not re.search(r"soil moisture", txt, re.I):
            d, _ = parse_date_any(m.group(1)); cur_dates = [d]; continue
        if re.fullmatch(r"date", _s(r[1]).lower() if len(r) > 1 else ""):
            cur_dates = [parse_date_any(c)[0] for c in r[2:] if c is not None and pd.notna(parse_date_any(c)[0])]
            continue
        if re.search(r"(control|subwatershed|sub-watershed)", txt, re.I) and not re.search(r"sl\.?\s*no", txt, re.I) and len(txt) < 90:
            if re.search(r"itgi", txt, re.I): cur_sws = "ITGI (Control Sub-watershed)"
            elif re.search(r"jantapur", txt, re.I): cur_sws = "Jantapur"
            elif re.search(r"huns", txt, re.I): cur_sws = "Hunsehadagli"
            else: cur_sws = txt
            continue
        # ITGI control block: 'Sl.no | Survey.no | Soil moisture | Soil tempture', one replicate per row
        if len(r) > 4 and re.search(r"^survey", _s(r[2]).lower()) and re.search(r"soil\s*moist", _s(r[3]).lower()):
            hdr = {"itgi": True, "survey": 2, "sm": 3, "st": 4}; continue
        if hdr is not None and hdr.get("itgi"):
            v = to_float(r[3]) if len(r) > 3 else np.nan
            if np.isnan(v):
                if _s(r[1]) == "" and _s(r[3]) == "": pass
                continue
            survey = _s(r[2]) if len(r) > 2 and _s(r[2]) else (recs[-1]["survey_no"] if recs else "")
            new_site = bool(_s(r[2]))
            if not new_site and recs and recs[-1]["n_replicates"] < 3 and recs[-1]["survey_no"] == survey and recs[-1]["remark"] == "itgi_row_replicates":
                k = recs[-1]["n_replicates"]; recs[-1][f"ssm{k+1}"] = v; recs[-1]["n_replicates"] = k + 1
                recs[-1]["ssm_mean"] = float(np.nanmean([recs[-1]["ssm1"], recs[-1]["ssm2"], recs[-1]["ssm3"]]))
                continue
            d = cur_dates[0] if cur_dates else pd.NaT
            recs.append({"institution": inst, "source_sheet": sheet, "source_row": i + 1, "block": 0,
                         "sws_name": cur_sws, "mws_name": "", "district": "", "bm_site_no": "", "survey_no": survey,
                         "soil_phase": "", "latitude": np.nan, "longitude": np.nan, "date": d,
                         "date_flag": "" if pd.notna(d) else "unparsed", "crop_raw": "", "crop": "unknown",
                         "ssm1": v, "ssm2": np.nan, "ssm3": np.nan, "ssm_mean": v, "n_replicates": 1,
                         "reported_avg_minus_mean3": np.nan, "remark": "itgi_row_replicates",
                         "soil_temp_mean_c": to_float(r[4]) if len(r) > 4 else np.nan,
                         "crop_height_cm": np.nan, "days_after_sowing": np.nan, "site_cols_inherited": False})
            continue
        low = [_s(c).lower() for c in r]
        if any(re.search(r"soil\s*moist", c) for c in low) and any(re.search(r"sl\.?\s*no", c) for c in low) and not (hdr and hdr.get("itgi") and re.search(r"^survey", _s(r[2]).lower())):
            hdr = {}
            for j, c in enumerate(low):
                if re.search(r"soil\s*phase", c): hdr["soil"] = j
                elif re.search(r"mws", c): hdr["mws"] = j
                elif re.search(r"survey|sy\s*no", c): hdr["survey"] = j
                elif re.search(r"soil\s*moist", c): hdr["sm"] = j
                elif re.search(r"temp", c): hdr["st"] = j
            continue
        if hdr is None or "sm" not in hdr:
            continue
        # data row: needs at least one numeric moisture value
        sm = [to_float(r[hdr["sm"] + k]) if hdr["sm"] + k < len(r) else np.nan for k in range(3)]
        st = [to_float(r[hdr["st"] + k]) if "st" in hdr and hdr["st"] + k < len(r) else np.nan for k in range(3)]
        if all(np.isnan(x) for x in sm):
            # ITGI control layout: 'Sl.no | Survey.no | Soil moisture | Soil temp' one replicate per row
            continue
        survey = _s(r[hdr["survey"]]) if "survey" in hdr and hdr["survey"] < len(r) else ""
        mws = _s(r[hdr["mws"]]) if "mws" in hdr and hdr["mws"] < len(r) else ""
        soil = _s(r[hdr["soil"]]) if "soil" in hdr and hdr["soil"] < len(r) else ""
        if not mws and recs:
            mws = recs[-1]["mws_name"]; soil = soil or recs[-1]["soil_phase"]
        if not survey and recs:
            survey = recs[-1]["survey_no"]
        n = int(sum(~np.isnan(x) for x in sm))
        # a 'Date | d1 | d2' header means the 3 moisture sub-columns are NOT replicates of one date; keep as reps but flag
        d = cur_dates[0] if cur_dates else pd.NaT
        recs.append({"institution": inst, "source_sheet": sheet, "source_row": i + 1, "block": 0,
                     "sws_name": cur_sws, "mws_name": mws, "district": "", "bm_site_no": "", "survey_no": survey,
                     "soil_phase": soil, "latitude": np.nan, "longitude": np.nan, "date": d,
                     "date_flag": "" if pd.notna(d) else "unparsed",
                     "crop_raw": "", "crop": "unknown", "ssm1": sm[0], "ssm2": sm[1], "ssm3": sm[2],
                     "ssm_mean": float(np.nanmean(sm)) if n else np.nan, "n_replicates": n,
                     "reported_avg_minus_mean3": np.nan, "remark": "multi_date_header" if len(cur_dates) > 1 else "",
                     "soil_temp_mean_c": float(np.nanmean(st)) if any(~np.isnan(x) for x in st) else np.nan,
                     "crop_height_cm": np.nan, "days_after_sowing": np.nan, "site_cols_inherited": False})
    return pd.DataFrame(recs)

def _parse_uasr_lai(rows, inst, sheet):
    """UASR LAI: raw AccuPAR ceptometer log. Keep only 'SUM' records that carry an LAI value and an
    annotation code (e.g. HUSWS71RGB = HU sub-watershed, survey no 71, RG redgram, B best plot).
    Coordinates in the log are garbled ('17?') -> NaN. Legend decoded from the sheet's own notes."""
    hdr = None; recs = []; last_ann = ""; legend_crop = {"RG": "redgram", "RS": "rose", "GV": "guava", "MG": "marigold",
                                          "PY": "papaya", "C": "cotton", "T": "tomato", "S": "sugarcane"}
    for i, r in enumerate(rows):
        low = [_s(c).lower() for c in r]
        if "record type" in low:
            hdr = {n: low.index(n) for n in ("record type", "date and time", "annotation", "leaf area index [lai]")}
            continue
        if hdr is None or len(r) <= hdr["leaf area index [lai]"]:
            continue
        if _s(r[hdr["record type"]]).upper() != "SUM":
            continue
        lai = to_float(r[hdr["leaf area index [lai]"]])
        if _s(r[hdr["annotation"]]):
            last_ann = _s(r[hdr["annotation"]])
        ann = last_ann
        if np.isnan(lai) or lai <= 0:
            continue
        d, fl = parse_date_any(r[hdr["date and time"]])
        m = re.match(r"^([A-Z]{2})SWS(\d+)([A-Z]{1,2})([BML])$", ann)
        survey = m.group(2) if m else ""
        crop = legend_crop.get(m.group(3), m.group(3).lower()) if m else ""
        plot_q = m.group(4) if m else ""
        recs.append({"institution": inst, "source_sheet": sheet, "source_row": i + 1, "block": 0, "_ann": ann,
                     "sws_name": "Hunsehadagli" if (m and m.group(1) == "HU") else (m.group(1) if m else ""),
                     "mws_name": "", "district": "", "bm_site_no": "", "survey_no": survey, "soil_phase": "",
                     "latitude": np.nan, "longitude": np.nan, "date": d, "date_flag": fl,
                     "crop_raw": crop, "crop": harmonize_crop(crop), "lai1": lai, "lai2": np.nan, "lai3": np.nan,
                     "lai_mean": lai, "n_replicates": 1, "reported_avg_minus_mean3": np.nan,
                     "remark": f"ceptometer annotation={ann}; plot_quality={plot_q}", "crop_height_cm": np.nan,
                     "days_after_sowing": np.nan, "site_cols_inherited": False})
    df = pd.DataFrame(recs)
    if not len(df):
        return df
    # several SUM records per plot per day are repeat readings of the same canopy -> ONE observation
    # per (annotation, date): lai1..3 = first three readings, lai_mean = mean of all, n_replicates = count
    out = []
    for (ann, d), g in df.groupby(["_ann", "date"], dropna=False, sort=False):
        r = g.iloc[0].to_dict(); vals = g["lai1"].tolist()
        r["lai1"], r["lai2"], r["lai3"] = (vals + [np.nan, np.nan, np.nan])[:3]
        r["lai_mean"] = float(np.mean(vals)); r["n_replicates"] = len(vals)
        r["remark"] = r["remark"] + f"; {len(vals)} ceptometer SUM records averaged"
        out.append(r)
    return pd.DataFrame(out).drop(columns="_ann")

# ============================================================== public SSM / LAI
# workbook save dates (from the archive listing) -- a reading cannot post-date its file
MIN_DATE = "2023-03-01"     # benchmark monitoring began in April 2023 (earliest dated record in any workbook)
FILE_MAX_DATE = {"UAHS": "2024-06-20", "UASB": "2024-06-24", "UASD": "2024-06-26", "UASR": "2023-12-27",
                 "UHSB": "2024-05-10", "IISc": "2023-09-13"}

def parse_ssm(path, inst):
    rows = read_rows(path, "SSM")
    if inst == "UASR":
        df = _parse_uasr_ssm(rows, inst, "SSM")
    else:
        df = _parse_replicate_sheet(rows, inst, "SSM", "ssm", "ssm")
    if len(df):
        df["_row"] = df["source_row"]
        df = resolve_ddmm_by_sequence(df, ["institution", "block", "bm_site_no", "sws_name", "mws_name", "survey_no"],
                                      max_date=pd.Timestamp(FILE_MAX_DATE.get(inst, "2026-09-13")), min_date=pd.Timestamp(MIN_DATE))
        df = df.drop(columns="_row")
    return df

def parse_lai(path, inst):
    rows = read_rows(path, "LAI")
    if inst == "UASR":
        return _parse_uasr_lai(rows, inst, "LAI")
    df = _parse_replicate_sheet(rows, inst, "LAI", "lai", "lai")
    if len(df):
        df["_row"] = df["source_row"] * 1000 + df["block"]
        df = resolve_ddmm_by_sequence(df, ["institution", "bm_site_no", "sws_name", "mws_name", "survey_no"],
                                      max_date=pd.Timestamp(FILE_MAX_DATE.get(inst, "2026-09-13")), min_date=pd.Timestamp(MIN_DATE))
        df = df.drop(columns="_row")
    return df

# ============================================================== Manual groundwater
def parse_gw(path, inst):
    rows = read_rows(path, "Manual GW")
    if inst == "UASR":
        df = _parse_gw_long(rows, inst)
        if len(df):
            df["_row"] = df["source_row"]
            df = resolve_ddmm_by_sequence(df, ["sws_name", "village", "mws_name", "survey_no", "borewell_no"],
                                          max_date=pd.Timestamp(FILE_MAX_DATE["UASR"]), min_date=pd.Timestamp("2023-03-01"))
            df = df.drop(columns="_row")
        return df
    return _parse_gw_wide(rows, inst)

def _parse_gw_wide(rows, inst):
    """UAHS / UASB / UASD / UHSB: one row per borewell, monthly readings in date-headed columns.
    Header found by 'Borewell number'. Month-name headers without a year (UHSB 'July'..'December')
    are assigned to the year of the nearest dated header to their left, or 2023 if none."""
    hdr_rows = [i for i, r in enumerate(rows) if any(re.search(r"borewell\s*n", _s(c).lower()) for c in r)]
    recs = []
    for hi, h in enumerate(hdr_rows):
        header = rows[h]
        nxt = hdr_rows[hi + 1] if hi + 1 < len(hdr_rows) else len(rows)
        low = [_s(c).lower() for c in header]
        cols = {}
        for j, c in enumerate(low):
            if re.search(r"^sws", c): cols.setdefault("sws", j)
            elif re.search(r"^mws", c): cols.setdefault("mws", j)
            elif re.search(r"^bm\s*site", c): cols.setdefault("bm", j)
            elif re.search(r"borewell\s*n", c): cols.setdefault("bw", j)
            elif re.search(r"^lat", c): cols.setdefault("lat", j)
            elif re.search(r"^lon", c): cols.setdefault("lon", j)
            elif re.search(r"^district", c): cols.setdefault("district", j)
            elif re.search(r"ground\s*level", c): cols.setdefault("gl", j)
            elif re.search(r"well[_ ]?depth", c): cols.setdefault("wd", j); cols["wd_unit"] = "ft" if "ft" in c else ("m" if "(m)" in c else "")
            elif re.search(r"geomorph", c): cols.setdefault("geo", j)
            elif re.search(r"soil\s*desc", c): cols.setdefault("soil", j)
            elif re.search(r"user", c): cols.setdefault("user", j)
            elif re.search(r"^survey", c): cols.setdefault("survey", j)
            elif re.search(r"irrigation", c): cols.setdefault("irr", j)
        # date columns: anything to the right of the last attribute column that parses as a date/month
        last_attr = max(v for k, v in cols.items() if k != "wd_unit")
        date_cols = []; last_year = None
        for j in range(last_attr + 1, len(header)):
            c = header[j]
            if c is None or re.search(r"remark", _s(c).lower()):
                continue
            d, fl = parse_date_any(c, default_year=last_year or 2023)
            if pd.notna(d):
                if fl == "month_only" and last_year and d.month < 6 and last_year == 2023:
                    d = pd.Timestamp(year=2024, month=d.month, day=1)
                last_year = d.year
                remark_col = j + 1 if (j + 1 < len(header) and re.search(r"remark|crop", _s(header[j + 1]).lower())) else None
                date_cols.append((j, d, fl, remark_col))
        # header dates form a chronological sequence: resolve swaps / year typos jointly
        if date_cols:
            hd = pd.DataFrame({"date": [d for _, d, _, _ in date_cols],
                               "date_flag": ["" if (fl == "month_only" or d.day == 1) else fl for _, d, fl, _ in date_cols],
                               "_row": range(len(date_cols)), "g": 0})
            hd = resolve_ddmm_by_sequence(hd, ["g"], max_date=pd.Timestamp(FILE_MAX_DATE.get(inst, "2026-09-13")),
                                          min_date=pd.Timestamp("2023-03-01")).sort_values("_row")
            date_cols = [(j, d2, (f2 if f2 else ("month_marker" if fl == "month_only" or d2.day == 1 else "")), rc)
                         for (j, _, fl, rc), d2, f2 in zip(date_cols, hd["date"], hd["date_flag"])]
        carry = {}
        for i in range(h + 1, nxt):
            r = rows[i]
            if all(c is None or _s(c) == "" for c in r):
                continue
            def g(n):
                j = cols.get(n); return r[j] if (j is not None and j < len(r)) else None
            for n in ("sws", "mws", "district"):
                if _s(g(n)): carry[n] = g(n)
            sws = clean_name(g("sws") or carry.get("sws")); mws = clean_name(g("mws") or carry.get("mws"))
            lat = parse_coord(g("lat"), "lat"); lon = parse_coord(g("lon"), "lon")
            if np.isnan(lat) and np.isnan(lon) and not _s(g("bw")):
                continue     # section label row (e.g. 'Control sub-watershed')
            base = {"institution": inst, "source_sheet": "Manual GW", "source_row": i + 1,
                    "sws_name": sws, "mws_name": mws, "district": clean_name(g("district") or carry.get("district")),
                    "bm_site_no": _s(g("bm")), "borewell_no": _s(g("bw")), "latitude": lat, "longitude": lon,
                    "ground_level_m": to_float(g("gl")), "well_depth": to_float(g("wd")), "well_depth_unit": cols.get("wd_unit", ""),
                    "geomorphology": _s(g("geo")), "soil_phase": _s(g("soil")), "survey_no": _s(g("survey")),
                    "irrigation_method": _s(g("irr"))}
            for j, d, fl, rc in date_cols:
                v = r[j] if j < len(r) else None
                val = to_float(v); flag = text_flag(v)
                if np.isnan(val) and not flag:
                    continue
                if isinstance(v, str) and ("+" in v or "above" in v.lower()):
                    flag = "censored_deeper_than:" + v.strip()
                if not np.isnan(val) and val < 0:
                    flag = "negative_depth"
                if not np.isnan(val) and val > 150:
                    flag = "implausible_depth_gt_150m"
                recs.append({**base, "date": d, "date_flag": fl, "gw_depth_m": val, "value_flag": flag,
                             "crop_remark": _s(r[rc]) if rc is not None and rc < len(r) else ""})
    return pd.DataFrame(recs)

def _parse_gw_long(rows, inst):
    """UASR: monthly blocks, each titled '<SWS> GWD for the month ...' followed by a header row.
    Three header variants seen: 'Sl no|Date|Time|Village name|MWS Name|Survey no.|Lat|Long|GW Depth,m|...',
    'Well_no|Village_name|MWS_Name|Survey no.|Date|Time|Lat|Long|GW_Depth, m|...', and
    'SI No|DATE|FORMER NAME OR VILLAGE NAME|SY NO|BOREWELL DEPTH|TYPE OF WELL|LATITUDE|LONGITUDE|YEAR OF
    INSTALLATION|WATER DEPTH METER|PURPOSE'. Columns are mapped by name; the SWS comes from the block title."""
    recs = []; cols = None; sws = ""
    for i, r in enumerate(rows):
        first = " ".join(_s(c) for c in r[:4] if _s(c))
        m = re.search(r"^([A-Za-z]+)\s*_?\s*(?:SWS)?\s*_?\s*GWD", first, re.I)
        if m:
            name = m.group(1)
            sws = {"hunsehadagli": "Hunsehadagli", "murlapur": "Koppal (4D4A2)", "jantapur": "Jantapur",
                   "halligera": "Halligera"}.get(name.lower(), name)
            cols = None
            continue
        low = [_s(c).lower() for c in r]
        if any(re.search(r"(gw[_ ]?depth|water\s*depth)", c) for c in low):
            cols = {}
            for j, c in enumerate(low):
                if re.search(r"^(sl|si|well)", c) and "type" not in c: cols.setdefault("bw", j)
                elif re.search(r"^date", c): cols.setdefault("date", j)
                elif re.search(r"village|former", c): cols.setdefault("village", j)
                elif re.search(r"mws", c): cols.setdefault("mws", j)
                elif re.search(r"survey|^sy\s*no", c): cols.setdefault("survey", j)
                elif re.search(r"^lat", c): cols.setdefault("lat", j)
                elif re.search(r"^lon", c): cols.setdefault("lon", j)
                elif re.search(r"(gw[_ ]?depth|water\s*depth)", c): cols.setdefault("gw", j)
                elif re.search(r"borewell\s*depth", c): cols.setdefault("wd", j)
                elif re.search(r"type\s*of\s*well", c): cols.setdefault("welltype", j)
                elif re.search(r"purpose", c): cols.setdefault("purpose", j)
            continue
        if cols is None or "gw" not in cols:
            continue
        def g(n):
            j = cols.get(n); return r[j] if (j is not None and j < len(r)) else None
        d, fl = parse_date_any(g("date"))
        raw = g("gw")
        val = to_float(raw) if not isinstance(raw, (dt.datetime, dt.date)) else np.nan
        flag = text_flag(raw)
        if isinstance(raw, (dt.datetime, dt.date)):
            flag = "date_in_value_cell"
        if pd.isna(d) and np.isnan(val):
            continue
        if not np.isnan(val) and val > 150:
            flag = "implausible_depth_gt_150m"
        mws = clean_name(g("mws")); village = clean_name(g("village"))
        wd = to_float(g("wd")); wd_unit = "ft" if (isinstance(g("wd"), str) and "feet" in g("wd").lower()) else ("" if np.isnan(wd) else "as_written")
        recs.append({"institution": inst, "source_sheet": "Manual GW", "source_row": i + 1,
                     "sws_name": sws, "mws_name": mws, "district": "", "bm_site_no": "", "borewell_no": _s(g("bw")),
                     "latitude": parse_coord(g("lat"), "lat"), "longitude": parse_coord(g("lon"), "lon"),
                     "ground_level_m": np.nan, "well_depth": wd, "well_depth_unit": wd_unit,
                     "geomorphology": "", "soil_phase": "", "survey_no": _s(g("survey")),
                     "irrigation_method": "", "date": d, "date_flag": fl, "gw_depth_m": val, "value_flag": flag,
                     "crop_remark": _s(g("purpose")), "village": village, "well_type": _s(g("welltype"))})
    return pd.DataFrame(recs)
