/* API of « Équipe plateforme » (lot 2026-10). Every mutation carries an Idempotency-Key chosen once per user action (a
   double click or a network retry replays the same operation, never a second one). Server messages are shown as written. */
import {UserFacingError, friendlyHttpMessage} from './errors';

const API = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const T = `${API}/platform/team`;
const auth = (token: string) => ({Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'});

export type MemberStatus = 'ACTIVE' | 'PENDING' | 'SUSPENDED' | 'DISABLED';
export type InvitationState = 'PENDING' | 'EXPIRED' | 'ACCEPTED' | null;
export type MemberRow = {id: string; email: string; full_name: string; account_active: boolean; platform_status: 'ACTIVE' | 'SUSPENDED'; status: MemberStatus;
  roles: string[]; role_labels: string[]; grants_count: number; last_activity: string | null; mfa_enrolled: boolean; invitation_state: InvitationState; is_me: boolean};
export type MembersPage = {items: MemberRow[]; total: number; has_more: boolean; next_cursor: string | null; limit: number; active_managers: number;
  email_invitations_available: boolean};
export type MemberFilters = {q: string; status: '' | 'ACTIVE' | 'PENDING' | 'SUSPENDED'; role: string};
export type Candidate = {id: string; full_name: string; email: string; active: boolean; schools_count: number; first_school: string | null};
export type Origin = {kind: 'ROLE'; code: string; label: string} | {kind: 'GRANT'; granted_by: string | null; granted_at: string; valid_until: string | null; reason: string};
export type EffectiveCapability = {code: string; label: string; group_name: string; risk: string | null; origins: Origin[]};
export type MemberDetail = {
  id: string; email: string; full_name: string; account_active: boolean; created_at: string; platform_status: 'ACTIVE' | 'SUSPENDED';
  status_reason: string | null; status_changed_at: string | null; must_change_password: boolean; invitation_state: InvitationState;
  last_activity: string | null; school_memberships: number; is_me: boolean; is_member: boolean;
  roles: {code: string; label: string; kind: string; status: string; active: boolean; created_at: string; reason: string | null}[];
  effective_permissions: string[]; capabilities: EffectiveCapability[]; inherited_count: number; supplementary_count: number; effective_count: number;
  grants: {capability_code: string; valid_from: string; valid_until: string | null; reason: string; created_at: string; granted_by: string | null}[];
  non_delegable: {code: string; label: string; group_name: string; reason: string}[];
  rights_changed: {occurred_at: string; action: string; actor: string | null} | null;
  sessions: {id: string; label: string | null; created_at: string; last_seen_at: string | null}[];
  audit: {occurred_at: string; action: string; reason: string | null; actor: string | null}[];
  mfa: {enrolled: boolean; confirmed_at: string | null; recovery_codes_remaining: number};
};

async function fail(r: Response, fallback: string): Promise<never> {
  let detail = '';
  try { const b = await r.json(); if (typeof b?.detail === 'string' && b.detail.length < 300) detail = b.detail; } catch { /* non JSON */ }
  throw new UserFacingError(detail || friendlyHttpMessage(r.status) || fallback, String(r.status));
}
async function get<R>(token: string, path: string, fallback: string, signal?: AbortSignal): Promise<R> {
  const r = await fetch(`${T}${path}`, {headers: auth(token), signal});
  if (!r.ok) return fail(r, fallback);
  return r.json();
}
async function post<R>(token: string, path: string, key: string, body: unknown, fallback: string): Promise<R> {
  const r = await fetch(`${T}${path}`, {method: 'POST', headers: {...auth(token), 'Idempotency-Key': key}, body: JSON.stringify(body)});
  if (!r.ok) return fail(r, fallback);
  return r.json();
}

export function fetchMembers(token: string, f: MemberFilters, cursor: string | null, limit: number, signal?: AbortSignal) {
  const p = new URLSearchParams();
  if (f.q.trim()) p.set('q', f.q.trim()); if (f.status) p.set('status', f.status); if (f.role) p.set('role', f.role);
  p.set('limit', String(limit)); if (cursor) p.set('cursor', cursor);
  return get<MembersPage>(token, `/users?${p}`, 'Équipe indisponible.', signal);
}
export const fetchMember = (token: string, id: string, signal?: AbortSignal) => get<MemberDetail>(token, `/users/${id}`, 'Fiche indisponible.', signal);
export const fetchCandidates = (token: string, q: string, signal?: AbortSignal) =>
  get<{items: Candidate[]}>(token, `/candidates?q=${encodeURIComponent(q)}`, 'Recherche impossible.', signal);
export const createMember = (token: string, key: string, input: {email: string; full_name: string; role_codes: string[]; reason: string; delivery: 'INVITATION' | 'TEMPORARY'}) =>
  post<{id: string; temporary_password: string | null; delivery: string}>(token, '/users', key, input, 'Création impossible.');
export const addExisting = (token: string, key: string, id: string, input: {role_codes: string[]; reason: string}) =>
  post<{id: string; school_memberships_kept: number}>(token, `/users/${id}/platform-access`, key, input, 'Ajout impossible.');
export const removeAccess = (token: string, key: string, id: string, reason: string) =>
  post<{roles_ended: string[]; capabilities_ended: string[]; school_memberships_kept: number}>(token, `/users/${id}/platform-access/revoke`, key, {reason}, 'Retrait impossible.');
export const resendInvitation = (token: string, key: string, id: string, reason: string) =>
  post(token, `/users/${id}/invitation/resend`, key, {reason}, 'Renvoi impossible.');
export const grantCapability = (token: string, key: string, id: string, input: {capability_code: string; reason: string; valid_until: string | null}) =>
  post<{effective_before: number; effective_after: number; added: string[]}>(token, `/users/${id}/capabilities`, key, input, 'Attribution impossible.');
export const revokeCapability = (token: string, key: string, id: string, code: string, reason: string) =>
  post<{effective_before: number; effective_after: number; removed: string[]}>(token, `/users/${id}/capabilities/${encodeURIComponent(code)}/revoke`, key, {reason}, 'Retrait impossible.');
export const assignRole = (token: string, key: string, id: string, role_code: string, reason: string) =>
  post<{effective_before: number; effective_after: number; added: string[]}>(token, `/users/${id}/roles`, key, {role_code, reason}, 'Attribution impossible.');
export const revokeRole = (token: string, key: string, id: string, code: string, reason: string) =>
  post(token, `/users/${id}/roles/${encodeURIComponent(code)}/revoke`, key, {reason}, 'Retrait impossible.');
export const setMemberStatus = (token: string, key: string, id: string, action: 'suspend' | 'reactivate', reason: string) =>
  post(token, `/users/${id}/${action}`, key, {reason}, 'Changement de statut impossible.');
export async function updateRole(token: string, key: string, id: string, input: {label: string; description: string; capabilities: string[]; version: number; reason?: string}) {
  const r = await fetch(`${T}/roles/${id}`, {method: 'PUT', headers: {...auth(token), 'Idempotency-Key': key}, body: JSON.stringify(input)});
  if (!r.ok) return fail(r, 'Modification impossible.');
  return r.json();
}
export const createRole = (token: string, key: string, input: {code: string; label: string; description: string; capabilities: string[]}) =>
  post<{id: string}>(token, '/roles', key, input, 'Création du rôle impossible.');
export const cloneRole = (token: string, key: string, id: string, input: {code: string; label: string}) =>
  post<{id: string}>(token, `/roles/${id}/clone`, key, input, 'Clonage impossible.');
export const roleStatus = (token: string, key: string, id: string, action: 'activate' | 'archive', reason: string) =>
  post(token, `/roles/${id}/${action}`, key, {reason}, 'Changement de statut impossible.');

export const resetPassword = (token: string, key: string, id: string, reason: string) =>
  post<{temporary_password: string | null; sessions_revoked: number}>(token, `/users/${id}/password-reset`, key, {reason}, 'Réinitialisation impossible.');
export const resetMfa = (token: string, key: string, id: string, reason: string, resetPasswordToo: boolean) =>
  post<{temporary_password: string | null}>(token, `/users/${id}/mfa-reset`, key, {reason, reset_password: resetPasswordToo}, 'Réinitialisation impossible.');
export const revokeSessions = (token: string, key: string, id: string, reason: string) =>
  post<{sessions_revoked: number}>(token, `/users/${id}/sessions/revoke-all`, key, {reason}, 'Déconnexion impossible.');

export const MEMBER_STATUS_LABEL: Record<MemberStatus, string> = {ACTIVE: 'Actif', PENDING: 'Activation en attente', SUSPENDED: 'Suspendu', DISABLED: 'Compte désactivé'};
export const RISK_LABEL: Record<string, string> = {LOW: 'Faible', MEDIUM: 'Modéré', HIGH: 'Élevé', CRITICAL: 'Critique'};
