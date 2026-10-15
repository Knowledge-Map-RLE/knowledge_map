"""Полный реестр определений и отдельная лицензия источникового противопоставления."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.categorical_licenses import VERSION, validate_licenses
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network


REASONS = {
    ('pmc5436834', 'K3'): 'Описаны признаки AD и различие специфичности; без отдельной лицензии диагностических критериев нельзя объявлять все реальные случаи универсальным классом.',
    ('pmc5436834', 'K9'): 'Составная молекулярная характеристика, массы и превращение форм скрыты в атрибутах; требуется отдельный типизированный оператор структуры и процесса.',
    ('pmc5436834', 'K25'): 'Описан механизм вмешательства, а не универсальное включение классов; механизм не доказывает будущий клинический эффект.',
    ('pmc5436834', 'K35'): 'Определение механизма доставки требует классового связывания средства и процесса; произвольное отношение characterized_by не лицензируется автоматически.',
    ('pmc6416157', 'K12'): 'Перекрывающиеся числовые диапазоны I² не являются непересекающимися классами; нужны интервальные ограничения.',
    ('pmc7789349', 'K1'): 'Минимальное влияние на повседневную жизнь не равно его полному отсутствию; промежуточность не задаёт универсальную причинную цепочку.',
    ('pmc7789349', 'K3'): 'Описание фенотипов составное, а исходы имеют модальность; тенденция к деменции не становится категорическим включением.',
    ('pmc7789349', 'K11'): 'Числа и шкала инструмента оценки требуют отдельного оператора, а не автоматического превращения метода в класс случаев.',
    ('pmc7789349', 'K90'): 'В одном противопоставлении объединены обязательные критерии, необязательное свидетельство и гипотетическое объяснение; все части нельзя лицензировать одной универсальной формой.',
    ('pmc8775386', 'K1'): 'Возможная вовлечённость воспаления в заболевания явно не является достаточной причиной.',
    ('pmc8775386', 'K5'): 'В одной части объединены описание MCI и фоновые вероятностные оценки; нужны независимые лицензии частей с сохранением условий.',
    ('pmc8775386', 'K17'): 'Определение суммы баллов и её направления требует арифметического оператора с диапазоном.',
    ('pmc8918697', 'K1'): 'Промежуточное состояние не даёт универсального включения или неизбежного перехода к деменции.',
    ('pmc8918697', 'K4'): 'Субъект — критерии Petersen; для правил о случаях требуется явное связывание класса диагностируемых случаев, а не отождествление критериев и пациентов.',
    ('pmc4336104', 'K33'): 'Определение нижнего квартиля и приблизительного порога привязано к выборке и требует числового оператора.',
    ('pmc4336104', 'K39'): 'Категории двух индексов имеют разные интервальные границы; их нельзя объединять по названиям.',
    ('pmc5005896', 'K14'): 'Пороговая классификация и расхождение границ в тексте/таблице требуют интервального оператора и отдельного учёта вариантов.',
    ('pmc5005896', 'K15'): 'Диапазон и ориентация MMSE являются измерительным определением, а не классификацией пациентов.',
    ('pmc6218168', 'K15'): 'Определяется оцениваемая величина модели — уровень, а не универсальная связь биомаркера и результата.',
    ('pmc6218168', 'K16'): 'Мгновенная скорость в заданный момент не равна постоянному наклону за весь срок; требуется оператор модели.',
    ('pmc5887909', 'K4'): 'Структура двух барьеров требует типизированного определения состава; различие названий не является автоматически доказанной дизъюнктностью классов.',
    ('pmc5651799', 'K10'): 'Три измерительных определения сохраняют разные временные и арифметические операции; они не являются тремя категорическими законами.',
    ('pmc8294390', 'K12'): 'Противопоставление моделей содержит состав доменов и дополнительную экспрессию; различие генотипов не следует превращать в универсальную эквивалентность или прогноз эффекта.',
}


def prepare(input_run, parent_audit):
    root = Path(input_run).resolve()
    forecast = FilePredictionStore(root.parent).read_seal(root.name)
    require(forecast is not None and forecast['model_calls'] == 0, 'Sealed forecast required')
    raw_manifest = (root / 'source-manifest.json').read_bytes()
    manifest = json.loads(raw_manifest)
    require(sha256(raw_manifest).hexdigest() == forecast['binding']['metadata']['source_manifest_sha256'],
            'Definition inventory manifest differs')
    port = FileForecastMaps(manifest['sources'])
    maps = [port.get(e['reference']['article_id'], e['reference']['pipeline_id'], port.owner, e['reference']['run_id'])
            for e in manifest['sources']]
    parent_raw = Path(parent_audit).read_bytes(); parent = json.loads(parent_raw)
    require(fingerprint(parent) == forecast['binding']['categorical_licenses_sha256'], 'Parent license differs')
    validate_licenses(maps, parent)
    target = next(m for m in maps if m['article_id'] == 'pilot-pmc10000452-pmc5436834-10b9d676a760e5df')
    knowledge = next(k for k in target['graph']['knowledge'] if k['knowledge_id'] == 'K11')
    require(knowledge['semantic_frame']['logic'] == 'contrast'
            and [s['predicate'] for s in knowledge['semantic_frame']['statements']] == ['has_death_domain'] * 2
            and [s['negated'] for s in knowledge['semantic_frame']['statements']] == [False, True],
            'Expected source contrast differs')
    units = {u['id']: u for u in target['source']['units']}
    text = units['U13']['text']
    require('TNFR1, which contains the DD' in text and 'TNFR2 lacks the DD' in text,
            'Source does not explicitly assert both contrast parts')
    first = knowledge['semantic_frame']['statements'][0]
    constraints = {'roles': [r for r in first['roles'] if r['role'] != 'subject'],
                   'attributes': first['qualifiers']['attributes'], 'conditions': first['conditions'],
                   'temporal_context': first['temporal_context']}
    article = target['article_id']; digest = fingerprint(constraints)
    scope = {'study_group': article, 'time': None, 'modality': None, 'conditions': [
        'Receptor classes as structurally described in this review; not a claim about engineered constructs or all experimental genotypes',
        'Intracellular death-domain presence only; no prediction of survival, apoptosis, intervention response or human benefit',
        'native_definition_constraints_sha256:' + digest]}
    property_ = {'kind': 'unary_property', 'predicate': 'has_death_domain',
                 'local_id': 'unary_property:has_death_domain:' + digest,
                 'text_en': 'Receptor structures containing an intracellular death domain',
                 'text_ru': 'Структуры рецепторов с внутриклеточным death domain',
                 'native_constraints': deepcopy(constraints)}
    property_['id'] = article + '::' + property_['local_id']
    annotations = []
    for statement, cid, name in zip(knowledge['semantic_frame']['statements'], ['C25', 'C26'], ['TNFR1', 'TNFR2']):
        require(next(r['concept_id'] for r in statement['roles'] if r['role'] == 'subject') == cid,
                'Source receptor role differs')
        subject = {'kind': 'concept', 'concept_id': cid, 'local_id': 'concept:' + cid,
                   'id': article + '::concept:' + cid, 'text_en': name, 'text_ru': name + ' в структурном описании обзора'}
        annotations.append({'statement_id': statement['statement_id'], 'decision': 'license_definition',
            'license_kind': 'unary_definition_requirement', 'bindings': {'subject': subject, 'object': deepcopy(property_)},
            'native_constraints': deepcopy(constraints),
            'clause': {'form': 'E' if statement['negated'] else 'A', 'subject': subject['id'],
                       'object': property_['id'], 'scope': deepcopy(scope)},
            'reason_ru': 'Источник прямо утверждает наличие или отсутствие домена; это структурное определение с локальной областью, не будущий эффект.'})
    parents = {uid for s in knowledge['semantic_frame']['statements'] for uid in s['provenance']['unit_ids']}
    evidence = [{'unit_id': uid, 'start': units[uid]['start'], 'end': units[uid]['end'],
                 'text': units[uid]['text'], 'sha256': sha256(units[uid]['text'].encode()).hexdigest()}
                for uid in sorted(parents)]
    entry = {'article_id': article, 'run_id': target['run_id'], 'knowledge_id': 'K11',
        'source_sha256': target['source']['sha256'], 'graph_sha256': fingerprint(target['graph']),
        'knowledge_sha256': fingerprint(knowledge), 'scope': scope, 'statements': annotations, 'evidence': evidence,
        'independent_contrast_parts': True, 'shared_native_constraints': deepcopy(constraints),
        'independence_reason_ru': 'Обе стороны противопоставления являются самостоятельными прямо утверждёнными структурными описаниями; противопоставление и целый родитель сохранены.',
        'reason_ru': 'Codex проверил обе исходные фразы; каноническая карта не меняется.',
        'scope_reason_ru': 'Речь о классах структур рецепторов в данном обзоре; генетические конструкты и результаты вмешательств не обобщаются.'}
    audit = deepcopy(parent); audit.update(version=VERSION, author_script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        parent_audit_sha256=fingerprint(parent)); audit['entries'].append(entry)
    validate_licenses(maps, audit)
    selected = {(e['article_id'], e['knowledge_id']) for e in audit['entries']}
    rows = []
    for e, m in zip(manifest['sources'], maps):
        pmc = e['pmcid'].lower()
        for k in m['graph']['knowledge']:
            if k['knowledge_kind'] != 'definition': continue
            licensed = (m['article_id'], k['knowledge_id']) in selected
            reason = 'Есть отдельная источниковая лицензия; остальные части целого блока сохраняются.' if licensed else REASONS.get((pmc, k['knowledge_id']))
            require(reason is not None, 'Unreviewed definition in full inventory')
            rows.append({'article_id': m['article_id'], 'pmcid': pmc, 'run_id': m['run_id'],
                'knowledge_id': k['knowledge_id'], 'knowledge_sha256': fingerprint(k),
                'source_sha256': m['source']['sha256'], 'graph_sha256': fingerprint(m['graph']),
                'decision': 'licensed_parts' if licensed else 'retain_without_categorical_conversion', 'reason_ru': reason,
                'complete_knowledge': deepcopy(k),
                'evidence': [{**deepcopy(u), 'sha256': sha256(u['text'].encode()).hexdigest()}
                    for u in m['source']['units'] if u['id'] in {uid for s in k['semantic_frame']['statements'] for uid in s['provenance']['unit_ids']}]})
    require(len(rows) == 26 and sum(len(m['graph']['knowledge']) for m in maps) == 943, 'Full inventory size differs')
    inventory = {'version': 'source-definition-inventory-1', 'author': 'Codex', 'expert_validated': False,
        'input_run_id': forecast['run_id'], 'input_sha256': fingerprint(forecast),
        'source_manifest_sha256': sha256(raw_manifest).hexdigest(), 'canonical_blocks': 943,
        'definition_blocks': len(rows), 'definition_statements': sum(len(r['complete_knowledge']['semantic_frame']['statements']) for r in rows),
        'categorical_license_sha256': fingerprint(audit), 'rows': rows, 'model_calls': 0,
        'coverage_limit_ru': 'Полный реестр существующей метки definition; истинные определения, ошибочно размеченные другими видами знания, этим реестром не исключаются и требуют отдельного аудита.'}
    return audit, inventory


def main():
    parser = argparse.ArgumentParser()
    for name in ('input-run', 'parent-audit', 'output'): parser.add_argument('--' + name, required=True)
    args = parser.parse_args(); disable_network()
    audit, inventory = prepare(args.input_run, args.parent_audit)
    output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=True)
    for name, value in [('categorical-licenses.json', audit), ('definition-inventory.json', inventory)]:
        write_immutable(output / name, FilePredictionStore.encode(value))
    print(json.dumps({'definitions': inventory['definition_blocks'], 'statements': inventory['definition_statements'],
        'licensed_parents': len(audit['entries']), 'model_calls': 0}, ensure_ascii=False))


if __name__ == '__main__': main()
