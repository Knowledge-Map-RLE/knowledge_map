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

import spacy

from typing import List, Tuple, NamedTuple, Optional

from pathlib import Path
from rdflib import Graph, Namespace, Literal, URIRef, RDF, RDFS
from rdflib.namespace import RDF, RDFS, OWL, FOAF, SKOS, DC
from graphviz import Digraph

from src.validation.markdown_validator import validate_frontmatter


# --------------------
# Тестовый RDF граф
# --------------------

def get_first_sentence_ontology():
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

    return g


# --------------------
# Graphviz visualization (for tests)
# --------------------

def visualize_ontology(rdf_graph, filename):
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



def text_to_ontology(
    text: str,
    nlp: Optional[spacy.language.Language] = None,
    base_uri: str = "http://example.org/ontology#"
) -> Graph:
    """
    Преобразует текст в онтологию используя spaCy NLP анализ.
    Использует подход с concept() и relation() для построения графа.
    
    Args:
        text: Исходный текст
        nlp: Модель spaCy
        base_uri: Базовый URI для онтологии
        
    Returns:
        RDF граф с извлеченными концептами и отношениями
    """
    if nlp is None:
        nlp = spacy.load("en_core_web_sm")
    
    # Создаем граф и namespace
    EX = Namespace(base_uri)
    g = Graph()
    g.bind("", EX)
    
    # Вспомогательные функции для создания концептов и связей
    def concept(name, label_text=None, lang="en"):
        """Создает концепт в графе"""
        n = EX[name]
        g.add((n, RDF.type, OWL.Thing))
        if label_text:
            g.add((n, RDFS.label, Literal(label_text, lang)))
        return n
    
    def relation(subj, pred, obj):
        """Создает отношение между концептами"""
        g.add((subj, EX[pred], obj))
    
    # Обрабатываем текст через spaCy
    doc = nlp(text)
    
    # Словарь для хранения уже созданных концептов (по лемме)
    concepts_cache = {}
    
    # Создаем концепты для каждого значимого токена
    for token in doc:
        # Пропускаем пунктуацию и служебные слова
        if token.is_punct or token.is_space:
            continue
        
        # Используем лемму как идентификатор концепта
        lemma = token.lemma_.lower()
        
        # Создаем уникальный ID для токена
        token_id = f"{lemma}_{token.i}"
        
        if token_id not in concepts_cache:
            # Создаем концепт
            token_concept = concept(token_id, label_text=token.text)
            concepts_cache[token_id] = token_concept
    
    # Создаем отношения на основе синтаксических зависимостей
    for token in doc:
        if token.is_punct or token.is_space:
            continue
        
        token_id = f"{token.lemma_.lower()}_{token.i}"
        token_concept = concepts_cache.get(token_id)
        
        if token_concept and token.head != token:
            head_id = f"{token.head.lemma_.lower()}_{token.head.i}"
            head_concept = concepts_cache.get(head_id)
            
            if head_concept:
                # Создаем отношение на основе типа зависимости
                dep_type = token.dep_
                relation(head_concept, dep_type, token_concept)
    
    # Обрабатываем именованные сущности
    for ent in doc.ents:
        # Создаем концепт для сущности
        ent_id = f"entity_{ent.text.replace(' ', '_')}"
        ent_concept = concept(ent_id, label_text=ent.text)
        
        # Добавляем тип сущности
        ent_type_concept = concept(f"entity_type_{ent.label_}", label_text=ent.label_)
        relation(ent_concept, "entity_type", ent_type_concept)
        
        # Связываем токены сущности с самой сущностью
        for token in ent:
            token_id = f"{token.lemma_.lower()}_{token.i}"
            token_concept = concepts_cache.get(token_id)
            if token_concept:
                relation(ent_concept, "has_token", token_concept)
    
    return g


# Получение текста

def test_text_to_ontology():
    with open(Path('../data/nlp/Новый формат статьи. Первый этап.eng.md'), 'r', encoding='utf8') as f:
        text = f.read().strip()
    
    # Если проходит валидация значит у нас уже есть вся необходимая структура Markdown файла
    validation_result = validate_frontmatter(text)


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
    
    nlp = spacy.load("en_core_web_sm")

    text = "Since the discovery of dopamine as a neurotransmitter in the 1950s, Parkinson's disease (PD) research has generated a rich and complex body of knowledge, revealing PD to be an age-related multifactorial disease, influenced by both genetic and environmental factors."

    # Эта онтология должна рассчитываться NLP сервисом и быть там
    current_first_sentence_ontology = text_to_ontology(text, nlp)
    # Это тестовая онтология должна быть здесь, захардкожена как эталон
    test_example_first_sentence_ontology = get_first_sentence_ontology()

    visualize_ontology(current_first_sentence_ontology, "../data/nlp/ontology_current")
    visualize_ontology(test_example_first_sentence_ontology, "../data/nlp/ontology_test")

    assert current_first_sentence_ontology.isomorphic(test_example_first_sentence_ontology), 'Ошибка. Текущая онтология первого предложения не соответствет тестовой онтологии первого предложения.'


    # Подобно Jupyter блокноту, мета информация, заголовки, абзацы, таблицы, илюстрации и описания к ним
    # могут быть отдельными "ячейками"


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
    print('Здесь должны быть примеры использования')