#!/bin/bash
# Final hero stills (4K Cycles). Each finished frame is converted to WebP for the site gallery.
cd "$(dirname "$0")/.."
LIST=${@:-golden_street aerial_golden day_front blue_hour night_aerial garden}
mkdir -p public/assets/stills
for p in $LIST; do
  echo "$(date +%H:%M) start $p"
  /opt/venvs/blender/bin/python blender/stills.py $p --res ${RES:-3840x2160} --samples ${SAMPLES:-128} --out blender/out/final_$p.png 2>&1 | grep -iE "traceback|error:|wrote"
  /opt/venvs/blender/bin/python - "$p" <<'PY'
import sys, json, os, glob
from PIL import Image
p = sys.argv[1]
src = f"blender/out/final_{p}.png"
if os.path.exists(src):
    im = Image.open(src).convert("RGB")
    im.save(f"public/assets/stills/{p}.webp", quality=92, method=6)
    t = im.copy(); t.thumbnail((640, 640)); t.save(f"public/assets/stills/{p}_thumb.webp", quality=82)
    order = ["golden_street", "aerial_golden", "day_front", "blue_hour", "night_aerial", "garden"]
    have = [o for o in order if os.path.exists(f"public/assets/stills/{o}.webp")]
    json.dump([f"assets/stills/{o}.webp" for o in have], open("public/assets/stills/index.json", "w"))
    print("converted", p)
PY
  echo "$(date +%H:%M) done $p"
done
