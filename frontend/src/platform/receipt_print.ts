const AGENT = 'http://127.0.0.1:47319/v1';
const STORAGE_KEY = 'edusync.receipt-print.key';
const VALID_KEY = /^[a-f0-9]{64}$/;
let submitting = false;

export function receiptPrintKey(): string {
  try { return localStorage.getItem(STORAGE_KEY) ?? ''; }
  catch { return ''; }
}

export function saveReceiptPrintKey(key: string) {
  if (!VALID_KEY.test(key)) throw new Error('Saisissez la clé de liaison du poste.');
  localStorage.setItem(STORAGE_KEY, key);
}

export function removeReceiptPrintKey() {
  localStorage.removeItem(STORAGE_KEY);
}

async function agentRequest(path: string, key: string, body?: Blob) {
  if (!VALID_KEY.test(key)) throw new Error('Clé de liaison du poste invalide.');
  return fetch(AGENT + path, {
    method: body ? 'POST' : 'GET',
    headers: {Authorization: `Bearer ${key}`, ...(body && {'Content-Type': 'application/pdf'})},
    body,
    cache: 'no-store',
    credentials: 'omit',
    redirect: 'error',
    signal: AbortSignal.timeout(body ? 35_000 : 5_000),
  });
}

export async function checkReceiptPrinter(key: string): Promise<string> {
  const res = await agentRequest('/status', key);
  if (!res.ok) throw new Error('Agent indisponible ou clé de liaison incorrecte.');
  const data = await res.json();
  if (data.status !== 'ready' || typeof data.printer !== 'string') throw new Error('Réponse de l’agent invalide.');
  return data.printer;
}

export function browserReceiptPrint(blob: Blob, onError: () => void) {
  const url = URL.createObjectURL(blob);
  const frame = document.createElement('iframe');
  frame.title = 'Reçu à imprimer';
  frame.style.cssText = 'position:fixed;width:1px;height:1px;left:-10000px';
  let done = false;
  const cleanup = () => {
    if (done) return;
    done = true;
    clearTimeout(timer);
    setTimeout(() => { frame.remove(); URL.revokeObjectURL(url); }, 1000);
  };
  const fail = () => { cleanup(); onError(); };
  const timer = setTimeout(cleanup, 120_000);
  frame.onload = () => {
    try {
      const target = frame.contentWindow;
      if (!target) { fail(); return; }
      target.addEventListener('afterprint', cleanup, {once: true});
      target.focus();
      target.print();
    } catch { fail(); }
  };
  frame.onerror = fail;
  frame.src = url;
  document.body.appendChild(frame);
}

export async function printReceiptOnWorkstation(
  loadPdf: () => Promise<Blob>,
  onBrowserError: () => void,
): Promise<string | null> {
  const key = receiptPrintKey();
  if (!key) {
    browserReceiptPrint(await loadPdf(), onBrowserError);
    return null;
  }
  if (submitting) throw new Error('Une impression est déjà en cours sur ce poste.');
  submitting = true;
  try {
    let printer: string;
    try { printer = await checkReceiptPrinter(key); }
    catch { throw new Error('Agent de caisse indisponible. Lancez-le ou utilisez l’aperçu pour imprimer.'); }
    const pdf = await loadPdf();
    let response: Response;
    try { response = await agentRequest('/print', key, pdf); }
    catch { throw new Error('Envoi non confirmé. Vérifiez l’imprimante avant de réessayer.'); }
    if (response.status === 409) throw new Error('L’agent traite déjà une impression sur ce poste.');
    if (!response.ok) throw new Error('Envoi non confirmé. Vérifiez l’imprimante avant de réessayer.');
    const result = await response.json().catch(() => null);
    if (result?.status !== 'submitted') throw new Error('Envoi non confirmé. Vérifiez l’imprimante avant de réessayer.');
    return `Reçu envoyé à « ${printer} ». Vérifiez la sortie papier.`;
  } finally { submitting = false; }
}
