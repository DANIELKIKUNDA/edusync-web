// Tariff assistant (settings parity pass 2, 2026-10-24): the preview applies the same precedence as the server
// (class › level › Humanités group › section › school) and the regulatory bundle is the Desktop one.
import {expect, it} from 'vitest';
import {previewTariffs, tariffTargets, REGULATORY_LINES} from '../src/settings_tariff_assistant';
import {feeOptions} from '../src/settings_benefits';
import type {AcademicYear, SchoolClass, SchoolOption, SchoolSection, Tariff} from '../src/api';

const year = {id: 'y', code: '2026-2027', label: '2026-2027', status: 'ACTIVE', start_date: '2026-09-01', end_date: '2027-07-02', version: 1} as AcademicYear;
const sections = [{id: 's-p', code: 'PRIMAIRE', label: 'Primaire', enabled: true, version: 1}, {id: 's-s', code: 'SECONDAIRE', label: 'Secondaire', enabled: true, version: 1}] as SchoolSection[];
const options = [{id: 'o-cg', section_id: 's-s', section_code: 'SECONDAIRE', code: 'CG', label: 'Commerciale', tariff_group_code: 'GENERAL', enabled: true, version: 1},
  {id: 'o-el', section_id: 's-s', section_code: 'SECONDAIRE', code: 'ELEC', label: 'Électricité', tariff_group_code: 'TECHNICAL', enabled: true, version: 1}] as SchoolOption[];
const cls = (id: string, section_id: string, reference_code: string, option_id?: string) => ({id, academic_year_id: 'y', section_id, reference_code, option_id, code: id, label: id, enabled: true, status: 'ACTIVE', version: 1}) as SchoolClass;
const classes = [cls('P1_A', 's-p', 'P1'), cls('P6', 's-p', 'P6'), cls('H1_CG', 's-s', 'H1', 'o-cg'), cls('H1_ELEC', 's-s', 'H1', 'o-el'), cls('H4_CG', 's-s', 'H4', 'o-cg')];
const rule = (scope_type: Tariff['scope_type'], scope_ref: string, amount: string) => ({id: scope_ref, academic_year_id: 'y', fee_type_id: 'f', scope_type, scope_ref, effective_from: '2026-09-01', status: 'ACTIVE', currency: 'CDF', amount, billing_months: [], enabled: true}) as unknown as Tariff;

it('the most precise rule wins, exactly as on the server', () => {
  const rows = previewTariffs({year, classes, options, existing: [rule('SECTION', 's-p', '10000')], planned: [
    {scope_type: 'ACADEMIC_CLASS', scope_ref: 'P6', label: '6e', amount: '12000', currency: 'CDF', status: 'ACTIVE'},
    {scope_type: 'OPTION_GROUP', scope_ref: 'GENERAL', label: 'Gén.', amount: '23000', currency: 'CDF', status: 'ACTIVE'},
    {scope_type: 'OPTION_GROUP', scope_ref: 'TECHNICAL', label: 'Tech.', amount: '25000', currency: 'CDF', status: 'ACTIVE'},
    {scope_type: 'ACADEMIC_CLASS', scope_ref: 'H4', label: '4e', amount: '30000', currency: 'CDF', status: 'ACTIVE'}]});
  const by = Object.fromEntries(rows.map(r => [r.cls.id, [r.amount, r.scope]]));
  expect(by.P1_A).toEqual(['10000', 'SECTION']);          // existing section rule
  expect(by.P6).toEqual(['12000', 'ACADEMIC_CLASS']);       // the 6e primaire differs
  expect(by.H1_CG).toEqual(['23000', 'OPTION_GROUP']);
  expect(by.H1_ELEC).toEqual(['25000', 'OPTION_GROUP']);
  expect(by.H4_CG).toEqual(['30000', 'ACADEMIC_CLASS']);    // a level beats the Humanités group
});

it('a class without any rule is reported, never invented', () => {
  const rows = previewTariffs({year, classes, options, existing: [], planned: []});
  expect(rows.every(r => r.scope === null && r.amount === null)).toBe(true);
});

it('targets: only open levels and the Humanités groups really in use', () => {
  const t = tariffTargets({year, classes, sections, refs: null, options});
  expect(t.ACADEMIC_CLASS.map(x => x.scope_ref).sort()).toEqual(['H1', 'H4', 'P1', 'P6']);
  expect(t.OPTION_GROUP.map(x => x.scope_ref)).toEqual(['GENERAL', 'TECHNICAL']);
});

it('regulatory bundle = Desktop configure_regulatory_fee_bundle amounts', () => {
  const by = Object.fromEntries(REGULATORY_LINES.map(l => [l.key, l.amount]));
  expect(by).toEqual({'etat-mat': '12000', 'etat-pri': '12000', 'etat-s7': '21000', 'etat-s8': '21000', 'etat-gen': '23000', 'etat-tec': '25000', 'tenasosp-s8': '60000', 'tech-tec': '25000'});
});

it('benefits: a saved fee code that is no longer listed stays visible and selectable', () => {
  const fees = [{id: '1', code: 'MINERVAL', label: 'Frais scolaires mensuels', periodicity: 'MONTHLY', default_currency: 'CDF', regulatory: false, enabled: true, version: 1}] as never;
  expect(feeOptions(fees, ['SCOLARITE', 'MINERVAL']).map(([c]) => c)).toEqual(['MINERVAL', 'SCOLARITE']);
});
