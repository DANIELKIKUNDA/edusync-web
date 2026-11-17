import {useId, useState} from 'react';
import {NavGlyph} from './nav_icons';
import type {ReceiptFormat} from '../api';
import {checkReceiptPrinter, receiptPrintKey, removeReceiptPrintKey, saveReceiptPrintKey, receiptWorkstationFormat, saveReceiptWorkstationFormat} from './receipt_print';

export function ReceiptPrintSettings() {
  const [configured, setConfigured] = useState(() => !!receiptPrintKey());
  const [format, setFormat] = useState(receiptWorkstationFormat);
  const keyInputId = useId();
  const [keyVisible, setKeyVisible] = useState(false);
  const [draft, setDraft] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  async function test(save: boolean) {
    setBusy(true);
    setMessage('');
    try {
      const key = save ? draft.trim() : receiptPrintKey();
      const printer = await checkReceiptPrinter(key);
      if (save) {
        saveReceiptPrintKey(key);
        setConfigured(true);
        setDraft('');
        setKeyVisible(false);
      }
      setMessage(`Agent accessible · imprimante configurée : ${printer}.`);
    } catch {
      setMessage('Connexion impossible. Vérifiez la clé, le démarrage de l’agent et l’autorisation de réseau local du navigateur.');
    } finally { setBusy(false); }
  }

  function disable() {
    try {
      removeReceiptPrintKey();
      setConfigured(false);
      setMessage('Les reçus passeront par le dialogue d’impression du navigateur.');
    } catch { setMessage('Impossible de modifier la configuration de ce navigateur.'); }
  }

  return <fieldset className="receiptNumbering">
    <legend>Impression directe sur ce poste</legend>
    <p>Installez et lancez l’agent EduSync sur ce PC Windows. Le réglage est propre à ce profil de navigateur.</p>
    <label>Format des reçus sur ce poste
      <select value={format ?? ''} onChange={event => {
        const next = (event.target.value || undefined) as ReceiptFormat | undefined;
        try { saveReceiptWorkstationFormat(next); setFormat(next); setMessage('Format du poste enregistré.'); }
        catch { setMessage('Impossible d’enregistrer le format sur ce navigateur.'); }
      }}>
        <option value="">Réglage de l’école</option>
        <option value="80MM">Ticket thermique 80 mm</option>
        <option value="58MM">Ticket thermique 58 mm</option>
        <option value="A4">Feuille A4</option>
        <option value="A5">Feuille A5</option>
      </select>
    </label>
    {configured ? <>
      <button type="button" className="es-btn" disabled={busy} onClick={() => void test(false)}>Vérifier la liaison</button>
      <button type="button" className="es-btn" disabled={busy} onClick={disable}>Désactiver l’impression directe</button>
    </> : <>
      <div className="receiptPrintKey">
        <label htmlFor={keyInputId}>Clé de liaison de l’agent</label>
        <div className="receiptPrintKeyField">
          <input id={keyInputId} type={keyVisible ? 'text' : 'password'} value={draft}
            onChange={e => setDraft(e.target.value)} autoComplete="off" spellCheck={false} autoCapitalize="none"/>
          <button type="button" aria-controls={keyInputId}
            aria-label={keyVisible ? 'Masquer la clé de liaison' : 'Afficher la clé de liaison'}
            onClick={() => setKeyVisible(visible => !visible)}>
            <NavGlyph g={keyVisible ? 'eyeOff' : 'eye'} size={18}/>
          </button>
        </div>
      </div>
      <button type="button" className="es-btn" disabled={busy || !draft.trim()} onClick={() => void test(true)}>Associer ce poste</button>
    </>}
    {message && <p role="status">{message}</p>}
  </fieldset>;
}
