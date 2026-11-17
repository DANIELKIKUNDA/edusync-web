import type {ReceiptFormat} from '../api';

const AGENT = 'http://127.0.0.1:47319/v1';
const STORAGE_KEY = 'edusync.receipt-print.key';
const VALID_KEY = /^[a-f0-9]{64}$/;
let submitting = false;

const FORMAT_KEY = 'edusync.receipt-print.format';

export function receiptWorkstationFormat(): ReceiptFormat | undefined {
  try {
    const format = localStorage.getItem(FORMAT_KEY);
    switch (format) {
      case 'A4': case 'A5': case '80MM': case '58MM': return format;
      default: return undefined;
    }
  } catch { return undefined; }
}

export function saveReceiptWorkstationFormat(format: ReceiptFormat | undefined) {
  if (format) localStorage.setItem(FORMAT_KEY, format);
  else localStorage.removeItem(FORMAT_KEY);
}

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

export async function pairReceiptPrinter(): Promise<{key: string; printer: string}> {
  let response: Response;
  try {
    response = await fetch(AGENT + '/pair', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      cache: 'no-store',
      credentials: 'omit',
      redirect: 'error',
      signal: AbortSignal.timeout(60_000),
    });
  } catch {
    throw new Error('Ouvrez EduSync Print Connector et autorisez l’accès au réseau local dans le navigateur.');
  }
  if (response.status === 403) throw new Error('Association refusée sur ce poste.');
  if (response.status === 429) throw new Error('Une demande d’association est en cours ou vient de se terminer. Réessayez dans quelques secondes.');
  if (response.status === 401 || response.status === 404) {
    throw new Error('Cette version de l’agent utilise la liaison par clé.');
  }
  if (!response.ok) throw new Error('Impossible d’ouvrir la confirmation Windows.');
  const data = await response.json();
  if (data.status !== 'paired' || typeof data.key !== 'string' || !VALID_KEY.test(data.key) ||
      typeof data.printer !== 'string') throw new Error('Réponse du connecteur invalide.');
  return {key: data.key, printer: data.printer};
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

async function prepareReceiptPdf(loadPdf: (format?: ReceiptFormat) => Promise<Blob>, format?: ReceiptFormat) {
  const start = performance.now();
  try { return await loadPdf(format); }
  finally { performance.measure('edusync-receipt-pdf', {start, end: performance.now()}); }
}

export async function printReceiptOnWorkstation(
  loadPdf: (format?: ReceiptFormat) => Promise<Blob>,
  onBrowserError: () => void,
): Promise<string | null> {
  const key = receiptPrintKey();
  const format = receiptWorkstationFormat();
  if (!key) {
    browserReceiptPrint(await prepareReceiptPdf(loadPdf, format), onBrowserError);
    return null;
  }
  if (submitting) throw new Error('Une impression est déjà en cours sur ce poste.');
  submitting = true;
  try {
    const pdf = await prepareReceiptPdf(loadPdf, format);
    let response: Response;
    const start = performance.now();
    try { response = await agentRequest('/print', key, pdf); }
    catch { throw new Error('Envoi non confirmé. Vérifiez l’imprimante avant de réessayer.'); }
    finally { performance.measure('edusync-receipt-spool', {start, end: performance.now()}); }
    if (response.status === 401 || response.status === 403) throw new Error('La liaison avec l’agent est refusée. Vérifiez l’association de ce poste.');
    if (response.status === 409) throw new Error('L’agent traite déjà une impression sur ce poste.');
    if (!response.ok) throw new Error('Envoi non confirmé. Vérifiez l’imprimante avant de réessayer.');
    const result = await response.json().catch(() => null);
    if (result?.status !== 'submitted') throw new Error('Envoi non confirmé. Vérifiez l’imprimante avant de réessayer.');
    return `Reçu envoyé à « ${typeof result.printer === 'string' ? result.printer : 'imprimante du poste'} ». Vérifiez la sortie papier.`;
  } finally { submitting = false; }
}
