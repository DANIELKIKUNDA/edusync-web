// Tariff assistant (settings parity pass 2, 2026-10-24) — the Desktop golden master offers « Assistant de création du
// tarif » (app/ui/settings_page.py::_open_tariff_dialog, live advisor preview), « Configurer les frais réglementaires »
// (app/db/configuration.py::configure_regulatory_fee_bundle) and a tariff step in the configuration wizard. The Web keeps
// the same rules and APIs (one dated rule per fee × target, the most precise rule applies) and adds:
//  * a grid that fixes a fee for the whole school, each section, each level and each Humanités group in one screen;
//  * one rule for SEVERAL targets at once (e.g. the same amount for 7e and 8e EB);
//  * a preview of the amount every open class will really pay, before anything is saved.
// Saving never rewrites a paid instalment: applying the tariffs to the classes stays a distinct, explicit step.
import React, {useEffect, useMemo, useState} from 'react';
import {createPortal} from 'react-dom';
import {toast} from 'sonner';
import {
  AcademicYear, FeeType, ReferenceCatalog, SchoolClass, SchoolOption, SchoolSection, Tariff, TariffScope, TariffStatus,
  createFeeType, listOptions, putTariffRule,
} from './api';
import {friendlyError} from './platform/errors';
import {formatMoney} from './platform/format';
import {Button} from './platform/ui';
import './settings_wizards.css';

export const SCOPE_PRIORITY: Record<TariffScope, number> = {CLASS: 600, ACADEMIC_CLASS: 500, OPTION_GROUP: 350, SECTION: 200, SCHOOL: 100};
const SCOPE_LABEL: Record<TariffScope, string> = {SCHOOL: 'Toute l’école', SECTION: 'Section', ACADEMIC_CLASS: 'Niveau', OPTION_GROUP: 'Groupe d’Humanités', CLASS: 'Classe ouverte'};
const GROUP_LABEL: Record<string, string> = {GENERAL: 'Humanités générales', TECHNICAL: 'Humanités techniques', OTHER: 'Autre groupe d’Humanités'};
const REGULATORY_SOURCE = 'Barème réglementaire validé par l’école';

/** A rule as the assistant plans it (amount null = pending official scale). */
export type PlannedRule = {scope_type: TariffScope; scope_ref: string; label: string; amount: string | null; currency: 'CDF' | 'USD'; status: TariffStatus};
type Target = {scope_type: TariffScope; scope_ref: string; label: string; hint?: string};

const amountOk = (v: string) => /^\d+([.,]\d{1,2})?$/.test(v.trim());
const norm = (v: string) => v.trim().replace(/\s/g, '').replace(',', '.');

/** Every target a rule can aim at for this year: school, sections, open levels, Humanités groups in use, open classes. */
export function tariffTargets({year, classes, sections, refs, options}: {year: AcademicYear; classes: SchoolClass[]; sections: SchoolSection[]; refs: ReferenceCatalog | null; options: SchoolOption[]}): Record<TariffScope, Target[]> {
  const open = classes.filter(c => c.academic_year_id === year.id && (c.status ?? (c.enabled ? 'ACTIVE' : 'INACTIVE')) !== 'ARCHIVED');
  const levelCodes = [...new Set(open.map(c => (c.reference_code ?? '').toUpperCase()).filter(Boolean))];
  const order = (code: string) => refs?.classes.find(r => r.code.toUpperCase() === code)?.sort_order ?? 999;
  const groups = [...new Set(open.map(c => options.find(o => o.id === c.option_id)?.tariff_group_code).filter((g): g is string => !!g))].sort();
  return {
    SCHOOL: [{scope_type: 'SCHOOL', scope_ref: '*', label: 'Toute l’école', hint: 'Montant de base, remplacé par toute règle plus précise'}],
    SECTION: sections.filter(s => s.enabled).map(s => ({scope_type: 'SECTION' as const, scope_ref: s.id, label: s.label})),
    ACADEMIC_CLASS: levelCodes.sort((a, b) => order(a) - order(b)).map(code => ({scope_type: 'ACADEMIC_CLASS' as const, scope_ref: code,
      label: refs?.classes.find(r => r.code.toUpperCase() === code)?.label ?? code, hint: `${open.filter(c => (c.reference_code ?? '').toUpperCase() === code).length} classe(s)`})),
    OPTION_GROUP: groups.map(g => ({scope_type: 'OPTION_GROUP' as const, scope_ref: g, label: GROUP_LABEL[g] ?? g, hint: 'Classes des Humanités dont l’option appartient à ce groupe'})),
    CLASS: open.map(c => ({scope_type: 'CLASS' as const, scope_ref: c.id, label: c.label, hint: c.section_label})),
  };
}

/** What every open class will pay for one fee once the planned rules are saved (Web resolve_tariff, end of the year). */
export function previewTariffs({year, classes, options, existing, planned}: {year: AcademicYear; classes: SchoolClass[]; options: SchoolOption[]; existing: Tariff[]; planned: PlannedRule[]}) {
  const open = classes.filter(c => c.academic_year_id === year.id && (c.status ?? (c.enabled ? 'ACTIVE' : 'INACTIVE')) !== 'ARCHIVED');
  const key = (s: string, r: string) => `${s}|${r.toUpperCase()}`;
  const rules = new Map<string, {amount: string | null; currency: string; status: TariffStatus; planned: boolean; label: string}>();
  for (const t of [...existing].filter(t => t.enabled !== false).sort((a, b) => a.effective_from.localeCompare(b.effective_from)))
    rules.set(key(t.scope_type, t.scope_ref), {amount: t.amount, currency: t.currency, status: t.status, planned: false, label: t.scope_label ?? SCOPE_LABEL[t.scope_type]});
  for (const p of planned) rules.set(key(p.scope_type, p.scope_ref), {amount: p.amount, currency: p.currency, status: p.status, planned: true, label: p.label});
  return open.map(c => {
    const group = options.find(o => o.id === c.option_id)?.tariff_group_code;
    const chain: [TariffScope, string | null | undefined][] = [['CLASS', c.id], ['ACADEMIC_CLASS', c.reference_code], ['OPTION_GROUP', group], ['SECTION', c.section_id], ['SCHOOL', '*']];
    for (const [scope, ref] of chain) {
      if (!ref) continue;
      const hit = rules.get(key(scope, ref));
      if (hit) return {cls: c, scope, ...hit};
    }
    return {cls: c, scope: null, amount: null, currency: 'CDF', status: 'ACTIVE' as TariffStatus, planned: false, label: ''};
  });
}

function Shell({title, subtitle, onClose, children, footer}: {title: string; subtitle: string; onClose: () => void; children: React.ReactNode; footer: React.ReactNode}) {
  // Capture + stop: opened above the setup assistant, Escape closes this dialog only, never both.
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } }; window.addEventListener('keydown', k, true); return () => window.removeEventListener('keydown', k, true); }, [onClose]);
  return createPortal(<div className="sw-backdrop" onClick={onClose}><div className="sw-dialog sw-wide" role="dialog" aria-modal="true" aria-label={title} onClick={e => e.stopPropagation()}>
    <header className="sw-head"><div><h3>{title}</h3><p>{subtitle}</p></div><button type="button" className="sw-close ta-close" aria-label="Fermer" onClick={onClose}>+</button></header>
    <div className="sw-body">{children}</div><footer className="sw-foot">{footer}</footer></div></div>, document.body);
}

type Props = {token: string; year: AcademicYear; fees: FeeType[]; classes: SchoolClass[]; sections: SchoolSection[]; refs: ReferenceCatalog | null;
  tariffs: Tariff[]; can: (p: string) => boolean; onClose: () => void; onDone: () => Promise<void>; initialMode?: Mode};
type Mode = 'grid' | 'rule' | 'regulatory';

export function TariffAssistant(props: Props) {
  const {token, year, onClose} = props;
  const [mode, setMode] = useState<Mode>(props.initialMode ?? 'grid');
  const [options, setOptions] = useState<SchoolOption[]>([]);
  useEffect(() => { listOptions(token).then(setOptions).catch(() => setOptions([])); }, [token]);
  const [busy, setBusy] = useState(false);
  const close = busy ? () => {} : onClose;
  const tabs: [Mode, string][] = [['grid', 'Grille par niveau'], ['rule', 'Règle guidée'], ['regulatory', 'Frais réglementaires']];
  return <Shell title={`Assistant tarifaire — ${year.label}`} subtitle="Les montants sont enregistrés comme règles datées. La règle la plus précise s’applique : classe › niveau › groupe d’Humanités › section › école." onClose={close}
    footer={<span className="sw-count">Les échéances des élèves ne changent qu’après « Appliquer les barèmes ».</span>}>
    <div className="sw-seg ta-tabs" role="tablist">{tabs.map(([m, l]) => <button key={m} type="button" role="tab" aria-selected={mode === m} className={mode === m ? 'on' : ''} disabled={busy} onClick={() => setMode(m)}>{l}</button>)}</div>
    {mode === 'grid' && <GridMode {...props} options={options} busy={busy} setBusy={setBusy}/>}
    {mode === 'rule' && <RuleMode {...props} options={options} busy={busy} setBusy={setBusy}/>}
    {mode === 'regulatory' && <RegulatoryMode {...props} options={options} busy={busy} setBusy={setBusy}/>}
  </Shell>;
}

type ModeProps = Props & {options: SchoolOption[]; busy: boolean; setBusy: (b: boolean) => void};

async function saveRules({token, year, feeId, rules, effective, source, onProgress}: {token: string; year: AcademicYear; feeId: string; rules: PlannedRule[]; effective: string; source: string; onProgress: (n: number) => void}) {
  let done = 0;
  for (const r of rules) {
    try {
      await putTariffRule(token, {academic_year_id: year.id, fee_type_id: feeId, scope_type: r.scope_type, scope_ref: r.scope_type === 'SCHOOL' ? null : r.scope_ref,
        amount: r.amount, currency: r.currency, status: r.status, effective_from: effective, source_reference: source.trim() || null});
    } catch (e) { throw new Error(`${r.label} : ${friendlyError(e)}${done ? ` (${done} règle(s) déjà enregistrée(s))` : ''}`); }
    done++; onProgress(done);
  }
  return done;
}

function CommonFields({currency, setCurrency, effective, setEffective, source, setSource, year}: {currency: 'CDF' | 'USD'; setCurrency: (c: 'CDF' | 'USD') => void;
  effective: string; setEffective: (d: string) => void; source: string; setSource: (s: string) => void; year: AcademicYear}) {
  return <div className="sw-grid">
    <label className="sw-input"><span>Devise</span><select value={currency} onChange={e => setCurrency(e.target.value as 'CDF' | 'USD')}><option>CDF</option><option>USD</option></select></label>
    <label className="sw-input"><span>Applicable dès</span><input type="date" min={year.start_date} max={year.end_date} value={effective} onChange={e => setEffective(e.target.value)}/></label>
    <label className="sw-input sw-wide-cell"><span>Référence officielle (facultatif)</span><input value={source} maxLength={240} placeholder="Ex. arrêté, circulaire, décision du comité de parents" onChange={e => setSource(e.target.value)}/></label>
  </div>;
}

function Preview({rows, currency}: {rows: ReturnType<typeof previewTariffs>; currency: string}) {
  const missing = rows.filter(r => r.amount === null && r.scope === null).length;
  const pending = rows.filter(r => r.scope !== null && (r.amount === null || r.status !== 'ACTIVE')).length;
  return <div className="sw-preview ta-preview"><b>Ce que chaque classe paiera <small>({rows.length} classe{rows.length > 1 ? 's' : ''} ouverte{rows.length > 1 ? 's' : ''})</small></b>
    {rows.length === 0 ? <p className="sw-hint">Aucune classe ouverte cette année : ouvrez d’abord les classes dans « Structure & classes ».</p> : <ul>
      {rows.map(r => <li key={r.cls.id} className={r.scope === null ? 'ta-missing' : r.planned ? 'ta-new' : ''}><span>{r.cls.label}</span>
        <span>{r.scope === null ? 'Aucun tarif' : r.amount === null || r.status !== 'ACTIVE' ? 'En attente du barème officiel' : formatMoney(r.amount, r.currency || currency)}
          {r.scope && <small> · {SCOPE_LABEL[r.scope]}{r.planned ? ' (nouveau)' : ''}</small>}</span></li>)}
    </ul>}
    {(missing > 0 || pending > 0) && <p className="sw-hint">{missing > 0 && `${missing} classe(s) sans tarif pour ce frais : aucun frais ne leur sera créé. `}{pending > 0 && `${pending} classe(s) en attente du barème officiel : leurs échéances seront créées dès que le montant sera fixé.`}</p>}
  </div>;
}

function FeeSelect({fees, fee, setFee}: {fees: FeeType[]; fee: string; setFee: (id: string) => void}) {
  return <label className="sw-input"><span>Frais *</span><select value={fee} onChange={e => setFee(e.target.value)}><option value="">Choisir le frais…</option>
    {fees.filter(f => f.enabled !== false).map(f => <option key={f.id} value={f.id}>{f.label}</option>)}</select></label>;
}

/** Desktop wizard tariff step, improved: one amount per row; an empty row creates nothing. */
function GridMode({token, year, fees, classes, sections, refs, tariffs, can, onDone, onClose, options, busy, setBusy}: ModeProps) {
  const [fee, setFee] = useState(fees.find(f => f.enabled !== false && f.periodicity === 'MONTHLY')?.id ?? '');
  const [currency, setCurrency] = useState<'CDF' | 'USD'>('CDF'); const [effective, setEffective] = useState(year.start_date); const [source, setSource] = useState('');
  const [amounts, setAmounts] = useState<Record<string, string>>({}); const [pendingRows, setPendingRows] = useState<string[]>([]);
  const [error, setError] = useState(''); const [done, setDone] = useState(0);
  useEffect(() => { const f = fees.find(x => x.id === fee); if (f) setCurrency(f.default_currency); setAmounts({}); setPendingRows([]); }, [fee]);
  const targets = useMemo(() => tariffTargets({year, classes, sections, refs, options}), [year, classes, sections, refs, options]);
  const groups: [string, Target[]][] = [['Base', targets.SCHOOL], ['Par section', targets.SECTION], ['Par niveau', targets.ACADEMIC_CLASS],
    ...(can('settings.tariff_groups.manage') && targets.OPTION_GROUP.length ? [['Humanités par groupe d’options', targets.OPTION_GROUP] as [string, Target[]]] : [])];
  const feeRules = tariffs.filter(t => t.academic_year_id === year.id && t.fee_type_id === fee && t.enabled !== false);
  const current = (t: Target) => feeRules.filter(r => r.scope_type === t.scope_type && r.scope_ref.toUpperCase() === t.scope_ref.toUpperCase()).sort((a, b) => b.effective_from.localeCompare(a.effective_from))[0];
  const k = (t: Target) => `${t.scope_type}|${t.scope_ref}`;
  const planned: PlannedRule[] = groups.flatMap(([, list]) => list).flatMap((t): PlannedRule[] => {
    const pend = pendingRows.includes(k(t)); const v = amounts[k(t)] ?? '';
    if (pend) return [{scope_type: t.scope_type, scope_ref: t.scope_ref, label: t.label, amount: amountOk(v) ? norm(v) : null, currency, status: 'PENDING_OFFICIAL' as const}];
    return v.trim() && amountOk(v) ? [{scope_type: t.scope_type, scope_ref: t.scope_ref, label: t.label, amount: norm(v), currency, status: 'ACTIVE' as const}] : [];
  });
  const invalid = Object.entries(amounts).filter(([, v]) => v.trim() && !amountOk(v));
  const rows = fee ? previewTariffs({year, classes, options, existing: feeRules, planned}) : [];
  async function save() {
    setError('');
    if (!fee) { setError('Choisissez d’abord le frais à tarifer.'); return; }
    if (invalid.length) { setError('Montant en chiffres, deux décimales au plus (ex. 15000 ou 12,50).'); return; }
    if (!planned.length) { setError('Saisissez au moins un montant (ou marquez une ligne « en attente du barème officiel »).'); return; }
    if (effective < year.start_date || effective > year.end_date) { setError(`La date d’effet doit être dans l’année ${year.label}.`); return; }
    try { setBusy(true); setDone(0); const n = await saveRules({token, year, feeId: fee, rules: planned, effective, source, onProgress: setDone}); toast.success(`${n} règle(s) tarifaire(s) enregistrée(s)`); await onDone(); onClose(); }
    catch (e) { setError(e instanceof Error ? e.message : friendlyError(e)); await onDone(); } finally { setBusy(false); }
  }
  return <>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="sw-grid"><FeeSelect fees={fees} fee={fee} setFee={setFee}/></div>
    {!fees.length && <p className="sw-hint">Aucun type de frais : créez-les d’abord dans « Types de frais ».</p>}
    {fee && <>
      <CommonFields {...{currency, setCurrency, effective, setEffective, source, setSource, year}}/>
      <div className="ta-grid">{groups.map(([title, list]) => list.length > 0 && <fieldset key={title} disabled={busy}><legend>{title}</legend>
        {list.map(t => { const cur = current(t); const pend = pendingRows.includes(k(t));
          return <div key={k(t)} className="ta-row"><div className="ta-row-name"><b>{t.label}</b>{(t.hint || cur) && <small>{cur ? `Actuel : ${cur.amount === null ? 'à fixer' : formatMoney(cur.amount, cur.currency)} dès le ${cur.effective_from}` : t.hint}</small>}</div>
            <input aria-label={`Montant — ${t.label}`} inputMode="decimal" autoComplete="off" placeholder={pend ? 'si connu' : '—'} value={amounts[k(t)] ?? ''} onChange={e => setAmounts(a => ({...a, [k(t)]: e.target.value}))}/>
            <label className="ta-pending" title="Le montant officiel n’est pas encore publié"><input type="checkbox" checked={pend} onChange={e => setPendingRows(p => e.target.checked ? [...p, k(t)] : p.filter(x => x !== k(t)))}/> En attente</label></div>; })}
      </fieldset>)}</div>
      <p className="sw-hint">Astuce : fixez le montant de toute l’école ou d’une section, puis seulement les niveaux qui diffèrent (par exemple la 6e primaire ou les finalistes). En Humanités, un montant par niveau l’emporte sur le groupe d’options : fixez « Humanités générales » et « techniques », puis « 4e Humanités » si son tarif est commun.</p>
      <Preview rows={rows} currency={currency}/>
      <div className="formActions"><span className="sw-count">{planned.length} règle(s) à enregistrer{busy ? ` · ${done}/${planned.length}` : ''}</span>
        <Button variant="secondary" onClick={onClose} disabled={busy}>Annuler</Button><Button variant="primary" disabled={busy || !planned.length} onClick={() => void save()}>{busy ? 'Enregistrement…' : 'Enregistrer la grille'}</Button></div>
    </>}
  </>;
}

/** Desktop « Assistant de création du tarif » with its live advisor, for one or SEVERAL targets of the same scope. */
function RuleMode({token, year, fees, classes, sections, refs, tariffs, can, onDone, onClose, options, busy, setBusy}: ModeProps) {
  const [fee, setFee] = useState(''); const [scope, setScope] = useState<TariffScope>('ACADEMIC_CLASS'); const [picked, setPicked] = useState<string[]>([]);
  const [amount, setAmount] = useState(''); const [status, setStatus] = useState<TariffStatus>('ACTIVE');
  const [currency, setCurrency] = useState<'CDF' | 'USD'>('CDF'); const [effective, setEffective] = useState(year.start_date); const [source, setSource] = useState('');
  const [error, setError] = useState(''); const [done, setDone] = useState(0);
  useEffect(() => { const f = fees.find(x => x.id === fee); if (f) setCurrency(f.default_currency); }, [fee]);
  const targets = useMemo(() => tariffTargets({year, classes, sections, refs, options}), [year, classes, sections, refs, options]);
  const scopes = (Object.keys(SCOPE_LABEL) as TariffScope[]).filter(s => s !== 'OPTION_GROUP' || can('settings.tariff_groups.manage'));
  const list = targets[scope];
  const chosen = scope === 'SCHOOL' ? list : list.filter(t => picked.includes(t.scope_ref));
  const planned: PlannedRule[] = chosen.map(t => ({scope_type: t.scope_type, scope_ref: t.scope_ref, label: t.label, amount: amountOk(amount) ? norm(amount) : null, currency, status}));
  const feeRules = tariffs.filter(t => t.academic_year_id === year.id && t.fee_type_id === fee && t.enabled !== false);
  const rows = fee ? previewTariffs({year, classes, options, existing: feeRules, planned}) : [];
  const affected = rows.filter(r => r.planned).length;
  const shadowed = fee && chosen.length ? previewTariffs({year, classes, options, existing: [], planned}).filter(r => r.planned).length - affected : 0;
  async function save() {
    setError('');
    if (!fee) { setError('Choisissez le frais.'); return; }
    if (!chosen.length) { setError('Cochez au moins une cible.'); return; }
    if (amount.trim() && !amountOk(amount)) { setError('Montant en chiffres, deux décimales au plus (ex. 15000 ou 12,50).'); return; }
    if (status === 'ACTIVE' && !amount.trim()) { setError('Un tarif actif doit avoir un montant. Sinon, choisissez « En attente du barème officiel ».'); return; }
    if (effective < year.start_date || effective > year.end_date) { setError(`La date d’effet doit être dans l’année ${year.label}.`); return; }
    try { setBusy(true); setDone(0); const n = await saveRules({token, year, feeId: fee, rules: planned, effective, source, onProgress: setDone}); toast.success(`${n} règle(s) tarifaire(s) enregistrée(s)`); await onDone(); onClose(); }
    catch (e) { setError(e instanceof Error ? e.message : friendlyError(e)); await onDone(); } finally { setBusy(false); }
  }
  return <>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="sw-grid"><FeeSelect fees={fees} fee={fee} setFee={setFee}/>
      <label className="sw-input"><span>Portée</span><select value={scope} onChange={e => { setScope(e.target.value as TariffScope); setPicked([]); }}>{scopes.map(s => <option key={s} value={s}>{SCOPE_LABEL[s]}</option>)}</select></label></div>
    {scope !== 'SCHOOL' && <div className="sw-field"><span>Cibles <small>(une règle par cible)</small></span>
      {list.length ? <div className="sw-chips">{list.map(t => { const on = picked.includes(t.scope_ref); return <button key={t.scope_ref} type="button" className={`sw-chip ${on ? 'on' : ''}`} aria-pressed={on} title={t.hint}
        onClick={() => setPicked(p => on ? p.filter(x => x !== t.scope_ref) : [...p, t.scope_ref])}>{t.label}</button>; })}</div>
        : <p className="sw-hint">Aucune cible disponible pour cette portée : ouvrez d’abord les classes de l’année.</p>}</div>}
    <div className="sw-grid">
      <label className="sw-input"><span>Statut</span><select value={status} onChange={e => setStatus(e.target.value as TariffStatus)}><option value="ACTIVE">Actif</option><option value="PENDING_OFFICIAL">En attente du barème officiel</option></select></label>
      <label className="sw-input"><span>{status === 'ACTIVE' ? 'Montant *' : 'Montant (si connu)'}</span><input inputMode="decimal" autoComplete="off" value={amount} placeholder="0" onChange={e => setAmount(e.target.value)}/></label>
    </div>
    <CommonFields {...{currency, setCurrency, effective, setEffective, source, setSource, year}}/>
    {fee && chosen.length > 0 && <p className="ta-advisor" role="status">{affected > 0 ? `Cette règle s’appliquera à ${affected} classe(s).` : 'Cette règle ne s’appliquera à aucune classe ouverte.'}
      {shadowed > 0 && ` ${shadowed} classe(s) gardent une règle plus précise déjà enregistrée.`}</p>}
    {fee && <Preview rows={rows} currency={currency}/>}
    <div className="formActions"><span className="sw-count">{planned.length} règle(s){busy ? ` · ${done}/${planned.length}` : ''}</span>
      <Button variant="secondary" onClick={onClose} disabled={busy}>Annuler</Button><Button variant="primary" disabled={busy || !planned.length || !fee} onClick={() => void save()}>{busy ? 'Enregistrement…' : 'Enregistrer'}</Button></div>
  </>;
}

/** Desktop configure_regulatory_fee_bundle: the school's agreed regulatory amounts, editable before saving. */
type RegLine = {key: string; fee: 'ETAT_MINERVAL' | 'ETAT_TENASOSP' | 'FRAIS_TECHNIQUES'; scope_type: TariffScope; ref: string; label: string; amount: string};
export const REGULATORY_FEES: Record<RegLine['fee'], {label: string; periodicity: FeeType['periodicity']; regulatory: boolean; hint: string}> = {
  ETAT_MINERVAL: {label: 'Frais de l’État', periodicity: 'PERIODIC', regulatory: true, hint: 'Par tranche (T1, T2, T3)'},
  ETAT_TENASOSP: {label: 'TENASOSP', periodicity: 'ONE_TIME', regulatory: true, hint: 'Une fois, 8e EB'},
  FRAIS_TECHNIQUES: {label: 'Frais techniques', periodicity: 'ONE_TIME', regulatory: false, hint: 'Une fois par an, options techniques'},
};
export const REGULATORY_LINES: Omit<RegLine, 'ref'>[] = [
  {key: 'etat-mat', fee: 'ETAT_MINERVAL', scope_type: 'SECTION', label: 'Maternelle', amount: '12000'},
  {key: 'etat-pri', fee: 'ETAT_MINERVAL', scope_type: 'SECTION', label: 'Primaire', amount: '12000'},
  {key: 'etat-s7', fee: 'ETAT_MINERVAL', scope_type: 'ACADEMIC_CLASS', label: '7e EB', amount: '21000'},
  {key: 'etat-s8', fee: 'ETAT_MINERVAL', scope_type: 'ACADEMIC_CLASS', label: '8e EB', amount: '21000'},
  {key: 'etat-gen', fee: 'ETAT_MINERVAL', scope_type: 'OPTION_GROUP', label: 'Humanités générales', amount: '23000'},
  {key: 'etat-tec', fee: 'ETAT_MINERVAL', scope_type: 'OPTION_GROUP', label: 'Humanités techniques', amount: '25000'},
  {key: 'tenasosp-s8', fee: 'ETAT_TENASOSP', scope_type: 'ACADEMIC_CLASS', label: '8e EB', amount: '60000'},
  {key: 'tech-tec', fee: 'FRAIS_TECHNIQUES', scope_type: 'OPTION_GROUP', label: 'Humanités techniques', amount: '25000'},
];
const REG_REF: Record<string, {section?: string; level?: string; group?: string}> = {
  'etat-mat': {section: 'MATERNELLE'}, 'etat-pri': {section: 'PRIMAIRE'}, 'etat-s7': {level: 'S7'}, 'etat-s8': {level: 'S8'},
  'etat-gen': {group: 'GENERAL'}, 'etat-tec': {group: 'TECHNICAL'}, 'tenasosp-s8': {level: 'S8'}, 'tech-tec': {group: 'TECHNICAL'},
};

function RegulatoryMode({token, year, fees, classes, sections, refs, can, onDone, onClose, options, busy, setBusy}: ModeProps) {
  const targets = useMemo(() => tariffTargets({year, classes, sections, refs, options}), [year, classes, sections, refs, options]);
  const lines: (RegLine & {available: boolean; why?: string})[] = REGULATORY_LINES.map(l => {
    const r = REG_REF[l.key];
    if (r.section) { const s = sections.find(x => x.code === r.section && x.enabled); return {...l, ref: s?.id ?? '', available: !!s, why: s ? undefined : `Section ${l.label} non organisée`}; }
    if (r.level) { const t = targets.ACADEMIC_CLASS.find(x => x.scope_ref === r.level); return {...l, ref: r.level, available: !!t, why: t ? undefined : `Aucune classe de ${l.label} ouverte`}; }
    const t = targets.OPTION_GROUP.find(x => x.scope_ref === r.group); const allowed = can('settings.tariff_groups.manage');
    return {...l, ref: r.group!, available: !!t && allowed, why: !allowed ? 'Droit « groupes d’Humanités » requis' : t ? undefined : `Aucune classe en ${l.label}`};
  });
  const [amounts, setAmounts] = useState<Record<string, string>>(() => Object.fromEntries(REGULATORY_LINES.map(l => [l.key, l.amount])));
  const [off, setOff] = useState<string[]>([]); const [effective, setEffective] = useState(year.start_date); const [source, setSource] = useState(REGULATORY_SOURCE);
  const [error, setError] = useState(''); const [progress, setProgress] = useState('');
  const chosen = lines.filter(l => l.available && !off.includes(l.key));
  const canCreateFees = can('settings.fee_types.manage');
  const missingFees = [...new Set(chosen.map(l => l.fee))].filter(code => !fees.some(f => f.code === code));
  async function save() {
    setError('');
    const bad = chosen.find(l => !amountOk(amounts[l.key] ?? ''));
    if (bad) { setError(`${REGULATORY_FEES[bad.fee].label} — ${bad.label} : montant en chiffres (ex. 12000).`); return; }
    if (missingFees.length && !canCreateFees) { setError('Les types de frais réglementaires manquent et votre rôle ne permet pas de les créer.'); return; }
    if (!chosen.length) { setError('Aucune ligne applicable à cette école.'); return; }
    try {
      setBusy(true);
      const byCode = new Map(fees.map(f => [f.code, f.id]));
      for (const code of missingFees) {
        setProgress(`Création du frais ${REGULATORY_FEES[code].label}…`);
        try { const f = await createFeeType(token, {code, label: REGULATORY_FEES[code].label, periodicity: REGULATORY_FEES[code].periodicity, default_currency: 'CDF', regulatory: REGULATORY_FEES[code].regulatory}); byCode.set(code, f.id); }
        catch (e) { throw new Error(`${REGULATORY_FEES[code].label} : ${friendlyError(e)}`); }
      }
      let n = 0;
      for (const l of chosen) {
        setProgress(`${n + 1}/${chosen.length} · ${REGULATORY_FEES[l.fee].label} — ${l.label}`);
        try {
          await putTariffRule(token, {academic_year_id: year.id, fee_type_id: byCode.get(l.fee)!, scope_type: l.scope_type, scope_ref: l.ref, amount: norm(amounts[l.key]),
            currency: 'CDF', status: 'ACTIVE', effective_from: effective, source_reference: source.trim() || null});
        } catch (e) { throw new Error(`${REGULATORY_FEES[l.fee].label} — ${l.label} : ${friendlyError(e)}${n ? ` (${n} règle(s) déjà enregistrée(s))` : ''}`); }
        n++;
      }
      toast.success(`Frais réglementaires configurés : ${n} règle(s). Appliquez ensuite les barèmes aux classes.`); await onDone(); onClose();
    } catch (e) { setError(e instanceof Error ? e.message : friendlyError(e)); await onDone(); } finally { setBusy(false); setProgress(''); }
  }
  return <>
    {error && <div className="error" role="alert">{error}</div>}
    <p className="sw-hint">Barème convenu repris du logiciel desktop. Vérifiez chaque montant avec le texte officiel de l’année : vous pouvez les modifier ou décocher une ligne avant d’enregistrer. Les frais manquants (Frais de l’État, TENASOSP, Frais techniques) sont créés automatiquement.</p>
    <div className="ta-grid">{(Object.keys(REGULATORY_FEES) as RegLine['fee'][]).map(code => <fieldset key={code} disabled={busy}>
      <legend>{REGULATORY_FEES[code].label} <small>{REGULATORY_FEES[code].hint}{!fees.some(f => f.code === code) ? ' · sera créé' : ''}</small></legend>
      {lines.filter(l => l.fee === code).map(l => <div key={l.key} className={`ta-row ${l.available ? '' : 'off'}`}>
        <label className="ta-row-name"><input type="checkbox" disabled={!l.available} checked={l.available && !off.includes(l.key)} onChange={e => setOff(o => e.target.checked ? o.filter(x => x !== l.key) : [...o, l.key])}/>
          <span><b>{l.label}</b><small>{l.available ? SCOPE_LABEL[l.scope_type] : l.why}</small></span></label>
        <input aria-label={`Montant — ${REGULATORY_FEES[code].label} ${l.label}`} inputMode="decimal" disabled={!l.available || off.includes(l.key)} value={amounts[l.key]} onChange={e => setAmounts(a => ({...a, [l.key]: e.target.value}))}/>
        <span className="ta-unit">CDF{code === 'ETAT_MINERVAL' ? ' / tranche' : ''}</span></div>)}
    </fieldset>)}</div>
    <div className="sw-grid">
      <label className="sw-input"><span>Applicable dès</span><input type="date" min={year.start_date} max={year.end_date} value={effective} onChange={e => setEffective(e.target.value)}/></label>
      <label className="sw-input"><span>Référence officielle</span><input value={source} maxLength={240} onChange={e => setSource(e.target.value)}/></label>
    </div>
    <div className="formActions"><span className="sw-count">{progress || `${chosen.length} règle(s) à enregistrer`}</span>
      <Button variant="secondary" onClick={onClose} disabled={busy}>Annuler</Button><Button variant="primary" disabled={busy || !chosen.length} onClick={() => void save()}>{busy ? 'Configuration…' : 'Configurer les frais réglementaires'}</Button></div>
  </>;
}
