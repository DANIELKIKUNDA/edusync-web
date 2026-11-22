import React, {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {Modal} from './account';
import {friendlyError, UserFacingError} from './errors';
import {NavGlyph} from './nav_icons';
import {OnlineActionButton} from './online_action';
import {changeSchoolModule, fetchSchoolModules, SWITCHABLE_MODULES, type SchoolModule, type SchoolModules} from './schools_api';
import './school_modules.css';

/* V2 lot 0 (owner 2026-11-22) — « Modules » card of the school sheet.
   V1 modules: included for every school (recorded, not switchable). Pedagogy (ACADEMIC): sold apart, activated or
   withdrawn here with a motif; the server asks for the confirmation code and keeps the history. */

const msg = (e: unknown) => (e instanceof UserFacingError ? e.message : friendlyError(e));
const day = (iso: string | null) => iso ? new Date(iso).toLocaleDateString('fr-FR', {day: '2-digit', month: 'short', year: 'numeric'}) : '';

function state(m: SchoolModule): {cls: string; text: string} {
  if (m.active) return {cls: 'sm-on', text: m.since ? `Actif depuis le ${day(m.since)}` : 'Actif'};
  if (m.entitlement_status === 'REVOKED') return {cls: 'sm-off', text: m.until ? `Retiré le ${day(m.until)}` : 'Retiré'};
  return {cls: 'sm-off', text: 'Non activé'};
}

export function SchoolModulesCard({token, schoolId, schoolActive, onChanged}: {token: string; schoolId: string; schoolActive: boolean; onChanged: () => void}) {
  const [d, setD] = useState<SchoolModules | null>(null);
  const [error, setError] = useState('');
  const [dialog, setDialog] = useState<null | {module: SchoolModule; kind: 'activate' | 'withdraw'}>(null);
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    const ctl = new AbortController(); setError('');
    fetchSchoolModules(token, schoolId, ctl.signal).then(setD).catch(e => { if (!ctl.signal.aborted) setError(msg(e)); });
    return () => ctl.abort();
  }, [token, schoolId, nonce]);

  if (error) return <section className="sc-card"><div className="sc-card-head"><h3>Modules</h3></div>
    <p className="sc-muted" role="alert">{error}</p>
    <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" onClick={() => setNonce(n => n + 1)}>Réessayer</button></section>;
  if (!d) return <section className="sc-card" aria-busy="true"><div className="sc-card-head"><h3>Modules</h3></div><i className="sc-skel" style={{width: '60%'}}/></section>;

  const sold = d.modules.filter(m => SWITCHABLE_MODULES.includes(m.code));
  const included = d.modules.filter(m => !SWITCHABLE_MODULES.includes(m.code) && m.active);
  const activeCount = d.modules.filter(m => m.active).length;
  return <section className="sc-card sm-card" aria-labelledby="sm-title">
    <div className="sc-card-head"><h3 id="sm-title">Modules</h3><span className="sc-muted">{activeCount} actif{activeCount > 1 ? 's' : ''}</span></div>

    <h4 className="sm-group">Vendus séparément</h4>
    <ul className="sm-sold">{sold.map(m => {
      const s = state(m);
      return <li key={m.code}>
        <span className={`sm-icon ${m.active ? 'sm-icon-on' : ''}`} aria-hidden="true"><NavGlyph g={m.active ? 'checkCircle' : 'layers'} size={18}/></span>
        <div className="sm-main">
          <b>{m.label}</b>
          <span className={`sm-state ${s.cls}`}>{s.text}</span>
          {m.reason && m.entitlement_status && <small className="sm-reason">Motif : {m.reason}</small>}
          {m.catalogue_status === 'DRAFT' && <small className="sm-draft">En préparation : activable pour essai, pas encore en vente.</small>}
        </div>
        {d.can_manage && <div className="sm-action">
          {m.active
            ? <OnlineActionButton type="button" className="sc-btn sc-btn-ghost sc-btn-sm sc-danger-text" onClick={() => setDialog({module: m, kind: 'withdraw'})}>Retirer</OnlineActionButton>
            : <OnlineActionButton type="button" className="sc-btn sc-btn-primary sc-btn-sm" disabled={!schoolActive}
                title={schoolActive ? undefined : 'Réactivez l’école avant d’activer un module'} onClick={() => setDialog({module: m, kind: 'activate'})}>Activer</OnlineActionButton>}
        </div>}
      </li>;
    })}</ul>

    <h4 className="sm-group">Inclus pour toutes les écoles</h4>
    <ul className="sm-included" aria-label="Modules inclus">{included.map(m => <li key={m.code}><NavGlyph g="check" size={14}/>{m.label}</li>)}</ul>
    {included.length === 0 && <p className="sc-muted">Aucun module inclus enregistré.</p>}

    {dialog && <ModuleDialog token={token} schoolId={schoolId} school={d.school.name} module={dialog.module} kind={dialog.kind}
      onClose={() => setDialog(null)} onDone={() => { setDialog(null); setNonce(n => n + 1); onChanged(); }}/>}
  </section>;
}

function ModuleDialog({token, schoolId, school, module, kind, onClose, onDone}: {token: string; schoolId: string; school: string; module: SchoolModule;
  kind: 'activate' | 'withdraw'; onClose: () => void; onDone: () => void}) {
  const [reason, setReason] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const activate = kind === 'activate';
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (reason.trim().length < 5) { setError('Indiquez le motif (au moins 5 caractères).'); return; }
    setBusy(true); setError('');
    try {
      await changeSchoolModule(token, schoolId, module.code, kind, reason.trim());
      toast.success(activate ? `${module.label} activé` : `${module.label} retiré`); onDone();
    } catch (err) { setError(msg(err)); } finally { setBusy(false); }
  }
  return <Modal title={activate ? 'Activer le module' : 'Retirer le module'} subtitle={`${module.label} · ${school}`} onClose={onClose}>
    <form className="sc-form" onSubmit={submit} noValidate>
      <p className="sc-hint">{activate
        ? 'L’école verra les écrans de ce module dès la prochaine ouverture d’EduSync. Un code de confirmation peut vous être demandé.'
        : 'Les écrans de ce module disparaissent pour l’école et le serveur refuse ses demandes. Ses données sont conservées ; le module peut être réactivé.'}</p>
      <div className="sc-field"><label htmlFor="sm-reason">Motif *</label>
        <textarea id="sm-reason" rows={3} value={reason} onChange={e => setReason(e.target.value)} maxLength={500}
          placeholder={activate ? 'Ex. : contrat signé le 22/11/2026' : 'Ex. : fin du contrat'}/></div>
      {error && <div className="es-alert es-alert-bad" role="alert">{error}</div>}
      <div className="es-modal-foot"><button type="button" className="es-btn es-btn-ghost" onClick={onClose}>Annuler</button>
        <button className={`es-btn ${activate ? 'es-btn-primary' : 'es-btn-danger'}`} disabled={busy}>{busy ? 'Traitement…' : activate ? 'Activer' : 'Retirer'}</button></div>
    </form></Modal>;
}
