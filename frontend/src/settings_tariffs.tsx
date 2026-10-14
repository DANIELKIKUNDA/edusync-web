// Tarifs & barèmes — copied from the Desktop golden master (app/ui/settings_page.py::_build_tariffs,
// app/db/configuration.py: upsert_tariff_rule, save_tariff_group_rule, save_monthly_billing_policy).
// A rule targets the school, a section, an academic class, an Humanities group or one class; it is dated and carries an
// official status. The most precise rule applies: class > academic class > Humanities group > section > school.
import React, {useEffect, useMemo, useState} from 'react';
import {toast} from 'sonner';
import {
  AcademicYear, BillingPolicy, FeeSchedule, FeeType, ReferenceCatalog, SchoolClass, SchoolSection, Tariff, TariffScope, TariffStatus,
  applyTariffs, getBillingPolicy, listFeeSchedules, putBillingPolicy, putTariffRule,
} from './api';
import {confirmAction} from './platform/dialogs';
import {friendlyError} from './platform/errors';
import {FormField} from './platform/forms';
import {formatDate, formatMoney} from './platform/format';

export const TARIFF_GROUPS: [string, string][] = [['GENERAL', 'Humanités générales'], ['TECHNICAL', 'Humanités techniques'], ['OTHER', 'Autre groupe']];
const SCOPES: [TariffScope, string][] = [['SCHOOL', 'Toute l’école'], ['SECTION', 'Section'], ['ACADEMIC_CLASS', 'Classe académique (niveau)'], ['OPTION_GROUP', 'Groupe d’Humanités'], ['CLASS', 'Classe ouverte']];
const STATUS_LABEL: Record<TariffStatus, string> = {ACTIVE: 'Actif', PENDING_OFFICIAL: 'En attente du barème officiel', INACTIVE: 'Inactif'};
const MONTHS: [string, string][] = [['09', 'Septembre'], ['10', 'Octobre'], ['11', 'Novembre'], ['12', 'Décembre'], ['01', 'Janvier'], ['02', 'Février'], ['03', 'Mars'], ['04', 'Avril'], ['05', 'Mai'], ['06', 'Juin'], ['07', 'Juillet'], ['08', 'Août']];
const PRIORITY: Record<TariffScope, number> = {CLASS: 1, ACADEMIC_CLASS: 2, OPTION_GROUP: 3, SECTION: 4, SCHOOL: 5};

type Props = {token: string; tariffs: Tariff[]; years: AcademicYear[]; fees: FeeType[]; classes: SchoolClass[]; sections: SchoolSection[];
  refs: ReferenceCatalog | null; can: (x: string) => boolean; onDone: () => Promise<void>};

export function TariffsSettings({token, tariffs, years, fees, classes, sections, refs, can, onDone}: Props) {
  const year = years.find(y => y.status === 'ACTIVE') ?? years.find(y => y.status === 'PREPARED');
  const yearRules = useMemo(() => tariffs.filter(t => t.academic_year_id === year?.id && t.enabled), [tariffs, year?.id]);
  const byFee = useMemo(() => {
    const m = new Map<string, Tariff[]>();
    for (const t of yearRules) m.set(t.fee_type_id, [...(m.get(t.fee_type_id) ?? []), t]);
    for (const list of m.values()) list.sort((a, b) => PRIORITY[a.scope_type] - PRIORITY[b.scope_type] || b.effective_from.localeCompare(a.effective_from));
    return [...m.entries()];
  }, [yearRules]);
  const [error, setError] = useState('');
  const [adding, setAdding] = useState(false);
  const locked = !year;
  const canManage = can('settings.tariffs.manage') && !locked;
  return <section className="panel">
    <div className="panelHead"><div><h3>Tarifs &amp; barèmes</h3><p>Tarifs hiérarchiques et datés : école → section → groupe d’Humanités → classe académique → classe ouverte. La règle la plus précise s’applique ; une nouvelle règle datée ne réécrit pas un mois déjà payé.</p></div></div>
    {error && <div className="error" role="alert">{error}</div>}
    {!year && <div className="emptyGuide"><b>Aucune année préparée ou en cours</b><p>Les tarifs appartiennent à une année scolaire : préparez-la d’abord.</p></div>}
    {year && yearRules.length === 0 && <div className="emptyGuide"><b>Aucune règle tarifaire pour {year.label}</b><p>{fees.length ? 'Ajoutez une règle pour chaque frais : par exemple un montant pour toute l’école, puis une règle plus précise pour une section ou une classe.' : 'Commencez par les types de frais, puis revenez fixer leurs montants.'}</p></div>}
    {byFee.map(([feeId, list]) => <div className="tariffGroup" key={feeId}>
      <h4>{list[0].fee_label ?? 'Frais'}</h4>
      <ul className="moneyList">{list.map(t => <li key={t.id} className={t.status === 'ACTIVE' ? '' : 'pending'}>
        <div><b>{t.scope_label ?? t.scope_type}</b><small>{SCOPES.find(s => s[0] === t.scope_type)?.[1]} · dès le {formatDate(t.effective_from)}{t.source_reference ? ` · ${t.source_reference}` : ''}</small></div>
        <div className="tariffAmount">{t.amount === null ? <em className="pill">À fixer</em> : <strong className="amount">{formatMoney(t.amount, t.currency)}</strong>}{t.status !== 'ACTIVE' && <small>{STATUS_LABEL[t.status]}</small>}</div>
      </li>)}</ul>
    </div>)}
    {canManage && (adding
      ? <RuleForm token={token} year={year!} fees={fees} classes={classes} sections={sections} refs={refs} can={can}
                  onCancel={() => setAdding(false)} onSaved={async () => { setAdding(false); await onDone(); }}/>
      : <button type="button" className="softBtn addLine" onClick={() => setAdding(true)}>+ Nouvelle règle tarifaire <small>{year?.label}</small></button>)}
    {can('settings.tariffs.read') && <BillingMonths token={token} canEdit={can('settings.billing_months.manage')} onError={setError}/>}
    {year && <Schedules token={token} year={year} canApply={can('settings.tariffs.apply') && !locked} onError={setError} onDone={onDone}/>}
    <p className="policyHint">Exemple : si l’école augmente le montant à partir de février, créez une nouvelle règle datée de février. Les mensualités antérieures gardent leur montant.</p>
  </section>;
}

function RuleForm({token, year, fees, classes, sections, refs, can, onCancel, onSaved}: {token: string; year: AcademicYear; fees: FeeType[]; classes: SchoolClass[];
  sections: SchoolSection[]; refs: ReferenceCatalog | null; can: (x: string) => boolean; onCancel: () => void; onSaved: () => Promise<void>}) {
  const [fee, setFee] = useState(''); const [scope, setScope] = useState<TariffScope>('SCHOOL'); const [target, setTarget] = useState('');
  const [amount, setAmount] = useState(''); const [currency, setCurrency] = useState<'CDF' | 'USD'>('CDF'); const [status, setStatus] = useState<TariffStatus>('ACTIVE');
  const [effective, setEffective] = useState(year.start_date); const [source, setSource] = useState(''); const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({}); const [error, setError] = useState('');
  const yearClasses = classes.filter(c => c.academic_year_id === year.id && (c.status ?? (c.enabled ? 'ACTIVE' : 'INACTIVE')) !== 'ARCHIVED');
  const academic = [...new Map(yearClasses.filter(c => c.reference_code).map(c => [c.reference_code!.toUpperCase(),
    refs?.classes.find(r => r.code.toUpperCase() === c.reference_code!.toUpperCase())?.label ?? c.reference_code!])).entries()];
  const targets: [string, string][] = scope === 'SECTION' ? sections.filter(s => s.enabled).map(s => [s.id, s.label])
    : scope === 'CLASS' ? yearClasses.map(c => [c.id, `${c.section_label ?? ''} · ${c.label}`])
    : scope === 'ACADEMIC_CLASS' ? academic : scope === 'OPTION_GROUP' ? TARIFF_GROUPS : [];
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!fee) errs.fee = 'Choisissez le type de frais.';
    if (scope !== 'SCHOOL' && !target) errs.target = 'Choisissez la cible de la règle.';
    if (amount.trim() && !/^\d+([.,]\d{1,2})?$/.test(amount.trim())) errs.amount = 'Montant en chiffres, deux décimales au plus (ex. 15000 ou 12,50).';
    if (status === 'ACTIVE' && !amount.trim()) errs.amount = 'Un tarif actif doit avoir un montant. Sinon, choisissez « En attente du barème officiel ».';
    if (effective < year.start_date || effective > year.end_date) errs.effective = `La date d’effet doit être dans l’année ${year.label}.`;
    setErrors(errs); if (Object.keys(errs).length) return;
    try {
      setBusy(true); setError('');
      await putTariffRule(token, {academic_year_id: year.id, fee_type_id: fee, scope_type: scope, scope_ref: scope === 'SCHOOL' ? null : target,
        amount: amount.trim() ? amount.trim().replace(',', '.') : null, currency, status, effective_from: effective, source_reference: source.trim() || null});
      toast.success('Règle tarifaire enregistrée'); await onSaved();
    } catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  return <form className="gridForm ruleForm" onSubmit={submit} noValidate>
    {error && <div className="error" role="alert">{error}</div>}
    <FormField label="Type de frais *" error={errors.fee}><select value={fee} onChange={e => setFee(e.target.value)}><option value="">Choisir…</option>{fees.filter(f => f.enabled !== false).map(f => <option key={f.id} value={f.id}>{f.label}</option>)}</select></FormField>
    <FormField label="Portée *"><select value={scope} onChange={e => { setScope(e.target.value as TariffScope); setTarget(''); }}>{SCOPES.filter(([s]) => s !== 'OPTION_GROUP' || can('settings.tariff_groups.manage')).map(([s, l]) => <option key={s} value={s}>{l}</option>)}</select></FormField>
    {scope !== 'SCHOOL' && <FormField label="Cible *" error={errors.target}><select value={target} onChange={e => setTarget(e.target.value)}><option value="">Choisir…</option>{targets.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></FormField>}
    <FormField label="Statut"><select value={status} onChange={e => setStatus(e.target.value as TariffStatus)}>{(Object.keys(STATUS_LABEL) as TariffStatus[]).map(s => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</select></FormField>
    <FormField label={status === 'ACTIVE' ? 'Montant *' : 'Montant (si connu)'} error={errors.amount}><input inputMode="decimal" autoComplete="off" value={amount} onChange={e => setAmount(e.target.value)} placeholder="0"/></FormField>
    <FormField label="Devise"><select value={currency} onChange={e => setCurrency(e.target.value as 'CDF' | 'USD')}><option>CDF</option><option>USD</option></select></FormField>
    <FormField label="Applicable dès *" error={errors.effective}><input type="date" min={year.start_date} max={year.end_date} value={effective} onChange={e => setEffective(e.target.value)}/></FormField>
    <FormField label="Référence officielle"><input value={source} maxLength={240} onChange={e => setSource(e.target.value)} placeholder="Ex. arrêté, circulaire"/></FormField>
    <div className="formActions"><button type="button" className="ghost" onClick={onCancel}>Annuler</button><button className="primaryBtn" disabled={busy}>{busy ? 'Enregistrement…' : 'Enregistrer la règle'}</button></div>
  </form>;
}

function BillingMonths({token, canEdit, onError}: {token: string; canEdit: boolean; onError: (m: string) => void}) {
  const [policy, setPolicy] = useState<BillingPolicy | null>(null); const [months, setMonths] = useState<string[]>([]); const [due, setDue] = useState(''); const [busy, setBusy] = useState(false);
  async function load() { try { const p = await getBillingPolicy(token); setPolicy(p); setMonths(p.billing_months); setDue(p.month_due_at_enrollment ?? ''); } catch (e) { onError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [token]);
  async function save() {
    if (!months.length) { onError('Sélectionnez au moins un mois facturé.'); return; }
    if (due && !months.includes(due)) { onError('Le mois exigé à l’inscription doit faire partie des mois facturés.'); return; }
    try { setBusy(true); await putBillingPolicy(token, {billing_months: months, month_due_at_enrollment: due || null, expected_version: policy?.version ?? null}); toast.success('Mois de facturation enregistrés'); await load(); }
    catch (e) { onError(friendlyError(e)); } finally { setBusy(false); }
  }
  if (!policy) return null;
  return <fieldset className="billingMonths" disabled={!canEdit || busy}>
    <legend>Facturation mensuelle</legend>
    <div className="monthGrid">{MONTHS.map(([code, label]) => <label key={code} className="checkField"><input type="checkbox" checked={months.includes(code)} onChange={e => setMonths(m => e.target.checked ? [...m, code] : m.filter(x => x !== code))}/> {label}</label>)}</div>
    <FormField label="Mois éventuellement exigé dès l’inscription"><select value={due} onChange={e => setDue(e.target.value)}><option value="">Aucun</option>{MONTHS.filter(([c]) => months.includes(c)).map(([c, l]) => <option key={c} value={c}>{l}</option>)}</select></FormField>
    {canEdit && <div className="formActions"><button type="button" className="softBtn" onClick={() => void save()}>Enregistrer les mois</button></div>}
  </fieldset>;
}

// Desktop « Appliquer les barèmes aux classes ouvertes »: schedule lines per class, then the due charges of every
// validated enrollment. A line that already received money is never rewritten (a dated rule is required instead).
function Schedules({token, year, canApply, onError, onDone}: {token: string; year: AcademicYear; canApply: boolean; onError: (m: string) => void; onDone: () => Promise<void>}) {
  const [rows, setRows] = useState<FeeSchedule[]>([]); const [busy, setBusy] = useState(false);
  async function load() { try { setRows(await listFeeSchedules(token, year.id)); } catch (e) { onError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [token, year.id]);
  const byClass = useMemo(() => { const m = new Map<string, FeeSchedule[]>(); for (const r of rows) m.set(r.class_label, [...(m.get(r.class_label) ?? []), r]); return [...m.entries()]; }, [rows]);
  async function apply() {
    if (!await confirmAction({title: `Appliquer les barèmes de ${year.label} ?`, message: 'Les échéances de chaque classe sont calculées à partir des règles tarifaires, puis les frais dus des élèves inscrits sont créés ou mis à jour. Une échéance déjà payée n’est jamais modifiée.', confirmLabel: 'Appliquer les barèmes'})) return;
    try {
      setBusy(true); const r = await applyTariffs(token, year.id);
      toast.success(`${r.materialized} échéance(s) appliquée(s) · ${r.charges_created} frais créés · ${r.charges_updated} mis à jour${r.pending_skipped ? ` · ${r.pending_skipped} en attente du barème officiel` : ''}`);
      await load(); await onDone();
    } catch (e) { onError(friendlyError(e)); } finally { setBusy(false); }
  }
  return <div className="schedules">
    <h4>Échéances par classe</h4>
    {rows.length === 0 && <p className="policyHint">Aucune échéance : appliquez les barèmes pour créer les échéances des classes et les frais dus des élèves.</p>}
    {byClass.map(([label, list]) => <details key={label} className="scheduleClass"><summary><b>{label}</b><small>{list.length} échéance(s)</small></summary>
      <ul className="moneyList">{list.map(r => <li key={r.id}><div><b>{r.fee_label}{r.period_label ? ` — ${r.period_label}` : ''}</b><small>{r.due_date ? `Échéance ${formatDate(r.due_date)}` : 'Sans échéance'} · {r.charge_count} élève(s)</small></div><strong className="amount">{formatMoney(r.amount, r.currency)}</strong></li>)}</ul>
    </details>)}
    {canApply && <div className="formActions"><button type="button" className="primaryBtn" disabled={busy} onClick={() => void apply()}>{busy ? 'Application…' : 'Appliquer les barèmes aux classes ouvertes'}</button></div>}
  </div>;
}
