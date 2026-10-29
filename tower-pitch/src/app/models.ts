import * as THREE from 'three';
import { GLTFLoader, GLTF } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { upgradeMaterials, INTERIOR } from './materials';
import { applyFx } from './fx';
import { SITE_ROT } from './coords';

export type ProgressFn = (label: string, frac: number) => void;

export class Models {
  loader: GLTFLoader;
  building!: THREE.Group;
  site!: THREE.Group;
  props!: THREE.Group;
  parking: THREE.Group | null = null;
  context: THREE.Group | null = null;
  terrain: THREE.Mesh | null = null;
  nodes = new Map<string, THREE.Object3D>();
  private parkingPromise: Promise<THREE.Group> | null = null;
  private contextPromise: Promise<THREE.Group> | null = null;

  constructor(private scene: THREE.Scene, private renderer: THREE.WebGLRenderer) {
    this.loader = new GLTFLoader();
    this.loader.setMeshoptDecoder(MeshoptDecoder);
    INTERIOR.uSiteRot2.value.set(Math.cos(SITE_ROT), Math.sin(SITE_ROT));
  }

  private load(url: string, onFrac?: (f: number) => void): Promise<GLTF> {
    return new Promise((res, rej) => {
      this.loader.load(url, res, (e) => e.total && onFrac?.(e.loaded / e.total), rej);
    });
  }

  private index(root: THREE.Object3D) {
    root.traverse((o) => {
      if (o.name) this.nodes.set(o.name, o);
    });
  }

  async loadCore(progress: ProgressFn) {
    const parts: Array<[string, string]> = [
      ['building', '/models/building.glb'],
      ['site', '/models/site.glb'],
      ['props', '/models/props.glb'],
    ];
    const fracs = parts.map(() => 0);
    const report = (label: string) => progress(label, fracs.reduce((a, b) => a + b, 0) / parts.length);
    const results = await Promise.all(
      parts.map(([name, url], i) =>
        this.load(url, (f) => {
          fracs[i] = f;
          report(name);
        }).then((g) => {
          fracs[i] = 1;
          report(name);
          return g;
        }),
      ),
    );
    this.building = results[0].scene;
    this.site = results[1].scene;
    this.props = results[2].scene;
    upgradeMaterials(this.building, 'building');
    upgradeMaterials(this.site, 'site');
    upgradeMaterials(this.props, 'props');
    this.index(this.building);
    this.index(this.site);
    this.scene.add(this.building, this.site);
    // the existing buildings are only shown in the "before" view
    const before = this.nodes.get('S_before');
    if (before) before.visible = false;
    // ground surfaces never cast shadows (saves shadow-map fill)
    for (const n of ['S_ground', 'S_road', 'S_marks']) {
      this.nodes.get(n)?.traverse((o) => ((o as THREE.Mesh).castShadow = false));
    }
  }

  loadParking(): Promise<THREE.Group> {
    if (!this.parkingPromise) {
      this.parkingPromise = this.load('/models/parking.glb').then((g) => {
        this.parking = g.scene;
        upgradeMaterials(this.parking, 'parking');
        this.index(this.parking);
        this.scene.add(this.parking);
        return this.parking;
      });
    }
    return this.parkingPromise;
  }

  loadContext(progress?: (f: number) => void): Promise<THREE.Group> {
    if (!this.contextPromise) {
      this.contextPromise = Promise.all([
        this.load('/models/context.glb', progress),
        new THREE.TextureLoader().loadAsync('/textures/ground.webp'),
      ]).then(([g, tex]) => {
        const root = g.scene;
        tex.flipY = false;
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
        root.traverse((o) => {
          const m = o as THREE.Mesh;
          if (!m.isMesh) return;
          const mat = m.material as THREE.MeshStandardMaterial;
          if (o.name.startsWith('ctx_terrain') || mat.name === 'ctx_ground') {
            m.material = new THREE.MeshStandardMaterial({ map: tex, color: new THREE.Color(0.78, 0.77, 0.74), roughness: 0.95, metalness: 0, name: 'ctx_ground' });
            m.receiveShadow = true;
            m.castShadow = false;
            this.terrain = m;
            // sink slightly so the detailed site surfaces always win
            m.position.y -= 0.03;
          } else {
            m.material = contextBuildingMaterial();
            m.castShadow = o.name === 'ctx_near' || o.parent?.name === 'ctx_near';
            m.receiveShadow = true;
          }
          applyFx(m.material as THREE.Material, 'site', { cut: true });
        });
        this.context = root;
        this.index(root);
        this.scene.add(root);
        return root;
      });
    }
    return this.contextPromise;
  }

  /** Meshes under a named node. */
  meshes(name: string): THREE.Mesh[] {
    const out: THREE.Mesh[] = [];
    this.nodes.get(name)?.traverse((o) => (o as THREE.Mesh).isMesh && out.push(o as THREE.Mesh));
    return out;
  }
}

let ctxMat: THREE.MeshStandardMaterial | null = null;
/** Neighbourhood buildings: plaster walls with a procedural window grid (lit at night), darker roofs. */
function contextBuildingMaterial() {
  if (ctxMat) return ctxMat;
  const m = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.88, metalness: 0, flatShading: true, name: 'ctx_building' });
  m.userData.shaderKey = 'ctx-building';
  m.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, { uNight: INTERIOR.uNight });
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vCtxW;')
      .replace('#include <project_vertex>', '#include <project_vertex>\nvCtxW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>
        varying vec3 vCtxW; uniform float uNight;
        float chash(vec3 p) { p = fract(p * 0.1031); p += dot(p, p.yzx + 33.33); return fract((p.x + p.y) * p.z); }`)
      .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
        vec3 wN = normalize((vec4(normal, 0.0) * viewMatrix).xyz);
        float bh = chash(floor(vCtxW * vec3(0.021, 0.0, 0.021)) + 3.0);
        if (abs(wN.y) < 0.4) {
          vec2 t = normalize(vec2(-wN.z, wN.x));
          float u = dot(vCtxW.xz, t);
          float cw = 3.2 + bh * 1.2;
          vec2 cell = vec2(floor(u / cw), floor((vCtxW.y + 40.0) / 3.1));
          vec2 f = vec2(fract(u / cw), fract((vCtxW.y + 40.0) / 3.1));
          float win = step(0.2, f.x) * step(f.x, 0.8) * step(0.3, f.y) * step(f.y, 0.86);
          float r = chash(vec3(cell, bh * 91.0));
          vec3 glass = vec3(0.11, 0.13, 0.15) + 0.06 * r;
          vec3 wallTint = mix(vec3(0.66, 0.62, 0.56), vec3(0.58, 0.59, 0.6), bh) * (0.85 + 0.2 * chash(vec3(bh * 13.0)));
          diffuseColor.rgb = mix(diffuseColor.rgb * wallTint, glass, win * 0.85);
          roughnessFactor = mix(roughnessFactor, 0.25, win);
          float lit = step(0.62, r) * uNight;
          totalEmissiveRadiance += win * lit * mix(vec3(1.0, 0.72, 0.45), vec3(0.95, 0.9, 0.8), chash(vec3(cell.yx, 7.0))) * 1.4;
        } else if (wN.y > 0.5) {
          diffuseColor.rgb *= (0.5 + 0.14 * bh) * vec3(0.92, 0.9, 0.88);
        }`);
  };
  applyFx(m, 'site', { cut: true });
  ctxMat = m;
  return m;
}
