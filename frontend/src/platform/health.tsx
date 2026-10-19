import React, {useCallback, useEffect, useRef, useState} from 'react';
import {friendlyError, UserFacingError, friendlyHttpMessage} from './errors';
import {NavGlyph} from './nav_icons';
import './schools.css';
import './health.css';

/* État du service (Plateforme EduSync), lot 2026-10. Real measurements only (latency, heartbeats, queues, counters, the
   backup report); a component that is not configured says so, never « Opérationnel ». The page refreshes every 30 s
   while it is visible (paused in a background tab), never lets an older answer overwrite a newer one, and flags data
   older than two refresh periods as stale. « Mesurer maintenant » is disabled while a measure runs and for a short
   cooldown; the server also shares one measurement between concurrent requests. */

type State = 'OK' | 'DEGRADED' | 'DOWN' | 'NOT_CONFIGURED';
type Component = {key: string; label: string; state: State; detail: string; measured_ms: number | null; measured_at: string; age_seconds?: number | null;
  queue?: {pending: number; failed: number; oldest_seconds: number | null}; provider?: {state: string}; value?: number | null; started_at?: string;
  backup?: {finished_at: string | null; ok: boolean; late: boolean; restore_verified: boolean; offsite: boolean; message: string}; depends_on: string[]};
type Health = {checked_at: string; overall: State; components: Component[]; refresh_seconds: number; shared: boolean;
  summary: {operational: number; configured: number; degraded: number; down: number; not_configured: number}; figures: Record<string, number | null>};

const API = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const STATE: Record<State, {label: string; cls: string; icon: string}> = {
  OK: {label: 'Opérationnel', cls: 'hl-ok', icon: 'checkCircle'}, DEGRADED: {label: 'Dégradé', cls: 'hl-warn', icon: 'alert'},
  DOWN: {label: 'Hors service', cls: 'hl-bad', icon: 'alert'}, NOT_CONFIGURED: {label: 'Non configuré', cls: 'hl-off', icon: 'info'},
};
const OVERALL: Record<State, string> = {OK: 'Tous les services fonctionnent normalement', DEGRADED: 'Certains services sont dégradés',
  DOWN: 'Incident en cours : au moins un service est hors service', NOT_CONFIGURED: 'Aucun service mesurable'};
const ICON: Record<string, string> = {api: 'cockpit', database: 'database', redis: 'layers', worker_outbox: 'sync', worker_communications: 'message', storage: 'folder', errors: 'alert', backup: 'cloudUp'};
/** Priority order (also the phone order): server, database, events, backup, storage, SMS, cache, errors. */
const ORDER = ['api', 'database', 'worker_outbox', 'backup', 'storage', 'worker_communications', 'redis', 'errors'];
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
  if (current && data) return <ServiceDetail c={current} all={comps} now={now} stale={stale} onBack={closeService} canMessaging={canMessaging} onOpenMessaging={onOpenMessaging}/>;
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
      <ul className="hl-grid">{comps.map(c => <li key={c.key}><ServiceCard c={c} now={now} stale={stale} onOpen={() => openService(c.key)}/></li>)}</ul>
      {data.figures && Object.keys(data.figures).length > 0 && <p className="hl-foot">{data.figures.schools_active ?? '—'} école(s) active(s) · {data.figures.sessions_open ?? '—'} session(s) ouverte(s)</p>}
      <p className="sc-hint hl-na"><NavGlyph g="info" size={12}/> Non disponibles (aucun historique conservé) : disponibilité sur la durée, historique, incidents et maintenances planifiées.</p>
    </>}
  </div>;
}

function keyFigure(c: Component, now: number): string {
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

function ServiceDetail({c, all, now, stale, onBack, canMessaging, onOpenMessaging}: {c: Component; all: Component[]; now: number; stale: boolean; onBack: () => void;
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
      <section className="sc-card"><h3>Mesure</h3><dl className="sc-dl">
        <dt>État</dt><dd>{st.label}</dd><dt>Mesuré</dt><dd>{ago(since(c.measured_at, now))} · {new Date(c.measured_at).toLocaleString('fr-FR', {dateStyle: 'medium', timeStyle: 'medium'})}</dd>
        {c.measured_ms != null && c.key !== 'api' && <><dt>Temps de réponse</dt><dd>{c.measured_ms} ms</dd></>}
        {c.age_seconds !== undefined && <><dt>Dernier signal du service</dt><dd>{ago(c.age_seconds)}{c.age_seconds == null ? ' : le service ne s’est pas signalé' : ''}</dd></>}
        {c.started_at && <><dt>Démarré</dt><dd>{new Date(c.started_at).toLocaleString('fr-FR', {dateStyle: 'medium', timeStyle: 'short'})}</dd></>}
        {c.key === 'errors' && <><dt>Erreurs inattendues (24 h)</dt><dd>{c.value ?? 'Compteur indisponible'}</dd></>}
        {c.provider && <><dt>Fournisseur SMS</dt><dd>{PROVIDER[c.provider.state] || c.provider.state}</dd></>}</dl></section>
      {c.queue && <section className="sc-card"><h3>File d’attente</h3><dl className="sc-dl">
        <dt>En attente</dt><dd>{c.queue.pending}</dd><dt>En échec</dt><dd>{c.queue.failed}{c.queue.failed ? ' (intervention requise)' : ''}</dd>
        {c.queue.oldest_seconds != null && <><dt>Plus ancien élément</dt><dd>{ago(c.queue.oldest_seconds).replace('il y a ', '')}</dd></>}</dl>
        {c.key === 'worker_communications' && canMessaging && onOpenMessaging && <button type="button" className="sc-btn sc-btn-ghost" onClick={onOpenMessaging}>Ouvrir la messagerie</button>}</section>}
      {c.backup && <section className="sc-card"><h3>Sauvegarde</h3><dl className="sc-dl">
        <dt>Dernière exécution</dt><dd>{c.backup.finished_at ? new Date(c.backup.finished_at).toLocaleString('fr-FR', {dateStyle: 'medium', timeStyle: 'short'}) : '—'}</dd>
        <dt>Résultat</dt><dd>{c.backup.ok ? 'Réussie' : 'En échec'}{c.backup.late ? ' · en retard (plus de 26 h)' : ''}</dd>
        <dt>Intégrité et restauration testée</dt><dd>{c.backup.restore_verified ? 'Vérifiées (empreintes et restauration d’essai)' : 'Non vérifiées'}</dd>
        <dt>Copie hors site</dt><dd>{c.backup.offsite ? 'Oui' : 'Non'}</dd>{c.backup.message && <><dt>Détail</dt><dd>{c.backup.message}</dd></>}</dl></section>}
      {c.depends_on.length > 0 && <section className="sc-card"><h3>Dépendances</h3><ul className="hl-deps">{c.depends_on.map(k => { const d = all.find(x => x.key === k); const ds = d ? STATE[d.state] : null;
        return <li key={k}><span>{d?.label || LABEL[k] || k}</span>{ds && <span className={`sc-badge hl-badge ${ds.cls}`}><NavGlyph g={ds.icon} size={12}/>{ds.label}</span>}</li>; })}</ul></section>}
    </div>
    <p className="sc-hint"><NavGlyph g="lock" size={12}/> Aucune donnée sensible n’est affichée ici (ni adresse interne, ni identifiant, ni trace technique).</p>
  </div>;
}
