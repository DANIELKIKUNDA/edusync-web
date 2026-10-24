// @vitest-environment jsdom
// Owner decisions 2026-10-23 (items 8, 9, 11): the school home shows only the widgets the server lists for the member's
// effective capabilities, never a guessed profile; a failing screen or card never takes the rest of the page down.
import React from 'react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import HomePage from '../src/home';
import {ScreenBoundary, classifyScreenError} from '../src/platform/screen_boundary';
import type {AccessMe} from '../src/api';

const base: AccessMe = {membership_id: 'm', school_id: 's', role_label: 'Administrateur système école', permissions: [], scoped: [], roles: [],
  navigation: [{key: 'home', label: 'Accueil', icon: 'home'}, {key: 'access', label: 'Accès & rôles', icon: 'lock'}],
  widgets: [{id: 'access.members', title: 'Comptes et accès', module: 'access', priority: 10},
            {id: 'settings.academic_year', title: 'Année scolaire', module: 'settings', priority: 13}],
  actions: [{id: 'members.create', label: 'Ajouter un utilisateur', module: 'access'}]};
const answers: Record<string, unknown> = {
  '/api/v1/access/dashboard': {'access.members': {active: 7, inactive: 1, without_role: 2, expiring: 0}, 'settings.academic_year': {active: '2026-2027', years: []}},
};
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const path = new URL(String(input), 'http://x').pathname;
    if (!(path in answers)) return new Response('{"detail":"inattendu"}', {status: 500, headers: {'Content-Type': 'application/json'}});
    return new Response(JSON.stringify(answers[path]), {headers: {'Content-Type': 'application/json'}});
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('administrator: administration widgets only — no recovery chart, no student search', async () => {
  render(<HomePage token="t" me={base} schoolName="École A" userName="Admin" onNavigate={() => {}}/>);
  expect(screen.getByText(/Administrateur système école/)).toBeTruthy();
  await waitFor(() => expect(screen.getByText('2 sans rôle')).toBeTruthy());
  expect(screen.getByText('2026-2027')).toBeTruthy();
  expect(screen.queryByText(/Évolution du recouvrement/)).toBeNull();
  expect(screen.queryByText(/Rechercher un élève/)).toBeNull();
  expect(screen.getByRole('button', {name: 'Ajouter un utilisateur'})).toBeTruthy();
  const calls = (fetch as unknown as {mock: {calls: unknown[][]}}).mock.calls.map(c => String(c[0]));
  expect(calls.some(u => u.includes('recovery') || u.includes('fee-tracking') || u.includes('cash'))).toBe(false);   // no finance request at all
});

it('the shortcut and the recovery card appear only when the server lists them', async () => {
  answers['/api/v1/finance/recovery/monthly'] = {items: [{month_label: 'Sept.', recovery_rate: 40}], total: {expected: 100, regularized_total: 40, recovery_rate: 40, remaining: 60}};
  const me = {...base, role_label: 'Promoteur', widgets: [{id: 'finance.recovery', title: 'Évolution du recouvrement', module: 'finance', priority: 40}],
    actions: [{id: 'students.search', label: 'Rechercher un élève', module: 'students'}]};
  render(<HomePage token="t" me={me} schoolName="École A" userName="P" onNavigate={() => {}}/>);
  expect(screen.getByText('Évolution du recouvrement')).toBeTruthy();
  expect(screen.getByText(/Rechercher un élève/)).toBeTruthy();
});

it('one card failing shows its own error with Réessayer; the other cards stay', async () => {
  const me = {...base, widgets: [...base.widgets, {id: 'settings.readiness', title: 'Paramétrage de l’établissement', module: 'settings', priority: 12}]};
  render(<HomePage token="t" me={me} schoolName="École A" userName="Admin" onNavigate={() => {}}/>);
  await waitFor(() => expect(screen.getByText('2 sans rôle')).toBeTruthy());
  await waitFor(() => expect(screen.getAllByRole('alert').length).toBe(1));                 // readiness answered 500
  expect(screen.getByRole('button', {name: 'Réessayer'})).toBeTruthy();
});

function Boom(): React.ReactElement { throw new Error('render failure'); }
it('ScreenBoundary: a crashing screen keeps the navigation around it and can be retried', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  let crash = true;
  function Screen() { return crash ? <Boom/> : <p>Écran rétabli</p>; }
  render(<div><nav aria-label="Navigation principale"><button>Accueil</button></nav><ScreenBoundary label="test"><Screen/></ScreenBoundary></div>);
  expect(screen.getByRole('navigation', {name: 'Navigation principale'})).toBeTruthy();
  expect(screen.getByText('Cette partie n’a pas pu s’afficher')).toBeTruthy();
  crash = false;
  await userEvent.click(screen.getByRole('button', {name: 'Réessayer'}));
  expect(screen.getByText('Écran rétabli')).toBeTruthy();
});

it('classifies network, session, permission, not found, server and offline errors', () => {
  expect(classifyScreenError(new Error('Votre session a expiré. Reconnectez-vous.')).kind).toBe('session');
  expect(classifyScreenError(new Error('Vous n’avez pas l’autorisation d’effectuer cette action.')).kind).toBe('permission');
  expect(classifyScreenError(new Error('La donnée demandée est introuvable.')).kind).toBe('not_found');
  expect(classifyScreenError(new Error('Le service rencontre momentanément une difficulté.')).kind).toBe('server');
  expect(classifyScreenError(Object.assign(new Error('x'), {code: 'OFFLINE_NOT_CACHED'})).kind).toBe('offline');
  expect(classifyScreenError(new TypeError('Failed to fetch')).kind).toBe('network');
});
