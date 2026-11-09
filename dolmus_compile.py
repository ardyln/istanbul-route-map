#!/usr/bin/env python3
"""Compile İBB's minibüs and taksi-dolmuş open data into ordered lines with named stops.

Usage: python3 dolmus_compile.py <data dir> <out json, or .json.gz to gzip it> [<shapes out json>]

Inputs in <data dir>: istanbul_minibus_guzergahlari.geojson, istanbul_minibus_duraklari.geojson,
istanbul_taksidolmus_guzergahlari.geojson, istanbul_taksidolmus_duraklari.geojson (data.ibb.gov.tr), and
iett_stops.json (İBB GetDurak_json: every İETT stop with coordinates).

Minibüs stops aren't tied to lines in the data, so a line's stops are the minibüs stops within STOP_M metres
of its route, in order along it. Taksi-dolmuş stop anywhere along the route; their stands are mostly at the
ends, so the İETT stops along a dolmuş route stand in as named places to get on and off. Taksi-dolmuş
alternative and depot routes (GUZERGAH "Alternatif…", "Depolama") are left out.
"""
import json, math, sys, collections, re

STOP_M = 30.0        # metres from a route for a minibüs or İETT stop to count as on it
STAND_M = 80.0       # metres for a dolmuş stand
MIN_KM = 0.3         # shorter route pieces are connectors between branches, not routes
LAT0 = 41.0
KX, KY = 111_320 * math.cos(math.radians(LAT0)), 110_570
LOWER = str.maketrans("İIÇĞÖŞÜ", "iıçğöşü")
def title(s):
    """ALL-CAPS Turkish names as Title Case, word by word and across hyphens and slashes."""
    s = re.sub(r"\s+", " ", (s or "").strip())
    def word(m):
        w = m.group(0)
        return w[:1] + w[1:].translate(LOWER).lower() if w.isupper() and len(w) > 1 else w
    return re.sub(r"[^\s\-/().,]+", word, s)

def xy(lon, lat):
    return lon * KX, lat * KY

class Grid:
    def __init__(self, cell=250.0):
        self.cell, self.cells = cell, collections.defaultdict(list)
    def add(self, x, y, item):
        self.cells[(int(x // self.cell), int(y // self.cell))].append((x, y, item))
    def near(self, x0, y0, x1, y1, pad):
        c = self.cell
        for i in range(int((min(x0, x1) - pad) // c), int((max(x0, x1) + pad) // c) + 1):
            for j in range(int((min(y0, y1) - pad) // c), int((max(y0, y1) + pad) // c) + 1):
                yield from self.cells.get((i, j), ())

def project(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy or 1e-9
    u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(ax + u * dx - px, ay + u * dy - py), u * math.sqrt(L2)

def stops_along(coords, grid, limit):
    """[(metres along, item)] of the grid's points within `limit` of the polyline, each at its nearest point."""
    pts = [xy(*c[:2]) for c in coords]
    best, along = {}, 0.0
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        for px, py, item in grid.near(ax, ay, bx, by, limit):
            d, u = project(px, py, ax, ay, bx, by)
            if d <= limit and (id(item) not in best or d < best[id(item)][0]):
                best[id(item)] = (d, along + u, item)
        along += math.hypot(bx - ax, by - ay)
    return sorted(((a, it) for _, a, it in best.values()), key=lambda x: x[0]), along

def lines_of(features):
    for f in features:
        g = f.get("geometry") or {}
        if g.get("type") == "LineString":
            yield f["properties"], [g["coordinates"]]
        elif g.get("type") == "MultiLineString":
            yield f["properties"], g["coordinates"]

def main(src, out, shapes_out=None):
    load = lambda n: json.load(open(f"{src}/{n}", encoding="utf-8"))
    mstops, dstands = Grid(), Grid()
    for f in load("istanbul_minibus_duraklari.geojson")["features"]:
        lon, lat = f["geometry"]["coordinates"][:2]
        mstops.add(*xy(lon, lat), {"name": title(f["properties"].get("DURAK_ADI") or "Minibüs durağı"), "lat": lat, "lon": lon, "kind": "minibus"})
    for f in load("istanbul_taksidolmus_duraklari.geojson")["features"]:
        lon, lat = f["geometry"]["coordinates"][:2]
        nm = re.sub(r"\s*\(.*?\)\s*", " ", f["properties"].get("DURAK_ADI") or "Dolmuş durağı").strip()
        if nm.lower().startswith("depolama"):
            continue  # a depot stand where dolmuş wait off duty, not a place to get on
        dstands.add(*xy(lon, lat), {"name": title(nm), "lat": lat, "lon": lon, "kind": "stand"})
    istops = Grid()
    for d in load("iett_stops.json"):
        m = re.match(r"POINT \(([\d.]+) ([\d.]+)\)", d.get("KOORDINAT") or "")
        if m:
            lon, lat = float(m.group(1)), float(m.group(2))
            istops.add(*xy(lon, lat), {"name": title(d["SDURAKADI"]), "lat": lat, "lon": lon, "kind": "iett"})

    def nearest(c, limit=400.0):
        x, y = xy(*c[:2])
        best = min(((math.hypot(px - x, py - y), it["name"]) for g in (dstands, istops, mstops)
                    for px, py, it in g.near(x, y, x, y, limit)), default=(None, None))
        return best[1] if best[0] is not None and best[0] <= limit else "Güzergah ucu"

    out_lines, shapes = [], {}
    def add(mode, no, name, variant, parts, finders):
        for k, coords in enumerate(parts):
            if len(coords) < 2: continue
            pts = [xy(*c[:2]) for c in coords]
            if sum(math.dist(a, b) for a, b in zip(pts, pts[1:])) < MIN_KM * 1000: continue
            found, total = [], 0.0
            for grid, limit in finders:
                got, total = stops_along(coords, grid, limit)
                found += got
            found.sort(key=lambda x: x[0])
            stops = []
            for a, it in found:      # one entry per name in a row (both sides of a road, a stand beside a stop)
                if stops and stops[-1][0] == it["name"]:
                    continue
                stops.append([it["name"], round(it["lat"], 6), round(it["lon"], 6), round(a / 1000, 2), it["kind"]])
            # a route's ends without a stop of their own take the name of the nearest stop (any kind), not the
            # line's name: that names the outward ends, and a route can run either way
            if not stops or stops[0][3] > 0.15:
                stops.insert(0, [nearest(coords[0]), round(coords[0][1], 6), round(coords[0][0], 6), 0.0, "end"])
            if stops[-1][3] < total / 1000 - 0.15:
                stops.append([nearest(coords[-1]), round(coords[-1][1], 6), round(coords[-1][0], 6), round(total / 1000, 2), "end"])
            lid = f"{mode}:{no}:{len([l for l in out_lines if l['no'] == no and l['mode'] == mode])}"
            out_lines.append({"id": lid, "mode": mode, "no": no, "name": title(name), "variant": title(variant),
                              "km": round(total / 1000, 2), "stops": stops})
            shapes[lid] = [[round(c[1], 5), round(c[0], 5)] for c in coords]

    for p, parts in lines_of(load("istanbul_minibus_guzergahlari.geojson")["features"]):
        add("minibus", p.get("HATNO") or "?", p.get("HAT_ADI") or "", p.get("GUZERGAH") or "", parts, [(mstops, STOP_M)])
    for p, parts in lines_of(load("istanbul_taksidolmus_guzergahlari.geojson")["features"]):
        g = (p.get("GUZERGAH") or "")
        if g.startswith("Alternatif") or g == "Depolama":
            continue
        add("dolmus", p.get("HAT_NO") or "?", p.get("HAT_ADI") or "", g, parts, [(dstands, STAND_M), (istops, STOP_M)])

    out_lines.sort(key=lambda l: (l["mode"], re.sub(r"\D", "", l["no"]).zfill(4), l["no"], l["id"]))
    meta = {"source": "data.ibb.gov.tr: Minibüs Hatları/Durakları, Taksi Dolmuş Hatları/Durakları (İBB Açık Veri Lisansı); "
                      "İETT stops from İBB HatDurakGuzergah GetDurak_json",
            "stop_metres": STOP_M, "lines": out_lines}
    text = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if out.endswith(".gz"):
        import gzip
        text = gzip.compress(text, 9, mtime=0)   # no timestamp: the same data gives the same file
    open(out, "wb").write(text)
    if shapes_out:
        json.dump(shapes, open(shapes_out, "w"), separators=(",", ":"))
    by = collections.Counter(l["mode"] for l in out_lines)
    nos = {(l["mode"], l["no"]) for l in out_lines}
    print(f"{len(out_lines)} routes ({dict(by)}), {len(nos)} lines, "
          f"{sum(len(l['stops']) for l in out_lines)} stop entries, "
          f"median {sorted(len(l['stops']) for l in out_lines)[len(out_lines) // 2]} stops a route -> {out}")

if __name__ == "__main__":
    main(*sys.argv[1:])
