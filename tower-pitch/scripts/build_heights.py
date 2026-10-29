"""Uniform height grid of the context terrain (same DEM + site flattening as build_context.py) for cheap
height lookups in the browser (POI pins, rings, routes). Output: public/data/heights.bin (Int16, decimetres)
+ src/content/heights.json (grid metadata)."""
import json
import numpy as np
import geo

E0, N0, E1, N1 = geo.local_extent()
dem = geo.DEM()
SC = geo.SITE_CENTRE_LOC
H0 = float(dem.sample_loc(np.array([SC[0]]), np.array([SC[1]]))[0])
NX = NY = 512
ge = np.linspace(E0, E1, NX)
gn = np.linspace(N0, N1, NY)
EE, NN = np.meshgrid(ge, gn)
raw = dem.sample_loc(EE.ravel(), NN.ravel()).reshape(EE.shape) - H0
r = np.hypot(EE - SC[0], NN - SC[1])
t = np.clip((r - 120.0) / (280.0 - 120.0), 0, 1)
HT = raw * (t * t * (3 - 2 * t))
out = geo.ROOT / "public" / "data"
out.mkdir(parents=True, exist_ok=True)
from PIL import Image
v = (np.round(HT * 10).astype(np.int32) + 32768).clip(0, 65535)
rgb = np.zeros((NY, NX, 3), np.uint8)
rgb[..., 0] = v >> 8
rgb[..., 1] = v & 255
Image.fromarray(rgb).save(out / "heights.png", optimize=True)  # R = high byte, G = low byte (dm + 32768)
json.dump({"nx": NX, "ny": NY, "e0": E0, "e1": E1, "n0": N0, "n1": N1, "unit": "dm", "rows": "north (row 0 = n0)",
           "h0_asl": H0}, open(geo.ROOT / "src" / "content" / "heights.json", "w"), indent=1)
print("heights", HT.min(), HT.max(), "H0", H0)
