// @vitest-environment jsdom
// Owner, 2026-11-15 (« obligé de se reconnecter ») : deeper session defects, each proven here.
import {afterEach, expect, it, vi} from 'vitest';
import {readFileSync} from 'node:fs';

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('la liste des espaces a une limite de temps : la reprise de session ne l’attend jamais indéfiniment', async () => {
  vi.useFakeTimers(); vi.resetModules();
  vi.stubGlobal('fetch', vi.fn((_u: string, init: RequestInit) => new Promise<Response>((_r, reject) =>
    init.signal?.addEventListener('abort', () => reject(new DOMException('délai', 'AbortError'))))));
  const s = await import('../src/platform/spaces');
  const pending = s.fetchSpaces().catch(e => e.name);
  await vi.advanceTimersByTimeAsync(s.SPACES_TIMEOUT_MS + 10);
  expect(await pending).toBe('AbortError');
});

it('le corps de la réponse de renouvellement est lu dans la limite de temps', async () => {
  vi.useFakeTimers(); vi.resetModules();
  // En-têtes reçus, corps jamais envoyé ; comme un navigateur, l'abandon de la requête met le flux du corps en erreur.
  let body!: ReadableStreamDefaultController;
  const stalled = new ReadableStream({start(c) { body = c; }});
  vi.stubGlobal('fetch', vi.fn((_u: string, init: RequestInit) => {
    init.signal?.addEventListener('abort', () => body.error(new DOMException('délai', 'AbortError')));
    return Promise.resolve(new Response(stalled, {status: 200}));
  }));
  Object.defineProperty(navigator, 'locks', {configurable: true, value: undefined});
  const c = await import('../src/platform/connectivity');
  // L'appelant lit ensuite le corps (comme App.tsx et le renouvellement de fond) : rien ne doit rester suspendu.
  const pending = c.refreshAccessSession().then(r => r.text()).then(() => 'lu', e => e?.name || 'rejeté');
  await vi.advanceTimersByTimeAsync(c.REFRESH_TIMEOUT_MS + 10);
  expect(await pending).toBe('AbortError');
});

it('une session encore valide n’est jamais déconnectée pour une ancienne clé refusée', () => {
  const app = readFileSync('src/App.tsx', 'utf8');
  const conn = readFileSync('src/platform/connectivity.ts', 'utf8');
  // à l'ouverture : on demande au serveur, et si la session courante est valide on réessaie une fois avant toute déconnexion
  expect(app).toMatch(/if\(spacesAfterRefusal\?\.current_valid\)\{\s*r=await refreshAccessSession\(ctl.signal\)/);
  expect(app.indexOf('if(spacesAfterRefusal?.current_valid)')).toBeLessThan(app.indexOf("clearPlatformContext();setPlatformToken('');setSchoolSession(null);"));
  // pendant le travail : un 401 est retenté une fois avec la clé actuelle
  expect(conn).toContain('if(r.status===401)r=await refreshAccessSession();');
});
