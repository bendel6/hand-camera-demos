import * as THREE from 'three';
import gsap from 'gsap';
import parkingLayout from '../content/parking-layout.json';
import { FX, applyFx } from './fx';
import { siteToWorld, SITE_ROT } from './coords';
import type { Models } from './models';

const UP = new THREE.Vector3(0, 1, 0);

export interface LayerDef {
  id: string;
  match: RegExp;
  offset: (name: string) => THREE.Vector3;
  order: number;
}

function siteDir(dx: number, dy: number, dz = 0) {
  const v = siteToWorld(dx, dy, dz);
  return v;
}

const DIRS: Record<string, [number, number]> = { S: [0, -1], N: [0, 1], E: [1, 0], W: [-1, 0] };

export const LAYERS: LayerDef[] = [
  { id: 'facade', match: /^(A|B)_facade_[SNEW]$|^P_facade$/, order: 0, offset: (n) => radial(n, 42) },
  { id: 'glazing', match: /^(A|B)_glazing_[SNEW]$|^P_glazing$/, order: 1, offset: (n) => radial(n, 21) },
  { id: 'roof', match: /^(A|B)_crown$|^P_roof$/, order: 2, offset: (n) => new THREE.Vector3(0, n === 'P_roof' ? 16 : 48, 0) },
  { id: 'slabs', match: /^(A|B|P)_slabs$/, order: 3, offset: (n) => (n.startsWith('P') ? new THREE.Vector3(0, -4, 0) : new THREE.Vector3(0, 0, 0)) },
  { id: 'columns', match: /^(A|B|P)_columns$/, order: 4, offset: () => new THREE.Vector3(0, 0, 0) },
  { id: 'cores', match: /^(A|B)_(core|stairs|lift_\d)$/, order: 5, offset: () => new THREE.Vector3(0, 0, 0) },
  { id: 'foundation', match: /^Foundation$/, order: 6, offset: () => new THREE.Vector3(0, -30, 0) },
];

function radial(name: string, dist: number) {
  const m = name.match(/_([SNEW])$/);
  if (!m) return siteDir(0, -dist * 0.7, 0);
  const [dx, dy] = DIRS[m[1]];
  return siteDir(dx * dist, dy * dist, 0);
}

export class Effects {
  exploded = false;
  xray = false;
  parking = false;
  building = false;
  layerNodes = new Map<string, THREE.Object3D[]>();
  basePos = new Map<THREE.Object3D, THREE.Vector3>();
  private ghostMat: THREE.ShaderMaterial;
  /** Fresnel ghost used to fade the building in the parking cutaway. */
  get ghost() {
    this.ghostMat.uniforms.uOpacity.value = 0.14;
    return this.ghostMat;
  }
  private glowMat: THREE.MeshStandardMaterial;
  private liftMat: THREE.MeshStandardMaterial;
  private edgeMat!: THREE.LineBasicMaterial;
  private edges: THREE.LineSegments[] = [];
  private swapped = new Map<THREE.Mesh, THREE.Material | THREE.Material[]>();
  parkingCars: THREE.Group | null = null;
  soil: THREE.Group | null = null;
  liftTweens: gsap.core.Tween[] = [];
  onLayerLabels?: (layers: Array<{ id: string; pos: THREE.Vector3 }>) => void;

  constructor(private scene: THREE.Scene, private models: Models) {
    for (const L of LAYERS) this.layerNodes.set(L.id, []);
    models.building.traverse((o) => {
      for (const L of LAYERS) {
        if (L.match.test(o.name) && o.parent && !L.match.test(o.parent.name)) {
          this.layerNodes.get(L.id)!.push(o);
          this.basePos.set(o, o.position.clone());
        }
      }
    });
    this.ghostMat = new THREE.ShaderMaterial({
      uniforms: { uCol: { value: new THREE.Color(0x8fb8e8) }, uOpacity: { value: 0.18 } },
      vertexShader: /* glsl */ `
        varying vec3 vN; varying vec3 vV;
        void main() {
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */ `
        uniform vec3 uCol; uniform float uOpacity; varying vec3 vN; varying vec3 vV;
        void main() {
          float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.5);
          gl_FragColor = vec4(uCol * (0.2 + 1.2 * f), (0.02 + 0.45 * f) * uOpacity);
        }`,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
    });
    this.glowMat = new THREE.MeshStandardMaterial({ color: 0x1c2630, emissive: new THREE.Color(0x2f8fd8), emissiveIntensity: 0.0, roughness: 0.6, metalness: 0.1, transparent: true, opacity: 0.85 });
    this.edgeMat = new THREE.LineBasicMaterial({ color: new THREE.Color(0x7fd4ff).multiplyScalar(2.2), transparent: true, opacity: 0, depthWrite: false, toneMapped: true });
    this.liftMat = new THREE.MeshStandardMaterial({ color: 0x3a2a10, emissive: new THREE.Color(0xffb04a), emissiveIntensity: 2.5 });
    applyFx(this.glowMat, 'structure');
  }

  // ------------------------------------------------------------------ explode
  layerCentre(id: string): THREE.Vector3 {
    const box = new THREE.Box3();
    for (const n of this.layerNodes.get(id) ?? []) box.expandByObject(n);
    return box.getCenter(new THREE.Vector3());
  }

  setExplode(on: boolean): Promise<void> {
    this.exploded = on;
    const tl = gsap.timeline();
    for (const L of LAYERS) {
      for (const n of this.layerNodes.get(L.id)!) {
        const base = this.basePos.get(n)!;
        // offsets are in world space, the nodes are children of the ENU root (rotated) -> convert
        const off = L.offset(n.name).clone();
        const parentInv = new THREE.Matrix4().copy(n.parent!.matrixWorld).invert();
        const localOff = off.applyMatrix3(new THREE.Matrix3().setFromMatrix4(parentInv));
        const to = on ? base.clone().add(localOff) : base;
        tl.to(n.position, { x: to.x, y: to.y, z: to.z, duration: 1.6, ease: on ? 'power3.out' : 'power3.inOut' }, (on ? L.order : LAYERS.length - 1 - L.order) * 0.16);
      }
    }
    return new Promise((res) => tl.eventCallback('onComplete', () => res()));
  }

  private anchorBox = new THREE.Box3();
  /** Label anchors on representative nodes of each layer (follow the exploded positions). */
  layerLabelPositions(): Array<{ id: string; pos: THREE.Vector3 }> {
    const anchors: Record<string, [string, number]> = {
      facade: ['B_facade_S', 0.75],
      glazing: ['B_glazing_E', 0.55],
      roof: ['A_crown', 1.0],
      slabs: ['A_slabs', 0.62],
      columns: ['B_columns', 0.35],
      cores: ['A_core', 0.9],
      foundation: ['Foundation', 0.5],
    };
    const out: Array<{ id: string; pos: THREE.Vector3 }> = [];
    for (const L of LAYERS) {
      const [name, fy] = anchors[L.id];
      const node = this.layerNodes.get(L.id)!.find((n) => n.name === name) ?? this.layerNodes.get(L.id)![0];
      if (!node) continue;
      this.anchorBox.setFromObject(node);
      const c = this.anchorBox.getCenter(new THREE.Vector3());
      c.y = THREE.MathUtils.lerp(this.anchorBox.min.y, this.anchorBox.max.y, fy);
      out.push({ id: L.id, pos: c });
    }
    return out;
  }

  meshesOfLayer(id: string): THREE.Object3D[] {
    return this.layerNodes.get(id) ?? [];
  }

  // ------------------------------------------------------------------ x-ray
  setXray(on: boolean) {
    if (on === this.xray) return;
    this.xray = on;
    const structure = new Set([...this.layerNodes.get('slabs')!, ...this.layerNodes.get('columns')!, ...this.layerNodes.get('cores')!, ...this.layerNodes.get('foundation')!]);
    if (on) {
      this.models.building.traverse((o) => {
        const m = o as THREE.Mesh;
        if (!m.isMesh) return;
        let p: THREE.Object3D | null = m;
        let isStruct = false;
        while (p) {
          if (structure.has(p)) isStruct = true;
          p = p.parent;
        }
        this.swapped.set(m, m.material);
        const isLift = /_lift_\d/.test(m.name) || /_lift_\d/.test(m.parent?.name ?? '');
        m.material = isLift ? this.liftMat : isStruct ? this.glowMat : this.ghostMat;
        if (!isStruct) m.castShadow = false;
        if (isStruct && !isLift && !m.userData.edges) {
          const e = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry, 30), this.edgeMat);
          e.raycast = () => {};
          m.add(e);
          m.userData.edges = e;
          this.edges.push(e);
        }
      });
      for (const e of this.edges) e.visible = true;
      gsap.to(this.glowMat, { emissiveIntensity: 0.22, duration: 1.2 });
      gsap.to(this.edgeMat, { opacity: 0.9, duration: 1.4 });
      gsap.fromTo(this.ghostMat.uniforms.uOpacity, { value: 0 }, { value: 0.18, duration: 1.0 });
      this.animateLifts(true);
    } else {
      for (const [m, mat] of this.swapped) {
        m.material = mat;
        m.castShadow = true;
      }
      this.swapped.clear();
      this.glowMat.emissiveIntensity = 0;
      this.edgeMat.opacity = 0;
      for (const e of this.edges) e.visible = false;
      this.animateLifts(false);
    }
  }

  private animateLifts(on: boolean) {
    for (const t of this.liftTweens) t.kill();
    this.liftTweens = [];
    if (!on) return;
    this.models.building.traverse((o) => {
      if (/^(A|B)_lift_\d$/.test(o.name)) {
        const floors = o.name.startsWith('A') ? 30 : 16;
        const top = (floors - 1) * 3.3 + 9.6;
        const t = gsap.to(o.position, { [this.upAxis(o)]: top, duration: 6 + Math.random() * 4, ease: 'sine.inOut', yoyo: true, repeat: -1, delay: Math.random() * 3 });
        this.liftTweens.push(t);
      }
    });
  }

  /** Lift nodes are children of the ENU root (Blender Z-up exported to Y-up): the up axis is local y. */
  private upAxis(_o: THREE.Object3D) {
    return 'y';
  }

  // ------------------------------------------------------------------ parking cutaway
  /** Cut depth that exposes a level from above (just below the slab above it). */
  static LEVEL_CUT: Record<string, number> = { B1: -0.45, B2: -4.0, B3: -7.6 };
  parkingLevel = 'B1';

  /**
   * Parking reveal: the building and ground over the plot are sliced away from the top down, then the three
   * basement levels are peeled one after another (B1 -> B2 -> B3) and the view returns to B1.
   */
  async setParking(on: boolean, props: THREE.Object3D, onLevel?: (level: string) => void) {
    this.parking = on;
    if (on) {
      const pk = await this.models.loadParking();
      pk.visible = true;
      if (!this.parkingCars) this.parkingCars = this.buildParkedCars(props);
      this.parkingCars.visible = true;
      if (!this.soil) this.soil = this.buildSoil();
      this.soil.visible = true;
      FX.uCutOn.value = 1;
      FX.uCutMin.value.set(-0.6, -0.7, 130);
      FX.uCutMax.value.set(82.2, 67.4, 400);
      await gsap.to(FX.uCutMin.value, { z: Effects.LEVEL_CUT.B1, duration: 2.8, ease: 'power2.inOut' });
      for (const [i, lv] of ['B1', 'B2', 'B3'].entries()) {
        if (!this.parking) return;
        this.parkingLevel = lv;
        onLevel?.(lv);
        this.levelGlow(lv, 1.8, 0);
        if (i > 0) await gsap.to(FX.uCutMin.value, { z: Effects.LEVEL_CUT[lv], duration: 1.4, ease: 'power2.inOut' });
        await new Promise((r) => setTimeout(r, 1700));
      }
      if (!this.parking) return;
      await this.showLevel('B1');
      onLevel?.('B1');
    } else {
      await gsap.to(FX.uCutMin.value, { z: 130, duration: 1.6, ease: 'power2.inOut' });
      FX.uCutOn.value = 0;
      if (this.models.parking) this.models.parking.visible = false;
      if (this.parkingCars) this.parkingCars.visible = false;
      if (this.soil) this.soil.visible = false;
      for (const l of ['B1', 'B2', 'B3']) this.levelGlow(l, 0, 0);
    }
  }

  showLevel(level: string) {
    this.parkingLevel = level;
    this.levelGlow(level, 1.8, 0);
    return gsap.to(FX.uCutMin.value, { z: Effects.LEVEL_CUT[level], duration: 1.2, ease: 'power2.inOut' });
  }

  levelGlow(level: string, intensity: number, delay: number) {
    this.models.parking?.traverse((o) => {
      const m = o as THREE.Mesh;
      if (!m.isMesh) return;
      for (const mat of (Array.isArray(m.material) ? m.material : [m.material]) as THREE.MeshStandardMaterial[]) {
        if (mat.name === `M_Level${level}`) gsap.to(mat, { emissiveIntensity: intensity, duration: 0.8, delay });
      }
    });
  }

  private buildParkedCars(props: THREE.Object3D): THREE.Group {
    const g = new THREE.Group();
    g.name = 'ParkedCars';
    const kinds = ['Car_sedan', 'Car_suv', 'Car_hatch'];
    const levels = (parkingLayout as any).meta.levels as Array<{ name: string; z: number }>;
    const all: Array<{ x: number; y: number; z: number; facing: number }> = [];
    for (const L of levels) for (const b of (parkingLayout as any).bays[L.name]) if (b.car) all.push({ x: b.x, y: b.y, z: L.z, facing: b.facing });
    const cols = ['#f2f2f0', '#1b1d20', '#8d9297', '#c4c7ca', '#2c3a52', '#6b1f22', '#d8d2c4', '#4a4f57'];
    kinds.forEach((k, ki) => {
      const proto = props.getObjectByName(k);
      if (!proto) return;
      const mine = all.filter((_, i) => i % 3 === ki);
      proto.updateMatrixWorld(true);
      const inv = proto.matrixWorld.clone().invert();
      proto.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (!mesh.isMesh) return;
        const local = inv.clone().multiply(mesh.matrixWorld);
        let mat = mesh.material as THREE.MeshStandardMaterial;
        if (mat.name === 'M_CarPaint') {
          // parked cars sit in the shaded pit: a less metallic paint reads better than mirror-like flakes
          mat = mat.clone();
          mat.userData = {};
          mat.name = 'M_CarPaint';
          mat.metalness = 0.15;
          mat.roughness = 0.38;
          applyFx(mat, 'site');
        }
        const im = new THREE.InstancedMesh(mesh.geometry, mat, mine.length);
        const m = new THREE.Matrix4();
        const q = new THREE.Quaternion();
        mine.forEach((c, i) => {
          const p = siteToWorld(c.x, c.y, c.z + 0.01);
          // nose towards the aisle: bay faces +y (facing 1) or -y
          q.setFromAxisAngle(UP, SITE_ROT + (c.facing > 0 ? -Math.PI / 2 : Math.PI / 2));
          m.compose(p, q, new THREE.Vector3(1, 1, 1)).multiply(local);
          im.setMatrixAt(i, m);
          if (mat.name === 'M_CarPaint') im.setColorAt(i, new THREE.Color(cols[(i * 5 + ki) % cols.length]).convertSRGBToLinear());
        });
        im.castShadow = false;
        im.receiveShadow = true;
        g.add(im);
      });
    });
    this.scene.add(g);
    return g;
  }

  private buildSoil(): THREE.Group {
    const g = new THREE.Group();
    const mat = new THREE.MeshStandardMaterial({ color: 0x6b5442, roughness: 1, side: THREE.DoubleSide });
    const c = document.createElement('canvas');
    c.width = 64;
    c.height = 256;
    const x = c.getContext('2d')!;
    const bands = ['#7a6450', '#6d5641', '#5f4a38', '#806b55', '#57442f', '#4a3a2a'];
    for (let i = 0; i < 256; i += 8) {
      x.fillStyle = bands[Math.floor((i / 256) * bands.length + Math.random() * 0.6) % bands.length];
      x.fillRect(0, i, 64, 8);
    }
    for (let i = 0; i < 600; i++) {
      x.fillStyle = `rgba(30,22,15,${Math.random() * 0.4})`;
      x.fillRect(Math.random() * 64, Math.random() * 256, 1 + Math.random() * 2, 1 + Math.random() * 2);
    }
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    mat.map = tex;
    applyFx(mat, 'site', { cut: false });
    const blocks: Array<[number, number, number, number, number, number]> = [
      [-12, -8, -0.4, 76, -14, -0.06], [82.2, -8, 94, 76, -14, -0.06], [-0.4, 67.4, 82.2, 76, -14, -0.06],
      [-0.4, -8, 82.2, -0.7, -14, -0.2], [-0.4, -0.7, 82.2, 67.4, -16, -12.62],
    ];
    for (const [x0, y0, x1, y1, z0, z1] of blocks) {
      const geo = new THREE.BoxGeometry(x1 - x0, z1 - z0, y1 - y0);
      const uv = geo.attributes.uv as THREE.BufferAttribute;
      for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * 2, uv.getY(i));
      const mesh = new THREE.Mesh(geo, mat);
      const p = siteToWorld((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2);
      mesh.position.copy(p);
      mesh.rotation.y = SITE_ROT;
      g.add(mesh);
    }
    g.visible = false;
    this.scene.add(g);
    return g;
  }

  // ------------------------------------------------------------------ build-up
  buildUp(onPhase: (i: number) => void): Promise<void> {
    FX.uBuildOn.value = 1;
    FX.uBuildH.value = -13;
    const tl = gsap.timeline();
    const phases = [-13, 0, 9.6, 62.4, 108.6, 125];
    for (let i = 0; i < phases.length - 1; i++) {
      tl.to(FX.uBuildH, { value: phases[i + 1], duration: [1.4, 1.4, 3.2, 3.0, 0.8][i], ease: 'none', onStart: () => onPhase(i) });
    }
    return new Promise((res) =>
      tl.eventCallback('onComplete', () => {
        FX.uBuildOn.value = 0;
        res();
      }),
    );
  }
}
