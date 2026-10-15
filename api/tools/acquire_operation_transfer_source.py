"""Сохраняет явный первичный источник для внешнего ретроспективного переноса."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import httpx

from domain.article_maps import fingerprint, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from infrastructure.primary_article_xml import materialize_primary_article


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True)
    args = parser.parse_args(); root = Path(args.output).resolve()
    plan = {'pmcid': 'PMC6133964', 'doi': '10.1038/s41598-018-31957-7',
        'source_url': 'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC6133964/fullTextXML',
        'publication_date': '2018-09-11', 'purpose_ru': 'Внешний принимающий опыт; прежний обучающий корпус из 11 карт не меняется.',
        'results_previously_disclosed': True, 'blind_control': False, 'model_calls': 0,
        'selection_ru': 'Выбран после обнаружения нехватки третьего совместимого опыта. Поисковые фрагменты и текст издателя уже раскрыли результаты; это ретроспективная инженерная проверка.',
        'author_script_sha256': sha256(Path(__file__).read_bytes()).hexdigest()}
    root.mkdir(parents=True, exist_ok=True)
    write_immutable(root / 'acquisition-plan.json', FilePredictionStore.encode(plan))
    raw_path = root / 'article.xml'
    if raw_path.exists(): raw = raw_path.read_bytes()
    else:
        response = httpx.get(plan['source_url'], timeout=60, follow_redirects=True)
        response.raise_for_status(); raw = response.content
    packet = materialize_primary_article(raw, plan['pmcid'], plan['doi'])
    require(packet['license'] and packet['reference_count'] > 0, 'Complete licensed full source required')
    for name, bytes_ in [('article.xml', raw), ('source.json', FilePredictionStore.encode(packet)),
                         ('source.en.md', packet['source']['text'].encode())]:
        write_immutable(root / name, bytes_)
    implementation = Path(__file__).parents[1] / 'infrastructure/primary_article_xml.py'
    write_immutable(root / 'implementation/primary_article_xml.py', implementation.read_bytes())
    write_immutable(root / 'implementation/acquire_operation_transfer_source.py', Path(__file__).read_bytes())
    receipt_path = root / 'acquisition.json'
    stable = {'plan_sha256': fingerprint(plan), 'source_sha256': packet['source']['sha256'],
        'raw_xml_sha256': packet['raw_xml_sha256'], 'source_packet_sha256': fingerprint(packet),
        'extractor_sha256': sha256(implementation.read_bytes()).hexdigest(), 'model_calls': 0,
        'results_previously_disclosed': True, 'blind_control': False}
    if receipt_path.exists():
        previous = json.loads(receipt_path.read_bytes())
        require(all(previous[k] == v for k, v in stable.items()), 'Acquisition receipt differs')
    else: write_immutable(receipt_path, FilePredictionStore.encode({**stable, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat()}))
    print(json.dumps({'pmcid': plan['pmcid'], 'source_sha256': packet['source']['sha256'],
        'units': len(packet['source']['units']), 'references': packet['reference_count'], 'model_calls': 0}))


if __name__ == '__main__': main()
