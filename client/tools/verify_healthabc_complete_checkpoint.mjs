// Проверяем автономность отчёта и действия карты; визуальную оценку не подменяем DOM.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { JSDOM, VirtualConsole } from 'jsdom';

const reportPath = path.resolve(process.argv[2]);
const folder = path.dirname(reportPath);
const data = JSON.parse(fs.readFileSync(path.join(folder, 'data.json'), 'utf8'));
const report = new JSDOM(fs.readFileSync(reportPath, 'utf8')).window.document;
assert.equal(report.documentElement.lang, 'ru');
assert.equal(report.querySelectorAll('script,iframe,link[rel="stylesheet"],img[src],[lang="en"]').length, 0);
assert.match(report.body.textContent, /не совпадения с целевой статьёй/);
assert.match(report.body.textContent, /преимущество Карты Знаний пока не установлено/);
assert.equal(data.canonical_blocks, 568);
assert.equal(data.eligible, 554);
assert.equal(data.partial_maps, 2);
assert.equal(data.new_supported_predictions, 0);
assert.equal(data.graph_advantage_demonstrated, false);
assert.equal(data.model_calls, 0);
assert.equal(data.target_reads, 0);
for (const a of report.querySelectorAll('a[href]')) {
  assert.ok(!/^(https?:|\/\/)/.test(a.getAttribute('href')));
  assert.ok(fs.existsSync(path.resolve(folder, a.getAttribute('href'))));
}
const mapPath = path.resolve(folder, '../runs', data.map_run_id, 'map.html');
const errors = [];
const console = new VirtualConsole();
console.on('jsdomError', e => errors.push(e.message));
const dom = new JSDOM(fs.readFileSync(mapPath, 'utf8'), {
  pretendToBeVisual: true, virtualConsole: console,
  beforeParse(window) {
    window.fetch = () => { throw new Error('Network forbidden'); };
    Object.defineProperty(window.HTMLElement.prototype, 'clientWidth', {get: () => 1000});
    Object.defineProperty(window.HTMLElement.prototype, 'clientHeight', {get: () => 700});
  },
});
const d = dom.window.document;
// Выполняем собственный встроенный скрипт в Bun без несовместимого vm-контекста jsdom.
for (const script of d.querySelectorAll('script:not([type])')) {
  assert.ok(!script.src);
  new Function('window', 'document', script.textContent)(dom.window, d);
}
assert.equal(d.querySelectorAll('[src],link[rel="stylesheet"]').length, 0);
const map = JSON.parse(d.querySelector('#data').textContent);
assert.equal(map.graph.knowledge.length, 96);
assert.equal(d.querySelectorAll('.card').length, map.graph.nodes.length);
assert.equal(d.querySelectorAll('.edge').length, map.graph.edges.length);
d.querySelector('.card').click();
assert.ok(d.querySelector('#details blockquote'));
assert.ok(d.querySelector('#details pre').textContent.includes('statements'));
const lang = d.querySelector('#language'); lang.value = 'ru';
lang.dispatchEvent(new dom.window.Event('change'));
const first = map.graph.nodes[0];
assert.ok(d.querySelector('.card').textContent.includes(map.translations.ru.labels[first.id]));
d.querySelector('.hit').dispatchEvent(new dom.window.MouseEvent('click', {bubbles: true}));
assert.ok(d.querySelector('#details blockquote'));
assert.match(d.querySelector('#details').textContent, /Совместные входы/);
const scene = d.querySelector('#scene');
const transform = scene.getAttribute('transform');
d.querySelector('#plus').click();
assert.notEqual(scene.getAttribute('transform'), transform);
d.querySelector('#source').click();
assert.equal(d.querySelector('#full').style.display, 'block');
assert.equal(d.querySelector('#full').textContent, map.source.text);
assert.deepEqual(errors, []);
dom.window.close();
const result = {passed: true, language: 'ru', report_external_dependencies: 0,
  map_nodes: map.graph.nodes.length, source_and_transition_selection: true,
  russian_labels: true, zoom: true, model_calls: 0, visual_inspection: false};
const bytes = JSON.stringify(result, null, 2) + '\n';
const output = path.join(folder, 'html-verification.json');
if (fs.existsSync(output)) assert.equal(fs.readFileSync(output, 'utf8'), bytes);
else fs.writeFileSync(output, bytes, {flag: 'wx'});
process.stdout.write(JSON.stringify(result) + '\n');
