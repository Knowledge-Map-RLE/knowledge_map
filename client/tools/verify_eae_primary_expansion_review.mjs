// Проверка автономных артефактов, научных ограничений и точных источников.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/eae-primary-map-v1');
const read = name => readFileSync(resolve(root, name));
const json = name => JSON.parse(read(name).toString('utf8'));
const hash = value => createHash('sha256').update(value).digest('hex');
const v = json('review-v1/verification.json');
const report = read('review-v1/report.html').toString('utf8');
assert.equal(hash(Buffer.from(report)), v.report_html_sha256);
assert.equal(hash(read('test-results-v2.xml')), v.test_results_sha256);
assert.equal(hash(read('build_review.py')), v.report_code_sha256);
assert.equal(hash(readFileSync(resolve(root, '../../../api/tests/test_eae_primary_map_artifact.py'))), v.test_code_sha256);
assert.match(report, /<html lang="ru">/);
assert.doesNotMatch(report, /<(?:script|iframe|link)\b|(?:src|href)\s*=\s*["'](?:https?:|\/\/)/i);
assert.equal(v.python_tests_passed, 130);
assert.equal(v.source_count, 10);
assert.equal(v.canonical_blocks, 890);
assert.equal(v.native_statements, 1797);
assert.equal(v.old_qualitative_premises, 22);
assert.equal(v.new_qualitative_premises, 58);
assert.equal(v.confirmed_predictions, 0);
assert.equal(v.accuracy, null);
assert.equal(v.scientific_success, false);
assert.equal(v.graph_advantage_demonstrated, false);
assert.equal(v.model_calls, 0);
assert.equal(v.live_ui_published, false);
assert.equal(v.source_coverage.expert_verified_complete_semantic_coverage, false);
assert.equal(v.source_coverage.declared_complete_semantic_coverage, false);
assert.ok(report.includes('Критерий успеха не достигнут'));

const mapPath = `maps/${v.map_run_id}`;
const manifest = json(`${mapPath}/manifest.json`);
for (const [name, digest] of Object.entries(manifest.files)) assert.equal(hash(read(`${mapPath}/${name}`)), digest);
const map = json(`${mapPath}/map.json`);
assert.equal(map.graph.schema_version, 6);
assert.equal(map.graph.knowledge.length, 78);
assert.equal(map.graph.analysis.statement_count, 204);
assert.equal(map.graph.analysis.depth, 6);
assert.equal(hash(Buffer.from(map.source.text, 'utf8')), v.source_sha256);
const points = Array.from(map.source.text);
for (const u of map.source.units) assert.equal(points.slice(u.start, u.end).join(''), u.text);
assert.equal(map.source.units.length, 105);
assert.ok(Object.keys(map.translations.ru.labels).length >= map.graph.nodes.length);
assert.equal(map.translations.ru.run_id, map.run_id);
const mapHtml = read(`${mapPath}/map.html`).toString('utf8');
assert.doesNotMatch(mapHtml, /<(?:script|iframe|link)\b[^>]*(?:src|href)\s*=\s*["'](?:https?:|\/\/)/i);
assert.doesNotMatch(mapHtml, /\bfetch\s*\(/);
const embedded = /<script id="data" type="application\/json">([\s\S]*?)<\/script>/.exec(mapHtml);
assert.deepEqual(JSON.parse(embedded[1]), map);
const scripts = [...mapHtml.matchAll(/<script>([\s\S]*?)<\/script>/g)];
assert.equal(scripts.length, 1);
new Function(scripts[0][1]);
assert.ok(mapHtml.includes('id="language"') && mapHtml.includes('id="source"'));

const a = json(`forecast-runs/${v.analogy_run_id}/predictions.json`);
const p = json(`part-forecast-runs/${v.part_forecast_run_id}/predictions.json`);
assert.deepEqual(a.pool_counts, { scope_matched: 0, transport_required: 4 });
assert.deepEqual(a.ablation.visible_dependencies, a.ablation.without_visible_dependencies);
assert.equal(a.ablation.same_proposal_ids, true);
assert.equal(a.future_results_scored, 0);
assert.equal(a.target_read, false);
assert.ok(Object.values(p.predictions).every(values => values.length === 0));
assert.ok(Object.values(p.learning_by_mode).every(mode => mode.primary_supported_rules.length === 0));
for (const [folder, id] of [['forecast-runs', v.analogy_run_id], ['part-forecast-runs', v.part_forecast_run_id]]) {
  const inputs = json(`${folder}/${id}/inputs-manifest.json`);
  assert.equal(inputs.sources.length, 10);
  for (const entry of inputs.sources) {
    const raw = read(`${folder}/${id}/${entry.map_path}`);
    assert.equal(hash(raw), entry.map_file_sha256);
    const sourceMap = JSON.parse(raw);
    assert.equal(hash(Buffer.from(sourceMap.source.text)), sourceMap.source.sha256);
    assert.notEqual(sourceMap.source.sha256, 'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
    if (entry.coverage_path) assert.equal(hash(read(`${folder}/${id}/${entry.coverage_path}`)), entry.coverage_sha256);
  }
}
const receipt = { passed: true, report_html_sha256: v.report_html_sha256,
  verifier_sha256: hash(readFileSync(import.meta.path)), python_tests: 130,
  standalone_script_syntax_checked: true, source_unicode_checked: true,
  visual_inspection: false, model_calls: 0, scientific_success: false };
const path = resolve(root, 'review-v1/html-verification.json');
const bytes = Buffer.from(JSON.stringify(receipt, null, 2) + '\n');
try { writeFileSync(path, bytes, { flag: 'wx' }); }
catch (e) { if (e.code !== 'EEXIST') throw e; assert.deepEqual(readFileSync(path), bytes); }
console.log(JSON.stringify(receipt));
