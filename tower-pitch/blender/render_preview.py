"""Quick Cycles preview renders of the building from the reference-render camera angles.

Run: /opt/venvs/blender/bin/python blender/render_preview.py <preset> [samples] [res]
Cameras are given in the site frame and parented to the ENU root so they line up with the model."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import mathutils  # noqa: E402

import lib  # noqa: E402

PRESETS = {
    # name: (camera xyz, target xyz, lens mm, shift_y, sun elevation deg, sun azimuth deg)
    "p05": ((-28, -52, 1.7), (40, 30, 1.7), 18, 0.36, 18, 250),
    "p07": ((66, -62, 14), (52, 20, 14), 26, 0.32, 35, 200),
    "p08": ((44, -38, 1.6), (44, 20, 1.6), 24, 0.18, 15, 260),
    "aerial": ((-90, -120, 120), (40, 30, 40), 30, 0.0, 40, 220),
    "top": ((40, 32, 300), (40, 32.01, 0), 30, 0.0, 60, 180),
}


def setup_world(sun_el, sun_az):
    world = bpy.data.worlds.new("Sky")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    sky = nt.nodes.new("ShaderNodeTexSky")
    try:
        sky.sky_type = "MULTIPLE_SCATTERING"
    except TypeError:
        sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(sun_el)
    sky.sun_rotation = math.radians(sun_az)
    sky.altitude = 500
    sky.sun_disc = False
    bg = nt.nodes["Background"]
    bg.inputs["Strength"].default_value = 0.5
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])


def main():
    preset = sys.argv[1] if len(sys.argv) > 1 else "p05"
    samples = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    res = int(sys.argv[3]) if len(sys.argv) > 3 else 800
    bpy.ops.wm.open_mainfile(filepath=os.path.join(lib.OUT, "building.blend"))
    scene = bpy.context.scene
    cam_pos, target, lens, shift, sun_el, sun_az = PRESETS[preset]
    root = bpy.data.objects["Building"]
    # ground plane for context
    bpy.ops.mesh.primitive_plane_add(size=1200, location=(40, 30, -0.02))
    g = bpy.context.active_object
    g.parent = root
    gm = lib.mat("M_PreviewGround", "#8f8b84", rough=0.8)
    g.data.materials.append(gm)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = lens
    cam_data.shift_y = shift
    cam_data.clip_end = 5000
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    cam.parent = root
    cam.location = cam_pos
    direction = mathutils.Vector(target) - mathutils.Vector(cam_pos)
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    setup_world(sun_el, sun_az)
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    scene.collection.objects.link(sun)
    sun.data.energy = 4.0
    sun.data.angle = math.radians(1.5)
    sun.rotation_euler = (math.radians(90 - sun_el), 0, math.radians(sun_az + 90))
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = res
    scene.render.resolution_y = res
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.3
    out = os.path.join(lib.OUT, f"preview_{preset}.png")
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
