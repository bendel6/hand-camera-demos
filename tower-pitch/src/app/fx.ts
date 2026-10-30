import * as THREE from 'three';
import { SITE_ROT } from './coords';

/**
 * Shader-level effects shared by every scene material, driven by uniforms (so gsap can animate them):
 *  - cutaway: discard fragments inside a site-frame box (parking section reveal)
 *  - build-up: discard above a rising height, with a glowing construction edge
 *  - fade: per-material ghosting used by X-ray / parking modes is done by swapping materials (see effects.ts)
 */
export const FX = {
  uSiteRot: { value: new THREE.Vector2(Math.cos(SITE_ROT), Math.sin(SITE_ROT)) },
  uCutOn: { value: 0 },
  uCutMin: { value: new THREE.Vector3(-20, -1, -40) },
  uCutMax: { value: new THREE.Vector3(100, 28, 200) },
  uBuildOn: { value: 0 },
  uBuildH: { value: 200 },
  uBuildGlow: { value: new THREE.Color(1.0, 0.55, 0.28) },
  uTime: { value: 0 },
};

export type FxRole = 'structure' | 'facade' | 'site' | 'parking' | 'none';

const VERT_DECL = /* glsl */ `
varying vec3 vFxWorld;
`;
const VERT_BODY = /* glsl */ `
#ifdef USE_INSTANCING
  vFxWorld = (modelMatrix * instanceMatrix * vec4(transformed, 1.0)).xyz;
#else
  vFxWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;
#endif
`;
const FRAG_DECL = /* glsl */ `
varying vec3 vFxWorld;
uniform vec2 uSiteRot;
uniform float uCutOn;
uniform vec3 uCutMin;
uniform vec3 uCutMax;
uniform float uBuildOn;
uniform float uBuildH;
uniform vec3 uBuildGlow;
uniform float uFxLag;
uniform float uFxCut;
vec3 fxSite(vec3 w) {
  float e = w.x; float n = -w.z;
  return vec3(e * uSiteRot.x + n * uSiteRot.y, -e * uSiteRot.y + n * uSiteRot.x, w.y);
}
`;
const FRAG_BODY = /* glsl */ `
  vec3 fxS = fxSite(vFxWorld);
  if (uCutOn > 0.5 && uFxCut > 0.5 && all(greaterThan(fxS, uCutMin)) && all(lessThan(fxS, uCutMax))) discard;
  float fxEdge = 0.0;
  if (uBuildOn > 0.5) {
    float lim = uBuildH - uFxLag;
    if (fxS.z > lim) discard;
    fxEdge = smoothstep(lim - 1.2, lim, fxS.z);
  }
`;
const FRAG_EMISSIVE = /* glsl */ `
  totalEmissiveRadiance += uBuildGlow * fxEdge * 6.0;
`;

/** Inject the FX uniforms into a material. lag: build-up delay (m) for this layer; cut: affected by cutaway. */
export function applyFx(mat: THREE.Material, role: FxRole, opts: { lag?: number; cut?: boolean } = {}) {
  const m = mat as THREE.Material & { userData: any };
  if (m.userData.fxApplied) return;
  m.userData.fxApplied = true;
  m.userData.fxRole = role;
  const lag = opts.lag ?? (role === 'facade' ? 9 : 0);
  const cut = opts.cut ?? true;
  const local = { uFxLag: { value: role === 'site' || role === 'none' ? -1000 : lag }, uFxCut: { value: cut ? 1 : 0 } };
  m.userData.fxLocal = local;
  const prev = m.onBeforeCompile;
  if (m.userData.shaderKey == null && prev !== THREE.Material.prototype.onBeforeCompile) {
    m.userData.shaderKey = `custom-${m.uuid}`; // pre-existing patch (e.g. ez-tree wind): keep its program separate
  }
  m.onBeforeCompile = (shader, renderer) => {
    prev?.call(m, shader, renderer);
    Object.assign(shader.uniforms, FX, local);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', `#include <common>\n${VERT_DECL}`)
      .replace('#include <project_vertex>', `#include <project_vertex>\n${VERT_BODY}`);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>\n${FRAG_DECL}`)
      .replace('#include <clipping_planes_fragment>', `#include <clipping_planes_fragment>\n${FRAG_BODY}`);
    if (shader.fragmentShader.includes('#include <emissivemap_fragment>')) {
      shader.fragmentShader = shader.fragmentShader.replace(
        '#include <emissivemap_fragment>',
        `#include <emissivemap_fragment>\n${FRAG_EMISSIVE}`,
      );
    }
  };
  // every patched material shares this wrapper's source, so the cache key must name the extra patches explicitly
  m.customProgramCacheKey = () => `fx|${m.userData.shaderKey ?? ''}`;
  m.needsUpdate = true;
}
