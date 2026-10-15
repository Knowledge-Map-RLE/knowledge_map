"""Раздельные файлы методов и исходов с проверкой полного источника."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from domain.article_maps import fingerprint, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.sealed_operation_transfer_corpus import SealedOperationTransferCorpus


class SealedExternalTrainingCorpus(SealedOperationTransferCorpus):
    def load(self):
        training = super().load()
        descriptor = json.loads((self.root / 'input-corpus.json').read_bytes())
        forecast_root = Path(descriptor['snapshot']).resolve()
        forecast = FilePredictionStore(forecast_root.parent).read_seal(forecast_root.name)
        require(forecast is not None, 'Complete forecast catalog missing')
        training['source_article_ids'] = [r['article_id'] for r in forecast['binding']['references']]
        require(len(training['source_article_ids']) == training['coverage']['sources'], 'Training registry differs')
        return training


def read_bound_source(path):
    packet = json.loads(Path(path).read_bytes()); source = packet['source']
    require(sha256(source['text'].encode()).hexdigest() == source['sha256']
            and source['offset_encoding'] == 'unicode_codepoints', 'External full source integrity differs')
    return packet


def validate_evidence(source, evidence):
    unit = next((u for u in source['units'] if u['id'] == evidence['unit_id']), None)
    require(unit is not None and unit['start'] <= evidence['start'] < evidence['end'] <= unit['end'] <= source['content_end']
            and source['text'][evidence['start']:evidence['end']] == evidence['text']
            and sha256(evidence['text'].encode()).hexdigest() == evidence['sha256'], 'External source quote differs')


class FileExternalReceivers:
    def __init__(self, packet_path, source_path):
        self.path, self.source_path = Path(packet_path).resolve(), Path(source_path).resolve()

    def load(self):
        packet = json.loads(self.path.read_bytes()); full = read_bound_source(self.source_path)
        require(packet['source_packet_sha256'] == fingerprint(full) and packet['model_calls'] == 0,
                'External method source binding differs')
        require(packet['expert_validated'] is False and len(packet['receivers']) == len(packet['method_evidence']),
                'Method annotations missing')
        for receiver, quotes in zip(packet['receivers'], packet['method_evidence']):
            require(receiver['source_sha256'] == full['source']['sha256'] and quotes['receiver_id'] == receiver['id'],
                    'External receiver source differs')
            for evidence in quotes['quotes']: validate_evidence(full['source'], evidence)
            for items in receiver['feature_evidence'].values():
                for evidence in items: validate_evidence(full['source'], evidence)
        # Полный источник нужен адаптеру для проверки координат; генератор его не получает.
        return deepcopy(packet)


class FileExternalOutcomes:
    def __init__(self, path, source_path):
        self.path, self.source_path = Path(path).resolve(), Path(source_path).resolve()

    def load(self):
        packet = json.loads(self.path.read_bytes()); full = read_bound_source(self.source_path)
        require(packet['source_packet_sha256'] == fingerprint(full) and packet['model_calls'] == 0,
                'External outcome source binding differs')
        outcomes = {}
        for outcome in packet['outcomes']:
            require(outcome['id'] not in outcomes and outcome['source_sha256'] == full['source']['sha256'],
                    'Repeated or foreign external outcome')
            for evidence in outcome['evidence']: validate_evidence(full['source'], evidence)
            outcomes[outcome['id']] = deepcopy(outcome)
        return outcomes
