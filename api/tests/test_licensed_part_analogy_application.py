"""Неизменяемый импорт двух явных срезов не создаёт модельных клиентов."""
from copy import deepcopy
import socket

import pytest

from application.licensed_part_analogy import DiscoverSealedPartAnalogies
from domain.article_maps import ArticleMapError, ArticleMapNotFound, fingerprint
from infrastructure.development_prediction_store import FilePredictionStore
from tests.test_licensed_part_analogy import inputs


def artifacts():
    parts, graph, origins, families = inputs()
    refs = [{'article_id': a, 'run_id': 'run-' + a, 'pipeline_id': 'text_reified'} for a in sorted(families)]
    binding = {'metadata': {'question': None, 'training_cutoff': '2022-12-31', 'excluded_source_sha256': ['excluded-target']},
        'references': refs, 'map_hashes': ['synthetic-' + a for a in sorted(families)], 'families': families,
        'context_audit_sha256': 'synthetic-context', 'origin_audit_sha256': fingerprint(origins)}
    parts['binding'] = {**deepcopy(binding), 'channel': 'parts'}; parts['run_id'] = fingerprint(parts['binding'])
    arguments = {'binding': {**deepcopy(binding), 'channel': 'arguments'}, 'semantic_graph': graph,
                 'model_calls': 0, 'target_read': False}
    arguments['run_id'] = fingerprint(arguments['binding'])
    return parts, arguments, origins


def stores(tmp_path):
    p, a, o = artifacts(); parts = FilePredictionStore(tmp_path / 'parts'); args = FilePredictionStore(tmp_path / 'arguments')
    parts.seal(p['run_id'], p); args.seal(a['run_id'], a)
    return parts, args, FilePredictionStore(tmp_path / 'output'), p, a, o


def test_no_network_or_model_and_repeat_is_immutable(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('Network and model calls forbidden')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    import httpx
    monkeypatch.setattr(httpx.Client, 'send', forbidden)
    p, a, out, pp, aa, origin = stores(tmp_path); app = DiscoverSealedPartAnalogies(p, a, out)
    first = app.execute(pp['run_id'], aa['run_id'], origin, {'fixed': 'implementation'})
    assert first == app.execute(pp['run_id'], aa['run_id'], origin, {'fixed': 'implementation'})
    assert len(first['all_candidates']) == 2 and len(list(out.root.iterdir())) == 1
    assert fingerprint(p.read_seal(pp['run_id'])) == fingerprint(pp)
    assert fingerprint(a.read_seal(aa['run_id'])) == fingerprint(aa)


@pytest.mark.parametrize('damage', ['map_version', 'context', 'target', 'origin', 'excluded_target'])
def test_incompatible_inputs_cannot_replace_previous_success(tmp_path, damage):
    p, a, out, pp, aa, origin = stores(tmp_path); app = DiscoverSealedPartAnalogies(p, a, out)
    first = app.execute(pp['run_id'], aa['run_id'], origin, {})
    changed = deepcopy(aa)
    if damage == 'map_version': changed['binding']['map_hashes'][0] = 'changed-map'
    elif damage == 'context': changed['binding']['context_audit_sha256'] = 'changed-context'
    elif damage == 'target': changed['target_read'] = True
    elif damage == 'origin': changed['binding']['origin_audit_sha256'] = 'changed-origin'
    else: changed['binding']['metadata']['excluded_source_sha256'] = [next(iter(changed['semantic_graph']['parents'].values()))['source_sha256']]
    changed['binding']['revision'] = damage; changed['run_id'] = fingerprint(changed['binding']); a.seal(changed['run_id'], changed)
    with pytest.raises(ArticleMapError): app.execute(pp['run_id'], changed['run_id'], origin, {})
    assert out.read_seal(first['run_id']) == first and len(list(out.root.iterdir())) == 1


def test_missing_explicit_source_does_not_publish(tmp_path):
    p, a, out, pp, aa, origin = stores(tmp_path)
    with pytest.raises(ArticleMapNotFound): DiscoverSealedPartAnalogies(p, a, out).execute('a' * 64, aa['run_id'], origin, {})
    assert not out.root.exists()
