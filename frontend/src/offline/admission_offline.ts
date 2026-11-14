/* Offline enrollment (owner, 2026-11-08: « l'inscription doit être faite offline, en attente — surtout avec le paiement des
   frais exigés ; c'est là que le système doit être fort »).
   Without network, the review step is computed on the device from the copy of « what a new pupil pays in each class »
   (downloaded while online by the same dry run as the server preview). The enrollment and its payment are then kept in the
   device outbox with their Idempotency-Key; at replay the server recomputes and re-checks everything. */
import {UserFacingError} from '../platform/errors';
import {offlineAdmissionPack, type AdmissionChild, type AdmissionPreview, type EnrollmentBatchInput} from '../api';

export function isOfflineError(e: unknown): boolean {
  if (e instanceof UserFacingError) return e.code.startsWith('OFFLINE');
  if (e instanceof TypeError) return true;                                   // fetch could not reach the server
  const err = e as {name?: string; message?: string} | null;
  return err?.name === 'AbortError' || err?.message === 'network' || (typeof navigator !== 'undefined' && navigator.onLine === false);
}

const add = (t: Record<string, number>, cur: string, v: number) => { t[cur] = (t[cur] ?? 0) + v; };
const str = (t: Record<string, number>) => Object.fromEntries(Object.entries(t).filter(([, v]) => v > 0).map(([k, v]) => [k, String(v)]));

export async function offlineAdmissionPreview(token: string, input: EnrollmentBatchInput): Promise<AdmissionPreview> {
  let pack;
  try { pack = await offlineAdmissionPack(token); }
  catch { throw new UserFacingError('Hors connexion : les montants d’inscription ne sont pas encore sur cet appareil. Ouvrez EduSync une fois avec la connexion pour les télécharger, puis réessayez.', 'OFFLINE_NOT_CACHED'); }
  const totals: Record<string, number> = {}; const blocked: string[] = [];
  const children: AdmissionChild[] = input.children.map((c: any, i: number) => {
    const cls = pack.classes.find(x => x.class_id === c.class_id);
    if (!cls || !cls.available) {
      blocked.push(`${cls?.class_label ?? 'classe'} : ${cls?.reason ?? 'classe absente de la copie de cet appareil'}`);
      return {index: i, enrollment_id: `offline-${i}`, student_id: null, name: [c.last_name, c.middle_name, c.first_name].filter(Boolean).join(' '), class_label: cls?.class_label ?? '',
        items: [], totals: {}, exemption: null, to_pay: false, configured: false, complete: false, missing: [cls?.reason ?? 'Classe indisponible hors connexion'], blocked: true};
    }
    let exemption: AdmissionChild['exemption'] = null;
    if (pack.policy.conditions_exempt_benefit_beneficiaries && (c.large_family_beneficiary || c.staff_beneficiary)) exemption = {kind: 'BENEFIT', label: 'Bénéficiaire d’un avantage (exempté par la politique de l’école)'};
    else if (pack.policy.conditions_exempt_staff_children && c.staff_member_id) exemption = {kind: 'STAFF_CHILD', label: 'Enfant du personnel (exempté par la politique de l’école)'};
    const childTotals: Record<string, number> = {};
    cls.items.forEach(it => add(childTotals, it.currency, Number(it.amount)));
    if (!exemption) Object.entries(childTotals).forEach(([k, v]) => add(totals, k, v));
    const isBlocked = !exemption && cls.missing.length > 0;
    if (isBlocked) blocked.push(`${cls.missing.join(' et ')} pour ${c.last_name ?? 'l’enfant'} (${cls.class_label})`);
    return {index: i, enrollment_id: `offline-${i}`, student_id: null, name: [c.last_name, c.middle_name, c.first_name].filter(Boolean).join(' '), class_label: cls.class_label,
      items: cls.items.map((it, k) => ({charge_id: `offline-${i}-${k}`, label: it.label, currency: it.currency, amount: it.amount} as any)),
      totals: str(childTotals), exemption, to_pay: !exemption && cls.items.length > 0, configured: cls.configured, complete: false, missing: cls.missing, blocked: isBlocked};
  });
  return {conditions: {children, totals: str(totals), requires_payment: Object.values(totals).some(v => v > 0), blocked: blocked.length > 0,
    blocked_message: blocked.length ? `Inscription impossible pour l’instant : ${blocked.join(' ; ')}.` : null},
    can_collect: pack.can_collect, can_waive: false, offline: {generated_at: pack.generated_at}};
}
