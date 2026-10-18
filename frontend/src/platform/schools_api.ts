/* API of the platform Schools module (lot 2026-10). Server messages (validation, conflicts) are shown as written. */
import {UserFacingError, friendlyHttpMessage} from './errors';

const API = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const auth = (token: string) => ({Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'});

export type SchoolStatus = 'ACTIVE' | 'SUSPENDED' | 'DISABLED';
export type ConfigState = 'COMPLETE' | 'INCOMPLETE' | 'ADMIN_PENDING' | 'ADMIN_MISSING';
export type SchoolSort = 'name' | 'created' | 'status';
export type SchoolRow = {id: string; code: string; name: string; status: SchoolStatus; province: string | null; city: string | null;
  contact_name: string | null; contact_phone: string | null; contact_phone_display: string | null; created_at: string; users_count: number;
  has_admin: boolean; has_active_admin: boolean; config_state: ConfigState};
export type SchoolsPage = {items: SchoolRow[]; total: number; has_more: boolean; next_cursor: string | null; limit: number; sort: SchoolSort};
export type SchoolFilters = {q: string; status: '' | SchoolStatus; config: '' | ConfigState; sort: SchoolSort; needsAdmin?: boolean};
export type SchoolIdentity = {name: string; province: string; city: string; address: string; email: string; phone: string;
  contact_name: string; contact_function: string; contact_phone: string; contact_email: string};
export type AdminInfo = {membership_id: string; user_id: string; full_name: string; email: string; state: 'ACTIVE' | 'PENDING' | 'DISABLED';
  must_change_password: boolean; invitation_pending: boolean; last_seen_at: string | null; membership_active: boolean};
export type SchoolSheet = {
  school: SchoolIdentity & {id: string; code: string; status: SchoolStatus; created_at: string; updated_at: string; version: number;
    phone_display: string | null; contact_phone_display: string | null};
  admins: AdminInfo[]; readiness: Record<string, boolean>; ready_count: number; total_gates: number; config_state: ConfigState;
  counters: {users_active: number; users_disabled: number; admins_active: number; invitations_pending: number};
  health: {access_ok: boolean; status: SchoolStatus; admin_active: boolean; configuration: ConfigState; last_activity_at: string | null; open_conflicts: number};
  history: {id: string; occurred_at: string; action: string; result: string; reason: string | null; actor: string | null}[] | null;
  email_invitations_available: boolean;
};

async function fail(r: Response, fallback: string): Promise<never> {
  let detail = '';
  try { const b = await r.json(); if (typeof b?.detail === 'string' && b.detail.length < 300) detail = b.detail; } catch { /* non JSON */ }
  throw new UserFacingError(detail || friendlyHttpMessage(r.status) || fallback);
}

function qs(f: SchoolFilters, cursor: string | null, limit: number) {
  const p = new URLSearchParams();
  if (f.q.trim()) p.set('q', f.q.trim());
  if (f.status) p.set('status', f.status);
  if (f.config) p.set('config', f.config);
  if (f.needsAdmin) p.set('needs_admin', 'true');
  p.set('sort', f.sort); p.set('limit', String(limit));
  if (cursor) p.set('cursor', cursor);
  return p.toString();
}

export async function fetchSchools(token: string, f: SchoolFilters, cursor: string | null, limit: number, signal?: AbortSignal): Promise<SchoolsPage> {
  const r = await fetch(`${API}/platform/schools-page?${qs(f, cursor, limit)}`, {headers: auth(token), signal});
  if (!r.ok) return fail(r, 'Impossible de charger les écoles.');
  return r.json();
}

export async function fetchSchoolSheet(token: string, id: string, signal?: AbortSignal): Promise<SchoolSheet> {
  const r = await fetch(`${API}/platform/schools/${id}/detail`, {headers: auth(token), signal});
  if (!r.ok) return fail(r, 'Fiche école indisponible.');
  return r.json();
}

export async function fetchCitySuggestions(token: string, province: string): Promise<{provinces: string[]; cities: string[]}> {
  const r = await fetch(`${API}/platform/schools/city-suggestions?province=${encodeURIComponent(province)}`, {headers: auth(token)});
  if (!r.ok) return {provinces: [], cities: []};
  return r.json();
}

const blankToNull = (v: SchoolIdentity) => Object.fromEntries(Object.entries(v).map(([k, x]) => [k, (x || '').trim() || null]));

export async function createSchool(token: string, key: string, v: SchoolIdentity): Promise<{id: string; code: string; name: string}> {
  const r = await fetch(`${API}/platform/schools`, {method: 'POST', headers: {...auth(token), 'Idempotency-Key': key}, body: JSON.stringify(blankToNull(v))});
  if (!r.ok) return fail(r, 'Création impossible.');
  return r.json();
}

export async function updateSchool(token: string, id: string, version: number, v: SchoolIdentity): Promise<{version: number; changed: string[]}> {
  const r = await fetch(`${API}/platform/schools/${id}`, {method: 'PATCH', headers: auth(token), body: JSON.stringify({...blankToNull(v), version})});
  if (!r.ok) return fail(r, 'Modification impossible.');
  return r.json();
}

export async function bootstrapAdmin(token: string, schoolId: string, key: string, input: {full_name: string; email: string; delivery: 'TEMPORARY' | 'INVITATION'}):
  Promise<{membership_id: string; account: string; temporary_password: string | null; invitation_sent?: boolean}> {
  const r = await fetch(`${API}/platform/schools/${schoolId}/bootstrap-admin`, {method: 'POST', headers: {...auth(token), 'Idempotency-Key': key}, body: JSON.stringify(input)});
  if (!r.ok) return fail(r, 'Administrateur non créé.');
  return r.json();
}

export async function resetAdminAccess(token: string, schoolId: string, membershipId: string, input: {reason: string; delivery: 'TEMPORARY' | 'INVITATION'}):
  Promise<{temporary_password: string | null; sessions_closed: number; invitation_sent: boolean}> {
  const r = await fetch(`${API}/platform/schools/${schoolId}/admins/${membershipId}/reset-access`, {method: 'POST', headers: auth(token), body: JSON.stringify(input)});
  if (!r.ok) return fail(r, 'Réinitialisation impossible.');
  return r.json();
}

export async function setSchoolStatus(token: string, schoolId: string, action: 'suspend' | 'reactivate', reason?: string): Promise<void> {
  const r = await fetch(`${API}/platform/schools/${schoolId}/${action}`, {method: 'POST', headers: {...auth(token), 'Idempotency-Key': crypto.randomUUID()},
    body: action === 'suspend' ? JSON.stringify({reason}) : undefined});
  if (!r.ok) return fail(r, action === 'suspend' ? 'Suspension impossible.' : 'Réactivation impossible.');
}

export async function setMembershipActive(token: string, membershipId: string, active: boolean, reason: string): Promise<void> {
  const r = await fetch(`${API}/platform/memberships/${membershipId}/${active ? 'activate' : 'deactivate'}`, {method: 'POST', headers: {...auth(token), 'Idempotency-Key': crypto.randomUUID()},
    body: JSON.stringify({reason})});
  if (!r.ok) return fail(r, 'Modification d’accès impossible.');
}

export async function downloadSchoolsCsv(token: string, f: SchoolFilters): Promise<void> {
  const p = new URLSearchParams(qs(f, null, 25)); p.delete('limit');
  const r = await fetch(`${API}/platform/schools/export.csv?${p.toString()}`, {headers: auth(token)});
  if (!r.ok) return fail(r, 'Export impossible.');
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement('a'); a.href = url; a.download = 'ecoles-edusync.csv'; a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1500);
}

export const RDC_PROVINCES = ['Bas-Uele', 'Équateur', 'Haut-Katanga', 'Haut-Lomami', 'Haut-Uele', 'Ituri', 'Kasaï', 'Kasaï-Central', 'Kasaï-Oriental',
  'Kinshasa', 'Kongo-Central', 'Kwango', 'Kwilu', 'Lomami', 'Lualaba', 'Mai-Ndombe', 'Maniema', 'Mongala', 'Nord-Kivu', 'Nord-Ubangi', 'Sankuru',
  'Sud-Kivu', 'Sud-Ubangi', 'Tanganyika', 'Tshopo', 'Tshuapa'];
export const STATUS_LABEL: Record<SchoolStatus, string> = {ACTIVE: 'Actif', SUSPENDED: 'Suspendu', DISABLED: 'Désactivé'};
export const CONFIG_LABEL: Record<ConfigState, string> = {COMPLETE: 'Configuration complète', INCOMPLETE: 'À finaliser',
  ADMIN_PENDING: 'Activation en attente', ADMIN_MISSING: 'Administrateur à créer'};
