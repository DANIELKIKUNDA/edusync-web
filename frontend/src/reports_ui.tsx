import {explainHttpError} from './platform/errors';
// N3-G — periodic financial reports and analyses copied from the Desktop golden master (terrain.financial_report_rows,
// register_generated_report, documents.export_periodic_financial_report_pdf/xlsx, operations.analysis_*).
import {previewPdf} from './document_io';
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {ProductSalesReport} from './schooling_parity_ui';
import {friendlyError} from './platform/errors';
import {formatMoney,formatDate} from './platform/format';

const API = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const auth = (token: string) => ({'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'});
// Server refusals go through the shared explainer (translated, remembered by friendlyError) — 2026-10-25.
async function detail(r: Response, fallback: string) { let body: unknown = null; try { body = await r.json(); } catch { /* non JSON */ } return r.status ? explainHttpError(r.status, body) : fallback; }
async function getJson<T>(token: string, path: string, fallback: string): Promise<T> { const r = await fetch(`${API}${path}`, {headers: auth(token)}); if (!r.ok) throw new Error(await detail(r, fallback)); return r.json(); }
async function getBlob(token: string, path: string, init: RequestInit = {}, fallback = 'Document indisponible'): Promise<Response> {
  const r = await fetch(`${API}${path}`, {...init, headers: {...auth(token), ...(init.headers ?? {})}}); if (!r.ok) throw new Error(await detail(r, fallback)); return r;
}
const qs = (o: Record<string, string>) => '?' + new URLSearchParams(o).toString();
const money = (v: string | number, c: string) => formatMoney(String(v), c);
type Profile = {code: string; label: string; title: string; intro: string};
type Row = {payment_id: string; paid_day: string; last_name?: string; middle_name?: string; first_name?: string; class_label?: string; observation: string; currency: string; amount: string; reporting_status: string};
type Report = {rows: Row[]; totals: Record<string, string>; partial_reporting_mode: string; profile: Profile};
const MODE_LABEL: Record<string, string> = {SEPARATE: 'acomptes présentés à part', INCLUDE: 'acomptes inclus', EXCLUDE_UNTIL_SETTLED: 'reconnus une fois soldés'};
const iso = (d: Date) => d.toISOString().slice(0, 10);
function reportActorScope(token:string):string {try {const claims=JSON.parse(atob(token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/')));if(/^[0-9a-f-]{36}$/i.test(claims.sub)&&/^[0-9a-f-]{36}$/i.test(claims.school_id))return `${claims.school_id}.${claims.sub}`}catch{/* opaque session */}return 'current-session'}

function bounds(type: string, ref: string): [string, string] {
  const d = new Date(ref + 'T00:00:00');
  if (type === 'HEBDOMADAIRE') { const day = (d.getDay() + 6) % 7; const a = new Date(d); a.setDate(d.getDate() - day); const b = new Date(a); b.setDate(a.getDate() + 6); return [iso(a), iso(b)]; }
  if (type === 'MENSUEL') { const a = new Date(d.getFullYear(), d.getMonth(), 1); const b = new Date(d.getFullYear(), d.getMonth() + 1, 0); return [iso(a), iso(b)]; }
  return [ref, ref];
}

export function PeriodicReports({token, can}: {token: string; can: (p: string) => boolean}) {
  const today = iso(new Date());
  const [profiles, setProfiles] = useState<Profile[]>([]); const [profile, setProfile] = useState('CONSOLIDE'); const [type, setType] = useState('JOURNALIER');
  const [ref, setRef] = useState(today); const [start, setStart] = useState(today); const [end, setEnd] = useState(today);
  const [report, setReport] = useState<Report | null>(null); const [generated, setGenerated] = useState<any[]>([]); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [a, b] = type === 'PERSONNALISE' ? [start, end] : bounds(type, ref);
  useEffect(() => { getJson<{profiles: Profile[]}>(token, '/finance/reports/profiles', 'Profils indisponibles').then(x => setProfiles(x.profiles)).catch(e => setError(friendlyError(e)));
    if (can('finance.reports.history.read')) getJson<{items: any[]}>(token, '/finance/reports/generated', '').then(x => setGenerated(x.items)).catch(() => undefined); }, [token]);
  async function run() { try { setError(''); setReport(await getJson<Report>(token, `/finance/reports/periodic${qs({profile_code: profile, period_type: type, start: a, end: b})}`, 'Rapport indisponible')); } catch (e) { setError(friendlyError(e)); } }
  async function officialPdf() {
    try { setBusy(true); const payload = JSON.stringify({profile_code: profile, period_type: type, start: a, end: b});
      const slot = `edusync.official-report.request.${reportActorScope(token)}`; const saved = JSON.parse(sessionStorage.getItem(slot) || 'null');
      const key = saved?.payload === payload ? saved.key : crypto.randomUUID();
      sessionStorage.setItem(slot, JSON.stringify({payload,key}));
      const r = await getBlob(token, '/finance/reports/periodic/pdf', {method: 'POST', body: payload, headers: {'Idempotency-Key': key}});
      const n = r.headers.get('X-Report-Number'); previewPdf(await r.blob()); toast.success(`Rapport officiel ${n ?? ''} ${r.headers.get('X-Report-Replayed') === 'yes' ? 'retrouvé' : 'généré et archivé'}`);
      if (can('finance.reports.history.read')) setGenerated((await getJson<{items: any[]}>(token, '/finance/reports/generated', '')).items); }
    catch (e) { setError(friendlyError(e)); } finally { setBusy(false); }
  }
  async function excel() {
    try { const r = await getBlob(token, `/finance/reports/periodic.xlsx${qs({profile_code: profile, period_type: type, start: a, end: b})}`); const url = URL.createObjectURL(await r.blob());
      const link = document.createElement('a'); link.href = url; link.download = `rapport_${profile.toLowerCase()}_${a}.xlsx`; link.click(); }
    catch (e) { setError(friendlyError(e)); }
  }
  return <section className="reportsDesk">
    <div className="reportControls">
      <label>Rapport<select value={profile} onChange={e => setProfile(e.target.value)}>{profiles.map(p => <option key={p.code} value={p.code}>{p.label}</option>)}</select></label>
      <label>Période<select value={type} onChange={e => setType(e.target.value)}><option value="JOURNALIER">Journalier</option><option value="HEBDOMADAIRE">Hebdomadaire</option><option value="MENSUEL">Mensuel</option><option value="PERSONNALISE">Personnalisée</option></select></label>
      {type === 'PERSONNALISE' ? <><label>Du<input type="date" aria-label="Du" value={start} onChange={e => setStart(e.target.value)}/></label><label>Au<input type="date" aria-label="Au" value={end} onChange={e => setEnd(e.target.value)}/></label></>
        : <label>Date de référence<input type="date" aria-label="Date de référence" value={ref} onChange={e => setRef(e.target.value)}/></label>}
      <button className="collectBtn" onClick={() => void run()}>Aperçu</button>
    </div>
    {error && <div className="error" role="alert">{error}</div>}
    {report ? <>
      <div className="reportTitle"><div><span className="eyebrow">{a === b ? formatDate(a) : `${formatDate(a)} → ${formatDate(b)}`} · {MODE_LABEL[report.partial_reporting_mode] ?? report.partial_reporting_mode}</span><h3>{report.profile.title}</h3><small>{report.profile.intro}</small></div>
        <b>{money(report.totals.CDF ?? 0, 'CDF')} · {money(report.totals.USD ?? 0, 'USD')}</b></div>
      <div className="dayActions">{can('finance.reports.periodic.generate') && <button className="collectBtn" disabled={busy} onClick={() => void officialPdf()}>Générer le rapport officiel</button>}
        {can('finance.reports.periodic.export') && <button className="softBtn" onClick={() => void excel()}>Excel (sans numéro)</button>}</div>
      <div className="cashTableWrap"><table className="cashSummaryTable"><thead><tr><th>N°</th><th>Noms et post-noms</th><th>Classe</th><th>Observation</th><th>FC</th><th>USD</th></tr></thead>
        <tbody>{report.rows.map((r, i) => <tr key={r.payment_id}><td>{i + 1}</td><td><b>{[r.last_name, r.middle_name, r.first_name].filter(Boolean).join(' ') || '—'}</b></td><td>{r.class_label || '—'}</td><td>{r.observation}</td>
          <td>{r.currency === 'CDF' ? money(r.amount, 'CDF') : ''}</td><td>{r.currency === 'USD' ? money(r.amount, 'USD') : ''}</td></tr>)}
          {report.rows.length === 0 && <tr><td colSpan={6}>Aucun encaissement pour ce rapport sur la période.</td></tr>}
          <tr><th></th><th>TOTAL</th><th></th><th></th><th>{money(report.totals.CDF ?? 0, 'CDF')}</th><th>{money(report.totals.USD ?? 0, 'USD')}</th></tr></tbody></table></div>
    </> : <div className="checkoutEmpty">Choisissez le rapport et la période, puis affichez-le. Le PDF officiel reçoit un numéro (préfixe des rapports) ; l’Excel n’en consomme pas.</div>}
    {generated.length > 0 && <details className="dayOps"><summary>Rapports officiels émis ({generated.length})</summary><ul>{generated.map(g => <li key={g.id}><span>{g.report_label} · {g.profile_code} · {formatDate(g.start_date)}{g.end_date !== g.start_date ? ` → ${formatDate(g.end_date)}` : ''}</span><b>{new Date(g.generated_at).toLocaleDateString('fr-FR')}</b></li>)}</ul></details>}
  </section>;
}

export function FinanceAnalyses({token, can}: {token: string; can: (p: string) => boolean}) {
  const [fees, setFees] = useState<any[]>([]); const [cashiers, setCashiers] = useState<any[]>([]); const [funds, setFunds] = useState<any[]>([]); const [error, setError] = useState('');
  useEffect(() => {
    if (can('finance.analysis.by_fee.read')) getJson<{items: any[]}>(token, '/finance/reports/analysis/fees', 'Analyse indisponible').then(x => setFees(x.items)).catch(e => setError(friendlyError(e)));
    if (can('finance.analysis.by_cashier.read')) getJson<{items: any[]}>(token, '/finance/reports/analysis/cashiers', 'Analyse indisponible').then(x => setCashiers(x.items)).catch(e => setError(friendlyError(e)));
    if (can('finance.analysis.advance.read')) getJson<{items: any[]}>(token, '/finance/reports/analysis/advance-funds', 'Analyse indisponible').then(x => setFunds(x.items)).catch(() => undefined);
  }, [token]);
  return <section className="reportsDesk">
    {error && <div className="error" role="alert">{error}</div>}
    {can('finance.analysis.by_fee.read') && <><h3>Analyse par type de frais</h3><div className="cashTableWrap"><table className="cashSummaryTable"><thead><tr><th>Frais</th><th>Élèves</th><th>Brut</th><th>Réductions</th><th>Net attendu</th><th>Réglé</th><th>Reste</th></tr></thead>
      <tbody>{fees.map((f, i) => <tr key={i}><td><b>{f.fee_name}</b></td><td>{f.students}</td><td>{money(f.gross_expected, f.currency)}</td><td>{money(f.discounts, f.currency)}</td><td>{money(f.net_expected, f.currency)}</td><td>{money(f.paid, f.currency)}</td><td><b>{money(f.balance, f.currency)}</b></td></tr>)}
        {fees.length === 0 && <tr><td colSpan={7}>Aucun frais pour l’année.</td></tr>}</tbody></table></div></>}
    {can('finance.analysis.by_cashier.read') && <><h3>Analyse par caissier</h3><div className="cashTableWrap"><table className="cashSummaryTable"><thead><tr><th>Caissier</th><th>Paiements</th><th>Montant</th></tr></thead>
      <tbody>{cashiers.map((c, i) => <tr key={i}><td><b>{c.cashier_name}</b></td><td>{c.payment_count}</td><td>{money(c.amount, c.currency)}</td></tr>)}{cashiers.length === 0 && <tr><td colSpan={3}>Aucun paiement.</td></tr>}</tbody></table></div></>}
    {can('finance.analysis.advance.read') && funds.length > 0 && <><h3>Fonds anticipés</h3><div className="cashTableWrap"><table className="cashSummaryTable"><thead><tr><th>Devise</th><th>Fonds</th><th>Reçus</th><th>Imputés</th><th>Disponibles</th><th>Restitués</th></tr></thead>
      <tbody>{funds.map((f, i) => <tr key={i}><td>{f.currency==='CDF'?'FC':f.currency}</td><td>{f.fund_count}</td><td>{money(f.received_total, f.currency)}</td><td>{money(f.allocated_total, f.currency)}</td><td>{money(f.available_total, f.currency)}</td><td>{money(f.reversed_total, f.currency)}</td></tr>)}</tbody></table></div></>}
    {can('finance.products.sales_report.read') && <ProductSalesReport token={token}/>}
  </section>;
}

export async function openStudentAccountPdf(token: string, studentId: string) {
  try { const r = await getBlob(token, `/finance/reports/students/${studentId}/account.pdf`); previewPdf(await r.blob()); } catch (e) { toast.error(friendlyError(e)); }
}
