"""Schematic Istanbul route map: every İETT bus line, the Metrobüs, minibüs and taksi-dolmuş lines,
every stop named. Octilinear corridors, route numbers along them. Writes an SVG.

Data (in data/): hat.json and durak.json from İBB's HatDurakGuzergah service (all İETT lines; all stops with
coordinates), lines/*.json from fetch_orders.py (each İETT line's stop order), dolmus.json from
dolmus_compile.py (minibüs and taksi-dolmuş routes with their stops in order).
"""
import bisect, json, glob, math, re, collections, html, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/iett-route-map.svg')
MODE = os.environ.get('MODE', 'snapped')             # snapped: true scale, real shores, lines straightened to 0/45/90° near
                                                     # their real roads; geographic: lines stop to stop; schematic: stretched
TRUE = MODE in ('geographic', 'snapped')
SNAP_EPS = float(os.environ.get('SNAP_EPS', 1.5))    # MODE=snapped: layout units (100 m) of road wiggle smoothed away
SNAP_PIECE = float(os.environ.get('SNAP_PIECE', 6))  # MODE=snapped: layout units; longer stretches are straightened in pieces
GEO_STEP = float(os.environ.get('GEO_STEP', 0.1))    # MODE=geographic: km per layout unit (labels and dots are sized in px)
WARP = 'blend' if TRUE else os.environ.get('WARP', 'elastic')             # elastic: room where the stops are, square by square; blend: per axis
GEOGRAPHY = 1.0 if TRUE else float(os.environ.get('GEOGRAPHY', 1.0))  # WARP=blend: share of true distances (1: true scale)
STEPS = int(os.environ.get('STEPS', 700))            # WARP=blend: grid steps across the map, west to east
ELASTIC_STEPS = int(os.environ.get('ELASTIC_STEPS', 830))  # WARP=elastic: grid steps across the stretched map
BASE = float(os.environ.get('BASE', 0.3))           # WARP=elastic: room for empty land, as a share of where stops are
MIN_GAP = float(os.environ.get('MIN_GAP', 1.5))      # grid steps every stop gets along its line, at least
COAST_EPS = float(os.environ.get('COAST_EPS', 2.0))
COAST_PIECE = float(os.environ.get('COAST_PIECE', 6.0))  # grid steps: longer stretches of shore are straightened in pieces  # grid steps of coastline detail smoothed away before it's straightened
SCALE = float(os.environ.get('SCALE', 32))           # px per grid step to start from; grows only if a name or line has no room
GROW = 1.15                                          # how much larger each attempt is
FS_STOP, FS_KEY, FS_HUB = 5.5, 7.0, 9.5         # px

durak = json.load(open(f'{HERE}/data/durak.json'))
iett = [json.load(open(f)) for f in sorted(glob.glob(f'{HERE}/data/lines/*.json'))]
dolmus = json.load(open(f'{HERE}/data/dolmus.json'))['lines'] if os.path.exists(f'{HERE}/data/dolmus.json') else []

LOWER = str.maketrans("İIÇĞÖŞÜ", "iıçğöşü")
def title(s):
    return re.sub(r"[^\s\-/().,]+", lambda m: m.group(0)[:1] + m.group(0)[1:].translate(LOWER).lower()
                  if m.group(0).isupper() and len(m.group(0)) > 1 else m.group(0), s.strip())
def km(a, b):
    return math.hypot((a[0] - b[0]) * 110.57, (a[1] - b[1]) * 111.32 * math.cos(math.radians(41)))

# -- places ---------------------------------------------------------------------------------------------
pos, name, modes = {}, {}, collections.defaultdict(set)
acc = collections.defaultdict(list)
for d in durak:
    m = re.match(r'POINT \(([\d.]+) ([\d.]+)\)', d['KOORDINAT'] or '')
    if not m: continue
    g = str(d['SDURAKKODU'])[:-1]
    acc[g].append((float(m.group(2)), float(m.group(1))))
    name.setdefault(g, title(d['SDURAKADI']))
for g, pts in acc.items():
    pos[g] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
is_mb = lambda g: g.startswith('9000')
# same name within 300 m: one place (both sides of a road split over two code prefixes); never across the Metrobüs
alias, by_name = {}, collections.defaultdict(list)
for g in sorted(pos):
    by_name[name[g]].append(g)
for nm, gs in by_name.items():
    heads = []
    for g in gs:
        h = next((h for h in heads if km(pos[h], pos[g]) <= 0.3 and is_mb(h) == is_mb(g)), None)
        if h is None: heads.append(g)
        else: alias[g] = h
heads_by_name = collections.defaultdict(list)
for g in pos:
    if g not in alias: heads_by_name[name[g]].append(g)
def place_for(nm, lat, lon, near=0.15):
    """A minibüs/dolmuş stop joins a place of the same name close by, or becomes a place of its own."""
    for g in heads_by_name.get(nm, ()):
        if km(pos[g], (lat, lon)) <= near:
            return g
    g = f"x{len(pos)}"
    pos[g] = (lat, lon); name[g] = nm; heads_by_name[nm].append(g)
    return g

# -- the network: consecutive places of every line, each direction ----------------------------------------
edge_lines = collections.defaultdict(set)          # (a, b) -> {(mode, line)}
terminals = collections.Counter()
def add_seq(seq, mode, line):
    seq = [g for i, g in enumerate(seq) if i == 0 or seq[i - 1] != g]
    if len(seq) < 2: return
    terminals[seq[0]] += 1; terminals[seq[-1]] += 1
    for g in seq: modes[g].add(mode)
    for a, b in zip(seq, seq[1:]):
        edge_lines[tuple(sorted((a, b)))].add((mode, line))
n_iett = 0
for L in iett:
    drawn = False
    for codes in L['dirs']:
        seq = [alias.get(c[:-1], c[:-1]) for c in codes if c[:-1] in pos]
        if len(set(seq)) >= 2:
            add_seq(seq, 'metrobus' if all(is_mb(g) for g in seq) else 'bus', L['line']); drawn = True
    n_iett += drawn
for r in dolmus:
    add_seq([place_for(s[0], s[1], s[2]) for s in r['stops']], r['mode'], r['no'])
adj = collections.defaultdict(set)
for a, b in edge_lines:
    adj[a].add(b); adj[b].add(a)
serves = collections.defaultdict(set)
for (a, b), ls in edge_lines.items():
    serves[a] |= ls; serves[b] |= ls

# -- key places and corridors -----------------------------------------------------------------------------
def is_key(g):
    if len(adj[g]) != 2 or g in terminals: return True
    a, b = sorted(adj[g])
    return edge_lines[tuple(sorted((g, a)))] != edge_lines[tuple(sorted((g, b)))]
key = {g for g in adj if is_key(g)}
def chains():
    out, seen = [], set()
    for k in sorted(key):          # sorted throughout: the same data always gives the same map
        for nb in sorted(adj[k]):
            if tuple(sorted((k, nb))) in seen: continue
            chain, prev, cur = [], k, nb
            seen.add(tuple(sorted((k, nb))))
            while cur not in key:
                chain.append(cur)
                nxt = next(iter(adj[cur] - {prev}))
                seen.add(tuple(sorted((cur, nxt))))
                prev, cur = cur, nxt
            out.append((k, cur, chain))
    return out
def bends(pts, eps):
    if len(pts) < 3: return []
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    L = math.hypot(x2 - x1, y2 - y1) or 1e-9
    dist = [abs((x2 - x1) * (y1 - y) - (x1 - x) * (y2 - y1)) / L for x, y in pts[1:-1]]
    i = max(range(len(dist)), key=dist.__getitem__)
    if dist[i] <= eps: return []
    i += 1
    return bends(pts[:i + 1], eps) + [i] + [i + j for j in bends(pts[i:], eps)]


# -- land and water ---------------------------------------------------------------------------------------
import geo  # noqa: E402  (next to this file)
SEA = '#d4e6f4'
GEO_BOX = (27.90, 40.70, 30.00, 41.62)   # lon/lat box the coastline was fetched for (see Makefile)
LAND = geo.land_polygons(f'{HERE}/data/geo/coastline.json', GEO_BOX) if os.path.exists(f'{HERE}/data/geo/coastline.json') else []
LAKES = geo.lakes(f'{HERE}/data/geo/water.json') if LAND and os.path.exists(f'{HERE}/data/geo/water.json') else []

# -- layout: stops spread out evenly, partly; then snapped to a grid ----------------------------------------
def _dp_keep(pts, eps):
    """Douglas–Peucker: indices kept (ends included)."""
    keep = {0, len(pts) - 1}
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
            keep.add(k); stack += [(i, k), (k, j)]
    return sorted(keep)

LAT0, LON0 = 41.035, 29.01
def lin(lat, lon):
    return (lon - LON0) * 111.32 * math.cos(math.radians(LAT0)), (LAT0 - lat) * 110.57
_pts = [lin(*pos[g]) for g in adj]
_xs, _ys = sorted(p[0] for p in _pts), sorted(p[1] for p in _pts)
X_MIN, X_MAX, Y_MIN, Y_MAX = _xs[0], _xs[-1], _ys[0], _ys[-1]
def _cdf(vals, v):
    """Share of the stops west (or north) of v, continuous between them."""
    if v <= vals[0]: return 0.0
    if v >= vals[-1]: return 1.0
    i = bisect.bisect_left(vals, v)
    lo, hi = vals[i - 1], vals[i]
    return (i - 1 + (v - lo) / (hi - lo or 1)) / (len(vals) - 1)
GRID = (X_MAX - X_MIN) / STEPS
def blend(lat, lon):
    """Each axis: GEOGRAPHY of the true distance, the rest by how many stops lie before it, so a dense
    district far out (Esenyurt) gets as much room as one in the centre, and empty forest and sea shrink."""
    x, y = lin(lat, lon)
    return (GEOGRAPHY * (x - X_MIN) + (1 - GEOGRAPHY) * _cdf(_xs, x) * (X_MAX - X_MIN),
            GEOGRAPHY * (y - Y_MIN) + (1 - GEOGRAPHY) * _cdf(_ys, y) * (Y_MAX - Y_MIN))
warp = blend
if TRUE:
    GRID = GEO_STEP
if WARP == 'elastic':
    import elastic  # noqa: E402
    import hashlib, pickle  # noqa: E401,E402
    _box = (X_MIN - 8, Y_MIN - 8, X_MAX + 8, Y_MAX + 8)
    _land_km = [[lin(lat, lon) for lon, lat in ring] for ring in LAND]
    _key = hashlib.sha1(repr((sorted(_pts), _box, BASE, len(LAND), sum(len(r) for r in LAND))).encode()).hexdigest()[:16]
    _cache = f'{HERE}/data/cartogram-{_key}.pickle'      # the flow takes a minute; the same stops give the same sheet
    if os.path.exists(_cache):
        _sheet = pickle.load(open(_cache, 'rb'))
    else:
        _sheet = elastic.Elastic(_pts, _box, base=BASE, land=_land_km)
        pickle.dump(_sheet, open(_cache, 'wb'))
    def warp(lat, lon):
        return _sheet(*lin(lat, lon))
    _w = [warp(*pos[g]) for g in adj]
    GRID = (max(p[0] for p in _w) - min(p[0] for p in _w)) / ELASTIC_STEPS

for a, b, chain in (chains() if not TRUE else []):      # keep where a corridor really bends
    pts = [warp(*pos[g]) for g in [a] + chain + [b]]
    for i in bends([(x / GRID, y / GRID) for x, y in pts], 2.5):
        key.add(([a] + chain + [b])[i])

taken, grid = {}, {}
GAP = int(os.environ.get('GAP', 2))   # grid steps between places, at least: a free grid line between neighbouring lines
def _clear(cx, cy):
    return all((cx + i, cy + j) not in taken for i in range(1 - GAP, GAP) for j in range(1 - GAP, GAP))
def snap(g):
    x, y = warp(*pos[g])
    gx, gy = round(x / GRID), round(y / GRID)
    for rad in range(0, 40):
        cells = [(gx + dx, gy + dy) for dx in range(-rad, rad + 1) for dy in range(-rad, rad + 1)
                 if max(abs(dx), abs(dy)) == rad and _clear(gx + dx, gy + dy)]
        if cells:
            best = min(cells, key=lambda c: (c[0] - x / GRID) ** 2 + (c[1] - y / GRID) ** 2)
            taken[best] = g; grid[g] = best
            return
    raise RuntimeError(f"no free grid point near {name.get(g, g)}")
if TRUE:                          # every place exactly where it is (snapped mode then snaps the junctions)
    for g in adj:
        x, y = warp(*pos[g]); grid[g] = (x / GRID, y / GRID)
    real = dict(grid)
    if MODE == 'snapped':
        GAP = 1
        for g in sorted(key, key=lambda g: (-len(serves[g]), g)):
            snap(g)
else:
    for g in sorted(key, key=lambda g: (-len(serves[g]), g)):      # busy places get their spot first
        snap(g)

def path_steps(a, b):
    (x1, y1), (x2, y2) = grid[a], grid[b]
    d = min(abs(x2 - x1), abs(y2 - y1))
    return d * math.sqrt(2) + max(abs(x2 - x1), abs(y2 - y1)) - d
# no squishing: a corridor needs a grid step for every stop along it, else its middle stop becomes a place of
# its own (on its own grid point), until every corridor has room
MIN_STEPS = MIN_GAP
passes = 0
while not TRUE:
    passes += 1
    split = 0
    for a, b, chain in chains():
        if chain and path_steps(a, b) < (len(chain) + 1) * MIN_STEPS:
            g = chain[len(chain) // 2]
            key.add(g); snap(g); split += 1
    if not split: break
corridors = [(a, b, chain, edge_lines[tuple(sorted((a, (chain or [b])[0])))]) for a, b, chain in chains()]
squish = 0 if TRUE else min((path_steps(a, b) / (len(chain) + 1) for a, b, chain, _ in corridors), default=0)
# how far the grid moved each place from where it is (true distance on a true-scale map, GEOGRAPHY=1)
_moved = sorted(math.dist(warp(*pos[g]), (grid[g][0] * GRID, grid[g][1] * GRID)) for g in key)
moved = {"median": _moved[len(_moved) // 2], "p95": _moved[int(len(_moved) * 0.95)], "max": _moved[-1]}

def octi(a, b, via):
    (x1, y1), (x2, y2) = a, b
    dx, dy = x2 - x1, y2 - y1
    d = min(abs(dx), abs(dy))
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    options = ((x1 + sx * d, y1 + sy * d), (x2 - sx * d, y2 - sy * d))
    return [a, min(options, key=lambda p: (p[0] - via[0]) ** 2 + (p[1] - via[1]) ** 2), b]
def _snapped_path(a, b, chain):
    """A corridor's real path (its stops in order) smoothed by SNAP_EPS, cut into pieces of at most SNAP_PIECE,
    with the points between snapped to the grid, each piece drawn with one 45° bend on the side of the real road."""
    pts = [grid[a]] + [real[c] for c in chain] + [grid[b]]
    idx = _dp_keep(pts, SNAP_EPS)
    cut = [idx[0]]
    for i, j in zip(idx, idx[1:]):
        run = 0.0
        for m in range(i + 1, j):
            run += math.dist(pts[m - 1], pts[m])
            if run >= SNAP_PIECE:
                cut.append(m); run = 0.0
        cut.append(j)
    anchors = [grid[a]] + [(round(pts[m][0]), round(pts[m][1])) for m in cut[1:-1]] + [grid[b]]
    out = [anchors[0]]
    for (i, j), (pa, pb) in zip(zip(cut, cut[1:]), zip(anchors, anchors[1:])):
        if pa == pb: continue
        for q in octi(pa, pb, pts[(i + j) // 2])[1:]:
            if q != out[-1]: out.append(q)
    return out if len(out) > 1 else [grid[a], grid[b]]

def _closest(path, q):
    """Distance along a path (layout units) of the point nearest q, and the total length."""
    best, at, run = None, 0.0, 0.0
    for p0, p1 in zip(path, path[1:]):
        L = math.dist(p0, p1)
        if L == 0: continue
        u = max(0.0, min(1.0, ((q[0] - p0[0]) * (p1[0] - p0[0]) + (q[1] - p0[1]) * (p1[1] - p0[1])) / (L * L)))
        d = math.dist(q, (p0[0] + u * (p1[0] - p0[0]), p0[1] + u * (p1[1] - p0[1])))
        if best is None or d < best: best, at = d, run + u * L
        run += L
    return at, run

paths = []
for a, b, chain, ls in sorted(corridors, key=lambda c: (len(c[3]), c[0], c[1])):
    via_real = pos[chain[len(chain) // 2]] if chain else ((pos[a][0] + pos[b][0]) / 2, (pos[a][1] + pos[b][1]) / 2)
    vx, vy = warp(*via_real)
    if MODE == 'geographic':      # stop to stop, as the line runs
        paths.append((a, b, chain, ls, [grid[a]] + [grid[c] for c in chain] + [grid[b]]))
    elif MODE == 'snapped':       # the real road smoothed, then straightened to 0/45/90° in short pieces
        paths.append((a, b, chain, ls, _snapped_path(a, b, chain)))
    else:
        paths.append((a, b, chain, ls, octi(grid[a], grid[b], (vx / GRID, vy / GRID))))


def _octi_ring(ring, P):
    """A coastline or lake shore smoothed (COAST_EPS grid steps) and straightened to 0/45/90°, like the lines;
    "" when it shrinks to nothing."""
    pts = [(warp(lat, lon)[0] / GRID, warp(lat, lon)[1] / GRID) for lon, lat in ring]
    if pts[0] == pts[-1] and len(pts) > 3:     # a ring: split at its farthest point so both halves keep their shape
        k = max(range(len(pts)), key=lambda m: math.dist(pts[0], pts[m]))
        idx = _dp_keep(pts[:k + 1], COAST_EPS) + [k + i for i in _dp_keep(pts[k:], COAST_EPS)][1:]
    else:
        idx = _dp_keep(pts, COAST_EPS)
    # a long stretch drawn with one 45° bend can stray far from the shore: cut it into pieces of COAST_PIECE
    cut = [idx[0]]
    for a, b in zip(idx, idx[1:]):
        run = 0.0
        for m in range(a + 1, b):
            run += math.dist(pts[m - 1], pts[m])
            if run >= COAST_PIECE:
                cut.append(m); run = 0.0
        cut.append(b)
    idx = cut
    out = []
    for a, b in zip(idx, idx[1:]):
        pa, pb = (round(pts[a][0]), round(pts[a][1])), (round(pts[b][0]), round(pts[b][1]))
        if pa == pb: continue
        mid = pts[(a + b) // 2]
        for q in octi(pa, pb, mid)[:-1]:
            if not out or out[-1] != q: out.append(q)
    if len(set(out)) < 3:
        return ""
    return "M" + "L".join(f"{P(q)[0]:.0f},{P(q)[1]:.0f}" for q in out) + "Z"

# -- colours ----------------------------------------------------------------------------------------------
BUS = ('#9ec5e8', '#5a9bd4', '#2f6fb3', '#163f7a')
MINI = ('#9fd8b4', '#4fb878', '#23864b', '#145c32')
DOLMUS = '#f08c1e'
def colour(ls):
    m = {mode for mode, _ in ls}
    n = len(ls)
    shade = 0 if n <= 2 else 1 if n <= 5 else 2 if n <= 12 else 3
    if m == {'metrobus'}: return '#e2231a'
    if m <= {'minibus'}: return MINI[shade]
    if m <= {'dolmus'}: return DOLMUS
    return BUS[shade]
order = lambda l: ({'metrobus': 0, 'bus': 1, 'dolmus': 2, 'minibus': 3}[l[0]],
                   re.sub(r'\D.*', '', l[1]).zfill(4) if re.match(r'\d', l[1]) else 'z' + l[1], l[1])

# -- overlap test for text: rotated rectangles, separating axes, spatial hash ------------------------------
PAD = 0.5   # px kept clear around every piece of text
def rect(px, py, w, h, ang, text=""):
    """A text box from its baseline start: h is the font size; real fonts reach about 1 em above the baseline
    and 0.25 below, measured like the browser does (getBBox), plus PAD all round."""
    ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    vx, vy = uy, -ux
    px, py = px - ux * PAD, py - uy * PAD
    up = 1.14 if any(ch in "İÖÜĞÂÎÛ" for ch in text) else 1.02      # a dot or breve above a capital reaches higher
    down = 0.34 if any(ch in "ŞÇşç" for ch in text) else 0.26       # a cedilla reaches lower
    w, below, h = w + 2 * PAD, h * down + PAD, h * (up + down) + 2 * PAD
    b0 = (px - vx * below, py - vy * below)
    return [b0, (b0[0] + ux * w, b0[1] + uy * w), (b0[0] + ux * w + vx * h, b0[1] + uy * w + vy * h), (b0[0] + vx * h, b0[1] + vy * h)]
def box(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
def overlap(a, b):
    for p, q in ((a[0], a[1]), (a[0], a[3]), (b[0], b[1]), (b[0], b[3])):
        ax = (q[0] - p[0], q[1] - p[1])
        pa = [x * ax[0] + y * ax[1] for x, y in a]; pb = [x * ax[0] + y * ax[1] for x, y in b]
        if max(pa) <= min(pb) or max(pb) <= min(pa): return False
    return True
# each character's width in em: the widest of the common sans-serif fonts (tools/measure_chars.js), so a
# name sized with it fits whichever a viewer's browser picks
_CW = json.load(open(f'{HERE}/tools/charwidths.json'))['widths'] if os.path.exists(f'{HERE}/tools/charwidths.json') else {}
def text_w(t, fs):
    return sum(_CW.get(ch, 0.72) for ch in t) * fs + 1.5

def draw(SCALE):
    """The whole map at SCALE px per grid step; returns the SVG and how many names or tags had no free spot."""
    CELL = 48
    occupied = collections.defaultdict(list)
    nid = [0]
    def cells_of(c):
        xs_, ys_ = [p[0] for p in c], [p[1] for p in c]
        return [(i, j) for i in range(int(min(xs_) // CELL), int(max(xs_) // CELL) + 1)
                for j in range(int(min(ys_) // CELL), int(max(ys_) // CELL) + 1)]
    def free(c):
        for cell in cells_of(c):
            for _, other in occupied[cell]:
                if overlap(c, other): return False
        return True
    def occupy(c):
        nid[0] += 1
        for cell in cells_of(c): occupied[cell].append((nid[0], c))

    xs = [c[0] for c in grid.values()]; ys = [c[1] for c in grid.values()]
    X0, Y0 = min(xs) - 10, min(ys) - 14
    W, H = (max(xs) - X0 + 10) * SCALE, (max(ys) - Y0 + 8) * SCALE
    P = lambda c: ((c[0] - X0) * SCALE, (c[1] - Y0) * SCALE)
    def along(path, frac):
        pts = [P(p) for p in path]
        segs = [math.dist(p, q) for p, q in zip(pts, pts[1:])]
        t = frac * (sum(segs) or 1)
        for (p, q), s in zip(zip(pts, pts[1:]), segs):
            if s > 0 and t <= s:
                return (p[0] + (q[0] - p[0]) * t / s, p[1] + (q[1] - p[1]) * t / s), ((q[0] - p[0]) / s, (q[1] - p[1]) / s)
            t -= s
        for p, q in zip(pts[::-1][1:], pts[::-1]):
            s = math.dist(p, q)
            if s > 0: return pts[-1], ((q[0] - p[0]) / s, (q[1] - p[1]) / s)
        return pts[-1], (1.0, 0.0)

    stats = collections.Counter()
    failed = []
    moved_px = []
    svg_lines, svg_dots, svg_labels, tags = [], [], [], []
    occupy(box(0, 0, 1500, 175))          # the title and key
    def place_label(x, y, text, fs, cands, weight=400):
        w, h = text_w(text, fs), fs
        for ring in (1.0, 1.8, 2.8, 4.0, 5.5, 7.5):
            for dx, dy, ang, anchor in cands:
                px, py = x + dx * ring, y + dy * ring
                if anchor == 'end':
                    px -= math.cos(math.radians(ang)) * w; py -= math.sin(math.radians(ang)) * w
                c = rect(px, py, w, h, ang, text)
                if free(c):
                    occupy(c)
                    if ring > 1:
                        mx, my = (c[0][0] + c[3][0]) / 2, (c[0][1] + c[3][1]) / 2
                        svg_labels.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{mx:.1f}" y2="{my:.1f}" stroke="#888" stroke-width="0.4"/>')
                        stats['leader'] += 1
                    rot = f' transform="rotate({ang:.0f} {px:.1f} {py:.1f})"' if ang else ''
                    svg_labels.append(f'<text x="{px:.1f}" y="{py:.1f}" font-size="{fs}" font-weight="{weight}" fill="#111"{rot} '
                                      f'stroke="#fbfaf7" stroke-width="{fs * 0.32:.1f}" paint-order="stroke">{html.escape(text)}</text>')
                    return True
        # still nowhere: a spiral of level spots further out, joined by a leader line
        for radius in range(int(3 * fs), int(40 * fs), int(1.5 * fs)):
            for k in range(16):
                ang = 2 * math.pi * k / 16
                px, py = x + math.cos(ang) * radius, y + math.sin(ang) * radius
                if math.cos(ang) < -0.3: px -= w
                c = rect(px, py, w, h, 0, text)
                if free(c):
                    occupy(c)
                    mx, my = (c[0][0] + c[3][0]) / 2 if math.cos(ang) >= -0.3 else (c[1][0] + c[2][0]) / 2, (c[0][1] + c[3][1]) / 2
                    svg_labels.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{mx:.1f}" y2="{my:.1f}" stroke="#888" stroke-width="0.4"/>')
                    svg_labels.append(f'<text x="{px:.1f}" y="{py:.1f}" font-size="{fs}" font-weight="{weight}" fill="#111" '
                                      f'stroke="#fbfaf7" stroke-width="{fs * 0.32:.1f}" paint-order="stroke">{html.escape(text)}</text>')
                    stats['leader'] += 1; stats['far'] += 1
                    return True
        stats['no_room'] += 1
        failed.append((text, round(x), round(y)))
        return False
    def stop_cands(d, r):
        o = r + 2
        if abs(d[1]) < 0.2:
            return [(o * 0.5, -o, -45, 'start'), (-o * 0.5, o, -45, 'end'), (o * 0.5, -o, -60, 'start'), (-o * 0.5, o, -60, 'end'),
                    (o * 0.3, -o, -90, 'start'), (-o * 0.3, o, -90, 'end')]
        if abs(d[0]) < 0.2:
            return [(o, FS_STOP * 0.35, 0, 'start'), (-o, FS_STOP * 0.35, 0, 'end'), (o, 0, -20, 'start'), (-o, FS_STOP * 0.7, 20, 'end'),
                    (o, -FS_STOP * 0.4, -35, 'start'), (-o, FS_STOP, 35, 'end')]
        perp = -45 if d[0] * d[1] > 0 else 45
        return [(o, FS_STOP * 0.35, 0, 'start'), (-o, FS_STOP * 0.35, 0, 'end'),
                (o * 0.7, -o * 0.7 if perp == -45 else o * 0.7, perp, 'start'), (-o * 0.7, o * 0.7 if perp == -45 else -o * 0.7, perp, 'end')]
    def key_cands(r, fs):
        o = r + 2
        return [(o, fs * 0.35, 0, 'start'), (-o, fs * 0.35, 0, 'end'), (o * 0.7, -o * 0.7, -45, 'start'), (-o * 0.7, o * 0.7, -45, 'end'),
                (o * 0.7, o * 0.7 + fs, 0, 'start'), (-o * 0.7, -o * 0.7, 0, 'end'), (0, -o, 0, 'start'), (0, o + fs, 0, 'start')]

    corridor_draw, stop_spots, key_spots = [], [], []
    for a, b, chain, ls, path in paths:
        w = min(1.8 + len(ls) * 0.4, 11)
        col = colour(ls)
        dash = ' stroke-dasharray="5 2.5"' if {m for m, _ in ls} == {'dolmus'} else ''
        svg_lines.append(f'<polyline points="{" ".join(f"{P(p)[0]:.0f},{P(p)[1]:.0f}" for p in path)}" fill="none" stroke="{col}" '
                         f'stroke-width="{w:.1f}" stroke-linejoin="round" stroke-linecap="round"{dash}/>')
        if MODE == 'snapped' and chain:
            # each stop on the straightened line where it's nearest to where the stop really is, in order and apart
            ats = [_closest(path, real[c]) for c in chain]
            total = ats[0][1] or 1.0
            gap = min(0.8, total / (len(chain) + 1))
            fracs, last = [], 0.0
            for k, (at, _) in enumerate(ats):
                at = min(max(at, last + gap), total - gap * (len(chain) - k))
                fracs.append(at / total); last = at
        for i, g in enumerate(chain):
            if MODE == 'snapped':     # on the straightened line, at the point nearest where the stop really is
                (x, y), d = along(path, fracs[i])
                moved_px.append(math.dist((x, y), P(real[g])))
            elif MODE == 'geographic':  # the stop where it is; the line's direction there, from its neighbours
                x, y = P(path[i + 1]); px_, py_ = P(path[i]); nx_, ny_ = P(path[i + 2])
                L = math.hypot(nx_ - px_, ny_ - py_) or 1.0
                d = ((nx_ - px_) / L, (ny_ - py_) / L)
            else:
                (x, y), d = along(path, (i + 1) / (len(chain) + 1))
            r = max(1.5, w / 2.6)
            svg_dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#fff" stroke="{col}" stroke-width="0.9"/>')
            occupy(box(x - r, y - r, x + r, y + r))
            stop_spots.append((g, x, y, d, r))
        corridor_draw.append((ls, path, col))
    for g in sorted(key):
        x, y = P(grid[g])
        n = len(serves[g])
        r = 2.6 + min(n, 30) * 0.12
        fill = '#e2231a' if is_mb(g) else '#fff'
        svg_dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" stroke="#111" stroke-width="1.1"/>')
        occupy(box(x - r, y - r, x + r, y + r))
    for g in sorted(key, key=lambda g: (-len(serves[g]), g)):
        x, y = P(grid[g]); n = len(serves[g])
        fs = FS_HUB if n >= 10 else FS_KEY
        place_label(x, y, name[g], fs, key_cands(2.6 + min(n, 30) * 0.12, fs), weight=600 if n >= 10 else 500)
    for g, x, y, d, r in stop_spots:
        place_label(x, y, name[g], FS_STOP, stop_cands(d, r))

    shown = set()
    def put_tag(x, y, nums, col):
        items = [l[1] for l in nums]
        rows = [" ".join(items[i:i + 8]) for i in range(0, len(items), 8)][:6]
        if len(items) > 48: rows[-1] += f" +{len(items) - 48}"
        fs = 6.4
        tw = max(text_w(r, fs) for r in rows) + 5; th = len(rows) * fs * 1.2 + 3
        c = box(x - tw / 2 - PAD, y - th / 2 - PAD, x + tw / 2 + PAD, y + th / 2 + PAD)
        if not free(c): return False
        occupy(c)
        shown.update(nums[:48])
        tags.append(f'<g><rect x="{x - tw / 2:.1f}" y="{y - th / 2:.1f}" width="{tw:.1f}" height="{th:.1f}" rx="2" fill="#fff" stroke="{col}" stroke-width="0.7"/>'
                    + "".join(f'<text x="{x:.1f}" y="{y - th / 2 + fs * 1.2 * (i + 1):.1f}" font-size="{fs}" text-anchor="middle" fill="#111">{html.escape(r)}</text>'
                              for i, r in enumerate(rows)) + '</g>')
        return True
    for ls, path, col in sorted(corridor_draw, key=lambda c: (-len(c[0]), sorted(c[0], key=order), P(c[1][0]))):
        nums = sorted(ls, key=order)
        for frac in (0.5, 0.35, 0.65):
            (x, y), _ = along(path, frac)
            if put_tag(x, y, nums, col): break
    all_lines = {l for ls, _, _ in corridor_draw for l in ls}
    for ls, path, col in sorted(corridor_draw, key=lambda c: (len(c[0]), sorted(c[0], key=order), P(c[1][0]))):
        left = [l for l in sorted(ls, key=order) if l not in shown]
        if not left: continue
        done = False
        for frac in (0.5, 0.3, 0.7, 0.15, 0.85, 0.05, 0.95):
            (x, y), d = along(path, frac)
            for k in (0, 9, -9, 16, -16, 24, -24):
                if put_tag(x - d[1] * k, y + d[0] * k, left, col): done = True; break
            if done: break
    stats['unnamed_lines'] = len(all_lines - shown)

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" viewBox="0 0 {W:.0f} {H:.0f}" '
           'font-family="Inter, Roboto, Helvetica, Arial, sans-serif">', f'<rect width="{W:.0f}" height="{H:.0f}" fill="#fbfaf7"/>']
    if LAND:     # the sea is the background; land over it, lakes over the land (OpenStreetMap)
        svg[1] = f'<rect width="{W:.0f}" height="{H:.0f}" fill="{SEA}"/>'
        if TRUE:                  # the real shore, only thinned to what shows at this scale
            def ring(r):
                pts = geo.simplify([P((warp(lat, lon)[0] / GRID, warp(lat, lon)[1] / GRID)) for lon, lat in r], 0.6)
                return "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z" if len(pts) > 3 else ""
        else:
            ring = lambda r: _octi_ring(r, P)
        svg.append(f'<path fill="#fbfaf7" stroke="#b9c9d6" stroke-width="1" d="{"".join(ring(r) for r in LAND)}"/>')
        svg.append(f'<path fill="{SEA}" fill-rule="evenodd" d="{"".join(ring(r) for outer, inner in LAKES for r in outer + inner)}"/>')
    svg += svg_lines + svg_dots + tags + svg_labels
    n_mini = len({l for l in all_lines if l[0] == 'minibus'}); n_dol = len({l for l in all_lines if l[0] == 'dolmus'})
    svg.append(f'<text x="40" y="70" font-size="52" font-weight="700" fill="#111">Istanbul buses, minibüs and dolmuş</text>'
               f'<text x="40" y="104" font-size="20" fill="#444">{n_iett} İETT lines (incl. Metrobüs) · {n_mini} minibüs lines · {n_dol} taksi-dolmuş lines · '
               f'{len(adj)} stops, every one named · {"true geography: every stop where it is, lines from stop to stop" if MODE == "geographic" else "true scale, lines straightened to 45° and 90° along their roads" if MODE == "snapped" else "stretched where the stops are dense, lines and shores straightened to 45° and 90°" if WARP == "elastic" else "true scale, lines straightened to 45° and 90°" if GEOGRAPHY >= 1 else "schematic, not to scale"} · '
               f'data: İBB open data, İETT, OpenStreetMap contributors (land and water), 9 November 2026</text>')
    KEYS = [("İETT bus, 1–2 lines", BUS[0], ''), ("3–5", BUS[1], ''), ("6–12", BUS[2], ''), ("13+", BUS[3], ''), ("Metrobüs", '#e2231a', ''),
            ("Minibüs", MINI[1], ''), ("Taksi-dolmuş", DOLMUS, ' stroke-dasharray="8 4"')]
    for i, (lab, col, dash) in enumerate(KEYS):
        x = 42 + i * 190
        svg.append(f'<line x1="{x}" y1="134" x2="{x + 50}" y2="134" stroke="{col}" stroke-width="9" stroke-linecap="round"{dash}/>'
                   f'<text x="{x + 60}" y="140" font-size="17" fill="#222">{lab}</text>')
    svg.append('</svg>')
    stats['failed'] = failed[:12]
    if moved_px:   # how far stops ended up from where they are, in metres
        mm = sorted(v / SCALE * GRID * 1000 for v in moved_px)
        stats['moved'] = (mm[len(mm) // 2], mm[int(len(mm) * 0.95)], mm[-1])
    stats.update(W=round(W), H=round(H), labels=len(stop_spots) + len(key), lines=len(all_lines), n_mini=n_mini, n_dol=n_dol)
    return "\n".join(svg), stats

scale = SCALE
while True:
    text, st = draw(scale)
    print(f"  scale {scale:.1f}: {st['W']}x{st['H']}px, names without room {st['no_room']} {st['failed'][:4]}, "
          f"far {st['far']}, lines unnamed {st['unnamed_lines']}", flush=True)
    if not st['no_room'] and not st['unnamed_lines']:
        break
    scale *= GROW
open(OUT, 'w').write(text)
if WARP == 'elastic' and not TRUE:
    _nn = []
    _keyset = sorted(key)
    _cells = collections.defaultdict(list)
    for g in _keyset: _cells[(grid[g][0] // 4, grid[g][1] // 4)].append(g)
    for g in _keyset:
        cx, cy = grid[g][0] // 4, grid[g][1] // 4
        _nn.append(min((math.dist(grid[g], grid[h]) for i in (-1, 0, 1) for j in (-1, 0, 1)
                        for h in _cells.get((cx + i, cy + j), ()) if h != g), default=99))
    _nn.sort()
    print(f"cartogram: {_sheet.folded} folded cells; grid step {GRID * 1000:.0f} m of stretched map; places' nearest neighbour: "
          f"median {_nn[len(_nn) // 2]:.1f} steps, {sum(1 for d in _nn if d < 2) * 100 / len(_nn):.0f} % closer than 2 steps")
if TRUE:
    where = ("every one where it really is, lines stop to stop" if MODE == 'geographic' else
             "lines straightened to 0/45/90° along their roads; stops off their real place by a median {:.0f} m, 95 % within {:.0f} m, "
             "at most {:.0f} m".format(*st['moved']))
    print(f"{n_iett} İETT + {st['n_mini']} minibüs + {st['n_dol']} dolmuş lines; {len(adj)} stops, {where}; {st['W']}x{st['H']}px ({scale / GRID:.0f} px a km); {st['labels']} names, none overlapping "
          f"({st['leader']} with a leader line); all {st['lines']} lines named -> {OUT}")
else:
    print(f"{n_iett} İETT + {st['n_mini']} minibüs + {st['n_dol']} dolmuş lines; {len(adj)} stops, {len(key)} key places "
          f"({passes - 1} splitting passes against squishing), {len(corridors)} corridors, every stop at least {squish:.2f} grid steps "
          f"from the next; places moved from where they are: median {moved['median'] * 1000:.0f} m, 95 % within "
          f"{moved['p95'] * 1000:.0f} m, at most {moved['max'] * 1000:.0f} m; {st['W']}x{st['H']}px at {scale:.1f} px a step; {st['labels']} names, none overlapping "
          f"({st['leader']} with a leader line); all {st['lines']} lines named -> {OUT}")
