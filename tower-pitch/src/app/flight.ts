import * as THREE from 'three';
import gsap from 'gsap';
import type { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { siteToWorld } from './coords';

export interface View {
  pos: THREE.Vector3;
  target: THREE.Vector3;
}

/** Site-frame helper: camera at (x,y,h) looking at (tx,ty,th). */
export function view(x: number, y: number, h: number, tx: number, ty: number, th: number): View {
  return { pos: siteToWorld(x, y, h), target: siteToWorld(tx, ty, th) };
}

export const VIEWS = {
  overview: view(-95, -150, 95, 42, 34, 42),
  intro0: view(-900, -1400, 900, 40, 30, 40),
  entrance: view(36, -36, 4.2, 44, 0, 5.5),
  parking: view(-30, -48, 72, 40, 30, -6),
  green: view(108, 98, 46, 64, 44, 4),
  rooftop: view(-10, -18, 48, 30, 18, 9.6),
  facade: view(74, -16, 44, 60, 2.1, 46),
  crown: view(70, -40, 128, 23, 41, 108),
  structure: view(-190, -230, 150, 40, 32, 48),
  buildup: view(-120, -150, 80, 40, 32, 40),
  location: view(-1300, -2600, 2100, 40, 30, 0),
};

export class Flight {
  busy = false;
  private tl: gsap.core.Timeline | null = null;
  constructor(private camera: THREE.PerspectiveCamera, private controls: OrbitControls) {}

  /** Eased flight with an arc over long distances (camera lifts while travelling). */
  to(v: View, duration?: number, opts: { arc?: number; ease?: string } = {}): Promise<void> {
    this.tl?.kill();
    const p0 = this.camera.position.clone();
    const t0 = this.controls.target.clone();
    const dist = p0.distanceTo(v.pos);
    const dur = duration ?? THREE.MathUtils.clamp(1.4 + Math.log10(1 + dist) * 0.9, 1.6, 5.5);
    const arc = opts.arc ?? Math.min(dist * 0.25, 2500);
    const state = { k: 0 };
    this.busy = true;
    this.controls.enabled = false;
    return new Promise((res) => {
      this.tl = gsap.timeline({
        onComplete: () => {
          this.busy = false;
          this.controls.enabled = true;
          res();
        },
      });
      this.tl.to(state, {
        k: 1,
        duration: dur,
        ease: opts.ease ?? 'power2.inOut',
        onUpdate: () => {
          const k = state.k;
          this.camera.position.lerpVectors(p0, v.pos, k);
          this.camera.position.y += Math.sin(Math.PI * k) * arc;
          this.controls.target.lerpVectors(t0, v.target, THREE.MathUtils.smootherstep(k, 0, 1));
          this.camera.lookAt(this.controls.target);
        },
      });
    });
  }

  stop() {
    this.tl?.kill();
    this.busy = false;
    this.controls.enabled = true;
  }

  /** Slow cinematic orbit around a target (for build-up / present mode). */
  orbit(target: THREE.Vector3, radius: number, height: number, startAngle: number, sweep: number, duration: number) {
    this.tl?.kill();
    const s = { a: startAngle };
    this.busy = true;
    this.controls.enabled = false;
    return new Promise<void>((res) => {
      this.tl = gsap.timeline({ onComplete: () => { this.busy = false; this.controls.enabled = true; res(); } });
      this.tl.to(s, {
        a: startAngle + sweep,
        duration,
        ease: 'sine.inOut',
        onUpdate: () => {
          this.camera.position.set(target.x + Math.cos(s.a) * radius, target.y + height, target.z + Math.sin(s.a) * radius);
          this.controls.target.copy(target);
          this.camera.lookAt(target);
        },
      });
    });
  }
}
