import {expect, it} from 'vitest';
import {readFileSync} from 'node:fs';

it('security password change has an independent accessible eye for all three passwords', () => {
  const source = readFileSync(new URL('../src/platform/account.tsx', import.meta.url), 'utf8');
  expect(source).toContain('security-current-password');
  expect(source).toContain('security-new-password');
  expect(source).toContain('security-confirm-password');
  expect(source).toContain("shown ? 'eyeOff' : 'eye'");
  expect(source).toContain("aria-pressed={shown}");
  expect(source).toContain("type={shown ? 'text' : 'password'}");
});

it('offline warm-up covers the essential consultation areas according to permissions', () => {
  const source = readFileSync(new URL('../src/offline/school_sync.tsx', import.meta.url), 'utf8');
  for (const capability of ['students.read', 'families.read', 'headcounts.read', 'finance.recovery.monthly.read', 'communications.read', 'audit.school.read', 'documents.history.read'])
    expect(source).toContain(capability);
});
