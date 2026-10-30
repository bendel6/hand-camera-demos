"""Real building footprints (site frame) around the modelled streetscape, used by blender/build_site.py to keep
lawns, trees and paths out of existing buildings. Output: data/near-footprints.json"""
import json, math
import pyarrow.parquet as pq
import shapely
from shapely.geometry import box, mapping
import geo

t = pq.read_table(geo.DATA / "overture_building.parquet", columns=["geometry", "num_floors"])
geoms = shapely.from_wkb(t.column("geometry").to_numpy(zero_copy_only=False))
a = math.radians(90 - geo.FRAME["x_axis_azimuth_true_deg"])
c, s = math.cos(a), math.sin(a)


def to_site(coords):
    out = []
    for lon, lat in coords:
        e, n = geo.ll2loc(lon, lat)
        out.append((e * c + n * s, -e * s + n * c))
    return out


region = box(-200, -90, 290, 90)
plot = shapely.geometry.Polygon(geo.PLOT_SITE)
feats = []
for g, nf in zip(geoms, t.column("num_floors").to_pylist()):
    if g is None or abs(g.centroid.x - 44.758) > 0.008 or abs(g.centroid.y - 41.7255) > 0.005:
        continue
    polys = getattr(g, "geoms", [g])
    for p in polys:
        sp = shapely.geometry.Polygon(to_site(p.exterior.coords))
        if sp.intersects(region) and not plot.contains(sp.centroid):
            feats.append({"floors": nf, "poly": [list(map(lambda v: round(v, 2), xy)) for xy in sp.exterior.coords]})
json.dump(feats, open(geo.DATA / "near-footprints.json", "w"))
print(len(feats), "footprints")
