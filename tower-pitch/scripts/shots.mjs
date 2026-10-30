// Several headless screenshots in one session: node scripts/shots.mjs <spec.json>
// spec: { "w":1600, "h":900, "frames":3, "shots":[{ "out":"a.png", "js":"..." }] }
import { createRequire } from 'node:module';
import fs from 'node:fs';
const { chromium } = createRequire(import.meta.url)(process.env.PW_PATH || '/opt/node-tools/node_modules/playwright/index.js');
const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const url = spec.url || 'http://localhost:4173/?shot';
const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: spec.w || 1600, height: spec.h || 900 }, deviceScaleFactor: 1 });
const logs = [];
page.on('console', (m) => logs.push(`[${m.type()}] ${m.text()}`));
page.on('pageerror', (e) => logs.push(`[pageerror] ${e.message}`));
page.setDefaultTimeout(900000);
await page.goto(url, { waitUntil: 'load', timeout: 900000 });
await page.waitForFunction(() => window.__shotReady === true, null, { timeout: 900000, polling: 1000 });
for (const s of spec.shots) {
  const t0 = Date.now();
  await page.evaluate(async ({ js, frames }) => {
    const app = window.__app;
    const V = window.__VIEWS;
    if (js) await (0, eval)(`(async (app, V) => { ${js} })`)(app, V);
    for (let i = 0; i < frames; i++) { app.frameOnce(); await new Promise((r) => setTimeout(r, 30)); }
  }, { js: s.js || '', frames: s.frames ?? spec.frames ?? 3 });
  await page.screenshot({ path: s.out });
  console.log(s.out, Date.now() - t0, 'ms');
}
console.log(logs.filter((l) => !/GPU stall|swiftshader|WebGL-/i.test(l)).slice(0, 30).join('\n'));
await browser.close();
