// N3-H — schooling parity copied from the Desktop golden master: probable duplicates before a new pupil
// (find_probable_students), historical arrears (student_historical_arrears), family contact diagnostics and indicators
// (family_contact_diagnostics, family_kpi_details), contribution register (contribution_register), article sales report
// (product_sales_report) and the read-only enrollment-date check (preview_enrollment_date_repair).
import React, {useEffect, useState} from 'react';
import {friendlyError} from './platform/errors';
import {formatMoney} from './platform/format';
import {DateInput} from './platform/date_input';
import {NavGlyph} from './platform/nav_icons';
import './schooling.css';

const API = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const auth = (token: string) => ({'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'});
async function getJson<T>(token: string, path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, {headers: auth(token)});
  if (!r.ok) { let d = 'Données indisponibles'; try { const j = await r.json(); if (typeof j.detail === 'string') d = j.detail; } catch { /* keep default */ } throw new Error(d); }
  return r.json();
}
const qs = (o: Record<string, string>) => '?' + new URLSearchParams(Object.entries(o).filter(([, v]) => v)).toString();
const money = (v: string | number, c: string) => formatMoney(String(v), c);
const iso = () => new Date().toISOString().slice(0, 10);

/** Desktop find_probable_students, shown while a new pupil is typed in the enrollment wizard. */
export function ProbableStudents({token, lastName, middleName, firstName, birthDate}: {token: string; lastName: string; middleName?: string; firstName?: string; birthDate?: string}) {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    if ((lastName || '').trim().length < 2) { setItems([]); return; }
    const t = window.setTimeout(() => getJson<{items: any[]}>(token, `/schooling/students/probable${qs({last_name: lastName.trim(), middle_name: (middleName || '').trim(), first_name: (firstName || '').trim(), birth_date: birthDate || ''})}`)
      .then(x => setItems(x.items)).catch(() => setItems([])), 300);
    return () => window.clearTimeout(t);
  }, [token, lastName, middleName, firstName, birthDate]);
  if (!items.length) return null;
  return <div className="probableBox" role="status"><b>Élève(s) probablement déjà enregistré(s)</b><small>Vérifiez avant de créer une nouvelle fiche : un élève existant se réinscrit avec son matricule.</small>
    <ul>{items.map(p => <li key={p.id}>{p.matricule} · {[p.last_name, p.middle_name, p.first_name].filter(Boolean).join(' ')}{p.birth_date ? ` · né(e) le ${p.birth_date}` : ''}{p.family_name ? ` · ${p.family_name}` : ''}</li>)}</ul></div>;
}

/** Desktop student_historical_arrears: earlier years, never mixed with the new enrollment. */
export function HistoricalArrears({token, studentId}: {token: string; studentId: string}) {
  const [items, setItems] = useState<any[] | null>(null);
  useEffect(() => { getJson<{items: any[]}>(token, `/schooling/students/${studentId}/historical-arrears`).then(x => setItems(x.items)).catch(() => setItems(null)); }, [token, studentId]);
  if (!items?.length) return null;
  return <div className="probableBox arrears"><b>Arriérés des années antérieures</b><small>Ils restent rattachés à leur année d’origine et s’encaissent sans changer l’année de l’application.</small>
    <ul>{items.map((a, i) => <li key={i}>{a.year_label} · <b>{money(a.balance, a.currency)}</b></li>)}</ul></div>;
}

/** Desktop family_contact_diagnostics + family_overview_summary + family_kpi_details.
 *  Owner report 2026-11-06: professional, clickable indicator cards; the detail opens as a list below the card chosen;
 *  contact quality reads as a checklist (green when nothing is missing). */
type FamilyMetric = 'LARGE_ELIGIBLE' | 'BENEFICIARIES' | 'STAFF_CHILDREN';
const BENEFIT_KIND: Record<string, string> = {LARGE_FAMILY: 'Famille nombreuse', STAFF_CHILD: 'Enfant du personnel'};
const FINANCE_MODE: Record<string, string> = {FAMILY: 'Payé par la famille', PAYROLL: 'Retenue sur salaire', SCHOOL: 'Pris en charge par l’école', THIRD_PARTY: 'Payé par un tiers'};
const plural = (n: number, one: string, many: string) => `${n} ${n > 1 ? many : one}`;
const pupil = (r: any) => [r.last_name, r.middle_name, r.first_name].filter(Boolean).join(' ');

export function FamilyInsights({token, onMetricChange}: {token: string; onMetricChange?: (metric: string) => void}) {
  const [diag, setDiag] = useState<Record<string, number> | null>(null); const [ov, setOv] = useState<Record<string, number> | null>(null);
  // Owner, 2026-11-08: ONE list at a time — choosing « Familles nombreuses » or « Bénéficiaires » replaces the directory
  // below (the screen tells the parent page), « Familles inscrites » brings the directory back.
  const [metric, setMetricState] = useState<FamilyMetric | ''>('');
  const setMetric = (m: FamilyMetric | '') => { setMetricState(m); onMetricChange?.(m); }; const [rows, setRows] = useState<any[] | null>(null); const [error, setError] = useState('');
  useEffect(() => { getJson<Record<string, number>>(token, '/schooling/families/diagnostics').then(setDiag).catch(e => setError(friendlyError(e)));
    getJson<Record<string, number>>(token, '/schooling/families/overview').then(setOv).catch(() => undefined); }, [token]);
  async function open(m: FamilyMetric) {
    if (metric === m) { setMetric(''); setRows(null); return; }
    setMetric(m); setRows(null);
    try { setRows((await getJson<{items: any[]}>(token, `/schooling/families/kpi/${m}`)).items); } catch (e) { setError(friendlyError(e)); setRows([]); }
  }
  function showDirectory() { setMetric(''); setRows(null); window.setTimeout(() => { const dir = document.querySelector<HTMLElement>('[data-family-directory]'); dir?.scrollIntoView({behavior: 'smooth', block: 'start'}); dir?.querySelector<HTMLInputElement>('input')?.focus({preventScroll: true}); }, 60); }
  const cards: {key: FamilyMetric | 'ALL'; icon: 'users' | 'star' | 'school' | 'home'; value: number; label: string; hint: string}[] = ov ? [
    {key: 'ALL', icon: 'home', value: ov.families ?? 0, label: 'Familles inscrites', hint: 'Voir l’annuaire des familles'},
    {key: 'LARGE_ELIGIBLE', icon: 'users', value: ov.large_eligible ?? 0, label: 'Familles nombreuses', hint: `${ov.large_family_min_children ?? 5} enfants inscrits ou plus`},
    {key: 'BENEFICIARIES', icon: 'star', value: ov.beneficiaries ?? 0, label: 'Bénéficiaires d’avantages', hint: 'Gratuités et remises accordées'},
    {key: 'STAFF_CHILDREN', icon: 'school', value: ov.staff_children ?? 0, label: 'Enfants du personnel', hint: 'Enfants rattachés à un agent'},
  ] : [];
  const checks = diag ? [
    {n: diag.without_responsible ?? 0, ok: 'Chaque famille a un responsable', ko: (n: number) => `${plural(n, 'famille', 'familles')} sans responsable`},
    {n: diag.multiple_primary ?? 0, ok: 'Un seul responsable principal par famille', ko: (n: number) => `${plural(n, 'famille', 'familles')} avec plusieurs responsables principaux`},
    {n: diag.responsible_without_phone ?? 0, ok: 'Tous les responsables ont un téléphone', ko: (n: number) => `${plural(n, 'responsable', 'responsables')} sans téléphone`},
    {n: diag.shared_phones ?? 0, ok: 'Aucun téléphone partagé entre familles', ko: (n: number) => `${plural(n, 'téléphone partagé', 'téléphones partagés')} entre familles`},
  ] : [];
  const issues = checks.filter(c => c.n > 0).length;
  const title = cards.find(c => c.key === metric)?.label ?? '';
  return <section className="fi" aria-label="Indicateurs des familles">
    {error && <div className="error" role="alert">{error}</div>}
    {ov && <div className="fi-cards">{cards.map(c => { const on = metric === c.key;
      const active = c.key === 'ALL' ? metric === '' : on;
      return <button key={c.key} type="button" className={`fi-card ${active ? 'on' : ''} ${c.value === 0 && c.key !== 'ALL' ? 'zero' : ''}`} aria-pressed={active}
        onClick={() => c.key === 'ALL' ? showDirectory() : void open(c.key)}>
        <span className="fi-icon" aria-hidden="true"><NavGlyph g={c.icon} size={20}/></span>
        <span className="fi-text"><b>{c.value}</b><span>{c.label}</span><small>{c.hint}</small></span>
        <NavGlyph g={on ? 'chevronDown' : 'chevronRight'} size={16}/>
      </button>; })}</div>}
    {metric && <div className="fi-detail" role="region" aria-label={title}>
      <header><b>{title}</b><small>{rows === null ? 'Chargement…' : plural(rows.length, 'ligne', 'lignes')}</small>
        <button type="button" className="fi-close" aria-label="Fermer la liste" onClick={() => { setMetric(''); setRows(null); }}><NavGlyph g="close" size={16}/></button></header>
      {rows && rows.length === 0 && <p className="fi-empty">{metric === 'LARGE_ELIGIBLE' ? 'Aucune famille n’atteint encore le nombre d’enfants requis.' : metric === 'BENEFICIARIES' ? 'Aucun élève ne bénéficie encore d’une gratuité ou d’une remise.' : 'Aucun enfant n’est encore rattaché à un agent de l’école.'}</p>}
      {rows && rows.length > 0 && <ul className="fi-rows">{rows.map((r, i) => metric === 'LARGE_ELIGIBLE'
        ? <li key={i}><span className="fi-main"><b>{r.family_name}</b><small>{[r.family_code, r.primary_responsible, r.primary_responsible_phone ?? r.phone].filter(Boolean).join(' · ')}</small></span>
            <em>{plural(Number(r.enrolled_children ?? 0), 'enfant', 'enfants')}</em></li>
        : metric === 'BENEFICIARIES'
        ? <li key={i}><span className="fi-main"><b>{pupil(r)}</b><small>{[r.matricule, r.class_label, r.family_name].filter(Boolean).join(' · ')}</small></span>
            <em>{BENEFIT_KIND[r.benefit_type] ?? 'Avantage'}{r.configured_percent != null ? ` · ${Number(r.configured_percent) >= 100 ? 'gratuit' : `${Number(r.configured_percent)} %`}` : ''}</em></li>
        : <li key={i}><span className="fi-main"><b>{pupil(r)}</b><small>{[r.matricule, r.class_label, r.staff_name ? `agent ${r.staff_name}` : ''].filter(Boolean).join(' · ')}</small></span>
            <em>{FINANCE_MODE[r.finance_mode] ?? 'Payé par la famille'}</em></li>)}</ul>}
    </div>}
    {diag && <div className={`fi-quality ${issues ? 'warn' : 'ok'}`}>
      <header><span className="fi-icon" aria-hidden="true"><NavGlyph g={issues ? 'alert' : 'checkCircle'} size={18}/></span>
        <span><b>Qualité des contacts</b><small>{issues ? `${plural(issues, 'point à corriger', 'points à corriger')} pour joindre les parents sans erreur` : 'Tous les contacts des familles sont exploitables'}</small></span></header>
      <ul>{checks.map((c, i) => <li key={i} className={c.n ? 'ko' : 'okItem'}><NavGlyph g={c.n ? 'alert' : 'check'} size={15}/>{c.n ? c.ko(c.n) : c.ok}</li>)}</ul>
    </div>}
  </section>;
}

/** Desktop contribution_register: required / delivered / remaining per pupil and item. */
export function ContributionRegister({token}: {token: string}) {
  const [data, setData] = useState<{items: any[]; rows: any[]} | null>(null); const [error, setError] = useState('');
  useEffect(() => { getJson<{items: any[]; rows: any[]}>(token, '/effectifs/contribution-register').then(setData).catch(e => setError(friendlyError(e))); }, [token]);
  if (error) return <div className="error" role="alert">{error}</div>;
  if (!data) return null;
  return <div className="cashTableWrap contributionRegister"><table className="cashSummaryTable"><thead><tr><th>Élève</th><th>Classe</th>{data.items.map(it => <th key={it.id}>{it.label}<small> (exigé {Number(it.required_quantity)} {it.unit})</small></th>)}</tr></thead>
    <tbody>{data.rows.map(r => <tr key={r.student_id}><td><b>{[r.last_name, r.first_name].filter(Boolean).join(' ')}</b><small> {r.matricule}</small></td><td>{r.class_label}</td>
      {data.items.map(it => { const c = r.items[it.id]; return <td key={it.id}>{Number(c.delivered)} / {Number(c.required)}{Number(c.remaining) > 0 ? <small> · reste {Number(c.remaining)}</small> : ''}</td>; })}</tr>)}
      {data.rows.length === 0 && <tr><td colSpan={2 + data.items.length}>Aucun élève inscrit.</td></tr>}</tbody></table></div>;
}

/** Desktop product_sales_report. */
export function ProductSalesReport({token}: {token: string}) {
  const [start, setStart] = useState(iso()); const [end, setEnd] = useState(iso()); const [data, setData] = useState<any>(null); const [error, setError] = useState('');
  async function run() { try { setError(''); setData(await getJson<any>(token, `/finance/reports/product-sales${qs({start, end})}`)); } catch (e) { setError(friendlyError(e)); } }
  return <div className="productSales"><h3>Ventes d’articles</h3>
    <div className="reportControls dense"><label>Du<DateInput aria-label="Ventes du" value={start} onChange={e => setStart(e.target.value)}/></label><label>Au<DateInput aria-label="Ventes au" value={end} onChange={e => setEnd(e.target.value)}/></label><button className="softBtn" onClick={() => void run()}>Afficher les ventes</button></div>
    {error && <div className="error" role="alert">{error}</div>}
    {data && <div className="cashTableWrap"><table className="cashSummaryTable"><thead><tr><th>Date</th><th>Élève</th><th>Article</th><th>Quantité</th><th>Montant</th><th>Caissier</th></tr></thead>
      <tbody>{data.rows.map((r: any) => <tr key={r.id} className={r.reversed ? 'muted' : ''}><td>{String(r.sold_at).slice(0, 16).replace('T', ' ')}</td><td>{[r.last_name, r.first_name].filter(Boolean).join(' ') || '—'}</td><td>{r.product_label}</td><td>{Number(r.quantity)}</td>
        <td>{money(r.total_amount, r.currency)}{r.reversed ? ' (annulée)' : ''}</td><td>{r.cashier_name}</td></tr>)}
        {data.rows.length === 0 && <tr><td colSpan={6}>Aucune vente sur la période.</td></tr>}
        {data.totals.map((t: any) => <tr key={t.currency}><th colSpan={4}>TOTAL {t.currency}</th><th>{money(t.amount, t.currency)}</th><th></th></tr>)}</tbody></table></div>}
  </div>;
}

/** Desktop preview_enrollment_date_repair: read-only, nothing is modified. */
export function EnrollmentDateCheck({token}: {token: string}) {
  const [data, setData] = useState<any>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function upload(f: File) {
    try { setBusy(true); setError(''); const r = await fetch(`${API}/import/students/date-repair/preview`, {method: 'POST', headers: {'Authorization': auth(token).Authorization, 'Content-Type': 'application/octet-stream'}, body: await f.arrayBuffer()});
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Contrôle impossible'); setData(await r.json()); }
    catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  return <section className="importCard"><h3>Contrôle des dates d’inscription</h3><p className="policyHint">Comparez un fichier historique (Nom, Postnom, Prénom, Sexe, Classe, Date inscription) aux inscriptions de l’année : aucune donnée n’est modifiée.</p>
    <input type="file" accept=".xlsx" aria-label="Fichier des dates d’inscription" disabled={busy} onChange={e => { const f = e.target.files?.[0]; if (f) void upload(f); }}/>
    {error && <div className="error" role="alert">{error}</div>}
    {data && <><small>{data.summary.examined} examinée(s) · {data.summary.certain} correction(s) certaine(s) · {data.summary.probable} probable(s) · {data.summary.ambiguous} à vérifier · {data.summary.not_found} non trouvée(s) · {data.summary.unchanged} inchangée(s)</small>
      <div className="cashTableWrap"><table className="cashSummaryTable"><thead><tr><th>Ligne</th><th>Élève</th><th>Résultat</th><th>Date actuelle</th><th>Date historique</th><th>Action</th></tr></thead>
        <tbody>{data.items.map((i: any) => <tr key={i.row}><td>{i.row}</td><td>{i.student_name}</td><td>{i.status}</td><td>{i.current_enrolled_on ?? '—'}</td><td>{i.historical_date ?? '—'}</td><td>{i.action ?? i.warning ?? '—'}</td></tr>)}</tbody></table></div></>}
  </section>;
}
