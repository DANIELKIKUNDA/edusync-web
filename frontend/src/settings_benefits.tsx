// Avantages & cas particuliers — copied from the Desktop golden master (app/ui/settings_page.py::_build_benefits,
// app/db/configuration.py::save_benefit_policy). One policy per school year; eligibility is automatic when possible but
// the beneficiary is always chosen manually by the school. Free beneficiaries = 100 %, otherwise the discount percent.
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {AcademicYear, FeeType, getBenefitPolicies, putBenefitPolicy, type BenefitPolicy} from './api';
import {friendlyError} from './platform/errors';
import {FormField} from './platform/forms';

type Draft = {enabled: boolean; min_children: string; max_beneficiaries: string; discount_percent: string; free_beneficiaries: string; applies_to_fee_code: string};
const DESKTOP_DEFAULTS: Record<'LARGE_FAMILY' | 'STAFF_CHILD', Draft> = {
  LARGE_FAMILY: {enabled: false, min_children: '5', max_beneficiaries: '0', discount_percent: '0', free_beneficiaries: '1', applies_to_fee_code: 'SCOLARITE'},
  STAFF_CHILD: {enabled: false, min_children: '0', max_beneficiaries: '2', discount_percent: '50', free_beneficiaries: '0', applies_to_fee_code: 'SCOLARITE'},
};

export function BenefitsSettings({token, years, fees, can}: {token: string; years: AcademicYear[]; fees: FeeType[]; can: (x: string) => boolean}) {
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
  </section>;
}

function PolicyCard({type, token, year, fees, editable, current, onSaved, onError}: {type: 'LARGE_FAMILY' | 'STAFF_CHILD'; token: string; year: AcademicYear; fees: FeeType[];
  editable: boolean; current: BenefitPolicy | null; onSaved: () => Promise<void>; onError: (m: string) => void}) {
  const initial: Draft = current ? {enabled: current.enabled, min_children: String(current.min_children), max_beneficiaries: String(current.max_beneficiaries),
    discount_percent: String(Number(current.discount_percent)), free_beneficiaries: String(current.free_beneficiaries), applies_to_fee_code: current.applies_to_fee_code ?? 'SCOLARITE'} : DESKTOP_DEFAULTS[type];
  const [d, setD] = useState<Draft>(initial); const [busy, setBusy] = useState(false);
  useEffect(() => setD(initial), [current?.version, current?.id]);
  const set = (k: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setD(x => ({...x, [k]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value}));
  const int = (v: string) => /^\d{1,2}$/.test(v.trim());
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (![d.min_children, d.max_beneficiaries, d.free_beneficiaries].every(int)) { onError('Les nombres doivent être des entiers de 0 à 50.'); return; }
    const pct = Number(d.discount_percent.replace(',', '.'));
    if (!(pct >= 0 && pct <= 100)) { onError('Le pourcentage doit être compris entre 0 et 100.'); return; }
    try {
      setBusy(true);
      await putBenefitPolicy(token, type, {academic_year_id: year.id, enabled: d.enabled, min_children: Number(d.min_children), max_beneficiaries: Number(d.max_beneficiaries),
        discount_percent: d.discount_percent.replace(',', '.'), free_beneficiaries: Number(d.free_beneficiaries), applies_to_fee_code: d.applies_to_fee_code || null, expected_version: current?.version ?? null});
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
        <FormField label="Frais concerné"><select value={d.applies_to_fee_code} onChange={set('applies_to_fee_code')}>
          {!fees.some(f => f.code === d.applies_to_fee_code) && <option value={d.applies_to_fee_code}>{d.applies_to_fee_code || '—'}</option>}
          {fees.map(f => <option key={f.id} value={f.code}>{f.label}</option>)}</select></FormField>
      </div>
      {editable && <div className="formActions"><button className="primaryBtn">{busy ? 'Enregistrement…' : 'Enregistrer'}</button></div>}
    </fieldset>
  </form>;
}
