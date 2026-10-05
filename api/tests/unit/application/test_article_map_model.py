"""Проверки полного ответа AI-сервиса и отказа до запроса при нехватке контекста."""
import json

import httpx
import pytest
from jsonschema import Draft202012Validator

from domain.article_maps import ArticleMapError
from domain.article_map_schema import reified_map_json_schema
from domain.knowledge_map_schema import dependency_review_json_schema, extraction_map_json_schema, knowledge_map_json_schema
from infrastructure.article_map_model import ArticleMapDependencyModelGateway, ArticleMapModelGateway


def gateway(monkeypatch, payload, status=200):
    model = ArticleMapModelGateway.__new__(ArticleMapModelGateway)
    model.model, model.provider, model.reasoning_effort = 'configured-profile', 'provider', 'max'
    model.context_length, model.max_tokens, model.timeout = 100000, 10000, 5
    model.url, model.last_call = 'http://ai-service/v1/chat/completions', {}
    model.output_schema = None
    model.strict_schema = False
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(status, content=payload, headers={'Content-Type': 'text/event-stream'})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    return model, requests


def stream(finish='stop', terminal=True):
    frames = [{'choices': [{'delta': {'content': '{"schema_version":4}'}, 'finish_reason': None}]},
              {'choices': [{'delta': {}, 'finish_reason': finish}]},
              {'choices': [], 'usage': {'completion_tokens': 20}}]
    return ''.join('data: ' + json.dumps(frame) + '\n\n' for frame in frames) + ('data: [DONE]\n\n' if terminal else '')


@pytest.mark.asyncio
async def test_full_article_uses_configured_profile_and_complete_stream(monkeypatch):
    model, requests = gateway(monkeypatch, stream())
    article = 'Entire article, including its final substantive paragraph.'
    assert await model('new independent prompt', article) == '{"schema_version":4}'
    assert requests[0]['messages'][1]['content'] == article
    assert requests[0]['model'] == 'configured-profile'
    assert model.last_call['finish_reason'] == 'stop'
    assert model.last_call['usage']['completion_tokens'] == 20


@pytest.mark.asyncio
async def test_sends_complete_graph_schema_without_changing_semantics(monkeypatch):
    model, requests = gateway(monkeypatch, stream())
    model.output_schema = reified_map_json_schema()
    await model('prompt', 'full article')
    definition = requests[0]['response_format']['json_schema']
    assert definition['schema'] == model.output_schema
    for branch in definition['schema']['properties']['nodes']['items']['anyOf']:
        assert 'modality' in branch['properties']['semantic']['required']
        assert branch['properties']['semantic']['properties']['qualifiers']['additionalProperties'] is True
    assert model.last_call['output_schema_sha256']


@pytest.mark.parametrize('schema_factory,name,strict', [
    (knowledge_map_json_schema, 'article_knowledge_map_v5', True),
    (extraction_map_json_schema, 'article_knowledge_map_v5', True),
])
@pytest.mark.asyncio
async def test_sends_current_stage_schema_through_configured_gateway(monkeypatch, schema_factory, name, strict):
    model, requests = gateway(monkeypatch, stream())
    model.output_schema = schema_factory()
    model.strict_schema = strict
    await model('stage prompt', 'complete article and extracted knowledge')
    definition = requests[0]['response_format']['json_schema']
    assert definition['name'] == name
    assert definition['schema'] == model.output_schema
    assert definition['strict'] is strict
    assert requests[0]['model'] == 'configured-profile'
    assert requests[0]['messages'][1]['content'] == 'complete article and extracted knowledge'


@pytest.mark.asyncio
async def test_dependency_gateway_binds_ids_to_actual_knowledge_texts(monkeypatch):
    model, requests = gateway(monkeypatch, stream())
    model.__class__ = ArticleMapDependencyModelGateway
    model.json_object = True
    nodes = [{'id': 'N45', 'display_text': 'The study used census data'},
             {'id': 'N119', 'display_text': 'The sample response rate was satisfactory'}]
    await model('dependency prompt', json.dumps({'knowledge_map': {'nodes': nodes}}))
    definition = requests[0]['response_format']['json_schema']
    assert definition['strict'] is True
    assert definition['schema'] == dependency_review_json_schema(nodes)
    assert set(definition['schema']['$defs']['source_reference']['enum']) == {'T1', 'T2'}
    assert definition['schema']['$defs']['input']['properties']['usage']['enum'] == [
        'condition', 'data', 'definition', 'evidence', 'method', 'premise', 'result']
    assert model.last_call['validation_schema_sha256']
    assert requests[0]['messages'][1]['content'] == json.dumps({'knowledge_map': {'nodes': nodes}})


def schema_node(kind='rule'):
    return {'id': 'R1', 'kind': kind, 'display_text': 'The diagnostic threshold is at least 15',
            'aliases': [], 'provenance': {'unit_ids': ['U1']},
            'semantic': {'predicate': 'is at least', 'roles': [{'role': 'measure', 'node_id': 'M1'}],
                         'quantifier': None, 'modality': None, 'negated': False, 'conditions': [],
                         'temporal_context': None, 'qualifiers': {'threshold': 15}}}


@pytest.mark.parametrize('kind', ['rule', 'assertion', 'comparison'])
@pytest.mark.parametrize('missing', ['predicate', 'roles'])
def test_supplied_schema_rejects_empty_reified_statement(kind, missing):
    schema = reified_map_json_schema()
    Draft202012Validator.check_schema(schema)
    candidate = schema_node(kind)
    candidate['semantic'][missing] = None if missing == 'predicate' else []
    assert not Draft202012Validator(schema).is_valid(
        {'schema_version': 4, 'nodes': [candidate], 'edges': []})


def test_supplied_schema_distinguishes_named_standard_from_complete_rule():
    validator = Draft202012Validator(reified_map_json_schema())
    named = schema_node('concept')
    named['display_text'] = 'AASM 2007 standard apnea/hypopnea procedures'
    named['semantic']['predicate'], named['semantic']['roles'] = None, []
    validator.validate({'schema_version': 4, 'nodes': [named, schema_node()], 'edges': []})


def test_supplied_schema_rejects_invented_event_kind():
    candidate = schema_node('event')
    candidate['display_text'] = 'A financial crisis'
    candidate['semantic']['predicate'], candidate['semantic']['roles'] = None, []
    assert not Draft202012Validator(reified_map_json_schema()).is_valid(
        {'schema_version': 4, 'nodes': [candidate], 'edges': []})


@pytest.mark.parametrize('payload', [stream(finish='length'), stream(terminal=False), 'data: invalid\n\n',
                                    'data: {"error":{"message":"failed"}}\n\n',
                                    stream() + 'data: {"choices":[]}\n\n'])
@pytest.mark.asyncio
async def test_rejects_incomplete_or_failed_streams(monkeypatch, payload):
    model, _ = gateway(monkeypatch, payload)
    with pytest.raises(ArticleMapError):
        await model('prompt', 'article')


@pytest.mark.asyncio
async def test_context_exceeded_does_not_send_or_shorten_article(monkeypatch):
    model, requests = gateway(monkeypatch, stream())
    model.context_length = 12000
    with pytest.raises(ArticleMapError, match='context'):
        await model('prompt', 'full article' * 1000)
    assert requests == []


@pytest.mark.asyncio
async def test_http_failure_rejects_response_without_revealing_body(monkeypatch):
    model, _ = gateway(monkeypatch, 'sensitive provider diagnostics', 503)
    with pytest.raises(ArticleMapError, match='HTTP 503') as error:
        await model('prompt', 'article')
    assert 'sensitive' not in str(error.value)


@pytest.mark.asyncio
async def test_upstream_incomplete_preserves_partial_output_usage_and_safe_reason(monkeypatch):
    frames = [
        {'id': 'resp-incomplete', 'model': 'configured-model',
         'choices': [{'delta': {'content': '{"dependencies":'}, 'finish_reason': None}]},
        {'id': 'resp-incomplete', 'choices': [], 'usage': {
            'prompt_tokens': 100, 'completion_tokens': 128000,
            'completion_tokens_details': {'reasoning_tokens': 120000}}},
        {'error': {'message': 'private source content must not enter diagnostics'},
         'upstream': {'event_type': 'response.incomplete', 'incomplete_reason': 'max_output_tokens'}},
    ]
    model, requests = gateway(monkeypatch, ''.join('data: ' + json.dumps(frame) + '\n\n' for frame in frames))
    with pytest.raises(ArticleMapError, match='max_output_tokens') as error:
        await model('prompt', 'complete article')
    assert len(requests) == 1
    assert model.last_response == '{"dependencies":'
    assert model.last_call['usage'] == frames[1]['usage']
    assert model.last_call['response_id'] == 'resp-incomplete'
    assert model.last_call['upstream_failure']['incomplete_reason'] == 'max_output_tokens'
    assert not model.last_call['sse_terminal_frame']
    assert 'private source' not in str(error.value) + json.dumps(model.last_call)


@pytest.mark.asyncio
async def test_atomic_upstream_keeps_sse_contract_and_records_transport(monkeypatch):
    frames = [{'id': 'resp-atomic', 'model': 'configured-model', 'upstream_transport': 'responses_json',
               'choices': [{'delta': {'content': '{"complete":true}'}, 'finish_reason': None}]},
              {'id': 'resp-atomic', 'model': 'configured-model', 'upstream_transport': 'responses_json',
               'choices': [{'delta': {}, 'finish_reason': 'stop'}], 'usage': {'total_tokens': 123}}]
    model, requests = gateway(monkeypatch, ''.join('data: ' + json.dumps(frame) + '\n\n' for frame in frames)
                              + 'data: [DONE]\n\n')
    assert await model('unchanged prompt', 'entire article') == '{"complete":true}'
    assert requests[0]['stream'] is True
    assert model.last_call['upstream_transport'] == 'responses_json'
    assert model.last_call['response_id'] == 'resp-atomic'
    assert model.last_call['usage'] == {'total_tokens': 123}
    assert model.last_call['sse_terminal_frame'] and model.last_call['finish_reason'] == 'stop'


@pytest.mark.asyncio
async def test_background_failure_keeps_id_request_hash_and_usage_without_accepting(monkeypatch):
    frames = [{'id': 'resp-background', 'model': 'configured-model', 'choices': [],
               'upstream_transport': 'responses_background', 'upstream_status': 'in_progress',
               'upstream_request_sha256': 'a' * 64},
              {'id': 'resp-background', 'choices': [], 'upstream_status': 'cancelled',
               'usage': {'total_tokens': 123}},
              {'error': {'message': 'private provider data'}, 'upstream': {
                  'event_type': 'response.failed', 'transport_reason': 'background_response_timed_out'}}]
    model, requests = gateway(monkeypatch, ''.join('data: ' + json.dumps(frame) + '\n\n' for frame in frames)
                              + 'data: [DONE]\n\n')
    with pytest.raises(ArticleMapError, match='background_response_timed_out'):
        await model('rules', 'entire article')
    assert len(requests) == 1 and model.last_response == ''
    assert model.last_call['response_id'] == 'resp-background'
    assert model.last_call['upstream_request_sha256'] == 'a' * 64
    assert model.last_call['upstream_status'] == 'cancelled'
    assert model.last_call['usage'] == {'total_tokens': 123}
    assert model.last_call['finish_reason'] is None
    assert 'private provider data' not in json.dumps(model.last_call)
