// Проверка сохранности двух прогонов и автономного русского отчёта о типах атрибутов.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

const base = resolve(import.meta.dir, '../../eval/whole_map_forecast');
const root = resolve(base, 'attribute-kinds-v1');
const read = path => readFileSync(resolve(root, path));
const json = path => JSON.parse(read(path).toString('utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const v = json('review-v1/verification.json');
for (const [file, digest] of Object.entries(v.files)) assert.equal(hash(read(`review-v1/${file}`)), digest);
for (const [file, digest] of Object.entries(v.input_files)) assert.equal(hash(readFileSync(resolve(base, file))), digest);
assert.equal(hash(read('build_review.py')), v.builder_sha256);
assert.equal(hash(read('test-results-v2.xml')), v.tests_sha256);
assert.equal(v.tests_passed, 117);
assert.equal(v.domain_seals_validated, true);
assert.equal(v.source_locator_proofs_checked, 43);
const report = read('review-v1/report.html').toString('utf8');
assert.match(report, /<html lang="ru">/);
assert.doesNotMatch(report, /<(?:script|iframe|link)\b|(?:src|href)\s*=\s*["'](?:https?:|\/\/)/i);
assert.match(report, /Новых прогнозов: 0/);
const data = json('review-v1/data.json');
assert.equal(data.same_inputs, true);
assert.equal(data.sources, 10);
assert.equal(data.canonical_blocks, 890);
assert.equal(data.licensed_parts, 794);
assert.equal(data.relocated_locators, 61);
assert.equal(data.maps_changed, false);
assert.equal(data.scientific_success, false);
assert.equal(data.graph_advantage_demonstrated, false);
assert.equal(data.future_results_scored, 0);
assert.ok(data.modes.every(m => m.new_predictions === 0));
assert.deepEqual(data.rejected_graph_groups, data.before_rejected_graph_groups);
const prediction = json(`runs/${data.run_after}/predictions.json`);
assert.equal(prediction.target_read, false);
assert.equal(prediction.model_calls, 0);
assert.ok(Object.values(prediction.predictions).every(list => list.length === 0));
const proofs = prediction.source_locator_metadata.proofs;
assert.equal(proofs.length, 43);
assert.equal(proofs.reduce((n, p) => n + p.locators.length, 0), 61);
for (const proof of proofs) {
  assert.equal(proof.scientific_attributes_removed, false);
  assert.equal(proof.scope_changed, false);
  assert.equal(proof.new_measurement, false);
  for (const locator of proof.locators) {
    assert.deepEqual(locator.attribute, proof.parent_frame.statements[locator.statement_position].attributes[locator.attribute_position]);
    assert.ok(locator.evidence.length > 0);
    for (const e of locator.evidence) assert.equal(Array.from(e.text).length, e.end - e.start);
  }
}
const receipt = { проверка: 'успешна', источников: 10, проверенных_локаторов: 61, прогнозов: 0,
  tests_passed: 117, verifier_sha256: hash(readFileSync(import.meta.path)),
  report_sha256: hash(Buffer.from(report)), visual_inspection: false };
const bytes = Buffer.from(JSON.stringify(receipt, null, 2) + '\n');
const path = resolve(root, 'review-v1/html-verification.json');
try { writeFileSync(path, bytes, { flag: 'wx' }); }
catch (e) { if (e.code !== 'EEXIST') throw e; assert.deepEqual(readFileSync(path), bytes); }
console.log(JSON.stringify(receipt));
