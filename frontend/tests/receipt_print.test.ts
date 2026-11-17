// @vitest-environment jsdom
import {afterEach, expect, it, vi} from 'vitest';
import {printReceiptOnWorkstation, saveReceiptPrintKey} from '../src/platform/receipt_print';

afterEach(() => { localStorage.clear(); vi.unstubAllGlobals(); });
const key = '1a'.repeat(32);
const pdf = new Blob(['%PDF-'], {type: 'application/pdf'});

it('checks the configured workstation and sends one PDF without opening the browser dialog', async () => {
  saveReceiptPrintKey(key);
  const fetchAgent = vi.fn()
    .mockResolvedValueOnce(Response.json({status: 'ready', printer: 'Ticket 80'}))
    .mockResolvedValueOnce(Response.json({status: 'submitted'}));
  vi.stubGlobal('fetch', fetchAgent);
  const loadPdf = vi.fn(async () => pdf);
  const fallback = vi.fn();
  expect(await printReceiptOnWorkstation(loadPdf, fallback)).toContain('Vérifiez la sortie papier');
  expect(fetchAgent.mock.calls.map(([path]) => path)).toEqual([
    'http://127.0.0.1:47319/v1/status', 'http://127.0.0.1:47319/v1/print',
  ]);
  expect(fetchAgent.mock.calls[1][1]).toMatchObject({method: 'POST', body: pdf, redirect: 'error'});
  expect(loadPdf).toHaveBeenCalledTimes(1);
  expect(fallback).not.toHaveBeenCalled();
  expect(document.querySelector('iframe')).toBeNull();
});

it('does not request a receipt if the configured agent is unavailable', async () => {
  saveReceiptPrintKey(key);
  const loadPdf = vi.fn(async () => pdf);
  vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new TypeError()));
  await expect(printReceiptOnWorkstation(loadPdf, vi.fn())).rejects.toThrow('Agent de caisse indisponible');
  expect(loadPdf).not.toHaveBeenCalled();
});

it('reports an unknown submission without falling back and risking a second print', async () => {
  saveReceiptPrintKey(key);
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(Response.json({status: 'ready', printer: 'Ticket 80'}))
    .mockRejectedValueOnce(new TypeError()));
  const fallback = vi.fn();
  await expect(printReceiptOnWorkstation(async () => pdf, fallback)).rejects.toThrow('Envoi non confirmé');
  expect(fallback).not.toHaveBeenCalled();
  expect(document.querySelector('iframe')).toBeNull();
});
