// Rapports (owner report 2026-10-25: opening the tab showed « Une difficulté est survenue »). The hub opened « Rapports
// périodiques » for everyone, a screen that needs finance.reports.periodic.generate. Each section is now shown only to the
// roles holding its capability and the first allowed one opens; the cashier finally reaches what his role grants: the
// daily financial report, the article sales report and the register of generated reports.
import React, {useEffect, useMemo, useState} from 'react';
import {toast} from 'sonner';
import {cashDayPdf} from './api';
import {previewPdf} from './document_io';
import {friendlyError} from './platform/errors';
import {NavGlyph} from './platform/nav_icons';
import {FinanceAnalyses, PeriodicReports, getJson} from './reports_ui';
import {ProductSalesReport} from './schooling_parity_ui';
import {generatedReports, type GeneratedReport} from './api';
import './reports_hub.css';
import {DateInput} from './platform/date_input';

type Key = 'daily' | 'periodic' | 'sales' | 'analyses' | 'templates' | 'history';
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const PERIOD: Record<string, string> = {JOURNALIER: 'Journalier', HEBDOMADAIRE: 'Hebdomadaire', MENSUEL: 'Mensuel', PERSONNALISE: 'Personnalisé'};
const frDay=(v:string)=>{const [y,m,d]=v.split('-').map(Number);return y&&m&&d?new Date(y,m-1,d).toLocaleDateString('fr-FR') : v};

export function ReportsHubPro({token, can, templates}: {token: string; can: (p: string) => boolean; templates: React.ReactNode}) {
  // Templates and the register of generated reports are school-wide read models: the server says whether this actor's
  // scope reaches them (a section-only Préfet / Directeur does not — PR #27). Unknown (no periodic right) = unchanged.
  const [schoolHistory, setSchoolHistory] = useState(true);
  useEffect(() => { if (!can('finance.reports.periodic.generate')) return;
    getJson<{generated_history_available: boolean}>(token, '/finance/reports/profiles', 'Profils indisponibles')
      .then(x => setSchoolHistory(x.generated_history_available !== false)).catch(() => {}); }, [token, can]);
  const sections = useMemo(() => ([
    ['daily', 'Rapport du jour', 'doc', can('finance.reports.daily.generate')],
    ['periodic', 'Rapports périodiques', 'calendar', can('finance.reports.periodic.generate')],
    ['sales', 'Ventes d’articles', 'cart', can('finance.products.sales_report.read')],
    ['analyses', 'Analyses de gestion', 'chart', can('finance.analysis.by_fee.read') || can('finance.analysis.by_cashier.read') || can('finance.analysis.advance.read')],
    ['templates', 'Synthèses par modèle', 'layers', can('finance.reports.periodic.generate') && schoolHistory],
    ['history', 'Rapports générés', 'clock', can('finance.reports.history.read') && schoolHistory],
  ] as Array<[Key, string, string, boolean]>).filter(s => s[3]), [can, schoolHistory]);
  const [key, setKey] = useState<Key | null>(sections[0]?.[0] ?? null);
  if (!sections.length) return <p className="rh-empty">Aucun rapport n’est ouvert à votre rôle.</p>;
  return <section className="rh-root">
    <nav className="rh-tabs" role="tablist" aria-label="Rapports">{sections.map(([k, l, g]) => <button key={k} type="button" role="tab" aria-selected={key === k} className={key === k ? 'on' : ''} onClick={() => setKey(k)}><NavGlyph g={g} size={16}/>{l}</button>)}</nav>
    {key === 'daily' && <DailyReport token={token}/>}
    {key === 'periodic' && <PeriodicReports token={token} can={can}/>}
    {key === 'sales' && <ProductSalesReport token={token}/>}
    {key === 'analyses' && <FinanceAnalyses token={token} can={(p: string) => p !== 'finance.products.sales_report.read' && can(p)}/>}
    {key === 'templates' && templates}
    {key === 'history' && <GeneratedList token={token}/>}
  </section>;
}

function DailyReport({token}: {token: string}) {
  const [day, setDay] = useState(iso(new Date())); const [busy, setBusy] = useState<'preview'|'official'|''>('');
  async function open(preview:boolean) { try { setBusy(preview?'preview':'official'); previewPdf(await cashDayPdf(token, 'report', day, preview), preview?'Aperçu du rapport financier journalier':'Rapport financier journalier officiel');
      toast.success(preview?'Aperçu préparé':'Rapport officiel généré et archivé dans Documents'); }
    catch (e) { toast.error(friendlyError(e)); } finally { setBusy(''); } }
  return <article className="rh-card"><div><h4>Rapport financier journalier</h4><p>L’aperçu ne crée aucun document officiel. « Générer le rapport officiel » archive une version figée dans Documents.</p></div>
    <div className="rh-row"><label className="rh-field"><span>Journée</span><DateInput value={day} max={iso(new Date())} onChange={e => setDay(e.target.value)}/></label>
      <button type="button" className="rh-btn" disabled={!!busy || !day} onClick={() => void open(true)}><NavGlyph g="eye" size={17}/>{busy==='preview'?'Préparation…':'Aperçu'}</button>
      <button type="button" className="rh-btn primary" disabled={!!busy || !day} onClick={() => void open(false)}><NavGlyph g="doc" size={17}/>{busy==='official'?'Génération…':'Générer le rapport officiel'}</button></div></article>;
}

function GeneratedList({token}: {token: string}) {
  const [items, setItems] = useState<GeneratedReport[] | null>(null); const [err, setErr] = useState(''); const [q, setQ] = useState('');
  useEffect(() => { generatedReports(token).then(setItems).catch(e => setErr(friendlyError(e))); }, [token]);
  const rows = (items ?? []).filter(r => !q.trim() || `${r.report_label} ${r.profile_code}`.toLowerCase().includes(q.trim().toLowerCase()));
  return <article className="rh-card"><div className="rh-row spread"><div><h4>Rapports officiels générés</h4><p>Chaque rapport officiel reçoit un numéro unique ; le document est classé dans « Documents ».</p></div>
    <label className="rh-search"><NavGlyph g="search" size={15}/><input value={q} onChange={e => setQ(e.target.value)} placeholder="Numéro, profil…" aria-label="Rechercher un rapport"/></label></div>
    {err && <div className="error" role="alert">{err}</div>}
    <div className="rh-table" role="table" aria-label="Rapports générés"><div className="rh-tr rh-th" role="row"><span>N°</span><span>Profil</span><span>Période</span><span>Du</span><span>Au</span><span>Généré le</span></div>
      {rows.map(r => <div className="rh-tr" role="row" key={r.id}><span><b>{r.report_label}</b></span><span>{r.profile_code}</span><span>{PERIOD[r.period_type] ?? r.period_type}</span><span>{frDay(r.start_date)}</span><span>{frDay(r.end_date)}</span><span>{new Date(r.generated_at).toLocaleString('fr-FR', {dateStyle: 'short', timeStyle: 'short'})}</span></div>)}
      {items && rows.length === 0 && <p className="rh-empty">Aucun rapport officiel généré pour le moment.</p>}
      {!items && !err && <p className="rh-empty">Chargement…</p>}</div></article>;
}
