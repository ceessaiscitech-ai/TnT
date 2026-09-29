"""
ground_utils.py -- shared helpers for REWARD ground-data harmonisation
======================================================================
Used by ground_parsers.py (benchmark hydrology), field_survey.py and mis_koppal.py.
Nothing here invents data: every function either reads a cell, converts a unit,
or flags what it could not parse.
"""
import re, math, datetime as dt
import numpy as np
import pandas as pd

# ----------------------------------------------------------------- pixel id
# EXACT copy of _prep_common.assign_pixel_ids (v14+): pixel_id is a pure function of
# the rounded coordinate at 5 decimals -> 18-digit zero-padded string.
UID_PRECISION_DEC = 5
def pixel_id_from_latlon(lat, lon, precision=UID_PRECISION_DEC):
    lat = np.asarray(lat, dtype=float); lon = np.asarray(lon, dtype=float)
    f = 10 ** precision
    ls = np.rint((lat + 90.0) * f).astype(np.int64)
    lo = np.rint((lon + 180.0) * f).astype(np.int64)
    out = np.char.add(np.char.zfill(ls.astype(str), 9), np.char.zfill(lo.astype(str), 9))
    out = np.where(np.isnan(lat) | np.isnan(lon), "", out)
    return out

# ---------------------------------------------------------------- season keys
# TWO season definitions exist in the project and they DISAGREE:
#   EXPORT (artal_exporter v109/v110, SEASONS): Kharif Jun-Sep, Rabi Oct-Feb, Zaid Mar-May;
#          Year = calendar year of the season start (a Rabi Jan/Feb month belongs to the previous Year).
#          Core (priority) months: Kharif Jul-Aug, Rabi Nov-Jan, Zaid Apr.
#   PREP   (_prep_common.SEASON_MONTHS, used only for fund-release dose timing): Kharif Jun-Oct,
#          Rabi Nov-Mar, Zaid Apr-May; agri-year = Jan-May belong to the previous year.
# The panel's Season/Year columns come from the EXPORT, so ground observations are keyed with the
# EXPORT definition. The prep definition is kept for reference (panel_year_season_prep).
SEASON_MONTHS = {1: [6, 7, 8, 9], 2: [10, 11, 12, 1, 2], 3: [3, 4, 5]}          # export definition
CORE_MONTHS = {1: [7, 8], 2: [11, 12, 1], 3: [4]}                                  # export SEASON_CORE_MONTHS
SEASON_MONTHS_PREP = {1: [6, 7, 8, 9, 10], 2: [11, 12, 1, 2, 3], 3: [4, 5]}
SEASON_LABEL = {0: "Yearly", 1: "Kharif", 2: "Rabi", 3: "Zaid"}
def season_code(date, months=None):
    months = months or SEASON_MONTHS
    m = date.month
    for s, ms in months.items():
        if m in ms:
            return s
    raise ValueError(date)
def panel_year_season(date):
    """(Year, Season) exactly as the GEE export keys them: season code from SEASON_MONTHS, Year = calendar
    year of the season start (Jan/Feb -> Rabi of the previous Year; Mar-May Zaid of the same year)."""
    s = season_code(date)
    year = date.year - 1 if (s == 2 and date.month <= 2) else date.year
    return year, s
def agri_year(date):
    """Prep-engine rule (_prep_common.assign_agri_year): Jan-May belong to the previous year."""
    return date.year if date.month >= 6 else date.year - 1
def panel_year_season_prep(date):
    return agri_year(date), season_code(date, SEASON_MONTHS_PREP)

# ----------------------------------------------------------------- numbers
_NUM_RE = re.compile(r"[-+]?\d*\.?\d+")
def to_float(v):
    """Numeric value or NaN. Accepts '11.30 m', '40+', '5.90 m'. Text like 'No borewell',
    'Dry', 'No water', 'Stollen', '-', 'Nil' -> NaN (the text is kept separately by callers)."""
    if v is None:
        return np.nan
    if isinstance(v, bool):
        return np.nan
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return np.nan
    s = str(v).strip()
    if s == "" or s.lower() in {"-", "nil", "na", "n/a", "no crop", "nocrop", "."}:
        return np.nan
    m = _NUM_RE.search(s)
    if not m:
        return np.nan
    # reject things like '112(A)' survey numbers being read as values: caller decides
    try:
        return float(m.group(0))
    except ValueError:
        return np.nan

def text_flag(v):
    """Return the non-numeric text of a cell (e.g. 'No water', 'Dry', 'No borewell'), else ''."""
    if v is None or isinstance(v, (int, float, dt.datetime, dt.date)):
        return ""
    s = str(v).strip()
    if s == "" or _NUM_RE.fullmatch(s.replace("m", "").strip()):
        return ""
    return s if not _NUM_RE.search(s) else s

# ----------------------------------------------------------------- coordinates
_DMS_RE = re.compile(r"(\d{1,3})\s*[°º'′ ]\s*(\d{1,2})\s*['′’]\s*(\d{1,2}(?:\.\d+)?)\s*(?:\"|″|'')?")
def parse_coord(v, kind):
    """kind='lat' or 'lon'. Accepts decimal degrees, or DMS like 16 07' 14\" or N-15'25951."""
    if v is None:
        return np.nan
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        s = str(v).strip()
        m = _DMS_RE.search(s)
        if m:
            d, mi, se = float(m.group(1)), float(m.group(2)), float(m.group(3))
            x = d + mi / 60 + se / 3600
        else:
            x = to_float(s)
    if np.isnan(x):
        return np.nan
    lo, hi = (11.0, 19.0) if kind == "lat" else (73.5, 78.7)   # Karnataka bounds
    return x if lo <= x <= hi else np.nan

# ----------------------------------------------------------------- dates
_MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
_MONTHS.update({"sept": 9, "january": 1, "february": 2, "march": 3, "april": 4, "june": 6, "july": 7,
                "august": 8, "september": 9, "october": 10, "november": 11, "december": 12})

def parse_date_any(v, default_year=None, dayfirst=True):
    """Parse the many date spellings in these workbooks. Returns (Timestamp|NaT, flag).
    flag: '' clean | 'ddmm_ambiguous' when a real datetime cell has day<=12 and month<=12
    (Excel may have swapped them) | 'month_only' | 'unparsed'.
    Strings are ALWAYS read day-first (dd-mm-yyyy, dd.mm.yyyy, dd/mm/yy) -- that is how every
    string date in these files is written."""
    if v is None:
        return pd.NaT, "unparsed"
    if isinstance(v, (dt.datetime, dt.date)):
        ts = pd.Timestamp(v)
        flag = "ddmm_ambiguous" if (ts.day <= 12 and ts.month <= 12 and ts.day != ts.month) else ""
        return ts.normalize(), flag
    s = str(v).strip()
    if s in {"", "-", "nil"}:
        return pd.NaT, "unparsed"
    s2 = re.sub(r"^(date|dated)\s*[:\-]?\s*", "", s, flags=re.I).strip()
    # 'Sept-2023', 'July', 'August 2023'
    m = re.match(r"^([A-Za-z]{3,9})[\s\-/]*(\d{2,4})?$", s2)
    if m and m.group(1).lower() in _MONTHS:
        mon = _MONTHS[m.group(1).lower()]
        yr = m.group(2)
        if yr is None:
            if default_year is None:
                return pd.NaT, "unparsed"
            yr = default_year
        yr = int(yr); yr = yr + 2000 if yr < 100 else yr
        return pd.Timestamp(year=yr, month=mon, day=1), "month_only"
    # dd-mm-yyyy / dd.mm.yyyy / dd/mm/yy with optional time
    m = re.match(r"^(\d{1,2})[\-./](\d{1,2})[\-./](\d{2,5})(?:\s+.*)?$", s2)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        y = int(y[:4]) if len(y) > 4 else int(y)          # '20243' typo -> 2024
        y = y + 2000 if y < 100 else y
        if mo > 12 and d <= 12:
            d, mo = mo, d
        try:
            return pd.Timestamp(year=y, month=mo, day=d), ""
        except ValueError:
            return pd.NaT, "unparsed"
    # yyyy-mm-dd
    m = re.match(r"^(\d{4})[\-./](\d{1,2})[\-./](\d{1,2})", s2)
    if m:
        try:
            return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=int(m.group(3))), ""
        except ValueError:
            return pd.NaT, "unparsed"
    try:
        ts = pd.to_datetime(s2, dayfirst=dayfirst, errors="coerce")
        if pd.isna(ts):
            return pd.NaT, "unparsed"
        return pd.Timestamp(ts).normalize(), ""
    except Exception:
        return pd.NaT, "unparsed"

def resolve_ddmm_by_sequence(df, group_cols, date_col="date", flag_col="date_flag", order_col="_row", max_date=None, min_date=None):
    """Monitoring visits are entered in chronological order within a site. A real Excel
    datetime whose day and month are both <=12 may have been swapped on import
    (dd/mm read as mm/dd). For each site, every such row has two candidate dates
    (as-read, swapped); this chooses ONE candidate per row jointly, by dynamic programming,
    minimising the number of backward steps in the sequence, with two hard facts added:
    a reading cannot post-date the workbook's own save date (max_date), and when both
    readings are consistent the as-read value is kept. Unambiguous rows are fixed anchors.
    Every change is recorded in flag_col:
        'ddmm_swapped_by_sequence' | 'ddmm_kept_by_sequence' | 'ddmm_ambiguous' (isolated row)."""
    df = df.sort_values(group_cols + [order_col]).copy()
    for _, idx in df.groupby(group_cols, sort=False).groups.items():
        idx = list(idx)
        needs = any(df.at[i, flag_col] == "ddmm_ambiguous" for i in idx)
        if max_date is not None:
            needs |= any(pd.notna(df.at[i, date_col]) and df.at[i, date_col] > max_date for i in idx)
        if min_date is not None:
            needs |= any(pd.notna(df.at[i, date_col]) and df.at[i, date_col] < min_date for i in idx)
        if not needs:
            continue
        cands = []
        for i in idx:
            d = df.at[i, date_col]
            if pd.isna(d):
                cands.append([(pd.NaT, "na")]); continue
            cl = [(d, "orig")]
            if df.at[i, flag_col] == "ddmm_ambiguous":
                try:
                    cl.append((pd.Timestamp(year=d.year, month=d.day, day=d.month), "swap"))
                except ValueError:
                    pass
            # year typos: offer year-1 / year+1 (and year-2 .. for far-out values) as last-resort candidates
            for dd, kind in list(cl):
                for k_ in (-1, 1, -2, -3):
                    try:
                        cand = pd.Timestamp(year=dd.year + k_, month=dd.month, day=dd.day)
                    except ValueError:
                        continue
                    if (max_date is None or cand <= max_date) and (min_date is None or cand >= min_date):
                        cl.append((cand, kind + f"_year{k_:+d}"))
            cands.append(cl)
        n = len(idx)
        INF = 1e18
        cost = [[INF] * len(c) for c in cands]; back = [[-1] * len(c) for c in cands]
        for a in range(len(cands[0])):
            d0 = cands[0][a][0]
            cost[0][a] = (1000.0 if (max_date is not None and pd.notna(d0) and d0 > max_date) else 0.0) \
                       + (1000.0 if (min_date is not None and pd.notna(d0) and d0 < min_date) else 0.0) \
                       + (1e-3 if cands[0][a][1] != "orig" else 0.0)
        last_real = None
        for k in range(1, n):
            for a, (da, _) in enumerate(cands[k]):
                for b, (db, _) in enumerate(cands[k - 1]):
                    if cost[k - 1][b] >= INF:
                        continue
                    step = 0.0
                    if pd.notna(da) and pd.notna(db):
                        gap = (da - db).days
                        step = 1000.0 if gap < -1 else 0.0
                    if max_date is not None and pd.notna(da) and da > max_date:
                        step += 1000.0
                    if min_date is not None and pd.notna(da) and da < min_date:
                        step += 1000.0
                    if cands[k][a][1] != "orig":
                        step += 1e-3 if "year" not in cands[k][a][1] else 5.0
                    c = cost[k - 1][b] + step
                    if c < cost[k][a]:
                        cost[k][a] = c; back[k][a] = b
        a = int(np.argmin(cost[-1]))
        choice = [0] * n
        for k in range(n - 1, -1, -1):
            choice[k] = a
            a = back[k][a] if k > 0 else a
        for k, i in enumerate(idx):
            d, kind = cands[k][choice[k]]
            if len(cands[k]) >= 2:
                df.at[i, date_col] = d
                df.at[i, flag_col] = {"orig": "ddmm_kept_by_sequence", "swap": "ddmm_swapped_by_sequence"}.get(
                    kind, ("ddmm_swapped_and_year_corrected" if kind.startswith("swap") else "year_corrected_by_sequence"))
    return df

# ----------------------------------------------------------------- crops
CROP_MAP = {
    # ragi / finger millet
    "ragi": "finger_millet", "raagi": "finger_millet", "ragii": "finger_millet", "ರಾಗಿ": "finger_millet",
    "finger millet": "finger_millet",
    # pigeon pea / tur / togari / redgram
    "togari": "pigeon_pea", "toor dal": "pigeon_pea", "pigeon pea": "pigeon_pea", "pigeon peas": "pigeon_pea",
    "thogra": "pigeon_pea", "thogre": "pigeon_pea", "thogr": "pigeon_pea", "tur": "pigeon_pea",
    "redgram": "pigeon_pea", "red gram": "pigeon_pea", "toor": "pigeon_pea", "togri": "pigeon_pea",
    "ತೊಗರಿ": "pigeon_pea", "togare": "pigeon_pea", "thogari": "pigeon_pea", "tugari": "pigeon_pea",
    "tohgr": "pigeon_pea", "togre": "pigeon_pea", "tohgre": "pigeon_pea", "thogar": "pigeon_pea", "toghre": "pigeon_pea",
    "togra": "pigeon_pea", "turi": "pigeon_pea", "tohari": "pigeon_pea", "thugra": "pigeon_pea", "thog": "pigeon_pea",
    "thoga": "pigeon_pea", "pigeon": "pigeon_pea", "togri ": "pigeon_pea",
    "halasande": "cowpea", "alasande": "cowpea", "cowpea": "cowpea", "uruli": "horse_gram", "jowae": "sorghum",
    "channa": "chickpea", "senga": "groundnut", "kusibi": "safflower", "peas": "peas", "potato": "potato",
    "hola": "unknown",
    # maize
    "corn": "maize", "maize": "maize", "mekkejola": "maize", "mekke jola": "maize", "ಮೆಕ್ಕೆಜೋಳ": "maize",
    "makkejola": "maize", "mekke": "maize", "mejola": "maize", "mjola": "maize", "mjol": "maize",
    # sorghum / jowar / jola
    "jola": "sorghum", "jowar": "sorghum", "jol": "sorghum", "ಜೋಳ": "sorghum", "sorghum": "sorghum", "jowar ": "sorghum",
    # horse gram
    "horse gram": "horse_gram", "horsegram": "horse_gram", "huruli": "horse_gram", "horse": "horse_gram",
    "hurali": "horse_gram", "ಹುರುಳಿ": "horse_gram", "horse gram ": "horse_gram",
    # green gram
    "hesaru": "green_gram", "green gram": "green_gram", "greengram": "green_gram", "moong": "green_gram",
    "ಹೆಸರು": "green_gram", "hesru": "green_gram",
    # black gram
    "black gram": "black_gram", "uddu": "black_gram", "blackgram": "black_gram", "urad": "black_gram",
    # bengal gram / chickpea
    "bengal gram": "chickpea", "kadale": "chickpea", "kadle": "chickpea", "kadli": "chickpea", "chana": "chickpea",
    "chickpea": "chickpea", "ಕಡಲೆ": "chickpea", "bengalgram": "chickpea", "gram": "chickpea",
    # groundnut
    "shenga": "groundnut", "groundnut": "groundnut", "ground nut": "groundnut", "kadalekai": "groundnut",
    "ಶೇಂಗಾ": "groundnut", "peanut": "groundnut",
    # others
    "sunflower": "sunflower", "surya kanti": "sunflower", "onion": "onion", "cotton": "cotton", "hatti": "cotton",
    "sajje": "pearl_millet", "bajra": "pearl_millet", "pearl millet": "pearl_millet",
    "kusubi": "safflower", "safflower": "safflower", "chilli": "chilli", "chilly": "chilli", "menasu": "chilli",
    "rice": "paddy", "paddy": "paddy", "bhatta": "paddy",
    "soya bean": "soybean", "soybean": "soybean", "soya": "soybean", "soyabean": "soybean",
    "adike": "arecanut", "arecanut": "arecanut", "areca": "arecanut",
    "coconut": "coconut", "tengu": "coconut", "mango": "mango", "banana": "banana", "sugarcane": "sugarcane",
    "sugar cane": "sugarcane", "kabbu": "sugarcane", "tomato": "tomato", "brinjal": "brinjal",
    "wheat": "wheat", "godhi": "wheat", "avare": "field_bean", "field bean": "field_bean",
    "castor": "castor", "haralu": "castor", "navane": "foxtail_millet", "foxtail": "foxtail_millet",
    "no crop": "no_crop", "nocrop": "no_crop", "fallow": "no_crop", "barren": "no_crop", "no": "no_crop",
    "nothing": "no_crop", "nill": "no_crop", "nil": "no_crop", "none": "no_crop", "-": "no_crop",
    "lime": "lime", "guava": "guava", "pomegranate": "pomegranate", "pomo": "pomegranate", "jamun": "jamun",
    "sapota": "sapota", "papaya": "papaya", "marigold": "marigold", "rose": "rose",
}
def harmonize_crop(v):
    """Map a raw crop string to a canonical crop class. Mixed entries ('Soyabean and Tur',
    'Maize,Redgram,Banana') -> first crop + '_mixed'. Unknown -> 'other:<raw>' (never dropped)."""
    if v is None:
        return "unknown"
    s = str(v).strip().lower()
    if s == "" or s in {"select crop", "nan"}:
        return "unknown"
    s = re.sub(r"\s+", " ", s)
    if s in CROP_MAP:
        return CROP_MAP[s]
    parts = [p.strip() for p in re.split(r"[,+&/]| and | with ", s) if p.strip()]
    if len(parts) > 1:
        first = CROP_MAP.get(parts[0], None)
        return (first if first else "other:" + parts[0]) + "_mixed"
    if re.match(r"^t[ho]+g", s):          # remaining spellings of togari (pigeon pea)
        return "pigeon_pea"
    # fuzzy: prefix match on known keys
    for k, val in CROP_MAP.items():
        if len(k) >= 4 and s.startswith(k):
            return val
    return "other:" + s

# ----------------------------------------------------------------- SWS role table
# Built ONLY from labels that appear in the workbooks themselves ("Saturation SWS", "Control
# Sub-Watershed", "ITGI (Control Sub-watershed)") plus the REWARD Koppal SWS code from the MIS.
# Any SWS not listed is 'unlabelled' -- do not assume. Fill the remaining rows from your
# RWD_Sub_watershed_final_list.xlsx crosswalk (the pipeline's SUBWSHED_CROSSWALK_PATH).
SWS_ROLE = {
    # UASD (Dharwad) -- labelled in the SSM/LAI/GW sheets
    "nilagunda": "saturation", "nilgunda": "saturation", "artal": "saturation", "kodihalli": "saturation",
    "shirur": "saturation",
    "gadag": "control", "kohalli": "control", "hosahalli": "control", "hanchinal": "control",
    # UASR (Raichur) -- 'ITGI (Control Sub-watershed)'
    "itgi": "control", "hunsehadagli": "unlabelled", "hunasehadigil": "unlabelled", "jantapur": "unlabelled",
    # UHSB (Bagalkot) -- 'Honnutagi saturation SWS', 'Chittraggi Saturation SWS', 'Ukumnal Control SWS'
    "honnutagi": "saturation", "chittaragi": "saturation", "chittraggi": "saturation",
    "ukumnal": "control", "pashapur": "unlabelled", "kandgul": "unlabelled", "ganjihal": "unlabelled",
    # UAHS (Shivamogga) / UASB (Bengaluru) -- no role labels in the files
}
def sws_role(name):
    if name is None:
        return "unlabelled"
    s = re.sub(r"[^a-z]", "", str(name).lower().split("sub")[0])
    for k, v in SWS_ROLE.items():
        if s.startswith(k):
            return v
    return "unlabelled"

def clean_name(v):
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()

def norm_key(v):
    return re.sub(r"[^a-z0-9]", "", str(v or "").lower())
