// node tools/shot.js <svg> <png> <width> <height> <x> <y> <zoom>: a view of a big SVG as a PNG
const { chromium } = require('playwright-core');
const fs = require('fs');
(async () => {
  const [src, out, w, h, x, y, zoom] = process.argv.slice(2);
  const b = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--headless=new'] });
  const pg = await b.newPage({ viewport: { width: +w, height: +h }, deviceScaleFactor: 1 });
  await pg.setContent('<html><body style="margin:0">' + fs.readFileSync(src, 'utf8') + '</body></html>');
  await pg.evaluate(([x, y, z]) => { const s = document.querySelector('svg');
    s.style.transformOrigin = '0 0'; s.style.transform = `scale(${z}) translate(${-x}px, ${-y}px)`; }, [+x, +y, +zoom]);
  await pg.waitForTimeout(300);
  await pg.screenshot({ path: out });
  await b.close();
})();
