import * as THREE from 'three';
import gsap from 'gsap';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import poiData from '../content/poi.json';
import routesData from '../content/routes.json';
import heightsMeta from '../content/heights.json';
import { SITE_CENTRE } from './coords';

export type Category = 'Transport' | 'Shopping' | 'Education' | 'Health' | 'Leisure' | 'Business' | 'Landmark';
export const CATEGORY_COLOURS: Record<Category, string> = {
  Transport: '#4fc3f7',
  Shopping: '#ffb74d',
  Education: '#b39ddb',
  Health: '#ef8a8a',
  Leisure: '#81c784',
  Business: '#9fb3c8',
  Landmark: '#ffd54f',
};

export interface Poi {
  id: string;
  name_en: string;
  name_ka?: string;
  category: Category;
  lat: number;
  lng: number;
  x: number;
  z: number;
  straight_m: number;
  walk_m: number | null;
  drive_m: number | null;
  walk_min: number | null;
  drive_min: number | null;
  y?: number;
  approximate?: boolean;
}

export const POIS: Poi[] = (poiData as any).pois;
export const POI_META = (poiData as any).meta;

/** Bilinear lookup in the precomputed terrain grid (same terrain as context.glb). */
export class Heights {
  data: Int16Array | null = null;
  async load() {
    const buf = await (await fetch('/data/heights.bin')).arrayBuffer();
    this.data = new Int16Array(buf);
  }
  at(x: number, z: number): number {
    if (!this.data) return 0;
    const m = heightsMeta as any;
    const e = x;
    const n = -z;
    const fx = ((e - m.e0) / (m.e1 - m.e0)) * (m.nx - 1);
    const fy = ((n - m.n0) / (m.n1 - m.n0)) * (m.ny - 1);
    if (fx < 0 || fy < 0 || fx > m.nx - 1 || fy > m.ny - 1) return 0;
    const x0 = Math.floor(fx), y0 = Math.floor(fy);
    const x1 = Math.min(x0 + 1, m.nx - 1), y1 = Math.min(y0 + 1, m.ny - 1);
    const tx = fx - x0, ty = fy - y0;
    const d = this.data;
    const h = (i: number, j: number) => d[j * m.nx + i] / 10;
    return (h(x0, y0) * (1 - tx) + h(x1, y0) * tx) * (1 - ty) + (h(x0, y1) * (1 - tx) + h(x1, y1) * tx) * ty;
  }
}

function beamMaterial(col: THREE.Color) {
  return new THREE.ShaderMaterial({
    uniforms: { uCol: { value: col }, uA: { value: 1 } },
    vertexShader: /* glsl */ `varying float vY; void main(){ vY = uv.y; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: /* glsl */ `uniform vec3 uCol; uniform float uA; varying float vY; void main(){ gl_FragColor = vec4(uCol * 2.2, (1.0 - vY) * 0.85 * uA); }`,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    fog: false,
  });
}

const RING_VERT = /* glsl */ `
varying vec2 vUv;
void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const RING_FRAG = /* glsl */ `
uniform vec3 uCol; uniform float uT; uniform float uA; varying vec2 vUv;
void main() {
  float edge = 1.0 - abs(vUv.y - 0.5) * 2.0;
  float dash = 0.65 + 0.35 * step(0.5, fract(vUv.x * 90.0 - uT * 0.6));
  float pulse = 0.75 + 0.25 * sin(uT * 2.0 - vUv.y * 3.0);
  gl_FragColor = vec4(uCol * 1.8 * pulse, pow(edge, 1.5) * dash * 0.8 * uA);
}`;

export class Location {
  group = new THREE.Group();
  pins = new Map<string, { beam: THREE.Mesh; disc: THREE.Mesh; top: THREE.Vector3; poi: Poi }>();
  rings: THREE.Mesh[] = [];
  ringLabels: Array<{ text: string; pos: THREE.Vector3; r: number }> = [];
  metro: Line2[] = [];
  trains: THREE.InstancedMesh | null = null;
  trainState: Array<{ line: number; d: number; v: number }> = [];
  route: Line2 | null = null;
  heights = new Heights();
  active = false;
  enabled = new Set<Category>(Object.keys(CATEGORY_COLOURS) as Category[]);
  private ringMats: THREE.ShaderMaterial[] = [];
  private metroPaths: Array<{ pts: THREE.Vector3[]; lens: number[]; total: number }> = [];
  private resolution = new THREE.Vector2(1, 1);

  constructor(private scene: THREE.Scene) {
    this.group.name = 'Location';
    this.group.visible = false;
    scene.add(this.group);
  }

  async init() {
    await this.heights.load();
    const H = this.heights;
    // pins
    for (const p of POIS) {
      const col = new THREE.Color(CATEGORY_COLOURS[p.category] ?? '#ffffff');
      const far = p.straight_m > 9000;
      const x = far ? SITE_CENTRE.x + (p.x - SITE_CENTRE.x) * (8500 / p.straight_m) : p.x;
      const z = far ? SITE_CENTRE.z + (p.z - SITE_CENTRE.z) * (8500 / p.straight_m) : p.z;
      const y = H.at(x, z);
      p.y = y;
      const hgt = 90 + Math.min(p.straight_m / 40, 140);
      const geo = new THREE.CylinderGeometry(3.5, 3.5, hgt, 12, 1, true);
      geo.translate(0, hgt / 2, 0);
      const beam = new THREE.Mesh(geo, beamMaterial(col));
      beam.position.set(x, y, z);
      beam.renderOrder = 5;
      const discGeo = new THREE.CircleGeometry(26, 40);
      discGeo.rotateX(-Math.PI / 2);
      const disc = new THREE.Mesh(discGeo, new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending, depthWrite: false, fog: false }));
      disc.position.set(x, y + 1.5, z);
      disc.renderOrder = 5;
      this.group.add(beam, disc);
      this.pins.set(p.id, { beam, disc, top: new THREE.Vector3(x, y + hgt, z), poi: p });
    }
    // accessibility rings
    const rings: Array<[number, string, string]> = [
      [500, '500 m', 'walk6'],
      [1000, '1 km', 'walk12'],
      [3000, '3 km', 'drive7'],
      [5000, '5 km', 'drive12'],
    ];
    for (const [r, label, key] of rings) {
      const seg = Math.round(64 + r / 25);
      const w = 4 + r / 260;
      const pos: number[] = [];
      const uv: number[] = [];
      const idx: number[] = [];
      for (let i = 0; i <= seg; i++) {
        const a = (i / seg) * Math.PI * 2;
        for (const k of [0, 1]) {
          const rr = r + (k - 0.5) * w;
          const x = SITE_CENTRE.x + Math.cos(a) * rr;
          const z = SITE_CENTRE.z + Math.sin(a) * rr;
          pos.push(x, H.at(x, z) + 6, z);
          uv.push(i / seg, k);
        }
        if (i < seg) {
          const b = i * 2;
          idx.push(b, b + 2, b + 1, b + 1, b + 2, b + 3);
        }
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
      g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
      g.setIndex(idx);
      const mat = new THREE.ShaderMaterial({
        vertexShader: RING_VERT,
        fragmentShader: RING_FRAG,
        uniforms: { uCol: { value: new THREE.Color('#ffb37a') }, uT: { value: 0 }, uA: { value: 1 } },
        transparent: true,
        depthWrite: false,
        side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending,
        fog: false,
      });
      this.ringMats.push(mat);
      const m = new THREE.Mesh(g, mat);
      m.renderOrder = 4;
      this.group.add(m);
      this.rings.push(m);
      const lp = new THREE.Vector3(SITE_CENTRE.x + Math.cos(-0.9) * r, 0, SITE_CENTRE.z + Math.sin(-0.9) * r);
      lp.y = H.at(lp.x, lp.z) + 30;
      this.ringLabels.push({ text: `${label}|${key}`, pos: lp, r });
    }
    // metro
    const lineCols = ['#2fbf71', '#e5484d'];
    (routesData as any).metro.lines.forEach((ln: any, li: number) => {
      const pts = (ln.points as number[][]).map(([x, z]) => new THREE.Vector3(x, H.at(x, z) + 8, z));
      // densify long segments so the line hugs the terrain
      const dense: THREE.Vector3[] = [];
      for (let i = 0; i < pts.length - 1; i++) {
        const a = pts[i], b = pts[i + 1];
        const n = Math.max(1, Math.ceil(a.distanceTo(b) / 120));
        for (let k = 0; k < n; k++) {
          const p = a.clone().lerp(b, k / n);
          p.y = H.at(p.x, p.z) + 8;
          dense.push(p);
        }
      }
      dense.push(pts[pts.length - 1]);
      const line = this.makeLine(dense, lineCols[li % 2], 4.5, 0.9);
      this.metro.push(line);
      this.group.add(line);
      const lens = [0];
      for (let i = 1; i < dense.length; i++) lens.push(lens[i - 1] + dense[i].distanceTo(dense[i - 1]));
      this.metroPaths.push({ pts: dense, lens, total: lens[lens.length - 1] });
    });
    const trainGeo = new THREE.SphereGeometry(14, 16, 8);
    this.trains = new THREE.InstancedMesh(trainGeo, new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false, fog: false }), 10);
    this.trains.frustumCulled = false;
    for (let i = 0; i < 10; i++) {
      const line = i % 2;
      this.trainState.push({ line, d: Math.random() * this.metroPaths[line].total, v: (i % 4 < 2 ? 1 : -1) * 260 });
      this.trains.setColorAt(i, new THREE.Color(lineCols[line]).multiplyScalar(3));
    }
    this.group.add(this.trains);
    // metro station markers
    for (const s of (routesData as any).metro.stations) {
      const g = new THREE.CylinderGeometry(22, 22, 3, 24);
      const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: 0xffffff, fog: false }));
      m.position.set(s.x, H.at(s.x, s.z) + 9, s.z);
      this.group.add(m);
    }
  }

  makeLine(pts: THREE.Vector3[], col: string, width: number, opacity = 1): Line2 {
    const g = new LineGeometry();
    g.setPositions(pts.flatMap((p) => [p.x, p.y, p.z]));
    const m = new LineMaterial({ color: new THREE.Color(col).multiplyScalar(1.6).getHex(), linewidth: width, transparent: true, opacity, depthWrite: false, worldUnits: false });
    m.resolution.copy(this.resolution);
    const l = new Line2(g, m);
    l.computeLineDistances();
    l.renderOrder = 6;
    return l;
  }

  setResolution(w: number, h: number) {
    this.resolution.set(w, h);
    this.group.traverse((o) => {
      const m = (o as Line2).material as LineMaterial;
      if (m && (m as any).isLineMaterial) m.resolution.set(w, h);
    });
  }

  show(on: boolean) {
    this.active = on;
    if (on) this.group.visible = true;
    const targets = [...this.ringMats.map((m) => m.uniforms.uA)];
    gsap.to(targets, { value: on ? 1 : 0, duration: 0.8, onComplete: () => { if (!on) this.group.visible = false; } });
  }

  setCategory(cat: Category, on: boolean) {
    if (on) this.enabled.add(cat); else this.enabled.delete(cat);
    for (const pin of this.pins.values()) {
      if (pin.poi.category !== cat) continue;
      const mats = [(pin.beam.material as THREE.ShaderMaterial).uniforms.uA];
      gsap.to(mats, { value: on ? 1 : 0, duration: 0.6 });
      gsap.to(pin.disc.material as THREE.Material, { opacity: on ? 0.55 : 0, duration: 0.6 });
    }
  }

  /** Draw the route to a POI (animated). */
  drawRoute(id: string): Promise<void> {
    if (this.route) {
      this.group.remove(this.route);
      this.route.geometry.dispose();
      this.route = null;
    }
    const r = (routesData as any).routes[id];
    if (!r) return Promise.resolve();
    let pts: THREE.Vector3[];
    if (r.mode === 'straight') {
      const [a, b] = r.points as number[][];
      const n = 80;
      const A = new THREE.Vector3(a[0], 0, a[1]);
      const pin = this.pins.get(id);
      const B = pin ? new THREE.Vector3(pin.beam.position.x, 0, pin.beam.position.z) : new THREE.Vector3(b[0], 0, b[1]);
      pts = [];
      for (let i = 0; i <= n; i++) {
        const p = A.clone().lerp(B, i / n);
        p.y = this.heights.at(p.x, p.z) + 10 + Math.sin((i / n) * Math.PI) * 900;
        pts.push(p);
      }
    } else {
      pts = [];
      const raw = (r.points as number[][]).map(([x, z]) => new THREE.Vector3(x, 0, z));
      for (let i = 0; i < raw.length - 1; i++) {
        const n = Math.max(1, Math.ceil(raw[i].distanceTo(raw[i + 1]) / 25));
        for (let k = 0; k < n; k++) pts.push(raw[i].clone().lerp(raw[i + 1], k / n));
      }
      pts.push(raw[raw.length - 1]);
      for (const p of pts) p.y = this.heights.at(p.x, p.z) + 4;
    }
    const col = r.mode === 'walk' ? '#7ee0a1' : '#ffb37a';
    const line = this.makeLine(pts, col, 6);
    this.route = line;
    this.group.add(line);
    const geo = line.geometry as LineGeometry;
    const total = pts.length - 1;
    const st = { n: 0 };
    geo.instanceCount = 0;
    return new Promise((res) => {
      gsap.to(st, { n: total, duration: Math.min(3.2, 0.8 + total / 120), ease: 'power1.inOut', onUpdate: () => { geo.instanceCount = Math.floor(st.n); }, onComplete: () => res() });
    });
  }

  clearRoute() {
    if (this.route) {
      this.group.remove(this.route);
      this.route = null;
    }
  }

  update(t: number, dt: number) {
    if (!this.group.visible) return;
    for (const m of this.ringMats) m.uniforms.uT.value = t;
    for (const pin of this.pins.values()) {
      const s = 1 + 0.18 * Math.sin(t * 2.4 + pin.top.x * 0.01);
      pin.disc.scale.setScalar(s);
    }
    if (this.trains) {
      const m = new THREE.Matrix4();
      const p = new THREE.Vector3();
      this.trainState.forEach((tr, i) => {
        const path = this.metroPaths[tr.line];
        tr.d = (tr.d + tr.v * dt + path.total) % path.total;
        let k = 1;
        while (k < path.lens.length - 1 && path.lens[k] < tr.d) k++;
        const f = (tr.d - path.lens[k - 1]) / Math.max(path.lens[k] - path.lens[k - 1], 1e-6);
        p.lerpVectors(path.pts[k - 1], path.pts[k], f);
        this.trains!.setMatrixAt(i, m.makeTranslation(p.x, p.y + 4, p.z));
      });
      this.trains.instanceMatrix.needsUpdate = true;
    }
  }

  /** Top-N POIs for the auto tour (nearest metro first, then a spread of categories). */
  tourIds(): string[] {
    const want = ['medical-university-metro', 'tbilisi-state-medical-university', 'city-mall-saburtalo', 'vake-park', 'freedom-square', 'old-town-abanotubani'];
    const ids = new Set(POIS.map((p) => p.id));
    const picked = want.filter((w) => ids.has(w));
    for (const p of POIS) if (picked.length < 6 && !picked.includes(p.id)) picked.push(p.id);
    return picked.slice(0, 6);
  }
}
