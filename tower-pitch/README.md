# Kazbegi 23: interactive 3D investor presentation

A desktop web experience for the proposed two-tower mixed-use complex at Aleksandre Kazbegi Avenue 23, Tbilisi.
You can orbit, explode the building into its construction layers, X-ray the structure, open the 350-space
underground parking, watch a build-up timelapse, compare today's site with the project, and fly over Tbilisi to
real metro stations, malls, universities and landmarks. Concept visual only, not engineering.

## Run it

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # static site in dist/
```

Add `?auto` to the URL to skip the Enter click (kiosk / TV). Present mode (top right) hides the UI; arrow keys
step through the hotspots.

## Deploy (Vercel)

1. Vercel → **Add New → Project** → import `bendel6/hand-camera-demos`.
2. Set **Root Directory** to `tower-pitch`. Vercel detects Vite: build `npm run build`, output `dist`.
3. Optional: add `VITE_GOOGLE_KEY` (see below) under Settings → Environment Variables, then redeploy.

## Google Photorealistic 3D Tiles (optional, recommended)

Without a key, the city is the open-data model: Overture Maps buildings on AWS terrain, plus real trees, roads and
POIs. With a key, the location mode uses Google's photoreal 3D city and the plot is flattened under the project.

- **Browser key** (`VITE_GOOGLE_KEY`): Map Tiles API only. Restrict it to your site's domain and `localhost:*`.
  It ships in the page, which is normal for Maps keys; the website restriction is what protects it.
- **Server key** (`GOOGLE_MAPS_SERVER_KEY`): Places API (New) + Routes API. Run once to replace the estimated
  travel times with Google Routes (walk, drive and transit) and to download one photo per place:
  `GOOGLE_MAPS_SERVER_KEY=... node scripts/fetch-poi.mjs`. Never commit either key.

## Pipeline

| Step | Script | Output |
|---|---|---|
| PDF extraction | `scripts/extract_pdfs.py` | `public/assets/pdf/raw/` (git-ignored) |
| Open map data | `scripts/fetch_overture.py`, `scripts/fetch_terrain.py` | `data/*.parquet`, `data/terrain_z14.npz` |
| City context | `scripts/build_context.py`, `build_ground.py`, `build_heights.py` | `public/models/context.glb`, ground map, height grid |
| POIs + routes | `scripts/build_poi.py` (open data), `scripts/fetch-poi.mjs` (Google) | `src/content/poi.json`, `routes.json` |
| Building | `blender/build_building.py` | towers, podium, structure layers, foundation |
| Parking | `blender/build_parking.py` | 3 levels, 117 / 117 / 116 bays + layout JSON |
| Site | `blender/build_site.py` | avenue, sidewalks, garden, playground, furniture + layout JSON |
| Props | `blender/build_props.py` | car, person, lamp and tree prototypes |
| Compression | `npm run optimize` | meshopt + WebP GLBs in `public/models/` |
| Hero stills | `blender/stills.py <preset>`, `blender/render_finals.sh` | 4K Cycles renders in `public/assets/stills/` |
| Artifact preview | `scripts/build-artifact.sh` | single-file build for the claude.ai preview |

Blender runs headless through `pip install bpy` (Blender 5.2). See `CLAUDE.md` for the environment setup and
`notes/building-spec.md` for every dimension and assumption.

## Credits

Map data © OpenStreetMap contributors, Overture Maps Foundation (ODbL). Terrain: AWS Terrain Tiles (Mapzen).
Trees: EZ-Tree by Daniel Greenheck (MIT). Architecture: client sketch project, 10.03.2026.
