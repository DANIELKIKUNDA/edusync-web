import React, {useCallback, useEffect, useId, useLayoutEffect, useRef, useState} from 'react';
import {platformDashboard, type DashboardWatchItem, type PlatformDashboardData} from '../api';
import {friendlyError} from './errors';
import {auditActionLabel, resultLabel} from './labels';
import {NavGlyph} from './nav_icons';
import './dashboard.css';

/* Platform dashboard (lot UX 2026-10). Every figure comes from GET /platform/dashboard, whose definitions are the
   same as the filtered views the cards open (see backend modules/platform/application/dashboard.py). The quick
   actions are computed from the capabilities of the signed-in account; hiding a button never replaces the server
   check, which refuses the action anyway. */

export type DashboardTarget =
  | {tab: 'schools'; status?: string; filter?: 'needs_admin'}
  | {tab: 'access'; activeOnly?: boolean}
  | {tab: 'team' | 'diagnostics' | 'audit'};

type Props = {token: string; userName?: string; can: (tab: string) => boolean; has: (cap: string) => boolean; onOpen: (t: DashboardTarget) => void; onCreateSchool: () => void};

const nf = new Intl.NumberFormat('fr-FR');

function relative(iso: string) {
  const d = new Date(iso); const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 2) return 'à l’instant';
  if (mins < 60) return `il y a ${mins} min`;
  if (mins < 60 * 24) return `il y a ${Math.round(mins / 60)} h`;
  if (mins < 60 * 24 * 7) return `il y a ${Math.round(mins / 1440)} j`;
  return d.toLocaleDateString('fr-FR', {day: '2-digit', month: 'short', year: 'numeric'});
}

function BlockError({message, onRetry}: {message: string; onRetry: () => void}) {
  return <div className="pd-error" role="alert"><NavGlyph g="alert" size={16}/><span>{message}</span><button type="button" className="pd-link" onClick={onRetry}>Réessayer</button></div>;
}

export function PlatformDashboard({token, userName, can, has, onOpen, onCreateSchool}: Props) {
  const [data, setData] = useState<PlatformDashboardData | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const watchRef = useRef<HTMLHeadingElement>(null);
  const load = useCallback((signal?: AbortSignal) => {
    setLoading(true); setError('');
    platformDashboard(token, signal)
      .then(d => { if (!signal?.aborted) setData(d); })
      .catch(e => { if (signal?.aborted) return; console.warn('[edusync] tableau de bord : chargement en échec', e?.name || 'erreur'); setError(friendlyError(e)); })
      .finally(() => { if (!signal?.aborted) setLoading(false); });
  }, [token]);
  useEffect(() => { const ctl = new AbortController(); load(ctl.signal); return () => ctl.abort(); }, [load]);
  const retry = () => load();
  const k = data?.kpis;
  const showWatch = () => { const el = watchRef.current; if (!el) return; el.scrollIntoView({behavior: 'smooth', block: 'start'}); el.focus({preventScroll: true}); };

  const cards: {key: string; icon: string; label: string; value?: number; hint: string; aria: string; tone?: string; go: () => void}[] = [
    {key: 'schools', icon: 'school', label: 'Écoles', value: k?.schools, hint: k ? (k.schools ? `dont ${nf.format(k.schools - k.active_schools)} non active(s)` : 'Aucune école pour le moment') : '',
      aria: `Écoles : ${k ? nf.format(k.schools) : 'chargement'}. Ouvrir la liste de toutes les écoles`, go: () => onOpen({tab: 'schools'})},
    {key: 'active', icon: 'checkCircle', label: 'Écoles actives', value: k?.active_schools, hint: k ? (k.schools ? `${Math.round(k.active_schools * 100 / k.schools)} % des écoles` : 'Aucune école active') : '',
      aria: `Écoles actives : ${k ? nf.format(k.active_schools) : 'chargement'}. Ouvrir la liste filtrée sur les écoles actives`, go: () => onOpen({tab: 'schools', status: 'ACTIVE'})},
    {key: 'access', icon: 'users', label: 'Accès actifs', value: k?.active_accesses, hint: k ? (k.active_accesses ? 'comptes avec un accès école' : 'Aucun accès actif') : '',
      aria: `Accès actifs : ${k ? nf.format(k.active_accesses) : 'chargement'}. Ouvrir la liste des comptes ayant un accès actif`, go: () => onOpen({tab: 'access', activeOnly: true})},
    {key: 'actions', icon: 'alert', label: 'Actions requises', value: k?.actions_required, tone: k && k.actions_required > 0 ? 'warn' : 'ok',
      hint: k ? (k.actions_required ? 'à traiter, détail ci-dessous' : 'Tout est en ordre') : '',
      aria: `Actions requises : ${k ? nf.format(k.actions_required) : 'chargement'}. Afficher les éléments à surveiller`, go: showWatch},
  ];
  const quick = [
    has('platform.schools.create') && {key: 'create', icon: 'plus', label: 'Créer une école', go: onCreateSchool},
    has('platform.collaborators.manage') && can('team') && {key: 'manager', icon: 'user', label: 'Ajouter un Manager', go: () => onOpen({tab: 'team'})},
    has('platform.school_admin.bootstrap') && {key: 'admin', icon: 'key', label: 'Inviter un administrateur', go: () => onOpen({tab: 'schools', filter: 'needs_admin'})},
    can('schools') && {key: 'schools', icon: 'school', label: 'Voir les écoles', go: () => onOpen({tab: 'schools'})},
  ].filter(Boolean) as {key: string; icon: string; label: string; go: () => void}[];

  const hour = new Date().getHours();
  const hello = hour < 5 || hour >= 18 ? 'Bonsoir' : 'Bonjour';
  const first = (userName || '').trim().split(/\s+/)[0];
  const today = new Date().toLocaleDateString('fr-FR', {weekday: 'long', day: 'numeric', month: 'long'});
  return <div className="pd">
    <header className="pd-hero">
      <div className="pd-hero-text">
        <p className="pd-hero-date">{today.charAt(0).toUpperCase() + today.slice(1)}</p>
        <h2>{hello}{first ? `, ${first}` : ''}</h2>
        <p>Vue d’ensemble de la plateforme EduSync : écoles, accès et points d’attention.</p>
      </div>
      <button type="button" className="pd-refresh" onClick={retry} disabled={loading} aria-label="Actualiser le tableau de bord">
        <NavGlyph g="sync" size={16}/><span>{loading ? 'Actualisation…' : data ? `Mis à jour à ${new Date(data.generated_at).toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit'})}` : 'Actualiser'}</span>
      </button>
    </header>
    <section className="pd-kpis" aria-label="Indicateurs clés">
      {cards.map(c => <button key={c.key} type="button" className={`pd-kpi ${c.tone ? `pd-kpi-${c.tone}` : ''}`} onClick={c.go} aria-label={c.aria} disabled={!k && !!error}>
        <span className="pd-kpi-icon" aria-hidden="true"><NavGlyph g={c.icon} size={20}/></span>
        <span className="pd-kpi-body">
          <small className="pd-kpi-label">{c.label}</small>
          {k ? <b className="pd-kpi-value">{nf.format(c.value ?? 0)}</b> : <i className="pd-skel pd-skel-value" aria-hidden="true"/>}
          {k ? <small className="pd-kpi-hint">{c.hint}</small> : <i className="pd-skel pd-skel-hint" aria-hidden="true"/>}
        </span>
        <span className="pd-kpi-chevron" aria-hidden="true"><NavGlyph g="chevronRight" size={18}/></span>
      </button>)}
    </section>
    {error && !data && <BlockError message={`Indicateurs indisponibles : ${error}`} onRetry={retry}/>}

    {quick.length > 0 && <section className="pd-quick" aria-labelledby="pd-quick-title">
      <h3 id="pd-quick-title">Actions rapides</h3>
      <div className="pd-quick-list">{quick.map(q => <button key={q.key} type="button" className="pd-quick-btn" onClick={q.go}>
        <span aria-hidden="true"><NavGlyph g={q.icon} size={17}/></span>{q.label}</button>)}</div>
    </section>}

    <div className="pd-mid">
      <section className="pd-card pd-trend" aria-labelledby="pd-trend-title">
        <TrendBlock data={data} loading={loading} error={error} onRetry={retry}/>
      </section>
      <section className="pd-card pd-watch" aria-labelledby="pd-watch-title">
        <div className="pd-card-head"><h3 id="pd-watch-title" ref={watchRef} tabIndex={-1}>À surveiller</h3>
          {data && k && k.actions_required > 0 && <span className="pd-badge pd-badge-warn">{nf.format(k.actions_required)} à traiter</span>}</div>
        {!data ? (error ? <BlockError message="Éléments à surveiller indisponibles." onRetry={retry}/> : <div className="pd-skel-list" aria-busy="true"><i/><i/><i/></div>)
          : <WatchList items={data.watchlist} can={can} onOpen={onOpen}/>}
      </section>
    </div>

    {(data?.recent_activity !== null || (!data && has('platform.audit.read'))) && <section className="pd-card pd-activity" aria-labelledby="pd-activity-title">
      <div className="pd-card-head"><h3 id="pd-activity-title">Activité récente</h3>
        {can('audit') && <button type="button" className="pd-link" onClick={() => onOpen({tab: 'audit'})}>Voir toute l’activité <NavGlyph g="chevronRight" size={15}/></button>}</div>
      {!data ? (error ? <BlockError message="Activité indisponible." onRetry={retry}/> : <div className="pd-skel-list" aria-busy="true"><i/><i/><i/><i/><i/></div>)
        : (data.recent_activity || []).length === 0 ? <p className="pd-empty">Aucune activité enregistrée pour le moment.</p>
        : <ul className="pd-events">{(data.recent_activity || []).map(e => <li key={e.id}>
            <span className={`pd-dot ${e.result === 'SUCCESS' ? 'pd-dot-ok' : 'pd-dot-warn'}`} aria-hidden="true"/>
            <div className="pd-event-main"><b title={e.action}>{auditActionLabel(e.action)}</b>
              <small>{e.school_name || e.school_code || 'Plateforme EduSync'}{e.actor ? ` · ${e.actor}` : ' · Système'}</small></div>
            <div className="pd-event-side"><time dateTime={e.occurred_at} title={new Date(e.occurred_at).toLocaleString('fr-FR')}>{relative(e.occurred_at)}</time>
              {e.result !== 'SUCCESS' && <em className="pd-badge pd-badge-warn">{resultLabel(e.result)}</em>}</div>
          </li>)}</ul>}
    </section>}
  </div>;
}

function WatchList({items, can, onOpen}: {items: DashboardWatchItem[]; can: (tab: string) => boolean; onOpen: (t: DashboardTarget) => void}) {
  if (items.length === 0) return <div className="pd-allgood"><NavGlyph g="checkCircle" size={20}/><div><b>Aucune anomalie</b><small>Rien ne demande votre intervention pour le moment.</small></div></div>;
  const sorted = [...items].sort((a, b) => (a.tone === b.tone ? 0 : a.tone === 'action' ? -1 : 1));
  return <ul className="pd-watch-list">{sorted.map(w => {
    const target = w.target && can(w.target.tab) ? w.target as DashboardTarget : null;
    const inner = <><span className={`pd-watch-icon pd-tone-${w.tone}`} aria-hidden="true"><NavGlyph g={w.tone === 'action' ? 'alert' : 'info'} size={17}/></span>
      <span className="pd-watch-text"><b>{w.title}</b>{w.detail && <small>{w.detail}</small>}</span>
      {target && <span className="pd-kpi-chevron" aria-hidden="true"><NavGlyph g="chevronRight" size={16}/></span>}</>;
    return <li key={w.key}>{target
      ? <button type="button" className="pd-watch-item" onClick={() => onOpen(target)} aria-label={`${w.title}. ${w.tone === 'action' ? 'Action requise' : 'Information'}. Ouvrir`}>{inner}</button>
      : <div className="pd-watch-item pd-static">{inner}</div>}</li>;
  })}</ul>;
}

const monthFmt = new Intl.DateTimeFormat('fr-FR', {month: 'short'});
const monthLong = new Intl.DateTimeFormat('fr-FR', {month: 'long', year: 'numeric'});
const monthDate = (m: string) => new Date(`${m}-01T12:00:00Z`);

function TrendBlock({data, loading, error, onRetry}: {data: PlatformDashboardData | null; loading: boolean; error: string; onRetry: () => void}) {
  const [range, setRange] = useState<6 | 12>(6);
  const head = <div className="pd-card-head"><h3 id="pd-trend-title">Évolution des écoles actives</h3>
    {data?.trend.has_data && <div className="pd-seg" role="group" aria-label="Période affichée">
      {([6, 12] as const).map(r => <button key={r} type="button" aria-pressed={range === r} className={range === r ? 'pd-on' : ''} onClick={() => setRange(r)}>{r} mois</button>)}</div>}</div>;
  if (!data) return <>{head}{error ? <BlockError message="Tendance indisponible." onRetry={onRetry}/> : <div className={`pd-skel pd-skel-chart ${loading ? '' : ''}`} aria-busy="true"/>}</>;
  if (!data.trend.has_data) return <>{head}<div className="pd-empty-chart"><NavGlyph g="trend" size={22}/><b>Aucune tendance disponible pour le moment.</b><small>La courbe apparaîtra avec l’activation des premières écoles.</small></div></>;
  const points = data.trend.months.slice(-range);
  return <>{head}<TrendChart points={points}/></>;
}

function TrendChart({points}: {points: {month: string; active: number}[]}) {
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(600);
  const titleId = useId();
  useLayoutEffect(() => {
    const el = box.current; if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))));
    ro.observe(el); return () => ro.disconnect();
  }, []);
  const h = w < 480 ? 180 : 220;
  const pad = {l: 34, r: 14, t: 16, b: 28};
  const max = Math.max(...points.map(p => p.active), 1);
  const step = Math.max(1, Math.ceil(max / 4));
  const top = step * Math.ceil(max / step);
  const ticks = Array.from({length: Math.floor(top / step) + 1}, (_, i) => i * step);
  const x = (i: number) => pad.l + (points.length === 1 ? 0 : i * (w - pad.l - pad.r) / (points.length - 1));
  const y = (v: number) => pad.t + (h - pad.t - pad.b) * (1 - v / top);
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.active).toFixed(1)}`).join(' ');
  const area = `${line} L${x(points.length - 1).toFixed(1)},${y(0)} L${x(0).toFixed(1)},${y(0)} Z`;
  const last = points[points.length - 1];
  const every = w < 420 && points.length > 6 ? 2 : 1;
  return <div className="pd-chart" ref={box}>
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-labelledby={titleId}>
      <title id={titleId}>{`Écoles actives par mois : ${points.map(p => `${monthLong.format(monthDate(p.month))} ${p.active}`).join(', ')}.`}</title>
      {ticks.map(t => <g key={t}><line className="pd-grid" x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)}/>
        <text className="pd-axis" x={pad.l - 8} y={y(t)} dy="0.32em" textAnchor="end">{t}</text></g>)}
      <defs><linearGradient id={`${titleId}-g`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" className="pd-grad-top"/><stop offset="100%" className="pd-grad-bottom"/></linearGradient></defs>
      <path className="pd-area" d={area} fill={`url(#${titleId}-g)`}/>
      <path className="pd-line" d={line}/>
      {points.map((p, i) => <g key={p.month}>
        <circle className={i === points.length - 1 ? 'pd-point pd-point-last' : 'pd-point'} cx={x(i)} cy={y(p.active)} r={i === points.length - 1 ? 4.5 : 3}>
          <title>{`${monthLong.format(monthDate(p.month))} : ${p.active} école(s) active(s)`}</title></circle>
        {i % every === (points.length - 1) % every && <text className="pd-axis" x={x(i)} y={h - 8} textAnchor={i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}>{monthFmt.format(monthDate(p.month)).replace('.', '')}</text>}
      </g>)}
    </svg>
    <p className="pd-chart-note">Ce mois-ci : <b>{nf.format(last.active)}</b> école(s) active(s), comme l’indicateur ci-dessus.</p>
  </div>;
}
