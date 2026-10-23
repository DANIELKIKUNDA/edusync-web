// @vitest-environment jsdom
// Lot 2026-10: one global window-title rule (no « EduSync » twice, no « Gestion scolaire », no technical id) and a
// confirmation before a VOLUNTARY sign-out, the same for every account menu and every role.
import React, {useState} from 'react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {pageLabel, pageTitle, windowTitle} from '../src/platform/navigation';
import {AppShell, type ShellAccount} from '../src/platform/shell';

function stubDisplayMode(standalone: boolean) {
  vi.stubGlobal('matchMedia', (q: string) => ({matches: standalone && q.includes('display-mode'), media: q, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false}));
}
beforeEach(() => {
  stubDisplayMode(false);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} unobserve() {} });
  vi.stubGlobal('requestAnimationFrame', (f: FrameRequestCallback) => { f(0); return 0; });
  vi.stubGlobal('cancelAnimationFrame', () => {});
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); document.title = ''; });

const ROUTES = ['Messagerie', 'Écoles', 'Utilisateurs & accès', 'Équipe plateforme', 'Notifications système', 'Journal d’audit', 'État du service'];

it('normalizes every platform route to « <page> — EduSync », once', () => {
  for (const r of ROUTES) {
    expect(pageTitle(r)).toBe(`${r} — EduSync`);
    expect(pageTitle(r).match(/EduSync/g)).toHaveLength(1);
  }
  expect(pageTitle('Push')).toBe('Push — EduSync');
  expect(pageTitle('EXCELLENCIA COLLÈGE RIZIKI')).toBe('EXCELLENCIA COLLÈGE RIZIKI — EduSync');
});

it('removes repetitions, « Gestion scolaire », technical ids and overlong labels', () => {
  expect(pageTitle('EduSync — Gestion scolaire - Push — EduSync')).toBe('Push — EduSync');
  expect(pageTitle('Push · EduSync')).toBe('Push — EduSync');
  expect(pageTitle('Envoi 0b7c3f0e-1111-4c2a-9e55-0123456789ab')).toBe('Envoi — EduSync');
  expect(pageTitle('')).toBe('Plateforme — EduSync');
  expect(pageLabel('x'.repeat(90)).length).toBeLessThanOrEqual(60);
});

it('gives the label only in an installed application (the browser already writes « EduSync »)', () => {
  stubDisplayMode(true);
  expect(windowTitle('Push')).toBe('Push');
  expect(windowTitle('EduSync — Gestion scolaire - Push — EduSync')).toBe('Push');
  stubDisplayMode(false);
  expect(windowTitle('Push')).toBe('Push — EduSync');
});

function account(onLogout: () => void, role = 'Manager Système'): ShellAccount {
  return {name: 'Recette Locale', email: 'recette@example.test', role, items: [
    {key: 'profile', label: 'Mon profil', icon: 'user', onSelect: () => {}},
    {key: 'logout', label: 'Se déconnecter', icon: 'logout', onSelect: onLogout, danger: true}]};
}
function Shell({title, onLogout, dock = true, role}: {title: string; onLogout: () => void; dock?: boolean; role?: string}) {
  return <AppShell accountDock={dock} orgLabel="Plateforme" title={title} nav={[]} account={account(onLogout, role)}><h2>{title}</h2></AppShell>;
}

it('the shell writes one title per route, follows navigation and context changes', async () => {
  function Nav() {
    const [t, setT] = useState('Messagerie');
    return <><Shell title={t} onLogout={() => {}}/>{ROUTES.map(r => <button key={r} onClick={() => setT(r)}>{`aller ${r}`}</button>)}</>;
  }
  render(<Nav/>);
  await waitFor(() => expect(document.title).toBe('Messagerie — EduSync'));
  for (const r of ROUTES) {
    await userEvent.click(screen.getByRole('button', {name: `aller ${r}`}));
    await waitFor(() => expect(document.title).toBe(`${r} — EduSync`));
    expect(document.title.match(/EduSync/g)).toHaveLength(1);
  }
});

for (const [role, dock] of [['Manager Système', true], ['Collaborateur plateforme', true], ['Rôle personnalisé', false]] as const) {
  it(`${role}: « Se déconnecter » asks first; Annuler keeps the session and gives the focus back`, async () => {
    const logout = vi.fn();
    render(<Shell title="Messagerie" onLogout={logout} dock={dock} role={role}/>);
    const trigger = dock ? screen.getByRole('button', {name: /Ouvrir le menu du compte/}) : screen.getByRole('button', {name: /Recette/});
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole('menuitem', {name: 'Se déconnecter'}));
    const dialog = screen.getByRole('alertdialog', {name: 'Se déconnecter ?'});
    expect(dialog.textContent).toContain('Voulez-vous vraiment vous déconnecter de votre session EduSync ?');
    expect(logout).not.toHaveBeenCalled();
    expect(document.activeElement?.textContent).toBe('Annuler');                       // safe default focus
    await userEvent.click(screen.getByRole('button', {name: 'Annuler'}));
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(logout).not.toHaveBeenCalled();
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });
}

it('Escape and a click outside cancel; Tab stays inside the dialog (focus trap)', async () => {
  const logout = vi.fn();
  render(<Shell title="Écoles" onLogout={logout}/>);
  await userEvent.click(screen.getByRole('button', {name: /Ouvrir le menu du compte/}));
  await userEvent.click(screen.getByRole('menuitem', {name: 'Se déconnecter'}));
  await userEvent.tab(); expect(document.activeElement?.textContent).toBe('Se déconnecter');
  await userEvent.tab(); expect(document.activeElement?.textContent).toBe('Annuler');    // wraps around
  await userEvent.keyboard('{Escape}');
  expect(screen.queryByRole('alertdialog')).toBeNull();
  await userEvent.click(screen.getByRole('button', {name: /Ouvrir le menu du compte/}));
  await userEvent.click(screen.getByRole('menuitem', {name: 'Se déconnecter'}));
  const backdrop = document.querySelector('.es-modal-backdrop') as HTMLElement;
  await userEvent.pointer({keys: '[MouseLeft]', target: backdrop});
  expect(screen.queryByRole('alertdialog')).toBeNull();
  expect(logout).not.toHaveBeenCalled();
});

it('« Se déconnecter » signs out once, shows a loading state and ignores a double click', async () => {
  let release!: () => void;
  const logout = vi.fn(() => new Promise<void>(r => { release = r; }));
  render(<Shell title="Journal d’audit" onLogout={logout}/>);
  await userEvent.click(screen.getByRole('button', {name: /Ouvrir le menu du compte/}));
  await userEvent.click(screen.getByRole('menuitem', {name: 'Se déconnecter'}));
  const go = screen.getByRole('button', {name: 'Se déconnecter'});
  await userEvent.dblClick(go);
  expect(logout).toHaveBeenCalledTimes(1);
  expect(screen.getByText('Déconnexion…')).toBeTruthy();
  expect((screen.getByRole('button', {name: 'Annuler'}) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.keyboard('{Escape}');                                                // no cancel while signing out
  expect(screen.getByRole('alertdialog')).toBeTruthy();
  await act(async () => { release(); });
});

it('the phone drawer menu goes through the same confirmation', async () => {
  const logout = vi.fn();
  render(<Shell title="Messagerie" onLogout={logout}/>);
  await userEvent.click(screen.getByRole('button', {name: 'Ouvrir le menu'}));
  const drawer = screen.getByRole('dialog', {name: 'Menu EduSync'});
  await userEvent.click(drawer.querySelector('.es-drawer-acct') as HTMLElement);
  await userEvent.click(Array.from(drawer.querySelectorAll('button')).find(b => b.textContent === 'Se déconnecter') as HTMLElement);
  expect(screen.getByRole('alertdialog', {name: 'Se déconnecter ?'})).toBeTruthy();
  expect(logout).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', {name: 'Se déconnecter'}));
  expect(logout).toHaveBeenCalledTimes(1);
});
