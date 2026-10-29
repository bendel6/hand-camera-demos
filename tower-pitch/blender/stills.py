"""Cycles hero stills: assembles building + site + city context + trees/cars/people, archviz materials, physical
sky, and renders named camera presets.

Run:  /opt/venvs/blender/bin/python blender/stills.py <preset> [--res 3840x2160] [--samples 384] [--out path]
      /opt/venvs/blender/bin/python blender/stills.py --list
Inputs (built beforehand): blender/out/building.blend, site.blend, context_raw.glb, trees/*.glb.
"""
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import mathutils  # noqa: E402

import lib  # noqa: E402
import props  # noqa: E402
from build_building import FH, PODIUM_TOP, TOWER_A, TOWER_B  # noqa: E402

FRAME = json.load(open(os.path.join(lib.ROOT, "data", "site-frame.json")))
SITE_ROT = math.radians(90.0 - FRAME["x_axis_azimuth_true_deg"])
LAYOUT = json.load(open(os.path.join(lib.ROOT, "src", "content", "site-layout.json")))

# preset: camera (site frame), target, lens, shift_y, time-of-day, sun azimuth/elevation (deg), exposure
PRESETS = {
    "golden_street": dict(cam=(-16, -14.2, 1.6), tgt=(40, 30, 46), lens=14, shift_override=0.46, shift=0.3, tod="golden", sun=(248, 7), exp=0.2),
    "aerial_golden": dict(cam=(-300, -360, 210), tgt=(40, 30, 40), lens=55, shift=0.0, tod="golden", sun=(250, 9), exp=0.1),
    "day_front": dict(cam=(44, -17.5, 1.6), tgt=(44, 20, 1.6), lens=17, shift=0.36, tod="day", sun=(200, 42), exp=-0.2),
    "night_aerial": dict(cam=(260, -300, 170), tgt=(40, 32, 45), lens=50, shift=0.0, tod="night", sun=(250, -15), exp=1.2),
    "blue_hour": dict(cam=(135, -46, 9), tgt=(38, 30, 52), lens=24, shift=0.18, tod="blue", sun=(255, -3), exp=1.0),
    "garden": dict(cam=(79, 63, 1.7), tgt=(46, 28, 18), lens=17, shift=0.25, tod="day", sun=(215, 38), exp=-0.1),
    "top": dict(cam=(40, 0, 600), tgt=(40, 0.01, 0), lens=30, shift=0.0, tod="day", sun=(200, 45), exp=-0.2),
}


def site_root(name="SiteFrame"):
    e = bpy.data.objects.get(name)
    if e:
        return e
    e = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(e)
    e.rotation_euler[2] = SITE_ROT
    return e


def node_mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    return m, nt, out


# --------------------------------------------------------------------------------------------- materials
def archviz_glass(name, tint=(0.82, 0.88, 0.9), reflect=1.0):
    """Thin architectural glass: Fresnel-weighted mirror over a tinted transparent layer (no refraction offset)."""
    m, nt, out = node_mat(name)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    tr.inputs["Color"].default_value = (*tint, 1)
    gl = nt.nodes.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = 0.015
    fr = nt.nodes.new("ShaderNodeFresnel")
    fr.inputs["IOR"].default_value = 1.52
    mx = nt.nodes.new("ShaderNodeMixShader")
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = reflect
    nt.links.new(fr.outputs[0], mul.inputs[0])
    nt.links.new(mul.outputs[0], mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(gl.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    m.blend_method = "HASHED" if hasattr(m, "blend_method") else None
    return m


def interior_material(name, lit_frac, warm_strength, shop=False):
    """Room liner behind the glass: per-room colour and random lit rooms (cells of 3.6 x 3.3 m)."""
    m, nt, out = node_mat(name)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    cell = nt.nodes.new("ShaderNodeCombineXYZ")
    sizes = (8.0, 8.0, 4.6) if shop else (3.6, 3.6, FH)
    for i, (ax, sz) in enumerate(zip("XYZ", sizes)):
        d = nt.nodes.new("ShaderNodeMath")
        d.operation = "DIVIDE"
        d.inputs[1].default_value = sz
        nt.links.new(sep.outputs[ax], d.inputs[0])
        f = nt.nodes.new("ShaderNodeMath")
        f.operation = "FLOOR"
        nt.links.new(d.outputs[0], f.inputs[0])
        nt.links.new(f.outputs[0], cell.inputs[i])
    wn = nt.nodes.new("ShaderNodeTexWhiteNoise")
    wn.noise_dimensions = "3D"
    nt.links.new(cell.outputs[0], wn.inputs["Vector"])
    # colour variety of interiors
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.62, 0.55, 0.47, 1)
    ramp.color_ramp.elements[1].color = (0.82, 0.8, 0.76, 1)
    nt.links.new(wn.outputs["Value"], ramp.inputs["Fac"])
    lit = nt.nodes.new("ShaderNodeMath")
    lit.operation = "LESS_THAN"
    lit.inputs[1].default_value = lit_frac
    sep2 = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(wn.outputs["Color"], sep2.inputs[0])
    nt.links.new(sep2.outputs[0], lit.inputs[0])
    # vertical gradient inside a room (brighter near the ceiling light)
    fz = nt.nodes.new("ShaderNodeMath")
    fz.operation = "FRACT"
    dz = nt.nodes.new("ShaderNodeMath")
    dz.operation = "DIVIDE"
    dz.inputs[1].default_value = sizes[2]
    nt.links.new(sep.outputs["Z"], dz.inputs[0])
    nt.links.new(dz.outputs[0], fz.inputs[0])
    grad = nt.nodes.new("ShaderNodeMapRange")
    grad.inputs["To Min"].default_value = 0.45
    grad.inputs["To Max"].default_value = 1.2
    nt.links.new(fz.outputs[0], grad.inputs["Value"])
    em = nt.nodes.new("ShaderNodeMath")
    em.operation = "MULTIPLY"
    em.inputs[1].default_value = warm_strength
    em2 = nt.nodes.new("ShaderNodeMath")
    em2.operation = "MULTIPLY"
    nt.links.new(lit.outputs[0], em.inputs[0])
    nt.links.new(em.outputs[0], em2.inputs[0])
    nt.links.new(grad.outputs[0], em2.inputs[1])
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bs.inputs["Roughness"].default_value = 0.8
    nt.links.new(ramp.outputs["Color"], bs.inputs["Base Color"])
    bs.inputs["Emission Color"].default_value = (1.0, 0.72, 0.45, 1) if not shop else (1.0, 0.8, 0.6, 1)
    nt.links.new(em2.outputs[0], bs.inputs["Emission Strength"])
    nt.links.new(bs.outputs[0], out.inputs["Surface"])
    return m


def context_material(night):
    """Neighbourhood buildings: plaster with a window grid (Brick texture in facade UV space), lit windows at night."""
    m, nt, out = node_mat("STILL_context")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sp = nt.nodes.new("ShaderNodeSeparateXYZ")
    sn = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sp.inputs[0])
    nt.links.new(geo.outputs["Normal"], sn.inputs[0])
    # u = x * -ny + y * nx  (horizontal coordinate along the wall), v = z
    a = nt.nodes.new("ShaderNodeMath")
    a.operation = "MULTIPLY"
    nt.links.new(sp.outputs["X"], a.inputs[0])
    nt.links.new(sn.outputs["Y"], a.inputs[1])
    b = nt.nodes.new("ShaderNodeMath")
    b.operation = "MULTIPLY"
    nt.links.new(sp.outputs["Y"], b.inputs[0])
    nt.links.new(sn.outputs["X"], b.inputs[1])
    u = nt.nodes.new("ShaderNodeMath")
    u.operation = "SUBTRACT"
    nt.links.new(b.outputs[0], u.inputs[0])
    nt.links.new(a.outputs[0], u.inputs[1])
    uv = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(u.outputs[0], uv.inputs["X"])
    nt.links.new(sp.outputs["Z"], uv.inputs["Y"])
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset = 0.0
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Brick Width"].default_value = 1.55
    br.inputs["Row Height"].default_value = 1.65
    br.inputs["Mortar Size"].default_value = 0.78
    br.inputs["Mortar Smooth"].default_value = 0.0
    br.inputs["Color1"].default_value = (0.05, 0.06, 0.07, 1)
    br.inputs["Color2"].default_value = (0.09, 0.1, 0.11, 1)
    # plaster colour varies from building to building (40 m noise) and weathers slightly
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.025
    nt.links.new(geo.outputs["Position"], nz.inputs["Vector"])
    pr = nt.nodes.new("ShaderNodeValToRGB")
    pr.color_ramp.elements[0].color = (0.56, 0.5, 0.42, 1)
    pr.color_ramp.elements[1].color = (0.72, 0.7, 0.66, 1)
    mid = pr.color_ramp.elements.new(0.55)
    mid.color = (0.66, 0.6, 0.53, 1)
    nt.links.new(nz.outputs["Fac"], pr.inputs["Fac"])
    nt.links.new(pr.outputs["Color"], br.inputs["Mortar"])
    nt.links.new(uv.outputs[0], br.inputs["Vector"])
    # walls vs roofs
    roofmask = nt.nodes.new("ShaderNodeMath")
    roofmask.operation = "GREATER_THAN"
    roofmask.inputs[1].default_value = 0.6
    nt.links.new(sn.outputs["Z"], roofmask.inputs[0])
    col = nt.nodes.new("ShaderNodeMix")
    col.data_type = "RGBA"
    nt.links.new(roofmask.outputs[0], col.inputs["Factor"])
    nt.links.new(br.outputs["Color"], col.inputs["A"])
    col.inputs["B"].default_value = (0.32, 0.31, 0.3, 1)
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(col.outputs["Result"], bs.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(br.outputs["Fac"], rough.inputs["Value"])
    rough.inputs["To Min"].default_value = 0.15
    rough.inputs["To Max"].default_value = 0.85
    nt.links.new(rough.outputs[0], bs.inputs["Roughness"])
    if night:
        lit = nt.nodes.new("ShaderNodeMath")
        lit.operation = "GREATER_THAN"
        lit.inputs[1].default_value = 0.081
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(br.outputs["Color"], sep.inputs[0])
        nt.links.new(sep.outputs[0], lit.inputs[0])
        win = nt.nodes.new("ShaderNodeMath")
        win.operation = "SUBTRACT"
        win.inputs[0].default_value = 1.0
        nt.links.new(br.outputs["Fac"], win.inputs[1])
        e = nt.nodes.new("ShaderNodeMath")
        e.operation = "MULTIPLY"
        nt.links.new(lit.outputs[0], e.inputs[0])
        nt.links.new(win.outputs[0], e.inputs[1])
        e2 = nt.nodes.new("ShaderNodeMath")
        e2.operation = "MULTIPLY"
        e2.inputs[1].default_value = 1.6
        nt.links.new(e.outputs[0], e2.inputs[0])
        bs.inputs["Emission Color"].default_value = (1.0, 0.7, 0.42, 1)
        nt.links.new(e2.outputs[0], bs.inputs["Emission Strength"])
    nt.links.new(bs.outputs[0], out.inputs["Surface"])
    return m


def tune_materials(tod):
    night = tod in ("night", "blue")
    glass = archviz_glass("STILL_glass", reflect=1.0)
    rail = archviz_glass("STILL_rail", tint=(0.9, 0.95, 0.95), reflect=0.8)
    shop = archviz_glass("STILL_shopglass", tint=(0.9, 0.92, 0.9), reflect=0.9)
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        for slot in o.material_slots:
            m = slot.material
            if not m:
                continue
            if m.name == "M_Glass_Res":
                slot.material = glass
            elif m.name == "M_RailGlass":
                slot.material = rail
            elif m.name == "M_Glass_Shop":
                slot.material = shop
    # cladding: slightly brighter, anodised look
    for nm, col, metal, rough in (("M_Cladding", "#7a8089", 0.35, 0.38), ("M_Frame", "#5d636b", 0.4, 0.34),
                                  ("M_Fin", "#868c94", 0.45, 0.3), ("M_PodiumRed", "#7a2f2b", 0.15, 0.45)):
        m = bpy.data.materials.get(nm)
        if m:
            b = m.node_tree.nodes.get("Principled BSDF")
            b.inputs["Base Color"].default_value = (*lib.hex_rgb(col), 1)
            b.inputs["Metallic"].default_value = metal
            b.inputs["Roughness"].default_value = rough
    lamp = bpy.data.materials.get("M_LampHead")
    if lamp:
        lamp.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 30.0 if night else 0.0


def add_interiors(tod):
    """Room liners 5.5 m behind the glass on every residential floor, plus warm shop interiors in the podium."""
    from shapely.geometry import Polygon
    lit = {"day": 0.08, "golden": 0.22, "blue": 0.55, "night": 0.62}[tod]
    strength = {"day": 0.0, "golden": 3.0, "blue": 6.0, "night": 7.0}[tod]
    mat = interior_material("STILL_interior", lit, strength)
    smat = interior_material("STILL_shops", 0.95, {"day": 0.9, "golden": 2.2, "blue": 7.0, "night": 8.0}[tod], shop=True)
    root = site_root()
    acc = lib.MeshAccum("Interiors")
    for poly, floors in ((TOWER_A, 30), (TOWER_B, 16)):
        ring = Polygon(poly).buffer(-6.0, join_style=2)
        pts = list(ring.exterior.coords)[:-1]
        for i in range(floors):
            z0 = PODIUM_TOP + i * FH
            n = len(pts)
            for k in range(n):
                (ax, ay), (bx, by) = pts[k], pts[(k + 1) % n]
                # face outward (towards the glass)
                acc.poly([(bx, by, z0), (ax, ay, z0), (ax, ay, z0 + FH - 0.25), (bx, by, z0 + FH - 0.25)], mat)
    from build_building import PODIUM
    ring = Polygon(PODIUM).buffer(-7.0, join_style=2)
    for g in getattr(ring, "geoms", [ring]):
        pts = list(g.exterior.coords)[:-1]
        n = len(pts)
        for z0, z1 in ((0.0, 4.7), (5.0, 8.3)):
            for k in range(n):
                (ax, ay), (bx, by) = pts[k], pts[(k + 1) % n]
                acc.poly([(bx, by, z0), (ax, ay, z0), (ax, ay, z1), (bx, by, z1)], smat)
    o = acc.build()
    o.parent = root


# --------------------------------------------------------------------------------------------- scene parts
def append_blend(path, root_name):
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects]
    for o in dst.objects:
        if o is not None and o.name not in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.link(o)
    return bpy.data.objects.get(root_name)


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def tree_collections():
    cols = {}
    for k in ("Tree_plane", "Tree_plane2", "Tree_small", "Tree_cypress"):
        path = os.path.join(lib.OUT, "trees", f"{k}.glb")
        objs = import_glb(path)
        col = bpy.data.collections.new(f"COL_{k}")
        for o in objs:
            for c in o.users_collection:
                c.objects.unlink(o)
            col.objects.link(o)
            if o.type == "MESH":
                for slot in o.material_slots:
                    m = slot.material
                    if m and "leaves" in m.name:
                        m.surface_render_method = "DITHERED" if hasattr(m, "surface_render_method") else None
        cols[k] = col
    return cols


def instance(col, name, parent, loc, rot=0.0, scale=1.0):
    e = bpy.data.objects.new(name, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = col
    bpy.context.scene.collection.objects.link(e)
    e.parent = parent
    e.location = loc
    e.rotation_euler[2] = rot
    e.scale = (scale, scale, scale)
    return e


def add_trees(cols, rnd):
    root = site_root()
    for i, t in enumerate(LAYOUT["trees"]):
        kind = t["t"] if t["t"] in cols else None
        if not kind:
            continue
        instance(cols[kind], f"tree_{i}", root, (t["x"], t["y"], t["z"]), t["r"], t["s"])
    # real neighbourhood trees (three.js coords -> blender ENU)
    data = json.load(open(os.path.join(lib.ROOT, "data", "trees-near.json")))["trees"]
    c, s = math.cos(SITE_ROT), math.sin(SITE_ROT)
    for i, (x, y, z, sc) in enumerate(data):
        e, n = x, -z
        sx, sy = e * c + n * s, -e * s + n * c
        if -175 < sx < 265 and -62 < sy < 72:
            continue
        if math.hypot(sx - 40, sy - 30) > 700:
            continue
        e_ = instance(cols["Tree_plane2" if i % 3 else "Tree_plane"], f"ctree_{i}", None, (e, n, y),
                      rnd.uniform(0, 6.28), 0.75 + (sc or 1) * 0.35)


def add_cars(rnd, night, cam=None):
    root = site_root()
    protos = {k: props.car(k).build() for k in ("sedan", "suv", "hatch")}
    paint, nt, out = node_mat("STILL_carpaint")
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(oi.outputs["Color"], bs.inputs["Base Color"])
    bs.inputs["Metallic"].default_value = 0.55
    bs.inputs["Roughness"].default_value = 0.3
    bs.inputs["Coat Weight"].default_value = 1.0
    bs.inputs["Coat Roughness"].default_value = 0.03
    nt.links.new(bs.outputs[0], out.inputs["Surface"])
    for p in protos.values():
        for slot in p.material_slots:
            if slot.material and slot.material.name == "M_CarPaint":
                slot.material = paint
        # weld + smooth for nicer highlights
        bpy.context.view_layer.objects.active = p
        p.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.remove_doubles(threshold=0.004)
        bpy.ops.object.mode_set(mode="OBJECT")
        p.select_set(False)
        p.hide_render = True
        p.hide_viewport = True
    if night:
        for nm, strength in (("M_HeadLight", 25.0), ("M_TailLight", 12.0)):
            m = bpy.data.materials.get(nm)
            if m:
                m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = strength
    colours = ["#f2f2f0", "#1b1d20", "#8d9297", "#c4c7ca", "#2c3a52", "#6b1f22", "#3d4a3e", "#d8d2c4", "#4a4f57"]
    kinds = list(protos)
    for li, lane in enumerate(LAYOUT["car_lanes"]):
        x = -160.0 + rnd.uniform(0, 20)
        while x < 255:
            if cam and abs(x - cam[0]) < 26 and abs(lane["y"] - cam[1]) < 8:
                x += rnd.uniform(14, 40)
                continue
            k = kinds[rnd.randrange(3)]
            o = bpy.data.objects.new(f"car_{li}_{int(x)}", protos[k].data)
            bpy.context.scene.collection.objects.link(o)
            o.parent = root
            o.location = (x, lane["y"] + rnd.uniform(-0.2, 0.2), 0.0)
            o.color = (*lib.hex_rgb(rnd.choice(colours)), 1)
            x += rnd.uniform(14, 40)


def add_people(rnd):
    root = site_root()
    proto = props.person().build(smooth=True)
    m, nt, out = node_mat("STILL_person")
    va = nt.nodes.new("ShaderNodeVertexColor")
    va.layer_name = "Col"
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(va.outputs["Color"], sep.inputs[0])
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    ramp_top = nt.nodes.new("ShaderNodeValToRGB")
    ramp_top.color_ramp.interpolation = "CONSTANT"
    tops = ["#e8e4dc", "#2b2f36", "#8a2f2b", "#3d5a80", "#c9a66b", "#5b6b4a", "#1f1f22"]
    els = ramp_top.color_ramp.elements
    for i, c in enumerate(tops):
        e = els[i] if i < len(els) else els.new(i / len(tops))
        e.position = i / len(tops)
        e.color = (*lib.hex_rgb(c), 1)
    nt.links.new(oi.outputs["Random"], ramp_top.inputs["Fac"])
    pants = nt.nodes.new("ShaderNodeMix")
    pants.data_type = "RGBA"
    pants.inputs["A"].default_value = (*lib.hex_rgb("#22262c"), 1)
    pants.inputs["B"].default_value = (*lib.hex_rgb("#5a5047"), 1)
    nt.links.new(oi.outputs["Random"], pants.inputs["Factor"])
    skin = (*lib.hex_rgb("#c99a74"), 1)
    m1 = nt.nodes.new("ShaderNodeMix")
    m1.data_type = "RGBA"
    nt.links.new(sep.outputs[0], m1.inputs["Factor"])
    m1.inputs["A"].default_value = skin
    nt.links.new(ramp_top.outputs["Color"], m1.inputs["B"])
    m2 = nt.nodes.new("ShaderNodeMix")
    m2.data_type = "RGBA"
    nt.links.new(sep.outputs[1], m2.inputs["Factor"])
    nt.links.new(m1.outputs["Result"], m2.inputs["A"])
    nt.links.new(pants.outputs["Result"], m2.inputs["B"])
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bs.inputs["Roughness"].default_value = 0.75
    nt.links.new(m2.outputs["Result"], bs.inputs["Base Color"])
    nt.links.new(bs.outputs[0], out.inputs["Surface"])
    proto.data.materials.clear()
    proto.data.materials.append(m)
    proto.hide_render = True
    paths = LAYOUT["people_paths"] + LAYOUT["terrace_paths"]
    for pi, path in enumerate(paths):
        terrace = pi >= len(LAYOUT["people_paths"])
        for k in range(len(path) - 1):
            (ax, ay), (bx, by) = path[k], path[k + 1]
            L = math.hypot(bx - ax, by - ay)
            n = max(1, int(L / 11))
            for j in range(n):
                f = rnd.random()
                o = bpy.data.objects.new(f"person_{pi}_{k}_{j}", proto.data)
                bpy.context.scene.collection.objects.link(o)
                o.parent = root
                o.location = (ax + (bx - ax) * f, ay + (by - ay) * f + rnd.uniform(-1, 1), PODIUM_TOP if terrace else 0.15)
                o.rotation_euler[2] = math.atan2(by - ay, bx - ax) + (math.pi if rnd.random() < 0.5 else 0)
                o.scale = (1, 1, rnd.uniform(0.94, 1.06))


def add_street_lights(night):
    if not night:
        return
    root = site_root()
    for i, (x, y, h) in enumerate(LAYOUT["lamps"]):
        L = bpy.data.lights.new(f"lamp_{i}", "SPOT")
        L.energy = 2200
        L.color = (1.0, 0.78, 0.52)
        L.spot_size = math.radians(120)
        L.spot_blend = 0.6
        L.shadow_soft_size = 0.4
        o = bpy.data.objects.new(f"lamp_{i}", L)
        bpy.context.scene.collection.objects.link(o)
        o.parent = root
        o.location = (x, y, h - 0.3)


# --------------------------------------------------------------------------------------------- world + camera
def setup_world(tod, sun_az, sun_el):
    sc = bpy.context.scene
    w = bpy.data.worlds.new("STILL_world")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    sky = nt.nodes.new("ShaderNodeTexSky")
    try:
        sky.sky_type = "MULTIPLE_SCATTERING"
    except TypeError:
        sky.sky_type = "NISHITA"
    sky.sun_disc = False
    sky.sun_elevation = math.radians(max(sun_el, -4))
    sky.sun_rotation = math.radians(90 - sun_az)  # blender: 0 = +X (east), CCW; azimuth: clockwise from north
    sky.altitude = 470
    sky.air_density = 1.2
    sky.aerosol_density = 1.6 if tod != "day" else 1.0
    bg = nt.nodes["Background"]
    bg.inputs["Strength"].default_value = {"day": 0.22, "golden": 0.26, "blue": 0.9, "night": 0.06}[tod]
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    if tod == "night":
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["Factor"].default_value = 0.85
        mix.inputs["B"].default_value = (0.012, 0.016, 0.03, 1)
        nt.links.new(sky.outputs["Color"], mix.inputs["A"])
        nt.links.new(mix.outputs["Result"], bg.inputs["Color"])
    if sun_el > -1:
        sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
        sc.collection.objects.link(sun)
        sun.data.energy = {"day": 9.0, "golden": 7.5, "blue": 0.0, "night": 0.0}[tod]
        warm = {"day": (1.0, 0.95, 0.88), "golden": (1.0, 0.56, 0.3), "blue": (1, 1, 1), "night": (1, 1, 1)}[tod]
        sun.data.color = warm
        sun.data.angle = math.radians(0.6)
        az = math.radians(sun_az)
        el = math.radians(sun_el)
        d = mathutils.Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
        sun.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    if tod in ("night", "blue"):
        moon = bpy.data.objects.new("Moon", bpy.data.lights.new("Moon", "SUN"))
        sc.collection.objects.link(moon)
        moon.data.energy = 0.06 if tod == "night" else 0.0
        moon.data.color = (0.6, 0.7, 1.0)
        moon.rotation_euler = (math.radians(40), 0, math.radians(120))


def setup_camera(p):
    root = site_root()
    cd = bpy.data.cameras.new("Cam")
    cd.lens = p["lens"]
    cd.shift_y = p.get("shift_override", p["shift"])
    cd.clip_start = 0.3
    cd.clip_end = 20000
    cam = bpy.data.objects.new("Cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    cam.parent = root
    cam.location = p["cam"]
    direction = mathutils.Vector(p["tgt"]) - mathutils.Vector(p["cam"])
    if p.get("shift_override", p["shift"]) > 0:
        direction.z = 0  # keep verticals straight; the lens shift frames the towers
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam


def render(preset, res, samples, out):
    p = PRESETS[preset]
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.012
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.max_bounces = 10
    sc.cycles.transparent_max_bounces = 24
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.blur_glossy = 1.0
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = p["exp"]
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "16"
    sc.render.filepath = out
    sc.render.threads_mode = "FIXED"
    sc.render.threads = int(os.environ.get("RENDER_THREADS", "4"))
    bpy.ops.render.render(write_still=True)
    print("wrote", out)


def main():
    args = sys.argv[1:]
    if "--list" in args:
        print("\n".join(PRESETS))
        return
    preset = args[0]
    res = tuple(int(v) for v in (args[args.index("--res") + 1] if "--res" in args else "3840x2160").split("x"))
    samples = int(args[args.index("--samples") + 1]) if "--samples" in args else 384
    out = args[args.index("--out") + 1] if "--out" in args else os.path.join(lib.OUT, f"still_{preset}.png")
    p = PRESETS[preset]
    tod = p["tod"]
    night = tod in ("night", "blue")
    rnd = random.Random(11)
    bpy.ops.wm.open_mainfile(filepath=os.path.join(lib.OUT, "building.blend"))
    append_blend(os.path.join(lib.OUT, "site.blend"), "Site")
    before = bpy.data.objects.get("S_before")
    if before:
        before.hide_render = True
    ctx = import_glb(os.path.join(lib.OUT, "context_raw.glb"))
    cmat = context_material(night)
    ground = None
    for o in ctx:
        if o.type != "MESH":
            continue
        if o.name.startswith("ctx_terrain"):
            ground = o
            gm, nt, out_n = node_mat("STILL_ground")
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = bpy.data.images.load(os.path.join(lib.ROOT, "public", "textures", "ground.webp"))
            bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
            bs.inputs["Roughness"].default_value = 0.95
            hsv = nt.nodes.new("ShaderNodeHueSaturation")
            hsv.inputs["Value"].default_value = 0.8
            nt.links.new(tex.outputs["Color"], hsv.inputs["Color"])
            nt.links.new(hsv.outputs["Color"], bs.inputs["Base Color"])
            nt.links.new(bs.outputs[0], out_n.inputs["Surface"])
            o.data.materials.clear()
            o.data.materials.append(gm)
            o.location.z -= 0.03
        else:
            o.data.materials.clear()
            o.data.materials.append(cmat)
    tune_materials(tod)
    add_interiors(tod)
    cols = tree_collections()
    add_trees(cols, rnd)
    add_cars(rnd, night, p["cam"])
    add_people(rnd)
    add_street_lights(night)
    setup_world(tod, *p["sun"])
    setup_camera(p)
    if "--blend" in args:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(lib.OUT, f"stills_{preset}.blend"))
    render(preset, res, samples, out)


if __name__ == "__main__":
    main()
