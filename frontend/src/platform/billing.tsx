// Abonnements EduSync — console plateforme (Volcano Tech → écoles). Rewritten 2026-11-21 after the owner's review:
// « son interface est trop bizarre, il déplace la barre du haut et la barre du bas ». Mobile first (no horizontal
// overflow down to 320 px), French labels and amounts, every server action reachable: attribuer une offre, tarifer et
// publier une offre, facturer, encaisser, changer l'état d'un abonnement (only the transitions the domain allows),
// exporter. Commercial invoices stay separate from the schools' own cash desks.
import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {toast} from 'sonner';
import {Button, EmptyState, PageHeader, Skeleton} from './ui';
import {friendlyError} from './errors';
import {NavGlyph} from './nav_icons';
import {fetchSchools, type SchoolRow} from './schools_api';
import {
  createPlan, createPlanVersion, createSubscription, exportBillingCsv, getCatalog, getInvoices, getPayments, getPlanVersions,
  getSubscriptions, issueInvoice, publishPlanVersion, recordPayment, transitionSubscription,
  type Invoice, type Module, type Payment, type Plan, type PlanVersion, type Subscription,
} from './billing_api';
import './billing.css';

type Tab = 'subscriptions' | 'invoices' | 'payments' | 'offers';
const STATUS: Record<string, string> = {
  TRIAL: 'Essai', PENDING_PAYMENT: 'Paiement attendu', ACTIVE: 'Actif', PAST_DUE: 'Échu', GRACE: 'Délai de grâce',
  LIMITED: 'Accès limité', SUSPENDED: 'Suspendu', CANCELLED: 'Résilié', EXPIRED: 'Expiré', ISSUED: 'Émise',
  PARTIALLY_PAID: 'Payée en partie', PAID: 'Payée', OVERDUE: 'En retard', VOID: 'Annulée', REFUNDED: 'Remboursée',
  SUCCEEDED: 'Confirmé', FAILED: 'Échec', PENDING: 'En attente', CREATED: 'Créé', DRAFT: 'Brouillon', PUBLISHED: 'Publiée',
  RETIRED: 'Retirée',
};
const TONE: Record<string, 'ok' | 'warn' | 'bad' | 'info' | 'mute'> = {
  ACTIVE: 'ok', PAID: 'ok', SUCCEEDED: 'ok', PUBLISHED: 'ok', TRIAL: 'info', PENDING_PAYMENT: 'info', ISSUED: 'info', PENDING: 'info',
  CREATED: 'info', DRAFT: 'mute', GRACE: 'warn', PAST_DUE: 'warn', PARTIALLY_PAID: 'warn', OVERDUE: 'warn', LIMITED: 'bad',
  SUSPENDED: 'bad', FAILED: 'bad', CANCELLED: 'mute', EXPIRED: 'mute', VOID: 'mute', REFUNDED: 'mute', RETIRED: 'mute',
};
const CYCLE: Record<string, string> = {MONTHLY: 'Mensuel', QUARTERLY: 'Trimestriel', ANNUAL: 'Annuel'};
const CYCLE_UNIT: Record<string, string> = {MONTHLY: 'mois', QUARTERLY: 'trimestre', ANNUAL: 'an'};
const CHANNEL: Record<string, string> = {MANUAL: 'Espèces / manuel', BANK: 'Banque', AIRTEL_MONEY: 'Airtel Money', ORANGE_MONEY: 'Orange Money',
  M_PESA: 'M-Pesa', MOBILE_MONEY: 'Mobile Money'};
// Same domain rules as backend/src/edusync/modules/subscriptions/domain/subscription.py (_ALLOWED): only legal moves are offered.
const MOVES: Record<string, string[]> = {
  TRIAL: ['ACTIVE', 'PENDING_PAYMENT', 'CANCELLED'], PENDING_PAYMENT: ['ACTIVE', 'CANCELLED'], ACTIVE: ['PAST_DUE', 'CANCELLED'],
  PAST_DUE: ['ACTIVE', 'GRACE', 'LIMITED', 'CANCELLED'], GRACE: ['ACTIVE', 'LIMITED', 'CANCELLED'], LIMITED: ['ACTIVE', 'SUSPENDED', 'CANCELLED'],
  SUSPENDED: ['ACTIVE', 'CANCELLED'], CANCELLED: [], EXPIRED: ['ACTIVE', 'PENDING_PAYMENT'],
};
const MOVE_LABEL: Record<string, string> = {ACTIVE: 'Activer / réactiver', PENDING_PAYMENT: 'Attendre le premier paiement', PAST_DUE: 'Marquer échu',
  GRACE: 'Accorder un délai de grâce', LIMITED: 'Limiter l’accès', SUSPENDED: 'Suspendre', CANCELLED: 'Résilier'};
const ATTENTION = new Set(['PAST_DUE', 'GRACE', 'LIMITED', 'SUSPENDED', 'PENDING_PAYMENT']);
const OPEN_INVOICE = new Set(['ISSUED', 'OVERDUE', 'PARTIALLY_PAID']);

export const money = (v: string | number, c = 'USD') =>
  `${(Number(v) || 0).toLocaleString('fr-FR', {minimumFractionDigits: 2, maximumFractionDigits: 2})} ${c === 'CDF' ? 'FC' : '$'}`;
const day = (v?: string | null) => (v ? new Date(v).toLocaleDateString('fr-FR') : '—');
const today = () => new Date().toISOString().slice(0, 10);
const Status = ({s}: {s: string}) => <span className={`bl-status ${TONE[s] || 'mute'}`}>{STATUS[s] || s}</span>;
const norm = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

export default function BillingPage({token, has}: {token: string; has: (cap: string) => boolean}) {
  const [tab, setTab] = useState<Tab>('subscriptions');
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [modules, setModules] = useState<Module[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dialog, setDialog] = useState<React.ReactNode>(null);
  const load = useCallback(async () => {
    try {
      setLoading(true); setError('');
      const [s, i, p, c] = await Promise.all([getSubscriptions(token), getInvoices(token), getPayments(token), getCatalog(token)]);
      setSubscriptions(s); setInvoices(i); setPayments(p); setPlans(c.plans); setModules(c.modules);
    } catch (e) { setError(friendlyError(e)); } finally { setLoading(false); }
  }, [token]);
  useEffect(() => { void load(); }, [load]);
  const close = () => setDialog(null);
  const done = async () => { setDialog(null); await load(); };
  const totals = useMemo(() => {
    const open = invoices.filter(i => OPEN_INVOICE.has(i.status));
    const due = (c: string) => open.filter(i => i.currency === c).reduce((n, i) => n + Number(i.total) - Number(i.paid_total), 0);
    return {active: subscriptions.filter(s => s.status === 'ACTIVE').length, attention: subscriptions.filter(s => ATTENTION.has(s.status)).length,
      overdue: invoices.filter(i => i.status === 'OVERDUE').length, usd: due('USD'), cdf: due('CDF')};
  }, [subscriptions, invoices]);
  async function exportCsv() {
    try {
      const url = URL.createObjectURL(await exportBillingCsv(token));
      const a = document.createElement('a'); a.href = url; a.download = `abonnements-edusync-${today()}.csv`; a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1500);
    } catch (e) { toast.error(friendlyError(e)); }
  }
  const tabs: [Tab, string, number][] = [['subscriptions', 'Abonnements', subscriptions.length], ['invoices', 'Factures', invoices.filter(i => OPEN_INVOICE.has(i.status)).length],
    ['payments', 'Paiements', payments.length], ['offers', 'Offres', plans.length]];
  return (
    <div className="ui-page bl">
      <PageHeader eyebrow="Commercial" title="Abonnements des écoles"
        subtitle="Offres EduSync, échéances, factures et paiements. Ces opérations sont séparées des caisses des écoles."
        actions={<div className="bl-head-actions">
          {has('platform.billing.export') && <Button icon="download" onClick={() => void exportCsv()} disabled={loading}>Exporter</Button>}
          <Button icon="sync" onClick={() => void load()} disabled={loading}>Actualiser</Button>
        </div>} />
      {error && <div className="sc-error" role="alert"><NavGlyph g="alert" size={18} /><div><b>Abonnements indisponibles</b><small>{error}</small></div>
        <Button onClick={() => void load()}>Réessayer</Button></div>}
      <div className="bl-kpis">
        <Kpi label="Abonnements actifs" value={String(totals.active)} hint={`sur ${subscriptions.length} école${subscriptions.length > 1 ? 's' : ''} abonnée${subscriptions.length > 1 ? 's' : ''}`} />
        <Kpi label="À surveiller" value={String(totals.attention)} hint="Paiement attendu, retard, grâce ou accès limité" tone={totals.attention ? 'warn' : undefined}
          onClick={() => setTab('subscriptions')} />
        <Kpi label="À encaisser (USD)" value={money(totals.usd, 'USD')} hint={`${totals.overdue} facture${totals.overdue > 1 ? 's' : ''} en retard`} tone={totals.overdue ? 'warn' : undefined}
          onClick={() => setTab('invoices')} />
        <Kpi label="À encaisser (FC)" value={money(totals.cdf, 'CDF')} hint="Factures émises en francs congolais" onClick={() => setTab('invoices')} />
      </div>
      <div className="bl-tabs" role="tablist" aria-label="Sections des abonnements">
        {tabs.map(([k, l, n]) => <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>
          {l}<em>{n}</em></button>)}
      </div>
      {loading ? <div className="bl-panel"><Skeleton lines={6} /></div> : <>
        {tab === 'subscriptions' && <Subscriptions items={subscriptions} has={has}
          onAssign={() => setDialog(<AssignDialog token={token} plans={plans} onClose={close} onDone={done} />)}
          onInvoice={x => setDialog(<InvoiceDialog token={token} item={x} onClose={close} onDone={done} />)}
          onMove={(x, target) => setDialog(<MoveDialog token={token} item={x} target={target} onClose={close} onDone={done} />)} />}
        {tab === 'invoices' && <Invoices items={invoices} canPay={has('platform.billing.payments.reconcile')}
          onPay={x => setDialog(<PaymentDialog token={token} item={x} onClose={close} onDone={done} />)} />}
        {tab === 'payments' && <Payments items={payments} />}
        {tab === 'offers' && <Offers token={token} items={plans} modules={modules} canManage={has('platform.billing.plans.manage')}
          onCreate={() => setDialog(<PlanDialog token={token} onClose={close} onDone={done} />)}
          onPrice={p => setDialog(<VersionDialog token={token} plan={p} modules={modules} onClose={close} onDone={done} />)}
          onPublish={(p, v) => setDialog(<PublishDialog token={token} plan={p} version={v} onClose={close} onDone={done} />)} />}
      </>}
      {dialog}
    </div>
  );
}

function Kpi({label, value, hint, tone, onClick}: {label: string; value: string; hint: string; tone?: 'warn'; onClick?: () => void}) {
  const body = <><span>{label}</span><b>{value}</b><small>{hint}</small></>;
  return onClick ? <button type="button" className={`bl-kpi ${tone || ''}`} onClick={onClick}>{body}</button> : <article className={`bl-kpi ${tone || ''}`}>{body}</article>;
}

function Toolbar({q, setQ, placeholder, filters, filter, setFilter, action}: {q: string; setQ: (v: string) => void; placeholder: string;
  filters: [string, string, number][]; filter: string; setFilter: (v: string) => void; action?: React.ReactNode}) {
  return <div className="bl-toolbar">
    <label className="bl-search"><NavGlyph g="search" size={17} /><input value={q} onChange={e => setQ(e.target.value)} placeholder={placeholder} aria-label={placeholder} /></label>
    <div className="bl-chips" role="group" aria-label="Filtrer">
      {filters.map(([k, l, n]) => <button key={k} type="button" aria-pressed={filter === k} className={filter === k ? 'on' : ''} onClick={() => setFilter(k)}>{l}<em>{n}</em></button>)}
    </div>
    {action}
  </div>;
}

function Subscriptions({items, has, onAssign, onInvoice, onMove}: {items: Subscription[]; has: (c: string) => boolean; onAssign: () => void;
  onInvoice: (x: Subscription) => void; onMove: (x: Subscription, target: string) => void}) {
  const [q, setQ] = useState(''); const [filter, setFilter] = useState('all');
  const canManage = has('platform.billing.subscriptions.manage'), canGrace = has('platform.billing.overrides.grant'), canInvoice = has('platform.billing.invoices.manage');
  const groups: Record<string, (s: Subscription) => boolean> = {all: () => true, attention: s => ATTENTION.has(s.status), active: s => s.status === 'ACTIVE',
    trial: s => s.status === 'TRIAL', closed: s => ['CANCELLED', 'EXPIRED'].includes(s.status)};
  const rank = (s: Subscription) => (ATTENTION.has(s.status) ? 0 : s.status === 'TRIAL' ? 1 : s.status === 'ACTIVE' ? 2 : 3);
  const shown = items.filter(groups[filter]).filter(s => !q || norm(`${s.school_name} ${s.plan_name}`).includes(norm(q)))
    .sort((a, b) => rank(a) - rank(b) || a.current_period_end.localeCompare(b.current_period_end));
  return <section className="bl-panel">
    <div className="bl-head"><h3>Abonnements</h3>{canManage && <Button variant="primary" icon="plus" onClick={onAssign}>Attribuer une offre</Button>}</div>
    <Toolbar q={q} setQ={setQ} placeholder="Rechercher une école ou une offre" filter={filter} setFilter={setFilter}
      filters={[['all', 'Tous', items.length], ['attention', 'À surveiller', items.filter(groups.attention).length], ['active', 'Actifs', items.filter(groups.active).length],
        ['trial', 'Essai', items.filter(groups.trial).length], ['closed', 'Clos', items.filter(groups.closed).length]]} />
    {!shown.length ? <EmptyState icon="school" title={items.length ? 'Aucun abonnement pour ce filtre' : 'Aucune école abonnée'}
      text={items.length ? 'Changez de filtre ou de recherche.' : 'Publiez une offre (onglet Offres), puis « Attribuer une offre » à une école.'} /> :
      <ul className="bl-list">{shown.map(x => {
        const moves = (MOVES[x.status] || []).filter(t => canManage && (t !== 'GRACE' || canGrace));
        return <li key={x.id} className="bl-card">
          <div className="bl-card-top"><b className="bl-school">{x.school_name}</b><Status s={x.status} /></div>
          <dl className="bl-facts">
            <div><dt>Offre</dt><dd>{x.plan_name} · {CYCLE[x.billing_cycle] || x.billing_cycle}</dd></div>
            <div><dt>Prix</dt><dd><span className="bl-money">{money(x.amount, x.currency)}</span> <small className="bl-unit">/ {CYCLE_UNIT[x.billing_cycle] || 'période'}</small></dd></div>
            <div><dt>Période</dt><dd>du {day(x.current_period_start)} <span className="bl-nowrap">au {day(x.current_period_end)}</span></dd></div>
            <div><dt>Grâce</dt><dd>{x.grace_days} jour{x.grace_days > 1 ? 's' : ''}</dd></div>
          </dl>
          {(canInvoice || moves.length > 0) && <div className="bl-card-actions">
            {canInvoice && !['CANCELLED', 'EXPIRED'].includes(x.status) && <Button size="sm" icon="receipt" onClick={() => onInvoice(x)}>Facturer</Button>}
            {moves.length > 0 && <select className="bl-move" aria-label={`Changer l’état de ${x.school_name}`} value=""
              onChange={e => { if (e.target.value) onMove(x, e.target.value); }}>
              <option value="">Changer l’état…</option>
              {moves.map(t => <option key={t} value={t}>{MOVE_LABEL[t]}</option>)}
            </select>}
          </div>}
        </li>;
      })}</ul>}
  </section>;
}

function Invoices({items, canPay, onPay}: {items: Invoice[]; canPay: boolean; onPay: (x: Invoice) => void}) {
  const [q, setQ] = useState(''); const [filter, setFilter] = useState('open');
  const groups: Record<string, (i: Invoice) => boolean> = {open: i => OPEN_INVOICE.has(i.status), overdue: i => i.status === 'OVERDUE', paid: i => i.status === 'PAID', all: () => true};
  const rank = (i: Invoice) => (i.status === 'OVERDUE' ? 0 : i.status === 'PARTIALLY_PAID' ? 1 : i.status === 'ISSUED' ? 2 : 3);
  const shown = items.filter(groups[filter]).filter(i => !q || norm(`${i.invoice_number} ${i.school_name}`).includes(norm(q)))
    .sort((a, b) => rank(a) - rank(b) || (b.due_at || '').localeCompare(a.due_at || ''));
  return <section className="bl-panel">
    <div className="bl-head"><h3>Factures</h3></div>
    <Toolbar q={q} setQ={setQ} placeholder="Rechercher un numéro ou une école" filter={filter} setFilter={setFilter}
      filters={[['open', 'À encaisser', items.filter(groups.open).length], ['overdue', 'En retard', items.filter(groups.overdue).length],
        ['paid', 'Payées', items.filter(groups.paid).length], ['all', 'Toutes', items.length]]} />
    {!shown.length ? <EmptyState icon="receipt" title={filter === 'open' ? 'Rien à encaisser' : 'Aucune facture pour ce filtre'}
      text={filter === 'open' ? 'Toutes les factures émises sont payées.' : undefined} /> :
      <ul className="bl-list">{shown.map(x => {
        const rest = Number(x.total) - Number(x.paid_total);
        return <li key={x.id} className="bl-card">
          <div className="bl-card-top"><b className="bl-school">{x.school_name}</b><Status s={x.status} /></div>
          <dl className="bl-facts">
            <div><dt>Facture</dt><dd className="bl-mono">{x.invoice_number}</dd></div>
            <div><dt>Échéance</dt><dd>{day(x.due_at)}</dd></div>
            <div><dt>Total</dt><dd className="bl-money">{money(x.total, x.currency)}</dd></div>
            <div><dt>Reste</dt><dd className={`bl-money ${rest > 0 ? 'due' : ''}`}>{money(rest, x.currency)}</dd></div>
          </dl>
          {canPay && rest > 0 && OPEN_INVOICE.has(x.status) && <div className="bl-card-actions">
            <Button size="sm" variant="primary" icon="checkCircle" onClick={() => onPay(x)}>Enregistrer un paiement</Button></div>}
        </li>;
      })}</ul>}
  </section>;
}

function Payments({items}: {items: Payment[]}) {
  const [q, setQ] = useState(''); const [filter, setFilter] = useState('all');
  const groups: Record<string, (p: Payment) => boolean> = {all: () => true, ok: p => p.status === 'SUCCEEDED', pending: p => ['CREATED', 'PENDING'].includes(p.status),
    failed: p => ['FAILED', 'EXPIRED', 'CANCELLED'].includes(p.status)};
  const shown = items.filter(groups[filter]).filter(p => !q || norm(`${p.school_name} ${p.invoice_number} ${p.provider_reference || ''}`).includes(norm(q)))
    .sort((a, b) => (b.confirmed_at || b.created_at || '').localeCompare(a.confirmed_at || a.created_at || ''));
  return <section className="bl-panel">
    <div className="bl-head"><h3>Paiements</h3></div>
    <Toolbar q={q} setQ={setQ} placeholder="Rechercher une école, une facture ou une référence" filter={filter} setFilter={setFilter}
      filters={[['all', 'Tous', items.length], ['ok', 'Confirmés', items.filter(groups.ok).length], ['pending', 'En attente', items.filter(groups.pending).length],
        ['failed', 'Échoués', items.filter(groups.failed).length]]} />
    {!shown.length ? <EmptyState icon="checkCircle" title="Aucun paiement pour ce filtre" /> :
      <ul className="bl-list">{shown.map(x => <li key={x.id} className="bl-card">
        <div className="bl-card-top"><b className="bl-school">{x.school_name}</b><Status s={x.status} /></div>
        <dl className="bl-facts">
          <div><dt>Montant</dt><dd className="bl-money">{money(x.amount, x.currency)}</dd></div>
          <div><dt>Date</dt><dd>{day(x.confirmed_at || x.created_at)}</dd></div>
          <div><dt>Facture</dt><dd className="bl-mono">{x.invoice_number}</dd></div>
          <div><dt>Moyen</dt><dd>{CHANNEL[x.provider] || CHANNEL[x.channel] || x.provider}</dd></div>
          <div className="wide"><dt>Référence</dt><dd className="bl-mono">{x.provider_reference || x.payment_reference}</dd></div>
        </dl>
      </li>)}</ul>}
  </section>;
}

function Offers({token, items, modules, canManage, onCreate, onPrice, onPublish}: {token: string; items: Plan[]; modules: Module[]; canManage: boolean;
  onCreate: () => void; onPrice: (p: Plan) => void; onPublish: (p: Plan, v: PlanVersion) => void}) {
  const [versions, setVersions] = useState<Record<string, PlanVersion[]>>({});
  const ids = items.map(p => `${p.id}:${p.version}:${p.version_count}`).join(',');
  useEffect(() => {
    let alive = true;
    Promise.all(items.map(p => getPlanVersions(token, p.id).then(v => [p.id, v] as const).catch(() => [p.id, []] as const)))
      .then(all => { if (alive) setVersions(Object.fromEntries(all)); });
    return () => { alive = false; };
  }, [token, ids]);
  const label = (code: string) => modules.find(m => m.code === code)?.label || code;
  return <section className="bl-panel">
    <div className="bl-head"><h3>Offres</h3>{canManage && <Button variant="primary" icon="plus" onClick={onCreate}>Nouvelle offre</Button>}</div>
    {!items.length ? <EmptyState icon="tag" title="Aucune offre" text="Créez une offre, donnez-lui un tarif, puis publiez-la pour l’attribuer aux écoles." /> :
      <div className="bl-offer-grid">{items.map(p => {
        const vs = versions[p.id]; const live = vs?.filter(v => v.status === 'PUBLISHED') || [];
        return <article className="bl-offer" key={p.id}>
          <div className="bl-card-top"><h4>{p.name}</h4><Status s={p.status} /></div>
          <small className="bl-mono">{p.code}</small>
          {p.description && <p>{p.description}</p>}
          {vs === undefined ? <Skeleton lines={2} /> : !vs.length ? <p className="bl-note">Aucun tarif : ajoutez-en un pour pouvoir publier cette offre.</p> :
            <ul className="bl-prices">{vs.map(v => <li key={v.id}>
              <div><b className="bl-money">{money(v.amount, v.currency)}</b> / {CYCLE_UNIT[v.billing_cycle]}<Status s={v.status} /></div>
              <small>{CYCLE[v.billing_cycle]} · essai {v.trial_days} j · grâce {v.grace_days} j · depuis le {day(v.effective_from)}</small>
              <small>{v.module_codes.map(label).join(' · ') || 'Aucun module'}</small>
              {canManage && v.status === 'DRAFT' && <Button size="sm" variant="primary" onClick={() => onPublish(p, v)}>Publier ce tarif</Button>}
            </li>)}</ul>}
          {canManage && <div className="bl-card-actions"><Button size="sm" icon="plus" onClick={() => onPrice(p)}>Ajouter un tarif</Button>
            {live.length > 0 && <span className="bl-note">{live.length} tarif{live.length > 1 ? 's' : ''} publié{live.length > 1 ? 's' : ''}</span>}</div>}
        </article>;
      })}</div>}
  </section>;
}

// ------------------------------------------------------------------------------------------------------------ dialogs
function Dialog({title, intro, busy, submitLabel, danger, onClose, onSubmit, children}: {title: string; intro?: React.ReactNode; busy: boolean;
  submitLabel: string; danger?: boolean; onClose: () => void; onSubmit: () => Promise<void>; children: React.ReactNode}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return <dialog ref={ref} className="bl-dialog" onCancel={e => { e.preventDefault(); if (!busy) onClose(); }}>
    <form className="bl-form" onSubmit={e => { e.preventDefault(); void onSubmit(); }}>
      <div className="bl-form-head"><h3>{title}</h3><button type="button" className="bl-x" aria-label="Fermer" onClick={onClose} disabled={busy}>×</button></div>
      {intro && <p className="bl-intro">{intro}</p>}
      {children}
      <div className="bl-form-actions">
        <Button type="button" onClick={onClose} disabled={busy}>Annuler</Button>
        <Button type="submit" variant={danger ? 'danger' : 'primary'} disabled={busy}>{busy ? 'Un instant…' : submitLabel}</Button>
      </div>
    </form>
  </dialog>;
}
function useSubmit(run: () => Promise<void>, ok: string, onDone: () => Promise<void>) {
  const [busy, setBusy] = useState(false);
  return {busy, submit: async () => { try { setBusy(true); await run(); toast.success(ok); await onDone(); } catch (e) { toast.error(friendlyError(e)); } finally { setBusy(false); } }};
}
const Reason = ({value, set, label = 'Motif (journal d’audit)'}: {value: string; set: (v: string) => void; label?: string}) =>
  <label>{label}<input required minLength={5} maxLength={500} value={value} onChange={e => set(e.target.value)} /></label>;

function AssignDialog({token, plans, onClose, onDone}: {token: string; plans: Plan[]; onClose: () => void; onDone: () => Promise<void>}) {
  const [q, setQ] = useState(''); const [found, setFound] = useState<SchoolRow[]>([]); const [school, setSchool] = useState<SchoolRow | null>(null);
  const [options, setOptions] = useState<(PlanVersion & {plan_name: string})[] | null>(null); const [version, setVersion] = useState('');
  const [start, setStart] = useState(today()); const [initial, setInitial] = useState<'TRIAL' | 'PENDING_PAYMENT' | 'ACTIVE'>('PENDING_PAYMENT');
  const [reason, setReason] = useState('Souscription de l’école');
  useEffect(() => {
    Promise.all(plans.map(p => getPlanVersions(token, p.id).then(vs => vs.filter(v => v.status === 'PUBLISHED').map(v => ({...v, plan_name: p.name}))).catch(() => [])))
      .then(all => { const flat = all.flat(); setOptions(flat); if (flat[0]) setVersion(flat[0].id); });
  }, [token, plans]);
  useEffect(() => {
    if (school || q.trim().length < 2) { setFound([]); return; }
    const t = window.setTimeout(() => { fetchSchools(token, {q: q.trim(), status: '', config: '', sort: 'name'}, null, 6).then(r => setFound(r.items)).catch(() => setFound([])); }, 250);
    return () => window.clearTimeout(t);
  }, [q, school, token]);
  const {busy, submit} = useSubmit(async () => {
    if (!school) throw new Error('Choisissez l’école.'); if (!version) throw new Error('Choisissez un tarif publié.');
    await createSubscription(token, {school_id: school.id, plan_version_id: version, starts_on: start, initial_status: initial, auto_renew: true, reason: reason.trim()});
  }, 'Offre attribuée à l’école', onDone);
  return <Dialog title="Attribuer une offre" intro="L’école reçoit l’offre choisie. Aucune facture n’est émise automatiquement : utilisez ensuite « Facturer »."
    busy={busy} submitLabel="Attribuer" onClose={onClose} onSubmit={submit}>
    {school ? <div className="bl-picked"><span><b>{school.name}</b><small>{school.code}</small></span>
      <button type="button" className="bl-link" onClick={() => { setSchool(null); setQ(''); }}>Changer</button></div> :
      <label>École<input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Nom ou code de l’école (2 lettres au moins)" />
        {found.length > 0 && <ul className="bl-suggest">{found.map(s => <li key={s.id}><button type="button" onClick={() => setSchool(s)}><b>{s.name}</b><small>{s.code}{s.city ? ` · ${s.city}` : ''}</small></button></li>)}</ul>}
      </label>}
    <label>Tarif publié
      {options === null ? <Skeleton lines={1} /> : !options.length ? <span className="bl-note">Aucun tarif publié : publiez d’abord un tarif dans l’onglet Offres.</span> :
        <select value={version} onChange={e => setVersion(e.target.value)}>{options.map(v => <option key={v.id} value={v.id}>
          {v.plan_name} — {money(v.amount, v.currency)} / {CYCLE_UNIT[v.billing_cycle]}</option>)}</select>}
    </label>
    <div className="bl-form-row">
      <label>Début<input type="date" required value={start} onChange={e => setStart(e.target.value)} /></label>
      <label>État de départ<select value={initial} onChange={e => setInitial(e.target.value as typeof initial)}>
        <option value="PENDING_PAYMENT">Paiement attendu</option><option value="TRIAL">Essai gratuit</option><option value="ACTIVE">Actif (déjà payé)</option></select></label>
    </div>
    <Reason value={reason} set={setReason} />
  </Dialog>;
}

function InvoiceDialog({token, item, onClose, onDone}: {token: string; item: Subscription; onClose: () => void; onDone: () => Promise<void>}) {
  const [start, setStart] = useState(item.current_period_end); const [days, setDays] = useState('7');
  const [discount, setDiscount] = useState('0'); const [fee, setFee] = useState('0'); const [reason, setReason] = useState('Facturation de la période');
  const total = Math.max(0, Number(item.amount) - (Number(discount) || 0) + (Number(fee) || 0));
  const {busy, submit} = useSubmit(() => issueInvoice(token, item.id, {period_start: start, due_days: Number(days) || 0, discount_total: discount || '0', fee_total: fee || '0', reason: reason.trim()}).then(() => undefined),
    'Facture émise', onDone);
  return <Dialog title="Émettre une facture" intro={<>{item.school_name} · {item.plan_name} · {money(item.amount, item.currency)} / {CYCLE_UNIT[item.billing_cycle]}</>}
    busy={busy} submitLabel={`Émettre ${money(total, item.currency)}`} onClose={onClose} onSubmit={submit}>
    <div className="bl-form-row">
      <label>Début de la période<input type="date" required value={start} onChange={e => setStart(e.target.value)} /></label>
      <label>À payer sous (jours)<input type="number" inputMode="numeric" min="0" max="90" value={days} onChange={e => setDays(e.target.value)} /></label>
    </div>
    <div className="bl-form-row">
      <label>Remise ({item.currency === 'CDF' ? 'FC' : '$'})<input type="number" inputMode="decimal" min="0" step="0.01" value={discount} onChange={e => setDiscount(e.target.value)} /></label>
      <label>Frais ajoutés ({item.currency === 'CDF' ? 'FC' : '$'})<input type="number" inputMode="decimal" min="0" step="0.01" value={fee} onChange={e => setFee(e.target.value)} /></label>
    </div>
    <Reason value={reason} set={setReason} />
  </Dialog>;
}

function PaymentDialog({token, item, onClose, onDone}: {token: string; item: Invoice; onClose: () => void; onDone: () => Promise<void>}) {
  const rest = (Number(item.total) - Number(item.paid_total)).toFixed(2);
  const [amount, setAmount] = useState(rest); const [provider, setProvider] = useState('MANUAL'); const [reference, setReference] = useState('');
  const [reason, setReason] = useState('Paiement reçu et vérifié');
  const {busy, submit} = useSubmit(() => recordPayment(token, item.id, {amount, currency: item.currency, provider, provider_reference: reference.trim(), reason: reason.trim()}).then(() => undefined),
    'Paiement enregistré, abonnement mis à jour', onDone);
  return <Dialog title="Enregistrer un paiement" intro={<>{item.school_name} · facture {item.invoice_number} · reste {money(rest, item.currency)}</>}
    busy={busy} submitLabel="Confirmer le paiement" onClose={onClose} onSubmit={submit}>
    <div className="bl-form-row">
      <label>Montant ({item.currency === 'CDF' ? 'FC' : '$'})<input type="number" inputMode="decimal" min="0.01" max={rest} step="0.01" required value={amount} onChange={e => setAmount(e.target.value)} /></label>
      <label>Moyen<select value={provider} onChange={e => setProvider(e.target.value)}>
        {['MANUAL', 'BANK', 'AIRTEL_MONEY', 'ORANGE_MONEY', 'M_PESA'].map(k => <option key={k} value={k}>{CHANNEL[k]}</option>)}</select></label>
    </div>
    <label>Référence du paiement<input required minLength={3} maxLength={180} value={reference} onChange={e => setReference(e.target.value)} placeholder="N° de reçu, de transaction ou de virement" /></label>
    <Reason value={reason} set={setReason} />
  </Dialog>;
}

function MoveDialog({token, item, target, onClose, onDone}: {token: string; item: Subscription; target: string; onClose: () => void; onDone: () => Promise<void>}) {
  const [reason, setReason] = useState('');
  const danger = ['SUSPENDED', 'CANCELLED', 'LIMITED'].includes(target);
  const {busy, submit} = useSubmit(() => transitionSubscription(token, item.id, target, {reason: reason.trim(), version: item.version}).then(() => undefined),
    `${item.school_name} : ${STATUS[target]}`, onDone);
  const effect: Record<string, string> = {CANCELLED: 'La résiliation est définitive : l’historique est conservé, mais l’abonnement ne pourra plus être réactivé.',
    SUSPENDED: 'L’abonnement est suspendu. Aucune donnée de l’école n’est supprimée.', LIMITED: 'L’accès commercial passe en mode limité. Aucune donnée n’est supprimée.',
    GRACE: 'L’école garde son accès pendant le délai de grâce.', ACTIVE: 'L’abonnement redevient actif.', PAST_DUE: 'L’abonnement est marqué échu ; les relances commencent.',
    PENDING_PAYMENT: 'L’abonnement attend son premier paiement.'};
  return <Dialog title={MOVE_LABEL[target]} intro={<><b>{item.school_name}</b> passe de « {STATUS[item.status]} » à « {STATUS[target]} ». {effect[target]}</>}
    busy={busy} danger={danger} submitLabel={MOVE_LABEL[target]} onClose={onClose} onSubmit={submit}>
    <Reason value={reason} set={setReason} label="Motif (obligatoire, journal d’audit)" />
  </Dialog>;
}

function PlanDialog({token, onClose, onDone}: {token: string; onClose: () => void; onDone: () => Promise<void>}) {
  const [code, setCode] = useState(''); const [name, setName] = useState(''); const [description, setDescription] = useState('');
  const {busy, submit} = useSubmit(() => createPlan(token, {code: code.trim().toUpperCase().replace(/[^A-Z0-9_]+/g, '_'), name: name.trim(), description: description.trim(), public_offer: true}).then(() => undefined),
    'Offre créée — ajoutez-lui un tarif', onDone);
  return <Dialog title="Nouvelle offre" intro="L’offre reste en brouillon tant qu’aucun tarif n’est publié." busy={busy} submitLabel="Créer l’offre" onClose={onClose} onSubmit={submit}>
    <label>Nom<input required minLength={2} maxLength={160} value={name} onChange={e => { setName(e.target.value); if (!code) setCode(''); }} placeholder="Gestion scolaire" /></label>
    <label>Code<input required pattern="[A-Z][A-Z0-9_]+" maxLength={64} value={code} onChange={e => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '_'))} placeholder="GESTION" /></label>
    <label>Description<textarea maxLength={2000} value={description} onChange={e => setDescription(e.target.value)} placeholder="Pour quelles écoles et quels besoins ?" /></label>
  </Dialog>;
}

function VersionDialog({token, plan, modules, onClose, onDone}: {token: string; plan: Plan; modules: Module[]; onClose: () => void; onDone: () => Promise<void>}) {
  const sellable = modules.filter(m => m.status === 'ACTIVE');
  const [cycle, setCycle] = useState('MONTHLY'); const [currency, setCurrency] = useState('USD'); const [amount, setAmount] = useState('');
  const [trial, setTrial] = useState('30'); const [grace, setGrace] = useState('10'); const [from, setFrom] = useState(today());
  const [picked, setPicked] = useState<string[]>(sellable.map(m => m.code));
  const {busy, submit} = useSubmit(async () => {
    if (!picked.length) throw new Error('Cochez au moins un module.');
    await createPlanVersion(token, plan.id, {billing_cycle: cycle, currency, amount, trial_days: Number(trial) || 0, grace_days: Number(grace) || 0, effective_from: from, module_codes: picked});
  }, 'Tarif créé en brouillon — publiez-le pour l’attribuer', onDone);
  return <Dialog title={`Tarif de « ${plan.name} »`} intro="Le tarif est créé en brouillon. Il ne s’applique aux écoles qu’après publication." busy={busy} submitLabel="Créer le tarif" onClose={onClose} onSubmit={submit}>
    <div className="bl-form-row">
      <label>Montant<input type="number" inputMode="decimal" min="0" step="0.01" required value={amount} onChange={e => setAmount(e.target.value)} placeholder="60" /></label>
      <label>Devise<select value={currency} onChange={e => setCurrency(e.target.value)}><option value="USD">Dollar ($)</option><option value="CDF">Franc congolais (FC)</option></select></label>
    </div>
    <div className="bl-form-row">
      <label>Rythme<select value={cycle} onChange={e => setCycle(e.target.value)}>{Object.entries(CYCLE).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
      <label>À partir du<input type="date" required value={from} onChange={e => setFrom(e.target.value)} /></label>
    </div>
    <div className="bl-form-row">
      <label>Essai gratuit (jours)<input type="number" inputMode="numeric" min="0" max="90" value={trial} onChange={e => setTrial(e.target.value)} /></label>
      <label>Délai de grâce (jours)<input type="number" inputMode="numeric" min="0" max="90" value={grace} onChange={e => setGrace(e.target.value)} /></label>
    </div>
    <fieldset className="bl-modules"><legend>Modules inclus</legend>
      {sellable.length ? sellable.map(m => <label key={m.code} className="bl-check"><input type="checkbox" checked={picked.includes(m.code)}
        onChange={e => setPicked(p => e.target.checked ? [...p, m.code] : p.filter(x => x !== m.code))} /><span><b>{m.label}</b>{m.description && <small>{m.description}</small>}</span></label>) :
        <span className="bl-note">Aucun module vendable n’est encore actif.</span>}
    </fieldset>
  </Dialog>;
}

function PublishDialog({token, plan, version, onClose, onDone}: {token: string; plan: Plan; version: PlanVersion; onClose: () => void; onDone: () => Promise<void>}) {
  const [reason, setReason] = useState('Mise en vente du tarif');
  const {busy, submit} = useSubmit(() => publishPlanVersion(token, version.id, plan.version, reason.trim()).then(() => undefined), 'Tarif publié', onDone);
  return <Dialog title="Publier ce tarif" intro={<>« {plan.name} » à <b>{money(version.amount, version.currency)} / {CYCLE_UNIT[version.billing_cycle]}</b>.
    Une fois publié, ce tarif peut être attribué aux écoles et ne se modifie plus : pour changer de prix, on crée un nouveau tarif.</>}
    busy={busy} submitLabel="Publier" onClose={onClose} onSubmit={submit}>
    <Reason value={reason} set={setReason} />
  </Dialog>;
}
