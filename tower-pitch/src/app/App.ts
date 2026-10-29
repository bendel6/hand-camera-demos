import * as THREE from 'three';
import gsap from 'gsap';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { Environment, Preset } from './environment';
import { Post } from './post';
import { Models } from './models';
import { Life } from './life';
import { Effects, LAYERS } from './effects';
import { Location, POIS, Category } from './location';
import { GoogleTiles } from './tiles';
import { Flight, VIEWS, View, view } from './flight';
import { INTERIOR } from './materials';
import { FX } from './fx';
import { SITE_CENTRE, siteToWorld } from './coords';
import type { UI } from '../ui/ui';

export type Mode = 'overview' | 'location' | 'structure' | 'parking' | 'buildup' | 'greenery' | 'compare';

export interface ScreenLabel {
  key: string;
  x: number;
  y: number;
  visible: boolean;
  depth: number;
}

export const HOTSPOTS: Array<{ id: string; at: THREE.Vector3; view: View; image?: string }> = [
  { id: 'entrance', at: siteToWorld(44, -0.5, 6), view: VIEWS.entrance, image: '/assets/pdf/render-p08.webp' },
  { id: 'parking', at: siteToWorld(46.4, 50, 4), view: view(70, 110, 32, 46, 48, 2), image: '/assets/pdf/siteplan.webp' },
  { id: 'green', at: siteToWorld(66, 50, 5), view: VIEWS.green, image: '/assets/pdf/siteplan.webp' },
  { id: 'rooftop', at: siteToWorld(25, 14, 12), view: VIEWS.rooftop, image: '/assets/pdf/render-p05.webp' },
  { id: 'facade', at: siteToWorld(61, 2.1, 42), view: VIEWS.facade, image: '/assets/pdf/render-p07.webp' },
];

export class App {
  renderer: THREE.WebGLRenderer;
  scene = new THREE.Scene();
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  env: Environment;
  post: Post;
  models: Models;
  life!: Life;
  effects!: Effects;
  location: Location;
  tiles: GoogleTiles | null = null;
  flight: Flight;
  ui!: UI;
  mode: Mode = 'overview';
  clock = new THREE.Clock();
  elapsed = 0;
  compareX = 0.5;
  present = false;
  presentIndex = 0;
  touring = false;
  private raycaster = new THREE.Raycaster();
  private ghosted = false;
  private ghostSwap = new Map<THREE.Mesh, THREE.Material | THREE.Material[]>();
  private nightMats: THREE.MeshStandardMaterial[] = [];
  private frameCount = 0;
  private lastLabelAt = 0;
  private tourAbort = false;
  private hiddenForBefore: THREE.Object3D[] = [];

  constructor(canvas: HTMLCanvasElement, opts: { preserve?: boolean } = {}) {
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: false,
      powerPreference: 'high-performance',
      stencil: false,
      preserveDrawingBuffer: !!opts.preserve,
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(window.innerWidth, window.innerHeight, false);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.NoToneMapping;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;

    this.camera = new THREE.PerspectiveCamera(38, window.innerWidth / window.innerHeight, 0.5, 80000);
    this.camera.position.copy(VIEWS.intro0.pos);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.target.copy(VIEWS.intro0.target);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.06;
    this.controls.minDistance = 6;
    this.controls.maxDistance = 12000;
    this.controls.maxPolarAngle = Math.PI * 0.82;
    this.controls.screenSpacePanning = false;
    this.controls.zoomSpeed = 1.1;

    this.env = new Environment(this.scene, this.renderer);
    this.post = new Post(this.renderer, this.scene, this.camera);
    this.models = new Models(this.scene, this.renderer);
    this.location = new Location(this.scene);
    this.flight = new Flight(this.camera, this.controls);

    window.addEventListener('resize', () => this.resize());
    canvas.addEventListener('dblclick', (e) => this.onDoubleClick(e));
    window.addEventListener('keydown', (e) => this.onKey(e));
    this.env.listeners.push(() => this.onLighting());
  }

  async load(onProgress: (label: string, f: number) => void) {
    await this.models.loadCore((l, f) => onProgress(l, f * 0.85));
    onProgress('life', 0.88);
    this.life = new Life(this.scene, this.models.props, SITE_CENTRE);
    this.effects = new Effects(this.scene, this.models);
    onProgress('location', 0.92);
    await this.location.init();
    this.collectNightMaterials();
    const key = import.meta.env.VITE_GOOGLE_KEY as string | undefined;
    if (key) {
      this.tiles = new GoogleTiles(this.scene, this.camera, this.renderer, key);
      this.tiles.setVisible(true);
    } else {
      // open-data city model (Overture + terrain), loaded in the background
      this.models.loadContext().then(async () => {
        const res = await fetch('/data/trees-near.json').catch(() => null);
        if (res && res.ok) {
          const d = await res.json();
          this.life.addContextTrees(this.models.props, d.trees);
        }
      });
    }
    this.env.setTime(this.env.presetMinutes('golden'));
    this.onLighting();
    // compile shaders up front so the first frames do not stutter
    this.renderer.compile(this.scene, this.camera);
    onProgress('ready', 1);
  }

  private collectNightMaterials() {
    const seen = new Set<THREE.Material>();
    this.scene.traverse((o) => {
      const m = o as THREE.Mesh;
      if (!m.isMesh) return;
      for (const mat of (Array.isArray(m.material) ? m.material : [m.material]) as THREE.MeshStandardMaterial[]) {
        if (seen.has(mat) || !mat.userData?.nightEmissive) continue;
        seen.add(mat);
        this.nightMats.push(mat);
      }
    });
  }

  /** Respond to time-of-day changes: interiors, street lights, headlights, exposure. */
  private onLighting() {
    const n = this.env.night;
    INTERIOR.uNight.value = n;
    INTERIOR.uDay.value = THREE.MathUtils.lerp(1.0, 0.25, n) * (1 - this.env.golden * 0.35);
    for (const m of this.nightMats) {
      const base: Record<string, number> = { M_HeadLight: 9, M_TailLight: 5, M_LampHead: 14 };
      const name = m.name;
      if (name in base) {
        m.emissive.set(name === 'M_TailLight' ? 0xff2a1a : name === 'M_LampHead' ? 0xffd9a0 : 0xfff3d6);
        m.emissiveIntensity = base[name] * THREE.MathUtils.smoothstep(n, 0.15, 0.6);
      }
    }
    this.post.grade.exposure = THREE.MathUtils.lerp(0.68, 1.55, n) * THREE.MathUtils.lerp(1, 1.3, this.env.golden);
    this.post.bloom.intensity = THREE.MathUtils.lerp(0.45, 1.05, n);
  }

  setPreset(p: Preset, animate = true) {
    const to = this.env.presetMinutes(p);
    if (!animate) return this.env.setTime(to);
    const s = { m: this.env.minutes };
    gsap.to(s, { m: to, duration: 2.5, ease: 'power2.inOut', onUpdate: () => this.env.setTime(s.m) });
  }

  // ------------------------------------------------------------------------------------------ modes
  async setMode(mode: Mode) {
    const prev = this.mode;
    if (prev === mode && mode !== 'overview') return;
    this.mode = mode;
    this.tourAbort = true;
    // leave previous mode
    if (prev === 'location' && mode !== 'location') {
      this.location.show(false);
      this.location.clearRoute();
      gsap.to((this.scene.fog as THREE.FogExp2), { density: 0.000075, duration: 1.5 });
    }
    if (prev === 'structure' && mode !== 'structure') {
      if (this.effects.exploded) await this.effects.setExplode(false);
      this.effects.setXray(false);
      this.post.outline.selection.clear();
    }
    if (prev === 'parking' && mode !== 'parking') {
      await this.effects.setParking(false, this.models.props);
      this.buildingShadows(true);
      this.controls.maxPolarAngle = Math.PI * 0.82;
    }
    if (prev === 'compare') this.setBefore(false);
    this.controls.minDistance = mode === 'location' ? 200 : 6;

    switch (mode) {
      case 'overview':
        await this.flight.to(VIEWS.overview);
        break;
      case 'location':
        this.location.show(true);
        if (this.tiles) this.tiles.setVisible(true);
        else this.models.loadContext();
        gsap.to(this.scene.fog as THREE.FogExp2, { density: 0.000045, duration: 2 });
        await this.flight.to(VIEWS.location, 4.5);
        break;
      case 'structure':
        await this.flight.to(VIEWS.structure);
        break;
      case 'parking':
        this.controls.maxPolarAngle = Math.PI / 2 + 0.25;
        this.buildingShadows(false);
        await this.flight.to(VIEWS.parking, 2.6);
        await this.effects.setParking(true, this.models.props, (lv) => this.ui.onParkingLevel(lv));
        break;
      case 'buildup':
        await this.flight.to(VIEWS.buildup, 2.2);
        await this.runBuildUp();
        break;
      case 'greenery':
        await this.flight.to(VIEWS.green, 2.6);
        break;
      case 'compare':
        await this.flight.to(view(-35, -95, 40, 40, 30, 38), 2.4);
        this.setBefore(true);
        break;
    }
  }

  /** Cut-away geometry still casts shadows from the depth pass, so building shadows are off during cutaways. */
  buildingShadows(on: boolean) {
    this.models.building.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.isMesh) m.castShadow = on;
    });
  }

  async runBuildUp() {
    this.buildingShadows(false);
    const orbit = this.flight.orbit(SITE_CENTRE.clone().setY(30), 210, 70, -2.2, 1.1, 11.5);
    await this.effects.buildUp((i) => this.ui.showPhase(i));
    await orbit;
    this.buildingShadows(true);
    this.ui.showPhase(-1);
  }

  /** Building turns into a translucent ghost (parking cutaway). */
  ghostBuilding(on: boolean) {
    if (on === this.ghosted) return;
    this.ghosted = on;
    if (on) {
      const ghost = this.effects.ghost;
      this.models.building.traverse((o) => {
        const m = o as THREE.Mesh;
        if (!m.isMesh || m.userData.node === 'Foundation') return;
        this.ghostSwap.set(m, m.material);
        m.material = ghost;
        m.castShadow = false;
      });
    } else {
      for (const [m, mat] of this.ghostSwap) {
        m.material = mat;
        m.castShadow = true;
      }
      this.ghostSwap.clear();
    }
  }

  setBefore(on: boolean) {
    const before = this.models.nodes.get('S_before');
    if (!on) {
      for (const o of this.hiddenForBefore) o.visible = true;
      this.hiddenForBefore = [];
      if (before) before.visible = false;
    }
    this.compareActive = on;
  }
  compareActive = false;

  async explode(on: boolean) {
    if (this.mode !== 'structure') await this.setMode('structure');
    if (on && this.effects.xray) this.effects.setXray(false);
    await this.effects.setExplode(on);
  }

  xray(on: boolean) {
    if (on && this.effects.exploded) this.effects.setExplode(false);
    this.effects.setXray(on);
  }

  async focusHotspot(id: string) {
    const h = HOTSPOTS.find((x) => x.id === id);
    if (!h) return;
    await this.flight.to(h.view);
  }

  async focusPoi(id: string) {
    const pin = this.location.pins.get(id);
    if (!pin) return;
    const p = pin.beam.position.clone();
    const dir = p.clone().sub(SITE_CENTRE).setY(0);
    const d = Math.max(dir.length(), 1);
    dir.normalize();
    // look from behind the site towards the POI, high enough to see both
    const back = Math.min(900 + d * 0.35, 4200);
    const camPos = p.clone().addScaledVector(dir, -back * 0.55).add(new THREE.Vector3(-dir.z, 0, dir.x).multiplyScalar(back * 0.3));
    camPos.y = p.y + Math.min(450 + d * 0.28, 3200);
    const mid = SITE_CENTRE.clone().lerp(p, 0.62);
    const route = this.location.drawRoute(id);
    await this.flight.to({ pos: camPos, target: mid }, undefined, { arc: 200 });
    await route;
  }

  async autoTour(onStep: (id: string | null) => void) {
    this.touring = true;
    this.tourAbort = false;
    if (this.mode !== 'location') await this.setMode('location');
    this.tourAbort = false;
    for (const id of this.location.tourIds()) {
      if (this.tourAbort) break;
      onStep(id);
      await this.focusPoi(id);
      await new Promise((r) => setTimeout(r, 3200));
    }
    if (!this.tourAbort) {
      onStep(null);
      this.location.clearRoute();
      await this.flight.to(VIEWS.location, 4);
    }
    this.touring = false;
  }

  stopTour() {
    this.tourAbort = true;
    this.flight.stop();
    this.touring = false;
  }

  async introFlight() {
    this.camera.position.copy(VIEWS.intro0.pos);
    this.controls.target.copy(VIEWS.intro0.target);
    await this.flight.to(VIEWS.overview, 6.5, { arc: 0, ease: 'power3.inOut' });
  }

  // ------------------------------------------------------------------------------------------ input
  private onDoubleClick(e: MouseEvent) {
    const r = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const targets: THREE.Object3D[] = [this.models.building, this.models.site];
    if (this.mode === 'location') {
      if (this.models.terrain) targets.push(this.models.terrain);
      if (this.tiles) targets.push(this.tiles.tiles.group);
    }
    const hit = this.raycaster.intersectObjects(targets, true)[0];
    if (!hit) return;
    const dist = this.camera.position.distanceTo(this.controls.target);
    const newDist = THREE.MathUtils.clamp(dist * 0.55, 25, 4000);
    const dir = this.camera.position.clone().sub(this.controls.target).normalize();
    this.flight.to({ pos: hit.point.clone().addScaledVector(dir, newDist), target: hit.point }, 1.6, { arc: 0 });
  }

  private onKey(e: KeyboardEvent) {
    if (!this.present) return;
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      this.presentIndex = (this.presentIndex + (e.key === 'ArrowRight' ? 1 : HOTSPOTS.length - 1)) % HOTSPOTS.length;
      const h = HOTSPOTS[this.presentIndex];
      this.focusHotspot(h.id);
      this.ui.openHotspot(h.id, false);
    }
  }

  resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h, false);
    this.post.setSize(w, h);
    const pr = this.renderer.getPixelRatio();
    this.location.setResolution(w * pr, h * pr);
  }

  // ------------------------------------------------------------------------------------------ labels
  project(p: THREE.Vector3, key: string): ScreenLabel {
    const v = p.clone().project(this.camera);
    const w = window.innerWidth;
    const h = window.innerHeight;
    const camSpace = p.clone().applyMatrix4(this.camera.matrixWorldInverse);
    return { key, x: (v.x * 0.5 + 0.5) * w, y: (-v.y * 0.5 + 0.5) * h, visible: camSpace.z < 0 && Math.abs(v.x) < 1.15 && Math.abs(v.y) < 1.15, depth: -camSpace.z };
  }

  private updateLabels() {
    const out: ScreenLabel[] = [];
    if (this.mode === 'overview' || this.mode === 'greenery' || this.present) {
      for (const h of HOTSPOTS) out.push(this.project(h.at, `hot:${h.id}`));
    }
    if (this.mode === 'structure' && this.effects.exploded) {
      for (const l of this.effects.layerLabelPositions()) out.push(this.project(l.pos, `layer:${l.id}`));
    }
    if (this.mode === 'parking' && this.effects.parking) {
      for (const [i, lv] of ['B1', 'B2', 'B3'].entries()) out.push(this.project(siteToWorld(-3, 8 + i * 16, -1.6 - i * 3.6), `level:${lv}`));
    }
    if (this.mode === 'location') {
      for (const pin of this.location.pins.values()) {
        if (!this.location.enabled.has(pin.poi.category as Category)) continue;
        out.push(this.project(pin.top, `poi:${pin.poi.id}`));
      }
      for (const r of this.location.ringLabels) out.push(this.project(r.pos, `ring:${r.text}`));
      out.push(this.project(siteToWorld(40, 32, 140), 'site:here'));
    }
    this.ui.positionLabels(out);
  }

  // ------------------------------------------------------------------------------------------ loop
  start() {
    this.renderer.setAnimationLoop(() => this.frame());
  }

  /** Render one frame synchronously (headless screenshots). */
  frameOnce() {
    this.env.forceEnv();
    this.frame();
  }

  /** Jump the camera to a named view without animation. */
  jump(v: View) {
    this.camera.position.copy(v.pos);
    this.controls.target.copy(v.target);
    this.camera.lookAt(v.target);
    this.controls.update();
  }

  private frame() {
    const dt = Math.min(this.clock.getDelta(), 0.1);
    this.elapsed += dt;
    FX.uTime.value = this.elapsed;
    if (!this.flight.busy) this.controls.update();
    // never below the ground (except inside the parking cutaway)
    const floorY = this.mode === 'parking' ? -12 : 1.2;
    if (this.camera.position.y < floorY) this.camera.position.y = floorY;
    const dist = this.camera.position.distanceTo(this.controls.target);
    this.camera.near = THREE.MathUtils.clamp(dist * 0.0025, 0.25, 40);
    this.camera.far = Math.max(60000, dist * 30);
    this.camera.updateProjectionMatrix();
    this.env.updateShadow(this.controls.target, dist);
    this.env.update(dt, this.elapsed);
    this.life?.update(dt, this.elapsed, this.env.night);
    this.location.update(this.elapsed, dt);
    this.tiles?.update();
    // the sky dome follows the camera so it never clips
    this.env.sky.position.copy(this.camera.position);
    this.env.clouds.position.copy(this.camera.position);
    this.env.stars.position.copy(this.camera.position);

    if (this.compareActive) this.renderCompare(dt);
    else this.post.render(dt);

    const now = performance.now();
    if (this.ui?.app && this.effects && now - this.lastLabelAt > 30) {
      this.lastLabelAt = now;
      this.updateLabels();
      this.ui.tick(this);
    }
    this.frameCount++;
  }

  /** Split-screen: left of the handle shows the site today, right shows the project. */
  private renderCompare(dt: number) {
    const r = this.renderer;
    const w = window.innerWidth;
    const h = window.innerHeight;
    const split = Math.round(w * this.compareX);
    const before = this.models.nodes.get('S_before');
    const project = [this.models.building, this.models.nodes.get('S_play'), this.models.nodes.get('S_furniture')].filter(Boolean) as THREE.Object3D[];
    r.setScissorTest(true);
    // before
    r.setScissor(0, 0, split, h);
    for (const o of project) o.visible = false;
    if (before) before.visible = true;
    if (this.life) this.life.trees.groups.visible = false;
    this.post.render(dt);
    // after
    r.setScissor(split, 0, w - split, h);
    for (const o of project) o.visible = true;
    if (before) before.visible = false;
    if (this.life) this.life.trees.groups.visible = true;
    this.post.render(dt);
    r.setScissorTest(false);
  }

  /** Layer ids for the UI. */
  get layerIds() {
    return LAYERS.map((l) => l.id);
  }

  get pois() {
    return POIS;
  }
}
