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
import {getPolicy, putPolicy} from './api';
import {confirmAction} from './platform/dialogs';
import {friendlyError} from './platform/errors';
import {FormField} from './platform/forms';
import {formatDate} from './platform/format';
import {NavGlyph} from './platform/nav_icons';

const TIMING: Record<string, string> = {AT_ENROLLMENT: 'À l’inscription', AFTER_ENROLLMENT: 'Après l’inscription', OPTIONAL: 'Facultatif'};
const SCOPE: Record<string, string> = {SCHOOL: 'Toute l’école', SECTION: 'Section', ACADEMIC_CLASS: 'Classe académique', CLASS: 'Classe ouverte'};

type Props = {token: string; years: AcademicYear[]; fees: FeeType[]; sections: SchoolSection[]; classes: SchoolClass[]; refs: ReferenceCatalog | null; can: (x: string) => boolean};

export function AdmissionConditionsSettings({token, years, fees, sections, classes, refs, can, onChanged}: Props & {onChanged?: () => void}) {
  const [showRemoved, setShowRemoved] = useState(false);
  const year = years.find(y => y.status === 'ACTIVE') ?? years.find(y => y.status === 'PREPARED');
  const [items, setItems] = useState<AdmissionCondition[]>([]); const [review, setReview] = useState<{reviewed_at: string | null} | null>(null);
  const [editing, setEditing] = useState<AdmissionCondition | 'new' | null>(null); const [error, setError] = useState('');
  async function load() { if (!year) return; try { const r = await getAdmissionConditions(token, year.id); setItems(r.items); setReview(r.review); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [token, year?.id]);
  async function toggle(c: AdmissionCondition) {
    if (c.active && !await confirmAction({title: `Retirer « ${c.label} » ?`, message: 'La condition n’est plus exigée pour les prochaines inscriptions. Elle reste dans l’historique et peut être réactivée.', confirmLabel: 'Retirer', danger: true})) return;
    try { await setAdmissionConditionActive(token, c.id, !c.active); toast.success(c.active ? 'Condition retirée' : 'Condition réactivée'); await load(); onChanged?.(); } catch (e) { setError(friendlyError(e)); }
  }
  async function markReviewed() {
    try { await reviewAdmissionConditions(token); toast.success('Conditions d’inscription validées'); await load(); } catch (e) { setError(friendlyError(e)); }
  }
  // Several targets since 0109 (owner request 2026-11-08): « Maternelle, Primaire » or « 1re primaire A, 2e primaire A ».
  const scopeLabel = (c: AdmissionCondition) => {
    if (c.scope_type === 'SCHOOL') return SCOPE.SCHOOL;
    const one = (r: string) => c.scope_type === 'SECTION' ? sections.find(s => s.id === r)?.label ?? 'Section' : c.scope_type === 'CLASS' ? classes.find(x => x.id === r)?.label ?? 'Classe' : r;
    const list = (c.scope_refs?.length ? c.scope_refs : [c.scope_ref]).map(one);
    return list.length > 4 ? `${list.slice(0, 3).join(', ')} et ${list.length - 3} autres` : list.join(', ');
  };
  if (!year) return null;
  const manage = can('settings.enrollment_policy.manage');
  const shown = items.filter(c => c.active || showRemoved);
  return <div className="ach">
    {error && <div className="error" role="alert">{error}</div>}
    {items.length === 0 && <div className="emptyGuide"><b>Aucune condition pour {year.label}</b><p>Tant que la rubrique n’est pas validée, la caisse applique le lot historique : Inscription + mensualité de juin. Validez la rubrique même si l’école n’exige aucun frais à l’inscription.</p></div>}
    <div className="ac-cards">{shown.map(c => <article key={c.id} className={`ac-card ${c.active ? '' : 'off'}`}>
      <div className="ac-cardTop"><span className="ac-cardIcon" aria-hidden="true"><NavGlyph g="receipt" size={18}/></span><div><b>{c.label}</b><small>{c.fee_label ?? 'Sans frais lié'}</small></div></div>
      <div className="ac-tags"><span>{TIMING[c.payment_timing]}</span>{c.required && <span className="strong">Obligatoire</span>}{c.can_pay_later && <span>Paiement différé possible</span>}{!c.active && <span className="muted">Retirée</span>}</div>
      <div className="ac-scope"><NavGlyph g="layers" size={14}/><span>{scopeLabel(c)}</span></div>
      <div className="ac-actions">{manage && c.active && <button type="button" className="ac-btn" onClick={() => setEditing(c)}>Modifier</button>}
        {can('settings.enrollment_policy.activate') && <button type="button" className={`ac-btn ${c.active ? 'danger' : ''}`} onClick={() => void toggle(c)}>{c.active ? 'Retirer' : 'Réactiver'}</button>}</div>
    </article>)}
      {manage && <button type="button" className="ac-card ac-add" onClick={() => setEditing('new')}><span aria-hidden="true">+</span><b>Nouvelle condition</b><small>Frais exigé à l’inscription : juin, uniformes, pulls…</small></button>}
    </div>
    {items.some(c => !c.active) && <button type="button" className="ac-link" onClick={() => setShowRemoved(v => !v)}>{showRemoved ? 'Masquer les conditions retirées' : `Voir les conditions retirées (${items.filter(c => !c.active).length})`}</button>}
    {editing && <div className="ac-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setEditing(null); }}>
      <div className="ac-dialog" role="dialog" aria-modal="true" aria-label={editing === 'new' ? 'Nouvelle condition d’inscription' : `Modifier ${editing.label}`}>
        <header><div><span className="eyebrow">Conditions d’inscription · {year.label}</span><h3>{editing === 'new' ? 'Nouvelle condition' : editing.label}</h3></div>
          <button type="button" className="ac-close" aria-label="Fermer" onClick={() => setEditing(null)}><NavGlyph g="close" size={18}/></button></header>
        <ConditionForm token={token} year={year} fees={fees} sections={sections} classes={classes} refs={refs} current={editing === 'new' ? null : editing}
          onCancel={() => setEditing(null)} onSaved={async () => { setEditing(null); await load(); onChanged?.(); }}/>
      </div></div>}
    <div className="reviewRow"><span>{review?.reviewed_at ? `Rubrique validée le ${formatDate(review.reviewed_at)}` : 'Rubrique pas encore validée'}</span>
      {can('settings.enrollment_policy.review') && <button type="button" className="softBtn" onClick={() => void markReviewed()}>Valider les conditions d’inscription</button>}</div>
  </div>;
}

function ConditionForm({token, year, fees, sections, classes, refs, current, onCancel, onSaved}: {token: string; year: AcademicYear; fees: FeeType[]; sections: SchoolSection[];
  classes: SchoolClass[]; refs: ReferenceCatalog | null; current: AdmissionCondition | null; onCancel: () => void; onSaved: () => Promise<void>}) {
  const [label, setLabel] = useState(current?.label ?? ''); const [fee, setFee] = useState(current?.fee_type_id ?? '');
  const [required, setRequired] = useState(current?.required ?? true); const [timing, setTiming] = useState(current?.payment_timing ?? 'AT_ENROLLMENT');
  const [later, setLater] = useState(current?.can_pay_later ?? false); const [bundle, setBundle] = useState(current?.bundle_code ?? '');
  const [scope, setScope] = useState(current?.scope_type ?? 'SCHOOL'); const [picked, setPicked] = useState<string[]>(current && current.scope_type !== 'SCHOOL' ? (current.scope_refs?.length ? current.scope_refs : [current.scope_ref]) : []);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const yearClasses = classes.filter(c => c.academic_year_id === year.id);
  const levels = [...new Set(yearClasses.map(c => (c.reference_code ?? '').toUpperCase()).filter(Boolean))];
  const targets: [string, string][] = scope === 'SECTION' ? sections.map(s => [s.id, s.label]) : scope === 'CLASS' ? yearClasses.map(c => [c.id, c.label])
    : scope === 'ACADEMIC_CLASS' ? levels.map(l => [l, refs?.classes.find(r => r.code.toUpperCase() === l)?.label ?? l]) : [];
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (label.trim().length < 2) { setError('Donnez un libellé à la condition, par exemple « Frais d’inscription ».'); return; }
    if (scope !== 'SCHOOL' && !picked.length) { setError('Cochez au moins une section, un niveau ou une classe.'); return; }
    try {
      setBusy(true); setError('');
      await putAdmissionCondition(token, {academic_year_id: year.id, condition_id: current?.id ?? null, label: label.trim(), fee_type_id: fee || null, required, payment_timing: timing,
        can_pay_later: later, bundle_code: bundle.trim() || null, scope_type: scope, scope_ref: scope === 'SCHOOL' ? null : picked[0], scope_refs: scope === 'SCHOOL' ? null : picked, sort_order: current?.sort_order ?? 100, expected_version: current?.version ?? null});
      toast.success('Condition enregistrée'); await onSaved();
    } catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  return <form className="gridForm ruleForm" onSubmit={submit} noValidate>
    {error && <div className="error" role="alert">{error}</div>}
    <FormField label="Libellé *"><input value={label} maxLength={160} onChange={e => setLabel(e.target.value)}/></FormField>
    <FormField label="Frais lié" hint="Le montant se règle dans Tarifs & barèmes. Un frais nouveau (uniformes, pulls…) : créez-le d’abord dans Types de frais."><select value={fee} onChange={e => setFee(e.target.value)}><option value="">— Aucun frais lié —</option>{fees.map(f => <option key={f.id} value={f.id}>{f.label}</option>)}</select></FormField>
    <FormField label="Moment du paiement"><select value={timing} onChange={e => setTiming(e.target.value)}>{Object.entries(TIMING).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></FormField>
    <FormField label="Portée"><select value={scope} onChange={e => { setScope(e.target.value); setPicked([]); }}>{Object.entries(SCOPE).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></FormField>
    {scope !== 'SCHOOL' && <fieldset className="planTargets wide"><legend>{scope === 'SECTION' ? 'Sections concernées' : scope === 'CLASS' ? 'Classes concernées' : 'Niveaux concernés'} * <small>({picked.length} cochée{picked.length > 1 ? 's' : ''} sur {targets.length})</small></legend>
      {targets.length ? <TargetChecklist groups={scope === 'CLASS' ? sections.map(sec => [sec.label, yearClasses.filter(c => c.section_id === sec.id).map(c => [c.id, c.label] as [string, string])] as [string, [string, string][]]).filter(([, l]) => l.length) : [['', targets]]}
        picked={picked} onChange={setPicked}/>
        : <p className="policyHint">Aucune cible disponible : ouvrez d’abord les sections et les classes de l’année.</p>}
      <p className="policyHint">La condition s’applique aux élèves de chaque cible cochée ; les autres classes ne la paient pas à l’inscription.</p>
    </fieldset>}
    <FormField label="Regroupement (facultatif)"><input value={bundle} maxLength={48} onChange={e => setBundle(e.target.value)}/></FormField>
    <label className="checkField"><input type="checkbox" checked={required} onChange={e => setRequired(e.target.checked)}/> Obligatoire</label>
    <label className="checkField"><input type="checkbox" checked={later} onChange={e => setLater(e.target.checked)}/> Paiement différé possible</label>
    <div className="formActions"><button type="button" className="ghost" onClick={onCancel}>Annuler</button><button className="primaryBtn" disabled={busy}>{busy ? 'Enregistrement…' : 'Enregistrer la condition'}</button></div>
  </form>;
}

// Real checkboxes, grouped by section for classes (owner request 2026-11-08: « cocher plusieurs classes »).
export function TargetChecklist({groups, picked, onChange}: {groups: [string, [string, string][]][]; picked: string[]; onChange: (v: string[]) => void}) {
  const all = groups.flatMap(([, l]) => l.map(([v]) => v));
  const toggle = (v: string) => onChange(picked.includes(v) ? picked.filter(x => x !== v) : [...picked, v]);
  const setMany = (vs: string[], on: boolean) => onChange(on ? [...new Set([...picked, ...vs])] : picked.filter(x => !vs.includes(x)));
  return <div className="ac-targets">
    <div className="ac-tools"><button type="button" className="ac-link" onClick={() => onChange(all)}>Tout cocher</button><button type="button" className="ac-link" onClick={() => onChange([])}>Tout décocher</button></div>
    {groups.map(([title, list]) => { const vs = list.map(([v]) => v); const n = vs.filter(v => picked.includes(v)).length;
      return <div key={title || 'all'} className="ac-group">{title && <div className="ac-groupHead"><b>{title}</b><small>{n}/{vs.length}</small>
        <button type="button" className="ac-link" onClick={() => setMany(vs, n < vs.length)}>{n < vs.length ? 'Tout' : 'Aucune'}</button></div>}
        <div className="ac-grid">{list.map(([v, l]) => <label key={v} title={l} className={`ac-check ${picked.includes(v) ? 'on' : ''}`}><input type="checkbox" checked={picked.includes(v)} onChange={() => toggle(v)}/><span>{l}</span></label>)}</div></div>; })}
  </div>;
}

// Exemptions of the enrollment conditions (owner decision 2026-11-06): school-wide categories that are enrolled without
// paying the conditions now (the fees stay due later unless a benefit covers them). Individual cases: the direction
// grants a waiver child by child at enrollment (reason, audit).
const EXEMPTIONS: [string, string, string][] = [
  ['conditions_exempt_staff_children', 'Enfants du personnel', 'L’enfant d’un agent de l’école est inscrit sans payer les conditions à l’inscription.'],
  ['conditions_exempt_benefit_beneficiaries', 'Bénéficiaires d’avantages', 'Un enfant gratuit (famille nombreuse) ou bénéficiaire « enfant du personnel » est inscrit sans payer les conditions.'],
];
export function ConditionExemptions({token, canManage, onChanged}: {token: string; canManage: boolean; onChanged?: () => void}) {
  const [policy, setPolicy] = useState<any>(undefined); const [busy, setBusy] = useState(''); const [error, setError] = useState('');
  async function load() { try { setPolicy(await getPolicy(token, 'ENROLLMENT')); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [token]);
  const payload = (policy?.payload ?? {}) as Record<string, unknown>;
  async function toggle(key: string) {
    try { setBusy(key); setError('');
      await putPolicy(token, 'ENROLLMENT', {payload: {...payload, [key]: !payload[key]}, status: 'ACTIVE', expected_version: policy?.version ?? null});
      toast.success('Exemption des conditions d’inscription enregistrée'); await load(); onChanged?.();
    } catch (e) { setError(friendlyError(e)); } finally { setBusy(''); }
  }
  if (policy === undefined && !error) return null;
  return <div className="admExempt embedded">
    <small>Ces enfants sont inscrits sans payer à l’inscription ; leurs frais restent dus plus tard, sauf s’ils sont couverts par un avantage. Pour un cas particulier, la direction accorde une dérogation à l’inscription, avec un motif.</small>
    {error && <div className="error" role="alert">{error}</div>}
    {EXEMPTIONS.map(([key, label, hint]) => <label key={key} className="switchRow"><span>{label}<small>{hint}</small></span>
      <input type="checkbox" role="switch" checked={!!payload[key]} disabled={!canManage || !!busy} onChange={() => void toggle(key)}/></label>)}
  </div>;
}

// Paramètres → Inscriptions as clickable cards (owner request 2026-11-08): each card says in one line what is set;
// one card open at a time, never a long sheet of forms.
type HubKey = 'conditions' | 'exemptions' | 'rules';
export function EnrollmentSettingsHub(props: Props & {rules: React.ReactNode}) {
  const {token, years, can} = props;
  const year = years.find(y => y.status === 'ACTIVE') ?? years.find(y => y.status === 'PREPARED');
  const [open, setOpen] = useState<HubKey | null>('conditions');
  const [conds, setConds] = useState<AdmissionCondition[] | null>(null); const [policy, setPolicy] = useState<Record<string, unknown> | null>(null);
  async function load() {
    try { if (year) setConds((await getAdmissionConditions(token, year.id)).items); } catch { setConds(null); }
    try { setPolicy(((await getPolicy(token, 'ENROLLMENT'))?.payload ?? {}) as Record<string, unknown>); } catch { setPolicy(null); }
  }
  useEffect(() => { void load(); }, [token, year?.id]);
  const active = (conds ?? []).filter(c => c.active && c.required && c.payment_timing === 'AT_ENROLLMENT');
  const exempt = EXEMPTIONS.filter(([k]) => policy?.[k]).map(([, l]) => l);
  const extra = Array.isArray(policy?.required_student_fields) ? (policy!.required_student_fields as string[]).filter(k => !['last_name', 'middle_name', 'first_name', 'gender', 'class_id'].includes(k)).length : 0;
  const cards: [HubKey, string, string, string][] = [
    ['conditions', 'receipt', 'Conditions d’inscription', conds === null ? '…' : active.length ? `${active.length} frais exigé${active.length > 1 ? 's' : ''} à l’inscription : ${active.map(c => c.label).join(', ')}` : 'Aucun frais exigé à l’inscription'],
    ['exemptions', 'shield', 'Exemptions', policy === null ? '…' : exempt.length ? `Exemptés : ${exempt.join(', ')}` : 'Aucune catégorie exemptée · dérogation au cas par cas'],
    ['rules', 'doc', 'Règles de saisie', policy === null ? '…' : `5 informations obligatoires${extra ? ` + ${extra} exigée${extra > 1 ? 's' : ''} par l’école` : ''}${policy?.guardian_required_at_enrollment ? ' · responsable exigé' : ''}`],
  ];
  return <section className="panel ach-hub">
    <div className="panelHead"><div><h3>Inscriptions{year ? <small> · {year.label}</small> : null}</h3><p>Ce que l’école exige pour inscrire un enfant. Cliquez sur une carte pour la régler.</p></div></div>
    <div className="ach-cards">{cards.map(([key, icon, title, summary]) => { const on = open === key;
      return <article key={key} className={`ach-card ${on ? 'on' : ''}`}>
        <button type="button" className="ach-head" aria-expanded={on} onClick={() => { setOpen(on ? null : key); void load(); }}>
          <span className="ach-icon" aria-hidden="true"><NavGlyph g={icon as any} size={20}/></span>
          <span className="ach-text"><b>{title}</b><small>{summary}</small></span><span className="ach-chev" aria-hidden="true">{on ? '−' : '+'}</span></button>
        {on && <div className="ach-body">
          {key === 'conditions' && <AdmissionConditionsSettings {...props} onChanged={() => void load()}/>}
          {key === 'exemptions' && <ConditionExemptions token={token} canManage={can('settings.enrollment_policy.manage')} onChanged={() => void load()}/>}
          {key === 'rules' && props.rules}
        </div>}
      </article>; })}</div>
  </section>;
}
