// Layout worker for the Istanbul route map viewer: the same rules as schematic.py, run in the browser.
// In: {params: {squish 0..1, snap 0..10, coast 'real'|'straight', minibus, dolmus}} after {data}.
// Out: everything to draw, in layout px (km × pxkm), plus figures for the panel.
'use strict';
let D = null, meshFrames = null;
const FS_STOP = 5.5, FS_KEY = 7, FS_HUB = 9.5, FS_TAG = 6.4, PAD = 0.5;
const FONT = 'Inter, Roboto, Helvetica, Arial, sans-serif';
const measureCtx = new OffscreenCanvas(8, 8).getContext('2d');
const widths = new Map();
function measure(text, fs, weight) {
  const k = weight + '|' + text;
  let m = widths.get(k);
  if (!m) {   // at 100 px, scaled: one measurement per text whatever the size
    measureCtx.font = `${weight} 100px ${FONT}`;
    const t = measureCtx.measureText(text);
    m = { w: t.width / 100, a: Math.max(t.actualBoundingBoxAscent, 72) / 100, d: Math.max(t.actualBoundingBoxDescent, 18) / 100 };
    widths.set(k, m);
  }
  return { w: m.w * fs + 1, a: m.a * fs, d: m.d * fs };
}

onmessage = (e) => {
  if (e.data.data) {
    D = e.data.data;
    meshFrames = D.mesh.frames.map((b64) => {
      const bin = atob(b64), buf = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
      return new Float32Array(buf.buffer);
    });
    D.lineMode = D.lines.map((l) => l[0]);
  }
  if (e.data.params) {
    const t0 = performance.now();
    const out = layout(e.data.params);
    out.stats.ms = Math.round(performance.now() - t0);
    postMessage(out);
  }
};

// -- the stretch: the cartogram's flow, partly done -------------------------------------------------------
function warper(squish) {
  const M = D.mesh, nx = M.nx, ny = M.ny, f = squish * (meshFrames.length - 1);
  const a = Math.floor(f), b = Math.min(a + 1, meshFrames.length - 1), w = f - a;
  const A = meshFrames[a], B = meshFrames[b];
  const vx = (i, j) => { const k = (i * nx + j) * 2; return A[k] * (1 - w) + B[k] * w; };
  const vy = (i, j) => { const k = (i * nx + j) * 2 + 1; return A[k] * (1 - w) + B[k] * w; };
  return (x, y) => {
    const fx = (x - M.x0) / M.step, fy = (y - M.y0) / M.step;
    const j = Math.min(Math.max(Math.floor(fx), 0), nx - 2), i = Math.min(Math.max(Math.floor(fy), 0), ny - 2);
    const tx = fx - j, ty = fy - i;
    return [vx(i, j) * (1 - tx) * (1 - ty) + vx(i, j + 1) * tx * (1 - ty) + vx(i + 1, j) * (1 - tx) * ty + vx(i + 1, j + 1) * tx * ty,
            vy(i, j) * (1 - tx) * (1 - ty) + vy(i, j + 1) * tx * (1 - ty) + vy(i + 1, j) * (1 - tx) * ty + vy(i + 1, j + 1) * tx * ty];
  };
}

// -- geometry helpers ------------------------------------------------------------------------------------
const dist = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1]);
function dpKeep(pts, eps) {   // Douglas–Peucker: kept indices, ends included
  const keep = new Set([0, pts.length - 1]), stack = [[0, pts.length - 1]];
  while (stack.length) {
    const [i, j] = stack.pop();
    const [x1, y1] = pts[i], [x2, y2] = pts[j];
    const L = Math.hypot(x2 - x1, y2 - y1) || 1e-9;
    let best = 0, k = -1;
    for (let m = i + 1; m < j; m++) {
      const d = Math.abs((x2 - x1) * (y1 - pts[m][1]) - (x1 - pts[m][0]) * (y2 - y1)) / L;
      if (d > best) { best = d; k = m; }
    }
    if (k >= 0 && best > eps) { keep.add(k); stack.push([i, k], [k, j]); }
  }
  return [...keep].sort((a, b) => a - b);
}
function octi(a, b, via) {   // a to b at 0/45/90°, one bend, on the side nearer via
  const dx = b[0] - a[0], dy = b[1] - a[1], d = Math.min(Math.abs(dx), Math.abs(dy));
  const sx = Math.sign(dx), sy = Math.sign(dy);
  const o1 = [a[0] + sx * d, a[1] + sy * d], o2 = [b[0] - sx * d, b[1] - sy * d];
  return [a, dist(o1, via) <= dist(o2, via) ? o1 : o2, b];
}
function pieces(pts, idx, piece) {   // cut long stretches between kept points into pieces of at most `piece`
  const cut = [idx[0]];
  for (let n = 0; n + 1 < idx.length; n++) {
    let run = 0;
    for (let m = idx[n] + 1; m < idx[n + 1]; m++) {
      run += dist(pts[m - 1], pts[m]);
      if (run >= piece) { cut.push(m); run = 0; }
    }
    cut.push(idx[n + 1]);
  }
  return cut;
}
function closest(path, q) {
  let best = Infinity, at = 0, run = 0;
  for (let k = 0; k + 1 < path.length; k++) {
    const p0 = path[k], p1 = path[k + 1], L = dist(p0, p1);
    if (!L) continue;
    const u = Math.max(0, Math.min(1, ((q[0] - p0[0]) * (p1[0] - p0[0]) + (q[1] - p0[1]) * (p1[1] - p0[1])) / (L * L)));
    const d = Math.hypot(p0[0] + u * (p1[0] - p0[0]) - q[0], p0[1] + u * (p1[1] - p0[1]) - q[1]);
    if (d < best) { best = d; at = run + u * L; }
    run += L;
  }
  return [at, run];
}
function along(path, frac) {   // point and unit direction at frac of a path's length
  let total = 0;
  for (let k = 0; k + 1 < path.length; k++) total += dist(path[k], path[k + 1]);
  let t = frac * (total || 1);
  for (let k = 0; k + 1 < path.length; k++) {
    const p = path[k], q = path[k + 1], s = dist(p, q);
    if (s > 0 && t <= s) return [[p[0] + (q[0] - p[0]) * t / s, p[1] + (q[1] - p[1]) * t / s], [(q[0] - p[0]) / s, (q[1] - p[1]) / s]];
    t -= s;
  }
  for (let k = path.length - 1; k > 0; k--) {
    const s = dist(path[k - 1], path[k]);
    if (s > 0) return [path[path.length - 1], [(path[k][0] - path[k - 1][0]) / s, (path[k][1] - path[k - 1][1]) / s]];
  }
  return [path[path.length - 1], [1, 0]];
}

// -- colours ----------------------------------------------------------------------------------------------
const BUS = ['#9ec5e8', '#5a9bd4', '#2f6fb3', '#163f7a'], MINI = ['#9fd8b4', '#4fb878', '#23864b', '#145c32'];
function colour(ls) {
  const modes = new Set(ls.map((l) => D.lineMode[l])), n = ls.length;
  const shade = n <= 2 ? 0 : n <= 5 ? 1 : n <= 12 ? 2 : 3;
  if (modes.size === 1 && modes.has('metrobus')) return '#e2231a';
  if ([...modes].every((m) => m === 'minibus')) return MINI[shade];
  if ([...modes].every((m) => m === 'dolmus')) return '#f08c1e';
  return BUS[shade];
}
const modeOrder = { metrobus: 0, bus: 1, dolmus: 2, minibus: 3 };
function lineOrder(a, b) {
  const la = D.lines[a], lb = D.lines[b];
  if (modeOrder[la[0]] !== modeOrder[lb[0]]) return modeOrder[la[0]] - modeOrder[lb[0]];
  const na = parseInt(la[1], 10), nb = parseInt(lb[1], 10);
  if (!isNaN(na) && !isNaN(nb) && na !== nb) return na - nb;
  if (isNaN(na) !== isNaN(nb)) return isNaN(na) ? 1 : -1;
  return la[1] < lb[1] ? -1 : la[1] > lb[1] ? 1 : 0;
}

// -- text boxes: rotated rectangles, separating axes, spatial hash -------------------------------------
function rect(px, py, m, ang) {
  const u = [Math.cos(ang * Math.PI / 180), Math.sin(ang * Math.PI / 180)], v = [u[1], -u[0]];
  const l = -PAD, r = m.w + PAD, bot = -(m.d + PAD), top = m.a + PAD;
  const c = (s, t) => [px + u[0] * s + v[0] * t, py + u[1] * s + v[1] * t];
  return [c(l, bot), c(r, bot), c(r, top), c(l, top)];
}
const box = (x0, y0, x1, y1) => [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
function overlap(A, B) {
  for (const [p, q] of [[A[0], A[1]], [A[0], A[3]], [B[0], B[1]], [B[0], B[3]]]) {
    const ax = q[0] - p[0], ay = q[1] - p[1];
    let amin = Infinity, amax = -Infinity, bmin = Infinity, bmax = -Infinity;
    for (const [x, y] of A) { const s = x * ax + y * ay; amin = Math.min(amin, s); amax = Math.max(amax, s); }
    for (const [x, y] of B) { const s = x * ax + y * ay; bmin = Math.min(bmin, s); bmax = Math.max(bmax, s); }
    if (amax <= bmin || bmax <= amin) return false;
  }
  return true;
}
class Hash {
  constructor() { this.cells = new Map(); }
  keys(c) {
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const [x, y] of c) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
    const out = [];
    for (let i = Math.floor(x0 / 48); i <= Math.floor(x1 / 48); i++) for (let j = Math.floor(y0 / 48); j <= Math.floor(y1 / 48); j++) out.push(i + ',' + j);
    return out;
  }
  free(c) {
    for (const k of this.keys(c)) for (const o of this.cells.get(k) || []) if (overlap(c, o)) return false;
    return true;
  }
  add(c) { for (const k of this.keys(c)) { if (!this.cells.has(k)) this.cells.set(k, []); this.cells.get(k).push(c); } }
}

// -- the layout -------------------------------------------------------------------------------------------
function layout(p) {
  const warp = warper(p.squish);
  const P = D.places, n = P.length;
  const visible = (l) => (D.lineMode[l] !== 'minibus' || p.minibus) && (D.lineMode[l] !== 'dolmus' || p.dolmus);
  const corridors = [];
  const serves = Array.from({ length: n }, () => new Set());
  for (const [a, b, chain, ls0] of D.corridors) {
    const ls = ls0.filter(visible);
    if (!ls.length) continue;
    corridors.push([a, b, chain, ls]);
    for (const g of [a, b, ...chain]) for (const l of ls) serves[g].add(l);
  }
  const used = new Uint8Array(n);
  for (const [a, b, chain] of corridors) { used[a] = used[b] = 1; for (const c of chain) used[c] = 1; }
  const real = P.map((pl) => warp(pl[1], pl[2]));          // km on the (partly) stretched map
  const isKey = (g) => (P[g][4] & 2) !== 0;
  const snap = p.snap;
  const at = real.slice();
  let moved = [];
  // junctions on a grid: snap level 5 is 100 m; each takes a free grid point near where it is
  const G = snap > 0 ? 0.02 * snap : 0;
  if (G) {
    const taken = new Set();
    const keys = [];
    for (let g = 0; g < n; g++) if (used[g] && isKey(g)) keys.push(g);
    keys.sort((a, b) => serves[b].size - serves[a].size || a - b);
    for (const g of keys) {
      const [x, y] = real[g], gx = Math.round(x / G), gy = Math.round(y / G);
      let best = null;
      for (let rad = 0; rad < 30 && !best; rad++) {
        let bd = Infinity;
        for (let dx = -rad; dx <= rad; dx++) for (let dy = -rad; dy <= rad; dy++) {
          if (Math.max(Math.abs(dx), Math.abs(dy)) !== rad || taken.has((gx + dx) + ',' + (gy + dy))) continue;
          const d = (gx + dx - x / G) ** 2 + (gy + dy - y / G) ** 2;
          if (d < bd) { bd = d; best = [gx + dx, gy + dy]; }
        }
      }
      taken.add(best[0] + ',' + best[1]);
      at[g] = [best[0] * G, best[1] * G];
    }
  }
  // paths (km): stop to stop, or the real path smoothed, cut into pieces and straightened
  const eps = 0.03 * snap, piece = 0.12 * snap;
  const paths = corridors.map(([a, b, chain]) => {
    const pts = [at[a], ...chain.map((c) => real[c]), at[b]];
    if (!G) return pts;
    const cut = pieces(pts, dpKeep(pts, eps), piece);
    const anchors = cut.map((m, k) => (k === 0 || k === cut.length - 1) ? pts[m] : [Math.round(pts[m][0] / G) * G, Math.round(pts[m][1] / G) * G]);
    const out = [anchors[0]];
    for (let k = 0; k + 1 < cut.length; k++) {
      const pa = anchors[k], pb = anchors[k + 1];
      if (pa[0] === pb[0] && pa[1] === pb[1]) continue;
      for (const q of octi(pa, pb, pts[(cut[k] + cut[k + 1]) >> 1]).slice(1)) {
        const last = out[out.length - 1];
        if (q[0] !== last[0] || q[1] !== last[1]) out.push(q);
      }
    }
    return out.length > 1 ? out : [at[a], at[b]];
  });

  // shores (km)
  const coast = (ring) => {
    const pts = ring.map(([x, y]) => warp(x, y));
    if (p.coast !== 'straight' || !G) return pts;
    const Gc = Math.max(G, 0.1);
    const cut = pieces(pts, dpKeep(pts, 1.5 * Gc), 6 * Gc);
    const out = [];
    for (let k = 0; k + 1 < cut.length; k++) {
      const pa = [Math.round(pts[cut[k]][0] / Gc) * Gc, Math.round(pts[cut[k]][1] / Gc) * Gc];
      const pb = [Math.round(pts[cut[k + 1]][0] / Gc) * Gc, Math.round(pts[cut[k + 1]][1] / Gc) * Gc];
      if (pa[0] === pb[0] && pa[1] === pb[1]) continue;
      for (const q of octi(pa, pb, pts[(cut[k] + cut[k + 1]) >> 1]).slice(0, 2)) out.push(q);
    }
    return out.length > 2 ? out : pts;
  };
  const landKm = D.land.map(coast), lakesKm = D.lakes.map(([outer, inner]) => [...outer, ...inner].map(coast));

  // extent
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let g = 0; g < n; g++) if (used[g]) { x0 = Math.min(x0, at[g][0]); x1 = Math.max(x1, at[g][0]); y0 = Math.min(y0, at[g][1]); y1 = Math.max(y1, at[g][1]); }
  x0 -= 3; y0 -= 3; x1 += 3; y1 += 3;

  // drawing in px; names placed without overlap, the map growing if a name or line has no room
  let pxkm = p.pxkm || 180;
  for (let attempt = 0; attempt < 8; attempt++) {
    const res = draw(pxkm);
    if ((!res.stats.noRoom && !res.stats.unnamed) || attempt === 7) {
      if (G) res.stats.moved = moved;
      return res;
    }
    pxkm *= 1.15;
  }

  function draw(pxkm) {
    const X = (q) => [(q[0] - x0) * pxkm, (q[1] - y0) * pxkm];
    const hash = new Hash();
    const lines = [], dots = [], keys = [], labels = [], tags = [], leaders = [];
    const stats = { noRoom: 0, unnamed: 0, leaders: 0, W: Math.round((x1 - x0) * pxkm), H: Math.round((y1 - y0) * pxkm), pxkm };
    moved = [];
    const stopSpots = [];
    const order = corridors.map((c, i) => i).sort((i, j) => corridors[i][3].length - corridors[j][3].length);
    for (const ci of order) {
      const [a, b, chain, ls] = corridors[ci];
      const path = paths[ci].map(X);
      const w = Math.min(1.8 + ls.length * 0.4, 11), col = colour(ls);
      const dash = ls.every((l) => D.lineMode[l] === 'dolmus');
      lines.push({ pts: path, w, col, dash, ls, i: ci });
      let fracs = null;
      if (G && chain.length) {
        const ats = chain.map((c) => closest(paths[ci], real[c]));
        const total = ats[0][1] || 1, gap = Math.min(0.08, total / (chain.length + 1));
        fracs = []; let last = 0;
        ats.forEach(([a1], k) => { const v = Math.min(Math.max(a1, last + gap), total - gap * (chain.length - k)); fracs.push(v / total); last = v; });
      }
      chain.forEach((g, i) => {
        let pt, d;
        if (fracs) {
          [pt, d] = along(path, fracs[i]);
          moved.push(Math.hypot(pt[0] / pxkm + x0 - real[g][0], pt[1] / pxkm + y0 - real[g][1]) * 1000);
        } else {
          pt = path[i + 1];
          const pr = path[i], nx = path[i + 2], L = Math.hypot(nx[0] - pr[0], nx[1] - pr[1]) || 1;
          d = [(nx[0] - pr[0]) / L, (nx[1] - pr[1]) / L];
        }
        const r = Math.max(1.5, w / 2.6);
        dots.push({ x: pt[0], y: pt[1], r, col, g });
        hash.add(box(pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r));
        stopSpots.push([g, pt, d, r]);
      });
    }
    const keyList = [];
    for (let g = 0; g < n; g++) if (used[g] && isKey(g)) keyList.push(g);
    for (const g of keyList) {
      const [x, y] = X(at[g]), r = 2.6 + Math.min(serves[g].size, 30) * 0.12;
      keys.push({ x, y, r, mb: (P[g][4] & 1) !== 0, g });
      hash.add(box(x - r, y - r, x + r, y + r));
    }
    function place(x, y, text, fs, weight, cands, g) {
      const m = measure(text, fs, weight);
      for (const ring of [1, 1.8, 2.8, 4, 5.5, 7.5]) {
        for (const [dx, dy, ang, anchor] of cands) {
          let px = x + dx * ring, py = y + dy * ring;
          if (anchor === 'end') { px -= Math.cos(ang * Math.PI / 180) * m.w; py -= Math.sin(ang * Math.PI / 180) * m.w; }
          const c = rect(px, py, m, ang);
          if (hash.free(c)) {
            hash.add(c);
            if (ring > 1) { leaders.push([x, y, (c[0][0] + c[3][0]) / 2, (c[0][1] + c[3][1]) / 2]); stats.leaders++; }
            labels.push({ x: px, y: py, ang, text, fs, weight, g });
            return;
          }
        }
      }
      for (let rad = 3 * fs; rad < 40 * fs; rad += 1.5 * fs) {
        for (let k = 0; k < 16; k++) {
          const a = 2 * Math.PI * k / 16;
          let px = x + Math.cos(a) * rad, py = y + Math.sin(a) * rad;
          const left = Math.cos(a) < -0.3;
          if (left) px -= m.w;
          const c = rect(px, py, m, 0);
          if (hash.free(c)) {
            hash.add(c);
            leaders.push([x, y, left ? c[1][0] : c[0][0], (c[0][1] + c[3][1]) / 2]); stats.leaders++;
            labels.push({ x: px, y: py, ang: 0, text, fs, weight, g });
            return;
          }
        }
      }
      stats.noRoom++;
    }
    const stopCands = (d, r) => {
      const o = r + 2;
      if (Math.abs(d[1]) < 0.2) return [[o * 0.5, -o, -45, 'start'], [-o * 0.5, o, -45, 'end'], [o * 0.5, -o, -60, 'start'], [-o * 0.5, o, -60, 'end'], [o * 0.3, -o, -90, 'start'], [-o * 0.3, o, -90, 'end']];
      if (Math.abs(d[0]) < 0.2) return [[o, FS_STOP * 0.35, 0, 'start'], [-o, FS_STOP * 0.35, 0, 'end'], [o, 0, -20, 'start'], [-o, FS_STOP * 0.7, 20, 'end'], [o, -FS_STOP * 0.4, -35, 'start'], [-o, FS_STOP, 35, 'end']];
      const perp = d[0] * d[1] > 0 ? -45 : 45;
      return [[o, FS_STOP * 0.35, 0, 'start'], [-o, FS_STOP * 0.35, 0, 'end'], [o * 0.7, perp === -45 ? -o * 0.7 : o * 0.7, perp, 'start'], [-o * 0.7, perp === -45 ? o * 0.7 : -o * 0.7, perp, 'end']];
    };
    const keyCands = (r, fs) => {
      const o = r + 2;
      return [[o, fs * 0.35, 0, 'start'], [-o, fs * 0.35, 0, 'end'], [o * 0.7, -o * 0.7, -45, 'start'], [-o * 0.7, o * 0.7, -45, 'end'], [o * 0.7, o * 0.7 + fs, 0, 'start'], [-o * 0.7, -o * 0.7, 0, 'end'], [0, -o, 0, 'start'], [0, o + fs, 0, 'start']];
    };
    for (const k of [...keys].sort((a, b) => serves[b.g].size - serves[a.g].size || a.g - b.g)) {
      const hub = serves[k.g].size >= 10, fs = hub ? FS_HUB : FS_KEY;
      place(k.x, k.y, P[k.g][0], fs, hub ? 600 : 500, keyCands(k.r, fs), k.g);
    }
    for (const [g, pt, d, r] of stopSpots) place(pt[0], pt[1], P[g][0], FS_STOP, 400, stopCands(d, r), g);
    // route numbers
    const shown = new Set();
    const putTag = (x, y, nums, col) => {
      const items = nums.map((l) => D.lines[l][1]);
      const rows = [];
      for (let i = 0; i < Math.min(items.length, 48); i += 8) rows.push(items.slice(i, i + 8).join(' '));
      if (items.length > 48) rows[rows.length - 1] += ` +${items.length - 48}`;
      const tw = Math.max(...rows.map((r) => measure(r, FS_TAG, 400).w)) + 5, th = rows.length * FS_TAG * 1.2 + 3;
      const c = box(x - tw / 2 - PAD, y - th / 2 - PAD, x + tw / 2 + PAD, y + th / 2 + PAD);
      if (!hash.free(c)) return false;
      hash.add(c);
      nums.slice(0, 48).forEach((l) => shown.add(l));
      tags.push({ x, y, tw, th, rows, col });
      return true;
    };
    const byMost = [...lines].sort((a, b) => b.ls.length - a.ls.length || a.i - b.i);
    for (const L of byMost) {
      const nums = [...L.ls].sort(lineOrder);
      for (const f of [0.5, 0.35, 0.65]) { const [q] = along(L.pts, f); if (putTag(q[0], q[1], nums, L.col)) break; }
    }
    for (const L of [...byMost].reverse()) {
      const left = [...L.ls].sort(lineOrder).filter((l) => !shown.has(l));
      if (!left.length) continue;
      let done = false;
      for (const f of [0.5, 0.3, 0.7, 0.15, 0.85, 0.05, 0.95]) {
        const [q, d] = along(L.pts, f);
        for (const k of [0, 9, -9, 16, -16, 24, -24]) if (putTag(q[0] - d[1] * k, q[1] + d[0] * k, left, L.col)) { done = true; break; }
        if (done) break;
      }
    }
    const all = new Set(); lines.forEach((L) => L.ls.forEach((l) => all.add(l)));
    stats.unnamed = [...all].filter((l) => !shown.has(l)).length;
    stats.lines = all.size; stats.stops = stopSpots.length + keys.length;
    const ring = (r) => r.map(X);
    return {
      W: stats.W, H: stats.H, pxkm, x0, y0, lines, dots, keys, labels, tags, leaders, stats,
      land: landKm.map(ring), lakes: lakesKm.map((rs) => rs.map(ring)),
      places: P.map((pl, g) => (used[g] ? [pl[0], ...X(at[g]), [...serves[g]].sort(lineOrder).map((l) => D.lines[l][1])] : null)),
    };
  }
}
