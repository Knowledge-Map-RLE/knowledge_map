// Независимо сверяются печать запуска, состав кандидатов и автономный русский отчёт.
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {rawJsonFingerprint} from './raw_json_fingerprint.mjs';

const runId=process.argv[2];assert.match(runId,/^[a-f0-9]{64}$/,'Укажите id запечатанного запуска');
const run=resolve(import.meta.dir,`../../eval/whole_map_forecast/timed-protocol-hypotheses-v1/runs/${runId}`);
const read=p=>readFileSync(p),json=p=>JSON.parse(read(p)),hash=b=>createHash('sha256').update(b).digest('hex');
const predictionBytes=read(resolve(run,'predictions.json')),result=JSON.parse(predictionBytes);
const seal=json(resolve(run,'seal.json'));
assert.equal(result.run_id,runId);assert.equal(rawJsonFingerprint(predictionBytes),seal.prediction_sha256);
assert.equal(rawJsonFingerprint(Buffer.from(JSON.stringify(result.binding))),runId);
assert.equal(result.version,'source-bound-timed-protocol-hypotheses-3');assert.equal(result.question,null);
assert.equal(result.canonical_blocks,943);assert.equal(result.semantic_statements,1897);
assert.equal(result.input_inventory.length,943);assert.equal(result.licensed_source_cases,2);
assert.equal(result.operator_coverage_is_whole_corpus,false);assert.equal(result.model_calls,0);assert.equal(result.target_read,false);
assert.equal(result.qualified_new_scientific_forecasts,0);assert.equal(result.scientific_success,false);
assert.equal(result.graph_advantage_demonstrated,false);assert.equal(result.new_independent_outcomes_read,false);
const graph=result.modes.graph,semantic=result.modes.same_facts_without_dependencies,permuted=result.modes.permuted_dependencies;
assert.equal(graph.length,3);assert.equal(semantic.length,3);assert.equal(permuted.length,0);
assert.deepEqual(graph.map(x=>x.id).sort(),semantic.map(x=>x.id).sort());
assert.ok(graph.every(x=>x.status==='exploratory_counterfactual_candidate'&&!x.valid_universal_rule&&!x.deductively_entailed
  &&!x.expert_validated&&!x.novelty.absence_from_all_source_texts_established&&!x.novelty.new_scientific_knowledge_confirmed));
assert.ok(graph.every(x=>x.scenario.assessed_coordinate==='17'&&x.scenario.unit==='source_day_coordinate'
  &&x.scenario.clock_type==='first_administration_of_this_proposed_episode'));
assert.ok(graph.every(x=>x.head.time_quantifier==='specified_relative_time_from_first_administration'
  &&x.head.assessment_time.value==='17'&&x.head.assessment_time.anchor==='first_administration_of_this_proposed_episode'
  &&x.head.effect_size===null&&x.head.statistical_significance===null&&x.head.clinical_causality_proven===false));
assert.ok(graph.every(x=>x.scenario.comparator_source_case===x.scenario.intervention_source_case
  &&x.scenario.comparator&&x.scenario.comparator_label&&x.support_witness_ids.length===2&&x.support_primary_families.length===2
  &&x.body.length===4&&x.body.slice(1).every(b=>b.kind==='action'&&b.action_status==='planned')));
assert.equal(new Set(graph.map(x=>x.scenario.dose.value+' '+x.scenario.dose.unit)).size,3);
const implementation=result.binding.implementation;
for(const [file,digest]of Object.entries(implementation))assert.equal(hash(read(resolve(run,'implementation',file))),digest,`Хеш снимка кода: ${file}`);

const reviewDir=resolve(import.meta.dir,'../../eval/whole_map_forecast/timed-protocol-hypotheses-v1/runs',runId,'review-v2');
const report=json(resolve(reviewDir,'verification.json'));
assert.equal(report.version,'timed-protocol-hypothesis-report-3');
assert.equal(report.run_id,runId);assert.equal(report.prediction_sha256,seal.prediction_sha256);
const md=read(resolve(reviewDir,'report.ru.md')),html=read(resolve(reviewDir,'report.html'));
assert.equal(hash(md),report.report_ru_sha256);assert.equal(hash(html),report.report_html_sha256);
assert.equal(hash(read(resolve(import.meta.dir,'../../api/tools/render_timed_protocol_hypotheses.py'))),report.renderer_sha256);
const doc=new JSDOM(html.toString()).window.document;
assert.equal(doc.documentElement.lang,'ru');assert.equal(doc.querySelectorAll('script,link[href]').length,0);
assert.equal(doc.querySelectorAll('article').length,3);assert.equal(doc.querySelectorAll('img').length,0);
assert.match(doc.body.textContent,/Критерий научного успеха не достигнут/);
assert.match(md.toString(),/через 17 дней после первого введения/);
assert.match(md.toString(),/943 знаний/);
assert.doesNotMatch(md.toString(),/microgram|mg\/kg|dependency|in vivo|female|mice/);
const proof={version:'timed-protocol-hypotheses-independent-check-1',run_id:runId,
  whole_corpus_blocks:result.canonical_blocks,semantic_statements:result.semantic_statements,
  source_cases:result.licensed_source_cases,graph_candidates:graph.length,semantic_candidates:semantic.length,
  permuted_candidates:permuted.length,graph_equals_semantic: true,relative_time_anchor_verified:true,
  comparator_explicit:true,planned_actions_only:true,new_scientific_forecasts:0,graph_advantage_demonstrated:false,
  model_calls:0,target_read:false,offline_russian_report:true,verifier_sha256:hash(read(import.meta.filename)),
  fingerprint_helper_sha256:hash(read(resolve(import.meta.dir,'raw_json_fingerprint.mjs')))};
const out=resolve(reviewDir,'bun-verification.json'),bytes=Buffer.from(JSON.stringify(proof,null,2)+'\n');
if(existsSync(out))assert.deepEqual(read(out),bytes);else writeFileSync(out,bytes,{flag:'wx'});
console.log(JSON.stringify(proof));
