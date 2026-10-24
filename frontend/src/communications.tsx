// Centre de communication de l'école (EXTERNAL_MESSAGING_ARCHITECTURE.md §7) — mobile first.
// Composer → aperçu (destinataires, numéros invalides, doublons, unités SMS, solde après envoi) → confirmation.
// Le serveur accepte l'envoi (« En file ») puis le worker envoie : l'écran n'affiche jamais « Envoyé » avant le serveur.
import React, {useEffect, useMemo, useState} from 'react';
import {toast} from 'sonner';
import {friendlyError} from './platform/errors';
import {listClassSelector, listSections, listStudents} from './api';
import {
  CHANNEL_LABEL, STATE_LABEL, STATUS_LABEL, confirmSend, deliveries, history, previewSend, pushDevices, pushTest, readiness, retryDelivery,
  saveSettings, walletLedger, type Draft, type HistoryItem, type Preview, type Readiness,
} from './messaging_api';
import {disablePush, enablePush, pushSupport, rememberedSubscription} from './push_client';
import {NavGlyph} from './platform/nav_icons';
import './communications.css';

type Props = {token: string; permissions: string[]; schoolId: string; schoolName: string; onNavigate?: (module: string) => void};
type Tab = 'compose' | 'history' | 'settings';
const AUD_LABEL: Record<Draft['audience_type'], string> = {INDIVIDUAL: 'Un élève (ses responsables)', CLASS: 'Une classe', SECTION: 'Une section', SCHOOL: 'Toute l’école'};
const AUD_CAP: Record<Draft['audience_type'], string> = {INDIVIDUAL: 'communications.send.individual', CLASS: 'communications.send.class',
  SECTION: 'communications.send.section', SCHOOL: 'communications.send.all_parents'};

function smsUnits(text: string) {
  const n = text.length; const gsm = [...text].every(c => c.charCodeAt(0) < 128);
  const seg = gsm ? (n <= 160 ? 1 : Math.ceil(n / 153)) : (n <= 70 ? 1 : Math.ceil(n / 67));
  return Math.max(seg, n <= 160 ? 1 : n <= 320 ? 2 : 3);
}
const fmt = (iso?: string | null) => iso ? new Date(iso).toLocaleString('fr-FR', {dateStyle: 'short', timeStyle: 'short'}) : '—';

export default function CommunicationsPage({token, permissions, schoolId, schoolName, onNavigate}: Props) {
  const can = (p: string) => permissions.includes(p);
  const [tab, setTab] = useState<Tab>(can('communications.compose') ? 'compose' : can('communications.history.read') ? 'history' : 'settings');
  const [ready, setReady] = useState<Readiness | null>(null);
  const [error, setError] = useState('');
  const reload = () => readiness(token).then(setReady).catch(e => setError(friendlyError(e)));
  useEffect(() => { void reload(); }, [token]);
  return <section className="commPage">
    <header className="commHero"><span className="commHeroIcon" aria-hidden="true"><NavGlyph g="message" size={26}/></span><div><div className="eyebrow">COMMUNICATION</div><h2>Centre de communication</h2>
      <p>{can('communications.compose') ? `Écrivez aux familles et au personnel de ${schoolName} par SMS, e-mail ou notification. Une panne d’un fournisseur ne bloque jamais l’école.`
        : `Vous décidez ici comment ${schoolName} communique : canaux autorisés, solde SMS, notifications de cet appareil. Les messages aux familles sont rédigés par les rôles qui en ont le droit.`}</p></div>
      {ready && <div className={`commWallet ${ready.wallet.low ? 'low' : ''}`} aria-label="Solde SMS"><b>{ready.wallet.available}</b><small>SMS disponibles</small>
        {ready.wallet.reserved > 0 && <small>{ready.wallet.reserved} réservés</small>}</div>}
    </header>
    {(can('communications.compose') || can('communications.history.read')) && <nav className="commTabs" role="tablist">
      {can('communications.compose') && <button role="tab" aria-selected={tab === 'compose'} className={tab === 'compose' ? 'active' : ''} onClick={() => setTab('compose')}><NavGlyph g="message" size={16}/>Écrire un message</button>}
      {can('communications.history.read') && <button role="tab" aria-selected={tab === 'history'} className={tab === 'history' ? 'active' : ''} onClick={() => setTab('history')}><NavGlyph g="clock" size={16}/>Historique</button>}
      <button role="tab" aria-selected={tab === 'settings'} className={tab === 'settings' ? 'active' : ''} onClick={() => setTab('settings')}><NavGlyph g="sliders" size={16}/>Réglages</button>
    </nav>}
    {error && <div className="error" role="alert">{error}</div>}
    {tab === 'compose' && ready && <Composer token={token} can={can} ready={ready} schoolId={schoolId} onSent={() => { void reload(); }}/>}
    {tab === 'history' && <History token={token} can={can}/>}
    {tab === 'settings' && ready && <Settings token={token} can={can} ready={ready} schoolId={schoolId} onChange={reload} onNavigate={onNavigate}/>}
  </section>;
}

// ---------------------------------------------------------------------------------------------------- Composer
function Composer({token, can, ready, schoolId, onSent}: {token: string; can: (p: string) => boolean; ready: Readiness; schoolId: string; onSent: () => void}) {
  const draftKey = `edusync.comm.draft.${schoolId}`;
  const saved = (() => { try { return JSON.parse(localStorage.getItem(draftKey) || 'null'); } catch { return null; } })();
  const audiences = (Object.keys(AUD_LABEL) as Draft['audience_type'][]).filter(a => can(AUD_CAP[a]));
  const [aud, setAud] = useState<Draft['audience_type']>(saved?.aud ?? audiences[0] ?? 'INDIVIDUAL');
  const [ref, setRef] = useState<string>(saved?.ref ?? '');
  const [channels, setChannels] = useState<string[]>(saved?.channels ?? []);
  const [subject, setSubject] = useState<string>(saved?.subject ?? '');
  const [body, setBody] = useState<string>(saved?.body ?? '');
  const [classes, setClasses] = useState<any[]>([]); const [sections, setSections] = useState<any[]>([]);
  const [q, setQ] = useState(''); const [students, setStudents] = useState<any[]>([]); const [studentLabel, setStudentLabel] = useState(saved?.studentLabel ?? '');
  const [pv, setPv] = useState<Preview | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [online, setOnline] = useState(navigator.onLine);
  const [sendKey, setSendKey] = useState(crypto.randomUUID());
  useEffect(() => { const on = () => setOnline(true), off = () => setOnline(false); addEventListener('online', on); addEventListener('offline', off);
    return () => { removeEventListener('online', on); removeEventListener('offline', off); }; }, []);
  useEffect(() => { void listClassSelector(token).then(setClasses).catch(() => setClasses([])); void listSections(token).then(setSections).catch(() => setSections([])); }, [token]);
  // Offline-first: the draft stays on this device until the server accepts the message.
  useEffect(() => { try { localStorage.setItem(draftKey, JSON.stringify({aud, ref, channels, subject, body, studentLabel})); } catch { /* private mode */ } }, [aud, ref, channels, subject, body, studentLabel]);
  useEffect(() => { setPv(null); }, [aud, ref, channels, body, subject]);
  useEffect(() => { if (aud !== 'INDIVIDUAL' || q.trim().length < 2) { setStudents([]); return; }
    const t = setTimeout(() => listStudents(token, {q: q.trim(), limit: 8}).then(r => setStudents(r.items)).catch(() => setStudents([])), 300); return () => clearTimeout(t); }, [q, aud]);
  const avail = {
    SMS: ready.enabled && ready.sms_enabled && ready.platform.sms.available && can(aud === 'INDIVIDUAL' ? 'communications.sms.send' : 'communications.sms.bulk_send'),
    EMAIL: ready.enabled && ready.email_enabled && ready.platform.email.available,
    PUSH: ready.enabled && ready.push_enabled && ready.platform.push.available,
  } as Record<string, boolean>;
  const units = useMemo(() => smsUnits(body), [body]);
  const draft: Draft = {audience_type: aud, audience_ref: aud === 'SCHOOL' ? null : ref || null, channels, subject: subject || undefined, body};
  const needRef = aud !== 'SCHOOL' && !ref;
  const toggle = (ch: string) => setChannels(cs => cs.includes(ch) ? cs.filter(c => c !== ch) : [...cs, ch]);
  async function check() {
    setError(''); setBusy(true);
    try { setPv(await previewSend(token, draft)); } catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  async function send() {
    setError(''); setBusy(true);
    try {
      const r = await confirmSend(token, draft, sendKey, pv?.fingerprint);
      toast.success(`Message accepté : ${r.recipients} destinataire(s), envoi en cours`);
      try { localStorage.removeItem(draftKey); } catch { /* ignore */ }
      setBody(''); setSubject(''); setPv(null); setSendKey(crypto.randomUUID()); onSent();
    } catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  if (!audiences.length) return <p className="commEmpty">Votre rôle ne permet pas d’envoyer des communications.</p>;
  return <div className="commCard">
    {!online && <div className="commNotice" role="status">Hors ligne : votre brouillon est conservé sur cet appareil. L’envoi sera possible au retour du réseau.</div>}
    <label className="commField"><span>Destinataires</span>
      <select value={aud} onChange={e => { setAud(e.target.value as Draft['audience_type']); setRef(''); setStudentLabel(''); }} aria-label="Type de destinataires">
        {audiences.map(a => <option key={a} value={a}>{AUD_LABEL[a]}</option>)}</select></label>
    {aud === 'CLASS' && <label className="commField"><span>Classe</span><select value={ref} onChange={e => setRef(e.target.value)} aria-label="Classe">
      <option value="">Choisir…</option>{classes.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select></label>}
    {aud === 'SECTION' && <label className="commField"><span>Section</span><select value={ref} onChange={e => setRef(e.target.value)} aria-label="Section">
      <option value="">Choisir…</option>{sections.filter(s => s.enabled !== false).map(s => <option key={s.id} value={s.id}>{s.label}</option>)}</select></label>}
    {aud === 'INDIVIDUAL' && <div className="commField"><span>Élève</span>
      {ref ? <div className="commPicked"><b>{studentLabel}</b><button className="softBtn" onClick={() => { setRef(''); setStudentLabel(''); }}>Changer</button></div>
        : <><input value={q} onChange={e => setQ(e.target.value)} placeholder="Nom ou matricule de l’élève" aria-label="Rechercher un élève"/>
          {students.length > 0 && <ul className="commResults">{students.map(s => <li key={s.id}><button onClick={() => { setRef(s.id); setStudentLabel(`${s.last_name} ${s.first_name ?? ''} · ${s.matricule}`); setQ(''); }}>
            {s.last_name} {s.middle_name ?? ''} {s.first_name ?? ''}<small>{s.matricule}</small></button></li>)}</ul>}</>}</div>}
    <fieldset className="commChannels"><legend>Canaux</legend>
      {(['SMS', 'EMAIL', 'PUSH'] as const).map(ch => <label key={ch} className={avail[ch] ? '' : 'off'}>
        <input type="checkbox" checked={channels.includes(ch)} disabled={!avail[ch]} onChange={() => toggle(ch)}/>
        <span>{CHANNEL_LABEL[ch]}</span><small>{avail[ch] ? (ch === 'SMS' ? 'facturé en unités SMS' : 'sans coût SMS') : 'indisponible'}</small></label>)}
    </fieldset>
    {(channels.includes('EMAIL') || channels.includes('PUSH')) && <label className="commField"><span>Objet</span>
      <input value={subject} maxLength={180} onChange={e => setSubject(e.target.value)} placeholder="Objet de l’e-mail ou titre de la notification" aria-label="Objet"/></label>}
    <label className="commField"><span>Message</span>
      <textarea value={body} maxLength={channels.includes('SMS') ? ready.max_sms_characters : 4000} rows={5} onChange={e => setBody(e.target.value)} aria-label="Message"
        placeholder="Texte envoyé aux destinataires"/>
      <small className="commCount">{body.length} caractères{channels.includes('SMS') ? ` · ${units} unité(s) SMS par destinataire · maximum ${ready.max_sms_characters}` : ''}</small></label>
    {pv && <div className={`commPreview ${pv.sufficient && !pv.too_long ? '' : 'warn'}`} aria-live="polite">
      <div><b>{pv.recipients}</b><small>destinataires</small></div>
      {channels.includes('SMS') && <><div><b>{pv.sms_valid}</b><small>numéros valides</small></div>
        <div><b>{pv.sms_invalid}</b><small>invalides (non facturés)</small></div><div><b>{pv.sms_duplicates_removed}</b><small>doublons retirés</small></div>
        <div><b>{pv.sms_units}</b><small>unités SMS nécessaires</small></div><div><b>{pv.balance_after}</b><small>solde après envoi</small></div></>}
      {channels.includes('EMAIL') && <div><b>{pv.email_valid}</b><small>adresses e-mail</small></div>}
      {!pv.sufficient && <p className="commWarn">Crédit SMS insuffisant : demandez une recharge à EduSync.</p>}
      {pv.too_long && <p className="commWarn">Message trop long pour un SMS.</p>}
    </div>}
    {error && <div className="error" role="alert">{error}</div>}
    <div className="commActions">
      <button className="softBtn" disabled={busy || !online || needRef || !body.trim() || !channels.length} onClick={() => void check()}>Vérifier l’envoi</button>
      <button className="primaryBtn" disabled={busy || !online || !pv || !pv.sufficient || pv.too_long || pv.recipients === 0} onClick={() => void send()}>
        {channels.includes('SMS') && pv ? `Confirmer l’envoi (${pv.sms_units} unités)` : 'Confirmer l’envoi'}</button>
    </div>
  </div>;
}

// ---------------------------------------------------------------------------------------------------- History
function History({token, can}: {token: string; can: (p: string) => boolean}) {
  const [items, setItems] = useState<HistoryItem[] | null>(null); const [open, setOpen] = useState<string | null>(null); const [rows, setRows] = useState<any[]>([]);
  const [error, setError] = useState('');
  const load = () => history(token).then(r => setItems(r.items)).catch(e => setError(friendlyError(e)));
  useEffect(() => { void load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [token]);
  async function expand(id: string) {
    if (open === id) { setOpen(null); return; }
    setOpen(id); setRows([]);
    try { setRows((await deliveries(token, id)).items); } catch (e) { setError(friendlyError(e)); }
  }
  async function retry(id: string) {
    try { await retryDelivery(token, id); toast.success('Nouvel essai programmé'); if (open) setRows((await deliveries(token, open)).items); }
    catch (e) { toast.error(friendlyError(e)); }
  }
  if (error) return <div className="error" role="alert">{error}</div>;
  if (!items) return <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>;
  if (!items.length) return <p className="commEmpty">Aucune communication envoyée pour l’instant.</p>;
  return <ul className="commHistory">{items.map(m => {
    const statuses = Object.entries(m.counts);
    return <li key={m.id}>
      <button className="commHistoryHead" onClick={() => void expand(m.id)} aria-expanded={open === m.id}>
        <span className="commChips">{m.channels.map(c => <em key={c}>{CHANNEL_LABEL[c] ?? c}</em>)}</span>
        <b>{m.subject || AUD_LABEL[m.audience_type as Draft['audience_type']] || m.audience_type}</b>
        <small>{fmt(m.created_at)} · {m.author ?? '—'} · {m.recipient_count} destinataire(s){m.sms_units_billed ? ` · ${m.sms_units_billed} unité(s) SMS` : ''}</small>
        <span className="commStatuses">{statuses.length ? statuses.map(([k, n]) => { const [ch, st] = k.split(':'); return <i key={k} className={`st-${st}`}>{CHANNEL_LABEL[ch] ?? ch} · {STATUS_LABEL[st] ?? st} · {n}</i>; })
          : <i className="st-QUEUED">{m.dispatched_at ? 'Aucun envoi externe' : 'En préparation'}</i>}</span>
        {m.errors?.length ? <small className="commErr">Erreurs : {m.errors.join(', ')}</small> : null}
      </button>
      {open === m.id && <ul className="commDeliveries">{rows.map(d => <li key={d.id}>
        <span><b>{d.display_name ?? '—'}</b><small>{CHANNEL_LABEL[d.channel] ?? d.channel}{d.destination ? ` · ${d.destination}` : ''}</small></span>
        <span className={`st-${d.status}`}>{STATUS_LABEL[d.status] ?? d.status}{d.last_error_code ? ` · ${d.last_error_code}` : ''}</span>
        {d.status === 'FAILED_PERMANENT' && can('communications.delivery.retry') && <button className="softBtn" onClick={() => void retry(d.id)}>Réessayer</button>}
      </li>)}{rows.length === 0 && <li><small>Chargement…</small></li>}</ul>}
    </li>;
  })}</ul>;
}

// ---------------------------------------------------------------------------------------------------- Settings
// Administrator view (finishing pass 2026-10-24): what this module controls, in four clickable cards, then each block.
const CH_ICON = {sms: 'message', email: 'doc', push: 'bell'} as const;
const SEND_CAPS: [string, string][] = [['communications.send.individual', 'un parent'], ['communications.send.class', 'une classe'],
  ['communications.send.section', 'une section'], ['communications.send.all_parents', 'toute l’école']];
type SchoolRole = {id: string; label: string; holders: number; capabilities: string[]; status: string};
async function schoolRoles(token: string): Promise<SchoolRole[]> {
  const r = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? '/api/v1'}/access/roles`, {headers: {Authorization: `Bearer ${token}`}});
  if (!r.ok) throw new Error('Rôles indisponibles');
  return (await r.json()).items;
}

function Settings({token, can, ready, schoolId, onChange, onNavigate}: {token: string; can: (p: string) => boolean; ready: Readiness; schoolId: string; onChange: () => void; onNavigate?: (m: string) => void}) {
  const [form, setForm] = useState({enabled: ready.enabled, sms_enabled: ready.sms_enabled, email_enabled: ready.email_enabled, push_enabled: ready.push_enabled,
    sms_low_balance_threshold: ready.sms_low_balance_threshold});
  const [ledger, setLedger] = useState<any[]>([]); const [saving, setSaving] = useState(false); const [roles, setRoles] = useState<SchoolRole[] | null>(null);
  const configure = can('notifications.internal.configure');
  useEffect(() => { if (can('communications.read')) void walletLedger(token).then(r => setLedger(r.items)).catch(() => setLedger([])); }, [token]);
  useEffect(() => { if (can('access.roles.read')) void schoolRoles(token).then(setRoles).catch(() => setRoles([])); }, [token]);
  const dirty = (Object.keys(form) as (keyof typeof form)[]).some(k => form[k] !== (ready as any)[k]);
  async function save() {
    setSaving(true);
    try { await saveSettings(token, {...form, expected_version: ready.version}); toast.success('Réglages de communication enregistrés'); onChange(); }
    catch (e) { toast.error(friendlyError(e)); } finally { setSaving(false); }
  }
  const go = (id: string) => document.getElementById(id)?.scrollIntoView({behavior: 'smooth', block: 'start'});
  const channels = [form.sms_enabled && 'SMS', form.email_enabled && 'e-mail', form.push_enabled && 'notifications'].filter(Boolean) as string[];
  const senders = (roles ?? []).filter(r => r.status === 'ACTIVE' && r.capabilities.some(c => c === 'communications.compose' || c.startsWith('communications.send.')));
  const support = pushSupport(); const pushHere = Boolean(rememberedSubscription(schoolId)) && support.permission === 'granted';
  const sw = (key: 'sms_enabled' | 'email_enabled' | 'push_enabled', label: string, hint: string, platformKey: 'sms' | 'email' | 'push') => {
    const state = ready.platform[platformKey].state; const off = !form.enabled;
    return <label className={`commToggle ${off ? 'muted' : ''}`}>
      <span className="commToggleIcon" aria-hidden="true"><NavGlyph g={CH_ICON[platformKey]} size={18}/></span>
      <span className="commToggleText"><b>{label}</b><small>{hint}</small><em className={`pill state-${String(state).toLowerCase()}`}>Plateforme : {STATE_LABEL[state]}</em></span>
      <input type="checkbox" role="switch" checked={Boolean(form[key])} disabled={!configure || off} onChange={e => setForm(f => ({...f, [key]: e.target.checked}))}/></label>;
  };
  return <div className="commAdmin">
    <div className="commOverview">
      <button type="button" className="commTile" onClick={() => go('comm-channels')}><span><NavGlyph g="sliders" size={20}/></span><b>{form.enabled ? (channels.length ? channels.join(' · ') : 'Aucun canal') : 'Désactivée'}</b><small>Canaux de l’école</small></button>
      {can('communications.read') && <button type="button" className={`commTile ${ready.wallet.low ? 'warn' : ''}`} onClick={() => go('comm-wallet')}><span><NavGlyph g="finance" size={20}/></span><b>{ready.wallet.available} SMS</b><small>{ready.wallet.low ? 'Solde bas : à recharger' : 'Solde disponible'}</small></button>}
      <button type="button" className="commTile" onClick={() => go('comm-device')}><span><NavGlyph g="bell" size={20}/></span><b>{pushHere ? 'Activées' : 'Non activées'}</b><small>Notifications sur cet appareil</small></button>
      {roles !== null && <button type="button" className="commTile" onClick={() => go('comm-senders')}><span><NavGlyph g="users" size={20}/></span><b>{senders.length} rôle(s)</b><small>Peuvent écrire aux familles</small></button>}
    </div>

    <div className="commGrid">
      <div className="commCard" id="comm-channels"><div className="commCardHead"><span className="commCardIcon"><NavGlyph g="sliders" size={18}/></span><div><h3>Canaux de l’école</h3><p>Ce que l’école autorise. Sans canal, EduSync fonctionne normalement : seuls les envois externes sont arrêtés.</p></div></div>
        <label className="commToggle master"><span className="commToggleIcon" aria-hidden="true"><NavGlyph g="message" size={18}/></span>
          <span className="commToggleText"><b>Communication externe</b><small>{form.enabled ? 'Activée : les rôles autorisés peuvent écrire aux familles.' : 'Désactivée : aucun SMS, e-mail ni notification ne part de l’école.'}</small></span>
          <input type="checkbox" role="switch" checked={form.enabled} disabled={!configure} onChange={e => setForm(f => ({...f, enabled: e.target.checked}))}/></label>
        {sw('sms_enabled', 'SMS', 'Facturé en unités sur le solde SMS de l’école.', 'sms')}
        {sw('email_enabled', 'E-mail', 'Gratuit pour l’école.', 'email')}
        {sw('push_enabled', 'Notifications', 'Sur les téléphones et ordinateurs qui les ont activées. Gratuit.', 'push')}
        <label className="commField"><span>Alerte quand le solde SMS descend sous</span>
          <input type="number" min={0} value={form.sms_low_balance_threshold} disabled={!configure} aria-label="Seuil d’alerte SMS"
            onChange={e => setForm(f => ({...f, sms_low_balance_threshold: Math.max(0, Number(e.target.value) || 0)}))}/></label>
        {configure ? <div className="commActions"><button className="primaryBtn" disabled={saving || !dirty} onClick={() => void save()}>{saving ? 'Enregistrement…' : dirty ? 'Enregistrer les réglages' : 'Réglages à jour'}</button></div>
          : <small>Seul l’administrateur système de l’école modifie ces réglages.</small>}
      </div>

      {can('communications.read') && <div className="commCard" id="comm-wallet"><div className="commCardHead"><span className="commCardIcon"><NavGlyph g="finance" size={18}/></span><div><h3>Solde SMS</h3><p>Une unité = un SMS facturable ; un message long compte plusieurs unités. Les crédits s’achètent auprès d’EduSync.</p></div></div>
        <div className="commWalletRow"><div><b>{ready.wallet.balance}</b><small>solde</small></div><div><b>{ready.wallet.reserved}</b><small>réservés</small></div>
          <div className={ready.wallet.low ? 'low' : ''}><b>{ready.wallet.available}</b><small>disponibles</small></div></div>
        <ul className="commLedger">{ledger.slice(0, 12).map(l => <li key={l.id}><span>{({TOPUP: 'Recharge', RESERVATION: 'Réservation', CONSUMPTION: 'Consommation', RELEASE: 'Libération',
          ADJUSTMENT: 'Ajustement', REFUND: 'Remboursement'} as Record<string, string>)[l.movement_type] ?? l.movement_type}<small>{fmt(l.created_at)}{l.reference ? ` · ${l.reference}` : ''}</small></span>
          <b className={l.direction === 'DEBIT' ? 'neg' : ''}>{l.direction === 'DEBIT' ? '−' : l.direction === 'CREDIT' ? '+' : ''}{l.quantity}</b></li>)}
          {ledger.length === 0 && <li className="commEmpty"><small>Aucun mouvement pour l’instant.</small></li>}</ul>
      </div>}

      <div id="comm-device"><PushOnThisDevice token={token} schoolId={schoolId} available={ready.platform.push.available}/></div>

      {roles !== null && <div className="commCard" id="comm-senders"><div className="commCardHead"><span className="commCardIcon"><NavGlyph g="users" size={18}/></span><div><h3>Qui peut écrire aux familles ?</h3><p>D’après les rôles de votre école. Pour confier l’envoi à quelqu’un, attribuez-lui l’un de ces rôles.</p></div></div>
        {senders.length === 0 ? <p className="commEmpty">Aucun rôle actif ne peut envoyer de message. Attribuez par exemple le rôle de préfet des études ou de directeur.</p>
          : <ul className="commRoles">{senders.map(r => {
            const scopes = SEND_CAPS.filter(([c]) => r.capabilities.includes(c)).map(([, l]) => l);
            return <li key={r.id}><span className="commRoleIcon" aria-hidden="true"><NavGlyph g="user" size={16}/></span>
              <span><b>{r.label}</b><small>{scopes.length ? `Écrit à ${scopes.join(', ')}` : 'Rédige des messages'}{r.capabilities.includes('communications.sms.bulk_send') ? ' · SMS groupés' : r.capabilities.includes('communications.sms.send') ? ' · SMS' : ''}</small></span>
              <em className={`pill ${r.holders ? 'ready' : ''}`}>{r.holders ? `${r.holders} personne(s)` : 'Personne'}</em></li>;
          })}</ul>}
        {onNavigate && can('access.roles.read') && <div className="commActions"><button className="softBtn" onClick={() => onNavigate('access')}><NavGlyph g="lock" size={15}/> Gérer dans Accès &amp; rôles</button></div>}
      </div>}
    </div>
  </div>;
}

function PushOnThisDevice({token, schoolId, available}: {token: string; schoolId: string; available: boolean}) {
  const support = pushSupport();
  const [active, setActive] = useState(Boolean(rememberedSubscription(schoolId)) && support.permission === 'granted');
  const [devices, setDevices] = useState<any[]>([]); const [busy, setBusy] = useState(false);
  const load = () => pushDevices(token).then(r => setDevices(r.items)).catch(() => setDevices([]));
  useEffect(() => { void load(); }, [token]);
  async function on() {
    setBusy(true);
    try { const r = await enablePush(token, schoolId); setActive(true); toast.success(r.simulated ? 'Notifications activées (mode développement simulé)' : 'Notifications activées sur cet appareil'); await load(); }
    catch (e) { toast.error(friendlyError(e)); } finally { setBusy(false); }
  }
  async function off() { setBusy(true); try { await disablePush(token, schoolId); setActive(false); toast.success('Notifications désactivées sur cet appareil'); await load(); } finally { setBusy(false); } }
  async function test() { try { const r = await pushTest(token); toast.success(`Test envoyé à ${r.devices} appareil(s)`); } catch (e) { toast.error(friendlyError(e)); } }
  return <div className="commCard"><div className="commCardHead"><span className="commCardIcon"><NavGlyph g="bell" size={18}/></span><div><h3>Notifications sur cet appareil</h3><p>Recevez ici les alertes d’EduSync, même application fermée.</p></div></div>
    {!support.supported ? <p className="commNotice">{support.reason}</p> : !available ? <p className="commNotice">Les notifications push ne sont pas encore disponibles sur la plateforme.</p> : <>
      <p className="commState">{active ? 'Activées sur cet appareil.' : support.permission === 'denied' ? 'Bloquées par le navigateur : réautorisez-les dans ses réglages.' : 'Non activées sur cet appareil.'}</p>
      <div className="commActions">
        {active ? <><button className="softBtn" disabled={busy} onClick={() => void off()}>Désactiver ici</button><button className="primaryBtn" onClick={() => void test()}>Envoyer un test</button></>
          : <button className="primaryBtn" disabled={busy || support.permission === 'denied'} onClick={() => void on()}>Activer les notifications</button>}
      </div></>}
    {devices.length > 0 && <ul className="commLedger">{devices.map(d => <li key={d.id}><span>{d.device_label || 'Appareil'}<small>depuis {fmt(d.created_at)}{d.last_error_code ? ` · ${d.last_error_code}` : ''}</small></span></li>)}</ul>}
  </div>;
}
