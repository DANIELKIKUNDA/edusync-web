// Types de frais as cards (owner request 2026-11-08): one card per fee, grouped by how it is paid (monthly, by
// instalments, once, optional); adding and editing open in a window. Same APIs and permissions as before: a disabled
// fee keeps its history and its existing charges, it is only no longer proposed for new tariffs.
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {createFeeType, updateFeeType, type FeeType, type ReferenceCatalog} from './api';
import {friendlyError} from './platform/errors';
import {PERIODICITY_LABEL} from './platform/format';
import {NavGlyph} from './platform/nav_icons';
import {autoCode, FEE_PRESETS} from './settings_wizards';
import './settings_fees.css';

type Periodicity = FeeType['periodicity'];
const PERIODS: [Periodicity, string, string, string][] = [
  ['MONTHLY', 'Mensuels', 'Payés chaque mois facturé (frais scolaires…)', 'calendar'],
  ['PERIODIC', 'Par tranches', 'Payés en tranches ou par trimestre (frais de l’État…)', 'layers'],
  ['ONE_TIME', 'Paiement unique', 'Payés une seule fois dans l’année (inscription, uniformes, bulletin…)', 'receipt'],
  ['OPTIONAL', 'Facultatifs', 'Proposés, jamais imposés (journal de classe…)', 'tag'],
];
const CURRENCY: Record<string, string> = {CDF: 'Francs congolais (FC)', USD: 'Dollars (USD)'};

export function Fees({token, fees, refs, can, onDone}: {token: string; fees: FeeType[]; refs: ReferenceCatalog | null; can: (x: string) => boolean; onDone: () => Promise<void>}) {
  const [error, setError] = useState(''); const [adding, setAdding] = useState(false); const [editing, setEditing] = useState<FeeType | null>(null); const [busy, setBusy] = useState('');
  const manage = can('settings.fee_types.manage');
  const active = fees.filter(f => f.enabled); const disabled = fees.filter(f => !f.enabled);
  async function toggle(f: FeeType) {
    try { setBusy(f.id); setError('');
      await updateFeeType(token, f, {label: f.label, periodicity: f.periodicity, default_currency: f.default_currency, regulatory: f.regulatory, enabled: !f.enabled});
      toast.success(f.enabled ? `${f.label} désactivé (historique et frais existants conservés)` : `${f.label} réactivé`); await onDone();
    } catch (e) { setError(friendlyError(e)); } finally { setBusy(''); }
  }
  const card = (f: FeeType) => { const canToggle = f.enabled ? can('settings.fee_types.activate') : manage;
    return <article key={f.id} className={`fe-card ${f.enabled ? '' : 'off'}`}>
      <div className="fe-top"><span className={`fe-icon p-${f.periodicity}`} aria-hidden="true"><NavGlyph g={(PERIODS.find(p => p[0] === f.periodicity)?.[3] ?? 'receipt') as any} size={18}/></span>
        <div><b>{f.label}</b><small>{PERIODICITY_LABEL[f.periodicity] ?? f.periodicity}</small></div></div>
      <div className="fe-tags"><span>{f.default_currency === 'USD' ? 'USD' : 'FC'}</span>{f.regulatory && <span className="reg">Réglementaire</span>}<span className={f.enabled ? 'ok' : 'muted'}>{f.enabled ? 'Actif' : 'Désactivé'}</span></div>
      {(manage || canToggle) && <div className="fe-actions">{manage && f.enabled && <button type="button" className="fe-btn" onClick={() => setEditing(f)}>Modifier</button>}
        {canToggle && <button type="button" className={`fe-btn ${f.enabled ? 'danger' : ''}`} disabled={busy === f.id} onClick={() => void toggle(f)}>{f.enabled ? 'Désactiver' : 'Réactiver'}</button>}</div>}
    </article>; };
  return <section className="panel fe-page">
    <div className="panelHead"><div><h3>Types de frais <small>· {active.length} actif{active.length > 1 ? 's' : ''}</small></h3>
      <p>Ce que l’école peut faire payer. Le montant de chaque frais se règle ensuite dans Tarifs &amp; barèmes ; aucun frais n’est dû tant qu’il n’a pas de tarif.</p></div>
      {manage && <button type="button" className="primaryBtn fe-addBtn" onClick={() => setAdding(true)}><NavGlyph g="plus" size={16}/> Ajouter un type de frais</button>}</div>
    {error && <div className="error" role="alert">{error}</div>}
    {fees.length === 0 && <div className="emptyGuide"><b>Aucun type de frais</b><p>Ajoutez les frais de l’école : un modèle courant (frais scolaires mensuels, inscription…) ou un frais propre à l’école (uniformes, laboratoire…).</p></div>}
    {PERIODS.map(([p, title, hint]) => { const list = active.filter(f => f.periodicity === p); if (!list.length) return null;
      return <div key={p} className="fe-group"><div className="fe-groupHead"><b>{title}</b><small>{hint}</small><em>{list.length}</em></div><div className="fe-grid">{list.map(card)}</div></div>; })}
    {disabled.length > 0 && <div className="fe-group"><div className="fe-groupHead"><b>Désactivés</b><small>Gardés pour l’historique ; plus proposés pour de nouveaux tarifs.</small><em>{disabled.length}</em></div><div className="fe-grid">{disabled.map(card)}</div></div>}
    {adding && <AddFeeDialog token={token} fees={fees} refs={refs} onClose={() => setAdding(false)} onDone={onDone}/>}
    {editing && <EditFeeDialog token={token} fee={editing} fees={fees} onClose={() => setEditing(null)} onDone={async () => { setEditing(null); await onDone(); }}/>}
  </section>;
}

function Dialog({title, eyebrow, onClose, children}: {title: string; eyebrow: string; onClose: () => void; children: React.ReactNode}) {
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); }; window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k); }, [onClose]);
  return <div className="ac-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
    <div className="ac-dialog fe-dialog" role="dialog" aria-modal="true" aria-label={title}>
      <header><div><span className="eyebrow">{eyebrow}</span><h3>{title}</h3></div><button type="button" className="ac-close" aria-label="Fermer" onClick={onClose}><NavGlyph g="close" size={18}/></button></header>
      {children}</div></div>;
}

function PeriodChoice({value, onChange}: {value: Periodicity; onChange: (p: Periodicity) => void}) {
  return <div className="fe-period" role="radiogroup" aria-label="Mode de paiement">{PERIODS.map(([p, title, hint]) =>
    <button key={p} type="button" role="radio" aria-checked={value === p} className={value === p ? 'on' : ''} onClick={() => onChange(p)}><b>{title}</b><small>{hint}</small></button>)}</div>;
}

function CurrencyChoice({value, onChange}: {value: 'CDF' | 'USD'; onChange: (c: 'CDF' | 'USD') => void}) {
  return <div className="fe-seg" role="radiogroup" aria-label="Devise">{(['CDF', 'USD'] as const).map(c =>
    <button key={c} type="button" role="radio" aria-checked={value === c} className={value === c ? 'on' : ''} onClick={() => onChange(c)}>{CURRENCY[c]}</button>)}</div>;
}

function AddFeeDialog({token, fees, refs, onClose, onDone}: {token: string; fees: FeeType[]; refs: ReferenceCatalog | null; onClose: () => void; onDone: () => Promise<void>}) {
  const existing = new Set(fees.map(f => f.code)); const labels = new Set(fees.map(f => f.label.toLowerCase()));
  const presets = [...FEE_PRESETS, ...(refs?.fee_types ?? []).filter(r => !FEE_PRESETS.some(p => p.code === r.code)).map(r => ({code: r.code, label: r.label, periodicity: r.periodicity as Periodicity, regulatory: false, hint: ''}))];
  const [label, setLabel] = useState(''); const [periodicity, setPeriodicity] = useState<Periodicity>('ONE_TIME'); const [currency, setCurrency] = useState<'CDF' | 'USD'>('CDF');
  const [busy, setBusy] = useState(''); const [error, setError] = useState('');
  async function add(code: string, name: string, p: Periodicity, cur: 'CDF' | 'USD', regulatory = false) {
    try { setBusy(code); setError(''); await createFeeType(token, {code, label: name, periodicity: p, default_currency: cur, regulatory}); toast.success(`${name} ajouté`); await onDone(); return true; }
    catch (e) { setError(friendlyError(e)); return false; } finally { setBusy(''); }
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault(); const name = label.trim();
    if (name.length < 2) { setError('Indiquez le nom du frais, par exemple « Tenue scolaire (uniforme + pull) ».'); return; }
    if (labels.has(name.toLowerCase())) { setError('Un type de frais porte déjà ce nom.'); return; }
    if (await add(autoCode(name, existing), name, periodicity, currency)) onClose();
  }
  return <Dialog title="Ajouter un type de frais" eyebrow="Types de frais" onClose={onClose}>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="fe-section"><b>Modèles courants</b><small>Un clic ajoute le frais ; le montant se règle ensuite dans Tarifs &amp; barèmes.</small>
      <div className="fe-presets">{presets.map(f => { const have = existing.has(f.code);
        return <button key={f.code} type="button" className={`fe-preset ${have ? 'on' : ''}`} disabled={have || !!busy} title={f.hint} onClick={() => void add(f.code, f.label, f.periodicity, 'CDF', !!f.regulatory)}>
          {have ? <NavGlyph g="check" size={14}/> : <NavGlyph g="plus" size={14}/>}<span>{f.label}</span><small>{PERIODICITY_LABEL[f.periodicity] ?? f.periodicity}</small></button>; })}</div></div>
    <form className="fe-section fe-form" onSubmit={submit} noValidate><b>Frais propre à l’école</b><small>Par exemple : uniformes et pulls, frais de laboratoire, transport.</small>
      <label className="fe-field"><span>Nom du frais *</span><input value={label} maxLength={140} placeholder="Tenue scolaire (uniforme + pull)" onChange={e => setLabel(e.target.value)}/></label>
      <div className="fe-field"><span>Mode de paiement</span><PeriodChoice value={periodicity} onChange={setPeriodicity}/></div>
      <div className="fe-field"><span>Devise</span><CurrencyChoice value={currency} onChange={setCurrency}/></div>
      <div className="fe-foot"><button type="button" className="fe-btn" onClick={onClose}>Fermer</button><button className="primaryBtn" disabled={!!busy}>{busy ? 'Création…' : 'Créer le frais'}</button></div>
    </form>
  </Dialog>;
}

function EditFeeDialog({token, fee, fees, onClose, onDone}: {token: string; fee: FeeType; fees: FeeType[]; onClose: () => void; onDone: () => Promise<void>}) {
  const labels = new Set(fees.filter(f => f.id !== fee.id).map(f => f.label.toLowerCase()));
  const [d, setD] = useState({label: fee.label, periodicity: fee.periodicity, currency: fee.default_currency as 'CDF' | 'USD', regulatory: fee.regulatory});
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function submit(e: React.FormEvent) {
    e.preventDefault(); const label = d.label.trim();
    if (label.length < 2) { setError('Le nom du frais doit compter au moins deux caractères.'); return; }
    if (labels.has(label.toLowerCase())) { setError('Un autre type de frais porte déjà ce nom.'); return; }
    try { setBusy(true); setError(''); await updateFeeType(token, fee, {label, periodicity: d.periodicity, default_currency: d.currency, regulatory: d.regulatory, enabled: fee.enabled}); toast.success(`${label} modifié`); await onDone(); }
    catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  return <Dialog title={fee.label} eyebrow="Modifier le type de frais" onClose={onClose}>
    {error && <div className="error" role="alert">{error}</div>}
    <form className="fe-section fe-form" onSubmit={submit} noValidate>
      <label className="fe-field"><span>Nom du frais *</span><input value={d.label} maxLength={140} onChange={e => setD(x => ({...x, label: e.target.value}))}/></label>
      <div className="fe-field"><span>Mode de paiement</span><PeriodChoice value={d.periodicity} onChange={p => setD(x => ({...x, periodicity: p}))}/></div>
      {d.periodicity !== fee.periodicity && <p className="fe-warn"><NavGlyph g="info" size={15}/> Les échéances déjà créées ne changent pas : réappliquez les barèmes pour les classes concernées.</p>}
      <div className="fe-field"><span>Devise</span><CurrencyChoice value={d.currency} onChange={c => setD(x => ({...x, currency: c}))}/></div>
      <label className="fe-check"><input type="checkbox" checked={d.regulatory} onChange={e => setD(x => ({...x, regulatory: e.target.checked}))}/><span><b>Frais réglementaire</b><small>Fixé par l’État (frais de l’État, examen d’État, TENASOSP…).</small></span></label>
      <div className="fe-foot"><button type="button" className="fe-btn" onClick={onClose}>Annuler</button><button className="primaryBtn" disabled={busy}>{busy ? 'Enregistrement…' : 'Enregistrer'}</button></div>
    </form>
  </Dialog>;
}
