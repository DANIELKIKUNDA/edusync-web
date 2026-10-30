// @vitest-environment jsdom
// Intendant / Directeur des études / Directeur de discipline (2026-10-30): « Le point du jour » speaks to every
// steering role, not only to cash supervisors, and each backend capability has its button — nothing more.
import React from 'react';
import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, render, screen} from '@testing-library/react';
import {DailyBriefing} from '../src/home_briefing';
import StewardshipPage from '../src/stewardship';
import type {AccessWidget} from '../src/api';

const json = (body: unknown) => new Response(JSON.stringify(body), {headers: {'Content-Type': 'application/json'}});
function serve(routes: Record<string, unknown>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = new URL(String(url), 'http://x').pathname;
    const hit = Object.entries(routes).find(([k]) => path.endsWith(k));
    return hit ? json(hit[1]) : new Response('{}', {status: 404});
  }));
}
const w = (id: string, module: string): AccessWidget => ({id, module, title: id} as AccessWidget);
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('intendance: low stock is read as a list (rupture first), broken equipment and counts to validate are spoken', async () => {
  serve({
    '/stewardship/dashboard': {low_stock: [{label: 'Craie', quantity: 0, low_threshold: 5}, {label: 'Papier', quantity: 2, low_threshold: 10}],
      sale_stock: [], assets: [{status: 'GOOD', n: 10}, {status: 'TO_REPAIR', n: 2}, {status: 'IN_REPAIR', n: 1}], locations: []},
    '/stewardship/counts': {items: [{status: 'DRAFT', total_variance: 3}, {status: 'VALIDATED', total_variance: 0}]},
  });
  render(<DailyBriefing token="t" widgets={[w('inventory.stock', 'stewardship'), w('inventory.counts', 'stewardship')]} open={() => {}}/>);
  expect(await screen.findByText('1 article en rupture de stock')).toBeTruthy();
  expect(screen.getByText(/Craie, Papier/)).toBeTruthy();
  expect(screen.getByText('2 équipements hors d’usage')).toBeTruthy();
  expect(screen.getByText('1 inventaire en cours à valider')).toBeTruthy();
  expect(screen.getByText(/À retenir en priorité : 1 article en rupture/)).toBeTruthy();
});

it('directors: movements of the last 30 days and staff are spoken in plain language', async () => {
  const today = new Date().toISOString().slice(0, 10);
  serve({
    '/effectifs/movements': {items: [{event_type: 'ABANDON', effective_date: today, student_name: 'KABILA Jean', class_label: '3e A'},
      {event_type: 'TRANSFER', effective_date: today, student_name: 'MBUYI Anne', class_label: '4e B'}], total: 2},
    '/personnel/summary': {total: 12, active: 10, suspended: 1, left: 1, teachers: 7, administrative: 2, workers: 1, other: 0},
  });
  render(<DailyBriefing token="t" widgets={[w('headcounts.movements', 'headcounts'), w('personnel.summary', 'personnel')]} open={() => {}}/>);
  expect(await screen.findByText('1 abandon sur les 30 derniers jours')).toBeTruthy();
  expect(screen.getByText(/1 abandon · 1 transfert\. Le dernier : KABILA Jean \(3e A\)/)).toBeTruthy();
  expect(screen.getByText('10 agents en service')).toBeTruthy();
  expect(screen.getByText(/7 enseignant\(s\).*1 suspendu\(s\)/)).toBeTruthy();
});

it('intendance: export and printable sheets appear only with their own capability', async () => {
  serve({'/stewardship/dashboard': {low_stock: [], sale_stock: [], assets: [], locations: []}, '/stewardship/stock': {items: []}, '/stewardship/sale-stock': {items: []},
    '/stewardship/counts': {items: [{id: 'c1', code: 'INV-1', status: 'VALIDATED', line_count: 1, total_variance: 0}]}});
  const base = ['inventory.stock.read', 'inventory.counts.read'];
  const {unmount} = render(<StewardshipPage token="t" permissions={base}/>);
  (await screen.findByRole('tab', {name: 'Consommables'})).click();
  expect(screen.queryByRole('button', {name: 'Exporter en Excel'})).toBeNull();
  expect(screen.queryByRole('button', {name: 'Imprimer la fiche de stock'})).toBeNull();
  unmount();
  render(<StewardshipPage token="t" permissions={[...base, 'inventory.stock.export_xlsx', 'inventory.stock.sheet.print', 'inventory.counts.export']}/>);
  (await screen.findByRole('tab', {name: 'Consommables'})).click();
  expect(await screen.findByRole('button', {name: 'Exporter en Excel'})).toBeTruthy();
  expect(screen.getByRole('button', {name: 'Imprimer la fiche de stock'})).toBeTruthy();
  (await screen.findByRole('tab', {name: 'Inventaires physiques'})).click();
  expect(await screen.findByRole('button', {name: 'Exporter l’inventaire INV-1 en Excel'})).toBeTruthy();
  expect(screen.getByRole('button', {name: 'Imprimer l’inventaire INV-1'})).toBeTruthy();
});
