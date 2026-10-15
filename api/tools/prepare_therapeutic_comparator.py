"""Дополняет разметку контроля TROS только прямо подтверждёнными сравнениями."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize_map
from domain.operation_role_bindings import project_role_bindings
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from infrastructure.sealed_forecast_corpus import SealedForecastCorpus
from tools.run_free_prediction import disable_network


def extend_comparator_audit(forecast, maps, parent):
    """Сохраняет прежние лицензии и не меняет сравнения с генетическим контролом."""
    require(parent['input_run_id'] == forecast['run_id']
            and parent['input_prediction_sha256'] == fingerprint(forecast), 'Parent role audit input differs')
    views = {tuple(v['key']): {**deepcopy(v), 'key': tuple(v['key']), 'native_key': tuple(v['native_key'])}
             for v in forecast['part_views']}
    candidates = [m for m in maps if m['article_id'] == 'research-pmc5651799-d577fb3b53bb16a1']
    require(len(candidates) == 1, 'Explicit therapeutic source required')
    m = candidates[0]
    units = {u['id']: u for u in m['source']['units']}

    def quote(uid, text):
        unit = units[uid]
        require(unit['text'].count(text) == 1, 'Therapeutic comparator quote must be unique')
        start = unit['start'] + unit['text'].index(text)
        return {'unit_id': uid, 'start': start, 'end': start + len(text), 'text': text,
                'sha256': sha256(text.encode()).hexdigest()}

    def selected(kid, predicate, outcome=None):
        found = [v for v in views.values() if v['native_key'] == (m['article_id'], kid)
                 and v['frame']['statements'][0]['predicate'] == predicate
                 and (outcome is None or any(r['role'] == 'outcome' and r['value'] == outcome
                                            for r in v['frame']['statements'][0]['roles']))]
        require(len(found) == 1, 'Therapeutic comparator part must be unique')
        return found[0]

    audit = deepcopy(parent)
    audit['parent_audit_sha256'] = fingerprint(parent)
    audit['author_script_sha256'] = sha256(Path(__file__).read_bytes()).hexdigest()
    method_quote = quote('U52', 'hTNFR1 Tg mice with ongoing EAE were divided in balanced groups and therapeutically treated with 500 µg TROS or PBS')
    clinical_quote = quote('U51', 'three treatments with 500 µg TROS every four days (on days 8, 12 and 16 PI) significantly arrested disease progression and limited body weight loss compared to PBS treatment for 30 days PI')
    maximum_quote = quote('U51', 'the mean maximum score was significantly lower than in PBS-treated EAE mice')
    targets = [(selected('K48', 'administer treatment'), method_quote),
               (selected('K49', 'reduced after intervention', 'eae clinical progression'), clinical_quote),
               (selected('K49', 'reduced after intervention', 'body-weight loss'), clinical_quote),
               (selected('K49', 'reduced after intervention', 'mean maximum disease score'), maximum_quote)]
    for view, evidence in targets:
        audit['entries'].append({'part_key': list(view['key']), 'variant': 'explicit_therapeutic_pbs_comparator',
            'run_id': view['run_id'], 'source_sha256': m['source']['sha256'], 'graph_sha256': fingerprint(m['graph']),
            'knowledge_sha256': view['projection_proof']['parent_knowledge_sha256'],
            'frame_sha256': fingerprint(view['frame']),
            'add_roles': [{'role': 'comparator', 'value': 'pbs vehicle control',
                           'source_asserts_role': True, 'evidence': evidence}],
            'rename_roles': [], 'binding_group': None,
            'reason_ru': 'Терапевтический контроль PBS прямо назван в источнике для данной операции или исхода. '
                         'Отдельные сравнения с TNFR1−/− не переименованы; дозы, фазы и полные родители сохранены. '
                         'Требуется экспертная проверка.'})
    audit['limitations_ru'].append('Роль PBS добавлена только к явно указанным терапевтическим сравнениям. '
                                  'Кумулятивный индекс без отдельной прямой цитаты PBS и сравнения с TNFR1−/− сохранены без новых ролей.')
    by_parent = {}
    for key, view in views.items(): by_parent.setdefault(view['native_key'], []).append(key)
    groups = [(tuple((m['article_id'], p) for p in group), (m['article_id'], k['id']))
              for m in maps for k in normalize_map(m) for group in k['premise_groups']]
    project_role_bindings(views, by_parent, set(), maps, groups, parent)
    projected, _, _, summary = project_role_bindings(views, by_parent, set(), maps, groups, audit)
    require(len(audit['entries']) == len(parent['entries']) + 4
            and summary['added_views'] == len(audit['entries']), 'Comparator extension count differs')
    # Ни одно прежнее представление не переписывается.
    require(all(projected[key] == value for key, value in views.items()), 'Comparator extension changed native views')
    return audit, summary


def main():
    parser = argparse.ArgumentParser()
    for name in ('input-run', 'parent-audit', 'output'): parser.add_argument('--' + name, required=True)
    args = parser.parse_args(); disable_network()
    forecast, maps, _ = SealedForecastCorpus(args.input_run).load()
    parent = json.loads(Path(args.parent_audit).read_bytes())
    audit, summary = extend_comparator_audit(forecast, maps, parent)
    output = Path(args.output).resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    write_immutable(output, FilePredictionStore.encode(audit))
    print(json.dumps({'added_role_views': summary['added_views'], 'new_entries': 4,
                      'unchanged_original_views': len(forecast['part_views']), 'model_calls': 0}))


if __name__ == '__main__': main()
