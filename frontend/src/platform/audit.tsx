import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {auditEvent, auditExport, auditLog, type AuditFilters, type AuditRow} from '../api';
import {Modal} from './account';
import {friendlyError} from './errors';
import {auditActionLabel, resultLabel} from './labels';
import {NavGlyph} from './nav_icons';
import './audit.css';

const EMPTY: AuditFilters = {q: '', action: '', scope: '', school: '', actor: '', result: '', date_from: '', date_to: ''};
const SOURCE: Record<string, string> = {WEB: 'Application web', OFFLINE: 'Hors ligne', SYNC: 'Synchronisation', SYSTEM: 'Système', IMPORT: 'Import', MIGRATION: 'Migration'};

function fmt(iso: string) { return new Date(iso).toLocaleString('fr-FR', {dateStyle: 'medium', timeStyle: 'medium'}); }

function Changes({before, after}: {before: any; after: any}) {
  const keys = Array.from(new Set([...Object.keys(before || {}), ...Object.keys(after || {})])).sort();
  if (!keys.length) return <p className="es-hint">Aucune donnée avant/après pour cet événement.</p>;
  const show = (v: any) => v === undefined ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v);
  return <table className="au-diff"><caption className="sr-only">Données avant et après</caption><thead><tr><th scope="col">Champ</th><th scope="col">Avant</th><th scope="col">Après</th></tr></thead>
    <tbody>{keys.map(k => { const a = show(before?.[k]), b = show(after?.[k]); return <tr key={k} className={a !== b ? 'au-changed' : ''}><th scope="row">{k}</th><td>{a}</td><td>{b}</td></tr>; })}</tbody></table>;
}

export function AuditPanel({token, canExport}: {token: string; canExport: boolean}) {
  const [f, setF] = useState<AuditFilters>(EMPTY);
  const [applied, setApplied] = useState<AuditFilters>(EMPTY);
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [actions, setActions] = useState<string[]>([]);
  const [cursor, setCursor] = useState<{at: string; id: string} | null>(null);
  const [error, setError] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [exporting, setExporting] = useState(false);
  async function load(filters = applied, more = false) {
    try { setError(''); const r = await auditLog(token, filters, more ? cursor : null); setRows(prev => more && prev ? [...prev, ...r.items] : r.items); setCursor(r.next_cursor); setActions(r.actions); }
    catch (e) { setError(friendlyError(e)); }
  }
  useEffect(() => { void load(EMPTY); }, [token]);
  useEffect(() => { if (!open) { setDetail(null); return; } auditEvent(token, open).then(setDetail).catch(e => setError(friendlyError(e))); }, [open]);
  const set = (k: keyof AuditFilters) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({...f, [k]: e.target.value});
  async function exportCsv() {
    try { setExporting(true); const blob = await auditExport(token, applied); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `audit-plateforme-${new Date().toISOString().slice(0, 10)}.csv`; a.click(); URL.revokeObjectURL(url); toast.success('Export prêt (l’export est lui-même tracé dans l’audit)'); }
    catch (e) { setError(friendlyError(e)); } finally { setExporting(false); }
  }
  const active = Object.values(applied).filter(Boolean).length;
  return <div className="au">
    <form className="au-filters" role="search" onSubmit={e => { e.preventDefault(); setApplied(f); void load(f); }}>
      <label className="au-q"><NavGlyph g="search" size={16}/><input aria-label="Rechercher dans l’audit" value={f.q} onChange={set('q')} placeholder="Rechercher une action, un objet, un motif"/></label>
      <label><span>Action</span><select value={f.action} onChange={set('action')}><option value="">Toutes</option>{actions.map(a => <option key={a} value={a}>{auditActionLabel(a)}</option>)}</select></label>
      <label><span>Portée</span><select value={f.scope} onChange={set('scope')}><option value="">Tout</option><option value="PLATFORM">Plateforme</option><option value="SCHOOL">Écoles</option></select></label>
      <label><span>École (code)</span><input value={f.school} onChange={set('school')} placeholder="Ex. : EXCELLENCIA"/></label>
      <label><span>Auteur</span><input value={f.actor} onChange={set('actor')} placeholder="Nom ou e-mail"/></label>
      <label><span>Résultat</span><select value={f.result} onChange={set('result')}><option value="">Tous</option><option value="SUCCESS">Réussi</option><option value="REJECTED">Refusé</option><option value="FAILED">Échoué</option></select></label>
      <label><span>Du</span><input type="date" value={f.date_from} onChange={set('date_from')}/></label>
      <label><span>Au</span><input type="date" value={f.date_to} onChange={set('date_to')}/></label>
      <div className="au-actions">
        <button className="es-btn es-btn-primary">Filtrer</button>
        {active > 0 && <button type="button" className="es-btn es-btn-ghost" onClick={() => { setF(EMPTY); setApplied(EMPTY); void load(EMPTY); }}>Effacer ({active})</button>}
        {canExport && <button type="button" className="es-btn" disabled={exporting || !applied.date_from} title={!applied.date_from ? 'Choisissez une date de début (92 jours maximum)' : undefined} onClick={() => void exportCsv()}><NavGlyph g="download" size={16}/>{exporting ? 'Export…' : 'Exporter (CSV)'}</button>}
      </div>
    </form>
    {canExport && !applied.date_from && <p className="es-hint">Pour exporter, filtrez d’abord par une date de début (92 jours maximum, 10 000 lignes).</p>}
    {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
    {rows === null ? <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div> : rows.length === 0 ? <div className="es-empty">Aucun événement ne correspond.</div> :
      <ul className="au-list">{rows.map(r => <li key={r.id}><button onClick={() => setOpen(r.id)} aria-label={`Détail : ${auditActionLabel(r.action)} du ${fmt(r.occurred_at)}`}>
        <span className="au-when">{fmt(r.occurred_at)}</span>
        <span className="au-what"><b>{auditActionLabel(r.action)}</b><small>{r.actor || 'Système'} · {r.school_code ? `${r.school_code}` : 'Plateforme'}{r.reason ? ` · ${r.reason}` : ''}</small></span>
        <em className={`au-res au-${r.result.toLowerCase()}`}>{resultLabel(r.result)}</em>
        <NavGlyph g="chevronRight" size={16}/>
      </button></li>)}</ul>}
    {cursor && <button className="es-btn es-btn-ghost au-more" onClick={() => void load(applied, true)}>Charger plus</button>}
    {open && <Modal title={detail ? auditActionLabel(detail.action) : 'Événement d’audit'} subtitle={detail ? fmt(detail.occurred_at) : undefined} onClose={() => setOpen(null)} wide>
      {!detail ? <div className="es-skeleton" aria-busy="true"><i/><i/></div> : <div className="au-detail">
        <dl>
          <dt>Auteur</dt><dd>{detail.actor || 'Système'}{detail.actor_email ? ` (${detail.actor_email})` : ''}</dd>
          <dt>Portée</dt><dd>{detail.school_name ? `${detail.school_name} · ${detail.school_code}` : 'Plateforme'}</dd>
          <dt>Objet</dt><dd>{detail.entity_type}{detail.entity_id ? ` · ${detail.entity_id}` : ''}</dd>
          <dt>Résultat</dt><dd>{resultLabel(detail.result)} · {SOURCE[detail.source] || detail.source}</dd>
          {detail.reason && <><dt>Motif</dt><dd>{detail.reason}</dd></>}
          {detail.correlation_id && <><dt>Corrélation</dt><dd><code>{detail.correlation_id}</code></dd></>}
          <dt>Code technique</dt><dd><code>{detail.action}</code></dd>
        </dl>
        <h3>Avant / après</h3><Changes before={detail.old_json} after={detail.new_json}/>
        {detail.related?.length > 0 && <><h3>Événements liés (même corrélation)</h3><ul className="au-related">{detail.related.map((x: any) => <li key={x.id}><button className="es-btn es-btn-ghost" onClick={() => setOpen(x.id)}>{auditActionLabel(x.action)} · {fmt(x.occurred_at)}</button></li>)}</ul></>}
        <p className="es-hint"><NavGlyph g="lock" size={12}/> Le journal d’audit est en ajout seul : aucun événement ne peut être modifié ni supprimé.</p>
      </div>}
    </Modal>}
  </div>;
}
