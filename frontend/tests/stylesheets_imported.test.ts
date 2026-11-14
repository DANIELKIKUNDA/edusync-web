// Owner report 2026-11-06: the families indicators looked « archaïques » because schooling.css was never imported.
// Every stylesheet of src/ must be imported by a module, otherwise its screen is silently unstyled.
import {expect, it} from 'vitest';
import {readdirSync, readFileSync, statSync} from 'node:fs';
import {join, relative} from 'node:path';

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap(name => { const p = join(dir, name); return statSync(p).isDirectory() ? walk(p) : [p]; });
}

it('imports every stylesheet of the application', () => {
  const files = walk('src');
  const code = files.filter(f => /\.(tsx?|jsx?)$/.test(f)).map(f => readFileSync(f, 'utf8')).join('\n');
  const orphans = files.filter(f => f.endsWith('.css')).filter(f => !code.includes(`/${f.split(/[\\/]/).pop()}'`)).map(f => relative('src', f));
  expect(orphans).toEqual([]);
});
