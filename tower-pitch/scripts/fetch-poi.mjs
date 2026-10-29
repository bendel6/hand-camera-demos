// Enrich src/content/poi.json + routes.json with Google Routes (walk / drive / transit) and Places photos.
// Run once when the server key exists; the live site never calls these APIs (results are cached in the repo).
//
//   GOOGLE_MAPS_SERVER_KEY=... node scripts/fetch-poi.mjs [--no-photos]
//
// Key: Places API (New) + Routes API enabled, restricted by API (not by website). Never commit it.
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const KEY = process.env.GOOGLE_MAPS_SERVER_KEY;
if (!KEY) {
  console.error('GOOGLE_MAPS_SERVER_KEY is not set');
  process.exit(1);
}
const photos = !process.argv.includes('--no-photos');
const site = JSON.parse(fs.readFileSync(path.join(root, 'src/content/site.json'), 'utf8'));
const poiPath = path.join(root, 'src/content/poi.json');
const routesPath = path.join(root, 'src/content/routes.json');
const poi = JSON.parse(fs.readFileSync(poiPath, 'utf8'));
const routes = JSON.parse(fs.readFileSync(routesPath, 'utf8'));
for (const [p, d] of [[poiPath, poi], [routesPath, routes]]) {
  const bak = p.replace('.json', '.overture.json');
  if (!fs.existsSync(bak)) fs.writeFileSync(bak, JSON.stringify(d, null, 1));
}

// entrance on the Kazbegi Ave sidewalk (site frame (40, -2)) -> lat/lng via the local tangent plane
const R = 6378137;
const rot = (site.rotationDeg * Math.PI) / 180;
function siteToLatLng(x, y) {
  const e = x * Math.cos(rot) - y * Math.sin(rot);
  const n = x * Math.sin(rot) + y * Math.cos(rot);
  return {
    latitude: site.originLat + (n / R) * (180 / Math.PI),
    longitude: site.originLng + (e / (R * Math.cos((site.originLat * Math.PI) / 180))) * (180 / Math.PI),
  };
}
function latLngToXZ(lat, lng) {
  const e = ((lng - site.originLng) * Math.PI) / 180 * R * Math.cos((site.originLat * Math.PI) / 180);
  const n = ((lat - site.originLat) * Math.PI) / 180 * R;
  return [Math.round(e * 10) / 10, Math.round(-n * 10) / 10];
}
const ORIGIN = siteToLatLng(40, -2);

function decodePolyline(str) {
  const pts = [];
  let i = 0, lat = 0, lng = 0;
  while (i < str.length) {
    for (const which of [0, 1]) {
      let b, shift = 0, result = 0;
      do {
        b = str.charCodeAt(i++) - 63;
        result |= (b & 0x1f) << shift;
        shift += 5;
      } while (b >= 0x20);
      const d = result & 1 ? ~(result >> 1) : result >> 1;
      if (which === 0) lat += d; else lng += d;
    }
    pts.push([lat / 1e5, lng / 1e5]);
  }
  return pts;
}

async function route(dest, mode) {
  const body = {
    origin: { location: { latLng: ORIGIN } },
    destination: { location: { latLng: { latitude: dest.lat, longitude: dest.lng } } },
    travelMode: mode,
    polylineQuality: 'HIGH_QUALITY',
    languageCode: 'en',
  };
  if (mode === 'DRIVE') body.routingPreference = 'TRAFFIC_UNAWARE';
  const res = await fetch('https://routes.googleapis.com/directions/v2:computeRoutes', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Goog-Api-Key': KEY,
      'X-Goog-FieldMask': 'routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline',
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Routes ${mode} ${res.status}: ${await res.text()}`);
  const r = (await res.json()).routes?.[0];
  if (!r) return null;
  return {
    m: r.distanceMeters ?? null,
    min: r.duration ? Math.max(1, Math.round(parseInt(r.duration, 10) / 60)) : null,
    line: r.polyline?.encodedPolyline ? decodePolyline(r.polyline.encodedPolyline) : null,
  };
}

async function placePhoto(p) {
  const res = await fetch('https://places.googleapis.com/v1/places:searchText', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Goog-Api-Key': KEY,
      'X-Goog-FieldMask': 'places.id,places.displayName,places.rating,places.photos',
    },
    body: JSON.stringify({
      textQuery: p.name_en,
      locationBias: { circle: { center: { latitude: p.lat, longitude: p.lng }, radius: 400 } },
      maxResultCount: 1,
    }),
  });
  if (!res.ok) throw new Error(`Places ${res.status}: ${await res.text()}`);
  const place = (await res.json()).places?.[0];
  const ph = place?.photos?.[0];
  if (!ph) return null;
  const img = await fetch(`https://places.googleapis.com/v1/${ph.name}/media?maxWidthPx=900&key=${KEY}`);
  if (!img.ok) return null;
  const dir = path.join(root, 'public/assets/poi');
  fs.mkdirSync(dir, { recursive: true });
  const file = `${p.id}.jpg`;
  fs.writeFileSync(path.join(dir, file), Buffer.from(await img.arrayBuffer()));
  return {
    photo: `assets/poi/${file}`,
    photo_credit: (ph.authorAttributions ?? []).map((a) => a.displayName).join(', '),
    rating: place.rating ?? null,
    google_place_id: place.id,
  };
}

for (const p of poi.pois) {
  try {
    const far = p.straight_m > 9000;
    const [walk, drive, transit] = await Promise.all([
      far ? null : route(p, 'WALK'),
      route(p, 'DRIVE'),
      route(p, 'TRANSIT').catch(() => null),
    ]);
    if (walk) Object.assign(p, { walk_m: walk.m, walk_min: walk.min });
    if (drive) Object.assign(p, { drive_m: drive.m, drive_min: drive.min, approximate: false });
    if (transit) Object.assign(p, { transit_min: transit.min });
    const best = walk && walk.m < 1500 ? walk : drive;
    if (best?.line) {
      routes.routes[p.id] = { mode: best === walk ? 'walk' : 'drive', points: best.line.map(([la, ln]) => latLngToXZ(la, ln)) };
    }
    if (photos) Object.assign(p, (await placePhoto(p).catch((e) => (console.warn(p.id, e.message), null))) ?? {});
    p.source = 'google-routes';
    console.log(p.id, p.walk_min, p.drive_min, p.transit_min ?? '-');
  } catch (e) {
    console.warn('skip', p.id, e.message);
  }
}
const metro = poi.pois.filter((p) => p.category === 'Transport' && p.walk_m).sort((a, b) => a.walk_m - b.walk_m)[0];
const centre = poi.pois.find((p) => p.id === 'freedom-square');
const airport = poi.pois.find((p) => p.id === 'tbilisi-international-airport');
poi.meta.summary = {
  ...poi.meta.summary,
  city_centre_drive_min: centre?.drive_min ?? poi.meta.summary.city_centre_drive_min,
  airport_drive_min: airport?.drive_min ?? poi.meta.summary.airport_drive_min,
  airport_approximate: false,
  nearest_metro: metro?.name_en ?? poi.meta.summary.nearest_metro,
  nearest_metro_walk_m: metro?.walk_m ?? poi.meta.summary.nearest_metro_walk_m,
  nearest_metro_walk_min: metro?.walk_min ?? poi.meta.summary.nearest_metro_walk_min,
};
poi.meta.note = `Distances and travel times from Google Routes (${new Date().toISOString().slice(0, 10)}).`;
routes.meta.note = 'Route lines from Google Routes';
fs.writeFileSync(poiPath, JSON.stringify(poi, null, 1));
fs.writeFileSync(routesPath, JSON.stringify(routes));
console.log('updated', poiPath, routesPath);
