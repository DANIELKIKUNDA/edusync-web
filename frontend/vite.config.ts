import {defineConfig} from 'vite';

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
  }],
});
