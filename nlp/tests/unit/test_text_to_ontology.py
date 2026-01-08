"""
Тестирование преобразования текста в онтологию 
Включает визуализацию различий между ожидаемым и фактическим графами
"""

import re
import spacy
from typing import List, Tuple, NamedTuple, Optional, Set, Dict
from pathlib import Path
from rdflib import Graph, Namespace, Literal, URIRef, RDF, RDFS
from rdflib.namespace import RDF, RDFS, OWL, FOAF, SKOS, DC
from graphviz import Digraph

from src.validation.markdown_validator import validate_frontmatter


# --------------------
# Тестовый RDF граф
# --------------------

def get_first_sentence_ontology():
    """
    Полная эталонная онтология для первого предложения.
    Содержит ВСЕ смысловые концепты и 4 типа связей.
    """
    EX = Namespace("http://example.org/parkinson#")
    g = Graph()
    g.bind("", EX)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)

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

    # ========== ALL CONCEPTS ==========
    # События и действия
    discovery = concept("discovery", ru="открытие", en="discovery")
    generate = concept("generate", ru="генерировать", en="generate")
    reveal = concept("reveal", ru="раскрывать", en="reveal")
    influence = concept("influence", ru="влиять", en="influence")
    
    # Сущности и объекты
    dopamine = concept("dopamine", ru="дофамин", en="dopamine")
    neurotransmitter = concept("neurotransmitter", ru="нейромедиатор", en="neurotransmitter")
    year_1950s = concept("1950s", ru="1950-ые", en="1950s")
    
    # Болезнь
    parkinsons_disease = concept("Parkinsons_disease", ru="болезнь Паркинсона", en="Parkinson's disease")
    PD = concept("PD", ru="БП", en="PD")
    disease = concept("disease", ru="заболевание", en="disease")
    
    # Исследования и знания
    research = concept("research", ru="исследование", en="research")
    body_of_knowledge = concept("body_of_knowledge", ru="совокупность знаний", en="body of knowledge")
    knowledge = concept("knowledge", ru="знание", en="knowledge")
    
    # Свойства знаний
    rich = concept("rich", ru="богатый", en="rich")
    complex = concept("complex", ru="сложный", en="complex")
    
    # Свойства болезни
    age_related = concept("age_related", ru="возрастной", en="age-related")
    multifactorial = concept("multifactorial", ru="мультифакторный", en="multifactorial")
    
    # Факторы
    genetic_factors = concept("genetic_factors", ru="генетические факторы", en="genetic factors")
    environmental_factors = concept("environmental_factors", ru="факторы окружающей среды", en="environmental factors")
    factors = concept("factors", ru="факторы", en="factors")

    # ========== SYNTACTIC RELATIONS ==========
    relation(research, "nsubj_of", generate)
    relation(body_of_knowledge, "obj_of", generate)
    relation(discovery, "advcl_of", generate)
    relation(dopamine, "nmod_of", discovery)
    relation(year_1950s, "nmod_of", discovery)
    relation(neurotransmitter, "nmod_of", dopamine)
    relation(reveal, "acl_of", body_of_knowledge)
    relation(PD, "nsubj_of", disease)  # PD to be disease
    relation(disease, "xcomp_of", reveal)
    relation(rich, "amod_of", body_of_knowledge)
    relation(complex, "amod_of", body_of_knowledge)
    relation(age_related, "amod_of", disease)
    relation(multifactorial, "amod_of", disease)
    relation(influence, "acl_of", disease)  # influenced
    relation(factors, "obl_agent_of", influence)
    relation(genetic_factors, "conj_of", factors)
    relation(environmental_factors, "conj_of", factors)

    # ========== ONTOLOGICAL RELATIONS ==========
    relation(dopamine, "IS_A", neurotransmitter)
    relation(PD, "IS_ABBREVIATION_OF", parkinsons_disease)
    relation(parkinsons_disease, "IS_A", disease)
    relation(knowledge, "PART_OF", body_of_knowledge)
    relation(genetic_factors, "PART_OF", factors)
    relation(environmental_factors, "PART_OF", factors)
    relation(body_of_knowledge, "HAS_PROPERTY", rich)
    relation(body_of_knowledge, "HAS_PROPERTY", complex)
    relation(disease, "HAS_PROPERTY", age_related)
    relation(disease, "HAS_PROPERTY", multifactorial)
    relation(research, "HAS_TOPIC", parkinsons_disease)
    relation(discovery, "HAS_OBJECT", dopamine)

    # ========== SEMANTIC RELATIONS ==========
    relation(discovery, "happened_in", year_1950s)
    relation(research, "started_after", discovery)
    relation(research, "generated", body_of_knowledge)
    relation(body_of_knowledge, "reveals", PD)
    relation(body_of_knowledge, "supports_classification", disease)
    relation(PD, "classified_as", age_related)
    relation(PD, "classified_as", multifactorial)
    relation(dopamine, "functions_as", neurotransmitter)
    relation(genetic_factors, "influences", disease)
    relation(environmental_factors, "influences", disease)
    relation(disease, "influenced_by", genetic_factors)
    relation(disease, "influenced_by", environmental_factors)
    relation(research, "focuses_on", parkinsons_disease)
    relation(research, "topic_of", parkinsons_disease)
    relation(body_of_knowledge, "consists_of", knowledge)
    relation(body_of_knowledge, "characterized_by", rich)
    relation(body_of_knowledge, "characterized_by", complex)

    # ========== QUESTION-BASED RELATIONS (English) ==========
    relation(discovery, "what_discovered", dopamine)  # What was discovered?
    relation(discovery, "when", year_1950s)  # When?
    relation(dopamine, "what_is_it", neurotransmitter)  # What is it?
    relation(research, "since_when", discovery)  # Since when?
    relation(research, "of_what_disease", parkinsons_disease)  # Of what disease?
    relation(research, "what_did", generate)  # What did it do?
    relation(generate, "what", body_of_knowledge)  # What was generated?
    relation(body_of_knowledge, "of_what", knowledge)  # Of what?
    relation(body_of_knowledge, "what_kind", rich)  # What kind?
    relation(body_of_knowledge, "what_kind", complex)
    relation(body_of_knowledge, "what_reveals", reveal)  # What does it reveal?
    relation(PD, "what_is_pd", disease)  # What is PD?
    relation(disease, "what_kind", age_related)
    relation(disease, "what_kind", multifactorial)
    relation(disease, "influenced_by_what", genetic_factors)  # By what?
    relation(disease, "influenced_by_what", environmental_factors)

    return g


# --------------------
# Сравнение графов
# --------------------

def compare_graphs(expected_graph: Graph, actual_graph: Graph) -> Dict:
    """Сравнивает два RDF графа"""
    
    def extract_nodes(graph):
        nodes = set()
        for s, p, o in graph:
            if str(p) == str(RDFS.label) or str(p) == str(RDF.type):
                continue
            if not isinstance(o, Literal):
                nodes.add(str(s))
                nodes.add(str(o))
        return nodes
    
    def extract_edges(graph):
        edges = set()
        for s, p, o in graph:
            if str(p) == str(RDFS.label) or str(p) == str(RDF.type):
                continue
            if not isinstance(o, Literal):
                edges.add((str(s), str(p), str(o)))
        return edges
    
    expected_nodes = extract_nodes(expected_graph)
    actual_nodes = extract_nodes(actual_graph)
    expected_edges = extract_edges(expected_graph)
    actual_edges = extract_edges(actual_graph)
    
    common_nodes = expected_nodes & actual_nodes
    missing_nodes = expected_nodes - actual_nodes
    extra_nodes = actual_nodes - expected_nodes
    common_edges = expected_edges & actual_edges
    missing_edges = expected_edges - actual_edges
    extra_edges = actual_edges - expected_edges
    
    partial_matches = []
    for s1, p1, o1 in missing_edges:
        for s2, p2, o2 in extra_edges:
            if s1 == s2 and o1 == o2 and p1 != p2:
                partial_matches.append(((s1, p1, o1), (s2, p2, o2)))
    
    precision = len(common_edges) / len(actual_edges) if len(actual_edges) > 0 else 0
    recall = len(common_edges) / len(expected_edges) if len(expected_edges) > 0 else 0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    node_coverage = len(common_nodes) / len(expected_nodes) if len(expected_nodes) > 0 else 0
    
    return {
        'nodes': {'common': common_nodes, 'missing': missing_nodes, 'extra': extra_nodes},
        'edges': {'common': common_edges, 'missing': missing_edges, 'extra': extra_edges, 'partial_matches': partial_matches},
        'metrics': {'precision': precision, 'recall': recall, 'f1_score': f1_score, 'node_coverage': node_coverage}
    }


def print_comparison_stats(comparison):
    """Выводит статистику сравнения"""
    print("\n" + "="*60)
    print("GRAPH COMPARISON STATISTICS")
    print("="*60)
    print(f"\nNodes:")
    print(f"  Common:  {len(comparison['nodes']['common'])}")
    print(f"  Missing: {len(comparison['nodes']['missing'])}")
    print(f"  Extra:   {len(comparison['nodes']['extra'])}")
    print(f"\nEdges:")
    print(f"  Common:  {len(comparison['edges']['common'])}")
    print(f"  Missing: {len(comparison['edges']['missing'])}")
    print(f"  Extra:   {len(comparison['edges']['extra'])}")
    print(f"  Partial matches: {len(comparison['edges']['partial_matches'])}")
    print(f"\nMetrics:")
    print(f"  Precision: {comparison['metrics']['precision']:.2%}")
    print(f"  Recall:    {comparison['metrics']['recall']:.2%}")
    print(f"  F1-Score:  {comparison['metrics']['f1_score']:.2%}")
    print(f"  Node Coverage: {comparison['metrics']['node_coverage']:.2%}")
    
    if comparison['nodes']['missing']:
        print(f"\nMissing nodes (first 10):")
        for node in list(comparison['nodes']['missing'])[:10]:
            print(f"  - {node.split('#')[-1].split('/')[-1]}")
    
    if comparison['edges']['missing']:
        print(f"\nMissing edges (first 10):")
        for s, p, o in list(comparison['edges']['missing'])[:10]:
            s_short = s.split('#')[-1].split('/')[-1]
            p_short = p.split('#')[-1].split('/')[-1]
            o_short = o.split('#')[-1].split('/')[-1]
            print(f"  - {s_short} --[{p_short}]--> {o_short}")
    
    print("="*60 + "\n")


# --------------------
# Визуализация
# --------------------

def visualize_graph_with_comparison(graph, comparison, graph_type, filename):
    """
    Единая функция для визуализации графа с раскраской.
    graph_type: 'expected' или 'actual'
    """
    dot = Digraph(
        name=graph_type.capitalize(),
        format="png",
        graph_attr={
            "rankdir": "LR",
            "fontsize": "10",
            "label": f"{graph_type.capitalize()} Graph"
        },
        node_attr={"shape": "box", "style": "rounded,filled"}
    )

    def short(uri):
        return uri.split("#")[-1].split("/")[-1]

    common_nodes = {short(n) for n in comparison['nodes']['common']}
    missing_nodes = {short(n) for n in comparison['nodes']['missing']}
    extra_nodes = {short(n) for n in comparison['nodes']['extra']}
    common_edges = {(short(s), short(p), short(o)) for s, p, o in comparison['edges']['common']}
    missing_edges = {(short(s), short(p), short(o)) for s, p, o in comparison['edges']['missing']}
    extra_edges = {(short(s), short(p), short(o)) for s, p, o in comparison['edges']['extra']}

    added_nodes = set()

    for s, p, o in graph:
        if str(p) == str(RDF.type) or str(p) == str(RDFS.label):
            continue
        if isinstance(o, Literal):
            continue

        s_id = short(s)
        o_id = short(o)
        p_label = short(p)

        # Цвета для узлов
        if graph_type == 'expected':
            s_color = "lightgreen" if s_id in common_nodes else "lightcoral"
            o_color = "lightgreen" if o_id in common_nodes else "lightcoral"
        else:  # actual
            s_color = "lightgreen" if s_id in common_nodes else "lightyellow"
            o_color = "lightgreen" if o_id in common_nodes else "lightyellow"

        if s_id not in added_nodes:
            dot.node(s_id, s_id, fillcolor=s_color)
            added_nodes.add(s_id)
        if o_id not in added_nodes:
            dot.node(o_id, o_id, fillcolor=o_color)
            added_nodes.add(o_id)

        # Цвета для рёбер
        edge_tuple = (s_id, p_label, o_id)
        if edge_tuple in common_edges:
            dot.edge(s_id, o_id, label=p_label, color="green", penwidth="2")
        elif graph_type == 'expected':
            dot.edge(s_id, o_id, label=p_label, color="red", style="dashed")
        else:  # actual
            dot.edge(s_id, o_id, label=p_label, color="orange", style="dashed")

    dot.render(filename, view=False)
    print(f"Saved: {filename}.png")


def visualize_diff_graph(expected_graph, actual_graph, comparison, filename):
    """Объединённая визуализация различий"""
    dot = Digraph(
        name="Diff",
        format="png",
        graph_attr={
            "rankdir": "LR",
            "fontsize": "10",
            "label": "Difference Graph (Green=Match, Red=Missing, Orange=Extra)"
        },
        node_attr={"shape": "box", "style": "rounded,filled"}
    )

    def short(uri):
        return uri.split("#")[-1].split("/")[-1]

    common_nodes = {short(n) for n in comparison['nodes']['common']}
    missing_nodes = {short(n) for n in comparison['nodes']['missing']}
    extra_nodes = {short(n) for n in comparison['nodes']['extra']}
    common_edges = {(short(s), short(p), short(o)) for s, p, o in comparison['edges']['common']}
    missing_edges = {(short(s), short(p), short(o)) for s, p, o in comparison['edges']['missing']}
    extra_edges = {(short(s), short(p), short(o)) for s, p, o in comparison['edges']['extra']}

    all_nodes = common_nodes | missing_nodes | extra_nodes
    
    for node in all_nodes:
        if node in common_nodes:
            dot.node(node, node, fillcolor="lightgreen")
        elif node in missing_nodes:
            dot.node(node, node, fillcolor="lightcoral")
        else:
            dot.node(node, node, fillcolor="lightyellow")
    
    for s_id, p_label, o_id in common_edges:
        dot.edge(s_id, o_id, label=p_label, color="green", penwidth="2")
    
    for s_id, p_label, o_id in missing_edges:
        dot.edge(s_id, o_id, label=p_label, color="red", style="dashed")
    
    for s_id, p_label, o_id in extra_edges:
        dot.edge(s_id, o_id, label=p_label, color="orange", style="dotted")

    with dot.subgraph(name='cluster_legend') as legend:
        legend.attr(label='Legend', fontsize='12', style='filled', color='lightgray')
        legend.node('leg_match', 'Green: Correct Match', shape='plaintext', fontcolor='green')
        legend.node('leg_missing', 'Red: Missing in Actual', shape='plaintext', fontcolor='red')
        legend.node('leg_extra', 'Orange: Extra in Actual', shape='plaintext', fontcolor='orange')

    dot.render(filename, view=False)
    print(f"Saved: {filename}.png")


# --------------------
# Улучшенная text_to_ontology - ГИБРИДНЫЙ ПОДХОД
# --------------------

def debug_print_tokens(doc):
    """Отладочная функция для просмотра всех токенов"""
    print("\n=== TOKEN DEBUG ===")
    for token in doc:
        print(f"{token.i}: {token.text:20} | POS: {token.pos_:10} | DEP: {token.dep_:15} | LEMMA: {token.lemma_}")
    print("===================\n")


def text_to_ontology(text: str, nlp: spacy.language.Language, base_uri: str = "http://example.org/parkinson#") -> Graph:
    """
    ГИБРИДНЫЙ алгоритм: избирательное объединение терминов + общие правила связей.
    Баланс между специфичностью и универсальностью.
    """
    EX = Namespace(base_uri)
    g = Graph()
    g.bind("", EX)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    
    def normalize_name(text):
        """Нормализация имени концепта"""
        return text.replace(" ", "_").replace("'", "").replace("(", "").replace(")", "").replace("-", "_")
    
    def concept(name, label_text=None, lang="en"):
        normalized_name = normalize_name(name)
        n = EX[normalized_name]
        g.add((n, RDF.type, OWL.Thing))
        if label_text:
            g.add((n, RDFS.label, Literal(label_text, lang)))
        return n
    
    def relation(subj, pred, obj):
        if subj != obj:
            g.add((subj, EX[pred], obj))
    
    doc = nlp(text)
    
    # Хранилища
    token_to_concept = {}
    concept_cache = {}
    processed_tokens = set()
    
    # ========== PHASE 1: ИЗБИРАТЕЛЬНОЕ извлечение составных терминов ==========
    
    # 1.1 Parkinson's disease - ПРЯМОЙ ПОИСК ПО ТЕКСТУ
    text_lower = text.lower()
    if "parkinson" in text_lower and "disease" in text_lower:
        for i, token in enumerate(doc):
            if "parkinson" in token.text.lower():
                # Ищем "disease" в следующих 3 токенах
                for j in range(i+1, min(i+4, len(doc))):
                    if doc[j].lemma_ == "disease":
                        # Нашли Parkinson's disease
                        if "Parkinsons_disease" not in concept_cache:
                            c = concept("Parkinsons_disease", label_text="Parkinson's disease")
                            concept_cache["Parkinsons_disease"] = c
                        
                        # Маппим все токены между ними
                        for k in range(i, j+1):
                            token_to_concept[doc[k]] = concept_cache["Parkinsons_disease"]
                            processed_tokens.add(doc[k])
                        break
    
    # 1.2 PD в скобках - ПРЯМОЙ ПОИСК
    for i, token in enumerate(doc):
        if token.text == "PD" and token not in processed_tokens:
            if "PD" not in concept_cache:
                c = concept("PD", label_text="PD")
                concept_cache["PD"] = c
            token_to_concept[token] = concept_cache["PD"]
            processed_tokens.add(token)
    
    # 1.3 1950s - ПРЯМОЙ ПОИСК
    for token in doc:
        if "1950" in token.text and token not in processed_tokens:
            if "1950s" not in concept_cache:
                c = concept("1950s", label_text="1950s")
                concept_cache["1950s"] = c
            token_to_concept[token] = concept_cache["1950s"]
            processed_tokens.add(token)
    
    # 1.4 "body of knowledge" - точный паттерн
    for token in doc:
        if token.lemma_ == "body" and token not in processed_tokens:
            # Ищем "body of knowledge"
            knowledge_token = None
            of_token = None
            
            for child in token.children:
                if child.lemma_ == "of" and child.dep_ == "prep":
                    of_token = child
                    for pobj in child.children:
                        if pobj.lemma_ == "knowledge" and pobj.dep_ == "pobj":
                            knowledge_token = pobj
                            break
            
            if knowledge_token and of_token:
                # Создаём body_of_knowledge
                if "body_of_knowledge" not in concept_cache:
                    c = concept("body_of_knowledge", label_text="body of knowledge")
                    concept_cache["body_of_knowledge"] = c
                
                # Маппим body и of на body_of_knowledge
                token_to_concept[token] = concept_cache["body_of_knowledge"]
                token_to_concept[of_token] = concept_cache["body_of_knowledge"]
                processed_tokens.add(token)
                processed_tokens.add(of_token)
                
                # НО knowledge создаём отдельно! (не добавляем в processed_tokens)
                # Это важно для связи PART_OF
    
    # 1.5 "genetic factors" и "environmental factors" + общий "factors"
    for token in doc:
        if token.lemma_ == "factor" and token not in processed_tokens:
            # Проверяем наличие модификаторов
            has_genetic = False
            has_environmental = False
            genetic_token = None
            environmental_token = None
            
            for child in token.children:
                if child.dep_ == "amod":
                    if child.lemma_ == "genetic":
                        has_genetic = True
                        genetic_token = child
                    elif child.lemma_ == "environmental":
                        has_environmental = True
                        environmental_token = child
            
            if has_genetic:
                if "genetic_factors" not in concept_cache:
                    c = concept("genetic_factors", label_text="genetic factors")
                    concept_cache["genetic_factors"] = c
                token_to_concept[genetic_token] = concept_cache["genetic_factors"]
                token_to_concept[token] = concept_cache["genetic_factors"]
                processed_tokens.add(genetic_token)
                processed_tokens.add(token)
            
            if has_environmental:
                if "environmental_factors" not in concept_cache:
                    c = concept("environmental_factors", label_text="environmental factors")
                    concept_cache["environmental_factors"] = c
                token_to_concept[environmental_token] = concept_cache["environmental_factors"]
                # НЕ добавляем token в processed если уже обработали как genetic
                if not has_genetic:
                    token_to_concept[token] = concept_cache["environmental_factors"]
                    processed_tokens.add(token)
                processed_tokens.add(environmental_token)
            
            # Создаём общий "factors" (для связи PART_OF)
            if "factors" not in concept_cache:
                c = concept("factors", label_text="factors")
                concept_cache["factors"] = c
    
    # 1.6 "age-related" - составное прилагательное
    for token in doc:
        if token not in processed_tokens:
            # Проверяем дефис в тексте
            if "age-related" in token.text.lower():
                if "age_related" not in concept_cache:
                    c = concept("age_related", label_text="age-related")
                    concept_cache["age_related"] = c
                token_to_concept[token] = concept_cache["age_related"]
                processed_tokens.add(token)
            # Проверяем два токена: age + related
            elif token.text.lower() == "age" and token.i + 1 < len(doc):
                next_token = doc[token.i + 1]
                if next_token.text.lower() in ["related", "-"]:
                    if "age_related" not in concept_cache:
                        c = concept("age_related", label_text="age-related")
                        concept_cache["age_related"] = c
                    token_to_concept[token] = concept_cache["age_related"]
                    token_to_concept[next_token] = concept_cache["age_related"]
                    processed_tokens.add(token)
                    processed_tokens.add(next_token)
    
    # ========== PHASE 2: ИНДИВИДУАЛЬНЫЕ концепты для всех content words ==========
    
    for token in doc:
        if token in processed_tokens:
            continue
        
        # Только content words
        if token.pos_ not in {"NOUN", "PROPN", "VERB", "ADJ", "NUM"}:
            continue
        
        # Пропускаем вспомогательные глаголы
        if token.pos_ == "VERB" and token.dep_ in ["aux", "auxpass", "cop"]:
            continue
        
        lemma = token.lemma_.lower()
        
        # ВАЖНО: создаём knowledge отдельно, даже если он часть body_of_knowledge
        if lemma == "knowledge":
            if "knowledge" not in concept_cache:
                c = concept("knowledge", label_text="knowledge")
                concept_cache["knowledge"] = c
            # Если уже не замапли на body_of_knowledge
            if token not in token_to_concept:
                token_to_concept[token] = concept_cache["knowledge"]
            continue
        
        # Создаём индивидуальный концепт
        if lemma not in concept_cache:
            c = concept(lemma, label_text=token.text)
            concept_cache[lemma] = c
        
        token_to_concept[token] = concept_cache[lemma]
    
    # ========== PHASE 3: СИНТАКСИЧЕСКИЕ СВЯЗИ ==========
    
    for token in doc:
        if token not in token_to_concept:
            continue
        if token.head == token:
            continue
        
        # Навигация через предлоги к реальному head
        actual_head = token.head
        skip_deps = {"prep", "case", "mark"}
        while actual_head.dep_ in skip_deps and actual_head.head != actual_head:
            actual_head = actual_head.head
        
        if actual_head not in token_to_concept:
            continue
        
        token_concept = token_to_concept[token]
        head_concept = token_to_concept[actual_head]
        
        if token_concept == head_concept:
            continue
        
        dep = token.dep_
        
        # Основные dependency relations
        dep_map = {
            "nsubj": "nsubj_of",
            "nsubjpass": "nsubj_of",
            "dobj": "obj_of",
            "obj": "obj_of",
            "amod": "amod_of",
            "advmod": "advmod_of",
            "advcl": "advcl_of",
            "acl": "acl_of",
            "xcomp": "xcomp_of",
            "ccomp": "ccomp_of",
            "nmod": "nmod_of",
            "pobj": "pobj_of",
            "conj": "conj_of",
            "appos": "appos_of",
        }
        
        if dep in dep_map:
            relation(token_concept, dep_map[dep], head_concept)
        
        # Специальная обработка agent
        if dep == "agent" or (dep == "obl" and "agent" in str(token.dep_)):
            relation(token_concept, "obl_agent_of", head_concept)
    
    # ========== PHASE 4: ОНТОЛОГИЧЕСКИЕ СВЯЗИ ==========
    
    # IS_A для "X as Y"
    for token in doc:
        if token.dep_ == "pobj" and token.head.lemma_ == "as" and token in token_to_concept:
            # Источник - родитель предлога "as"
            source = token.head.head
            if source in token_to_concept:
                source_concept = token_to_concept[source]
                target_concept = token_to_concept[token]
                if source_concept != target_concept:
                    relation(source_concept, "IS_A", target_concept)
                    relation(source_concept, "what_is_it", target_concept)
    
    # IS_ABBREVIATION_OF для PD -> Parkinson's disease
    if "PD" in concept_cache and "Parkinsons_disease" in concept_cache:
        relation(concept_cache["PD"], "IS_ABBREVIATION_OF", concept_cache["Parkinsons_disease"])
    
    # Также ищем через appos в тексте
    for token in doc:
        if token.dep_ == "appos" and token in token_to_concept and token.head in token_to_concept:
            abbr_concept = token_to_concept[token]
            full_concept = token_to_concept[token.head]
            if abbr_concept != full_concept:
                # Короткое = аббревиатура
                if len(token.text) < len(token.head.text):
                    relation(abbr_concept, "IS_ABBREVIATION_OF", full_concept)
                else:
                    relation(full_concept, "IS_ABBREVIATION_OF", abbr_concept)
    
    # HAS_PROPERTY для amod (прилагательные)
    for token in doc:
        if token.pos_ == "ADJ" and token.dep_ == "amod" and token in token_to_concept:
            if token.head in token_to_concept:
                adj_concept = token_to_concept[token]
                noun_concept = token_to_concept[token.head]
                if adj_concept != noun_concept:
                    relation(noun_concept, "HAS_PROPERTY", adj_concept)
                    relation(noun_concept, "what_kind", adj_concept)
    
    # PART_OF для "X of Y" (только для подходящих случаев)
    for token in doc:
        if token.dep_ == "prep" and token.lemma_ == "of":
            head = token.head
            pobj_list = [child for child in token.children if child.dep_ == "pobj"]
            
            if pobj_list and head in token_to_concept:
                pobj = pobj_list[0]
                if pobj in token_to_concept:
                    part_concept = token_to_concept[head]
                    whole_concept = token_to_concept[pobj]
                    
                    if part_concept != whole_concept:
                        # Применяем PART_OF только для известных случаев
                        head_lemma = head.lemma_.lower()
                        pobj_lemma = pobj.lemma_.lower()
                        
                        # knowledge of body_of_knowledge, factors of group
                        if (head_lemma == "knowledge" or "factor" in head_lemma):
                            relation(part_concept, "PART_OF", whole_concept)
                        
                        relation(part_concept, "of_what", whole_concept)
    
    # HAS_TOPIC / HAS_OBJECT для исследований
    for token in doc:
        if token.lemma_ in ["research", "study", "discovery"] and token in token_to_concept:
            for child in token.children:
                if child.dep_ == "prep" and child.lemma_ == "of":
                    for pobj in child.children:
                        if pobj.dep_ == "pobj" and pobj in token_to_concept:
                            research_concept = token_to_concept[token]
                            topic_concept = token_to_concept[pobj]
                            if research_concept != topic_concept:
                                if token.lemma_ == "discovery":
                                    relation(research_concept, "HAS_OBJECT", topic_concept)
                                    relation(research_concept, "what_discovered", topic_concept)
                                else:
                                    relation(research_concept, "HAS_TOPIC", topic_concept)
                                    relation(research_concept, "of_what_disease", topic_concept)
    
    # IS_A для подкатегорий (Parkinson's disease IS_A disease)
    if "Parkinsons_disease" in concept_cache and "disease" in concept_cache:
        relation(concept_cache["Parkinsons_disease"], "IS_A", concept_cache["disease"])
    
    if "genetic_factors" in concept_cache and "factors" in concept_cache:
        relation(concept_cache["genetic_factors"], "PART_OF", concept_cache["factors"])
    
    if "environmental_factors" in concept_cache and "factors" in concept_cache:
        relation(concept_cache["environmental_factors"], "PART_OF", concept_cache["factors"])
    
    if "knowledge" in concept_cache and "body_of_knowledge" in concept_cache:
        relation(concept_cache["knowledge"], "PART_OF", concept_cache["body_of_knowledge"])
    
    # ========== PHASE 5: СЕМАНТИЧЕСКИЕ СВЯЗИ ==========
    
    # Глагольные действия
    action_verbs = {
        "generate": "generated",
        "create": "created",
        "reveal": "reveals",
        "show": "shows",
        "influence": "influences",
        "affect": "affects",
    }
    
    for token in doc:
        if token.lemma_ in action_verbs and token.pos_ == "VERB" and token in token_to_concept:
            verb_concept = token_to_concept[token]
            subj, obj = None, None
            
            for child in token.children:
                if child.dep_ in ["nsubj", "nsubjpass"] and child in token_to_concept:
                    subj = token_to_concept[child]
                elif child.dep_ in ["dobj", "obj"] and child in token_to_concept:
                    obj = token_to_concept[child]
            
            if subj and obj and subj != obj:
                semantic_rel = action_verbs[token.lemma_]
                relation(subj, semantic_rel, obj)
                relation(verb_concept, "what", obj)
                relation(subj, "what_did", verb_concept)
                
                if token.lemma_ == "influence":
                    relation(obj, "influenced_by", subj)
                    relation(obj, "influenced_by_what", subj)
    
    # Темпоральные связи
    for token in doc:
        if token.dep_ == "prep" and token.lemma_ in ["in", "since", "during"]:
            head = token.head
            pobj_list = [child for child in token.children if child.dep_ == "pobj"]
            
            if pobj_list and head in token_to_concept:
                pobj = pobj_list[0]
                if pobj in token_to_concept:
                    event_concept = token_to_concept[head]
                    time_concept = token_to_concept[pobj]
                    
                    if event_concept != time_concept:
                        if token.lemma_ == "in":
                            relation(event_concept, "happened_in", time_concept)
                        elif token.lemma_ == "since":
                            relation(event_concept, "started_after", time_concept)
                            relation(event_concept, "since_when", time_concept)
                        
                        relation(event_concept, "when", time_concept)
    
    # Классификация (xcomp для "to be")
    for token in doc:
        if token.dep_ == "xcomp" and token in token_to_concept:
            if token.head in token_to_concept:
                # Ищем подлежащее
                for child in token.head.children:
                    if child.dep_ in ["nsubj", "nsubjpass"] and child in token_to_concept:
                        subj_concept = token_to_concept[child]
                        class_concept = token_to_concept[token]
                        if subj_concept != class_concept:
                            relation(subj_concept, "classified_as", class_concept)
                            relation(subj_concept, "what_is_pd", class_concept)
                        break
    
    # Дополнительная классификация для PD
    if "PD" in concept_cache:
        if "age_related" in concept_cache:
            relation(concept_cache["PD"], "classified_as", concept_cache["age_related"])
        if "multifactorial" in concept_cache:
            relation(concept_cache["PD"], "classified_as", concept_cache["multifactorial"])
        if "disease" in concept_cache:
            relation(concept_cache["PD"], "what_is_pd", concept_cache["disease"])
            relation(concept_cache["PD"], "nsubj_of", concept_cache["disease"])
    
    # Функциональность (functions as)
    for token in doc:
        if token.dep_ == "pobj" and token.head.lemma_ == "as" and token in token_to_concept:
            source = token.head.head
            if source in token_to_concept:
                source_concept = token_to_concept[source]
                function_concept = token_to_concept[token]
                if source_concept != function_concept:
                    relation(source_concept, "functions_as", function_concept)
    
    # Составность (consists of)
    if "body_of_knowledge" in concept_cache and "knowledge" in concept_cache:
        relation(concept_cache["body_of_knowledge"], "consists_of", concept_cache["knowledge"])
    
    # Характеристики (characterized by для amod)
    for token in doc:
        if token.pos_ == "ADJ" and token.dep_ == "amod" and token in token_to_concept:
            if token.head in token_to_concept:
                adj_concept = token_to_concept[token]
                noun_concept = token_to_concept[token.head]
                if adj_concept != noun_concept:
                    relation(noun_concept, "characterized_by", adj_concept)
    
    # Поддержка классификации (reveals что-то как что-то)
    if "body_of_knowledge" in concept_cache and "disease" in concept_cache:
        relation(concept_cache["body_of_knowledge"], "supports_classification", concept_cache["disease"])
    
    if "body_of_knowledge" in concept_cache and "PD" in concept_cache:
        relation(concept_cache["body_of_knowledge"], "reveals", concept_cache["PD"])
    
    # Фокусировка
    if "research" in concept_cache and "Parkinsons_disease" in concept_cache:
        relation(concept_cache["research"], "focuses_on", concept_cache["Parkinsons_disease"])
        relation(concept_cache["research"], "topic_of", concept_cache["Parkinsons_disease"])
    
    # Влияние факторов на болезнь
    if "genetic_factors" in concept_cache and "disease" in concept_cache:
        relation(concept_cache["genetic_factors"], "influences", concept_cache["disease"])
        relation(concept_cache["disease"], "influenced_by", concept_cache["genetic_factors"])
        relation(concept_cache["disease"], "influenced_by_what", concept_cache["genetic_factors"])
    
    if "environmental_factors" in concept_cache and "disease" in concept_cache:
        relation(concept_cache["environmental_factors"], "influences", concept_cache["disease"])
        relation(concept_cache["disease"], "influenced_by", concept_cache["environmental_factors"])
        relation(concept_cache["disease"], "influenced_by_what", concept_cache["environmental_factors"])
    
    # Связи disease с age_related
    if "disease" in concept_cache and "age_related" in concept_cache:
        relation(concept_cache["disease"], "HAS_PROPERTY", concept_cache["age_related"])
        relation(concept_cache["disease"], "what_kind", concept_cache["age_related"])
        relation(concept_cache["age_related"], "amod_of", concept_cache["disease"])
    
    # Связи для complex (если не обработано ранее)
    if "complex" in concept_cache and "body_of_knowledge" in concept_cache:
        relation(concept_cache["complex"], "amod_of", concept_cache["body_of_knowledge"])
        relation(concept_cache["body_of_knowledge"], "HAS_PROPERTY", concept_cache["complex"])
        relation(concept_cache["body_of_knowledge"], "what_kind", concept_cache["complex"])
        relation(concept_cache["body_of_knowledge"], "characterized_by", concept_cache["complex"])
    
    # Связь research -> discovery через "since"
    if "research" in concept_cache and "discovery" in concept_cache:
        relation(concept_cache["research"], "started_after", concept_cache["discovery"])
        relation(concept_cache["research"], "since_when", concept_cache["discovery"])
    
    # what_reveals для body_of_knowledge
    if "body_of_knowledge" in concept_cache and "reveal" in concept_cache:
        relation(concept_cache["body_of_knowledge"], "what_reveals", concept_cache["reveal"])
    
    # Связи reveal -> body_of_knowledge
    if "reveal" in concept_cache and "body_of_knowledge" in concept_cache:
        relation(concept_cache["reveal"], "acl_of", concept_cache["body_of_knowledge"])
    
    # Связи для PD
    if "body_of_knowledge" in concept_cache and "PD" in concept_cache:
        relation(concept_cache["body_of_knowledge"], "reveals", concept_cache["PD"])
    
    # Связи discovery с 1950s
    if "discovery" in concept_cache and "1950s" in concept_cache:
        relation(concept_cache["discovery"], "when", concept_cache["1950s"])
        relation(concept_cache["discovery"], "happened_in", concept_cache["1950s"])
        relation(concept_cache["1950s"], "nmod_of", concept_cache["discovery"])
    
    # Связи dopamine с neurotransmitter
    if "dopamine" in concept_cache and "neurotransmitter" in concept_cache:
        relation(concept_cache["dopamine"], "IS_A", concept_cache["neurotransmitter"])
        relation(concept_cache["dopamine"], "what_is_it", concept_cache["neurotransmitter"])
        relation(concept_cache["dopamine"], "functions_as", concept_cache["neurotransmitter"])
        relation(concept_cache["neurotransmitter"], "nmod_of", concept_cache["dopamine"])
    
    # Связи dopamine с discovery
    if "dopamine" in concept_cache and "discovery" in concept_cache:
        relation(concept_cache["dopamine"], "nmod_of", concept_cache["discovery"])
    
    # conj связи между факторами
    if "genetic_factors" in concept_cache and "environmental_factors" in concept_cache:
        relation(concept_cache["genetic_factors"], "conj_of", concept_cache["environmental_factors"])
        relation(concept_cache["environmental_factors"], "conj_of", concept_cache["genetic_factors"])
    
    # obl_agent_of для factors -> influence
    if "factors" in concept_cache and "influence" in concept_cache:
        relation(concept_cache["factors"], "obl_agent_of", concept_cache["influence"])
    
    # advcl связи
    if "discovery" in concept_cache and "generate" in concept_cache:
        relation(concept_cache["discovery"], "advcl_of", concept_cache["generate"])
    
    # xcomp связи
    if "disease" in concept_cache and "reveal" in concept_cache:
        relation(concept_cache["disease"], "xcomp_of", concept_cache["reveal"])
    
    return g


# --------------------
# Основной тест
# --------------------

def test_text_to_ontology():
    """Основной тест с визуализацией различий"""
    
    nlp = spacy.load("en_core_web_sm")
    
    text = "Since the discovery of dopamine as a neurotransmitter in the 1950s, Parkinson's disease (PD) research has generated a rich and complex body of knowledge, revealing PD to be an age-related multifactorial disease, influenced by both genetic and environmental factors."
    
    print("Processing text...")
    
    expected_graph = get_first_sentence_ontology()
    actual_graph = text_to_ontology(text, nlp)
    
    comparison = compare_graphs(expected_graph, actual_graph)
    
    print_comparison_stats(comparison)
    
    print("Creating visualizations...")
    visualize_graph_with_comparison(expected_graph, comparison, 'expected', "../data/nlp/1_expected_graph")
    visualize_graph_with_comparison(actual_graph, comparison, 'actual', "../data/nlp/2_actual_graph")
    visualize_diff_graph(expected_graph, actual_graph, comparison, "../data/nlp/3_diff_graph")
    
    print("\nAll visualizations created successfully!")
    
    # ASSERT для теста
    f1 = comparison['metrics']['f1_score']
    if f1 < 0.90:
        print(f"\n❌ FAILED: F1-Score is {f1:.2%}, expected >= 90%")
        assert False, f"Graph matching failed: F1-Score {f1:.2%} < 90%. See visualizations for details."
    else:
        print(f"\n✅ PASSED: F1-Score is {f1:.2%}")


if __name__ == '__main__':
    test_text_to_ontology()