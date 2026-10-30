#!/bin/bash
# Low-res composition tests for still presets (default: all).
cd "$(dirname "$0")/.."
LIST=${@:-golden_street aerial_golden day_front night_aerial blue_hour garden}
for p in $LIST; do
  /opt/venvs/blender/bin/python blender/stills.py $p --res ${RES:-960x540} --samples ${SAMPLES:-32} --out blender/out/test_$p.png 2>&1 | grep -iE "traceback|error:|wrote"
done
