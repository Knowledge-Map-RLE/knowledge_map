"""Подготавливает типизированные условия переноса и ссылки на первичные методы."""
import argparse
import json
from pathlib import Path
from domain.article_maps import fingerprint,require
from domain.incidence_transfer_scope import VERSION,validate_scope
from infrastructure.immutable_files import write_immutable
from infrastructure.development_prediction_store import FilePredictionStore
from tools.run_free_prediction import disable_network

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True);parser.add_argument('--primary',required=True)
    args=parser.parse_args();disable_network()
    ROOT=Path(args.root).resolve();PRIMARY=Path(args.primary).resolve()
    spec=json.loads((ROOT/'context-spec.json').read_text(encoding='utf-8'))
    require(set(spec)=={'version','author','expert_validated','settings'} and spec['version']==VERSION and
            spec['author']=='Codex' and spec['expert_validated'] is False,'Invalid context annotation')
    SETTINGS=spec['settings']
    annotations=json.loads((PRIMARY/'annotation-spec.json').read_text(encoding='utf-8'))
    evidence=json.loads((PRIMARY/'source-evidence.json').read_text(encoding='utf-8'))
    base_path=(PRIMARY/'prepared/inputs-manifest.json').resolve();base=json.loads(base_path.read_text(encoding='utf-8'))
    scopes={}
    for source,settings in SETTINGS.items():
        profile=annotations['profiles'][source];critical={k:v for k,v in settings.items() if k!='phenotypes'}
        critical.update(population='general_older_adults',baseline_status='no_mci_no_dementia',sex='all',
                        measure='incidence_rate',unit='per1000personyears')
        provenance=[]
        for page in profile['methods_pages']:
            p=evidence[source+':methods-'+str(page)]
            provenance.append({k:p[k] for k in ['source_id','source_sha256','start','end','offset_encoding','text_sha256','pdf_page']}
                              | {'kind':'methods_or_definition'})
        # Возраст Mayo подтверждён сноской, но числовая таблица в предиктор не попадает.
        if source=='roberts2012':
            text=(PRIMARY/'sources'/source/'article.layout.txt').read_text(encoding='utf-8')
            import re
            m=re.search(r'Age at baseline\.',text);require(m is not None,'Baseline-age footnote missing')
            from domain.article_maps import digest
            provenance.append({'source_id':source,'source_sha256':evidence[source+':table']['source_sha256'],
                'start':m.start(),'end':m.end(),'offset_encoding':'unicode_codepoints',
                'text_sha256':digest(m.group()),'pdf_page':5,'kind':'methods_or_definition'})
        for endpoint,phenotype in settings['phenotypes'].items():
            c={**critical,'phenotype':phenotype}
            if source=='katz2012' and endpoint=='naMCI':
                c.update(threshold_rule='sd1_5',complaint_rule=None)
            scope={'critical':c,'moderators':{'country':profile['country'],
                'calendar_period':profile['extra'].get('baseline_frame'),
                'followup':profile['followup'],'sample_size':profile['riskset']}}
            validate_scope(scope)
            scopes[profile['study']+':'+endpoint]={'study_id':profile['study'],'endpoint':endpoint,
                'source_id':source,'cohort_id':profile['cohort'],'scope':scope,'provenance':provenance}
    registry={'version':VERSION,'author':'Codex','expert_validated':False,
              'scopes':scopes,'source_bindings':base['source_bindings']}
    manifest={'version':VERSION,'base_manifest':str(base_path),'base_manifest_sha256':fingerprint(base),
              'registry':'typed-contexts.json','registry_sha256':fingerprint(registry)}
    write_immutable(ROOT/'prepared/typed-contexts.json',FilePredictionStore.encode(registry))
    write_immutable(ROOT/'prepared/manifest.json',FilePredictionStore.encode(manifest))
    print(json.dumps({'typed_series':len(scopes),'model_calls':0,'future_control_access':False}))


if __name__=='__main__':main()
