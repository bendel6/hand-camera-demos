"""Cinematic drone reels (Cycles): keyframed camera moves over the assembled scene, rendered frame by frame
(resumable) and encoded to MP4 with ffmpeg.

Run:  /opt/venvs/blender/bin/python blender/reels.py <reel> [--res 1080x1920] [--fps 24] [--samples 48]
                                                     [--frames a-b] [--blend] [--encode-only]
      /opt/venvs/blender/bin/python blender/reels.py --list
Cameras are in the site frame (x along Kazbegi Ave, y into the plot, z up). With blender/out/gtiles present the
real Google city is used automatically (attribution is burned into the video)."""
import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import mathutils  # noqa: E402

import lib  # noqa: E402
import stills  # noqa: E402

# each key: (time s, camera xyz, target xyz); smooth Bezier between keys
REELS = {
    "rise": dict(tod="golden", sun=(248, 8), exp=0.25, dur=10, lens=20, keys=[
        (0.0, (44, -30, 9.0), (46, 0, 12)),
        (4.0, (40, -40, 30), (44, 6, 38)),
        (10.0, (30, -88, 96), (30, 30, 82)),
    ]),
    "orbit": dict(tod="golden", sun=(250, 9), exp=0.15, dur=12, lens=35, orbit=dict(
        centre=(38, 30, 58), radius=240, height=150, a0=-115, a1=-45)),
    "flyin": dict(tod="golden", sun=(252, 10), exp=0.15, dur=10, lens=28, keys=[
        (0.0, (-760, -980, 460), (40, 30, 30)),
        (10.0, (-95, -150, 120), (38, 30, 58)),
    ]),
    "nightpush": dict(tod="blue", sun=(255, -3), exp=1.0, dur=8, lens=32, keys=[
        (0.0, (150, -190, 95), (35, 32, 92)),
        (8.0, (82, -78, 80), (33, 35, 98)),
    ]),
}


def args_get(name, default):
    a = sys.argv
    return a[a.index(name) + 1] if name in a else default


def make_camera(r, fps):
    root = stills.site_root()
    cd = bpy.data.cameras.new("ReelCam")
    cd.lens = r["lens"]
    cd.clip_start = 0.5
    cd.clip_end = 30000
    cam = bpy.data.objects.new("ReelCam", cd)
    tgt = bpy.data.objects.new("ReelTarget", None)
    for o in (cam, tgt):
        bpy.context.scene.collection.objects.link(o)
        o.parent = root
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.fps = fps
    n = int(round(r["dur"] * fps))
    sc.frame_start, sc.frame_end = 1, n
    if "orbit" in r:
        o = r["orbit"]
        cx, cy, cz = o["centre"]
        steps = 6
        for k in range(steps + 1):
            f = k / steps
            a = math.radians(o["a0"] + (o["a1"] - o["a0"]) * f)
            cam.location = (cx + math.cos(a) * o["radius"], cy + math.sin(a) * o["radius"], o["height"])
            tgt.location = (cx, cy, cz)
            fr = 1 + f * (n - 1)
            cam.keyframe_insert("location", frame=fr)
            tgt.keyframe_insert("location", frame=fr)
    else:
        for t, cpos, tpos in r["keys"]:
            fr = 1 + t * fps
            cam.location = cpos
            tgt.location = tpos
            cam.keyframe_insert("location", frame=fr)
            tgt.keyframe_insert("location", frame=fr)
    for ob in (cam, tgt):
        if ob.animation_data and ob.animation_data.action:
            for fc in getattr(ob.animation_data.action, "fcurves", []):
                for kp in fc.keyframe_points:
                    kp.interpolation = "BEZIER"
                    kp.easing = "EASE_IN_OUT"
    return n


def render_frames(name, n, res, samples, frames, real_city):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.max_bounces = 6
    sc.cycles.transparent_max_bounces = 16
    sc.cycles.blur_glossy = 1.0
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.45
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = REELS[name]["exp"]
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "8"
    sc.render.threads_mode = "FIXED"
    sc.render.threads = int(os.environ.get("RENDER_THREADS", "4"))
    out_dir = os.path.join(lib.OUT, "reels", name)
    os.makedirs(out_dir, exist_ok=True)
    a, b = frames if frames else (1, n)
    for f in range(a, b + 1):
        path = os.path.join(out_dir, f"frame_{f:04d}.png")
        if os.path.exists(path):
            continue
        sc.frame_set(f)
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        print(f"frame {f}/{n}", flush=True)
    json.dump({"real_city": real_city, "frames": n}, open(os.path.join(out_dir, "info.json"), "w"))


def encode(name, fps):
    out_dir = os.path.join(lib.OUT, "reels", name)
    info = json.load(open(os.path.join(out_dir, "info.json")))
    dst_dir = os.path.join(lib.ROOT, "public", "assets", "reels")
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, f"{name}.mp4")
    vf = "format=yuv420p"
    if info.get("real_city"):
        vf = ("drawtext=text='Google':fontcolor=white@0.85:fontsize=h/60:x=w*0.03:y=h-h*0.04-th:"
              "shadowcolor=black@0.5:shadowx=2:shadowy=2," + vf)
    cmd = ["ffmpeg", "-y", "-framerate", str(fps), "-i", os.path.join(out_dir, "frame_%04d.png"), "-vf", vf,
           "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-movflags", "+faststart", dst]
    subprocess.run(cmd, check=True)
    print("encoded", dst)


def main():
    if "--list" in sys.argv:
        print("\n".join(REELS))
        return
    name = sys.argv[1]
    r = REELS[name]
    fps = int(args_get("--fps", "24"))
    if "--encode-only" in sys.argv:
        encode(name, fps)
        return
    res = tuple(int(v) for v in args_get("--res", "1080x1920").split("x"))
    samples = int(args_get("--samples", "48"))
    fr = args_get("--frames", "")
    frames = tuple(int(v) for v in fr.split("-")) if fr else None
    real = stills.build_scene(r["tod"], cam=None)
    stills.setup_world(r["tod"], *r["sun"])
    n = make_camera(r, fps)
    if "--blend" in sys.argv:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(lib.OUT, f"reel_{name}.blend"))
    render_frames(name, n, res, samples, frames, real)
    if not frames or frames[1] >= n:
        encode(name, fps)


if __name__ == "__main__":
    main()
