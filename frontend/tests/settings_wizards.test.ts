// Settings assistants (2026-10-24): codes are generated, never typed; options exist only in the Humanités; parallels
// and one class per option are planned without ever recreating an existing class.
import {expect, it} from 'vitest';
import {autoCode, planClasses, RDC_OPTIONS, FEE_PRESETS} from '../src/settings_wizards';
import type {ReferenceCatalog, SchoolOption, SchoolSection} from '../src/api';

it('autoCode: accents, spaces and symbols become a clean code, unique among the existing ones', () => {
  expect(autoCode('Frais de laboratoire')).toBe('FRAIS_DE_LABORATOIRE');
  expect(autoCode('Papier hygiénique (PH)')).toBe('PAPIER_HYGIENIQUE_PH');
  expect(autoCode('Écusson', ['ECUSSON'])).toBe('ECUSSON_2');
  expect(autoCode('Écusson', ['ECUSSON', 'ECUSSON_2'])).toBe('ECUSSON_3');
  expect(autoCode('   ')).toBe('ITEM');
  expect(autoCode('x'.repeat(80)).length).toBeLessThanOrEqual(48);
});

const sections: SchoolSection[] = [
  {id: 's-p', code: 'PRIMAIRE', label: 'Primaire', enabled: true, version: 1},
  {id: 's-s', code: 'SECONDAIRE', label: 'Secondaire', enabled: true, version: 1},
];
const refs: ReferenceCatalog = {sections: [], fee_types: [], classes: [
  {code: 'P1', section_code: 'PRIMAIRE', label: '1re primaire', sort_order: 110},
  {code: 'S7', section_code: 'SECONDAIRE', label: '7e EB', sort_order: 210},
  {code: 'H1', section_code: 'SECONDAIRE', label: '1re Humanités', sort_order: 310},
]};
const options: SchoolOption[] = [
  {id: 'o-cg', section_id: 's-s', section_code: 'SECONDAIRE', code: 'CG', label: 'Commerciale et gestion', enabled: true, version: 1},
  {id: 'o-sc', section_id: 's-s', section_code: 'SECONDAIRE', code: 'SC', label: 'Scientifique', enabled: true, version: 1},
];

it('parallels: A, B, C with generated names and codes', () => {
  const plan = planClasses({sections, refs, options, picked: ['P1'], parallels: 3, optionIds: [], existing: new Set()});
  expect(plan.map(p => p.label)).toEqual(['1re primaire A', '1re primaire B', '1re primaire C']);
  expect(plan.map(p => p.code)).toEqual(['P1_A', 'P1_B', 'P1_C']);
  expect(plan.every(p => !p.option)).toBe(true);                          // never an option outside the Humanités
});

it('Humanités: one class per chosen option (× parallels); 7e EB stays without option', () => {
  const plan = planClasses({sections, refs, options, picked: ['S7', 'H1'], parallels: 2, optionIds: ['o-cg', 'o-sc'], existing: new Set()});
  expect(plan.filter(p => p.reference.code === 'S7').map(p => p.label)).toEqual(['7e EB A', '7e EB B']);
  expect(plan.filter(p => p.reference.code === 'H1').map(p => p.label)).toEqual([
    '1re Humanités Commerciale et gestion A', '1re Humanités Commerciale et gestion B', '1re Humanités Scientifique A', '1re Humanités Scientifique B']);
  expect(plan.find(p => p.code === 'H1_CG_A')?.option?.id).toBe('o-cg');
});

it('existing classes are never recreated: adding a parallel C keeps A and B untouched', () => {
  const plan = planClasses({sections, refs, options, picked: ['P1'], parallels: 3, optionIds: [], existing: new Set(['P1_A', 'P1_B'])});
  expect(plan.map(p => p.label)).toEqual(['1re primaire C']);
});

it('catalogues ported from the desktop', () => {
  expect(RDC_OPTIONS.some(o => o.code === 'EB')).toBe(false);              // Éducation de base is not an option
  expect(RDC_OPTIONS.filter(o => o.group === 'TECHNICAL').length).toBeGreaterThan(5);
  expect(FEE_PRESETS.map(f => f.code)).toEqual(expect.arrayContaining(['INSCRIPTION', 'MINERVAL', 'ETAT_EXAMEN_ETAT', 'ETAT_TENASOSP', 'ECUSSON']));
});
