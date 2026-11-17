import {useState} from 'react';
import {checkReceiptPrinter, receiptPrintKey, removeReceiptPrintKey, saveReceiptPrintKey} from './receipt_print';

export function ReceiptPrintSettings() {
  const [configured, setConfigured] = useState(() => !!receiptPrintKey());
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
    {configured ? <>
      <button type="button" className="es-btn" disabled={busy} onClick={() => void test(false)}>Vérifier la liaison</button>
      <button type="button" className="es-btn" disabled={busy} onClick={disable}>Désactiver l’impression directe</button>
    </> : <>
      <label>Clé de liaison de l’agent
        <input type="password" value={draft} onChange={e => setDraft(e.target.value)} autoComplete="off" spellCheck={false}/>
      </label>
      <button type="button" className="es-btn" disabled={busy || !draft.trim()} onClick={() => void test(true)}>Associer ce poste</button>
    </>}
    {message && <p role="status">{message}</p>}
  </fieldset>;
}
