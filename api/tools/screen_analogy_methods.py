"""Офлайн-проверка явно зарегистрированных контрольных методов; AI-клиентов нет."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from application.analogy_method_screening import ScreenSealedAnalogyMethods
from domain.article_maps import fingerprint, require
from infrastructure.control_method_packets import method_packet
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE = ('domain/analogy_method_screening.py', 'application/analogy_method_screening.py',
        'tools/screen_analogy_methods.py', 'infrastructure/control_method_packets.py')


def main():
    parser = argparse.ArgumentParser()
    for name in ('protocols', 'run-id', 'screening', 'annotation', 'disclosure', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(); disable_network(); root = Path(args.screening)
    registration = json.loads((root / 'protocol.json').read_bytes())
    plan = json.loads((root / 'method-acquisition-plan-v2.json').read_bytes()); packets = {}; raw_sources = {}
    for selected in plan['selected']:
        folder = root / 'controls' / selected['pmcid'].lower(); raw = (folder / 'article.xml').read_bytes()
        packet = json.loads((folder / 'method-packet-v2.json').read_bytes())
        receipt = json.loads((folder / 'availability-v2.json').read_bytes())
        require(receipt['plan_sha256'] == fingerprint(plan) and receipt['status'] == 'full_xml_retrieved'
                and receipt['xml_sha256'] == sha256(raw).hexdigest() and receipt['packet_sha256'] == fingerprint(packet),
                'Method acquisition receipt changed')
        require(packet == method_packet(raw, selected['pmcid'], selected['doi']), 'Method parser reproduction differs')
        packets[selected['pmcid']] = packet; raw_sources[selected['pmcid']] = raw
    annotation_bytes = Path(args.annotation).read_bytes(); disclosure_bytes = Path(args.disclosure).read_bytes()
    annotation = json.loads(annotation_bytes); disclosure = json.loads(disclosure_bytes)
    # Проверка записи о раскрытии читает уже раскрытый пакет, не остальные результаты XML.
    for row in disclosure['controls']:
        if not row['partial_outcome_disclosure']: continue
        old = json.loads((root / 'controls' / row['pmcid'].lower() / 'method-packet.json').read_bytes())
        require(fingerprint(old) == row['old_packet_sha256'] and old['raw_xml_sha256'] == row['raw_xml_sha256'], 'Disclosure source changed')
        unit = next(u for u in old['method_source']['units'] if u['id'] == row['unit_id'])
        require(unit['sha256'] == row['unit_sha256'] and row['quote'] in unit['text']
                and row['quote'] not in packets[row['pmcid']]['method_source']['text'], 'Disclosure audit not reproduced')
    api = Path(__file__).resolve().parents[1]; code = {p: sha256((api / p).read_bytes()).hexdigest() for p in CODE}
    output = FilePredictionStore(args.output)
    result = ScreenSealedAnalogyMethods(FilePredictionStore(args.protocols), output).execute(
        args.run_id, registration, packets, plan, annotation, disclosure, code)
    out = output.path(result['run_id']); source = FilePredictionStore(args.protocols).path(args.run_id)
    for name in ('predictions.json', 'seal.json'): write_immutable(out / 'inputs/source_protocols' / name, (source / name).read_bytes())
    for name in ('protocol.json', 'method-acquisition-plan-v2.json'): write_immutable(out / 'inputs' / name, (root / name).read_bytes())
    write_immutable(out / 'inputs/annotation.json', annotation_bytes); write_immutable(out / 'inputs/disclosure.json', disclosure_bytes)
    for pmcid, packet in packets.items():
        write_immutable(out / 'inputs/methods' / pmcid / 'packet.json', output.encode(packet))
        write_immutable(out / 'inputs/methods' / pmcid / 'article.xml', raw_sources[pmcid])
    for name in CODE: write_immutable(out / 'implementation' / name, (api / name).read_bytes())
    write_immutable(out / 'reads.json', output.encode({'network_disabled': True, 'model_calls': 0,
        'control_parser_reads_full_xml': True, 'scope_comparator_reads_selected_methods_only': True,
        'generator_reads_controls': False, 'other_maps_read': False, 'effects_evaluated': False}))
    print(json.dumps({'run_id': result['run_id'], 'controls': result['controls_accounted'], 'counts': result['counts']}, ensure_ascii=True))


if __name__ == '__main__': main()
