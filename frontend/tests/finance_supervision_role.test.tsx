// @vitest-environment jsdom
import React from 'react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, render, screen} from '@testing-library/react';
import FinancePage from '../src/finance';

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
    items: [],
    total: {expected: 0, regularized_total: 0, recovery_rate: 0, remaining: 0},
    currencies: {CDF: {opening: 0, receipts: 0, expenses: 0, reversals: 0, supervisor_reversals: 0, expected_cash: 0}, USD: {opening: 0, receipts: 0, expenses: 0, reversals: 0, supervisor_reversals: 0, expected_cash: 0}},
    open_count: 0,
    closed_count: 0,
  }), {headers: {'Content-Type': 'application/json'}})));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('governance/finance readers land on supervision, never on an operational checkout', () => {
  render(<FinancePage token="t" permissions={[
    'finance.recovery.monthly.read',
    'finance.cash.read',
    'finance.cash.other.read',
    'finance.reports.history.read',
    'finance.analysis.by_fee.read',
    'finance.decisions.read',
  ]}/>);
  expect(screen.queryByRole('button', {name: 'Encaissement'})).toBeNull();
  expect(screen.getByText('Vue de supervision')).toBeTruthy();
  expect(screen.getByRole('button', {name: 'Recouvrement'}).className).toContain('active');
  expect(screen.getByText(/Supervision financière/)).toBeTruthy();
});

it('cashier/operator keeps the operational checkout as the first finance screen', () => {
  render(<FinancePage token="t" permissions={[
    'finance.checkout.collect',
    'finance.cash.read',
    'finance.cash.open',
  ]}/>);
  expect(screen.getByRole('button', {name: 'Encaissement'}).className).toContain('active');
  expect(screen.getByText('Caisse personnelle')).toBeTruthy();
  expect(screen.getByText(/Encaissement terrain rapide/)).toBeTruthy();
});

it('gestionnaire contract is supervision-only even when all of its finance read permissions are present', () => {
  render(<FinancePage token="t" permissions={[
    'finance.cash.read',
    'finance.cash.other.read',
    'finance.recovery.monthly.read',
    'finance.reports.history.read',
    'finance.analysis.by_fee.read',
    'finance.decisions.read',
    'finance.responsibility.read',
    'finance.credits.read',
  ]}/>);
  expect(screen.getByText('Vue de supervision')).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Encaissement'})).toBeNull();
  expect(screen.queryByText('Encaissement terrain rapide, sécurisé et sans mélange de devises.')).toBeNull();
  expect(screen.getByRole('button', {name: 'Caisse'})).toBeTruthy();
  expect(screen.getByRole('button', {name: 'Rapports'})).toBeTruthy();
  expect(screen.getByRole('button', {name: 'Décisions financières'})).toBeTruthy();
});
