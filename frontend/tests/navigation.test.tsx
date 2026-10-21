// @vitest-environment jsdom
import React from 'react';
import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {PageTrail, pageTitle, scrollPosition, VerticalNavigation} from '../src/platform/navigation';
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.useRealTimers();});

it('renders human parent labels, a current context and a safe direct-link fallback',async()=>{
  const schools=vi.fn(), users=vi.fn();
  render(<PageTrail parents={[{label:'Écoles',onSelect:schools},{label:'Riziki',onSelect:users}]} current="Utilisateurs"/>);
  expect(screen.getByText('Utilisateurs',{selector:'[aria-current]'})).toBeTruthy();
  await userEvent.click(screen.getByRole('button',{name:'Écoles',exact:true}));expect(schools).toHaveBeenCalledOnce();
  await userEvent.click(screen.getByRole('button',{name:'Retour : Riziki'}));expect(users).toHaveBeenCalledOnce();
  expect(location.href).not.toContain('undefined');
});
it('omits a redundant root trail and normalizes titles',()=>{
  const view=render(<PageTrail parents={[]} current="Messagerie"/>);expect(view.container.textContent).toBe('');
  expect(pageTitle('Messagerie · EduSync')).toBe('Messagerie — EduSync');
  expect(pageTitle('EduSync — Écoles')).toBe('Écoles — EduSync');
});
it('distinguishes short, top, middle, bottom and rotated viewports',()=>{
  expect(scrollPosition(0,700,700)).toEqual({long:false,started:false,bottom:true});
  expect(scrollPosition(0,4000,700)).toEqual({long:true,started:false,bottom:false});
  expect(scrollPosition(1000,4000,700)).toEqual({long:true,started:true,bottom:false});
  expect(scrollPosition(3200,4000,700)).toEqual({long:true,started:true,bottom:true});
  expect(scrollPosition(3200,4000,360).bottom).toBe(false);
});
it('keeps the single vertical control hidden on a short page',()=>{
  vi.stubGlobal('ResizeObserver',class{observe(){} disconnect(){}});
  vi.stubGlobal('requestAnimationFrame',()=>0);vi.stubGlobal('cancelAnimationFrame',()=>{});
  render(<VerticalNavigation/>);
  const button=screen.getByRole('button',{hidden:true});expect(button.dataset.visible).toBe('false');expect(button.tabIndex).toBe(-1);
});
