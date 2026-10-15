"""Codex фиксирует известное направление и источниковые временные ограничения."""
import argparse
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json

from domain.article_maps import fingerprint, require
from domain.forecast_claim_qualification import VERSION
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.external_operation_inputs import read_bound_source
from infrastructure.immutable_files import write_immutable
from infrastructure.sealed_forecast_corpus import SealedForecastCorpus
from tools.run_free_prediction import disable_network


def prepare(root):
    frozen = FilePredictionStore(root.parent).read_seal(root.name)
    descriptor = json.loads((root / 'input-corpus.json').read_bytes())
    applicability_root = Path(descriptor['snapshot'])
    upstream_root = Path(json.loads((applicability_root / 'input-corpus.json').read_bytes())['snapshot'])
    _, maps, _ = SealedForecastCorpus(upstream_root).load()
    source_packet = read_bound_source(root / 'external-source.json')
    require(source_packet['pmcid'] == 'PMC6133964', 'Registered temporal source required')
    source = source_packet['source']; units = {u['id']: u for u in source['units']}
    def quote(uid, text):
        u = units[uid]; require(u['text'].count(text) == 1, 'Exact temporal quote must be unique')
        start = u['start'] + u['text'].index(text)
        return {'unit_id': uid, 'start': start, 'end': start + len(text), 'text': text, 'sha256': sha256(text.encode()).hexdigest()}
    candidates = {c['id']: c for folds in frozen['modes'].values() for f in folds for c in f['predictions']}
    rows = []
    for cid, c in sorted(candidates.items()):
        bindings = {**deepcopy(c['head']['participants']), 'measurement': 'ordinal_eae_clinical_score', 'aggregate': 'reported_group_comparison'}
        contract = {'anchor': 'EAE disease onset', 'unit': 'day', 'episode': 'initial_four_dose_course',
            'time_quantifier': 'some_assessed_time', 'window': {'start': '3', 'end': '3', 'start_inclusive': True, 'end_inclusive': True},
            'bindings': bindings}
        known, observations = [], []
        if 'atrosab' in c['receiver_id']:
            for m in maps:
                for u in m['source']['units']:
                    text = 'Atrosab demonstrated therapeutic activity in the EAE model of MS (17)'
                    if text not in u['text']: continue
                    start = u['start'] + u['text'].index(text)
                    known.append({'article_id': m['article_id'], 'run_id': m['run_id'], 'source_sha256': m['source']['sha256'],
                        'unit_id': u['id'], 'start': start, 'end': start + len(text), 'text': text,
                        'sha256': sha256(text.encode()).hexdigest(), 'relation': 'coarse_direction_already_described',
                        'license_kind': 'explicit_therapeutic_activity_eae', 'intervention_alias': 'Atrosab'})
            require(known, 'Training text already describing ATROSAB must be retained')
            # Подпись прямо задаёт третий день; неизвестные будущие сроки этим не заполняются.
            contract['time_quantifier'] = 'specified_time'
            observations.append({'id': 'atrosab-caption-day3', 'contract': contract, 'direction': 'lower', 'precision': 'exact', 'assessment_times': ['3'],
                'evidence': [quote('U10', 'ATROSAB treatment led to a significant reduction in disease severity from the third day of EAE onwards.')]})
            reason = 'Общее направление ATROSAB уже описано в тексте обучения; точное тождество полного опыта не установлено. '
            reason += 'День 3 относится к оценщику, не добавляется в старый прогноз. Ограничение до дня 24 и потеря ответа сохраняются отдельно.'
        else:
            # Примерный конец не становится точной точкой и не задаёт неизвестное начало интервала.
            contract['time_quantifier'] = 'specified_time'; contract['window'].update(start='35', end='35')
            observations.append({'id': 'h398-approximately-day35', 'contract': contract, 'direction': 'lower', 'precision': 'approximate', 'assessment_times': [],
                'evidence': [quote('U21', 'Blockade of TNFR1 with H398 again resulted in an amelioration of EAE, until approximately 35 days after the onset of EAE')]})
            reason = 'Точное совпадение H398 в полном корпусе не установлено; отсутствие найденной лицензии не доказывает новизну. '
            reason += 'Примерный день 35 не является точным измерением; рецидив и повторные курсы не превращаются в отрицательный относительный эффект.'
        rows.append({'prediction_id': cid, 'known_pattern_evidence': known,
            'outcome_temporal_observations': observations, 'reason_ru': reason})
    return {'version': VERSION, 'author': 'Codex', 'expert_validated': False, 'model_calls': 0,
        'forecast_sha256': fingerprint(frozen), 'external_source_packet_sha256': fingerprint(source_packet),
        'external_doi': source_packet['doi'], 'map_hashes': [fingerprint(m) for m in maps],
        'candidates': rows, 'author_script_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope_ru': 'Источниковый аудит уже зафиксированных кандидатов; новые временные прогнозы не создаются.'}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--forecast', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args(); disable_network(); packet = prepare(Path(args.forecast).resolve())
    path = Path(args.output).resolve(); path.parent.mkdir(parents=True, exist_ok=True)
    write_immutable(path, FilePredictionStore.encode(packet))
    print(json.dumps({'candidates': len(packet['candidates']), 'model_calls': 0}))


if __name__ == '__main__': main()
