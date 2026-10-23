// Messagerie plateforme — client du centre d'exploitation (lot 2026-10). Métadonnées seulement : jamais le corps d'un
// message d'école, jamais un secret fournisseur, destinataires masqués par le serveur.
import {UserFacingError, friendlyHttpMessage} from './errors';

const API = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const B = `${API}/platform/messaging`;

export type Check = {name: string; ok: boolean | null; detail: string};
export type ProviderState = 'NOT_CONFIGURED' | 'CONFIGURED' | 'OPERATIONAL' | 'DEGRADED' | 'UNAVAILABLE';
export type Channel = {
  key: 'push' | 'email' | 'sms'; channel: 'PUSH' | 'EMAIL' | 'SMS'; provider: string; provider_label: string; config_state: string; state: ProviderState;
  reasons: string[]; simulated: boolean;
  diagnostics?: {api: Check[]; worker: Check[]};
  provider_health?: null | {ok: boolean | null; fresh: boolean; error_code: string | null; send_authorized?: boolean | null};
  delivery_health?: {failed_15m_systemic: number; failed_15m_recipient: number; sent_15m: number; last_failure_code: string | null;
    last_failure_scope: 'DEVICE' | 'PROVIDER' | 'TRANSIENT' | null; last_failure_detail: string | null; last_failure_hint: string | null};
  health: null | {checked_at: string; fresh: boolean; ok: boolean | null; latency_ms: number | null; error_code: string | null; project_id: string | null;
    config: Record<string, string | number | boolean | null>};
  last_success_at: string | null; last_failure_at: string | null; last_failure_code: string | null; backlog: number; retrying: number; dead_7d: number;
  oldest_due_seconds: number | null; volumes_24h: Record<string, number>;
  last_test: null | {status: string; error_code: string | null; at: string; sent_at: string | null; provider_proof: boolean};
};
export type Status = {
  channels: Channel[]; health_checked_at: string | null; measured_at: string;
  queue: {due: number; processing: number; retrying: number; dead_7d: number; failed_15m: number; oldest_due: string | null; waiting_dispatch: number;
    receipts_waiting: number; worker_heartbeat: string | null; worker_age_seconds: number | null; worker_state: 'OK' | 'LATE' | 'DOWN'};
};
export type DeliveryRow = {id: string; channel: string; status: string; provider: string | null; destination: string; attempts: number; event: string;
  school_id: string | null; school_name: string | null; created_at: string; last_attempt_at: string | null; next_attempt_at: string | null; sent_at: string | null;
  delivered_at: string | null; failed_at: string | null; error_code: string | null};
export type DeliveryDetail = DeliveryRow & {kind: string; first_attempt_at: string | null; cancelled_at: string | null; error_detail: string | null;
  message_id: string; outbox_id: string | null; correlation_id: string | null; provider_message_id: string | null; segments_billed: number | null;
  wallet_state: string | null; delivered_proof: boolean; impact: string | null; can_retry: boolean; retry_policy: string | null;
  message: {private?: boolean; recipients: number; created_at: string; dispatched_at: string | null; deliveries_by_status: Record<string, number>};
  retries: {at: string; reason: string | null}[]};
export type Wallet = {school_id: string; name: string; code: string; status: string; balance: number; reserved: number; available: number; low: boolean;
  sms_enabled: boolean; threshold: number; consumed_30d: number; last_topup_at: string | null};
export type LedgerRow = {id: string; movement_type: string; direction: string; quantity: number; balance_before: number; balance_after: number; reserved_after: number;
  reference: string | null; reason: string | null; source_type: string | null; commercial_price: number | null; commercial_currency: string | null;
  created_at: string; actor: string | null};
export type Filters = {channel?: string; status?: string; scope?: string; school_id?: string; event?: string; date_from?: string; date_to?: string; q?: string};

async function req<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(`${B}${path}`, {...init, headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...(init.headers || {})}});
  if (!r.ok) {
    let msg = friendlyHttpMessage(r.status);
    try { const j = await r.json(); if (typeof j.detail === 'string') msg = j.detail; } catch { /* message générique */ }
    throw new UserFacingError(msg, String(r.status));
  }
  return r.json();
}
const qs = (o: Record<string, string | number | boolean | undefined | null>) =>
  Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '' && v !== false).map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&');

export const getStatus = (t: string) => req<Status>(t, '/status');
export const requestHealthCheck = (t: string) => req<{requested: boolean; detail?: string}>(t, '/health-check', {method: 'POST'});
export const listDeliveries = (t: string, f: Filters, cursor?: string | null, limit = 25, signal?: AbortSignal) =>
  req<{items: DeliveryRow[]; next_cursor: string | null}>(t, `/deliveries?${qs({...f, cursor, limit})}`, {signal});
export const getDelivery = (t: string, id: string) => req<DeliveryDetail>(t, `/deliveries/${encodeURIComponent(id)}`);
export const retryDelivery = (t: string, id: string, reason: string, key: string) =>
  req<{status: string; requeued: boolean; replayed?: boolean}>(t, `/deliveries/${encodeURIComponent(id)}/retry`, {method: 'POST', body: JSON.stringify({reason}), headers: {'Idempotency-Key': key}});
export const listWallets = (t: string, q: string, low: boolean, cursor?: string | null, signal?: AbortSignal) =>
  req<{items: Wallet[]; next_cursor: string | null; totals: {balance: number; reserved: number; available: number; funded_schools: number}}>(t, `/wallets?${qs({q, low, cursor, limit: 30})}`, {signal});
export const getLedger = (t: string, schoolId: string) =>
  req<{items: LedgerRow[]; wallet: {name: string; balance: number; reserved: number; available: number}}>(t, `/wallets/${schoolId}/ledger?limit=100`);
export const creditWallet = (t: string, schoolId: string, body: {quantity: number; reference: string; reason: string; paid_on: string; commercial_price: number; commercial_currency: string}, key: string) =>
  req<{balance_before: number; balance: number; replayed: boolean}>(t, `/wallets/${schoolId}/credit`, {method: 'POST', body: JSON.stringify(body), headers: {'Idempotency-Key': key}});
export const adjustWallet = (t: string, schoolId: string, body: {direction: 'CREDIT' | 'DEBIT'; quantity: number; reason: string; reference?: string}, key: string) =>
  req<{balance_before: number; balance: number; replayed: boolean}>(t, `/wallets/${schoolId}/adjust`, {method: 'POST', body: JSON.stringify(body), headers: {'Idempotency-Key': key}});
export const testSend = (t: string, channel: 'EMAIL' | 'PUSH') => req<{message_id: string}>(t, '/test-send', {method: 'POST', body: JSON.stringify({channel})});
export const testStatus = (t: string, id: string) => req<{items: {channel: string; status: string; last_error_code: string | null; provider_proof: boolean}[]}>(t, `/test-send/${id}`);

export const STATUS_LABEL: Record<string, string> = {
  QUEUED: 'En file', PROCESSING: 'En cours', SENT: 'Envoyé', DELIVERED: 'Distribué (preuve)', FAILED_RETRYABLE: 'Nouvel essai prévu',
  FAILED_PERMANENT: 'Échec définitif', CANCELLED: 'Non envoyé',
};
export const CHANNEL_LABEL: Record<string, string> = {SMS: 'SMS', EMAIL: 'E-mail', PUSH: 'Push', IN_APP: 'Dans l’application'};
export const EVENT_LABEL: Record<string, string> = {
  ACCOUNT_INVITATION: 'Invitation', ACCOUNT_PASSWORD_RESET: 'Mot de passe oublié', ACCOUNT_SECURITY_ALERT: 'Alerte de sécurité', PLATFORM_ALERT: 'Alerte plateforme',
  PLATFORM: 'Message plateforme', ACCOUNT: 'Compte', COMMUNIQUE: 'Communiqué d’école', MANUAL: 'Message d’école', ANNOUNCEMENT: 'Annonce', PUSH_TEST: 'Test push', SCHOOL_MESSAGE: 'Message d’école (contenu privé)',
};
export const MOVEMENT_LABEL: Record<string, string> = {
  TOPUP: 'Recharge', RESERVATION: 'Réservation', CONSUMPTION: 'Consommation', RELEASE: 'Libération de réservation', ADJUSTMENT: 'Ajustement', REFUND: 'Remboursement',
};
