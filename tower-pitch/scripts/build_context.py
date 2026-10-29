"""Build the stylised white-model city context from Overture Maps + AWS terrain tiles.

Outputs
  public/models/context.glb   nodes: context > ctx_terrain, ctx_near, ctx_bld_<i>_<j>
  data/context-meta.json      extents, site elevation, texture convention, stats
  data/trees-near.json        street/park tree positions near the site (three.js coords)

Run: /opt/venvs/blender/bin/python scripts/build_context.py"""
import hashlib, json, math, time
import numpy as np
import pyarrow.parquet as pq
import shapely
from shapely.geometry import Polygon, Point
from shapely.geometry.polygon import orient
from scipy.interpolate import RegularGridInterpolator
import mapbox_earcut as earcut

import geo
from glb import GLB

t0 = time.time()
E0, N0, E1, N1 = geo.local_extent()
SC = np.array(geo.SITE_CENTRE_LOC)
dem = geo.DEM()
H0 = float(dem.sample_loc(*SC)[0])
PLOT = Polygon(geo.PLOT_LOC)


def hash01(s, salt=""):
    return int(hashlib.md5((salt + s).encode()).hexdigest()[:8], 16) / 2 ** 32


# ---------------------------------------------------------------- terrain
def graded_axis(a, b, c, fine=12.0, coarse=60.0, r0=500.0, r1=3000.0):
    def step(d):
        return fine if d < r0 else min(coarse, fine + (d - r0) * (coarse - fine) / (r1 - r0))
    pts = [c]
    t = c
    while t < b:
        t += step(t - c); pts.append(t)
    t = c
    while t > a:
        t -= step(c - t); pts.append(t)
    pts = np.array(sorted(p for p in pts if a < p < b))
    pts = pts[(pts - a > 4) & (b - pts > 4)]
    return np.concatenate([[a], pts, [b]])


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


ge = graded_axis(E0, E1, SC[0])
gn = graded_axis(N0, N1, SC[1])
EE, NN = np.meshgrid(ge, gn)  # rows = north index
raw = dem.sample_loc(EE.ravel(), NN.ravel()).reshape(EE.shape) - H0
r = np.hypot(EE - SC[0], NN - SC[1])
HT = raw * smoothstep(120.0, 280.0, r)
terrain_h = RegularGridInterpolator((gn, ge), HT, bounds_error=False, fill_value=None)


def th(e, n):
    return terrain_h(np.column_stack([np.atleast_1d(n), np.atleast_1d(e)]))


ny, nx = HT.shape
tpos = np.column_stack([EE.ravel(), HT.ravel(), -NN.ravel()])
# normals from central differences on the graded grid
dhde = np.gradient(HT, ge, axis=1)
dhdn = np.gradient(HT, gn, axis=0)
nrm = np.column_stack([-dhde.ravel(), np.ones(HT.size), dhdn.ravel()])  # three: z = -N so dz component flips
nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
tuv = np.column_stack([(EE.ravel() - E0) / (E1 - E0), (N1 - NN.ravel()) / (N1 - N0)])
ii = np.arange(ny * nx).reshape(ny, nx)
a = ii[:-1, :-1].ravel(); b = ii[:-1, 1:].ravel(); c = ii[1:, 1:].ravel(); d = ii[1:, :-1].ravel()
# row index grows with north; in three coords north = -z. Triangle (a,b,c): a=(e,n) b=(e+,n) c=(e+,n+)
tidx = np.concatenate([np.column_stack([a, c, b]), np.column_stack([a, d, c])])
# verify winding faces up
p = tpos
cr = np.cross(p[tidx[:, 1]] - p[tidx[:, 0]], p[tidx[:, 2]] - p[tidx[:, 0]])
if (cr[:, 1] < 0).mean() > 0.5:
    tidx = tidx[:, [0, 2, 1]]
print(f"terrain grid {nx}x{ny} = {len(tidx)} tris, h range {HT.min():.1f}..{HT.max():.1f}")

# ---------------------------------------------------------------- buildings
tb = pq.read_table(geo.DATA / "overture_building.parquet",
                   columns=["id", "geometry", "height", "num_floors", "is_underground", "class", "subtype"])
ids = tb.column("id").to_pylist()
geoms = shapely.from_wkb(tb.column("geometry").to_numpy(zero_copy_only=False))
heights = tb.column("height").to_pylist()
floors = tb.column("num_floors").to_pylist()
underground = tb.column("is_underground").to_pylist()
classes = tb.column("class").to_pylist()


def to_loc(xy):
    e, n = geo._ll2loc.transform(xy[:, 0], xy[:, 1])
    return np.column_stack([e, n])


geoms = shapely.transform(geoms, to_loc)
cent = shapely.centroid(geoms)
cx = shapely.get_x(cent); cy = shapely.get_y(cent)
dist = np.hypot(cx - SC[0], cy - SC[1])
inside_ext = (cx > E0 + 20) & (cx < E1 - 20) & (cy > N0 + 20) & (cy < N1 - 20)
on_plot = shapely.contains_xy(PLOT, cx, cy)


def est_height(i, area):
    h = heights[i]
    if h is not None and 2.0 <= h <= 320:
        return float(h)
    f = floors[i]
    if f is not None and 0 < f < 80:
        return f * 3.1 + 0.6
    u = hash01(ids[i])
    if area < 150:
        fl = 2 + int(u * 2)
    elif area < 600:
        fl = 4 + int(u * 3)
    elif area < 1500:
        fl = 5 + int(u * 5)
    else:
        fl = 9 + int(u * 6)
    return fl * 3.1 + 0.6


def simplify_for(dd, poly):
    if dd < 400:
        return poly.simplify(0.4)
    if dd < 2000:
        return poly.simplify(1.0)
    if dd < 4000:
        return poly.simplify(1.8)
    if poly.area < 2500:
        return poly.minimum_rotated_rectangle
    return poly.simplify(3.0)


def min_area(dd):
    return 25 if dd < 2000 else (45 if dd < 5000 else 80)


chunks = {}
stats = {"skipped_plot": 0, "skipped_small": 0, "skipped_other": 0, "kept": 0}
for i, g in enumerate(geoms):
    if underground[i] or not inside_ext[i] or g is None or g.is_empty:
        stats["skipped_other"] += 1; continue
    if on_plot[i]:
        stats["skipped_plot"] += 1; continue
    if classes[i] in ("roof",):
        stats["skipped_other"] += 1; continue
    dd = dist[i]
    polys = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
    area_total = sum(pp.area for pp in polys)
    hgt = est_height(i, area_total)
    near = dd < 400
    key = "ctx_near" if near else f"ctx_bld_{int((cx[i] - E0) // 1000)}_{int((cy[i] - N0) // 1000)}"
    tint = 0.94 + 0.06 * hash01(ids[i], "t")
    warm = np.array([244, 241, 235]) * tint
    for pp in polys:
        if pp.area < min_area(dd):
            stats["skipped_small"] += 1; continue
        pp = simplify_for(dd, pp)
        if pp.is_empty or pp.geom_type != "Polygon" or pp.area < min_area(dd):
            stats["skipped_small"] += 1; continue
        pp = orient(pp, 1.0)
        rings = [np.asarray(pp.exterior.coords)[:-1]] + [np.asarray(h.coords)[:-1] for h in pp.interiors if Polygon(h).area > 30]
        rings = [rg for rg in rings if len(rg) >= 3]
        allxy = np.vstack(rings)
        ground = th(allxy[:, 0], allxy[:, 1])
        base = float(ground.min()) - 3.0
        top = float(th(cx[i], cy[i])[0]) + hgt
        if top - base < 3.5:
            top = base + 3.5
        ch = chunks.setdefault(key, {"pos": [], "col": [], "idx": [], "n": 0, "count": 0})
        off = ch["n"]
        verts_top, verts_bot = [], []
        ring_starts = []
        k = 0
        for rg in rings:
            ring_starts.append(k); k += len(rg)
        nv = len(allxy)
        # vertices: [top ring verts..., bottom ring verts...]
        pos = np.empty((2 * nv, 3))
        pos[:nv, 0] = allxy[:, 0]; pos[:nv, 1] = top; pos[:nv, 2] = -allxy[:, 1]
        pos[nv:, 0] = allxy[:, 0]; pos[nv:, 1] = base; pos[nv:, 2] = -allxy[:, 1]
        col = np.empty((2 * nv, 4))
        col[:nv, :3] = warm; col[nv:, :3] = warm * 0.70; col[:, 3] = 255
        tris = []
        for s, rg in zip(ring_starts, rings):
            m = len(rg)
            for j in range(m):
                t_a = nv + s + j; t_b = nv + s + (j + 1) % m
                t_c = s + (j + 1) % m; t_d = s + j
                tris.append((t_a, t_b, t_c)); tris.append((t_a, t_c, t_d))
        ends = np.cumsum([len(rg) for rg in rings]).astype(np.uint32)
        rt = earcut.triangulate_float64(allxy, ends).reshape(-1, 3)
        for t in rt:
            pa, pb, pc_ = allxy[t[0]], allxy[t[1]], allxy[t[2]]
            sa = (pb[0] - pa[0]) * (pc_[1] - pa[1]) - (pb[1] - pa[1]) * (pc_[0] - pa[0])
            tris.append((t[0], t[1], t[2]) if sa > 0 else (t[0], t[2], t[1]))
        ch["pos"].append(pos); ch["col"].append(col)
        ch["idx"].append(np.asarray(tris, np.int64) + off)
        ch["n"] += 2 * nv; ch["count"] += 1
        stats["kept"] += 1

# ---------------------------------------------------------------- write GLB
out = GLB()
mat_ground = out.material("ctx_ground", (1, 1, 1, 1), roughness=1.0)
mat_bld = out.material("ctx_building", (1, 1, 1, 1), roughness=0.85)
root = out.add_group("context", extras={"generator": "build_context.py", "units": "m",
                                        "frame": "local tmerc at SW plot corner; x=E, y=up, z=-N; y=0 at site ground"})
out.add_mesh_node("ctx_terrain", tpos, tidx, mat_ground, normals=nrm, uvs=tuv, parent=root)
tri_total = len(tidx)
chunk_stats = {}
for key in sorted(chunks, key=lambda k: (k != "ctx_near", k)):
    ch = chunks[key]
    pos = np.vstack(ch["pos"]); col = np.vstack(ch["col"]).round().clip(0, 255)
    idx = np.vstack(ch["idx"])
    out.add_mesh_node(key, pos, idx, mat_bld, colors=col, parent=root, extras={"buildings": ch["count"]})
    tri_total += len(idx)
    chunk_stats[key] = {"buildings": ch["count"], "tris": int(len(idx))}
size = out.save(geo.ROOT / "blender" / "out" / "context_raw.glb")
print(f"context.glb {size/1e6:.1f} MB, tris {tri_total}, chunks {len(chunks)}, stats {stats}")

# ---------------------------------------------------------------- trees near the site
tl = pq.read_table(geo.DATA / "overture_land.parquet", columns=["geometry", "subtype", "class"])
lgeo = shapely.transform(shapely.from_wkb(tl.column("geometry").to_numpy(zero_copy_only=False)), to_loc)
lcls = tl.column("class").to_pylist()
near_poly = Point(SC).buffer(700)
bld_near = shapely.STRtree([gg for gg, dd in zip(geoms, dist) if dd < 900 and gg is not None])
trees = []
rng = np.random.default_rng(23)
for gg, cl in zip(lgeo, lcls):
    if gg is None or not gg.intersects(near_poly):
        continue
    pts = []
    if cl == "tree" and gg.geom_type == "Point":
        pts = [(gg.x, gg.y)]
    elif cl == "tree_row":
        L = gg.length
        pts = [gg.interpolate(s).coords[0] for s in np.arange(0, L, 8.0)]
    elif cl in ("wood", "forest") and gg.geom_type in ("Polygon", "MultiPolygon"):
        cl_ = gg.intersection(near_poly)
        n = int(cl_.area / 70)
        if n:
            mnx, mny, mxx, mxy = cl_.bounds
            cand = np.column_stack([rng.uniform(mnx, mxx, n * 3), rng.uniform(mny, mxy, n * 3)])
            inside = shapely.contains_xy(cl_, cand[:, 0], cand[:, 1])
            pts = [tuple(p) for p in cand[inside][:n]]
    for (e, n_) in pts:
        if not near_poly.contains(Point(e, n_)) or PLOT.buffer(2).contains(Point(e, n_)):
            continue
        if len(bld_near.query(Point(e, n_), predicate="intersects")):
            continue
        trees.append([round(e, 2), round(float(th(e, n_)[0]), 2), round(-n_, 2), round(0.8 + 0.5 * rng.random(), 2)])
(geo.DATA / "trees-near.json").write_text(json.dumps({"note": "three.js coords [x, groundY, z, scale]; from Overture land (tree, tree_row, wood/forest scatter) within 700 m",
                                                    "trees": trees}))
print("trees near", len(trees))

meta = {"extent_local": {"E0": E0, "N0": N0, "E1": E1, "N1": N1},
        "extent_three": {"xmin": E0, "xmax": E1, "zmin": -N1, "zmax": -N0},
        "site_elevation_m_asl": round(H0, 2),
        "site_centre_three": [round(SC[0], 2), 0, round(-SC[1], 2)],
        "plot_three": [[round(e, 2), round(-n, 2)] for e, n in geo.PLOT_LOC],
        "flatten_radius_m": [120, 280],
        "ground_texture": "public/textures/ground.webp; terrain UVs use glTF convention (v=0 = north edge = top row): set texture.flipY = false",
        "building_material": "ctx_building uses COLOR_0 (warm white, darker at base) and no normals -> GLTFLoader enables flatShading",
        "chunks": chunk_stats, "triangles_total": tri_total, "buildings": stats,
        "dem": {"source": "AWS Terrain Tiles (terrarium z14)", "filled_nodata_px": dem.nbad}}
(geo.DATA / "context-meta.json").write_text(json.dumps(meta, indent=1))
print(f"done in {time.time()-t0:.0f}s")
