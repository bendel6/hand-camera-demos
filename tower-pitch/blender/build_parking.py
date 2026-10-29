"""Three underground parking levels (B1-B3), 350 bays -> public/models/parking.glb + src/content/parking-layout.json.

Layout (ASSUMED, see spec): 8.1 m column grid in x, 16.2 m double-loaded modules in y (5.0 bay + 6.2 aisle + 5.0 bay),
cross aisles at both ends, straight two-way ramp x 43.2-49.6 / y 24.4-46.4 stacked on every level, tower cores
continuing down. Cars are NOT in the GLB: the web app instances props.glb cars from the layout JSON.
"""
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from shapely.geometry import Point, Polygon, box  # noqa: E402

import lib  # noqa: E402
from build_building import B_LEVELS, PLOT, enu_root, triangulate  # noqa: E402
from lib import MeshAccum, mat  # noqa: E402

LEVEL_H = 3.6
BAY_W, BAY_D, AISLE = 2.5, 5.0, 6.2
COLS_X = [9.5 + 8.1 * k for k in range(9)]
MODULES_Y = [4.0, 20.2, 36.4]
RAMP = box(43.2, 24.4, 49.6, 46.4)
CORE_A = box(18.8, 35.4, 27.8, 47.4)
CORE_B = box(42.3, 7.85, 49.3, 16.85)
STAIRS = [box(1.6, 57.5, 7.4, 63.0), box(73.0, 1.6, 78.4, 7.5)]
TECH = box(72.5, 22.0, 79.0, 40.0)
TARGET = {"B1": 117, "B2": 117, "B3": 116}
LEVEL_COL = {"B1": "#e0a458", "B2": "#4fb3a9", "B3": "#5b8def"}
LEVEL_ZONE = {"B1": "Commercial / visitors", "B2": "Residential", "B3": "Residential"}


def materials():
    return {
        "floor": mat("M_ParkingFloor", "#7d8186", rough=0.55, tex="epoxy_albedo.jpg", tex_scale=6.0),
        "aisle": mat("M_ParkingAisle", "#5f6368", rough=0.5),
        "line": mat("M_ParkingLine", "#f2f2ee", rough=0.6),
        "concrete": mat("M_Concrete", "#b8b4ac", rough=0.85, tex="concrete_albedo.jpg", normal="concrete_normal.png",
                        tex_scale=4.0, normal_strength=0.4),
        "light": mat("M_ParkingLight", "#ffffff", emit="#eef4ff", emit_strength=6.0),
        "acc": mat("M_BayAccessible", "#2f6fd6", rough=0.6),
        "ev": mat("M_BayEV", "#2fb36e", rough=0.6),
        "charger": mat("M_Charger", "#e9ecef", metal=0.2, rough=0.4),
        "charger_led": mat("M_ChargerLED", "#2fe08a", emit="#2fe08a", emit_strength=4.0),
        "ramp": mat("M_Ramp", "#6a6e72", rough=0.7),
        "B1": mat("M_LevelB1", LEVEL_COL["B1"], rough=0.5, emit=LEVEL_COL["B1"], emit_strength=0.0),
        "B2": mat("M_LevelB2", LEVEL_COL["B2"], rough=0.5, emit=LEVEL_COL["B2"], emit_strength=0.0),
        "B3": mat("M_LevelB3", LEVEL_COL["B3"], rough=0.5, emit=LEVEL_COL["B3"], emit_strength=0.0),
        "sign": mat("M_Sign", "#1d2126", rough=0.4),
        "wall": mat("M_ParkingWall", "#c9c6bf", rough=0.8),
    }


def bays_for_level():
    """Candidate bays (x0, y0, x1, y1, facing) in site frame, filtered against obstacles."""
    base = Polygon(PLOT).buffer(-1.4, join_style=2)
    obstacles = [RAMP.buffer(0.3), CORE_A.buffer(1.2), CORE_B.buffer(1.2), TECH] + [s.buffer(0.3) for s in STAIRS]
    rows = []
    for yc in MODULES_Y:
        rows.append((yc, yc + BAY_D, +1))                       # back on column line, faces +y aisle
        rows.append((yc + BAY_D + AISLE, yc + 2 * BAY_D + AISLE, -1))
    rows.append((58.6, 63.6, -1))                               # single-loaded row against the north wall
    out = []
    for y0, y1, facing in rows:
        for cx0, cx1 in zip(COLS_X[:-1], COLS_X[1:]):
            for k in range(3):
                x0 = cx0 + 0.3 + k * BAY_W
                b = box(x0, y0, x0 + BAY_W, y1)
                if not base.contains(b):
                    continue
                if any(b.intersects(o) for o in obstacles):
                    continue
                out.append((round(x0, 2), y0, round(x0 + BAY_W, 2), y1, facing))
    return out


def build_level(name, z, M, col, rnd):
    floor_z = z
    acc = MeshAccum(f"PK_{name}")
    base = Polygon(PLOT).buffer(-1.4, join_style=2)
    # floor slab (concrete edge + epoxy top)
    ring = list(base.exterior.coords)[:-1]
    acc.prism(ring, floor_z - 0.3, floor_z - 0.01, M["concrete"], skip=("+z",))
    hole = RAMP.buffer(0.2)
    for tri in triangulate(base.difference(hole)):
        acc.poly([(x, y, floor_z) for x, y in tri], M["floor"])
    # darker aisle bands
    for yc in MODULES_Y:
        acc.box(2.0, yc + BAY_D, floor_z, 78.0, yc + BAY_D + AISLE, floor_z + 0.004, M["aisle"], skip=("-z",))
    acc.box(2.0, 52.6, floor_z, 78.0, 58.6, floor_z + 0.004, M["aisle"], skip=("-z",))
    # columns with level-colour bands
    lines = MeshAccum(f"PK_{name}_marks")
    for cx in COLS_X:
        for yc in MODULES_Y + [52.6]:
            p = Point(cx, yc)
            if not base.buffer(-0.5).contains(p) or RAMP.buffer(1).contains(p) or CORE_A.buffer(1).contains(p):
                continue
            acc.box(cx - 0.3, yc - 0.3, floor_z, cx + 0.3, yc + 0.3, floor_z + LEVEL_H - 0.3, M["concrete"],
                    skip=("-z", "+z"))
            acc.box(cx - 0.31, yc - 0.31, floor_z + 1.0, cx + 0.31, yc + 0.31, floor_z + 1.6, M[name],
                    skip=("-z", "+z"))
    # cores, stairs, tech rooms as solid walls
    for b in [CORE_A, CORE_B, TECH] + STAIRS:
        x0, y0, x1, y1 = b.bounds
        acc.box(x0, y0, floor_z, x1, y1, floor_z + LEVEL_H - 0.3, M["wall"], skip=("-z",))
        acc.box(x0 - 0.01, y0 - 0.01, floor_z + 1.0, x1 + 0.01, y1 + 0.01, floor_z + 1.6, M[name], skip=("-z", "+z"))
    # perimeter wall (inside face)
    nr = len(ring)
    for i in range(nr):
        (ax, ay), (bx, by) = ring[i], ring[(i + 1) % nr]
        acc.poly([(bx, by, floor_z), (ax, ay, floor_z), (ax, ay, floor_z + LEVEL_H - 0.3),
                  (bx, by, floor_z + LEVEL_H - 0.3)], M["wall"])
    # ramp down to the next level (the ramp on this level goes from this floor down)
    x0, y0, x1, y1 = RAMP.bounds
    if name != "B3":
        acc.poly([(x0, y1, floor_z), (x0, y0, floor_z - LEVEL_H), (x1, y0, floor_z - LEVEL_H), (x1, y1, floor_z)],
                 M["ramp"])
        for xx in (x0, x1 - 0.25):
            acc.box(xx, y0, floor_z - LEVEL_H, xx + 0.25, y1, floor_z + 1.0, M["wall"])
    # bays
    cands = bays_for_level()
    target = TARGET[name]
    if len(cands) < target:
        raise SystemExit(f"{name}: only {len(cands)} bays fit, need {target}")
    # keep the bays closest to the cores/ramp (drop the far east ones first)
    cands.sort(key=lambda b: (b[0] > 70, -b[1] if b[4] < 0 else b[1], b[0]))
    chosen = sorted(cands[:target], key=lambda b: (b[1], b[0]))
    core_pts = [CORE_A.centroid, CORE_B.centroid]
    by_dist = sorted(range(len(chosen)), key=lambda i: min(Point((chosen[i][0] + chosen[i][2]) / 2,
                                                                   (chosen[i][1] + chosen[i][3]) / 2).distance(c)
                                                             for c in core_pts))
    acc_idx = set(by_dist[:4])
    ev_idx = set(by_dist[12:20])
    bays = []
    for i, (bx0, by0, bx1, by1, facing) in enumerate(chosen):
        kind = "accessible" if i in acc_idx else ("ev" if i in ev_idx else "standard")
        zf = floor_z + 0.006
        if kind != "standard":
            lines.box(bx0 + 0.08, by0 + 0.08, floor_z, bx1 - 0.08, by1 - 0.08, zf, M["acc" if kind == "accessible" else "ev"],
                      skip=("-z",))
        # side lines (U shape open to the aisle)
        for xx in (bx0, bx1 - 0.1):
            lines.box(xx, by0, floor_z, xx + 0.1, by1, zf + 0.001, M["line"], skip=("-z",))
        back = by0 if facing > 0 else by1 - 0.1
        lines.box(bx0, back, floor_z, bx1, back + 0.1, zf + 0.001, M["line"], skip=("-z",))
        if kind == "ev":
            cy = by0 + 0.25 if facing > 0 else by1 - 0.25
            lines.box((bx0 + bx1) / 2 - 0.15, cy - 0.1, floor_z, (bx0 + bx1) / 2 + 0.15, cy + 0.1, floor_z + 1.4,
                      M["charger"])
            lines.box((bx0 + bx1) / 2 - 0.08, cy - 0.11 * facing, floor_z + 1.1, (bx0 + bx1) / 2 + 0.08,
                      cy - 0.105 * facing, floor_z + 1.25, M["charger_led"])
        occupied = rnd.random() < (0.62 if kind != "accessible" else 0.3)
        bays.append({"x": round((bx0 + bx1) / 2, 2), "y": round((by0 + by1) / 2, 2), "facing": facing, "kind": kind,
                     "car": occupied})
    # aisle arrows (one-way loop: east in odd aisles, west in even)
    for i, yc in enumerate(MODULES_Y + [52.6 - BAY_D]):
        ay = yc + BAY_D + AISLE / 2
        d = 1 if i % 2 == 0 else -1
        for ax in (16, 30, 56, 66):
            pts = [(ax - 1.2 * d, ay - 0.25), (ax + 0.4 * d, ay - 0.25), (ax + 0.4 * d, ay - 0.6), (ax + 1.4 * d, ay),
                   (ax + 0.4 * d, ay + 0.6), (ax + 0.4 * d, ay + 0.25), (ax - 1.2 * d, ay + 0.25)]
            if d < 0:
                pts = pts[::-1]
            lines.poly([(x, y, floor_z + 0.008) for x, y in pts], M["line"])
    # ceiling light strips along aisles + level sign boxes
    lights = MeshAccum(f"PK_{name}_lights")
    for yc in MODULES_Y + [52.6]:
        ay = yc + BAY_D + AISLE / 2 if yc != 52.6 else 55.6
        for lx in range(6, 76, 5):
            if RAMP.buffer(1).contains(Point(lx, ay)):
                continue
            lights.box(lx - 0.6, ay - 0.06, floor_z + LEVEL_H - 0.42, lx + 0.6, ay + 0.06, floor_z + LEVEL_H - 0.38,
                       M["light"])
    for sx, sy in ((30.0, 30.0), (60.0, 30.0), (12.0, 13.0)):
        lights.box(sx - 0.9, sy - 0.05, floor_z + 2.3, sx + 0.9, sy + 0.05, floor_z + 2.9, M["sign"])
        lights.box(sx - 0.8, sy - 0.06, floor_z + 2.35, sx - 0.25, sy + 0.06, floor_z + 2.85, M[name])
    objs = [acc.build(col), lines.build(col), lights.build(col)]
    return objs, bays


def main():
    lib.reset_scene()
    M = materials()
    col = bpy.context.scene.collection
    rnd = random.Random(23)
    layout = {"meta": {"total": 0, "levels": [], "note": "ASSUMED layout; 350 bays per client brief"}, "bays": {}}
    allobjs = []
    for name, z in zip(["B1", "B2", "B3"], B_LEVELS):
        grp = lib.empty(f"PK_{name}_grp")
        objs, bays = build_level(name, z, M, col, rnd)
        for o in objs:
            o.parent = grp
        allobjs += [grp] + objs
        layout["bays"][name] = bays
        n = len(bays)
        layout["meta"]["levels"].append({"name": name, "z": z, "bays": n, "zone": LEVEL_ZONE[name],
                                         "colour": LEVEL_COL[name],
                                         "accessible": sum(b["kind"] == "accessible" for b in bays),
                                         "ev": sum(b["kind"] == "ev" for b in bays),
                                         "cars": sum(b["car"] for b in bays)})
        layout["meta"]["total"] += n
        print(name, n, "bays")
    enu_root(allobjs, "Parking")
    lib.export_glb(os.path.join(lib.OUT, "parking_raw.glb"))
    json.dump(layout, open(os.path.join(lib.ROOT, "src", "content", "parking-layout.json"), "w"), indent=1)
    print(json.dumps(layout["meta"], indent=1))
    if "--blend" in sys.argv:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(lib.OUT, "parking.blend"))


if __name__ == "__main__":
    main()
