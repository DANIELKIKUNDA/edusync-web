// Exploration helper: log in as a journey account, click a path of visible texts, dump controls + screenshot.
// Usage: node journey_explore.mjs <USER_KEY> <shotName> "<click 1>" "<click 2>" ...
import fs from 'node:fs/promises';
import {open, uiLogin} from './ui.mjs';
const [key, shot, ...path] = process.argv.slice(2);
const fx = JSON.parse(await fs.readFile(new URL('../../.local/claude-fixtures-edusync_claude_fresh.json', import.meta.url), 'utf8'));
const A = fx.A, u = A.users[key];
const page = await open();
await page.viewport(1366, 768);
await uiLogin(page, {code: A.code, email: u.email, password: u.password});
for (const p of path) {
  if (p.startsWith('fill:')) { const [, hint, value] = p.split(':'); await page.fill(hint, value); await new Promise(r => setTimeout(r, 1500)); continue; }
  await page.click(p); await page.settle();
}
await page.shot(shot);
console.log('CONTROLS', JSON.stringify(await page.visibleControls()));
console.log('TEXT', (await page.ev('document.querySelector("main")?.innerText||document.body.innerText')).slice(0, 1500).replace(/\n+/g, ' ⏎ '));
console.log('ERRORS', JSON.stringify(page.errors), 'HTTP>=400', JSON.stringify(page.http.filter(h => !h.includes('/auth/refresh'))));
await page.close();
