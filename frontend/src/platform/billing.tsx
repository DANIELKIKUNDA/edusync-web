import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";
import { Button, EmptyState, PageHeader, Skeleton } from "./ui";
import { friendlyError } from "./errors";
import { NavGlyph } from "./nav_icons";
import {
  createPlan,
  getCatalog,
  getInvoices,
  getPayments,
  getSubscriptions,
  issueInvoice,
  recordPayment,
  type Invoice,
  type Payment,
  type Plan,
  type Subscription,
} from "./billing_api";
import './billing.css';

type Tab = "subscriptions" | "invoices" | "payments" | "offers";
const STATUS: Record<string, string> = {
  TRIAL: "Essai",
  PENDING_PAYMENT: "Paiement attendu",
  ACTIVE: "Actif",
  PAST_DUE: "Échu",
  GRACE: "Délai de grâce",
  LIMITED: "Accès limité",
  SUSPENDED: "Suspendu",
  CANCELLED: "Résilié",
  EXPIRED: "Expiré",
  ISSUED: "Émise",
  PARTIALLY_PAID: "Partiellement payée",
  PAID: "Payée",
  OVERDUE: "En retard",
  VOID: "Annulée",
  REFUNDED: "Remboursée",
  SUCCEEDED: "Confirmé",
  FAILED: "Échec",
  PENDING: "En attente",
  DRAFT: "Brouillon",
  PUBLISHED: "Publiée",
  RETIRED: "Retirée",
};
const money = (v: string | number, c = "USD") =>
  new Intl.NumberFormat("fr-CD", {
    style: "currency",
    currency: c,
    maximumFractionDigits: 2,
  }).format(Number(v) || 0);
const day = (v?: string | null) =>
  v ? new Date(v).toLocaleDateString("fr-FR") : "—";
const status = (s: string) => (
  <span className={`bl-status ${s}`}>{STATUS[s] || s}</span>
);

export default function BillingPage({
  token,
  has,
}: {
  token: string;
  has: (cap: string) => boolean;
}) {
  const [tab, setTab] = useState<Tab>("subscriptions");
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [invoiceTarget, setInvoiceTarget] = useState<Subscription | null>(null);
  const [paymentTarget, setPaymentTarget] = useState<Invoice | null>(null);
  const [newPlan, setNewPlan] = useState(false);
  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const [s, i, p, c] = await Promise.all([
        getSubscriptions(token),
        getInvoices(token),
        getPayments(token),
        getCatalog(token),
      ]);
      setSubscriptions(s);
      setInvoices(i);
      setPayments(p);
      setPlans(c.plans);
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setLoading(false);
    }
  }, [token]);
  useEffect(() => {
    void load();
  }, [load]);
  const totals = useMemo(() => {
    const open = invoices.filter(
      (i) => !["PAID", "VOID", "REFUNDED"].includes(i.status),
    );
    return {
      active: subscriptions.filter((s) => s.status === "ACTIVE").length,
      attention: subscriptions.filter((s) =>
        ["GRACE", "LIMITED", "PAST_DUE"].includes(s.status),
      ).length,
      dueUSD: open
        .filter((i) => i.currency === "USD")
        .reduce((n, i) => n + Number(i.total) - Number(i.paid_total), 0),
      dueCDF: open
        .filter((i) => i.currency === "CDF")
        .reduce((n, i) => n + Number(i.total) - Number(i.paid_total), 0),
    };
  }, [subscriptions, invoices]);
  return (
    <div className="ui-page bl">
      <PageHeader
        eyebrow="Atelier Pro"
        title="Abonnements"
        subtitle="Offres EduSync, échéances, factures et paiements des écoles. Ces opérations restent séparées de leurs caisses scolaires."
        actions={
          <Button icon="sync" onClick={() => void load()} disabled={loading}>
            Actualiser
          </Button>
        }
      />
      {error && (
        <div className="sc-error" role="alert">
          <NavGlyph g="alert" size={18} />
          <div>
            <b>Abonnements indisponibles</b>
            <small>{error}</small>
          </div>
          <Button onClick={() => void load()}>Réessayer</Button>
        </div>
      )}
      <div className="bl-kpis">
        <Kpi
          label="Abonnements actifs"
          value={String(totals.active)}
          hint={`${subscriptions.length} école${subscriptions.length > 1 ? "s" : ""} abonnée${subscriptions.length > 1 ? "s" : ""}`}
        />
        <Kpi
          label="À surveiller"
          value={String(totals.attention)}
          hint="Grâce, retard ou accès limité"
        />
        <Kpi
          label="Solde USD"
          value={money(totals.dueUSD, "USD")}
          hint="Factures encore ouvertes"
        />
        <Kpi
          label="Solde CDF"
          value={money(totals.dueCDF, "CDF")}
          hint="Factures encore ouvertes"
        />
      </div>
      <nav className="bl-tabs" aria-label="Sections des abonnements">
        {(
          [
            ["subscriptions", "Abonnements"],
            ["invoices", "Factures"],
            ["payments", "Paiements"],
            ["offers", "Offres"],
          ] as [Tab, string][]
        ).map(([k, l]) => (
          <button
            key={k}
            className={tab === k ? "active" : ""}
            onClick={() => setTab(k)}
          >
            {l}
          </button>
        ))}
      </nav>
      {loading ? (
        <div className="bl-panel">
          <Skeleton lines={6} />
        </div>
      ) : (
        <>
          {tab === "subscriptions" && (
            <Subscriptions
              items={subscriptions}
              canInvoice={has("platform.billing.invoices.manage")}
              onInvoice={setInvoiceTarget}
            />
          )}
          {tab === "invoices" && (
            <Invoices
              items={invoices}
              canPay={has("platform.billing.payments.reconcile")}
              onPay={setPaymentTarget}
            />
          )}
          {tab === "payments" && <Payments items={payments} />}
          {tab === "offers" && (
            <Offers
              items={plans}
              canCreate={has("platform.billing.plans.manage")}
              onCreate={() => setNewPlan(true)}
            />
          )}
        </>
      )}
      {invoiceTarget && (
        <InvoiceDialog
          token={token}
          item={invoiceTarget}
          onClose={() => setInvoiceTarget(null)}
          onDone={async () => {
            setInvoiceTarget(null);
            await load();
          }}
        />
      )}
      {paymentTarget && (
        <PaymentDialog
          token={token}
          item={paymentTarget}
          onClose={() => setPaymentTarget(null)}
          onDone={async () => {
            setPaymentTarget(null);
            await load();
          }}
        />
      )}
      {newPlan && (
        <PlanDialog
          token={token}
          onClose={() => setNewPlan(false)}
          onDone={async () => {
            setNewPlan(false);
            await load();
          }}
        />
      )}
    </div>
  );
}
function Kpi({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <article className="bl-kpi">
      <span>{label}</span>
      <b>{value}</b>
      <small>{hint}</small>
    </article>
  );
}
function Subscriptions({
  items,
  canInvoice,
  onInvoice,
}: {
  items: Subscription[];
  canInvoice: boolean;
  onInvoice: (x: Subscription) => void;
}) {
  return (
    <div className="bl-panel">
      <div className="bl-head">
        <h3>Abonnements des écoles</h3>
      </div>
      {!items.length ? (
        <EmptyState
          icon="school"
          title="Aucun abonnement"
          text="Attribuez une offre publiée à une école depuis sa fiche."
        />
      ) : (
        <table className="bl-table">
          <thead>
            <tr>
              <th>École</th>
              <th>Offre</th>
              <th>État</th>
              <th>Période</th>
              <th>Prix</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((x) => (
              <tr key={x.id}>
                <td data-label="École">
                  <b>{x.school_name}</b>
                </td>
                <td data-label="Offre">
                  {x.plan_name}
                  <small> · {STATUS[x.billing_cycle] || x.billing_cycle}</small>
                </td>
                <td data-label="État">{status(x.status)}</td>
                <td data-label="Période">
                  {day(x.current_period_start)} → {day(x.current_period_end)}
                </td>
                <td data-label="Prix" className="bl-money">
                  {money(x.amount, x.currency)}
                </td>
                <td data-label="Action">
                  <div className="bl-actions">
                    {canInvoice && (
                      <Button
                        size="sm"
                        icon="receipt"
                        onClick={() => onInvoice(x)}
                      >
                        Facturer
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
function Invoices({
  items,
  canPay,
  onPay,
}: {
  items: Invoice[];
  canPay: boolean;
  onPay: (x: Invoice) => void;
}) {
  return (
    <div className="bl-panel">
      <div className="bl-head">
        <h3>Factures commerciales</h3>
      </div>
      {!items.length ? (
        <EmptyState icon="receipt" title="Aucune facture" />
      ) : (
        <table className="bl-table">
          <thead>
            <tr>
              <th>Numéro</th>
              <th>École</th>
              <th>État</th>
              <th>Échéance</th>
              <th>Total</th>
              <th>Reste</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((x) => {
              const rest = Number(x.total) - Number(x.paid_total);
              return (
                <tr key={x.id}>
                  <td data-label="Numéro">
                    <b>{x.invoice_number}</b>
                  </td>
                  <td data-label="École">{x.school_name}</td>
                  <td data-label="État">{status(x.status)}</td>
                  <td data-label="Échéance">{day(x.due_at)}</td>
                  <td data-label="Total" className="bl-money">
                    {money(x.total, x.currency)}
                  </td>
                  <td data-label="Reste" className="bl-money">
                    {money(rest, x.currency)}
                  </td>
                  <td data-label="Action">
                    <div className="bl-actions">
                      {canPay &&
                        rest > 0 &&
                        !["VOID", "REFUNDED"].includes(x.status) && (
                          <Button
                            size="sm"
                            icon="checkCircle"
                            onClick={() => onPay(x)}
                          >
                            Paiement
                          </Button>
                        )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
function Payments({ items }: { items: Payment[] }) {
  return (
    <div className="bl-panel">
      <div className="bl-head">
        <h3>Paiements rapprochés</h3>
      </div>
      {!items.length ? (
        <EmptyState icon="checkCircle" title="Aucun paiement" />
      ) : (
        <table className="bl-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>École</th>
              <th>Facture</th>
              <th>Référence</th>
              <th>Canal</th>
              <th>Montant</th>
              <th>État</th>
            </tr>
          </thead>
          <tbody>
            {items.map((x) => (
              <tr key={x.id}>
                <td data-label="Date">{day(x.confirmed_at || x.created_at)}</td>
                <td data-label="École">{x.school_name}</td>
                <td data-label="Facture">{x.invoice_number}</td>
                <td data-label="Référence">
                  <b>{x.provider_reference || x.payment_reference}</b>
                </td>
                <td data-label="Canal">{x.provider}</td>
                <td data-label="Montant" className="bl-money">
                  {money(x.amount, x.currency)}
                </td>
                <td data-label="État">{status(x.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
function Offers({
  items,
  canCreate,
  onCreate,
}: {
  items: Plan[];
  canCreate: boolean;
  onCreate: () => void;
}) {
  return (
    <div className="bl-panel">
      <div className="bl-head">
        <h3>Offres commerciales</h3>
        {canCreate && (
          <Button variant="primary" icon="plus" onClick={onCreate}>
            Nouvelle offre
          </Button>
        )}
      </div>
      {!items.length ? (
        <EmptyState icon="tag" title="Aucune offre" />
      ) : (
        <div className="bl-offer-grid">
          {items.map((x) => (
            <article className="bl-offer" key={x.id}>
              <div>{status(x.status)}</div>
              <h4>{x.name}</h4>
              <small>
                {x.code} · {x.version_count} version
                {x.version_count > 1 ? "s" : ""}
              </small>
              <p>{x.description || "Aucune description."}</p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function useOpenDialog() {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return ref;
}
function InvoiceDialog({
  token,
  item,
  onClose,
  onDone,
}: {
  token: string;
  item: Subscription;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const ref = useOpenDialog();
  const [start, setStart] = useState(item.current_period_end);
  const [days, setDays] = useState(7);
  const [discount, setDiscount] = useState("0");
  const [fee, setFee] = useState("0");
  const [reason, setReason] = useState("Facturation périodique");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      setBusy(true);
      await issueInvoice(token, item.id, {
        period_start: start,
        due_days: days,
        discount_total: discount,
        fee_total: fee,
        reason,
      });
      toast.success("Facture émise");
      await onDone();
    } catch (e) {
      toast.error(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog ref={ref} className="bl-dialog" onCancel={onClose}>
      <form className="bl-form" onSubmit={submit}>
        <h3>Émettre une facture</h3>
        <p>
          {item.school_name} · {item.plan_name}
        </p>
        <label>
          Début de la période
          <input
            type="date"
            required
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <div className="bl-form-row">
          <label>
            Échéance (jours)
            <input
              type="number"
              min="0"
              max="90"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            />
          </label>
          <label>
            Devise
            <input disabled value={item.currency} />
          </label>
        </div>
        <div className="bl-form-row">
          <label>
            Remise
            <input
              type="number"
              min="0"
              step="0.01"
              value={discount}
              onChange={(e) => setDiscount(e.target.value)}
            />
          </label>
          <label>
            Frais ajoutés
            <input
              type="number"
              min="0"
              step="0.01"
              value={fee}
              onChange={(e) => setFee(e.target.value)}
            />
          </label>
        </div>
        <label>
          Motif
          <input
            minLength={5}
            required
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        <div className="bl-form-actions">
          <Button onClick={onClose}>Annuler</Button>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "Émission…" : "Émettre"}
          </Button>
        </div>
      </form>
    </dialog>
  );
}
function PaymentDialog({
  token,
  item,
  onClose,
  onDone,
}: {
  token: string;
  item: Invoice;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const ref = useOpenDialog();
  const rest = (Number(item.total) - Number(item.paid_total)).toFixed(2);
  const [amount, setAmount] = useState(rest);
  const [provider, setProvider] = useState("MANUAL");
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState("Paiement confirmé par le gestionnaire");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      setBusy(true);
      await recordPayment(token, item.id, {
        amount,
        currency: item.currency,
        provider,
        provider_reference: reference,
        reason,
      });
      toast.success("Paiement enregistré et abonnement actualisé");
      await onDone();
    } catch (e) {
      toast.error(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog ref={ref} className="bl-dialog" onCancel={onClose}>
      <form className="bl-form" onSubmit={submit}>
        <h3>Enregistrer un paiement</h3>
        <p>
          {item.school_name} · {item.invoice_number} · reste{" "}
          {money(rest, item.currency)}
        </p>
        <div className="bl-form-row">
          <label>
            Montant
            <input
              type="number"
              min="0.01"
              max={rest}
              step="0.01"
              required
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </label>
          <label>
            Devise
            <input disabled value={item.currency} />
          </label>
        </div>
        <label>
          Origine
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          >
            <option value="MANUAL">Paiement manuel</option>
            <option value="BANK">Banque</option>
            <option value="AIRTEL_MONEY">Airtel Money</option>
            <option value="ORANGE_MONEY">Orange Money</option>
            <option value="M_PESA">M-Pesa</option>
          </select>
        </label>
        <label>
          Référence du paiement
          <input
            minLength={3}
            required
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            placeholder="Reçu, transaction ou virement"
          />
        </label>
        <label>
          Justification
          <input
            minLength={5}
            required
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        <div className="bl-form-actions">
          <Button onClick={onClose}>Annuler</Button>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "Enregistrement…" : "Confirmer le paiement"}
          </Button>
        </div>
      </form>
    </dialog>
  );
}
function PlanDialog({
  token,
  onClose,
  onDone,
}: {
  token: string;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const ref = useOpenDialog();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      setBusy(true);
      await createPlan(token, {
        code: code.trim().toUpperCase().replace(/\s+/g, "_"),
        name,
        description,
        public_offer: true,
      });
      toast.success("Offre créée en brouillon");
      await onDone();
    } catch (e) {
      toast.error(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog ref={ref} className="bl-dialog" onCancel={onClose}>
      <form className="bl-form" onSubmit={submit}>
        <h3>Nouvelle offre</h3>
        <p>
          Une offre reste en brouillon jusqu’à la publication de sa première
          version tarifaire.
        </p>
        <label>
          Code
          <input
            required
            pattern="[A-Z][A-Z0-9_]+"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="ESSENTIEL"
          />
        </label>
        <label>
          Nom
          <input
            required
            minLength={2}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="EduSync Essentiel"
          />
        </label>
        <label>
          Description
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Pour quelles écoles et quels besoins ?"
          />
        </label>
        <div className="bl-form-actions">
          <Button onClick={onClose}>Annuler</Button>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "Création…" : "Créer l’offre"}
          </Button>
        </div>
      </form>
    </dialog>
  );
}
