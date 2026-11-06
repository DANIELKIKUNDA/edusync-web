// Settings assistants (2026-10-24): codes are generated, never typed; options exist only in the Humanités; parallels
// and one class per option are planned without ever recreating an existing class.
import {expect, it} from 'vitest';
import {autoCode, optionSigle, plannedClassLabel, sigleRenames, planClasses, parallelCount, existingParallels, MAX_PARALLELS, RDC_OPTIONS, FEE_PRESETS} from '../src/settings_wizards';
import type {ReferenceCatalog, SchoolClass, SchoolOption, SchoolSection} from '../src/api';

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
    '1re CG A', '1re CG B', '1re HSC A', '1re HSC B']);
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

it('parallels per level: 2 in 1re primaire, a single class in 7e EB (owner request 2026-10-24)', () => {
  const plan = planClasses({sections, refs, options, picked: ['P1', 'S7'], parallels: {P1: 2}, optionIds: [], existing: new Set()});
  expect(plan.map(p => p.label)).toEqual(['1re primaire A', '1re primaire B', '7e EB']);
});

it('parallels per Humanités option: 2 in Commerciale et gestion, 1 in Scientifique', () => {
  const plan = planClasses({sections, refs, options, picked: ['H1'], parallels: {'H1:CG': 2}, optionIds: ['o-cg', 'o-sc'], existing: new Set()});
  expect(plan.map(p => p.code)).toEqual(['H1_CG_A', 'H1_CG_B', 'H1_SC']);
  expect(parallelCount({P1: 99}, 'P1')).toBe(MAX_PARALLELS);                // bounded
  expect(parallelCount({}, 'P2')).toBe(1);                                  // default: a single class
});

it('a level already split in A and B never gets an extra class without letter', () => {
  expect(planClasses({sections, refs, options, picked: ['P1'], parallels: {P1: 1}, optionIds: [], existing: new Set(['P1_A', 'P1_B'])})).toEqual([]);
});

it('an existing class without letter counts as the first parallel', () => {
  const plan = planClasses({sections, refs, options, picked: ['P1'], parallels: {P1: 2}, optionIds: [], existing: new Set(['P1'])});
  expect(plan.map(p => p.label)).toEqual(['1re primaire B']);
});

it('the grid starts from the parallels already open', () => {
  const c = (code: string, ref: string, option_id?: string) => ({id: code, academic_year_id: 'y', section_id: 's', reference_code: ref, option_id, code, label: code, enabled: true, version: 1}) as SchoolClass;
  expect(existingParallels([c('P1_A', 'P1'), c('P1_B', 'P1'), c('S7', 'S7'), c('H1_CG_A', 'H1', 'o-cg'), {...c('P2', 'P2'), academic_year_id: 'old'}], 'y', options))
    .toEqual({P1: 2, S7: 1, 'H1:CG': 1});
});

it('Humanités classes are named with the school sigles; options keep their full name (owner request 2026-11-06)', () => {
  const sig = (code: string, label = code) => optionSigle({code, label});
  expect(['HP', 'SC', 'CG', 'LITTERAIRE', 'TCC', 'ELEC', 'ELECTRONIQUE', 'MG', 'MA', 'CONSTRUCTION', 'NUTRITION'].map(c => sig(c)))
    .toEqual(['HP', 'HSC', 'CG', 'LIT', 'TCC', 'ELEC', 'ELECTRO', 'MG', 'MA', 'CONSTRU', 'NUTRITION']);
  expect(sig('AGRONOMIE', 'Agronomie')).toBe('AGRONOM');
  expect(plannedClassLabel({code: 'H1', label: '1re Humanités'}, {code: 'HP', label: 'Pédagogie générale'})).toBe('1re HP');
  expect(plannedClassLabel({code: 'H3', label: '3e Humanités'}, {code: 'SC', label: 'Scientifique'}, 'B')).toBe('3e HSC B');
  expect(plannedClassLabel({code: 'P1', label: '1re primaire'}, undefined, 'A')).toBe('1re primaire A');
});

it('full Humanités names can be shortened to the sigle, keeping the parallel letter', () => {
  const c = (id: string, label: string, ref: string, option_id?: string) => ({id, academic_year_id: 'y', section_id: 's-s', reference_code: ref, option_id, code: id, label, enabled: true, version: 1}) as SchoolClass;
  const renames = sigleRenames([c('a', '1re Humanités Commerciale et gestion B', 'H1', 'o-cg'), c('b', '1re CG', 'H1', 'o-cg'), c('c', '7e EB A', 'S7')], refs.classes, options);
  expect(renames.map(r => [r.cls.id, r.label])).toEqual([['a', '1re CG B']]);
});
