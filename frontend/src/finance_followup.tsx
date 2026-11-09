// Suivi financier (owner request 2026-10-25): « on veut voir la classe de 2e CG, qui est en ordre avec le mois de mars et
// qui ne l'a pas encore payé, pour permettre le recouvrement — en RDC il faut renvoyer les enfants pour qu'ils paient ».
// Pattern of school fee-collection tools (defaulters list per class and period, printable for the person who goes into the
// classroom, then a quick re-check after payments): class → fee → period, cumulative by default, not-in-order first.
import React, {useEffect, useMemo, useState} from 'react';
import {toast} from 'sonner';
import {fetchFollowup, followupFile, listClassSelector, type FollowupResponse, type SchoolClass} from './api';
import {exportManaged, previewPdf} from './document_io';
import {friendlyError} from './platform/errors';
import {formatMoney} from './platform/format';
import {NavGlyph} from './platform/nav_icons';
import './finance_followup.css';

type View = 'NOT' | 'OK' | 'ALL';
export default function FinanceFollowup({token, can, yearId, schoolName}: {token: string; can: (p: string) => boolean; yearId?: string; schoolName?: string}) {
  const [classes, setClasses] = useState<SchoolClass[]>([]);
  const [section, setSection] = useState(''); const [classId, setClassId] = useState('');
  const [currency, setCurrency] = useState<'CDF' | 'USD'>('CDF'); const [fee, setFee] = useState(''); const [column, setColumn] = useState(''); const [cumulative, setCumulative] = useState(true);
  const [res, setRes] = useState<FollowupResponse | null>(null); const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const [view, setView] = useState<View>('NOT'); const [q, setQ] = useState('');
  useEffect(() => { listClassSelector(token, yearId).then(c => { setClasses(c); }).catch(e => setErr(friendlyError(e))); }, [token, yearId]);
  const sections = useMemo(() => [...new Map(classes.map(c => [c.section_id, c.section_label ?? 'Section'])).entries()], [classes]);
  const classChoices = classes.filter(c => !section || c.section_id === section);
  useEffect(() => { if (!classId) { setRes(null); return; } let alive = true; setBusy(true); setErr('');
    fetchFollowup(token, {class_id: classId, column: column || undefined, cumulative, currency, year_id: yearId})
      .then(r => { if (!alive) return; setRes(r); if (r.data) { setColumn(r.data.column); setFee(r.fees.find(g => g.periods.some(p => p.key === r.data!.column))?.key ?? ''); } })
      .catch(e => { if (alive) { setRes(null); setErr(friendlyError(e)); } }).finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; }; }, [token, classId, column, cumulative, currency, yearId]);
  const group = res?.fees.find(g => g.key === fee);
  const d = res?.data;
  const rows = useMemo(() => (d?.rows ?? []).filter(r => r.status !== 'NA' && (view === 'ALL' || (view === 'OK') === (r.status === 'OK'))
    && (!q.trim() || `${r.student_name} ${r.matricule}`.toLowerCase().includes(q.trim().toLowerCase()))), [d, view, q]);
  const params = () => ({class_id: classId, column, cumulative, currency, year_id: yearId});
  async function print(all: boolean) { try { previewPdf(await followupFile(token, 'pdf', {...params(), all_students: all})); toast.success(all ? 'Situation de la classe ouverte' : 'Liste des élèves non en ordre ouverte'); } catch (e) { toast.error(friendlyError(e)); } }
  async function excel() { try { await exportManaged(await followupFile(token, 'xlsx', params()), {school: schoolName ?? 'École', module: 'Centre financier', category: 'Suivi financier', filename: `suivi_${d?.class_label ?? 'classe'}_${d?.period_label ?? ''}.xlsx`}); toast.success('Suivi exporté en Excel'); } catch (e) { toast.error(friendlyError(e)); } }
  const canExport = can('finance.views.vf01.export');

  return <section className="ff-root">
    <header className="ff-head"><div><span className="ff-eyebrow">Suivi financier</span><h3>Qui est en ordre ?</h3><p>Choisissez une classe, un frais et une période : la liste des élèves non en ordre s’imprime pour le passage en classe.</p></div></header>
    <div className="ff-filters">
      <label className="ff-field"><span>Section</span><select value={section} onChange={e => { setSection(e.target.value); setClassId(''); setColumn(''); }}><option value="">Toutes</option>{sections.map(([id, l]) => <option key={id} value={id}>{l}</option>)}</select></label>
      <label className="ff-field grow"><span>Classe</span><select value={classId} onChange={e => { setClassId(e.target.value); setColumn(''); }} aria-invalid={!classId}><option value="">Choisir une classe…</option>{classChoices.map(c => <option key={c.id} value={c.id}>{section ? '' : `${c.section_label ?? ''} · `}{c.label}</option>)}</select></label>
      <label className="ff-field"><span>Devise</span><select value={currency} onChange={e => { setCurrency(e.target.value as 'CDF' | 'USD'); setColumn(''); }}><option value="CDF">FC</option><option value="USD">USD</option></select></label>
      {res && res.fees.length > 0 && <label className="ff-field"><span>Frais</span><select value={fee} onChange={e => { const g = res.fees.find(x => x.key === e.target.value); setFee(e.target.value); if (g) setColumn(g.periods[g.periods.length - 1].key); }}>{res.fees.map(g => <option key={g.key} value={g.key}>{g.label}</option>)}</select></label>}
    </div>
    {group && group.periods.length > 1 && <div className="ff-periods">
      <div className="ff-chips" role="group" aria-label="Période">{group.periods.map(p => <button key={p.key} type="button" aria-pressed={column === p.key} className={column === p.key ? 'on' : ''} onClick={() => setColumn(p.key)}>{p.label}</button>)}</div>
      <div className="ff-seg" role="group" aria-label="Lecture"><button type="button" aria-pressed={cumulative} className={cumulative ? 'on' : ''} onClick={() => setCumulative(true)}>Jusqu’à ce mois</button><button type="button" aria-pressed={!cumulative} className={!cumulative ? 'on' : ''} onClick={() => setCumulative(false)}>Ce mois seulement</button></div>
    </div>}
    {err && <div className="error" role="alert">{err}</div>}
    {!classId ? <div className="ff-empty"><NavGlyph g="users" size={28}/><b>Choisissez une classe</b><span>La situation de chaque élève s’affiche immédiatement.</span></div>
      : busy && !d ? <div className="ff-skel"><i/><i/><i/><i/></div>
      : res && !d ? <div className="ff-empty"><b>Aucun frais généré pour cette classe en {currency}</b><span>Vérifiez les barèmes de la classe ou changez de devise.</span></div>
      : d && <>
        <div className="ff-kpis">
          <button type="button" className={`not ${view === 'NOT' ? 'on' : ''}`} onClick={() => setView('NOT')}><b>{d.counts.not_in_order}</b><span>Non en ordre</span><small>{d.counts.partial} partiel(s)</small></button>
          <button type="button" className={`ok ${view === 'OK' ? 'on' : ''}`} onClick={() => setView('OK')}><b>{d.counts.in_order}</b><span>En ordre</span><small>sur {d.counts.students} élève(s)</small></button>
          <button type="button" className={view === 'ALL' ? 'on' : ''} onClick={() => setView('ALL')}><b>{formatMoney(d.remaining, d.currency)}</b><span>Reste à recouvrer</span><small>taux {d.rate.toLocaleString('fr-FR')} %</small></button>
        </div>
        <div className="ff-bar"><div><b>{d.class_label}</b> · {d.title}{d.cumulative && d.periods.length > 1 ? <small> ({d.periods.join(', ')})</small> : null}</div>
          <label className="ff-search"><NavGlyph g="search" size={15}/><input value={q} onChange={e => setQ(e.target.value)} placeholder="Nom ou matricule…" aria-label="Rechercher un élève"/></label>
          {canExport && <div className="ff-actions" aria-label="Actions d’export"><button type="button" className="ff-btn primary" onClick={() => void print(false)} disabled={!d.counts.not_in_order}><NavGlyph g="print" size={17}/>Liste des non-régularisés</button>
            <button type="button" className="ff-btn" onClick={() => void print(true)}><NavGlyph g="doc" size={17}/>Situation de toute la classe</button><button type="button" className="ff-btn" onClick={() => void excel()}><NavGlyph g="sheet" size={17}/>Exporter vers Excel</button></div>}
        </div>
        <div className="ff-table" role="table" aria-label="Situation des élèves">
          <div className="ff-row ff-th" role="row"><span>Élève</span><span>Situation</span><span>Reste dû</span><span>Périodes non réglées</span></div>
          {rows.map(r => <div className={`ff-row ${r.status.toLowerCase()}`} role="row" key={r.student_id}>
            <span><b>{r.student_name}</b><small>{r.matricule}{r.terminal ? ` · ${r.terminal === 'ABANDON' ? 'abandon' : 'transféré'}` : ''}</small></span>
            <span><em className={`ff-chip ${r.status.toLowerCase()}`}>{r.status_label}</em></span>
            <span className={r.status === 'OK' ? '' : 'ff-due'}>{formatMoney(r.remaining, d.currency)}</span>
            <span className="ff-missing">{r.missing.length ? r.missing.join(', ') : '—'}</span></div>)}
          {rows.length === 0 && <p className="ff-none">{view === 'NOT' ? 'Tous les élèves sont en ordre pour cette période.' : 'Aucun élève dans ce filtre.'}</p>}
        </div>
      </>}
  </section>;
}
