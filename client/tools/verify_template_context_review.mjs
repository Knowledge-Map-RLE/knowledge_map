// Проверка русского автономного отчёта и неизменности прогнозов при диагностических масках.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

const base = resolve(import.meta.dir, '../../eval/whole_map_forecast');
const root = resolve(base, 'template-context-audit-v1');
const read = path => readFileSync(resolve(root, path));
const json = path => JSON.parse(read(path).toString('utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const v = json('review-v1/verification.json');
for (const [file, digest] of Object.entries(v.files)) assert.equal(hash(read(`review-v1/${file}`)), digest);
for (const [file, digest] of Object.entries(v.input_files)) assert.equal(hash(readFileSync(resolve(base, file))), digest);
assert.equal(hash(read('build_review.py')), v.builder_sha256);
assert.equal(hash(read('test-results-v1.xml')), v.tests_sha256);
assert.equal(v.tests_passed, 43);
assert.equal(v.domain_seals_validated, true);
assert.equal(v.source_method_proofs_checked, 15);
assert.equal(v.native_transition_groups_checked, 21);
const report = read('review-v1/report.html').toString('utf8');
assert.match(report, /<html lang="ru">/);
assert.doesNotMatch(report, /<(?:script|iframe|link)\b|(?:src|href)\s*=\s*["'](?:https?:|\/\/)/i);
assert.match(report, /Новых прогнозов: 0/);
const d = json('review-v1/data.json');
assert.equal(d.same_maps, true);
assert.equal(d.same_audits, false);
assert.deepEqual(d.changed_audits, ['context']);
assert.equal(d.generator_unchanged, true);
assert.equal(d.canonical_blocks, 890);
assert.equal(d.parts_before, 794);
assert.equal(d.parts_after, 809);
assert.equal(d.resolved_methods, 15);
assert.equal(d.other_records_unchanged, 875);
assert.equal(d.primary_templates_after, 54);
assert.equal(d.all_action_premise_templates, 53);
assert.equal(d.distinct_native_heads, 21);
assert.ok(d.diagnostic_levels.every(r => r.cross_primary_clusters.length === 0 && r.rules_admitted === 0));
assert.ok(Object.values(d.predictions).every(n => n === 0));
assert.equal(d.scientific_success, false);
assert.equal(d.graph_advantage_demonstrated, false);
assert.equal(d.target_read, false);
assert.equal(d.model_calls, 0);
const analysis = json('analysis-v1/template-context-audit.json');
assert.equal(analysis.masks_used_for_generation, false);
assert.equal(analysis.forecasts_modified, false);
const usage = json('analysis-v1/transition-usage-audit.json');
assert.equal(usage.distinct_native_groups, 21);
assert.equal(usage.primary_template_examples, 54);
for (const row of usage.rows) for (const proof of row.full_author_transitions) {
  assert.ok(proof.transition.reason.length > 0);
  for (const e of proof.evidence) assert.equal(Array.from(e.text).length, e.end - e.start);
}
const receipt = { проверка: 'успешна', источников: 10, восстановленных_методов: 15,
  первичных_шаблонов: 54, прогнозов: 0, тестов: 43, визуальная_проверка: false,
  файл_проверки_sha256: hash(readFileSync(import.meta.path)), отчёт_sha256: hash(read('review-v1/report.html')) };
const target = resolve(root, 'review-v1/html-verification.json');
const bytes = Buffer.from(JSON.stringify(receipt, null, 2) + '\n');
try { writeFileSync(target, bytes, { flag: 'wx' }); }
catch (error) { if (error.code !== 'EEXIST') throw error; assert.deepEqual(readFileSync(target), bytes); }
console.log(JSON.stringify(receipt));
