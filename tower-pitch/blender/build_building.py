"""Scripted build of the Kazbegi 23 towers + podium + structure -> public/models/building.glb.

Run: /opt/venvs/blender/bin/python blender/build_building.py [--blend]
All dimensions in metres, site frame (see notes/building-spec.md). Node names are the contract with the web app:
  <T>_slabs, <T>_columns, <T>_core, <T>_stairs, <T>_lift_<n>, <T>_facade_<dir>, <T>_glazing_<dir>, <T>_crown
  for T in {A, B, P (podium)}, plus Foundation. The web app groups them into explode layers.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402

import lib  # noqa: E402
from lib import MeshAccum, mat  # noqa: E402

FH = 3.3          # residential floor-to-floor (ASSUMED)
PODIUM_TOP = 9.6  # drawing
GF_H = 5.0        # podium ground floor height (ASSUMED)
B_LEVELS = [-3.6, -7.2, -10.8]

PLOT = [(0, 0), (79.4, 0), (81.3, 64.2), (0.5, 66.7)]
PODIUM = [(5.7, 0), (80.9, 0), (80.9, 31.2), (68.8, 31.2), (68.8, 14.8), (55.1, 14.8), (55.1, 46.4),
          (35.8, 46.4), (35.8, 56.4), (10.8, 56.4), (10.8, 46.4), (5.7, 46.4)]
TOWER_A = [(10.8, 26.4), (35.8, 26.4), (35.8, 56.4), (10.8, 56.4)]
TOWER_B = [(36.9, 2.1), (71.1, 2.1), (71.1, 14.8), (54.7, 14.8), (54.7, 22.6), (36.9, 22.6)]
A_FLOORS, B_FLOORS = 30, 16
B_SPLIT_X = 49.6  # fin zone / framed balcony zone boundary on Tower B (renders p07 / p08: ~37 / 63)


def crown_a(x, y):
    """Tower A crown (renders p01 / p05): peak +115.0 at the SW corner; the framed west face and the fin face to
    the south both fall away from it, cutting diagonally across the top floors, down to +104 at the NE corner."""
    f = ((35.8 - x) / 25.0 + (56.4 - y) / 30.0) / 2
    f = min(max(f, 0.0), 1.0)
    return 104.0 + 11.0 * f ** 1.1


def crown_b(x, y):
    """Tower B crown: peak +68.0 at the fin/frame boundary; the frame top falls east to +64.2 and the fins step
    down west to +64.6 (renders p05 / p07)."""
    if x >= B_SPLIT_X:
        return 71.5 - 7.3 * ((x - B_SPLIT_X) / (71.1 - B_SPLIT_X)) ** 0.9
    return 71.5 - 5.5 * ((B_SPLIT_X - x) / (B_SPLIT_X - 36.9)) ** 1.1


# ------------------------------------------------------------------------------------------------ materials
def materials():
    M = {}
    M["clad"] = mat("M_Cladding", "#5b6068", metal=0.15, rough=0.5)
    M["frame"] = mat("M_Frame", "#6a717b", metal=0.45, rough=0.36, normal="ribs_normal.png",
                     tex_scale=2.4, normal_strength=0.6)
    M["fin"] = mat("M_Fin", "#5d646e", metal=0.5, rough=0.32)
    M["slab_edge"] = mat("M_BalconySlab", "#dcdcd8", rough=0.55)
    M["spandrel"] = mat("M_Spandrel", "#2c3137", metal=0.4, rough=0.3)
    M["sill"] = mat("M_Sill", "#bfc3c7", metal=0.1, rough=0.5)
    M["mullion"] = mat("M_Mullion", "#2a2d31", metal=0.7, rough=0.35)
    M["glass_res"] = mat("M_Glass_Res", "#1d2a33", metal=0.0, rough=0.04)
    M["rail_glass"] = mat("M_RailGlass", "#c9d3d8", rough=0.08, alpha=0.42)
    M["rail"] = mat("M_RailMetal", "#8d9298", metal=0.85, rough=0.3)
    M["divider"] = mat("M_Divider", "#30353c", metal=0.5, rough=0.35)
    M["red"] = mat("M_PodiumRed", "#7a2f2b", metal=0.25, rough=0.5)
    M["glass_shop"] = mat("M_Glass_Shop", "#1c2328", metal=0.0, rough=0.03)
    M["concrete"] = mat("M_Concrete", "#b8b4ac", rough=0.85, tex="concrete_albedo.jpg", normal="concrete_normal.png",
                        tex_scale=4.0, normal_strength=0.4)
    M["roof"] = mat("M_RoofMembrane", "#55585c", rough=0.9)
    M["plant"] = mat("M_RoofPlant", "#8b9096", metal=0.6, rough=0.45)
    M["paving"] = mat("M_TerracePaving", "#b9b4aa", rough=0.75, tex="paving_albedo.jpg", normal="paving_normal.png",
                      rough_tex="paving_rough.jpg", tex_scale=2.4)
    M["planter"] = mat("M_Planter", "#3f4347", metal=0.3, rough=0.5)
    M["soil_green"] = mat("M_Shrub", "#4d6b2e", rough=0.85)
    M["wood"] = mat("M_Wood", "#8a6243", rough=0.6)
    M["umbrella"] = mat("M_Umbrella", "#ece7dc", rough=0.8)
    M["lift"] = mat("M_LiftCab", "#d6b46a", metal=0.9, rough=0.25)
    M["soffit"] = mat("M_SoffitLight", "#cfcac2", rough=0.3, emit="#ffd9a8", emit_strength=0.0)
    M["led"] = mat("M_LED", "#4d5157", rough=0.3, emit="#e9f1ff", emit_strength=0.0)
    return M


# ------------------------------------------------------------------------------------------------ helpers
def edge_frame(p0, p1):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy)
    d = (dx / L, dy / L)
    n = (d[1], -d[0])  # outward for CCW polygons
    return L, d, n


def to_world(p0, d, n, u, w, z):
    return (p0[0] + d[0] * u + n[0] * w, p0[1] + d[1] * u + n[1] * w, z)


def fbox(acc, p0, d, n, u0, u1, w0, w1, z0, z1, m, skip=()):
    """Box in face-local coords (u along face, w outward)."""
    pts = [to_world(p0, d, n, u, w, 0)[:2] for u, w in ((u0, w0), (u1, w0), (u1, w1), (u0, w1))]
    # orientation of (u,w) frame: d x n has negative z for CCW faces -> reverse to keep CCW
    pts = pts[::-1]
    acc.prism(pts, z0, z1, m, skip=skip)


def fquad(acc, p0, d, n, u0, u1, w, z0, z1, m):
    """Vertical quad facing outward at offset w."""
    a = to_world(p0, d, n, u0, w, z0)
    b = to_world(p0, d, n, u1, w, z0)
    c = to_world(p0, d, n, u1, w, z1)
    e = to_world(p0, d, n, u0, w, z1)
    acc.poly([a, b, c, e], m)


def fprofile(acc, p0, d, n, u0, u1, w0, w1, zbot, ztop_fn, m, steps=10):
    """Wall slab between u0..u1 / w0..w1 whose top follows ztop_fn(x, y) (sloped / concave crown).
    zbot may be a constant or a function of (x, y)."""
    us = [u0 + (u1 - u0) * i / steps for i in range(steps + 1)]
    zb_fn = zbot if callable(zbot) else (lambda _x, _y: zbot)
    for i in range(steps):
        ua, ub = us[i], us[i + 1]
        xa, ya, _ = to_world(p0, d, n, ua, 0, 0)
        xb, yb, _ = to_world(p0, d, n, ub, 0, 0)
        za, zb = ztop_fn(xa, ya), ztop_fn(xb, yb)
        zba, zbb = zb_fn(xa, ya), zb_fn(xb, yb)
        for w in (w1, w0):  # front (w1) and back (w0) faces
            pa, pb = to_world(p0, d, n, ua, w, zba), to_world(p0, d, n, ub, w, zbb)
            pc, pd = to_world(p0, d, n, ub, w, zb), to_world(p0, d, n, ua, w, za)
            if w == w1:
                acc.poly([pa, pb, pc, pd], m)
            else:
                acc.poly([pb, pa, pd, pc], m)
        # sloped top
        acc.poly([to_world(p0, d, n, ua, w0, za), to_world(p0, d, n, ua, w1, za),
                  to_world(p0, d, n, ub, w1, zb), to_world(p0, d, n, ub, w0, zb)], m)
    # end caps
    for u, s in ((u0, -1), (u1, 1)):
        x, y, _ = to_world(p0, d, n, u, 0, 0)
        zt = ztop_fn(x, y)
        zb0 = zb_fn(x, y)
        q = [to_world(p0, d, n, u, w0, zb0), to_world(p0, d, n, u, w1, zb0),
             to_world(p0, d, n, u, w1, zt), to_world(p0, d, n, u, w0, zt)]
        acc.poly(q if s > 0 else q[::-1], m)


def floor_ok(crown, x, y, z_floor_top):
    """A floor exists at (x, y) when the crown clears its ceiling by at least 0.8 m."""
    return crown(x, y) >= z_floor_top + 0.8


def last_floor_top(crown, x, y, z0, floors):
    """Height of the highest complete floor at (x, y) under a sloping crown."""
    k = int((crown(x, y) - 0.8 - z0) // FH)
    return z0 + max(0, min(floors, k)) * FH


# ------------------------------------------------------------------------------------------------ facades
def balcony_zone(F, G, M, p0, d, n, u0, u1, z0, floors, crown, post0=True, post1=True):
    """Framed balcony zone between u0..u1 of a face (renders p07 / p08): ribbed metal frame with a sloped crown
    panel, continuous white balcony slabs, frosted glass balustrades, dark posts between apartments (~2.3 m),
    triangular privacy dividers and floor-to-ceiling glazing with mullions. F: facade, G: glazing accumulator."""
    fw = 1.0
    w_glass, w_front = -1.5, 0.35
    ztop = z0 + floors * FH
    a = u0 + (fw if post0 else 0.0)
    b = u1 - (fw if post1 else 0.0)
    for on, (pa, pb) in ((post0, (u0, u0 + fw)), (post1, (u1 - fw, u1))):
        if on:
            fprofile(F, p0, d, n, pa, pb, w_glass, w_front, z0, crown, M["frame"], steps=2)
    panel_bottom = lambda x, y: last_floor_top(crown, x, y, z0, floors)  # noqa: E731
    fprofile(F, p0, d, n, a, b, -0.25, w_front, panel_bottom, crown, M["frame"], steps=32)
    steps = 16
    for k in range(steps):  # LED line tracing the crown's top edge (lit at night)
        ua = a + (b - a) * k / steps
        ub = a + (b - a) * (k + 1) / steps
        xa, ya, _ = to_world(p0, d, n, ua, 0, 0)
        xb, yb, _ = to_world(p0, d, n, ub, 0, 0)
        za, zb = crown(xa, ya) - 0.25, crown(xb, yb) - 0.25
        F.poly([to_world(p0, d, n, ua, w_front + 0.012, za - 0.1), to_world(p0, d, n, ub, w_front + 0.012, zb - 0.1),
                to_world(p0, d, n, ub, w_front + 0.012, zb), to_world(p0, d, n, ua, w_front + 0.012, za)], M["led"])
    span = b - a
    ndiv = max(1, round(span / 2.3))
    fquad(G, p0, d, n, a, b, w_glass, z0, ztop, M["glass_res"])
    # dark posts between apartments (continuous through the floors) and glazing mullions between them
    for k in range(1, ndiv):
        u = a + span * k / ndiv
        fbox(F, p0, d, n, u - 0.18, u + 0.18, w_glass, w_glass + 0.14, z0, ztop, M["spandrel"], skip=("-z", "+z"))
    for k in range(ndiv):
        ua, ub = a + span * k / ndiv, a + span * (k + 1) / ndiv
        for j in (1, 2):
            u = ua + (ub - ua) * j / 3
            fbox(F, p0, d, n, u - 0.025, u + 0.025, w_glass, w_glass + 0.09, z0, ztop, M["mullion"], skip=("-z", "+z"))
    samples = [a + span * k / 48 for k in range(49)]
    for i in range(floors + 1):
        z = z0 + i * FH
        # part of this floor line that lies under the crown (the sloping crown cuts the top floors)
        ok = [u for u in samples if floor_ok(crown, *to_world(p0, d, n, u, 0, 0)[:2], z + (FH if i < floors else 0))]
        if not ok:
            continue
        fa, fb = min(ok), max(ok)
        if i > 0:  # balcony slab cantilever (white edge + soffit)
            fbox(F, p0, d, n, fa, fb, w_glass, 0.06, z - 0.32, z, M["slab_edge"])
        fbox(F, p0, d, n, fa, fb, w_glass + 0.01, w_glass + 0.1, z - 0.32, z + 0.1, M["spandrel"], skip=("-z", "+z"))
        if i == floors:
            break
        zs = z + FH - 0.325
        for k in range(ndiv):  # soffit downlights, one per apartment bay
            uc = a + span * (k + 0.5) / ndiv
            if not (fa <= uc <= fb):
                continue
            q = [to_world(p0, d, n, uc - 0.15, -0.8, zs), to_world(p0, d, n, uc + 0.15, -0.8, zs),
                 to_world(p0, d, n, uc + 0.15, -0.5, zs), to_world(p0, d, n, uc - 0.15, -0.5, zs)]
            F.poly(q, M["soffit"])
        fquad(G, p0, d, n, fa, fb, -0.03, z, z + 1.1, M["rail_glass"])
        fbox(F, p0, d, n, fa, fb, -0.07, 0.0, z + 1.08, z + 1.13, M["rail"])
        for k in range(1, ndiv):  # triangular privacy dividers (dark, wide at the slab, narrowing upwards)
            u = a + span * k / ndiv
            if not (fa <= u <= fb):
                continue
            t = 0.04
            tri = [(w_glass, z), (-0.08, z), (w_glass, z + FH - 0.35)]
            for side in (-t, t):
                pts = [to_world(p0, d, n, u + side, w, zz) for w, zz in tri]
                F.poly(pts if side > 0 else pts[::-1], M["divider"])
            (wa, za), (wb, zb) = tri[1], tri[2]
            F.poly([to_world(p0, d, n, u - t, wa, za), to_world(p0, d, n, u + t, wa, za),
                    to_world(p0, d, n, u + t, wb, zb), to_world(p0, d, n, u - t, wb, zb)], M["divider"])


def fblade(acc, p0, d, n, u0, u1, wb, wf, z0, zt_back, zt_front, m):
    """Vertical blade (fin) from wb (back) to wf (front) with a top sloping from zt_back down to zt_front."""
    prof = [(wb, z0), (wf, z0), (wf, zt_front), (wb, zt_back)]
    for u, s in ((u0, -1), (u1, 1)):
        pts = [to_world(p0, d, n, u, w, z) for w, z in prof]
        acc.poly(pts if s < 0 else pts[::-1], m)
    for (wa, za), (wb2, zb) in zip(prof, prof[1:] + prof[:1]):
        q = [to_world(p0, d, n, u0, wa, za), to_world(p0, d, n, u1, wa, za), to_world(p0, d, n, u1, wb2, zb),
             to_world(p0, d, n, u0, wb2, zb)]
        acc.poly(q[::-1], m)


def fin_zone(F, G, M, p0, d, n, u0, u1, z0, floors, crown, corner0=True, corner1=True, bay=4.1):
    """Vertical-fin zone (renders p05 / p08): deep slate blades with pointed tops that rise in steps to the crown,
    bays with a light parapet panel below each window, mullioned glazing and a dark spandrel at every slab."""
    w_glass, w_fin = -0.6, 1.0
    ztop = z0 + floors * FH
    span = u1 - u0
    nb = max(1, round(span / bay))
    fin_us = [u0 + span * k / nb for k in range(nb + 1)]
    fins = []
    for k, u in enumerate(fin_us):
        if k == 0:
            fins.append((u, u + (0.8 if corner0 else 0.22)))
        elif k == nb:
            fins.append((u - (0.8 if corner1 else 0.22), u))
        else:
            fins.append((u - 0.24, u + 0.24))
    tops = []
    for fa, fb in fins:
        x, y, _ = to_world(p0, d, n, (fa + fb) / 2, 0, 0)
        top = crown(x, y) + 2.6
        tops.append(top)
        fblade(F, p0, d, n, fa, fb, w_glass, w_fin, z0, top, top - 1.9, M["fin"])
        uc = (fa + fb) / 2
        F.poly([to_world(p0, d, n, uc - 0.05, w_fin + 0.012, top - 9.0), to_world(p0, d, n, uc + 0.05, w_fin + 0.012, top - 9.0),
                to_world(p0, d, n, uc + 0.05, w_fin + 0.012, top - 2.1), to_world(p0, d, n, uc - 0.05, w_fin + 0.012, top - 2.1)],
               M["led"])
    fquad(G, p0, d, n, u0, u1, w_glass, z0, ztop, M["glass_res"])
    for k in range(nb):
        a, b = fins[k][1], fins[k + 1][0]
        bw = b - a
        # crown screen between the blades, kept well below them so the blades read as a sawtooth
        xc, yc, _ = to_world(p0, d, n, (a + b) / 2, 0, 0)
        bay_top = last_floor_top(crown, xc, yc, z0, floors)
        infill_top = min(tops[k], tops[k + 1]) - 3.4
        if infill_top > bay_top:
            fbox(F, p0, d, n, a, b, w_glass, w_glass + 0.15, bay_top, infill_top, M["spandrel"])
        nmul = 1 if bw < 2.6 else 2
        for i in range(floors):
            z = z0 + i * FH
            if z + FH > bay_top + 0.01:
                break
            fbox(F, p0, d, n, a, b, w_glass, w_glass + 0.14, z, z + 0.95, M["sill"])  # light parapet panel
            fbox(F, p0, d, n, a, b, w_glass, w_glass + 0.16, z + 0.95, z + 1.02, M["mullion"])
            fbox(F, p0, d, n, a, b, w_glass, w_glass + 0.08, z + FH - 0.3, z + FH, M["spandrel"], skip=("-z",))
            for j in range(1, nmul + 1):
                u = a + bw * j / (nmul + 1)
                fbox(F, p0, d, n, u - 0.03, u + 0.03, w_glass, w_glass + 0.1, z + 1.02, z + FH - 0.3, M["mullion"],
                     skip=("-z", "+z"))
        fbox(F, p0, d, n, a, b, w_glass, w_glass + 0.2, bay_top - 0.3, bay_top, M["spandrel"])


def tower(T, poly, floors, crown, faces, M, col, bay=4.1):
    """faces: list of per-edge specs: ('fin'|'bal'|('split', x_split, first_kind)), per CCW edge of poly."""
    dirs = []
    z0 = PODIUM_TOP
    ztop = z0 + floors * FH
    accs = {}
    for i, spec in enumerate(faces):
        p0, p1 = poly[i], poly[(i + 1) % len(poly)]
        L, d, n = edge_frame(p0, p1)
        tag = "SENW"[[abs(n[1] + 1) < 0.1, abs(n[0] - 1) < 0.1, abs(n[1] - 1) < 0.1, abs(n[0] + 1) < 0.1].index(True)]
        key = tag
        if key not in accs:
            accs[key] = (MeshAccum(f"{T}_facade_{key}"), MeshAccum(f"{T}_glazing_{key}"))
            dirs.append(key)
        F, G = accs[key]
        if spec == "fin":
            fin_zone(F, G, M, p0, d, n, 0, L, z0, floors, crown, bay=bay)
        elif spec == "bal":
            balcony_zone(F, G, M, p0, d, n, 0, L, z0, floors, crown)
        else:
            _, xs, first = spec
            us = abs(xs - p0[0])
            if first == "fin":
                fin_zone(F, G, M, p0, d, n, 0, us, z0, floors, crown, corner1=False, bay=bay)
                balcony_zone(F, G, M, p0, d, n, us, L, z0, floors, crown, post0=True)
            else:
                balcony_zone(F, G, M, p0, d, n, 0, us, z0, floors, crown, post1=True)
                fin_zone(F, G, M, p0, d, n, us, L, z0, floors, crown, corner0=False, bay=bay)
    objs = []
    for k in dirs:
        for a in accs[k]:
            objs.append(a.build(col))
    # roof slab + membrane + plant + lift overrun
    shp = Polygon(poly).buffer(-0.4, join_style=2)
    roof = MeshAccum(f"{T}_crown")
    ring = list(shp.exterior.coords)[:-1]
    rz = [crown(x, y) - 1.2 for x, y in ring]
    roof.poly([(x, y, z) for (x, y), z in zip(ring, rz)], M["roof"])
    roof.poly([(x, y, z - 0.35) for (x, y), z in zip(ring[::-1], rz[::-1])], M["roof"])
    cx, cy = shp.centroid.x, shp.centroid.y
    zr = min(crown(cx + dx, cy + dy) for dx in (-7, 7) for dy in (-3, 3)) - 1.55
    roof.box(cx - 3, cy - 2.5, zr, cx + 3, cy + 2.5, zr + 1.2, M["plant"])
    roof.box(cx + 3.5, cy - 1.5, zr, cx + 6.5, cy + 1.5, zr + 0.9, M["plant"])
    objs.append(roof.build(col))
    return objs


# ------------------------------------------------------------------------------------------------ structure
def structure(T, poly, floors, core_rect, n_lifts, n_stairs, M, col, z_base=PODIUM_TOP, crown=None):
    ztop = z_base + floors * FH
    shp = Polygon(poly)
    slabs = MeshAccum(f"{T}_slabs")
    inner = list(shp.buffer(-0.3, join_style=2).exterior.coords)[:-1]
    crown_min = min(crown(x, y) for x, y in inner) if crown else 1e9
    for i in range(1, floors + 1):
        z = z_base + i * FH
        if z > crown_min - 1.0:  # slabs under the sloping crown stop at its lowest point
            break
        slabs.prism(inner, z - 0.25, z, M["concrete"])
    cols = MeshAccum(f"{T}_columns")
    ring = shp.buffer(-1.6, join_style=2).exterior
    npts = max(4, int(ring.length / 7.0))
    for k in range(npts):
        p = ring.interpolate(k * ring.length / npts)
        ct = min(ztop, crown(p.x, p.y) - 1.5) if crown else ztop
        cols.box(p.x - 0.4, p.y - 0.4, z_base, p.x + 0.4, p.y + 0.4, ct - 0.25, M["concrete"], skip=("-z", "+z"))
    x0, y0, x1, y1 = core_rect
    t = 0.35
    core = MeshAccum(f"{T}_core")
    zc0, zc1 = B_LEVELS[-1], (min(ztop + 4.2, crown((x0 + x1) / 2, (y0 + y1) / 2) - 1.3) if crown else ztop + 4.2)
    core.box(x0, y0, zc0, x1, y0 + t, zc1, M["concrete"])
    core.box(x0, y1 - t, zc0, x1, y1, zc1, M["concrete"])
    core.box(x0, y0, zc0, x0 + t, y1, zc1, M["concrete"])
    core.box(x1 - t, y0, zc0, x1, y1, zc1, M["concrete"])
    core.box(x0, y0, zc1 - 0.3, x1, y1, zc1, M["concrete"])
    # lift shafts along the north side of the core, stairs along the south side
    depth = y1 - y0
    lift_y0 = y0 + depth * 0.55
    core.box(x0, lift_y0 - t / 2, zc0, x1, lift_y0 + t / 2, zc1, M["concrete"])
    lw = (x1 - x0) / n_lifts
    for k in range(1, n_lifts):
        core.box(x0 + k * lw - 0.1, lift_y0, zc0, x0 + k * lw + 0.1, y1, zc1, M["concrete"])
    objs = [slabs.build(col), cols.build(col), core.build(col)]
    for k in range(n_lifts):
        cab = MeshAccum(f"{T}_lift_{k + 1}")
        lx0 = x0 + k * lw + 0.35
        cab.box(lx0, lift_y0 + 0.4, 0, lx0 + lw - 0.7, y1 - 0.6, 2.5, M["lift"])
        o = cab.build(col)
        o.location.z = z_base + ((k * 7 + 3) % floors) * FH
        objs.append(o)
    stairs = MeshAccum(f"{T}_stairs")
    sw = (x1 - x0) / n_stairs
    for s in range(n_stairs):
        sx0, sx1 = x0 + s * sw + t, x0 + (s + 1) * sw - t
        sy0, sy1 = y0 + t, lift_y0 - t / 2
        half = (sx1 - sx0) / 2
        run = (sy1 - sy0) - 2.6
        levels = [B_LEVELS[-1] + i * 3.6 for i in range(3)] + [0.0, GF_H] + \
                 [z_base + i * FH for i in range(floors)]
        for zf, zn in zip(levels[:-1], levels[1:]):
            h = (zn - zf) / 2
            nst = 10
            for k in range(nst):  # flight 1: up along +y on the left half
                zz = zf + h * (k + 1) / nst
                yy = sy0 + 1.2 + run * k / nst
                stairs.box(sx0, yy, zz - 0.18, sx0 + half - 0.05, yy + run / nst, zz, M["concrete"])
            stairs.box(sx0, sy1 - 1.4, zf + h - 0.2, sx1, sy1, zf + h, M["concrete"])  # landing
            for k in range(nst):  # flight 2: back along -y on the right half
                zz = zf + h + h * (k + 1) / nst
                yy = sy1 - 1.4 - run * (k + 1) / nst
                stairs.box(sx0 + half + 0.05, yy, zz - 0.18, sx1, yy + run / nst, zz, M["concrete"])
            stairs.box(sx0, sy0, zn - 0.2, sx1, sy0 + 1.2, zn, M["concrete"])
    objs.append(stairs.build(col))
    return objs


def podium(M, col):
    objs = []
    shp = Polygon(PODIUM)
    F = MeshAccum("P_facade")
    G = MeshAccum("P_glazing")
    n = len(PODIUM)
    for i in range(n):
        p0, p1 = PODIUM[i], PODIUM[(i + 1) % n]
        L, d, nn = edge_frame(p0, p1)
        south = abs(nn[1] + 1) < 0.1 and p0[1] < 1
        # red bands wrap the whole podium (top fascia + mid band) projecting slightly
        fbox(F, p0, d, nn, -0.15, L + 0.15, -0.35, 0.15, 8.3, PODIUM_TOP + 0.05, M["red"])
        piers = []
        if south:
            piers = [(46.2 - p0[0], 47.8 - p0[0]), (60.0 - p0[0], 61.6 - p0[0])]
        lobby = (piers[0][1], piers[1][0]) if piers else None
        for u0, u1 in piers:
            fbox(F, p0, d, nn, u0, u1, -0.35, 0.35, 0, 8.3, M["red"])
        # mid band, interrupted over the double-height lobby
        segs = [(-0.15, L + 0.15)] if not lobby else [(-0.15, lobby[0]), (lobby[1], L + 0.15)]
        for a, b in segs:
            fbox(F, p0, d, nn, a, b, -0.35, 0.12, 3.45, 4.95, M["red"])
        if lobby:
            fbox(F, p0, d, nn, lobby[0], lobby[1], -0.6, -0.3, 4.95, 5.12, M["mullion"])
        # curtain wall glass + mullions + transoms
        fquad(G, p0, d, nn, 0, L, -0.35, 0.0, 8.3, M["glass_shop"])
        nm = max(1, int(L / 1.15))
        for k in range(nm + 1):
            u = L * k / nm
            fbox(F, p0, d, nn, u - 0.035, u + 0.035, -0.35, -0.2, 0.0, 8.3, M["mullion"], skip=("-z", "+z"))
        for z in (0.0, 2.9, 7.4):
            fbox(F, p0, d, nn, 0, L, -0.35, -0.24, z, z + 0.08, M["mullion"])
        # terrace balustrade on the roof edge
        fquad(G, p0, d, nn, 0, L, -0.3, PODIUM_TOP, PODIUM_TOP + 1.1, M["rail_glass"])
        fbox(F, p0, d, nn, 0, L, -0.34, -0.26, PODIUM_TOP + 1.07, PODIUM_TOP + 1.13, M["rail"])
    objs += [F.build(col), G.build(col)]
    # slabs and roof terrace
    S = MeshAccum("P_slabs")
    inner = list(shp.buffer(-0.36, join_style=2).exterior.coords)[:-1]
    S.prism(inner, -0.3, 0.0, M["concrete"])
    S.prism(inner, GF_H - 0.3, GF_H, M["concrete"])
    S.prism(inner, PODIUM_TOP - 0.5, PODIUM_TOP - 0.1, M["concrete"])
    objs.append(S.build(col))
    R = MeshAccum("P_roof")
    terrace = shp.buffer(-0.36, join_style=2)
    holes = Polygon(TOWER_A).union(Polygon(TOWER_B))
    terr = terrace.difference(holes.buffer(-0.5, join_style=2))
    geoms = getattr(terr, "geoms", [terr])
    for g in geoms:
        # terrace deck: triangulate via the convex decomposition of a grid-free approach -> use earcut-like split
        for tri in triangulate(g):
            R.poly([(x, y, PODIUM_TOP) for x, y in tri], M["paving"])
    import random
    rnd = random.Random(4)
    no_go = holes.buffer(2.0).union(terrace.exterior.buffer(2.2))
    placed = []
    for _ in range(600):
        if len(placed) >= 26:
            break
        x, y = rnd.uniform(6, 80), rnd.uniform(1, 46)
        from shapely.geometry import Point
        if not terrace.contains(Point(x, y)) or no_go.contains(Point(x, y)):
            continue
        if any(math.hypot(x - a, y - b) < 5.5 for a, b, _ in placed):
            continue
        placed.append((x, y, rnd.random()))
    for x, y, r in placed:
        z = PODIUM_TOP
        if r < 0.55:   # umbrella + table + 4 chairs
            R.box(x - 0.04, y - 0.04, z, x + 0.04, y + 0.04, z + 2.4, M["rail"])
            umb = [(x + 1.4 * math.cos(a), y + 1.4 * math.sin(a), z + 2.2) for a in
                   [i * math.pi / 4 for i in range(8)]]
            for i in range(8):
                R.poly([umb[i], umb[(i + 1) % 8], (x, y, z + 2.65)], M["umbrella"])
                R.poly([umb[(i + 1) % 8], umb[i], (x, y, z + 2.15)], M["umbrella"])
            R.box(x - 0.4, y - 0.4, z + 0.72, x + 0.4, y + 0.4, z + 0.76, M["wood"])
            R.box(x - 0.05, y - 0.05, z, x + 0.05, y + 0.05, z + 0.72, M["rail"])
            for a in range(4):
                cxx, cyy = x + 0.85 * math.cos(a * math.pi / 2 + 0.3), y + 0.85 * math.sin(a * math.pi / 2 + 0.3)
                R.box(cxx - 0.22, cyy - 0.22, z + 0.42, cxx + 0.22, cyy + 0.22, z + 0.47, M["wood"])
                R.box(cxx - 0.03, cyy - 0.03, z, cxx + 0.03, cyy + 0.03, z + 0.42, M["rail"])
        else:          # planter with shrub mound
            R.box(x - 1.2, y - 0.6, z, x + 1.2, y + 0.6, z + 0.7, M["planter"])
            for k in range(3):
                bx = x - 0.7 + 0.7 * k
                R.box(bx - 0.38, y - 0.38, z + 0.7, bx + 0.38, y + 0.38, z + 1.25 + 0.15 * (k % 2), M["soil_green"])
    objs.append(R.build(col))
    # podium grid columns (GF + 1F) outside the tower footprints
    C = MeshAccum("P_columns")
    for gx in frange(9.5, 80, 8.1):
        for gy in frange(4.0, 46, 8.1):
            from shapely.geometry import Point
            p = Point(gx, gy)
            if shp.buffer(-1.0).contains(p) and not holes.buffer(0.5).contains(p):
                C.box(gx - 0.3, gy - 0.3, B_LEVELS[-1], gx + 0.3, gy + 0.3, PODIUM_TOP - 0.5, M["concrete"],
                      skip=("-z", "+z"))
    objs.append(C.build(col))
    return objs


def frange(a, b, s):
    v = a
    while v < b:
        yield v
        v += s


def triangulate(poly):
    """Constrained triangulation of a shapely polygon (with holes) via shapely's constrained Delaunay."""
    from shapely import constrained_delaunay_triangles
    tris = constrained_delaunay_triangles(poly)
    out = []
    for t in tris.geoms:
        c = list(t.exterior.coords)[:-1]
        if Polygon(c).exterior.is_ccw is False:
            c = c[::-1]
        out.append(c)
    return out


def foundation(M, col):
    F = MeshAccum("Foundation")
    base = Polygon(PLOT).buffer(-1.0, join_style=2)
    ring = list(base.exterior.coords)[:-1]
    F.prism(ring, B_LEVELS[-1] - 1.8, B_LEVELS[-1], M["concrete"])
    inner = base.buffer(-0.4, join_style=2)
    wall = base.difference(inner)
    for tri in triangulate(wall):
        F.poly([(x, y, 0.0) for x, y in tri], M["concrete"])
    for ringc, outward in ((list(base.exterior.coords)[:-1], True), (list(inner.exterior.coords)[:-1], False)):
        nr = len(ringc)
        for i in range(nr):
            (ax, ay), (bx, by) = ringc[i], ringc[(i + 1) % nr]
            q = [(ax, ay, B_LEVELS[-1]), (bx, by, B_LEVELS[-1]), (bx, by, 0.0), (ax, ay, 0.0)]
            F.poly(q if outward else q[::-1], M["concrete"])
    return [F.build(col)]


def enu_root(objs, name):
    """Parent everything to a root rotated from the site frame into ENU (true north)."""
    fr = json.load(open(os.path.join(lib.ROOT, "data", "site-frame.json")))
    root = lib.empty(name)
    root.rotation_euler[2] = math.radians(90.0 - fr["x_axis_azimuth_true_deg"])
    for o in objs:
        if o is not None and o.parent is None:
            o.parent = root
    return root


def main():
    lib.reset_scene()
    M = materials()
    col = bpy.context.scene.collection
    objs = []
    objs += tower("A", TOWER_A, A_FLOORS, crown_a, ["fin", "bal", "fin", "bal"], M, col)
    objs += tower("B", TOWER_B, B_FLOORS, crown_b,
                  [("split", B_SPLIT_X, "fin"), "bal", "fin", "bal", ("split", B_SPLIT_X, "bal"), "fin"], M, col, bay=2.3)
    objs += structure("A", TOWER_A, A_FLOORS, (18.8, 35.4, 27.8, 47.4), 3, 2, M, col, crown=crown_a)
    objs += structure("B", TOWER_B, B_FLOORS, (42.3, 7.85, 49.3, 16.85), 2, 1, M, col, crown=crown_b)
    objs += podium(M, col)
    objs += foundation(M, col)
    root = enu_root(objs, "Building")
    print("triangles:", lib.tri_count(objs))
    if "--blend" in sys.argv:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(lib.OUT, "building.blend"))
    lib.export_glb(os.path.join(lib.OUT, "building_raw.glb"))
    return root


if __name__ == "__main__":
    main()
