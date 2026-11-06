// Owner report 2026-11-06: dates read « JJ/MM/AAAA » whatever the browser language, the class is found by a search,
// and benefits are written in words (never « 100 % sur SCOLARITE »).
import {expect, it} from 'vitest';
import {frenchToIso, isoToFrench, maskFrenchDate} from '../src/platform/date_input';
import {levelName, matchesClass} from '../src/class_select';
import {benefitShort} from '../src/enrollment_helpers';

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
  expect(benefitShort({discount_percent: '100', fee_code: 'SCOLARITE'})).toBe('minerval gratuit');
  expect(benefitShort({discount_percent: '50', fee_code: 'SCOLARITE', fee_codes: ['MINERVAL']})).toBe('50 % de remise sur le minerval');
});
