"""Download AWS Terrain Tiles (terrarium PNG, open data) for the context bbox and stitch a height grid.

Output: data/terrain_z14.npz with heights (m, float32), and the WebMercator bounds."""
import math, io, os, sys, urllib.request
import numpy as np
from PIL import Image

Z = 14
BBOX = (44.70, 41.67, 44.86, 41.775)

def tile(lon, lat, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y

x0, y1 = tile(BBOX[0], BBOX[1], Z)
x1, y0 = tile(BBOX[2], BBOX[3], Z)
xs = range(int(x0), int(x1) + 1)
ys = range(int(y0), int(y1) + 1)
grid = np.zeros((len(ys) * 256, len(xs) * 256), np.float32)
for j, ty in enumerate(ys):
    for i, tx in enumerate(xs):
        url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{tx}/{ty}.png"
        data = urllib.request.urlopen(url, timeout=60).read()
        a = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"), np.float32)
        grid[j*256:(j+1)*256, i*256:(i+1)*256] = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
        sys.stdout.write(".")
        sys.stdout.flush()
np.savez_compressed("data/terrain_z14.npz", h=grid, z=Z, tx0=xs[0], ty0=ys[0], nx=len(xs), ny=len(ys))
print("\nterrain", grid.shape, grid.min(), grid.max())
