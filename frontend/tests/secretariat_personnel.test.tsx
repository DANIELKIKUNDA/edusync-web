// @vitest-environment jsdom
// Secrétariat / Caissier (2026-10-31): they create staff records (personnel.create) but neither read the function catalogue
// (personnel.functions.read) nor assign (personnel.assignments.add). The page used to call /personnel/catalog/functions
// anyway (server refusal 403) and offered an « Affectation initiale » the server would refuse.
import React from 'react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PersonnelPage from '../src/personnel';

const calls: string[] = [];
beforeEach(() => {
  calls.length = 0;
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const u = new URL(String(input), 'http://x'); calls.push(u.pathname);
    const body = u.pathname.endsWith('/personnel/scope-options') ? {schoolwide: true, sections: [], classes: []}
      : u.pathname.endsWith('/personnel/catalog/functions') ? [] : {items: [], total: 0, limit: 200, offset: 0};
    return new Response(JSON.stringify(body), {headers: {'Content-Type': 'application/json'}});
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('creates the record without asking for the function catalogue nor offering an assignment', async () => {
  render(<PersonnelPage token="t" schoolName="École A" permissions={['personnel.read', 'personnel.create', 'personnel.update']}/>);
  await userEvent.click(await screen.findByRole('button', {name: /Nouvel agent/}));
  expect(await screen.findByText(/le gestionnaire du personnel affectera ensuite l’agent/)).toBeTruthy();
  expect(screen.queryByText('Fonction initiale')).toBeNull();
  await waitFor(() => expect(calls.some(p => p.endsWith('/personnel/scope-options'))).toBe(true));
  expect(calls.some(p => p.endsWith('/personnel/catalog/functions'))).toBe(false);
});

it('the staff manager keeps the initial assignment', async () => {
  render(<PersonnelPage token="t" schoolName="École A" permissions={['personnel.read', 'personnel.create', 'personnel.functions.read', 'personnel.assignments.add']}/>);
  await userEvent.click(await screen.findByRole('button', {name: /Nouvel agent/}));
  expect(await screen.findByText('Fonction initiale')).toBeTruthy();
  expect(calls.some(p => p.endsWith('/personnel/catalog/functions'))).toBe(true);
});

it('« Le point du jour » tells the Secrétariat how many pupil files remain to complete (server count, whole school)', async () => {
  const {DailyBriefing} = await import('../src/home_briefing');
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({active_students: 40, profiles_to_complete: 30}), {headers: {'Content-Type': 'application/json'}})));
  render(<DailyBriefing token="t" widgets={[{id: 'students.files', module: 'students', title: 'Dossiers élèves à compléter'} as any]} open={() => {}}/>);
  expect(await screen.findByText('30 dossiers d’élève à compléter')).toBeTruthy();
  expect(screen.getByText(/25 % des dossiers sont complets/)).toBeTruthy();
});
