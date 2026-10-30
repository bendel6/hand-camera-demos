"""Export prop prototypes to public/models/props.glb (+ optional preview render of a line-up)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402

import lib  # noqa: E402
import props  # noqa: E402


def build():
    lib.reset_scene()
    items = [props.car("sedan"), props.car("suv"), props.car("hatch"),
             props.tree("plane", 1), props.tree("plane", 7), props.tree("cypress", 2), props.tree("small", 3),
             props.tree("shrub", 4), props.person(), props.street_lamp(), props.bollard_light(), props.bench()]
    names = ["Car_sedan", "Car_suv", "Car_hatch", "Tree_plane", "Tree_plane2", "Tree_cypress", "Tree_small",
             "Shrub", "Person", "StreetLamp", "Bollard", "Bench"]
    objs = []
    for acc, nm in zip(items, names):
        acc.name = nm
        smooth = nm.startswith("Tree") or nm == "Shrub" or nm == "Person"
        o = acc.build(smooth=smooth)
        objs.append(o)
    return objs


if __name__ == "__main__":
    objs = build()
    print("props tris:", {o.name: lib.tri_count([o]) for o in objs})
    lib.export_glb(os.path.join(lib.OUT, "props_raw.glb"))
    if "--preview" in sys.argv:
        import math
        import mathutils
        for i, o in enumerate(objs):
            o.location.x = i * 5.5 - 30
        bpy.ops.mesh.primitive_plane_add(size=200)
        g = bpy.context.active_object
        g.data.materials.append(lib.mat("M_G", "#9a968f", rough=0.8))
        cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
        bpy.context.scene.collection.objects.link(cam)
        cam.location = (0, -58, 8)
        cam.rotation_euler = (mathutils.Vector((0, 0, 3)) - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = 40
        bpy.context.scene.camera = cam
        sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
        bpy.context.scene.collection.objects.link(sun)
        sun.data.energy = 4
        sun.rotation_euler = (math.radians(50), 0, math.radians(30))
        w = bpy.data.worlds.new("W")
        w.use_nodes = True
        w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.6, 0.7, 0.85, 1)
        w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
        bpy.context.scene.world = w
        sc = bpy.context.scene
        sc.render.engine = "CYCLES"
        sc.cycles.samples = 16
        sc.cycles.use_denoising = True
        sc.render.resolution_x, sc.render.resolution_y = 1400, 500
        sc.view_settings.view_transform = "AgX"
        sc.render.filepath = os.path.join(lib.OUT, "props_preview.png")
        bpy.ops.render.render(write_still=True)
