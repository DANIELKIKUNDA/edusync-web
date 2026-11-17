import {timingSafeEqual} from 'node:crypto';
import {execFile} from 'node:child_process';
import {createServer} from 'node:http';
import {mkdtemp, readFile, rm, writeFile} from 'node:fs/promises';
import {dirname, isAbsolute, join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {promisify} from 'node:util';

const HOST = '127.0.0.1';
const PORT = 47319;
const MAX_PDF_BYTES = 16 * 1024 * 1024;
const KEY = /^[a-f0-9]{64}$/;
const execute = promisify(execFile);

function authorized(value, key) {
  const match = /^Bearer ([a-f0-9]{64})$/.exec(value ?? '');
  return !!match && timingSafeEqual(Buffer.from(match[1], 'hex'), Buffer.from(key, 'hex'));
}

export function createPrintServer({origin, key, printer, print, approvePairing}) {
  if (new URL(origin).origin !== origin || !origin.startsWith('https://') || !KEY.test(key) || !printer?.trim()) {
    throw new Error('Configuration du poste invalide.');
  }
  let busy = false;
  let pairing = false;
  let nextPairingAttempt = 0;
  return createServer({requestTimeout: 40_000, headersTimeout: 10_000}, async (request, response) => {
    const send = (status, data) => {
      response.writeHead(status, {'Content-Type': 'application/json', 'Cache-Control': 'no-store'});
      response.end(JSON.stringify(data));
    };
    if (request.headers.host !== `${HOST}:${PORT}` || request.headers.origin !== origin) {
      send(403, {status: 'forbidden'});
      return;
    }
    response.setHeader('Access-Control-Allow-Origin', origin);
    response.setHeader('Vary', 'Origin');
    const pairingRoute = approvePairing && request.url === '/v1/pair';
    if (request.method === 'OPTIONS' && (pairingRoute || ['/v1/status', '/v1/print'].includes(request.url))) {
      response.setHeader('Access-Control-Allow-Methods', 'GET, POST');
      response.setHeader('Access-Control-Allow-Headers', 'Authorization, Content-Type');
      response.setHeader('Access-Control-Allow-Private-Network', 'true');
      response.writeHead(204).end();
      return;
    }
    if (pairingRoute && request.method === 'POST') {
      if (request.headers['content-type'] !== 'application/json' ||
          request.headers['content-length'] !== '0' || request.headers['transfer-encoding']) {
        send(400, {status: 'invalid_request'});
        return;
      }
      if (pairing || Date.now() < nextPairingAttempt) {
        send(429, {status: 'pairing_busy'});
        return;
      }
      pairing = true;
      try {
        if (await approvePairing()) send(200, {status: 'paired', printer, key});
        else send(403, {status: 'pairing_denied'});
      } catch {
        if (!response.destroyed) send(503, {status: 'pairing_unavailable'});
      } finally {
        pairing = false;
        nextPairingAttempt = Date.now() + 3000;
      }
      return;
    }
    if (!authorized(request.headers.authorization, key)) {
      send(401, {status: 'unauthorized'});
      return;
    }
    if (request.method === 'GET' && request.url === '/v1/status') {
      send(200, {status: 'ready', printer});
      return;
    }
    if (request.method !== 'POST' || request.url !== '/v1/print') {
      send(404, {status: 'not_found'});
      return;
    }
    const length = Number(request.headers['content-length']);
    if (request.headers['content-type'] !== 'application/pdf' || !Number.isInteger(length)
        || length < 5 || length > MAX_PDF_BYTES) {
      send(400, {status: 'invalid_pdf'});
      return;
    }
    if (busy) {
      send(409, {status: 'busy'});
      return;
    }
    busy = true;
    try {
      const chunks = [];
      for await (const chunk of request) chunks.push(chunk);
      const pdf = Buffer.concat(chunks);
      if (!request.complete || pdf.length !== length || pdf.subarray(0, 5).toString() !== '%PDF-') {
        send(400, {status: 'invalid_pdf'});
        return;
      }
      await print(pdf);
      send(200, {status: 'submitted', printer});
    } catch {
      if (!response.destroyed) send(502, {status: 'unconfirmed'});
    } finally {
      busy = false;
    }
  });
}

async function start() {
  if (process.platform !== 'win32') throw new Error('Cet agent nécessite Windows.');
  const configPath = process.argv[2];
  if (!configPath) throw new Error('Chemin du fichier de configuration requis.');
  const config = JSON.parse((await readFile(configPath, 'utf8')).replace(/^\uFEFF/, ''));
  if (!isAbsolute(config.renderer) || !config.renderer.toLowerCase().endsWith('sumatrapdf.exe')) {
    throw new Error('Indiquez le chemin absolu vers SumatraPDF.exe.');
  }
  const approvePairing = config.interactivePairing === true ? async () => {
    try {
      await execute(join(dirname(process.execPath), 'EduSyncPrintConnector.exe'),
        ['--approve', config.origin], {timeout: 55_000, windowsHide: true});
      return true;
    } catch (error) {
      if (error.code === 2) return false;
      throw error;
    }
  } : undefined;
  const server = createPrintServer({...config, approvePairing, print: async pdf => {
    const directory = await mkdtemp(join(dirname(configPath), 'receipt-'));
    try {
      const file = join(directory, 'receipt.pdf');
      await writeFile(file, pdf, {flag: 'wx'});
      await execute(config.renderer, ['-silent', '-print-to', config.printer, '-print-settings', 'noscale', file],
                    {timeout: 25_000, windowsHide: true});
    } finally {
      await rm(directory, {recursive: true, force: true}).catch(() => {});
    }
  }});
  server.on('error', () => {
    console.error('Impossible de démarrer l’agent. Le port local est peut-être déjà occupé.');
    process.exitCode = 1;
  });
  server.listen(PORT, HOST, () => console.log('Agent EduSync prêt sur ce poste.'));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  start().catch(() => {
    console.error('Impossible de démarrer l’agent. Vérifiez Windows et le fichier de configuration.');
    process.exitCode = 1;
  });
}
