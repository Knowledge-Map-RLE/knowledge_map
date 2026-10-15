"""Административная диагностика совместных мотивов из явного списка карт, без AI."""
import argparse
from hashlib import sha256
import json
import logging
from pathlib import Path
import time

from domain.article_maps import fingerprint, require
from domain.joint_operator_patterns import VERSION, census
from domain.participant_availability import audit as audit_participants
from tools.run_free_prediction import disable_network

logger = logging.getLogger(__name__)


def read_manifest(path, excluded_sha256):
    manifest = json.loads(path.read_text(encoding='utf-8-sig'))
    require(manifest['version'] == 'joint-motif-explicit-inputs-1', 'Explicit compatible manifest required')
    maps, families = [], {}
    for row in manifest['sources']:
        raw = Path(row['path']).read_bytes()
        require(sha256(raw).hexdigest() == row['file_sha256'], 'Map file hash differs')
        snapshot = json.loads(raw)
        require(snapshot['article_id'] == row['article_id'] and snapshot['run_id'] == row['run_id'],
                'Map identity differs')
        require(snapshot['source']['sha256'] == row['source_sha256'] != excluded_sha256,
                'Excluded target or changed source')
        require(row['article_id'] not in families, 'Repeated manifest source')
        maps.append(snapshot)
        families[row['article_id']] = row['family']
    return manifest, maps, families


def render_ru(result):
    lines = ['# Совместные мотивы с сохранением ролей участников', '',
             f"Проверено карт: {result['maps']}. Совместные группы содержат от одной до трёх предпосылок.",
             '**Новых научных прогнозов — 0. Преимущество графа этой диагностикой не установлено.**', '',
             'В этой проверке одновременно сохраняются совместные входы, совпадения участников между ролями '
             'и ссылки на знания внутри группы. Альтернативные пути остаются отдельными группами. '
             'Внутренние зависимости между посылками сохраняются. Циклы скрытых ссылок не разворачиваются рекурсивно.', '',
             '| Представление | Различных мотивов | В нескольких публикациях | В нескольких заданных семействах |',
             '| --- | ---: | ---: | ---: |']
    labels = {'faithful': 'Предикаты, значения и условия сохранены', 'structural': 'Только форма операции и роли'}
    for mode, label in labels.items():
        data = result['modes'][mode]
        lines.append(f"| {label} | {data['pattern_count']} | {data['cross_source_patterns']} | {data['cross_family_patterns']} |")
    lines += ['', '## Охват совместных групп', '', '| Карта | Один вход | Два входа | Три входа | Более трёх |',
              '| --- | ---: | ---: | ---: | ---: |']
    for row in result['sources']:
        lines.append(f"| {row['article_id']} | {row.get('arity_1', 0)} | {row.get('arity_2', 0)} | {row.get('arity_3', 0)} | {row.get('over_three_joint_premises', 0)} |")
    lines += ['', '## Повторяемые составные мотивы', '']
    for mode in labels:
        repeated = [r for r in result['modes'][mode]['patterns']
                    if r['source_support'] >= 2 and r['pattern']['arity'] >= 2]
        lines.append(f"{labels[mode]}: {len(repeated)} составных мотивов в нескольких публикациях.")
        for row in repeated[:10]:
            lines.append(f"- `{row['pattern']['id']}`: {row['pattern']['arity']} совместных входа; "
                         f"публикаций {row['source_support']}; примеры "
                         + '; '.join(e['article_id'] + ': ' + ', '.join(e['premises']) + ' → ' + e['head']
                                    for e in row['examples'][:3]) + '.')
        lines.append('')
    lines += ['## Возможность связать участников', '',
              f"Из рассмотренных групп {sum(r.get('groups_with_new_head_participants', 0) for r in result['sources'])} "
              'содержат в заключении участника, которого нет в посылках. Такой мотив нельзя непосредственно применить '
              'как правило с привязанными переменными: получение нового участника потребует отдельного источника или операции. '
              'Сравнение выполняется по локальным идентификаторам внутри группы; доступность того же понятия в остальных блоках '
              'и смысловые синонимы здесь не проверяются. Это не диагноз ошибки карты.',
              f"Внутренние зависимости между посылками имеются в {sum(r.get('groups_with_internal_premise_edges', 0) for r in result['sources'])} группах.", '']
    lines += ['## Границы интерпретации', '', *result['limitations_ru'], '',
              'Совпадение формы при скрытии контекста и чисел служит лишь очередью для проверки. '
              'Исходные значения сохранены в артефактах карт; такая форма автоматически не становится правилом переноса. '
              'Полярность, кванторы, модальность, статус действия, размерности и топология участников сохраняются в обоих режимах.', '',
              'Следующий шаг выбирается по фактическим повторениям: источниковая проверка каждого составного мотива, '
              'затем проверка применимости к новым посылкам. Если повторений нет, расширение числа предпосылок само по себе не устраняет недостаток поддержки.', '',
              'CLI запрещает сетевые подключения. Модельных вызовов — 0. GOLD и текущие карты не изменены. '
              'Сервисы не менялись. Экспертная проверка отсутствует.', '']
    if 'participant_availability' in result:
        audits = result['participant_availability']
        sums = {key: sum(a['counts'].get(key, 0) for a in audits)
                for key in ('groups_all_new_symbols_elsewhere', 'groups_with_unavailable_symbols',
                            'no_new_symbol_in_head', 'other_ancestor_symbol_terms', 'off_chain_symbol_terms',
                            'target_or_target_dependent_only_terms', 'groups_with_target_dependent_premises')}
        lines += ['## Дополнительная проверка доступности участников во всей карте', '',
                  'Эта проверка охватывает все размеры совместных групп. Заключение и все блоки, использующие его '
                  'через видимые переходы или скрытые ссылки, исключены из источников доступности, '
                  'даже если такой блок указан среди исходных предпосылок.', '',
                  f"В {sums['groups_all_new_symbols_elsewhere']} группах все дополнительные символы встречаются в других допустимых блоках; "
                  f"в {sums['groups_with_unavailable_symbols']} группах хотя бы один не найден вне заключения и зависимых от него блоков. "
                  f"В {sums['no_new_symbol_in_head']} группах дополнительных символов нет.", '',
                  f"По отдельным упоминаниям: {sums['other_ancestor_symbol_terms']} доступны в других предках заключения; "
                  f"{sums['off_chain_symbol_terms']} — в блоках вне этой цепочки; "
                  f"{sums['target_or_target_dependent_only_terms']} — только в исключённых блоках.", '',
                  f"Групп с зависимой от заключения исходной посылкой: {sums['groups_with_target_dependent_premises']}. "
                  'Такие ссылки могут быть допустимы в скрытой семантике, но не дают независимых исходных посылок для предсказания.', '',
                  'Это уточняет диагноз локальных непривязанных участников. Известность понятия не означает известность '
                  'его нового свойства, причины или результата вмешательства. Дополнительные блоки не добавляются в '
                  'авторские группы автоматически. Контекст, достаточность посылок и оператор ещё требуют проверки. '
                  'Отсутствие участника в текущих посылках само по себе не доказывает недостаток обучающего корпуса.', '']
    return '\n'.join(lines)


def run(manifest_path, output, excluded_sha256):
    started = time.monotonic()
    manifest, maps, families = read_manifest(manifest_path, excluded_sha256)
    logger.info('joint_motif_audit_start maps=%d', len(maps))
    result = census(maps, families)
    result['participant_availability'] = [audit_participants(snapshot) for snapshot in maps]
    implementation = {
        relative: sha256((Path(__file__).resolve().parents[1] / relative).read_bytes()).hexdigest()
        for relative in ('domain/joint_operator_patterns.py', 'domain/operator_pattern_forecast.py',
                         'domain/participant_availability.py',
                         'domain/operator_frame_routing.py', 'domain/comparison_normalization.py',
                         'domain/article_maps.py', 'domain/development_prediction.py',
                         'tools/audit_joint_operator_patterns.py', 'tools/run_free_prediction.py')}
    identity = fingerprint({'version': VERSION, 'manifest': manifest, 'implementation': implementation,
                            'excluded_target_source_sha256': excluded_sha256})
    result.update(run_id=identity, inputs=manifest, implementation_sha256=implementation,
                  excluded_target_source_sha256=excluded_sha256)
    files = {'data.json': json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8'),
             'report.ru.md': render_ru(result).encode('utf-8')}
    verification = {'run_id': identity, 'files': {name: sha256(data).hexdigest() for name, data in files.items()},
                    'input_hashes_verified': True, 'target_excluded_by_source_hash': True,
                    'expert_validated': False, 'model_calls': 0}
    files['verification.json'] = json.dumps(verification, ensure_ascii=False, indent=2).encode('utf-8')
    target = output / 'runs' / identity
    # Изменённый артефакт не перезаписывается даже при совпадении идентификатора запуска.
    for name, data in files.items():
        if (target / name).exists():
            require((target / name).read_bytes() == data, 'Immutable artifact differs')
    target.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        if not (target / name).exists():
            with (target / name).open('xb') as stream:
                stream.write(data)
    logger.info('joint_motif_audit_complete maps=%d duration_seconds=%.3f run_id=%s',
                len(maps), time.monotonic() - started, identity)
    return target


def main():
    parser = argparse.ArgumentParser(description='Совместные мотивы явного корпуса без модельных вызовов')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--exclude-source-sha256', required=True)
    args = parser.parse_args()
    disable_network()
    logging.basicConfig(level=logging.INFO)
    print(run(args.manifest, args.output, args.exclude_source_sha256))


if __name__ == '__main__':
    main()
