// Проверяем русский отчёт, автономность и честное различие счётчиков.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
const file = process.argv[2];
const document = new JSDOM(fs.readFileSync(file, 'utf8')).window.document;
const data = JSON.parse(fs.readFileSync(path.join(path.dirname(file), 'data.json'), 'utf8'));
assert.equal(document.documentElement.lang, 'ru');
assert.equal(document.querySelectorAll('script,iframe,link[rel="stylesheet"],img[src]').length, 0);
assert.equal(document.querySelectorAll('[lang="en"],#en,#lang').length, 0);
const text = document.body.textContent;
for (const value of ['495', '481', '77', '60', '296', '279', '106']) assert.ok(text.includes(value));
assert.match(text, /не совпадения с целевой статьёй/);
assert.match(text, /покрытие выборочное/);
assert.match(text, /преимущество структуры Карты Знаний пока не установлено/);
assert.equal(document.querySelectorAll('table tbody tr').length, 7);
for (const link of document.querySelectorAll('a[href]')) {
  assert.ok(!/^(https?:|\/\/)/.test(link.getAttribute('href')));
  assert.ok(fs.existsSync(path.resolve(path.dirname(file), link.getAttribute('href'))));
}
assert.equal(data.canonical_blocks, 495);
assert.equal(data.eligible, 481);
assert.equal(data.new_supported_predictions, 0);
assert.equal(data.graph_advantage_demonstrated, false);
assert.equal(data.partial_maps, 3);
assert.equal(data.provenance_partitioned_blocks, 76);
assert.equal(data.modes.known_union, 20);
assert.equal(data.modes.frequency, 20);
assert.equal(data.complete_article_semantics_verified, false);
assert.equal(data.model_calls, 0);
assert.equal(data.target_reads, 0);
const verification = {language: 'ru', sources: 8, canonical_blocks: 495, modes: 6,
  external_dependencies: 0, visual_inspection: false, passed: true};
const output = path.join(path.dirname(file), 'html-verification.json');
const bytes = JSON.stringify(verification, null, 2) + '\n';
if (fs.existsSync(output)) assert.equal(fs.readFileSync(output, 'utf8'), bytes);
else fs.writeFileSync(output, bytes, {flag: 'wx'});
process.stdout.write(JSON.stringify(verification) + '\n');
