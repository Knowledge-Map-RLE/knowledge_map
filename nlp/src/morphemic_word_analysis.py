import inspect
import os
from tihonov_dictorinary_parser import parse_tikhonov_dict_file
import pymorphy2

# Патч для совместимости с Python 3.11+
if not hasattr(inspect, 'getargspec'):
    def getargspec(func):
        spec = inspect.getfullargspec(func)
        return spec.args, spec.varargs, spec.varkw, spec.defaults
    inspect.getargspec = getargspec

# Загружаем словарь Тихонова один раз при импорте
# TIHONOV_DICT_PATH = os.environ.get('TIHONOV_DICT_PATH', 'tikhonov_sample.txt')
TIHONOV_DICT_PATH = '../data/Морфемно-орфографический словарь. Тихонов.txt'
try:
    tihonov_entries = parse_tikhonov_dict_file(TIHONOV_DICT_PATH)
    tihonov_dict = {entry['word']: entry for entry in tihonov_entries}
except Exception as e:
    print(f"[WARN] Не удалось загрузить словарь Тихонова: {e}")
    tihonov_dict = {}

morph = pymorphy2.MorphAnalyzer()

# Примитивные списки для fallback
PREFIXES = ['пере', 'при', 'про', 'вы', 'за', 'на', 'об', 'от', 'под', 'раз', 'с']
SUFFIXES = ['ыва', 'ющ', 'ова', 'ир', 'енн', 'нн', 'к', 'ск', 'ов', 'ий', 'ый', 'а', 'я', 'о', 'е', 'ть', 'ся']
POSTFIXES = ['ся']
ENDINGS = ['ий', 'ый', 'ая', 'ое', 'яя', 'ее', 'ся']


def morphemic_split(word):
    """
    Возвращает структуру с морфемами (prefix, root, suffixes, ending, postfix), а также морфологию (lemma, tag).
    Сначала ищет в словаре Тихонова, если нет — использует pymorphy2 и примитивный разбор.
    """
    # 1. Морфология через pymorphy2
    parse = morph.parse(word)[0]
    lemma = parse.normal_form
    tag = parse.tag

    # 2. Пробуем найти в словаре Тихонова
    entry = tihonov_dict.get(word)
    if entry and entry['morphemes']:
        # Попробуем классифицировать морфемы по типу (очень грубо)
        morphemes = entry['morphemes']
        result = {
            'prefix': '',
            'root': '',
            'suffixes': [],
            'ending': '',
            'postfix': '',
            'lemma': lemma,
            'tag': tag,
            'source': 'tikhonov'
        }
        # Грубое определение: приставка — первая морфема, окончание — последняя, корень — первая морфема с гласной, суффиксы — между ними
        if len(morphemes) == 1:
            result['root'] = morphemes[0]
        elif len(morphemes) >= 2:
            # Приставка (если есть)
            if morphemes[0].endswith('-') or morphemes[0] in PREFIXES:
                result['prefix'] = morphemes[0].replace('-', '')
                morphemes = morphemes[1:]
            # Постфикс (если есть)
            if morphemes[-1] in POSTFIXES:
                result['postfix'] = morphemes[-1]
                morphemes = morphemes[:-1]
            # Окончание (если есть)
            if morphemes and morphemes[-1] in ENDINGS:
                result['ending'] = morphemes[-1]
                morphemes = morphemes[:-1]
            # Корень — первая морфема с гласной
            vowels = 'аеёиоуыэюяAEЁИОУЫЭЮЯ'
            for i, m in enumerate(morphemes):
                if any(v in m for v in vowels):
                    result['root'] = m
                    # Всё между корнем и окончанием — суффиксы
                    result['suffixes'] = morphemes[:i] + morphemes[i+1:]
                    break
            else:
                # Если не нашли корень, всё — суффиксы
                result['suffixes'] = morphemes
        return result

    # 3. Если нет в словаре — fallback: грубый разбор
    w = word
    result = {
        'prefix': '',
        'root': '',
        'suffixes': [],
        'ending': '',
        'postfix': '',
        'lemma': lemma,
        'tag': tag,
        'source': 'fallback'
    }
    # Приставка
    for p in sorted(PREFIXES, key=len, reverse=True):
        if w.startswith(p):
            result['prefix'] = p
            w = w[len(p):]
            break
    # Постфикс
    for pf in POSTFIXES:
        if w.endswith(pf):
            result['postfix'] = pf
            w = w[:-len(pf)]
            break
    # Окончание
    for e in ENDINGS:
        if w.endswith(e):
            result['ending'] = e
            w = w[:-len(e)]
            break
    # Суффиксы (может быть несколько)
    for s in sorted(SUFFIXES, key=len, reverse=True):
        if w.endswith(s):
            result['suffixes'].insert(0, s)
            w = w[:-len(s)]
    # Корень — остаток
    result['root'] = w
    return result

if __name__ == "__main__":
    test_words = [
        'переписывающийся',
        'абажуродержатель',
        'абонентка',
        'абстракция',
        'абсурдный',
        'абрикосовый',
        'абонементный',
        'абляционный',
    ]
    for word in test_words:
        print(f"{word}: {morphemic_split(word)}")