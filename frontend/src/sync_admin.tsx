// Synchronisation & appareils (administrator finishing pass 2026-10-24) — same data and capabilities as before
// (sync.status.read, sync.device.register / revoke, sync.conflicts.read / resolve), explained in plain French:
// what waits to be sent, which devices are trusted, which cases need a decision. Every count card opens its section.
import React, {useEffect, useRef, useState} from 'react';
import {toast} from 'sonner';
import {auditActionLabel} from './platform/labels';
import {confirmAction} from './platform/dialogs';
import {friendlyError} from './platform/errors';
import {NavGlyph} from './platform/nav_icons';
import {syncConflicts, syncDeviceRegister, syncDeviceRevoke, syncDevices, syncPendingOutbox, syncResolveConflict, syncReviewConflicts, syncStatus, type SyncCursor} from './api';
import './sync_admin.css';

type Props = {token: string; permissions: string[]};
const has = (p: string[], c: string) => p.includes(c);

export function ago(v?: string | null): string {
  if (!v) return 'jamais';
  const s = Math.round((Date.now() - new Date(v).getTime()) / 1000);
  if (Number.isNaN(s)) return '—';
  if (s < 60) return 'à l’instant';
  if (s < 3600) return `il y a ${Math.round(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
  if (s < 86400 * 30) return `il y a ${Math.round(s / 86400)} j`;
  return new Date(v).toLocaleDateString('fr-FR', {day: 'numeric', month: 'short', year: 'numeric'});
}
const platformLabel = (p?: string) => ({WEB: 'Navigateur', ANDROID: 'Android', IOS: 'iPhone / iPad', WINDOWS: 'Windows', DESKTOP: 'Ordinateur'} as Record<string, string>)[p ?? ''] ?? (p || 'Appareil');
const ref = (type: string, id: string) => `${auditActionLabel(type)} · ${String(id).slice(0, 8)}`;

export default function SyncAdminPage({token, permissions}: Props) {
  const [data, setData] = useState<any>({}); const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true);
  const [confCursor, setConfCursor] = useState<SyncCursor | undefined>(); const [outCursor, setOutCursor] = useState<SyncCursor | undefined>();
  const [arb, setArb] = useState<{id: string; decision: 'RESOLVED' | 'DISMISSED'; label: string} | null>(null); const [note, setNote] = useState('');
  const sections = {devices: useRef<HTMLElement>(null), outbox: useRef<HTMLElement>(null), review: useRef<HTMLElement>(null), rejected: useRef<HTMLElement>(null)};
  const go = (k: keyof typeof sections) => sections[k].current?.scrollIntoView({behavior: 'smooth', block: 'start'});
  async function load() {
    try {
      setError('');
      const d: any = {status: await syncStatus(token)};
      if (has(permissions, 'sync.status.read')) { [d.devices, d.outbox] = await Promise.all([syncDevices(token), syncPendingOutbox(token)]); }
      if (has(permissions, 'sync.conflicts.read')) { [d.conflicts, d.review] = await Promise.all([syncConflicts(token), syncReviewConflicts(token)]); }
      setConfCursor(d.conflicts?.next_cursor ? {at: d.conflicts.next_cursor.received_at, id: d.conflicts.next_cursor.id} : undefined);
      setOutCursor(d.outbox?.next_cursor ? {at: d.outbox.next_cursor.created_at, id: d.outbox.next_cursor.id} : undefined);
      setData(d);
    } catch (e) { setError(friendlyError(e)); } finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, [token]);
  async function moreConf() { if (!confCursor) return; try { setBusy(true); const n = await syncConflicts(token, confCursor); setData((d: any) => ({...d, conflicts: {...n, items: [...(d.conflicts?.items ?? []), ...(n.items ?? [])]}})); setConfCursor(n.next_cursor ? {at: n.next_cursor.received_at, id: n.next_cursor.id} : undefined); } catch (e) { toast.error(friendlyError(e)); } finally { setBusy(false); } }
  async function moreOut() { if (!outCursor) return; try { setBusy(true); const n = await syncPendingOutbox(token, outCursor); setData((d: any) => ({...d, outbox: {...n, items: [...(d.outbox?.items ?? []), ...(n.items ?? [])]}})); setOutCursor(n.next_cursor ? {at: n.next_cursor.created_at, id: n.next_cursor.id} : undefined); } catch (e) { toast.error(friendlyError(e)); } finally { setBusy(false); } }
  async function add() { try { setBusy(true); await syncDeviceRegister(token, {label: `Navigateur EduSync · ${new Date().toLocaleDateString('fr-FR')}`, platform: 'WEB'}); toast.success('Cet appareil est maintenant autorisé'); await load(); } catch (e) { toast.error(friendlyError(e)); } finally { setBusy(false); } }
  async function revoke(id: string, label: string) {
    if (!await confirmAction({title: `Révoquer « ${label} » ?`, message: 'Cet appareil ne pourra plus envoyer d’opérations hors connexion. Les opérations déjà reçues restent enregistrées. À faire en cas de perte, de vol ou de départ d’un agent.', confirmLabel: 'Révoquer l’appareil', danger: true})) return;
    try { setBusy(true); await syncDeviceRevoke(token, id); toast.success('Appareil révoqué'); await load(); } catch (e) { toast.error(friendlyError(e)); } finally { setBusy(false); }
  }
  async function resolve() {
    if (!arb) return; if (note.trim().length < 5) { toast.error('Justification obligatoire (5 caractères minimum)'); return; }
    try { setBusy(true); await syncResolveConflict(token, arb.id, {decision: arb.decision, note: note.trim()}); toast.success('Décision enregistrée dans le journal'); setArb(null); setNote(''); await load(); }
    catch (e) { toast.error(friendlyError(e)); } finally { setBusy(false); }
  }
  const devices: any[] = data.devices?.items ?? []; const activeDevices = devices.filter(x => !x.revoked_at);
  const outbox: any[] = data.outbox?.items ?? []; const review: any[] = data.review?.items ?? []; const rejected: any[] = data.conflicts?.items ?? [];
  const pending = data.status?.pending_outbox ?? outbox.length;
  const toHandle = review.length;
  return <div className="syncAdmin syncPremium">
    <header className="syncHero">
      <span className="syncHeroIcon" aria-hidden="true"><NavGlyph g="sync" size={26}/></span>
      <div><small>Fonctionnement hors connexion</small><h2>Synchronisation &amp; appareils</h2>
        <p>Sans Internet, EduSync garde les opérations sur l’appareil et les envoie au serveur dès le retour du réseau. Ici, vous voyez ce qui attend d’être envoyé, les appareils autorisés de l’école et les rares cas qui demandent votre décision.</p></div>
      <div className={`syncHealth ${loading ? '' : toHandle ? 'warn' : 'ok'}`} role="status">
        <NavGlyph g={toHandle ? 'alert' : 'checkCircle'} size={18}/>
        <span>{loading ? 'Vérification…' : toHandle ? `${toHandle} cas à arbitrer` : pending ? `${pending} opération(s) en cours d’envoi` : 'Tout est synchronisé'}</span>
      </div>
    </header>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="syncKpis">
      <Kpi icon="cloudUp" value={pending} label="En attente d’envoi" hint="Opérations gardées par les appareils" onClick={has(permissions, 'sync.status.read') ? () => go('outbox') : undefined}/>
      <Kpi icon="device" value={data.status?.active_devices ?? activeDevices.length} label="Appareils autorisés" hint="Ordinateurs et téléphones de l’école" onClick={has(permissions, 'sync.status.read') ? () => go('devices') : undefined}/>
      <Kpi icon="alert" value={review.length} label="Cas à arbitrer" hint="Même donnée modifiée à deux endroits" tone={review.length ? 'warn' : undefined} onClick={has(permissions, 'sync.conflicts.read') ? () => go('review') : undefined}/>
      <Kpi icon="shield" value={data.status?.finance_offline_enabled_by_default ? 'Autorisée' : 'Protégée'} label="Caisse hors connexion"
        hint={data.status?.finance_offline_enabled_by_default ? 'Encaissements hors ligne possibles' : 'Aucun encaissement hors ligne sans autorisation'}/>
    </div>

    {has(permissions, 'sync.status.read') && <section className="syncCard" ref={sections.devices}>
      <div className="syncCardHead"><span className="syncCardIcon"><NavGlyph g="device" size={18}/></span><div><h3>Appareils autorisés</h3><p>Seuls ces appareils peuvent envoyer des opérations faites hors connexion. Révoquez un appareil perdu, volé ou rendu par un agent.</p></div>
        {has(permissions, 'sync.device.register') && <button className="primaryBtn" disabled={busy} onClick={() => void add()}><NavGlyph g="plus" size={15}/> Autoriser cet appareil</button>}</div>
      {devices.length === 0 ? <Empty icon="device" title="Aucun appareil enregistré" text="Autorisez les ordinateurs de la caisse et du secrétariat pour qu’ils puissent travailler sans Internet."/>
        : <div className="deviceGrid">{devices.map(x => <article key={x.id} className={`deviceCard ${x.revoked_at ? 'revoked' : ''}`}>
          <span className="deviceIcon" aria-hidden="true"><NavGlyph g={x.platform === 'ANDROID' || x.platform === 'IOS' ? 'phone' : 'monitor'} size={20}/></span>
          <div><b>{x.label || 'Appareil'}</b><small>{platformLabel(x.platform)} · actif {ago(x.last_seen_at)}</small></div>
          <em className={`pill ${x.revoked_at ? '' : 'ready'}`}>{x.revoked_at ? 'Révoqué' : 'Autorisé'}</em>
          {!x.revoked_at && has(permissions, 'sync.device.revoke') && <button className="linkBtn danger" disabled={busy} onClick={() => void revoke(x.id, x.label || 'Appareil')}>Révoquer</button>}
        </article>)}</div>}
    </section>}

    {has(permissions, 'sync.status.read') && <section className="syncCard" ref={sections.outbox}>
      <div className="syncCardHead"><span className="syncCardIcon"><NavGlyph g="cloudUp" size={18}/></span><div><h3>En attente d’envoi</h3><p>Opérations reçues qui attendent d’être transmises aux autres services (notifications, rapports). Elles partent automatiquement.</p></div></div>
      {outbox.length === 0 ? <Empty icon="checkCircle" ok title="Rien en attente" text="Toutes les opérations ont été transmises."/>
        : <ul className="syncList">{outbox.map(x => <li key={x.id}><span><b>{auditActionLabel(x.event_type)}</b><small>{ref(x.aggregate_type, x.aggregate_id)} · {ago(x.created_at)}</small></span><em className="pill">{x.attempts ? `${x.attempts} tentative(s)` : 'En file'}</em></li>)}</ul>}
      {outCursor && <button className="softBtn" disabled={busy} onClick={() => void moreOut()}>Afficher plus</button>}
    </section>}

    {has(permissions, 'sync.conflicts.read') && <>
      <section className="syncCard" ref={sections.review}>
        <div className="syncCardHead"><span className="syncCardIcon warn"><NavGlyph g="alert" size={18}/></span><div><h3>Cas à arbitrer</h3><p>Une même donnée a été modifiée sur deux appareils pendant une coupure. Choisissez de valider la version reçue ou de classer le cas ; votre décision est inscrite au journal.</p></div></div>
        {review.length === 0 ? <Empty icon="checkCircle" ok title="Aucun cas à arbitrer" text="Les synchronisations se sont faites sans conflit."/>
          : <ul className="syncList">{review.map(x => <li key={x.id}><span><b>{ref(x.aggregate_type, x.aggregate_id)}</b><small>Version attendue {x.expected_version ?? '—'} · version trouvée {x.actual_version ?? '—'} · {ago(x.created_at)}</small></span>
            {has(permissions, 'sync.conflicts.resolve') ? <span className="syncActions"><button className="primaryBtn" disabled={busy} onClick={() => { setArb({id: x.id, decision: 'RESOLVED', label: ref(x.aggregate_type, x.aggregate_id)}); setNote(''); }}>Valider</button>
              <button className="softBtn" disabled={busy} onClick={() => { setArb({id: x.id, decision: 'DISMISSED', label: ref(x.aggregate_type, x.aggregate_id)}); setNote(''); }}>Classer</button></span> : <em className="pill">Lecture seule</em>}</li>)}</ul>}
      </section>
      <section className="syncCard" ref={sections.rejected}>
        <div className="syncCardHead"><span className="syncCardIcon"><NavGlyph g="info" size={18}/></span><div><h3>Opérations refusées</h3><p>Opérations hors connexion que le serveur a refusées (règle non respectée, donnée déjà changée). Elles n’ont rien modifié ; l’agent concerné doit refaire l’opération en ligne.</p></div></div>
        {rejected.length === 0 ? <Empty icon="checkCircle" ok title="Aucune opération refusée" text="Le serveur a accepté toutes les opérations reçues."/>
          : <ul className="syncList">{rejected.map(x => <li key={x.id}><span><b>{auditActionLabel(x.operation_type)}</b><small>{ref(x.aggregate_type, x.aggregate_id)} · {ago(x.received_at)}</small></span><em className="pill">{x.status}</em></li>)}</ul>}
        {confCursor && <button className="softBtn" disabled={busy} onClick={() => void moreConf()}>Afficher plus</button>}
      </section>
    </>}

    {arb && <div className="wizardBackdrop"><div className="accountSecurityDialog" role="dialog" aria-modal="true" aria-label="Arbitrer le cas">
      <div className="modalHead"><div><h3>{arb.decision === 'RESOLVED' ? 'Valider la version reçue' : 'Classer le cas'}</h3><p>{arb.label} — décision définitive, inscrite au journal.</p></div><button type="button" aria-label="Fermer" onClick={() => setArb(null)}>×</button></div>
      <label>Justification *<textarea value={note} onChange={e => setNote(e.target.value)} rows={4} autoFocus placeholder="Ex. vérifié avec le caissier, la version reçue est la bonne."/></label>
      <div className="modalActions"><button className="ghost" onClick={() => setArb(null)}>Annuler</button><button disabled={busy || note.trim().length < 5} onClick={() => void resolve()}>{arb.decision === 'RESOLVED' ? 'Confirmer' : 'Classer le cas'}</button></div>
    </div></div>}
  </div>;
}

function Kpi({icon, value, label, hint, tone, onClick}: {icon: string; value: React.ReactNode; label: string; hint: string; tone?: 'warn'; onClick?: () => void}) {
  const body = <><span className="syncKpiIcon" aria-hidden="true"><NavGlyph g={icon} size={20}/></span><b>{value}</b><span className="syncKpiLabel">{label}</span><small>{hint}</small></>;
  return onClick ? <button type="button" className={`syncKpi ${tone ?? ''}`} onClick={onClick}>{body}</button> : <div className={`syncKpi ${tone ?? ''}`}>{body}</div>;
}
function Empty({icon, title, text, ok}: {icon: string; title: string; text: string; ok?: boolean}) {
  return <div className={`syncEmpty ${ok ? 'ok' : ''}`}><NavGlyph g={icon} size={22}/><b>{title}</b><small>{text}</small></div>;
}
