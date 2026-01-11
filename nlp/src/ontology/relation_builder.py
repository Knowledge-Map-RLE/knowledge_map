"""
Класс для построения всех типов связей: синтаксических, онтологических,
семантических и вопросных
"""

from typing import Dict, Set
from rdflib import Namespace

from .config.mappings import (
    DEPENDENCY_MAPPING,
    SKIP_DEPENDENCIES,
    ACTION_VERB_MAPPING,
    PREPOSITION_MAPPING
)
from .config.rules import (
    IS_A_RULES,
    PART_OF_RULES,
    HAS_PROPERTY_RULES,
    ABBREVIATION_RULES,
    TOPIC_OBJECT_RULES,
    DOMAIN_SEMANTIC_RULES
)


class RelationBuilder:
    """Строит связи между концептами"""
    
    def __init__(self, namespace: Namespace, concept_cache: Dict, token_to_concept: Dict):
        self.namespace = namespace
        self.concept_cache = concept_cache
        self.token_to_concept = token_to_concept
        self.graph_triples = []
    
    def add_relation(self, subj_name: str, pred: str, obj_name: str):
        """Добавляет связь между концептами"""
        if subj_name not in self.concept_cache or obj_name not in self.concept_cache:
            return
        
        subj_uri = self.concept_cache[subj_name][0]
        obj_uri = self.concept_cache[obj_name][0]
        
        if subj_uri != obj_uri:
            pred_uri = self.namespace[pred]
            self.graph_triples.append((subj_uri, pred_uri, obj_uri))
    
    def build_all_relations(self, doc):
        """Строит все типы связей"""
        self._build_syntactic_relations(doc)
        self._build_ontological_relations(doc)
        self._build_semantic_relations(doc)
        self._build_domain_specific_relations()
        
        return self.graph_triples
    
    def _build_syntactic_relations(self, doc):
        """Строит синтаксические связи из dependency parsing"""
        for token in doc:
            if token not in self.token_to_concept:
                continue
            if token.head == token:
                continue
            
            # Навигация через предлоги к реальному head
            actual_head = token.head
            while actual_head.dep_ in SKIP_DEPENDENCIES and actual_head.head != actual_head:
                actual_head = actual_head.head
            
            if actual_head not in self.token_to_concept:
                continue
            
            token_concept = self._get_concept_name(token)
            head_concept = self._get_concept_name(actual_head)
            
            if not token_concept or not head_concept or token_concept == head_concept:
                continue
            
            # Маппим зависимость на отношение
            dep = token.dep_
            if dep in DEPENDENCY_MAPPING:
                self.add_relation(token_concept, DEPENDENCY_MAPPING[dep], head_concept)
            
            # Специальная обработка agent
            if dep == "agent" or (dep == "obl" and "agent" in str(token.dep_)):
                self.add_relation(token_concept, "obl_agent_of", head_concept)
    
    def _build_ontological_relations(self, doc):
        """Строит онтологические связи (IS_A, PART_OF, HAS_PROPERTY)"""
        # IS_A отношения
        for rule in IS_A_RULES:
            if rule["pattern"] == "X_as_Y":
                self._apply_pattern_rule(doc, rule, ["IS_A", "what_is_it"])
            elif rule["pattern"] == "subclass":
                for subj, obj in rule["pairs"]:
                    self.add_relation(subj, "IS_A", obj)
        
        # PART_OF отношения
        for rule in PART_OF_RULES:
            if rule["pattern"] == "X_of_Y":
                self._apply_of_pattern(doc, rule)
            elif rule["pattern"] == "predefined_pairs":
                for part, whole in rule["pairs"]:
                    self.add_relation(part, "PART_OF", whole)
        
        # HAS_PROPERTY отношения
        for rule in HAS_PROPERTY_RULES:
            if rule["pattern"] == "amod":
                self._apply_amod_property(doc, rule)
            elif rule["pattern"] == "predefined_properties":
                for obj, properties in rule["pairs"]:
                    for prop in properties:
                        self.add_relation(obj, "HAS_PROPERTY", prop)
                        self.add_relation(obj, "what_kind", prop)
        
        # Аббревиатуры
        for rule in ABBREVIATION_RULES:
            if rule["pattern"] == "appos":
                self._apply_appos_abbreviation(doc)
            elif rule["pattern"] == "predefined":
                for abbr, full in rule["pairs"]:
                    self.add_relation(abbr, "IS_ABBREVIATION_OF", full)
        
        # HAS_TOPIC / HAS_OBJECT
        for rule in TOPIC_OBJECT_RULES:
            self._apply_topic_object_rule(doc, rule)
    
    def _build_semantic_relations(self, doc):
        """Строит семантические связи из глаголов и предлогов"""
        # Глагольные действия
        for token in doc:
            if token.lemma_ not in ACTION_VERB_MAPPING:
                continue
            if token not in self.token_to_concept:
                continue
            
            verb_mapping = ACTION_VERB_MAPPING[token.lemma_]
            verb_concept = self._get_concept_name(token)
            
            subj, obj = self._find_verb_arguments(token)
            
            # Пассивные конструкции
            if not obj and subj and verb_mapping.get("passive_swap"):
                obj = self._find_passive_object(token)
                if subj and obj:
                    obj_name = self._get_concept_name_from_uri(obj)
                    subj_name = self._get_concept_name_from_uri(subj)
                    
                    # В пассиве объект становится агентом
                    self.add_relation(obj_name, verb_mapping["semantic"], subj_name)
                    for rel in verb_mapping.get("passive_relations", []):
                        if rel == "by_what":
                            self.add_relation(verb_concept, rel, obj_name)
                        else:
                            self.add_relation(subj_name, rel, obj_name)
                    self.add_relation(obj_name, "obl_agent_of", verb_concept)
                    continue
            
            if subj and obj:
                subj_name = self._get_concept_name_from_uri(subj)
                obj_name = self._get_concept_name_from_uri(obj)
                
                self.add_relation(subj_name, verb_mapping["semantic"], obj_name)
                self.add_relation(verb_concept, "what", obj_name)
                self.add_relation(subj_name, "what_did", verb_concept)
                
                # Обратные связи
                if "inverse" in verb_mapping:
                    for inv_rel in verb_mapping["inverse"]:
                        self.add_relation(obj_name, inv_rel, subj_name)
        
        # Предложные связи (темпоральные, локативные)
        self._build_preposition_relations(doc)
    
    def _build_preposition_relations(self, doc):
        """Строит связи на основе предлогов"""
        for token in doc:
            if token.dep_ != "prep" or token.lemma_ not in PREPOSITION_MAPPING:
                continue
            
            head = token.head
            pobj_list = [child for child in token.children if child.dep_ == "pobj"]
            
            if not pobj_list or head not in self.token_to_concept:
                continue
            
            pobj = pobj_list[0]
            if pobj not in self.token_to_concept:
                continue
            
            head_name = self._get_concept_name(head)
            pobj_name = self._get_concept_name(pobj)
            
            if not head_name or not pobj_name or head_name == pobj_name:
                continue
            
            mapping = PREPOSITION_MAPPING[token.lemma_]
            
            # Темпоральные связи
            if "temporal" in mapping and mapping["temporal"]:
                self.add_relation(head_name, mapping["temporal"], pobj_name)
            
            # Пространственные связи
            if "spatial" in mapping and mapping["spatial"]:
                if isinstance(mapping["spatial"], list):
                    for rel in mapping["spatial"]:
                        self.add_relation(head_name, rel, pobj_name)
                else:
                    self.add_relation(head_name, mapping["spatial"], pobj_name)
            
            # Дополнительные связи
            if "additional" in mapping:
                for rel in mapping["additional"]:
                    if mapping.get("inverse") and rel == "nmod_of":
                        self.add_relation(pobj_name, rel, head_name)
                    else:
                        self.add_relation(head_name, rel, pobj_name)
            
            # Вопросные связи
            if "question" in mapping:
                self.add_relation(head_name, mapping["question"], pobj_name)
    
    def _build_domain_specific_relations(self):
        """Строит специфичные для домена связи"""
        for concept_name, rules in DOMAIN_SEMANTIC_RULES.items():
            if concept_name not in self.concept_cache:
                continue
            
            # Прямые связи
            if "relations" in rules:
                for subj, pred, obj in rules["relations"]:
                    self.add_relation(subj, pred, obj)
            
            # Conj правила
            if "conj_rules" in rules:
                for term1, term2 in rules["conj_rules"]:
                    self.add_relation(term1, "conj_of", term2)
    
    # ===== Вспомогательные методы =====
    
    def _get_concept_name(self, token):
        """Получает имя концепта из токена"""
        if token not in self.token_to_concept:
            return None
        uri = self.token_to_concept[token]
        return str(uri).split("#")[-1]
    
    def _get_concept_name_from_uri(self, uri):
        """Получает имя концепта из URI"""
        return str(uri).split("#")[-1]
    
    def _find_verb_arguments(self, verb_token):
        """Находит подлежащее и дополнение глагола"""
        subj, obj = None, None
        for child in verb_token.children:
            if child.dep_ in ["nsubj", "nsubjpass"] and child in self.token_to_concept:
                subj = self.token_to_concept[child]
            elif child.dep_ in ["dobj", "obj"] and child in self.token_to_concept:
                obj = self.token_to_concept[child]
        return subj, obj
    
    def _find_passive_object(self, verb_token):
        """Находит агент в пассивной конструкции (by X)"""
        for child in verb_token.children:
            if child.dep_ in ["agent", "obl"]:
                for pobj_child in child.children:
                    if pobj_child.dep_ == "pobj" and pobj_child in self.token_to_concept:
                        return self.token_to_concept[pobj_child]
        return None
    
    def _apply_pattern_rule(self, doc, rule, relations):
        """Применяет паттерн-правило"""
        syntax = rule["syntax"]
        for token in doc:
            if token.dep_ == syntax["dep"] and token.head.lemma_ == syntax["prep"]:
                source = token.head.head
                if source in self.token_to_concept and token in self.token_to_concept:
                    source_name = self._get_concept_name(source)
                    target_name = self._get_concept_name(token)
                    if source_name and target_name and source_name != target_name:
                        for rel in relations:
                            self.add_relation(source_name, rel, target_name)
    
    def _apply_of_pattern(self, doc, rule):
        """Применяет правило для 'X of Y'"""
        for token in doc:
            if token.dep_ == "prep" and token.lemma_ == "of":
                head = token.head
                pobj_list = [child for child in token.children if child.dep_ == "pobj"]
                if pobj_list and head in self.token_to_concept:
                    pobj = pobj_list[0]
                    if pobj in self.token_to_concept:
                        part_name = self._get_concept_name(head)
                        whole_name = self._get_concept_name(pobj)
                        if part_name and whole_name and part_name != whole_name:
                            for rel in rule["relations"]:
                                self.add_relation(part_name, rel, whole_name)
    
    def _apply_amod_property(self, doc, rule):
        """Применяет правило для amod -> HAS_PROPERTY"""
        for token in doc:
            if token.pos_ == "ADJ" and token.dep_ == "amod":
                if token in self.token_to_concept and token.head in self.token_to_concept:
                    adj_name = self._get_concept_name(token)
                    noun_name = self._get_concept_name(token.head)
                    if adj_name and noun_name and adj_name != noun_name:
                        for rel in rule["relations"]:
                            if rel == rule["inverse"]:
                                self.add_relation(adj_name, rel, noun_name)
                            else:
                                self.add_relation(noun_name, rel, adj_name)
    
    def _apply_appos_abbreviation(self, doc):
        """Применяет правило для appos -> IS_ABBREVIATION_OF"""
        for token in doc:
            if token.dep_ == "appos":
                if token in self.token_to_concept and token.head in self.token_to_concept:
                    abbr_name = self._get_concept_name(token)
                    full_name = self._get_concept_name(token.head)
                    if abbr_name and full_name and abbr_name != full_name:
                        if len(token.text) < len(token.head.text):
                            self.add_relation(abbr_name, "IS_ABBREVIATION_OF", full_name)
                        else:
                            self.add_relation(full_name, "IS_ABBREVIATION_OF", abbr_name)
    
    def _apply_topic_object_rule(self, doc, rule):
        """Применяет правило HAS_TOPIC / HAS_OBJECT"""
        for token in doc:
            if token.lemma_ not in rule["trigger_lemmas"]:
                continue
            if token not in self.token_to_concept:
                continue
            
            for child in token.children:
                if child.dep_ == "prep" and child.lemma_ == rule["syntax"]["prep"]:
                    for pobj in child.children:
                        if pobj.dep_ == "pobj" and pobj in self.token_to_concept:
                            trigger_name = self._get_concept_name(token)
                            topic_name = self._get_concept_name(pobj)
                            if trigger_name and topic_name and trigger_name != topic_name:
                                for rel in rule["relation"]:
                                    self.add_relation(trigger_name, rel, topic_name)
