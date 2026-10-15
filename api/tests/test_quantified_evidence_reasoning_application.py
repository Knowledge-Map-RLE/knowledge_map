"""Запечатанный вход и отказ оператора не меняют ранее опубликованный результат."""
from copy import deepcopy
import socket
import pytest

from application.quantified_evidence_reasoning import ReasonSealedQuantitativeEvidence
from domain.article_maps import ArticleMapError, ArticleMapNotFound, fingerprint
from domain.author_argument_circuits import build_circuits
from domain.evidence_origin_audit import validate_origins
from domain.semantic_operator_graph import build_graph
from infrastructure.development_prediction_store import FilePredictionStore
from tests.test_semantic_part_forecast import prepare
from tests.test_quantified_evidence_reasoning import measured_map


def input_artifact():
    maps, origins = prepare([measured_map()]); graph = build_graph(maps)
    binding = {'metadata': {'question': None}, 'synthetic_example_only': True}
    run = fingerprint(binding)
    return {'run_id': run, 'binding': binding, 'model_calls': 0, 'target_read': False,
        'semantic_graph': graph, 'argument_circuits': build_circuits(graph, validate_origins(maps, origins))}


def test_explicit_sealed_input_without_network_or_model_calls(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('Network forbidden')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    import httpx
    monkeypatch.setattr(httpx.Client, 'send', forbidden)
    source, output = FilePredictionStore(tmp_path / 'source'), FilePredictionStore(tmp_path / 'output')
    artifact = input_artifact(); source.seal(artifact['run_id'], artifact)
    use = ReasonSealedQuantitativeEvidence(source, output)
    first = use.execute(artifact['run_id'], {'version': 'fixed'}); second = use.execute(artifact['run_id'], {'version': 'fixed'})
    assert first == second and len(first['proofs']) == 1 and not first['new_predictions']
    assert source.read_seal(artifact['run_id']) == artifact and len(list(output.root.iterdir())) == 1


def test_missing_source_or_target_input_cannot_publish(tmp_path):
    source, output = FilePredictionStore(tmp_path / 'source'), FilePredictionStore(tmp_path / 'output')
    use = ReasonSealedQuantitativeEvidence(source, output)
    with pytest.raises(ArticleMapNotFound): use.execute('a' * 64, {})
    artifact = input_artifact(); artifact['target_read'] = True; source.seal(artifact['run_id'], artifact)
    with pytest.raises(ArticleMapError): use.execute(artifact['run_id'], {})
    assert not output.root.exists()


def test_failure_preserves_previous_result(tmp_path):
    source, output = FilePredictionStore(tmp_path / 'source'), FilePredictionStore(tmp_path / 'output')
    artifact = input_artifact(); source.seal(artifact['run_id'], artifact)
    use = ReasonSealedQuantitativeEvidence(source, output); previous = use.execute(artifact['run_id'], {})
    changed = deepcopy(artifact); changed['binding']['revision'] = 2; changed['run_id'] = fingerprint(changed['binding'])
    changed['semantic_graph']['statement_count'] += 1; source.seal(changed['run_id'], changed)
    with pytest.raises(ArticleMapError): use.execute(changed['run_id'], {})
    assert output.read_seal(previous['run_id']) == previous and len(list(output.root.iterdir())) == 1
