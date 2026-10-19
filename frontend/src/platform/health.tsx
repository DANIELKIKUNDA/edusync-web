import React, {useCallback, useEffect, useRef, useState} from 'react';
import {friendlyError, UserFacingError, friendlyHttpMessage} from './errors';
import {NavGlyph} from './nav_icons';
import './schools.css';
import './health.css';

/* État du service (Plateforme EduSync), lot 2026-10. Real measurements only (latency, heartbeats, queues, counters, the
   backup report); a component that is not configured says so, never « Opérationnel ». The page refreshes every 30 s
   while it is visible (paused in a background tab), never lets an older answer overwrite a newer one, and flags data
   older than two refresh periods as stale. « Mesurer maintenant » is disabled while a measure runs and for a short
   cooldown; the server also shares one measurement between concurrent requests.
   Diagnosable cockpit (lot 2026-10): every non-OK state comes with its reason (alerts under the banner); server errors
   are grouped (route, code, type) with first / last occurrence and correlation ids; the CURRENT state (errors of the
   last 5 minutes) is separated from the history (1 h / 24 h / 7 d), which never degrades it; golden signals of the
   API (traffic, errors, latency, saturation) with a short history; messaging providers (a simulation is never
   « certifié »). */

type State = 'OK' | 'DEGRADED' | 'DOWN' | 'NOT_CONFIGURED';
type Signals = {minutes: number; requests: number; per_minute: number | null; server_errors: number; client_refusals: number; error_rate: number;
  latency_avg_ms: number | null; latency_p50_ms: number | null; latency_p95_ms: number | null; latency_p95_over: boolean};
type GroupRow = {id: string; method: string; route: string; status: number; type: string; active: boolean; count_1h: number; count_24h: number; last_at: string;
  message?: string; first_at?: string; count_7d?: number; count_total?: number};
type ErrorsInfo = {current_state: State; active_groups: number; last_hour: number; last_24h: number; refusals_24h: number; first_active_at: string | null;
  last_at: string | null; active_window_seconds: number; groups: GroupRow[]};
type Provider = {channel: string; label: string; config_state: string; config_label: string; state: State; certified: boolean | null;
  last_success_at: string | null; last_failure_at: string | null; last_error_code: string | null; failures_15m: number};
type Alert = {key: string; severity: 'critical' | 'warning'; title: string; explain: string; since: string | null};
type Component = {key: string; label: string; state: State; detail: string; measured_ms: number | null; measured_at: string; age_seconds?: number | null;
  signals?: {last_5m: Signals; last_1h: Signals; last_24h: Signals; saturation: {db_pool_in_use: number; db_pool_capacity: number; db_pool_ratio: number | null} | null};
  errors?: ErrorsInfo; providers?: Provider[];
  queue?: {pending: number; failed: number; oldest_seconds: number | null}; provider?: {state: string}; value?: number | null; started_at?: string;
  backup?: {finished_at: string | null; ok: boolean; late: boolean; restore_verified: boolean; offsite: boolean; message: string; duration_seconds?: number | null; restore_seconds?: number | null}; depends_on: string[]};
type Health = {checked_at: string; overall: State; components: Component[]; refresh_seconds: number; shared: boolean; alerts?: Alert[];
  summary: {operational: number; configured: number; degraded: number; down: number; not_configured: number}; figures: Record<string, number | null>};

const API = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const STATE: Record<State, {label: string; cls: string; icon: string}> = {
  OK: {label: 'Opérationnel', cls: 'hl-ok', icon: 'checkCircle'}, DEGRADED: {label: 'Dégradé', cls: 'hl-warn', icon: 'alert'},
  DOWN: {label: 'Hors service', cls: 'hl-bad', icon: 'alert'}, NOT_CONFIGURED: {label: 'Non configuré', cls: 'hl-off', icon: 'info'},
};
const OVERALL: Record<State, string> = {OK: 'Tous les services fonctionnent normalement', DEGRADED: 'Certains services sont dégradés',
  DOWN: 'Incident en cours : au moins un service est hors service', NOT_CONFIGURED: 'Aucun service mesurable'};
const ICON: Record<string, string> = {api: 'cockpit', database: 'database', redis: 'layers', worker_outbox: 'sync', worker_communications: 'message', storage: 'folder', errors: 'alert', backup: 'cloudUp', messaging: 'bell'};
/** Priority order (also the phone order, after the incident): server, database, workers, backup, storage, messaging, errors, cache. */
const ORDER = ['api', 'database', 'worker_outbox', 'worker_communications', 'backup', 'storage', 'messaging', 'errors', 'redis'];
const LABEL: Record<string, string> = {api: 'Serveur d’application', database: 'Base de données', redis: 'Cache et files rapides', storage: 'Stockage des documents'};
const PROVIDER: Record<string, string> = {CONFIGURED: 'Configuré', SIMULATED: 'Simulation (hors production)', INCOMPLETE: 'Configuration incomplète', DISABLED: 'Désactivé', REFUSED: 'Refusé (simulation interdite en production)'};
const COOLDOWN_MS = 10_000;

function ago(seconds: number | null | undefined) {
  if (seconds == null) return 'aucun signal';
  if (seconds < 0) return 'à l’instant';
  if (seconds < 90) return `il y a ${seconds} s`;
  if (seconds < 5400) return `il y a ${Math.round(seconds / 60)} min`;
  if (seconds < 172800) return `il y a ${Math.round(seconds / 3600)} h`;
  return `il y a ${Math.round(seconds / 86400)} j`;
}
const since = (iso: string | null | undefined, now: number) => iso ? Math.round((now - new Date(iso).getTime()) / 1000) : null;

export function HealthPanel({token, canMessaging, onOpenMessaging}: {token: string; canMessaging?: boolean; onOpenMessaging?: () => void}) {
  const [data, setData] = useState<Health | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [open, setOpen] = useState<string | null>(() => new URLSearchParams(window.location.search).get('service'));
  const [lastOk, setLastOk] = useState(0);
  const reqId = useRef(0);
  const load = useCallback(async () => {
    const id = ++reqId.current;
    try {
      setBusy(true);
      const r = await fetch(`${API}/platform/system/health`, {headers: {Authorization: `Bearer ${token}`}});
      if (!r.ok) throw new UserFacingError(friendlyHttpMessage(r.status), String(r.status));
      const body: Health = await r.json();
      if (id !== reqId.current) return;                         // an older answer never overwrites a newer one
      setData(body); setError(''); setLastOk(Date.now());
    } catch (e) { if (id === reqId.current) setError(e instanceof UserFacingError ? e.message : friendlyError(e)); }
    finally { if (id === reqId.current) setBusy(false); }
  }, [token]);
  useEffect(() => {
    void load();
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    const poll = window.setInterval(() => { if (document.visibilityState === 'visible') void load(); }, 30_000);
    const vis = () => { if (document.visibilityState === 'visible' && Date.now() - lastOkRef.current > 30_000) void load(); };
    document.addEventListener('visibilitychange', vis);
    return () => { window.clearInterval(tick); window.clearInterval(poll); document.removeEventListener('visibilitychange', vis); };
  }, [load]);
  const lastOkRef = useRef(0); lastOkRef.current = lastOk;
  useEffect(() => {   // browser / Android back from a service detail returns to the cockpit
    const h = () => setOpen(new URLSearchParams(window.location.search).get('service'));
    window.addEventListener('popstate', h); return () => window.removeEventListener('popstate', h);
  }, []);
  function openService(key: string) { setOpen(key); history.pushState({...(history.state || {}), service: key}, '', `${window.location.pathname}?service=${key}`); window.scrollTo(0, 0); }
  function closeService() { if (history.state?.service) history.back(); else { setOpen(null); history.replaceState(history.state, '', window.location.pathname); } }
  function measureNow() {
    if (busy || cooldown) return;
    setCooldown(true); window.setTimeout(() => setCooldown(false), COOLDOWN_MS);
    void load();
  }
  const stale = data ? now - lastOk > 2 * (data.refresh_seconds || 30) * 1000 : false;
  const comps = data ? [...data.components].sort((a, b) => (ORDER.indexOf(a.key) + 99) % 99 - (ORDER.indexOf(b.key) + 99) % 99) : [];
  const current = comps.find(c => c.key === open);
  const overall = data ? STATE[data.overall] : null;
  if (current && data) return <ServiceDetail token={token} c={current} all={comps} now={now} stale={stale} onBack={closeService} canMessaging={canMessaging} onOpenMessaging={onOpenMessaging}/>;
  const alerts = data?.alerts || [];
  return <div className="sc hl">
    <header className="sc-head">
      <div><h2>État du service</h2><p>Mesures réelles de la plateforme. Actualisation automatique toutes les {data?.refresh_seconds || 30} s quand la page est affichée.</p></div>
      <div className="sc-head-actions"><button type="button" className="sc-btn sc-btn-ghost hl-measure" onClick={measureNow} disabled={busy || cooldown} aria-live="polite">
        <NavGlyph g="sync" size={16}/><span>{busy ? 'Mesure en cours…' : cooldown ? 'Mesure récente' : 'Mesurer maintenant'}</span></button></div>
    </header>
    {error && <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Impossible de mesurer les services.</b><small>{error}{data ? ' Les valeurs ci-dessous sont celles de la dernière mesure réussie.' : ''}</small></div>
      <button type="button" className="sc-btn sc-btn-ghost" onClick={() => void load()}>Réessayer</button></div>}
    {!data && !error && <div className="hl-grid" aria-busy="true" aria-label="Mesure en cours">{Array.from({length: 6}).map((_, i) => <div key={i} className="hl-card hl-skel"><i className="sc-skel" style={{width: '55%'}}/><i className="sc-skel" style={{width: '35%'}}/></div>)}</div>}
    {data && overall && <>
      <section className={`hl-banner ${stale ? 'hl-warn' : overall.cls}`} role="status" aria-live="polite">
        <NavGlyph g={stale ? 'clock' : overall.icon} size={22}/>
        <div><b>{stale ? 'Donnée périmée : la dernière mesure date de plus d’une minute' : OVERALL[data.overall]}</b>
          <small>{data.summary.operational}/{data.summary.configured} service(s) opérationnel(s){data.summary.degraded ? ` · ${data.summary.degraded} dégradé(s)` : ''}{data.summary.down ? ` · ${data.summary.down} hors service` : ''}{data.summary.not_configured ? ` · ${data.summary.not_configured} non configuré(s)` : ''} · mesure {ago(since(data.checked_at, now))}</small></div>
      </section>
      {alerts.length > 0 && <section className="hl-alerts" aria-label="Pourquoi l’état est dégradé">
        <h3>{alerts.some(a => a.severity === 'critical') ? 'Incident en cours' : 'À surveiller'}</h3>
        <ul>{alerts.map(a => <li key={a.key}><button type="button" className={`hl-alert ${a.severity === 'critical' ? 'hl-bad' : 'hl-warn'}`} onClick={() => openService(a.key)}>
          <NavGlyph g="alert" size={16}/><span><b>{a.title}</b><small>{a.explain}{a.since ? ` · depuis ${ago(since(a.since, now)).replace('il y a ', '')}` : ''}</small></span><NavGlyph g="chevronRight" size={16}/></button></li>)}</ul>
      </section>}
      <ul className="hl-grid">{comps.map(c => <li key={c.key}><ServiceCard c={c} now={now} stale={stale} onOpen={() => openService(c.key)}/></li>)}</ul>
      {data.figures && Object.keys(data.figures).length > 0 && <p className="hl-foot">{data.figures.schools_active ?? '—'} école(s) active(s) · {data.figures.sessions_open ?? '—'} session(s) ouverte(s)</p>}
      <Incidents token={token} now={now}/>
      <p className="sc-hint hl-na"><NavGlyph g="info" size={12}/> Historique conservé : 26 h par minute, 7 jours par heure. Non disponibles : disponibilité sur la durée, maintenances planifiées.</p>
    </>}
  </div>;
}

function keyFigure(c: Component, now: number): string {
  if (c.key === 'errors' && c.errors) return c.errors.active_groups ? `${c.errors.active_groups} en cours · ${c.errors.last_hour} sur 1 h` : `Aucune en cours · ${c.errors.last_24h} sur 24 h`;
  if (c.key === 'api' && c.signals?.last_5m.requests) return `${num(c.signals.last_5m.per_minute)} req/min · p95 ${p95(c.signals.last_5m)}`;
  if (c.key === 'messaging' && c.providers) { const short = (p: Provider) => p.config_state === 'CONFIGURED' ? STATE[p.state].label.toLowerCase() : SHORT_CFG[p.config_state] || p.config_state;
    const all = new Set(c.providers.map(short)); return all.size === 1 ? `SMS, e-mail, push : ${short(c.providers[0])}` : c.providers.map(p => `${p.channel} ${short(p)}`).join(' · '); }
  if (c.queue && (c.queue.pending || c.queue.failed)) return `${c.queue.pending} en attente${c.queue.oldest_seconds ? ` · plus ancien ${ago(c.queue.oldest_seconds).replace('il y a ', '')}` : ''}${c.queue.failed ? ` · ${c.queue.failed} en échec` : ''}`;
  if (c.measured_ms != null && c.key !== 'api') return `${c.measured_ms} ms`;
  if (c.age_seconds !== undefined) return `Dernier signal ${ago(c.age_seconds)}`;
  if (c.key === 'errors' && c.value != null) return `${c.value} erreur(s) / 24 h`;
  if (c.backup?.finished_at) return `${c.backup.ok ? 'Réussie' : 'Échec'} ${ago(since(c.backup.finished_at, now))}`;
  return '';
}

function ServiceCard({c, now, stale, onOpen}: {c: Component; now: number; stale: boolean; onOpen: () => void}) {
  const st = STATE[c.state] || STATE.DOWN;
  return <button type="button" className={`hl-card ${st.cls}`} onClick={onOpen} aria-label={`${c.label} : ${st.label}. ${c.detail}. Ouvrir le détail`}>
    <span className="hl-ico" aria-hidden="true"><NavGlyph g={ICON[c.key] || 'pulse'} size={20}/></span>
    <span className="hl-body"><b>{c.label}</b><em className="hl-pill"><NavGlyph g={st.icon} size={12}/>{st.label}</em>
      {keyFigure(c, now) && <span className="hl-fig">{keyFigure(c, now)}</span>}
      <small>{stale ? 'Donnée périmée' : `Mesuré ${ago(since(c.measured_at, now))}`}</small></span>
    <NavGlyph g="chevronRight" size={18}/>
  </button>;
}

const SHORT_CFG: Record<string, string> = {SIMULATED: 'simulation (jamais certifiée)', DISABLED: 'désactivé', INCOMPLETE: 'incomplet', REFUSED: 'refusé'};
const num = (x: number | null | undefined) => x == null ? '—' : x.toLocaleString('fr-FR', {maximumFractionDigits: 1});
const p95 = (x: Signals) => x.latency_p95_over ? '> 2,5 s' : x.latency_p95_ms != null ? `≤ ${x.latency_p95_ms} ms` : '—';
const pct = (x: number) => `${(x * 100).toLocaleString('fr-FR', {maximumFractionDigits: 2})} %`;
const when = (iso: string | null | undefined) => iso ? new Date(iso).toLocaleString('fr-FR', {dateStyle: 'medium', timeStyle: 'medium'}) : '—';

async function getJson<T>(url: string, token: string): Promise<T> {
  const r = await fetch(`${API}${url}`, {headers: {Authorization: `Bearer ${token}`}});
  if (!r.ok) throw new UserFacingError(r.status === 404 ? 'Groupe d’erreurs introuvable ou expiré (conservation : 7 jours).' : friendlyHttpMessage(r.status), String(r.status));
  return r.json();
}

function ServiceDetail({token, c, all, now, stale, onBack, canMessaging, onOpenMessaging}: {token: string; c: Component; all: Component[]; now: number; stale: boolean; onBack: () => void;
  canMessaging?: boolean; onOpenMessaging?: () => void}) {
  const st = STATE[c.state] || STATE.DOWN;
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => { title.current?.focus({preventScroll: true}); }, [c.key]);
  return <div className="sc-sheet-page">
    <button type="button" className="sc-back" onClick={onBack}><NavGlyph g="chevronLeft" size={18}/>État du service</button>
    <header className="sc-card sc-sheet-head"><div className="sc-sheet-id"><span className={`sc-sheet-logo hl-logo ${st.cls}`} aria-hidden="true"><NavGlyph g={ICON[c.key] || 'pulse'} size={24}/></span>
      <div><h2 ref={title} tabIndex={-1}>{c.label}</h2><p>{c.detail}</p><div className="sc-badges"><span className={`sc-badge hl-badge ${st.cls}`}><NavGlyph g={st.icon} size={12}/>{st.label}</span>
        {stale && <span className="sc-badge hl-badge hl-warn"><NavGlyph g="clock" size={12}/>Donnée périmée</span>}</div></div></div></header>
    <div className="sc-sheet-grid">
      {!c.errors && <section className="sc-card"><h3>Mesure</h3><dl className="sc-dl">
        <dt>État</dt><dd>{st.label}</dd><dt>Mesuré</dt><dd>{ago(since(c.measured_at, now))} · {new Date(c.measured_at).toLocaleString('fr-FR', {dateStyle: 'medium', timeStyle: 'medium'})}</dd>
        {c.measured_ms != null && c.key !== 'api' && <><dt>Temps de réponse</dt><dd>{c.measured_ms} ms</dd></>}
        {c.age_seconds !== undefined && <><dt>Dernier signal du service</dt><dd>{ago(c.age_seconds)}{c.age_seconds == null ? ' : le service ne s’est pas signalé' : ''}</dd></>}
        {c.started_at && <><dt>Démarré</dt><dd>{new Date(c.started_at).toLocaleString('fr-FR', {dateStyle: 'medium', timeStyle: 'short'})}</dd></>}
        {c.key === 'errors' && !c.errors && <><dt>Erreurs inattendues</dt><dd>Compteur indisponible</dd></>}
        {c.provider && <><dt>Fournisseur SMS</dt><dd>{PROVIDER[c.provider.state] || c.provider.state}</dd></>}</dl></section>}
      {c.queue && <section className="sc-card"><h3>File d’attente</h3><dl className="sc-dl">
        <dt>En attente</dt><dd>{c.queue.pending}</dd><dt>En échec</dt><dd>{c.queue.failed}{c.queue.failed ? ' (intervention requise)' : ''}</dd>
        {c.queue.oldest_seconds != null && <><dt>Plus ancien élément</dt><dd>{ago(c.queue.oldest_seconds).replace('il y a ', '')}</dd></>}</dl>
        {c.key === 'worker_communications' && canMessaging && onOpenMessaging && <button type="button" className="sc-btn sc-btn-ghost" onClick={onOpenMessaging}>Ouvrir la messagerie</button>}</section>}
      {c.backup && <section className="sc-card"><h3>Sauvegarde</h3><dl className="sc-dl">
        <dt>Dernière exécution</dt><dd>{c.backup.finished_at ? new Date(c.backup.finished_at).toLocaleString('fr-FR', {dateStyle: 'medium', timeStyle: 'short'}) : '—'}</dd>
        <dt>Résultat</dt><dd>{c.backup.ok ? 'Réussie' : 'En échec'}{c.backup.late ? ' · en retard (plus de 26 h)' : ''}</dd>
        <dt>Intégrité et restauration testée</dt><dd>{c.backup.restore_verified ? 'Vérifiées (empreintes et restauration d’essai)' : 'Non vérifiées'}</dd>
        {c.backup.restore_seconds != null && <><dt>Durée de restauration mesurée</dt><dd>{dur(c.backup.restore_seconds)} (restauration d’essai complète de cette sauvegarde)</dd></>}
        <dt>Copie hors site</dt><dd>{c.backup.offsite ? 'Oui' : 'Non'}</dd>{c.backup.message && <><dt>Détail</dt><dd>{c.backup.message}</dd></>}</dl></section>}
      {c.errors && <section className="sc-card"><h3>État actuel et historique</h3><dl className="sc-dl">
        <dt>Mesuré</dt><dd>{ago(since(c.measured_at, now))}</dd><dt>État actuel</dt><dd>{STATE[c.errors.current_state].label}{c.errors.active_groups ? ` · ${c.errors.active_groups} erreur(s) en cours` : ' · aucune erreur en cours'}</dd>
        <dt>Dernière heure</dt><dd>{c.errors.last_hour} erreur(s) inattendue(s)</dd><dt>24 dernières heures</dt><dd>{c.errors.last_24h} (historique : ne dégrade pas l’état actuel)</dd>
        {c.errors.first_active_at && <><dt>Incident commencé</dt><dd>{when(c.errors.first_active_at)}</dd></>}
        <dt>Dernière occurrence</dt><dd>{c.errors.last_at ? `${ago(since(c.errors.last_at, now))} · ${when(c.errors.last_at)}` : '—'}</dd>
        <dt>Refus attendus (24 h)</dt><dd>{c.errors.refusals_24h} · validation, mot de passe, droits, introuvable : jamais une dégradation</dd></dl>
        <p className="sc-hint">Une erreur est « en cours » pendant {Math.round(c.errors.active_window_seconds / 60)} minutes après sa dernière occurrence ; ensuite le service revient à Opérationnel et l’erreur reste dans l’historique.</p></section>}
      {c.key === 'errors' && c.errors && <ErrorGroups token={token} now={now}/>}
      {c.signals && <GoldenSignals token={token} s={c.signals}/>}
      {c.providers && <section className="sc-card"><h3>Fournisseurs</h3><ul className="hl-prov">{c.providers.map(p => { const ps = STATE[p.state];
        return <li key={p.channel}><div><b>{p.label}</b><small>{p.config_label}{p.certified === false ? ' · non certifié' : ''}</small></div>
          <span className={`sc-badge hl-badge ${ps.cls}`}><NavGlyph g={ps.icon} size={12}/>{ps.label}</span>
          <dl className="sc-dl"><dt>Dernier envoi réussi</dt><dd>{p.last_success_at ? `${ago(since(p.last_success_at, now))}` : 'Aucun sur 7 jours'}</dd>
            <dt>Dernier échec</dt><dd>{p.last_failure_at ? `${ago(since(p.last_failure_at, now))}${p.last_error_code ? ` · ${p.last_error_code}` : ''}` : 'Aucun sur 7 jours'}</dd>
            {p.failures_15m > 0 && <><dt>Échecs (15 min)</dt><dd>{p.failures_15m}</dd></>}</dl></li>; })}</ul>
        {canMessaging && onOpenMessaging && <button type="button" className="sc-btn sc-btn-ghost" onClick={onOpenMessaging}>Ouvrir la messagerie</button>}</section>}
      {c.depends_on.length > 0 && <section className="sc-card"><h3>Dépendances</h3><ul className="hl-deps">{c.depends_on.map(k => { const d = all.find(x => x.key === k); const ds = d ? STATE[d.state] : null;
        return <li key={k}><span>{d?.label || LABEL[k] || k}</span>{ds && <span className={`sc-badge hl-badge ${ds.cls}`}><NavGlyph g={ds.icon} size={12}/>{ds.label}</span>}</li>; })}</ul></section>}
    </div>
    <p className="sc-hint"><NavGlyph g="lock" size={12}/> Aucune donnée sensible n’est affichée ici (ni adresse interne, ni identifiant, ni trace technique).</p>
  </div>;
}

/** Error groups of a window, active first; a group opens its detail (first / last occurrence, correlation ids, impact). */
function ErrorGroups({token, now}: {token: string; now: number}) {
  const [win, setWin] = useState<'1h' | '24h' | '7d'>('24h');
  const [groups, setGroups] = useState<GroupRow[] | null>(null);
  const [error, setError] = useState('');
  const [open, setOpen] = useState<string | null>(() => new URLSearchParams(window.location.search).get('egroup'));
  const req = useRef(0);
  useEffect(() => { const id = ++req.current; setGroups(null); setError('');
    getJson<{groups: GroupRow[]}>(`/platform/system/health/errors?window=${win}`, token).then(b => { if (id === req.current) setGroups(b.groups); })
      .catch(e => { if (id === req.current) setError(e instanceof UserFacingError ? e.message : friendlyError(e)); }); }, [win, token, now - now % 30000]);
  function show(id: string | null) { setOpen(id); const q = new URLSearchParams(window.location.search); if (id) q.set('egroup', id); else q.delete('egroup');
    history.replaceState(history.state, '', `${window.location.pathname}?${q.toString()}`); }
  if (open) return <ErrorGroupDetail token={token} id={open} now={now} onBack={() => show(null)}/>;
  return <section className="sc-card hl-groups hl-wide"><div className="hl-groups-head"><h3>Erreurs regroupées</h3>
    <div className="hl-seg" role="group" aria-label="Période">{(['1h', '24h', '7d'] as const).map(w => <button key={w} type="button" aria-pressed={win === w} onClick={() => setWin(w)}>{w === '7d' ? '7 j' : w}</button>)}</div></div>
    {error && <p className="sc-hint" role="alert">{error}</p>}
    {!groups && !error && <div className="es-skeleton" aria-busy="true"><i/><i/></div>}
    {groups && groups.length === 0 && <p className="hl-empty"><NavGlyph g="checkCircle" size={16}/>Aucune erreur inattendue sur cette période.</p>}
    {groups && groups.length > 0 && <ul className="hl-glist">{groups.map(g => <li key={g.id}><button type="button" onClick={() => show(g.id)}>
      <span className={`sc-badge hl-badge ${g.active ? 'hl-warn' : 'hl-off'}`}>{g.active ? 'En cours' : 'Résolue'}</span>
      <span className="hl-gtxt"><b>{g.type}</b><code>{g.method} {g.route}</code><small>Code {g.status} · {win === '1h' ? g.count_1h : win === '24h' ? g.count_24h : g.count_7d ?? g.count_24h} occurrence(s) · dernière {ago(since(g.last_at, now))}</small></span>
      <NavGlyph g="chevronRight" size={16}/></button></li>)}</ul>}
  </section>;
}

type GroupDetail = GroupRow & {occurrences: {at: string; correlation_id: string; status: number; duration_ms: number}[];
  impact: {share_of_errors_24h: number | null; requests_24h: number}; audit_link: string};

function ErrorGroupDetail({token, id, now, onBack}: {token: string; id: string; now: number; onBack: () => void}) {
  const [g, setG] = useState<GroupDetail | null>(null);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');
  useEffect(() => { getJson<GroupDetail>(`/platform/system/health/errors/${encodeURIComponent(id)}`, token).then(setG)
    .catch(e => setError(e instanceof UserFacingError ? e.message : friendlyError(e))); }, [id, token, now - now % 30000]);   // follows the 30 s refresh: « En cours » becomes « Résolue » by itself
  async function copy(v: string) { try { await navigator.clipboard.writeText(v); setCopied(v); window.setTimeout(() => setCopied(''), 1800); } catch { /* copie indisponible */ } }
  return <section className="sc-card hl-gdetail hl-wide">
    <button type="button" className="sc-back" onClick={onBack}><NavGlyph g="chevronLeft" size={18}/>Erreurs regroupées</button>
    {error && <p className="sc-hint" role="alert">{error}</p>}
    {!g && !error && <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>}
    {g && <>
      <h3>{g.type} <span className={`sc-badge hl-badge ${g.active ? 'hl-warn' : 'hl-off'}`}>{g.active ? 'En cours' : 'Résolue'}</span></h3>
      <dl className="sc-dl">
        <dt>Route</dt><dd><code>{g.method} {g.route}</code></dd><dt>Code HTTP</dt><dd>{g.status}</dd>
        <dt>Message (expurgé)</dt><dd>{g.message || '—'}</dd>
        <dt>Première occurrence</dt><dd>{when(g.first_at)}</dd><dt>Dernière occurrence</dt><dd>{ago(since(g.last_at, now))} · {when(g.last_at)}</dd>
        <dt>Occurrences</dt><dd>{g.count_1h} sur 1 h · {g.count_24h} sur 24 h · {g.count_7d ?? '—'} sur 7 j</dd>
        <dt>Impact</dt><dd>{g.impact.share_of_errors_24h != null ? `${pct(g.impact.share_of_errors_24h)} des erreurs des 24 h` : '—'} · {g.impact.requests_24h} requête(s) servies sur 24 h</dd>
        <dt>Journal d’audit</dt><dd>Non disponible : une erreur serveur n’est pas une action métier journalisée</dd></dl>
      <h4>Dernières occurrences</h4>
      <ul className="hl-occ">{g.occurrences.map(o => <li key={o.correlation_id + o.at}><span>{when(o.at)}</span><span>Code {o.status} · {o.duration_ms} ms</span>
        <button type="button" className="hl-cid" onClick={() => void copy(o.correlation_id)} aria-label={`Copier la référence ${o.correlation_id}`}><code>{o.correlation_id.slice(0, 8)}</code>{copied === o.correlation_id ? ' Copiée' : ' Copier'}</button></li>)}</ul>
      <p className="sc-hint">La référence est celle affichée à l’utilisateur et inscrite dans les journaux du serveur : elle relie ce groupe à la ligne de journal complète.</p>
    </>}
  </section>;
}

type Point = {at: string; requests: number; server_errors: number; client_refusals: number; latency_p95_ms: number | null};

/** Golden signals of the API (traffic, errors, latency, saturation) and a short history. */
function GoldenSignals({token, s}: {token: string; s: NonNullable<Component['signals']>}) {
  const [span, setSpan] = useState<'1h' | '24h' | '7d'>('1h');
  const [points, setPoints] = useState<Point[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { let alive = true; setPoints(null); setError('');
    getJson<{points: Point[]}>(`/platform/system/health/history?span=${span}`, token).then(b => { if (alive) setPoints(b.points); })
      .catch(e => { if (alive) setError(e instanceof UserFacingError ? e.message : friendlyError(e)); }); return () => { alive = false; }; }, [span, token]);
  const rows: [string, Signals][] = [['5 min', s.last_5m], ['1 h', s.last_1h], ['24 h', s.last_24h]];
  const max = Math.max(1, ...(points || []).map(p => p.requests));
  return <>
    <section className="sc-card hl-wide"><h3>Signaux clés</h3>
      <div className="hl-table" role="table" aria-label="Signaux clés du serveur">
        <div role="row" className="hl-tr hl-th"><span role="columnheader">Période</span><span role="columnheader">Trafic</span><span role="columnheader">Erreurs</span><span role="columnheader">Refus attendus</span><span role="columnheader">Latence p95</span></div>
        {rows.map(([label, x]) => <div role="row" className="hl-tr" key={label}><span role="cell">{label}</span><span role="cell">{x.requests} req{x.per_minute != null ? ` · ${num(x.per_minute)}/min` : ''}</span>
          <span role="cell">{x.server_errors}{x.requests ? ` (${pct(x.error_rate)})` : ''}</span><span role="cell">{x.client_refusals}</span><span role="cell">{p95(x)}</span></div>)}
      </div>
      <dl className="sc-dl"><dt>Saturation</dt><dd>{s.saturation ? `${s.saturation.db_pool_in_use}/${s.saturation.db_pool_capacity} connexions base utilisées par ce serveur` : 'Non disponible'}</dd>
        <dt>Latence moyenne (5 min)</dt><dd>{s.last_5m.latency_avg_ms != null ? `${s.last_5m.latency_avg_ms} ms` : '—'}</dd></dl>
      <p className="sc-hint">La latence est donnée par tranche (≤ 50, 100, 250, 500 ms, 1 s, 2,5 s) : une valeur honnête plutôt qu’un chiffre faussement précis.</p></section>
    <section className="sc-card hl-wide"><div className="hl-groups-head"><h3>Historique</h3>
      <div className="hl-seg" role="group" aria-label="Période">{(['1h', '24h', '7d'] as const).map(w => <button key={w} type="button" aria-pressed={span === w} onClick={() => setSpan(w)}>{w === '7d' ? '7 j' : w}</button>)}</div></div>
      {error && <p className="sc-hint" role="alert">{error}</p>}
      {!points && !error && <div className="es-skeleton" aria-busy="true"><i/></div>}
      {points && <><div className="hl-bars" role="img" aria-label={`Requêtes et erreurs sur ${span === '7d' ? '7 jours' : span}`}>{points.map(p =>
        <span key={p.at} title={`${when(p.at)} : ${p.requests} requête(s), ${p.server_errors} erreur(s)`} style={{height: `${Math.max(2, (p.requests / max) * 100)}%`}} className={p.server_errors ? 'hl-bar-err' : ''}/>)}</div>
        <p className="hl-legend"><i className="hl-k-ok"/>Requêtes <i className="hl-k-err"/>Période avec erreur(s) inattendue(s) · {points.reduce((a, p) => a + p.requests, 0)} requête(s), {points.reduce((a, p) => a + p.server_errors, 0)} erreur(s)</p></>}
    </section>
  </>;
}

type IncidentsData = {incidents: {id: string; component_key: string; component_label: string; explain: string; opened_at: string; notified_at: string | null;
  resolved_at: string | null; resolution_notified_at: string | null; duration_seconds: number}[];
  recipients: {managers: number; can_manage: boolean; extra: {id: string; email: string; label: string | null; created_at: string}[]}; delay_seconds: number; enabled: boolean};

const dur = (s: number) => s < 90 ? `${s} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${Math.round(s / 360) / 10} h`;

/** Incidents (components « Hors service ») and who receives the alert e-mails; a Manager adds on-call addresses and sends a test. */
function Incidents({token, now}: {token: string; now: number}) {
  const [d, setD] = useState<IncidentsData | null>(null);
  const [error, setError] = useState('');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const load = useCallback(() => getJson<IncidentsData>('/platform/system/health/incidents', token).then(x => { setD(x); setError(''); })
    .catch(e => setError(e instanceof UserFacingError ? e.message : friendlyError(e))), [token]);
  useEffect(() => { void load(); }, [load, now - now % 60000]);
  async function post(url: string, body?: unknown, ok?: string) {
    setBusy(true); setNote(''); setError('');
    try {
      const r = await fetch(`${API}${url}`, {method: 'POST', headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined});
      if (!r.ok) { const j = await r.json().catch(() => ({})); throw new UserFacingError(typeof j.detail === 'string' ? j.detail : friendlyHttpMessage(r.status), String(r.status)); }
      if (ok) setNote(ok);
      await load(); return true;
    } catch (e) { setError(e instanceof UserFacingError ? e.message : friendlyError(e)); return false; }
    finally { setBusy(false); }
  }
  const open = d?.incidents.filter(i => !i.resolved_at) || [];
  return <section className="sc-card hl-incidents" aria-label="Incidents et alertes">
    <div className="hl-groups-head"><h3>Incidents et alertes</h3>{d && <span className={`sc-badge hl-badge ${open.length ? 'hl-bad' : 'hl-ok'}`}><NavGlyph g={open.length ? 'alert' : 'checkCircle'} size={12}/>{open.length ? `${open.length} en cours` : 'Aucun incident en cours'}</span>}</div>
    {error && <p className="sc-hint" role="alert">{error}</p>}
    {!d && !error && <div className="es-skeleton" aria-busy="true"><i/><i/></div>}
    {d && <>
      <p className="sc-hint">Un service « Hors service » plus de {Math.round(d.delay_seconds / 60)} minutes déclenche un e-mail aux destinataires ci-dessous, puis un second à la résolution.{d.enabled ? '' : ' Les alertes sont désactivées sur ce serveur.'}</p>
      {d.incidents.length === 0 ? <p className="hl-empty"><NavGlyph g="checkCircle" size={16}/>Aucun incident enregistré.</p> :
        <ul className="hl-inc">{d.incidents.slice(0, 10).map(i => <li key={i.id}>
          <span className={`sc-badge hl-badge ${i.resolved_at ? 'hl-off' : 'hl-bad'}`}>{i.resolved_at ? 'Résolu' : 'En cours'}</span>
          <span className="hl-gtxt"><b>{i.component_label}</b><small>{when(i.opened_at)} · durée {dur(i.duration_seconds)}{i.notified_at ? ' · alerte envoyée' : ' · sans alerte (moins de 5 min)'}</small>
            {!i.resolved_at && <small>{i.explain}</small>}</span></li>)}</ul>}
      <h4>Destinataires des alertes</h4>
      <ul className="hl-recip"><li><NavGlyph g="users" size={14}/>{d.recipients.managers} Manager(s) Système actif(s) (toujours prévenus)</li>
        {d.recipients.extra.map(x => <li key={x.id}><NavGlyph g="message" size={14}/><span>{x.email}{x.label ? ` · ${x.label}` : ''}</span>
          {d.recipients.can_manage && <button type="button" className="sc-btn sc-btn-ghost hl-sm" disabled={busy} onClick={() => void post(`/platform/system/health/alert-recipients/${x.id}/remove`, undefined, 'Adresse retirée.')}>Retirer</button>}</li>)}</ul>
      {d.recipients.can_manage && <form className="hl-addr" onSubmit={async e => { e.preventDefault(); if (await post('/platform/system/health/alert-recipients', {email: email.trim()}, 'Adresse ajoutée : elle recevra les prochaines alertes.')) setEmail(''); }}>
        <label htmlFor="hl-addr">Ajouter une adresse d’astreinte</label>
        <div><input id="hl-addr" type="email" inputMode="email" autoComplete="email" placeholder="nom@exemple.com" value={email} onChange={e => setEmail(e.target.value)} required/>
          <button className="sc-btn" disabled={busy || !email.includes('@')}>Ajouter</button></div>
        <button type="button" className="sc-btn sc-btn-ghost" disabled={busy} onClick={() => void post('/platform/system/health/alerts/test', undefined, 'E-mail de test envoyé à tous les destinataires.')}>Envoyer un e-mail de test</button>
      </form>}
      {note && <p className="hl-empty" role="status"><NavGlyph g="checkCircle" size={16}/>{note}</p>}
    </>}
  </section>;
}
