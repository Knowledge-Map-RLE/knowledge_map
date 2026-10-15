// Автономный отчёт не должен превращать отсутствие результата в совпадение.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import { JSDOM, VirtualConsole } from 'jsdom';

const path = process.argv[2];
const html = fs.readFileSync(path, 'utf8');
const failures = [];
const vc = new VirtualConsole();
vc.on('jsdomError', error => failures.push(error.message));
const dom = new JSDOM(html, { virtualConsole: vc });
const { document } = dom.window;
let networkCalls = 0;
const forbidden = () => { networkCalls++; throw new Error('Network is forbidden'); };
const scripts = [...document.querySelectorAll('script:not([type="application/json"])')];
assert.equal(scripts.length, 1);
new Function('document', 'window', 'fetch', 'XMLHttpRequest', 'WebSocket', scripts[0].textContent)(
  document, dom.window, forbidden, forbidden, forbidden);
const data = JSON.parse(document.getElementById('payload').textContent);
assert.equal(data.screening.selected_assessable_control, null);
assert.equal(data.audit.independent_pattern_matches, 0);
assert.equal(data.audit.empirical_test_performed, false);
assert.equal(data.audit.graph_gain, null);
assert.equal(document.querySelectorAll('#hypotheses article').length, 2);
const details = [...document.querySelectorAll('#hypotheses details')];
for (const detail of details) {
  detail.open = true;
  assert.match(detail.textContent, /not_addressed/);
  assert.match(detail.textContent, /hazard_association/);
}
assert.deepEqual([...document.querySelectorAll('#modes tbody tr')].map(tr =>
  [...tr.querySelectorAll('td')].slice(1).map(td => td.textContent)),
  [['2', '0', '0', '—'], ['17', '0', '0', '—'], ['11', '0', '0', '—']]);
let languageChecks = 0;
for (const language of ['ru', 'en']) {
  if (document.documentElement.lang !== language) document.getElementById('language').click();
  assert.equal(document.documentElement.lang, language);
  assert.match(document.getElementById('lead').textContent, language === 'ru' ? /не опровержение/ : /neither refutation/);
  assert.match(document.getElementById('next').textContent, /10\.1176\/appi\.neuropsych\.20230180/);
  const filter = document.getElementById('filter');
  filter.value = 'all'; filter.onchange();
  assert.equal(document.querySelectorAll('#screening tbody tr').length, 55);
  filter.value = 'unresolved'; filter.onchange();
  const expected = data.screening.records.filter(r => r.status.includes('unresolved')).length;
  assert.equal(document.querySelectorAll('#screening tbody tr').length, expected);
  assert.equal(expected, 3);
  filter.value = 'checked'; filter.onchange();
  assert.equal(document.querySelectorAll('#screening tbody tr').length,
    data.screening.records.filter(r => r.status !== 'not_screened_further').length);
  languageChecks++;
}
assert.equal(document.querySelectorAll('script[src],link[rel="stylesheet"],iframe,img[src^="http"]').length, 0);
assert.equal(networkCalls, 0);
assert.deepEqual(failures, []);
console.log(JSON.stringify({ languageChecks, hypotheses: 2, metadata: 55, unresolved: 3,
  modeCandidateCounts: [2, 17, 11], assessable: 0, matches: 0, networkCalls, errors: failures }));
