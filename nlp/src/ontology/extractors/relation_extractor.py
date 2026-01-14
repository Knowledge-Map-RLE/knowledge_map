"""
=============================================================================
ФАЙЛ 4: src/ontology/extractors/relation_extractor.py
=============================================================================
Извлечение отношений между концептами
"""
import json
from typing import Dict, List, Tuple
import spacy


class RelationExtractor:
    """Извлекает отношения из dependency parse"""
    
    def __init__(self, config_path: str):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.dep_map = {
            "nsubj": "nsubj_of",
            "nsubjpass": "nsubjpass_of",
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
            "compound": "compound_of",
            "npadvmod": "npadvmod_of",
        }
    
    def extract_syntactic_relations(self, doc: spacy.tokens.Doc, 
                                    token_to_concept: Dict) -> List[Tuple]:
        """Извлекает синтаксические отношения"""
        relations = []
        
        for token in doc:
            if token not in token_to_concept:
                continue
            if token.head == token:
                continue
            
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
            if dep in self.dep_map:
                relations.append((token_concept, self.dep_map[dep], head_concept))
            
            if dep == "agent" or (dep == "obl" and "agent" in str(token.dep_)):
                relations.append((token_concept, "obl_agent_of", head_concept))
            
            if dep == "pobj" and actual_head.dep_ == "agent":
                relations.append((token_concept, "obl_agent_of", head_concept))
        
        return relations
    
    def extract_has_property_relations(self, doc: spacy.tokens.Doc,
                                      token_to_concept: Dict) -> List[Tuple]:
        """Извлекает HAS_PROPERTY отношения для amod"""
        relations = []
        
        # Основная обработка: amod → HAS_PROPERTY
        for token in doc:
            if token.dep_ == "amod" and token in token_to_concept:
                if token.head in token_to_concept:
                    adj_concept = token_to_concept[token]
                    noun_concept = token_to_concept[token.head]
                    if adj_concept != noun_concept:
                        relations.append((noun_concept, "HAS_PROPERTY", adj_concept))
                        relations.append((adj_concept, "amod_of", noun_concept))
        
        # Конъюнкции прилагательных
        for token in doc:
            if token.pos_ == "ADJ" and token.dep_ == "conj" and token in token_to_concept:
                if token.head in token_to_concept:
                    adj1_concept = token_to_concept[token.head]
                    adj2_concept = token_to_concept[token]
                    if adj1_concept != adj2_concept:
                        relations.append((adj1_concept, "conj_of", adj2_concept))
                    
                    if token.head.dep_ == "amod" and token.head.head in token_to_concept:
                        noun_concept = token_to_concept[token.head.head]
                        if adj2_concept != noun_concept:
                            relations.append((noun_concept, "HAS_PROPERTY", adj2_concept))
                            relations.append((adj2_concept, "amod_of", noun_concept))
        
        return relations
    
    def extract_part_of_relations(self, doc: spacy.tokens.Doc,
                                  token_to_concept: Dict) -> List[Tuple]:
        relations = []
        
        for token in doc:
            if token.dep_ == "prep" and token.lemma_ in ["of", "around"]:
                head = token.head
                pobj_list = [child for child in token.children if child.dep_ == "pobj"]
                if pobj_list and head in token_to_concept:
                    pobj = pobj_list[0]
                    if pobj in token_to_concept:
                        part_concept = token_to_concept[head]
                        whole_concept = token_to_concept[pobj]
                        if part_concept != whole_concept:
                            if token.lemma_ == "of":
                                relations.append((part_concept, "PART_OF", whole_concept))
                            if head.pos_ == "VERB" or head.dep_ in ["advcl", "acl"]:
                                relations.append((whole_concept, "pobj_of", part_concept))
        
        return relations
    
    def extract_is_a_relations(self, doc: spacy.tokens.Doc,
                               token_to_concept: Dict) -> List[Tuple]:
        relations = []
        
        for token in doc:
            if token.dep_ == "pobj" and token.head.lemma_ == "as" and token in token_to_concept:
                source = token.head.head
                if source in token_to_concept:
                    source_concept = token_to_concept[source]
                    target_concept = token_to_concept[token]
                    if source_concept != target_concept:
                        relations.append((source_concept, "IS_A", target_concept))
        
        return relations
    
    def extract_temporal_relations(self, doc: spacy.tokens.Doc,
                                   token_to_concept: Dict) -> List[Tuple]:
        relations = []
        
        for token in doc:
            if token.dep_ == "prep" and token.lemma_ in ["in", "since", "between"]:
                head = token.head
                pobj_list = [child for child in token.children if child.dep_ == "pobj"]
                if pobj_list and head in token_to_concept:
                    pobj = pobj_list[0]
                    if pobj in token_to_concept:
                        semantic_head = head
                        
                        if head.dep_ == "pobj":
                            prep_parent = head.head
                            if prep_parent.dep_ == "prep" and prep_parent.head in token_to_concept:
                                semantic_head = prep_parent.head
                        
                        event_concept = token_to_concept[semantic_head]
                        location_concept = token_to_concept[pobj]
                        
                        if event_concept != location_concept:
                            if token.lemma_ == "in":
                                relations.append((event_concept, "happened_in", location_concept))
                                relations.append((location_concept, "nmod_of", event_concept))
                            elif token.lemma_ == "since":
                                relations.append((event_concept, "started_after", location_concept))
                            elif token.lemma_ == "between":
                                relations.append((event_concept, "happens_between", location_concept))
        
        return relations
    
    def extract_semantic_verb_relations(self, doc: spacy.tokens.Doc,
                                       token_to_concept: Dict) -> List[Tuple]:
        relations = []
        action_verbs = self.config.get('semantic_relations', {}).get('action_verbs', {})
        
        for token in doc:
            if token.lemma_ in action_verbs and token.pos_ == "VERB" and token in token_to_concept:
                subj, obj = None, None
                
                for child in token.children:
                    if child.dep_ in ["nsubj", "nsubjpass"] and child in token_to_concept:
                        subj = token_to_concept[child]
                    elif child.dep_ in ["dobj", "obj"] and child in token_to_concept:
                        obj = token_to_concept[child]
                
                if not obj and subj and token.lemma_ == "increase":
                    for child in token.children:
                        if child.dep_ in ["agent", "obl"]:
                            for pobj_child in child.children:
                                if pobj_child.dep_ == "pobj" and pobj_child in token_to_concept:
                                    obj = token_to_concept[pobj_child]
                                    if subj and obj:
                                        relations.append((subj, "increased_by", obj))
                                    break
                
                if subj and obj and subj != obj:
                    semantic_rel = action_verbs[token.lemma_]
                    relations.append((subj, semantic_rel, obj))
                    
                    if token.lemma_ == "influence":
                        relations.append((obj, "influenced_by", subj))
        
        return relations
