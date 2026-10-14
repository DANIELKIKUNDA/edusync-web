// Conditions d'inscription — copied from the Desktop golden master (app/ui/settings_page.py::_build_enrollment,
// app/db/configuration.py: upsert_enrollment_policy_item, set_enrollment_policy_item_active, mark_enrollment_policy_reviewed).
// An admission condition is an obligation of the school year (linked fee, required, payment timing, scope). The required
// "at enrollment" conditions form the registration bundle the cash desk settles first.
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {
  AcademicYear, AdmissionCondition, FeeType, ReferenceCatalog, SchoolClass, SchoolSection,
  getAdmissionConditions, putAdmissionCondition, reviewAdmissionConditions, setAdmissionConditionActive,
} from './api';
import {confirmAction} from './platform/dialogs';
import {friendlyError} from './platform/errors';
import {FormField} from './platform/forms';
import {formatDate} from './platform/format';

const TIMING: Record<string, string> = {AT_ENROLLMENT: 'À l’inscription', AFTER_ENROLLMENT: 'Après l’inscription', OPTIONAL: 'Facultatif'};
const SCOPE: Record<string, string> = {SCHOOL: 'Toute l’école', SECTION: 'Section', ACADEMIC_CLASS: 'Classe académique', CLASS: 'Classe ouverte'};

type Props = {token: string; years: AcademicYear[]; fees: FeeType[]; sections: SchoolSection[]; classes: SchoolClass[]; refs: ReferenceCatalog | null; can: (x: string) => boolean};

export function AdmissionConditionsSettings({token, years, fees, sections, classes, refs, can}: Props) {
  const year = years.find(y => y.status === 'ACTIVE') ?? years.find(y => y.status === 'PREPARED');
  const [items, setItems] = useState<AdmissionCondition[]>([]); const [review, setReview] = useState<{reviewed_at: string | null} | null>(null);
  const [editing, setEditing] = useState<AdmissionCondition | 'new' | null>(null); const [error, setError] = useState('');
  async function load() { if (!year) return; try { const r = await getAdmissionConditions(token, year.id); setItems(r.items); setReview(r.review); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [token, year?.id]);
  async function toggle(c: AdmissionCondition) {
    if (c.active && !await confirmAction({title: `Retirer « ${c.label} » ?`, message: 'La condition n’est plus exigée pour les prochaines inscriptions. Elle reste dans l’historique et peut être réactivée.', confirmLabel: 'Retirer', danger: true})) return;
    try { await setAdmissionConditionActive(token, c.id, !c.active); toast.success(c.active ? 'Condition retirée' : 'Condition réactivée'); await load(); } catch (e) { setError(friendlyError(e)); }
  }
  async function markReviewed() {
    try { await reviewAdmissionConditions(token); toast.success('Conditions d’inscription validées'); await load(); } catch (e) { setError(friendlyError(e)); }
  }
  const scopeLabel = (c: AdmissionCondition) => c.scope_type === 'SECTION' ? sections.find(s => s.id === c.scope_ref)?.label ?? 'Section'
    : c.scope_type === 'CLASS' ? classes.find(x => x.id === c.scope_ref)?.label ?? 'Classe' : c.scope_type === 'ACADEMIC_CLASS' ? c.scope_ref : SCOPE.SCHOOL;
  if (!year) return null;
  return <section className="panel">
    <div className="panelHead"><div><h3>Conditions d’inscription</h3><p>Ce qui est exigé à l’inscription, ce qui peut attendre et la portée de chaque condition. Les conditions obligatoires « à l’inscription » forment le lot que la caisse encaisse en premier.</p></div></div>
    {error && <div className="error" role="alert">{error}</div>}
    {items.length === 0 && <div className="emptyGuide"><b>Aucune condition pour {year.label}</b><p>Tant que la rubrique n’est pas validée, la caisse applique le lot historique : Inscription + mensualité de juin. Validez la rubrique même si l’école n’exige aucun frais à l’inscription.</p></div>}
    <ul className="moneyList">{items.map(c => <li key={c.id} className={c.active ? '' : 'pending'}>
      <div><b>{c.label}</b><small>{c.fee_label ?? 'Sans frais lié'} · {TIMING[c.payment_timing]}{c.required ? ' · obligatoire' : ''}{c.can_pay_later ? ' · paiement différé possible' : ''} · {scopeLabel(c)}{c.active ? '' : ' · retirée'}</small></div>
      <div className="classActions">{can('settings.enrollment_policy.manage') && c.active && <button type="button" className="ghost" onClick={() => setEditing(c)}>Modifier</button>}
        {can('settings.enrollment_policy.activate') && <button type="button" className={c.active ? 'ghost dangerText' : 'softBtn'} onClick={() => void toggle(c)}>{c.active ? 'Retirer' : 'Réactiver'}</button>}</div>
    </li>)}</ul>
    {editing && <ConditionForm token={token} year={year} fees={fees} sections={sections} classes={classes} refs={refs} current={editing === 'new' ? null : editing}
      onCancel={() => setEditing(null)} onSaved={async () => { setEditing(null); await load(); }}/>}
    {!editing && can('settings.enrollment_policy.manage') && <button type="button" className="softBtn addLine" onClick={() => setEditing('new')}>+ Nouvelle condition</button>}
    <div className="reviewRow"><span>{review?.reviewed_at ? `Rubrique validée le ${formatDate(review.reviewed_at)}` : 'Rubrique pas encore validée'}</span>
      {can('settings.enrollment_policy.review') && <button type="button" className="softBtn" onClick={() => void markReviewed()}>Valider les conditions d’inscription</button>}</div>
  </section>;
}

function ConditionForm({token, year, fees, sections, classes, refs, current, onCancel, onSaved}: {token: string; year: AcademicYear; fees: FeeType[]; sections: SchoolSection[];
  classes: SchoolClass[]; refs: ReferenceCatalog | null; current: AdmissionCondition | null; onCancel: () => void; onSaved: () => Promise<void>}) {
  const [label, setLabel] = useState(current?.label ?? ''); const [fee, setFee] = useState(current?.fee_type_id ?? '');
  const [required, setRequired] = useState(current?.required ?? true); const [timing, setTiming] = useState(current?.payment_timing ?? 'AT_ENROLLMENT');
  const [later, setLater] = useState(current?.can_pay_later ?? false); const [bundle, setBundle] = useState(current?.bundle_code ?? '');
  const [scope, setScope] = useState(current?.scope_type ?? 'SCHOOL'); const [target, setTarget] = useState(current?.scope_type === 'SCHOOL' ? '' : current?.scope_ref ?? '');
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const yearClasses = classes.filter(c => c.academic_year_id === year.id);
  const levels = [...new Set(yearClasses.map(c => (c.reference_code ?? '').toUpperCase()).filter(Boolean))];
  const targets: [string, string][] = scope === 'SECTION' ? sections.map(s => [s.id, s.label]) : scope === 'CLASS' ? yearClasses.map(c => [c.id, c.label])
    : scope === 'ACADEMIC_CLASS' ? levels.map(l => [l, refs?.classes.find(r => r.code.toUpperCase() === l)?.label ?? l]) : [];
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (label.trim().length < 2) { setError('Donnez un libellé à la condition, par exemple « Frais d’inscription ».'); return; }
    if (scope !== 'SCHOOL' && !target) { setError('Choisissez la cible de la condition.'); return; }
    try {
      setBusy(true); setError('');
      await putAdmissionCondition(token, {academic_year_id: year.id, condition_id: current?.id ?? null, label: label.trim(), fee_type_id: fee || null, required, payment_timing: timing,
        can_pay_later: later, bundle_code: bundle.trim() || null, scope_type: scope, scope_ref: scope === 'SCHOOL' ? null : target, sort_order: current?.sort_order ?? 100, expected_version: current?.version ?? null});
      toast.success('Condition enregistrée'); await onSaved();
    } catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  return <form className="gridForm ruleForm" onSubmit={submit} noValidate>
    {error && <div className="error" role="alert">{error}</div>}
    <FormField label="Libellé *"><input value={label} maxLength={160} onChange={e => setLabel(e.target.value)}/></FormField>
    <FormField label="Frais lié"><select value={fee} onChange={e => setFee(e.target.value)}><option value="">— Aucun frais lié —</option>{fees.map(f => <option key={f.id} value={f.id}>{f.label}</option>)}</select></FormField>
    <FormField label="Moment du paiement"><select value={timing} onChange={e => setTiming(e.target.value)}>{Object.entries(TIMING).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></FormField>
    <FormField label="Portée"><select value={scope} onChange={e => { setScope(e.target.value); setTarget(''); }}>{Object.entries(SCOPE).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></FormField>
    {scope !== 'SCHOOL' && <FormField label="Cible *"><select value={target} onChange={e => setTarget(e.target.value)}><option value="">Choisir…</option>{targets.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></FormField>}
    <FormField label="Regroupement (facultatif)"><input value={bundle} maxLength={48} onChange={e => setBundle(e.target.value)}/></FormField>
    <label className="checkField"><input type="checkbox" checked={required} onChange={e => setRequired(e.target.checked)}/> Obligatoire</label>
    <label className="checkField"><input type="checkbox" checked={later} onChange={e => setLater(e.target.checked)}/> Paiement différé possible</label>
    <div className="formActions"><button type="button" className="ghost" onClick={onCancel}>Annuler</button><button className="primaryBtn" disabled={busy}>{busy ? 'Enregistrement…' : 'Enregistrer la condition'}</button></div>
  </form>;
}
