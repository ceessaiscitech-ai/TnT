"""
_sites.py -- the 20 sub-watersheds and their control rings, from SWSs20_KarnatakaAll5k (v20.22).

The shapefile (kept in data/sites/) holds 120 polygons: for each of the 20 saturation sub-watersheds the core
(buff_km 0) and five 1-km control rings (buff_km 1..5), identified by SWSiD_All (1..20). Each site belongs to
Saturation Phase 1 (11 sites) or Phase 2 (9 sites, Artal = 1 among them). Two phases mean two treatment
cohorts once the panel is pooled -- the staggered estimators (M05, M09, M30, M31, M22) become identified, and
clustering by site gives 20 clusters instead of 6-7.

`sites.csv` is the registry both engines read. Fill `treatment_year` per phase (or per site) before a pooled
run; leave blank to fall back to the scenario's single TREATMENT_YEAR.

    import _sites as S
    S.registry()                    -> DataFrame: SWSiD_All, name, phase, treatment_year, n_rings
    S.treatment_year(7)             -> the treatment year for site 7 (registry, else the scenario default)
    S.name(1) -> "Artal";  S.site_id("Artal") -> 1
"""
import os, struct
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SITES_DIR = os.path.join(HERE, "data", "sites")
SHAPEFILE_STEM = "SWSs20_KarnatakaAll5k"
REGISTRY_CSV = os.path.join(SITES_DIR, "sites.csv")
SITE_ID_COL = "SWSiD_All"          # the column the pooled exports carry
PHASE_TREATMENT_YEAR = {1: None, 2: 2022}   # v20.26: Phase 2 (Artal) works started 2022; FILL Phase 1 if it differs
                                            # (None = the scenario's TREATMENT_YEAR, now 2022)


def read_dbf(path):
    """Attribute table of a shapefile, no GIS library needed."""
    b = open(path, "rb").read()
    n_rec = struct.unpack("<I", b[4:8])[0]; hdr = struct.unpack("<H", b[8:10])[0]; rec = struct.unpack("<H", b[10:12])[0]
    fields, p = [], 32
    while b[p] != 0x0D:
        name = b[p:p + 11].split(b"\x00")[0].decode("latin-1"); typ = chr(b[p + 11]); ln = b[p + 16]
        fields.append((name, typ, ln)); p += 32
    rows, p = [], hdr
    for _ in range(n_rec):
        r = b[p:p + rec]; p += rec; q = 1; row = {}
        for name, typ, ln in fields:
            v = r[q:q + ln].decode("latin-1").strip(); q += ln
            if typ in ("N", "F"):
                try: v = float(v) if ("." in v or "e" in v.lower()) else int(v)
                except ValueError: v = np.nan
            row[name] = v
        rows.append(row)
    return pd.DataFrame(rows)


def build_registry(dbf_path=None, out_csv=None, verbose=True):
    """sites.csv from the shapefile attributes: one row per SWSiD_All with name, phase, rings, treatment_year."""
    dbf_path = dbf_path or os.path.join(SITES_DIR, SHAPEFILE_STEM + ".dbf")
    d = read_dbf(dbf_path)
    d["SWSiD_All"] = d["SWSiD_All"].astype(int); d["buff_km"] = d["buff_km"].astype(int)
    reg = (d.groupby("SWSiD_All").agg(name=("SUBWSHED", "first"), phase=("SorC_SWS", "first"),
                                      phase_label=("Name", "first"), n_rings=("buff_km", lambda s: int((s > 0).sum())),
                                      core_area=("Shape_Area", lambda s: float(d.loc[s.index][d.loc[s.index, "buff_km"] == 0]["Shape_Area"].sum())))
             .reset_index())
    reg["phase"] = reg["phase"].astype(int)
    reg["treatment_year"] = reg["phase"].map(PHASE_TREATMENT_YEAR)
    reg = reg.sort_values("SWSiD_All").reset_index(drop=True)
    out_csv = out_csv or REGISTRY_CSV
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    reg.to_csv(out_csv, index=False)
    if verbose:
        print(f"[OK]      sites registry: {len(reg)} sites, phases {reg.phase.value_counts().to_dict()} -> {out_csv}")
        blank = reg[reg.treatment_year.isna()]
        if len(blank):
            print(f"[WARNING] treatment_year is blank for {len(blank)} site(s) (phase {sorted(blank.phase.unique())}): "
                  f"fill sites.csv (or PHASE_TREATMENT_YEAR) before a pooled staggered run; single-cohort runs fall "
                  f"back to the scenario's TREATMENT_YEAR")
    return reg


_REG = None
def registry(refresh=False):
    global _REG
    if _REG is None or refresh:
        if os.path.exists(REGISTRY_CSV):
            _REG = pd.read_csv(REGISTRY_CSV)
        elif os.path.exists(os.path.join(SITES_DIR, SHAPEFILE_STEM + ".dbf")):
            _REG = build_registry(verbose=False)
        else:
            _REG = pd.DataFrame(columns=["SWSiD_All", "name", "phase", "phase_label", "n_rings", "core_area", "treatment_year"])
    return _REG


def name(site_id):
    r = registry(); m = r[r.SWSiD_All == int(site_id)]
    return str(m.name.iloc[0]) if len(m) else f"site_{int(site_id)}"


def site_id(site_name):
    r = registry(); key = str(site_name).strip().lower()
    m = r[r.name.astype(str).str.strip().str.lower() == key]
    return int(m.SWSiD_All.iloc[0]) if len(m) else None


def phase(site_id):
    r = registry(); m = r[r.SWSiD_All == int(site_id)]
    return int(m.phase.iloc[0]) if len(m) else None


def treatment_year(site_id, default=None):
    """Registry year for the site; else the phase default; else `default` (the scenario's TREATMENT_YEAR)."""
    r = registry(); m = r[r.SWSiD_All == int(site_id)]
    if len(m) and pd.notna(m.treatment_year.iloc[0]): return int(m.treatment_year.iloc[0])
    ph = phase(site_id)
    if ph is not None and PHASE_TREATMENT_YEAR.get(ph): return int(PHASE_TREATMENT_YEAR[ph])
    return default


def treatment_year_source(site_id):
    """v20.39: where a site's implementation year comes from -- 'registry' (data/sites/sites.csv), 'phase default'
    (PHASE_TREATMENT_YEAR), or 'ASSUMED' (neither: the scenario's TREATMENT_YEAR is used, silently until now)."""
    r = registry(); m = r[r.SWSiD_All == int(site_id)]
    if len(m) and pd.notna(m.treatment_year.iloc[0]): return "registry"
    ph = phase(site_id)
    if ph is not None and PHASE_TREATMENT_YEAR.get(ph): return "phase default"
    return "ASSUMED"


def cohorts(default=None):
    """{SWSiD_All: treatment_year} for every site (None where nothing is known and no default given)."""
    return {int(s): treatment_year(s, default) for s in registry().SWSiD_All}


def n_cohorts(default=None):
    return len({y for y in cohorts(default).values() if y is not None})


if __name__ == "__main__":
    print(build_registry().to_string(index=False))
