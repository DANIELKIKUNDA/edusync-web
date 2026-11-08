// Atomic enrollment (owner report 2026-11-06): before anything is saved, the form shows — child by child, with the
// class — what the school requires at enrollment, who is exempted and the family total. The payment and the enrollment
// are one operation: « Encaisser et inscrire ». Without the right to collect, the form becomes a dossier « en attente »
// that the cashier completes.
import React from 'react';
import type {AdmissionPayment, AdmissionPreview} from './api';
import {formatMoney} from './platform/format';
import {NavGlyph} from './platform/nav_icons';
import './admission_settlement.css';

export const PAYMENT_MODES: [AdmissionPayment['mode'], string][] = [['CASH', 'Espèces'], ['MOBILE_MONEY', 'Mobile Money'], ['BANQUE', 'Banque'], ['AUTRE', 'Autre']];

export function totalsText(totals: Record<string, string>): string {
  const parts = Object.entries(totals).filter(([, v]) => Number(v) > 0).map(([c, v]) => formatMoney(v, c));
  return parts.join(' + ') || 'rien';
}

/** What the primary button says, so the user knows exactly what will happen. */
export function settlementAction(p: AdmissionPreview | null, n: number): {label: string; kind: 'PAY' | 'DOSSIER' | 'ENROLL' | 'BLOCKED'} {
  const plural = n > 1 ? 's' : '';
  // A required fee not configured for a class (owner report 2026-11-08): nothing can be enrolled until it is configured
  // or waived; someone who cannot collect may still keep the dossier « en attente ».
  if (p?.conditions.blocked && p.can_collect) return {label: 'Conditions à configurer', kind: 'BLOCKED'};
  if (!p || !p.conditions.requires_payment) return {label: `Valider ${n} inscription${plural}`, kind: 'ENROLL'};
  if (!p.can_collect) return {label: 'Enregistrer le dossier (paiement à la caisse)', kind: 'DOSSIER'};
  return {label: `Encaisser ${totalsText(p.conditions.totals)} et inscrire`, kind: 'PAY'};
}

export function AdmissionSettlement({preview, loading, error, waivers, onWaiver, payment, onPayment, dossierMode, approved, onApprove}: {
  preview: AdmissionPreview | null; loading: boolean; error: string; waivers: Record<number, string>; onWaiver: (index: number, reason: string | null) => void;
  payment: AdmissionPayment; onPayment: (p: AdmissionPayment) => void; dossierMode?: boolean; approved?: Record<number, string>; onApprove?: (index: number, reason: string) => void}) {
  if (loading && !preview) return <div className="as-box as-loading" role="status"><span className="as-spin" aria-hidden="true"/>Calcul des conditions d’inscription…</div>;
  if (error) return <div className="error" role="alert">{error}</div>;
  if (!preview) return null;
  const c = preview.conditions;
  const canWaive = preview.can_waive; const canRequest = !canWaive && (dossierMode || !preview.can_collect);
  const anyConfigured = c.children.some(x => x.configured);
  return <div className="as-box" role="region" aria-label="Conditions d’inscription">
    {preview.offline && <div className="as-offline" role="status"><NavGlyph g="wifiOff" size={18}/><div><b>Hors connexion : l’inscription sera enregistrée sur cet appareil, en attente</b>
      <span>Montants de la copie de cet appareil (mise à jour {new Date(preview.offline.generated_at).toLocaleString('fr-FR', {day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit'})}). L’inscription et le paiement seront envoyés automatiquement au retour du réseau ; le serveur attribuera alors les matricules et les reçus, après avoir tout revérifié.</span></div></div>}
    <header className="as-head"><span className="as-icon" aria-hidden="true"><NavGlyph g="receipt" size={20}/></span>
      <div><b>Conditions d’inscription fixées par l’école</b>
        <small>{anyConfigured ? 'Rien n’est enregistré tant que ces frais ne sont pas payés : les enfants, leurs frais et les reçus sont enregistrés ensemble, en une seule opération.' : 'L’école n’exige aucun paiement à l’inscription.'}</small></div></header>
    <ul className="as-rows">{c.children.map(ch => { const w = waivers[ch.index]; const waived = ch.exemption?.kind === 'WAIVER' || (w !== undefined && w !== null);
      return <li key={ch.index} className={ch.exemption ? 'exempt' : ch.blocked ? 'blocked' : ch.to_pay ? 'due' : 'free'}>
        <div className="as-who"><b>{ch.name || `Enfant ${ch.index + 1}`}</b><small>{ch.class_label}</small></div>
        <div className="as-items">{ch.items.length ? ch.items.map(i => <span key={i.charge_id}>{i.label} · {formatMoney(i.amount, i.currency)}</span>) : (ch.blocked || ch.exemption ? null : <span className="as-none">{ch.configured ? 'Rien à payer à l’inscription' : 'Aucune condition fixée pour cette classe'}</span>)}
          {!ch.exemption && ch.missing?.map(m => <span key={m} className="as-missing"><NavGlyph g="alert" size={13}/>{m} : non configuré pour {ch.class_label || 'cette classe'}</span>)}
          {ch.exemption && <em className="as-exempt"><NavGlyph g="check" size={13}/>{ch.exemption.label}{ch.exemption.reason ? ` : ${ch.exemption.reason}` : ''}</em>}
          {!ch.exemption && w !== undefined && w !== null && !canWaive && <em className="as-request">Dérogation demandée : {w || '(motif à préciser)'}</em>}</div>
        <div className="as-amount">{ch.exemption ? <span className="as-zero">Exempté</span> : ch.blocked ? <span className="as-todo">À configurer{ch.to_pay ? ` + ${totalsText(ch.totals)}` : ''}</span> : ch.to_pay ? <b>{totalsText(ch.totals)}</b> : <span className="as-zero">0</span>}</div>
        {(canWaive || canRequest) && (ch.to_pay || ch.blocked || waived) && <div className="as-waiver">
          {w === undefined || w === null
            ? <button type="button" className="as-link" onClick={() => onWaiver(ch.index, '')}>{canWaive ? 'Accorder une dérogation' : 'Demander une dérogation à la direction'}</button>
            : <label className="as-reason"><span>{canWaive ? 'Motif de la dérogation (direction)' : 'Motif de la demande'}</span>
                <input value={w} maxLength={300} placeholder="Ex. orphelin pris en charge par la paroisse" onChange={e => onWaiver(ch.index, e.target.value)}/>
                {onApprove && w.trim().length >= 5 && approved?.[ch.index] !== w && <button type="button" className="as-approve" onClick={() => onApprove(ch.index, w.trim())}>Accorder</button>}
                <button type="button" className="as-link danger" onClick={() => onWaiver(ch.index, null)}>Retirer</button></label>}
        </div>}
      </li>; })}</ul>
    {c.blocked && c.blocked_message && <div className="as-blocked" role="alert"><NavGlyph g="alert" size={18}/><div><b>Inscription impossible pour l’instant</b><span>{c.blocked_message}</span></div></div>}
    {c.requires_payment && <footer className="as-foot">
      <div className="as-total"><span>Total à payer par la famille</span><b>{totalsText(c.totals)}</b></div>
      {preview.can_collect && !dossierMode ? <div className="as-pay">
        <div className="as-modes" role="radiogroup" aria-label="Mode de paiement">{PAYMENT_MODES.map(([m, l]) =>
          <button key={m} type="button" role="radio" aria-checked={payment.mode === m} className={payment.mode === m ? 'on' : ''} onClick={() => onPayment({...payment, mode: m})}>{l}</button>)}</div>
        {payment.mode !== 'CASH' && <input className="as-ref" aria-label="Référence du paiement" placeholder="Référence (n° de transaction, bordereau…)" value={payment.reference ?? ''} maxLength={80}
          onChange={e => onPayment({...payment, reference: e.target.value})}/>}
        <small>Un reçu individuel est émis pour chaque enfant.</small></div>
        : <p className="as-note"><NavGlyph g="info" size={15}/> {preview.can_collect ? 'Le dossier sera gardé en attente : il pourra être encaissé plus tard.' : 'Vous ne pouvez pas encaisser : le dossier sera enregistré « en attente de paiement », sans aucun élève inscrit. Le caissier l’encaissera et l’inscription deviendra effective en une seule opération.'}</p>}
    </footer>}
  </div>;
}
