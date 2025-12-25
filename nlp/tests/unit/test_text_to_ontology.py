"""
Тестирование преобразования текста в онтологию 
"""

"""
Напиши тесты преобразоывания текста в онтологию через NLP.
Возьми текст из файла `data\nlp\Новый формат статьи. Первый этап.eng.md`
и с помощью функции ❓ переобразуй его в семантический граф,
а затем сравни с файлом онтологией ниже.

Для полной обработки нужно преобразоывать каждое предложение в
онтологию и убедиться что эта онтология может преобразовываться
обратно в тоже самое предложение.
"""

import re

from typing import List, Tuple, NamedTuple

from pathlib import Path
from rdflib import Graph, Namespace, Literal
from rdflib.namespace import RDF, RDFS, OWL
from graphviz import Digraph

from src.processors.level1_tokenization_processor import Level1TokenizationProcessor
from src.multilevel_analyzer import MultiLevelAnalyzer


# --------------------
# Тестовый RDF граф
# --------------------

EX = Namespace("http://example.org/parkinson#")

g = Graph()
g.bind("", EX)

def concept(name, ru=None, en=None):
    n = EX[name]
    g.add((n, RDF.type, OWL.Thing))
    if ru:
        g.add((n, RDFS.label, Literal(ru, "ru")))
    if en:
        g.add((n, RDFS.label, Literal(en, "en")))
    return n

def relation(s, p, o):
    g.add((s, EX[p], o))


# --------- Concepts ---------

открыть = concept("открыть", ru="открыть")
дофамин = concept("дофамин", ru="дофамин")
нейромедиатор = concept("нейромедиатор", ru="нейромедиатор")
_1950ых = concept("1950ых", ru="1950-ых")

исследование = concept("исследование", ru="исследование", en="research")
проводить = concept("проводить", ru="проводить", en="conduct")

болезнь = concept("болезнь", ru="болезнь", en="disease")
паркинсон = concept("Паркинсон", ru="Паркинсон", en="Parkinson")
болезнь_Паркинсона = concept(
    "болезнь_Паркинсона",
    ru="болезнь Паркинсона",
    en="Parkinson's disease"
)
БП = concept("БП", ru="БП", en="PD")

сформировать = concept("сформировать", ru="сформировать", en="generated")
совокупность = concept("совокупность", ru="совокупность", en="body")
знание = concept("знание", ru="знание", en="knowledge")
сложный = concept("сложный", ru="сложный", en="complex")
богатый = concept("богатый", ru="богатый", en="rich")


# --------- Semantic relations (question-based) ---------

relation(открыть, "что", дофамин)
relation(открыть, "когда", _1950ых)
relation(дофамин, "как_что", нейромедиатор)

relation(исследование, "с_какого_момента", открыть)
relation(исследование, "чего", болезнь)
relation(исследование, "что_сделали", сформировать)

relation(проводить, "что", исследование)

relation(болезнь, "какой", паркинсон)
relation(БП, "сокращение", болезнь_Паркинсона)

relation(сформировать, "что", совокупность)
relation(совокупность, "о_чём", болезнь)
relation(совокупность, "чего", знание)
relation(совокупность, "какая", сложный)
relation(совокупность, "какая", богатый)


# --------------------
# Graphviz visualization (for tests)
# --------------------

def visualize_ontology(rdf_graph, filename="../data/nlp/ontology_test"):
    dot = Digraph(
        name="Ontology",
        format="png",
        graph_attr={
            "rankdir": "LR",
            "fontsize": "10"
        },
        node_attr={
            "shape": "box",
            "style": "rounded"
        }
    )

    def short(uri):
        return uri.split("#")[-1]

    OWL_THING = str(OWL.Thing)
    RDFS_LABEL = str(RDFS.label)

    added_nodes = set()

    for s, p, o in rdf_graph:
        # 1. Пропускаем owl:Thing и все смежные рёбра
        if str(s) == OWL_THING or str(o) == OWL_THING:
            continue

        # 2. Пропускаем rdfs:label и связанные literal-узлы
        if str(p) == RDFS_LABEL:
            # но субъект (концепт) мы всё равно добавим как узел
            s_id = short(s)
            if s_id not in added_nodes:
                dot.node(s_id, s_id)
                added_nodes.add(s_id)
            continue

        # 3. Пропускаем literal-объекты (на всякий случай)
        if isinstance(o, Literal):
            continue

        s_id = short(s)
        o_id = short(o)
        p_label = short(p)

        if s_id not in added_nodes:
            dot.node(s_id, s_id)
            added_nodes.add(s_id)

        if o_id not in added_nodes:
            dot.node(o_id, o_id)
            added_nodes.add(o_id)

        dot.edge(s_id, o_id, label=p_label)

    dot.render(filename, view=True)


# --------------------
# Моё тестирование
# --------------------

# Вспомогательные функции

def find_h1_headers_simple(markdown_text: str) -> Tuple[List[dict], int]:
    """Подсчёт заголовков первого уровня"""
    headers = []
    pattern = re.compile(r'^# (.+)$', re.MULTILINE)
    
    for match in pattern.finditer(markdown_text):
        headers.append({
            'text': match.group(1).strip(),
            'start': match.start(),
            'end': match.end(),
            'full_match': match.group(0)
        })
    
    return headers, len(headers)

# Получение текста

def test_tokenization_first_sentence():
    with open(Path('../data/nlp/Новый формат статьи. Первый этап.eng.md'), 'r', encoding='utf8') as f:
        text = f.read().strip()
    
    # Прежде чем брать первое предложение
    # Нужно
    # - отделить текст от мета информации
    # - (TODO) решить за что принимать заголовки, за структуру/контекст, не за предложения?
    text_original = text

    parts_one = text_original.split('---')
    parts_two = parts_one[2].split('## References')
    
    meta = parts_one[1].strip()
    text = parts_two[0].strip()
    refs = parts_two[1].strip()


    # Проверка, что обязательно есть только 1 заголовок первого уровня
    pattern = re.compile(r'^# ', re.MULTILINE)
    matches, length = find_h1_headers_simple(text)

    assert length == 1, 'Ошибка. Не каноничный Markdown. Должен быть только один заголовок первого уровня.'
    print(length)

    # for match in pattern.finditer(text):
    #     print(f"Найдено на позиции {match.start()}: '{match.group()}'")
    #     print(f"Строка: {match.span()}")

    # print(text)

    # Подобно Jupyter блокноту, мета информация, заголовки, абзацы, таблицы, илюстрации и описания к ним
    # могут быть отдельными "ячейками"


    # 
    # process_level_1 = Level1TokenizationProcessor(enable_voting=False)
    # result = process_level_1.process_text(text)
    # sentences = [s['text'] for s in result['sentences']]

    # print('ТУТ')
    # assert str(sentences[6]) == "The hallmarks of Parkinson's disease\n\n## Abstract\n\nSince the discovery of dopamine as a neurotransmitter in the 1950s, Parkinson's disease (PD) research has generated a rich and complex body of knowledge, revealing PD to be an age-related multifactorial disease, influenced by both genetic and environmental factors."

# --------------------
# Output
# --------------------

# print(g.serialize(format="turtle"))

# визуальная проверка онтологии
# visualize_ontology(g)

def test_division():
    assert 10 / 2 == 5

if __name__ == '__main__':
    test_tokenization_first_sentence()