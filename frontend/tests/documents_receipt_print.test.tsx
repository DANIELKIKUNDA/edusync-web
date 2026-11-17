// @vitest-environment jsdom
import React from 'react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DocumentsPage from '../src/documents';

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({items: []})));
});
afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
});

it('lets a cashier configure the workstation without school settings access', async () => {
  const user = userEvent.setup();
  render(<DocumentsPage token="test" schoolName="École" permissions={['documents.history.read', 'finance.receipts.print']}/>);
  expect(screen.queryByRole('tab', {name: 'Logo et impression'})).toBeNull();
  await user.click(screen.getByRole('tab', {name: 'Impression des reçus'}));
  expect(screen.getByRole('button', {name: 'Connecter mon imprimante'})).toBeTruthy();
  await user.selectOptions(screen.getByRole('combobox', {name: 'Format des reçus sur ce poste'}), '80MM');
  expect(localStorage.getItem('edusync.receipt-print.format')).toBe('80MM');
});

it('keeps workstation controls hidden for a receipts-only reader', () => {
  render(<DocumentsPage token="test" schoolName="École" permissions={['documents.history.read', 'finance.receipts.read']}/>);
  expect(screen.queryByRole('tab', {name: 'Impression des reçus'})).toBeNull();
});
