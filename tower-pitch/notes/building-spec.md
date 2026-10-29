# Building spec: Kazbegi Avenue N23 mixed-use complex

Sources: `input/eskizi-proeqti-10.03.2026.pdf` (sketch project, Archicad, 10 pages: cover render, site plan,
explanatory note, 4 renders, 2 photomontages), cadastral plans `01.10.15.010.015` and `01.10.15.010.016`.
Items marked **ASSUMED** are not stated in the PDFs and were chosen to match the renders. Check them.

## Site
| Item | Value | Source |
|---|---|---|
| Address | Tbilisi, Aleksandre Kazbegi Avenue N23 | cover |
| Plots | 01.10.15.010.015: 1,932 m² (L-shape, west). 01.10.15.010.016: 3,385 m² (east) | cadastral |
| Total plot | 5,317 m², roughly 81 m along the avenue × 64–67 m deep | cadastral UTM 38N grid |
| Site centre | 41.725816, 44.757717 (WGS84) | computed from cadastral corner coordinates |
| Orientation | Avenue frontage runs at azimuth 81.5° (ENE). The plot faces the avenue to the SSE | computed |
| Ground level | ±0.00 = avenue sidewalk; terrain treated as flat inside the plot. **ASSUMED** | |

Site frame used in Blender: origin = SW plot corner (UTM 479813.4 E, 4619325.3 N), +X along the avenue,
+Y into the plot (away from the avenue). Exact transform stored in `data/site-frame.json`.

Plot polygon (site frame, m): (0,0) (79.4,0) (81.3,64.2) (0.5,66.7).

## Programme (explanatory note)
- 2-storey podium (stylobate): shops, cafés and restaurants, service units, residential lobbies, admin.
- Two towers on the podium with apartment-type residential units (studio, 1-bedroom, 2-bedroom), shared recreation.
- Separate entrances and cores for commercial and residential users.
- Monolithic reinforced-concrete frame. Foundation is a raft or piles, depending on the geotechnical survey.
- Underground parking, split into residential and commercial zones, with accessible bays.
- Green terraces on the podium roof, rainwater management, energy-efficient glazing.

## Massing
| Element | Footprint (site frame) | Levels | Heights |
|---|---|---|---|
| Podium | Polygon (5.7,0)(80.9,0)(80.9,31.2)(68.8,31.2)(68.8,14.8)(55.1,14.8)(55.1,46.4)(5.7,46.4), about 2,870 m² | 2 | GF 5.0 m, 1F 4.6 m, roof at **+9.60** (drawing) |
| Tower A (tall, NW) | x 10.8–35.7, y 26.4–56.4 (24.9 × 30.0 m) | 30 residential floors above the podium | roof +108.6, crown top **+115.0** (drawing) |
| Tower B (short, SE) | L-shape: x 36.9–54.7 × y 2.1–22.6, plus x 54.7–71.1 × y 2.1–14.8 | 16 residential floors above the podium | roof +66.0, crown top **+68.0** (note) |

- Residential floor-to-floor **3.3 m (ASSUMED)**. 9.6 + 30 × 3.3 = 108.6, which matches the drawing mark exactly.
- Tower B: 9.6 + 16 × 3.3 = 62.4 top slab, then a 3.6 m parapet/plant zone to +66.0 and the crown peak at +68.0. **ASSUMED split**
- Footprints are scaled from the site plan, which is not dimensioned (≈0.076 m per pixel on the embedded image). **ASSUMED ±1 m**

## Facade (from renders p05–p08)
Each tower facade is split into two zones:
1. **Fin zone**: deep vertical fins (≈0.45 m wide × 1.1 m deep) at ≈3.6 m centres, in light anodised grey with darker
   sides. Between them are tall windows with dark-grey spandrels and light sills on every floor. The fins run past
   the roof and step up following the crown slope (sawtooth crown).
2. **Framed balcony zone**: continuous balcony slabs on every floor (white soffit, ≈1.5 m deep), glass balustrades,
   full-height glazing with dark mullions behind. A thick dark-grey metal frame (≈1.2 m) borders the zone. The top of
   the frame is a sloped crown panel with vertical ribs.

- Tower A: fins on the avenue (S) and back (N) faces, framed balconies on the E and W faces. The crown rises to its
  high point at the SW corner (+115.0) and falls to +108.6, with a concave curve on the balcony faces.
- Tower B: the S and N faces are split into a fin zone (west ≈40%) and a framed balcony zone (east ≈60%). The crown
  rises towards the fin side.
- Colours: cladding warm-neutral grey `#6b7078`, frame darker `#4a4f57`, fins and balcony edges light `#b9bdc2`,
  glass blue-grey, reflective.

### Podium
- Two floors, almost fully glazed: curtain wall with mullions at ≈1.5 m and a transom at the floor line.
- Oxblood/terracotta composite cladding `#7a2f2b`: a top fascia band (≈1.2 m), a mid band between the floors, and
  thick piers framing the main entrance(s) (render p08).
- The main residential lobby is in the centre of the avenue frontage, double-height glass between two red piers.
- Shopfronts with warm interiors. Street trees, planters, benches and lamp posts along the sidewalk.

## Structure (for explode / X-ray)
- Monolithic RC frame (note). **ASSUMED** sizes: columns 0.8 × 0.8 m (towers), 0.6 × 0.6 m (podium/parking) on a
  ≈8.1 × 8.1 m grid. Slabs 0.25 m. Core walls 0.35 m.
- Cores: Tower A has 3 lifts, 2 stairs and a fire lift lobby (≈9 × 12 m). Tower B has 2 lifts and 1 stair (≈7 × 9 m). **ASSUMED**
- Foundation: 1.8 m raft under the whole basement. **ASSUMED** (the note says raft or piles)
- Explode layers: foundation, columns, slabs, cores and lift shafts, stairs, facade panels, glazing, roof/crown.

## Parking (client request: 350 spaces on 3 levels)
- The note says underground parking, so the default is **3 underground levels** under the plot: B1 −3.6, B2 −7.2,
  B3 −10.8 (3.6 m floor-to-floor). **ASSUMED** This replaces the guide's "open deck + 2 underground" option.
- Each level ≈75 × 60 m, 117 / 117 / 116 bays = **350**. Bays 2.5 × 5.0 m, two-way aisles 6.0 m.
- Each level has accessible bays near the cores, EV charging bays, and residential/commercial zones colour-coded per the note.
- Two-way ramp from the access loop on the west side of the plot (the site plan shows a drive loop around Tower A). **ASSUMED**

## Landscape (site plan legend)
1. Project buildings
2. Terrace on the commercial roof: podium roof terrace with café tables, umbrellas, planters
3. Green zone: NE garden, lawns with curved paths and trees
4. Path: light stone paving, organic shapes
5. Children's playground: round rubber surface, play tower
6. Road: Kazbegi Avenue in front (4+ lanes), plus the internal access loop along the W and N sides

## Key numbers (for the numbers bar)
| Number | Value | Status |
|---|---|---|
| Height | 115 m | drawing |
| Floors | 30 + 16 residential, 2 commercial | note |
| Plot | 5,317 m² | cadastral |
| Gross above-ground area | ≈37,400 m² (A 750 m² × 30, B ≈573 m² × 16, podium ≈2,870 m² × 2) | **ESTIMATE** |
| Parking | 350 spaces / 3 levels | client brief |
| Green area | ≈18% of plot (garden + playground + planted terrace) | **ESTIMATE** |

## Reference renders (visual targets)
| File | Camera |
|---|---|
| p05 (`..._p05_img1`) | Street level SW of site, looking NE, eye ≈1.7 m, 24 mm, dusk with wet asphalt |
| p07 (`..._p07_img1`) | Across the avenue, slightly east, looking N at Tower B with Tower A behind, overcast |
| p08 (`..._p08_img1`) | Frontal elevation of the podium from the opposite sidewalk, golden hour |
| p09/p10 photomontages | Drone views ≈150 m up from the avenue, showing the real Tbilisi context and the Mtatsminda ridge |

## Not yet known (need the client)
Project and developer name, logo, brand colour, contact details, construction dates, selling points, POI wishes,
confirmation of the parking levels, and real GFA.
