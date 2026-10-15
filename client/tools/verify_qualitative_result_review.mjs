// Автономный русский отчёт проверяется по неизменяемым входам и полным доказательствам.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

const base = resolve(import.meta.dir, '../../eval/whole_map_forecast');
const root = resolve(base, 'qualitative-result-projection-v1');
const read = path => readFileSync(resolve(root, path));
const json = path => JSON.parse(read(path).toString('utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const v = json('review-v1/verification.json');
for (const [file, digest] of Object.entries(v.files)) assert.equal(hash(read(`review-v1/${file}`)), digest);
for (const [file, digest] of Object.entries(v.input_files)) assert.equal(hash(readFileSync(resolve(base, file))), digest);
assert.equal(hash(read('build_review.py')), v.builder_sha256);
assert.equal(hash(read('test-results-v2.xml')), v.tests_sha256);
assert.equal(v.tests_passed, 125);
assert.equal(v.domain_seals_validated, true);
assert.equal(v.qualitative_proofs_checked, 29);
const report = read('review-v1/report.html').toString('utf8');
assert.match(report, /<html lang="ru">/);
assert.doesNotMatch(report, /<(?:script|iframe|link)\b|(?:src|href)\s*=\s*["'](?:https?:|\/\/)/i);
assert.match(report, /Новых прогнозов: 0/);
const data = json('review-v1/data.json');
assert.equal(data.same_inputs, true);
assert.equal(data.sources, 10);
assert.equal(data.canonical_blocks, 890);
assert.equal(data.licensed_parts, 794);
assert.equal(data.qualitative_statements, 86);
assert.equal(data.summaries_in_evidence, 69);
assert.equal(data.maps_changed, false);
assert.equal(data.scientific_success, false);
assert.equal(data.graph_advantage_demonstrated, false);
assert.equal(data.future_results_scored, 0);
assert.ok(data.modes.every(m => m.new_predictions === 0));
assert.equal(data.before_rejected_graph_groups.unmodelled_numeric_conclusion, 143);
assert.equal(data.rejected_graph_groups.unmodelled_numeric_conclusion, 130);
const prediction = json(`runs/${data.run_after}/predictions.json`);
assert.equal(prediction.target_read, false);
assert.equal(prediction.model_calls, 0);
assert.ok(Object.values(prediction.predictions).every(list => list.length === 0));
const proofs = prediction.qualitative_result_projection.proofs;
assert.equal(proofs.length, 29);
assert.equal(proofs.reduce((n, p) => n + p.statements.length, 0), 86);
assert.equal(proofs.reduce((n, p) => n + p.statements.reduce((m, s) => m + s.summaries.length, 0), 0), 69);
for (const proof of proofs) {
  for (const flag of ['scope_changed', 'participants_changed', 'direction_inferred_from_numbers',
    'new_measurement', 'significance_predicted', 'causality_asserted']) assert.equal(proof[flag], false);
  for (const s of proof.statements) {
    assert.equal(s.origin.origin, 'primary_result');
    for (const summary of s.summaries) {
      assert.deepEqual(summary.attribute, proof.parent_frame.statements[s.position].attributes[summary.position]);
    }
    assert.ok(s.evidence.length > 0);
    for (const e of s.evidence) assert.equal(Array.from(e.text).length, e.end - e.start);
  }
}
const receipt = { проверка: 'успешна', источников: 10, качественных_результатов: 86,
  характеристик_в_доказательстве: 69, прогнозов: 0, тестов: 125,
  визуальная_проверка: false, файл_проверки_sha256: hash(readFileSync(import.meta.path)),
  отчёт_sha256: hash(read('review-v1/report.html')) };
const target = resolve(root, 'review-v1/html-verification.json');
const bytes = Buffer.from(JSON.stringify(receipt, null, 2) + '\n');
try { writeFileSync(target, bytes, { flag: 'wx' }); }
catch (error) { if (error.code !== 'EEXIST') throw error; assert.deepEqual(readFileSync(target), bytes); }
console.log(JSON.stringify(receipt));
