// @vitest-environment jsdom
import React from 'react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PersonnelPage from '../src/personnel';

const managerPermissions = [
  'personnel.read',
  'personnel.summary.read',
  'personnel.functions.read',
  'personnel.assignments.read',
  'personnel.staff_children.read',
];

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const u = new URL(String(input), 'http://x');
    if (u.pathname.endsWith('/personnel/summary')) {
      return new Response(JSON.stringify({
        total: 28, active: 25, suspended: 1, left: 2, teachers: 18, administrative: 5,
        workers: 2, other: 0, active_assignments: 25, linked_accounts: 6, staff_children: 3,
      }), {headers: {'Content-Type': 'application/json'}});
    }
    if (u.pathname.endsWith('/personnel/catalog/functions')) {
      return new Response('[]', {headers: {'Content-Type': 'application/json'}});
    }
    if (u.pathname.endsWith('/personnel/scope-options')) {
      return new Response(JSON.stringify({sections: [], classes: []}), {headers: {'Content-Type': 'application/json'}});
    }
    if (u.pathname.endsWith('/personnel')) {
      return new Response(JSON.stringify({items: [], total: 0, limit: 200, offset: 0}), {headers: {'Content-Type': 'application/json'}});
    }
    return new Response(JSON.stringify({detail: 'unexpected'}), {status: 500, headers: {'Content-Type': 'application/json'}});
  }));
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('gestionnaire personnel is supervision/read-only: no create or mutation controls are exposed', async () => {
  render(<PersonnelPage token="t" permissions={managerPermissions} schoolName="École A"/>);
  await waitFor(() => expect(screen.getByText('Agents actifs')).toBeTruthy());
  expect(screen.getAllByText('25').length).toBeGreaterThan(0);
  expect(screen.queryByRole('button', {name: /Nouvel agent/i})).toBeNull();

  await userEvent.click(screen.getByRole('button', {name: /Fonctions & affectations/i}));
  expect(screen.queryByRole('button', {name: /Nouvelle fonction/i})).toBeNull();
  expect(screen.getByText(/Aucune fonction configurée/i)).toBeTruthy();
});
