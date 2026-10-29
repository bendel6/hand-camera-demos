// Download Google Photorealistic 3D Tiles around the site and convert them for Blender: Draco decoded,
// re-projected from ECEF into the site's local ENU frame (metres; x east, y up, z = -north, origin = SW plot
// corner), one GLB per tile + manifest.json. Blender then imports them with blender/import_gtiles.py.
//
//   GOOGLE_MAPS_BROWSER_KEY=... node scripts/google_tiles.mjs [--radius 900] [--far 2600] [--near-error 1.2] [--k 0.01]
//
// Detail: tiles are refined until geometricError <= max(nearError, k * distance-from-site), so the plot and its
// neighbours load at the finest level and the city falls off smoothly towards the horizon.
// Google Maps Platform terms apply (attribution "Google" + data providers on every rendered frame/video).
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import draco3d from 'draco3dgltf';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const KEY = process.env.GOOGLE_MAPS_BROWSER_KEY || process.env.VITE_GOOGLE_KEY || process.env.GOOGLE_MAPS_SERVER_KEY;
if (!KEY) {
  console.error('Set GOOGLE_MAPS_BROWSER_KEY (Map Tiles API enabled).');
  process.exit(1);
}
const arg = (name, def) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? Number(process.argv[i + 1]) : def;
};
const RADIUS = arg('radius', 900); // full-detail neighbourhood (m)
const FAR = arg('far', 2600); // outer ring kept at coarser detail (m)
const NEAR_ERR = arg('near-error', 1.2); // finest geometric error to reach near the site (m)
const K = arg('k', 0.01); // error grows by this much per metre of distance
const OUT = path.join(root, 'blender/out/gtiles');
fs.mkdirSync(OUT, { recursive: true });

const site = JSON.parse(fs.readFileSync(path.join(root, 'src/content/site.json'), 'utf8'));
const HOST = 'https://tile.googleapis.com';
// browser keys are referrer-restricted: present the local dev origin the key allows
const HEADERS = { Referer: 'http://localhost:5173/' };

// ------------------------------------------------------------------ geodesy (WGS84)
const A = 6378137;
const F = 1 / 298.257223563;
const E2 = F * (2 - F);
const rad = (d) => (d * Math.PI) / 180;
function llhToEcef(latDeg, lonDeg, h) {
  const p = rad(latDeg), l = rad(lonDeg);
  const N = A / Math.sqrt(1 - E2 * Math.sin(p) ** 2);
  return [(N + h) * Math.cos(p) * Math.cos(l), (N + h) * Math.cos(p) * Math.sin(l), (N * (1 - E2) + h) * Math.sin(p)];
}
const lat0 = rad(site.originLat), lon0 = rad(site.originLng);
// origin ~ street level (ellipsoidal height = ASL + ~20 m geoid); Blender re-levels it exactly by raycast
const O = llhToEcef(site.originLat, site.originLng, site.elevationAsl + 20);
const RE = [-Math.sin(lon0), Math.cos(lon0), 0];
const RN = [-Math.sin(lat0) * Math.cos(lon0), -Math.sin(lat0) * Math.sin(lon0), Math.cos(lat0)];
const RU = [Math.cos(lat0) * Math.cos(lon0), Math.cos(lat0) * Math.sin(lon0), Math.sin(lat0)];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
function ecefToEnu(p) {
  const d = [p[0] - O[0], p[1] - O[1], p[2] - O[2]];
  return [dot(RE, d), dot(RN, d), dot(RU, d)];
}
const SITE_ENU = [35, 38, 0]; // plot centre (east, north, up), for distances

// ------------------------------------------------------------------ fetching
let session = null;
function withAuth(uri, base) {
  const u = new URL(uri, base ?? HOST);
  if (!u.searchParams.has('key')) u.searchParams.set('key', KEY);
  const s = u.searchParams.get('session');
  if (s) session = s;
  else if (session) u.searchParams.set('session', session);
  return u;
}
async function get(url, type = 'json', tries = 4) {
  for (let t = 0; t < tries; t++) {
    try {
      const r = await fetch(url, { headers: HEADERS });
      if (r.status === 429 || r.status >= 500) throw new Error(`HTTP ${r.status}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}: ${(await r.text()).slice(0, 300)}`);
      return type === 'json' ? r.json() : Buffer.from(await r.arrayBuffer());
    } catch (e) {
      if (t === tries - 1) throw e;
      await new Promise((res) => setTimeout(res, 800 * 2 ** t));
    }
  }
}

// ------------------------------------------------------------------ traversal
function boxSphere(box) {
  const c = [box[0], box[1], box[2]];
  const r = Math.hypot(...box.slice(3, 6)) + Math.hypot(...box.slice(6, 9)) + Math.hypot(...box.slice(9, 12));
  return { c, r };
}
function distToSite(tile) {
  const bv = tile.boundingVolume;
  if (!bv?.box) return 0;
  const { c, r } = boxSphere(bv.box);
  const e = ecefToEnu(c);
  const d = Math.hypot(e[0] - SITE_ENU[0], e[1] - SITE_ENU[1]);
  return Math.max(0, d - r);
}
const wanted = []; // { url, error, dist }
let visited = 0;
async function walk(tile, baseUrl) {
  visited++;
  const d = distToSite(tile);
  if (d > FAR) return;
  const target = Math.max(NEAR_ERR, K * d) * (d > RADIUS ? 2.2 : 1);
  const refine = tile.geometricError > target && (tile.children?.length || tile.content?.uri?.includes('.json'));
  const contentUri = tile.content?.uri ?? tile.content?.url;
  if (contentUri && contentUri.includes('.json')) {
    // external tileset: its root replaces this tile
    const u = withAuth(contentUri, baseUrl);
    const ts = await get(u);
    await walk(ts.root, u.toString());
    return;
  }
  if (refine && tile.children?.length) {
    await Promise.all(tile.children.map((c) => walk(c, baseUrl)));
    return;
  }
  if (contentUri) wanted.push({ url: withAuth(contentUri, baseUrl).toString(), error: tile.geometricError, dist: Math.round(d) });
}

// ------------------------------------------------------------------ conversion
const io = new NodeIO()
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({ 'draco3d.decoder': await draco3d.createDecoderModule() });

async function convert(buf, outPath) {
  const doc = await io.readBinary(new Uint8Array(buf));
  const rootNode = doc.getRoot();
  for (const scene of rootNode.listScenes()) {
    for (const top of scene.listChildren()) {
      top.traverse((node) => {
        const mesh = node.getMesh();
        if (!mesh) return;
        const m = node.getWorldMatrix(); // column-major
        for (const prim of mesh.listPrimitives()) {
          const pos = prim.getAttribute('POSITION');
          const arr = pos.getArray();
          const out = new Float32Array(arr.length);
          for (let i = 0; i < arr.length; i += 3) {
            const x = arr[i], y = arr[i + 1], z = arr[i + 2];
            // node transform (glTF, y-up) ...
            const gx = m[0] * x + m[4] * y + m[8] * z + m[12];
            const gy = m[1] * x + m[5] * y + m[9] * z + m[13];
            const gz = m[2] * x + m[6] * y + m[10] * z + m[14];
            // ... then 3D Tiles y-up -> z-up (ECEF): (x, -z, y)
            const e = ecefToEnu([gx, -gz, gy]);
            out[i] = e[0];
            out[i + 1] = e[2];
            out[i + 2] = -e[1];
          }
          pos.setArray(out);
          const nrm = prim.getAttribute('NORMAL');
          if (nrm) prim.setAttribute('NORMAL', null);
        }
      });
      // positions are now final: clear node transforms
      top.traverse((node) => {
        node.setTranslation([0, 0, 0]);
        node.setRotation([0, 0, 0, 1]);
        node.setScale([1, 1, 1]);
        node.setMatrix?.([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
      });
    }
  }
  for (const ext of rootNode.listExtensionsUsed()) if (ext.extensionName === 'KHR_draco_mesh_compression') ext.dispose();
  await io.write(outPath, doc);
}

// ------------------------------------------------------------------ main
console.log(`radius ${RADIUS} m (far ${FAR} m), near error ${NEAR_ERR} m, k ${K}`);
const rootTs = await get(withAuth('/v1/3dtiles/root.json'));
await walk(rootTs.root, `${HOST}/v1/3dtiles/root.json`);
console.log(`visited ${visited} tiles, ${wanted.length} content tiles selected`);
const manifest = [];
let done = 0;
const queue = [...wanted];
async function worker() {
  while (queue.length) {
    const t = queue.shift();
    const name = crypto.createHash('sha1').update(new URL(t.url).pathname).digest('hex').slice(0, 16) + '.glb';
    const out = path.join(OUT, name);
    try {
      if (!fs.existsSync(out)) await convert(await get(t.url, 'bin'), out);
      manifest.push({ file: name, error: t.error, dist: t.dist });
    } catch (e) {
      console.warn('tile failed', e.message);
    }
    if (++done % 25 === 0) console.log(`${done}/${wanted.length}`);
  }
}
await Promise.all(Array.from({ length: 8 }, worker));
fs.writeFileSync(path.join(OUT, 'manifest.json'), JSON.stringify({ origin: { lat: site.originLat, lng: site.originLng }, tiles: manifest }, null, 1));
console.log(`wrote ${manifest.length} tiles to ${OUT}`);
console.log('Attribution required on renders: "Google" + the data providers listed in the tiles (copyright field).');
