// Settings audit 2026-11-06: summaries shown to the school administrator are worded correctly.
import {expect, it} from 'vitest';
import {unitLabel} from '../src/settings_contributions';
import {benefitRule} from '../src/settings_benefits';
import {stockState} from '../src/settings_products';
import type {SettingsProduct} from '../src/api';

it('contribution units take the French plural', () => {
  expect([unitLabel(1, 'pièce'), unitLabel(3, 'pièce'), unitLabel(2, 'rouleau'), unitLabel(2, 'kilos'), unitLabel(2, 'boîte de craie')])
    .toEqual(['pièce', 'pièces', 'rouleaux', 'kilos', 'boîte de craie']);
});

it('a benefit is summarised in one sentence', () => {
  expect(benefitRule('LARGE_FAMILY', {min_children: 5, max_beneficiaries: 0, discount_percent: '0', free_beneficiaries: 1})).toBe('1 enfant gratuit par famille dès 5 enfants inscrits');
  expect(benefitRule('STAFF_CHILD', {min_children: 0, max_beneficiaries: 2, discount_percent: '50', free_beneficiaries: 0})).toBe('50 % de réduction · 2 enfants max. par agent');
});

it('stock states: rupture at 0, low stock at the threshold', () => {
  const p = (quantity: string, low_threshold: string, stock_tracking = true) => ({id: 'p', code: 'P', label: 'Pull', currency: 'CDF', unit_price: '1', stock_tracking, enabled: true, version: 1, quantity, low_threshold}) as SettingsProduct;
  expect(stockState(p('0', '10')).label).toBe('Rupture');
  expect(stockState(p('10', '10')).label).toBe('Stock bas');
  expect(stockState(p('11', '10')).label).toBe('En stock');
  expect(stockState(p('5', '0', false)).label).toBe('Stock non suivi');
});
