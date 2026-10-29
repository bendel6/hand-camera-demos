"""Shared helpers for the scripted Blender build: geometry accumulation, materials, export.

Geometry is accumulated per node name into a MeshAccum (one Blender object per node, one material slot per
material) so the GLB stays at a sane draw-call count while keeping the named layers the web app animates.
Coordinates are the site frame (metres): +X along Kazbegi Ave, +Y into the plot, +Z up.
"""
import math
import os

import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "blender", "out")
TEX = os.path.join(ROOT, "blender", "textures")
os.makedirs(OUT, exist_ok=True)
os.makedirs(TEX, exist_ok=True)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    return scene


# ---------------------------------------------------------------------------------------------------------------
# Geometry accumulation


class MeshAccum:
    """Collects quads/tris for one object, split by material, with metre-based box-projected UVs."""

    def __init__(self, name):
        self.name = name
        self.verts = []
        self.faces = []
        self.face_mat = []
        self.uvs = []  # per-loop
        self.cols = []  # per-loop RGBA (optional vertex colour)
        self.mats = []
        self.has_col = False

    def _mat_index(self, mat):
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def poly(self, pts, mat, uv=None, col=None):
        """Add one polygon (list of 3D points, CCW seen from the front)."""
        base = len(self.verts)
        self.verts.extend(pts)
        self.faces.append(tuple(range(base, base + len(pts))))
        self.face_mat.append(self._mat_index(mat))
        if uv is None:
            uv = box_uv(pts)
        self.uvs.extend(uv)
        if col is not None:
            self.has_col = True
        c = col if col is not None else (1.0, 1.0, 1.0, 1.0)
        self.cols.extend([c] * len(pts))

    def mesh(self, pts, tris, mat, cols=None):
        """Shared-vertex triangle mesh (smooth-shadable). cols: per-vertex RGBA or None."""
        base = len(self.verts)
        self.verts.extend(pts)
        mi = self._mat_index(mat)
        for t in tris:
            self.faces.append(tuple(base + i for i in t))
            self.face_mat.append(mi)
            self.uvs.extend([(pts[i][0], pts[i][2]) for i in t])
            if cols is not None:
                self.has_col = True
                self.cols.extend([cols[i] for i in t])
            else:
                self.cols.extend([(1.0, 1.0, 1.0, 1.0)] * len(t))

    def box(self, x0, y0, z0, x1, y1, z1, mat, skip=(), col=None):
        """Axis-aligned box. skip: subset of {'-x','+x','-y','+y','-z','+z'} faces to omit."""
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        if z0 > z1:
            z0, z1 = z1, z0
        p = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        quads = {
            "-z": (0, 3, 2, 1), "+z": (4, 5, 6, 7),
            "-y": (0, 1, 5, 4), "+y": (2, 3, 7, 6),
            "-x": (3, 0, 4, 7), "+x": (1, 2, 6, 5),
        }
        for k, q in quads.items():
            if k in skip:
                continue
            self.poly([p[i] for i in q], mat, col=col)

    def obox(self, cx, cy, z0, length, depth, height, ang, mat, col=None, skip=()):
        """Oriented box: centred at (cx, cy) in plan, 'length' along direction ang (radians), 'depth' across."""
        ca, sa = math.cos(ang), math.sin(ang)
        hl, hd = length / 2, depth / 2
        corners = [(-hl, -hd), (hl, -hd), (hl, hd), (-hl, hd)]
        pts = [(cx + u * ca - v * sa, cy + u * sa + v * ca) for u, v in corners]
        self.prism(pts, z0, z0 + height, mat, col=col, skip=skip)

    def prism(self, poly2d, z0, z1, mat, col=None, cap_mat=None, skip=(), walls=True):
        """Extrude a CCW 2D polygon (convex or not; caps use the n-gon) from z0 to z1."""
        n = len(poly2d)
        cap = cap_mat or mat
        if "-z" not in skip:
            self.poly([(x, y, z0) for x, y in reversed(poly2d)], cap, col=col)
        if "+z" not in skip:
            self.poly([(x, y, z1) for x, y in poly2d], cap, col=col)
        if walls:
            for i in range(n):
                (ax, ay), (bx, by) = poly2d[i], poly2d[(i + 1) % n]
                self.poly([(ax, ay, z0), (bx, by, z0), (bx, by, z1), (ax, ay, z1)], mat, col=col)

    def merge(self, other, offset=(0, 0, 0), rot=0.0, scale=1.0):
        """Append another accumulator's geometry transformed (rotation about Z)."""
        ca, sa = math.cos(rot), math.sin(rot)
        base = len(self.verts)
        for x, y, z in other.verts:
            x, y, z = x * scale, y * scale, z * scale
            self.verts.append((x * ca - y * sa + offset[0], x * sa + y * ca + offset[1], z + offset[2]))
        for f, mi in zip(other.faces, other.face_mat):
            self.faces.append(tuple(i + base for i in f))
            self.face_mat.append(self._mat_index(other.mats[mi]))
        self.uvs.extend(other.uvs)
        self.cols.extend(other.cols)
        self.has_col = self.has_col or other.has_col

    def build(self, collection=None, smooth=False):
        if not self.faces:
            return None
        me = bpy.data.meshes.new(self.name)
        me.from_pydata(self.verts, [], self.faces)
        me.validate(clean_customdata=False)
        uvl = me.uv_layers.new(name="UVMap")
        uvl.data.foreach_set("uv", np.array(self.uvs, np.float32).ravel())
        if self.has_col:
            ca = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
            ca.data.foreach_set("color", np.array(self.cols, np.float32).ravel())
        me.polygons.foreach_set("material_index", self.face_mat)
        me.polygons.foreach_set("use_smooth", [smooth] * len(self.faces))
        for m in self.mats:
            me.materials.append(m)
        me.update()
        ob = bpy.data.objects.new(self.name, me)
        (collection or bpy.context.scene.collection).objects.link(ob)
        return ob


def box_uv(pts):
    """Metre-scale box projection by dominant normal axis."""
    a, b, c = np.array(pts[0]), np.array(pts[1]), np.array(pts[2])
    n = np.cross(b - a, c - a)
    ax = int(np.argmax(np.abs(n)))
    out = []
    for x, y, z in pts:
        if ax == 2:
            out.append((x, y))
        elif ax == 0:
            out.append((y if n[0] > 0 else -y, z))
        else:
            out.append((-x if n[1] > 0 else x, z))
    return out


def new_collection(name, parent=None):
    col = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(col)
    return col


def empty(name, parent=None, collection=None):
    ob = bpy.data.objects.new(name, None)
    (collection or bpy.context.scene.collection).objects.link(ob)
    if parent:
        ob.parent = parent
    return ob


# ---------------------------------------------------------------------------------------------------------------
# Materials


def hex_rgb(h):
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb)


_MATS = {}


def mat(name, color="#808080", metal=0.0, rough=0.5, emit=None, emit_strength=0.0, alpha=1.0,
        tex=None, tex_scale=1.0, normal=None, normal_strength=1.0, rough_tex=None, vcol=False, ior=1.5,
        transmission=0.0):
    """Principled material that round-trips through glTF (base colour, metal/rough, normal, emission, alpha)."""
    if name in _MATS:
        return _MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    rgb = hex_rgb(color)
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["IOR"].default_value = ior
    if transmission:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    uv = None
    if tex or normal or rough_tex:
        uv = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1 / tex_scale, 1 / tex_scale, 1)
        nt.links.new(uv.outputs["UV"], mp.inputs["Vector"])
        uv = mp
    if tex:
        it = nt.nodes.new("ShaderNodeTexImage")
        it.image = bpy.data.images.load(os.path.join(TEX, tex), check_existing=True)
        nt.links.new(uv.outputs["Vector"], it.inputs["Vector"])
        if vcol:
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            va = nt.nodes.new("ShaderNodeVertexColor")
            va.layer_name = "Col"
            nt.links.new(it.outputs["Color"], mix.inputs["A"])
            nt.links.new(va.outputs["Color"], mix.inputs["B"])
            nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
        else:
            nt.links.new(it.outputs["Color"], bsdf.inputs["Base Color"])
    elif vcol:
        va = nt.nodes.new("ShaderNodeVertexColor")
        va.layer_name = "Col"
        nt.links.new(va.outputs["Color"], bsdf.inputs["Base Color"])
    if rough_tex:
        it = nt.nodes.new("ShaderNodeTexImage")
        it.image = bpy.data.images.load(os.path.join(TEX, rough_tex), check_existing=True)
        it.image.colorspace_settings.name = "Non-Color"
        nt.links.new(uv.outputs["Vector"], it.inputs["Vector"])
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(it.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    if normal:
        it = nt.nodes.new("ShaderNodeTexImage")
        it.image = bpy.data.images.load(os.path.join(TEX, normal), check_existing=True)
        it.image.colorspace_settings.name = "Non-Color"
        nt.links.new(uv.outputs["Vector"], it.inputs["Vector"])
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = normal_strength
        nt.links.new(it.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*hex_rgb(emit), 1.0)
        bsdf.inputs["Emission Strength"].default_value = emit_strength
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        m.surface_render_method = "BLENDED"
    _MATS[name] = m
    return m


# ---------------------------------------------------------------------------------------------------------------
# Export


def export_glb(path, objects=None, texcoords=True):
    bpy.ops.object.select_all(action="DESELECT")
    if objects:
        for o in objects:
            o.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=bool(objects),
        export_apply=True,
        export_yup=True,
        export_texcoords=texcoords,
        export_normals=True,
        export_vertex_color="ACTIVE",
        export_extras=True,
        export_animations=False,
        export_image_format="AUTO",
    )
    print("exported", path, round(os.path.getsize(path) / 1e6, 2), "MB")


def tri_count(objs):
    t = 0
    for o in objs:
        if o.type == "MESH":
            t += sum(len(p.vertices) - 2 for p in o.data.polygons)
    return t
