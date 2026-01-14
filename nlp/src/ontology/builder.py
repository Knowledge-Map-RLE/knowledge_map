"""
=============================================================================
ФАЙЛ 6: src/ontology/builder_refactored.py
=============================================================================
Основной рефакторенный билдер
"""
import json
from rdflib import Graph, Namespace, Literal, RDF, RDFS
from rdflib.namespace import OWL
from typing import List, Dict, Set
import spacy

from .extractors.compound_extractor import CompoundTermExtractor
from .extractors.relation_extractor import RelationExtractor
from .extractors.special_patterns import SpecialPatternMatcher
from .utils.term_utils import normalize_term, normalize_name


class OntologyBuilder:
    """Рефакторенный билдер онтологий с конфигурацией"""
    
    def __init__(self, config_path: str = "config/domain_config.json", 
                 base_uri: str = "http://example.org/parkinson#"):
        self.config_path = config_path
        self.base_uri = base_uri
        self.namespace = Namespace(base_uri)
        self.debug = False
        
        # Загружаем конфигурацию
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # Инициализируем экстракторы
        self.compound_extractor = CompoundTermExtractor(config_path)
        self.relation_extractor = RelationExtractor(config_path)
        self.pattern_matcher = SpecialPatternMatcher(config_path)
        
        # Специальные формы из конфига
        self.preserve_forms = self.config['special_terms']['preserve_form']
        self.normalize_plural = self.config['special_terms'].get('normalize_plural', {})
    
    def text_to_ontology(self, text: str, nlp: spacy.language.Language) -> Graph:
        """Преобразует текст в онтологию"""
        EX = self.namespace
        g = Graph()
        g.bind("", EX)
        g.bind("owl", OWL)
        g.bind("rdfs", RDFS)
        
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
        
        if self.debug:
            print("\n=== DEPENDENCY PARSE ===")
            for token in doc:
                print(f"{token.text:20} {token.pos_:10} {token.dep_:15} {token.head.text}")
        
        # ========== PHASE 1: СОСТАВНЫЕ ТЕРМИНЫ ==========
        compound_data = self.compound_extractor.extract_all(doc, self.debug)
        
        token_to_concept = {}
        concept_cache = {}
        processed_tokens = set()
        
        # Создаём концепты для составных терминов
        for compound_name, data in compound_data.items():
            if compound_name not in concept_cache:
                c = concept(data['name'], label_text=data['label'])
                concept_cache[compound_name] = c
            
            # Мапим все токены на этот концепт
            for token in data['tokens']:
                token_to_concept[token] = concept_cache[compound_name]
                processed_tokens.add(token)
        
        # Создаём базовые концепты для составных терминов (knowledge, factors, etc)
        base_concepts_created = set()
        for compound_name, config in self.compound_extractor.compound_terms.items():
            if 'create_base_concepts' in config:
                for base_concept_name in config['create_base_concepts']:
                    if base_concept_name not in base_concepts_created:
                        if base_concept_name not in concept_cache:
                            c = concept(base_concept_name, label_text=base_concept_name)
                            concept_cache[base_concept_name] = c
                            base_concepts_created.add(base_concept_name)
                            if self.debug:
                                print(f"Created base concept: {base_concept_name}")
        
        # ========== PHASE 2: ИНДИВИДУАЛЬНЫЕ КОНЦЕПТЫ ==========
        base_verb_forms = self.config.get('base_verb_forms', {})
        
        for token in doc:
            if token in processed_tokens:
                continue
            
            if token.pos_ not in {"NOUN", "PROPN", "VERB", "ADJ", "NUM", "PRON"}:
                continue
            
            if token.pos_ == "VERB" and token.dep_ in ["aux", "auxpass", "cop"]:
                continue
            
            # Нормализуем термин
            term = normalize_term(token, self.preserve_forms)
            
            # Применяем plural normalization
            if term in self.normalize_plural:
                term = self.normalize_plural[term]
            
            # Создаём концепт
            if term not in concept_cache:
                c = concept(term, label_text=token.text)
                concept_cache[term] = c
            
            token_to_concept[token] = concept_cache[term]
            
            # Создаём базовую форму глагола если есть
            if term in base_verb_forms:
                base_form = base_verb_forms[term]
                if base_form not in concept_cache:
                    c = concept(base_form, label_text=base_form)
                    concept_cache[base_form] = c
                    if self.debug:
                        print(f"Created base verb form: {base_form} from {term}")
        
        # ========== PHASE 3: СИНТАКСИЧЕСКИЕ СВЯЗИ ==========
        syntactic_relations = self.relation_extractor.extract_syntactic_relations(
            doc, token_to_concept
        )
        
        for subj, pred, obj in syntactic_relations:
            relation(subj, pred, obj)
        
        # ========== PHASE 4: ОНТОЛОГИЧЕСКИЕ СВЯЗИ ==========
        
        # HAS_PROPERTY для amod
        has_property_relations = self.relation_extractor.extract_has_property_relations(
            doc, token_to_concept
        )
        for subj, pred, obj in has_property_relations:
            relation(subj, pred, obj)
        
        # PART_OF отношения
        part_of_relations = self.relation_extractor.extract_part_of_relations(
            doc, token_to_concept
        )
        for subj, pred, obj in part_of_relations:
            relation(subj, pred, obj)
        
        # IS_A отношения
        is_a_relations = self.relation_extractor.extract_is_a_relations(
            doc, token_to_concept
        )
        for subj, pred, obj in is_a_relations:
            relation(subj, pred, obj)
        
        # Временные отношения
        temporal_relations = self.relation_extractor.extract_temporal_relations(
            doc, token_to_concept
        )
        for subj, pred, obj in temporal_relations:
            relation(subj, pred, obj)
        
        # Семантические глагольные отношения
        verb_relations = self.relation_extractor.extract_semantic_verb_relations(
            doc, token_to_concept
        )
        for subj, pred, obj in verb_relations:
            relation(subj, pred, obj)
        
        # ========== PHASE 5: СПЕЦИАЛЬНЫЕ ПАТТЕРНЫ ==========
        
        # targeting паттерн
        targeting_relations = self.pattern_matcher.handle_targeting_pattern(
            doc, token_to_concept, concept_cache, self.debug
        )
        for subj, pred, obj in targeting_relations:
            relation(subj, pred, obj)
        
        # related to паттерн
        related_relations = self.pattern_matcher.handle_related_pattern(
            doc, token_to_concept, concept_cache, self.debug
        )
        for subj, pred, obj in related_relations:
            relation(subj, pred, obj)

        # Перенос модификаторов 
        modifier_transfer_relations = self.pattern_matcher.handle_modifier_transfer(
            doc, token_to_concept, concept_cache, self.debug
        )
        for subj, pred, obj in modifier_transfer_relations:
            relation(subj, pred, obj)
        
        # Модификаторы составных терминов (modulatory, emerging)
        modifier_relations = self.pattern_matcher.add_modifier_relations(
            compound_data, token_to_concept, concept_cache, self.debug
        )
        for subj, pred, obj in modifier_relations:
            relation(subj, pred, obj)
        
        # ========== PHASE 6: ДОМЕННЫЕ ОТНОШЕНИЯ ИЗ КОНФИГА ==========
        
        # Онтологические отношения
        ont_relations = self.config.get('ontological_relations', {})
        for rel_type, pairs in ont_relations.items():
            for source_name, target_name in pairs:
                if source_name in concept_cache and target_name in concept_cache:
                    relation(concept_cache[source_name], rel_type, concept_cache[target_name])
        
        # Семантические доменные отношения
        domain_specific = self.config.get('semantic_relations', {}).get('domain_specific', [])
        for source_name, pred, target_name in domain_specific:
            if source_name in concept_cache and target_name in concept_cache:
                relation(concept_cache[source_name], pred, concept_cache[target_name])
        
        # Временные отношения из конфига
        temporal_config = self.config.get('semantic_relations', {}).get('temporal_relations', [])
        for source_name, pred, target_name in temporal_config:
            if source_name in concept_cache and target_name in concept_cache:
                relation(concept_cache[source_name], pred, concept_cache[target_name])
        
        # Специальные паттерны из конфига
        special_patterns = self.config.get('semantic_relations', {}).get('special_patterns', {})
        for pattern_name, pattern_data in special_patterns.items():
            concepts = pattern_data['concepts']
            rel = pattern_data['relation']
            if all(c in concept_cache for c in concepts):
                relation(concept_cache[concepts[0]], rel, concept_cache[concepts[1]])
        
        if self.debug:
            print("\n=== CONCEPT CACHE ===")
            for key in sorted(concept_cache.keys()):
                print(f"  {key}")
        
        return g
    
    def texts_to_ontology(self, texts: List[str], nlp: spacy.language.Language) -> List[Graph]:
        return [self.text_to_ontology(text, nlp) for text in texts]
    
    def add_cross_sentence_links(self, graphs: List[Graph]) -> Graph:
        merged = Graph()
        merged.bind("", self.namespace)
        merged.bind("owl", OWL)
        merged.bind("rdfs", RDFS)
        
        for g in graphs:
            for triple in g:
                merged.add(triple)
        
        def get_concepts(graph):
            concepts = set()
            for s, p, o in graph:
                if not isinstance(o, Literal):
                    concepts.add(str(s).split("#")[-1])
                    concepts.add(str(o).split("#")[-1])
            return concepts
        
        all_concepts = [get_concepts(g) for g in graphs]
        common = set.intersection(*all_concepts) if len(all_concepts) > 1 else set()
        
        if len(graphs) >= 2:
            for concept_name in common:
                concept_uri = self.namespace[concept_name]
                merged.add((
                    concept_uri,
                    self.namespace["COREF"],
                    Literal(f"sentences_{'_'.join(map(str, range(1, len(graphs)+1)))}")
                ))
        
        return merged