// node tools/viewer_test.js <url> <out prefix>: loads the viewer, waits for each layout, screenshots, reports errors
const { chromium } = require('playwright-core');
(async () => {
  const [url, out] = process.argv.slice(2);
  const b = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--headless=new'] });
  const pg = await b.newPage({ viewport: { width: 1400, height: 900 } });
  const errs = [];
  pg.on('pageerror', (e) => errs.push(String(e))); pg.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()); });
  const settle = async () => { await pg.waitForFunction(() => /Laid out/.test(document.getElementById('status').textContent), null, { timeout: 120000 }); await pg.waitForTimeout(400); };
  await pg.goto(url); await settle();
  console.log('default:', await pg.textContent('#status'));
  await pg.screenshot({ path: out + '-overview.png' });
  // zoom into the centre (Zincirlikuyu) with the search
  await pg.fill('#search', 'Zincirlikuyu Metrobüs'); await pg.waitForTimeout(300);
  await pg.click('#results li >> nth=0'); await pg.waitForTimeout(400);
  await pg.screenshot({ path: out + '-zoom.png' });
  console.log('picked:', (await pg.textContent('#info')).slice(0, 120));
  for (const [sq, sn] of [[50, 8], [0, 0], [100, 3]]) {
    await pg.evaluate(([sq, sn]) => { const s = document.getElementById('squish'), n = document.getElementById('snap');
      s.value = sq; n.value = sn; s.dispatchEvent(new Event('change')); }, [sq, sn]);
    await pg.waitForTimeout(200); await settle();
    console.log(`squish ${sq} snap ${sn}:`, await pg.textContent('#status'));
    await pg.screenshot({ path: `${out}-s${sq}-n${sn}.png` });
  }
  console.log('errors:', JSON.stringify(errs.slice(0, 5)));
  await b.close();
})();
