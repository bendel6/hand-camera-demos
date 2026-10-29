import * as THREE from 'three';
import { siteToWorld } from './coords';
import type { Environment } from './environment';

/**
 * Local reflection probe: a cube capture of the real surroundings (city, street, trees, sky) taken from in front of
 * the towers, prefiltered with PMREM and used as the environment map of the building's glass and metal. Without it
 * the glass would only reflect the sky. Re-captured when the time of day changes (debounced).
 */
export class CityReflections {
  private rt = new THREE.WebGLCubeRenderTarget(512, { type: THREE.HalfFloatType, generateMipmaps: false });
  private cam: THREE.CubeCamera;
  private pmrem: THREE.PMREMGenerator;
  private envRT: THREE.WebGLRenderTarget | null = null;
  private timer: number | null = null;
  private targets: THREE.MeshStandardMaterial[] = [];
  readonly probe = siteToWorld(40, -6, 34);

  constructor(private renderer: THREE.WebGLRenderer, private scene: THREE.Scene, private env: Environment, private building: THREE.Object3D) {
    this.cam = new THREE.CubeCamera(1, 25000, this.rt);
    this.cam.position.copy(this.probe);
    this.pmrem = new THREE.PMREMGenerator(renderer);
    const names = /^M_(Glass_Res|Glass_Shop|RailGlass|Spandrel|Fin|Frame|Cladding|Mullion|RailMetal)$/;
    const seen = new Set<THREE.Material>();
    building.traverse((o) => {
      const m = o as THREE.Mesh;
      if (!m.isMesh) return;
      for (const mat of (Array.isArray(m.material) ? m.material : [m.material]) as THREE.MeshStandardMaterial[]) {
        if (!seen.has(mat) && names.test(mat.name)) {
          seen.add(mat);
          this.targets.push(mat);
        }
      }
    });
  }

  /** Capture now (hides the building so the probe sees the city, and centres the sky dome on the probe). */
  capture() {
    const sky = [this.env.sky, this.env.clouds, this.env.stars];
    const saved = sky.map((o) => o.position.clone());
    for (const o of sky) o.position.copy(this.probe);
    const vis = this.building.visible;
    this.building.visible = false;
    this.cam.update(this.renderer, this.scene);
    this.building.visible = vis;
    sky.forEach((o, i) => o.position.copy(saved[i]));
    const next = this.pmrem.fromCubemap(this.rt.texture);
    for (const m of this.targets) {
      m.envMap = next.texture;
      m.needsUpdate = true;
    }
    this.envRT?.dispose();
    this.envRT = next;
  }

  /** Debounced capture (time-of-day slider, context finished loading). */
  request(delay = 700) {
    if (this.timer) clearTimeout(this.timer);
    this.timer = window.setTimeout(() => {
      this.timer = null;
      this.capture();
    }, delay);
  }
}
