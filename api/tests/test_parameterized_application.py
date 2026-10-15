"""Разделение ответов, происхождение, неизменяемость и воспроизводимость операции."""
import json
from copy import deepcopy
from pathlib import Path
import pytest
from domain.article_maps import fingerprint,ArticleMapError
from application.parameterized_reasoning import SealInterpretations,EvaluateInterpretations
from infrastructure.prepared_reasoning_corpus import PreparedReasoningCorpus
from infrastructure.development_prediction_store import FilePredictionStore

ROOT=Path(__file__).resolve().parents[2]/'eval/question_prediction/il6-plasma-global-v1/parameterized-operators-v1'
def read(p):return json.loads(p.read_text(encoding='utf-8'))

def test_real_eight_cases_seal_before_evaluator_and_repeat_identically(tmp_path):
    corpus=PreparedReasoningCorpus(read(ROOT/'prepared-v2/manifest.json'));store=FilePredictionStore(tmp_path/'runs')
    protocol=read(ROOT/'protocol.json')
    first=SealInterpretations(corpus,store).execute(protocol)
    assert corpus.reads==['premises']
    assert all(p['result_available'] for p in first['predictions'])
    assert all('expected' not in p and 'author_evidence' not in p for p in first['predictions'])
    second=SealInterpretations(corpus,store).execute(protocol);assert first==second
    evaluation=EvaluateInterpretations(corpus,store).execute(first['run_id'])
    assert corpus.reads==['premises','premises','controls']
    assert evaluation['matches']==evaluation['answered']==8 and not evaluation['scientific_success']
    assert evaluation==EvaluateInterpretations(corpus,store).execute(first['run_id'])
    assert len(evaluation['patterns'][0]['evaluated_families'])==1


def test_evaluator_does_not_read_answers_before_a_seal(tmp_path):
    corpus=PreparedReasoningCorpus(read(ROOT/'prepared-v2/manifest.json'))
    with pytest.raises(ArticleMapError):EvaluateInterpretations(corpus,FilePredictionStore(tmp_path)).execute('a'*64)
    assert corpus.reads==[]


def test_answer_or_article_tampering_is_rejected(tmp_path):
    corpus=PreparedReasoningCorpus(read(ROOT/'prepared-v2/manifest.json'));store=FilePredictionStore(tmp_path/'runs')
    sealed=SealInterpretations(corpus,store).execute(read(ROOT/'protocol.json'))
    manifest=deepcopy(corpus.manifest);raw=read(Path(manifest['controls']['path']))
    raw['source_binding']['source_sha256']='b'*64
    p=tmp_path/'different-target.json';p.write_text(json.dumps(raw),encoding='utf-8')
    manifest['controls']={'path':str(p),'sha256':fingerprint(raw)}
    with pytest.raises(ArticleMapError,match='article/map'):EvaluateInterpretations(PreparedReasoningCorpus(manifest),store).execute(sealed['run_id'])
    manifest['controls']['sha256']='a'*64
    with pytest.raises(ArticleMapError,match='input changed'):PreparedReasoningCorpus(manifest).controls()


def test_real_reference_quotes_use_codepoints_and_maps_remain_separate():
    pack=read(ROOT/'prepared-v2/premises.json');controls=read(ROOT/'prepared-v2/controls.json')
    source=read(ROOT.parent/'expanded-semantic-three-v1/maps-v2/PMC6218168/map.json')['source']
    for c in controls['controls']:
        for span in c['evidence']:
            assert source['text'][span['start']:span['end']]==span['text']
            assert span['end']<=source['content_end'] and span['source_sha256']==source['sha256']
    assert len(pack['cases'])==8
    assert all('expected' not in c for c in pack['cases'])
    assert {c['context']['stratum'] for c in pack['cases']}=={'baseline MCI','no baseline MCI'}
