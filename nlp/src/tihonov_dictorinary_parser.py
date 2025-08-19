import re

def parse_tikhonov_dict_line(line):
    """
    Парсит одну строку морфемного словаря Тихонова.
    Возвращает: (слово, список морфем, комментарий)
    """
    # Убираем комментарии после знака |
    if '|' in line:
        word, comment = line.split('|', 1)
        word = word.strip()
        comment = comment.strip()
    else:
        word = line.strip()
        comment = ''
    # Если есть разметка морфем через /, выделяем морфемы
    if '/' in word:
        parts = word.split('/')
        # Слово — это первая часть до первого /
        main_word = parts[0].replace('-', '').replace("'", "").strip()
        # Морфемы — все части после первого /
        morphemes = [p.replace("'", "").strip() for p in parts[1:] if p.strip()]
        return main_word, morphemes, comment
    else:
        # Если нет разметки, просто возвращаем слово
        main_word = word.replace('-', '').replace("'", "").strip()
        return main_word, [], comment

def parse_tikhonov_dict_file(filepath):
    """
    Парсит весь файл морфемного словаря Тихонова.
    Возвращает список словарей: [{'word': ..., 'morphemes': [...], 'comment': ...}, ...]
    """
    entries = []
    with open(filepath, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            word, morphemes, comment = parse_tikhonov_dict_line(line)
            entries.append({
                'word': word,
                'morphemes': morphemes,
                'comment': comment
            })
    return entries

# Пример использования:
if __name__ == "__main__":
    # Замените на путь к вашему файлу
    filepath = "tikhonov_sample.txt"
    entries = parse_tikhonov_dict_file(filepath)
    for entry in entries[:10]:
        print(entry)