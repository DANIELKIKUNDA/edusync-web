import fs from 'node:fs';
import crypto from 'node:crypto';
const vector=JSON.parse(fs.readFileSync(new URL('../contracts/OFFLINE_FINANCE_HASH_TEST_VECTOR.json',import.meta.url),'utf8'));
function canonicalJson(value){
  if(value===null || typeof value!=='object') return JSON.stringify(value);
  if(Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  return `{${Object.keys(value).sort().map(k=>`${JSON.stringify(k)}:${canonicalJson(value[k])}`).join(',')}}`;
}
const actual=crypto.createHash('sha256').update(canonicalJson(vector.payload),'utf8').digest('hex');
if(actual!==vector.sha256){
  console.error(`OFFLINE_FINANCE_HASH_VECTOR_FAIL expected=${vector.sha256} actual=${actual}`);
  process.exit(1);
}
console.log('OFFLINE_FINANCE_HASH_VECTOR_PASS');
