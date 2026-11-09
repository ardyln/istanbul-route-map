// node tools/check_overlaps.js <svg>: measures every <text> as Chrome renders it and reports text boxes that overlap
const { chromium } = require('playwright-core');
const fs = require('fs');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--headless=new'] });
  const pg = await b.newPage({ viewport: { width: 1200, height: 800 } });
  await pg.setContent('<html><body style="margin:0">' + fs.readFileSync(process.argv[2], 'utf8') + '</body></html>');
  const res = await pg.evaluate(() => {
    const boxes = [];
    const texts = [...document.querySelectorAll('svg text')];
    // a route tag's rows are one box (its <rect>); names are their own boxes, rotated as drawn
    for (const g of document.querySelectorAll('svg g')) {
      const r = g.querySelector('rect'); if (!r) continue;
      const x = +r.getAttribute('x'), y = +r.getAttribute('y'), w = +r.getAttribute('width'), h = +r.getAttribute('height');
      boxes.push({ name: 'tag:' + [...g.querySelectorAll('text')].map(t => t.textContent).join(' '), c: [[x, y], [x + w, y], [x + w, y + h], [x, y + h]] });
    }
    for (const t of texts) {
      if (t.closest('g')) continue;
      const bb = t.getBBox();
      if (!bb.width) continue;
      let c = [[bb.x, bb.y], [bb.x + bb.width, bb.y], [bb.x + bb.width, bb.y + bb.height], [bb.x, bb.y + bb.height]];
      const m = /rotate\(([-\d.]+) ([-\d.]+) ([-\d.]+)\)/.exec(t.getAttribute('transform') || '');
      if (m) {
        const a = +m[1] * Math.PI / 180, cx = +m[2], cy = +m[3];
        c = c.map(([x, y]) => [cx + (x - cx) * Math.cos(a) - (y - cy) * Math.sin(a), cy + (x - cx) * Math.sin(a) + (y - cy) * Math.cos(a)]);
      }
      boxes.push({ name: t.textContent, c });
    }
    const shrink = (c) => { // a hair inside the drawn box, so boxes that only touch don't count
      const mx = c.reduce((s, p) => s + p[0], 0) / 4, my = c.reduce((s, p) => s + p[1], 0) / 4;
      return c.map(([x, y]) => [mx + (x - mx) * 0.97, my + (y - my) * 0.97]);
    };
    const overlap = (A, B) => {
      for (const [p, q] of [[A[0], A[1]], [A[0], A[3]], [B[0], B[1]], [B[0], B[3]]]) {
        const ax = [q[0] - p[0], q[1] - p[1]];
        const pa = A.map(([x, y]) => x * ax[0] + y * ax[1]), pb = B.map(([x, y]) => x * ax[0] + y * ax[1]);
        if (Math.max(...pa) <= Math.min(...pb) || Math.max(...pb) <= Math.min(...pa)) return false;
      }
      return true;
    };
    const CELL = 64, grid = new Map(), hits = [];
    boxes.forEach((bx, i) => {
      bx.c = shrink(bx.c);
      const xs = bx.c.map(p => p[0]), ys = bx.c.map(p => p[1]);
      const seen = new Set();
      for (let gx = Math.floor(Math.min(...xs) / CELL); gx <= Math.floor(Math.max(...xs) / CELL); gx++)
        for (let gy = Math.floor(Math.min(...ys) / CELL); gy <= Math.floor(Math.max(...ys) / CELL); gy++) {
          const k = gx + ',' + gy;
          for (const j of grid.get(k) || []) if (!seen.has(j)) { seen.add(j); if (overlap(bx.c, boxes[j].c)) hits.push([boxes[j].name, bx.name]); }
          if (!grid.has(k)) grid.set(k, []); grid.get(k).push(i);
        }
    });
    return { boxes: boxes.length, overlaps: hits.length, examples: hits.slice(0, 10) };
  });
  console.log(JSON.stringify(res, null, 1));
  await b.close();
})();
