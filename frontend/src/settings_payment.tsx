// Règles d'encaissement — copied from the Desktop golden master (app/ui/settings_page.py::_build_payments,
// app/db/configuration.py::save_payment_policy, enforced by app/db/finance_checkout.py). All money received is recorded;
// the school chooses whether deposits are allowed (and their minimum), advance and future-month payments, accepted modes.
import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {getPaymentPolicy, putPaymentPolicy, type PaymentPolicy} from './api';
import {friendlyError} from './platform/errors';
import {FormField} from './platform/forms';

const MODES: [string, string][] = [['CASH', 'Espèces'], ['MOBILE_MONEY', 'Mobile Money'], ['BANQUE', 'Banque'], ['AUTRE', 'Autre']];

export function PaymentPolicySettings({token, can}: {token: string; can: (x: string) => boolean}) {
  const [p, setP] = useState<PaymentPolicy | null>(null); const [d, setD] = useState<PaymentPolicy | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function load() { try { const x = await getPaymentPolicy(token); setP(x); setD(x); } catch (e) { setError(friendlyError(e)); } }
  useEffect(() => { void load(); }, [token]);
  if (!d) return error ? <div className="error" role="alert">{error}</div> : null;
  const editable = can('settings.payment_policy.manage');
  const flag = (k: 'partial_payments_enabled' | 'advance_payments_enabled' | 'future_charge_payments_enabled') => (e: React.ChangeEvent<HTMLInputElement>) => setD({...d, [k]: e.target.checked});
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!d!.accepted_modes.length) { setError('Au moins un mode de paiement doit être autorisé.'); return; }
    if (!/^\d+([.,]\d{1,2})?$/.test(String(d!.partial_min_amount).trim())) { setError('Acompte minimum en chiffres, deux décimales au plus.'); return; }
    try {
      setBusy(true); setError('');
      await putPaymentPolicy(token, {partial_payments_enabled: d!.partial_payments_enabled, partial_min_amount: String(d!.partial_min_amount).replace(',', '.'),
        partial_reporting_mode: d!.partial_reporting_mode, advance_payments_enabled: d!.advance_payments_enabled,
        future_charge_payments_enabled: d!.future_charge_payments_enabled, accepted_modes: d!.accepted_modes, expected_version: p?.version ?? null});
      toast.success('Règles d’encaissement enregistrées'); await load();
    } catch (err) { setError(friendlyError(err)); } finally { setBusy(false); }
  }
  return <section className="panel">
    <div className="panelHead"><div><h3>Règles d’encaissement</h3><p>Tout argent reçu est enregistré. Ces règles s’appliquent à la caisse dès l’enregistrement.</p></div></div>
    {error && <div className="error" role="alert">{error}</div>}
    <form className="policyForm" onSubmit={save} noValidate><fieldset disabled={!editable || busy}>
      <label className="switchRow"><span>Autoriser les paiements partiels / acomptes<small>Sinon, chaque frais choisi doit être soldé en une fois.</small></span><input type="checkbox" role="switch" checked={d.partial_payments_enabled} onChange={flag('partial_payments_enabled')}/></label>
      {d.partial_payments_enabled && <FormField label="Acompte minimum (0 = aucun minimum)"><input inputMode="decimal" value={String(d.partial_min_amount)} onChange={e => setD({...d, partial_min_amount: e.target.value})}/></FormField>}
      <label className="switchRow"><span>Autoriser les paiements anticipés<small>Avance versée sur un plan de paiement anticipé.</small></span><input type="checkbox" role="switch" checked={d.advance_payments_enabled} onChange={flag('advance_payments_enabled')}/></label>
      <label className="switchRow"><span>Autoriser le paiement des mois futurs<small>Une mensualité dont l’échéance n’est pas encore arrivée.</small></span><input type="checkbox" role="switch" checked={d.future_charge_payments_enabled} onChange={flag('future_charge_payments_enabled')}/></label>
    </fieldset>
    <fieldset disabled={!editable || busy}><legend>Modes de paiement acceptés</legend>
      <div className="monthGrid">{MODES.map(([code, label]) => <label key={code} className="checkField"><input type="checkbox" checked={d.accepted_modes.includes(code)} onChange={e => setD({...d, accepted_modes: e.target.checked ? [...d.accepted_modes, code] : d.accepted_modes.filter(m => m !== code)})}/> {label}</label>)}</div>
    </fieldset>
    <p className="policyHint">Protection : même un acompte reste dans la caisse, le reçu, l’historique et l’audit.</p>
    {editable && <div className="stickyActions"><button className="primaryBtn" disabled={busy}>{busy ? 'Enregistrement…' : 'Enregistrer les règles d’encaissement'}</button></div>}
    </form>
  </section>;
}
