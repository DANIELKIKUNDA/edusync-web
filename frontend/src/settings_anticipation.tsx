// Plans de paiement anticipé — copied from the Desktop golden master (app/ui/settings_page.py, plans anticipés;
// app/db/anticipation.py::save_anticipation_plan). A plan routes part of a monthly payment to NAMED future months of one
// monthly fee; it never holds a provision (Plan anticipé ≠ Fonds anticipé). A plan with memberships keeps its structure:
// deactivate it and create a new version.
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {AcademicYear, FeeType, ReferenceCatalog, SchoolClass, SchoolSection, getAnticipationPlans, putAnticipationPlan, setAnticipationPlanActive, type AnticipationPlan} from './api';
import {friendlyError} from './platform/errors';
import {FormField} from './platform/forms';
import {confirmAction} from './platform/dialogs';
import {formatDate} from './platform/format';
import {TARIFF_GROUPS} from './settings_tariffs';
import {DateInput} from './platform/date_input';

export const SCHOOL_MONTHS: [string, string][] = [['09', 'Septembre'], ['10', 'Octobre'], ['11', 'Novembre'], ['12', 'Décembre'], ['01', 'Janvier'], ['02', 'Février'],
  ['03', 'Mars'], ['04', 'Avril'], ['05', 'Mai'], ['06', 'Juin'], ['07', 'Juillet'], ['08', 'Août']];
export const monthName = (m: string) => SCHOOL_MONTHS.find(([c]) => c === m)?.[1] ?? m;
const SCOPES: [AnticipationPlan['scope_type'], string][] = [['SCHOOL', 'Toute l’école'], ['SECTION', 'Section'], ['OPTION_GROUP', 'Groupe d’Humanités'], ['ACADEMIC_CLASS', 'Classe académique (niveau)'], ['CLASS', 'Classe ouverte']];

type Props = {token: string; years: AcademicYear[]; fees: FeeType[]; classes: SchoolClass[]; sections: SchoolSection[]; refs: ReferenceCatalog | null; can: (x: string) => boolean};

export function AnticipationPlansSettings({token, years, fees, classes, sections, refs, can}: Props) {
  const year = years.find(y => y.status === 'ACTIVE') ?? years.find(y => y.status === 'PREPARED');
  const [rows, setRows] = useState<AnticipationPlan[] | null>(null); const [error, setError] = useState('');
  const [editing, setEditing] = useState<AnticipationPlan | 'new' | null>(null);
  async function load() { if (!year) { setRows([]); return; } try { setRows(await getAnticipationPlans(token, year.id)); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [token, year?.id]);
  const editable = can('finance.anticipation_plans.manage') && !!year;
  const yearClasses = classes.filter(c => year && c.academic_year_id === year.id && (c.status ?? (c.enabled ? 'ACTIVE' : 'INACTIVE')) !== 'ARCHIVED');
  // Several targets of the same kind since migration 0089 (owner request 2026-10-24).
  const one = (p: AnticipationPlan, ref: string) => p.scope_type === 'SECTION' ? sections.find(s => s.id === ref)?.label ?? ''
    : p.scope_type === 'OPTION_GROUP' ? TARIFF_GROUPS.find(([c]) => c === ref)?.[1] ?? ref
    : p.scope_type === 'CLASS' ? yearClasses.find(c => c.id === ref)?.label ?? ''
    : refs?.classes.find(r => r.code.toUpperCase() === ref)?.label ?? ref;
  const scopeLabel = (p: AnticipationPlan) => {
    if (p.scope_type === 'SCHOOL') return 'Toute l’école';
    const list = (p.scope_refs?.length ? p.scope_refs : [p.scope_ref]).map(r => one(p, r)).filter(Boolean);
    const kind = {SECTION: 'Section', OPTION_GROUP: 'Groupe', CLASS: 'Classe', ACADEMIC_CLASS: 'Niveau'}[p.scope_type];
    return list.length > 3 ? `${list.length} ${kind?.toLowerCase()}s : ${list.slice(0, 3).join(', ')}…` : `${kind}${list.length > 1 ? 's' : ''} ${list.join(', ')}`;
  };
  async function toggle(p: AnticipationPlan) {
    if (p.active && !await confirmAction({title: 'Désactiver ce plan ?', message: 'Il ne sera plus proposé à la caisse. Les adhésions et paiements déjà enregistrés restent intacts.', confirmLabel: 'Désactiver'})) return;
    try { await setAnticipationPlanActive(token, p.id, !p.active); toast.success(p.active ? 'Plan désactivé' : 'Plan réactivé'); await load(); } catch (e) { setError(friendlyError(e)); }
  }
  return <section className="panel">
    <div className="panelHead"><div><h3>Plans de paiement anticipé</h3><p>Un plan dirige une partie d’un paiement mensuel vers des mois futurs nommés d’un même frais. Il ne crée pas de réserve : c’est différent d’une avance libre (fonds anticipé).</p></div>
      {editable && !editing && <button className="primaryBtn" onClick={() => setEditing('new')}>Nouveau plan</button>}</div>
    {error && <div className="error" role="alert">{error}</div>}
    {!year && <div className="emptyGuide"><b>Aucune année préparée ou en cours</b><p>Les plans se règlent pour une année scolaire.</p></div>}
    {year && editing && <PlanForm token={token} year={year} fees={fees} sections={sections} yearClasses={yearClasses} refs={refs} current={editing === 'new' ? null : editing}
      onCancel={() => setEditing(null)} onSaved={async () => { setEditing(null); await load(); }}/>}
    {year && rows && rows.length === 0 && !editing && <div className="emptyGuide"><b>Aucun plan pour {year.label}</b><p>Sans plan, la caisse encaisse normalement ; aucun paiement anticipé n’est proposé.</p></div>}
    {rows && rows.length > 0 && <ul className="classList planList">{rows.map(p => <li key={p.id} className={p.active ? '' : 'muted'}>
      <div><b>{p.name}</b><small>{p.fee_label} · {scopeLabel(p)} · {p.participation_mode === 'MANDATORY' ? 'obligatoire' : 'facultatif'}{p.active ? '' : ' · désactivé'}</small>
        <small>Mois cibles : {p.target_months.map(monthName).join(', ')}</small>
        <small>Contribution : {p.contribution_months.map(monthName).join(', ')} · répartition égale · dès le {formatDate(p.effective_from)}</small>
        <small>{p.memberships ?? 0} adhésion(s)</small></div>
      {editable && <div className="rowActions"><button className="softBtn" onClick={() => setEditing(p)}>Modifier</button><button className="ghost" onClick={() => void toggle(p)}>{p.active ? 'Désactiver' : 'Réactiver'}</button></div>}
    </li>)}</ul>}
  </section>;
}

function PlanForm({token, year, fees, sections, yearClasses, refs, current, onCancel, onSaved}: {token: string; year: AcademicYear; fees: FeeType[]; sections: SchoolSection[];
  yearClasses: SchoolClass[]; refs: ReferenceCatalog | null; current: AnticipationPlan | null; onCancel: () => void; onSaved: () => Promise<void>}) {
  const monthly = fees.filter(f => f.periodicity === 'MONTHLY' && f.enabled);
  const [name, setName] = useState(current?.name ?? ''); const [fee, setFee] = useState(current?.fee_type_id ?? monthly[0]?.id ?? '');
  const [scope, setScope] = useState<AnticipationPlan['scope_type']>(current?.scope_type ?? 'SCHOOL');
  const [picked, setPicked] = useState<string[]>(current && current.scope_type !== 'SCHOOL' ? (current.scope_refs?.length ? current.scope_refs : [current.scope_ref]) : []);
  const [targets, setTargets] = useState<string[]>(current?.target_months ?? []); const [contribs, setContribs] = useState<string[]>(current?.contribution_months ?? []);
  const [mode, setMode] = useState<'OPTIONAL' | 'MANDATORY'>(current?.participation_mode ?? 'OPTIONAL'); const [effective, setEffective] = useState(current?.effective_from ?? year.start_date);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const locked = (current?.memberships ?? 0) > 0;
  const academic = [...new Map(yearClasses.filter(c => c.reference_code).map(c => [c.reference_code!.toUpperCase(),
    refs?.classes.find(r => r.code.toUpperCase() === c.reference_code!.toUpperCase())?.label ?? c.reference_code!])).entries()];
  const choices: [string, string][] = scope === 'SECTION' ? sections.filter(s => s.enabled).map(s => [s.id, s.label])
    : scope === 'CLASS' ? yearClasses.map(c => [c.id, `${c.section_label ?? ''} · ${c.label}`]) : scope === 'ACADEMIC_CLASS' ? academic : scope === 'OPTION_GROUP' ? TARIFF_GROUPS : [];
  const order = (xs: string[]) => SCHOOL_MONTHS.map(([m]) => m).filter(m => xs.includes(m));
  const flip = (xs: string[], set: (v: string[]) => void, m: string) => set(order(xs.includes(m) ? xs.filter(x => x !== m) : [...xs, m]));
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (name.trim().length < 2) { setError('Donnez un nom au plan (2 caractères au moins).'); return; }
    if (!fee) { setError('Choisissez le frais mensuel concerné.'); return; }
    if (scope !== 'SCHOOL' && !picked.length) { setError('Cochez au moins une cible du plan.'); return; }
    if (!targets.length || !contribs.length) { setError('Sélectionnez au moins un mois cible et un mois de contribution.'); return; }
    if (targets.some(m => contribs.includes(m))) { setError('Un mois cible ne peut pas être aussi un mois de contribution.'); return; }
    try {
      setBusy(true); setError('');
      await putAnticipationPlan(token, {academic_year_id: year.id, plan_id: current?.id ?? null, name: name.trim(), fee_type_id: fee, target_months: targets, contribution_months: contribs,
        participation_mode: mode, scope_type: scope, scope_ref: scope === 'SCHOOL' ? null : picked[0], scope_refs: scope === 'SCHOOL' ? null : picked,
        effective_from: effective, active: current?.active ?? true});
      toast.success(current ? 'Plan enregistré' : 'Plan créé'); await onSaved();
    } catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  return <form className="benefitCard planForm" onSubmit={submit} noValidate>
    {error && <div className="error" role="alert">{error}</div>}
    {locked && <p className="policyHint">Ce plan a déjà des adhésions : seuls le nom, le mode de participation et la date d’effet sont modifiables. Pour changer sa structure, désactivez-le et créez une nouvelle version.</p>}
    <fieldset disabled={busy}>
      <legend>{current ? 'Modifier le plan' : 'Nouveau plan'}</legend>
      <div className="benefitGrid">
        <FormField label="Nom du plan *"><input value={name} maxLength={160} onChange={e => setName(e.target.value)}/></FormField>
        <FormField label="Frais mensuel *" hint={monthly.length ? undefined : 'Aucun frais mensuel actif : créez-le dans Types de frais.'}><select value={fee} disabled={locked} onChange={e => setFee(e.target.value)}>
          {monthly.map(f => <option key={f.id} value={f.id}>{f.label}</option>)}</select></FormField>
        <FormField label="Portée *"><select value={scope} disabled={locked} onChange={e => { setScope(e.target.value as AnticipationPlan['scope_type']); setPicked([]); }}>{SCOPES.map(([s, l]) => <option key={s} value={s}>{l}</option>)}</select></FormField>
        <FormField label="Participation"><select value={mode} onChange={e => setMode(e.target.value as 'OPTIONAL' | 'MANDATORY')}>
          <option value="OPTIONAL">Facultative : le parent choisit</option><option value="MANDATORY">Obligatoire : adhésion au premier paiement selon le plan</option></select></FormField>
        <FormField label="Date d’effet"><DateInput value={effective} min={year.start_date} max={year.end_date} onChange={e => setEffective(e.target.value)}/></FormField>
      </div>
    </fieldset>
    {scope !== 'SCHOOL' && <fieldset disabled={busy || locked} className="planTargets"><legend>Cibles du plan <small>({picked.length} choisie{picked.length > 1 ? 's' : ''} sur {choices.length})</small></legend>
      <div className="planTargetTools"><button type="button" className="linkBtn" onClick={() => setPicked(choices.map(([v]) => v))}>Tout cocher</button><button type="button" className="linkBtn" onClick={() => setPicked([])}>Tout décocher</button></div>
      {choices.length ? <div className="sw-chips">{choices.map(([v, l]) => { const on = picked.includes(v); return <button key={v} type="button" className={`sw-chip ${on ? 'on' : ''}`} aria-pressed={on}
        onClick={() => setPicked(p => on ? p.filter(x => x !== v) : [...p, v])}>{on ? '✓ ' : '+ '}{l}</button>; })}</div>
        : <p className="policyHint">Aucune cible disponible pour cette portée : ouvrez d’abord les classes de l’année.</p>}
      <p className="policyHint">{scope === 'CLASS' ? 'Exemple : seulement 1re primaire A et 2e primaire A.' : 'Le plan s’applique aux élèves de chaque cible cochée.'} Les autres élèves paient normalement, sans plan.</p>
    </fieldset>}
    <fieldset disabled={busy || locked}><legend>Mois cibles (payés à l’avance)</legend>
      <div className="monthGrid">{SCHOOL_MONTHS.map(([m, l]) => <label key={m} className="checkField"><input type="checkbox" checked={targets.includes(m)} disabled={contribs.includes(m)} onChange={() => flip(targets, setTargets, m)}/> {l}</label>)}</div>
    </fieldset>
    <fieldset disabled={busy || locked}><legend>Mois de contribution (le parent verse en plus)</legend>
      <div className="monthGrid">{SCHOOL_MONTHS.map(([m, l]) => <label key={m} className="checkField"><input type="checkbox" checked={contribs.includes(m)} disabled={targets.includes(m)} onChange={() => flip(contribs, setContribs, m)}/> {l}</label>)}</div>
    </fieldset>
    <p className="policyHint">Répartition égale au centime : le montant restant des mois cibles est figé à l’adhésion puis réparti sur les mois de contribution. Un paiement selon le plan règle d’abord le mois courant, puis uniquement les mois cibles.</p>
    <div className="formActions"><button type="button" className="ghost" onClick={onCancel}>Annuler</button><button className="primaryBtn" disabled={busy}>{busy ? 'Enregistrement…' : 'Enregistrer le plan'}</button></div>
  </form>;
}
