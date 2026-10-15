"""Функциональный источник и рецептор модели не заменяются одним фактом связывания."""
from copy import deepcopy
from hashlib import sha256
import re
from domain.article_maps import fingerprint,require

VERSION='source-bound-functional-target-guard-2'
DOMAIN='human TNFR1 extracellular binding domain'


def functional_evidence_sufficient(binding_reported,inhibition_reported,model_domain,target_domain):
    """Проверка происхождения предпосылки, без вывода эффективности в живом организме."""
    require(type(binding_reported) is bool and type(inhibition_reported) is bool,'Explicit source evidence statuses required')
    return binding_reported and inhibition_reported and bool(model_domain) and bool(target_domain) and model_domain==target_domain


def compile_guards(orientation,frozen,maps,cases,audit):
    require(orientation['run_id']==fingerprint(orientation['binding']) and orientation['version']=='source-bound-measurement-orientation-1'
            and audit['version']==VERSION and audit['author']=='Codex' and audit['expert_validated'] is False
            and audit['model_calls']==0 and audit['source_sha256']==fingerprint(frozen)
            and audit['map_hashes']==[fingerprint(m) for m in maps],'Functional guard provenance differs')
    catalog={m['article_id']:m for m in maps};case_index={c['case_id']:c for c in cases}
    certificates=[];case_guards={};seen=set()
    for e in audit['entries']:
        article=e['article_id'];require(article in catalog and article not in seen,'Unknown or repeated functional source');seen.add(article)
        m=catalog[article];native={k['knowledge_id']:k for k in m['graph']['knowledge']}
        require(e['run_id']==m['run_id'] and e['source_sha256']==m['source']['sha256'],'Functional source binding differs')
        require(len(e['case_ids'])==len(set(e['case_ids'])) and all(c in case_index for c in e['case_ids']),'Unknown or repeated functional case')
        source_cases=[case_index[c] for c in e['case_ids']]
        require(source_cases and all(c['article_id']==article for c in source_cases),'Functional guard crosses articles')
        people={next(r['value'] for r in c['method']['frame']['statements'][0]['roles'] if r['role']=='population') for c in source_cases}
        agents={next(r['value'] for r in c['method']['frame']['statements'][0]['roles'] if r['role']=='intervention') for c in source_cases}
        require(len(people)==len(agents)==1 and next(iter(agents))==e['intervention'],'Mechanism belongs to another intervention/model')
        require(e['required_target_domain']==e['model_target_domain']==DOMAIN,'Unsupported or mismatched receptor domain')
        full_parents=[];units={u['id']:u for u in m['source']['units']}
        for evidence in e['evidence']:
            kid=evidence['knowledge_id'];require(kid in native,'Unknown mechanism parent')
            parent=native[kid];allowed={uid for s in parent['semantic_frame']['statements'] for uid in s['provenance']['unit_ids']}
            q=evidence['quote'];u=units.get(q['unit_id']);require(u is not None and q['unit_id'] in allowed,'Functional evidence outside parent source')
            require(u['start']<=q['start']<q['end']<=u['end']<=m['source']['content_end']
                and m['source']['text'][q['start']:q['end']]==q['text'] and sha256(q['text'].encode()).hexdigest()==q['sha256'],
                'Functional evidence fragment changed')
            require(evidence['kind'] in {'binding','inhibition','model_domain','source_antagonist_interpretation'},'Unregistered functional evidence kind')
            if not any(p['knowledge_id']==kid for p in full_parents):full_parents.append(deepcopy(parent))
        by_kind={kind:[x['quote']['text'] for x in e['evidence'] if x['kind']==kind] for kind in ('binding','inhibition','model_domain')}
        require(all(by_kind.values()),'Binding alone is not functional inhibition or model compatibility')
        require(any(re.search(r'\bbind(?:s|ing)?\b',text,re.I) for text in by_kind['binding']),'Positive receptor binding claim required')
        require(any('TNFR1' in text and ('human' in text or 'hTNFR1' in text) for text in by_kind['binding']),
                'Binding to the required human receptor domain not reported')
        require(bool(re.search(r'\b'+re.escape(e['agent_alias'])+r'\b',e['intervention'],re.I)),'Mechanism alias does not identify the intervention')
        require(any(re.search(r'\b'+re.escape(e['agent_alias'])+r'\b',text,re.I) and (
            'inhibits the TNF/hTNFR1 pathway' in text or 'showed a dose-dependent inhibition of the TNF-induced IL-8 release' in text)
            for text in by_kind['inhibition']),'Functional inhibition is not licensed by binding or non-detection')
        require(any('expressing hTNFR1' in text or 'extracellular domains of human TNFR1' in text for text in by_kind['model_domain']),
                'Model receptor domain not explicitly supported')
        require(e['functional_origin'] in {'cited_or_prior_report','own_report_with_unread_supplement'},'Functional origin not declared')
        functional_parents=[native[x['knowledge_id']]for x in e['evidence']if x['kind']=='inhibition']
        presentations={a['value']for p in functional_parents for s in p['semantic_frame']['statements']
                       for a in s['qualifiers']['attributes']if a['name']=='evidence_presentation'}
        require((presentations=={'background'} and e['functional_origin']=='cited_or_prior_report')
                or (presentations=={'own_result'} and e['functional_origin']=='own_report_with_unread_supplement'),
                'Functional observation origin does not match full source parents')
        frame=e['functional_frame']
        require(frame['kind']=='state' and frame['logic']=='single' and frame['action_status'] is None
                and len(frame['statements'])==1,'Functional assertion must be a source-scoped state')
        fs=frame['statements'][0];fr={r['role']:r['value']for r in fs['roles']}
        require(len(fr)==len(fs['roles']) and fr.get('intervention')==e['intervention'] and not fs['negated']
                and fs['scope']['conditions'] and fs['scope']['study_group']==article,
                'Functional semantics lost agent or scope')
        require((e['agent_alias']=='TROS' and fs['predicate']=='reported pathway inhibition'
                    and fr.get('target')=='human TNFR1' and fr.get('ligand')=='tumor necrosis factor alpha')
                or (e['agent_alias']=='Atrosimab' and fs['predicate']=='reported inhibition of stimulated release'
                    and fr.get('stimulus')=='tumor necrosis factor alpha' and fr.get('outcome')=='interleukin 8 release'
                    and fr.get('assay population')=='HT1080 cells' and 'target' not in fr),
                'Unlicensed functional mechanism or inferred receptor causation')
        expected_roles={'intervention':e['intervention']}
        if e['agent_alias']=='TROS':
            expected_roles.update(ligand='tumor necrosis factor alpha',target='human TNFR1',
                                  systems='in vitro; ex vivo; in vivo in partially humanized mice')
        else:
            expected_roles.update(stimulus='tumor necrosis factor alpha',outcome='interleukin 8 release')
            expected_roles['assay population']='HT1080 cells'
        require(fr==expected_roles and all(r['reference_kind']=='concept' for r in fs['roles'])
                and fs['negated'] is False and fs['attributes']==[]
                and fs['scope']=={'conditions':by_kind['inhibition'],'study_group':article,
                    'modality':'reported source claim','quantifier':None,
                    'time':'reported functional context; no clinical time window inferred'},
                'Functional frame adds unlicensed participants, quantities or clinical scope')
        require(functional_evidence_sufficient(True,True,e['model_target_domain'],e['required_target_domain']),'Functional prerequisites incomplete')
        certificate={'article_id':article,'case_ids':e['case_ids'],'intervention':e['intervention'],'population':next(iter(people)),
            'required_target_domain':DOMAIN,'full_native_parents':full_parents,'evidence':deepcopy(e['evidence']),
            'functional_frame':deepcopy(frame),'original_functional_source_attributes':[
                {'knowledge_id':p['knowledge_id'],'statements':deepcopy(p['semantic_frame']['statements'])}for p in functional_parents],
            'source_functional_context_ru':e['functional_context_ru'],'source_model_context_ru':e['model_context_ru'],
            'functional_origin':e['functional_origin'],'source_binding_and_inhibition_are_distinct':True,
            'structural_target_compatibility_supported':True,'in_vivo_target_engagement_established':False,
            'brain_delivery_established':False,'tnfr2_functional_preservation_established':False,
            'pure_antagonism_all_doses_established':False,'clinical_efficacy_inferred':False,
            'mechanism_from_clinical_efficacy_inferred':False,'extra_primary_clinical_replications':0,
            'source_report_status':'reported_functional_activity_and_model_compatibility_only','expert_validated':False}
        certificate['id']=fingerprint(certificate);certificates.append(certificate)
        for cid in e['case_ids']:
            require(cid not in case_guards,'Repeated functional case guard');case_guards[cid]=certificate['id']
    require(set(case_guards)=={p['case_id'] for p in orientation['orientation_proofs']},'Functional guard must cover the exact selected prototype cases')
    groups=orientation['policies']['source_bound_measurement_orientation']['graph']['guard_barriers']
    bound=[]
    for group in groups:
        head=group['structure']['head']['statements'][0]
        measurement=next(f for f in group['structure']['body'] if f['statements'][0]['predicate']=='measure clinical course')
        value=next(r['value'] for r in head['roles'] if r['role']=='outcome')
        if 'variable' in value and value==next(r['value'] for r in measurement['statements'][0]['roles'] if r['role']=='outcome'):bound.append(group)
    require(len(bound)==1,'Exactly one quantity-bound source prototype required')
    core=deepcopy(bound[0]['structure']);head=core['head']['statements'][0]
    roles={r['role']:r['value'] for r in head['roles']}
    guard={'kind':'state','action_status':None,'logic':'single','statements':[{
        'predicate':'reported inhibitory function and model binding domain compatibility',
        'roles':[{'role':'intervention','value':roles['intervention'],'reference_kind':'concept'},
                 {'role':'population','value':roles['population'],'reference_kind':'concept'},
                 {'role':'required target domain','value':{'constant':DOMAIN},'reference_kind':'concept'}],
        'scope':{'full_guard_context_binding_pending':True},'attributes':[],'negated':False}]}
    prototype={'body':[guard,*core['body']],'head':core['head'],'original_quantity_bound_prototype_id':bound[0]['id'],
        'source_variants_with_all_constraints':deepcopy(bound[0]['variants']),'certificates':case_guards,
        'primary_families':bound[0]['primary_families'],'guard_was_added_by_compiler':True,'author_asserted_this_three_part_group':False,
        'is_executable_rule':False,'is_future_prediction':False,'clinical_conclusion_deductively_entailed':False,
        'remaining_requirements_ru':['Связать дозы и режимы со своими процедурами без перевода по среднему весу.',
            'Различить биологические часы и неизвестные сроки, сохранить генотипы, пол и исходные инструменты.',
            'Не переносить клеточное ингибирование в утверждение о доказанной блокаде в живом организме.']}
    prototype['id']=fingerprint(prototype)
    return {'version':VERSION,'canonical_blocks':orientation['canonical_blocks'],'semantic_statements':orientation['semantic_statements'],
        'input_parts':orientation['oriented_parts'],'functional_certificates':certificates,'guarded_prototype':prototype,
        'model_calls':0,'target_read':False,'new_empirical_forecasts':0,'scientific_success':False,
        'graph_advantage_demonstrated':False,'independent_future_validation':False}
