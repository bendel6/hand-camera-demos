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
B_SPLIT_X = 50.5  # fin zone / framed balcony zone boundary on Tower B


def crown_a(x, y):
    """Tower A crown: peak +115.0 at the SW corner, concave fall towards NE (+110.6)."""
    f = ((35.8 - x) / 25.0 + (56.4 - y) / 30.0) / 2
    f = min(max(f, 0.0), 1.0)
    return 109.8 + 5.2 * f ** 1.25


def crown_b(x, y):
    """Tower B crown: peak +68.0 at the fin/frame boundary, frame falls east to +66.0, fins step down west."""
    if x >= B_SPLIT_X:
        return 68.0 - 2.0 * ((x - B_SPLIT_X) / (71.1 - B_SPLIT_X)) ** 0.8
    return 68.0 - 3.4 * ((B_SPLIT_X - x) / (B_SPLIT_X - 36.9)) ** 1.1


# ------------------------------------------------------------------------------------------------ materials
def materials():
    M = {}
    M["clad"] = mat("M_Cladding", "#5b6068", metal=0.15, rough=0.5)
    M["frame"] = mat("M_Frame", "#4a4f57", metal=0.2, rough=0.45, normal="ribs_normal.png",
                     tex_scale=2.4, normal_strength=0.6)
    M["fin"] = mat("M_Fin", "#767b83", metal=0.2, rough=0.42)
    M["slab_edge"] = mat("M_BalconySlab", "#cfcdc7", rough=0.65)
    M["spandrel"] = mat("M_Spandrel", "#2c3137", metal=0.4, rough=0.3)
    M["sill"] = mat("M_Sill", "#9a9ea3", metal=0.1, rough=0.55)
    M["mullion"] = mat("M_Mullion", "#2a2d31", metal=0.7, rough=0.35)
    M["glass_res"] = mat("M_Glass_Res", "#1d2a33", metal=0.0, rough=0.04)
    M["rail_glass"] = mat("M_RailGlass", "#a9c2c9", rough=0.05, alpha=0.28)
    M["rail"] = mat("M_RailMetal", "#8d9298", metal=0.85, rough=0.3)
    M["divider"] = mat("M_Divider", "#33383f", metal=0.5, rough=0.35)
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
    """Wall slab between u0..u1 / w0..w1 whose top follows ztop_fn(x, y) (sloped / concave crown)."""
    us = [u0 + (u1 - u0) * i / steps for i in range(steps + 1)]
    for i in range(steps):
        ua, ub = us[i], us[i + 1]
        xa, ya, _ = to_world(p0, d, n, ua, 0, 0)
        xb, yb, _ = to_world(p0, d, n, ub, 0, 0)
        za, zb = ztop_fn(xa, ya), ztop_fn(xb, yb)
        for w in (w1, w0):  # front (w1) and back (w0) faces
            pa, pb = to_world(p0, d, n, ua, w, zbot), to_world(p0, d, n, ub, w, zbot)
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
        q = [to_world(p0, d, n, u, w0, zbot), to_world(p0, d, n, u, w1, zbot),
             to_world(p0, d, n, u, w1, zt), to_world(p0, d, n, u, w0, zt)]
        acc.poly(q if s > 0 else q[::-1], m)


# ------------------------------------------------------------------------------------------------ facades
def balcony_zone(F, G, M, p0, d, n, u0, u1, z0, floors, crown, post0=True, post1=True):
    """Framed balcony zone between u0..u1 of a face. F: facade accumulator, G: glazing accumulator."""
    fw = 1.2
    w_glass, w_front = -1.5, 0.3
    ztop = z0 + floors * FH
    a = u0 + (fw if post0 else 0.0)
    b = u1 - (fw if post1 else 0.0)
    # frame posts rising to the crown
    for on, (pa, pb) in ((post0, (u0, u0 + fw)), (post1, (u1 - fw, u1))):
        if on:
            fprofile(F, p0, d, n, pa, pb, w_glass, w_front, z0, crown, M["frame"], steps=2)
    # crown panel (parapet) across the zone, sloped/concave top
    fprofile(F, p0, d, n, a, b, -0.25, w_front, ztop, crown, M["frame"], steps=14)
    # LED line tracing the crown's top edge (lit at night)
    steps = 14
    for k in range(steps):
        ua = a + (b - a) * k / steps
        ub = a + (b - a) * (k + 1) / steps
        xa, ya, _ = to_world(p0, d, n, ua, 0, 0)
        xb, yb, _ = to_world(p0, d, n, ub, 0, 0)
        za, zb = crown(xa, ya) - 0.25, crown(xb, yb) - 0.25
        F.poly([to_world(p0, d, n, ua, w_front + 0.012, za - 0.1), to_world(p0, d, n, ub, w_front + 0.012, zb - 0.1),
                to_world(p0, d, n, ub, w_front + 0.012, zb), to_world(p0, d, n, ua, w_front + 0.012, za)], M["led"])
    # glazing line + mullions + floor spandrels
    fquad(G, p0, d, n, a, b, w_glass, z0, ztop, M["glass_res"])
    nm = max(2, int((b - a) / 1.5))
    for k in range(1, nm):
        u = a + (b - a) * k / nm
        fbox(F, p0, d, n, u - 0.035, u + 0.035, w_glass, w_glass + 0.1, z0, ztop, M["mullion"], skip=("-z", "+z"))
    span = b - a
    ndiv = max(1, round(span / 3.6))
    for i in range(floors + 1):
        z = z0 + i * FH
        # slab edge band (balcony slab cantilever)
        if i > 0:
            fbox(F, p0, d, n, a, b, w_glass, 0.05, z - 0.28, z, M["slab_edge"])
        fbox(F, p0, d, n, a, b, w_glass + 0.01, w_glass + 0.08, z - 0.3, z + 0.12, M["spandrel"], skip=("-z", "+z"))
        if i == floors:
            break
        # downlights in the soffit of the balcony above (one per apartment bay)
        zs = z + FH - 0.285
        for k in range(ndiv):
            uc = a + span * (k + 0.5) / ndiv
            q = [to_world(p0, d, n, uc - 0.16, -0.78, zs), to_world(p0, d, n, uc + 0.16, -0.78, zs),
                 to_world(p0, d, n, uc + 0.16, -0.46, zs), to_world(p0, d, n, uc - 0.16, -0.46, zs)]
            F.poly(q, M["soffit"])  # faces down
        # glass balustrade + top rail
        fquad(G, p0, d, n, a, b, -0.02, z, z + 1.08, M["rail_glass"])
        fbox(F, p0, d, n, a, b, -0.06, 0.0, z + 1.06, z + 1.12, M["rail"])
        # triangular privacy dividers between apartments
        for k in range(1, ndiv):
            u = a + span * k / ndiv
            t = 0.04
            tri = [(w_glass, z), (-0.05, z), (w_glass, z + FH - 0.3)]
            for side in (-t, t):
                pts = [to_world(p0, d, n, u + side, w, zz) for w, zz in tri]
                F.poly(pts if side > 0 else pts[::-1], M["divider"])
            # hypotenuse face
            (wa, za), (wb, zb) = tri[1], tri[2]
            F.poly([to_world(p0, d, n, u - t, wa, za), to_world(p0, d, n, u + t, wa, za),
                    to_world(p0, d, n, u + t, wb, zb), to_world(p0, d, n, u - t, wb, zb)], M["divider"])


def fin_zone(F, G, M, p0, d, n, u0, u1, z0, floors, crown, corner0=True, corner1=True):
    """Vertical-fin zone between u0..u1: fins rise to the crown in steps, windows with sills between."""
    w_glass = -0.6
    ztop = z0 + floors * FH
    span = u1 - u0
    nb = max(1, round(span / 3.5))
    fin_us = [u0 + span * k / nb for k in range(nb + 1)]
    fins = []
    for k, u in enumerate(fin_us):
        if k == 0:
            fins.append((u, u + (1.0 if corner0 else 0.25)))
        elif k == nb:
            fins.append((u - (1.0 if corner1 else 0.25), u))
        else:
            fins.append((u - 0.25, u + 0.25))
    for fa, fb in fins:
        x, y, _ = to_world(p0, d, n, (fa + fb) / 2, 0, 0)
        top = crown(x, y) + 1.6
        fbox(F, p0, d, n, fa, fb, w_glass, 0.75, z0, top, M["fin"])
        uc = (fa + fb) / 2
        F.poly([to_world(p0, d, n, uc - 0.05, 0.762, top - 8.0), to_world(p0, d, n, uc + 0.05, 0.762, top - 8.0),
                to_world(p0, d, n, uc + 0.05, 0.762, top - 0.2), to_world(p0, d, n, uc - 0.05, 0.762, top - 0.2)], M["led"])
    fquad(G, p0, d, n, u0, u1, w_glass, z0, ztop, M["glass_res"])
    for k in range(nb):
        a, b = fins[k][1], fins[k + 1][0]
        bw = b - a
        # crown infill between fins: dark recessed panel to just below the lower neighbouring fin top
        xa, ya, _ = to_world(p0, d, n, a, 0, 0)
        xb, yb, _ = to_world(p0, d, n, b, 0, 0)
        infill_top = min(crown(xa, ya), crown(xb, yb)) - 0.9
        if infill_top > ztop:
            fbox(F, p0, d, n, a, b, w_glass, w_glass + 0.15, ztop, infill_top, M["spandrel"])
        for i in range(floors):
            z = z0 + i * FH
            fbox(F, p0, d, n, a, b, w_glass, -0.42, z, z + 0.2, M["sill"])           # light sill band
            fbox(F, p0, d, n, a, b, w_glass, w_glass + 0.08, z + FH - 0.32, z + FH, M["spandrel"], skip=("-z",))
            fbox(F, p0, d, n, b - bw * 0.34, b, w_glass, w_glass + 0.06, z + 0.2, z + FH - 0.32,
                 M["spandrel"], skip=("-z", "+z"))                                   # solid panel beside window
            fbox(F, p0, d, n, a + bw * 0.33 - 0.03, a + bw * 0.33 + 0.03, w_glass, w_glass + 0.1,
                 z + 0.2, z + FH - 0.32, M["mullion"], skip=("-z", "+z"))
        fbox(F, p0, d, n, a, b, w_glass, w_glass + 0.2, ztop - 0.3, ztop, M["spandrel"])


def tower(T, poly, floors, crown, faces, M, col):
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
            fin_zone(F, G, M, p0, d, n, 0, L, z0, floors, crown)
        elif spec == "bal":
            balcony_zone(F, G, M, p0, d, n, 0, L, z0, floors, crown)
        else:
            _, xs, first = spec
            us = abs(xs - p0[0])
            if first == "fin":
                fin_zone(F, G, M, p0, d, n, 0, us, z0, floors, crown, corner1=False)
                balcony_zone(F, G, M, p0, d, n, us, L, z0, floors, crown, post0=True)
            else:
                balcony_zone(F, G, M, p0, d, n, 0, us, z0, floors, crown, post1=True)
                fin_zone(F, G, M, p0, d, n, us, L, z0, floors, crown, corner0=False)
    objs = []
    for k in dirs:
        for a in accs[k]:
            objs.append(a.build(col))
    # roof slab + membrane + plant + lift overrun
    shp = Polygon(poly).buffer(-0.4, join_style=2)
    roof = MeshAccum(f"{T}_crown")
    roof.prism(list(shp.exterior.coords)[:-1], ztop - 0.3, ztop + 0.05, M["roof"])
    cx, cy = shp.centroid.x, shp.centroid.y
    roof.box(cx - 3, cy - 2.5, ztop, cx + 3, cy + 2.5, ztop + 2.4, M["plant"])
    roof.box(cx + 3.5, cy - 1.5, ztop, cx + 6.5, cy + 1.5, ztop + 1.8, M["plant"])
    roof.box(cx - 7.0, cy - 1.2, ztop, cx - 4.5, cy + 1.2, ztop + 1.4, M["plant"])
    objs.append(roof.build(col))
    return objs


# ------------------------------------------------------------------------------------------------ structure
def structure(T, poly, floors, core_rect, n_lifts, n_stairs, M, col, z_base=PODIUM_TOP):
    ztop = z_base + floors * FH
    shp = Polygon(poly)
    slabs = MeshAccum(f"{T}_slabs")
    inner = list(shp.buffer(-0.3, join_style=2).exterior.coords)[:-1]
    for i in range(1, floors + 1):
        z = z_base + i * FH
        slabs.prism(inner, z - 0.25, z, M["concrete"])
    cols = MeshAccum(f"{T}_columns")
    ring = shp.buffer(-1.6, join_style=2).exterior
    npts = max(4, int(ring.length / 7.0))
    for k in range(npts):
        p = ring.interpolate(k * ring.length / npts)
        cols.box(p.x - 0.4, p.y - 0.4, z_base, p.x + 0.4, p.y + 0.4, ztop - 0.25, M["concrete"], skip=("-z", "+z"))
    x0, y0, x1, y1 = core_rect
    t = 0.35
    core = MeshAccum(f"{T}_core")
    zc0, zc1 = B_LEVELS[-1], ztop + 4.2
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
            piers = [(35.0 - p0[0], 36.8 - p0[0]), (52.0 - p0[0], 53.8 - p0[0])]
        lobby = (piers[0][1], piers[1][0]) if piers else None
        for u0, u1 in piers:
            fbox(F, p0, d, nn, u0, u1, -0.35, 0.35, 0, 8.3, M["red"])
        # mid band, interrupted over the double-height lobby
        segs = [(-0.15, L + 0.15)] if not lobby else [(-0.15, lobby[0]), (lobby[1], L + 0.15)]
        for a, b in segs:
            fbox(F, p0, d, nn, a, b, -0.35, 0.12, 4.6, 5.55, M["red"])
        if lobby:
            fbox(F, p0, d, nn, lobby[0], lobby[1], -0.6, -0.3, 5.0, 5.18, M["mullion"])
        # curtain wall glass + mullions + transoms
        fquad(G, p0, d, nn, 0, L, -0.35, 0.0, 8.3, M["glass_shop"])
        nm = max(1, int(L / 1.5))
        for k in range(nm + 1):
            u = L * k / nm
            fbox(F, p0, d, nn, u - 0.04, u + 0.04, -0.35, -0.2, 0.0, 8.3, M["mullion"], skip=("-z", "+z"))
        for z in (0.0, 3.4, 7.3):
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
                  [("split", B_SPLIT_X, "fin"), "bal", "fin", "bal", ("split", B_SPLIT_X, "bal"), "fin"], M, col)
    objs += structure("A", TOWER_A, A_FLOORS, (18.8, 35.4, 27.8, 47.4), 3, 2, M, col)
    objs += structure("B", TOWER_B, B_FLOORS, (42.3, 7.85, 49.3, 16.85), 2, 1, M, col)
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
