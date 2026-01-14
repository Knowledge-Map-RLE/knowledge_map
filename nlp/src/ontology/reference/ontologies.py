"""
ФИНАЛЬНЫЕ эталонные RDF онтологии (оптимизированные, без избыточности)
Версия: 2025-01-11 - Полностью синхронизирована с OntologyBuilder
"""

from rdflib import Graph, Namespace, Literal
from rdflib.namespace import RDF, RDFS, OWL


def get_first_sentence_ontology():
    """Эталонная онтология для первого предложения"""
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

    # Concepts
    discovery = concept("discovery")
    generate = concept("generate")
    reveal = concept("reveal")
    influence = concept("influence")
    dopamine = concept("dopamine")
    neurotransmitter = concept("neurotransmitter")
    year_1950s = concept("1950s")
    parkinsons_disease = concept("Parkinsons_disease")
    PD = concept("PD")
    disease = concept("disease")
    research = concept("research")
    body_of_knowledge = concept("body_of_knowledge")
    knowledge = concept("knowledge")
    rich = concept("rich")
    complex = concept("complex")
    age_related = concept("age_related")
    multifactorial = concept("multifactorial")
    genetic_factors = concept("genetic_factors")
    environmental_factors = concept("environmental_factors")
    factors = concept("factors")

    # Syntactic relations
    relation(research, "nsubj_of", generate)
    relation(body_of_knowledge, "obj_of", generate)
    relation(discovery, "advcl_of", generate)
    relation(dopamine, "nmod_of", discovery)
    relation(year_1950s, "nmod_of", discovery)
    relation(neurotransmitter, "nmod_of", dopamine)
    relation(reveal, "acl_of", body_of_knowledge)
    relation(PD, "nsubj_of", disease)
    relation(disease, "xcomp_of", reveal)
    relation(rich, "amod_of", body_of_knowledge)
    relation(complex, "amod_of", body_of_knowledge)
    relation(age_related, "amod_of", disease)
    relation(multifactorial, "amod_of", disease)
    relation(influence, "acl_of", disease)
    relation(factors, "obl_agent_of", influence)
    relation(genetic_factors, "conj_of", environmental_factors)

    # Ontological relations
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

    # Semantic relations
    relation(discovery, "happened_in", year_1950s)
    relation(research, "started_after", discovery)
    relation(research, "generated", body_of_knowledge)
    relation(body_of_knowledge, "reveals", PD)
    relation(body_of_knowledge, "supports_classification", disease)
    relation(PD, "classified_as", age_related)
    relation(PD, "classified_as", multifactorial)
    relation(body_of_knowledge, "consists_of", knowledge)
    relation(genetic_factors, "influences", disease)
    relation(environmental_factors, "influences", disease)
    relation(disease, "influenced_by", genetic_factors)
    relation(disease, "influenced_by", environmental_factors)
    relation(research, "focuses_on", parkinsons_disease)
    relation(discovery, "HAS_OBJECT", dopamine)

    return g


def get_second_sentence_ontology():
    """Эталонная онтология для второго предложения"""
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

    # Concepts
    complexity = concept("complexity")
    disease = concept("disease")
    progression = concept("progression")
    pathogenesis = concept("pathogenesis")
    systems = concept("systems")
    increase = concept("increase")
    tremendous = concept("tremendous")
    nonlinear = concept("nonlinear")
    molecular = concept("molecular")
    cellular = concept("cellular")
    organic = concept("organic")

    # Syntactic relations
    relation(complexity, "nsubjpass_of", increase)
    relation(tremendous, "amod_of", complexity)
    relation(disease, "nmod_of", complexity)
    relation(progression, "obl_agent_of", increase)
    relation(nonlinear, "amod_of", progression)
    relation(pathogenesis, "nmod_of", progression)
    relation(systems, "nmod_of", progression)
    relation(molecular, "amod_of", systems)
    relation(cellular, "amod_of", systems)
    relation(organic, "amod_of", systems)
    relation(molecular, "conj_of", cellular)
    relation(cellular, "conj_of", organic)

    # Ontological relations
    relation(complexity, "HAS_PROPERTY", tremendous)
    relation(complexity, "PART_OF", disease)
    relation(progression, "HAS_PROPERTY", nonlinear)
    relation(progression, "PART_OF", pathogenesis)
    relation(systems, "HAS_PROPERTY", molecular)
    relation(systems, "HAS_PROPERTY", cellular)
    relation(systems, "HAS_PROPERTY", organic)
    relation(pathogenesis, "PART_OF", disease)

    # Semantic relations
    relation(complexity, "increased_by", progression)
    relation(progression, "happens_between", systems)
    relation(pathogenesis, "progresses_through", systems)
    relation(disease, "has_complexity", complexity)

    return g


def get_third_sentence_ontology():
    """
    Эталонная онтология для третьего предложения
    ВАЖНО: Использует systems_based как составной термин!
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

    # Concepts
    minireview = concept("minireview")
    we = concept("we")
    explore = concept("explore")
    propose = concept("propose")
    complexity = concept("complexity")
    PD = concept("PD")
    approach = concept("approach")
    systems_based = concept("systems_based")  # Составной термин!
    organize = concept("organize")
    information = concept("information")
    available = concept("available")
    cellular = concept("cellular")
    disease = concept("disease")
    hallmark = concept("hallmark")

    # Syntactic relations
    relation(we, "nsubj_of", explore)
    relation(complexity, "obj_of", explore)
    relation(approach, "obj_of", propose)
    relation(systems_based, "amod_of", approach)  # systems_based модифицирует approach
    relation(organize, "advcl_of", propose)
    relation(information, "obj_of", organize)
    relation(available, "amod_of", information)
    relation(cellular, "amod_of", hallmark)
    relation(disease, "compound_of", hallmark)
    relation(explore, "conj_of", propose)

    # Ontological relations
    relation(complexity, "PART_OF", PD)
    relation(approach, "HAS_PROPERTY", systems_based)
    relation(information, "HAS_PROPERTY", available)
    relation(hallmark, "HAS_PROPERTY", cellular)

    return g


def get_fourth_sentence_ontology():
    """ПРАВИЛЬНАЯ эталонная онтология для четвёртого предложения"""
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

    # === КОНЦЕПТЫ ===
    encourage = concept("encourage")
    adopt = concept("adopt")
    improve = concept("improve")
    view = concept("view")
    aim = concept("aim")
    communication = concept("communication")
    endeavors = concept("endeavors")
    cell_based = concept("cell_based")
    research = concept("research")
    interdisciplinary = concept("interdisciplinary")
    molecular_events = concept("molecular_events")
    signaling_pathways = concept("signaling_pathways")
    clinical_phenotypes = concept("clinical_phenotypes")
    modulatory = concept("modulatory")
    emerging = concept("emerging")
    cell_to_cell = concept("cell_to_cell")
    PD = concept("PD")

    # === СИНТАКСИЧЕСКИЕ СВЯЗИ ===
    relation(adopt, "xcomp_of", encourage)
    relation(view, "obj_of", adopt)
    relation(cell_based, "amod_of", view)
    relation(improve, "acl_of", aim)
    relation(communication, "obj_of", improve)
    relation(interdisciplinary, "amod_of", endeavors)
    relation(research, "PART_OF", endeavors)

    # Нет: targeting как объект
    # Вместо этого — conj связи между объектами targeting
    relation(signaling_pathways, "conj_of", molecular_events)
    relation(clinical_phenotypes, "conj_of", molecular_events)
    relation(modulatory, "compound_of", signaling_pathways)
    relation(cell_to_cell, "compound_of", signaling_pathways)
    relation(emerging, "amod_of", clinical_phenotypes)
    relation(PD, "nmod_of", clinical_phenotypes)

    # === ОНТОЛОГИЧЕСКИЕ СВЯЗИ ===
    relation(view, "HAS_PROPERTY", cell_based)
    relation(endeavors, "HAS_PROPERTY", interdisciplinary)
    relation(research, "PART_OF", endeavors)
    relation(endeavors, "targeting", molecular_events)
    relation(endeavors, "targeting", signaling_pathways)
    relation(endeavors, "targeting", clinical_phenotypes)
    relation(signaling_pathways, "HAS_PROPERTY", modulatory)
    relation(signaling_pathways, "HAS_PROPERTY", cell_to_cell)
    relation(clinical_phenotypes, "HAS_PROPERTY", emerging)
    relation(clinical_phenotypes, "PART_OF", PD)

    return g





def get_all_reference_ontologies():
    """Возвращает список всех эталонных онтологий"""
    return [
        ("sentence_1", get_first_sentence_ontology()),
        ("sentence_2", get_second_sentence_ontology()),
        ("sentence_3", get_third_sentence_ontology()),
        ("sentence_4", get_fourth_sentence_ontology())
    ]


def export_ontology_to_file(graph: Graph, filename: str, format: str = "turtle"):
    """Экспортирует онтологию в файл"""
    graph.serialize(destination=filename, format=format)
    print(f"Ontology exported to {filename}")


def load_ontology_from_file(filename: str, format: str = "turtle") -> Graph:
    """Загружает онтологию из файла"""
    g = Graph()
    g.parse(filename, format=format)
    return g