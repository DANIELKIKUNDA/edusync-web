// Owner report 2026-10-25: « Une difficulté est survenue » everywhere, « l'utilisateur ne sait pas pourquoi ».
import {describe, expect, it} from 'vitest';
import {explainHttpError, friendlyError, isHumanMessage, UserFacingError} from '../src/platform/errors';

const GENERIC = 'Une difficulté est survenue. Réessayez ; si elle persiste, contactez l’administrateur.';

describe('friendlyError keeps sentences written for people', () => {
  it('shows a screen validation sentence', () => {
    expect(friendlyError(new Error('Choisissez une année, une section et une classe.'))).toBe('Choisissez une année, une section et une classe.');
    expect(friendlyError(new Error('Autorisation refusée : réactivez les notifications dans les réglages du navigateur'))).toContain('Autorisation refusée');
  });
  it('hides technical messages', () => {
    for (const m of ['SESSION_SERVICE_UNAVAILABLE', 'Cannot read properties of undefined (reading x)', 'Unexpected token < in JSON', 'Seul un lease ACTIVE peut armer la caisse offline', 'Error: boom'])
      expect(friendlyError(new Error(m))).toBe(GENERIC);
    expect(isHumanMessage('x')).toBe(false);
  });
  it('keeps the dedicated messages', () => {
    expect(friendlyError(new UserFacingError('Le navigateur a bloqué l’ouverture du PDF.'))).toBe('Le navigateur a bloqué l’ouverture du PDF.');
    expect(friendlyError(new TypeError('Failed to fetch'))).toContain('Connexion interrompue');
    const refusal = explainHttpError(403, {detail: 'Permission requise: finance.reports.periodic.generate'});
    expect(friendlyError(new Error(refusal))).toBe(refusal);
    expect(refusal).not.toBe(GENERIC);
  });
});
