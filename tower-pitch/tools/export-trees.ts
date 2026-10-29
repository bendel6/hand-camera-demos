// Dev-only: generate the ez-tree variants used on the site and export them as GLB for the Blender stills.
import * as THREE from 'three';
import { Tree } from '@dgreenheck/ez-tree';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';

const VARIANTS = [
  { key: 'Tree_plane', preset: 'Ash Medium', height: 13, seed: 1203 },
  { key: 'Tree_plane2', preset: 'Oak Medium', height: 11, seed: 77 },
  { key: 'Tree_small', preset: 'Aspen Small', height: 8, seed: 9 },
  { key: 'Tree_cypress', preset: 'Pine Medium', height: 14, seed: 31 },
];

async function run() {
  const out: Record<string, string> = {};
  for (const v of VARIANTS) {
    const tree = new Tree();
    tree.loadPreset(v.preset);
    tree.options.seed = v.seed;
    tree.generate();
    // wait for textures
    await new Promise((r) => setTimeout(r, 1500));
    const box = new THREE.Box3().setFromObject(tree);
    const k = v.height / (box.max.y - box.min.y);
    const g = new THREE.Group();
    g.name = v.key;
    for (const [mesh, name] of [[tree.branchesMesh, 'bark'], [tree.leavesMesh, 'leaves']] as const) {
      const src = mesh.material as THREE.MeshPhongMaterial;
      const mat = new THREE.MeshStandardMaterial({
        name: `${v.key}_${name}`,
        map: src.map,
        normalMap: (src as any).normalMap ?? null,
        color: src.color,
        side: name === 'leaves' ? THREE.DoubleSide : THREE.FrontSide,
        alphaTest: name === 'leaves' ? 0.5 : 0,
        roughness: name === 'leaves' ? 0.6 : 0.9,
      });
      const m = new THREE.Mesh(mesh.geometry, mat);
      m.name = `${v.key}_${name}`;
      m.scale.setScalar(k);
      g.add(m);
    }
    const glb = await new GLTFExporter().parseAsync(g, { binary: true });
    const bytes = new Uint8Array(glb as ArrayBuffer);
    let bin = '';
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    out[v.key] = btoa(bin);
  }
  (window as any).__TREES__ = out;
}
run();
