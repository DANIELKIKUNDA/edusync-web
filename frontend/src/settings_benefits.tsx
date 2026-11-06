// Avantages (summary cards, form on demand — owner request 2026-11-06) — copied from the Desktop golden master (app/ui/settings_page.py::_build_benefits,
// app/db/configuration.py::save_benefit_policy). One policy per school year; eligibility is automatic when possible but
// the beneficiary is always chosen manually by the school. Free beneficiaries = 100 %, otherwise the discount percent.
// Settings parity 2026-10-24: a benefit covers SEVERAL fees (tuition, State fee…); individual exemptions for any other
// pupil are traceable financial decisions (Finance › Contrôles), reachable from here.
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {AcademicYear, FeeType, getBenefitPolicies, putBenefitPolicy, type BenefitPolicy} from './api';
import {friendlyError} from './platform/errors';
import {FormField} from './platform/forms';
import {NavGlyph} from './platform/nav_icons';

type Draft = {enabled: boolean; min_children: string; max_beneficiaries: string; discount_percent: string; free_beneficiaries: string; fee_codes: string[]; per_group: boolean};
const DESKTOP_DEFAULTS: Record<'LARGE_FAMILY' | 'STAFF_CHILD', Draft> = {
  LARGE_FAMILY: {enabled: false, min_children: '5', max_beneficiaries: '0', discount_percent: '0', free_beneficiaries: '1', fee_codes: ['SCOLARITE'], per_group: true},
  STAFF_CHILD: {enabled: false, min_children: '0', max_beneficiaries: '2', discount_percent: '50', free_beneficiaries: '0', fee_codes: ['SCOLARITE'], per_group: false},
};

const TITLE = {LARGE_FAMILY: 'Famille nombreuse', STAFF_CHILD: 'Enfants du personnel'} as const;
const PITCH = {LARGE_FAMILY: 'Réduction ou gratuité pour les familles qui inscrivent plusieurs enfants.', STAFF_CHILD: 'Réduction ou gratuité pour les enfants des agents de l’école.'} as const;

/** Fee codes proposed by default: the school's monthly tuition (never a code the school does not have). */
function defaultFeeCodes(fees: FeeType[]): string[] {
  const monthly = fees.find(f => f.code === 'MINERVAL' && f.enabled !== false) ?? fees.find(f => f.periodicity === 'MONTHLY' && f.enabled !== false);
  return monthly ? [monthly.code] : fees.some(f => f.code === 'SCOLARITE') ? ['SCOLARITE'] : [];
}

/** One sentence that says what the policy grants (shown on the summary card). */
export function benefitRule(type: 'LARGE_FAMILY' | 'STAFF_CHILD', p: {min_children: number; max_beneficiaries: number; discount_percent: string | number; free_beneficiaries: number; per_group?: boolean}): string {
  const pct = Number(p.discount_percent); const free = Number(p.free_beneficiaries);
  if (type === 'LARGE_FAMILY' && p.per_group) { const n = free || 1; return `${free > 0 ? `${n} enfant${n > 1 ? 's' : ''} gratuit${n > 1 ? 's' : ''}` : `${pct} % de réduction pour ${n} enfant${n > 1 ? 's' : ''}`} par tranche de ${p.min_children} enfants inscrits (${2 * p.min_children} enfants → ${2 * n})`; }
  if (type === 'LARGE_FAMILY') return free > 0 ? `${free} enfant${free > 1 ? 's' : ''} gratuit${free > 1 ? 's' : ''} par famille dès ${p.min_children} enfants inscrits` : `${pct} % de réduction dès ${p.min_children} enfants inscrits`;
  const cap = p.max_beneficiaries > 0 ? ` · ${p.max_beneficiaries} enfant${p.max_beneficiaries > 1 ? 's' : ''} max. par agent` : '';
  return free > 0 ? `${free} enfant${free > 1 ? 's' : ''} gratuit${free > 1 ? 's' : ''} par agent${cap}` : `${pct} % de réduction${cap}`;
}

export function BenefitsSettings({token, years, fees, can, onOpenFinance}: {token: string; years: AcademicYear[]; fees: FeeType[]; can: (x: string) => boolean; onOpenFinance?: () => void}) {
  const year = years.find(y => y.status === 'ACTIVE') ?? years.find(y => y.status === 'PREPARED');
  const [rows, setRows] = useState<BenefitPolicy[] | null>(null); const [error, setError] = useState(''); const [editing, setEditing] = useState<'LARGE_FAMILY' | 'STAFF_CHILD' | null>(null);
  async function load() { if (!year) { setRows([]); return; } try { setRows(await getBenefitPolicies(token, year.id)); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [token, year?.id]);
  const editable = can('settings.benefits.manage') && !!year;
  const feeLabel = (code: string) => feeOptions(fees, [code]).find(([c]) => c === code)?.[1] ?? code;
  return <section className="panel benefitsPage">
    <div className="panelHead"><div><h3>Avantages{year ? <small> · {year.label}</small> : null}</h3><p>L’école décide des règles ; au moment de l’inscription, la secrétaire choisit l’élève bénéficiaire. L’éligibilité est vérifiée automatiquement lorsque c’est possible.</p></div></div>
    {error && <div className="error" role="alert">{error}</div>}
    {!year && <div className="emptyGuide"><b>Aucune année préparée ou en cours</b><p>Les avantages se règlent pour une année scolaire.</p></div>}
    {year && rows && <div className="benefitTiles">{(['LARGE_FAMILY', 'STAFF_CHILD'] as const).map(type => {
      const current = rows.find(r => r.benefit_type === type) ?? null; const on = !!current?.enabled; const open = editing === type;
      const codes = current ? (current.applies_to_fee_codes?.length ? current.applies_to_fee_codes : current.applies_to_fee_code ? [current.applies_to_fee_code] : []) : [];
      return <article key={type} className={`benefitTile ${on ? 'on' : ''} ${open ? 'editing' : ''}`} aria-label={TITLE[type]}>
        <div className="benefitTileHead"><span className="benefitIcon" aria-hidden="true"><NavGlyph g={type === 'LARGE_FAMILY' ? 'users' : 'user'} size={20}/></span>
          <div><b>{TITLE[type]}</b><small>{PITCH[type]}</small></div>
          <em className={`pill ${on ? 'ok' : ''}`}>{on ? 'Actif' : current ? 'Inactif' : 'Non configuré'}</em></div>
        {!open && <ul className="benefitFacts">
          <li><span>Règle</span><b>{current ? benefitRule(type, current) : 'À définir'}</b></li>
          <li><span>Frais couverts</span><b>{codes.length ? codes.map(feeLabel).join(', ') : '—'}</b></li>
        </ul>}
        {open && <PolicyCard type={type} token={token} year={year} fees={fees} editable={editable} current={current} onError={setError}
          onSaved={async () => { await load(); setEditing(null); }} onCancel={() => setEditing(null)}/>}
        {!open && editable && <div className="benefitTileActions"><button type="button" className={current ? 'softBtn' : 'primaryBtn'} onClick={() => { setError(''); setEditing(type); }}>{current ? 'Modifier' : 'Configurer'}</button></div>}
      </article>; })}</div>}
    <div className="benefitNote"><span className="benefitIcon" aria-hidden="true"><NavGlyph g="doc" size={20}/></span>
      <div><b>Exonérations individuelles</b>
        <p>Pour un autre élève, une dispense d’un ou de plusieurs frais est une décision financière traçable (motif, date, auteur), appliquée sans modifier le tarif : Finance › Contrôles › Situation d’un élève › Nouvelle décision.</p></div>
      {onOpenFinance && <button type="button" className="softBtn" onClick={onOpenFinance}>Ouvrir Finance</button>}
    </div>
  </section>;
}

function PolicyCard({type, token, year, fees, editable, current, onSaved, onError, onCancel}: {type: 'LARGE_FAMILY' | 'STAFF_CHILD'; token: string; year: AcademicYear; fees: FeeType[];
  editable: boolean; current: BenefitPolicy | null; onSaved: () => Promise<void>; onError: (m: string) => void; onCancel: () => void}) {
  const initial: Draft = current ? {enabled: current.enabled, min_children: String(current.min_children), max_beneficiaries: String(current.max_beneficiaries),
    discount_percent: String(Number(current.discount_percent)), free_beneficiaries: String(current.free_beneficiaries),
    fee_codes: current.applies_to_fee_codes?.length ? current.applies_to_fee_codes : current.applies_to_fee_code ? [current.applies_to_fee_code] : [], per_group: !!current.per_group} : {...DESKTOP_DEFAULTS[type], fee_codes: defaultFeeCodes(fees)};
  const [d, setD] = useState<Draft>(initial); const [busy, setBusy] = useState(false);
  useEffect(() => setD(initial), [current?.version, current?.id]);
  const set = (k: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setD(x => ({...x, [k]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value}));
  const int = (v: string) => /^\d{1,2}$/.test(v.trim());
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (![d.min_children, d.max_beneficiaries, d.free_beneficiaries].every(int)) { onError('Les nombres doivent être des entiers de 0 à 50.'); return; }
    const pct = Number(d.discount_percent.replace(',', '.'));
    if (!(pct >= 0 && pct <= 100)) { onError('Le pourcentage doit être compris entre 0 et 100.'); return; }
    if (!d.fee_codes.length) { onError('Cochez au moins un frais couvert par l’avantage.'); return; }
    try {
      setBusy(true);
      await putBenefitPolicy(token, type, {academic_year_id: year.id, enabled: d.enabled, min_children: Number(d.min_children), max_beneficiaries: Number(d.max_beneficiaries),
        discount_percent: d.discount_percent.replace(',', '.'), free_beneficiaries: Number(d.free_beneficiaries), applies_to_fee_code: d.fee_codes[0] ?? null, applies_to_fee_codes: d.fee_codes, per_group: type === 'LARGE_FAMILY' && d.per_group, expected_version: current?.version ?? null});
      toast.success(type === 'LARGE_FAMILY' ? 'Politique Famille nombreuse enregistrée' : 'Politique Enfants du personnel enregistrée'); onError(''); await onSaved();
    } catch (err) { onError(friendlyError(err)); } finally { setBusy(false); }
  }
  const free = Number(d.free_beneficiaries) > 0;
  return <form className="benefitCard" onSubmit={save} noValidate>
    <fieldset disabled={!editable || busy}>
      <legend>{type === 'LARGE_FAMILY' ? 'Famille nombreuse' : 'Enfants du personnel'}</legend>
      <label className="switchRow"><span>Activer<small>{d.enabled ? `Actif pour ${year.label}` : 'Inactif : aucun bénéficiaire ne peut être choisi'}</small></span><input type="checkbox" role="switch" checked={d.enabled} onChange={set('enabled')}/></label>
      <div className="benefitGrid">
        {type === 'LARGE_FAMILY'
          ? <FormField label="Éligible à partir de (enfants inscrits)"><input inputMode="numeric" value={d.min_children} onChange={set('min_children')}/></FormField>
          : <FormField label="Nombre max. de bénéficiaires par agent"><input inputMode="numeric" value={d.max_beneficiaries} onChange={set('max_beneficiaries')}/></FormField>}
        <FormField label={type === 'LARGE_FAMILY' ? (d.per_group ? 'Bénéficiaires gratuits par tranche' : 'Bénéficiaires gratuits par famille') : 'Bénéficiaires gratuits'}><input inputMode="numeric" value={d.free_beneficiaries} onChange={set('free_beneficiaries')}/></FormField>
        <FormField label={type === 'LARGE_FAMILY' ? 'Réduction alternative (%)' : 'Réduction (%)'} hint={free ? 'Bénéficiaire gratuit : la réduction appliquée est de 100 %.' : undefined}><input inputMode="decimal" value={d.discount_percent} onChange={set('discount_percent')}/></FormField>
      </div>
      {type === 'LARGE_FAMILY' && <label className="switchRow"><span>Par tranche d’enfants<small>{d.per_group ? `${Number(d.free_beneficiaries) || 1} bénéficiaire(s) pour chaque groupe de ${d.min_children || '5'} enfants : ${Number(d.min_children) * 2 || 10} enfants inscrits → ${(Number(d.free_beneficiaries) || 1) * 2} bénéficiaires.` : `Limite fixe : ${Number(d.free_beneficiaries) || 1} bénéficiaire(s) par famille, quel que soit le nombre d’enfants.`}</small></span><input type="checkbox" role="switch" checked={d.per_group} onChange={set('per_group')}/></label>}
      <div className="feeChecks" role="group" aria-label="Frais couverts par l’avantage">
        <span>Frais couverts <small>({d.fee_codes.length} choisi{d.fee_codes.length > 1 ? 's' : ''})</small></span>
        <div className="feeCheckGrid">
          {feeOptions(fees, d.fee_codes).map(([code, label]) => <label key={code} className="checkField"><input type="checkbox" checked={d.fee_codes.includes(code)}
            onChange={e => setD(x => ({...x, fee_codes: e.target.checked ? [...x.fee_codes, code] : x.fee_codes.filter(c => c !== code)}))}/> {label}</label>)}
        </div>
        {!fees.length && <small className="policyHint">Créez d’abord les types de frais pour pouvoir les cocher.</small>}
      </div>
      {editable && <div className="formActions"><button type="button" className="ghost" onClick={onCancel}>Annuler</button><button className="primaryBtn">{busy ? 'Enregistrement…' : 'Enregistrer'}</button></div>}
    </fieldset>
  </form>;
}

/** Fee types of the school, plus a code already saved on the policy that is no longer in the list (kept visible). */
export function feeOptions(fees: FeeType[], chosen: string[]): [string, string][] {
  const list: [string, string][] = fees.filter(f => f.enabled !== false || chosen.includes(f.code)).map(f => [f.code, f.label]);
  for (const c of chosen) if (!list.some(([code]) => code === c)) list.push([c, c === 'SCOLARITE' ? 'Frais scolaires (SCOLARITE)' : c]);
  return list;
}
