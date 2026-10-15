// Полное покрытие и категории поиска не засчитываются как научный результат.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {JSDOM} from 'jsdom';

const file = path.resolve(process.argv[2]), folder = path.dirname(file);
const read = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const data = read(path.join(folder, 'data.json')), v = data.verification;
const doc = new JSDOM(fs.readFileSync(file, 'utf8')).window.document;
assert.equal(doc.documentElement.lang, 'ru');
assert.equal(doc.querySelectorAll('[src],script,iframe,link[rel="stylesheet"],[lang="en"]').length, 0);
assert.match(doc.body.textContent, /Преимущество графа не доказано/);
assert.match(doc.body.textContent, /Это не 20 прогнозов/);
assert.equal(doc.querySelectorAll('table.sources tbody tr').length, 8);
assert.equal(doc.querySelectorAll('.metric').length, 4);
for (const a of doc.querySelectorAll('a[href]')) {
  assert.ok(!/^(https?:|\/\/)/.test(a.getAttribute('href')));
  assert.ok(fs.existsSync(path.resolve(folder, a.getAttribute('href'))));
}
assert.equal(v.canonical_blocks, 759); assert.equal(v.statements, 1478);
assert.equal(v.nodes, 3199); assert.equal(v.edges, 6127);
assert.equal(v.classified_statements, 1057); assert.equal(v.unregistered_statements, 421);
assert.equal(v.native_shared_motifs, 3); assert.equal(v.family_shared_motifs, 20);
assert.equal(v.new_predictions, 0); assert.equal(v.model_calls, 0); assert.equal(v.target_reads, 0);
assert.equal(v.scientific_success, false); assert.equal(v.graph_advantage_demonstrated, false);
assert.equal(v.python_tests_passed, 286);
assert.equal(data.coverage.length, 759);
assert.equal(data.coverage.reduce((n, r) => n + r.count, 0), 1478);
assert.equal(data.routing_ledger.length, 1478);
assert.equal(new Set(data.routing_ledger.map(r => r.statement_id)).size, 1478);
assert.ok(data.routing_ledger.every(r => !r.forecast_licensed && !r.semantic_equivalence_established));
const runs = path.resolve(folder, '../runs');
const current = read(path.join(runs, v.run_id, 'predictions.json'));
const base = read(path.join(runs, v.base_run_id, 'predictions.json'));
assert.deepEqual(current.semantic_graph, base.semantic_graph);
assert.deepEqual(current.binding.map_hashes, base.binding.map_hashes);
assert.deepEqual(current.motif_inventory, base.motif_inventory);
assert.equal(current.semantic_graph.statement_count, 1478);
for (const statement of Object.values(current.semantic_graph.statements)) {
  const parent = current.semantic_graph.parents[statement.parent].complete_parent;
  assert.deepEqual(statement.original_statement, parent.semantic_frame.statements[statement.position]);
  assert.equal(statement.independent_premise_licensed, false);
  for (const evidence of statement.evidence) assert.ok(current.semantic_graph.source_units[evidence]);
}
assert.ok(current.family_motif_inventory.patterns.every(p => !p.inference_licensed));
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
for (const run of [v.run_id, v.base_run_id]) {
  const result = read(path.join(runs, run, 'predictions.json'));
  for (const [name, digest] of Object.entries(result.binding.implementation)) {
    assert.equal(hash(fs.readFileSync(path.join(runs, run, 'implementation', name))), digest);
  }
}
const result = {passed: true, language: 'ru', external_resources: 0, full_statement_coverage_verified: true,
  paired_graph_identical: true, canonical_blocks: 759, statements: 1478, new_predictions: 0,
  scientific_success: false, graph_advantage_demonstrated: false, visual_inspection: false};
const output = path.join(folder, 'html-verification.json'), raw = JSON.stringify(result, null, 2) + '\n';
if (fs.existsSync(output)) assert.equal(fs.readFileSync(output, 'utf8'), raw);
else fs.writeFileSync(output, raw, {flag: 'wx'});
process.stdout.write(JSON.stringify(result) + '\n');
