"""Site + Kazbegi Avenue streetscape -> public/models/site.glb + src/content/site-layout.json.

Static surfaces (roads, curbs, paving, lawns, playground, street furniture) go into the GLB. Trees, people and cars
are written as instance data (site frame) for the web app, which instances props.glb with wind/walk shaders.
Kazbegi Ave: one-way eastbound primary (Overture), centreline ~14.9 m south of the plot frontage, ~15 m wide.
"""
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import lib  # noqa: E402
import props  # noqa: E402
from build_building import PLOT, PODIUM, TOWER_A, enu_root, triangulate  # noqa: E402
from lib import MeshAccum, mat  # noqa: E402

X0, X1 = -170.0, 260.0           # modelled stretch of the avenue (site frame x)
SW_N = (-6.4, 0.0)               # north sidewalk (site side)
ROAD = (-21.4, -6.4)             # carriageway, 4 lanes eastbound
SW_S = (-25.4, -21.4)            # south sidewalk
GREEN_S = (-58.0, -25.4)         # tree-lined strip across the avenue
LANES = [-6.4 - 1.9 - 3.4 * k for k in range(4)]
ACCESS_W = (0.0, 5.7)            # west access road x-range (site plan)
ACCESS_N = (58.1, 64.2)          # north leg y-range
ACCESS_E = (43.7, 49.0)          # east leg x-range (to the ramp portal at the podium face)
PLAY = (61.9, 25.1, 6.8)
_FP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "near-footprints.json")
FOOTPRINTS = unary_union([Polygon(f["poly"]).buffer(0) for f in json.load(open(_FP))]) if os.path.exists(_FP) else None


def materials():
    return {
        "asphalt": mat("M_Asphalt", "#3a3b3d", rough=0.85, tex="asphalt_albedo.jpg", normal="asphalt_normal.png",
                       rough_tex="asphalt_rough.jpg", tex_scale=6.0, normal_strength=0.6),
        "sidewalk": mat("M_Sidewalk", "#8c8984", rough=0.75, tex="sidewalk_albedo.jpg", normal="sidewalk_normal.png",
                        rough_tex="sidewalk_rough.jpg", tex_scale=2.4),
        "paving": mat("M_Paving", "#b9b4aa", rough=0.75, tex="paving_albedo.jpg", normal="paving_normal.png",
                      rough_tex="paving_rough.jpg", tex_scale=3.0),
        "flag": mat("M_Flagstone", "#ddd8cf", rough=0.7, tex="flagstone_albedo.jpg", normal="flagstone_normal.png",
                    tex_scale=6.0),
        "grass": mat("M_Grass", "#5e7d38", rough=0.9, tex="grass_albedo.jpg", normal="grass_normal.png", tex_scale=5.0),
        "rubber": mat("M_Rubber", "#a44c39", rough=0.9, tex="rubber_albedo.jpg", tex_scale=3.0),
        "curb": mat("M_Curb", "#a9a59d", rough=0.8, tex="concrete_albedo.jpg", tex_scale=3.0),
        "marking": mat("M_RoadMarking", "#efeee8", rough=0.6),
        "marking_y": mat("M_RoadMarkingYellow", "#e6b532", rough=0.6),
        "play": mat("M_PlayFrame", "#e7e2d6", metal=0.1, rough=0.5),
        "play_acc": mat("M_PlayAccent", "#2f8f83", rough=0.5),
        "fence": mat("M_Fence", "#2e3236", metal=0.6, rough=0.45),
        "planter": mat("M_Planter", "#3f4347", metal=0.3, rough=0.5),
        "before": mat("M_Existing", "#b7b1a6", rough=0.85),
        "before_roof": mat("M_ExistingRoof", "#8e5b4a", rough=0.8),
    }


def surf(acc, geom, z, m):
    for g in getattr(geom, "geoms", [geom]):
        if g.is_empty or g.area < 0.01:
            continue
        for tri in triangulate(g):
            acc.poly([(x, y, z) for x, y in tri], m)


def curb(acc, line, z0, h, w, m):
    """Raised curb strip along a LineString, offset to the left side."""
    poly = line.buffer(w / 2, cap_style=2, join_style=2)
    surf(acc, poly, z0 + h, m)
    ext = poly.exterior.coords
    for (ax, ay), (bx, by) in zip(ext[:-1], ext[1:]):
        acc.poly([(ax, ay, z0), (bx, by, z0), (bx, by, z0 + h), (ax, ay, z0 + h)], m)


def dashed(acc, y, x0, x1, dash, gap, w, z, m):
    x = x0
    while x < x1:
        acc.box(x, y - w / 2, z, min(x + dash, x1), y + w / 2, z + 0.01, m, skip=("-z",))
        x += dash + gap


def main():
    lib.reset_scene()
    M = materials()
    P = {k: MeshAccum(k) for k in ("S_ground", "S_road", "S_marks", "S_furniture", "S_play", "S_before")}
    plot = Polygon(PLOT)
    podium = Polygon(PODIUM)
    rnd = random.Random(5)

    # ---------------- avenue
    surf(P["S_road"], box(X0, ROAD[0], X1, ROAD[1]), 0.0, M["asphalt"])
    for y in LANES[:-1]:
        dashed(P["S_marks"], y - 1.7, X0, X1, 3.0, 6.0, 0.15, 0.0, M["marking"])
    P["S_marks"].box(X0, ROAD[0] + 0.5, 0.0, X1, ROAD[0] + 0.65, 0.01, M["marking"], skip=("-z",))
    P["S_marks"].box(X0, ROAD[1] - 0.65, 0.0, X1, ROAD[1] - 0.5, 0.01, M["marking"], skip=("-z",))
    # zebra crossing in front of the lobby and at the west access road
    for cx in (44.0, -14.0):
        for k in range(8):
            yy = ROAD[0] + 0.9 + k * 1.75
            P["S_marks"].box(cx - 2.5, yy, 0.0, cx + 2.5, yy + 0.9, 0.012, M["marking"], skip=("-z",))
        P["S_marks"].box(cx - 3.2, ROAD[1] - 1.5, 0.0, cx - 2.9, ROAD[0] + 0.9, 0.012, M["marking"], skip=("-z",))
    # sidewalks (raised 0.15) + curbs
    for y0, y1 in (SW_N, SW_S):
        surf(P["S_ground"], box(X0, y0, X1, y1), 0.15, M["sidewalk"])
    for yy in (ROAD[1], ROAD[0]):
        curb(P["S_road"], LineString([(X0, yy), (X1, yy)]), 0.0, 0.16, 0.3, M["curb"])
    # green strip across the avenue: lawn + low fence + paths
    gs = box(X0, GREEN_S[0], X1, GREEN_S[1])
    path_s = box(X0, -39.6, X1, -37.2)
    if FOOTPRINTS is not None:
        # real buildings stand south of the avenue: keep the lawn and path out of them (+ a paved apron)
        fp = FOOTPRINTS.buffer(2.5, join_style=2)
        surf(P["S_ground"], fp.intersection(gs), 0.05, M["sidewalk"])
        gs = gs.difference(fp)
        path_s = path_s.difference(fp)
    surf(P["S_ground"], gs.difference(path_s), 0.05, M["grass"])
    surf(P["S_ground"], path_s, 0.06, M["flag"])
    for yy in (GREEN_S[1] - 0.4,):
        for x in range(int(X0), int(X1), 3):
            P["S_furniture"].box(x, yy - 0.02, 0.05, x + 0.04, yy + 0.02, 0.9, M["fence"])
        P["S_furniture"].box(X0, yy - 0.02, 0.82, X1, yy + 0.02, 0.86, M["fence"])

    # ---------------- plot surfaces
    access = unary_union([box(*ACCESS_W[:1], 0, ACCESS_W[1], ACCESS_N[1]) if False else
                          box(ACCESS_W[0], 0, ACCESS_W[1], ACCESS_N[1]),
                          box(ACCESS_W[0], ACCESS_N[0], ACCESS_E[1], ACCESS_N[1]),
                          box(ACCESS_E[0], 46.4, ACCESS_E[1], ACCESS_N[1])]).intersection(plot)
    surf(P["S_road"], access, 0.02, M["asphalt"])
    # access road centre dashes
    for seg in ([(2.85, 2), (2.85, 61)], [(2.85, 61.15), (46.3, 61.15)], [(46.35, 61), (46.35, 47)]):
        ln = LineString(seg)
        d = 0.0
        while d < ln.length:
            a, b = ln.interpolate(d), ln.interpolate(min(d + 2.0, ln.length))
            P["S_marks"].poly([(a.x - 0.06 * (b.y - a.y) / max(ln.length, 1e-6) * 0, a.y, 0.03),
                               (b.x, b.y, 0.03), (b.x + 0.0, b.y, 0.03)], M["marking"]) if False else None
            seg_poly = LineString([(a.x, a.y), (b.x, b.y)]).buffer(0.07, cap_style=2)
            surf(P["S_marks"], seg_poly, 0.035, M["marking"])
            d += 5.0
    # garden: everything in the plot not podium / access / tower
    playground = Point(PLAY[0], PLAY[1]).buffer(PLAY[2], 48)
    garden_zone = plot.difference(podium).difference(access).difference(Polygon(TOWER_A).buffer(0.2))
    # curved garden paths (site plan legend 4)
    paths = unary_union([
        LineString([(49.5, 50.5), (55, 52), (62, 57.5), (70, 59.5), (77, 56), (79.5, 48)]).buffer(1.1),
        LineString([(52, 40), (58, 45), (66, 47.5), (74, 46), (79, 41)]).buffer(1.0),
        LineString([(55.5, 33.5), (58, 38), (62, 44), (66, 52), (66.5, 60)]).buffer(0.9),
        Point(PLAY[0], PLAY[1]).buffer(PLAY[2] + 1.4, 48).exterior.buffer(0.9),
        LineString([(49.2, 47.5), (55.2, 47.5)]).buffer(1.2),
    ]).intersection(garden_zone)
    lawn = garden_zone.difference(paths).difference(playground.buffer(0.5))
    hard = garden_zone.difference(lawn).difference(paths).difference(playground)
    surf(P["S_ground"], lawn, 0.06, M["grass"])
    surf(P["S_ground"], paths, 0.07, M["flag"])
    surf(P["S_ground"], hard, 0.06, M["paving"])
    surf(P["S_play"], playground, 0.08, M["rubber"])
    # playground tower: frame, deck, slide, roof
    px, py = PLAY[0], PLAY[1]
    pl = P["S_play"]
    for dx, dy in ((-1.2, -1.2), (1.2, -1.2), (1.2, 1.2), (-1.2, 1.2)):
        pl.box(px + dx - 0.07, py + dy - 0.07, 0.08, px + dx + 0.07, py + dy + 0.07, 3.6, M["play"])
    pl.box(px - 1.3, py - 1.3, 1.5, px + 1.3, py + 1.3, 1.62, M["play_acc"])
    pl.poly([(px - 1.5, py - 1.5, 3.6), (px + 1.5, py - 1.5, 3.6), (px, py, 4.6)], M["play_acc"])
    pl.poly([(px + 1.5, py - 1.5, 3.6), (px + 1.5, py + 1.5, 3.6), (px, py, 4.6)], M["play_acc"])
    pl.poly([(px + 1.5, py + 1.5, 3.6), (px - 1.5, py + 1.5, 3.6), (px, py, 4.6)], M["play_acc"])
    pl.poly([(px - 1.5, py + 1.5, 3.6), (px - 1.5, py - 1.5, 3.6), (px, py, 4.6)], M["play_acc"])
    pl.poly([(px + 1.3, py - 0.45, 1.6), (px + 4.6, py - 0.45, 0.25), (px + 4.6, py + 0.45, 0.25),
             (px + 1.3, py + 0.45, 1.6)], M["play_acc"])
    for k in range(6):  # climbing steps
        pl.box(px - 1.3 - 0.35, py - 0.5 + 0, 0.08 + k * 0.25, px - 1.3, py + 0.5, 0.14 + k * 0.25, M["play"])
    # swings frame
    sx, sy = px - 3.5, py + 3.6
    for dx in (-1.6, 1.6):
        pl.box(sx + dx - 0.06, sy - 0.06, 0.08, sx + dx + 0.06, sy + 0.06, 2.4, M["play"])
    pl.box(sx - 1.7, sy - 0.05, 2.35, sx + 1.7, sy + 0.05, 2.45, M["play"])
    for dx in (-0.7, 0.7):
        pl.box(sx + dx - 0.25, sy - 0.12, 0.5, sx + dx + 0.25, sy + 0.12, 0.56, M["play_acc"])
    # apron paving outside the plot west/east (between neighbours), kept modest
    apron = box(-12, 0, 0, 66).union(box(81.3, 0, 92, 64))
    surf(P["S_ground"], apron, 0.03, M["paving"])

    # ---------------- street furniture (static, merged)
    F = P["S_furniture"]
    lamp = props.street_lamp()
    bench = props.bench()
    bollard = props.bollard_light()
    lamps = []
    for x in range(int(X0) + 10, int(X1), 26):
        F.merge(lamp, offset=(x, -5.7, 0.15), rot=-math.pi / 2)
        lamps.append((x + 0.0, -5.7 + 1.1, 6.0))
        F.merge(lamp, offset=(x + 13, -22.1, 0.15), rot=math.pi / 2)
        lamps.append((x + 13.0, -22.1 - 1.1, 6.0))
    for x in (12.0, 24.0, 58.0, 70.0):
        F.merge(bench, offset=(x, -3.6, 0.15))
        F.box(x + 2.0, -4.2, 0.15, x + 4.4, -3.0, 0.75, M["planter"])
    for x, y in ((56, 56), (72, 52), (60, 36), (75, 44)):
        F.merge(bench, offset=(x, y, 0.07), rot=rnd.uniform(0, math.pi))
    bollards = []
    for ln in (LineString([(49.5, 50.5), (55, 52), (62, 57.5), (70, 59.5), (77, 56), (79.5, 48)]),
               LineString([(52, 40), (58, 45), (66, 47.5), (74, 46), (79, 41)])):
        d = 2.0
        while d < ln.length:
            p = ln.interpolate(d)
            F.merge(bollard, offset=(p.x, p.y + 1.5, 0.07))
            bollards.append((p.x, p.y + 1.5, 0.85))
            d += 7.0

    # ---------------- existing buildings on the plot today (for the before/after slider), from the cadastral plan
    existing = [  # (polygon in site frame, floors)  ASSUMED from cadastral plan 01.10.15.010.016 + Overture footprints
        ([(9, 18), (21, 18), (21, 56), (9, 56)], 5),
        ([(27, 26), (50, 26), (50, 40), (27, 40)], 2),
        ([(13, 4), (78, 4), (78, 13), (13, 13)], 4),
        ([(28, 52), (78, 56), (78, 63), (28, 61)], 1),
    ]
    for poly, fl in existing:
        h = fl * 3.2
        P["S_before"].prism(poly, 0.0, h, M["before"], cap_mat=M["before_roof"])

    col = bpy.context.scene.collection
    objs = [a.build(col) for a in P.values()]
    enu_root(objs, "Site")
    print("site tris:", lib.tri_count(objs))
    lib.export_glb(os.path.join(lib.OUT, "site_raw.glb"))
    if "--blend" in sys.argv:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(lib.OUT, "site.blend"))

    # ---------------- instance layout for the web app
    trees = []
    for x in range(int(X0) + 4, int(X1), 9):           # street trees, north sidewalk (skip driveway + lobby)
        if -2 < x < 8 or 36 < x < 52:
            continue
        trees.append({"t": "Tree_plane" if x % 2 else "Tree_plane2", "x": x, "y": -4.9, "z": 0.15,
                      "s": round(0.85 + rnd.random() * 0.3, 2), "r": round(rnd.random() * 6.28, 2)})
    for x in range(int(X0) + 2, int(X1), 8):            # south sidewalk
        trees.append({"t": "Tree_plane", "x": x, "y": -23.6, "z": 0.15, "s": round(0.8 + rnd.random() * 0.35, 2),
                      "r": round(rnd.random() * 6.28, 2)})
    def free(x, y, r=3.0):
        return FOOTPRINTS is None or not FOOTPRINTS.buffer(r).contains(Point(x, y))

    for row_y in (-30.0, -44.0, -52.0):                 # green strip rows (p10 photomontage)
        for x in range(int(X0), int(X1), 7):
            if not free(x, row_y):
                continue
            kind = "Tree_cypress" if (x // 7) % 5 == 0 and row_y == -42.0 else "Tree_plane2"
            trees.append({"t": kind, "x": x + rnd.uniform(-1.5, 1.5), "y": row_y + rnd.uniform(-1.5, 1.5),
                          "z": 0.05, "s": round(0.75 + rnd.random() * 0.4, 2), "r": round(rnd.random() * 6.28, 2)})
    garden_trees = [(57, 59), (63, 61.5), (72, 62), (78.5, 60), (53, 55), (69, 53), (76, 50), (59, 50), (70, 41),
                    (77, 37), (57.5, 30), (66, 33), (52.5, 44)]
    for x, y in garden_trees:
        trees.append({"t": rnd.choice(["Tree_small", "Tree_plane", "Tree_small"]), "x": x, "y": y, "z": 0.06,
                      "s": round(0.8 + rnd.random() * 0.3, 2), "r": round(rnd.random() * 6.28, 2)})
    for y in range(4, 60, 7):                           # trees along the west edge (outside the plot)
        trees.append({"t": "Tree_plane2", "x": -4.5, "y": y, "z": 0.03, "s": round(0.8 + rnd.random() * 0.3, 2),
                      "r": round(rnd.random() * 6.28, 2)})
    shrubs = []
    for _ in range(140):
        p = Point(rnd.uniform(49, 81), rnd.uniform(14, 64))
        if lawn.buffer(-0.8).contains(p):
            shrubs.append({"t": "Shrub", "x": round(p.x, 2), "y": round(p.y, 2), "z": 0.06,
                           "s": round(0.7 + rnd.random() * 0.6, 2), "r": round(rnd.random() * 6.28, 2)})
    shrubs = shrubs[:60]
    people_paths = [
        [[X0 + 20, -1.6], [X1 - 20, -1.6]], [[X1 - 20, -3.0], [X0 + 20, -3.0]],
        [[X0 + 20, -23.0], [X1 - 20, -23.0]], [[X1 - 20, -24.4], [X0 + 20, -24.4]],
        [[-4.0, -38.4], [138.0, -38.4]],
        [[44.0, -1.0], [44.0, -4.5], [30.0, -4.5]], [[56, 52.5], [62, 57.5], [70, 59.5], [77, 56], [79.5, 48]],
        [[52, 40], [58, 45], [66, 47.5], [74, 46], [79, 41]],
    ]
    terrace_people = [[[14, 20], [30, 12], [50, 8]], [[60, 6], [75, 20], [78, 28]]]
    car_lanes = [{"y": y, "x0": X0 - 120, "x1": X1 + 160} for y in LANES]
    parking_route = [[X0, LANES[0]], [-8, LANES[0]], [2.85, -3], [2.85, 61.15], [46.3, 61.15], [46.3, 47.0],
                     [46.3, 46.4]]
    layout = {
        "meta": {"frame": "site", "rotation_deg": 90.0 - json.load(open(os.path.join(lib.ROOT, "data",
                                                                                     "site-frame.json")))["x_axis_azimuth_true_deg"],
                 "note": "site frame: x along Kazbegi Ave (east-bound), y into the plot, z up"},
        "trees": trees + shrubs, "lamps": lamps, "bollards": bollards, "people_paths": people_paths,
        "terrace_paths": terrace_people, "car_lanes": car_lanes, "parking_route": parking_route,
        "road": {"x0": X0, "x1": X1, "y0": ROAD[0], "y1": ROAD[1]}, "playground": PLAY,
    }
    json.dump(layout, open(os.path.join(lib.ROOT, "src", "content", "site-layout.json"), "w"))
    print("trees", len(trees), "shrubs", len(shrubs), "lamps", len(lamps))


if __name__ == "__main__":
    main()
