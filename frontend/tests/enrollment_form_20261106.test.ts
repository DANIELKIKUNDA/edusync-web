// Owner report 2026-11-06: dates read « JJ/MM/AAAA » whatever the browser language, the class is found by a search,
// and benefits are written in words (never « 100 % sur SCOLARITE »).
import {expect, it} from 'vitest';
import {frenchToIso, isoToFrench, maskFrenchDate} from '../src/platform/date_input';
import {levelName, matchesClass} from '../src/class_select';
import {benefitShort, largeFamilyState} from '../src/enrollment_helpers';

it('types a birth date day first and keeps ISO for the server', () => {
  expect(maskFrenchDate('04032015')).toBe('04/03/2015');
  expect(maskFrenchDate('0403')).toBe('04/03');
  expect(maskFrenchDate('4/3/2015')).toBe('04/03/2015');
  expect(maskFrenchDate('2015-03-04')).toBe('04/03/2015');
  expect(frenchToIso('04/03/2015')).toBe('2015-03-04');
  expect(isoToFrench('2015-03-04')).toBe('04/03/2015');
});

it('refuses impossible or incomplete dates instead of guessing', () => {
  expect(frenchToIso('31/02/2015')).toBeNull();
  expect(frenchToIso('00/13/2015')).toBeNull();
  expect(frenchToIso('04/03')).toBe('');
  expect(isoToFrench('')).toBe('');
});

const cls = (label: string, reference_code: string, section_label = 'Secondaire') => ({id: label, label, reference_code, section_id: 's', section_label} as any);

it('finds a class by sigle, level or option without accents or spaces', () => {
  expect(matchesClass(cls('1re HP A', 'H1'), '1re hp')).toBe(true);
  expect(matchesClass(cls('1re HP A', 'H1'), '1hp')).toBe(true);
  expect(matchesClass(cls('1re HP A', 'H1'), 'humanites')).toBe(true);
  expect(matchesClass(cls('7e EB B', 'S7'), '7e b')).toBe(true);
  expect(matchesClass(cls('1re HP A', 'H1'), 'hsc')).toBe(false);
  expect(levelName(cls('8e EB', 'S8'))).toBe('8e EB');
});

it('writes benefits in words, never with a fee code', () => {
  expect(benefitShort({discount_percent: '100', fee_code: 'SCOLARITE'})).toBe('gratuité : minerval');
  expect(benefitShort({discount_percent: '50', fee_code: 'SCOLARITE', fee_codes: ['MINERVAL']})).toBe('remise de 50 % : minerval');
  expect(benefitShort({discount_percent: '100', fee_code: 'X', fee_labels: ['Frais scolaires mensuels', 'Frais de transport']})).toBe('gratuité : frais scolaires mensuels, frais de transport');
  expect(benefitShort({discount_percent: '100', fee_code: 'X', all_fees: true})).toBe('gratuité : tous les frais');
});

it('offers the large-family benefit only from the school threshold and within its limit', () => {
  const v = {min_children: 5, beneficiary_limit: 1, discount_percent: '100', fee_code: 'SCOLARITE', family_enrolled_children: 0, family_beneficiaries: 0};
  expect(largeFamilyState(v, 3, 0).visible).toBe(false);           // 3 children: nothing shown
  const five = largeFamilyState(v, 5, 0); expect(five.visible).toBe(true); expect(five.total).toBe(5); expect(five.canAdd).toBe(true);
  expect(largeFamilyState(v, 5, 1).canAdd).toBe(false);            // one free child already chosen
  expect(largeFamilyState({...v, family_enrolled_children: 4}, 1, 0).visible).toBe(true);   // 4 already enrolled + 1
  expect(largeFamilyState({...v, family_enrolled_children: 6, family_beneficiaries: 1}, 1, 0).visible).toBe(false); // limit used
  expect(largeFamilyState(null, 9, 0).visible).toBe(false);         // school without the policy
});

it('grants the large-family benefit per group of children when the school chose « par tranche »', () => {
  const v = {min_children: 5, beneficiary_limit: 1, per_group: true, discount_percent: '100', fee_code: 'SCOLARITE', family_enrolled_children: 0, family_beneficiaries: 0};
  expect(largeFamilyState(v, 4, 0).visible).toBe(false);
  expect(largeFamilyState(v, 8, 0).remaining).toBe(1);             // 8 children → 1 group of 5
  expect(largeFamilyState(v, 10, 0).remaining).toBe(2);            // 10 children → 2
  expect(largeFamilyState(v, 10, 2).canAdd).toBe(false);
  expect(largeFamilyState({...v, family_enrolled_children: 9, family_beneficiaries: 1}, 1, 0).remaining).toBe(1); // 10th child unlocks the 2nd
});
