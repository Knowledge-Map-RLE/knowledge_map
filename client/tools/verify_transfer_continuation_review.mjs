// Диагностический отчёт не должен засчитывать неподходящие контроли как успех.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import { JSDOM, VirtualConsole } from 'jsdom';

const html = fs.readFileSync(process.argv[2], 'utf8');
const errors = [];
const console = new VirtualConsole();
console.on('jsdomError', error => errors.push(error.message));
const dom = new JSDOM(html, { virtualConsole: console });
const { document } = dom.window;
let networkCalls = 0;
const forbidden = () => { networkCalls++; throw new Error('Network forbidden'); };
const scripts = [...document.querySelectorAll('script:not([type="application/json"])')];
assert.equal(scripts.length, 1);
new Function('document', 'window', 'fetch', 'XMLHttpRequest', 'WebSocket', scripts[0].textContent)(
  document, dom.window, forbidden, forbidden, forbidden);
const data = JSON.parse(document.getElementById('payload').textContent);
assert.equal(data.summary.frozen_hypotheses, 2);
assert.equal(data.summary.matches, 0);
assert.equal(data.summary.direction_accuracy, null);
assert.equal(data.summary.graph_gain, null);
assert.equal(data.screening.selected_assessable_control, null);
assert.equal(data.screening.new_fulltexts_obtained, 9);
let languageChecks = 0;
for (const language of ['ru', 'en']) {
  if (document.documentElement.lang !== language) document.getElementById('language').click();
  assert.equal(document.documentElement.lang, language);
  assert.equal(document.querySelectorAll('#hypotheses li').length, 2);
  assert.equal(document.querySelectorAll('#sources article').length, 9);
  assert.equal(document.querySelectorAll('#unresolved li').length, 3);
  assert.match(document.getElementById('skip').textContent, /10\.1176\/appi\.neuropsych\.20230180/);
  assert.match(document.getElementById('accuracy').textContent, language === 'ru' ? /не определена/ : /undefined/);
  const rows = [...document.querySelectorAll('#audits tbody tr')];
  assert.equal(rows.length, 6);
  const expectedCounts = language === 'ru'
    ? { 'Семантический': '2', 'Известные знания': '17', 'Частотная база': '11' }
    : { 'Semantic': '2', 'Known union': '17', 'Frequency': '11' };
  for (const row of rows) {
    const cells = [...row.querySelectorAll('td')].map(td => td.textContent);
    assert.deepEqual(cells.slice(2), [expectedCounts[cells[1]], '0', '0', 'unassessable']);
  }
  const filter = document.getElementById('filter');
  for (const [value, count] of [['all', 55], ['unresolved', 3], ['skipped', 1], ['full', 9]]) {
    filter.value = value; filter.onchange();
    assert.equal(document.querySelectorAll('#registry tr').length, count);
  }
  filter.value = 'all'; filter.onchange();
  const search = document.getElementById('search');
  search.value = '10.1136/jnnp-2024-333837'; search.oninput();
  assert.equal(document.querySelectorAll('#registry tr').length, 1);
  assert.match(document.getElementById('registry').textContent, /2024-08-13/);
  search.value = ''; search.oninput();
  const details = [...document.querySelectorAll('#sources details')];
  for (const detail of details) { detail.open = true; assert.match(detail.textContent, /Unicode code points/); }
  languageChecks++;
}
assert.equal(document.querySelectorAll('script[src],link[rel="stylesheet"],iframe,img[src^="http"]').length, 0);
assert.equal(networkCalls, 0);
assert.deepEqual(errors, []);
process.stdout.write(JSON.stringify({ languageChecks, sources: 9, registry: 55, unresolved: 3,
  userSkipped: 1, frozenHypotheses: 2, matches: 0, accuracy: null, networkCalls, errors }) + '\n');
