// Caisse, industrialised (owner request 2026-10-25: « le ui et le ux sont tellement banals, inspire-toi du desktop ; il faut
// voir les caisses passées et exporter la caisse »). Desktop CashPage (app/ui/operations_pages.py): state of the day,
// entries / outflows / balance per currency, the journal of movements, expense, closing with the counted amounts, PDF.
// Web: one session per cashier (owner decision 2026-10-15). Amounts are computed in cents (BigInt), CDF and USD never mixed.
import React, {useEffect, useMemo, useState} from 'react';
import {createPortal} from 'react-dom';
import {toast} from 'sonner';
import {cashClose, cashCurrent, cashDaySummary, cashJournal, cashOpen, cashSessionJournalFile, cashSessions, cashSessionsXlsx, type CashSession, type CashSessionRow, type CashSessionsPage} from './api';
import {CashExpenseForm, SchoolDayPanel, useReversal} from './cash_controls';
import {listOutbox} from './offline/outbox';
import {exportManaged, previewPdf} from './document_io';
import {friendlyError} from './platform/errors';
import {formatMoney} from './platform/format';
import {NavGlyph} from './platform/nav_icons';
import './cash_desk.css';

type Cur = 'CDF' | 'USD';
const money = (v: string | number | null | undefined, c: Cur) => formatMoney(String(v ?? 0), c);
const cents = (v: string | number | null | undefined): bigint => { const s = String(v ?? '0').trim().replace(',', '.'); if (!/^-?\d+(\.\d{0,2})?$/.test(s)) return 0n;
  const neg = s.startsWith('-'); const [i, d = ''] = s.replace('-', '').split('.'); const n = BigInt(i) * 100n + BigInt((d + '00').slice(0, 2)); return neg ? -n : n; };
const fromCents = (n: bigint) => { const neg = n < 0n; const a = neg ? -n : n; return `${neg ? '-' : ''}${a / 100n}.${String(a % 100n).padStart(2, '0')}`; };
const validAmount = (s: string) => /^\d+([.,]\d{1,2})?$/.test(s.trim());
const hm = (v?: string | null) => v ? new Date(v).toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit'}) : '—';
const dayFr = (v: string) => new Date(`${v}T12:00:00`).toLocaleDateString('fr-FR', {weekday: 'short', day: '2-digit', month: 'short', year: 'numeric'});
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const KIND: Record<string, string> = {RECEIPT: 'Encaissement', EXPENSE: 'Dépense', REMBOURSEMENT: 'Remboursement', ANNULATION: 'Annulation'};
const outflow = (x: CashSession['cdf']) => fromCents(cents(x.expenses) + cents((x as any).reversals));

function Modal({title, sub, onClose, children, foot}: {title: string; sub?: string; onClose: () => void; children: React.ReactNode; foot: React.ReactNode}) {
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); }; window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k); }, [onClose]);
  return createPortal(<div className="cd-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}>
    <div className="cd-modal" role="dialog" aria-modal="true" aria-label={title}><header><div><h3>{title}</h3>{sub && <p>{sub}</p>}</div><button type="button" className="cd-x" aria-label="Fermer" onClick={onClose}>×</button></header>
      <div className="cd-body">{children}</div><footer>{foot}</footer></div></div>, document.body);
}

export function CashDeskPro({token, can, schoolName}: {token: string; can: (p: string) => boolean; schoolName?: string}) {
  const [current, setCurrent] = useState<CashSession | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [journal, setJournal] = useState<Awaited<ReturnType<typeof cashJournal>> | null>(null);
  const [dialog, setDialog] = useState<'open' | 'expense' | 'close' | null>(null);
  const [err, setErr] = useState('');
  async function refresh() {
    // Offline (2026-10-25): the cash desk keeps working — operations waiting in the device outbox are merged into what
    // the server last said (opening / closing / payments / expenses recorded here), marked « en attente ».
    const pend = (await listOutbox().catch(() => [])).filter(r => r.status === 'PENDING');
    const lastCash = pend.filter(r => r.kind === 'CASH_OPEN' || r.kind === 'CASH_CLOSE').pop();
    let c: CashSession | null = null, failed: unknown = null;
    try { c = (await cashCurrent(token)).session; } catch (e) { failed = e; }
    if (lastCash?.kind === 'CASH_CLOSE') c = null;
    else if (lastCash?.kind === 'CASH_OPEN' && !c) { const b = JSON.parse(lastCash.body || '{}'); const z = (o: string) => ({opening: o, receipts: '0', expenses: '0', reversals: '0', expected_cash: o});
      c = {id: 'offline', membership_id: '', business_date: lastCash.createdAt.slice(0, 10), opened_at: lastCash.createdAt, status: 'OPEN', cdf: z(String(b.opening_cdf ?? '0')), usd: z(String(b.opening_usd ?? '0'))} as CashSession; }
    setCurrent(c); setErr(failed && !c && !lastCash ? friendlyError(failed) : '');
    let j: Awaited<ReturnType<typeof cashJournal>> | null = null;
    if (c && c.id !== 'offline') { try { j = await cashJournal(token, c.id); } catch { /* offline, not cached */ } }
    if (c) { const local = pend.filter(r => r.kind === 'PAYMENT' || r.kind === 'SALE' || r.kind === 'EXPENSE').map(r => { const b = JSON.parse(r.body || '{}');
        return {created_at: r.createdAt, kind: r.kind === 'EXPENSE' ? 'EXPENSE' : 'RECEIPT', reference: `En attente · ${r.label}`, amount: String(b.amount ?? (b.lines ?? []).reduce((t: number, l: any) => t + Number(l.amount || 0), 0)), currency: b.currency ?? b.lines?.[0]?.currency ?? 'CDF', pending: true}; });
      j = {session: j?.session ?? c, items: [...(j?.items ?? []), ...local] as any}; }
    setJournal(j); setLoaded(true);
  }
  useEffect(() => { const h = () => { void refresh(); }; window.addEventListener('edusync:outbox', h); return () => window.removeEventListener('edusync:outbox', h); }, [token]);
  useEffect(() => { void refresh(); }, [token]);
  const [askReversal, reversalNode] = useReversal(token, refresh);
  const operator=can('finance.cash.open')||can('finance.cash.close')||can('finance.cash.expense.create')||can('finance.checkout.collect');
  const supervisor=can('finance.cash.other.read')||can('finance.cash.day.close');

  return <section className="cd-root">
    {err && <div className="error" role="alert">{err}</div>}
    {operator && <article className={`cd-hero ${current ? 'open' : 'closed'}`}>
      <div className="cd-state"><span className={`cd-dot ${current ? 'open' : ''}`}/><div><span className="cd-eyebrow">Ma caisse</span>
        <h3>{!loaded ? 'Chargement…' : current ? <>Ouverte <small>depuis {hm(current.opened_at)}</small></> : 'Fermée'}</h3>
        <span className={`cashState ${current ? 'open' : 'closed'}`}><i/>{current ? 'OUVERTE' : 'FERMÉE'}</span></div></div>
      {current && <div className="cd-balances">{(['CDF', 'USD'] as Cur[]).map(c => { const x = current[c.toLowerCase() as 'cdf']; return <div key={c}>
        <span>Solde théorique {c === 'CDF' ? 'FC' : 'USD'}</span><b>{money(x.expected_cash, c)}</b>
        <small>Fond {money(x.opening, c)} · Entrées {money(x.receipts, c)} · Sorties {money(outflow(x), c)}</small></div>; })}</div>}
      <div className="cd-actions">
        {loaded && !err && !current && can('finance.cash.open') && <button type="button" className="cd-btn primary" onClick={() => setDialog('open')}><NavGlyph g="key" size={18}/>Ouvrir ma caisse</button>}
        {current && can('finance.cash.expense.create') && <button type="button" className="cd-btn" onClick={() => setDialog('expense')}><NavGlyph g="minus" size={18}/>Nouvelle dépense</button>}
        {current && can('finance.cash.journal.export') && <><button type="button" className="cd-btn" onClick={() => void exportSession(token, current.id, 'pdf', schoolName)}><NavGlyph g="doc" size={18}/>Journal PDF</button>
          <button type="button" className="cd-btn" onClick={() => void exportSession(token, current.id, 'xlsx', schoolName, current.business_date)}><NavGlyph g="sheet" size={18}/>Excel</button></>}
        {current && can('finance.cash.close') && <button type="button" className="cd-btn danger" onClick={() => setDialog('close')}><NavGlyph g="lock" size={18}/>Clôturer ma caisse</button>}
      </div>
    </article>}

    {operator && current && journal && <SessionJournal items={journal.items} canReverse={can('finance.payments.reverse')} onReverse={askReversal} title="Mouvements de ma caisse"/>}
    {operator && !current && loaded && <p className="cd-hint">Ouvrez votre caisse pour encaisser et enregistrer des dépenses. Vos caisses précédentes restent consultables ci-dessous.</p>}

    {supervisor && <Supervision token={token} can={can}/>}
    <PastSessions token={token} can={can} schoolName={schoolName} reloadKey={current?.status ?? 'none'}/>

    {operator && dialog === 'open' && <OpenDialog token={token} onClose={() => setDialog(null)} onDone={async () => { setDialog(null); await refresh(); }}/>}
    {operator && dialog === 'expense' && <Modal title="Nouvelle dépense" sub="La dépense sort de votre caisse et reste dans le journal (elle ne se supprime pas)." onClose={() => setDialog(null)} foot={<span className="cd-muted">Échap pour fermer</span>}>
      <CashExpenseForm token={token} onDone={async () => { setDialog(null); await refresh(); }}/></Modal>}
    {operator && dialog === 'close' && current && <CloseDialog token={token} session={current} onClose={() => setDialog(null)} onDone={async () => { setDialog(null); await refresh(); }}/>}
    {operator && reversalNode}
  </section>;
}

async function exportSession(token: string, id: string, kind: 'pdf' | 'xlsx', school?: string, day?: string) {
  try { const b = await cashSessionJournalFile(token, id, kind);
    if (kind === 'pdf') previewPdf(b); else await exportManaged(b, {school: school ?? 'École', module: 'Centre financier', category: 'Caisse', filename: `journal_caisse_${day ?? 'session'}.xlsx`});
    toast.success(kind === 'pdf' ? 'Journal de caisse ouvert' : 'Journal de caisse exporté en Excel'); }
  catch (e) { toast.error(friendlyError(e)); }
}

function SessionJournal({items, canReverse, onReverse, title}: {items: Awaited<ReturnType<typeof cashJournal>>['items']; canReverse: boolean; onReverse?: (id: string, ref: string) => void; title: string}) {
  const [dir, setDir] = useState<'ALL' | 'IN' | 'OUT'>('ALL'); const [q, setQ] = useState('');
  const rows = useMemo(() => items.filter((x: any) => (dir === 'ALL' || (dir === 'IN') === (x.kind === 'RECEIPT')) && (!q.trim() || `${x.reference} ${KIND[x.kind] ?? x.kind}`.toLowerCase().includes(q.trim().toLowerCase()))), [items, dir, q]);
  const totals = useMemo(() => { const t: Record<string, {in: bigint; out: bigint}> = {}; for (const x of items as any[]) { const k = x.currency; t[k] ??= {in: 0n, out: 0n}; if (x.kind === 'RECEIPT') t[k].in += cents(x.amount); else t[k].out += cents(x.amount); } return t; }, [items]);
  return <section className="cd-card"><header className="cd-cardHead"><div><h4>{title}</h4><small>{items.length} mouvement(s){Object.entries(totals).map(([c, t]) => ` · ${c === 'CDF' ? 'FC' : c} : +${money(fromCents(t.in), c as Cur)} / −${money(fromCents(t.out), c as Cur)}`).join('')}</small></div>
    <div className="cd-tools"><div className="cd-seg" role="group" aria-label="Sens">{([['ALL', 'Tout'], ['IN', 'Entrées'], ['OUT', 'Sorties']] as const).map(([k, l]) => <button key={k} type="button" aria-pressed={dir === k} className={dir === k ? 'on' : ''} onClick={() => setDir(k)}>{l}</button>)}</div>
      <label className="cd-search"><NavGlyph g="search" size={15}/><input value={q} onChange={e => setQ(e.target.value)} placeholder="Reçu, libellé…" aria-label="Rechercher un mouvement"/></label></div></header>
    <div className="cd-table" role="table" aria-label={title}><div className="cd-row cd-th" role="row"><span>Heure</span><span>Opération</span><span>Référence</span><span>Montant</span><span/></div>
      {rows.map((x: any, i) => <div className={`cd-row${x.reversed ? ' void' : ''}${x.pending ? ' cd-pending' : ''}`} role="row" key={i}>
        <span>{new Date(x.created_at).toLocaleTimeString('fr-FR')}</span>
        <span><em className={`cd-chip ${x.kind === 'RECEIPT' ? 'in' : 'out'}`}>{x.kind === 'RECEIPT' ? (x.reversed ? 'Entrée contre-opérée' : 'Entrée') : KIND[x.kind] ?? x.kind}</em></span>
        <span>{x.reference}</span><span className={x.kind === 'RECEIPT' ? 'cd-in' : 'cd-out'}>{x.kind === 'RECEIPT' ? '+' : '−'}{money(x.amount, x.currency)}</span>
        <span>{canReverse && onReverse && x.kind === 'RECEIPT' && !x.reversed && x.payment_id && <button type="button" className="cd-link" onClick={() => onReverse(x.payment_id, x.reference)}>Contre-opération</button>}</span></div>)}
      {rows.length === 0 && <p className="cd-empty">{items.length ? 'Aucun mouvement dans ce filtre.' : 'Aucun mouvement pour le moment.'}</p>}</div></section>;
}

function OpenDialog({token, onClose, onDone}: {token: string; onClose: () => void; onDone: () => Promise<void>}) {
  const [cdf, setCdf] = useState('0'); const [usd, setUsd] = useState('0'); const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const bad = !validAmount(cdf) || !validAmount(usd);
  async function go() { if (bad) { setErr('Montants en chiffres (0 si la caisse est vide).'); return; }
    try { setBusy(true); setErr(''); const res: any = await cashOpen(token, cdf.replace(',', '.'), usd.replace(',', '.')); toast.success(res?.offline_queued ? 'Hors connexion : ouverture de caisse enregistrée sur cet appareil. Vous pouvez encaisser.' : 'Caisse ouverte : vous pouvez encaisser.'); await onDone(); }
    catch (e) { const m = friendlyError(e); if (/déjà ouverte/i.test(m)) { toast.info('Votre caisse était déjà ouverte : elle est affichée.'); await onDone(); return; } setErr(m); } finally { setBusy(false); } }
  return <Modal title="Ouvrir ma caisse" sub="Indiquez l’argent présent dans la caisse au départ (fond initial)." onClose={onClose}
    foot={<><button type="button" className="cd-btn" onClick={onClose}>Annuler</button><button type="button" className="cd-btn primary" disabled={busy || bad} onClick={() => void go()}>{busy ? 'Ouverture…' : 'Ouvrir ma caisse'}</button></>}>
    {err && <div className="error" role="alert">{err}</div>}
    <div className="cd-grid2"><label className="cd-field"><span>Fond initial CDF</span><input inputMode="decimal" value={cdf} onChange={e => setCdf(e.target.value)} aria-invalid={!validAmount(cdf)} autoFocus/></label>
      <label className="cd-field"><span>Fond initial USD</span><input inputMode="decimal" value={usd} onChange={e => setUsd(e.target.value)} aria-invalid={!validAmount(usd)}/></label></div>
  </Modal>;
}

function CloseDialog({token, session, onClose, onDone}: {token: string; session: CashSession; onClose: () => void; onDone: () => Promise<void>}) {
  const [cdf, setCdf] = useState(''); const [usd, setUsd] = useState(''); const [note, setNote] = useState(''); const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const line = (c: Cur, v: string) => { const exp = cents(session[c.toLowerCase() as 'cdf'].expected_cash); const counted = v.trim() === '' ? exp : cents(v); return {exp, counted, diff: counted - exp, ok: v.trim() === '' || validAmount(v)}; };
  const L = {CDF: line('CDF', cdf), USD: line('USD', usd)};
  const gap = L.CDF.diff !== 0n || L.USD.diff !== 0n;
  async function go() {
    if (!L.CDF.ok || !L.USD.ok) { setErr('Montants comptés en chiffres.'); return; }
    if (gap && note.trim().length < 3) { setErr('Il y a un écart : expliquez-le dans la note (3 caractères au moins).'); return; }
    try { setBusy(true); setErr(''); const res: any = await cashClose(token, fromCents(L.CDF.counted), fromCents(L.USD.counted), note.trim() || undefined);
      toast.success(res?.offline_queued ? 'Hors connexion : clôture enregistrée sur cet appareil, envoyée après les encaissements du jour.' : gap ? 'Caisse clôturée avec un écart noté.' : 'Caisse clôturée : comptage conforme.'); await onDone(); }
    catch (e) { setErr(friendlyError(e)); } finally { setBusy(false); }
  }
  return <Modal title="Clôturer ma caisse" sub="Comptez l’argent réellement présent. Laissez vide si le montant est exactement le solde théorique." onClose={onClose}
    foot={<><button type="button" className="cd-btn" onClick={onClose}>Annuler</button><button type="button" className="cd-btn danger" disabled={busy} onClick={() => void go()}>{busy ? 'Clôture…' : 'Clôturer ma caisse'}</button></>}>
    {err && <div className="error" role="alert">{err}</div>}
    <div className="cd-count">{(['CDF', 'USD'] as Cur[]).map(c => <div key={c}>
      <label className="cd-field"><span>Compté {c}</span><input inputMode="decimal" placeholder={session[c.toLowerCase() as 'cdf'].expected_cash} value={c === 'CDF' ? cdf : usd} onChange={e => (c === 'CDF' ? setCdf : setUsd)(e.target.value)} aria-invalid={!L[c].ok}/></label>
      <p>Théorique <b>{money(fromCents(L[c].exp), c)}</b> · Écart <b className={L[c].diff === 0n ? 'cd-in' : 'cd-out'}>{L[c].diff > 0n ? '+' : ''}{money(fromCents(L[c].diff), c)}</b></p></div>)}</div>
    <label className="cd-field"><span>Note de clôture {gap ? '(obligatoire : écart constaté)' : '(facultatif)'}</span><textarea rows={2} maxLength={500} value={note} onChange={e => setNote(e.target.value)}/></label>
  </Modal>;
}

const PRESETS: Array<[string, string, () => [string, string]]> = [
  ['today', 'Aujourd’hui', () => { const d = iso(new Date()); return [d, d]; }],
  ['7', '7 derniers jours', () => { const z = new Date(); const a = new Date(); a.setDate(z.getDate() - 6); return [iso(a), iso(z)]; }],
  ['month', 'Ce mois', () => { const z = new Date(); return [iso(new Date(z.getFullYear(), z.getMonth(), 1)), iso(z)]; }],
  ['last', 'Mois dernier', () => { const z = new Date(); return [iso(new Date(z.getFullYear(), z.getMonth() - 1, 1)), iso(new Date(z.getFullYear(), z.getMonth(), 0))]; }],
];

function PastSessions({token, can, schoolName, reloadKey}: {token: string; can: (p: string) => boolean; schoolName?: string; reloadKey: string}) {
  const [preset, setPreset] = useState('month'); const [range, setRange] = useState<[string, string]>(PRESETS[2][2]());
  const [status, setStatus] = useState(''); const [cashier, setCashier] = useState(''); const [page, setPage] = useState(0);
  const [data, setData] = useState<CashSessionsPage | null>(null); const [err, setErr] = useState(''); const [open, setOpen] = useState<CashSessionRow | null>(null);
  const PAGE = 20;
  useEffect(() => { let alive = true; setErr('');
    cashSessions(token, {start: range[0], end: range[1], status: status || undefined, membership_id: cashier || undefined, limit: PAGE, offset: page * PAGE})
      .then(d => { if (alive) setData(d); }).catch(e => { if (alive) setErr(friendlyError(e)); });
    return () => { alive = false; }; }, [token, range[0], range[1], status, cashier, page, reloadKey]);
  const cashiers = useMemo(() => [...new Map((data?.items ?? []).map(s => [s.membership_id, s.cashier_name])).entries()], [data]);
  async function exportPeriod() { try { const b = await cashSessionsXlsx(token, {start: range[0], end: range[1], status: status || undefined, membership_id: cashier || undefined});
    await exportManaged(b, {school: schoolName ?? 'École', module: 'Centre financier', category: 'Caisse', filename: `caisses_${range[0]}_${range[1]}.xlsx`}); toast.success('Historique des caisses exporté en Excel'); }
    catch (e) { toast.error(friendlyError(e)); } }
  return <section className="cd-card">
    <header className="cd-cardHead"><div><h4>Caisses passées</h4><small>{data ? `${data.total} caisse(s) du ${dayFr(data.start)} au ${dayFr(data.end)}${data.all_cashiers ? ' · tous les caissiers' : ' · vos caisses'}` : 'Chargement…'}</small></div>
      {can('finance.cash.journal.export') && <button type="button" className="cd-btn" onClick={() => void exportPeriod()} disabled={!data?.total}><NavGlyph g="sheet" size={17}/>Exporter la période</button>}</header>
    <div className="cd-filters">
      <div className="cd-seg" role="group" aria-label="Période">{PRESETS.map(([k, l, f]) => <button key={k} type="button" aria-pressed={preset === k} className={preset === k ? 'on' : ''} onClick={() => { setPreset(k); setRange(f()); setPage(0); }}>{l}</button>)}</div>
      <label className="cd-field inline"><span>Du</span><input type="date" value={range[0]} max={range[1]} onChange={e => { setPreset('custom'); setRange([e.target.value, range[1]]); setPage(0); }}/></label>
      <label className="cd-field inline"><span>Au</span><input type="date" value={range[1]} min={range[0]} onChange={e => { setPreset('custom'); setRange([range[0], e.target.value]); setPage(0); }}/></label>
      <label className="cd-field inline"><span>Statut</span><select value={status} onChange={e => { setStatus(e.target.value); setPage(0); }}><option value="">Toutes</option><option value="OPEN">Ouvertes</option><option value="CLOSED">Clôturées</option></select></label>
      {data?.all_cashiers && <label className="cd-field inline"><span>Caissier</span><select value={cashier} onChange={e => { setCashier(e.target.value); setPage(0); }}><option value="">Tous</option>{cashiers.map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select></label>}
    </div>
    {err && <div className="error" role="alert">{err}</div>}
    <div className="cd-table" role="table" aria-label="Caisses passées">
      <div className="cd-row cd-sess cd-th" role="row"><span>Journée</span><span>Caissier</span><span>Horaire</span><span>Entrées</span><span>Sorties</span><span>Solde</span><span>Écart</span><span>Statut</span></div>
      {(data?.items ?? []).map(s => { const v = [s.cdf.variance, s.usd.variance].filter(x => x != null && cents(x) !== 0n);
        return <button type="button" className="cd-row cd-sess" role="row" key={s.id} onClick={() => setOpen(s)}>
          <span><b>{dayFr(s.business_date)}</b></span><span>{s.cashier_name}</span><span>{hm(s.opened_at)} → {s.closed_at ? hm(s.closed_at) : '…'}</span>
          <span className="cd-in">{money(s.cdf.receipts, 'CDF')}{cents(s.usd.receipts) ? <small>{money(s.usd.receipts, 'USD')}</small> : null}</span>
          <span className="cd-out">{money(outflow(s.cdf), 'CDF')}{cents(outflow(s.usd)) ? <small>{money(outflow(s.usd), 'USD')}</small> : null}</span>
          <span><b>{money(s.cdf.expected_cash, 'CDF')}</b>{cents(s.usd.expected_cash) ? <small>{money(s.usd.expected_cash, 'USD')}</small> : null}</span>
          <span>{s.status !== 'CLOSED' ? '—' : v.length ? <em className="cd-chip out">Écart</em> : <em className="cd-chip in">Conforme</em>}</span>
          <span><em className={`cd-chip ${s.status === 'OPEN' ? 'live' : ''}`}>{s.status === 'OPEN' ? 'Ouverte' : 'Clôturée'}</em></span></button>; })}
      {data && data.items.length === 0 && <p className="cd-empty">Aucune caisse sur cette période.</p>}
      {!data && !err && <div className="cd-skel"><i/><i/><i/></div>}
    </div>
    {data && data.total > PAGE && <nav className="cd-pager" aria-label="Pages"><button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>‹ Précédent</button><span>Page {page + 1} / {Math.ceil(data.total / PAGE)}</span><button type="button" disabled={(page + 1) * PAGE >= data.total} onClick={() => setPage(page + 1)}>Suivant ›</button></nav>}
    {open && <SessionDrawer token={token} can={can} session={open} schoolName={schoolName} onClose={() => setOpen(null)}/>}
  </section>;
}

function SessionDrawer({token, can, session: row, schoolName, onClose}: {token: string; can: (p: string) => boolean; session: CashSessionRow; schoolName?: string; onClose: () => void}) {
  const [j, setJ] = useState<Awaited<ReturnType<typeof cashJournal>> | null>(null); const [err, setErr] = useState('');
  useEffect(() => { cashJournal(token, row.id).then(setJ).catch(e => setErr(friendlyError(e))); }, [token, row.id]);
  // The journal call returns the session as it is NOW (closed meanwhile, new expense…): it wins over the list line.
  const session: CashSessionRow = j ? {...row, ...(j.session as CashSessionRow), cashier_name: row.cashier_name} : row;
  return <Modal title={`Caisse du ${dayFr(session.business_date)}`} sub={`${session.cashier_name} · ${hm(session.opened_at)} → ${session.closed_at ? hm(session.closed_at) : 'en cours'} · ${session.status === 'OPEN' ? 'Ouverte' : 'Clôturée'}`} onClose={onClose}
    foot={<>{can('finance.cash.journal.export') && <><button type="button" className="cd-btn" onClick={() => void exportSession(token, session.id, 'pdf', schoolName)}><NavGlyph g="doc" size={17}/>Journal PDF</button>
      <button type="button" className="cd-btn" onClick={() => void exportSession(token, session.id, 'xlsx', schoolName, session.business_date)}><NavGlyph g="sheet" size={17}/>Excel</button></>}<button type="button" className="cd-btn primary" onClick={onClose}>Fermer</button></>}>
    <div className="cd-sumTable" role="table" aria-label="Synthèse"><div className="cd-srow cd-th"><span>Devise</span><span>Fond</span><span>Entrées</span><span>Sorties</span><span>Théorique</span><span>Compté</span><span>Écart</span></div>
      {(['CDF', 'USD'] as Cur[]).map(c => { const x = session[c.toLowerCase() as 'cdf']; return <div className="cd-srow" key={c}><span><b>{c === 'CDF' ? 'FC' : 'USD'}</b></span><span>{money(x.opening, c)}</span><span>{money(x.receipts, c)}</span><span>{money(outflow(x), c)}</span>
        <span><b>{money(x.expected_cash, c)}</b></span><span>{x.counted != null ? money(x.counted, c) : '—'}</span><span className={x.variance && cents(x.variance) !== 0n ? 'cd-out' : ''}>{x.variance != null ? money(x.variance, c) : '—'}</span></div>; })}</div>
    {session.close_note && <p className="cd-note"><b>Note de clôture :</b> {session.close_note}</p>}
    {err && <div className="error" role="alert">{err}</div>}
    {j ? <SessionJournal items={j.items} canReverse={false} title="Journal"/> : !err && <div className="cd-skel"><i/><i/></div>}
  </Modal>;
}

/** Supervisors (finance.cash.other.read): every cashier's session of a day, then the school's day (closure, PDFs). */
function Supervision({token, can}: {token: string; can: (p: string) => boolean}) {
  const [day, setDay] = useState(iso(new Date())); const [global, setGlobal] = useState<any>(null); const [err, setErr] = useState('');
  useEffect(() => { if (!can('finance.cash.other.read')) return; setErr(''); cashDaySummary(token, day).then(setGlobal).catch(e => setErr(friendlyError(e))); }, [token, day]);
  const row = (currency: Cur, x: any) => <tr key={currency}><th>{currency}</th><td>{money(x.opening, currency)}</td><td>{money(x.receipts, currency)}</td>
    <td>{money(fromCents(cents(x.expenses) + cents(x.reversals) + cents(x.supervisor_reversals)), currency)}</td><td><b>{money(x.expected_cash, currency)}</b></td></tr>;
  return <section className="cd-card cd-superCard">
    <header className="cd-cardHead"><div><h4>Supervision des caisses</h4><small>Contrôle autorisé : toutes les caisses de l’école pour la journée choisie.</small></div>
      <label className="cd-field inline"><span>Journée</span><input type="date" value={day} max={iso(new Date())} onChange={e => setDay(e.target.value)}/></label></header>
    {err && <div className="error" role="alert">{err}</div>}
    {can('finance.cash.other.read') && global && <div className="cashGlobal"><b>Situation globale des caisses</b> <small>{global.open_count} ouverte(s) · {global.closed_count} clôturée(s)</small>
      <div className="cashTableWrap"><table className="cashSummaryTable"><thead><tr><th>Devise</th><th>Fonds initiaux</th><th>Entrées</th><th>Sorties</th><th>Solde théorique global</th></tr></thead>
        <tbody>{row('CDF', global.currencies.CDF)}{row('USD', global.currencies.USD)}</tbody></table></div></div>}
    <SchoolDayPanel token={token} can={can} day={day}/>
  </section>;
}
