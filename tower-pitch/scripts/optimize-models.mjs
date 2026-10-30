// Compress raw GLBs from Blender into public/models: dedup, weld, meshopt + quantize, textures to WebP.
// Usage: node scripts/optimize-models.mjs [name ...]   (names without .glb; default: all known models)
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { dedup, prune, meshopt, textureCompress, quantize } from '@gltf-transform/functions';
import { MeshoptEncoder, MeshoptDecoder } from 'meshoptimizer';
import sharp from 'sharp';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const SOURCES = {
  building: 'blender/out/building_raw.glb',
  parking: 'blender/out/parking_raw.glb',
  site: 'blender/out/site_raw.glb',
  props: 'blender/out/props_raw.glb',
  context: 'blender/out/context_raw.glb',
};

await MeshoptEncoder.ready;
const io = new NodeIO()
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({ 'meshopt.encoder': MeshoptEncoder, 'meshopt.decoder': MeshoptDecoder });

const names = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(SOURCES);
for (const name of names) {
  const src = path.join(root, SOURCES[name]);
  if (!fs.existsSync(src)) {
    console.log(`skip ${name}: ${src} missing`);
    continue;
  }
  const doc = await io.read(src);
  await doc.transform(
    dedup(),
    prune({ keepAttributes: true }),
    // keep positions at 16-bit grid of each mesh's bbox (sub-mm for building parts); normals 10-bit
    quantize({ quantizePosition: 16, quantizeNormal: 10, quantizeTexcoord: 14, quantizeColor: 10 }),
    textureCompress({ encoder: sharp, targetFormat: 'webp', quality: 92, resize: [4096, 4096] }),
    meshopt({ encoder: MeshoptEncoder, level: 'medium' }),
  );
  const out = path.join(root, 'public/models', `${name}.glb`);
  await io.write(out, doc);
  const mb = (fs.statSync(out).size / 1e6).toFixed(2);
  console.log(`${name}: ${(fs.statSync(src).size / 1e6).toFixed(2)} MB -> ${mb} MB`);
}
