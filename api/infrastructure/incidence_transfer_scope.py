"""Файловый порт: только зарегистрированные контексты и прежние разбиения."""
import json
from pathlib import Path

from domain.article_maps import require,fingerprint
from domain.incidence_transfer_scope import validate_scope,VERSION
from infrastructure.cohort_transfer_files import FileCohortTransferInputs


class FileIncidenceScopeInputs:
    def __init__(self,manifest):self.path=Path(manifest).resolve();self.reads=[]

    def read_inputs(self):
        manifest=json.loads(self.path.read_text(encoding='utf-8'));self.reads.append(str(self.path))
        require(set(manifest)=={'version','base_manifest','base_manifest_sha256','registry','registry_sha256'},'Scope manifest must not contain controls')
        require(manifest['version']==VERSION,'Unsupported incidence scope version')
        registry_path=(self.path.parent/manifest['registry']).resolve()
        require(registry_path.parent==self.path.parent,'Registry path outside explicit preparation')
        registry=json.loads(registry_path.read_text(encoding='utf-8'));self.reads.append(str(registry_path))
        require(fingerprint(registry)==manifest['registry_sha256'],'Typed registry changed')
        require(set(registry)=={'version','author','expert_validated','scopes','source_bindings'},'Registry contains unknown fields or results')
        require(registry['version']==VERSION and registry['author']=='Codex' and registry['expert_validated'] is False,'Unsupported scope annotation')
        require(isinstance(manifest['base_manifest'],str),'Explicit base manifest required')
        base_path=Path(manifest['base_manifest'])
        require(base_path.is_absolute(),'Base manifest requires an absolute path')
        port=FileCohortTransferInputs(base_path);data=port.read_inputs();self.reads+=port.reads
        require(fingerprint(data['manifest'])==manifest['base_manifest_sha256'],'Original corpus changed')
        bindings={b['reference']['article_id']:b['source_sha256'] for b in data['manifest']['source_bindings']}
        require(registry['source_bindings']==data['manifest']['source_bindings'],'Scope source registry differs')
        scope_keys=set()
        for fold in data['folds']:
            for item in fold['training']+fold['queries']:
                context=item['context'];key=context['study_id']+':'+context['endpoint'];scope_keys.add(key)
                require(key in registry['scopes'],'Missing typed study/outcome scope')
                record=registry['scopes'][key]
                require(set(record)=={'study_id','endpoint','source_id','cohort_id','scope','provenance'},'Invalid scope record')
                require(record['study_id']==context['study_id'] and record['endpoint']==context['endpoint'],'Scope identity differs')
                require(record['cohort_id']==context['family_id'],'Scope cohort differs')
                validate_scope(record['scope'])
                require(record['scope']['critical']['measure']==context['measure'] and
                        record['scope']['critical']['unit']==context['unit'],'Quantity type differs from rate input')
                require(record['source_id'] in bindings,'Unknown scope source')
                require(isinstance(record['provenance'],list) and record['provenance'],'Scope provenance missing')
                for proof in record['provenance']:
                    require(set(proof)=={'source_id','source_sha256','start','end','offset_encoding','text_sha256','pdf_page','kind'},'Unexpected text or result in scope pointer')
                    require(proof['source_id']==record['source_id'] and proof['source_sha256']==bindings[record['source_id']],'Scope source hash differs')
                    require(proof['offset_encoding']=='unicode_codepoints' and type(proof['start']) is int and
                            type(proof['end']) is int and 0<=proof['start']<proof['end'],'Invalid scope pointer')
                    require(proof['kind']=='methods_or_definition','Only methods/context provenance allowed')
        require(scope_keys==set(registry['scopes']),'Unused or hidden-result scope added')
        return {'scope_manifest':manifest,'manifest':data['manifest'],'registry':registry,'folds':data['folds']}
