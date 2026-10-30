import * as THREE from 'three';
import { Sky } from 'three/addons/objects/Sky.js';
import * as SunCalc from 'suncalc';
import { site, SITE_CENTRE } from './coords';

/** Tbilisi is UTC+4 all year (no DST). */
export const TZ_OFFSET_H = 4;

export function tbilisiDate(base: Date, minutesLocal: number): Date {
  const d = new Date(Date.UTC(base.getUTCFullYear(), base.getUTCMonth(), base.getUTCDate(), 0, 0, 0));
  d.setUTCMinutes(minutesLocal - TZ_OFFSET_H * 60);
  return d;
}

export function fmtTime(minutesLocal: number): string {
  const m = ((Math.round(minutesLocal) % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

const CLOUD_VERT = /* glsl */ `
varying vec3 vDir;
void main() {
  vDir = normalize((modelMatrix * vec4(position, 0.0)).xyz);
  vec4 p = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  gl_Position = p.xyww;
}`;

const CLOUD_FRAG = /* glsl */ `
uniform vec3 uSunDir;
uniform vec3 uSunCol;
uniform vec3 uSkyCol;
uniform float uTime;
uniform float uCover;
uniform float uNight;
uniform float uBright;
varying vec3 vDir;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
  vec2 i = floor(p); vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}
float fbm(vec2 p) {
  float a = 0.5, s = 0.0;
  for (int i = 0; i < 6; i++) { s += a * noise(p); p = p * 2.03 + vec2(1.7, 9.2); a *= 0.5; }
  return s;
}
void main() {
  vec3 d = normalize(vDir);
  if (d.y < 0.01) discard;
  vec2 uv = d.xz / (d.y + 0.08) * 1.6 + vec2(uTime * 0.004, uTime * 0.0015);
  float n = fbm(uv);
  float n2 = fbm(uv * 2.7 + 3.1);
  float c = smoothstep(1.0 - uCover, 1.0 - uCover + 0.32, n * 0.75 + n2 * 0.35);
  // light: thicker cloud = darker core, sun-facing edges lit
  float thick = smoothstep(0.35, 1.0, c);
  float sunAmt = max(dot(d, uSunDir), 0.0);
  vec3 lit = uSunCol * (1.0 + 1.4 * pow(sunAmt, 6.0));
  vec3 shade = mix(uSkyCol, vec3(0.78, 0.8, 0.84), 0.55) * 0.82;
  vec3 col = mix(lit, shade, thick * 0.55) * uBright;
  col = mix(col, vec3(0.018, 0.024, 0.042) + vec3(0.045, 0.028, 0.018), uNight);
  float horizon = smoothstep(0.0, 0.18, d.y);
  gl_FragColor = vec4(col, c * horizon * 0.92);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

const STAR_FRAG = /* glsl */ `
uniform float uNight;
varying float vB;
void main() {
  vec2 p = gl_PointCoord - 0.5;
  float a = smoothstep(0.5, 0.0, length(p));
  gl_FragColor = vec4(vec3(1.0), a * vB * uNight);
}`;
const STAR_VERT = /* glsl */ `
attribute float aB;
varying float vB;
void main() {
  vB = aB;
  vec4 p = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  gl_Position = p.xyww;
  gl_PointSize = 1.0 + aB * 1.6;
}`;

export type Preset = 'day' | 'golden' | 'night';

export class Environment {
  scene: THREE.Scene;
  renderer: THREE.WebGLRenderer;
  sky: Sky;
  clouds: THREE.Mesh;
  stars: THREE.Points;
  sun: THREE.DirectionalLight;
  moonFill: THREE.HemisphereLight;
  sunDir = new THREE.Vector3();
  date = new Date();
  minutes = 13 * 60;
  night = 0; // 0 day .. 1 full night
  golden = 0; // 0..1 warm low sun
  sunAlt = 0;
  envMap: THREE.Texture | null = null;
  private envRT: THREE.WebGLRenderTarget | null = null;
  private pmrem: THREE.PMREMGenerator;
  private envScene = new THREE.Scene();
  private envSky: Sky;
  private envDirty = true;
  private lastEnvAt = 0;
  listeners: Array<() => void> = [];
  shadowFocus = new THREE.Vector3();
  shadowSize = 180;

  constructor(scene: THREE.Scene, renderer: THREE.WebGLRenderer) {
    this.scene = scene;
    this.renderer = renderer;
    this.pmrem = new THREE.PMREMGenerator(renderer);
    this.pmrem.compileEquirectangularShader();

    this.sky = new Sky();
    this.sky.scale.setScalar(30000); // inside the camera far plane (60 km)
    this.sky.frustumCulled = false;
    const sm = this.sky.material as THREE.ShaderMaterial;
    sm.uniforms.turbidity.value = 2.6;
    sm.uniforms.rayleigh.value = 1.15;
    sm.uniforms.mieCoefficient.value = 0.0045;
    sm.uniforms.mieDirectionalG.value = 0.82;
    scene.add(this.sky);

    this.envSky = new Sky();
    this.envSky.scale.setScalar(1000);
    this.envScene.add(this.envSky);
    // ground hemisphere for the environment so reflections below the horizon are not black
    const ground = new THREE.Mesh(
      new THREE.SphereGeometry(900, 32, 16, 0, Math.PI * 2, Math.PI / 2 + 0.02, Math.PI / 2),
      new THREE.MeshBasicMaterial({ color: 0x4a4740, side: THREE.BackSide }),
    );
    this.envScene.add(ground);
    (this.envScene.userData as any).ground = ground;

    this.clouds = new THREE.Mesh(
      new THREE.SphereGeometry(1, 64, 32),
      new THREE.ShaderMaterial({
        vertexShader: CLOUD_VERT,
        fragmentShader: CLOUD_FRAG,
        uniforms: {
          uSunDir: { value: new THREE.Vector3() },
          uSunCol: { value: new THREE.Color() },
          uSkyCol: { value: new THREE.Color(0.55, 0.65, 0.8) },
          uTime: { value: 0 },
          uCover: { value: 0.3 },
          uNight: { value: 0 },
          uBright: { value: 1 },
        },
        side: THREE.BackSide,
        transparent: true,
        depthWrite: false,
        fog: false,
      }),
    );
    this.clouds.scale.setScalar(25000);
    this.clouds.frustumCulled = false;
    this.clouds.renderOrder = -5;
    scene.add(this.clouds);

    const starPos: number[] = [];
    const starB: number[] = [];
    for (let i = 0; i < 2500; i++) {
      const u = Math.random() * 2 - 1;
      const th = Math.random() * Math.PI * 2;
      const r = Math.sqrt(1 - u * u);
      const y = Math.abs(u);
      starPos.push(r * Math.cos(th) * 24000, y * 24000, r * Math.sin(th) * 24000);
      starB.push(Math.pow(Math.random(), 3));
    }
    const sg = new THREE.BufferGeometry();
    sg.setAttribute('position', new THREE.Float32BufferAttribute(starPos, 3));
    sg.setAttribute('aB', new THREE.Float32BufferAttribute(starB, 1));
    this.stars = new THREE.Points(
      sg,
      new THREE.ShaderMaterial({
        vertexShader: STAR_VERT,
        fragmentShader: STAR_FRAG,
        uniforms: { uNight: { value: 0 } },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        fog: false,
      }),
    );
    this.stars.frustumCulled = false;
    this.stars.renderOrder = -6;
    scene.add(this.stars);

    this.sun = new THREE.DirectionalLight(0xffffff, 4);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(4096, 4096);
    this.sun.shadow.bias = -0.00012;
    this.sun.shadow.normalBias = 0.035;
    this.sun.shadow.radius = 3;
    this.sun.shadow.blurSamples = 16;
    const sc = this.sun.shadow.camera;
    sc.near = 1;
    sc.far = 3000;
    scene.add(this.sun, this.sun.target);

    this.moonFill = new THREE.HemisphereLight(0x5a6f99, 0x1b1a1e, 0);
    scene.add(this.moonFill);

    scene.fog = new THREE.FogExp2(0xb8c4d0, 0.000075);
    this.setTime(this.minutes);
  }

  /** Sunrise/sunset (local minutes) for the current date. */
  sunTimes() {
    const t = SunCalc.getTimes(this.date, site.centreLat, site.centreLng);
    const toMin = (d: Date | null) => !d ? 0 : (d.getUTCHours() + TZ_OFFSET_H) * 60 + d.getUTCMinutes();
    return { sunrise: toMin(t.sunrise), sunset: toMin(t.sunset), golden: toMin(t.goldenHour) };
  }

  presetMinutes(p: Preset): number {
    const t = this.sunTimes();
    if (p === 'day') return 13 * 60;
    if (p === 'golden') return t.sunset - 38;
    return t.sunset + 85;
  }

  setTime(minutes: number) {
    this.minutes = minutes;
    const when = tbilisiDate(this.date, minutes);
    const pos = SunCalc.getPosition(when, site.centreLat, site.centreLng);
    // suncalc 2.x: degrees, azimuth clockwise from north
    const az = THREE.MathUtils.degToRad(pos.azimuth);
    const alt = THREE.MathUtils.degToRad(pos.altitude);
    this.sunAlt = alt;
    this.sunDir.set(Math.sin(az) * Math.cos(alt), Math.sin(alt), -Math.cos(az) * Math.cos(alt)).normalize();
    const altDeg = THREE.MathUtils.radToDeg(alt);
    this.night = THREE.MathUtils.smoothstep(-altDeg, -1.5, 7.5);
    this.golden = altDeg > -2 ? 1 - THREE.MathUtils.smoothstep(altDeg, 2, 16) : 0;

    // sky: physical sky for the sun position; keep a slightly elevated sun direction for a lit dusk sky
    const skyDir = this.sunDir.clone();
    const sm = this.sky.material as THREE.ShaderMaterial;
    sm.uniforms.sunPosition.value.copy(skyDir);
    sm.uniforms.turbidity.value = THREE.MathUtils.lerp(2.4, 6.0, this.golden);
    sm.uniforms.rayleigh.value = THREE.MathUtils.lerp(1.1, 2.4, this.golden);
    const esm = this.envSky.material as THREE.ShaderMaterial;
    for (const k of ['sunPosition', 'turbidity', 'rayleigh', 'mieCoefficient', 'mieDirectionalG']) {
      const v = sm.uniforms[k].value;
      esm.uniforms[k].value = v?.clone ? v.clone() : v;
    }

    // sun light: warm at low altitude, moonlight at night
    const warm = new THREE.Color().setHSL(0.07, 0.95, 0.58);
    const noon = new THREE.Color(1.0, 0.97, 0.92);
    const sunCol = noon.clone().lerp(warm, this.golden);
    const dayI = THREE.MathUtils.lerp(7.0, 4.2, this.golden) * (1 - this.night);
    if (this.night > 0.6) {
      // moon: fixed pleasant direction, cool and dim
      this.sunDir.set(-0.45, 0.62, -0.3).normalize();
      this.sun.color.set(0x8fa6d6);
      this.sun.intensity = 0.32 * this.night;
    } else {
      this.sun.color.copy(sunCol);
      this.sun.intensity = Math.max(dayI, 0);
    }
    this.moonFill.intensity = 0.55 * this.night;

    const cm = this.clouds.material as THREE.ShaderMaterial;
    cm.uniforms.uSunDir.value.copy(this.sunDir);
    cm.uniforms.uSunCol.value.copy(sunCol).multiplyScalar(1 - this.night * 0.9);
    cm.uniforms.uNight.value = this.night;
    // match the physical sky's brightness so clouds read as bright cumulus, not grey smudges
    cm.uniforms.uBright.value = THREE.MathUtils.lerp(1.0, 0.75, this.golden) * Math.max(0.15, Math.sin(Math.max(alt, 0.05))) * 1.6 + 0.35;
    cm.uniforms.uSkyCol.value.setRGB(0.55, 0.66, 0.82).lerp(new THREE.Color(0.85, 0.62, 0.5), this.golden);
    (this.stars.material as THREE.ShaderMaterial).uniforms.uNight.value = Math.max(0, this.night - 0.35) / 0.65;

    // aerial perspective tint
    const fog = this.scene.fog as THREE.FogExp2;
    const dayFog = new THREE.Color(0xbfcad6);
    const goldFog = new THREE.Color(0xd9b49a);
    const nightFog = new THREE.Color(0x0d1220);
    fog.color.copy(dayFog).lerp(goldFog, this.golden * 0.85).lerp(nightFog, this.night);
    fog.density = THREE.MathUtils.lerp(0.00007, 0.00011, this.golden);
    const ground = (this.envScene.userData as any).ground as THREE.Mesh;
    (ground.material as THREE.MeshBasicMaterial).color
      .set(0x6d675c)
      .lerp(new THREE.Color(0x7a5a44), this.golden * 0.6)
      .multiplyScalar(1 - this.night * 0.92);
    this.envDirty = true;
    for (const fn of this.listeners) fn();
  }

  /** Fit the shadow frustum around the point of interest (tight when close = crisp shadows). */
  updateShadow(focus: THREE.Vector3, camDist: number) {
    const size = THREE.MathUtils.clamp(camDist * 0.75, 70, 900);
    this.shadowFocus.copy(focus);
    this.shadowSize = size;
    const d = this.sunDir.y < 0.05 ? new THREE.Vector3(0.3, 0.5, 0.2).normalize() : this.sunDir;
    this.sun.position.copy(focus).addScaledVector(d, 1200);
    this.sun.target.position.copy(focus);
    const sc = this.sun.shadow.camera;
    // snap to texels to avoid shimmering while orbiting
    const texel = (2 * size) / this.sun.shadow.mapSize.x;
    sc.left = -size;
    sc.right = size;
    sc.top = size;
    sc.bottom = -size;
    sc.updateProjectionMatrix();
    this.sun.position.x = Math.round(this.sun.position.x / texel) * texel;
    this.sun.position.z = Math.round(this.sun.position.z / texel) * texel;
    this.sun.target.updateMatrixWorld();
  }

  get envDirtyFlag() {
    return this.envDirty;
  }

  /** Regenerate the environment map now (used by headless renders). */
  forceEnv() {
    this.lastEnvAt = 0;
    this.envDirty = true;
    this.update(0, 0);
  }

  update(dt: number, elapsed: number) {
    if (elapsed) (this.clouds.material as THREE.ShaderMaterial).uniforms.uTime.value = elapsed;
    const now = performance.now();
    if (this.envDirty && now - this.lastEnvAt > 180) {
      this.envDirty = false;
      this.lastEnvAt = now;
      const rt = this.pmrem.fromScene(this.envScene, 0, 1, 2000);
      const old = this.envRT;
      this.envRT = rt;
      this.envMap = rt.texture;
      this.scene.environment = rt.texture;
      this.scene.environmentIntensity = THREE.MathUtils.lerp(0.5, 0.32, this.golden) * (1 - this.night * 0.85);
      if (old) old.dispose();
    }
    void dt;
  }

  /** Approximate horizon colour, for UI tinting. */
  get isNight() {
    return this.night > 0.5;
  }
}

export { SITE_CENTRE };
