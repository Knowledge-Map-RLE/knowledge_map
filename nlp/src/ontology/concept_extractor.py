"""
Класс для извлечения концептов из текста на основе паттернов
"""

from typing import Dict, Set, Tuple
from rdflib import Namespace, URIRef
import spacy

from .config.patterns import (
    COMPOUND_PATTERNS,
    NER_PATTERNS,
    SPECIAL_TOKENS,
    PRESERVE_FORM
)
from .utils.normalization import (
    normalize_concept_name,
    should_preserve_form,
    is_content_word
)


class ConceptExtractor:
    """Извлекает концепты из текста"""
    
    def __init__(self, namespace: Namespace):
        self.namespace = namespace
        self.concept_cache = {}
        self.token_to_concept = {}
        self.processed_tokens = set()
    
    def create_concept(self, name: str, label: str = None):
        """Создаёт новый концепт"""
        if name not in self.concept_cache:
            normalized = normalize_concept_name(name)
            uri = self.namespace[normalized]
            self.concept_cache[name] = (uri, label or name)
        return self.concept_cache[name][0]
    
    def extract_from_doc(self, doc) -> Tuple[Dict, Dict, Set]:
        """
        Извлекает все концепты из spaCy Doc
        Returns: (token_to_concept, concept_cache, processed_tokens)
        """
        # 1. Специальные токены (PD, 1950s, age-related)
        self._extract_special_tokens(doc)
        
        # 2. Именованные сущности
        self._extract_named_entities(doc)
        
        # 3. Составные термины
        self._extract_compound_terms(doc)
        
        # 4. Индивидуальные концепты
        self._extract_individual_concepts(doc)
        
        return self.token_to_concept, self.concept_cache, self.processed_tokens
    
    def _extract_special_tokens(self, doc):
        """Извлекает специальные токены"""
        for token in doc:
            if token in self.processed_tokens:
                continue
            
            for pattern_name, pattern in SPECIAL_TOKENS.items():
                if pattern["match"](token):
                    concept = self.create_concept(
                        pattern["concept_name"],
                        pattern["label"]
                    )
                    self.token_to_concept[token] = concept
                    self.processed_tokens.add(token)
                    break
    
    def _extract_named_entities(self, doc):
        """Извлекает именованные сущности"""
        for pattern_name, pattern in NER_PATTERNS.items():
            text_lower = doc.text.lower()
            contains_all = all(term in text_lower for term in pattern["text_contains"])
            
            if not contains_all:
                continue
            
            # Ищем токены с нужными словами
            trigger_tokens = []
            for i, token in enumerate(doc):
                if any(term in token.text.lower() for term in pattern["text_contains"]):
                    trigger_tokens.append((i, token))
            
            # Группируем близкие токены
            if len(trigger_tokens) >= len(pattern["text_contains"]):
                start_idx = trigger_tokens[0][0]
                end_idx = trigger_tokens[-1][0]
                
                if end_idx - start_idx <= pattern["max_distance"]:
                    concept = self.create_concept(
                        pattern["concept_name"],
                        pattern["label"]
                    )
                    for idx in range(start_idx, end_idx + 1):
                        self.token_to_concept[doc[idx]] = concept
                        self.processed_tokens.add(doc[idx])
    
    def _extract_compound_terms(self, doc):
        """Извлекает составные термины по паттернам"""
        for pattern_name, pattern in COMPOUND_PATTERNS.items():
            for token in doc:
                if token.lemma_ != pattern["trigger"]:
                    continue
                if token in self.processed_tokens:
                    continue
                
                # Проверяем паттерн
                matched_tokens = {"trigger": token}
                match_success = True
                
                for rel_type, target, max_dist in pattern["search"]:
                    found = False
                    for child in token.children:
                        if child.dep_ == rel_type and child.lemma_ == target:
                            matched_tokens[rel_type] = child
                            
                            # Ищем pobj внутри prep
                            if rel_type == "prep":
                                for pobj_child in child.children:
                                    if pobj_child.dep_ == "pobj" and pobj_child.lemma_ in [s[1] for s in pattern["search"] if s[0] == "pobj"]:
                                        matched_tokens["pobj"] = pobj_child
                            found = True
                            break
                    
                    if not found:
                        match_success = False
                        break
                
                if match_success:
                    concept = self.create_concept(
                        pattern["concept_name"],
                        pattern["label"]
                    )
                    
                    # Маппим токены
                    for key in pattern["tokens_to_map"]:
                        if key in matched_tokens:
                            self.token_to_concept[matched_tokens[key]] = concept
                            # Исключаем из processed если нужно создать отдельно
                            if "exclude_from_separate" not in pattern or key not in pattern["exclude_from_separate"]:
                                self.processed_tokens.add(matched_tokens[key])
                    
                    # Создаём "factors" для genetic/environmental factors
                    if "factors" in pattern["concept_name"]:
                        self.create_concept("factors", "factors")
    
    def _extract_individual_concepts(self, doc):
        """Извлекает индивидуальные концепты"""
        for token in doc:
            if token in self.processed_tokens:
                continue
            
            if not is_content_word(token):
                continue
            
            text_lower = token.text.lower()
            
            # Проверяем нужно ли сохранить форму
            if should_preserve_form(token, PRESERVE_FORM):
                concept_name = PRESERVE_FORM[text_lower]
                concept = self.create_concept(concept_name, token.text)
                if token not in self.token_to_concept:
                    self.token_to_concept[token] = concept
                continue
            
            # Обычная лемматизация
            lemma = token.lemma_.lower()
            concept = self.create_concept(lemma, token.text)
            self.token_to_concept[token] = concept