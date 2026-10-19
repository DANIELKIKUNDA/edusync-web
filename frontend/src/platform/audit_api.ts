/* API of the « Journal d'audit » (lot 2026-10): read only (the audit trail is append-only on the server). */
import {UserFacingError, friendlyHttpMessage} from './errors';

const API = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const auth = (token: string) => ({Authorization: `Bearer ${token}`});

export type AuditCategory = '' | 'FAILURES' | 'SECURITY' | 'PLATFORM' | 'SCHOOLS';
export type AuditQuery = {q: string; category: AuditCategory; action: string; school: string; schoolName: string; actor: string;
  result: '' | 'SUCCESS' | 'REJECTED' | 'FAILED'; from: string; to: string; sort: 'newest' | 'oldest'};
export type AuditItem = {id: string; occurred_at: string; school_id: string | null; school_code: string | null; school_name: string | null;
  actor_user_id: string | null; actor: string | null; action: string; entity_type: string; entity_id: string | null; source: string;
  result: string; reason: string | null; correlation_id: string | null; has_changes: boolean};
export type AuditPage = {items: AuditItem[]; has_more: boolean; actions: string[]; next_cursor: {at: string; id: string} | null};
export type AuditDetail = AuditItem & {actor_email: string | null; membership_id: string | null; device_id: string | null; causation_id: string | null;
  old_json: Record<string, unknown> | null; new_json: Record<string, unknown> | null;
  related: {id: string; occurred_at: string; action: string; result: string}[];
  context: {school_exists: boolean; actor_exists: boolean; actor_is_member: boolean; entity_is_user: boolean; entity_is_school: boolean; entity_is_campaign: boolean}};

async function fail(r: Response, fallback: string): Promise<never> {
  let detail = '';
  try { const b = await r.json(); if (typeof b?.detail === 'string' && b.detail.length < 300) detail = b.detail; } catch { /* non JSON */ }
  throw new UserFacingError(detail || friendlyHttpMessage(r.status) || fallback, String(r.status));
}

function params(f: AuditQuery) {
  const p = new URLSearchParams();
  if (f.q.trim()) p.set('q', f.q.trim()); if (f.category) p.set('category', f.category); if (f.action) p.set('action', f.action);
  if (f.school) p.set('school', f.school); if (f.actor.trim()) p.set('actor', f.actor.trim()); if (f.result) p.set('result', f.result);
  if (f.from) p.set('date_from', f.from); if (f.to) p.set('date_to', f.to);
  return p;
}

export async function fetchAudit(token: string, f: AuditQuery, cursor: {at: string; id: string} | null, limit: number, signal?: AbortSignal): Promise<AuditPage> {
  const p = params(f); p.set('sort', f.sort); p.set('limit', String(limit));
  if (cursor) { p.set('cursor_at', cursor.at); p.set('cursor_id', cursor.id); }
  const r = await fetch(`${API}/platform/audit-log?${p}`, {headers: auth(token), signal});
  if (!r.ok) return fail(r, 'Impossible de charger le journal.');
  return r.json();
}
export async function fetchAuditEvent(token: string, id: string, signal?: AbortSignal): Promise<AuditDetail> {
  const r = await fetch(`${API}/platform/audit-log/${id}`, {headers: auth(token), signal});
  if (!r.ok) return fail(r, 'Événement introuvable.');
  return r.json();
}
export async function downloadAuditCsv(token: string, f: AuditQuery): Promise<void> {
  const r = await fetch(`${API}/platform/audit-log/export.csv?${params(f)}`, {headers: auth(token)});
  if (!r.ok) return fail(r, 'Export impossible.');
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement('a'); a.href = url; a.download = `audit-plateforme-${new Date().toISOString().slice(0, 10)}.csv`; a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1500);
}
