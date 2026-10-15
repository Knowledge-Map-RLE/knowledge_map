import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { JSDOM } from 'jsdom';

// Автономность и соответствие сохранённым результатам проверяются отдельно от науки.
const file = path.resolve(process.argv[2]), folder = path.dirname(file), root = path.dirname(folder);
const read = name => JSON.parse(fs.readFileSync(name, 'utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const doc = new JSDOM(fs.readFileSync(file, 'utf8')).window.document;
assert.equal(doc.documentElement.lang, 'ru');
assert.equal(doc.querySelectorAll('script,iframe,img,link').length, 0);
assert.equal(doc.querySelectorAll('tbody tr').length, 8);
assert.ok(doc.body.textContent.includes('Критерий успеха не достигнут'));
assert.ok(doc.body.textContent.includes('Точность не определена'));
for (const a of doc.querySelectorAll('a')) {
  const href = a.getAttribute('href');
  assert.ok(!/^[a-z]+:/i.test(href));
  const target = path.resolve(folder, href);
  assert.ok(target.startsWith(root + path.sep) && fs.existsSync(target));
}
const data = read(path.join(folder, 'data.json')), v = data.verification;
assert.equal(v.canonical_blocks, 812); assert.equal(v.template_count, 195); assert.equal(v.exact_rules, 0);
assert.equal(v.model_calls, 0); assert.equal(v.target_read, false); assert.equal(v.new_predictions, 0);
assert.equal(v.scientific_success, false); assert.equal(v.graph_advantage_demonstrated, false);
assert.equal(v.production_forecaster_changed, false); assert.equal(v.accuracy, null);
assert.equal(v.python_tests_passed, 25);
assert.equal(hash(fs.readFileSync(path.join(root, 'test-results-v3.xml'))), v.test_results_sha256);
const runFolder = path.join(root, 'runs', v.run_id), result = read(path.join(runFolder, 'predictions.json'));
assert.equal(result.run_id, v.run_id);
assert.equal(result.binding.forecast_run, v.forecast_run);
assert.equal(result.complete_original_templates.length, 195); assert.equal(result.coverage.length, 812);
assert.equal(result.joint_gate_removal_cannot_help_with_no_rules, true);
assert.equal(result.predictions.length, 0);
assert.deepEqual(result.learning_rejections, data.learning_rejections);
for (const [name, digest] of Object.entries(result.binding.implementation)) {
  const target = path.resolve(runFolder, 'implementation', name);
  assert.ok(target.startsWith(path.join(runFolder, 'implementation') + path.sep));
  assert.equal(hash(fs.readFileSync(target)), digest);
}
for (const [i, row] of data.mode_rows.entries()) {
  const mode = result.modes[row.mode];
  assert.equal(row.shapes, mode.shape_count); assert.equal(row.multiple_publications, 0);
  assert.equal(row.multiple_primary_datasets, 0);
  const cells = [...doc.querySelectorAll('tbody tr')[i].querySelectorAll('td')].map(c => c.textContent);
  assert.deepEqual(cells, [row.label_ru, String(row.shapes), '0', '0']);
  assert.ok(mode.groups.every(g => !g.inference_licensed && !g.context_equivalence_established));
}
const check = { passed: true, language: 'ru', external_resources: 0, diagnostic_modes: 8,
  whole_map_blocks: 812, unsupported_templates: 195, python_tests_passed: 25,
  new_predictions: 0, scientific_success: false, graph_advantage_demonstrated: false,
  visual_inspection: false };
const output = path.join(folder, 'html-verification.json'), bytes = JSON.stringify(check, null, 2) + '\n';
if (fs.existsSync(output)) assert.equal(fs.readFileSync(output, 'utf8'), bytes);
else fs.writeFileSync(output, bytes, { flag: 'wx' });
console.log(JSON.stringify(check));
