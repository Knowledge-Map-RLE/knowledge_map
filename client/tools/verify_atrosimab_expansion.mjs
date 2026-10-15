// Независимая проверка нового источника, таблицы, сохранности корпуса и причин отказов.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { rawJsonFingerprint } from './raw_json_fingerprint.mjs';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/atrosimab-primary-expansion-v1');
const read = p => readFileSync(resolve(root, p));
const json = p => JSON.parse(read(p));
const hash = v => createHash('sha256').update(v).digest('hex');
const verification = json('review-v1/verification.json'), data = json('review-v1/data.json');
for (const [p, h] of Object.entries(verification.inputs)) assert.equal(hash(readFileSync(p)), h);
for (const [p, h] of Object.entries(verification.files)) assert.equal(hash(read('review-v1/' + p)), h);
assert.equal(hash(read('build_review.py')), verification.builder_sha256);

function rawField(bytes, name) {
  const text = bytes.toString('utf8'), match = new RegExp('^  "' + name + '":\\s*', 'm').exec(text);
  assert.ok(match, 'Не найдено поле верхнего уровня'); const begin = match.index + match[0].length;
  assert.ok(['{','['].includes(text[begin])); let depth = 0, quoted = false, escaped = false;
  for (let i = begin; i < text.length; i++) {
    const c = text[i];
    if (quoted) { if (escaped) escaped = false; else if (c === '\\') escaped = true; else if (c === '"') quoted = false; continue; }
    if (c === '"') { quoted = true; continue; }
    if (c === '{' || c === '[') depth++; else if (c === '}' || c === ']') depth--;
    if (depth === 0) return Buffer.from(text.slice(begin, i + 1));
  }
  assert.fail('Незавершённое поле JSON');
}
function checkSeal(folder) {
  const raw = read(folder + '/predictions.json'), d = JSON.parse(raw), s = json(folder + '/seal.json');
  assert.equal(rawJsonFingerprint(raw), s.prediction_sha256);
  assert.equal(rawJsonFingerprint(rawField(raw, 'binding')), d.run_id);
  for (const [p, h] of Object.entries(d.binding.implementation)) assert.equal(hash(read(folder + '/implementation/' + p)), h);
  assert.equal(d.model_calls, 0); assert.equal(d.target_read, false);
  assert.equal(d.scientific_success, false); assert.equal(d.graph_advantage_demonstrated, false);
  assert.equal(json(folder + '/reads.json').network_disabled, true);
  return d;
}
const forecast = checkSeal('part-runs/' + data.part_run), circuit = checkSeal('circuit-runs/' + data.circuit_run);
const manifest = json('prepared-v1/sources.json'); assert.equal(manifest.sources.length, 11);
const oldRoot = resolve(root, '../template-context-audit-v1/runs/' + data.baseline_run);
const oldManifest = JSON.parse(readFileSync(resolve(oldRoot, 'source-manifest.json')));
assert.deepEqual(manifest.sources.slice(0, -1), oldManifest.sources);
const baseline = JSON.parse(readFileSync(resolve(oldRoot, 'predictions.json')));
assert.deepEqual(forecast.binding.implementation, baseline.binding.implementation);
let sourceRefs = 0, statements = 0;
const maps = [];
for (const entry of manifest.sources) {
  const raw = readFileSync(entry.path), m = JSON.parse(raw); maps.push(m);
  assert.equal(hash(raw), entry.file_sha256); assert.equal(rawJsonFingerprint(rawField(raw, 'graph')), entry.graph_sha256);
  assert.equal(hash(Buffer.from(m.source.text)), m.source.sha256); assert.equal(m.source.sha256, entry.source_sha256);
  assert.notEqual(m.source.sha256, data.target_source_sha256_excluded);
  assert.equal(m.graph.schema_version, 6);
  const text = [...m.source.text], units = new Map(m.source.units.map(u => [u.id, u]));
  const knowledge = new Map(m.graph.knowledge.map(k => [k.knowledge_id, k])), concepts = new Set(m.graph.concepts.map(c => c.id));
  const nodes = new Map(m.graph.nodes.map(n => [n.id, n])), edges = new Set();
  assert.equal(nodes.size, m.graph.nodes.length); assert.equal(knowledge.size, m.graph.knowledge.length);
  const pending = new Map([...nodes].map(([id]) => [id, 0])), next = new Map([...nodes].map(([id]) => [id, []]));
  for (const e of m.graph.edges) {
    assert.deepEqual(Object.keys(e).sort(), ['source','target']); assert.ok(nodes.has(e.source) && nodes.has(e.target));
    const key = JSON.stringify([e.source,e.target]); assert.ok(!edges.has(key)); edges.add(key);
    pending.set(e.target, pending.get(e.target) + 1); next.get(e.source).push(e.target);
    assert.ok(nodes.get(e.source).rank < nodes.get(e.target).rank);
  }
  const queue = [...pending].filter(([,n]) => n === 0).map(([id]) => id); let visited = 0;
  while (queue.length) { const id = queue.shift(); visited++; for (const target of next.get(id)) {
    pending.set(target,pending.get(target)-1); if (pending.get(target) === 0) queue.push(target);
  }}
  assert.equal(visited, nodes.size);
  for (const node of nodes.values()) assert.ok(knowledge.has(node.knowledge_id));
  function provenance(p) {
    assert.ok(p.unit_ids.length); for (const id of p.unit_ids) assert.ok(units.has(id));
    for (const span of p.source_spans) {
      assert.ok([...units.values()].some(u => u.start === span.start && u.end === span.end && u.end <= m.source.content_end));
      assert.ok(text.slice(span.start,span.end).join('').length); sourceRefs++;
    }
  }
  for (const k of knowledge.values()) {
    provenance(k.provenance); assert.ok(['state','action'].includes(k.kind));
    for (const s of k.semantic_frame.statements) {
      statements++; provenance(s.provenance);
      for (const role of s.roles) {
        if (role.concept_id !== null) assert.ok(concepts.has(role.concept_id));
        if (role.knowledge_id !== null) assert.ok(knowledge.has(role.knowledge_id));
      }
    }
  }
  for (const t of m.graph.transitions) {
    assert.ok(t.sources.length && nodes.has(t.target));
    for (const source of t.sources) assert.ok(edges.has(JSON.stringify([source,t.target])));
    for (const id of t.unit_ids) assert.ok(units.has(id));
  }
}
assert.equal(statements, 1897); assert.equal(circuit.argument_circuits.statement_count, statements);
assert.equal(Object.keys(circuit.argument_circuits.groups).length, 703);
const m = maps.at(-1), folder = 'maps/' + data.map_run, receipt = json(folder + '/manifest.json');
for (const [p,h] of Object.entries(receipt.files)) assert.equal(hash(read(folder + '/' + p)), h);
assert.equal(m.prompt.version, '4'); assert.equal(m.dependency_prompt.version, '16');
assert.equal(hash(read(folder + '/prompt.extraction.en.md')), m.prompt.sha256);
assert.equal(hash(read(folder + '/prompt.dependencies.en.md')), m.dependency_prompt.sha256);
for (const k of ['external_llm_calls','local_llm_calls','translation_llm_calls','embedding_calls']) assert.equal(m.generation[k],0);
assert.equal(m.generation.token_usage,null);
const packet = json('source/source-v2.json'), source = packet.source, codepoints = [...source.text];
assert.equal(packet.pmcid,'PMC8294390'); assert.equal(packet.doi,'10.3389/fimmu.2021.705485');
assert.equal(packet.reference_count,53); assert.equal((read('source/article.xml').toString('utf8').match(/<ref(?:\s|>)/g)||[]).length,53);
assert.equal(source.units.length,117);
for (const u of source.units) { assert.equal(codepoints.slice(u.start,u.end).join(''),u.text); assert.equal(hash(Buffer.from(u.text)),u.sha256); }
for (const ref of packet.references) assert.ok(source.text.slice(source.content_end).includes(ref.text));
const coverage = json(folder + '/coverage.json'); assert.equal(coverage.units.length,117);
assert.equal(coverage.complete_semantic_coverage,false);
assert.equal(coverage.table_cells_exhaustively_formalized,true);
for (const u of coverage.units) assert.ok(u.status === 'represented' ? u.knowledge_ids.length > 0 : u.reason_ru?.length > 0);
const labels = json(folder + '/translation.ru.json'); assert.deepEqual(Object.keys(labels).sort(),m.graph.knowledge.map(k=>k.knowledge_id).sort());
const rowIds = ['U58','U59','U60','U62','U63','U64','U66','U67','U69','U70'];
const table = m.graph.knowledge.filter(k=>k.semantic_frame.statements[0].predicate === 'reported pharmacokinetic parameter');
assert.equal(table.length,10); let cells = 0, undetermined = 0;
const concepts = new Map(m.graph.concepts.map(c=>[c.id,c.display_text]));
for (let i=0;i<10;i++) {
  const k=table[i], claims=k.semantic_frame.statements, u=source.units.find(u=>u.id===rowIds[i]);
  assert.equal(claims.length,4); assert.ok(k.provenance.unit_ids.includes(u.id));
  const values=u.text.split(' | ').slice(1); assert.equal(values.length,4);
  const route=i<6?'i.v.':'s.c.', dose=[0,1,2,6,7].includes(i)?'30.0':'1.0';
  for (let j=0;j<4;j++) {
    const s=claims[j], a=new Map(s.qualifiers.attributes.map(a=>[a.name,a]));
    assert.equal(a.get('reported mean and SD').value,values[j]); assert.equal(a.get('dose').value,dose); assert.equal(a.get('route').value,route);
    const roles=new Map(s.roles.map(r=>[r.role,concepts.get(r.concept_id)]));
    assert.match(roles.get('population'),j<2?/huTNFR1-k\/i/:/wild-type/);
    assert.match(roles.get('intervention'),j%2===0?/^Atrosimab/:/^Atrosab/);
    if (values[j]==='n.d.') { undetermined++; assert.ok(!a.has('reported mean')&&!a.has('reported SD')); }
    else { const [mean,sd]=values[j].split(' ± '); assert.equal(a.get('reported mean').value,mean); assert.equal(a.get('reported SD').value,sd); }
    cells++;
  }
}
assert.equal(cells,40); assert.equal(undetermined,1);
for (const row of data.modes) {
  assert.equal(forecast.predictions[row.mode].length,0); assert.equal(baseline.predictions[row.mode].length,0);
}
assert.equal(data.rejected.length,14);
const actualRejected=forecast.learning_by_mode.graph.learning.rejected_groups.filter(r=>r.head[0]===m.article_id);
assert.equal(actualRejected.length,14);
for (const r of data.rejected) assert.ok(actualRejected.some(a=>JSON.stringify(a.head)===JSON.stringify(r.part_key)&&a.reason===r.reason));
const html=read('review-v1/report.html').toString('utf8');
assert.match(html,/<html lang="ru">/); assert.match(html,/Новых подтверждённых прогнозов — 0/);
for (const name of ['review-v1/report.html',folder+'/map.html']) {
  const text=read(name).toString('utf8'); assert.doesNotMatch(text,/<script[^>]*\bsrc\s*=/i);
  assert.doesNotMatch(text,/<(?:link|img|iframe)[^>]*(?:src|href)\s*=\s*["']https?:/i);
}
const output={source_maps:11,knowledge:943,statements,table_cells:cells,undetermined_cells:undetermined,
  source_references_checked:sourceRefs,visible_dags_checked:11,rejected_alignments:14,model_calls:0,
  new_predictions:0,graph_advantage_demonstrated:false,scientific_validation:false,
  verifier_sha256:hash(readFileSync(import.meta.path)),json_helper_sha256:hash(readFileSync(resolve(import.meta.dir,'raw_json_fingerprint.mjs')))};
const path=resolve(root,'review-v1/bun-verification.json'), bytes=Buffer.from(JSON.stringify(output,null,2)+'\n');
try { writeFileSync(path,bytes,{flag:'wx'}); } catch(error) { if(error.code!=='EEXIST') throw error; assert.deepEqual(readFileSync(path),bytes); }
console.log(JSON.stringify(output));
