// School outbox — owner decision 2026-10-25: « au niveau école, le système doit fonctionner sans internet puis
// synchroniser ; l'inscription, la réinscription et les paiements ne doivent pas dépendre de la connexion ».
// Pattern (offline-first outbox): a business write that cannot reach the server is stored on the device WITH its
// Idempotency-Key, the user keeps working, and the queue is replayed in order when the network returns. The key makes a
// replay safe even when the first attempt reached the server before the line dropped (no double payment / enrollment).
// The server re-checks everything at replay time (months in order, concurrency between cashiers): a refusal is kept in
// « À vérifier » with the server's reason, never silently dropped. No token is ever stored here.
export type OutboxStatus = 'PENDING' | 'CONFLICT';
export type OutboxRequest = {
  id: string; scope: string; method: string; path: string; body: string; idempotencyKey: string;
  kind: string; label: string; createdAt: string; enqueueOrder?: number; attempts: number; status: OutboxStatus; lastError?: string; syncedReceipt?: string;
  ifMatch?: string;   // the version the user edited: replayed as is, the server answers the first result (same key) or a real conflict
};
export type OfflinePack = {scope: string; generatedAt: string; people: any[]; balances: Record<string, any[]>};

const DB = 'edusync-outbox-v1';
const REQ = 'requests';
const PACK = 'packs';
function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(DB, 1);
    r.onupgradeneeded = () => { const db = r.result;
      if (!db.objectStoreNames.contains(REQ)) db.createObjectStore(REQ, {keyPath: 'id'}).createIndex('scope', 'scope', {unique: false});
      if (!db.objectStoreNames.contains(PACK)) db.createObjectStore(PACK, {keyPath: 'scope'}); };
    r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error);
  });
}
async function tx<T>(store: string, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest | void): Promise<T> {
  const db = await openDb();
  try {
    return await new Promise<T>((resolve, reject) => {
      const t = db.transaction(store, mode); const req = fn(t.objectStore(store)); let out: any;
      if (req) req.onsuccess = () => { out = req.result; };
      t.oncomplete = () => resolve(out); t.onerror = () => reject(t.error); t.onabort = () => reject(t.error);
    });
  } finally { db.close(); }
}

// ---------------------------------------------------------------- what may be recorded offline
const OFFLINE_WRITES: Array<[RegExp, string, string]> = [
  [/^\/api\/v1\/schooling\/enrollments\/family$/, 'ENROLLMENT', 'Inscription'],
  [/^\/api\/v1\/finance\/checkout\/collect$/, 'PAYMENT', 'Encaissement'],
  [/^\/api\/v1\/finance\/checkout\/collect-plan$/, 'PAYMENT', 'Encaissement (plan anticipé)'],
  [/^\/api\/v1\/finance\/checkout\/family-collect$/, 'PAYMENT', 'Encaissement familial'],
  [/^\/api\/v1\/finance\/checkout\/products\/sell$/, 'SALE', 'Vente d’article'],
  [/^\/api\/v1\/finance\/cash\/expenses$/, 'EXPENSE', 'Dépense de caisse'],
  [/^\/api\/v1\/finance\/cash\/open$/, 'CASH_OPEN', 'Ouverture de caisse'],
  [/^\/api\/v1\/finance\/cash\/close$/, 'CASH_CLOSE', 'Clôture de caisse'],
  [/^\/api\/v1\/effectifs\/deposits$/, 'DEPOSIT', 'Dépôt matériel'],
  [/^\/api\/v1\/finance\/checkout\/(collect-with-fund|advance-funds)$/, 'PAYMENT', 'Fonds d’avance'],
  // 2026-10-31 (owner: « au niveau école tout le monde peut travailler offline »): every school role. Only operations the
  // server replays safely with their Idempotency-Key (tools/ci/offline_replay_postgres_integration.py). Kept online on
  // purpose: accounts and access (/access), imports (/import), reversals, cash-day closing and financial decisions
  // (cash integrity), document generation and devices — the screen says the network is needed.
  [/^\/api\/v1\/schooling\/students\/[0-9a-f-]{36}$/, 'STUDENT', 'Fiche élève'],
  [/^\/api\/v1\/schooling\/students\/[0-9a-f-]{36}\/(abandon|suspend|transfer|reintegrate|class-change)$/, 'STUDENT', 'Mouvement d’élève'],
  [/^\/api\/v1\/schooling\/families\/[0-9a-f-]{36}(\/guardians(\/[0-9a-f-]{36})?)?$/, 'FAMILY', 'Famille et responsables'],
  [/^\/api\/v1\/personnel$/, 'STAFF', 'Nouvel agent'],
  [/^\/api\/v1\/personnel\/[0-9a-f-]{36}$/, 'STAFF', 'Fiche agent'],
  [/^\/api\/v1\/personnel\/[0-9a-f-]{36}\/(status|exit|reactivate)$/, 'STAFF', 'Statut d’agent'],
  [/^\/api\/v1\/personnel\/(catalog\/functions(\/[0-9a-f-]{36})?|assignments(\/[0-9a-f-]{36}\/end)?)$/, 'STAFF', 'Fonctions et affectations'],
  [/^\/api\/v1\/personnel\/([0-9a-f-]{36}\/children(\/[0-9a-f-]{36}\/payroll-deductions)?|children\/[0-9a-f-]{36}\/finance-mode|payroll-deductions\/[0-9a-f-]{36}\/cancel)$/, 'STAFF', 'Enfants du personnel'],
  [/^\/api\/v1\/stewardship\/items(\/[0-9a-f-]{36})?$/, 'STOCK', 'Article de stock'],
  [/^\/api\/v1\/stewardship\/stock\/movements$/, 'STOCK', 'Mouvement de stock'],
  [/^\/api\/v1\/stewardship\/assets(\/[0-9a-f-]{36}(\/(status|repairs))?)?$/, 'ASSET', 'Patrimoine'],
  [/^\/api\/v1\/stewardship\/counts(\/[0-9a-f-]{36}\/(lines|validate))?$/, 'COUNT', 'Inventaire physique'],
  [/^\/api\/v1\/communications\/send$/, 'MESSAGE', 'Message aux familles'],
  [/^\/api\/v1\/communications\/templates$/, 'MESSAGE', 'Modèle de message'],
  [/^\/api\/v1\/settings\/(?!backups|branding)[a-z-]+(\/[^/]+){0,3}$/, 'SETTINGS', 'Paramétrage'],
];
export function offlineWriteKind(path: string): [string, string] | null { const m = OFFLINE_WRITES.find(([re]) => re.test(path)); return m ? [m[1], m[2]] : null; }

// ---------------------------------------------------------------- scope, token, notifications
let scope = ''; let tokenOf: () => string | null = () => null;
/** Called by the school app: one queue per school + user (+ this browser); the token is read at replay time only. */
export function configureOutbox(nextScope: string, token: () => string | null) { scope = nextScope; tokenOf = token; void notify(); void syncOutbox(); }
export function outboxScope() { return scope; }
export type OutboxState = {pending: number; conflicts: number; syncing: boolean; lastSync?: number; lastResult?: 'ok' | 'partial' | 'offline'};
let state: OutboxState = {pending: 0, conflicts: 0, syncing: false};
const listeners = new Set<(s: OutboxState) => void>();
export function subscribeOutbox(fn: (s: OutboxState) => void) { listeners.add(fn); fn({...state}); return () => { listeners.delete(fn); }; }
async function notify(patch: Partial<OutboxState> = {}) {
  const all = scope ? await listOutbox() : [];
  state = {...state, ...patch, pending: all.filter(r => r.status === 'PENDING').length, conflicts: all.filter(r => r.status === 'CONFLICT').length};
  listeners.forEach(fn => fn({...state})); window.dispatchEvent(new CustomEvent('edusync:outbox', {detail: {...state}}));
}

export async function listOutbox(): Promise<OutboxRequest[]> {
  if (!scope) return [];
  const rows = await tx<OutboxRequest[]>(REQ, 'readonly', s => s.index('scope').getAll(scope));
  return (rows ?? []).sort((a, b) => (a.enqueueOrder ?? 0) - (b.enqueueOrder ?? 0)
    || a.createdAt.localeCompare(b.createdAt) || a.id.localeCompare(b.id));
}
/** Stores a write that could not reach the server; the caller receives a synthetic « queued » answer. */
export async function enqueueWrite(path: string, method: string, body: string, idempotencyKey: string, ifMatch?: string | null): Promise<OutboxRequest> {
  const k = offlineWriteKind(path); if (!k || !scope) throw new Error('Opération non disponible hors connexion');
  const currentScope = scope;
  const req: OutboxRequest = {id: crypto.randomUUID(), scope: currentScope, method, path, body, idempotencyKey, kind: k[0], label: describe(k[1], path, body),
    createdAt: new Date().toISOString(), attempts: 0, status: 'PENDING', ...(ifMatch ? {ifMatch} : {})};
  // The read and the write share one IndexedDB write transaction. Concurrent cashiers in
  // the same PWA therefore get a stable queue order, even within the same millisecond.
  const db = await openDb(); let saved = req;
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction(REQ, 'readwrite');
      const store = transaction.objectStore(REQ);
      const get = store.index('scope').getAll(currentScope);
      get.onsuccess = () => {
        const rows = get.result as OutboxRequest[];
        const existing = rows.find(row => row.idempotencyKey === idempotencyKey);
        if (existing) { saved = existing; return; }                       // duplicate key is one operation
        req.enqueueOrder = Math.max(0, ...rows.map(row => row.enqueueOrder ?? 0)) + 1;
        store.add(req);
      };
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally { db.close(); }
  await notify(); return saved;
}
export async function retryConflict(id: string) { const r = (await listOutbox()).find(x => x.id === id); if (!r) return; await tx(REQ, 'readwrite', s => s.put({...r, status: 'PENDING', lastError: undefined})); await notify(); void syncOutbox(); }
export async function dismissConflict(id: string) { await tx(REQ, 'readwrite', s => s.delete(id)); await notify(); }
function describe(base: string, path: string, body: string) {
  try { const b = JSON.parse(body); const amount = b.amount ? ` · ${b.amount} ${b.currency === 'CDF' ? 'FC' : (b.currency ?? '')}` : '';   // the UI reads FC, never CDF
    const child = Array.isArray(b.children) && b.children[0] ? ` · ${[b.children[0].last_name, b.children[0].first_name].filter(Boolean).join(' ')}${b.children.length > 1 ? ` +${b.children.length - 1}` : ''}` : '';
    return `${base}${child}${amount}`.trim(); } catch { return base; }
}

// ---------------------------------------------------------------- replay
// Business refusals the server answers when the operation already happened: the replay counts as done.
const ALREADY_DONE = /(déjà ouverte|Aucune caisse ouverte à clôturer|already)/i;
let running: Promise<void> | null = null;
export function syncOutbox(): Promise<void> {
  if (running) return running;
  running = (async () => {
    const token = tokenOf(); if (!scope || !token || navigator.onLine === false) { await notify({lastResult: navigator.onLine === false ? 'offline' : state.lastResult}); return; }
    const queue = (await listOutbox()).filter(r => r.status === 'PENDING'); if (!queue.length) return;
    await notify({syncing: true}); let sent = 0, refused = 0, stopped = false;
    for (const r of queue) {
      let res: Response;
      try { res = await fetch(r.path, {method: r.method, headers: {'Authorization': `Bearer ${tokenOf()}`, 'Content-Type': 'application/json', 'Idempotency-Key': r.idempotencyKey, 'X-EduSync-Replay': 'outbox', ...(r.ifMatch ? {'If-Match': r.ifMatch} : {})}, body: r.body}); }
      catch { stopped = true; break; }                                               // still no network: keep the order, retry later
      if (res.status === 401 || res.status >= 500 || res.status === 429) { stopped = true; break; }
      if (res.ok) { let receipt = ''; try { const j = await res.clone().json(); receipt = j?.receipt_number ?? j?.receipts?.[0]?.receipt_number ?? ''; } catch { /* no body */ }
        await tx(REQ, 'readwrite', s => s.delete(r.id)); sent++; window.dispatchEvent(new CustomEvent('edusync:outbox-sent', {detail: {kind: r.kind, label: r.label, receipt}})); continue; }
      let reason = `Refus du serveur (${res.status})`; try { const j = await res.json(); if (typeof j?.detail === 'string') reason = j.detail; } catch { /* no body */ }
      if (ALREADY_DONE.test(reason)) { await tx(REQ, 'readwrite', s => s.delete(r.id)); sent++; continue; }
      await tx(REQ, 'readwrite', s => s.put({...r, status: 'CONFLICT', attempts: r.attempts + 1, lastError: reason})); refused++;
    }
    await notify({syncing: false, lastSync: Date.now(), lastResult: stopped ? 'offline' : refused ? 'partial' : 'ok'});
    if (sent || refused) window.dispatchEvent(new CustomEvent('edusync:outbox-synced', {detail: {sent, refused}}));
  })().finally(() => { running = null; });
  return running;
}
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => { void syncOutbox(); });
  window.addEventListener('edusync:connectivity', e => { if ((e as CustomEvent).detail?.state === 'ONLINE') void syncOutbox(); });
  setInterval(() => { if (state.pending > 0) void syncOutbox(); }, 20_000);
}

// ---------------------------------------------------------------- offline pack (pupils + payable charges)
export async function savePack(pack: Omit<OfflinePack, 'scope'>) { if (scope) await tx(PACK, 'readwrite', s => s.put({...pack, scope})); }
export async function loadPack(): Promise<OfflinePack | null> { return scope ? (await tx<OfflinePack | undefined>(PACK, 'readonly', s => s.get(scope))) ?? null : null; }
/** After a payment recorded offline, the local copy reflects it at once: the same month cannot be collected twice here. */
export async function applyLocalPayment(enrollmentId: string, chargeIds: string[], amount: string) {
  const pack = await loadPack(); if (!pack) return;
  let left = Math.round(Number(amount) * 100);
  const list = (pack.balances[enrollmentId] ?? []).map(c => ({...c}));
  for (const c of list) { if (!chargeIds.includes(c.id) || left <= 0) continue;
    const rem = Math.round(Number(c.remaining) * 100); const take = Math.min(rem, left); left -= take;
    c.remaining = ((rem - take) / 100).toFixed(2); c.paid_amount = ((Math.round(Number(c.paid_amount) * 100) + take) / 100).toFixed(2); }
  const open = list.filter(c => Number(c.remaining) > 0);
  // Next period of each chain becomes eligible once its predecessors are settled locally.
  for (const c of open) { const req: string[] = (c.requires ?? []).filter((id: string) => open.some(o => o.id === id)); c.requires = req; if (!req.length) { c.eligible = true; c.lock_reason = null; } }
  pack.balances[enrollmentId] = open; await tx(PACK, 'readwrite', s => s.put(pack));
}
export function searchPack(pack: OfflinePack, q: string) {
  const t = q.trim().toLowerCase(); if (!t) return [];
  return pack.people.filter(p => `${p.matricule} ${p.last_name} ${p.middle_name ?? ''} ${p.first_name} ${p.family_name ?? ''} ${p.phone ?? ''}`.toLowerCase().includes(t)).slice(0, 12);
}
