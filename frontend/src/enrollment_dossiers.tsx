// Dossiers « en attente de paiement » (owner decision 2026-11-06): filled in by someone who cannot collect, nobody is
// enrolled yet. The direction may grant a waiver child by child; the cashier opens the dossier, collects the enrollment
// conditions and the children are enrolled in that same operation.
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {cancelEnrollmentDossier, completeEnrollmentDossier, listEnrollmentDossiers, previewEnrollmentDossier, setDossierWaiver,
  type AdmissionPayment, type AdmissionPreview, type EnrollmentDossier} from './api';
import {AdmissionSettlement, settlementAction, totalsText} from './admission_settlement';
import {promptText} from './platform/dialogs';
import {friendlyError} from './platform/errors';
import {NavGlyph} from './platform/nav_icons';

const when = (iso: string) => new Date(iso).toLocaleString('fr-FR', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'});

export function EnrollmentDossiers({token, can, onDone}: {token: string; can: (p: string) => boolean; onDone: () => Promise<void>}) {
  const [items, setItems] = useState<EnrollmentDossier[]>([]); const [open, setOpen] = useState<EnrollmentDossier | null>(null);
  const visible = ['enrollments.create', 'enrollments.reenroll', 'finance.checkout.collect', 'finance.decisions.create'].some(can);
  async function load() { if (visible) setItems(await listEnrollmentDossiers(token)); }
  useEffect(() => { void load(); }, [token, visible]);
  if (!visible || items.length === 0) return null;
  return <section className="ed-panel" aria-label="Dossiers d’inscription en attente">
    <header><span className="ed-icon" aria-hidden="true"><NavGlyph g="clock" size={18}/></span>
      <div><b>{items.length} dossier{items.length > 1 ? 's' : ''} d’inscription en attente de paiement</b><small>Aucun de ces enfants n’est encore inscrit : l’inscription devient effective quand les conditions sont encaissées.</small></div></header>
    <ul>{items.map(d => { const requested = d.waivers.filter(w => w.status === 'REQUESTED').length; const approved = d.waivers.filter(w => w.status === 'APPROVED').length;
      return <li key={d.id}><div><b>{d.label}</b><small>{d.children_count} enfant{d.children_count > 1 ? 's' : ''} · saisi le {when(d.created_at)}{approved ? ` · ${approved} dérogation${approved > 1 ? 's' : ''} accordée${approved > 1 ? 's' : ''}` : ''}</small>
        {requested > 0 && <em>{requested} dérogation{requested > 1 ? 's' : ''} demandée{requested > 1 ? 's' : ''}</em>}</div>
        <button type="button" className="ed-open" onClick={() => setOpen(d)}>{can('finance.checkout.collect') ? 'Encaisser et inscrire' : 'Ouvrir'}</button></li>; })}</ul>
    {open && <DossierDialog token={token} dossier={open} can={can} onClose={() => setOpen(null)} onDone={async () => { setOpen(null); await load(); await onDone(); }}/>}
  </section>;
}

function DossierDialog({token, dossier, can, onClose, onDone}: {token: string; dossier: EnrollmentDossier; can: (p: string) => boolean; onClose: () => void; onDone: () => Promise<void>}) {
  const [d, setD] = useState(dossier); const [preview, setPreview] = useState<AdmissionPreview | null>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [payment, setPayment] = useState<AdmissionPayment>({mode: 'CASH', reference: ''});
  const [drafts, setDrafts] = useState<Record<number, string>>(() => Object.fromEntries(dossier.waivers.map(w => [w.index, w.reason])));
  async function load(x = d) { try { setError(''); const p = await previewEnrollmentDossier(token, x.id); setPreview(p); if (p.dossier) setD(p.dossier); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(); }, []);
  async function saveWaiver(index: number, reason: string | null) {
    try { setBusy(true); const next = await setDossierWaiver(token, d, index, reason); setD(next); toast.success(reason ? 'Dérogation accordée' : 'Dérogation retirée'); await load(next); }
    catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  async function complete() {
    if (!preview) return;
    try { setBusy(true); setError('');
      const res = await completeEnrollmentDossier(token, d, preview.conditions.requires_payment ? {mode: payment.mode, reference: (payment.reference ?? '').trim() || null} : null);
      const receipts = (res?.admission_payment?.lines ?? []).map((l: any) => l.receipt_number).filter(Boolean);
      toast.success(`${d.label} : ${d.children_count} enfant${d.children_count > 1 ? 's' : ''} inscrit${d.children_count > 1 ? 's' : ''}`, {description: receipts.length ? `Conditions payées · reçus ${receipts.join(', ')}` : undefined, duration: 15000});
      await onDone();
    } catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  async function cancel() {
    const reason = await promptText({title: `Annuler le dossier ${d.label} ?`, message: 'Aucun élève n’a été inscrit ; le dossier sera gardé comme annulé dans l’historique.', label: 'Motif', confirmLabel: 'Annuler le dossier', minLength: 3});
    if (!reason) return;
    try { setBusy(true); await cancelEnrollmentDossier(token, d, reason); toast.success('Dossier annulé'); await onDone(); } catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  const approved = Object.fromEntries(d.waivers.filter(w => w.status === 'APPROVED').map(w => [w.index, w.reason]));
  const canCollect = can('finance.checkout.collect'); const canWaive = can('finance.decisions.create');
  const action = settlementAction(preview, d.children_count);
  return <div className="kp-backdrop" onClick={() => { if (!busy) onClose(); }}>
    <div className="kp-dialog ed-dialog" role="dialog" aria-modal="true" aria-labelledby="ed-title" onClick={e => e.stopPropagation()}>
      <header className="kp-dhead"><span className="kp-dicon"><NavGlyph g="receipt" size={22}/></span><div><h3 id="ed-title">{d.label}</h3>
        <p>Dossier en attente de paiement · {d.children_count} enfant{d.children_count > 1 ? 's' : ''}. L’inscription devient effective au moment de l’encaissement.</p></div>
        <button type="button" className="kp-close" aria-label="Fermer" onClick={onClose} disabled={busy}><NavGlyph g="close" size={18}/></button></header>
      <div className="kp-dbody">
        {d.waivers.some(w => w.status === 'REQUESTED') && <div className="kp-note"><NavGlyph g="info" size={16}/> Dérogation demandée : {d.waivers.filter(w => w.status === 'REQUESTED').map(w => `${preview?.conditions.children[w.index]?.name ?? `enfant ${w.index + 1}`} (« ${w.reason} »)`).join(', ')}. {canWaive ? 'Accordez-la ci-dessous si la direction l’approuve.' : 'La direction doit l’accorder avant l’encaissement, sinon l’enfant paie comme les autres.'}</div>}
        <AdmissionSettlement preview={preview} loading={!preview && !error} error={error && !preview ? error : ''} dossierMode={!canCollect}
          waivers={canWaive ? drafts : approved} payment={payment} onPayment={setPayment} approved={approved} onApprove={canWaive ? (i, r) => void saveWaiver(i, r) : undefined}
          onWaiver={(i, r) => { if (!canWaive) return; setDrafts(w => { const n = {...w}; if (r === null) delete n[i]; else n[i] = r; return n; }); if (r === null && approved[i] !== undefined) void saveWaiver(i, null); }}/>
        {error && preview && <div className="error" role="alert">{error}</div>}
      </div>
      <footer className="kp-dfoot"><span className="kp-summary">{preview ? (preview.conditions.requires_payment ? <>À encaisser : <b>{totalsText(preview.conditions.totals)}</b></> : 'Aucun paiement exigé') : '…'}</span>
        <button type="button" className="kp-btn ghost" onClick={() => void cancel()} disabled={busy}>Annuler le dossier</button>
        {canCollect && <button type="button" className="kp-btn primary" disabled={busy || !preview} onClick={() => void complete()}><NavGlyph g="check" size={16}/>{busy ? 'Inscription…' : action.kind === 'ENROLL' ? 'Inscrire' : action.label}</button>}</footer>
    </div></div>;
}
