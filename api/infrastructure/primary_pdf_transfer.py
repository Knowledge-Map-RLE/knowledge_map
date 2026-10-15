"""Читает только перечисленные PDF, привязывает фрагменты и сохраняет новую ревизию."""
import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import digest, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable


def load_primary_inputs(root, legacy_manifest):
    root=Path(root).resolve();annotation=json.loads((root/'annotation-spec.json').read_text(encoding='utf-8'))
    evidence={};bindings=[];identities={};texts={}
    for key,profile in annotation['profiles'].items():
        folder=root/'sources'/key;intake=json.loads((folder/'intake.json').read_text(encoding='utf-8'))
        pdf=(folder/'article.pdf').read_bytes();raw=(folder/'article.layout.txt').read_bytes()
        require(sha256(pdf).hexdigest()==intake['pdf_sha256'], 'Primary PDF changed')
        require(sha256(raw).hexdigest()==intake['layout_sha256'], 'Primary extracted text changed')
        text=raw.decode('utf-8');texts[key]=text;pages=text.split('\f')
        start=text.index(profile['title_start']);end=text.index(profile['title_end'],start)+len(profile['title_end'])
        require(end<=len(pages[0]), 'Title extends beyond first page')
        doi_present=intake['expected_doi'].lower() in text.lower()
        identities[key]={'doi':intake['expected_doi'],'doi_printed':doi_present,
            'verification':'Codex checked title, author, journal/year/pages against registered bibliographic metadata; DOI printed where present',
            'pdf_sha256':intake['pdf_sha256'],'layout_sha256':intake['layout_sha256'],
            'annotation_author':'Codex','expert_validated':False}
        def proof(name,a,b,kind,page):
            fragment=text[a:b]
            evidence[key+':'+name]={'article_id':key,'source_id':key,'cohort':profile['cohort'],
                'source_sha256':intake['layout_sha256'],'offset_encoding':'unicode_codepoints',
                'start':a,'end':b,'text':fragment,'text_sha256':digest(fragment),'kind':kind,'pdf_page':page}
        proof('title',start,end,'title',1)
        for page in set(profile['methods_pages']+[profile['table_page']]):
            require(1<=page<=intake['pages'], 'Missing PDF evidence page')
            a=sum(len(p)+1 for p in pages[:page-1]);b=a+len(pages[page-1])
            proof('table' if page==profile['table_page'] else 'methods-'+str(page),a,b,
                  'table' if page==profile['table_page'] else 'methods',page)
        bindings.append({'reference':{'article_id':key},'source_sha256':intake['layout_sha256'],
                         'pdf_sha256':intake['pdf_sha256'],'doi':intake['expected_doi']})
    manifest_path=Path(legacy_manifest).resolve();old_manifest=json.loads(manifest_path.read_text(encoding='utf-8'));legacy={}
    for item in old_manifest['folds']:
        path=(manifest_path.parent/item['path']).resolve()
        require(path.parent==manifest_path.parent,'Legacy fold outside explicit manifest')
        fold=json.loads(path.read_text(encoding='utf-8'))
        from domain.article_maps import fingerprint
        require(fingerprint(fold)==item['sha256'],'Legacy fold changed')
        for observation in fold['training']:
            if observation['id'] in legacy:require(legacy[observation['id']]==observation,'Conflicting legacy observation')
            legacy[observation['id']]=observation
    return annotation,evidence,legacy,bindings,identities,texts


def save_preparation(root, result, identities, evidence):
    root=Path(root);prepared=root/'prepared'
    for index,fold in enumerate(result['folds'],1):
        write_immutable(prepared/f'fold-{index}.json',FilePredictionStore.encode(fold))
    for filename,value in [('inputs-manifest.json',result['manifest']),('hidden-controls.json',result['hidden'])]:
        write_immutable(prepared/filename,FilePredictionStore.encode(value))
    for filename,value in [('review-cell-audit.json',result['audit']),('semantic-frames.json',result['frames']),
                           ('identity-review.json',identities),('source-evidence.json',evidence)]:
        write_immutable(root/filename,FilePredictionStore.encode(value))
