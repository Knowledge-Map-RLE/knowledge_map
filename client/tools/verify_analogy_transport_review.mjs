// Проверка автономного отчёта и точных доказательств без внешних ресурсов и моделей.
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/analogy-transport-v1');
const report = JSON.parse(readFileSync(resolve(root, 'review-v1/data.json'), 'utf8'));
const v = report.verification;
const run = resolve(root, 'runs', v.run_id);
const artifact = JSON.parse(readFileSync(resolve(run, 'predictions.json'), 'utf8'));
const manifest = JSON.parse(readFileSync(resolve(run, 'inputs-manifest.json'), 'utf8'));
const html = readFileSync(resolve(root, 'review-v1/report.html'), 'utf8');
const hash = content => createHash('sha256').update(content).digest('hex');
const maps = new Map();
assert.match(html, /lang="ru"/);
assert.doesNotMatch(html, /<(?:script|iframe|link)\b|(?:src|href)\s*=\s*["'](?:https?:|\/\/)/i);
assert.equal(v.python_tests_passed, 91);
assert.equal(hash(readFileSync(resolve(root, 'test-results-v3.xml'))), v.test_results_sha256);
assert.equal(v.new_empirical_predictions, 0);
assert.equal(v.future_results_scored, 0);
assert.equal(v.accuracy, null);
assert.equal(v.scientific_success, false);
assert.equal(v.graph_advantage_demonstrated, false);
assert.equal(artifact.hypotheses.length, 0);
assert.deepEqual(artifact.ablation.visible_dependencies, artifact.ablation.without_visible_dependencies);
assert.equal(artifact.already_tested_gaps.length, 1);
assert.equal(report.rows.length, 4);
assert.equal(artifact.canonical_blocks, 812);
assert.equal(artifact.native_statements, 1593);
assert.equal(artifact.coverage.coverage.length, 812);
for (const input of manifest.sources) {
  const raw = readFileSync(resolve(run, input.map_path));
  assert.equal(hash(raw), input.map_file_sha256);
  const map = JSON.parse(raw);
  assert.equal(hash(Buffer.from(map.source.text, 'utf8')), map.source.sha256);
  const points = Array.from(map.source.text);
  for (const unit of map.source.units) assert.equal(points.slice(unit.start, unit.end).join(''), unit.text);
  maps.set(map.article_id, map);
}
for (const row of report.rows) {
  assert.match(html, new RegExp(`data-candidate="${row.id}"`));
  assert.ok(html.includes(row.task_ru));
  assert.equal(row.candidate.generated_knowledge_kind, 'research_task');
  assert.equal(row.candidate.generated_action_status, 'unresolved');
  assert.equal(row.candidate.logical_entailment, false);
  assert.deepEqual(row.candidate.conclusion_support_families, []);
  assert.equal(row.candidate.quantitative_prediction, null);
  for (const witness of row.candidate.witnesses) {
    assert.equal(witness.premises.length, 3);
    assert.equal(witness.premise_publication_families.length, 1);
    for (const premise of witness.premises) {
      const [article, kid] = premise.native_key;
      const native = maps.get(article).graph.knowledge.find(k => k.knowledge_id === kid);
      assert.deepEqual(premise.complete_projection_proof.complete_native_knowledge, native);
      assert.equal(premise.complete_projection_proof.conditions_removed, false);
    }
  }
  for (const p of row.premises) {
    const points = Array.from(maps.get(p.article_id).source.text);
    for (const unit of p.fragments) assert.equal(points.slice(unit.start, unit.end).join(''), unit.text);
  }
}
for (const [name, digest] of Object.entries(artifact.binding.implementation)) {
  assert.equal(hash(readFileSync(resolve(run, 'implementation', name))), digest);
  assert.equal(hash(readFileSync(resolve(import.meta.dir, '../../api', name))), digest);
}
console.log(JSON.stringify({ ok: true, tasks: 4, empiricalPredictions: 0, pythonTests: 91,
  sourceBindings: true, unicodeOffsets: true, offlineResources: true, visualInspection: false }));
