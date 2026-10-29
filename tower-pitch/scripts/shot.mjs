// Headless screenshots with explicit frame rendering (SwiftShader is too slow for a live loop).
// node scripts/shot.mjs <out.png> <setup-js> [frames] [width] [height]
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)(process.env.PW_PATH || 'playwright');
const [out, setup = '', frames = '3', W = '1600', H = '900'] = process.argv.slice(2);
const url = process.env.SHOT_URL || 'http://localhost:4173/?shot';
const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: +W, height: +H }, deviceScaleFactor: 1 });
const logs = [];
page.on('console', (m) => logs.push(`[${m.type()}] ${m.text()}`));
page.on('pageerror', (e) => logs.push(`[pageerror] ${e.message}`));
page.setDefaultTimeout(600000);
await page.goto(url, { waitUntil: 'load', timeout: 600000 });
await page.waitForFunction(() => window.__shotReady === true, null, { timeout: 600000, polling: 1000 });
const t0 = Date.now();
await page.evaluate(async ({ setup, frames }) => {
  const app = window.__app;
  const V = window.__VIEWS;
  if (setup) await (0, eval)(`(async (app, V) => { ${setup} })`)(app, V);
  for (let i = 0; i < frames; i++) { app.frameOnce(); await new Promise((r) => setTimeout(r, 50)); }
}, { setup, frames: +frames });
console.log('render ms', Date.now() - t0);
await page.screenshot({ path: out, timeout: 600000 });
console.log(logs.filter((l) => !l.includes('GPU stall')).slice(0, 30).join('\n'));
await browser.close();
