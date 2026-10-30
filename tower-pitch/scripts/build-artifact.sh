#!/bin/bash
# Build the claude.ai artifact preview: single HTML page + sibling assets (models renamed to a served type).
set -e
cd "$(dirname "$0")/.."
VITE_MODEL_SUFFIX=.wasm npx vite build -c vite.artifact.config.ts > /dev/null
rm -rf dist-artifact/site && mkdir -p dist-artifact/site
python3 - <<'PY'
import re, shutil, os, glob
s = open('dist-artifact/index.html', encoding='utf-8').read()
for pat in [r'<!doctype html>\s*', r'<html[^>]*>\s*', r'</html>\s*', r'<head>\s*', r'</head>\s*', r'<body>\s*', r'</body>\s*',
            r'<meta charset="UTF-8"\s*/?>\s*', r'<meta name="viewport"[^>]*>\s*']:
    s = re.sub(pat, '', s, flags=re.I)
s = s.replace('<title>Kazbegi 23 · Tbilisi</title>', '<title>Kazbegi 23</title>')
open('dist-artifact/site/kazbegi23.html', 'w', encoding='utf-8').write(s)
for d in ['models', 'textures', 'data', 'assets/pdf', 'assets/stills']:
    for f in glob.glob(f'public/{d}/*'):
        if os.path.isdir(f) or f.endswith('.bin'):
            continue
        dst = 'dist-artifact/site/' + f[len('public/'):] + ('.wasm' if f.endswith('.glb') else '')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(f, dst)
PY
find dist-artifact/site -type f | wc -l
