import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {toast} from 'sonner';
import {cancelFact, getConductClass, getConductClasses, reportFact, reportFactBatch, type ConductClass, type ConductPupil} from './api';
import {ReasonDialog} from './pedagogy_calendar';
import {ConductTab as ConductScaleTab} from './pedagogy_teachers';
import {friendlyError} from './platform/errors';
import {useLive} from './platform/live';
import {NavGlyph} from './platform/nav_icons';
import {Button, EmptyState, Skeleton} from './platform/ui';

/* V2 lot 3b — conduct (owner 2026-11-22: « rendre ça automatique »). Nobody grades conduct: the staff report facts in
   3 taps (class → pupil → fact), EduSync computes points and mention live. Serious facts only for the management;
   « Annuler » right after a mistake; the list « à suivre » for the titular and the discipline director. */

const TONE: Record<string, string> = {E: 'pc-ok', TB: 'pc-ok', B: 'pc-info', AB: 'pc-info', ME: 'pc-warn', MA: 'pc-warn'};

export function ConductArea({token, canReport, canConfigure}: {token: string; canReport: boolean; canConfigure: boolean}) {
  const [view, setView] = useState<'facts' | 'scale'>(canReport ? 'facts' : 'scale');
  return <div className="pcd">
    {canReport && <div className="pg-chips pcd-switch" role="group" aria-label="Conduite">
      <button type="button" aria-pressed={view === 'facts'} onClick={() => setView('facts')}>Signaler et suivre</button>
      <button type="button" aria-pressed={view === 'scale'} onClick={() => setView('scale')}>{canConfigure ? 'Régler le barème' : 'Barème de l’école'}</button>
    </div>}
    {view === 'facts' ? <ConductFacts token={token}/> : <ConductScaleTab token={token}/>}
  </div>;
}

function ConductFacts({token}: {token: string}) {
  const [classes, setClasses] = useState<{class_id: string; label: string; section_label: string; titular: boolean; teaches: boolean}[] | null>(null);
  const [classId, setClassId] = useState<string>(() => { try { return localStorage.getItem('edusync.conduct.class') || ''; } catch { return ''; } });
  const [error, setError] = useState('');
  useEffect(() => { getConductClasses(token).then(r => { setClasses(r.items); if (!r.items.some(c => c.class_id === classId)) setClassId(r.items[0]?.class_id || ''); })
    .catch(e => setError(friendlyError(e))); }, [token]);
  if (error) return <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Conduite indisponible</b><small>{error}</small></div></div>;
  if (!classes) return <Skeleton lines={5}/>;
  if (!classes.length) return <EmptyState icon="users" title="Aucune classe pour vous" text="Les classes dont vous êtes enseignant ou titulaire apparaîtront ici."/>;
  return <>
    <label className="pt-field pcd-class"><span>Classe</span>
      <select value={classId} onChange={e => { setClassId(e.target.value); try { localStorage.setItem('edusync.conduct.class', e.target.value); } catch { /* private mode */ } }}>
        {classes.map(c => <option key={c.class_id} value={c.class_id}>{c.label}{c.titular ? ' · titulaire' : ''}</option>)}
      </select></label>
    {classId && <ClassConduct key={classId} token={token} classId={classId}/>}
  </>;
}

function ClassConduct({token, classId}: {token: string; classId: string}) {
  const [data, setData] = useState<ConductClass | null>(null);
  const [error, setError] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [onlyFollow, setOnlyFollow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [cancelling, setCancelling] = useState<null | {id: string; label: string}>(null);
  const [many, setMany] = useState(false); const [picked, setPicked] = useState<string[]>([]);   // « toute la rangée bavarde »
  const load = useCallback(() => { getConductClass(token, classId).then(setData).catch(e => setError(friendlyError(e))); }, [token, classId]);
  useEffect(load, [load]);
  useLive(['pedagogy'], load);
  const update = (p: Partial<ConductPupil> & {student_id: string}) => setData(d => d && {...d, pupils: d.pupils.map(x => x.student_id === p.student_id ? {...x, ...p} : x)});
  const list = useMemo(() => (data?.pupils ?? []).filter(p => (!onlyFollow || p.to_follow) && (!q.trim() || p.name.toLowerCase().includes(q.trim().toLowerCase()))), [data, q, onlyFollow]);
  async function report(p: ConductPupil, rule: ConductClass['rules'][number]) {
    setBusy(true);
    try {
      const r = await reportFact(token, {class_id: classId, student_id: p.student_id, rule_code: rule.code});
      if (r.offline_queued) { toast.info(`${rule.label} — ${p.name} : enregistré sur cet appareil`, {description: 'Envoyé automatiquement au retour du réseau.'}); setOpen(null); return; }
      update(r); setOpen(null);
      toast.success(`${rule.label} — ${p.name} : ${r.points} points (${r.mention})`, {duration: 6000,
        action: {label: 'Annuler', onClick: () => { void cancelFact(token, r.fact_id, 'Annulé aussitôt par son auteur (erreur de saisie)').then(u => { update(u); toast('Fait annulé'); }).catch(e => toast.error(friendlyError(e))); }}});
    } catch (e) { toast.error(friendlyError(e)); } finally { setBusy(false); }
  }
  async function reportMany(rule: ConductClass['rules'][number]) {
    setBusy(true);
    try {
      const r = await reportFactBatch(token, {class_id: classId, student_ids: picked, rule_code: rule.code});
      if (r.offline_queued) toast.info(`${rule.label} — ${picked.length} élèves : enregistré sur cet appareil`, {description: 'Envoyé automatiquement au retour du réseau.'});
      else { r.pupils.forEach(update); toast.success(`${rule.label} : ${r.count} élèves`); }
      setPicked([]); setMany(false);
    } catch (e) { toast.error(friendlyError(e)); } finally { setBusy(false); }
  }
  if (error) return <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Conduite indisponible</b><small>{error}</small></div></div>;
  if (!data) return <Skeleton lines={6}/>;
  const s = data.summary;
  return <>
    <div className="pg-summary" aria-label="Résumé">
      <div><b>{data.period.code}</b><small>{data.period.label}{data.period.current ? ' · en cours' : ''}{data.period.closed ? ' · figée' : ''}</small></div>
      <div className={s.to_follow ? 'pg-warn' : 'pg-ok'}><b>{s.to_follow}</b><small>élève{s.to_follow > 1 ? 's' : ''} à suivre</small></div>
      <div><b>{s.facts}</b><small>fait{s.facts > 1 ? 's' : ''} signalé{s.facts > 1 ? 's' : ''}</small></div>
      <div><b>{s.pupils}</b><small>élèves</small></div>
    </div>
    {data.period.closed && <div className="pc-note"><NavGlyph g="info" size={16}/><span>Période clôturée : la conduite est figée pour le bulletin.</span></div>}
    <div className="pcd-tools">
      <label className="pg-search"><NavGlyph g="search" size={16}/><span className="sr-only">Chercher un élève</span>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Chercher un élève" inputMode="search"/></label>
      <button type="button" className="pcd-follow" aria-pressed={onlyFollow} onClick={() => setOnlyFollow(x => !x)}>À suivre seulement</button>
      {!data.period.closed && <button type="button" className="pcd-follow" aria-pressed={many} onClick={() => { setMany(x => !x); setPicked([]); setOpen(null); }}>Plusieurs élèves</button>}
    </div>
    <ul className={`pcd-list ${many ? 'pcd-many' : ''}`}>{list.map(p => <li key={p.student_id} className={p.to_follow ? 'pcd-alert' : ''}>
      <button type="button" className={`pcd-row ${many && picked.includes(p.student_id) ? 'picked' : ''}`} aria-expanded={!many && open === p.student_id}
        aria-pressed={many ? picked.includes(p.student_id) : undefined} disabled={data.period.closed}
        onClick={() => many ? setPicked(x => x.includes(p.student_id) ? x.filter(i => i !== p.student_id) : [...x, p.student_id]) : setOpen(o => o === p.student_id ? null : p.student_id)}>
        {many && <span className="pcd-tick" aria-hidden="true">{picked.includes(p.student_id) ? <NavGlyph g="check" size={16}/> : null}</span>}
        <span className="pcd-name"><b>{p.name}{p.suspended && <em className="pgr-susp">Suspendu</em>}</b><small>{p.facts ? `${p.facts} fait${p.facts > 1 ? 's' : ''}${p.lates ? ` · ${p.lates} retard${p.lates > 1 ? 's' : ''}` : ''}` : 'Aucun fait'}{p.to_follow ? ' · à suivre' : ''}</small></span>
        <span className="pcd-score"><b>{p.points}</b><span className={`pc-chip ${TONE[p.mention] || ''}`}>{p.mention}</span></span>
      </button>
      {!many && open === p.student_id && <div className="pcd-open">
        <p className="pcd-ask">Que s’est-il passé ?</p>
        <div className="pcd-rules">{data.rules.map(r => <button key={r.code} type="button" disabled={busy} className={r.points > 0 ? 'plus' : r.grave ? 'grave' : ''}
          onClick={() => void report(p, r)}><span>{r.label}</span><b>{r.points > 0 ? `+${r.points}` : r.points}</b></button>)}</div>
        {p.recent.length > 0 && <ul className="pcd-recent">{p.recent.map(f => <li key={f.id}>
          <span>{new Date(f.occurred_on + 'T12:00:00').toLocaleDateString('fr-FR', {day: 'numeric', month: 'short'})} · {f.label} <b>{f.points > 0 ? `+${f.points}` : f.points}</b></span>
          {f.can_cancel && <button type="button" onClick={() => setCancelling({id: f.id, label: f.label})}>Annuler</button>}</li>)}</ul>}
      </div>}
    </li>)}</ul>
    {many && picked.length > 0 && <div className="pcd-bar" role="region" aria-label="Signaler pour les élèves choisis">
      <b>{picked.length} élève{picked.length > 1 ? 's' : ''} choisi{picked.length > 1 ? 's' : ''} : que s’est-il passé ?</b>
      <div className="pcd-rules">{data.rules.map(r => <button key={r.code} type="button" disabled={busy} className={r.points > 0 ? 'plus' : r.grave ? 'grave' : ''}
        onClick={() => void reportMany(r)}><span>{r.label}</span><b>{r.points > 0 ? `+${r.points}` : r.points}</b></button>)}</div>
    </div>}
    {cancelling && <ReasonDialog title={`Annuler « ${cancelling.label} »`} hint="Le fait ne compte plus dans la conduite ; il reste dans l’historique avec votre motif."
      onClose={() => setCancelling(null)} onConfirm={async reason => { const id = cancelling.id; setCancelling(null);
        try { update(await cancelFact(token, id, reason)); toast.success('Fait annulé'); } catch (e) { toast.error(friendlyError(e)); } }}/>}
  </>;
}
