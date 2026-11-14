// Owner report 2026-11-08: a child whose class does not carry the fee required at enrollment (June) is never shown as
// « rien à payer »; the enrollment button is blocked until the fee is configured or the direction waives it.
import {expect, it} from 'vitest';
import {settlementAction} from '../src/admission_settlement';
import type {AdmissionPreview} from '../src/api';

const preview = (blocked: boolean, canCollect = true): AdmissionPreview => ({can_collect: canCollect, can_waive: false, conditions: {
  children: [], totals: {CDF: '55000'}, requires_payment: true, blocked, blocked_message: blocked ? 'Conditions d’inscription non configurées : …' : null}});

it('blocks the cash desk when a required fee is not configured for a class', () => {
  expect(settlementAction(preview(true), 6)).toEqual({label: 'Conditions à configurer', kind: 'BLOCKED'});
});

it('keeps the pending dossier for someone who cannot collect, and the normal payment otherwise', () => {
  expect(settlementAction(preview(true, false), 6).kind).toBe('DOSSIER');
  expect(settlementAction(preview(false), 6).kind).toBe('PAY');
});
