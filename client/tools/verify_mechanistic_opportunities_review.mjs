// Проверка русского автономного отчёта, фиксации прогноза и исходных фрагментов.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';

const file = path.resolve(process.argv[2]), folder = path.dirname(file);
const read = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const data = read(path.join(folder, 'data.json')), v = data.verification;
const dom = new JSDOM(fs.readFileSync(file, 'utf8')).window.document;
assert.equal(dom.documentElement.lang, 'ru');
assert.equal(dom.querySelectorAll('script,[src],iframe,link[rel="stylesheet"],[lang="en"]').length, 0);
assert.equal(dom.querySelectorAll('.hypothesis').length, 3);
assert.equal(dom.querySelectorAll('tbody tr').length, 4);
assert.ok(dom.querySelector('svg[aria-label]'));
assert.match(dom.body.textContent, /Преимущество графа не доказано/);
assert.match(dom.body.textContent, /759 блокам/);
for (const a of dom.querySelectorAll('a[href]')) {
  assert.ok(!/^(https?:|\/\/)/.test(a.getAttribute('href')));
  assert.ok(fs.existsSync(path.resolve(folder, a.getAttribute('href'))));
}
assert.equal(v.canonical_blocks, 390); assert.equal(v.statements, 958);
assert.equal(v.licensed_parent_blocks, 8); assert.equal(v.python_tests_passed, 258);
assert.equal(v.model_calls, 0); assert.equal(v.graph_advantage_demonstrated, false);
const run = path.resolve(folder, '../runs', v.run_id);
assert.deepEqual(read(path.join(run, 'predictions.json')), data.forecast);
assert.deepEqual(read(path.join(run, 'evaluations', v.evaluation_id + '.json')), data.assessment);
assert.equal(read(path.join(run, 'seal.json')).prediction_sha256, data.plan.forecast_sha256);
assert.deepEqual(data.assessment.modes.without_dependencies.counts, {direction_match: 2, not_addressed: 1});
assert.deepEqual(data.assessment.modes.permuted_dependencies.counts, {direction_match: 2, not_addressed: 1});
assert.equal(data.assessment.modes.graph.candidates, 0);
const source = read(path.resolve(folder, '../control-sources/pmc9612380/source-v2.json'));
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
assert.equal(hash(source.text), source.sha256);
assert.equal(v.source_coverage.references_preserved, 58);
assert.equal(v.source_coverage.captions_preserved, 11);
for (const observation of data.control.observations) for (const e of [...observation.context_evidence, ...observation.evidence]) {
  assert.equal([...source.text].slice(e.start, e.end).join(''), e.text);
  assert.equal(hash(e.text), e.sha256); assert.ok(e.end <= source.content_end);
}
for (const c of data.forecast.candidates.without_dependencies) {
  assert.equal(c.premises.length, 4); assert.equal(c.cautions.length, 4);
  assert.equal(c.logical_entailment, false);
  for (const p of c.premises) assert.ok(data.forecast.facet_proofs[p.facet_sha256].complete_parent_frame);
}
const verification = {passed: true, language: 'ru', external_resources: 0, source_fragments_verified: true,
  frozen_forecast_verified: true, hypotheses: 3, direction_matches: 2, unmeasured: 1,
  scientific_success: false, graph_advantage_demonstrated: false, visual_inspection: false};
const output = path.join(folder, 'html-verification.json'), text = JSON.stringify(verification, null, 2) + '\n';
if (fs.existsSync(output)) assert.equal(fs.readFileSync(output, 'utf8'), text);
else fs.writeFileSync(output, text, {flag: 'wx'});
process.stdout.write(JSON.stringify(verification) + '\n');
