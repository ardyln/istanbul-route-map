// node tools/measure_chars.js <chars file> <out json>: each character's width (in em) as the widest of the common
// sans-serif fonts installed here, regular and semi-bold, so names sized with it fit whichever a viewer has
const { chromium } = require('playwright-core');
const fs = require('fs');
(async () => {
  const chars = [...new Set([...fs.readFileSync(process.argv[2], 'utf8')])].filter(c => c !== '\n');
  const b = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--headless=new'] });
  const pg = await b.newPage();
  await pg.setContent('<html><body><canvas id="c"></canvas></body></html>');
  const res = await pg.evaluate((chars) => {
    const fonts = ['Inter', 'Roboto', 'Helvetica', 'Arial', 'Liberation Sans', 'DejaVu Sans', 'Noto Sans', 'Ubuntu', 'sans-serif'];
    const ctx = document.getElementById('c').getContext('2d');
    const have = fonts.filter(f => f === 'sans-serif' || document.fonts.check(`16px "${f}"`));
    const w = {};
    for (const ch of chars) {
      let m = 0;
      for (const f of have) for (const wt of [400, 700]) {
        ctx.font = `${wt} 100px ${f === 'sans-serif' ? f : `"${f}"`}`;
        m = Math.max(m, ctx.measureText(ch).width / 100);
      }
      w[ch] = Math.round(m * 1000) / 1000;
    }
    return { fonts: have, widths: w };
  }, chars);
  fs.writeFileSync(process.argv[3], JSON.stringify(res));
  console.log('fonts measured:', res.fonts.join(', '), '·', Object.keys(res.widths).length, 'characters');
  await b.close();
})();
