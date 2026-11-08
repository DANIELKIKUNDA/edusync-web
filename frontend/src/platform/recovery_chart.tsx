// Recovery evolution per due period (owner request 2026-10-24: « un vrai graphique qui montre l'évolution du
// recouvrement de chaque mois, % et montant »). Data: /finance/recovery/monthly (expected, regularized, remaining, rate
// per due period — months and State-fee tranches — in ONE currency: EduSync never mixes CDF and USD).
// Data-viz rules: never two y-scales on one chart → two aligned charts sharing the x axis (rate on top, amounts below:
// expected as a grey track, regularized as the filled bar, the gap is what remains); one hue; thin marks; recessive
// grid; hover tooltip on a full-height column; legend; table view; light and dark tokens.
import React, {useEffect, useMemo, useRef, useState} from 'react';
import {recoveryMonthly} from '../api';
import {formatMoney} from './format';
import './recovery_chart.css';

type Row = {ord?: number; month_label: string; expected: string | number; regularized_total: string | number; remaining: string | number; recovery_rate: string | number; debtors?: number | null};
type Data = {items: Row[]; total: Row | null};
const num = (v: unknown) => Number(v ?? 0) || 0;
const MONTHS: Record<string, string> = {janvier: 'Janv', février: 'Févr', mars: 'Mars', avril: 'Avr', mai: 'Mai', juin: 'Juin', juillet: 'Juil', août: 'Août', septembre: 'Sept', octobre: 'Oct', novembre: 'Nov', décembre: 'Déc'};
/** Consistent short labels: months (Sept, Oct… Juin, Juil) and State-fee tranches (T1, T2, T3). */
export const short = (label: string) => { const m = MONTHS[label.trim().toLowerCase()]; if (m) return m; const t = label.replace(/^.*?(\d+)(re|e) tranche$/i, 'T$1');
  return t.length <= 9 ? t : `${t.slice(0, 8).trim()}.`; };  // other fees (inscription, articles…): their own band, short axis label

export function RecoveryChart({token, yearId, compact, onOpen}: {token: string; yearId?: string; compact?: boolean; onOpen?: () => void}) {
  const [currency, setCurrency] = useState<'CDF' | 'USD'>('CDF');
  const [data, setData] = useState<Data | null>(null); const [error, setError] = useState(''); const [view, setView] = useState<'chart' | 'table'>('chart');
  const [hover, setHover] = useState<number | null>(null);
  const [width, setWidth] = useState(640); const ro = useRef<ResizeObserver | null>(null);
  // Callback ref: the chart box appears only once the data is loaded, so the observer is attached at that moment.
  const box = (el: HTMLDivElement | null) => { ro.current?.disconnect(); if (!el || typeof ResizeObserver === 'undefined') return;
    setWidth(Math.max(280, Math.round(el.getBoundingClientRect().width)));
    ro.current = new ResizeObserver(e => setWidth(Math.max(280, Math.round(e[0].contentRect.width)))); ro.current.observe(el); };
  useEffect(() => () => ro.current?.disconnect(), []);
  useEffect(() => { let alive = true; setData(null); setError('');
    recoveryMonthly(token, yearId, currency).then((r: any) => { if (alive) setData({items: r?.items ?? [], total: r?.total ?? null}); }).catch(e => { if (alive) setError(e instanceof Error ? e.message : 'Données indisponibles'); });
    return () => { alive = false; }; }, [token, yearId, currency]);
  const items = data?.items ?? [];
  const maxAmount = useMemo(() => Math.max(1, ...items.map(r => num(r.expected))), [items]);
  const t = data?.total;
  const pad = {l: 44, r: 12}; const plotW = width - pad.l - pad.r; const step = items.length ? plotW / items.length : plotW;
  const x = (i: number) => pad.l + step * i + step / 2; const barW = Math.max(6, Math.min(34, step * 0.56));
  const rateH = compact ? 96 : 120; const amtH = compact ? 120 : 160;
  const yRate = (v: number) => 10 + (rateH - 22) * (1 - Math.min(100, Math.max(0, v)) / 100);
  const yAmt = (v: number) => 8 + (amtH - 16) * (1 - v / maxAmount);
  const tick = (v: number) => v >= 1e6 ? `${(v / 1e6).toLocaleString('fr-FR', {maximumFractionDigits: 1})} M` : v >= 1e3 ? `${Math.round(v / 1e3).toLocaleString('fr-FR')} k` : String(Math.round(v));
  const linePath = items.map((r, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${yRate(num(r.recovery_rate)).toFixed(1)}`).join(' ');
  const h = hover !== null ? items[hover] : null;
  const summary = t ? `Taux de recouvrement ${num(t.recovery_rate)} % : ${formatMoney(String(t.regularized_total), currency)} régularisés sur ${formatMoney(String(t.expected), currency)} attendus.` : '';
  return <div className="rc-root">
    <div className="rc-head">
      <div className="rc-kpis">
        <div><b>{t ? `${num(t.recovery_rate).toLocaleString('fr-FR')} %` : '—'}</b><small>taux de recouvrement</small></div>
        <div><b>{t ? formatMoney(String(t.regularized_total), currency) : '—'}</b><small>régularisés</small></div>
        <div><b>{t ? formatMoney(String(t.expected), currency) : '—'}</b><small>attendus</small></div>
        <div className="rc-remaining"><b>{t ? formatMoney(String(t.remaining), currency) : '—'}</b><small>reste à recouvrer</small></div>
      </div>
      <div className="rc-controls">
        <div className="rc-seg" role="group" aria-label="Devise">{(['CDF', 'USD'] as const).map(c => <button key={c} type="button" aria-pressed={currency === c} className={currency === c ? 'on' : ''} onClick={e => { e.stopPropagation(); setCurrency(c); }}>{c === 'CDF' ? 'FC' : c}</button>)}</div>
        <div className="rc-seg" role="group" aria-label="Affichage">{([['chart', 'Graphique'], ['table', 'Tableau']] as const).map(([k, l]) => <button key={k} type="button" aria-pressed={view === k} className={view === k ? 'on' : ''} onClick={e => { e.stopPropagation(); setView(k); }}>{l}</button>)}</div>
      </div>
    </div>
    {error ? <p className="rc-empty">{error}</p> : !data ? <div className="rc-skeleton" aria-busy="true"/> : items.length === 0 ? <p className="rc-empty">Aucune échéance en {currency === 'CDF' ? 'FC' : currency} pour cette année : le recouvrement s’affichera dès que des frais seront dus.</p>
      : view === 'table' ? <div className="rc-tableWrap"><table className="rc-table"><thead><tr><th>Échéance</th><th>Taux</th><th>Régularisé</th><th>Attendu</th><th>Reste</th><th>Débiteurs</th></tr></thead>
        <tbody>{items.map((r, i) => <tr key={i}><td>{r.month_label}</td><td>{num(r.recovery_rate).toLocaleString('fr-FR')} %</td><td>{formatMoney(String(r.regularized_total), currency)}</td><td>{formatMoney(String(r.expected), currency)}</td><td>{formatMoney(String(r.remaining), currency)}</td><td>{r.debtors ?? '—'}</td></tr>)}</tbody>
        {t && <tfoot><tr><td>Total</td><td>{num(t.recovery_rate).toLocaleString('fr-FR')} %</td><td>{formatMoney(String(t.regularized_total), currency)}</td><td>{formatMoney(String(t.expected), currency)}</td><td>{formatMoney(String(t.remaining), currency)}</td><td/></tr></tfoot>}</table></div>
      : <div className="rc-charts" ref={box} onMouseLeave={() => setHover(null)}>
        <figure className="rc-figure"><figcaption>Taux de recouvrement par échéance (%)</figcaption>
          <svg width={width} height={rateH} role="img" aria-label={summary}>
            {[0, 50, 100].map(v => <g key={v}><line className="rc-grid" x1={pad.l} x2={width - pad.r} y1={yRate(v)} y2={yRate(v)}/><text className="rc-tick" x={pad.l - 8} y={yRate(v) + 4} textAnchor="end">{v} %</text></g>)}
            {hover !== null && <rect className="rc-band" x={x(hover) - step / 2} y={0} width={step} height={rateH}/>}
            <path className="rc-line" d={linePath}/>
            {items.map((r, i) => <circle key={i} className={`rc-dot ${hover === i ? 'on' : ''}`} cx={x(i)} cy={yRate(num(r.recovery_rate))} r={hover === i ? 5.5 : 4}/>)}
            {items.length > 0 && <text className="rc-direct" x={x(items.length - 1)} y={yRate(num(items[items.length - 1].recovery_rate)) - 9} textAnchor="end">{num(items[items.length - 1].recovery_rate).toLocaleString('fr-FR')} %</text>}
          </svg></figure>
        <figure className="rc-figure"><figcaption>Montants par échéance ({currency === 'CDF' ? 'FC' : currency})
          <span className="rc-legend"><i className="rc-key track"/>Attendu<i className="rc-key fill"/>Régularisé</span></figcaption>
          <svg width={width} height={amtH + 22} role="img" aria-label={`Montants attendus et régularisés par échéance, en ${currency}.`}>
            {[0, 0.5, 1].map(f => <g key={f}><line className="rc-grid" x1={pad.l} x2={width - pad.r} y1={yAmt(maxAmount * f)} y2={yAmt(maxAmount * f)}/><text className="rc-tick" x={pad.l - 8} y={yAmt(maxAmount * f) + 4} textAnchor="end">{tick(maxAmount * f)}</text></g>)}
            {hover !== null && <rect className="rc-band" x={x(hover) - step / 2} y={0} width={step} height={amtH}/>}
            {items.map((r, i) => { const e = num(r.expected), g = Math.min(num(r.regularized_total), e); const base = yAmt(0);
              return <g key={i}>
                <rect className="rc-track" x={x(i) - barW / 2} y={yAmt(e)} width={barW} height={Math.max(0, base - yAmt(e))} rx={4}/>
                {g > 0 && <rect className="rc-fill" x={x(i) - barW / 2} y={yAmt(g)} width={barW} height={Math.max(2, base - yAmt(g))} rx={4}/>}
                {/* Owner report 2026-11-08: months first, then each non-monthly fee in its own band, after a separator */}
                {num(r.ord) >= 100 && num(items[i - 1]?.ord) < 100 && i > 0 && <line className="rc-sep" x1={x(i) - step / 2} x2={x(i) - step / 2} y1={4} y2={amtH + 4}/>}
                {(step >= 34 || i % 2 === 0) && <text className="rc-x" x={x(i)} y={amtH + 15} textAnchor="middle">{step < 84 ? short(r.month_label) : r.month_label}</text>}
              </g>; })}
          </svg></figure>
        {items.map((_, i) => <button key={i} type="button" className="rc-hit" style={{left: x(i) - step / 2, width: step}} aria-label={`${items[i].month_label} : ${num(items[i].recovery_rate)} %`}
          onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} onClick={e => { e.stopPropagation(); setHover(i); }}/>)}
        {h && hover !== null && <div className="rc-tip" role="status" style={{left: Math.min(Math.max(x(hover) - 110, 0), width - 220)}}>
          <b>{h.month_label}</b>
          <span><em>Taux</em>{num(h.recovery_rate).toLocaleString('fr-FR')} %</span>
          <span><em>Régularisé</em>{formatMoney(String(h.regularized_total), currency)}</span>
          <span><em>Attendu</em>{formatMoney(String(h.expected), currency)}</span>
          <span><em>Reste</em>{formatMoney(String(h.remaining), currency)}</span>
          {h.debtors != null && <span><em>Élèves concernés</em>{h.debtors}</span>}
        </div>}
      </div>}
    {onOpen && <div className="rc-foot"><button type="button" className="rc-link" onClick={onOpen}>Ouvrir le recouvrement détaillé ›</button></div>}
  </div>;
}
