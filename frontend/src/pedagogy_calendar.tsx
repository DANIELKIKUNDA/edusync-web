import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {toast} from 'sonner';
import {getCalendars, saveCalendar, setEntry, validateCalendar, type CalPeriod, type PedCalendar, type PedCalendars} from './api';
import {Modal} from './platform/account';
import {DateInput} from './platform/date_input';
import {friendlyError} from './platform/errors';
import {NavGlyph} from './platform/nav_icons';
import {Button, Skeleton} from './platform/ui';

/* V2 lot 2 — calendrier pédagogique (owner 2026-11-22: « facile même pour quelqu'un de niveau 0 »).
   EduSync proposes every date from the school year; the user only checks them on a timeline, adjusts with the phone's
   date picker, saves, validates. Days not covered (holidays) are shown, never refused. */

const TERM_WORD = {TRIMESTRIEL: 'trimestre', SEMESTRIEL: 'semestre'} as const;
const TERM_ORD = ['', '1er', '2e', '3e'];
const ENTRY: Record<CalPeriod['entry_state'], {label: string; tone: string}> = {
  DRAFT: {label: '', tone: ''}, UPCOMING: {label: 'À venir', tone: 'muted'}, ONGOING: {label: 'En cours', tone: 'ok'},
  OPEN: {label: 'Saisie encore ouverte', tone: 'warn'}, CLOSED: {label: 'Saisie clôturée', tone: 'muted'}};
const fmt = (iso: string, withYear = false) => new Date(iso + 'T12:00:00').toLocaleDateString('fr-FR', {weekday: 'short', day: 'numeric', month: 'short', ...(withYear ? {year: 'numeric'} : {})});
const dayDiff = (a: string, b: string) => Math.round((new Date(b + 'T12:00:00').getTime() - new Date(a + 'T12:00:00').getTime()) / 86400000);

export function CalendarTab({token, onChanged}: {token: string; onChanged?: () => void}) {
  const [data, setData] = useState<PedCalendars | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(() => { setError(''); getCalendars(token).then(setData).catch(e => setError(friendlyError(e))); }, [token]);
  useEffect(load, [load]);
  if (error) return <div className="sc-error" role="alert"><NavGlyph g="alert" size={18}/><div><b>Calendrier indisponible</b><small>{error}</small></div><Button onClick={load}>Réessayer</Button></div>;
  if (!data) return <Skeleton lines={8}/>;
  return <div className="pc">
    <p className="pc-intro">Année scolaire <b>{data.year.label}</b> : du {fmt(data.year.start_date, true)} au {fmt(data.year.end_date, true)}.</p>
    {data.calendars.map(c => <CalendarCard key={c.structure} token={token} cal={c} year={data.year} canManage={data.can_manage}
      onSaved={next => { setData(d => d && {...d, calendars: d.calendars.map(x => x.structure === next.structure ? next : x)}); onChanged?.(); }}/>)}
  </div>;
}

function CalendarCard({token, cal, year, canManage, onSaved}: {token: string; cal: PedCalendar; year: PedCalendars['year']; canManage: boolean; onSaved: (c: PedCalendar) => void}) {
  const [dates, setDates] = useState(() => cal.periods.map(p => ({code: p.code, starts_on: p.starts_on, ends_on: p.ends_on})));
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [ask, setAsk] = useState<null | {kind: 'save' | 'reopen'; code?: string}>(null);
  useEffect(() => { setDates(cal.periods.map(p => ({code: p.code, starts_on: p.starts_on, ends_on: p.ends_on}))); }, [cal]);
  const validated = cal.status === 'VALIDATED';
  const editable = canManage && (!validated || editing);
  const dirty = dates.some((d, i) => d.starts_on !== cal.periods[i]?.starts_on || d.ends_on !== cal.periods[i]?.ends_on);
  const terms = useMemo(() => [...new Set(cal.periods.map(p => p.term))], [cal]);
  async function run(key: string, fn: () => Promise<PedCalendar>, ok: string) {
    setBusy(key); setError('');
    try { const next = await fn(); onSaved(next); setEditing(false); toast.success(ok); }
    catch (e) { setError(friendlyError(e)); } finally { setBusy(''); }
  }
  const save = (reason?: string) => run('save', () => saveCalendar(token, cal.structure, dates, reason), 'Dates enregistrées');
  const status = !cal.saved ? {label: 'Proposition EduSync', tone: 'info'} : validated ? {label: 'Validé', tone: 'ok'} : {label: 'À valider', tone: 'warn'};
  return <section className="pc-card" aria-label={cal.label}>
    <header className="pc-head">
      <div><h3>{cal.label}</h3><small>{cal.structure === 'TRIMESTRIEL' ? '3 trimestres · 6 périodes · 3 examens' : '2 semestres · 4 périodes · 2 examens'}</small></div>
      <span className={`pc-status pc-${status.tone}`}>{validated && <NavGlyph g="checkCircle" size={14}/>}{status.label}</span>
    </header>
    {!cal.saved && <div className="pc-note"><NavGlyph g="sparkles" size={16}/><span>EduSync a préparé ces dates à partir de l’année scolaire. <b>Vérifiez-les</b>, changez-les si besoin, puis enregistrez.</span></div>}
    <Timeline periods={dates} year={year} gaps={cal.gaps}/>
    {terms.map(t => <div key={t} className="pc-term">
      <h4>{TERM_ORD[t]} {TERM_WORD[cal.structure]}</h4>
      <ul>{cal.periods.filter(p => p.term === t).map(p => {
        const i = cal.periods.indexOf(p); const d = dates[i]; const st = ENTRY[p.entry_state];
        return <li key={p.code} className={p.is_exam ? 'pc-exam' : ''}>
          <div className="pc-name"><b>{p.label}</b>{!editable && <small>{fmt(d.starts_on)} → {fmt(d.ends_on, true)} · {dayDiff(d.starts_on, d.ends_on) + 1} jours</small>}</div>
          {editable ? <div className="pc-dates">
            <label><span>Du</span><DateInput value={d.starts_on} min={year.start_date} max={year.end_date} aria-label={`${p.label} : début`}
              onChange={e => setDates(x => x.map((y, j) => j === i ? {...y, starts_on: e.target.value} : y))}/></label>
            <label><span>Au</span><DateInput value={d.ends_on} min={year.start_date} max={year.end_date} aria-label={`${p.label} : fin`}
              onChange={e => setDates(x => x.map((y, j) => j === i ? {...y, ends_on: e.target.value} : y))}/></label>
          </div> : validated && <div className="pc-entry">
            {st.label && <span className={`pc-chip pc-${st.tone}`}>{st.label}</span>}
            {canManage && p.entry_state !== 'CLOSED' && p.entry_state !== 'UPCOMING' && <Button size="sm" disabled={!!busy}
              onClick={() => void run(p.code, () => setEntry(token, cal.structure, p.code, true), `${p.label} : saisie clôturée`)}>Clôturer la saisie</Button>}
            {canManage && p.entry_state === 'CLOSED' && <Button size="sm" variant="quiet" disabled={!!busy} onClick={() => setAsk({kind: 'reopen', code: p.code})}>Rouvrir</Button>}
          </div>}
        </li>;
      })}</ul>
    </div>)}
    {cal.gaps.length > 0 && !dirty && <div className="pc-gaps"><NavGlyph g="info" size={16}/><div><b>Jours sans période</b>
      {cal.gaps.map(g => <small key={g.from}>du {fmt(g.from)} au {fmt(g.to, true)} · {g.days} jour{g.days > 1 ? 's' : ''} (vacances ?)</small>)}</div></div>}
    {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
    {canManage && <footer className="pc-actions">
      {!validated && (!cal.saved || dirty) && <Button variant="primary" disabled={!!busy} onClick={() => void save()}>{busy === 'save' ? 'Enregistrement…' : 'Enregistrer ces dates'}</Button>}
      {!validated && cal.saved && !dirty && <Button variant="primary" icon="checkCircle" disabled={!!busy}
        onClick={() => void run('validate', () => validateCalendar(token, cal.structure), 'Calendrier validé')}>{busy === 'validate' ? 'Validation…' : 'Valider le calendrier'}</Button>}
      {validated && !editing && <Button variant="quiet" onClick={() => setEditing(true)}>Modifier les dates</Button>}
      {validated && editing && <><Button variant="primary" disabled={!dirty || !!busy} onClick={() => setAsk({kind: 'save'})}>Enregistrer les changements</Button>
        <Button variant="quiet" onClick={() => { setEditing(false); setDates(cal.periods.map(p => ({code: p.code, starts_on: p.starts_on, ends_on: p.ends_on}))); }}>Annuler</Button></>}
      {!validated && dirty && cal.saved && <Button variant="quiet" onClick={() => setDates(cal.periods.map(p => ({code: p.code, starts_on: p.starts_on, ends_on: p.ends_on})))}>Annuler les changements</Button>}
    </footer>}
    {ask && <ReasonDialog title={ask.kind === 'save' ? 'Modifier un calendrier validé' : 'Rouvrir la saisie'}
      hint={ask.kind === 'save' ? 'Le calendrier est déjà validé : indiquez pourquoi les dates changent. Le changement est enregistré dans le journal.' : 'Les enseignants pourront de nouveau saisir les cotes de cette période.'}
      onClose={() => setAsk(null)} onConfirm={async reason => {
        setAsk(null);
        if (ask.kind === 'save') await save(reason);
        else await run(ask.code!, () => setEntry(token, cal.structure, ask.code!, false, reason), 'Saisie rouverte');
      }}/>}
  </section>;
}

function Timeline({periods, year, gaps}: {periods: {code: string; starts_on: string; ends_on: string}[]; year: {start_date: string; end_date: string}; gaps: {from: string; to: string}[]}) {
  const total = dayDiff(year.start_date, year.end_date) + 1;
  const seg = (a: string, b: string) => ({left: `${Math.max(0, dayDiff(year.start_date, a)) / total * 100}%`, width: `${Math.max(0.6, (dayDiff(a, b) + 1) / total * 100)}%`});
  const months = useMemo(() => {
    const out: {label: string; left: string}[] = []; const d = new Date(year.start_date + 'T12:00:00'); d.setDate(1);
    const end = new Date(year.end_date + 'T12:00:00');
    while (d <= end) { const iso = d.toISOString().slice(0, 10); if (iso >= year.start_date) out.push({label: d.toLocaleDateString('fr-FR', {month: 'short'}).replace('.', ''), left: `${dayDiff(year.start_date, iso) / total * 100}%`}); d.setMonth(d.getMonth() + 1); }
    return out;
  }, [year, total]);
  return <div className="pc-timeline" aria-hidden="true">
    <div className="pc-bar">
      {gaps.map(g => <i key={g.from} className="pc-seg pc-seg-gap" style={seg(g.from, g.to)}/>)}
      {periods.map(p => <i key={p.code} className={`pc-seg ${p.code.startsWith('EX') ? 'pc-seg-exam' : 'pc-seg-period'}`} style={seg(p.starts_on, p.ends_on)} title={p.code}><span>{p.code}</span></i>)}
    </div>
    <div className="pc-months">{months.map(m => <span key={m.left} style={{left: m.left}}>{m.label}</span>)}</div>
    <div className="pc-legend"><span><i className="pc-seg-period"/>Période</span><span><i className="pc-seg-exam"/>Examens</span>{gaps.length > 0 && <span><i className="pc-seg-gap"/>Sans période</span>}</div>
  </div>;
}

export function ReasonDialog({title, hint, onClose, onConfirm}: {title: string; hint: string; onClose: () => void; onConfirm: (reason: string) => void | Promise<void>}) {
  const [reason, setReason] = useState(''); const [error, setError] = useState('');
  return <Modal title={title} onClose={onClose}>
    <form className="es-form" onSubmit={e => { e.preventDefault(); if (reason.trim().length < 5) { setError('Écrivez le motif en quelques mots.'); return; } void onConfirm(reason.trim()); }} noValidate>
      <p className="es-hint">{hint}</p>
      <label htmlFor="pc-reason">Motif *</label>
      <textarea id="pc-reason" rows={3} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} placeholder="Ex. : vacances déplacées par la province"/>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button><button className="es-btn es-btn-primary">Confirmer</button></div>
    </form>
  </Modal>;
}
