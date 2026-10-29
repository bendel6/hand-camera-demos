import * as THREE from 'three';
import { Tree } from '@dgreenheck/ez-tree';
import layout from '../content/site-layout.json';
import { siteToWorld, SITE_ROT, latLngToWorld } from './coords';
import { applyFx } from './fx';

type V3 = THREE.Vector3;
const tmpM = new THREE.Matrix4();
const tmpQ = new THREE.Quaternion();
const tmpS = new THREE.Vector3();
const tmpP = new THREE.Vector3();
const UP = new THREE.Vector3(0, 1, 0);

/** Collect (geometry, material, localMatrix) for every mesh under a prototype node. */
function parts(proto: THREE.Object3D) {
  proto.updateMatrixWorld(true);
  const inv = proto.matrixWorld.clone().invert();
  const out: Array<{ geo: THREE.BufferGeometry; mat: THREE.Material; local: THREE.Matrix4 }> = [];
  proto.traverse((o) => {
    const m = o as THREE.Mesh;
    if (m.isMesh) out.push({ geo: m.geometry, mat: m.material as THREE.Material, local: inv.clone().multiply(m.matrixWorld) });
  });
  return out;
}

/** A set of InstancedMeshes (one per prototype part) sharing per-instance transforms. */
class InstancedProto {
  meshes: THREE.InstancedMesh[] = [];
  locals: THREE.Matrix4[] = [];
  count: number;
  constructor(proto: THREE.Object3D, count: number, parent: THREE.Object3D, opts: { shadow?: boolean; colorMat?: string } = {}) {
    this.count = count;
    for (const p of parts(proto)) {
      const im = new THREE.InstancedMesh(p.geo, p.mat, count);
      im.castShadow = opts.shadow ?? true;
      im.receiveShadow = true;
      im.frustumCulled = false;
      if (opts.colorMat && p.mat.name === opts.colorMat) im.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(count * 3).fill(1), 3);
      this.meshes.push(im);
      this.locals.push(p.local);
      parent.add(im);
    }
  }
  set(i: number, m: THREE.Matrix4) {
    for (let k = 0; k < this.meshes.length; k++) this.meshes[k].setMatrixAt(i, tmpM.multiplyMatrices(m, this.locals[k]));
  }
  color(i: number, c: THREE.Color) {
    for (const im of this.meshes) if (im.instanceColor) im.setColorAt(i, c);
  }
  commit() {
    for (const im of this.meshes) {
      im.instanceMatrix.needsUpdate = true;
      if (im.instanceColor) im.instanceColor.needsUpdate = true;
    }
  }
  set visible(v: boolean) {
    for (const im of this.meshes) im.visible = v;
  }
}

function siteMatrix(x: number, y: number, h: number, yawSite: number, s = 1, out = new THREE.Matrix4()) {
  siteToWorld(x, y, h, tmpP);
  // site yaw (about up, CCW in plan) -> world yaw = SITE_ROT + yaw
  tmpQ.setFromAxisAngle(UP, SITE_ROT + yawSite);
  tmpS.setScalar(s);
  return out.compose(tmpP, tmpQ, tmpS);
}

// ------------------------------------------------------------------------------------------------- trees
const TREE_VARIANTS: Array<{ key: string; preset: string; height: number; seed: number }> = [
  { key: 'Tree_plane', preset: 'Ash Medium', height: 13, seed: 1203 },
  { key: 'Tree_plane2', preset: 'Oak Medium', height: 11, seed: 77 },
  { key: 'Tree_small', preset: 'Aspen Small', height: 8, seed: 9 },
  { key: 'Tree_cypress', preset: 'Pine Medium', height: 14, seed: 31 },
];

class TreeField {
  trees: Tree[] = [];
  groups = new THREE.Group();
  uniforms = { uWind: { value: 0 } };
  constructor(parent: THREE.Object3D, props: THREE.Object3D) {
    parent.add(this.groups);
    const byKind = new Map<string, Array<{ x: number; y: number; z: number; s: number; r: number }>>();
    for (const t of (layout as any).trees) {
      if (!byKind.has(t.t)) byKind.set(t.t, []);
      byKind.get(t.t)!.push(t);
    }
    for (const v of TREE_VARIANTS) {
      const list = byKind.get(v.key) ?? [];
      if (!list.length) continue;
      const tree = new Tree();
      tree.loadPreset(v.preset);
      tree.options.seed = v.seed;
      tree.generate();
      const box = new THREE.Box3().setFromObject(tree);
      const k = v.height / Math.max(box.max.y - box.min.y, 0.001);
      this.trees.push(tree);
      const height = box.max.y - box.min.y;
      const leafMat = makeLeafMaterial(tree.leavesMesh.material as THREE.MeshPhongMaterial, height, this.uniforms);
      const barkMat = makeBarkMaterial(tree.branchesMesh.material as THREE.MeshPhongMaterial, height, this.uniforms);
      for (const [mesh, mat] of [[tree.branchesMesh, barkMat], [tree.leavesMesh, leafMat]] as const) {
        const im = new THREE.InstancedMesh(mesh.geometry, mat, list.length);
        im.castShadow = true;
        im.receiveShadow = true;
        im.frustumCulled = false;
        list.forEach((t, i) => im.setMatrixAt(i, siteMatrix(t.x, t.y, t.z, t.r, t.s * k)));
        im.instanceMatrix.needsUpdate = true;
        applyFx(mat, 'site');
        this.groups.add(im);
      }
    }
    // shrubs use the low-poly prototype
    const shrubs = byKind.get('Shrub') ?? [];
    const proto = props.getObjectByName('Shrub');
    if (proto && shrubs.length) {
      const ip = new InstancedProto(proto, shrubs.length, this.groups);
      shrubs.forEach((t, i) => ip.set(i, siteMatrix(t.x, t.y, t.z, t.r, t.s)));
      ip.commit();
    }
  }
  update(t: number) {
    this.uniforms.uWind.value = t;
  }
}

/** PBR leaf material with instancing-aware wind and mip-stable alpha (leaves do not vanish with distance). */
function makeLeafMaterial(src: THREE.MeshPhongMaterial, height: number, u: { uWind: { value: number } }) {
  const m = new THREE.MeshStandardMaterial({
    name: 'ez_leaves',
    map: src.map,
    color: src.color.clone().multiplyScalar(0.95),
    side: THREE.DoubleSide,
    alphaTest: 0.42,
    roughness: 0.62,
    metalness: 0,
  });
  if (m.map) m.map.colorSpace = THREE.SRGBColorSpace;
  m.userData.shaderKey = 'ez-leaf';
  m.onBeforeCompile = (sh) => {
    sh.uniforms.uWind = u.uWind;
    sh.uniforms.uTreeH = { value: height };
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nuniform float uWind; uniform float uTreeH;')
      .replace(
        '#include <begin_vertex>',
        `#include <begin_vertex>
        #ifdef USE_INSTANCING
          float wph = dot(instanceMatrix[3].xyz, vec3(0.071, 0.0, 0.053));
        #else
          float wph = 0.0;
        #endif
        float hk = clamp(position.y / uTreeH, 0.0, 1.0);
        vec2 sway = vec2(sin(uWind * 0.9 + wph), cos(uWind * 0.7 + wph * 1.3)) * hk * hk * uTreeH * 0.012;
        transformed.xz += sway;
        transformed += normal * sin(uWind * 3.1 + wph + position.x * 0.4) * 0.12 * hk;`,
      );
    sh.fragmentShader = sh.fragmentShader.replace(
      '#include <alphatest_fragment>',
      `#ifdef USE_MAP
        vec2 dUv = fwidth(vMapUv) * vec2(textureSize(map, 0));
        float lod = max(0.0, 0.5 * log2(max(dot(dUv, dUv), 1e-6)));
        diffuseColor.a *= 1.0 + lod * 0.32;
      #endif
      #include <alphatest_fragment>`,
    );
  };
  return m;
}

function makeBarkMaterial(src: THREE.MeshPhongMaterial, height: number, u: { uWind: { value: number } }) {
  const m = new THREE.MeshStandardMaterial({
    name: 'ez_bark',
    map: src.map,
    normalMap: (src as any).normalMap ?? null,
    color: src.color.clone(),
    roughness: 0.9,
    metalness: 0,
  });
  if (m.map) m.map.colorSpace = THREE.SRGBColorSpace;
  m.userData.shaderKey = 'ez-bark';
  m.onBeforeCompile = (sh) => {
    sh.uniforms.uWind = u.uWind;
    sh.uniforms.uTreeH = { value: height };
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nuniform float uWind; uniform float uTreeH;')
      .replace(
        '#include <begin_vertex>',
        `#include <begin_vertex>
        #ifdef USE_INSTANCING
          float wph = dot(instanceMatrix[3].xyz, vec3(0.071, 0.0, 0.053));
        #else
          float wph = 0.0;
        #endif
        float hk = clamp(position.y / uTreeH, 0.0, 1.0);
        transformed.xz += vec2(sin(uWind * 0.9 + wph), cos(uWind * 0.7 + wph * 1.3)) * hk * hk * uTreeH * 0.012;`,
      );
  };
  return m;
}

/** Real tree positions around the neighbourhood (Overture land cover), low-poly instanced. */
class ContextTrees {
  group = new THREE.Group();
  constructor(parent: THREE.Object3D, props: THREE.Object3D, data: number[][]) {
    const proto = props.getObjectByName('Tree_plane2') ?? props.getObjectByName('Tree_plane');
    if (!proto) return;
    const keep = data.filter(([x, , z]) => {
      // skip the modelled streetscape (site layout has its own trees)
      const e = x, n = -z;
      const c = Math.cos(SITE_ROT), s = Math.sin(SITE_ROT);
      const sx = e * c + n * s, sy = -e * s + n * c;
      return !(sx > -175 && sx < 265 && sy > -62 && sy < 72);
    });
    const ip = new InstancedProto(proto, keep.length, this.group, { shadow: true });
    keep.forEach(([x, y, z, s], i) => {
      tmpP.set(x, y, z);
      tmpQ.setFromAxisAngle(UP, (i * 2.399) % (Math.PI * 2));
      tmpS.setScalar(0.65 + (s ?? 1) * 0.45);
      ip.set(i, tmpM.compose(tmpP, tmpQ, tmpS).clone());
    });
    ip.commit();
    parent.add(this.group);
  }
}

// ------------------------------------------------------------------------------------------------- cars
const CAR_COLOURS = ['#f2f2f0', '#1b1d20', '#8d9297', '#c4c7ca', '#2c3a52', '#6b1f22', '#3d4a3e', '#d8d2c4', '#4a4f57', '#b9b2a3'];

class Traffic {
  protos: InstancedProto[] = [];
  cars: Array<{ lane: number; x: number; speed: number; kind: number; slot: number; y: number }> = [];
  beams: THREE.InstancedMesh;
  lanes: Array<{ y: number; x0: number; x1: number }>;
  route: THREE.CurvePath<THREE.Vector3>;
  routeCar = { t: -1, kind: 0, slot: 0 };
  constructor(parent: THREE.Object3D, props: THREE.Object3D) {
    this.lanes = (layout as any).car_lanes;
    const perKind = 18;
    const kinds = ['Car_sedan', 'Car_suv', 'Car_hatch'];
    kinds.forEach((k) => {
      const proto = props.getObjectByName(k)!;
      const ip = new InstancedProto(proto, perKind + 1, parent, { colorMat: 'M_CarPaint' });
      this.protos.push(ip);
    });
    const used = [0, 0, 0];
    let id = 0;
    this.lanes.forEach((ln, li) => {
      const n = 12;
      for (let i = 0; i < n; i++) {
        const kind = id % 3;
        if (used[kind] >= perKind) continue;
        const slot = used[kind]++;
        const len = ln.x1 - ln.x0;
        this.cars.push({ lane: li, x: ln.x0 + (len * (i + Math.random() * 0.5)) / n, speed: 9 + Math.random() * 5 - li * 0.8, kind, slot, y: ln.y + (Math.random() - 0.5) * 0.25 });
        this.protos[kind].color(slot, new THREE.Color(CAR_COLOURS[(id * 7) % CAR_COLOURS.length]).convertSRGBToLinear());
        id++;
      }
    });
    // spare slot per kind for the car that drives into the parking
    this.routeCar.slot = perKind;
    // headlight beams on the road (additive, visible at night)
    const beamTex = makeBeamTexture();
    const beamGeo = new THREE.PlaneGeometry(14, 5);
    beamGeo.rotateX(-Math.PI / 2);
    beamGeo.translate(9.2, 0.06, 0);
    this.beams = new THREE.InstancedMesh(
      beamGeo,
      new THREE.MeshBasicMaterial({ map: beamTex, color: 0xfff1d0, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: true, fog: false }),
      this.cars.length + 1,
    );
    this.beams.frustumCulled = false;
    parent.add(this.beams);
    // site-frame route into the parking ramp
    const pts = (layout as any).parking_route.map(([x, y]: number[]) => new THREE.Vector3(x, y, 0));
    this.route = new THREE.CurvePath<THREE.Vector3>();
    for (let i = 0; i < pts.length - 1; i++) this.route.add(new THREE.LineCurve3(pts[i], pts[i + 1]));
    for (const ip of this.protos) ip.commit();
  }

  update(dt: number, night: number) {
    const m = new THREE.Matrix4();
    let bi = 0;
    for (const c of this.cars) {
      const ln = this.lanes[c.lane];
      c.x += c.speed * dt;
      if (c.x > ln.x1) c.x = ln.x0 + Math.random() * 20;
      siteMatrix(c.x, c.y, 0, 0, 1, m);
      this.protos[c.kind].set(c.slot, m);
      this.beams.setMatrixAt(bi++, m);
    }
    // a car turns in from the avenue and drives down into the parking every ~35 s
    const rc = this.routeCar;
    if (rc.t < 0 && Math.random() < dt / 30) {
      rc.t = 0;
      rc.kind = Math.floor(Math.random() * 3);
      this.protos[rc.kind].color(rc.slot, new THREE.Color(CAR_COLOURS[Math.floor(Math.random() * CAR_COLOURS.length)]).convertSRGBToLinear());
    }
    for (let k = 0; k < 3; k++) {
      if (rc.t < 0 || k !== rc.kind) this.protos[k].set(rc.slot, m.makeScale(0, 0, 0));
    }
    if (rc.t >= 0) {
      const L = this.route.getLength();
      rc.t += (7.5 * dt) / L;
      if (rc.t >= 1) {
        rc.t = -1;
      } else {
        const p = this.route.getPointAt(rc.t);
        const tan = this.route.getTangentAt(rc.t);
        const yaw = Math.atan2(tan.y, tan.x);
        siteMatrix(p.x, p.y, 0.02, yaw, 1, m);
        this.protos[rc.kind].set(rc.slot, m);
        this.beams.setMatrixAt(bi++, m);
      }
    }
    for (; bi < this.beams.count; bi++) this.beams.setMatrixAt(bi, m.makeScale(0, 0, 0));
    this.beams.instanceMatrix.needsUpdate = true;
    (this.beams.material as THREE.MeshBasicMaterial).opacity = 0.55 * night;
    for (const ip of this.protos) ip.commit();
  }
}

function makeBeamTexture() {
  const c = document.createElement('canvas');
  c.width = 256;
  c.height = 128;
  const g = c.getContext('2d')!;
  const grd = g.createRadialGradient(0, 64, 4, 0, 64, 250);
  grd.addColorStop(0, 'rgba(255,255,255,0.9)');
  grd.addColorStop(0.5, 'rgba(255,240,210,0.35)');
  grd.addColorStop(1, 'rgba(255,240,210,0)');
  g.fillStyle = grd;
  g.beginPath();
  g.moveTo(0, 54);
  g.lineTo(256, 0);
  g.lineTo(256, 128);
  g.lineTo(0, 74);
  g.fill();
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function makeGlowTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d')!;
  const grd = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grd.addColorStop(0, 'rgba(255,255,255,1)');
  grd.addColorStop(0.35, 'rgba(255,255,255,0.45)');
  grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd;
  g.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c);
  return t;
}

// ------------------------------------------------------------------------------------------------- people
const WALK_VERT_DECL = /* glsl */ `
attribute vec3 aPants;
attribute vec3 aSkin;
attribute float aPhase;
uniform float uWalkTime;
varying vec3 vPersonCol;
`;
const WALK_VERT = /* glsl */ `
  // colour zones from vertex colour (R top, G pants, B skin), limb id in alpha
  #ifdef USE_INSTANCING_COLOR
    vec3 topC = instanceColor;
  #else
    vec3 topC = vec3(0.8);
  #endif
  vPersonCol = topC * color.r + aPants * color.g + aSkin * color.b;
  float limb = color.a;
  float ph = uWalkTime * 6.2 + aPhase;
  float sw = 0.0; float pivot = 0.0;
  if (limb > 0.2 && limb < 0.3) { sw = sin(ph) * 0.42; pivot = 0.92; }
  else if (limb > 0.45 && limb < 0.55) { sw = -sin(ph) * 0.42; pivot = 0.92; }
  else if (limb > 0.7 && limb < 0.8) { sw = -sin(ph) * 0.35; pivot = 1.45; }
  else if (limb > 0.95) { sw = sin(ph) * 0.35; pivot = 1.45; }
  if (sw != 0.0) {
    vec3 q = transformed - vec3(0.0, pivot, 0.0);
    float c = cos(sw), s = sin(sw);
    q = vec3(q.x * c - q.y * s, q.x * s + q.y * c, q.z);
    transformed = q + vec3(0.0, pivot, 0.0);
  }
  transformed.y += abs(sin(ph)) * 0.03;
`;

class Crowd {
  im: InstancedProto;
  people: Array<{ path: V3[]; lens: number[]; total: number; d: number; speed: number; dir: number; terrace: boolean }> = [];
  uniforms = { uWalkTime: { value: 0 } };
  constructor(parent: THREE.Object3D, props: THREE.Object3D) {
    const proto = props.getObjectByName('Person')!;
    const paths: Array<{ pts: number[][]; terrace: boolean }> = [
      ...(layout as any).people_paths.map((p: number[][]) => ({ pts: p, terrace: false })),
      ...(layout as any).terrace_paths.map((p: number[][]) => ({ pts: p, terrace: true })),
    ];
    const per = paths.map((p) => Math.max(2, Math.round(polyLen(p.pts) / 9)));
    const total = per.reduce((a, b) => a + b, 0);
    this.im = new InstancedProto(proto, total, parent, { colorMat: 'M_Person' });
    const mat = (this.im.meshes[0].material as THREE.MeshStandardMaterial).clone();
    mat.userData = {};
    this.im.meshes[0].material = mat;
    mat.vertexColors = true;
    const uniforms = this.uniforms;
    mat.userData.shaderKey = 'walk';
    mat.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, uniforms);
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', `#include <common>\n${WALK_VERT_DECL}`)
        .replace('#include <begin_vertex>', `#include <begin_vertex>\n${WALK_VERT}`);
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', '#include <common>\nvarying vec3 vPersonCol;')
        .replace('#include <color_fragment>', 'diffuseColor.rgb = vPersonCol;');
    };
    const geo = this.im.meshes[0].geometry;
    const pants = new Float32Array(total * 3);
    const skin = new Float32Array(total * 3);
    const phase = new Float32Array(total);
    const tops = ['#e8e4dc', '#2b2f36', '#8a2f2b', '#3d5a80', '#c9a66b', '#5b6b4a', '#d9d2c5', '#6c4f7c', '#1f1f22'];
    const legs = ['#22262c', '#3a3f4a', '#5a5047', '#c8bfae', '#1c2535'];
    const skins = ['#e0b896', '#c99a74', '#a8795a', '#f0cfb0'];
    let i = 0;
    paths.forEach((p, pi) => {
      const pts = p.pts.map(([x, y]) => new THREE.Vector3(x, y, 0));
      const lens = [0];
      for (let k = 1; k < pts.length; k++) lens.push(lens[k - 1] + pts[k].distanceTo(pts[k - 1]));
      for (let k = 0; k < per[pi]; k++, i++) {
        this.people.push({ path: pts, lens, total: lens[lens.length - 1], d: Math.random() * lens[lens.length - 1], speed: 1.1 + Math.random() * 0.5, dir: Math.random() < 0.5 ? 1 : -1, terrace: p.terrace });
        this.im.color(i, new THREE.Color(tops[(i * 5) % tops.length]).convertSRGBToLinear());
        const lc = new THREE.Color(legs[(i * 3) % legs.length]).convertSRGBToLinear();
        const sc = new THREE.Color(skins[(i * 7) % skins.length]).convertSRGBToLinear();
        pants.set([lc.r, lc.g, lc.b], i * 3);
        skin.set([sc.r, sc.g, sc.b], i * 3);
        phase[i] = Math.random() * 6.28;
      }
    });
    geo.setAttribute('aPants', new THREE.InstancedBufferAttribute(pants, 3));
    geo.setAttribute('aSkin', new THREE.InstancedBufferAttribute(skin, 3));
    geo.setAttribute('aPhase', new THREE.InstancedBufferAttribute(phase, 1));
    applyFx(mat, 'site');
  }
  update(dt: number, t: number) {
    this.uniforms.uWalkTime.value = t;
    const m = new THREE.Matrix4();
    this.people.forEach((p, i) => {
      p.d += p.speed * dt * p.dir;
      if (p.d > p.total) { p.d = p.total; p.dir = -1; }
      if (p.d < 0) { p.d = 0; p.dir = 1; }
      let k = 1;
      while (k < p.lens.length - 1 && p.lens[k] < p.d) k++;
      const a = p.path[k - 1], b = p.path[k];
      const f = (p.d - p.lens[k - 1]) / Math.max(p.lens[k] - p.lens[k - 1], 1e-6);
      const x = a.x + (b.x - a.x) * f, y = a.y + (b.y - a.y) * f;
      const yaw = Math.atan2(b.y - a.y, b.x - a.x) + (p.dir < 0 ? Math.PI : 0);
      // lateral offset so people pass each other
      const off = p.dir > 0 ? 0.6 : -0.6;
      siteMatrix(x - Math.sin(yaw) * off * 0, y + off * 0.5, p.terrace ? 9.6 : 0.15, yaw, 1, m);
      this.im.set(i, m);
    });
    this.im.commit();
  }
}

function polyLen(p: number[][]) {
  let s = 0;
  for (let i = 1; i < p.length; i++) s += Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]);
  return s;
}

// ------------------------------------------------------------------------------------------------- birds
class Birds {
  mesh: THREE.InstancedMesh;
  n = 24;
  data: Array<{ r: number; h: number; w: number; o: number }> = [];
  wingMat: THREE.MeshBasicMaterial;
  constructor(parent: THREE.Object3D, private centre: V3) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, -0.25, 0, 0.55, 0.2, 0, 0, 0, 0, 0, -0.25, 0, -0.55, 0.2, 0, 0], 3));
    g.setAttribute('wing', new THREE.Float32BufferAttribute([0, 1, 0, 0, 1, 0], 1));
    this.wingMat = new THREE.MeshBasicMaterial({ color: 0x24262a, side: THREE.DoubleSide });
    const u = { uT: { value: 0 } };
    this.wingMat.onBeforeCompile = (s) => {
      s.uniforms.uT = u.uT;
      s.vertexShader = s.vertexShader
        .replace('#include <common>', '#include <common>\nattribute float wing; uniform float uT;')
        .replace('#include <begin_vertex>', `#include <begin_vertex>\n float fl = sin(uT * 9.0 + float(gl_InstanceID) * 1.7); transformed.y += wing * fl * 0.35 * sign(position.z);`);
    };
    (this.wingMat.userData as any).u = u;
    this.mesh = new THREE.InstancedMesh(g, this.wingMat, this.n);
    this.mesh.frustumCulled = false;
    for (let i = 0; i < this.n; i++) this.data.push({ r: 70 + Math.random() * 60, h: 55 + Math.random() * 50, w: 0.08 + Math.random() * 0.05, o: Math.random() * 6.28 });
    parent.add(this.mesh);
  }
  update(t: number) {
    ((this.wingMat.userData as any).u.uT.value = t);
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    this.data.forEach((b, i) => {
      const a = b.o + t * b.w;
      tmpP.set(this.centre.x + Math.cos(a) * b.r, b.h + Math.sin(t * 0.3 + b.o) * 6, this.centre.z + Math.sin(a) * b.r);
      q.setFromAxisAngle(UP, -a);
      tmpS.setScalar(1.6);
      this.mesh.setMatrixAt(i, m.compose(tmpP, q, tmpS));
    });
    this.mesh.instanceMatrix.needsUpdate = true;
  }
}

// ------------------------------------------------------------------------------------------------- night glows
class NightGlow {
  pools: THREE.InstancedMesh;
  shop: THREE.Mesh;
  constructor(parent: THREE.Object3D) {
    const lamps = (layout as any).lamps as number[][];
    const tex = makeGlowTexture();
    const g = new THREE.PlaneGeometry(1, 1);
    g.rotateX(-Math.PI / 2);
    this.pools = new THREE.InstancedMesh(
      g,
      new THREE.MeshBasicMaterial({ map: tex, color: 0xffc98a, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, fog: false }),
      lamps.length,
    );
    const m = new THREE.Matrix4();
    lamps.forEach(([x, y], i) => this.pools.setMatrixAt(i, siteMatrix(x, y, 0.2, 0, 1, m).multiply(new THREE.Matrix4().makeScale(16, 1, 16))));
    this.pools.frustumCulled = false;
    this.pools.renderOrder = 2;
    parent.add(this.pools);
    // warm light spilling from the shopfronts onto the sidewalk
    const c = document.createElement('canvas');
    c.width = 4;
    c.height = 128;
    const gx = c.getContext('2d')!;
    const grd = gx.createLinearGradient(0, 0, 0, 128);
    grd.addColorStop(0, 'rgba(255,255,255,1)');
    grd.addColorStop(1, 'rgba(255,255,255,0)');
    gx.fillStyle = grd;
    gx.fillRect(0, 0, 4, 128);
    const sg = new THREE.PlaneGeometry(75, 7);
    sg.rotateX(-Math.PI / 2);
    this.shop = new THREE.Mesh(
      sg,
      new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(c), color: 0xffb877, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, fog: false }),
    );
    const p = siteToWorld(43.3, -3.5, 0.18);
    this.shop.position.copy(p);
    this.shop.rotation.y = SITE_ROT;
    this.shop.renderOrder = 2;
    parent.add(this.shop);
  }
  update(night: number) {
    (this.pools.material as THREE.MeshBasicMaterial).opacity = 0.42 * night;
    (this.shop.material as THREE.MeshBasicMaterial).opacity = 0.35 * night;
  }
}

// ------------------------------------------------------------------------------------------------- life
export class Life {
  group = new THREE.Group();
  trees: TreeField;
  traffic: Traffic;
  crowd: Crowd;
  birds: Birds;
  glow: NightGlow;
  contextTrees: ContextTrees | null = null;
  constructor(scene: THREE.Scene, props: THREE.Object3D, centre: V3) {
    this.group.name = 'Life';
    scene.add(this.group);
    this.trees = new TreeField(this.group, props);
    this.traffic = new Traffic(this.group, props);
    this.crowd = new Crowd(this.group, props);
    this.birds = new Birds(this.group, centre);
    this.glow = new NightGlow(this.group);
  }
  addContextTrees(props: THREE.Object3D, data: number[][]) {
    if (!this.contextTrees) this.contextTrees = new ContextTrees(this.group, props, data);
  }
  update(dt: number, t: number, night: number) {
    this.trees.update(t);
    this.traffic.update(dt, night);
    this.crowd.update(dt, t);
    this.birds.update(t);
    this.glow.update(night);
  }
}

export { latLngToWorld };
