import {OnlineActionButton} from './online_action';
import {PageTrail} from './navigation';
// Plateforme EduSync — Messagerie : centre d'exploitation des canaux (lot 2026-10).
// Cartes cliquables (push, e-mail, SMS, file d'envoi, échecs actifs) à valeur centrée ; état COURANT de chaque fournisseur
// (une erreur résolue reste dans l'historique sans dégrader l'état) ; explorateur de la file avec filtres serveur et
// pagination ; diagnostic d'un envoi (tentatives, codes, identifiants) et relance motivée ; portefeuilles SMS en grand
// livre (solde, réservé, disponible, recharge payée, ajustement séparé). Jamais le corps d'un message d'école, jamais un
// secret, destinataires masqués par le serveur. Mutations en ligne uniquement.
import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {toast} from 'sonner';
import {friendlyError, UserFacingError} from './errors';
import {NavGlyph} from './nav_icons';
import {promptText} from './dialogs';
import {getConnectivity, subscribeConnectivity} from './connectivity';
import {disablePush, enablePush, pushSupport, rememberedSubscription} from '../push_client';
import {pushDevices, type PushDevice} from '../messaging_api';
import {
  CHANNEL_LABEL, EVENT_LABEL, MOVEMENT_LABEL, STATUS_LABEL, adjustWallet, creditWallet, getDelivery, getLedger, getStatus, listDeliveries, listWallets,
  requestHealthCheck, retryDelivery, testSend, testStatus,
  type Channel, type DeliveryDetail, type DeliveryRow, type Filters, type LedgerRow, type ProviderState, type Status, type Wallet,
} from './messaging_api';
import './schools.css';
import './messaging.css';

const STATE: Record<ProviderState, {label: string; cls: string; icon: string}> = {
  OPERATIONAL: {label: 'Opérationnel', cls: 'ms-ok', icon: 'checkCircle'}, CONFIGURED: {label: 'Configuré', cls: 'ms-info', icon: 'info'},
  DEGRADED: {label: 'Dégradé', cls: 'ms-warn', icon: 'alert'}, UNAVAILABLE: {label: 'Indisponible', cls: 'ms-bad', icon: 'alert'},
  NOT_CONFIGURED: {label: 'Non configuré', cls: 'ms-off', icon: 'minus'},
};
const ICON: Record<string, string> = {PUSH: 'bell', EMAIL: 'message', SMS: 'phone'};
const ST_CLS: Record<string, string> = {SENT: 'ms-ok', DELIVERED: 'ms-ok', QUEUED: 'ms-info', PROCESSING: 'ms-info', FAILED_RETRYABLE: 'ms-warn',
  FAILED_PERMANENT: 'ms-bad', CANCELLED: 'ms-off'};
const when = (iso?: string | null) => iso ? new Date(iso).toLocaleString('fr-FR', {dateStyle: 'short', timeStyle: 'medium'}) : '—';
const ago = (iso?: string | null, now = Date.now()) => {
  if (!iso) return 'jamais';
  const s = Math.round((now - new Date(iso).getTime()) / 1000);
  return s < 60 ? `il y a ${Math.max(0, s)} s` : s < 3600 ? `il y a ${Math.round(s / 60)} min` : s < 172800 ? `il y a ${Math.round(s / 3600)} h` : `il y a ${Math.round(s / 86400)} j`;
};
const n = (v: number | null | undefined) => (v ?? 0).toLocaleString('fr-FR');
type View = {kind: 'home'} | {kind: 'channel'; channel: string} | {kind: 'deliveries'; filters: Filters} | {kind: 'delivery'; id: string} | {kind: 'wallet'; id: string};

function readView(): View {
  const p = new URLSearchParams(window.location.search);
  const m = p.get('msg') || '';
  if (m.startsWith('channel:')) return {kind: 'channel', channel: m.slice(8)};
  if (m.startsWith('delivery:')) return {kind: 'delivery', id: m.slice(9)};
  if (m.startsWith('wallet:')) return {kind: 'wallet', id: m.slice(7)};
  if (m === 'deliveries') return {kind: 'deliveries', filters: Object.fromEntries(['channel', 'status', 'scope', 'event', 'date_from', 'date_to', 'q'].map(k => [k, p.get(`m_${k}`) || undefined]).filter(([, v]) => v)) as Filters};
  return {kind: 'home'};
}
function writeView(v: View, push = true) {
  const p = new URLSearchParams();
  if (v.kind === 'channel') p.set('msg', `channel:${v.channel}`);
  if (v.kind === 'delivery') p.set('msg', `delivery:${v.id}`);
  if (v.kind === 'wallet') p.set('msg', `wallet:${v.id}`);
  if (v.kind === 'deliveries') { p.set('msg', 'deliveries'); Object.entries(v.filters).forEach(([k, val]) => val && p.set(`m_${k}`, String(val))); }
  const url = `${window.location.pathname}${p.toString() ? `?${p}` : ''}`;
  if (push) history.pushState({...(history.state || {}), msg: true}, '', url); else history.replaceState(history.state, '', url);
}
function useOnline() { const [on, setOn] = useState(getConnectivity().state !== 'OFFLINE'); useEffect(() => subscribeConnectivity(s => setOn(s.state !== 'OFFLINE')), []); return on; }

export default function PlatformMessaging({token, canCredit, canAdjust = false, canRetry = false}: {token: string; canCredit: boolean; canAdjust?: boolean; canRetry?: boolean}) {
  const [view, setView] = useState<View>(readView);
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState('');
  const [now, setNow] = useState(Date.now());
  const [busy, setBusy] = useState(false);
  const reqId = useRef(0);
  const online = useOnline();
  const load = useCallback(async () => {
    const id = ++reqId.current;
    try { const s = await getStatus(token); if (id === reqId.current) { setStatus(s); setError(''); } }
    catch (e) { if (id === reqId.current) setError(e instanceof UserFacingError ? e.message : friendlyError(e)); }
  }, [token]);
  useEffect(() => {
    void load();
    const t = window.setInterval(() => setNow(Date.now()), 5000);
    const poll = window.setInterval(() => { if (document.visibilityState === 'visible') void load(); }, 30_000);
    return () => { window.clearInterval(t); window.clearInterval(poll); };
  }, [load]);
  useEffect(() => { const h = () => setView(readView()); window.addEventListener('popstate', h); return () => window.removeEventListener('popstate', h); }, []);
  const go = (v: View) => { writeView(v); setView(v); window.scrollTo(0, 0); };
  const back = () => { if (history.state?.msg) history.back(); else go({kind: 'home'}); };
  async function measure() {
    if (!online) return;
    setBusy(true);
    try {
      const r = await requestHealthCheck(token);
      toast.message(r.requested ? 'Contrôle réel des fournisseurs demandé (aucun message envoyé)' : (r.detail || 'Contrôle déjà demandé'));
      const before = status?.health_checked_at;
      for (let i = 0; i < 12; i++) { await new Promise(res => setTimeout(res, 2500)); const s = await getStatus(token); setStatus(s); if (s.health_checked_at !== before) break; }
    } catch (e) { toast.error(e instanceof UserFacingError ? e.message : friendlyError(e)); } finally { setBusy(false); }
  }
  if (view.kind === 'delivery') return <DeliveryPage token={token} id={view.id} online={online} canRetry={canRetry} onBack={back}/>;
  if (view.kind === 'wallet') return <WalletPage token={token} id={view.id} online={online} canCredit={canCredit} canAdjust={canAdjust} onBack={back}/>;
  if (view.kind === 'deliveries') return <DeliveriesPage token={token} initial={view.filters} onBack={back} onOpen={id => go({kind: 'delivery', id})}
    onFilters={f => writeView({kind: 'deliveries', filters: f}, false)}/>;
  const channel = view.kind === 'channel' ? status?.channels.find(c => c.channel === view.channel) : undefined;
  if (view.kind === 'channel' && channel && status) return <ChannelPage token={token} c={channel} now={now} online={online} onBack={back}
    onDeliveries={f => go({kind: 'deliveries', filters: f})} onMeasure={measure} busy={busy}/>;
  return <div className="sc ms">
    <header className="sc-head"><div><h2>Messagerie</h2><p>Fournisseurs push, e-mail et SMS, file d’envoi, échecs, portefeuilles SMS des écoles. Jamais le contenu des messages des écoles.</p></div>
      <div className="sc-head-actions"><button type="button" className="sc-btn sc-btn-ghost" onClick={() => void measure()} disabled={busy || !online}>
        <NavGlyph g="sync" size={16}/><span>{busy ? 'Contrôle en cours…' : 'Contrôler les fournisseurs'}</span></button></div></header>
    {!online && <div className="es-alert es-alert-warn" role="status"><NavGlyph g="wifiOff" size={16}/><span>Hors connexion — tests, relances et mouvements de portefeuille indisponibles.</span></div>}
    {error && <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Messagerie indisponible.</b><small>{error}</small></div>
      <button type="button" className="sc-btn sc-btn-ghost" onClick={() => void load()}>Réessayer</button></div>}
    {!status && !error && <div className="ms-kpis" aria-busy="true">{Array.from({length: 5}).map((_, i) => <div key={i} className="ms-kpi ms-skel"><i className="sc-skel" style={{width: '40%'}}/><i className="sc-skel" style={{width: '60%'}}/></div>)}</div>}
    {status && <>
      <ul className="ms-kpis" aria-label="Canaux et file d’envoi">
        {status.channels.map(c => { const st = STATE[c.state]; const sent = (c.volumes_24h.SENT || 0) + (c.volumes_24h.DELIVERED || 0);
          return <li key={c.channel}><button type="button" className={`ms-kpi ${st.cls}`} onClick={() => go({kind: 'channel', channel: c.channel})}
            aria-label={`${CHANNEL_LABEL[c.channel]} : ${st.label}. ${n(sent)} envoi(s) réussi(s) sur 24 h. ${c.reasons[0] || ''}. Ouvrir le détail`}>
            <span className="ms-kpi-ico" aria-hidden="true"><NavGlyph g={ICON[c.channel]} size={18}/></span>
            <b className="ms-kpi-val">{n(sent)}</b><span className="ms-kpi-lbl">{CHANNEL_LABEL[c.channel]}<small>envois réussis 24 h</small></span>
            <em className="ms-pill"><NavGlyph g={st.icon} size={12}/>{st.label}</em></button></li>; })}
        <li><button type="button" className={`ms-kpi ${status.queue.worker_state !== 'OK' ? 'ms-bad' : (status.queue.due || 0) > 0 ? 'ms-info' : 'ms-ok'}`}
          onClick={() => go({kind: 'deliveries', filters: {status: 'BACKLOG'}})} aria-label={`File d’envoi : ${status.queue.due} en attente. Ouvrir les envois en attente`}>
          <span className="ms-kpi-ico" aria-hidden="true"><NavGlyph g="layers" size={18}/></span>
          <b className="ms-kpi-val">{n((status.queue.due || 0) + (status.queue.processing || 0))}</b><span className="ms-kpi-lbl">File d’envoi<small>en attente</small></span>
          <em className="ms-pill"><NavGlyph g={status.queue.worker_state === 'OK' ? 'checkCircle' : 'alert'} size={12}/>{status.queue.worker_state === 'OK' ? 'Worker actif' : status.queue.worker_state === 'LATE' ? 'Worker en retard' : 'Worker arrêté'}</em></button></li>
        <li><button type="button" className={`ms-kpi ${status.queue.failed_15m > 0 ? 'ms-bad' : (status.queue.dead_7d + status.queue.retrying) > 0 ? 'ms-warn' : 'ms-ok'}`}
          onClick={() => go({kind: 'deliveries', filters: {status: 'ACTIVE_FAILURES'}})} aria-label={`Échecs : ${status.queue.dead_7d} définitifs sur 7 jours, ${status.queue.retrying} en nouvel essai. Ouvrir les échecs`}>
          <span className="ms-kpi-ico" aria-hidden="true"><NavGlyph g="alert" size={18}/></span>
          <b className="ms-kpi-val">{n(status.queue.dead_7d + status.queue.retrying)}</b><span className="ms-kpi-lbl">Échecs<small>7 j et nouveaux essais</small></span>
          <em className="ms-pill"><NavGlyph g={status.queue.failed_15m ? 'alert' : 'checkCircle'} size={12}/>{status.queue.failed_15m ? `${status.queue.failed_15m} en cours` : 'Aucun en cours'}</em></button></li>
      </ul>
      <p className="ms-fresh"><NavGlyph g="clock" size={12}/> Contrôle réel des fournisseurs : {status.health_checked_at ? ago(status.health_checked_at, now) : 'pas encore effectué'} · état {ago(status.measured_at, now)} · actualisation automatique toutes les 30 s</p>
      <button type="button" className="ms-link" onClick={() => go({kind: 'deliveries', filters: {}})}><NavGlyph g="search" size={14}/>Rechercher dans tous les envois<NavGlyph g="chevronRight" size={14}/></button>
      <Wallets token={token} onOpen={id => go({kind: 'wallet', id})}/>
    </>}
  </div>;
}

/* ------------------------------------------------------------------------------------------------ channel detail */
function ChannelPage({token, c, now, online, onBack, onDeliveries, onMeasure, busy}: {token: string; c: Channel; now: number; online: boolean; onBack: () => void;
  onDeliveries: (f: Filters) => void; onMeasure: () => Promise<void>; busy: boolean}) {
  const st = STATE[c.state];
  const [testing, setTesting] = useState(false);
  async function test() {
    if (c.channel === 'SMS' || !online) return;
    setTesting(true);
    try {
      const r = await testSend(token, c.channel as 'EMAIL' | 'PUSH');
      toast.message(c.channel === 'EMAIL' ? 'E-mail de test mis en file vers votre adresse' : 'Push de test mis en file vers vos appareils');
      for (let i = 0; i < 20; i++) {
        await new Promise(res => setTimeout(res, 1500));
        const fin = (await testStatus(token, r.message_id)).items.find(x => ['SENT', 'DELIVERED', 'FAILED_PERMANENT', 'CANCELLED'].includes(x.status));
        if (fin) { (fin.status === 'SENT' || fin.status === 'DELIVERED' ? toast.success : toast.error)(`Test : ${STATUS_LABEL[fin.status]}${fin.last_error_code ? ` (${fin.last_error_code})` : ''}${fin.status === 'SENT' ? ' — vérifiez la réception' : ''}`); return; }
      }
      toast.message('Test toujours en file : vérifiez le worker');
    } catch (e) { toast.error(e instanceof UserFacingError ? e.message : friendlyError(e)); } finally { setTesting(false); }
  }
  const cfg = c.health?.config || {};
  const cfgRows: [string, string][] = c.channel === 'EMAIL' ? [['Serveur', cfg.host ? `${cfg.host}:${cfg.port}` : '—'], ['Chiffrement', String(cfg.security || '—').toUpperCase()],
    ['Identifiant SMTP', cfg.username_configured ? 'Présent' : 'Absent'], ['Mot de passe SMTP', cfg.password_configured ? 'Présent (jamais affiché)' : 'Absent'],
    ['Expéditeur', cfg.from_configured ? `Configuré${cfg.from_name ? ` (${cfg.from_name})` : ''}` : 'Absent']]
    : c.channel === 'PUSH' ? [['Compte de service', cfg.credential_source === 'file' ? `Fichier monté${cfg.credential_file_readable ? '' : ' — illisible'}` : cfg.credential_source === 'json' ? 'Secret injecté' : 'Absent'],
      ['Projet Firebase', c.health?.project_id || '—']]
    : [['Identifiants', cfg.client_configured ? 'Présents (jamais affichés)' : 'Absents'], ['Expéditeur', cfg.sender_configured ? 'Configuré' : 'Absent']];
  return <div className="sc-sheet-page ms">
    <PageTrail parents={[{label: 'Messagerie', onSelect: onBack}]} current={CHANNEL_LABEL[c.channel] || 'Canal'}/>
    <header className="sc-card sc-sheet-head"><div className="sc-sheet-id"><span className={`sc-sheet-logo ms-logo ${st.cls}`} aria-hidden="true"><NavGlyph g={ICON[c.channel]} size={24}/></span>
      <div><h2>{CHANNEL_LABEL[c.channel]} — {c.provider_label}</h2><p>{c.reasons.join(' · ')}</p>
        <div className="sc-badges"><span className={`sc-badge ms-badge ${st.cls}`}><NavGlyph g={st.icon} size={12}/>{st.label}</span>
          {c.simulated && <span className="sc-badge ms-badge ms-off">Simulation — jamais certifié</span>}</div></div></div></header>
    <div className="sc-sheet-grid">
      <section className="sc-card"><h3>État actuel</h3><dl className="sc-dl">
        <dt>Contrôle réel du fournisseur</dt><dd>{c.health ? `${c.health.ok === true ? 'Réussi' : c.health.ok === false ? `Échec (${c.health.error_code})` : 'Non applicable'} · ${ago(c.health.checked_at, now)}${c.health.fresh ? '' : ' (périmé)'}` : 'Pas encore effectué'}</dd>
        {c.health?.latency_ms != null && <><dt>Temps de réponse</dt><dd>{c.health.latency_ms} ms</dd></>}
        <dt>Dernier envoi réussi</dt><dd>{c.last_success_at ? `${ago(c.last_success_at, now)} · ${when(c.last_success_at)}` : 'Aucun'}</dd>
        <dt>Dernier échec (historique)</dt><dd>{c.last_failure_at ? `${ago(c.last_failure_at, now)}${c.last_failure_code ? ` · ${c.last_failure_code}` : ''}` : 'Aucun'}</dd>
        <dt>En attente / nouvel essai</dt><dd>{n(c.backlog)} / {n(c.retrying)}{c.oldest_due_seconds ? ` · plus ancien ${Math.round(c.oldest_due_seconds / 60)} min` : ''}</dd>
        <dt>Échecs définitifs (7 j)</dt><dd>{n(c.dead_7d)}</dd>
        <dt>Dernier test réel</dt><dd>{c.last_test ? `${STATUS_LABEL[c.last_test.status] || c.last_test.status} · ${ago(c.last_test.at, now)}${c.last_test.provider_proof ? ' · preuve du fournisseur' : ''}${c.last_test.error_code ? ` · ${c.last_test.error_code}` : ''}` : 'Aucun'}</dd></dl>
        <p className="sc-hint">Une erreur ancienne (plus de 15 min) reste dans l’historique sans dégrader l’état. « Distribué » n’est affiché que sur preuve du fournisseur.</p>
        <div className="ms-actions">
          <button type="button" className="sc-btn sc-btn-ghost" onClick={() => void onMeasure()} disabled={busy || !online}><NavGlyph g="sync" size={16}/>{busy ? 'Contrôle…' : 'Contrôler maintenant'}</button>
          {c.channel !== 'SMS' && <button type="button" className="sc-btn" onClick={() => void test()} disabled={testing || !online}>{testing ? 'Test en cours…' : c.channel === 'EMAIL' ? 'M’envoyer un e-mail de test' : 'Envoyer un push à mes appareils'}</button>}
        </div></section>
      {c.channel === 'PUSH' && <ThisDevice token={token} online={online}/>}
      {c.diagnostics && (c.diagnostics.api.length > 0 || c.diagnostics.worker.length > 0) && <section className="sc-card ms-wide"><h3>Diagnostic de configuration</h3>
        <div className="ms-diag">{([['Serveur API', c.diagnostics.api], ['Worker d’envoi', c.diagnostics.worker]] as const).map(([side, list]) => <div key={side}>
          <h4>{side}</h4>{list.length === 0 ? <p className="sc-hint">Aucun contrôle publié (worker arrêté ou ancienne version).</p> :
          <ul>{list.map(x => <li key={x.name} className={x.ok ? 'ms-dok' : x.ok === false ? 'ms-dko' : ''}><NavGlyph g={x.ok ? 'checkCircle' : x.ok === false ? 'alert' : 'info'} size={14}/>
            <span><code>{x.name}</code><small>{x.detail}</small></span></li>)}</ul>}</div>)}</div>
        <p className="sc-hint">Noms de variables et résultats seulement : aucune valeur n’est jamais transmise. Les deux processus doivent recevoir la configuration.</p></section>}
      <section className="sc-card"><h3>Configuration (sans secret)</h3><dl className="sc-dl">
        <dt>Fournisseur</dt><dd>{c.provider_label}</dd>{cfgRows.map(([k, v]) => <React.Fragment key={k}><dt>{k}</dt><dd>{v}</dd></React.Fragment>)}</dl>
        <p className="sc-hint">Les secrets restent sur le serveur, avec le worker d’envoi ; ils ne sont jamais affichés ni modifiables ici.</p></section>
      <section className="sc-card ms-wide"><h3>Volumes 24 h</h3>
        <div className="ms-mini">{Object.keys(STATUS_LABEL).map(s => <button type="button" key={s} className={`ms-mini-i ${ST_CLS[s]}`} onClick={() => onDeliveries({channel: c.channel, status: s})}>
          <b>{n(c.volumes_24h[s])}</b><span>{STATUS_LABEL[s]}</span></button>)}</div></section>
    </div>
  </div>;
}

/** Push on this device for the platform account: explicit action (permission prompt only on click), token sent once to
    the server (stored encrypted), never shown nor kept in the browser. Needed to receive the real test push. */
function ThisDevice({token, online}: {token: string; online: boolean}) {
  const support = pushSupport();
  const [active, setActive] = useState(false);
  const [devices,setDevices]=useState<PushDevice[]>([]);
  useEffect(()=>{let alive=true;if(online)void pushDevices(token,true).then(r=>{if(alive){setDevices(r.items);setActive(r.items.some(d=>d.id===rememberedSubscription('platform')))}}).catch(()=>{});return()=>{alive=false}},[token,online]);
  const [busy, setBusy] = useState(false);
  async function on() { setBusy(true); try { const r = await enablePush(token, 'platform', true); setActive(true);
    void pushDevices(token,true).then(result=>setDevices(result.items)).catch(()=>{});
    toast.success(r.simulated ? 'Notifications activées (mode développement simulé)' : 'Notifications activées sur cet appareil'); }
    catch (e) { toast.error(e instanceof Error ? e.message : friendlyError(e)); } finally { setBusy(false); } }
  async function off() { setBusy(true); try { await disablePush(token, 'platform', true); setActive(false); toast.success('Notifications désactivées sur cet appareil'); }
    catch(e){toast.error(friendlyError(e));}
    finally { setBusy(false); } }
  return <section className="sc-card"><h3>Notifications sur cet appareil</h3>
    <p className="sc-hint">{!support.supported ? support.reason : active ? 'Cet appareil est enregistré. Envoyez un push de test pour vérifier sa réception.' : 'Activez-les pour recevoir le push de test et les alertes sur ce téléphone ou cet ordinateur.'}</p>
    {devices.length>0&&<p className="sc-hint">Appareils actifs confirmés par le serveur : {devices.length}.</p>}
    {support.supported && <div className="ms-actions">{active
      ? <OnlineActionButton type="button" className="sc-btn sc-btn-ghost" onClick={() => void off()} disabled={busy}>Désactiver sur cet appareil</OnlineActionButton>
      : <button type="button" className="sc-btn" onClick={() => void on()} disabled={busy || !online}><NavGlyph g="bell" size={16}/>{busy ? 'Activation…' : 'Activer sur cet appareil'}</button>}</div>}
  </section>;
}

/* ------------------------------------------------------------------------------------------------ deliveries explorer */
const FILTER_LABEL: Record<string, string> = {ACTIVE_FAILURES: 'Échecs actifs', BACKLOG: 'En attente'};

function DeliveriesPage({token, initial, onBack, onOpen, onFilters}: {token: string; initial: Filters; onBack: () => void; onOpen: (id: string) => void; onFilters: (f: Filters) => void}) {
  const [f, setF] = useState<Filters>(initial);
  const [q, setQ] = useState(initial.q || '');
  const [items, setItems] = useState<DeliveryRow[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [more, setMore] = useState(false);
  const [sheet, setSheet] = useState(false);
  const ctl = useRef<AbortController | null>(null);
  useEffect(() => { const t = window.setTimeout(() => setF(x => (x.q || '') === q.trim() ? x : {...x, q: q.trim() || undefined}), 350); return () => window.clearTimeout(t); }, [q]);
  useEffect(() => {
    onFilters(f); ctl.current?.abort(); const c = new AbortController(); ctl.current = c; setItems(null); setError('');
    listDeliveries(token, f, null, 25, c.signal).then(r => { setItems(r.items); setCursor(r.next_cursor); })
      .catch(e => { if ((e as Error).name !== 'AbortError') setError(e instanceof UserFacingError ? e.message : friendlyError(e)); });
    return () => c.abort();
  }, [token, JSON.stringify(f)]);
  async function loadMore() { if (!cursor) return; setMore(true); try { const r = await listDeliveries(token, f, cursor); setItems(x => [...(x || []), ...r.items]); setCursor(r.next_cursor); } catch (e) { toast.error(friendlyError(e)); } finally { setMore(false); } }
  const set = (k: keyof Filters, v?: string) => setF(x => ({...x, [k]: v || undefined}));
  const chips = Object.entries(f).filter(([k, v]) => v && k !== 'q') as [keyof Filters, string][];
  const controls = <>
    <label className="ms-f"><span>Canal</span><select value={f.channel || ''} onChange={e => set('channel', e.target.value)}><option value="">Tous</option><option value="EMAIL">E-mail</option><option value="PUSH">Push</option><option value="SMS">SMS</option></select></label>
    <label className="ms-f"><span>État</span><select value={f.status || ''} onChange={e => set('status', e.target.value)}><option value="">Tous</option><option value="ACTIVE_FAILURES">Échecs actifs</option><option value="BACKLOG">En attente</option>
      {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
    <label className="ms-f"><span>Origine</span><select value={f.scope || ''} onChange={e => set('scope', e.target.value)}><option value="">Toutes</option><option value="PLATFORM">Plateforme et comptes</option><option value="SCHOOL">Écoles</option></select></label>
    <label className="ms-f"><span>Événement</span><select value={f.event || ''} onChange={e => set('event', e.target.value)}><option value="">Tous</option>
      {['ACCOUNT_INVITATION', 'ACCOUNT_PASSWORD_RESET', 'ACCOUNT_SECURITY_ALERT', 'PLATFORM_ALERT', 'PLATFORM', 'SCHOOL_MESSAGE'].map(k => <option key={k} value={k}>{EVENT_LABEL[k]}</option>)}</select></label>
    <label className="ms-f"><span>Du</span><input type="date" value={f.date_from || ''} onChange={e => set('date_from', e.target.value)}/></label>
    <label className="ms-f"><span>Au</span><input type="date" value={f.date_to || ''} onChange={e => set('date_to', e.target.value)}/></label>
  </>;
  return <div className="sc ms">
    <PageTrail parents={[{label: 'Messagerie', onSelect: onBack}]} current={'Envois'}/>
    <header className="sc-head"><div><h2>Envois</h2><p>Recherche et filtres côté serveur. Destinataires masqués.</p></div></header>
    <div className="ms-bar">
      <label className="ms-search"><NavGlyph g="search" size={16}/><input type="search" value={q} onChange={e => setQ(e.target.value)} placeholder="Identifiant, référence fournisseur ou adresse exacte" aria-label="Rechercher un envoi"/></label>
      <button type="button" className="sc-btn sc-btn-ghost ms-fbtn" onClick={() => setSheet(true)} aria-label="Filtres"><NavGlyph g="sliders" size={16}/><span>Filtres{chips.length ? ` (${chips.length})` : ''}</span></button>
    </div>
    <div className="ms-filters-desk">{controls}</div>
    {chips.length > 0 && <div className="ms-chips">{chips.map(([k, v]) => <button type="button" key={k} className="ms-chip" onClick={() => set(k)} aria-label={`Retirer le filtre ${v}`}>
      {k === 'channel' ? CHANNEL_LABEL[v] : k === 'status' ? (FILTER_LABEL[v] || STATUS_LABEL[v]) : k === 'event' ? (EVENT_LABEL[v] || v) : k === 'scope' ? (v === 'PLATFORM' ? 'Plateforme' : 'Écoles') : `${k === 'date_from' ? 'Du' : 'Au'} ${v}`}<NavGlyph g="close" size={12}/></button>)}
      <button type="button" className="ms-chip ms-chip-clear" onClick={() => { setQ(''); setF({}); }}>Tout effacer</button></div>}
    {sheet && <div className="es-modal-backdrop" onMouseDown={e => e.currentTarget === e.target && setSheet(false)}>
      <div className="es-modal" role="dialog" aria-modal="true" aria-label="Filtres des envois"><div className="es-modal-head"><div><h2>Filtres</h2></div>
        <button className="es-icon-btn" aria-label="Fermer" onClick={() => setSheet(false)}><NavGlyph g="close" size={18}/></button></div>
        <div className="ms-sheet">{controls}</div>
        <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={() => setF({})}>Effacer</button><button type="button" className="es-btn es-btn-primary" onClick={() => setSheet(false)}>Voir les résultats</button></div></div></div>}
    {error && <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Recherche impossible.</b><small>{error}</small></div></div>}
    {!items && !error && <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>}
    {items && items.length === 0 && <p className="ms-empty"><NavGlyph g="checkCircle" size={16}/>Aucun envoi ne correspond.</p>}
    {items && items.length > 0 && <>
      <div className="ms-table" role="table" aria-label="Envois">
        <div className="ms-tr ms-th" role="row"><span role="columnheader">État</span><span role="columnheader">Canal</span><span role="columnheader">Événement</span><span role="columnheader">Destinataire</span><span role="columnheader">Origine</span><span role="columnheader">Tentatives</span><span role="columnheader">Date</span></div>
        {items.map(d => <button type="button" role="row" className="ms-tr" key={d.id} onClick={() => onOpen(d.id)}>
          <span role="cell"><em className={`ms-pill ${ST_CLS[d.status]}`}>{STATUS_LABEL[d.status] || d.status}</em>{d.error_code && <small className="ms-err">{d.error_code}</small>}</span>
          <span role="cell">{CHANNEL_LABEL[d.channel] || d.channel}</span><span role="cell">{EVENT_LABEL[d.event] || d.event}</span><span role="cell" className="ms-mono">{d.destination}</span>
          <span role="cell">{d.school_name || 'Plateforme'}</span><span role="cell">{d.attempts}</span><span role="cell">{when(d.created_at)}</span></button>)}
      </div>
      <ul className="ms-cards">{items.map(d => <li key={d.id}><button type="button" className="ms-card" onClick={() => onOpen(d.id)}>
        <span className="ms-card-top"><em className={`ms-pill ${ST_CLS[d.status]}`}>{STATUS_LABEL[d.status] || d.status}</em><small>{when(d.created_at)}</small></span>
        <b>{CHANNEL_LABEL[d.channel]} · {EVENT_LABEL[d.event] || d.event}</b><span className="ms-mono">{d.destination}</span>
        <small>{d.school_name || 'Plateforme'} · {d.attempts} tentative(s){d.error_code ? ` · ${d.error_code}` : ''}</small></button></li>)}</ul>
      {cursor && <button type="button" className="sc-btn sc-btn-ghost ms-more" onClick={() => void loadMore()} disabled={more}>{more ? 'Chargement…' : 'Afficher plus'}</button>}
    </>}
  </div>;
}

/* ------------------------------------------------------------------------------------------------ delivery detail */
function DeliveryPage({token, id, online, canRetry, onBack}: {token: string; id: string; online: boolean; canRetry: boolean; onBack: () => void}) {
  const [d, setD] = useState<DeliveryDetail | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const key = useRef(crypto.randomUUID());
  const load = useCallback(() => getDelivery(token, id).then(x => { setD(x); setError(''); }).catch(e => setError(e instanceof UserFacingError ? e.message : friendlyError(e))), [token, id]);
  useEffect(() => { void load(); }, [load]);
  async function retry() {
    if (!d || !online) return;
    const reason = await promptText({title: 'Relancer cet envoi', message: 'Le motif est journalisé. Une seule nouvelle tentative est faite ; un envoi déjà réussi n’est jamais renvoyé.',
      label: 'Motif de la relance', placeholder: 'Ex. : adresse corrigée, fournisseur rétabli', confirmLabel: 'Relancer', required: true, minLength: 5});
    if (!reason) return;
    setBusy(true);
    try { const r = await retryDelivery(token, d.id, reason.trim(), key.current); key.current = crypto.randomUUID();
      toast[r.requeued ? 'success' : 'message'](r.requeued ? 'Envoi remis en file' : `Aucune relance : ${STATUS_LABEL[r.status] || r.status}`); await load(); }
    catch (e) { toast.error(e instanceof UserFacingError ? e.message : friendlyError(e)); } finally { setBusy(false); }
  }
  async function copy(v: string) { try { await navigator.clipboard.writeText(v); toast.success('Copié'); } catch { /* indisponible */ } }
  const Id = ({v}: {v: string | null}) => v ? <span className="ms-id"><code>{v}</code><button type="button" className="ms-copy" onClick={() => void copy(v)} aria-label={`Copier ${v}`}><NavGlyph g="doc" size={13}/></button></span> : <>—</>;
  return <div className="sc-sheet-page ms">
    <PageTrail parents={[{label: 'Retour', onSelect: onBack}]} current={'Détail de l’envoi'}/>
    {error && <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Envoi introuvable.</b><small>{error}</small></div></div>}
    {!d && !error && <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>}
    {d && <>
      <header className="sc-card sc-sheet-head"><div className="sc-sheet-id"><span className={`sc-sheet-logo ms-logo ${ST_CLS[d.status]}`} aria-hidden="true"><NavGlyph g={ICON[d.channel] || 'message'} size={24}/></span>
        <div><h2>{CHANNEL_LABEL[d.channel]} · {EVENT_LABEL[d.event] || d.event}</h2><p>{d.school_name || 'Plateforme EduSync'} · {d.destination}</p>
          <div className="sc-badges"><span className={`sc-badge ms-badge ${ST_CLS[d.status]}`}>{STATUS_LABEL[d.status] || d.status}</span>{d.provider && <span className="sc-badge ms-badge ms-off">{d.provider}</span>}</div></div></div>
        {d.can_retry && canRetry && <button type="button" className="sc-btn" onClick={() => void retry()} disabled={busy || !online}><NavGlyph g="sync" size={16}/>{busy ? 'Relance…' : 'Relancer'}</button>}</header>
      <div className="sc-sheet-grid">
        <section className="sc-card"><h3>Diagnostic</h3><dl className="sc-dl">
          <dt>État</dt><dd>{STATUS_LABEL[d.status] || d.status}{d.status === 'SENT' ? ' (accepté par le fournisseur, distribution non prouvée)' : ''}</dd>
          <dt>Code</dt><dd>{d.error_code || '—'}</dd>{d.error_detail && <><dt>Détail (expurgé)</dt><dd>{d.error_detail}</dd></>}
          {d.impact && <><dt>Impact</dt><dd>{d.impact}</dd></>}
          {d.retry_policy && <><dt>Relance</dt><dd>{d.retry_policy}</dd></>}</dl></section>
        <section className="sc-card"><h3>Tentatives</h3><dl className="sc-dl">
          <dt>Nombre</dt><dd>{d.attempts}</dd><dt>Créé</dt><dd>{when(d.created_at)}</dd><dt>Première tentative</dt><dd>{when(d.first_attempt_at)}</dd>
          <dt>Dernière tentative</dt><dd>{when(d.last_attempt_at)}</dd><dt>Prochaine tentative</dt><dd>{d.next_attempt_at ? when(d.next_attempt_at) : '—'}</dd>
          <dt>Envoyé</dt><dd>{when(d.sent_at)}</dd><dt>Distribué (preuve)</dt><dd>{d.delivered_proof ? when(d.delivered_at) : 'Non prouvé'}</dd>
          {d.failed_at && <><dt>Échec</dt><dd>{when(d.failed_at)}</dd></>}</dl></section>
        <section className="sc-card"><h3>Identifiants</h3><dl className="sc-dl">
          <dt>Envoi</dt><dd><Id v={d.id}/></dd><dt>Message</dt><dd><Id v={d.message_id}/></dd><dt>Événement outbox</dt><dd><Id v={d.outbox_id}/></dd>
          <dt>Corrélation</dt><dd><Id v={d.correlation_id}/></dd><dt>Référence fournisseur</dt><dd><Id v={d.provider_message_id}/></dd></dl></section>
        <section className="sc-card"><h3>Message</h3><dl className="sc-dl">
          {d.message.private ? <><dt>Message</dt><dd>Message d’une école : contenu et destinataires privés, non lisibles par la plateforme</dd></> :
            <><dt>Destinataires</dt><dd>{n(d.message.recipients)}</dd><dt>Créé</dt><dd>{when(d.message.created_at)}</dd><dt>Distribué au worker</dt><dd>{when(d.message.dispatched_at)}</dd></>}
          <dt>Envois du message</dt><dd>{Object.entries(d.message.deliveries_by_status).map(([s, k]) => `${STATUS_LABEL[s] || s} ${k}`).join(' · ') || '—'}</dd>
          {d.segments_billed != null && <><dt>Unités SMS</dt><dd>{d.segments_billed}</dd></>}</dl>
          <p className="sc-hint">Le contenu des messages n’est jamais affiché ici.</p></section>
        {d.retries.length > 0 && <section className="sc-card ms-wide"><h3>Relances manuelles</h3><ul className="ms-list">{d.retries.map(r => <li key={r.at}><span>{when(r.at)}</span><span>{r.reason || '—'}</span></li>)}</ul></section>}
      </div>
    </>}
  </div>;
}

/* ------------------------------------------------------------------------------------------------ SMS wallets */
function Wallets({token, onOpen}: {token: string; onOpen: (id: string) => void}) {
  const [q, setQ] = useState(''); const [low, setLow] = useState(false);
  const [data, setData] = useState<{items: Wallet[]; next: string | null; totals: {balance: number; reserved: number; available: number; funded_schools: number}} | null>(null);
  const [error, setError] = useState(''); const [more, setMore] = useState(false);
  const ctl = useRef<AbortController | null>(null);
  useEffect(() => { const t = window.setTimeout(() => { ctl.current?.abort(); const c = new AbortController(); ctl.current = c;
    listWallets(token, q.trim(), low, null, c.signal).then(r => { setData({items: r.items, next: r.next_cursor, totals: r.totals}); setError(''); })
      .catch(e => { if ((e as Error).name !== 'AbortError') setError(friendlyError(e)); }); }, 300); return () => window.clearTimeout(t); }, [token, q, low]);
  async function loadMore() { if (!data?.next) return; setMore(true); try { const r = await listWallets(token, q.trim(), low, data.next); setData(d => d && {...d, items: [...d.items, ...r.items], next: r.next_cursor}); } catch (e) { toast.error(friendlyError(e)); } finally { setMore(false); } }
  return <section className="sc-card ms-wallets" aria-label="Portefeuilles SMS des écoles">
    <div className="ms-whead"><h3>Portefeuilles SMS des écoles</h3>{data && <div className="ms-tot"><span><b>{n(data.totals.balance)}</b>solde total</span><span><b>{n(data.totals.reserved)}</b>réservé</span><span><b>{n(data.totals.available)}</b>disponible</span></div>}</div>
    <div className="ms-bar"><label className="ms-search"><NavGlyph g="search" size={16}/><input type="search" value={q} onChange={e => setQ(e.target.value)} placeholder="Rechercher une école (nom ou code)" aria-label="Rechercher une école"/></label>
      <label className="ms-check"><input type="checkbox" checked={low} onChange={e => setLow(e.target.checked)}/> Solde bas seulement</label></div>
    {error && <p className="sc-hint" role="alert">{error}</p>}
    {!data && !error && <div className="es-skeleton" aria-busy="true"><i/><i/></div>}
    {data && data.items.length === 0 && <p className="ms-empty">Aucune école ne correspond.</p>}
    {data && data.items.length > 0 && <ul className="ms-wl">{data.items.map(w => <li key={w.school_id}><button type="button" onClick={() => onOpen(w.school_id)}>
      <span className="ms-wn"><b>{w.name}</b><small>{w.code} · {w.sms_enabled ? 'SMS activés' : 'SMS désactivés'} · consommés 30 j : {n(w.consumed_30d)}</small></span>
      <span className={`ms-wv ${w.low ? 'ms-warn' : ''}`}><b>{n(w.available)}</b><small>disponibles{w.reserved ? ` · ${n(w.reserved)} réservés` : ''}{w.low ? ' · solde bas' : ''}</small></span>
      <NavGlyph g="chevronRight" size={16}/></button></li>)}</ul>}
    {data?.next && <button type="button" className="sc-btn sc-btn-ghost ms-more" onClick={() => void loadMore()} disabled={more}>{more ? 'Chargement…' : 'Afficher plus'}</button>}
  </section>;
}

function WalletPage({token, id, online, canCredit, canAdjust, onBack}: {token: string; id: string; online: boolean; canCredit: boolean; canAdjust: boolean; onBack: () => void}) {
  const [data, setData] = useState<{items: LedgerRow[]; wallet: {name: string; balance: number; reserved: number; available: number}} | null>(null);
  const [error, setError] = useState(''); const [mode, setMode] = useState<'' | 'credit' | 'adjust'>('');
  const load = useCallback(() => getLedger(token, id).then(x => { setData(x); setError(''); }).catch(e => setError(e instanceof UserFacingError ? e.message : friendlyError(e))), [token, id]);
  useEffect(() => { void load(); }, [load]);
  return <div className="sc-sheet-page ms">
    <PageTrail parents={[{label: 'Messagerie', onSelect: onBack}]} current={data ? `Portefeuille SMS — ${data.wallet.name}` : 'Portefeuille SMS'}/>
    {error && <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Portefeuille indisponible.</b><small>{error}</small></div></div>}
    {!data && !error && <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>}
    {data && <>
      <header className="sc-card sc-sheet-head"><div className="sc-sheet-id"><span className="sc-sheet-logo ms-logo ms-info" aria-hidden="true"><NavGlyph g="phone" size={24}/></span>
        <div><h2>Portefeuille SMS — {data.wallet.name}</h2><p>Grand livre en ajout seul : chaque mouvement est conservé, jamais modifié.</p></div></div></header>
      <ul className="ms-kpis ms-kpis-3"><li><div className="ms-kpi ms-static"><b className="ms-kpi-val">{n(data.wallet.balance)}</b><span className="ms-kpi-lbl">Solde total</span></div></li>
        <li><div className="ms-kpi ms-static"><b className="ms-kpi-val">{n(data.wallet.reserved)}</b><span className="ms-kpi-lbl">Réservé (envois en cours)</span></div></li>
        <li><div className="ms-kpi ms-static ms-ok"><b className="ms-kpi-val">{n(data.wallet.available)}</b><span className="ms-kpi-lbl">Disponible</span></div></li></ul>
      {(canCredit || canAdjust) && <div className="ms-actions">
        {canCredit && <button type="button" className="sc-btn" onClick={() => setMode(mode === 'credit' ? '' : 'credit')} disabled={!online} aria-expanded={mode === 'credit'}><NavGlyph g="plus" size={16}/>Recharge payée</button>}
        {canAdjust && <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setMode(mode === 'adjust' ? '' : 'adjust')} disabled={!online} aria-expanded={mode === 'adjust'}>Ajustement</button>}
        {!online && <small className="sc-hint">Hors connexion : mouvements indisponibles.</small>}</div>}
      {mode && <WalletForm token={token} id={id} mode={mode} onDone={async () => { setMode(''); await load(); }} onCancel={() => setMode('')}/>}
      <section className="sc-card"><h3>Mouvements</h3>
        {data.items.length === 0 ? <p className="ms-empty">Aucun mouvement.</p> : <ul className="ms-ledger">{data.items.map(l => <li key={l.id}>
          <span className="ms-ln"><b>{MOVEMENT_LABEL[l.movement_type] || l.movement_type}</b><small>{when(l.created_at)}{l.actor ? ` · ${l.actor}` : ''}{l.reference ? ` · réf. ${l.reference}` : ''}</small>
            {l.reason && <small>{l.reason}</small>}</span>
          <span className="ms-lv"><b className={l.direction === 'DEBIT' ? 'ms-neg' : l.direction === 'CREDIT' ? 'ms-pos' : ''}>{l.direction === 'DEBIT' ? '−' : l.direction === 'CREDIT' ? '+' : ''}{n(l.quantity)}</b>
            <small>solde {n(l.balance_before)} → {n(l.balance_after)}{l.reserved_after ? ` · réservé ${n(l.reserved_after)}` : ''}</small></span></li>)}</ul>}
      </section>
    </>}
  </div>;
}

function F({id: fid, label, error, children}: {id: string; label: string; error?: string; children: React.ReactNode}) {
  return <label className={`ms-ff ${error ? 'ms-invalid' : ''}`} htmlFor={fid}><span>{label}</span>{children}{error && <small role="alert">{error}</small>}</label>;
}

function WalletForm({token, id, mode, onDone, onCancel}: {token: string; id: string; mode: 'credit' | 'adjust'; onDone: () => Promise<void>; onCancel: () => void}) {
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const [qty, setQty] = useState(''); const [ref, setRef] = useState(''); const [reason, setReason] = useState(''); const [paidOn, setPaidOn] = useState(today);
  const [amount, setAmount] = useState(''); const [cur, setCur] = useState('USD'); const [dir, setDir] = useState<'CREDIT' | 'DEBIT'>('CREDIT');
  const [errors, setErrors] = useState<Record<string, string>>({}); const [busy, setBusy] = useState(false);
  const key = useRef(crypto.randomUUID());     // one key per form: a double click never credits twice
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const q = Number(qty); const er: Record<string, string> = {};
    if (!Number.isInteger(q) || q <= 0) er.qty = 'Nombre entier positif.';
    if (mode === 'credit') {
      if (ref.trim().length < 2) er.ref = 'Référence du paiement obligatoire.';
      if (!paidOn || paidOn > today) er.paidOn = 'Date du paiement (pas dans le futur).';
      if (!(Number(amount.replace(',', '.')) > 0)) er.amount = 'Montant payé obligatoire.';
      if (reason.trim().length < 5) er.reason = 'Motif obligatoire (5 caractères au moins).';
    } else if (reason.trim().length < 10) er.reason = 'Justification obligatoire (10 caractères au moins).';
    setErrors(er); if (Object.keys(er).length) return;
    setBusy(true);
    try {
      const r = mode === 'credit'
        ? await creditWallet(token, id, {quantity: q, reference: ref.trim(), reason: reason.trim(), paid_on: paidOn, commercial_price: Number(amount.replace(',', '.')), commercial_currency: cur}, key.current)
        : await adjustWallet(token, id, {direction: dir, quantity: q, reason: reason.trim(), reference: ref.trim() || undefined}, key.current);
      toast.success(r.replayed ? 'Déjà enregistré (aucun double mouvement)' : `Solde : ${n(r.balance_before)} → ${n(r.balance)}`);
      key.current = crypto.randomUUID(); await onDone();
    } catch (err) { toast.error(err instanceof UserFacingError ? err.message : friendlyError(err)); } finally { setBusy(false); }
  }
  return <form className="sc-card ms-form" onSubmit={submit} noValidate aria-label={mode === 'credit' ? 'Recharge payée' : 'Ajustement'}>
    <h3>{mode === 'credit' ? 'Recharge après paiement de l’école' : 'Ajustement (crédit ou débit motivé)'}</h3>
    <div className="ms-fgrid">
      {mode === 'adjust' && <F id="w-dir" label="Sens"><select id="w-dir" value={dir} onChange={e => setDir(e.target.value as 'CREDIT' | 'DEBIT')}><option value="CREDIT">Crédit</option><option value="DEBIT">Débit</option></select></F>}
      <F id="w-qty" label="Quantité (unités SMS) *" error={errors.qty}><input id="w-qty" inputMode="numeric" value={qty} onChange={e => setQty(e.target.value.replace(/\D/g, ''))}/></F>
      <F id="w-ref" label={mode === 'credit' ? 'Référence du paiement *' : 'Référence (facultatif)'} error={errors.ref}><input id="w-ref" value={ref} onChange={e => setRef(e.target.value)} maxLength={120}/></F>
      {mode === 'credit' && <>
        <F id="w-date" label="Date du paiement *" error={errors.paidOn}><input id="w-date" type="date" max={today} value={paidOn} onChange={e => setPaidOn(e.target.value)}/></F>
        <F id="w-amt" label="Montant payé *" error={errors.amount}><input id="w-amt" inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value.replace(/[^\d.,]/g, ''))}/></F>
        <F id="w-cur" label="Devise *"><select id="w-cur" value={cur} onChange={e => setCur(e.target.value)}><option>USD</option><option>CDF</option></select></F></>}
      <F id="w-reason" label={mode === 'credit' ? 'Motif (journalisé) *' : 'Justification (journalisée) *'} error={errors.reason}><input id="w-reason" value={reason} onChange={e => setReason(e.target.value)} maxLength={500}/></F>
    </div>
    <p className="sc-hint">Opération auditée ; un code de vérification récent peut vous être demandé. Le solde ne peut jamais devenir négatif.</p>
    <div className="ms-actions"><button type="button" className="sc-btn sc-btn-ghost" onClick={onCancel}>Annuler</button><button className="sc-btn" disabled={busy}>{busy ? 'Enregistrement…' : 'Enregistrer'}</button></div>
  </form>;
}
