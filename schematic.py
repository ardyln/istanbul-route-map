"""Schematic Istanbul route map: every İETT bus line, the Metrobüs, minibüs and taksi-dolmuş lines,
every stop named. Octilinear corridors, route numbers along them. Writes an SVG.

Data (in data/): hat.json and durak.json from İBB's HatDurakGuzergah service (all İETT lines; all stops with
coordinates), lines/*.json from fetch_orders.py (each İETT line's stop order), dolmus.json from
dolmus_compile.py (minibüs and taksi-dolmuş routes with their stops in order).
"""
import json, glob, math, re, collections, html, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/iett-route-map.svg')
R0 = float(os.environ.get('R0', 5.0))          # km; distances beyond this are squeezed logarithmically
STRETCH = float(os.environ.get('STRETCH', 2.2))
GRID = float(os.environ.get('GRID', 0.12))      # warped km per grid step
SCALE = float(os.environ.get('SCALE', 36))      # px per grid step
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

LAT0, LON0 = 41.035, 29.01
def warp(lat, lon):
    x = (lon - LON0) * 111.32 * math.cos(math.radians(LAT0))
    y = (LAT0 - lat) * 110.57
    r = math.hypot(x, y)
    if r == 0: return 0.0, 0.0
    s = R0 * math.log1p(r / R0) * STRETCH / r
    return x * s, y * s
for a, b, chain in chains():
    pts = [warp(*pos[g]) for g in [a] + chain + [b]]
    for i in bends([(x / GRID, y / GRID) for x, y in pts], 2.5):
        key.add(([a] + chain + [b])[i])
corridors = [(a, b, chain, edge_lines[tuple(sorted((a, (chain or [b])[0])))]) for a, b, chain in chains()]

taken, grid = {}, {}
for g in sorted(key, key=lambda g: (-len(serves[g]), g)):
    x, y = warp(*pos[g])
    gx, gy = round(x / GRID), round(y / GRID)
    best = None
    for rad in range(0, 12):
        cells = [(gx + dx, gy + dy) for dx in range(-rad, rad + 1) for dy in range(-rad, rad + 1)
                 if max(abs(dx), abs(dy)) == rad and (gx + dx, gy + dy) not in taken]
        if cells:
            best = min(cells, key=lambda c: (c[0] - x / GRID) ** 2 + (c[1] - y / GRID) ** 2); break
    best = best or (gx, gy)
    taken[best] = g; grid[g] = best
xs = [c[0] for c in grid.values()]; ys = [c[1] for c in grid.values()]
X0, Y0 = min(xs) - 10, min(ys) - 12
W, H = (max(xs) - X0 + 10) * SCALE, (max(ys) - Y0 + 8) * SCALE
P = lambda c: ((c[0] - X0) * SCALE, (c[1] - Y0) * SCALE)

def octi(a, b, via):
    (x1, y1), (x2, y2) = a, b
    dx, dy = x2 - x1, y2 - y1
    d = min(abs(dx), abs(dy))
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    options = ((x1 + sx * d, y1 + sy * d), (x2 - sx * d, y2 - sy * d))
    return [a, min(options, key=lambda p: (p[0] - via[0]) ** 2 + (p[1] - via[1]) ** 2), b]
def along(path, frac):
    """Point and unit direction at `frac` of a path's length (in px)."""
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
def tag_text(l):
    mode, line = l
    return line
order = lambda l: ({'metrobus': 0, 'bus': 1, 'dolmus': 2, 'minibus': 3}[l[0]],
                   re.sub(r'\D.*', '', l[1]).zfill(4) if re.match(r'\d', l[1]) else 'z' + l[1], l[1])

# -- label placement: rotated rectangles, separating-axis overlap test, spatial hash ----------------------
CELL = 48
occupied = collections.defaultdict(list)
def rect(px, py, w, h, ang):
    """Corners of a text box: baseline start (px, py), width w, height h, rotated by ang degrees."""
    ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    vx, vy = uy, -ux                       # "up" for the text
    b0 = (px - vx * h * 0.25, py - vy * h * 0.25)
    return [b0, (b0[0] + ux * w, b0[1] + uy * w), (b0[0] + ux * w + vx * h, b0[1] + uy * w + vy * h), (b0[0] + vx * h, b0[1] + vy * h)]
def axes(c):
    return [(c[1][0] - c[0][0], c[1][1] - c[0][1]), (c[3][0] - c[0][0], c[3][1] - c[0][1])]
def overlap(a, b):
    for ax in axes(a) + axes(b):
        pa = [p[0] * ax[0] + p[1] * ax[1] for p in a]; pb = [p[0] * ax[0] + p[1] * ax[1] for p in b]
        if max(pa) <= min(pb) or max(pb) <= min(pa): return False
    return True
def cells_of(c):
    xs_, ys_ = [p[0] for p in c], [p[1] for p in c]
    return [(i, j) for i in range(int(min(xs_) // CELL), int(max(xs_) // CELL) + 1)
            for j in range(int(min(ys_) // CELL), int(max(ys_) // CELL) + 1)]
def hits(c):
    seen = set(); n = 0
    for cell in cells_of(c):
        for k, other in occupied[cell]:
            if k not in seen and overlap(c, other):
                seen.add(k); n += 1
    return n
_nid = [0]
def occupy(c):
    _nid[0] += 1
    for cell in cells_of(c): occupied[cell].append((_nid[0], c))
def text_w(t, fs): return len(t) * fs * 0.56 + 1

svg_lines, svg_dots, svg_labels = [], [], []
stats = collections.Counter()
def place_label(x, y, text, fs, cands, weight=400, fill='#111'):
    """cands: [(dx, dy, angle, anchor 'start'|'end')] offsets from the dot; first free wins, then further out."""
    w, h = text_w(text, fs), fs * 1.15
    best = None
    for ring in (1.0, 2.0, 3.2):
        for dx, dy, ang, anchor in cands:
            px, py = x + dx * ring, y + dy * ring
            if anchor == 'end':
                px -= math.cos(math.radians(ang)) * w; py -= math.sin(math.radians(ang)) * w
            c = rect(px, py, w, h, ang)
            n = hits(c)
            if best is None or n < best[0]: best = (n, px, py, ang, c, ring)
            if n == 0: break
        if best[0] == 0: break
    n, px, py, ang, c, ring = best
    stats['labels'] += 1
    if n: stats['crowded'] += 1
    if ring > 1: stats['leader'] += 1
    occupy(c)
    if ring > 1:   # a short leader line from the dot to a label moved out
        mx, my = (c[0][0] + c[3][0]) / 2, (c[0][1] + c[3][1]) / 2
        svg_labels.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{mx:.1f}" y2="{my:.1f}" stroke="#888" stroke-width="0.4"/>')
    rot = f' transform="rotate({ang:.0f} {px:.1f} {py:.1f})"' if ang else ''
    svg_labels.append(f'<text x="{px:.1f}" y="{py:.1f}" font-size="{fs}" font-weight="{weight}" fill="{fill}"{rot} '
                      f'stroke="#fbfaf7" stroke-width="{fs * 0.32:.1f}" paint-order="stroke">{html.escape(text)}</text>')

def stop_cands(d, r):
    """Label spots for a stop on a corridor going in direction d (unit vector, screen coords)."""
    o = r + 2
    if abs(d[1]) < 0.2:                       # horizontal: names at 45°, above or below
        return [(o * 0.5, -o, -45, 'start'), (-o * 0.5, o, -45, 'end'), (o * 0.5, -o, -60, 'start'), (-o * 0.5, o, -60, 'end')]
    if abs(d[0]) < 0.2:                       # vertical: names level, right or left
        return [(o, FS_STOP * 0.35, 0, 'start'), (-o, FS_STOP * 0.35, 0, 'end'), (o, 0, -20, 'start'), (-o, FS_STOP * 0.7, 20, 'end')]
    perp = -45 if d[0] * d[1] > 0 else 45     # diagonal: across the line, or level beside it
    return [(o, FS_STOP * 0.35, 0, 'start'), (-o, FS_STOP * 0.35, 0, 'end'),
            (o * 0.7, -o * 0.7 if perp == -45 else o * 0.7, perp, 'start'), (-o * 0.7, o * 0.7 if perp == -45 else -o * 0.7, perp, 'end')]
def key_cands(r, fs):
    o = r + 2
    return [(o, fs * 0.35, 0, 'start'), (-o, fs * 0.35, 0, 'end'), (-text_w('x', fs), -o, 0, 'start'), (o * 0.7, -o * 0.7, -45, 'start'),
            (-o * 0.7, o * 0.7, -45, 'end'), (o * 0.7, o * 0.7 + fs, 0, 'start'), (-o * 0.7, -o * 0.7, 0, 'end'), (0, o + fs, 0, 'start')]

# -- draw ---------------------------------------------------------------------------------------------------
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" viewBox="0 0 {W:.0f} {H:.0f}" '
       'font-family="Inter, Roboto, Helvetica, Arial, sans-serif">', f'<rect width="{W:.0f}" height="{H:.0f}" fill="#fbfaf7"/>']
BOSPHORUS = [(41.235, 29.115), (41.205, 29.085), (41.175, 29.07), (41.14, 29.075), (41.115, 29.07), (41.09, 29.065),
             (41.075, 29.055), (41.06, 29.045), (41.045, 29.033), (41.035, 29.012), (41.025, 29.0), (41.01, 29.0), (40.99, 29.0)]
HORN = [(41.052, 28.935), (41.042, 28.944), (41.035, 28.951), (41.028, 28.961), (41.022, 28.972), (41.018, 28.982)]
for pts, w in ((BOSPHORUS, 40), (HORN, 22)):
    d = " ".join(f"{(warp(*p)[0] / GRID - X0) * SCALE:.0f},{(warp(*p)[1] / GRID - Y0) * SCALE:.0f}" for p in pts)
    svg.append(f'<polyline points="{d}" fill="none" stroke="#cfe3f2" stroke-width="{w}" stroke-linejoin="round" stroke-linecap="round"/>')

corridor_draw, stop_spots = [], []
for a, b, chain, ls in sorted(corridors, key=lambda c: (len(c[3]), c[0], c[1])):
    via_real = pos[chain[len(chain) // 2]] if chain else ((pos[a][0] + pos[b][0]) / 2, (pos[a][1] + pos[b][1]) / 2)
    vx, vy = warp(*via_real)
    path = octi(grid[a], grid[b], (vx / GRID, vy / GRID))
    w = min(1.8 + len(ls) * 0.4, 11)
    col = colour(ls)
    dash = ' stroke-dasharray="5 2.5"' if {m for m, _ in ls} == {'dolmus'} else ''
    svg_lines.append(f'<polyline points="{" ".join(f"{P(p)[0]:.0f},{P(p)[1]:.0f}" for p in path)}" fill="none" stroke="{col}" '
                     f'stroke-width="{w:.1f}" stroke-linejoin="round" stroke-linecap="round"{dash}/>')
    for i, g in enumerate(chain):
        (x, y), d = along(path, (i + 1) / (len(chain) + 1))
        r = max(1.5, w / 2.6)
        svg_dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#fff" stroke="{col}" stroke-width="0.9"/>')
        stop_spots.append((g, x, y, d, r))
    corridor_draw.append((ls, path, col))
for g in sorted(key):
    x, y = P(grid[g])
    n = len(serves[g])
    r = 2.6 + min(n, 30) * 0.12
    fill = '#e2231a' if is_mb(g) else '#fff'
    svg_dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" stroke="#111" stroke-width="1.1"/>')
# names: every place. Dots and lines block nothing; names keep clear of each other and of route tags.
for g in sorted(key, key=lambda g: (-len(serves[g]), g)):
    x, y = P(grid[g]); n = len(serves[g])
    fs = FS_HUB if n >= 10 else FS_KEY
    place_label(x, y, name[g], fs, key_cands(2.6 + min(n, 30) * 0.12, fs), weight=600 if n >= 10 else 500)
for g, x, y, d, r in stop_spots:
    place_label(x, y, name[g], FS_STOP, stop_cands(d, r))
# route numbers along corridors, where there's room; then every line still unnamed gets one somewhere
tags, shown = [], set()
def put_tag(x, y, nums, col, force=False):
    items = [tag_text(l) for l in nums]
    rows = [" ".join(items[i:i + 8]) for i in range(0, len(items), 8)][:6]
    if len(items) > 48: rows[-1] += f" +{len(items) - 48}"
    fs = 6.4
    tw = max(len(r) for r in rows) * fs * 0.6 + 5; th = len(rows) * fs * 1.2 + 3
    c = [(x - tw / 2, y - th / 2), (x + tw / 2, y - th / 2), (x + tw / 2, y + th / 2), (x - tw / 2, y + th / 2)]
    if hits(c) and not force: return False
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
    for frac in (0.5, 0.3, 0.7, 0.15, 0.85):
        (x, y), d = along(path, frac)
        for ox, oy in ((0, 0), (-d[1] * 9, d[0] * 9), (d[1] * 9, -d[0] * 9), (-d[1] * 16, d[0] * 16), (d[1] * 16, -d[0] * 16)):
            if put_tag(x + ox, y + oy, left, col): done = True; break
        if done: break
for ls, path, col in corridor_draw:      # last resort: a line with no free spot anywhere still gets named
    left = [l for l in sorted(ls, key=order) if l not in shown]
    if left:
        (x, y), _ = along(path, 0.5); put_tag(x, y, left, col, force=True); stats['forced_tags'] += 1

svg += svg_lines + svg_dots + tags + svg_labels
# title and key
n_mini = len({l for l in all_lines if l[0] == 'minibus'}); n_dol = len({l for l in all_lines if l[0] == 'dolmus'})
svg.append(f'<text x="40" y="70" font-size="52" font-weight="700" fill="#111">Istanbul buses, minibüs and dolmuş</text>'
           f'<text x="40" y="104" font-size="20" fill="#444">{n_iett} İETT lines (incl. Metrobüs) · {n_mini} minibüs lines · {n_dol} taksi-dolmuş lines · '
           f'{len(adj)} stops, every one named · schematic, not to scale, centre enlarged · data: İBB open data and İETT, 9 November 2026</text>')
KEYS = [("İETT bus, 1–2 lines", BUS[0], ''), ("3–5", BUS[1], ''), ("6–12", BUS[2], ''), ("13+", BUS[3], ''), ("Metrobüs", '#e2231a', ''),
        ("Minibüs", MINI[1], ''), ("Taksi-dolmuş", DOLMUS, ' stroke-dasharray="8 4"')]
for i, (lab, col, dash) in enumerate(KEYS):
    x = 42 + i * 190
    svg.append(f'<line x1="{x}" y1="134" x2="{x + 50}" y2="134" stroke="{col}" stroke-width="9" stroke-linecap="round"{dash}/>'
               f'<text x="{x + 60}" y="140" font-size="17" fill="#222">{lab}</text>')
svg.append('</svg>')
open(OUT, 'w').write("\n".join(svg))
print(f"{n_iett} İETT + {n_mini} minibüs + {n_dol} dolmuş lines; {len(adj)} stops, {len(key)} key places, {len(corridors)} corridors; "
      f"{W:.0f}x{H:.0f}px; labels {stats['labels']} (crowded {stats['crowded']}, with leader {stats['leader']}); "
      f"lines named {len(shown & all_lines)}/{len(all_lines)} (forced {stats['forced_tags']}) -> {OUT}")
