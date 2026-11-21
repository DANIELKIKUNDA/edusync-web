import { UserFacingError, friendlyHttpMessage } from "./errors";
const API = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
export type SchoolSubscription = {
  id: string;
  status: string;
  billing_cycle: string;
  current_period_start: string;
  current_period_end: string;
  next_billing_on: string | null;
  grace_days: number;
  auto_renew: boolean;
  plan_name: string;
  plan_description: string;
  amount: string;
  currency: string;
  trial_days: number;
};
export type SchoolModule = {
  module_code: string;
  label: string;
  description: string;
  status: string;
  ends_at: string | null;
  limits: Record<string, unknown>;
};
export type SchoolInvoice = {
  id: string;
  invoice_number: string;
  status: string;
  currency: string;
  period_start: string;
  period_end: string;
  issued_at: string | null;
  due_at: string | null;
  subtotal: string;
  discount_total: string;
  fee_total: string;
  total: string;
  paid_total: string;
};
export type SchoolPayment = {
  id: string;
  payment_reference: string;
  invoice_id: string;
  invoice_number: string;
  provider: string;
  provider_reference: string | null;
  channel: string;
  status: string;
  currency: string;
  amount: string;
  confirmed_at: string | null;
  created_at: string;
  expires_at?: string | null;
  failure_message?: string | null;
};
export type SchoolSubscriptionAccount = {
  subscription: SchoolSubscription | null;
  modules: SchoolModule[];
  invoices: SchoolInvoice[];
  payments: SchoolPayment[];
};
export async function getSchoolSubscriptionAccount(
  token: string,
): Promise<SchoolSubscriptionAccount> {
  const r = await fetch(`${API}/subscription/account`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) {
    let message = friendlyHttpMessage(r.status);
    try {
      const body = await r.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* message générique */
    }
    throw new UserFacingError(message, String(r.status));
  }
  return r.json();
}
export async function initiateSubscriptionPayment(
  token: string,
  invoiceId: string,
  phone: string,
  amount: string,
) {
  const r = await fetch(
    `${API}/subscription/invoices/${invoiceId}/mobile-money`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify({ phone, amount }),
    },
  );
  if (!r.ok) {
    let message = friendlyHttpMessage(r.status);
    try {
      const body = await r.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* message générique */
    }
    throw new UserFacingError(message, String(r.status));
  }
  return r.json() as Promise<{
    status: string;
    message: string;
    payment_reference: string;
  }>;
}
