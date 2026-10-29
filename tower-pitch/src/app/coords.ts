import * as THREE from 'three';
import site from '../content/site.json';

/** Rotation (radians) of the site frame relative to ENU east, about the up axis. */
export const SITE_ROT = THREE.MathUtils.degToRad(site.rotationDeg);
const C = Math.cos(SITE_ROT);
const S = Math.sin(SITE_ROT);

/** Site frame (x along Kazbegi Ave, y into the plot, h up) -> three.js world (x east, y up, z = -north). */
export function siteToWorld(x: number, y: number, h = 0, out = new THREE.Vector3()): THREE.Vector3 {
  const e = x * C - y * S;
  const n = x * S + y * C;
  return out.set(e, h, -n);
}

export function worldToSite(v: THREE.Vector3): { x: number; y: number; h: number } {
  const e = v.x;
  const n = -v.z;
  return { x: e * C + n * S, y: -e * S + n * C, h: v.y };
}

/** Site centre in world coordinates (middle of the plot at ground level). */
export const SITE_CENTRE = siteToWorld(40.5, 32.5, 0);
export const TOWER_A_TOP = siteToWorld(23.3, 41.4, 115);

const R = 6378137;
/** Lat/lng -> local tangent-plane metres around the plot origin (good to ~0.1% within 10 km). */
export function latLngToWorld(lat: number, lng: number, h = 0, out = new THREE.Vector3()): THREE.Vector3 {
  const dLat = THREE.MathUtils.degToRad(lat - site.originLat);
  const dLng = THREE.MathUtils.degToRad(lng - site.originLng);
  const e = dLng * R * Math.cos(THREE.MathUtils.degToRad(site.originLat));
  const n = dLat * R;
  return out.set(e, h, -n);
}

export { site };
