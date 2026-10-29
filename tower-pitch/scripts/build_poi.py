"""Curated POIs (Overture places) with network distances over the Overture road graph.

Outputs
  src/content/poi.json     curated POIs with straight / walk / drive distances and estimated times
  src/content/routes.json  route polylines per POI (three.js [x, z]) + metro lines and stations
  data/site-ground.json    site elevation, Kazbegi Avenue centrelines, nearby road centrelines

Run: /opt/venvs/blender/bin/python scripts/build_poi.py"""
import json, math, re
import numpy as np
import networkx as nx
import pyarrow.parquet as pq
import shapely
from shapely.geometry import LineString, Point
from shapely.ops import linemerge
from scipy.spatial import cKDTree

import geo

SOURCE = "overture-2026-10-21"
SC = np.array(geo.SITE_CENTRE_LOC)
ENT = np.array(geo.ENTRANCE_LOC)


def to_loc(xy):
    e, n = geo._ll2loc.transform(xy[:, 0], xy[:, 1])
    return np.column_stack([e, n])


def three(e, n):
    return [round(float(e), 1), round(float(-n), 1)]


# ------------------------------------------------------------------ road graph
seg = pq.read_table(geo.DATA / "overture_segment.parquet",
                    columns=["id", "names", "subtype", "class", "geometry", "connectors", "access_restrictions"]).to_pylist()

DRIVE_SPEED = {"motorway": 60, "trunk": 45, "primary": 35, "secondary": 30, "tertiary": 25, "unclassified": 20,
               "residential": 20, "living_street": 10, "service": 12, "track": 10, "unknown": 15}
NO_WALK = {"motorway"}


def oneway(ar):
    """Return 'forward' / 'backward' if motor traffic is allowed only in that direction, else None."""
    if not ar:
        return None
    for r in ar:
        w = r.get("when") or {}
        if r.get("access_type") != "denied" or r.get("between"):
            continue
        modes = w.get("mode")
        if modes and not set(modes) & {"motor_vehicle", "car", "vehicle"}:
            continue
        if w.get("vehicle") or w.get("using") or w.get("recognized") or w.get("during"):
            continue
        if w.get("heading") == "backward":
            return "forward"
        if w.get("heading") == "forward":
            return "backward"
    return None


W = nx.Graph()
D = nx.DiGraph()
coords = {}
segs_loc = []
for s in seg:
    if s["subtype"] != "road":
        continue
    g = shapely.from_wkb(s["geometry"])
    if g.geom_type != "LineString":
        continue
    xy = to_loc(np.asarray(g.coords))
    cum = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    L = cum[-1]
    if L <= 0:
        continue
    pts = [(cum[k] / L, xy[k], f"{s['id']}:{k}") for k in range(len(xy))]
    for c in s["connectors"] or []:
        at = c["at"]
        j = int(np.argmin([abs(p[0] - at) for p in pts]))
        if abs(pts[j][0] - at) * L < 0.75:
            pts[j] = (pts[j][0], pts[j][1], c["connector_id"])
        else:
            pos = np.array([np.interp(at, cum / L, xy[:, 0]), np.interp(at, cum / L, xy[:, 1])])
            pts.append((at, pos, c["connector_id"]))
    pts.sort(key=lambda p: p[0])
    cl = s["class"] or "unknown"
    ow = oneway(s["access_restrictions"])
    drive = cl in DRIVE_SPEED
    walk = cl not in NO_WALK
    segs_loc.append((s, xy))
    for (fa, pa, na), (fb, pb, nb) in zip(pts[:-1], pts[1:]):
        if na == nb:
            continue
        ln = float(np.hypot(*(pb - pa)))
        coords[na] = pa; coords[nb] = pb
        if walk:
            W.add_edge(na, nb, length=ln)
        if drive:
            t = ln / (DRIVE_SPEED[cl] / 3.6)
            if ow != "backward":
                D.add_edge(na, nb, length=ln, time=t)
            if ow != "forward":
                D.add_edge(nb, na, length=ln, time=t)

print("walk graph", W.number_of_nodes(), W.number_of_edges(), "drive graph", D.number_of_nodes(), D.number_of_edges())
wcc = max(nx.connected_components(W), key=len)
scc = max(nx.strongly_connected_components(D), key=len)
print("walk LCC", len(wcc), "drive SCC", len(scc))
wnodes = list(wcc); wtree = cKDTree(np.array([coords[n] for n in wnodes]))
dnodes = list(scc); dtree = cKDTree(np.array([coords[n] for n in dnodes]))


def snap(tree, nodes, p):
    d, i = tree.query(p)
    return nodes[i], float(d)


w0, w0d = snap(wtree, wnodes, ENT)
d0, d0d = snap(dtree, dnodes, ENT)
print(f"origin snap walk {w0d:.1f} m, drive {d0d:.1f} m")
wpred, wdist = nx.dijkstra_predecessor_and_distance(W, w0, weight="length")
dpred, dtime = nx.dijkstra_predecessor_and_distance(D, d0, weight="time")


def path(pred, target):
    out = [target]
    while pred.get(out[-1]):
        out.append(pred[out[-1]][0])
    return out[::-1]


def path_len(G, p, key="length"):
    return sum(G[a][b][key] for a, b in zip(p[:-1], p[1:]))


# ------------------------------------------------------------------ places
pl = pq.read_table(geo.DATA / "overture_place.parquet",
                   columns=["id", "names", "basic_category", "confidence", "geometry"]).to_pylist()
by_name = {}
for r in pl:
    n = (r["names"] or {}).get("primary")
    if n:
        by_name.setdefault(n, []).append(r)

# (overture primary name, display name EN, name KA, category)
CURATED = [
    ("Metro Medical University", "Medical University metro", "მეტრო სამედიცინო უნივერსიტეტი", "Transport"),
    ("Metro Delisi", "Delisi metro", "მეტრო დელისი", "Transport"),
    ("Vazha-Pshavela (Tbilisi Metro)", "Vazha-Pshavela metro", "მეტრო ვაჟა-ფშაველა", "Transport"),
    ("Technical University Metro", "Technical University metro", "მეტრო ტექნიკური უნივერსიტეტი", "Transport"),
    ("Metro Station Square (1 & 2)", "Station Square metro & Central Station", "მეტრო სადგურის მოედანი", "Transport"),
    ("Metro Rustaveli", "Rustaveli metro", "მეტრო რუსთაველი", "Transport"),
    ("Metro Station University", "State University metro", "მეტრო სახელმწიფო უნივერსიტეტი", "Transport"),
    ("City Mall Saburtalo", "City Mall Saburtalo", "სითი მოლი საბურთალო", "Shopping"),
    ("Galleria Tbilisi", "Galleria Tbilisi", "გალერია თბილისი", "Shopping"),
    ("თბილისის სახელმწიფო სამედიცინო უნივერსიტეტი • Tbilisi State Medical University",
     "Tbilisi State Medical University", "თბილისის სახელმწიფო სამედიცინო უნივერსიტეტი", "Education"),
    ("TSU Library", "Tbilisi State University (main campus)", "თბილისის სახელმწიფო უნივერსიტეტი", "Education"),
    ("საქართველოს ტექნიკური უნივერსიტეტის III კორპუსი", "Georgian Technical University", "საქართველოს ტექნიკური უნივერსიტეტი", "Education"),
    ("Ilia State University", "Ilia State University", "ილიას სახელმწიფო უნივერსიტეტი", "Education"),
    ("Tbilisi State Medical University, Central Clinic", "TSMU Central Clinic", "სამედიცინო უნივერსიტეტის ცენტრალური კლინიკა", "Health"),
    ("სიმონ ხეჩინაშვილის სახელობის საუნივერსიტეტო კლინიკა", "Khechinashvili University Clinic", "ხეჩინაშვილის საუნივერსიტეტო კლინიკა", "Health"),
    ("American Hospital Tbilisi", "American Hospital Tbilisi", "ამერიკული ჰოსპიტალი თბილისი", "Health"),
    ("ვაკის პარკი", "Vake Park", "ვაკის პარკი", "Leisure"),
    ("Mziuri garden", "Mziuri Park", "მზიურის პარკი", "Leisure"),
    ("კუს ტბა • Turtle Lake", "Turtle Lake", "კუს ტბა", "Leisure"),
    ("Tbilisi TV Tower   თბილისის ტელეანძა", "Mtatsminda & TV Tower", "მთაწმინდა · ტელეანძა", "Leisure"),
    ("Boris Paichadze Dinamo Arena", "Dinamo Arena", "დინამო არენა", "Leisure"),
    ("Rike Park", "Rike Park", "რიყის პარკი", "Leisure"),
    ("Freedom Square", "Freedom Square", "თავისუფლების მოედანი", "Landmark"),
    ("Rustaveli National Theatre", "Rustaveli Avenue", "რუსთაველის გამზირი", "Landmark"),
    ("Bridge of Peace", "Bridge of Peace", "მშვიდობის ხიდი", "Landmark"),
    ("Holy Trinity Cathedral of Tbilisi", "Holy Trinity Cathedral", "სამების საკათედრო ტაძარი", "Landmark"),
    ("Abanotubani", "Old Town · Abanotubani", "ძველი თბილისი · აბანოთუბანი", "Landmark"),
    ("Heroes' Square | გმირთა მოედანი", "Heroes' Square", "გმირთა მოედანი", "Landmark"),
    ("Axis Towers Business Center", "Axis Towers", "აქსის თაუერსი", "Business"),
    ("Expo Georgia | ექსპო ჯორჯია", "Expo Georgia", "ექსპო ჯორჯია", "Business"),
]

pois = []
used = set()
for name, en, ka, cat in CURATED:
    cands = by_name.get(name)
    if not cands:
        raise SystemExit(f"missing place: {name}")
    r = max(cands, key=lambda c: c["confidence"])
    g = shapely.from_wkb(r["geometry"])
    e, n = geo.ll2loc(g.x, g.y)
    p = np.array([e, n])
    straight = float(np.hypot(*(p - SC)))
    wn, wsnap = snap(wtree, wnodes, p)
    dn, dsnap = snap(dtree, dnodes, p)
    wm = wdist[wn] + wsnap + w0d
    dpath = path(dpred, dn)
    dm = path_len(D, dpath) + dsnap + d0d
    dt = dtime[dn] + (dsnap + d0d) / (12 / 3.6)
    pid = re.sub(r"[^a-z0-9]+", "-", en.lower()).strip("-")
    pois.append({"id": pid, "name_en": en, "name_ka": ka, "category": cat,
                 "lat": round(g.y, 6), "lng": round(g.x, 6), "x": round(e, 1), "z": round(-n, 1),
                 "straight_m": round(straight), "walk_m": round(wm), "drive_m": round(dm),
                 "walk_min": round(wm / (4.8 / 3.6) / 60), "drive_min": round(dt / 60 + 1.5),
                 "confidence": round(r["confidence"], 2), "overture_id": r["id"], "source": SOURCE,
                 "_wpath": path(wpred, wn), "_dpath": dpath})

# Airport: outside the data bbox. Straight line is exact; road distance is approximate (x1.3 detour, 45 km/h).
ae, an = geo.ll2loc(44.9547, 41.6692)
straight = float(np.hypot(ae - SC[0], an - SC[1]))
pois.append({"id": "tbilisi-international-airport", "name_en": "Tbilisi International Airport",
             "name_ka": "თბილისის საერთაშორისო აეროპორტი", "category": "Transport",
             "lat": 41.6692, "lng": 44.9547, "x": round(ae, 1), "z": round(-an, 1),
             "straight_m": round(straight), "walk_m": None, "drive_m": round(straight * 1.3),
             "walk_min": None, "drive_min": round(straight * 1.3 / (45 / 3.6) / 60 + 1.5),
             "approximate": True, "source": "manual coordinates; road distance approximated as 1.3 x straight line"})

pois.sort(key=lambda p: p["straight_m"])

# ------------------------------------------------------------------ routes
def simplify_path(nodes):
    pts = [coords[n] for n in nodes]
    if len(pts) < 2:
        return []
    ls = LineString([geo.ENTRANCE_LOC] + pts).simplify(5.0)
    return [three(x, y) for x, y in ls.coords]


routes = {}
for p in pois:
    wp, dp = p.pop("_wpath", None), p.pop("_dpath", None)
    if p.get("approximate"):
        routes[p["id"]] = {"mode": "straight", "points": [three(*ENT), [p["x"], p["z"]]],
                           "note": "outside the road data; draw as an arc"}
        continue
    mode = "walk" if p["walk_m"] < 1500 else "drive"
    pts = simplify_path(wp if mode == "walk" else dp)
    pts.append([p["x"], p["z"]])
    routes[p["id"]] = {"mode": mode, "points": pts}

# metro lines from Overture subway rail segments
rails = []
for s in seg:
    if s["subtype"] == "rail" and s["class"] == "subway":
        g = shapely.from_wkb(s["geometry"])
        rails.append((LineString(to_loc(np.asarray(g.coords))), (s["names"] or {}).get("primary")))
merged = linemerge([r[0] for r in rails])
lines = list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]
STATIONS_SABURTALO = ["Metro Station University", "Vazha-Pshavela (Tbilisi Metro)", "Metro Delisi",
                      "Metro Medical University", "Technical University Metro", "Metro Station Square (1 & 2)"]
st_pts = {}
for nme in STATIONS_SABURTALO + ["Metro Rustaveli"]:
    r = max(by_name[nme], key=lambda c: c["confidence"])
    g = shapely.from_wkb(r["geometry"])
    st_pts[nme] = Point(geo.ll2loc(g.x, g.y))
metro = []
lines = [ln for ln in lines if ln.length >= 500]
for ln in lines:
    if ln.length < 150:
        continue
    near_sab = sum(ln.distance(st_pts[s]) < 250 for s in STATIONS_SABURTALO[:4])
    near_main = ln.distance(st_pts["Metro Rustaveli"]) < 250
    name = "Saburtalo line" if near_sab >= 2 else ("Akhmeteli–Varketili line" if near_main else "Tbilisi Metro")
    metro.append({"name": name, "points": [three(x, y) for x, y in ln.simplify(4.0).coords],
                  "length_m": round(ln.length)})
station_list = []
for nme in STATIONS_SABURTALO:
    pt = st_pts[nme]
    station_list.append({"name": nme, "x": round(pt.x, 1), "z": round(-pt.y, 1),
                         "line": "Saburtalo line"})
best = {}
for m in metro:
    if m["name"] not in best or m["length_m"] > best[m["name"]]["length_m"]:
        best[m["name"]] = m
metro = [m for m in best.values() if m["name"] != "Tbilisi Metro"]
for m in metro:
    m["note"] = "one track of the line (Overture subway rails, underground); draw at ground level"
sab = [m for m in metro if m["name"] == "Saburtalo line"]
if not sab:
    metro.append({"name": "Saburtalo line", "schematic": True,
                  "points": [[s["x"], s["z"]] for s in station_list]})

routes_doc = {"meta": {"coords": "three.js [x, z]; x = east m, z = -north m, origin = SW plot corner",
                       "origin_point": three(*ENT), "source": SOURCE,
                       "note": "routes follow the Overture road graph; walking if under 1.5 km, otherwise driving"},
              "routes": routes, "metro": {"lines": metro, "stations": station_list}}

nearest_metro = min((p for p in pois if p["category"] == "Transport" and "metro" in p["name_en"].lower()),
                    key=lambda p: p["walk_m"])
fs = next(p for p in pois if p["id"] == "freedom-square")
ap = next(p for p in pois if p["id"] == "tbilisi-international-airport")
poi_doc = {"meta": {"note": "network distances from Overture Maps road graph; travel times estimated, "
                            "will be replaced by Google Routes when the API key is added",
                    "origin": {"label": "Kazbegi Ave 23 entrance", "x": three(*ENT)[0], "z": three(*ENT)[1]},
                    "walk_speed_kmh": 4.8, "drive_speeds_kmh": DRIVE_SPEED, "drive_overhead_min": 1.5,
                    "summary": {"city_centre_drive_min": fs["drive_min"], "city_centre_drive_m": fs["drive_m"],
                                "airport_drive_min": ap["drive_min"], "airport_approximate": True,
                                "nearest_metro": nearest_metro["name_en"], "nearest_metro_walk_m": nearest_metro["walk_m"],
                                "nearest_metro_walk_min": nearest_metro["walk_min"]},
                    "name_ka_note": "Georgian names partly taken from Overture, partly added by hand; please proofread",
                    "source": SOURCE},
           "pois": pois}
cdir = geo.ROOT / "src" / "content"
cdir.mkdir(parents=True, exist_ok=True)
(cdir / "poi.json").write_text(json.dumps(poi_doc, ensure_ascii=False, indent=1))
(cdir / "routes.json").write_text(json.dumps(routes_doc, ensure_ascii=False, separators=(",", ":")))

# ------------------------------------------------------------------ site ground / street info
dem = geo.DEM()
h0 = float(dem.sample_loc(*SC)[0])
sc_pt = Point(SC)
kaz, others, service = [], {}, []
for s, xy in segs_loc:
    ls = LineString(xy)
    d = ls.distance(sc_pt)
    nm = (s["names"] or {}).get("primary") or ""
    if d < 400 and ("ყაზბეგ" in nm or "kazbeg" in nm.lower()):
        clip = ls.intersection(sc_pt.buffer(400))
        for part in (clip.geoms if clip.geom_type.startswith("Multi") else [clip]):
            if part.length > 1:
                kaz.append({"id": s["id"], "class": s["class"], "oneway": oneway(s["access_restrictions"]),
                            "points": [three(x, y) for x, y in part.simplify(0.5).coords],
                            "distance_to_site_centre_m": round(d, 1)})
    elif d < 250 and s["class"] not in ("footway", "steps", "path", "cycleway", "service", "track", None):
        key = nm or s["id"]
        if key not in others or others[key]["d"] > d:
            others[key] = {"name": nm, "class": s["class"], "d": d, "geoms": []}
        others[key]["geoms"].append(ls)
    elif d < 100 and s["class"] == "service":
        service.append({"points": [three(x, y) for x, y in ls.simplify(0.5).coords], "distance_m": round(d, 1)})

# estimated Kazbegi width from carriageway separation near the site
widths = []
if len(kaz) >= 2:
    a_ = [LineString([(p[0], -p[1]) for p in k["points"]]) for k in kaz]
    for i in range(len(a_)):
        for j in range(i + 1, len(a_)):
            if kaz[i]["oneway"] and kaz[j]["oneway"]:
                sep = a_[i].distance(a_[j])
                if 3 < sep < 60:
                    widths.append(sep)
sep = float(np.median(widths)) if widths else 0.0
front = Point(geo.site2loc(40.0, 0.0))
kaz_lines = [LineString([(q[0], -q[1]) for q in k["points"]]) for k in kaz]
front_to_cl = min(l.distance(front) for l in kaz_lines) if kaz_lines else None
near3 = sorted(others.values(), key=lambda o: o["d"])[:3]
site_ground = {
    "site_elevation_m_asl": round(h0, 2),
    "coords": "three.js [x, z]; x = east m, z = -north m; y = 0 at site ground",
    "plot_three": [three(e, n) for e, n in geo.PLOT_LOC],
    "entrance_three": three(*ENT),
    "kazbegi_avenue": {"name": "ალექსანდრე ყაზბეგის გამზირი (Aleksandre Kazbegi Avenue)", "class": "primary",
                       "carriageways": kaz,
                       "carriageway_separation_m": round(sep, 1) if sep else None,
                       "plot_frontage_to_centreline_m": round(front_to_cl, 1) if front_to_cl else None,
                       "estimated_total_width_m": round(sep + 11, 1) if sep else 17.0,
                       "width_note": ("dual carriageway; width = centreline separation + one 3-lane carriageway (~11 m); estimate"
                                      if sep else "Overture maps it here as ONE one-way (eastbound, +x) primary carriageway; "
                                      "width not in the data, estimated from the client site plan (about 4 lanes, 17-19 m)")},
    "nearby_roads": [{"name": o["name"], "class": o["class"], "distance_m": round(o["d"], 1),
                      "points": [[three(x, y) for x, y in g.intersection(sc_pt.buffer(300)).simplify(0.5).coords]
                                 for g in o["geoms"] if not g.intersection(sc_pt.buffer(300)).is_empty
                                 and g.intersection(sc_pt.buffer(300)).geom_type == "LineString"]}
                     for o in near3],
    "service_roads_within_100m": service,
}
(geo.DATA / "site-ground.json").write_text(json.dumps(site_ground, ensure_ascii=False, indent=1))

print(f"{len(pois)} POIs, metro lines {[ (m['name'], m.get('length_m')) for m in metro]}")
print("kazbegi carriageways", len(kaz), "separation", round(sep, 1), "frontage->centreline", front_to_cl, "nearby", [(o['name'], round(o['d'])) for o in near3])
for p in pois:
    print(f"{p['name_en'][:38]:38s} {p['category']:9s} straight {p['straight_m']:6d}  walk {p['walk_m'] or '-':>6} m {p['walk_min'] or '-':>4} min  drive {p['drive_m']:6d} m {p['drive_min']:3d} min")
