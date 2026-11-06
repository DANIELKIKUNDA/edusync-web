// Tarifs & barèmes — copied from the Desktop golden master (app/ui/settings_page.py::_build_tariffs,
// app/db/configuration.py: upsert_tariff_rule, save_tariff_group_rule, save_monthly_billing_policy).
// A rule targets the school, a section, an academic class, an Humanities group or one class; it is dated and carries an
// official status. The most precise rule applies: class > academic class > Humanities group > section > school.
import React, {useEffect, useMemo, useState} from 'react';
import {toast} from 'sonner';
import {
  AcademicYear, BillingPolicy, FeeSchedule, FeeType, ReferenceCatalog, SchoolClass, SchoolSection, Tariff, TariffScope, TariffStatus,
  applyTariffs, getBillingPolicy, listFeeSchedules, putBillingPolicy, putTariffRule,
  AnnualExigibilityPolicy, ExigibilityBand, ExigibilityRule, activateAnnualExigibility, createAnnualExigibility, getAnnualExigibility,
  listAnnualExigibility, putAnnualExigibilityRule,
} from './api';
import {confirmAction} from './platform/dialogs';
import {friendlyError} from './platform/errors';
import {FormField} from './platform/forms';
import {formatDate, formatMoney} from './platform/format';
import {TariffAssistant} from './settings_tariff_assistant';
import {DateInput} from './platform/date_input';

export const TARIFF_GROUPS: [string, string][] = [['GENERAL', 'Humanités générales'], ['TECHNICAL', 'Humanités techniques'], ['OTHER', 'Autre groupe']];
const SCOPES: [TariffScope, string][] = [['SCHOOL', 'Toute l’école'], ['SECTION', 'Section'], ['ACADEMIC_CLASS', 'Classe académique (niveau)'], ['OPTION_GROUP', 'Groupe d’Humanités'], ['CLASS', 'Classe ouverte']];
const STATUS_LABEL: Record<TariffStatus, string> = {ACTIVE: 'Actif', PENDING_OFFICIAL: 'En attente du barème officiel', INACTIVE: 'Inactif'};
const MONTHS: [string, string][] = [['09', 'Septembre'], ['10', 'Octobre'], ['11', 'Novembre'], ['12', 'Décembre'], ['01', 'Janvier'], ['02', 'Février'], ['03', 'Mars'], ['04', 'Avril'], ['05', 'Mai'], ['06', 'Juin'], ['07', 'Juillet'], ['08', 'Août']];
const PRIORITY: Record<TariffScope, number> = {CLASS: 1, ACADEMIC_CLASS: 2, OPTION_GROUP: 3, SECTION: 4, SCHOOL: 5};

type Props = {token: string; tariffs: Tariff[]; years: AcademicYear[]; fees: FeeType[]; classes: SchoolClass[]; sections: SchoolSection[];
  refs: ReferenceCatalog | null; can: (x: string) => boolean; onDone: () => Promise<void>};

type TariffTab = 'rules' | 'months' | 'exigibility' | 'schedules';
const TAB_KEY = 'edusync.settings.tariffs.tab';

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
  const [assistant, setAssistant] = useState<null | 'grid' | 'rule' | 'regulatory'>(null);
  // Page organisation (owner, 2026-11-02: « une page trop longue », the annual exigibility hidden at the very bottom):
  // the four jobs of this screen are four tabs with their state in the tab itself — the administrator sees at once what
  // is configured and what is not, and each tab is short. Same pattern as the settings of Stripe / Shopify / Odoo.
  const [tab, setTabState] = useState<TariffTab>(() => { try { return (sessionStorage.getItem(TAB_KEY) as TariffTab) || 'rules'; } catch { return 'rules'; } });
  const setTab = (t: TariffTab) => { setTabState(t); setError(''); try { sessionStorage.setItem(TAB_KEY, t); } catch { /* optional */ } };
  const [months, setMonths] = useState<BillingPolicy | null>(null);
  const [exig, setExig] = useState<{active: AnnualExigibilityPolicy | null; draft: AnnualExigibilityPolicy | null} | null>(null);
  const loadExig = async () => { if (!year) return; try { const rows = await listAnnualExigibility(token, year.id); setExig({active: rows.find(p => p.status === 'ACTIVE') ?? null, draft: rows.find(p => p.status === 'DRAFT') ?? null}); } catch { setExig({active: null, draft: null}); } };
  useEffect(() => { void loadExig(); }, [token, year?.id]);
  useEffect(() => { if (can('settings.tariffs.read')) getBillingPolicy(token).then(setMonths).catch(() => setMonths(null)); }, [token]);
  const locked = !year;
  const canManage = can('settings.tariffs.manage') && !locked;
  const monthLabel = (code: string) => MONTHS.find(m => m[0] === code)?.[1] ?? code;
  // An academic class is stored by its official RDC code (P6, S7, S8, H4…): show its name, the code only as a detail.
  const scopeName = (t: Tariff) => { const raw = t.scope_label ?? t.scope_ref; if (t.scope_type !== 'ACADEMIC_CLASS') return raw ?? t.scope_type;
    const ref = refs?.classes.find(c => c.code.toUpperCase() === String(raw).toUpperCase()); return ref ? ref.label : raw; };
  const scopeCode = (t: Tariff) => { const raw = t.scope_label ?? t.scope_ref; return t.scope_type === 'ACADEMIC_CLASS' && scopeName(t) !== raw ? ` · code ${raw}` : ''; };
  const tabs: {key: TariffTab; label: string; state: string; tone: 'ok' | 'warn' | 'idle'}[] = [
    {key: 'rules', label: 'Tarifs', state: yearRules.length ? `${byFee.length} frais · ${yearRules.length} règle(s)` : 'À configurer', tone: yearRules.length ? 'ok' : 'warn'},
    {key: 'months', label: 'Mois facturés', state: months ? `${months.billing_months.length} mois${months.month_due_at_enrollment ? ` · ${monthLabel(months.month_due_at_enrollment)} à l’inscription` : ''}` : '…', tone: months ? 'ok' : 'idle'},
    {key: 'exigibility', label: 'Arrivée en cours d’année', state: !exig ? '…' : exig.active ? `Active · v${exig.active.version}` : exig.draft ? 'Brouillon à activer' : 'Non configurée', tone: exig?.active ? 'ok' : exig ? 'warn' : 'idle'},
    {key: 'schedules', label: 'Échéances des classes', state: 'Appliquer aux classes', tone: 'idle'},
  ];
  return <section className="panel tariffsPage">
    <div className="panelHead"><div><h3>Tarifs &amp; barèmes{year ? <small> · {year.label}</small> : null}</h3><p>Ce que paie chaque classe, les mois facturés, la règle pour un élève qui arrive en cours d’année, puis les échéances créées pour les élèves.</p></div></div>
    {!year && <div className="emptyGuide"><b>Aucune année préparée ou en cours</b><p>Les tarifs appartiennent à une année scolaire : préparez-la d’abord.</p></div>}
    {year && <div className="tariffTabs" role="tablist" aria-label="Tarifs et barèmes">{tabs.map((t, i) =>
      <button key={t.key} type="button" role="tab" id={`tt-${t.key}`} aria-selected={tab === t.key} aria-controls={`tp-${t.key}`} className={`tariffTab ${t.tone}`} onClick={() => setTab(t.key)}>
        <span className="tariffTabNum">{i + 1}</span><span><b>{t.label}</b><small>{t.tone === 'warn' ? <svg className="tariffTabMark" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.5 15 14H1z" fill="currentColor"/><path d="M8 6v4M8 11.6v.4" stroke="#fff" strokeWidth="1.8" strokeLinecap="round"/></svg> : t.tone === 'ok' ? '✓ ' : ''}{t.state}</small></span></button>)}</div>}
    {error && <div className="error" role="alert">{error}</div>}
    {year && <div role="tabpanel" id={`tp-${tab}`} aria-labelledby={`tt-${tab}`} className="tariffPanel">
      {tab === 'rules' && <>
        {canManage && <div className="tariffCtas">
          <button type="button" className="primaryBtn" onClick={() => setAssistant('grid')}>Assistant tarifaire</button>
          <button type="button" className="softBtn" onClick={() => setAssistant('rule')}>Règle sur plusieurs cibles</button>
          <button type="button" className="softBtn" onClick={() => setAssistant('regulatory')}>Configurer les frais réglementaires</button>
          <small>Grille par niveau, aperçu de ce que chaque classe paiera, frais de l’État / TENASOSP / frais techniques.</small>
        </div>}
        {assistant && <TariffAssistant token={token} year={year} fees={fees} classes={classes} sections={sections} refs={refs} tariffs={tariffs} can={can}
          initialMode={assistant} onClose={() => setAssistant(null)} onDone={onDone}/>}
        {yearRules.length === 0 && <div className="emptyGuide"><b>Aucune règle tarifaire pour {year.label}</b><p>{fees.length ? 'Ajoutez une règle pour chaque frais : par exemple un montant pour toute l’école, puis une règle plus précise pour une section ou une classe.' : 'Commencez par les types de frais, puis revenez ici.'}</p></div>}
        <p className="policyHint">La règle la plus précise s’applique : classe ouverte → classe académique → groupe d’Humanités → section → école. Une nouvelle règle datée ne réécrit jamais un mois déjà payé.</p>
        {byFee.map(([feeId, list], i) => {
          const amounts = list.filter(t => t.amount !== null).map(t => Number(t.amount)); const cur = list[0].currency;
          const range = amounts.length ? (Math.min(...amounts) === Math.max(...amounts) ? formatMoney(String(amounts[0]), cur) : `${formatMoney(String(Math.min(...amounts)), cur)} → ${formatMoney(String(Math.max(...amounts)), cur)}`) : 'À fixer';
          return <details className="tariffGroup tariffFee" key={feeId} open={byFee.length <= 2 || i === 0}>
            <summary><h4>{list[0].fee_label ?? 'Frais'}</h4><span className="tariffFeeMeta">{list.length} règle(s) · {range}{list.some(t => t.status !== 'ACTIVE') ? ' · en attente' : ''}</span></summary>
            <ul className="moneyList">{list.map(t => <li key={t.id} className={t.status === 'ACTIVE' ? '' : 'pending'}>
              <div><b>{scopeName(t)}</b><small>{SCOPES.find(s => s[0] === t.scope_type)?.[1]}{scopeCode(t)} · dès le {formatDate(t.effective_from)}{t.source_reference ? ` · ${t.source_reference}` : ''}</small></div>
              <div className="tariffAmount">{t.amount === null ? <em className="pill">À fixer</em> : <strong className="amount">{formatMoney(t.amount, t.currency)}</strong>}{t.status !== 'ACTIVE' && <small>{STATUS_LABEL[t.status]}</small>}</div>
            </li>)}</ul>
          </details>;
        })}
        {canManage && (adding
          ? <RuleForm token={token} year={year} fees={fees} classes={classes} sections={sections} refs={refs} can={can}
                      onCancel={() => setAdding(false)} onSaved={async () => { setAdding(false); await onDone(); }}/>
          : <button type="button" className="softBtn addLine" onClick={() => setAdding(true)}>+ Nouvelle règle tarifaire <small>{year.label}</small></button>)}
        <p className="policyHint">Exemple : si l’école augmente le montant à partir de février, créez une nouvelle règle datée de février. Les mensualités antérieures gardent leur montant.</p>
      </>}
      {tab === 'months' && can('settings.tariffs.read') && <BillingMonths token={token} canEdit={can('settings.billing_months.manage')} onError={setError}
        onSaved={() => getBillingPolicy(token).then(setMonths).catch(() => undefined)}/>}
      {tab === 'exigibility' && <AnnualExigibility token={token} year={year} fees={fees} canManage={canManage} canActivate={can('settings.tariffs.apply')} onChanged={loadExig}/>}
      {tab === 'schedules' && <Schedules token={token} year={year} canApply={can('settings.tariffs.apply') && !locked} onError={setError} onDone={onDone}/>}
    </div>}
  </section>;
}

/* « Arrivée en cours d'année » (annual exigibility, MEF). For each monthly fee, how much of a month is due when a pupil
   arrives during that month (day bands), and whether the months before the arrival are due. Versioned per year:
   a draft is edited, then activated; an active version is never rewritten (a new draft is copied from it). */
const PRIOR_LABEL: Record<ExigibilityRule['prior_mode'], string> = {NOT_APPLICABLE: 'Mois avant l’arrivée : non dus', FULL: 'Mois avant l’arrivée : dus en totalité', CUSTOM: 'Mois avant l’arrivée : dus à'};
const STATUS_FR: Record<AnnualExigibilityPolicy['status'], string> = {DRAFT: 'Brouillon', ACTIVE: 'Active', SUPERSEDED: 'Remplacée'};
const RECOMMENDED: ExigibilityBand[] = [{first_day: 1, last_day: 15, percent: '100'}, {first_day: 16, last_day: 24, percent: '50'}, {first_day: 25, last_day: null, percent: '0'}];
const bandText = (b: ExigibilityBand) => `${b.last_day === null ? `à partir du ${b.first_day}` : `du ${b.first_day} au ${b.last_day}`} : ${Number(b.percent)} %`;
const ruleText = (r: Pick<ExigibilityRule, 'prior_mode' | 'prior_percent' | 'bands'>) =>
  `Mois d’arrivée — ${r.bands.map(bandText).join(' · ')}. ${PRIOR_LABEL[r.prior_mode]}${r.prior_mode === 'CUSTOM' ? ` ${Number(r.prior_percent)} %` : ''}.`;

function AnnualExigibility({token, year, fees, canManage, canActivate, onChanged}: {token: string; year: AcademicYear; fees: FeeType[]; canManage: boolean; canActivate: boolean; onChanged: () => Promise<void>}) {
  const [items, setItems] = useState<AnnualExigibilityPolicy[]>([]); const [current, setCurrent] = useState<AnnualExigibilityPolicy | null>(null);
  const [activeDetail, setActiveDetail] = useState<AnnualExigibilityPolicy | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [editing, setEditing] = useState<FeeType | null>(null);
  const monthly = fees.filter(f => f.enabled && f.periodicity === 'MONTHLY');
  const load = async () => {
    try { setError(''); const rows = await listAnnualExigibility(token, year.id); setItems(rows);
      const draft = rows.find(x => x.status === 'DRAFT'); const act = rows.find(x => x.status === 'ACTIVE');
      setCurrent(draft ? await getAnnualExigibility(token, draft.id) : null); setActiveDetail(act ? await getAnnualExigibility(token, act.id) : null);
    } catch (e) { setError(friendlyError(e)); }
  };
  useEffect(() => { void load(); }, [token, year.id]);
  const active = items.find(x => x.status === 'ACTIVE');
  const run = async (job: () => Promise<void>) => { setBusy(true); setError(''); try { await job(); await load(); await onChanged(); } catch (e) { setError(friendlyError(e)); } finally { setBusy(false); } };
  // One click: a draft is created on the fly (copied from the active version if there is one), so « Configurer » always works.
  const ensureDraft = async () => current ?? await createAnnualExigibility(token, {academic_year_id: year.id, effective_from: year.start_date, source_policy_id: active?.id ?? null});
  const save = (fee: FeeType, rule: {prior_mode: ExigibilityRule['prior_mode']; prior_percent: string | null; bands: ExigibilityBand[]}) =>
    run(async () => { const d = await ensureDraft(); await putAnnualExigibilityRule(token, d.id, {fee_type_id: fee.id, ...rule}); setEditing(null); toast.success(`Règle enregistrée pour ${fee.label}`); });
  const activate = async () => {
    if (!current || !await confirmAction({title: 'Activer cette règle ?', message: 'Les élèves inscrits ensuite en cours d’année paieront selon cette règle. Les paiements et frais déjà créés ne sont pas réécrits.', confirmLabel: 'Activer'})) return;
    await run(async () => { await activateAnnualExigibility(token, current.id, year.id); toast.success('Règle d’arrivée en cours d’année activée'); });
  };
  const shown = current ?? activeDetail;
  return <div className="exigibility">
    <div className="panelHead"><div><h4>Élève qui arrive en cours d’année</h4><p>Pour chaque frais mensuel, la part du mois d’arrivée à payer selon le jour d’arrivée, et le sort des mois précédents. Exemple recommandé : arrivé du 1 au 15 → 100 % du mois ; du 16 au 24 → 50 % ; à partir du 25 → rien ce mois-là. Un montant à 0 reste « non exigible », jamais « payé ».</p></div>
      <span className={`pill ${active ? 'ok' : 'warn'}`}>{active ? `Active · version ${active.version}` : current ? 'Brouillon à activer' : 'Non configurée'}</span></div>
    {error && <div className="error" role="alert">{error}</div>}
    {monthly.length === 0 && <div className="emptyGuide"><b>Aucun frais mensuel</b><p>Cette règle s’applique aux frais mensuels (minerval…). Créez-les dans « Types de frais ».</p></div>}
    {current && <p className="policyHint"><b>Brouillon v{current.version}</b> · effet au {formatDate(current.effective_from)} — modifiez les règles puis activez-les.{active ? ` La version ${active.version} reste appliquée jusqu’à l’activation.` : ''}</p>}
    <ul className="moneyList exigibilityList">{monthly.map(f => {
      const rule = shown?.rules?.find(r => r.fee_type_id === f.id);
      return <li key={f.id}><div><b>{f.label}</b><small>{rule ? ruleText(rule) : 'Aucune règle : le mois d’arrivée est dû en entier.'}</small></div>
        {canManage && <div className="exigibilityActions">
          {!rule && <button type="button" className="primaryBtn" disabled={busy} onClick={() => void save(f, {prior_mode: 'NOT_APPLICABLE', prior_percent: null, bands: RECOMMENDED})}>Appliquer la règle recommandée</button>}
          <button type="button" className="softBtn" disabled={busy} onClick={() => setEditing(f)}>{rule ? 'Modifier' : 'Personnaliser'}</button></div>}
        {editing?.id === f.id && <ExigibilityEditor initial={rule ?? {prior_mode: 'NOT_APPLICABLE', prior_percent: null, bands: RECOMMENDED}} busy={busy}
          onCancel={() => setEditing(null)} onSave={r => void save(f, r)}/>}
      </li>;
    })}</ul>
    {current && canActivate && <div className="formActions"><button type="button" className="primaryBtn" disabled={busy || !current.rules?.length} onClick={() => void activate()}>{busy ? 'Activation…' : 'Valider et activer'}</button>{!current.rules?.length && <small>Configurez au moins un frais pour activer.</small>}</div>}
    {items.length > 0 && <details className="exigibilityHistory"><summary>Historique des versions ({items.length})</summary><ul>{items.map(p => <li key={p.id}>Version {p.version} · {STATUS_FR[p.status]} · {p.rule_count ?? p.rules?.length ?? 0} règle(s){p.approved_at ? ` · activée le ${formatDate(p.approved_at)}` : ''}</li>)}</ul></details>}
  </div>;
}

function ExigibilityEditor({initial, busy, onCancel, onSave}: {initial: Pick<ExigibilityRule, 'prior_mode' | 'prior_percent' | 'bands'>; busy: boolean; onCancel: () => void;
  onSave: (r: {prior_mode: ExigibilityRule['prior_mode']; prior_percent: string | null; bands: ExigibilityBand[]}) => void}) {
  const [bands, setBands] = useState<ExigibilityBand[]>(initial.bands.map(b => ({...b, percent: String(Number(b.percent))})));
  const [mode, setMode] = useState(initial.prior_mode); const [prior, setPrior] = useState(initial.prior_percent ? String(Number(initial.prior_percent)) : '');
  const [err, setErr] = useState('');
  const set = (i: number, patch: Partial<ExigibilityBand>) => setBands(bs => bs.map((b, j) => j === i ? {...b, ...patch} : b));
  // Bands follow each other: each one starts the day after the previous one ends; the last one runs to the end of the month.
  const normalized = (bs: ExigibilityBand[]) => bs.map((b, i) => ({...b, first_day: i === 0 ? 1 : (bs[i - 1].last_day ?? 31) + 1, last_day: i === bs.length - 1 ? null : b.last_day}));
  function submit() {
    const bs = normalized(bands);
    for (const b of bs) { const p = Number(b.percent); if (!(p >= 0 && p <= 100)) { setErr('Chaque pourcentage doit être entre 0 et 100.'); return; } if (b.last_day !== null && (b.last_day < b.first_day || b.last_day > 30)) { setErr('Chaque tranche doit finir après son premier jour (au plus le 30, la dernière va jusqu’à la fin du mois).'); return; } }
    if (mode === 'CUSTOM' && !(Number(prior) >= 0 && Number(prior) <= 100 && prior !== '')) { setErr('Indiquez le pourcentage des mois avant l’arrivée.'); return; }
    onSave({prior_mode: mode, prior_percent: mode === 'CUSTOM' ? prior : null, bands: bs});
  }
  const bs = normalized(bands);
  return <div className="exigibilityEditor">
    <b>Mois d’arrivée</b>
    {bs.map((b, i) => <div className="bandRow" key={i}>
      <span>{i === bs.length - 1 ? `À partir du ${b.first_day}` : `Du ${b.first_day} au`}</span>
      {i < bs.length - 1 && <input type="number" min={b.first_day} max={30} value={b.last_day ?? ''} aria-label={`Dernier jour de la tranche ${i + 1}`} onChange={e => set(i, {last_day: Number(e.target.value) || null})}/>}
      <span>→</span><input type="number" min={0} max={100} value={b.percent} aria-label={`Pourcentage dû, tranche ${i + 1}`} onChange={e => set(i, {percent: e.target.value})}/><span>% du mois</span>
      {bs.length > 1 && <button type="button" className="ghost" aria-label={`Retirer la tranche ${i + 1}`} onClick={() => setBands(x => x.filter((_, j) => j !== i))}>×</button>}
    </div>)}
    {bs[bs.length - 1].first_day < 30 && <button type="button" className="ghost" onClick={() => setBands(x => { const n = normalized(x); const last = n[n.length - 1]; return [...n.slice(0, -1), {...last, last_day: Math.min(29, last.first_day + 7)}, {first_day: 0, last_day: null, percent: '0'}]; })}>+ Ajouter une tranche</button>}
    <FormField label="Mois avant l’arrivée"><select value={mode} onChange={e => setMode(e.target.value as ExigibilityRule['prior_mode'])}>
      <option value="NOT_APPLICABLE">Non dus (recommandé)</option><option value="FULL">Dus en totalité</option><option value="CUSTOM">Dus à un pourcentage</option></select></FormField>
    {mode === 'CUSTOM' && <FormField label="Pourcentage des mois avant l’arrivée"><input type="number" min={0} max={100} value={prior} onChange={e => setPrior(e.target.value)}/></FormField>}
    {err && <div className="error" role="alert">{err}</div>}
    <div className="formActions"><button type="button" className="ghost" onClick={onCancel}>Annuler</button><button type="button" className="primaryBtn" disabled={busy} onClick={submit}>Enregistrer la règle</button></div>
  </div>;
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
    <FormField label="Devise"><select value={currency} onChange={e => setCurrency(e.target.value as 'CDF' | 'USD')}><option value="CDF">FC</option><option>USD</option></select></FormField>
    <FormField label="Applicable dès *" error={errors.effective}><DateInput min={year.start_date} max={year.end_date} value={effective} onChange={e => setEffective(e.target.value)}/></FormField>
    <FormField label="Référence officielle"><input value={source} maxLength={240} onChange={e => setSource(e.target.value)} placeholder="Ex. arrêté, circulaire"/></FormField>
    <div className="formActions"><button type="button" className="ghost" onClick={onCancel}>Annuler</button><button className="primaryBtn" disabled={busy}>{busy ? 'Enregistrement…' : 'Enregistrer la règle'}</button></div>
  </form>;
}

function BillingMonths({token, canEdit, onError, onSaved}: {token: string; canEdit: boolean; onError: (m: string) => void; onSaved?: () => void}) {
  const [policy, setPolicy] = useState<BillingPolicy | null>(null); const [months, setMonths] = useState<string[]>([]); const [due, setDue] = useState(''); const [busy, setBusy] = useState(false);
  async function load() { try { const p = await getBillingPolicy(token); setPolicy(p); setMonths(p.billing_months); setDue(p.month_due_at_enrollment ?? ''); } catch (e) { onError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [token]);
  async function save() {
    if (!months.length) { onError('Sélectionnez au moins un mois facturé.'); return; }
    if (due && !months.includes(due)) { onError('Le mois exigé à l’inscription doit faire partie des mois facturés.'); return; }
    try { setBusy(true); await putBillingPolicy(token, {billing_months: months, month_due_at_enrollment: due || null, expected_version: policy?.version ?? null}); toast.success('Mois de facturation enregistrés'); await load(); onSaved?.(); }
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

