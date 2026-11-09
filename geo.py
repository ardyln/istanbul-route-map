"""Land and lakes for a true-scale map, from OpenStreetMap (data/geo/, fetched with Overpass; see Makefile).

OSM draws a coastline with the land on its left. The pieces are joined into chains, clipped to the map's box,
and closed along the box's edge (counterclockwise, keeping the land on the left) into land polygons; islands
are closed rings already. The sea is whatever isn't land. Lakes and reservoirs are drawn over the land.
Coordinates here are (lon, lat).
"""
import json
import math


def _chains(ways):
    """Coastline ways joined end to start by their node ids: lists of (lon, lat), and whether each is closed."""
    by_start = {w["nodes"][0]: w for w in ways}
    ends = {w["nodes"][-1] for w in ways}
    used, out = set(), []
    def follow(w):
        pts, nodes = [], []
        while w is not None and w["id"] not in used:
            used.add(w["id"])
            g = [(p["lon"], p["lat"]) for p in w["geometry"]]
            pts += g if not pts else g[1:]
            nodes.append(w["nodes"][-1])
            w = by_start.get(w["nodes"][-1])
        return pts
    for w in ways:                                   # open chains first: from a way nothing leads into
        if w["nodes"][0] not in ends and w["id"] not in used:
            out.append(follow(w))
    for w in ways:                                   # what's left are rings
        if w["id"] not in used:
            out.append(follow(w))
    return out


def _clip_segment(p, q, box):
    """Liang–Barsky: the part of segment p→q inside box (W, S, E, N), as (a, b, t0, t1), or None."""
    (x0, y0), (x1, y1) = p, q
    W, S, E, N = box
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, x0 - W), (dx, E - x0), (-dy, y0 - S), (dy, N - y0)):
        if pp == 0:
            if qq < 0: return None
        else:
            r = qq / pp
            if pp < 0:
                if r > t1: return None
                t0 = max(t0, r)
            else:
                if r < t0: return None
                t1 = min(t1, r)
    return (x0 + dx * t0, y0 + dy * t0), (x0 + dx * t1, y0 + dy * t1), t0, t1


def _pieces(chain, box):
    """The parts of a chain inside the box; a ring wholly inside stays one closed piece."""
    pieces, cur = [], None
    for p, q in zip(chain, chain[1:]):
        c = _clip_segment(p, q, box)
        if c is None:
            continue
        a, b, t0, t1 = c
        if cur is None:
            cur = [a]
        cur.append(b)
        if t1 < 1:
            pieces.append(cur); cur = None
    if cur:
        pieces.append(cur)
    closed = chain[0] == chain[-1]
    if closed and len(pieces) > 1 and pieces[0][0] == chain[0] and pieces[-1][-1] == chain[-1]:
        pieces[0] = pieces.pop() + pieces[0][1:]     # a ring cut by the box: its start and end pieces are one
    return pieces


def _perimeter(pt, box):
    """Position along the box's edge, counterclockwise from the south-west corner."""
    W, S, E, N = box
    x, y = pt
    w, h = E - W, N - S
    if abs(y - S) < 1e-9: return x - W
    if abs(x - E) < 1e-9: return w + (y - S)
    if abs(y - N) < 1e-9: return w + h + (E - x)
    return 2 * w + h + (N - y)


def land_polygons(coastline_json, box):
    W, S, E, N = box
    ways = [e for e in json.load(open(coastline_json))["elements"] if e["type"] == "way" and e.get("geometry")]
    polys, open_pieces = [], []
    for chain in _chains(ways):
        for piece in _pieces(chain, box):
            if piece[0] == piece[-1] and len(piece) > 3:
                polys.append(piece)                   # an island
            elif len(piece) >= 2:
                open_pieces.append(piece)
    corners = [((W, S), 0), ((E, S), E - W), ((E, N), (E - W) + (N - S)), ((W, N), 2 * (E - W) + (N - S))]
    total = 2 * ((E - W) + (N - S))
    entries = sorted(((_perimeter(p[0], box), i) for i, p in enumerate(open_pieces)))
    done = set()
    for start in range(len(open_pieces)):
        if start in done: continue
        ring, i = [], start
        for _ in range(len(open_pieces) + 1):
            done.add(i)
            ring += open_pieces[i]
            t_exit = _perimeter(open_pieces[i][-1], box)
            # the next coastline coming back in, counterclockwise from where this one left
            nxt = min(entries, key=lambda e: (e[0] - t_exit) % total)
            t_next = nxt[0]
            span = (t_next - t_exit) % total
            for c, tc in sorted(corners, key=lambda c: (c[1] - t_exit) % total):
                if 0 < (tc - t_exit) % total < span:
                    ring.append(c)
            i = nxt[1]
            if i == start:
                break
        ring.append(ring[0])
        polys.append(ring)
    return polys


def _area_km2(ring):
    kx = 111.32 * math.cos(math.radians(41)); ky = 110.57
    return abs(sum((a[0] * kx) * (b[1] * ky) - (b[0] * kx) * (a[1] * ky) for a, b in zip(ring, ring[1:]))) / 2


def _rings_from_members(members):
    """Outer and inner ways of a multipolygon joined into closed rings by matching end points."""
    out = {"outer": [], "inner": []}
    for role in out:
        segs = [[(p["lon"], p["lat"]) for p in m["geometry"]] for m in members
                if m.get("role", "outer") == role and m.get("type") == "way" and m.get("geometry")]
        while segs:
            ring = segs.pop(0)
            changed = True
            while ring[0] != ring[-1] and changed:
                changed = False
                for k, s in enumerate(segs):
                    if s[0] == ring[-1]: ring += s[1:]
                    elif s[-1] == ring[-1]: ring += s[::-1][1:]
                    elif s[-1] == ring[0]: ring = s + ring[1:]
                    elif s[0] == ring[0]: ring = s[::-1] + ring[1:]
                    else: continue
                    segs.pop(k); changed = True; break
            if ring[0] == ring[-1] and len(ring) > 3:
                out[role].append(ring)
    return out


def lakes(water_json, min_km2=0.15):
    """[(outer rings, inner rings)] of lakes, reservoirs and lagoons at least min_km2 in area."""
    found = []
    for e in json.load(open(water_json))["elements"]:
        if e["type"] == "way" and e.get("geometry"):
            ring = [(p["lon"], p["lat"]) for p in e["geometry"]]
            if ring[0] == ring[-1] and _area_km2(ring) >= min_km2:
                found.append(([ring], []))
        elif e["type"] == "relation":
            r = _rings_from_members(e.get("members", []))
            outer = [x for x in r["outer"] if _area_km2(x) >= min_km2]
            if outer:
                found.append((outer, r["inner"]))
    return found


def simplify(pts, eps):
    """Douglas–Peucker on screen points, keeping the ends. A ring is split at its farthest point first."""
    if len(pts) < 3: return pts
    if pts[0] == pts[-1] and len(pts) > 3:
        k = max(range(len(pts)), key=lambda m: math.dist(pts[0], pts[m]))
        return simplify(pts[:k + 1], eps) + simplify(pts[k:], eps)[1:]
    keep = [False] * len(pts); keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        (x1, y1), (x2, y2) = pts[i], pts[j]
        L = math.hypot(x2 - x1, y2 - y1) or 1e-9
        best, k = 0.0, None
        for m in range(i + 1, j):
            d = abs((x2 - x1) * (y1 - pts[m][1]) - (x1 - pts[m][0]) * (y2 - y1)) / L
            if d > best: best, k = d, m
        if k is not None and best > eps:
            keep[k] = True; stack += [(i, k), (k, j)]
    return [p for p, kk in zip(pts, keep) if kk]
