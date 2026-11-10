// Istanbul route map viewer: draws what layout.js (a worker) lays out, with pan and zoom.
'use strict';
const FONT = 'Inter, Roboto, Helvetica, Arial, sans-serif';
const canvas = document.getElementById('map'), ctx = canvas.getContext('2d');
const $ = (id) => document.getElementById(id);
// ?v= on every file, stamped by `make viewer`: a reload never mixes new and cached (GitHub Pages: 10 min) files
const V = new URL(document.currentScript.src).search;
const worker = new Worker('layout.js' + V);
let M = null;                 // the current layout
let view = null;              // {cx, cy (km), z (screen px per km)}
let pending = null, busy = false, raf = 0;
let anchor = null;            // the stop nearest the middle of the screen, kept there across a new layout

// -- settings, kept in the URL so a view can be shared ----------------------------------------------------
const url = new URLSearchParams(location.search);
for (const [id, def] of [['squish', '0'], ['snap', '5']]) $(id).value = url.get(id) ?? def;
$('straightCoast').checked = url.get('coast') === 'straight';
if (['code', 'none'].includes(url.get('merge'))) $('merge').value = url.get('merge');
for (const id of ['minibus', 'dolmus']) $(id).checked = url.get(id) !== '0';
function params() {
  return { squish: $('squish').value / 100, snap: +$('snap').value, coast: $('straightCoast').checked ? 'straight' : 'real',
           minibus: $('minibus').checked, dolmus: $('dolmus').checked };
}
function labelsUpdate() {
  $('squishV').textContent = $('squish').value === '0' ? 'none (true scale)' : $('squish').value + ' %';
  $('snapV').textContent = $('snap').value === '0' ? 'none (stop to stop)' : $('snap').value + ' / 10';
}
function relayout() {
  labelsUpdate();
  const p = params();
  const q = new URLSearchParams({ squish: $('squish').value, snap: $('snap').value });
  if (p.coast === 'straight') q.set('coast', 'straight');
  if (!p.minibus) q.set('minibus', '0');
  if (!p.dolmus) q.set('dolmus', '0');
  if (merge !== 'name') q.set('merge', merge);
  history.replaceState(null, '', '?' + q);
  if (M && view && anchor === null) {   // remember what's in the middle, to keep it there
    const { k, ox, oy } = toScreen();
    const cx = (canvas.clientWidth / 2 - ox) / k, cy = (canvas.clientHeight / 2 - oy) / k;
    let bd = Infinity;
    M.places.forEach((pl, g) => { if (pl) { const d = Math.hypot(pl[1] - cx, pl[2] - cy); if (d < bd) { bd = d; anchor = [g, pl[1] - cx, pl[2] - cy, M.pxkm, pl[0], pl[1], pl[2]]; } } });
  }
  if (busy) { pending = p; return; }
  busy = true;
  $('status').textContent = 'Laying out…';
  worker.postMessage({ params: p });
}
for (const id of ['squish', 'snap']) { $(id).addEventListener('input', labelsUpdate); $(id).addEventListener('change', relayout); }
for (const id of ['straightCoast', 'minibus', 'dolmus']) $(id).addEventListener('change', relayout);

worker.onmessage = (e) => {
  M = e.data;
  busy = false;
  index();
  if (!view) fit();
  else if (anchor && !pending && (() => {   // the same stop in the middle as before
    let pl = M.places[anchor[0]];
    if (!pl || pl[0] !== anchor[4]) {   // stops merged another way: the nearest stop of that name
      const r = M.pxkm / anchor[3];
      let bd = Infinity;
      pl = null;
      for (const q of M.places) if (q && q[0] === anchor[4]) { const d = Math.hypot(q[1] - anchor[5] * r, q[2] - anchor[6] * r); if (d < bd) { bd = d; pl = q; } }
    }
    anchor.pl = pl;
    return pl;
  })()) {
    const pl = anchor.pl;
    view.cx = M.x0 + (pl[1] - anchor[1] * M.pxkm / anchor[3]) / M.pxkm;
    view.cy = M.y0 + (pl[2] - anchor[2] * M.pxkm / anchor[3]) / M.pxkm;
  }
  if (!pending) anchor = null;
  const s = M.stats;
  const mv = s.moved && s.moved.length ? (() => { const a = [...s.moved].sort((x, y) => x - y); return `, stops a median ${Math.round(a[a.length >> 1])} m off their real place`; })() : '';
  $('status').textContent = `${s.lines} lines, ${s.stops} stops, every one named, no text overlapping` +
    (s.noRoom || s.unnamed ? ` (except ${s.noRoom} names and ${s.unnamed} lines with no room)` : '') +
    `${mv}. Laid out in ${(s.ms / 1000).toFixed(1)} s.`;
  draw();
  if (pending) { const p = pending; pending = null; busy = true; $('status').textContent = 'Laying out…'; worker.postMessage({ params: p }); }
};
// stops merged by name come with network.json; the other ways are fetched when first chosen
const graphs = {};
let merge = 'name';
function setMerge() {
  const want = $('merge').value;
  if (want === merge) return relayout();
  $('status').textContent = 'Loading the stops…';
  const got = graphs[want] || (graphs[want] = fetch(`network-${want}.json` + V).then((r) => r.json())
    .then((g) => ({ places: g.places, lines: g.lines, corridors: g.corridors })));
  Promise.all([got, base]).then(([g]) => {   // the worker needs the base network (shores, flow) first
    if ($('merge').value !== want) return;   // changed again while loading
    merge = want;
    worker.postMessage({ graph: g });
    relayout();
  }, () => { graphs[want] = null; $('merge').value = merge; $('status').textContent = 'Could not load those stops.'; });
}
$('merge').addEventListener('change', setMerge);
const base = fetch('network.json' + V).then((r) => r.json()).then((data) => {
  graphs.name = Promise.resolve({ places: data.places, lines: data.lines, corridors: data.corridors });
  worker.postMessage({ data });
});
base.then(() => { if ($('merge').value !== 'name') setMerge(); else relayout(); });

// -- view: km centre and screen px per km, so it survives a new layout ---------------------------------
function fit() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const z = Math.min(w / (M.W / M.pxkm), h / (M.H / M.pxkm));
  view = { cx: M.x0 + M.W / M.pxkm / 2, cy: M.y0 + M.H / M.pxkm / 2, z };
}
function toScreen() {   // layout px -> screen px
  const k = view.z / M.pxkm;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  return { k, ox: w / 2 - (view.cx - M.x0) * view.z, oy: h / 2 - (view.cy - M.y0) * view.z };
}

// -- spatial index of what's drawn, for culling and clicks -------------------------------------------------
let grid = null;
function index() {
  grid = new Map();
  const add = (x0, y0, x1, y1, item) => {
    for (let i = Math.floor(x0 / 512); i <= Math.floor(x1 / 512); i++)
      for (let j = Math.floor(y0 / 512); j <= Math.floor(y1 / 512); j++) {
        const k = i + ',' + j;
        if (!grid.has(k)) grid.set(k, []);
        grid.get(k).push(item);
      }
  };
  M.lines.forEach((L) => {
    let a = Infinity, b = Infinity, c = -Infinity, d = -Infinity;
    for (const [x, y] of L.pts) { a = Math.min(a, x); b = Math.min(b, y); c = Math.max(c, x); d = Math.max(d, y); }
    add(a - 6, b - 6, c + 6, d + 6, ['line', L]);
  });
  M.dots.forEach((o) => add(o.x - 4, o.y - 4, o.x + 4, o.y + 4, ['dot', o]));
  M.keys.forEach((o) => add(o.x - 8, o.y - 8, o.x + 8, o.y + 8, ['key', o]));
  M.tags.forEach((o) => add(o.x - o.tw / 2, o.y - o.th / 2, o.x + o.tw / 2, o.y + o.th / 2, ['tag', o]));
  M.labels.forEach((o) => add(o.x - 60, o.y - 60, o.x + 160, o.y + 60, ['label', o]));
  M.leaders.forEach((o) => add(Math.min(o[0], o[2]), Math.min(o[1], o[3]), Math.max(o[0], o[2]), Math.max(o[1], o[3]), ['leader', o]));
}

// -- drawing ------------------------------------------------------------------------------------------------
function draw() {
  cancelAnimationFrame(raf);
  raf = requestAnimationFrame(paint);
}
function paint() {
  if (!M) return;
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) { canvas.width = w * dpr; canvas.height = h * dpr; }
  const { k, ox, oy } = toScreen();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = '#d4e6f4'; ctx.fillRect(0, 0, w, h);
  ctx.setTransform(dpr * k, 0, 0, dpr * k, dpr * ox, dpr * oy);
  const path = (rings) => { ctx.beginPath(); for (const r of rings) { r.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath(); } };
  ctx.fillStyle = '#fbfaf7'; ctx.strokeStyle = '#b9c9d6'; ctx.lineWidth = 1 / k;
  path(M.land); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#d4e6f4';
  for (const rs of M.lakes) { path(rs); ctx.fill('evenodd'); }
  // what's on screen
  const vx0 = -ox / k, vy0 = -oy / k, vx1 = (w - ox) / k, vy1 = (h - oy) / k;
  const seen = new Set(), items = { line: [], dot: [], key: [], tag: [], label: [], leader: [] };
  for (let i = Math.floor(vx0 / 512); i <= Math.floor(vx1 / 512); i++)
    for (let j = Math.floor(vy0 / 512); j <= Math.floor(vy1 / 512); j++)
      for (const it of grid.get(i + ',' + j) || []) if (!seen.has(it[1])) { seen.add(it[1]); items[it[0]].push(it[1]); }
  ctx.lineJoin = 'round'; ctx.lineCap = 'round';
  items.line.sort((a, b) => a.ls.length - b.ls.length);
  for (const L of items.line) {
    ctx.strokeStyle = L.col; ctx.lineWidth = L.w; ctx.setLineDash(L.dash ? [5, 2.5] : []);
    ctx.beginPath(); L.pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.stroke();
  }
  ctx.setLineDash([]);
  const detail = k > 0.28, names = k > 0.5;
  if (detail) {
    for (const o of items.dot) { ctx.beginPath(); ctx.arc(o.x, o.y, o.r, 0, 7); ctx.fillStyle = '#fff'; ctx.fill(); ctx.lineWidth = 0.9; ctx.strokeStyle = o.col; ctx.stroke(); }
  }
  for (const o of items.key) {
    ctx.beginPath(); ctx.arc(o.x, o.y, o.r, 0, 7); ctx.fillStyle = o.mb ? '#e2231a' : '#fff'; ctx.fill();
    ctx.lineWidth = 1.1; ctx.strokeStyle = '#111'; ctx.stroke();
  }
  if (detail) {
    for (const t of items.tag) {
      ctx.fillStyle = '#fff'; ctx.strokeStyle = t.col; ctx.lineWidth = 0.7;
      ctx.beginPath(); ctx.roundRect(t.x - t.tw / 2, t.y - t.th / 2, t.tw, t.th, 2); ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#111'; ctx.font = `400 6.4px ${FONT}`; ctx.textAlign = 'center';
      t.rows.forEach((r, i) => ctx.fillText(r, t.x, t.y - t.th / 2 + 6.4 * 1.2 * (i + 1)));
    }
    ctx.textAlign = 'left';
  }
  if (names || k > 0.12) {
    ctx.strokeStyle = '#888'; ctx.lineWidth = 0.4;
    if (names) for (const l of items.leader) { ctx.beginPath(); ctx.moveTo(l[0], l[1]); ctx.lineTo(l[2], l[3]); ctx.stroke(); }
    for (const o of items.label) {
      if (!names && o.fs < 9) continue;      // zoomed out: only the big interchanges
      ctx.font = `${o.weight} ${o.fs}px ${FONT}`;
      ctx.save(); ctx.translate(o.x, o.y); if (o.ang) ctx.rotate(o.ang * Math.PI / 180);
      ctx.lineWidth = o.fs * 0.32; ctx.strokeStyle = '#fbfaf7'; ctx.lineJoin = 'round';
      ctx.strokeText(o.text, 0, 0); ctx.fillStyle = '#111'; ctx.fillText(o.text, 0, 0);
      ctx.restore();
    }
  }
}

// -- pan, zoom, click -------------------------------------------------------------------------------------
const pointers = new Map();
let drag = null, pinch = null, clickAt = null;
canvas.addEventListener('pointerdown', (e) => {
  canvas.setPointerCapture(e.pointerId);
  pointers.set(e.pointerId, [e.clientX, e.clientY]);
  if (pointers.size === 1) { drag = [e.clientX, e.clientY, view.cx, view.cy]; clickAt = [e.clientX, e.clientY]; canvas.classList.add('drag'); }
  if (pointers.size === 2) { const [a, b] = [...pointers.values()]; pinch = [Math.hypot(a[0] - b[0], a[1] - b[1]), view.z]; drag = null; }
});
canvas.addEventListener('pointermove', (e) => {
  if (!pointers.has(e.pointerId) || !view) return;
  pointers.set(e.pointerId, [e.clientX, e.clientY]);
  if (pinch && pointers.size === 2) {
    const [a, b] = [...pointers.values()];
    view.z = Math.max(0.5, Math.min(4000, pinch[1] * Math.hypot(a[0] - b[0], a[1] - b[1]) / pinch[0])); draw();
  } else if (drag) {
    view.cx = drag[2] - (e.clientX - drag[0]) / view.z; view.cy = drag[3] - (e.clientY - drag[1]) / view.z; draw();
  }
});
const up = (e) => {
  pointers.delete(e.pointerId);
  if (pointers.size < 2) pinch = null;
  if (!pointers.size) {
    canvas.classList.remove('drag');
    if (clickAt && Math.hypot(e.clientX - clickAt[0], e.clientY - clickAt[1]) < 4) pick(e.clientX, e.clientY);
    drag = null; clickAt = null;
  }
};
canvas.addEventListener('pointerup', up); canvas.addEventListener('pointercancel', up);
canvas.addEventListener('wheel', (e) => {
  e.preventDefault();
  if (!view) return;
  const f = Math.exp(-e.deltaY * (e.deltaMode ? 0.05 : 0.0015));
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const mx = view.cx + (e.clientX - w / 2) / view.z, my = view.cy + (e.clientY - h / 2) / view.z;
  view.z = Math.max(0.5, Math.min(4000, view.z * f));
  view.cx = mx - (e.clientX - w / 2) / view.z; view.cy = my - (e.clientY - h / 2) / view.z;
  draw();
}, { passive: false });
window.addEventListener('resize', draw);

function pick(sx, sy) {
  const { k, ox, oy } = toScreen();
  const x = (sx - ox) / k, y = (sy - oy) / k;
  let best = null, bd = 12 / k;
  for (const o of [...M.dots, ...M.keys]) { const d = Math.hypot(o.x - x, o.y - y); if (d < bd) { bd = d; best = o; } }
  const info = $('info');
  if (!best) { info.style.display = 'none'; return; }
  const pl = M.places[best.g];
  info.innerHTML = `<b>${esc(pl[0])}</b><br><span class="hint">${pl[3].length} line${pl[3].length === 1 ? '' : 's'}:</span> ${esc(pl[3].join(', '))}`;
  info.style.display = 'block';
}
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// -- search -----------------------------------------------------------------------------------------------
const fold = (t) => t.toLocaleLowerCase('tr').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/ı/g, 'i');
$('search').addEventListener('input', () => {
  const q = fold($('search').value.trim()), ul = $('results');
  ul.innerHTML = '';
  if (!M || q.length < 2) return;
  const found = [];
  M.places.forEach((pl, g) => { if (pl && fold(pl[0]).includes(q)) found.push(g); });
  found.slice(0, 30).forEach((g) => {
    const li = document.createElement('li');
    li.textContent = `${M.places[g][0]} · ${M.places[g][3].slice(0, 6).join(' ')}${M.places[g][3].length > 6 ? '…' : ''}`;
    li.onclick = () => {
      view.cx = M.x0 + M.places[g][1] / M.pxkm; view.cy = M.y0 + M.places[g][2] / M.pxkm; view.z = Math.max(view.z, M.pxkm * 1.6);
      draw();
      const { k, ox, oy } = toScreen(); pick(M.places[g][1] * k + ox, M.places[g][2] * k + oy);
    };
    ul.appendChild(li);
  });
});

// -- panel on small screens -------------------------------------------------------------------------------
$('hide').onclick = (e) => { e.preventDefault(); $('panel').style.display = 'none'; $('toggle').style.display = 'block'; };
$('toggle').onclick = () => { $('panel').style.display = 'block'; $('toggle').style.display = 'none'; };
labelsUpdate();
