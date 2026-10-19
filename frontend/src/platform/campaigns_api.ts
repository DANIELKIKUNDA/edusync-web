/* API of « Notifications système » (lot 2026-10): internal in-app notifications only (no SMS, no WhatsApp, no e-mail). */
import {UserFacingError, friendlyHttpMessage} from './errors';

const API = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const auth = (token: string) => ({Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'});

export type TargetType = 'ALL_ACTIVE_SCHOOLS' | 'SCHOOLS' | 'SCHOOL_ROLE' | 'SCHOOL_USER' | 'PLATFORM_ALL' | 'PLATFORM_ROLE' | 'PLATFORM_USER';
export type Target = {type: TargetType; school_ids: string[]; role_code: string | null; user_id: string | null};
export type Severity = 'INFO' | 'WARNING' | 'CRITICAL';
export type Audience = {deliveries: number; people: number; schools: number; message: string | null; mass?: boolean};
export type CampaignRow = {id: string; title: string; severity: Severity; target_scope: string; target_json: Target | null; link_path: string | null;
  expires_at: string | null; created_at: string; recipient_count: number; people_count: number | null; author: string | null;
  target_school_code: string | null; status: 'ACTIVE' | 'EXPIRED'; read_count: number};
export type CampaignPage = {items: CampaignRow[]; total: number; has_more: boolean; next_cursor: string | null; limit: number};
export type CampaignDetail = CampaignRow & {body: string; audit_event_id: string | null;
  target: {type: string; schools?: {id: string; code: string; name: string}[]; schools_total?: number; role?: string; user?: string | null}};
export type HistoryFilters = {q: string; severity: '' | Severity; target: '' | TargetType; status: '' | 'ACTIVE' | 'EXPIRED'; author: string; from: string; to: string};

export class AudienceChangedError extends Error {
  constructor(public audience: Audience, message: string) { super(message); }
}

async function fail(r: Response, fallback: string): Promise<never> {
  let detail: unknown = null;
  try { detail = (await r.json())?.detail; } catch { /* non JSON */ }
  if (r.status === 409 && detail && typeof detail === 'object' && (detail as {code?: string}).code === 'AUDIENCE_CHANGED') {
    const d = detail as Audience & {message: string};
    throw new AudienceChangedError({deliveries: d.deliveries, people: d.people, schools: d.schools, message: null}, d.message);
  }
  const text = typeof detail === 'string' && detail.length < 300 ? detail : '';
  throw new UserFacingError(text || friendlyHttpMessage(r.status) || fallback, String(r.status));
}

export async function fetchHistory(token: string, f: HistoryFilters, cursor: string | null, limit: number, signal?: AbortSignal): Promise<CampaignPage> {
  const p = new URLSearchParams();
  if (f.q.trim()) p.set('q', f.q.trim()); if (f.severity) p.set('severity', f.severity); if (f.target) p.set('target', f.target);
  if (f.status) p.set('status', f.status); if (f.author) p.set('author', f.author);
  if (f.from) p.set('date_from', new Date(`${f.from}T00:00:00`).toISOString());
  if (f.to) { const d = new Date(`${f.to}T00:00:00`); d.setDate(d.getDate() + 1); p.set('date_to', d.toISOString()); }
  p.set('limit', String(limit)); if (cursor) p.set('cursor', cursor);
  const r = await fetch(`${API}/platform/notification-campaigns?${p}`, {headers: auth(token), signal});
  if (!r.ok) return fail(r, 'Historique indisponible.');
  return r.json();
}
export async function fetchAuthors(token: string): Promise<{id: string; full_name: string; sent: number}[]> {
  const r = await fetch(`${API}/platform/notification-campaigns/authors`, {headers: auth(token)});
  if (!r.ok) return [];
  return (await r.json()).items;
}
export async function fetchCampaign(token: string, id: string, signal?: AbortSignal): Promise<CampaignDetail> {
  const r = await fetch(`${API}/platform/notification-campaigns/${id}`, {headers: auth(token), signal});
  if (!r.ok) return fail(r, 'Notification introuvable.');
  return r.json();
}
export async function previewAudience(token: string, target: Target, signal?: AbortSignal): Promise<Audience> {
  const r = await fetch(`${API}/platform/notification-campaigns/preview`, {method: 'POST', headers: auth(token), body: JSON.stringify({target}), signal});
  if (!r.ok) return fail(r, 'Impossible d’estimer les destinataires.');
  return r.json();
}
export async function sendCampaign(token: string, key: string, input: {title: string; body: string; severity: Severity; target: Target; link_path: string | null;
  expires_at: string | null; confirmed_recipients: number | null}): Promise<{id: string; recipient_count: number; people_count: number}> {
  const r = await fetch(`${API}/platform/notification-campaigns`, {method: 'POST', headers: {...auth(token), 'Idempotency-Key': key}, body: JSON.stringify(input)});
  if (!r.ok) return fail(r, 'Envoi impossible.');
  return r.json();
}

export const TARGETS: {value: TargetType; label: string; hint: string; team?: boolean}[] = [
  {value: 'ALL_ACTIVE_SCHOOLS', label: 'Toutes les écoles actives', hint: 'Chaque membre actif de chaque école active.'},
  {value: 'SCHOOLS', label: 'Écoles choisies', hint: 'Les membres actifs des écoles sélectionnées.'},
  {value: 'SCHOOL_ROLE', label: 'Un rôle école', hint: 'Les membres qui détiennent ce rôle : dans toutes les écoles actives, ou seulement dans les écoles choisies.'},
  {value: 'SCHOOL_USER', label: 'Un membre d’une école', hint: 'Choisissez l’école, puis la personne dans cette école.'},
  {value: 'PLATFORM_ALL', label: 'Toute l’équipe plateforme', hint: 'Les membres actifs de l’équipe (comptes suspendus exclus).', team: true},
  {value: 'PLATFORM_ROLE', label: 'Un rôle plateforme', hint: 'Les membres actifs qui détiennent ce rôle plateforme.', team: true},
  {value: 'PLATFORM_USER', label: 'Un membre de l’équipe', hint: 'Une personne précise de l’équipe plateforme.', team: true},
];
export const TARGET_LABEL: Record<string, string> = Object.fromEntries(TARGETS.map(t => [t.value, t.label]).concat([['SCHOOL', 'Une école']]));
export const SEVERITY: Record<Severity, {label: string; icon: string}> = {INFO: {label: 'Information', icon: 'info'}, WARNING: {label: 'Avertissement', icon: 'alert'},
  CRITICAL: {label: 'Critique', icon: 'alert'}};
