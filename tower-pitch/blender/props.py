"""Procedural props: cars, trees, people, street furniture. Each returns a MeshAccum in local coords
(origin at ground centre, +X forward for cars/people). Exported as prototypes in props.glb and instanced in
three.js (InstancedMesh), so paint/clothing colours are per-instance and the materials stay white-based."""
import math
import random

from lib import MeshAccum, mat


def M():
    return {
        "paint": mat("M_CarPaint", "#ffffff", metal=0.6, rough=0.25),
        "cglass": mat("M_CarGlass", "#11161b", metal=0.2, rough=0.05),
        "tire": mat("M_Tire", "#1a1a1b", rough=0.85),
        "rim": mat("M_Rim", "#b8bcc0", metal=0.9, rough=0.3),
        "head": mat("M_HeadLight", "#f4f1e8", emit="#fff3d6", emit_strength=0.0, rough=0.2),
        "tail": mat("M_TailLight", "#7a0d0d", emit="#ff2a1a", emit_strength=0.0, rough=0.3),
        "trim": mat("M_CarTrim", "#202224", rough=0.5),
        "bark": mat("M_Bark", "#5b4a3c", rough=0.9),
        "leaf": mat("M_Leaf", "#ffffff", rough=0.75, vcol=True),
        "skin": mat("M_Person", "#ffffff", rough=0.7, vcol=True),
        "metal_dark": mat("M_StreetMetal", "#2e3236", metal=0.7, rough=0.4),
        "lamp": mat("M_LampHead", "#fff6e0", emit="#ffd9a0", emit_strength=0.0, rough=0.3),
        "wood": mat("M_Wood", "#8a6243", rough=0.6),
        "concrete": mat("M_Concrete", "#b8b4ac", rough=0.85),
    }


def loft(acc, sections, m, cap=True):
    """sections: list of (x, [(y,z), ...]) rings with equal point counts, built along +x."""
    for (xa, ra), (xb, rb) in zip(sections[:-1], sections[1:]):
        n = len(ra)
        for i in range(n):
            j = (i + 1) % n
            acc.poly([(xa, ra[i][0], ra[i][1]), (xa, ra[j][0], ra[j][1]),
                      (xb, rb[j][0], rb[j][1]), (xb, rb[i][0], rb[i][1])], m)
    if cap:
        x0, r0 = sections[0]
        acc.poly([(x0, y, z) for y, z in r0], m)
        x1, r1 = sections[-1]
        acc.poly([(x1, y, z) for y, z in reversed(r1)], m)


def ring(hw, z0, z1, top_hw=None, chamfer=0.08):
    """Rounded-rectangle-ish cross-section (8 pts), CCW when viewed from -x."""
    t = top_hw if top_hw is not None else hw
    c = chamfer
    return [(-hw + c, z0), (hw - c, z0), (hw, z0 + c), (t, z1 - c), (t - c, z1), (-t + c, z1), (-t, z1 - c),
            (-hw, z0 + c)][::-1]


def car(kind="sedan"):
    m = M()
    a = MeshAccum(f"Car_{kind}")
    if kind == "suv":
        L, W, belt, roof, gl0 = 4.75, 1.95, 1.08, 1.72, 0.55
        prof = [(0.0, 0.42, 0.95), (0.25, 0.35, 1.02), (1.1, 0.33, 1.1), (3.9, 0.33, 1.12), (4.55, 0.35, 1.08),
                (4.75, 0.42, 0.98)]
        cab = [(1.3, belt), (1.95, roof), (4.35, roof), (4.6, belt)]
    elif kind == "hatch":
        L, W, belt, roof, gl0 = 4.1, 1.8, 0.95, 1.48, 0.45
        prof = [(0.0, 0.32, 0.72), (0.2, 0.27, 0.86), (0.95, 0.25, 0.96), (3.6, 0.25, 0.98), (4.0, 0.3, 0.95),
                (4.1, 0.36, 0.86)]
        cab = [(1.25, belt), (2.05, roof), (3.75, roof), (4.02, belt)]
    else:
        L, W, belt, roof, gl0 = 4.75, 1.85, 0.96, 1.44, 0.45
        prof = [(0.0, 0.32, 0.68), (0.2, 0.27, 0.82), (0.95, 0.25, 0.95), (3.85, 0.25, 0.98), (4.55, 0.3, 0.9),
                (4.75, 0.36, 0.8)]
        cab = [(1.45, belt), (2.25, roof), (3.55, roof), (4.2, belt)]
    hw = W / 2
    secs = [(x - L / 2, ring(hw - (0.06 if i in (0, len(prof) - 1) else 0), z0, z1, chamfer=0.1))
            for i, (x, z0, z1) in enumerate(prof)]
    loft(a, secs, m["paint"])
    # greenhouse: glass sides with painted roof
    (xa, za), (xb, zb), (xc, zc), (xd, zd) = [(x - L / 2, z) for x, z in cab]
    lo, hi = hw - 0.05, hw - 0.2
    P = {"a0": (xa, -lo, za), "a1": (xa, lo, za), "b0": (xb, -hi, zb), "b1": (xb, hi, zb),
         "c0": (xc, -hi, zc), "c1": (xc, hi, zc), "d0": (xd, -lo, zd), "d1": (xd, lo, zd)}
    a.poly([P["a0"], P["a1"], P["b1"], P["b0"]], m["cglass"])      # windscreen
    a.poly([P["c0"], P["c1"], P["d1"], P["d0"]], m["cglass"])      # rear window
    a.poly([P["b0"], P["b1"], P["c1"], P["c0"]], m["paint"])       # roof
    a.poly([P["a1"], P["d1"], P["c1"], P["b1"]], m["cglass"])      # left side
    a.poly([P["d0"], P["a0"], P["b0"], P["c0"]], m["cglass"])      # right side
    # wheels
    for wx in (0.78 * L / 2 - 0.1, -0.78 * L / 2 + 0.25):
        for side in (-1, 1):
            cyl(a, wx, side * (hw - 0.12), 0.33, 0.33, 0.24, m["tire"], axis="y", n=12)
            cyl(a, wx, side * (hw - 0.0), 0.33, 0.2, 0.02, m["rim"], axis="y", n=12)
    # lights
    zl = prof[0][2] - 0.1
    for side in (-1, 1):
        a.box(-L / 2 - 0.02, side * (hw - 0.45) - 0.22, zl - 0.06, -L / 2 + 0.06, side * (hw - 0.45) + 0.22,
              zl + 0.05, m["tail"])
        a.box(L / 2 - 0.08, side * (hw - 0.42) - 0.2, prof[-1][2] - 0.16, L / 2 + 0.02, side * (hw - 0.42) + 0.2,
              prof[-1][2] - 0.07, m["head"])
    a.box(L / 2 - 0.05, -0.45, 0.32, L / 2 + 0.01, 0.45, 0.5, m["trim"])
    return a


def cyl(acc, cx, cy, cz, r, length, m, axis="z", n=10, caps=True):
    pts = [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    h = length / 2

    def P(u, v, w):
        if axis == "y":
            return (cx + u, cy + w, cz + v)
        if axis == "x":
            return (cx + w, cy + u, cz + v)
        return (cx + u, cy + v, cz + w)

    for i in range(n):
        (u0, v0), (u1, v1) = pts[i], pts[(i + 1) % n]
        acc.poly([P(u0, v0, -h), P(u1, v1, -h), P(u1, v1, h), P(u0, v0, h)], m)
    if caps:
        acc.poly([P(u, v, h) for u, v in pts], m)
        acc.poly([P(u, v, -h) for u, v in reversed(pts)], m)


def cone_trunk(acc, x, y, z0, z1, r0, r1, m, n=7):
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        acc.poly([(x + r0 * math.cos(a0), y + r0 * math.sin(a0), z0), (x + r0 * math.cos(a1), y + r0 * math.sin(a1), z0),
                  (x + r1 * math.cos(a1), y + r1 * math.sin(a1), z1), (x + r1 * math.cos(a0), y + r1 * math.sin(a0), z1)],
                 m)


ICO = None


def icosphere(subdiv=1):
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    v = [tuple(c / math.sqrt(sum(cc * cc for cc in p)) for c in p) for p in v]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
         (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
         (8, 6, 7), (9, 8, 1)]
    for _ in range(subdiv):
        cache = {}
        nf = []

        def mid(i, j):
            k = (min(i, j), max(i, j))
            if k not in cache:
                p = [(a + b) / 2 for a, b in zip(v[i], v[j])]
                ln = math.sqrt(sum(c * c for c in p))
                v.append(tuple(c / ln for c in p))
                cache[k] = len(v) - 1
            return cache[k]

        for a_, b_, c_ in f:
            ab, bc, ca = mid(a_, b_), mid(b_, c_), mid(c_, a_)
            nf += [(a_, ab, ca), (b_, bc, ab), (c_, ca, bc), (ab, bc, ca)]
        f = nf
    return v, f


def blob(acc, cx, cy, cz, rx, ry, rz, m, col, rnd, subdiv=1, jitter=0.18):
    v, f = icosphere(subdiv)
    pts, cols = [], []
    for x, y, z in v:
        k = 1 + jitter * (rnd.random() - 0.5) * 2
        pts.append((cx + x * rx * k, cy + y * ry * k, cz + z * rz * k))
        shade = 0.72 + 0.28 * (z * 0.5 + 0.5)  # lighter on top, darker underneath (fake self-shadowing)
        cols.append((col[0] * shade, col[1] * shade, col[2] * shade, 1.0))
    acc.mesh(pts, f, m, cols)


def srgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def tree(kind="plane", seed=1):
    m = M()
    rnd = random.Random(seed)
    a = MeshAccum(f"Tree_{kind}")
    if kind == "cypress":
        cone_trunk(a, 0, 0, 0, 1.5, 0.16, 0.12, m["bark"])
        greens = [srgb("#2f4a24"), srgb("#3a5a2b"), srgb("#28401f")]
        for i in range(7):
            z = 1.6 + i * 1.25
            r = 1.25 * (1 - i / 8.5)
            blob(a, rnd.uniform(-0.1, 0.1), rnd.uniform(-0.1, 0.1), z, r, r, 1.1, m["leaf"], rnd.choice(greens), rnd)
        return a
    if kind == "small":
        cone_trunk(a, 0, 0, 0, 2.2, 0.12, 0.08, m["bark"])
        greens = [srgb("#6f8f3a"), srgb("#5d7d31"), srgb("#86a24a")]
        for i in range(5):
            ang = rnd.uniform(0, 2 * math.pi)
            d = rnd.uniform(0.2, 0.9)
            blob(a, d * math.cos(ang), d * math.sin(ang), 2.8 + rnd.uniform(-0.3, 0.6), 1.2, 1.2, 1.0, m["leaf"],
                 rnd.choice(greens), rnd)
        return a
    if kind == "shrub":
        greens = [srgb("#4c6b2d"), srgb("#5c7d35"), srgb("#3f5b26")]
        for i in range(4):
            ang = i * math.pi / 2 + rnd.uniform(-0.4, 0.4)
            blob(a, 0.35 * math.cos(ang), 0.35 * math.sin(ang), 0.45, 0.6, 0.6, 0.5, m["leaf"], rnd.choice(greens),
                 rnd, subdiv=1)
        return a
    # plane / linden street tree: trunk, 4 limbs, 9 canopy clusters
    cone_trunk(a, 0, 0, 0, 3.4, 0.26, 0.18, m["bark"])
    greens = [srgb("#4f6e2c"), srgb("#5f8034"), srgb("#3f5d25"), srgb("#6b8b3c")]
    for i in range(4):
        ang = i * math.pi / 2 + rnd.uniform(-0.3, 0.3)
        ex, ey = 1.6 * math.cos(ang), 1.6 * math.sin(ang)
        a.poly([(0.12 * math.cos(ang + 1.6), 0.12 * math.sin(ang + 1.6), 3.2), (0.12 * math.cos(ang - 1.6),
                0.12 * math.sin(ang - 1.6), 3.2), (ex, ey, 6.0)], m["bark"])
    blob(a, 0, 0, 7.4, 2.6, 2.6, 2.2, m["leaf"], rnd.choice(greens), rnd, subdiv=2)
    for i in range(8):
        ang = 2 * math.pi * i / 8 + rnd.uniform(-0.3, 0.3)
        d = rnd.uniform(1.8, 2.6)
        r = rnd.uniform(1.4, 2.0)
        blob(a, d * math.cos(ang), d * math.sin(ang), rnd.uniform(5.4, 7.6), r, r, r * 0.85, m["leaf"],
             rnd.choice(greens), rnd, subdiv=1)
    return a


def person():
    """Stylised walking figure, 1.75 m. Vertex colour R/G/B channels carry clothing zones (tinted per instance in
    three.js); alpha encodes the limb for the walk-cycle vertex shader: 0.0 body, 0.25 left leg, 0.5 right leg,
    0.75 left arm, 1.0 right arm."""
    m = M()
    a = MeshAccum("Person")
    TOP, PANTS, SKIN = (1, 0, 0), (0, 1, 0), (0, 0, 1)

    def part(fn, zone, limb):
        before = len(a.cols)
        fn()
        for i in range(before, len(a.cols)):
            a.cols[i] = (*zone, limb)
        a.has_col = True

    rnd = random.Random(3)
    part(lambda: blob(a, 0, 0, 1.63, 0.1, 0.09, 0.12, m["skin"], (1, 1, 1), rnd, subdiv=1, jitter=0.0), SKIN, 0.0)
    part(lambda: cone_trunk(a, 0, 0, 0.95, 1.5, 0.15, 0.19, m["skin"], n=8), TOP, 0.0)
    part(lambda: a.box(-0.1, -0.2, 1.38, 0.1, 0.2, 1.5, m["skin"]), TOP, 0.0)
    part(lambda: cone_trunk(a, 0, 0, 0.85, 0.98, 0.16, 0.15, m["skin"], n=8), PANTS, 0.0)
    for side, limb in ((-1, 0.25), (1, 0.5)):
        part(lambda s=side: cone_trunk(a, 0, s * 0.09, 0.04, 0.9, 0.06, 0.085, m["skin"], n=6), PANTS, limb)
        part(lambda s=side: a.box(-0.06, s * 0.09 - 0.05, 0.0, 0.16, s * 0.09 + 0.05, 0.07, m["skin"]), PANTS, limb)
    for side, limb in ((-1, 0.75), (1, 1.0)):
        part(lambda s=side: cone_trunk(a, 0, s * 0.23, 0.82, 1.46, 0.04, 0.055, m["skin"], n=6), TOP, limb)
    return a


def street_lamp():
    m = M()
    a = MeshAccum("StreetLamp")
    cyl(a, 0, 0, 3.0, 0.07, 6.0, m["metal_dark"], n=8)
    a.box(-0.05, -0.05, 5.9, 1.2, 0.05, 6.0, m["metal_dark"])
    a.box(0.7, -0.18, 5.82, 1.5, 0.18, 5.92, m["metal_dark"])
    a.box(0.75, -0.14, 5.78, 1.45, 0.14, 5.82, m["lamp"])
    return a


def bollard_light():
    m = M()
    a = MeshAccum("Bollard")
    cyl(a, 0, 0, 0.45, 0.08, 0.9, m["metal_dark"], n=8)
    cyl(a, 0, 0, 0.8, 0.085, 0.12, m["lamp"], n=8, caps=False)
    return a


def bench():
    m = M()
    a = MeshAccum("Bench")
    a.box(-0.9, -0.25, 0.0, -0.8, 0.25, 0.42, m["concrete"])
    a.box(0.8, -0.25, 0.0, 0.9, 0.25, 0.42, m["concrete"])
    for k in range(5):
        y = -0.24 + k * 0.1
        a.box(-1.0, y, 0.42, 1.0, y + 0.08, 0.46, m["wood"])
    return a
