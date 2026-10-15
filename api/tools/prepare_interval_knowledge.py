"""Codex связывает две напечатанные пары ДИ с собственным источником и режимом опыта."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from domain.article_maps import fingerprint, require
from domain.interval_knowledge import VERSION
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.sealed_forecast_corpus import SealedForecastCorpus
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--input-run', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args(); disable_network(); root = Path(args.input_run).resolve()
    baseline = FilePredictionStore(root.parent).read_seal(root.name)
    descriptor = json.loads((root / 'input-corpus.json').read_bytes())
    frozen, maps, _ = SealedForecastCorpus(descriptor['snapshot']).load()
    require(fingerprint(frozen) == baseline['binding']['source_sha256'], 'Interval preparation source differs')
    m = next(x for x in maps if 'pmc5651799' in x['article_id'])
    unit = next(u for u in m['source']['units'] if u['id'] == 'U21')
    def quote(text):
        require(unit['text'].count(text) == 1, 'Interval source quote must be unique')
        start = unit['start'] + unit['text'].index(text)
        return {'unit_id': unit['id'], 'start': start, 'end': start + len(text), 'text': text, 'sha256': sha256(text.encode()).hexdigest()}
    entries = []
    cases = [('K30', 'K30S5', 'detected',
        'Furthermore, defining disease onset as the day mice were symptomatic for two consecutive days, we observed a significant delay of disease onset in TROS-treated mice compared to PBS-treated mice (95% CI 7.241–11.09 vs. 5.366–7.884 days, respectively) (Table 1).',
        'Mice were injected i.p. every two days with 200 µg TROS or PBS as a control.'),
        ('K31', 'K31S3', 'not_detected',
        'Also, disease onset was slightly delayed by the lower TROS dose, but this delay was not significant (95% CI 7.55–10.65 vs 6.03–7.69 days, respectively) (Table 1).',
        'Next, we aimed to reduce the dose and dosing frequency of TROS from 200 µg every two days to 150 µg every three days, which could improve therapy adherence and reduce the side-effects in a clinical setting.')]
    for kid, statement, detection, result_quote, protocol_quote in cases:
        k = next(k for k in m['graph']['knowledge'] if k['knowledge_id'] == kid)
        entries.append({'native_key': [m['article_id'], kid], 'run_id': m['run_id'], 'source_sha256': m['source']['sha256'],
            'knowledge_sha256': fingerprint(k), 'statement_id': statement, 'level_field': 'ci level', 'unit': 'day',
            'estimand_ru': 'Средний день начала клинических симптомов EAE; симптомы два последовательных дня.',
            'clock_ru': 'Дни после иммунизации; отдельный профилактический режим этого источника.',
            'intervals': [{'label_ru': 'TROS в данном режиме', 'lower_field': 'tros onset ci lower', 'upper_field': 'tros onset ci upper'},
                          {'label_ru': 'PBS в данном режиме', 'lower_field': 'pbs onset ci lower', 'upper_field': 'pbs onset ci upper'}],
            'reported_detection': detection, 'evidence': [quote(result_quote), quote(protocol_quote), quote(
                'Mean day of disease onset (±SEM) is defined as the day of clinical symptoms for two consecutive days.')],
            'reason_ru': 'Пары и порядок групп прямо заданы автором. Геометрия относится к напечатанным границам; '
                         'перекрытие не определяет результат авторского теста. Разметка требует экспертной проверки.'})
    audit = {'version': VERSION, 'author': 'Codex', 'expert_validated': False, 'model_calls': 0,
        'input_sha256': fingerprint(frozen), 'map_hashes': [fingerprint(m) for m in maps], 'entries': entries,
        'preparation_sha256': sha256(Path(__file__).read_bytes()).hexdigest(), 'independent_future_validation': False}
    write_immutable(Path(args.output), FilePredictionStore.encode(audit)); print(json.dumps({'entries': len(entries), 'sha256': fingerprint(audit)}))


if __name__ == '__main__': main()
