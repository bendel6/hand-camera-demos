"""Shared geo helpers: site frame, local ENU projection, DEM sampling, extents.

Local frame: transverse Mercator centred on the SW plot corner (data/site-frame.json).
E = east metres, N = north metres. three.js: x = E, y = up, z = -N.
Elevation 0 = terrain height at the site centre."""
import json, math, pathlib
import numpy as np
from pyproj import Transformer
from scipy import ndimage

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

FRAME = json.loads((DATA / "site-frame.json").read_text())
LOCAL_PROJ = (f"+proj=tmerc +lat_0={FRAME['origin_lat']} +lon_0={FRAME['origin_lng']} "
              "+k=1 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs")
_ll2loc = Transformer.from_crs("EPSG:4326", LOCAL_PROJ, always_xy=True)
_loc2ll = Transformer.from_crs(LOCAL_PROJ, "EPSG:4326", always_xy=True)
_utm2ll = Transformer.from_crs("EPSG:32638", "EPSG:4326", always_xy=True)

BBOX_LL = (44.70, 41.67, 44.86, 41.775)

PLOT_SITE = [(0.0, 0.0), (79.4, 0.0), (81.3, 64.2), (0.5, 66.7)]


def ll2loc(lon, lat):
    return _ll2loc.transform(lon, lat)


def loc2ll(e, n):
    return _loc2ll.transform(e, n)


def site2utm(x, y):
    a = math.radians(FRAME["street_angle_grid_deg"])
    e0, n0 = FRAME["origin_utm38n"]
    return e0 + x * math.cos(a) - y * math.sin(a), n0 + x * math.sin(a) + y * math.cos(a)


def site2loc(x, y):
    lon, lat = _utm2ll.transform(*site2utm(x, y))
    return ll2loc(lon, lat)


PLOT_LOC = [site2loc(x, y) for x, y in PLOT_SITE]
SITE_CENTRE_LOC = ll2loc(FRAME["centre_lng"], FRAME["centre_lat"])
ENTRANCE_LOC = site2loc(40.0, -2.0)


def local_extent():
    """Axis-aligned local rectangle fully inside the lon/lat bbox (E0, N0, E1, N1)."""
    x0, y0, x1, y1 = BBOX_LL
    c = [ll2loc(x, y) for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]
    e0 = max(c[0][0], c[3][0]); e1 = min(c[1][0], c[2][0])
    n0 = max(c[0][1], c[1][1]); n1 = min(c[2][1], c[3][1])
    return (math.ceil(e0), math.ceil(n0), math.floor(e1), math.floor(n1))


class DEM:
    """Terrarium z14 grid (WebMercator), cleaned, bilinear sampling in lon/lat."""

    def __init__(self):
        d = np.load(DATA / "terrain_z14.npz")
        h = d["h"].astype(np.float64)
        self.z = int(d["z"]); self.tx0 = int(d["tx0"]); self.ty0 = int(d["ty0"])
        bad = (h < 0) | (h > 2000)
        if bad.any():
            idx = ndimage.distance_transform_edt(bad, return_distances=False, return_indices=True)
            h = h[tuple(idx)]
        # spike removal: compare with a 5x5 median
        m = ndimage.median_filter(h, size=5, mode="nearest")
        spikes = np.abs(h - m) > 40
        h[spikes] = m[spikes]
        self.h = h
        self.nbad = int(bad.sum()); self.nspikes = int(spikes.sum())

    def _px(self, lon, lat):
        n = 2 ** self.z
        x = (np.asarray(lon) + 180) / 360 * n
        y = (1 - np.arcsinh(np.tan(np.radians(np.asarray(lat)))) / math.pi) / 2 * n
        return (x - self.tx0) * 256 - 0.5, (y - self.ty0) * 256 - 0.5

    def sample_ll(self, lon, lat):
        px, py = self._px(lon, lat)
        return ndimage.map_coordinates(self.h, [np.atleast_1d(py), np.atleast_1d(px)], order=1, mode="nearest")

    def sample_loc(self, e, n):
        lon, lat = _loc2ll.transform(np.asarray(e, dtype=float), np.asarray(n, dtype=float))
        return self.sample_ll(lon, lat)
