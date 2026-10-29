"""Procedural tileable PBR textures (albedo + normal + roughness), generated with numpy.

Poly Haven is not reachable from the build machine, so the ground and facade textures are synthesised here.
All textures tile seamlessly (noise is generated in the frequency domain / with wrapped coordinates)."""
import os

import numpy as np
from PIL import Image

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "textures")
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(7)


def fbm(n, octaves=6, persistence=0.55, base=4, seed=0):
    """Tileable fractal noise in [0,1] via FFT-filtered white noise per octave."""
    r = np.random.default_rng(seed)
    acc = np.zeros((n, n))
    amp, tot = 1.0, 0.0
    fy = np.fft.fftfreq(n)[:, None]
    fx = np.fft.fftfreq(n)[None, :]
    f = np.sqrt(fx ** 2 + fy ** 2) * n
    for o in range(octaves):
        freq = base * 2 ** o
        spec = np.fft.fft2(r.standard_normal((n, n)))
        band = np.exp(-((f - freq) ** 2) / (2 * (freq * 0.5) ** 2))
        layer = np.real(np.fft.ifft2(spec * band))
        layer = (layer - layer.mean()) / (layer.std() + 1e-9)
        acc += amp * layer
        tot += amp
        amp *= persistence
    acc /= tot
    return (acc - acc.min()) / (acc.max() - acc.min())


def normal_from_height(h, strength=4.0):
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * strength
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * strength
    n = np.dstack([-gx, gy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return ((n * 0.5 + 0.5) * 255).astype(np.uint8)


def save(name, arr):
    Image.fromarray(arr).save(os.path.join(OUT, name), quality=90)


def rgb(c):
    return np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], np.float64)


def colourise(t, c0, c1):
    return (rgb(c0)[None, None] * (1 - t[..., None]) + rgb(c1)[None, None] * t[..., None]).clip(0, 255).astype(np.uint8)


def pavers(n=1024, cell=(4, 8), grout=0.012, c0="#9d9a94", c1="#c3bfb6", seed=1, name="paving"):
    """Running-bond rectangular pavers. cell = (rows, cols) per tile."""
    r = np.random.default_rng(seed)
    y, x = np.mgrid[0:n, 0:n] / n
    rows, cols = cell
    ry = y * rows
    row = np.floor(ry).astype(int)
    rx = x * cols + (row % 2) * 0.5
    col = np.floor(rx).astype(int) % cols
    fy, fx = ry - row, rx - np.floor(rx)
    edge = np.minimum.reduce([fy, 1 - fy, (fx) * rows / cols, (1 - fx) * rows / cols])
    g = np.clip(edge / (grout * rows), 0, 1)
    tone = r.random((rows, cols))[row % rows, col]
    noise = fbm(n, seed=seed)
    t = np.clip(0.25 + 0.5 * tone + 0.35 * (noise - 0.5), 0, 1)
    alb = colourise(t, c0, c1).astype(np.float64)
    alb *= (0.55 + 0.45 * g)[..., None]
    save(f"{name}_albedo.jpg", alb.clip(0, 255).astype(np.uint8))
    h = g * 0.8 + noise * 0.2 + tone * 0.05
    save(f"{name}_normal.png", normal_from_height(h, 6))
    rough = (0.65 + 0.25 * (1 - g) + 0.1 * noise).clip(0, 1)
    save(f"{name}_rough.jpg", np.dstack([rough * 255] * 3).astype(np.uint8))


def flagstones(n=1024, cells=34, c0="#cfcac0", c1="#ebe7de", seed=3, name="flagstone"):
    """Irregular (Voronoi) light stone paving, like the site plan's garden paths."""
    r = np.random.default_rng(seed)
    g = int(round(cells ** 0.5))
    gy, gx = np.mgrid[0:g, 0:g]
    pts = (np.dstack([gx, gy]).reshape(-1, 2) + 0.15 + 0.7 * r.random((g * g, 2))) / g  # jittered grid
    cells = g * g
    y, x = (np.mgrid[0:n, 0:n] / n).astype(np.float32)
    # wrapped (toroidal) distance to every seed, then the two nearest
    dx = np.abs(x[None] - pts[:, 0, None, None].astype(np.float32))
    dy = np.abs(y[None] - pts[:, 1, None, None].astype(np.float32))
    d = np.hypot(np.minimum(dx, 1 - dx), np.minimum(dy, 1 - dy))
    idx = np.argmin(d, axis=0)
    two = np.partition(d, 1, axis=0)
    d1, d2 = two[0], two[1]
    edge = np.clip((d2 - d1) / 0.012, 0, 1)
    tone = r.random(cells)[idx]
    noise = fbm(n, seed=seed + 1)
    t = np.clip(0.3 + 0.4 * tone + 0.3 * (noise - 0.5), 0, 1)
    alb = colourise(t, c0, c1).astype(np.float64) * (0.6 + 0.4 * edge)[..., None]
    save(f"{name}_albedo.jpg", alb.clip(0, 255).astype(np.uint8))
    save(f"{name}_normal.png", normal_from_height(edge * 0.7 + noise * 0.3, 5))


def asphalt(n=1024, seed=5):
    noise = fbm(n, octaves=7, persistence=0.6, base=8, seed=seed)
    grain = np.random.default_rng(seed).random((n, n))
    speck = (grain > 0.985) * 0.35 + (grain < 0.01) * -0.25
    t = np.clip(0.35 + 0.35 * (noise - 0.5) + speck, 0, 1)
    save("asphalt_albedo.jpg", colourise(t, "#2b2c2e", "#5a5b5d"))
    save("asphalt_normal.png", normal_from_height(noise * 0.5 + grain * 0.5, 2.5))
    rough = (0.82 + 0.15 * noise - speck * 0.3).clip(0, 1)
    save("asphalt_rough.jpg", np.dstack([rough * 255] * 3).astype(np.uint8))


def grass(n=1024, seed=9):
    big = fbm(n, octaves=4, base=3, seed=seed)
    fine = fbm(n, octaves=4, base=64, seed=seed + 1)
    blades = np.random.default_rng(seed).random((n, n))
    t = np.clip(0.2 + 0.45 * big + 0.35 * fine + 0.15 * (blades - 0.5), 0, 1)
    alb = colourise(t, "#3d5a26", "#7f9c48")
    save("grass_albedo.jpg", alb)
    save("grass_normal.png", normal_from_height(fine * 0.6 + blades * 0.4, 3))


def rubber(n=512, seed=11):
    noise = fbm(n, base=32, seed=seed)
    grain = np.random.default_rng(seed).random((n, n))
    t = np.clip(0.3 + 0.4 * noise + 0.3 * (grain - 0.5), 0, 1)
    save("rubber_albedo.jpg", colourise(t, "#8a3b2c", "#b65a43"))


def concrete(n=1024, seed=13):
    big = fbm(n, octaves=5, base=2, seed=seed)
    fine = fbm(n, octaves=5, base=48, seed=seed + 1)
    t = np.clip(0.4 + 0.35 * (big - 0.5) + 0.25 * (fine - 0.5), 0, 1)
    save("concrete_albedo.jpg", colourise(t, "#a8a49c", "#c9c5bd"))
    save("concrete_normal.png", normal_from_height(fine, 1.5))


def ribs(n=512, count=16):
    """Vertical standing-seam ribs for the crown and frame cladding (normal + subtle albedo)."""
    x = np.mgrid[0:n, 0:n][1] / n
    f = (x * count) % 1.0
    h = np.clip(np.minimum(f, 1 - f) * 12, 0, 1) ** 0.5
    save("ribs_normal.png", normal_from_height(h, 3))
    t = 0.5 + 0.08 * h + 0.05 * fbm(n, base=2, seed=21)
    save("ribs_albedo.jpg", np.dstack([t * 255] * 3).clip(0, 255).astype(np.uint8))


def parking_floor(n=1024, seed=17):
    big = fbm(n, octaves=5, base=3, seed=seed)
    fine = fbm(n, octaves=4, base=64, seed=seed + 1)
    t = np.clip(0.45 + 0.3 * (big - 0.5) + 0.15 * (fine - 0.5), 0, 1)
    save("epoxy_albedo.jpg", colourise(t, "#6d7176", "#8d9196"))


if __name__ == "__main__":
    pavers()
    pavers(cell=(8, 8), grout=0.02, c0="#7d7a74", c1="#a19d95", seed=2, name="sidewalk")
    flagstones()
    asphalt()
    grass()
    rubber()
    concrete()
    ribs()
    parking_floor()
    print(sorted(os.listdir(OUT)))
