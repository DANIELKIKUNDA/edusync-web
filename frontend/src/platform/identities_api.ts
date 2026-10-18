/* API of the platform directory « Utilisateurs & accès » (lot 2026-10). Read only; server messages are shown as written. */
import {UserFacingError, friendlyHttpMessage} from './errors';

const API = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const auth = (token: string) => ({Authorization: `Bearer ${token}`});

export type IdentityScope = 'PLATFORM' | 'SCHOOL' | 'BOTH' | 'NONE';
export type IdentityStatus = 'ACTIVE' | 'PENDING' | 'SUSPENDED' | 'DISABLED';
export type IdentityRow = {id: string; full_name: string; email: string; active: boolean; scope: IdentityScope; status: IdentityStatus;
  platform_roles: string[]; school_roles: string[]; schools_count: number; first_school_id: string | null; first_school_name: string | null;
  first_school_code: string | null; last_activity_at: string | null};
export type IdentitiesPage = {items: IdentityRow[]; total: number; has_more: boolean; next_cursor: string | null; limit: number};
export type IdentityFilters = {q: string; scope: '' | 'PLATFORM' | 'SCHOOL'; status: '' | IdentityStatus; schoolId: string; schoolName: string;
  role: string; activeOnly: boolean};
export type FilterRole = {code: string; label: string; level: 'PLATFORM' | 'SCHOOL'};
export type IdentityDetail = {id: string; full_name: string; email: string; active: boolean; created_at: string; must_change_password: boolean;
  status: IdentityStatus; last_activity_at: string | null; scope: IdentityScope;
  platform_roles: {code: string; label: string; since: string | null}[];
  memberships: {school_id: string; code: string; name: string; school_status: 'ACTIVE' | 'SUSPENDED' | 'DISABLED'; active: boolean; since: string;
    roles: string[]; last_activity_at: string | null}[];
  security: {mfa_enrolled: boolean; open_sessions: number} | null; can_manage_collaborators: boolean};

async function fail(r: Response, fallback: string): Promise<never> {
  let detail = '';
  try { const b = await r.json(); if (typeof b?.detail === 'string' && b.detail.length < 300) detail = b.detail; } catch { /* non JSON */ }
  throw new UserFacingError(detail || friendlyHttpMessage(r.status) || fallback);
}

export async function fetchIdentities(token: string, f: IdentityFilters, cursor: string | null, limit: number, signal?: AbortSignal): Promise<IdentitiesPage> {
  const p = new URLSearchParams();
  if (f.q.trim()) p.set('q', f.q.trim());
  if (f.scope) p.set('scope', f.scope);
  if (f.status) p.set('status', f.status);
  if (f.schoolId) p.set('school_id', f.schoolId);
  if (f.role) p.set('role', f.role);
  if (f.activeOnly) p.set('active_only', 'true');
  p.set('limit', String(limit));
  if (cursor) p.set('cursor', cursor);
  const r = await fetch(`${API}/platform/identities?${p}`, {headers: auth(token), signal});
  if (!r.ok) return fail(r, 'Impossible de charger les utilisateurs.');
  return r.json();
}

export async function fetchIdentityFilters(token: string): Promise<{roles: FilterRole[]}> {
  const r = await fetch(`${API}/platform/identities/filters`, {headers: auth(token)});
  if (!r.ok) return {roles: []};
  return r.json();
}

export async function fetchIdentity(token: string, id: string, signal?: AbortSignal): Promise<IdentityDetail> {
  const r = await fetch(`${API}/platform/identities/${id}`, {headers: auth(token), signal});
  if (!r.ok) return fail(r, 'Détail du compte indisponible.');
  return r.json();
}

export const SCOPE_LABEL: Record<IdentityScope, string> = {PLATFORM: 'Plateforme', SCHOOL: 'École', BOTH: 'Plateforme + école', NONE: 'Aucun accès actif'};
export const IDENTITY_STATUS_LABEL: Record<IdentityStatus, string> = {ACTIVE: 'Actif', PENDING: 'Activation en attente', SUSPENDED: 'Accès plateforme suspendu', DISABLED: 'Désactivé'};
