// External messaging client (EXTERNAL_MESSAGING_ARCHITECTURE.md): school Communication Center, Atelier Pro supervision,
// push devices and account links. Sending is always accepted by the server first (QUEUED): the UI never shows "envoyé"
// before the server answered, and never a provider credential or a push token.
const API = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const auth = (token: string) => ({'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'});

async function call<T>(token: string | null, path: string, init: RequestInit = {}, fallback = 'Opération impossible'): Promise<T> {
  const headers: Record<string, string> = {...(token ? auth(token) : {'Content-Type': 'application/json'}), ...(init.headers as Record<string, string> | undefined)};
  const r = await fetch(`${API}${path}`, {...init, headers});
  if (!r.ok) {
    let detail = fallback;
    try { const j = await r.json(); if (typeof j.detail === 'string') detail = j.detail; } catch { /* keep fallback */ }
    const e = new Error(detail) as Error & {status?: number}; e.status = r.status; throw e;
  }
  return r.status === 204 ? (undefined as T) : r.json();
}
const post = <T,>(token: string | null, path: string, body: unknown, key = true) =>
  call<T>(token, path, {method: 'POST', body: JSON.stringify(body), headers: key ? {'Idempotency-Key': crypto.randomUUID()} : {}});

export type ChannelState = 'DISABLED' | 'SIMULATED' | 'CONFIGURED' | 'INCOMPLETE' | 'REFUSED';
export type Readiness = {
  enabled: boolean; sms_enabled: boolean; email_enabled: boolean; push_enabled: boolean; sms_low_balance_threshold: number; version: number;
  platform: Record<'sms' | 'email' | 'push', {state: ChannelState; available: boolean}>;
  wallet: {balance: number; reserved: number; available: number; low: boolean}; max_sms_characters: number;
};
export type Preview = {
  recipients: number; sms_valid: number; sms_invalid: number; sms_duplicates_removed: number; email_valid: number; characters: number;
  units_per_sms: number; sms_units: number; wallet_available: number; balance_after: number; sufficient: boolean; too_long: boolean; fingerprint: string;
};
export type Draft = {audience_type: 'INDIVIDUAL' | 'CLASS' | 'SECTION' | 'SCHOOL'; audience_ref?: string | null; channels: string[]; subject?: string; body: string};
export type HistoryItem = {
  id: string; kind: string; subject: string | null; audience_type: string; channels: string[]; recipient_count: number; sms_segments_reserved: number;
  created_at: string; dispatched_at: string | null; author: string | null; counts: Record<string, number>; sms_units_billed: number; errors: string[] | null;
};
export type SupervisionIncident = {id:string;rule_code:string;domain:string;severity:'INFO'|'WARNING'|'CRITICAL';condition_status:'OPEN'|'RESOLVED';
  response_status:'NEW'|'ACKNOWLEDGED'|'IN_PROGRESS'|'CLOSED';title:string;summary:string;explanation:string;recommendation:string;
  metric_json:Record<string,unknown>;target_path:string|null;opened_at:string;last_seen_at:string;resolved_at:string|null;reminder_count:number};

export const readiness = (t: string) => call<Readiness>(t, '/communications/readiness');
export const saveSettings = (t: string, s: {enabled: boolean; sms_enabled: boolean; email_enabled: boolean; push_enabled: boolean; sms_low_balance_threshold: number; expected_version: number}) =>
  call<{version: number}>(t, '/communications/settings', {method: 'PUT', body: JSON.stringify(s)});
export const walletLedger = (t: string) => call<{items: any[]}>(t, '/communications/wallet/ledger');
export const previewSend = (t: string, d: Draft) => post<Preview>(t, '/communications/preview', {...d, idempotency_key: crypto.randomUUID()}, false);
export const confirmSend = (t: string, d: Draft, key: string, fingerprint?: string) =>
  post<{id: string; status: string; recipients: number; sms_units_reserved: number}>(t, '/communications/send', {...d, idempotency_key: key, confirm_fingerprint: fingerprint}, false);
export const history = (t: string) => call<{items: HistoryItem[]}>(t, '/communications/history');
export const deliveries = (t: string, id: string) => call<{items: any[]}>(t, `/communications/history/${id}/deliveries`);
export const retryDelivery = (t: string, id: string) => post<{requeued: boolean}>(t, `/communications/deliveries/${id}/retry`, {});
export const supervisionIncidents = (t:string, state='active', domain='') => call<{items:SupervisionIncident[];counts:{active:number;critical:number;new:number}}>(t, `/supervision/incidents?state=${encodeURIComponent(state)}&domain=${encodeURIComponent(domain)}`);
export const supervisionAction = (t:string,id:string,action:'acknowledge'|'start'|'close') => post<{id:string;action:string}>(t, `/supervision/incidents/${id}/${action}`, {});
export const supervisionEvaluate = (t:string) => post<{findings:number;opened:number;notified:number;resolved:number}>(t, '/supervision/evaluate', {});

// Push devices (this browser) ------------------------------------------------------------------------------------
export type PushConfig = {provider: 'fcm' | 'fake' | 'disabled'; web_config: Record<string, string> | null; vapid_public_key: string | null};
export const pushConfig = (t: string, platform = false) => call<PushConfig>(t, platform ? '/platform/inbox/push/config' : '/notifications/push/config');
export const pushSubscribe = (t: string, body: {provider: string; endpoint: string; device_label?: string; platform?: string; browser?: string}, platform = false) =>
  post<{id: string; status: string}>(t, platform ? '/platform/inbox/push-subscriptions' : '/notifications/push-subscriptions', body);
export const pushRevoke = (t: string, id: string, platform = false) =>
  post<{revoked: boolean}>(t, platform ? `/platform/inbox/push-subscriptions/${id}/revoke` : `/notifications/push-subscriptions/${id}/revoke`, {});
export type PushDevice={id:string;provider:string;device_label:string|null;created_at:string;last_used_at:string|null};
export const pushDevices = (t: string, platform = false) => call<{items: PushDevice[]}>(t, platform ? '/platform/inbox/push-subscriptions' : '/notifications/push-subscriptions');
export const pushTest = (t: string) => post<{message_id: string; devices: number}>(t, '/notifications/push-test', {});

// Atelier Pro -------------------------------------------------------------------------------------------------------
export const platformMessagingStatus = (t: string) => call<any>(t, '/platform/messaging/status');
export const platformWallets = (t: string) => call<{items: any[]}>(t, '/platform/messaging/wallets');
export const platformLedger = (t: string, schoolId: string) => call<{items: any[]}>(t, `/platform/messaging/wallets/${schoolId}/ledger`);
export const platformCredit = (t: string, schoolId: string, body: {quantity: number; reference: string; reason: string; paid_on?: string; commercial_price?: number; commercial_currency?: string}) =>
  post<{balance: number}>(t, `/platform/messaging/wallets/${schoolId}/credit`, body);
export const platformAdjust = (t: string, schoolId: string, body: {direction: 'CREDIT' | 'DEBIT'; quantity: number; reason: string}) =>
  post<{balance: number}>(t, `/platform/messaging/wallets/${schoolId}/adjust`, body);
export const platformTestSend = (t: string, channel: 'EMAIL' | 'PUSH') => post<{message_id: string}>(t, '/platform/messaging/test-send', {channel});
export const platformTestStatus = (t: string, id: string) => call<{items: any[]}>(t, `/platform/messaging/test-send/${id}`);

// Account links (public) ------------------------------------------------------------------------------------------------
export const forgotPassword = (email: string) => post<{detail: string}>(null, '/auth/password/forgot', {email}, false);
export const resetPassword = (token: string, new_password: string) => post<{changed: boolean}>(null, '/auth/password/reset', {token, new_password}, false);
export const invitationDetails = (token: string) => call<{full_name: string; school_name: string | null}>(null, `/auth/invitations/${encodeURIComponent(token)}`, {}, 'Lien invalide ou expiré');
export const acceptInvitation = (token: string, new_password: string) => post<{activated: boolean; email?: string; scope?: 'PLATFORM' | 'SCHOOL'}>(null, '/auth/invitations/accept', {token, new_password}, false);

export const STATUS_LABEL: Record<string, string> = {
  QUEUED: 'En file', PROCESSING: 'En cours', SENT: 'Envoyé', DELIVERED: 'Distribué', FAILED_RETRYABLE: 'Nouvel essai prévu',
  FAILED_PERMANENT: 'Échec', CANCELLED: 'Non envoyé',
};
export const CHANNEL_LABEL: Record<string, string> = {SMS: 'SMS', EMAIL: 'E-mail', PUSH: 'Notification', IN_APP: 'Dans l’application'};
export const DELIVERY_ERROR_LABEL: Record<string, string> = {
  NO_PUSH_DEVICE: 'Aucun appareil du destinataire n’a activé les notifications',
  CHANNEL_DISABLED: 'Ce canal est désactivé pour l’école',
  PUSH_DISABLED_FOR_SCHOOL: 'Les notifications externes sont désactivées pour l’école',
  EMAIL_DISABLED_FOR_SCHOOL: 'Les e-mails sont désactivés pour l’école',
  SMS_DISABLED_FOR_SCHOOL: 'Les SMS sont désactivés pour l’école',
  NO_EMAIL_ADDRESS: 'Aucune adresse e-mail enregistrée',
  NO_VALID_PHONE: 'Aucun numéro de téléphone valide enregistré',
  INVALID_DESTINATION: 'Coordonnée du destinataire invalide',
  PROVIDER_NOT_CONFIGURED: 'Service d’envoi non configuré',
  PUSH_DEVICE_REVOKED: 'Notifications retirées sur cet appareil',
  PUSH_TOKEN_INVALID: 'Inscription de l’appareil expirée',
  PUSH_TOKEN_UNREGISTERED: 'Cet appareil n’est plus inscrit aux notifications',
  PUSH_PROVIDER_UNAVAILABLE: 'Service de notifications temporairement indisponible',
  PROVIDER_TIMEOUT: 'Le service d’envoi ne répond pas pour le moment',
  PROVIDER_RATE_LIMITED: 'Service momentanément saturé',
};

export const deliveryErrorLabel = (code?: string | null) => code ? (DELIVERY_ERROR_LABEL[code] ?? 'Incident technique à vérifier') : '';

export function deliveryStatusLabel(channel: string, status: string, errorCode?: string | null) {
  if (channel === 'PUSH' && status === 'CANCELLED' && errorCode === 'NO_PUSH_DEVICE') return 'Push non remis';
  if (channel === 'PUSH' && status === 'CANCELLED') return 'Push non envoyé';
  return STATUS_LABEL[status] ?? 'État à vérifier';
}
export const STATE_LABEL: Record<ChannelState, string> = {
  DISABLED: 'Non activé sur la plateforme', SIMULATED: 'Mode développement (simulé)', CONFIGURED: 'Disponible', INCOMPLETE: 'Configuration incomplète',
  REFUSED: 'Refusé (simulation interdite)',
};
