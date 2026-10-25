// Situation financière in the pupil file (owner report 2026-10-25: « dans la fiche de l'élève je ne vois pas l'historique
// financier »). Reads the Desktop student_account statement the server already exposes: totals per currency (CDF and
// USD never mixed), every obligation of the current enrollment with its balance, every payment with its receipt.
import React, {useEffect, useMemo, useState} from 'react';
import {toast} from 'sonner';
import {getStudentAccount, printReceipt, studentAccountPdf, type StudentAccount} from './api';
import {friendlyError} from './platform/errors';
import {previewPdf} from './document_io';
import './student_finance.css';

const money = (v: string | number, cur: string) => `${new Intl.NumberFormat('fr-FR', {maximumFractionDigits: cur === 'USD' ? 2 : 0}).format(Number(v || 0))} ${cur === 'CDF' ? 'FC' : cur}`;
const MODE: Record<string, string> = {CASH: 'Espèces', MOBILE_MONEY: 'Mobile Money', BANQUE: 'Banque', AUTRE: 'Autre'};
const PAY: Record<string, string> = {VALIDE: 'Validé', ANNULE: 'Annulé', REMBOURSE: 'Remboursé'};
const dt = (v: string) => new Date(v).toLocaleString('fr-FR', {day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'});
const day = (v?: string | null) => v ? new Date(`${v}T12:00:00`).toLocaleDateString('fr-FR', {day: '2-digit', month: 'short'}) : '—';

export function StudentFinancePanel({token, studentId, can}: {token: string; studentId: string; can: (p: string) => boolean}) {
  const [data, setData] = useState<StudentAccount | null>(null);
  const [err, setErr] = useState('');
  const [view, setView] = useState<'charges' | 'payments'>('charges');
  const [onlyOpen, setOnlyOpen] = useState(false);
  useEffect(() => { let alive = true; setData(null); setErr('');
    getStudentAccount(token, studentId).then(d => { if (alive) setData(d); }).catch(e => { if (alive) setErr(friendlyError(e)); });
    return () => { alive = false; }; }, [token, studentId]);
  const charges = useMemo(() => (data?.charges ?? []).filter(c => !onlyOpen || Number(c.balance) > 0), [data, onlyOpen]);
  async function statement() { try { previewPdf(await studentAccountPdf(token, studentId)); } catch (e) { toast.error(friendlyError(e)); } }
  async function receipt(id: string, no: string) { try { previewPdf(await printReceipt(token, id)); toast.success(`Reçu ${no} ouvert`); } catch (e) { toast.error(friendlyError(e)); } }

  return <section className="sf-root" aria-labelledby="sf-title">
    <header className="sf-head"><h4 id="sf-title">Situation financière</h4>{data && <small>{data.student.year_label} · {data.student.class_label}</small>}
      {can('students.account.export') && data && <button type="button" className="sf-link" onClick={() => void statement()}>Relevé PDF</button>}</header>
    {err ? <p className="sf-empty" role="alert">{err}</p> : !data ? <div className="sf-skel"><i/><i/><i/></div> : <>
      {data.summary.length === 0 ? <p className="sf-empty">Aucun frais n’est encore généré pour l’inscription de cette année.</p>
        : <div className="sf-sum">{data.summary.map(s => <div key={s.currency} className={Number(s.balance) > 0 ? 'due' : 'ok'}>
          <span>{s.currency === 'CDF' ? 'Francs congolais' : 'Dollars'}</span>
          <b>{money(s.balance, s.currency)}</b><small>reste à payer</small>
          <em><i style={{width: `${Math.min(100, s.recovery_rate)}%`}}/></em>
          <small>{money(s.paid, s.currency)} payés sur {money(s.net_expected, s.currency)} · {s.recovery_rate.toLocaleString('fr-FR')} %</small></div>)}</div>}
      <div className="sf-tabs" role="tablist">
        <button role="tab" aria-selected={view === 'charges'} className={view === 'charges' ? 'on' : ''} onClick={() => setView('charges')}>Frais ({data.charges.length})</button>
        <button role="tab" aria-selected={view === 'payments'} className={view === 'payments' ? 'on' : ''} onClick={() => setView('payments')}>Paiements ({data.payments.length})</button>
        {view === 'charges' && <label className="sf-only"><input type="checkbox" checked={onlyOpen} onChange={e => setOnlyOpen(e.target.checked)}/> Seulement les impayés</label>}
      </div>
      {view === 'charges' ? <div className="sf-table" role="table" aria-label="Frais de l’élève">
        <div className="sf-row sf-th" role="row"><span>Frais</span><span>Échéance</span><span>Dû</span><span>Payé</span><span>Reste</span></div>
        {charges.map(c => { const bal = Number(c.balance), paid = Number(c.paid);
          return <div className="sf-row" role="row" key={c.id}><span><b>{c.label}</b><em className={`sf-chip ${bal <= 0 ? 'ok' : paid > 0 ? 'part' : 'due'}`}>{bal <= 0 ? 'Soldé' : paid > 0 ? 'Partiel' : 'Impayé'}</em></span>
            <span>{day(c.due_date)}</span><span>{money(c.net_amount, c.currency)}</span><span>{money(c.paid, c.currency)}</span><span className={bal > 0 ? 'sf-due' : ''}>{money(c.balance, c.currency)}</span></div>; })}
        {charges.length === 0 && <p className="sf-empty">{onlyOpen ? 'Tout est soldé.' : 'Aucun frais.'}</p>}
      </div> : <div className="sf-table" role="table" aria-label="Paiements de l’élève">
        <div className="sf-row sf-pay sf-th" role="row"><span>Reçu</span><span>Date</span><span>Mode</span><span>Montant</span><span>Statut</span></div>
        {data.payments.map(p => <div className={`sf-row sf-pay${p.status !== 'VALIDE' ? ' void' : ''}`} role="row" key={p.payment_id ?? p.receipt_no}>
          <span>{can('finance.receipts.reprint') && p.payment_id ? <button type="button" className="sf-link" onClick={() => void receipt(p.payment_id, p.receipt_no)} title="Réimprimer le reçu">{p.receipt_no}</button> : <b>{p.receipt_no}</b>}</span>
          <span>{dt(p.paid_at)}</span><span>{MODE[p.mode] ?? p.mode}</span><span><b>{money(p.amount, p.currency)}</b></span><span><em className={`sf-chip ${p.status === 'VALIDE' ? 'ok' : 'due'}`}>{PAY[p.status] ?? p.status}</em></span></div>)}
        {data.payments.length === 0 && <p className="sf-empty">Aucun paiement enregistré pour cette inscription.</p>}
      </div>}
    </>}
  </section>;
}
