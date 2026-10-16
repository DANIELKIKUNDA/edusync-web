// N3-H — schooling parity copied from the Desktop golden master: probable duplicates before a new pupil
// (find_probable_students), historical arrears (student_historical_arrears), family contact diagnostics and indicators
// (family_contact_diagnostics, family_kpi_details), contribution register (contribution_register), article sales report
// (product_sales_report) and the read-only enrollment-date check (preview_enrollment_date_repair).
import React, {useEffect, useState} from 'react';
import {friendlyError} from './platform/errors';
import {formatMoney} from './platform/format';

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

/** Desktop family_contact_diagnostics + family_overview_summary + family_kpi_details. */
export function FamilyInsights({token}: {token: string}) {
  const [diag, setDiag] = useState<Record<string, number> | null>(null); const [ov, setOv] = useState<Record<string, number> | null>(null);
  const [metric, setMetric] = useState(''); const [rows, setRows] = useState<any[]>([]); const [error, setError] = useState('');
  useEffect(() => { getJson<Record<string, number>>(token, '/schooling/families/diagnostics').then(setDiag).catch(e => setError(friendlyError(e)));
    getJson<Record<string, number>>(token, '/schooling/families/overview').then(setOv).catch(() => undefined); }, [token]);
  async function open(m: string) { setMetric(m); try { setRows((await getJson<{items: any[]}>(token, `/schooling/families/kpi/${m}`)).items); } catch (e) { setError(friendlyError(e)); } }
  return <div className="familyInsights">
    {error && <div className="error" role="alert">{error}</div>}
    {ov && <div className="familyKpis">
      <span><b>{ov.families}</b><small>Familles inscrites</small></span>
      <button onClick={() => void open('LARGE_ELIGIBLE')}><b>{ov.large_eligible}</b><small>Familles nombreuses ({ov.large_family_min_children}+ enfants)</small></button>
      <button onClick={() => void open('BENEFICIARIES')}><b>{ov.beneficiaries}</b><small>Bénéficiaires d’avantages</small></button>
      <button onClick={() => void open('STAFF_CHILDREN')}><b>{ov.staff_children}</b><small>Enfants du personnel</small></button></div>}
    {diag && <div className="familyDiag"><b>Qualité des contacts</b>
      <small>{diag.without_responsible} famille(s) sans responsable · {diag.multiple_primary} avec plusieurs responsables principaux · {diag.responsible_without_phone} responsable(s) sans téléphone · {diag.shared_phones} téléphone(s) partagé(s) entre familles</small></div>}
    {metric && <ul className="dayDetails">{rows.map((r, i) => <li key={i}><span>{r.family_name ?? [r.last_name, r.first_name].filter(Boolean).join(' ')}{r.matricule ? ` · ${r.matricule}` : ''}{r.children ? ` · ${r.children}` : ''}{r.staff_name ? ` · agent ${r.staff_name}` : ''}{r.benefit_type ? ` · ${r.benefit_type}` : ''}</span>
      <b>{r.enrolled_children ?? r.class_label ?? ''}</b></li>)}{rows.length === 0 && <li><span>Aucune ligne.</span></li>}</ul>}
  </div>;
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
    <div className="reportControls dense"><label>Du<input type="date" aria-label="Ventes du" value={start} onChange={e => setStart(e.target.value)}/></label><label>Au<input type="date" aria-label="Ventes au" value={end} onChange={e => setEnd(e.target.value)}/></label><button className="softBtn" onClick={() => void run()}>Afficher les ventes</button></div>
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
