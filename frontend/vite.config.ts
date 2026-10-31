import {defineConfig} from 'vite';
import fs from 'node:fs';
import path from 'node:path';

/* Build identity (update notice, lot 2026-10): every build gets an id — the commit SHA in CI (EDUSYNC_BUILD_ID build
   argument), a timestamp otherwise. It is compiled into the app and published as /version.json; a running tab
   compares the two to know that a newer version has been deployed. */
const env = (globalThis as {process?: {env: Record<string, string | undefined>}}).process?.env ?? {};
const BUILD_ID = (env.EDUSYNC_BUILD_ID || '').trim() || `dev-${new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14)}`;

export default defineConfig({
  define: {__EDUSYNC_BUILD__: JSON.stringify(BUILD_ID)},
  plugins: [{
    name: 'edusync-version',
    apply: 'build',
    generateBundle() {
      this.emitFile({type: 'asset', fileName: 'version.json', source: JSON.stringify({build: BUILD_ID, built_at: new Date().toISOString()})});
    },
  }, {
    /* Offline proof on a phone (2026-10-31): a module never opened online could not open without network — its code was
       only cached once loaded. Every build now writes the full list of its hashed assets into dist/sw.js (PRECACHE) and
       names the cache after the build: the phone downloads every module at the first online visit, and a new build
       replaces the worker (byte change) and its cache. */
    name: 'edusync-offline-precache',
    apply: 'build',
    closeBundle() {
      const out = path.resolve('dist'); const sw = path.join(out, 'sw.js'); if (!fs.existsSync(sw)) return;
      const assets = fs.readdirSync(path.join(out, 'assets')).filter(f => /\.(js|css|woff2|svg|png)$/.test(f)).sort().map(f => `/assets/${f}`);
      const src = fs.readFileSync(sw, 'utf8')
        .replace(/const CACHE='[^']*';/, `const CACHE='edusync-shell-${BUILD_ID}';`)
        .replace(/const PRECACHE=\[[^\]]*\];/, `const PRECACHE=${JSON.stringify(assets)};`);
      fs.writeFileSync(sw, src);
    },
  }],
});
