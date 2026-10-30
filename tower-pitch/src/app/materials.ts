import * as THREE from 'three';
import { applyFx, FxRole } from './fx';

/**
 * Material upgrades applied by name after loading the Blender GLBs.
 * Glass uses interior mapping: each window shows a fake 3D room (back wall, side walls, floor, ceiling with a
 * light), randomly lit / curtained per room, computed in the site frame so rooms line up with the facades.
 */
export const INTERIOR = {
  uNight: { value: 0 }, // 0 day .. 1 night (lit-room fraction + brightness)
  uDay: { value: 1 },
  uSiteRot2: { value: new THREE.Vector2(1, 0) },
};

const INTERIOR_DECL = /* glsl */ `
varying vec3 vIwPos;
varying vec3 vIwNrm;
uniform float uNight;
uniform float uDay;
uniform vec2 uSiteRot2;
uniform vec3 uRoom;       // width, depth, floor height
uniform float uBase;      // first floor level (m)
uniform float uShop;      // 1 = podium shops
float ihash(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
vec3 toSite(vec3 w) { float e = w.x, n = -w.z; return vec3(e * uSiteRot2.x + n * uSiteRot2.y, -e * uSiteRot2.y + n * uSiteRot2.x, w.y); }
vec3 dirSite(vec3 d) { float e = d.x, n = -d.z; return vec3(e * uSiteRot2.x + n * uSiteRot2.y, -e * uSiteRot2.y + n * uSiteRot2.x, d.y); }

vec3 interiorColour(vec3 wpos, vec3 wnrm, vec3 camPos, out float lit) {
  vec3 p = toSite(wpos);
  vec3 n = dirSite(wnrm);
  vec3 d = normalize(dirSite(wpos - camPos));
  // facade axis: tangent u, depth w (into the building), vertical v
  bool alongX = abs(n.y) > abs(n.x);
  float u = alongX ? p.x : p.y;
  float du = alongX ? d.x : d.y;
  float dw = alongX ? -sign(n.y) * d.y : -sign(n.x) * d.x;
  float fh = uRoom.z;
  float base = uBase;
  if (uShop > 0.5) { if (p.z < 5.0) { base = 0.0; fh = 5.0; } else { base = 5.0; fh = 4.6; } }
  float v = p.z - base;
  float fl = floor(v / fh);
  float fv = v - fl * fh;
  float W = uRoom.x;
  float cu = floor(u / W);
  float fu = u - cu * W;
  float D = uRoom.y;
  dw = max(dw, 0.02);
  // distances to room bounds
  float tU = du > 0.0 ? (W - fu) / du : -fu / min(du, -1e-4);
  float tV = d.z > 0.0 ? (fh - fv) / d.z : -fv / min(d.z, -1e-4);
  float tW = D / dw;
  float t = min(tU, min(tV, tW));
  vec3 rnd = vec3(cu, fl, alongX ? 1.0 + sign(n.y) : 5.0 + sign(n.x));
  float h1 = ihash(rnd), h2 = ihash(rnd + 7.31), h3 = ihash(rnd + 19.7);
  float hu = fu + du * t, hv = fv + d.z * t, hw = dw * t;
  vec3 wall = mix(vec3(0.78, 0.74, 0.68), vec3(0.62, 0.66, 0.70), h2);
  vec3 col;
  float shade;
  if (t == tW) {           // back wall with a darker 'furniture' band and a picture
    col = wall * 0.95;
    float sofa = step(hv, 0.85) * step(0.15 * W, hu) * step(hu, 0.85 * W);
    col = mix(col, vec3(0.25, 0.22, 0.2) + h3 * vec3(0.2, 0.12, 0.08), sofa * 0.85);
    float art = step(1.5, hv) * step(hv, 2.2) * step(0.35 * W, hu) * step(hu, 0.65 * W);
    col = mix(col, vec3(0.3 + h1 * 0.5, 0.25 + h2 * 0.3, 0.2 + h3 * 0.4), art * step(0.4, h3));
    shade = 0.8;
  } else if (t == tU) {    // side walls
    col = wall * 0.8;
    shade = 0.65 + 0.2 * (hw / D);
  } else if (d.z > 0.0) {  // ceiling with a light pool
    col = vec3(0.92, 0.9, 0.86);
    float lamp = exp(-dot(vec2(hu - W * 0.5, hw - D * 0.45), vec2(hu - W * 0.5, hw - D * 0.45)) * 0.9);
    col += lamp * 1.2;
    shade = 0.9;
  } else {                 // floor: warm wood
    col = mix(vec3(0.42, 0.3, 0.2), vec3(0.6, 0.5, 0.38), h2);
    shade = 0.55 + 0.35 * (1.0 - hw / D);
  }
  // depth darkening (light falls off away from the window)
  shade *= mix(1.0, 0.55, clamp(hw / D, 0.0, 1.0));
  // lighting: daylight ambient vs. artificial warm light at night
  float onChance = uShop > 0.5 ? 0.97 : mix(0.15, 0.62, uNight);
  lit = step(h1, onChance);
  vec3 warm = mix(vec3(1.0, 0.78, 0.52), vec3(1.0, 0.9, 0.78), h3);
  vec3 dayLight = vec3(0.55, 0.58, 0.6) * uDay;
  vec3 artificial = warm * lit * (uShop > 0.5 ? 2.4 : 1.6);
  vec3 c = col * shade * (dayLight + artificial * mix(0.35, 1.0, uNight));
  // sheer curtains on some windows
  float curtain = step(0.62, h2) * (uShop > 0.5 ? 0.0 : 1.0);
  c = mix(c, (vec3(0.86, 0.83, 0.78) * (dayLight + artificial * 0.9)) * 0.75, curtain * 0.7);
  return c;
}
`;

function interiorGlass(base: THREE.MeshStandardMaterial, room: [number, number, number], floorBase: number, shop: boolean) {
  const m = new THREE.MeshPhysicalMaterial({
    name: base.name,
    color: new THREE.Color(0.02, 0.025, 0.03),
    metalness: 0.0,
    roughness: 0.035,
    ior: 1.52,
    specularIntensity: 1,
    envMapIntensity: 1.05,
    clearcoat: 0.0,
  });
  const local = {
    uRoom: { value: new THREE.Vector3(...room) },
    uBase: { value: floorBase },
    uShop: { value: shop ? 1 : 0 },
  };
  m.userData.shaderKey = shop ? 'interior-shop' : 'interior-res';
  m.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, INTERIOR, local);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vIwPos;\nvarying vec3 vIwNrm;')
      .replace(
        '#include <project_vertex>',
        `#include <project_vertex>
        vIwPos = (modelMatrix * vec4(transformed, 1.0)).xyz;
        vIwNrm = normalize(mat3(modelMatrix) * objectNormal);`,
      );
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>\n${INTERIOR_DECL}`)
      .replace(
        '#include <emissivemap_fragment>',
        `#include <emissivemap_fragment>
        float iLit;
        vec3 iCol = interiorColour(vIwPos, vIwNrm, cameraPosition, iLit);
        // light transmitted through the glass (1 - Fresnel), reflections come from the env map
        float ndv = clamp(abs(dot(normalize(vViewPosition), normal)), 0.0, 1.0);
        float trans = (1.0 - pow(1.0 - ndv, 5.0)) * 0.92;
        totalEmissiveRadiance += iCol * trans;`,
      );
  };
  return m;
}

const tuned: Record<string, Partial<THREE.MeshPhysicalMaterialParameters & { envMapIntensity: number }>> = {
  M_Cladding: { roughness: 0.42, metalness: 0.25, envMapIntensity: 1.2, color: new THREE.Color('#7a8089').convertSRGBToLinear() },
  M_Frame: { roughness: 0.38, metalness: 0.3, envMapIntensity: 1.2, color: new THREE.Color('#5d636b').convertSRGBToLinear() },
  M_Fin: { roughness: 0.32, metalness: 0.35, envMapIntensity: 1.3, color: new THREE.Color('#959ba3').convertSRGBToLinear() },
  M_Sill: { roughness: 0.45, color: new THREE.Color('#b5b8bb').convertSRGBToLinear() },
  M_BalconySlab: { roughness: 0.6, color: new THREE.Color('#e3e1dc').convertSRGBToLinear() },
  M_Spandrel: { roughness: 0.18, metalness: 0.3, envMapIntensity: 1.3 },
  M_Mullion: { roughness: 0.3, metalness: 0.7 },
  M_RailMetal: { roughness: 0.25, metalness: 0.9 },
  M_PodiumRed: { roughness: 0.45, metalness: 0.15 },
  M_CarPaint: { roughness: 0.22, metalness: 0.5 },
};

export type Role = FxRole;

/** Decide the FX role of a node by its name (layers for explode / build-up / cutaway). */
export function roleForNode(name: string): FxRole {
  if (/_(slabs|columns|core|stairs|lift_\d)$/.test(name) || name === 'Foundation') return 'structure';
  if (/_(facade|glazing)_|^P_(facade|glazing|roof)$|_crown$/.test(name)) return 'facade';
  if (name.startsWith('PK_')) return 'parking';
  return 'site';
}

const cache = new Map<string, THREE.Material>();

/** Upgrade all materials of a loaded GLB scene. */
export function upgradeMaterials(root: THREE.Object3D, kind: 'building' | 'site' | 'parking' | 'props' | 'context') {
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh) return;
    // the layer node is the direct child of the GLB's root empty (Building / Site / Parking)
    let node: THREE.Object3D = mesh;
    while (node.parent && node.parent !== root && !/^(Building|Site|Parking|Scene|AuxScene)$/.test(node.parent.name)) node = node.parent;
    const nodeName = node.name || mesh.name;
    const role: FxRole = kind === 'building' ? roleForNode(nodeName) : kind === 'parking' ? 'parking' : 'site';
    mesh.userData.role = role;
    mesh.userData.node = nodeName;
    mesh.castShadow = kind !== 'context';
    mesh.receiveShadow = true;
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    const out = mats.map((m0) => {
      const m = m0 as THREE.MeshStandardMaterial;
      const key = `${kind}|${role}|${m.name}|${nodeName.startsWith('A_') ? 'A' : nodeName.startsWith('B_') ? 'B' : ''}`;
      if (cache.has(key)) return cache.get(key)!;
      let nm: THREE.Material = m;
      if (m.name === 'M_Glass_Res') {
        nm = interiorGlass(m, [3.6, 6.0, 3.3], 9.6, false);
      } else if (m.name === 'M_Glass_Shop') {
        nm = interiorGlass(m, [8.0, 9.0, 4.6], 0, true);
      } else if (m.name === 'M_RailGlass') {
        nm = new THREE.MeshPhysicalMaterial({
          name: m.name, color: 0xb9ccd2, metalness: 0, roughness: 0.04, transparent: true, opacity: 0.22,
          envMapIntensity: 1.4, depthWrite: false, side: THREE.DoubleSide,
        });
      } else if (m.name === 'M_ParkingLight' || m.name === 'M_ChargerLED') {
        m.toneMapped = true;
      } else {
        const t = tuned[m.name];
        if (t) Object.assign(m, t);
        if (m.map) m.map.anisotropy = 16;
        if (m.normalMap) m.normalMap.anisotropy = 16;
      }
      if (/^M_(HeadLight|TailLight|LampHead|Level|ParkingLight|ChargerLED|SoffitLight|LED)/.test(m.name)) {
        (nm as any).userData.nightEmissive = true;
      }
      applyFx(nm, role, { cut: kind !== 'context' });
      cache.set(key, nm);
      return nm;
    });
    mesh.material = Array.isArray(mesh.material) ? out : out[0];
  });
}
