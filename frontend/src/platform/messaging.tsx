// Atelier Pro — Messagerie (EXTERNAL_MESSAGING_ARCHITECTURE.md §8). Technical / commercial supervision only:
// providers, worker and queue health, volumes and failure rates, SMS wallet of every school, audited manual credit.
// The platform never reads the body of a school message here.
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {friendlyError} from './errors';
import {
  STATE_LABEL, platformAdjust, platformCredit, platformLedger, platformMessagingStatus, platformTestSend, platformTestStatus, platformWallets,
  type ChannelState,
} from '../messaging_api';
import '../communications.css';

const fmt = (iso?: string | null) => iso ? new Date(iso).toLocaleString('fr-FR', {dateStyle: 'short', timeStyle: 'short'}) : '—';

export default function PlatformMessaging({token, canCredit}: {token: string; canCredit: boolean}) {
  const [status, setStatus] = useState<any>(null); const [wallets, setWallets] = useState<any[]>([]); const [error, setError] = useState('');
  const [selected, setSelected] = useState<any | null>(null); const [ledger, setLedger] = useState<any[]>([]);
  const [q, setQ] = useState('');
  const load = async () => {
    try { const [s, w] = await Promise.all([platformMessagingStatus(token), platformWallets(token)]); setStatus(s); setWallets(w.items); setError(''); }
    catch (e) { setError(friendlyError(e)); }
  };
  useEffect(() => { void load(); }, [token]);
  async function open(w: any) { setSelected(w); setLedger([]); try { setLedger((await platformLedger(token, w.school_id)).items); } catch (e) { toast.error(friendlyError(e)); } }
  async function test(channel: 'EMAIL' | 'PUSH') {
    try {
      const r = await platformTestSend(token, channel);
      toast.message(`Test ${channel === 'EMAIL' ? 'e-mail' : 'push'} mis en file`);
      for (let i = 0; i < 20; i++) {
        await new Promise(res => setTimeout(res, 1500));
        const s = (await platformTestStatus(token, r.message_id)).items;
        const final = s.find(x => ['SENT', 'DELIVERED', 'FAILED_PERMANENT', 'CANCELLED'].includes(x.status));
        if (final) { (final.status === 'SENT' || final.status === 'DELIVERED' ? toast.success : toast.error)(`Test : ${final.status}${final.last_error_code ? ` (${final.last_error_code})` : ''}`); return; }
      }
      toast.message('Test toujours en file : vérifiez la santé du worker');
    } catch (e) { toast.error(friendlyError(e)); }
  }
  if (error) return <div className="error" role="alert">{error}</div>;
  if (!status) return <div className="es-skeleton" aria-busy="true"><i/><i/><i/></div>;
  const prov = status.providers as Record<'sms' | 'email' | 'push', {provider: string; state: ChannelState}>;
  const filtered = wallets.filter(w => !q || w.name.toLowerCase().includes(q.toLowerCase()));
  return <div className="commPage">
    <div className="commGrid">
      <div className="commCard"><h3>Fournisseurs</h3>
        {(['sms', 'email', 'push'] as const).map(ch => <div key={ch} className="commSwitch"><span>
          <b>{ch === 'sms' ? 'SMS (Orange)' : ch === 'email' ? 'E-mail (SMTP)' : 'Push (Firebase)'}</b>
          <small>{STATE_LABEL[prov[ch].state]} · fournisseur : {prov[ch].provider}{status.failure_rate_24h?.[ch.toUpperCase()] ? ` · échecs 24 h : ${(status.failure_rate_24h[ch.toUpperCase()] * 100).toFixed(1)} %` : ''}</small></span></div>)}
        <div className="commActions"><button className="softBtn" onClick={() => void test('EMAIL')}>Tester l’e-mail (vers moi)</button>
          <button className="softBtn" onClick={() => void test('PUSH')}>Tester le push (mes appareils)</button></div>
        <small>Un fournisseur « simulé » n’est jamais une certification : seul un test réel valide un fournisseur.</small>
      </div>
      <div className="commCard"><h3>File d’envoi et worker</h3>
        <div className="commWalletRow"><div><b>{status.queue.due ?? 0}</b><small>à envoyer</small></div><div><b>{status.queue.processing ?? 0}</b><small>en cours</small></div>
          <div className={(status.queue.dead_7d ?? 0) > 0 ? 'low' : ''}><b>{status.queue.dead_7d ?? 0}</b><small>échecs définitifs (7 j)</small></div></div>
        <small>Dernier signal du worker : {fmt(status.worker_heartbeat)} · plus ancien envoi en attente : {fmt(status.queue.oldest_due)} · accusés à appliquer : {status.receipts_waiting}</small>
        <ul className="commLedger">{Object.entries(status.volumes_24h as Record<string, Record<string, number>>).map(([ch, st]) =>
          <li key={ch}><span>{ch}<small>{Object.entries(st).map(([k, n]) => `${k} ${n}`).join(' · ')}</small></span></li>)}
          {Object.keys(status.volumes_24h).length === 0 && <li><small>Aucun envoi sur les dernières 24 h.</small></li>}</ul>
      </div>
    </div>
    <div className="commCard"><h3>Portefeuilles SMS des écoles</h3>
      <input className="commSearch" value={q} onChange={e => setQ(e.target.value)} placeholder="Rechercher une école" aria-label="Rechercher une école"/>
      <ul className="commLedger">{filtered.map(w => <li key={w.school_id}>
        <span><b>{w.name}</b><small>{w.sms_enabled ? 'SMS activés' : 'SMS désactivés'} · consommés 30 j : {w.consumed_30d} · dernière recharge : {fmt(w.last_topup_at)}</small></span>
        <span className={w.low ? 'st-FAILED_RETRYABLE' : ''}><b>{w.available}</b> disponibles{w.reserved ? ` (${w.reserved} réservés)` : ''}</span>
        <button className="softBtn" onClick={() => void open(w)}>Détail</button></li>)}</ul>
    </div>
    {selected && <WalletDialog token={token} wallet={selected} ledger={ledger} canCredit={canCredit} onClose={() => setSelected(null)}
      onDone={async () => { await load(); await open(selected); }}/>}
  </div>;
}

function WalletDialog({token, wallet, ledger, canCredit, onClose, onDone}: {token: string; wallet: any; ledger: any[]; canCredit: boolean; onClose: () => void; onDone: () => Promise<void>}) {
  const [mode, setMode] = useState<'credit' | 'adjust'>('credit');
  const [qty, setQty] = useState(''); const [ref, setRef] = useState(''); const [reason, setReason] = useState(''); const [price, setPrice] = useState('');
  const [currency, setCurrency] = useState('USD'); const [paidOn, setPaidOn] = useState(''); const [dir, setDir] = useState<'CREDIT' | 'DEBIT'>('CREDIT'); const [busy, setBusy] = useState(false);
  async function submit() {
    const n = Number(qty);
    if (!Number.isInteger(n) || n <= 0) { toast.error('Quantité entière positive obligatoire'); return; }
    if (reason.trim().length < 5) { toast.error('Motif obligatoire (5 caractères au moins)'); return; }
    setBusy(true);
    try {
      if (mode === 'credit') {
        if (ref.trim().length < 2) { toast.error('Référence du paiement obligatoire'); setBusy(false); return; }
        await platformCredit(token, wallet.school_id, {quantity: n, reference: ref.trim(), reason: reason.trim(), paid_on: paidOn || undefined,
          commercial_price: price ? Number(price) : undefined, commercial_currency: price ? currency : undefined});
        toast.success(`${n} SMS crédités`);
      } else {
        await platformAdjust(token, wallet.school_id, {direction: dir, quantity: n, reason: reason.trim()});
        toast.success('Ajustement enregistré');
      }
      setQty(''); setRef(''); setReason(''); setPrice(''); await onDone();
    } catch (e) { toast.error(friendlyError(e)); } finally { setBusy(false); }
  }
  return <div className="es-modal-backdrop" role="dialog" aria-modal="true" aria-label={`Portefeuille SMS — ${wallet.name}`} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
    <div className="es-modal commCard" style={{maxWidth: 560, width: 'calc(100% - 32px)', maxHeight: '90vh', overflow: 'auto'}}>
      <h3>Portefeuille SMS — {wallet.name}</h3>
      <div className="commWalletRow"><div><b>{wallet.balance}</b><small>solde</small></div><div><b>{wallet.reserved}</b><small>réservés</small></div><div><b>{wallet.available}</b><small>disponibles</small></div></div>
      {canCredit && <>
        <div className="commTabs"><button className={mode === 'credit' ? 'active' : ''} onClick={() => setMode('credit')}>Recharge payée</button>
          <button className={mode === 'adjust' ? 'active' : ''} onClick={() => setMode('adjust')}>Ajustement</button></div>
        <label className="commField"><span>Quantité (unités SMS)</span><input inputMode="numeric" value={qty} onChange={e => setQty(e.target.value.replace(/\D/g, ''))} aria-label="Quantité"/></label>
        {mode === 'credit' ? <>
          <label className="commField"><span>Référence du paiement de l’école</span><input value={ref} onChange={e => setRef(e.target.value)} aria-label="Référence"/></label>
          <label className="commField"><span>Date du paiement</span><input type="date" value={paidOn} onChange={e => setPaidOn(e.target.value)} aria-label="Date du paiement"/></label>
          <div className="commActions"><label className="commField"><span>Prix payé (facultatif)</span><input inputMode="decimal" value={price} onChange={e => setPrice(e.target.value)} aria-label="Prix payé"/></label>
            <label className="commField"><span>Devise</span><select value={currency} onChange={e => setCurrency(e.target.value)} aria-label="Devise"><option>USD</option><option>CDF</option></select></label></div>
        </> : <label className="commField"><span>Sens</span><select value={dir} onChange={e => setDir(e.target.value as 'CREDIT' | 'DEBIT')} aria-label="Sens"><option value="CREDIT">Crédit</option><option value="DEBIT">Débit</option></select></label>}
        <label className="commField"><span>Motif (journalisé)</span><input value={reason} onChange={e => setReason(e.target.value)} aria-label="Motif"/></label>
        <small>Opération auditée ; un code de vérification récent vous sera demandé.</small>
        <div className="commActions"><button className="softBtn" onClick={onClose}>Fermer</button><button className="primaryBtn" disabled={busy} onClick={() => void submit()}>Enregistrer</button></div>
      </>}
      <h3>Mouvements</h3>
      <ul className="commLedger">{ledger.map(l => <li key={l.id}><span>{l.movement_type}<small>{fmt(l.created_at)}{l.reference ? ` · ${l.reference}` : ''}{l.actor ? ` · ${l.actor}` : ''}{l.reason ? ` · ${l.reason}` : ''}</small></span>
        <b className={l.direction === 'DEBIT' ? 'neg' : ''}>{l.direction === 'DEBIT' ? '−' : l.direction === 'CREDIT' ? '+' : ''}{l.quantity}</b></li>)}
        {ledger.length === 0 && <li><small>Aucun mouvement.</small></li>}</ul>
      {!canCredit && <div className="commActions"><button className="softBtn" onClick={onClose}>Fermer</button></div>}
    </div>
  </div>;
}
