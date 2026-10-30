"""Rasterise a stylised map texture (land cover, land use, water, roads, rail) aligned with ctx_terrain UVs.

Image row 0 = north edge (N1), column 0 = west edge (E0)  -> glTF UV convention, flipY = false in three.js.
Outputs public/textures/ground.webp (6144 px wide) and ground_2k.webp."""
import time
import numpy as np
import pyarrow.parquet as pq
import shapely
from PIL import Image, ImageDraw, ImageFilter

import geo

t0 = time.time()
E0, N0, E1, N1 = geo.local_extent()
W = 6144
H = int(round(W * (N1 - N0) / (E1 - E0)))
SS = 2  # supersampling
w, h = W * SS, H * SS
sx = w / (E1 - E0); sy = h / (N1 - N0)
px_m = (E1 - E0) / W
print(f"texture {W}x{H}, {px_m:.2f} m/px")

BASE = (234, 231, 225)
img = Image.new("RGB", (w, h), BASE)
dr = ImageDraw.Draw(img)


def to_loc(xy):
    e, n = geo._ll2loc.transform(xy[:, 0], xy[:, 1])
    return np.column_stack([e, n])


def load(name, cols):
    t = pq.read_table(geo.DATA / f"overture_{name}.parquet", columns=cols)
    g = shapely.transform(shapely.from_wkb(t.column("geometry").to_numpy(zero_copy_only=False)), to_loc)
    return g, t


def pix(coords):
    c = np.asarray(coords)
    return list(zip(((c[:, 0] - E0) * sx).tolist(), ((N1 - c[:, 1]) * sy).tolist()))


def fill_poly(g, color):
    if g is None or g.is_empty:
        return
    if g.geom_type == "MultiPolygon" or g.geom_type == "GeometryCollection":
        for p in g.geoms:
            fill_poly(p, color)
        return
    if g.geom_type != "Polygon":
        return
    ext = pix(g.exterior.coords)
    if not g.interiors:
        dr.polygon(ext, fill=color)
        return
    # polygon with holes: rasterise a cropped mask so holes keep whatever is underneath
    xs = [p[0] for p in ext]; ys = [p[1] for p in ext]
    x0, y0 = max(0, int(min(xs)) - 1), max(0, int(min(ys)) - 1)
    x1, y1 = min(w, int(max(xs)) + 2), min(h, int(max(ys)) + 2)
    if x1 <= x0 or y1 <= y0:
        return
    m = Image.new("L", (x1 - x0, y1 - y0), 0)
    md = ImageDraw.Draw(m)
    md.polygon([(x - x0, y - y0) for x, y in ext], fill=255)
    for hole in g.interiors:
        md.polygon([(x - x0, y - y0) for x, y in pix(hole.coords)], fill=0)
    img.paste(color, (x0, y0, x1, y1), m)


def line(g, color, width_m):
    if g is None or g.is_empty:
        return
    if g.geom_type.startswith("Multi"):
        for p in g.geoms:
            line(p, color, width_m)
        return
    if g.geom_type != "LineString":
        return
    wpx = max(1, int(round(width_m * sx)))
    pts = pix(g.coords)
    dr.line(pts, fill=color, width=wpx, joint="curve")
    if wpx >= 4:
        r = wpx / 2
        for x, y in (pts[0], pts[-1]):
            dr.ellipse([x - r, y - r, x + r, y + r], fill=color)


# --- natural land cover (coarse) ---
LC = {"forest": (198, 212, 184), "shrub": (213, 222, 198), "grass": (222, 228, 208), "crop": (226, 226, 206),
      "barren": (230, 224, 212), "wetland": (210, 222, 214)}
g, t = load("land_cover", ["geometry", "subtype"])
for gg, st in zip(g, t.column("subtype").to_pylist()):
    if st in LC:
        fill_poly(gg, LC[st])

# --- land (OSM natural) ---
LAND = {"wood": (196, 211, 182), "forest": (196, 211, 182), "grassland": (220, 228, 205), "scrub": (210, 220, 196),
        "heath": (214, 221, 199), "shrub": (210, 220, 196), "bare_rock": (226, 221, 211), "scree": (226, 221, 211),
        "sand": (232, 226, 210), "wetland": (208, 221, 212)}
g, t = load("land", ["geometry", "class"])
for gg, cl in zip(g, t.column("class").to_pylist()):
    if cl in LAND and gg is not None and gg.geom_type in ("Polygon", "MultiPolygon"):
        fill_poly(gg, LAND[cl])

# --- land use ---
LU = {"park": (205, 221, 192), "dog_park": (208, 222, 196), "grass": (212, 225, 198), "garden": (208, 222, 194),
      "flowerbed": (208, 222, 194), "recreation_ground": (210, 223, 197), "pitch": (200, 218, 190),
      "playground": (214, 223, 203), "golf": (205, 221, 192), "green": (205, 221, 192), "cemetery": (214, 221, 204),
      "grave_yard": (214, 221, 204), "allotments": (218, 224, 204), "orchard": (214, 222, 198),
      "vineyard": (216, 222, 200), "meadow": (220, 228, 205), "farmland": (226, 226, 206),
      "pedestrian": (238, 235, 230), "plaza": (238, 235, 230), "stadium": (214, 223, 203),
      "university": (230, 228, 222), "school": (230, 228, 222), "hospital": (233, 228, 225)}
g, t = load("land_use", ["geometry", "class"])
order = sorted(range(len(g)), key=lambda i: -(g[i].area if g[i] is not None else 0))
cls = t.column("class").to_pylist()
for i in order:
    if cls[i] in LU and g[i] is not None and g[i].geom_type in ("Polygon", "MultiPolygon"):
        fill_poly(g[i], LU[cls[i]])

# --- water ---
WATER = (166, 194, 206)
g, t = load("water", ["geometry", "class", "subtype"])
for gg, cl in zip(g, t.column("class").to_pylist()):
    if gg is None:
        continue
    if gg.geom_type in ("Polygon", "MultiPolygon"):
        fill_poly(gg, WATER)
    elif gg.geom_type in ("LineString", "MultiLineString"):
        line(gg, WATER, {"river": 30, "canal": 6, "stream": 3, "drain": 2, "ditch": 1.5}.get(cl, 2))

# --- roads (width by class, drawn minor -> major) ---
RW = {"motorway": (22, (200, 196, 189)), "trunk": (22, (203, 199, 192)), "primary": (18, (206, 202, 195)),
      "secondary": (14, (209, 205, 198)), "tertiary": (11, (212, 208, 201)), "unclassified": (8, (215, 211, 205)),
      "residential": (7, (216, 212, 206)), "living_street": (6, (218, 214, 208)), "service": (4.5, (220, 216, 210)),
      "pedestrian": (6, (241, 238, 233)), "track": (3, (222, 218, 210))}
RANK = ["track", "pedestrian", "service", "living_street", "residential", "unclassified", "tertiary", "secondary",
        "primary", "trunk", "motorway"]
g, t = load("segment", ["geometry", "subtype", "class"])
sub = t.column("subtype").to_pylist(); rcls = t.column("class").to_pylist()
for cl in RANK:
    wd, col = RW[cl]
    for gg, st, c in zip(g, sub, rcls):
        if st == "road" and c == cl:
            line(gg, col, wd)
for gg, st, c in zip(g, sub, rcls):
    if st == "rail":
        line(gg, (190, 185, 178), 2.5 if c != "subway" else 0)  # subway is underground: skip

# --- the plot itself: soft neutral pad so the hero site reads cleanly ---
fill_poly(shapely.Polygon(geo.PLOT_LOC), (226, 223, 217))

img = img.resize((W, H), Image.LANCZOS)
# subtle paper grain for a less digital look
rng = np.random.default_rng(7)
arr = np.asarray(img).astype(np.int16)
arr += rng.integers(-3, 4, size=arr.shape[:2], dtype=np.int16)[..., None]
img = Image.fromarray(arr.clip(0, 255).astype(np.uint8))
out = geo.ROOT / "public" / "textures"
out.mkdir(parents=True, exist_ok=True)
img.save(out / "ground.webp", quality=82, method=6)
img.resize((2048, int(round(2048 * H / W))), Image.LANCZOS).save(out / "ground_2k.webp", quality=85, method=6)
print("saved", (out / "ground.webp").stat().st_size / 1e6, "MB", f"{time.time()-t0:.0f}s")
