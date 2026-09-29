"""
Band-tracking mock of the `ee` (Earth Engine) Python client.

Purpose: exercise artal_exporter_*.py end-to-end WITHOUT network access, while
still catching the class of bug real Earth Engine catches server-side --
selecting a band that does not exist in an image / collection. Every mock
Image carries a `bands` list; select() raises if a requested band is absent
(mirroring "Image.select: Band pattern 'X' did not match any bands").

Collections carry a band list derived from a small catalog and a mock
"data end" date so collection_end()/_covers()/clamp_window() behave as they
would against the live catalog on the run date. Both can be overridden from a
test (see CATALOG / DATA_END / today()).
"""
import datetime as _dt
from datetime import date as _date
import re as _re

# ----------------------------------------------------------------------------
# Test-controllable state
# ----------------------------------------------------------------------------
_TODAY = None                     # None -> real date.today()


def set_today(d):
    global _TODAY
    _TODAY = d


def today():
    return _TODAY or _date.today()


# Bands published by each collection id (only what the exporter touches).
CATALOG = {
    'COPERNICUS/S2_SR_HARMONIZED': ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A',
                                    'B9', 'B11', 'B12', 'SCL', 'QA60', 'MSK_CLDPRB'],
    'COPERNICUS/S2_HARMONIZED': ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A',
                                 'B9', 'B10', 'B11', 'B12', 'QA60'],
    'GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED': ['cs', 'cs_cdf'],
    'LANDSAT/LC08/C02/T1_L2': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7',
                               'ST_B10', 'QA_PIXEL'],
    'LANDSAT/LC09/C02/T1_L2': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7',
                               'ST_B10', 'QA_PIXEL'],
    'MODIS/061/MOD09A1': ['sur_refl_b01', 'sur_refl_b02', 'sur_refl_b03', 'sur_refl_b04',
                          'sur_refl_b05', 'sur_refl_b06', 'sur_refl_b07', 'StateQA'],
    'MODIS/061/MYD09A1': ['sur_refl_b01', 'sur_refl_b02', 'sur_refl_b03', 'sur_refl_b04',
                          'sur_refl_b05', 'sur_refl_b06', 'sur_refl_b07', 'StateQA'],
    'MODIS/061/MOD13Q1': ['NDVI', 'EVI', 'SummaryQA', 'DetailedQA'],
    'MODIS/061/MYD13Q1': ['NDVI', 'EVI', 'SummaryQA', 'DetailedQA'],
    'MODIS/061/MOD11A2': ['LST_Day_1km', 'QC_Day', 'LST_Night_1km', 'QC_Night'],
    'MODIS/061/MYD11A2': ['LST_Day_1km', 'QC_Day', 'LST_Night_1km', 'QC_Night'],
    'MODIS/061/MOD15A2H': ['Fpar_500m', 'Lai_500m', 'FparLai_QC', 'FparExtra_QC'],
    'MODIS/061/MYD15A2H': ['Fpar_500m', 'Lai_500m', 'FparLai_QC', 'FparExtra_QC'],
    'MODIS/061/MOD16A2GF': ['ET', 'LE', 'PET', 'PLE', 'ET_QC'],
    'MODIS/061/MYD16A2GF': ['ET', 'LE', 'PET', 'PLE', 'ET_QC'],
    'MODIS/061/MOD16A2': ['ET', 'LE', 'PET', 'PLE', 'ET_QC'],
    'IDAHO_EPSCOR/TERRACLIMATE': ['aet', 'def', 'pdsi', 'pet', 'pr', 'ro', 'soil', 'srad',
                                  'swe', 'tmmn', 'tmmx', 'vap', 'vpd', 'vs'],
    'UCSB-CHG/CHIRPS/DAILY': ['precipitation'],
    'UCSB-CHG/CHIRTS/DAILY': ['maximum_temperature', 'minimum_temperature'],
    'ECMWF/ERA5_LAND/DAILY_AGGR': ['temperature_2m', 'temperature_2m_max', 'temperature_2m_min',
                                   'skin_temperature', 'volumetric_soil_water_layer_1',
                                   'volumetric_soil_water_layer_2',
                                   'volumetric_soil_water_layer_3', 'total_precipitation_sum'],
    'ECMWF/ERA5_LAND/MONTHLY_AGGR': ['temperature_2m', 'temperature_2m_max', 'temperature_2m_min',
                                     'skin_temperature', 'volumetric_soil_water_layer_1',
                                     'volumetric_soil_water_layer_2',
                                     'volumetric_soil_water_layer_3'],
    'GOOGLE/DYNAMICWORLD/V1': ['water', 'trees', 'grass', 'flooded_vegetation', 'crops',
                               'shrub_and_scrub', 'built', 'bare', 'snow_and_ice', 'label'],
    'COPERNICUS/S1_GRD': ['VV', 'VH', 'angle'],
    'COPERNICUS/DEM/GLO30_2024_1': ['DEM', 'EDM', 'FLM', 'HEM', 'WBM'],
    'projects/sat-io/open-datasets/FABDEM': ['b1'],
    'LARSE/GEDI/GEDI04_A_002': [],
}
IMAGE_CATALOG = {
    'NASA/NASADEM_HGT/001': ['elevation', 'num', 'swb'],
    'OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02': ['b0', 'b10', 'b30', 'b60', 'b100', 'b200'],
    'OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02': ['b0', 'b10', 'b30', 'b60', 'b100', 'b200'],
    'OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02': ['b0', 'b10', 'b30', 'b60', 'b100', 'b200'],
    'OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02': ['b0', 'b10', 'b30', 'b60', 'b100', 'b200'],
    'MERIT/Hydro/v1_0_1': ['elv', 'dir', 'wth', 'wat', 'upa', 'upg', 'hnd', 'viswth'],
}

# Last image date per collection, "as of" a Sept-2026 run against the live catalog.
DATA_END = {
    'MODIS/061/MOD16A2GF': _date(2025, 12, 27),
    'MODIS/061/MYD16A2GF': _date(2025, 12, 27),
    'IDAHO_EPSCOR/TERRACLIMATE': _date(2024, 12, 1),
    'UCSB-CHG/CHIRTS/DAILY': _date(2016, 12, 31),
}
# Lag (days behind the run date) of the near-real-time collections.
LAG_DAYS = {
    'UCSB-CHG/CHIRPS/DAILY': 42,           # Sept-11 run -> data through 2026-07-31
    'MODIS/061/MOD16A2': 13,
    'ECMWF/ERA5_LAND/DAILY_AGGR': 73,
    'ECMWF/ERA5_LAND/MONTHLY_AGGR': 103,
}
DEFAULT_END_OFFSET_DAYS = 6       # everything else: today - 6 d


def data_end(cid):
    if cid in DATA_END:
        return DATA_END[cid]
    return today() - _dt.timedelta(days=LAG_DAYS.get(cid, DEFAULT_END_OFFSET_DAYS))


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
class EEException(Exception):
    pass


def _as_list(x):
    if x is None:
        return None
    if isinstance(x, (list, tuple)):
        return [_unwrap_str(v) for v in x]
    if isinstance(x, List):
        return [_unwrap_str(v) for v in x._value] if isinstance(x._value, list) else None
    return [_unwrap_str(x)]


def _unwrap_str(v):
    if isinstance(v, String):
        return v._value
    return v


def _parse_date(x):
    if isinstance(x, Date):
        return x._d
    if isinstance(x, _dt.datetime):
        return x.date()
    if isinstance(x, _date):
        return x
    if isinstance(x, str):
        return _dt.datetime.fromisoformat(x[:19]).date()
    if isinstance(x, (int, float)):
        return _dt.datetime.utcfromtimestamp(x / 1000.0).date()
    raise EEException(f"bad date {x!r}")


# ----------------------------------------------------------------------------
# Scalars / containers
# ----------------------------------------------------------------------------
class ComputedObject:
    def getInfo(self):
        return None

    def __repr__(self):
        return f"<mock {self.__class__.__name__}>"


class Number(ComputedObject):
    def __init__(self, v=0):
        self._value = v._value if isinstance(v, Number) else v

    def _num(self, o):
        return o._value if isinstance(o, Number) else o

    def add(self, o): return Number(self._value + self._num(o))
    def subtract(self, o): return Number(self._value - self._num(o))
    def multiply(self, o): return Number(self._value * self._num(o))
    def divide(self, o): return Number(self._value / self._num(o))
    def gt(self, o): return Number(int(self._value > self._num(o)))
    def gte(self, o): return Number(int(self._value >= self._num(o)))
    def lt(self, o): return Number(int(self._value < self._num(o)))
    def lte(self, o): return Number(int(self._value <= self._num(o)))
    def eq(self, o): return Number(int(self._value == self._num(o)))
    def int(self): return Number(int(self._value))
    def getInfo(self): return self._value


class String(ComputedObject):
    def __init__(self, v=''):
        self._value = v

    def getInfo(self): return self._value


class List(ComputedObject):
    def __init__(self, v=None):
        if isinstance(v, List):
            v = v._value
        self._value = list(v) if isinstance(v, (list, tuple)) else v

    @staticmethod
    def sequence(a, b, step=None):
        a = a._value if isinstance(a, Number) else a
        b = b._value if isinstance(b, Number) else b
        step = step._value if isinstance(step, Number) else (step or 1)
        out, x = [], a
        while x <= b + 1e-9:
            out.append(x)
            x += step
        return List(out)

    def map(self, fn):
        if isinstance(self._value, list):
            return List([fn(v) for v in self._value])
        return List(None)

    def get(self, i):
        if isinstance(self._value, list) and self._value:
            return self._value[i]
        return Number(0)

    def flatten(self):
        out = []
        for v in (self._value or []):
            if isinstance(v, List):
                out.extend(v._value or [])
            elif isinstance(v, list):
                out.extend(v)
            else:
                out.append(v)
        return List(out)

    def reduce(self, r):
        vals = [x._value if isinstance(x, Number) else x for x in (self._value or [])]
        vals = [v for v in vals if isinstance(v, (int, float))]
        if not vals:
            return Number(0)
        return Number(min(vals) if r == 'min' else max(vals) if r == 'max' else sum(vals))

    def contains(self, x):
        return Number(int(x in (self._value or [])))

    def size(self):
        return Number(len(self._value or []))

    def getInfo(self):
        return [v.getInfo() if isinstance(v, ComputedObject) else v for v in (self._value or [])]


class Date(ComputedObject):
    def __init__(self, d):
        self._d = _parse_date(d)

    @staticmethod
    def fromYMD(y, m, d):
        y = y._value if isinstance(y, Number) else y
        m = m._value if isinstance(m, Number) else m
        d = d._value if isinstance(d, Number) else d
        try:
            return Date(_date(int(y), int(m), int(d)))
        except ValueError:
            return Date(_date(int(y), int(m), 28))

    def advance(self, n, unit):
        n = n._value if isinstance(n, Number) else n
        if unit == 'day':
            return Date(self._d + _dt.timedelta(days=int(n)))
        if unit == 'year':
            try:
                return Date(self._d.replace(year=self._d.year + int(n)))
            except ValueError:
                return Date(self._d.replace(year=self._d.year + int(n), day=28))
        if unit == 'month':
            m = self._d.month - 1 + int(n)
            y = self._d.year + m // 12
            m = m % 12 + 1
            return Date(_date(y, m, min(self._d.day, 28)))
        raise EEException(unit)

    def millis(self):
        return Number(int(_dt.datetime(self._d.year, self._d.month, self._d.day,
                                       tzinfo=_dt.timezone.utc).timestamp() * 1000))

    def format(self, *a):
        return String(self._d.isoformat())

    def getInfo(self):
        return {'type': 'Date', 'value': self.millis()._value}


class ErrorMargin(ComputedObject):
    def __init__(self, v, unit='meters'):
        self._v = v


class Projection(ComputedObject):
    def __init__(self, crs='EPSG:4326', transform=None):
        self._crs = crs

    def atScale(self, s):
        return self

    def getInfo(self):
        return {'type': 'Projection', 'crs': self._crs}


class Reducer:
    @staticmethod
    def min(): return 'min'
    @staticmethod
    def max(): return 'max'
    @staticmethod
    def mean(): return 'mean'
    @staticmethod
    def sum(): return 'sum'
    @staticmethod
    def first(): return 'first'
    @staticmethod
    def count(): return 'count'
    @staticmethod
    def median(): return 'median'
    @staticmethod
    def percentile(p): return f'p{p}'
    @staticmethod
    def toList(n=None): return 'toList'
    @staticmethod
    def pearsonsCorrelation(): return 'pearson'


class Filter:
    def __init__(self, kind='filter'):
        self.kind = kind

    @staticmethod
    def lt(*a): return Filter('lt')
    @staticmethod
    def gt(*a): return Filter('gt')
    @staticmethod
    def eq(*a): return Filter('eq')
    @staticmethod
    def listContains(*a): return Filter('listContains')
    @staticmethod
    def notNull(*a): return Filter('notNull')
    @staticmethod
    def And(*a): return Filter('and')
    @staticmethod
    def date(*a): return Filter('date')
    @staticmethod
    def bounds(*a): return Filter('bounds')


# ----------------------------------------------------------------------------
# Geometry / Feature / FeatureCollection
# ----------------------------------------------------------------------------
ROI_BOX = [75.20, 15.30, 75.31, 15.41]   # lon/lat box (Karnataka)


def _box_coords(b):
    w, s, e, n = b
    return [[[w, s], [e, s], [e, n], [w, n], [w, s]]]


ROI_KIND = 'polygon'        # 'polygon' (Sirur-like) | 'collection' (Gummlapalli-like multi-feature)
MULTIGEOM_ERR = ("GeometryConstructors.MultiGeometry: Geometry coordinate projection "
                 "requires non-zero maxError.")


def _poison_check(g):
    if isinstance(g, Geometry) and g._poison:
        raise EEException(g._poison)


class Geometry(ComputedObject):
    """Mirrors the ONE Earth Engine rule the exporter tripped on: a
    GeometryCollection re-constructed with an explicit geodesic/CRS request
    but no maxError is rejected by the server the first time anything
    evaluates it. Such a geometry is 'poisoned' here and every use raises
    the real error text, exactly where the live service raised it."""
    def __init__(self, geojson=None, proj=None, geodesic=None, box=None, poison=None):
        self._box = box or ROI_BOX
        self._poison = poison
        self._kind = 'Polygon'
        if isinstance(geojson, dict):
            self._kind = geojson.get('type', 'Polygon')
            if self._kind == 'GeometryCollection' and (proj is not None or geodesic is not None):
                self._poison = MULTIGEOM_ERR
            try:
                c = (geojson['coordinates'][0] if self._kind == 'Polygon'
                     else geojson['coordinates'][0][0] if self._kind == 'MultiPolygon'
                     else geojson['geometries'][0]['coordinates'][0])
                xs = [p[0] for p in c]
                ys = [p[1] for p in c]
                self._box = [min(xs), min(ys), max(xs), max(ys)]
            except Exception:
                pass

    @staticmethod
    def Rectangle(coords, proj=None, geodesic=None):
        c = [v._value if isinstance(v, Number) else v for v in coords]
        return Geometry(box=c)

    @staticmethod
    def MultiPolygon(coords, proj=None, geodesic=None, maxError=None, evenOdd=None):
        if (proj is not None or geodesic is not None) and not maxError:
            # the server tolerates raw coordinates without maxError, but the
            # exporter is expected to pass one; flag it loudly in tests
            raise EEException("MultiPolygon: test harness expects an explicit maxError "
                              "when proj/geodesic are requested")
        try:
            c = coords[0][0]
            xs = [p[0] for p in c]; ys = [p[1] for p in c]
            box = [min(xs), min(ys), max(xs), max(ys)]
        except Exception:
            box = None
        g = Geometry(box=box)
        g._kind = 'MultiPolygon'
        g._nparts = len(coords)
        return g

    def dissolve(self, *a):
        _poison_check(self)
        g = Geometry(box=self._box)
        g._kind = 'MultiPolygon' if self._kind == 'GeometryCollection' else self._kind
        g._dissolved = True
        return g

    @staticmethod
    def Point(*a, **k):
        return Geometry(box=[75.25, 15.35, 75.25, 15.35])

    def bounds(self, *a, **k):
        _poison_check(self)
        return Geometry(box=self._box)

    def coordinates(self):
        _poison_check(self)
        return List(_box_coords(self._box))

    def simplify(self, *a):
        _poison_check(self)
        return self

    def buffer(self, *a):
        _poison_check(self)
        return self

    def centroid(self, *a):
        _poison_check(self)
        cx = (self._box[0] + self._box[2]) / 2
        cy = (self._box[1] + self._box[3]) / 2
        return Geometry(box=[cx, cy, cx, cy])

    def intersection(self, other, *a):
        _poison_check(self)
        return self

    def area(self, *a):
        _poison_check(self)
        return Number(1e6)

    def getInfo(self):
        _poison_check(self)
        if getattr(self, '_dissolved', False) or self._kind == 'MultiPolygon':
            return {'type': 'MultiPolygon', 'coordinates': [_box_coords(self._box)]}
        if self._kind == 'GeometryCollection':
            b = self._box
            return {'type': 'GeometryCollection', 'geometries': [
                {'type': 'Polygon', 'coordinates': _box_coords(b), 'geodesic': True},
                {'type': 'Polygon', 'coordinates': _box_coords([b[0], b[1], (b[0]+b[2])/2, (b[1]+b[3])/2]), 'geodesic': True}]}
        return {'type': 'Polygon', 'coordinates': _box_coords(self._box)}


class Feature(ComputedObject):
    def __init__(self, geom=None, props=None):
        self._geom = geom if isinstance(geom, Geometry) else Geometry(box=ROI_BOX)
        self._props = dict(props or {})

    def geometry(self, *a):
        return self._geom

    def propertyNames(self):
        return List(list(self._props.keys()))

    def get(self, k):
        return self._props.get(k, 0)

    def set(self, d, v=None):
        if isinstance(d, dict):
            self._props.update(d)
        else:
            self._props[d] = v
        return self

    def getInfo(self):
        return {'type': 'Feature', 'properties': self._props,
                'geometry': self._geom.getInfo()}


class FeatureCollection(ComputedObject):
    def __init__(self, arg=None, *a):
        self._id = arg if isinstance(arg, str) else None
        if isinstance(arg, list):
            self._features = [f if isinstance(f, Feature) else Feature(f) for f in arg]
        elif isinstance(arg, FeatureCollection):
            self._features = list(arg._features)
        elif isinstance(arg, List) and isinstance(arg._value, list):
            self._features = [f if isinstance(f, Feature) else Feature(f) for f in arg._value]
        else:
            self._features = [Feature(Geometry(box=ROI_BOX),
                                      {'SubwshedID': 1, 'buff_km': 0, 'OBJECTID': 1})]

    def map(self, fn):
        out = FeatureCollection([fn(f) for f in self._features])
        out._id = self._id          # a mapped asset collection is still that asset
        return out

    def geometry(self, *a):
        g = Geometry(box=ROI_BOX)
        if ROI_KIND == 'collection' and self._id is not None:
            g._kind = 'GeometryCollection'
        return g

    def filterBounds(self, g):
        _poison_check(g)
        return self

    def filterDate(self, *a):
        return self

    def filter(self, *a):
        return self

    def select(self, *a):
        return self

    def limit(self, n):
        return self

    def size(self):
        return Number(len(self._features))

    def first(self):
        return self._features[0] if self._features else Feature()

    @staticmethod
    def randomPoints(region, points=100, seed=0, *a):
        _poison_check(region)
        return FeatureCollection([Feature(Geometry.Point(), {}) for _ in range(int(points))])

    def reduceToImage(self, props, reducer):
        return Image(bands=list(_as_list(props)))

    def reduceColumns(self, reducer, selectors):
        cols = _as_list(selectors)
        if reducer == 'toList':
            def _u(v):
                return v._value if isinstance(v, Number) else v
            rows = [[_u(f._props.get(c, 0)) for c in cols] for f in self._features]
            return _Info({'list': rows})
        if reducer == 'pearson':
            return _Info({'correlation': 0.5, 'p-value': 0.01})
        return _Info({})

    def getInfo(self):
        return {'type': 'FeatureCollection',
                'features': [f.getInfo() for f in self._features]}


class _Info(ComputedObject):
    def __init__(self, v):
        self._v = v

    def getInfo(self):
        return self._v


# ----------------------------------------------------------------------------
# Image (band tracking)
# ----------------------------------------------------------------------------
class Image(ComputedObject):
    def __init__(self, arg=None, bands=None):
        if isinstance(arg, Image):
            self.bands = list(arg.bands)
            self._masked = arg._masked
            return
        self._masked = False
        if bands is not None:
            self.bands = list(bands)
        elif isinstance(arg, str):
            if arg not in IMAGE_CATALOG:
                raise EEException(f"Image asset '{arg}' not found")
            self.bands = list(IMAGE_CATALOG[arg])
        elif isinstance(arg, (int, float, Number)):
            self.bands = ['constant']
        elif isinstance(arg, (list, tuple)):
            self.bands = [f'constant{"_" + str(i) if i else ""}' for i in range(len(arg))]
        elif arg is None:
            self.bands = ['constant']
        else:
            self.bands = ['constant']

    # ---- constructors
    @staticmethod
    def constant(v):
        if isinstance(v, (list, tuple)):
            return Image(bands=[f'constant{"_" + str(i) if i else ""}' for i in range(len(v))])
        return Image(bands=['constant'])

    @staticmethod
    def cat(*imgs):
        if len(imgs) == 1 and isinstance(imgs[0], (list, tuple)):
            imgs = imgs[0]
        bands = []
        for im in imgs:
            for b in im.bands:
                bands.append(_dedupe(bands, b))
        return Image(bands=bands)

    @staticmethod
    def pixelCoordinates(proj):
        return Image(bands=['x', 'y'])

    @staticmethod
    def pixelLonLat():
        return Image(bands=['longitude', 'latitude'])

    @staticmethod
    def pixelArea():
        return Image(bands=['area'])

    # ---- band ops
    def bandNames(self):
        return List(list(self.bands))

    def select(self, names, new_names=None):
        if isinstance(names, int):
            if names >= len(self.bands):
                raise EEException(f"Image.select: band index {names} out of range "
                                  f"({len(self.bands)} bands)")
            out = Image(bands=[self.bands[names]])
        else:
            req = _as_list(names)
            out_b = []
            for r in req:
                if isinstance(r, int):
                    if r >= len(self.bands):
                        raise EEException(f"Image.select: band index {r} out of range")
                    out_b.append(self.bands[r])
                    continue
                if r in self.bands:
                    out_b.append(r)
                    continue
                # regex pattern support (EE accepts patterns)
                try:
                    pat = _re.compile('^' + r + '$')
                    m = [b for b in self.bands if pat.match(b)]
                except Exception:
                    m = []
                if not m:
                    raise EEException(f"Image.select: Band pattern '{r}' did not match any "
                                      f"bands. Available bands: {self.bands}")
                out_b.extend(m)
            out = Image(bands=out_b)
        if new_names is not None:
            out.bands = list(_as_list(new_names))
        out._masked = self._masked
        return out

    def rename(self, names, *more):
        req = _as_list(names)
        if more:
            req = req + list(more)
        if len(self.bands) == 0:
            # A zero-band image only arises from an EMPTY collection reduce;
            # every such use in the exporter sits inside ee.Algorithms.If,
            # whose untaken branch is never evaluated server-side.
            return Image(bands=[])
        if len(req) != len(self.bands):
            raise EEException(f"Image.rename: The number of names ({len(req)}) must match "
                              f"the number of bands ({len(self.bands)}) {self.bands} -> {req}")
        out = Image(bands=req)
        out._masked = self._masked
        return out

    def addBands(self, other, names=None, overwrite=False):
        if isinstance(other, (list, tuple)):
            other = Image.cat(other)
        add = list(other.bands) if names is None else list(_as_list(names))
        for b in add:
            if b not in other.bands:
                raise EEException(f"Image.addBands: band '{b}' not in {other.bands}")
        bands = list(self.bands)
        for b in add:
            if b in bands:
                if not overwrite:
                    bands.append(_dedupe(bands, b))
            else:
                bands.append(b)
        out = Image(bands=bands)
        return out

    def _same(self):
        out = Image(bands=list(self.bands))
        out._masked = self._masked
        return out

    def _binary(self, other):
        # EE rule: if one image has no bands, the other must too.
        if isinstance(other, Image):
            if (len(self.bands) == 0) != (len(other.bands) == 0):
                raise EEException("Image.multiply: If one image has no bands, the other must "
                                  f"also have no bands. Got {len(self.bands)} and {len(other.bands)}.")
            if len(self.bands) > 1 and len(other.bands) > 1 and len(self.bands) != len(other.bands):
                # EE pairs bands by name / position; different counts is a graph error
                raise EEException(f"Image binary op: band count mismatch {self.bands} vs {other.bands}")
        return self._same()

    for _op in ('add', 'subtract', 'multiply', 'divide', 'max', 'min', 'pow', 'lt', 'gt',
                'lte', 'gte', 'eq', 'neq', 'And', 'Or', 'bitwiseAnd', 'rightShift',
                'leftShift', 'mod'):
        exec(f"def {_op}(self, other=None): return self._binary(other)")

    def where(self, test, value):
        return self._same()

    def updateMask(self, m):
        out = self._same()
        return out

    def mask(self, *a):
        return self._same()

    def unmask(self, *a):
        return self._same()

    def blend(self, other):
        return self._same()

    def clamp(self, lo, hi):
        return self._same()

    def abs(self): return self._same()
    def Not(self): return self._same()
    def sin(self): return self._same()
    def cos(self): return self._same()
    def tan(self): return self._same()
    def exp(self): return self._same()
    def log(self): return self._same()
    def sqrt(self): return self._same()
    def toFloat(self): return self._same()
    def toInt16(self): return self._same()
    def toInt32(self): return self._same()
    def toInt64(self): return self._same()
    def toInt(self): return self._same()
    def resample(self, *a): return self._same()
    def reproject(self, *a, **k): return self._same()
    def clip(self, *a): return self._same()
    def focal_mean(self, *a, **k): return self._same()

    def expression(self, expr, args=None):
        return Image(bands=['constant'])

    def reduce(self, reducer):
        # ee.Image.reduce() applies the reducer ACROSS bands -> one output band
        # named after the reducer (e.g. 'mean').
        if not self.bands:
            return Image(bands=[])
        return Image(bands=[str(reducer)])

    def toArray(self):
        return Image(bands=['array'])

    def arrayArgmax(self):
        return Image(bands=['array'])

    def arrayGet(self, i):
        return Image(bands=['array'])

    def set(self, *a, **k):
        return self._same()

    def get(self, k):
        return Number(0)

    def reduceRegion(self, reducer=None, geometry=None, scale=None, **k):
        _poison_check(geometry)
        return _Info({b: 0.5 for b in self.bands})

    def reduceRegions(self, collection=None, reducer=None, scale=None, **k):
        return collection

    def sampleRegions(self, collection=None, properties=None, scale=None, **k):
        n = len(collection._features) if collection is not None else 10
        return FeatureCollection([Feature(Geometry.Point(), {b: 0.3 + 0.001 * i * (j + 1)
                                                            for j, b in enumerate(self.bands)})
                                  for i in range(n)])

    def sample(self, region=None, scale=None, projection=None, **k):
        _poison_check(region)
        return FeatureCollection([Feature(Geometry(), {b: 0 for b in self.bands})])

    def getInfo(self):
        return {'type': 'Image', 'bands': [{'id': b} for b in self.bands]}


def _dedupe(existing, b):
    if b not in existing:
        return b
    i = 1
    while f'{b}_{i}' in existing:
        i += 1
    return f'{b}_{i}'


# ----------------------------------------------------------------------------
# ImageCollection
# ----------------------------------------------------------------------------
class ImageCollection(ComputedObject):
    def __init__(self, arg=None, bands=None, cid=None, start=None, end=None, n=None):
        self._cid = cid
        self._start, self._end = start, end
        self._n_override = n
        self._mapfns = []
        if isinstance(arg, ImageCollection):
            self.bands = list(arg.bands)
            self._cid, self._start, self._end = arg._cid, arg._start, arg._end
            self._n_override = arg._n_override
            self._mapfns = list(arg._mapfns)
            self._images = getattr(arg, '_images', None)
            return
        self._images = None
        if bands is not None:
            self.bands = list(bands)
        elif isinstance(arg, str):
            if arg not in CATALOG:
                raise EEException(f"ImageCollection asset '{arg}' not found")
            self._cid = arg
            self.bands = list(CATALOG[arg])
        elif isinstance(arg, (list, tuple)):
            imgs = [im if isinstance(im, Image) else Image(im) for im in arg]
            self._images = imgs
            self.bands = list(imgs[0].bands) if imgs else []
        elif isinstance(arg, List):
            imgs = [im for im in (arg._value or []) if isinstance(im, Image)]
            self._images = imgs
            self.bands = list(imgs[0].bands) if imgs else []
        elif isinstance(arg, Image):
            self._images = [arg]
            self.bands = list(arg.bands)
        else:
            self.bands = []

    @staticmethod
    def fromImages(imgs):
        return ImageCollection(imgs)

    def _copy(self, bands=None):
        out = ImageCollection(self)
        if bands is not None:
            out.bands = list(bands)
        return out

    # ---- the "size" semantic: does this collection have data in [start,end)?
    def _count(self):
        if self._n_override is not None:
            return self._n_override
        if self._images is not None:
            return len(self._images)
        if self._cid is None:
            return 1
        if self._start is None:
            return 1000
        end = data_end(self._cid)
        s, e = self._start, self._end
        if e <= s:
            return 0
        if s > end:
            return 0
        got = (min(e, end + _dt.timedelta(days=1)) - s).days
        return max(0, int(got / 5))       # roughly one image / 5 days

    def size(self):
        return Number(self._count())

    def filterDate(self, a, b=None):
        out = self._copy()
        a = _parse_date(a)
        b = _parse_date(b) if b is not None else a + _dt.timedelta(days=1)
        out._start, out._end = a, b
        return out

    def filterBounds(self, g):
        _poison_check(g)
        return self._copy()

    def filter(self, f):
        return self._copy()

    def limit(self, n):
        out = self._copy()
        if out._count() > n:
            out._n_override = n
        return out

    def select(self, names, new_names=None):
        probe = Image(bands=self.bands).select(names, new_names)
        return self._copy(probe.bands)

    def map(self, fn):
        # Apply fn to a representative image to derive the output band list.
        probe = fn(Image(bands=self.bands))
        out = self._copy(probe.bands)
        if self._images is not None:
            out._images = [fn(im) for im in self._images]
        return out

    def merge(self, other):
        out = self._copy()
        if other._count() > out._count():
            out._n_override = other._count()
        return out

    def linkCollection(self, other, bands, *a, **k):
        return self._copy(self.bands + [b for b in _as_list(bands) if b not in self.bands])

    def first(self):
        return Image(bands=self.bands)

    def mosaic(self):
        return Image(bands=self.bands)

    def _reduced(self):
        if self._count() == 0:
            return Image(bands=[])            # EE: empty collection -> zero bands
        return Image(bands=self.bands)

    def mean(self): return self._reduced()
    def sum(self): return self._reduced()
    def min(self): return self._reduced()
    def max(self): return self._reduced()
    def median(self): return self._reduced()
    def count(self): return self._reduced()
    def mode(self): return self._reduced()

    def reduce(self, reducer):
        if self._count() == 0:
            return Image(bands=[])
        return Image(bands=[f'{b}_{reducer}' for b in self.bands])

    def aggregate_max(self, prop):
        end = data_end(self._cid) if self._cid else today()
        return Number(int(_dt.datetime(end.year, end.month, end.day,
                                       tzinfo=_dt.timezone.utc).timestamp() * 1000))

    def aggregate_min(self, prop):
        return Number(0)

    def toList(self, n):
        return List([Image(bands=self.bands) for _ in range(min(n, self._count()))])

    def toBands(self):
        return Image(bands=self.bands)

    def getInfo(self):
        return {'type': 'ImageCollection', 'bands': self.bands}


class Terrain:
    @staticmethod
    def slope(img):
        return Image(bands=['slope'])

    @staticmethod
    def aspect(img):
        return Image(bands=['aspect'])


class Algorithms:
    @staticmethod
    def If(cond, a, b):
        # Evaluate client-side when we can (Number conditions), else assume
        # the "true" branch (non-empty collection) -- but ALSO type-check the
        # false branch so a zero-band placeholder is exercised.
        c = cond._value if isinstance(cond, Number) else 1
        return a if c else b


# ----------------------------------------------------------------------------
# batch / data
# ----------------------------------------------------------------------------
class _Task:
    _n = 0

    def __init__(self, **kw):
        _Task._n += 1
        self.id = f"MOCKTASK{_Task._n:05d}"
        self.config = kw
        self.started = False

    def start(self):
        self.started = True
        STARTED_TASKS.append(self)

    def status(self):
        return {'state': 'COMPLETED'}


STARTED_TASKS = []


class batch:
    class Export:
        class table:
            @staticmethod
            def toDrive(collection=None, description='', folder='', fileNamePrefix='',
                        fileFormat='CSV', selectors=None, **kw):
                if selectors is not None:
                    have = collection._features[0]._props.keys() if collection._features else []
                    missing = [s for s in selectors if s not in have]
                    if missing:
                        raise EEException(f"Export selectors not in table: {missing}")
                return _Task(description=description, folder=folder,
                             fileNamePrefix=fileNamePrefix, selectors=selectors)

        class image:
            @staticmethod
            def toDrive(**kw):
                return _Task(**kw)


OPERATIONS = []      # test-controllable: what ee.data.listOperations() returns


class data:
    @staticmethod
    def listOperations(*a, **k):
        return list(OPERATIONS)

    @staticmethod
    def getTaskList(*a, **k):
        return []

    @staticmethod
    def cancelOperation(name):
        return None

    @staticmethod
    def cancelTask(tid):
        return None


def Initialize(*a, **k):
    return None


def Authenticate(*a, **k):
    return None
