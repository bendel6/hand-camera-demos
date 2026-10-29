# Investor 3D Presentation – Full Build Guide

## MASTER CHECKLIST – everything to prepare before and during the build

Go through this top to bottom. Tick each item. Keep the answers in a text file so you can paste them when Claude Code asks.

### A. Hardware

- [ ] Windows PC with a decent GPU (NVIDIA RTX recommended for Cycles baking), 16 GB+ RAM, 50 GB free disk
- [ ] Stable internet (Google 3D Tiles and asset downloads are heavy)
- [ ] A phone to test the final link on

### B. Software to download and install

- [ ] Node.js 20 LTS or newer (nodejs.org) – check: `node -v`
- [ ] Git (git-scm.com) – check: `git --version`
- [ ] Python 3.11+ (python.org, tick "Add to PATH") – check: `python --version`
- [ ] Python packages: `pip install pymupdf pillow`
- [ ] Blender 4.2 or newer (blender.org)
- [ ] uv: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
- [ ] Blender MCP add-on: download addon.py from github.com/ahujasid/blender-mcp → Blender → Edit > Preferences > Add-ons > Install from Disk → enable it
- [ ] Claude Code: `npm install -g @anthropic-ai/claude-code` (needs a Claude Pro/Max plan or Anthropic API credits)
- [ ] Connect Blender to Claude Code: `claude mcp add blender -- uvx blender-mcp`, check with `claude mcp list`
- [ ] gltf-transform: `npm install -g @gltf-transform/cli`
- [ ] Vercel CLI: `npm install -g vercel` then `vercel login`
- [ ] Optional: FFmpeg (ffmpeg.org) for converting recorded tours to MP4 for WhatsApp
- [ ] Optional: VS Code to look at files; Google Chrome for testing

### C. Accounts to create

- [ ] Claude account with Claude Code access
- [ ] Google Cloud account with billing enabled (card required; free monthly credit covers this project)
- [ ] Vercel account (free Hobby plan is fine; sign in with GitHub or email)
- [ ] GitHub account (optional but recommended as backup of the code)
- [ ] Poly Haven needs no account (free HDRIs, textures, models)
- [ ] Optional: Sketchfab account for extra free car / people / tree models

### D. Google Cloud APIs to enable (console.cloud.google.com → APIs & Services → Library)

- [ ] Map Tiles API – photorealistic 3D city of Tbilisi
- [ ] Places API (New) – metro stations, malls, landmarks near the site
- [ ] Routes API – walking / driving / transit times and route lines
- [ ] Geocoding API – turns the address into exact coordinates
- [ ] Optional: Maps JavaScript API – only if you want a small 2D minimap
- [ ] Optional: Elevation API – terrain height for the fallback mode
- [ ] Create ONE API key → restrict it to the APIs above → under Website restrictions add `localhost:*` and later your Vercel URL (`*.vercel.app/*`)
- [ ] Set a budget alert (Billing → Budgets) at around $20 so you never get a surprise bill

### E. Information to collect from the client

- [ ] All PDFs (renders, elevations, sections, site plan, any sizes) → put in `input\`
- [ ] Google Maps pin → right-click → copy the latitude and longitude
- [ ] Exact address (Kazbegi Avenue, number)
- [ ] Project name and developer / company name
- [ ] Logo (PNG or SVG with transparent background)
- [ ] Brand colors if they have any (otherwise Claude picks one accent color)
- [ ] Number of floors, total height, total m² (if not in the PDFs)
- [ ] Plot size and green area % (if known)
- [ ] Parking: 350 spaces on 3 levels – confirm if underground, above ground or mixed
- [ ] Facade materials and colors they want (glass, stone, metal, concrete)
- [ ] Construction timeline (start and finish dates) for the build-up animation captions
- [ ] Short project description in English and Georgian (2–3 sentences)
- [ ] Key selling points they want investors to see (e.g. near metro, views, parking)
- [ ] List of nearby places THEY want highlighted (specific metro stations, malls, universities, landmarks)
- [ ] Contact info for the end card (phone, email, website)
- [ ] Optional: drone or site photos of the empty plot today (for the before/after slider)
- [ ] Optional: background music they like (royalty-free)

### F. Files and folders

- [ ] Create `C:\projects\tower-pitch\`
- [ ] Inside it: `input\` (all PDFs, logo, photos)
- [ ] Create `.env` with:
  - `VITE_GOOGLE_KEY=your_key`
  - `VITE_SITE_LAT=41.xxxxx`
  - `VITE_SITE_LNG=44.xxxxx`
  - `VITE_PROJECT_NAME=Project Name`
- [ ] Paste the final block from the bottom of this doc into `CLAUDE.md` in the same folder

### G. Before you start Claude Code each session

- [ ] Open Blender → press N → BlenderMCP tab → enable Poly Haven → click Connect
- [ ] Keep Blender open the whole time Claude Code works
- [ ] Open a terminal in `C:\projects\tower-pitch\`, run `claude`, say: "Read CLAUDE.md and start with Step 1."

### H. Things Claude Code will ask you to do or decide

- [ ] Approve `notes/building-spec.md` after Step 2 (check sizes, floors, materials, ASSUMED items)
- [ ] Pick the reference renders it should match
- [ ] Confirm the parking layout (underground vs beside the building)
- [ ] Approve or edit the list of nearby places in `poi.json`
- [ ] Choose the accent color and look (dark glass UI by default)
- [ ] Give feedback on screenshots after each major step
- [ ] Add the Google key to Vercel: Project → Settings → Environment Variables (never put it in git)
- [ ] After deploy, add the Vercel URL to the Google API key's website restrictions
- [ ] Test the link on laptop and phone, report anything broken

### I. Worth exploring (optional, makes it better)

- [ ] Poly Haven HDRIs – pick a sky you like (clear day, golden hour)
- [ ] Sketchfab / Poly Haven – nicer cars, trees, people
- [ ] Look at 2–3 real estate 3D sites for inspiration and send links to Claude Code
- [ ] Decide if you want a custom domain (e.g. projectname.ge) – can be added in Vercel later

### J. Costs to expect

- [ ] Claude plan or API credits
- [ ] Google Cloud: usually inside the free monthly credit for a pitch site with cached POI data
- [ ] Vercel: free
- [ ] Everything else: free

## Full CLAUDE.md for Claude Code

**This is the final version. It replaces the earlier prompts above.** Copy everything in the block below into a file named `CLAUDE.md` in `C:\projects\tower-pitch\`, run `claude`, and say: "Read CLAUDE.md and start with Step 1."

```markdown
# CLAUDE.md — Investor 3D Presentation (Tbilisi Tower)

> TOP PRIORITY: IT MUST LOOK BEAUTIFUL.
> This is an investor pitch. Visual quality beats technical accuracy. Use the best possible shading, lighting,
> materials, reflections and atmosphere, plus lots of life and detail, so an investor feels "this looks real".
> It is a FREE-ROAM INTERACTIVE experience: mouse to orbit, zoom and pan, click things to trigger effects.
> NOT scroll-driven. No per-floor or apartment features (no floor plans exist yet).
> Focus: the building exterior, its construction/structure details, the 3-level parking, the surroundings.
> After every major step, take a screenshot, critique it like a professional archviz artist, and improve it.
> Use any tool available: Blender MCP, Poly Haven, Python, npm packages. Install whatever you need.
> This is a full build, not a quick draft. Take the time to do it properly.

## 0. Context
- Interactive 3D web presentation of a proposed building in Tbilisi, Georgia. Concept visual, NOT engineering
  (no government K1/K2/K3 coefficients yet).
- Inputs: PDFs only, in /input (renders, drawings, site plan with parking and greenery, sizes). No FBX or CAD.
  Where the PDFs are unclear, invent plausible details and mark them ASSUMED in the spec.
- .env: VITE_GOOGLE_KEY, VITE_SITE_LAT, VITE_SITE_LNG.
- Pipeline: Blender (model, materials, baked lighting, baked animations) -> GLB -> three.js website -> Vercel link.
- Work step by step. Commit after each step. Ask me only when blocked. Stop for my OK after Step 2.

## 1. Environment (verify, install anything missing)
- Node.js 20+, Git, Python 3.11+, pip install pymupdf pillow
- Vercel CLI (npm i -g vercel), gltf-transform (npm i -g @gltf-transform/cli)
- Blender 4.2+ with the Blender MCP add-on connected (claude mcp add blender -- uvx blender-mcp).
  Poly Haven enabled; Hyper3D/Hunyuan3D for props only, never for the main building.
- Check with claude mcp list and confirm you can control Blender before starting.

## 2. Extract and study the PDFs
- PyMuPDF script: export every page as PNG at 200 dpi and every embedded image to /public/assets/pdf.
- Look at every image. Write /notes/building-spec.md: footprint shape and size, floor count, floor height
  (3.2 m if unknown), total height, facade materials and colors, balconies, roof, entrances, structure
  (columns, cores, slabs), parking, green areas, paths, plot size.
- Pick 3-4 reference renders as the visual target and note each camera angle.
- Show me the spec and wait for my OK.

## 3. Rebuild the model in Blender (via Blender MCP)
- Real-world scale in meters. Massing first, then detail: floor slabs, curtain wall with mullions, window frames,
  balconies with glass railings, facade panels, rooftop plant, entrance canopy, lobby glazing.
- Model the structure too, as separate collections: foundation, columns, slabs, cores, elevator shafts,
  stairs, facade panels, glazing, roof. Needed for the explode and X-ray effects.
- Windows: glass with reflections and some softly lit, blurred interiors (fake interior mapping), no real floor plans.
- Small bevels on hard edges so they catch light.
- Site: plot ground, roads, curbs, sidewalks, lawns, planters, benches, lamp posts, trees and shrubs per the plan.
- Materials: PBR from Poly Haven (concrete, stone, asphalt, grass, metal).
- Render viewport screenshots from the reference angles, compare with the PDF renders, fix proportions until it
  reads as the same building.

## 4. Parking: 350 spaces, 3 levels (client request)
- 350 spaces over 3 levels, about 117 per level. Default: ground-level open-air deck plus two underground levels.
  If the site plan fits better, a 3-level structure beside the building. Mark the choice ASSUMED.
- Ramps, columns, painted bays, lane arrows, ceiling lights, EV charging spots, signage, parked cars on ~60% of bays.
- Each level is a separate object for the cutaway animation.

## 5. Bake animations in Blender
- Animate in Blender, export as named GLB clips (played with three.js AnimationMixer, triggered by clicks):
  Explode, Assemble, BuildUp, ParkingReveal, ParkingHide.

## 6. Bake lighting and export
- Cycles bake AO and soft shadows into lightmaps for static objects. Glass and metal stay unbaked for live reflections.
- Export GLB with named nodes and animations. Compress with gltf-transform (meshopt + KTX2/webp).
  Split into building.glb, parking.glb, site.glb. Target under 40 MB at first load.
- Render 3 hero stills in Cycles (day, golden hour, night) for the gallery.

## 7. Web scaffold
- Vite + TypeScript, three.js, 3d-tiles-renderer (NASA-AMMOS), postprocessing (pmndrs), gsap, suncalc.
  Captions and labels in /src/content/en.json and ka.json.

## 8. Surroundings
- Google Photorealistic 3D Tiles centered on the site coordinates. Place the GLB on the ground; hide or flatten
  existing tiles inside the plot.
- FALLBACK: terrain plus grey OpenStreetMap massing of nearby blocks, with the PDF site plan as ground texture.

## 9. Lighting and look (spend real time here)
- Poly Haven HDRI for sky and reflections, sun with soft shadows (cascaded or high-res map), AgX or ACES tone mapping.
- Post-processing: N8AO/SSAO, subtle bloom on windows and lamps, light vignette, gentle depth fog, SMAA.
- Presets: Day, Golden Hour, Night (lit windows, street lights, headlights).
- Sun slider: sunrise to night with the real Tbilisi sun position (suncalc), shadows moving live.

## 10. Life and movement
- Cars driving nearby roads on spline paths, headlights at night, some entering and leaving the parking.
- People walking on sidewalks and near the entrance (instanced rigged low-poly or billboards).
- Trees swaying, a few birds, a moving flag or banner.

## 11. Wow effects (all click-triggered)
1. Explode / Assemble button: the building separates into its construction layers (foundation, structure,
   slabs, cores, facade panels, glazing, roof) with staggered gsap easing and a glow outline. Each layer gets a
   label with a short description. Click a layer to see its card. Press again and it snaps back together.
2. X-ray mode: facade turns transparent, structure (columns, slabs, cores, elevators) shows as a glowing skeleton.
3. Parking cutaway: ground slices away, the 3 levels light up one by one, counter animates to 350. Click a
   level to fly the camera into it and orbit inside.
4. Build-up animation: building rises foundation to roof in ~10 s, like a construction timelapse.
5. Before / after slider: today's empty site vs the finished project.
6. Key numbers bar: height, floors, total m2, 350 parking, green area %, animated counters.

## 12. Interaction and UI
- Free orbit, zoom, pan with mouse and touch, with limits (never below ground, except in cutaway mode).
  Double-click anywhere on the model to fly the camera there.
- Glowing hotspots: Main Entrance, Parking, Green Zone, Rooftop, Facade Detail. Click -> camera flight +
  side card with short text and the matching render.
- Bottom bar: Overview, Location, Structure (Explode / X-ray), Parking, Build-up, Greenery, Gallery, Lighting.
- Location mode (MAJOR FEATURE, see 8b): camera lifts off the building and glides over Tbilisi.

## 8b. Location & accessibility (investors must FEEL where it is)
- Site is on Kazbegi Avenue, Tbilisi (exact coords from .env).
- Enable Google Places API (New) + Routes API on the same key. Fetch nearby POIs: metro stations, malls,
  universities, hospitals, parks, landmarks, business centers, Freedom Square, Old Town, airport.
  Cache to /src/content/poi.json so the live site does not hit the APIs on every load. Let me edit the list.
- Each POI: glowing 3D pin above the 3D Tiles with name + distance (m/km) + travel time (walk / car / metro).
- Click a POI: camera flies from the building to it, a glowing route line draws along the real streets,
  card shows distance, minutes by foot/car, and a photo.
- Accessibility rings: pulsing circles at 500 m, 1 km, 3 km, 5 km labeled "5 min walk", "10 min drive" etc.
- Metro: highlight nearest stations and the line, animated dots moving along it.
- Category filters: Transport, Shopping, Education, Health, Leisure, Business; pins fade in/out with gsap.
- Auto-tour button: camera hops through the top 6 POIs and back to the building (~40 s), works in Present mode.
- Summary card: "X min to city center, Y min to airport, nearest metro Z m".
- All dynamic and fluid: eased camera flights, no hard cuts, labels face the camera and never overlap.
- Gallery: fullscreen lightbox of PDF renders and Cycles stills.
- Short skippable fly-in on load, then the user is in full control.
- Minimal premium UI: dark glass panels, white text, one accent color, smooth transitions everywhere.
  Loading screen with logo (placeholder "PROJECT NAME"). EN / KA toggle. Soft music toggle (off by default).
- Present mode: fullscreen, UI hidden, arrow keys jump between hotspots, for a TV in a meeting.
- Record tour: exports a 30 s MP4/WebM flythrough for WhatsApp.

## 13. Performance
- 60 fps on a normal laptop. Auto lower preset on phones (fewer shadows, no AO, fewer people and cars).
- Instancing for trees, cars, people. Lazy-load parking interior and gallery.

## 14. Deploy
- npm run build, then vercel --prod. Google key in Vercel env vars, never in git. Give me the URL.
- Test desktop and phone, send me screenshots of every mode.

## 15. Later (when floor plans exist)
- Click a floor to zoom inside, apartment/unit plans, views from units, real architect model, final branding.
```
