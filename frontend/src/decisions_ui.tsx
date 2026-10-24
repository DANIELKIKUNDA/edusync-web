// N3-C — financial decisions copied from the Desktop golden master (app/db/financial_decisions.py): creation with scope,
// nature, value, priority, cumulative flag, period and effective dates; cancellation with reason; the pupil's financial
// view (status per charge, decisions applied in order, planned responsibility). Superior authority: GESTIONNAIRE.
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {CheckoutPerson, checkoutSearch, createDecision, setChargeResponsibility, studentFinanceView, type OperatorCharge} from './api';
import {friendlyError} from './platform/errors';
import {formatMoney} from './platform/format';
import {openStudentAccountPdf} from './reports_ui';

export const KIND_LABEL: Record<string, string> = {DISCOUNT: 'Réduction', EXEMPTION: 'Exonération', INDIVIDUAL_FREE: 'Gratuité individuelle',
  COLLECTIVE_EXEMPTION: 'Exonération collective', DIRECTION_EXCEPTION: 'Exception de la direction', THIRD_PARTY_COVERAGE: 'Prise en charge par un tiers',
  REDUCTION: 'Réduction (ancienne)', SPONSORSHIP: 'Parrainage (ancien)', OTHER: 'Autre (ancien)'};
const STATUS_LABEL: Record<string, string> = {NEUTRALISEE: 'Neutralisé', EXONEREE: 'Exonéré', SOLDEE: 'Soldé', PARTIELLE: 'Partiel', A_REGLER: 'À régler'};
const FULL = ['EXEMPTION', 'INDIVIDUAL_FREE', 'COLLECTIVE_EXEMPTION'];
const money = (v: string | number, c: string) => formatMoney(String(v), c);

function Finder({token, onChoose}: {token: string; onChoose: (p: CheckoutPerson) => void}) {
  const [q, setQ] = useState(''); const [hits, setHits] = useState<CheckoutPerson[]>([]);
  useEffect(() => { if (q.trim().length < 2) { setHits([]); return; } const t = window.setTimeout(() => checkoutSearch(token, q).then(x => setHits(x.items)).catch(() => setHits([])), 200); return () => window.clearTimeout(t); }, [q, token]);
  return <div className="decisionFinder"><input aria-label="Rechercher un élève" placeholder="Nom ou matricule de l’élève…" value={q} onChange={e => setQ(e.target.value)}/>
    {hits.length > 0 && <div className="checkoutHits">{hits.map(p => <button key={p.enrollment_id} onClick={() => { onChoose(p); setQ(''); setHits([]); }}><b>{p.last_name} {p.middle_name} {p.first_name}</b><span>{p.matricule} · {p.class_label}</span></button>)}</div>}</div>;
}

export function StudentFinancePanel({token, can}: {token: string; can: (p: string) => boolean}) {
  const [person, setPerson] = useState<CheckoutPerson | null>(null); const [view, setView] = useState<Awaited<ReturnType<typeof studentFinanceView>> | null>(null);
  const [error, setError] = useState(''); const [form, setForm] = useState(false); const [resp, setResp] = useState<OperatorCharge | null>(null);
  async function load(p = person) { if (!p) return; try { setView(await studentFinanceView(token, p.student_id)); setError(''); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [person?.enrollment_id]);
  return <section className="decisionPanel">
    <div className="reportControls dense"><span className="controlHint">Une exonération ou réduction est une décision traçable, appliquée par ordre de priorité ; le tarif n’est jamais modifié.</span></div>
    <Finder token={token} onChoose={p => { setPerson(p); setForm(false); }}/>
    {error && <div className="error" role="alert">{error}</div>}
    {person && view && <>
      <div className="payerStrip"><div className="payerAvatar">{person.last_name[0]}{person.first_name[0]}</div><div><b>{person.last_name} {person.middle_name} {person.first_name}</b><span>{person.matricule} · {person.class_label}</span>
        <small>{Object.entries(view.summary).map(([c, s]) => `${c} : net ${money(s.net, c)} · réglé ${money(s.settled, c)} · reste ${money(s.remaining, c)}`).join(' — ')}</small></div>
        {can('students.account.export') && <button onClick={() => void openStudentAccountPdf(token, person.student_id)}>Relevé PDF</button>}{can('finance.decisions.create') && <button onClick={() => setForm(f => !f)}>{form ? 'Fermer' : 'Nouvelle décision'}</button>}</div>
      {form && <DecisionForm token={token} person={person} charges={view.charges} onDone={async () => { setForm(false); await load(); }}/>}
      <ul className="operatorCharges">{view.charges.map(c => <li key={c.id} className={`op-${c.status}`}>
        <div><b>{c.period_label || c.label}</b><small>{STATUS_LABEL[c.status]} · brut {money(c.gross, c.currency)} · net {money(c.net, c.currency)} · réglé {money(c.settled, c.currency)}</small>
          {c.decisions.map((d, i) => <small key={i}>↳ {KIND_LABEL[d.decision_kind] ?? d.decision_kind} ({d.value_type === 'PERCENT' ? `${Number(d.value_amount)} %` : money(d.value_amount, c.currency)}, priorité {d.priority}) : −{money(d.applied_amount, c.currency)}</small>)}
          {c.responsibility && <small>Prévu : {c.responsibility.responsibility_type === 'THIRD_PARTY' ? 'tiers' : c.responsibility.responsibility_type === 'PAYROLL_DEDUCTION' ? 'retenue sur salaire' : 'famille'} {money(c.responsibility.planned_amount, c.currency)}{c.responsibility.responsible_name ? ` · ${c.responsibility.responsible_name}` : ''}</small>}</div>
        <div className="opRight"><strong>{money(c.remaining, c.currency)}</strong>{can('finance.responsibility.set') && Number(c.remaining) > 0 && <button className="ghost" onClick={() => setResp(c)}>Responsabilité</button>}</div></li>)}</ul>
      {resp && <ResponsibilityForm token={token} charge={resp} onClose={() => setResp(null)} onDone={async () => { setResp(null); await load(); }}/>}
    </>}
  </section>;
}

function DecisionForm({token, person, charges, onDone}: {token: string; person: CheckoutPerson; charges: OperatorCharge[]; onDone: () => Promise<void>}) {
  // Settings parity 2026-10-24: several fees (or several instalments) at once — one traceable decision per target.
  const [kind, setKind] = useState('DISCOUNT'); const [scope, setScope] = useState('FEE_CODE'); const [ref, setRef] = useState(''); const [picked, setPicked] = useState<string[]>([]);
  const feeTypes = [...new Map(charges.filter(c => c.fee_code).map(c => [c.fee_code!, c.fee_label || c.label])).entries()];
  const [valueType, setValueType] = useState<'PERCENT' | 'FIXED'>('PERCENT'); const [amount, setAmount] = useState(''); const [currency, setCurrency] = useState<'CDF' | 'USD'>('CDF');
  const [priority, setPriority] = useState('100'); const [cumulative, setCumulative] = useState(true); const [periodStart, setPeriodStart] = useState(''); const [periodEnd, setPeriodEnd] = useState('');
  const [effective, setEffective] = useState(''); const [reason, setReason] = useState(''); const [reference, setReference] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const full = FULL.includes(kind);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (reason.trim().length < 3) { setError('Le motif de la décision financière est obligatoire.'); return; }
    const targets = scope === 'FEE_CODE' || scope === 'CHARGE' ? picked : scope === 'FEE_CATEGORY' ? [ref.trim()] : [null];
    if (scope !== 'ALL_FEES' && !targets.filter(Boolean).length) { setError(scope === 'FEE_CODE' ? 'Cochez au moins un frais concerné.' : scope === 'CHARGE' ? 'Cochez au moins une échéance.' : 'La cible de la décision financière est obligatoire.'); return; }
    if (!full && !/^\d+([.,]\d{1,2})?$/.test(amount.trim())) { setError('Valeur en chiffres, deux décimales au plus.'); return; }
    if (!full && valueType === 'PERCENT' && Number(amount.replace(',', '.')) > 100) { setError('Un pourcentage ne dépasse pas 100.'); return; }
    try {
      setBusy(true); setError(''); let done = 0;
      for (const target of targets) {
        const name = scope === 'FEE_CODE' ? feeTypes.find(([c]) => c === target)?.[1] : scope === 'CHARGE' ? charges.find(c => c.id === target)?.label : null;
        try {
          await createDecision(token, {enrollment_id: person.enrollment_id, decision_type: kind, scope_type: scope, scope_ref: target,
            value_type: full ? 'PERCENT' : valueType, amount: full ? '100' : amount.replace(',', '.'), currency, priority: Number(priority) || 100, cumulative,
            period_start: periodStart || null, period_end: periodEnd || null, effective_date: effective || null, reason: reason.trim(), reference: reference.trim() || null});
          done++;
        } catch (err) { throw new Error(`${name ? `${name} : ` : ''}${friendlyError(err)}${done ? ` (${done} décision(s) déjà enregistrée(s))` : ''}`); }
      }
      toast.success(done > 1 ? `${done} décisions enregistrées et appliquées` : 'Décision enregistrée et appliquée'); await onDone();
    } catch (err) { setError(err instanceof Error ? err.message : friendlyError(err)); } finally { setBusy(false); }
  }
  return <form className="benefitCard decisionForm" onSubmit={submit} noValidate>
    {error && <div className="error" role="alert">{error}</div>}
    <fieldset disabled={busy}><legend>Nouvelle décision financière</legend>
      <div className="benefitGrid">
        <label>Nature<select value={kind} onChange={e => setKind(e.target.value)}>{Object.entries(KIND_LABEL).slice(0, 6).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label>Portée<select value={scope} onChange={e => { setScope(e.target.value); setRef(''); setPicked([]); }}><option value="FEE_CODE">Un ou plusieurs frais</option><option value="CHARGE">Une ou plusieurs échéances précises</option><option value="ALL_FEES">Tous les frais</option><option value="FEE_CATEGORY">Une catégorie de frais (code)</option></select></label>
        {scope === 'FEE_CATEGORY' && <label>Code de la catégorie<input value={ref} maxLength={80} onChange={e => setRef(e.target.value)}/></label>}
        {full ? <p className="policyHint">Exonération et gratuité : toujours 100 % (règle Desktop).</p> : <>
          <label>Valeur<select value={valueType} onChange={e => setValueType(e.target.value as 'PERCENT' | 'FIXED')}><option value="PERCENT">Pourcentage</option><option value="FIXED">Montant fixe</option></select></label>
          <label>{valueType === 'PERCENT' ? 'Pourcentage' : 'Montant'}<input inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)}/></label>
          {valueType === 'FIXED' && <label>Devise<select value={currency} onChange={e => setCurrency(e.target.value as 'CDF' | 'USD')}><option value="CDF">CDF</option><option value="USD">USD</option></select></label>}</>}
        <label>Priorité (plus petit = appliqué d’abord)<input inputMode="numeric" value={priority} onChange={e => setPriority(e.target.value)}/></label>
        <label className="checkField"><input type="checkbox" checked={cumulative} onChange={e => setCumulative(e.target.checked)}/> Cumulable avec les autres décisions</label>
        <label>Période : du (facultatif)<input type="date" value={periodStart} onChange={e => setPeriodStart(e.target.value)}/></label>
        <label>au<input type="date" value={periodEnd} onChange={e => setPeriodEnd(e.target.value)}/></label>
        <label>Applicable aux échéances à partir du<input type="date" value={effective} onChange={e => setEffective(e.target.value)}/></label>
        <label>Motif *<input value={reason} maxLength={500} onChange={e => setReason(e.target.value)}/></label>
        <label>Référence (facultatif)<input value={reference} maxLength={120} onChange={e => setReference(e.target.value)}/></label>
      </div>
      {(scope === 'FEE_CODE' || scope === 'CHARGE') && <div className="feeChecks" role="group" aria-label={scope === 'FEE_CODE' ? 'Frais concernés' : 'Échéances concernées'}>
        <span>{scope === 'FEE_CODE' ? 'Frais concernés' : 'Échéances concernées'} <small>({picked.length} choisi{picked.length > 1 ? 's' : ''} · une décision par {scope === 'FEE_CODE' ? 'frais' : 'échéance'})</small></span>
        <div className="feeCheckGrid">{(scope === 'FEE_CODE' ? feeTypes : charges.map(c => [c.id, c.period_label ? `${c.fee_label ?? c.label} — ${c.period_label}` : c.label] as [string, string])).map(([v, l]) =>
          <label key={v} className="checkField"><input type="checkbox" checked={picked.includes(v)} onChange={e => setPicked(p => e.target.checked ? [...p, v] : p.filter(x => x !== v))}/> {l}</label>)}</div>
        {scope === 'FEE_CODE' && !feeTypes.length && <small className="policyHint">Aucun frais dû pour cet élève : appliquez d’abord les barèmes.</small>}
      </div>}
      <p className="policyHint">Sans date, la décision s’applique aux échéances à partir d’aujourd’hui (règle Desktop).</p>
      <div className="formActions"><button className="primaryBtn">{busy ? 'Enregistrement…' : 'Enregistrer la décision'}</button></div>
    </fieldset>
  </form>;
}

function ResponsibilityForm({token, charge, onClose, onDone}: {token: string; charge: OperatorCharge; onClose: () => void; onDone: () => Promise<void>}) {
  const [type, setType] = useState('THIRD_PARTY'); const [amount, setAmount] = useState(String(Number(charge.remaining))); const [name, setName] = useState('');
  const [reason, setReason] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (reason.trim().length < 3) { setError('Le motif est obligatoire.'); return; }
    if (Number(amount.replace(',', '.')) > Number(charge.remaining)) { setError('La responsabilité prévue ne peut pas dépasser le restant réel de ce frais.'); return; }
    try { setBusy(true); await setChargeResponsibility(token, charge.id, {responsibility_type: type, planned_amount: amount.replace(',', '.'), responsible_name: name.trim() || null, reason: reason.trim()}); toast.success('Responsabilité prévue enregistrée'); await onDone(); }
    catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  return <form className="benefitCard" onSubmit={submit} noValidate>
    {error && <div className="error" role="alert">{error}</div>}
    <fieldset disabled={busy}><legend>Qui réglera « {charge.period_label || charge.label} » ? (reste {money(charge.remaining, charge.currency)})</legend>
      <div className="benefitGrid">
        <label>Règlement prévu<select value={type} onChange={e => setType(e.target.value)}><option value="FAMILY_CASH">Famille, à la caisse</option><option value="PAYROLL_DEDUCTION">Retenue sur salaire</option><option value="THIRD_PARTY">Tiers (bourse, organisme)</option></select></label>
        <label>Montant prévu<input inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)}/></label>
        <label>Responsable (facultatif)<input value={name} maxLength={160} onChange={e => setName(e.target.value)}/></label>
        <label>Motif *<input value={reason} maxLength={500} onChange={e => setReason(e.target.value)}/></label>
      </div>
      <div className="formActions"><button type="button" className="ghost" onClick={onClose}>Annuler</button><button className="primaryBtn">{busy ? 'Enregistrement…' : 'Enregistrer'}</button></div>
    </fieldset>
  </form>;
}
