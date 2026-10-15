// Проверка русских автономных отчётов и сохранности обоих контрольных прогонов.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/contrast-clause-licenses-v1');
const read = path => readFileSync(resolve(root, path));
const json = path => JSON.parse(read(path).toString('utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
// Доменная печать проверяется Python: JSON чисел не сериализуется одинаково в двух средах.
const files = json('review-v1/prediction-files.json');
assert.equal(files.domain_seals_validated, true);
assert.equal(hash(read('seal_input_files.py')), files.validator_sha256);
for (const [path, digest] of Object.entries(files.files)) assert.equal(hash(read(path)), digest);
const verification = json('review-v1/verification.json');
for (const [file, digest] of Object.entries(verification.files)) assert.equal(hash(read(`review-v1/${file}`)), digest);
assert.equal(hash(read('build_review.py')), verification.builder_sha256);
assert.equal(hash(read('test-results-v1.xml')), verification.test_receipt_sha256);
const report = read('review-v1/report.html').toString('utf8');
assert.match(report, /<html lang="ru">/);
assert.doesNotMatch(report, /<(?:script|iframe|link)\b|(?:src|href)\s*=\s*["'](?:https?:|\/\/)/i);
assert.match(report, /Новых прогнозов: 0/);
assert.equal((report.match(/<details>/g) || []).length, 17);
const data = json('review-v1/data.json');
assert.equal(data.sources, 10);
assert.equal(data.canonical_blocks, 890);
assert.equal(data.before_parts, 723);
assert.equal(data.after_parts, 794);
assert.equal(data.additional_parts, 71);
assert.equal(data.tests_passed, 81);
assert.equal(data.scientific_success, false);
assert.equal(data.graph_advantage_demonstrated, false);
assert.equal(data.future_results_scored, 0);
assert.equal(data.model_calls, 0);
const inputs = [];
for (const [folder, run] of [['baseline-runs', data.baseline_run], ['runs', data.licensed_run]]) {
  const path = `${folder}/${run}`;
  const prediction = json(`${path}/predictions.json`);
  assert.equal(json(`${path}/seal.json`).run_id, run);
  assert.equal(prediction.run_id, run);
  assert.equal(prediction.target_read, false);
  assert.equal(prediction.model_calls, 0);
  assert.ok(Object.values(prediction.predictions).every(values => values.length === 0));
  const manifest = json(`${path}/inputs-manifest.json`);
  assert.equal(manifest.sources.length, 10);
  for (const entry of manifest.sources) assert.equal(hash(read(`${path}/${entry.map_path}`)), entry.map_file_sha256);
  for (const [name, digest] of Object.entries(prediction.binding.implementation)) {
    assert.equal(hash(read(`${path}/implementation/${name}`)), digest);
  }
  for (const [name, digest] of Object.entries(prediction.binding.metadata.input_audit_file_sha256)) {
    assert.equal(hash(read(`${path}/${name}.json`)), digest);
  }
  inputs.push(manifest);
}
assert.deepEqual(inputs[0], inputs[1]);
const licenses = json('compound-licenses.json');
assert.equal(licenses.entries.length, 17);
assert.equal(hash(read('compound-licenses.json')), json('prepare-seal.json').licenses_sha256);
assert.equal(licenses.model_calls, 0);
assert.equal(licenses.expert_validated, false);
const receipt = { проверка: 'успешна', источников: 10, допущенных_частей: 71, новых_прогнозов: 0,
  автономный_русский_отчёт: true, verifier_sha256: hash(readFileSync(import.meta.path)),
  report_sha256: hash(Buffer.from(report)), visual_inspection: false };
const bytes = Buffer.from(JSON.stringify(receipt, null, 2) + '\n');
const path = resolve(root, 'review-v1/html-verification.json');
try { writeFileSync(path, bytes, { flag: 'wx' }); }
catch (e) { if (e.code !== 'EEXIST') throw e; assert.deepEqual(readFileSync(path), bytes); }
console.log(JSON.stringify(receipt));
