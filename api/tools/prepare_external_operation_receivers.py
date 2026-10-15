"""Codex отделяет описанные методы принимающего опыта от уже прочитанных исходов."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.conditional_operation_transfer import _validate_receiver
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from infrastructure.external_operation_inputs import read_bound_source, validate_evidence
from tools.run_free_prediction import disable_network

SOURCE_SHA = 'bf45c4b77e2ace6e3a17fc2dafa4f56d52eaf2650119d8dff0cc0ad5dc5c8fd5'


def prepare(source_path):
    full = read_bound_source(source_path); source = full['source']
    require(full['pmcid'] == 'PMC6133964' and full['doi'] == '10.1038/s41598-018-31957-7'
            and source['sha256'] == SOURCE_SHA and full['reference_count'] == 50, 'Registered primary source differs')
    units = {u['id']: u for u in source['units']}
    def quote(uid, text):
        u = units[uid]; require(u['text'].count(text) == 1, 'External source fragment is not unique')
        start = u['start'] + u['text'].index(text)
        evidence = {'unit_id': uid, 'start': start, 'end': start + len(text), 'text': text,
                    'sha256': sha256(text.encode()).hexdigest()}
        validate_evidence(source, evidence); return evidence
    features = {'species': 'mouse', 'disease_model': 'mog35_55_induced_eae',
        'target': 'human_tnfr1_extracellular_binding', 'intervention_action': 'selective_tnfr1_inhibition',
        'route': 'intraperitoneal', 'phase': 'manifest_disease', 'measurement_kind': 'ordinal_eae_clinical_score'}
    evidence = {
        'species': [quote('U68', 'Experiments were performed only on female mice of the same age (6–8 weeks old)')],
        'disease_model': [quote('U49', 'mice were immunized sub-cutaneously with 300 µg MOG35−55')],
        'target': [quote('U9', 'chimeric human/murine TNFR-knock-in mice, in which the extracellular part of human TNFR1 is fused to the trans-membrane and intracellular region of mouse TNFR1')],
        'intervention_action': [quote('U49', 'the human TNFR1-selective antagonistic antibodies ATROSAB23,44 or H39845')],
        'route': [quote('U49', 'Mice received intra-peritoneal injections')],
        'measurement_kind': [quote('U49', 'Mice were weighed and scored on a daily basis, with disease severity assessed using a scale ranging from 0 to 5')],
    }
    receivers, method_evidence, outcomes = [], [], []
    article = 'external-pmc6133964-' + SOURCE_SHA[:16]
    population = 'female 6-8-week C57BL/6 human/mouse TNFR1 knock-in mice in PMC6133964'
    challenge = 'mog35-55-induced experimental autoimmune encephalomyelitis'
    for drug, method_uid, method_text, phase_uid, phase_text, comparator in [
        ('ATROSAB', 'U11', 'animals were injected intra-peritoneally with 20 mg/kg of either the human-specific TNFR1 antagonistic antibody ATROSAB, or an isotype control IgG (anti-hu epidermal growth factor receptor) on days 1, 4, 8 and 12 of manifest EAE.',
         'U11', 'on days 1, 4, 8 and 12 of manifest EAE', 'Cetuximab isotype control IgG in PMC6133964'),
        ('H398', 'U21', 'mice were treated with either 20 mg/kg H398 or control IgG on days 1, 4, 8 and 12 of EAE.',
         'U22', 'on days 1, 4, 8 and 12 of manifest EAE', 'mouse control IgG in PMC6133964'),
    ]:
        case_id = 'pmc6133964-' + drug.lower() + '-initial-four-dose'
        local_evidence = deepcopy(evidence); local_evidence['phase'] = [quote(phase_uid, phase_text)]
        scope = {'quantifier': None, 'modality': None, 'time': 'days 1, 4, 8 and 12 after EAE onset',
            'study_group': article, 'conditions': ['Source-local initial four-dose comparison; no inference of dose equivalence, human efficacy or indefinite benefit']}
        def body(kid, predicate, roles, attrs, temporal):
            return {'key': [article, kid], 'native_key': [article, kid],
                'frame': {'kind': 'action', 'action_status': 'performed', 'logic': 'single', 'statements': [{
                    'predicate': predicate, 'roles': [{'role': role, 'value': value, 'reference_kind': 'concept'} for role, value in sorted(roles.items())],
                    'scope': {**deepcopy(scope), 'time': temporal}, 'negated': False,
                    'attributes': [{'name': name, 'value': value, 'unit': unit} for name, value, unit in attrs]}]}}
        method = body('method-' + drug, 'administer treatment', {'population': population,
            'intervention': drug + ' selective human TNFR1 antagonist in PMC6133964', 'challenge': challenge, 'comparator': comparator},
            [('dose', '20', 'mg/kg'), ('route', 'intraperitoneal', None), ('EAE-relative days', '1; 4; 8; 12', 'day'),
             ('sex', 'female', None), ('age', '6-8', 'week')], scope['time'])
        observation_end = '28' if drug == 'ATROSAB' else None
        measurement = body('clinical-measurement-' + drug, 'measure clinical course',
            {'population': population, 'challenge': challenge, 'outcome': 'eae clinical score'},
            [('score minimum', '0', 'score'), ('score maximum', '5', 'score'), ('frequency', 'daily', None),
             ('explicit clinical observation end', observation_end, 'day after EAE onset'),
             ('histopathology endpoint, separate measure', '85' if drug == 'H398' else None, 'day after EAE onset')],
            'daily after EAE onset; clinical endpoint ' + (observation_end or 'not explicitly identified in text'))
        receiver = {'id': case_id, 'article_id': article, 'run_id': fingerprint({'source_sha256': SOURCE_SHA, 'method': method, 'measurement': measurement}),
            'primary_family': 'pmc6133964-humanized-eae-experiments', 'features': deepcopy(features),
            'feature_evidence': local_evidence, 'source_sha256': SOURCE_SHA, 'body': [method, measurement]}
        _validate_receiver(receiver); receivers.append(receiver)
        quotes = [quote(method_uid, method_text), quote('U49', 'Mice were weighed and scored on a daily basis, with disease severity assessed using a scale ranging from 0 to 5'),
            quote('U49', 'Cetuximab46 (RRID: AB_24896053) for ATROSAB, or mouse IgG (Sigma Aldrich, St. Louis, MO, USA; RRID: AB_253291), for H398.')]
        if drug == 'ATROSAB': quotes.append(quote('U10', 'followed until day 28 of EAE'))
        else: quotes.append(quote('U25', 'Histopathological analyses of spinal cords were performed at day 85 after onset of EAE'))
        method_evidence.append({'receiver_id': case_id, 'quotes': quotes})
        if drug == 'ATROSAB':
            observed = [quote('U11', 'ATROSAB-treated mice showed a highly significant reduction in disease severity in comparison to those treated with the control antibody, until 24 days after disease onset'),
                        quote('U12', 'in some animals (marked in green), the efficacy of ATROSAB treatment appeared to have ceased by the experiment end'),
                        quote('U12', 'r = 0.75, n = 6, p = 0.086')]
            limitations = ['Уменьшение тяжести описано до дня 24; клиническое наблюдение — до дня 28.',
                'У части животных описана потеря ответа. Корреляция антител к препарату с тяжестью не доказана как причинный механизм и имеет p=0,086.',
                'Нельзя утверждать устойчивый эффект во всём окне или отсутствие иммуногенности.']
            end = '24'
        else:
            observed = [quote('U21', 'Blockade of TNFR1 with H398 again resulted in an amelioration of EAE, until approximately 35 days after the onset of EAE'),
                        quote('U21', 'After this time, all H398-treated mice experienced a discernible relapse with an increase in disease severity'),
                        quote('U23', 'Animals receiving this second H398 treatment showed another improvement in EAE which lasted for approximately 20 days')]
            limitations = ['Первый курс сопровождался улучшением примерно до дня 35, затем описан рецидив.',
                'Повторное введение является отдельным изменением вмешательства; его исход нельзя приписать первоначальному курсу.',
                'День 85 относится к гистопатологии; не подставлен как явно указанный конец клинического измерения.']
            end = 'approximately 35'
        outcomes.append({'id': case_id, 'article_id': article, 'source_sha256': SOURCE_SHA,
            'qualitative_direction': 'lower_clinical_burden', 'outcome_class': 'clinical_eae_burden',
            'reported_initial_effect_end': end, 'explicit_clinical_observation_end': observation_end,
            'limitations_ru': limitations, 'evidence': observed})
    packet = {'version': 'source-method-only-receivers-1', 'author': 'Codex', 'expert_validated': False,
        'source_packet_sha256': fingerprint(full), 'source_sha256': SOURCE_SHA, 'receivers': receivers,
        'method_evidence': method_evidence, 'model_calls': 0, 'results_previously_disclosed': True,
        'blind_control': False, 'temporal_train_test_split': False, 'author_script_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope_ru': 'Две вручную проверенные проекции методов одного источника. Это не полная карта статьи и не два независимых исследования. Исходы уже читались Codex; внешний опыт 2018 года старше части обучения.'}
    evaluation = {'version': 'external-operation-outcomes-1', 'source_packet_sha256': fingerprint(full),
        'outcomes': outcomes, 'model_calls': 0, 'expert_validated': False}
    return packet, evaluation


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--source', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args(); disable_network(); methods, outcomes = prepare(args.source)
    root = Path(args.output).resolve(); root.mkdir(parents=True, exist_ok=True)
    write_immutable(root / 'receivers.json', FilePredictionStore.encode(methods))
    write_immutable(root / 'outcomes.json', FilePredictionStore.encode(outcomes))
    print(json.dumps({'receivers': len(methods['receivers']), 'source_sha256': SOURCE_SHA, 'model_calls': 0}))


if __name__ == '__main__': main()
