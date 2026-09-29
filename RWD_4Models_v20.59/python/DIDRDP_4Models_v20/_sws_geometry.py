"""
_sws_geometry.py -- which sub-watershed (and which ring) every pixel really falls in (v20.28).

Reads the 20-site shapefile SWSs20_KarnatakaAll5k (shipped in data/sites/): 120 polygons = for each SWSiD_All (1..20,
name in SUBWSHED) the saturation core (buff_km 0) and five 1-km control rings (buff_km 1..5), as hollow bands
(outer ring + hole, some with hundreds of parts). The shapefile is in WGS 84 / UTM zone 43N (metres, read from the
.prj); pixel coordinates are latitude / longitude, so every point is projected with the Krueger series (Karney 2011,
sub-millimetre inside a zone) before testing.

Point-in-polygon is the even-odd crossing rule, indexed: each polygon's edges are bucketed into horizontal bands,
so a point is tested only against the few edges that cross its band (tens instead of ~1,300). No GIS library is
needed; `validate_sws_geometry.py` checks it against matplotlib's independent C implementation.

    L = SWSLocator.from_shapefile()          # built once per process, < 1 s
    hits = L.locate(lat, lon)                # every (site, ring) each point falls in
    out = L.tag(lat, lon, indicated_site)    # verified / corrected / assigned site + ring per row
"""
import os, re, struct
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SHAPEFILE = os.path.join(HERE, "data", "sites", "SWSs20_KarnatakaAll5k.shp")

# site_check codes written with every row
CONFIRMED, CORRECTED, ASSIGNED, OUTSIDE, NO_GEOMETRY = 0, 1, 2, 3, 4
CHECK_LABEL = {CONFIRMED: "confirmed (id in the data matches the polygon)",
               CORRECTED: "corrected (id in the data was wrong; polygon id assigned)",
               ASSIGNED: "assigned (no id in the data; polygon id assigned)",
               OUTSIDE: "outside every polygon (kept with the id from the data, flagged)",
               NO_GEOMETRY: "not checked (shapefile unavailable)"}


# ----------------------------------------------------------------------------------------------- shapefile
def read_shp_polygons(path):
    """[(parts: list of (N,2) float64 arrays, bbox)] per record, in file order. Polygon / PolygonZ / PolygonM."""
    b = open(path, "rb").read()
    if struct.unpack(">i", b[0:4])[0] != 9994: raise ValueError(f"{path} is not a shapefile")
    flen = struct.unpack(">i", b[24:28])[0] * 2
    out, p = [], 100
    while p < flen:
        _rn, cl = struct.unpack(">2i", b[p:p + 8]); c = b[p + 8:p + 8 + cl * 2]; p += 8 + cl * 2
        st = struct.unpack("<i", c[0:4])[0]
        if st == 0: out.append(([], (np.nan,) * 4)); continue
        if st not in (5, 15, 25): raise ValueError(f"shape type {st} is not a polygon")
        xmin, ymin, xmax, ymax = struct.unpack("<4d", c[4:36]); npart, npts = struct.unpack("<2i", c[36:44])
        starts = list(struct.unpack(f"<{npart}i", c[44:44 + 4 * npart])) + [npts]
        xy = np.frombuffer(c[44 + 4 * npart:44 + 4 * npart + 16 * npts], dtype="<f8").reshape(npts, 2)
        out.append(([xy[starts[i]:starts[i + 1]].copy() for i in range(npart)], (xmin, ymin, xmax, ymax)))
    return out


def read_prj(path):
    """{'kind': 'utm'|'geographic', 'lon0', 'k0', 'fe', 'fn'} from a .prj (ESRI WKT)."""
    wkt = open(path, encoding="latin-1").read()
    if wkt.strip().upper().startswith("GEOGCS"): return {"kind": "geographic"}
    if "Transverse_Mercator" not in wkt and "TRANSVERSE_MERCATOR" not in wkt.upper():
        raise ValueError(f"unsupported projection in {path}: only UTM / Transverse Mercator or geographic WGS 84")
    if "WGS_1984" not in wkt and "WGS 84" not in wkt and "WGS84" not in wkt:
        raise ValueError(f"datum in {path} is not WGS 84")
    def par(name, default):
        m = re.search(r'PARAMETER\["' + name + r'",\s*([-0-9.eE+]+)\]', wkt, re.I)
        return float(m.group(1)) if m else default
    return {"kind": "utm", "lon0": par("Central_Meridian", 75.0), "k0": par("Scale_Factor", 0.9996),
            "fe": par("False_Easting", 500000.0), "fn": par("False_Northing", 0.0), "lat0": par("Latitude_Of_Origin", 0.0)}


# ----------------------------------------------------------------------------------------------- projection
_A, _F = 6378137.0, 1 / 298.257223563           # WGS 84
_N = _F / (2 - _F)
_ALPHA = (_N / 2 - 2 * _N**2 / 3 + 5 * _N**3 / 16 + 41 * _N**4 / 180 - 127 * _N**5 / 288 + 7891 * _N**6 / 37800,
          13 * _N**2 / 48 - 3 * _N**3 / 5 + 557 * _N**4 / 1440 + 281 * _N**5 / 630 - 1983433 * _N**6 / 1935360,
          61 * _N**3 / 240 - 103 * _N**4 / 140 + 15061 * _N**5 / 26880 + 167603 * _N**6 / 181440,
          49561 * _N**4 / 161280 - 179 * _N**5 / 168 + 6601661 * _N**6 / 7257600,
          34729 * _N**5 / 80640 - 3418889 * _N**6 / 1995840,
          212378941 * _N**6 / 319334400)
_BETA = (_N / 2 - 2 * _N**2 / 3 + 37 * _N**3 / 96 - _N**4 / 360 - 81 * _N**5 / 512 + 96199 * _N**6 / 604800,
         _N**2 / 48 + _N**3 / 15 - 437 * _N**4 / 1440 + 46 * _N**5 / 105 - 1118711 * _N**6 / 3870720,
         17 * _N**3 / 480 - 37 * _N**4 / 840 - 209 * _N**5 / 4480 + 5569 * _N**6 / 90720,
         4397 * _N**4 / 161280 - 11 * _N**5 / 504 - 830251 * _N**6 / 7257600,
         4583 * _N**5 / 161280 - 108847 * _N**6 / 3991680,
         20648693 * _N**6 / 638668800)
_AR = _A / (1 + _N) * (1 + _N**2 / 4 + _N**4 / 64 + _N**6 / 256)     # rectifying radius
_E = np.sqrt(_F * (2 - _F))


def latlon_to_tm(lat, lon, lon0=75.0, k0=0.9996, fe=500000.0, fn=0.0):
    """WGS 84 latitude/longitude (degrees) -> Transverse Mercator easting/northing (metres), Krueger 6th order."""
    phi = np.radians(np.asarray(lat, np.float64)); lam = np.radians(np.asarray(lon, np.float64) - lon0)
    t = np.sinh(np.arctanh(np.sin(phi)) - _E * np.arctanh(_E * np.sin(phi)))
    xi_p = np.arctan2(t, np.cos(lam)); eta_p = np.arctanh(np.sin(lam) / np.sqrt(1 + t * t))
    xi, eta = xi_p.copy(), eta_p.copy()
    for j, a in enumerate(_ALPHA, start=1):
        xi += a * np.sin(2 * j * xi_p) * np.cosh(2 * j * eta_p)
        eta += a * np.cos(2 * j * xi_p) * np.sinh(2 * j * eta_p)
    return fe + k0 * _AR * eta, fn + k0 * _AR * xi


def tm_to_latlon(x, y, lon0=75.0, k0=0.9996, fe=500000.0, fn=0.0):
    """Inverse of latlon_to_tm (used for validation and for building synthetic test pixels)."""
    xi = (np.asarray(y, np.float64) - fn) / (k0 * _AR); eta = (np.asarray(x, np.float64) - fe) / (k0 * _AR)
    xi_p, eta_p = xi.copy(), eta.copy()
    for j, b in enumerate(_BETA, start=1):
        xi_p -= b * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
        eta_p -= b * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
    tau_p = np.sin(xi_p) / np.sqrt(np.sinh(eta_p) ** 2 + np.cos(xi_p) ** 2)
    tau = tau_p.copy()
    for _ in range(6):                                        # Newton on tau (Karney 2011, eq. 19-21)
        sig = np.sinh(_E * np.arctanh(_E * tau / np.sqrt(1 + tau * tau)))
        tp = tau * np.sqrt(1 + sig * sig) - sig * np.sqrt(1 + tau * tau)
        dtau = (tau_p - tp) / np.sqrt(1 + tp * tp) * (1 + (1 - _E**2) * tau * tau) / ((1 - _E**2) * np.sqrt(1 + tau * tau))
        tau += dtau
    return np.degrees(np.arctan(tau)), lon0 + np.degrees(np.arctan2(np.sinh(eta_p), np.cos(xi_p)))


# ----------------------------------------------------------------------------------------------- point in polygon
class PolygonIndex:
    """Even-odd point-in-polygon for one (multi-part, holed) polygon, with edges bucketed by horizontal band."""
    def __init__(self, parts, band_h=None):
        segs = []
        for ring in parts:
            if len(ring) < 3: continue
            r = np.asarray(ring, np.float64)
            if not np.allclose(r[0], r[-1]): r = np.vstack([r, r[:1]])
            segs.append(np.column_stack([r[:-1], r[1:]]))
        e = np.vstack(segs) if segs else np.zeros((0, 4))
        e = e[e[:, 1] != e[:, 3]]                                  # horizontal edges never cross a horizontal ray
        self.x0, self.y0, self.x1, self.y1 = e[:, 0], e[:, 1], e[:, 2], e[:, 3]
        self.bbox = (e[:, [0, 2]].min(), e[:, [1, 3]].min(), e[:, [0, 2]].max(), e[:, [1, 3]].max()) if len(e) else (np.inf,) * 2 + (-np.inf,) * 2
        ymin_e = np.minimum(self.y0, self.y1); ymax_e = np.maximum(self.y0, self.y1)
        H = (self.bbox[3] - self.bbox[1]) if len(e) else 1.0
        self.h = float(band_h or max(H / max(len(e) / 8.0, 1.0), 1.0))  # ~8 edges per band on average
        self.Y0 = self.bbox[1]
        b0 = np.floor((ymin_e - self.Y0) / self.h).astype(np.int64); b1 = np.floor((ymax_e - self.Y0) / self.h).astype(np.int64)
        cnt = b1 - b0 + 1
        eidx = np.repeat(np.arange(len(e)), cnt)
        band = np.repeat(b0, cnt) + (np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt))
        o = np.argsort(band, kind="mergesort")
        self.band_edges = eidx[o]; bands_sorted = band[o]
        self.nb = int(bands_sorted.max()) + 1 if len(bands_sorted) else 0
        self.ptr = np.searchsorted(bands_sorted, np.arange(self.nb + 1))

    def contains(self, x, y):
        x = np.asarray(x, np.float64); y = np.asarray(y, np.float64)
        inside = np.zeros(len(x), dtype=bool)
        if self.nb == 0: return inside
        cand = (x >= self.bbox[0]) & (x <= self.bbox[2]) & (y >= self.bbox[1]) & (y <= self.bbox[3])
        idx = np.nonzero(cand)[0]
        if not len(idx): return inside
        band = np.floor((y[idx] - self.Y0) / self.h).astype(np.int64)
        band = np.clip(band, 0, self.nb - 1)
        o = np.argsort(band, kind="mergesort"); idx, band = idx[o], band[o]
        ub, first = np.unique(band, return_index=True)
        last = list(first[1:]) + [len(band)]
        for b, s, t in zip(ub, first, last):
            es = self.band_edges[self.ptr[b]:self.ptr[b + 1]]
            if not len(es): continue
            px = x[idx[s:t]][:, None]; py = y[idx[s:t]][:, None]
            y0 = self.y0[es][None, :]; y1 = self.y1[es][None, :]; x0 = self.x0[es][None, :]; x1 = self.x1[es][None, :]
            straddle = (y0 > py) != (y1 > py)
            with np.errstate(divide="ignore", invalid="ignore"):
                xint = x0 + (py - y0) * (x1 - x0) / (y1 - y0)
            inside[idx[s:t]] = (np.count_nonzero(straddle & (px < xint), axis=1) % 2) == 1
        return inside


# ----------------------------------------------------------------------------------------------- the locator
class SWSLocator:
    """Sites and rings of the 20-SWS shapefile, ready to locate latitude/longitude points."""
    def __init__(self, records, attrs, prj):
        self.prj = prj
        self.polys = []            # (site, buff, PolygonIndex)
        for (parts, _bb), (_, a) in zip(records, attrs.iterrows()):
            if not parts: continue
            self.polys.append((int(a["SWSiD_All"]), int(a["buff_km"]), PolygonIndex(parts)))
        self.sites = sorted({s for s, _, _ in self.polys})
        self.names = {int(r.SWSiD_All): str(r.SUBWSHED).strip() for r in attrs.itertuples()}
        self.name_to_id = {self._norm(v): k for k, v in self.names.items()}
        self.site_bbox = {}
        for s in self.sites:
            bb = np.array([p.bbox for ss, _, p in self.polys if ss == s])
            self.site_bbox[s] = (bb[:, 0].min(), bb[:, 1].min(), bb[:, 2].max(), bb[:, 3].max())

    @staticmethod
    def _norm(s):
        return re.sub(r"[^a-z0-9]", "", str(s).lower())

    @classmethod
    def from_shapefile(cls, path=None):
        path = path or DEFAULT_SHAPEFILE
        stem = os.path.splitext(path)[0]
        import _sites as _S
        return cls(read_shp_polygons(stem + ".shp"), _S.read_dbf(stem + ".dbf"), read_prj(stem + ".prj"))

    def site_id_for_name(self, name):
        """SWSiD_All for a sub-watershed NAME (case / punctuation insensitive), else None."""
        if name is None: return None
        k = self._norm(name)
        if not k: return None
        if k in self.name_to_id: return self.name_to_id[k]
        # a folder like "REWARD_Artal_Exports" or "Nilgunda sub-watershed" CONTAINS the name; the LONGEST contained
        # name wins ("Chhatrakodihalli ..." must not resolve to "Kodihalli")
        hits = [(len(nk), sid) for nk, sid in self.name_to_id.items() if len(nk) >= 4 and nk in k]
        if hits: return max(hits)[1]
        # v20.47: YOUR 80 % RULE -- a word of the name >= 80 % similar to ONE sub-watershed (unambiguous) names it
        import _names as _N
        cands = {nk: sid for nk, sid in self.name_to_id.items()}
        cands.update({ak: self.name_to_id[_N.norm_name(v)] for ak, v in _N.PROGRAMME_ALIASES.items() if _N.norm_name(v) in self.name_to_id})
        for tok in sorted(set(re.findall(r"[a-z]{4,}", str(name).lower())) | {k}, key=len, reverse=True):
            sid, sc, _ = _N.best_match(tok, cands)
            if sid is not None: return sid
        return None

    def project(self, lat, lon):
        if self.prj["kind"] == "geographic": return np.asarray(lon, np.float64), np.asarray(lat, np.float64)
        return latlon_to_tm(lat, lon, self.prj["lon0"], self.prj["k0"], self.prj["fe"], self.prj["fn"])

    def locate(self, lat, lon):
        """{site: buff array (int8, -1 = not in that site)} for every site whose outline could contain a point."""
        x, y = self.project(lat, lon)
        res = {}
        for s in self.sites:
            bx0, by0, bx1, by1 = self.site_bbox[s]
            m = (x >= bx0) & (x <= bx1) & (y >= by0) & (y <= by1)
            if not m.any(): continue
            buff = np.full(len(x), -1, dtype=np.int8)
            idx = np.nonzero(m)[0]
            for ss, bk, poly in sorted([t for t in self.polys if t[0] == s], key=lambda t: t[1]):
                todo = idx[buff[idx] < 0]
                if not len(todo): break
                hit = poly.contains(x[todo], y[todo])
                buff[todo[hit]] = bk
            if (buff >= 0).any(): res[s] = buff
        return res

    def tag(self, lat, lon, indicated=None):
        """Per row: site_id, buff_km_geom, site_check (see CHECK_LABEL). `indicated` = the site the data says
        (int array / scalar, 0 or None = none). A point in the indicated site's polygons keeps that site
        (overlapping rings of neighbouring sites are legitimate); otherwise it takes the site whose polygon holds it
        (core before rings, then the lower SWSiD_All); a point in no polygon keeps the indicated site, flagged."""
        n = len(lat)
        ind = np.zeros(n, dtype=np.int64) if indicated is None else np.broadcast_to(
            np.nan_to_num(np.asarray(indicated, dtype=np.float64), nan=0).astype(np.int64), (n,)).copy()
        hits = self.locate(lat, lon)
        site = np.zeros(n, dtype=np.int16); buff = np.full(n, -1, dtype=np.int8); check = np.full(n, OUTSIDE, dtype=np.int8)
        best_s = np.zeros(n, dtype=np.int64); best_b = np.full(n, 99, dtype=np.int64)
        for s in sorted(hits):
            b = hits[s].astype(np.int64); m = (b >= 0) & (b < best_b)
            best_s[m] = s; best_b[m] = b[m]
        conf = np.zeros(n, dtype=bool)
        for s, b in hits.items():
            m = (ind == s) & (b >= 0)
            site[m] = s; buff[m] = b[m]; conf |= m
        check[conf] = CONFIRMED
        rest = ~conf & (best_s > 0)
        site[rest] = best_s[rest]; buff[rest] = best_b[rest]
        check[rest & (ind > 0)] = CORRECTED; check[rest & (ind <= 0)] = ASSIGNED
        out_ = ~conf & (best_s == 0)
        site[out_] = np.clip(ind[out_], 0, 32767)
        return site, buff, check
