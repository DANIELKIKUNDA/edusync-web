// Avantages & cas particuliers — copied from the Desktop golden master (app/ui/settings_page.py::_build_benefits,
// app/db/configuration.py::save_benefit_policy). One policy per school year; eligibility is automatic when possible but
// the beneficiary is always chosen manually by the school. Free beneficiaries = 100 %, otherwise the discount percent.
// Settings parity 2026-10-24: a benefit covers SEVERAL fees (tuition, State fee…); individual exemptions for any other
// pupil are traceable financial decisions (Finance › Contrôles), reachable from here.
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {AcademicYear, FeeType, getBenefitPolicies, putBenefitPolicy, type BenefitPolicy} from './api';
import {friendlyError} from './platform/errors';
import {FormField} from './platform/forms';

type Draft = {enabled: boolean; min_children: string; max_beneficiaries: string; discount_percent: string; free_beneficiaries: string; fee_codes: string[]};
const DESKTOP_DEFAULTS: Record<'LARGE_FAMILY' | 'STAFF_CHILD', Draft> = {
  LARGE_FAMILY: {enabled: false, min_children: '5', max_beneficiaries: '0', discount_percent: '0', free_beneficiaries: '1', fee_codes: ['SCOLARITE']},
  STAFF_CHILD: {enabled: false, min_children: '0', max_beneficiaries: '2', discount_percent: '50', free_beneficiaries: '0', fee_codes: ['SCOLARITE']},
};

export function BenefitsSettings({token, years, fees, can, onOpenFinance}: {token: string; years: AcademicYear[]; fees: FeeType[]; can: (x: string) => boolean; onOpenFinance?: () => void}) {
  const year = years.find(y => y.status === 'ACTIVE') ?? years.find(y => y.status === 'PREPARED');
  const [rows, setRows] = useState<BenefitPolicy[] | null>(null); const [error, setError] = useState('');
  async function load() { if (!year) { setRows([]); return; } try { setRows(await getBenefitPolicies(token, year.id)); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [token, year?.id]);
  const editable = can('settings.benefits.manage') && !!year;
  return <section className="panel">
    <div className="panelHead"><div><h3>Avantages &amp; cas particuliers</h3><p>L’éligibilité est automatique lorsque possible, mais le bénéficiaire reste toujours choisi manuellement par l’école, au moment de l’inscription.</p></div></div>
    {error && <div className="error" role="alert">{error}</div>}
    {!year && <div className="emptyGuide"><b>Aucune année préparée ou en cours</b><p>Les avantages se règlent pour une année scolaire.</p></div>}
    {year && rows && (['LARGE_FAMILY', 'STAFF_CHILD'] as const).map(type => <PolicyCard key={type} type={type} token={token} year={year} fees={fees} editable={editable}
      current={rows.find(r => r.benefit_type === type) ?? null} onSaved={load} onError={setError}/>)}
    <div className="benefitCard exemptionCard">
      <b>Exonérations individuelles</b>
      <p>Un élève qui n’est ni enfant du personnel ni pris en charge peut être dispensé d’un ou de plusieurs frais précis (frais de l’État, frais auxiliaire…). C’est une décision financière traçable — motif, date, auteur — appliquée sans jamais modifier le tarif : <b>Finance › Contrôles › Situation d’un élève › Nouvelle décision</b>, puis cochez les frais concernés.</p>
      {onOpenFinance && <div className="formActions"><button type="button" className="softBtn" onClick={onOpenFinance}>Ouvrir Finance</button></div>}
    </div>
  </section>;
}

function PolicyCard({type, token, year, fees, editable, current, onSaved, onError}: {type: 'LARGE_FAMILY' | 'STAFF_CHILD'; token: string; year: AcademicYear; fees: FeeType[];
  editable: boolean; current: BenefitPolicy | null; onSaved: () => Promise<void>; onError: (m: string) => void}) {
  const initial: Draft = current ? {enabled: current.enabled, min_children: String(current.min_children), max_beneficiaries: String(current.max_beneficiaries),
    discount_percent: String(Number(current.discount_percent)), free_beneficiaries: String(current.free_beneficiaries),
    fee_codes: current.applies_to_fee_codes?.length ? current.applies_to_fee_codes : current.applies_to_fee_code ? [current.applies_to_fee_code] : []} : DESKTOP_DEFAULTS[type];
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
        discount_percent: d.discount_percent.replace(',', '.'), free_beneficiaries: Number(d.free_beneficiaries), applies_to_fee_code: d.fee_codes[0] ?? null, applies_to_fee_codes: d.fee_codes, expected_version: current?.version ?? null});
      toast.success(type === 'LARGE_FAMILY' ? 'Politique Famille nombreuse enregistrée' : 'Politique Enfants du personnel enregistrée'); await onSaved();
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
        <FormField label={type === 'LARGE_FAMILY' ? 'Bénéficiaires gratuits par famille' : 'Bénéficiaires gratuits'}><input inputMode="numeric" value={d.free_beneficiaries} onChange={set('free_beneficiaries')}/></FormField>
        <FormField label={type === 'LARGE_FAMILY' ? 'Réduction alternative (%)' : 'Réduction (%)'} hint={free ? 'Bénéficiaire gratuit : la réduction appliquée est de 100 %.' : undefined}><input inputMode="decimal" value={d.discount_percent} onChange={set('discount_percent')}/></FormField>
      </div>
      <div className="feeChecks" role="group" aria-label="Frais couverts par l’avantage">
        <span>Frais couverts <small>({d.fee_codes.length} choisi{d.fee_codes.length > 1 ? 's' : ''})</small></span>
        <div className="feeCheckGrid">
          {feeOptions(fees, d.fee_codes).map(([code, label]) => <label key={code} className="checkField"><input type="checkbox" checked={d.fee_codes.includes(code)}
            onChange={e => setD(x => ({...x, fee_codes: e.target.checked ? [...x.fee_codes, code] : x.fee_codes.filter(c => c !== code)}))}/> {label}</label>)}
        </div>
        {!fees.length && <small className="policyHint">Créez d’abord les types de frais pour pouvoir les cocher.</small>}
      </div>
      {editable && <div className="formActions"><button className="primaryBtn">{busy ? 'Enregistrement…' : 'Enregistrer'}</button></div>}
    </fieldset>
  </form>;
}

/** Fee types of the school, plus a code already saved on the policy that is no longer in the list (kept visible). */
export function feeOptions(fees: FeeType[], chosen: string[]): [string, string][] {
  const list: [string, string][] = fees.filter(f => f.enabled !== false || chosen.includes(f.code)).map(f => [f.code, f.label]);
  for (const c of chosen) if (!list.some(([code]) => code === c)) list.push([c, c === 'SCOLARITE' ? 'Frais scolaires (SCOLARITE)' : c]);
  return list;
}
