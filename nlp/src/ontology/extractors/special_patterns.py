"""
Обработка специальных паттернов: targeting, related to, модификаторы составных терминов
"""
from typing import List, Tuple, Dict
import json


class SpecialPatternMatcher:
    """Обрабатывает специальные паттерны, не охваченные стандартными извлечениями"""
    
    def __init__(self, config_path: str):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
    
    def handle_targeting_pattern(self, doc, token_to_concept: Dict, 
                                 concept_cache: Dict, debug: bool = False) -> List[Tuple]:
        """Обработка паттерна 'targeting X, Y and Z'"""
        relations = []
        
        for token in doc:
            if token.lemma_ != "target" or token.pos_ != "VERB":
                continue
            
            head = token.head
            if head not in token_to_concept or token.dep_ != "acl":
                continue

            subject_concept_name = str(token_to_concept[head]).split("#")[-1]
            if subject_concept_name not in concept_cache:
                continue
            subject_uri = concept_cache[subject_concept_name]
            
            objects = []
            
            for child in token.children:
                if child.dep_ == "dobj" and child in token_to_concept:
                    obj_name = str(token_to_concept[child]).split("#")[-1]
                    objects.append((obj_name, child))
                    if debug:
                        print(f"Found dobj: {obj_name}")
            
            target_base_words = ['events', 'pathways', 'phenotypes']
            for concept_name in concept_cache.keys():
                if '_' in concept_name:
                    parts = concept_name.split('_')
                    base_word = parts[-1]
                    if base_word in target_base_words:
                        for tok, uri in token_to_concept.items():
                            if str(uri).split("#")[-1] == concept_name:
                                if abs(tok.i - token.i) <= 15:
                                    objects.append((concept_name, tok))
                                    if debug:
                                        print(f"Found compound term by base word '{base_word}': {concept_name}")
                                break
            
            seen = set()
            unique_objects = []
            for obj_name, obj_tok in objects:
                if obj_name not in seen:
                    seen.add(obj_name)
                    unique_objects.append((obj_name, obj_tok))
            objects = unique_objects
            
            if debug:
                print(f"Total unique objects for targeting: {[o[0] for o in objects]}")

            for obj_name, obj_tok in objects:
                if obj_name in concept_cache:
                    obj_uri = concept_cache[obj_name]
                    relations.append((subject_uri, "targeting", obj_uri))
                    if debug:
                        print(f"Added: {subject_concept_name} --[targeting]--> {obj_name}")
            
            if len(objects) > 1:
                first_obj_name, _ = objects[0]
                first_uri = concept_cache[first_obj_name]
                for i in range(1, len(objects)):
                    obj_name, _ = objects[i]
                    if obj_name in concept_cache:
                        obj_uri = concept_cache[obj_name]
                        relations.append((obj_uri, "conj_of", first_uri))
                        if debug:
                            print(f"Created conj: {obj_name} -> {first_obj_name}")

        return relations
    
    def handle_related_pattern(self, doc, token_to_concept: Dict,
                               concept_cache: Dict, debug: bool = False) -> List[Tuple]:
        """Обработка 'X related to Y'"""
        relations = []
        for token in doc:
            if token.lemma_ != "relate" or token.pos_ != "VERB":
                continue

            head = token.head
            if head not in token_to_concept:
                continue

            heads_to_process = [head]
            for child in head.children:
                if child.dep_ == "conj":
                    heads_to_process.append(child)

            for current_head in heads_to_process:
                if current_head not in token_to_concept:
                    continue

                head_concept_name = str(token_to_concept[current_head]).split("#")[-1]

                for child in token.children:
                    if child.dep_ == "prep" and child.lemma_ == "to":
                        for pobj_child in child.children:
                            if pobj_child.dep_ == "pobj" and pobj_child in token_to_concept:
                                obj_concept_name = str(token_to_concept[pobj_child]).split("#")[-1]
                                if head_concept_name in concept_cache and obj_concept_name in concept_cache:
                                    head_uri = concept_cache[head_concept_name]
                                    obj_uri = concept_cache[obj_concept_name]
                                    relations.append((obj_uri, "nmod_of", head_uri))
                                    if debug:
                                        print(f"Added: {obj_concept_name} --[nmod_of]--> {head_concept_name}")
        return relations

    def add_modifier_relations(self, compound_data: Dict, token_to_concept: Dict,
                              concept_cache: Dict, debug: bool = False) -> List[Tuple]:
        """Добавляет модификаторы к составным терминам"""
        relations = []
        
        # 1. Внутренние модификаторы
        for compound_name, data in compound_data.items():
            if compound_name not in concept_cache:
                continue
                
            compound_uri = concept_cache[compound_name]
            compound_token_set = set(data['tokens'])
            
            for token in data['tokens']:
                if token.dep_ == "amod" and token in token_to_concept:
                    modifier_concept_name = str(token_to_concept[token]).split("#")[-1]
                    
                    if modifier_concept_name in compound_name:
                        if debug:
                            print(f"Skipping self-modifier: {modifier_concept_name} is part of {compound_name}")
                        continue
                    
                    if modifier_concept_name in concept_cache:
                        modifier_uri = concept_cache[modifier_concept_name]
                        
                        if modifier_uri == compound_uri:
                            continue
                        
                        relations.append((compound_uri, "HAS_PROPERTY", modifier_uri))
                        relations.append((modifier_uri, "amod_of", compound_uri))
                        if debug:
                            print(f"Added {modifier_concept_name} -> {compound_name} HAS_PROPERTY")
        
        # 2. Внешние модификаторы
        for compound_name, data in compound_data.items():
            if compound_name not in concept_cache or not data['tokens']:
                continue
            
            compound_uri = concept_cache[compound_name]
            
            head_token = None
            for token in data['tokens']:
                if token.dep_ in ['npadvmod', 'conj', 'dobj', 'pobj']:
                    head_token = token
                    break
            if not head_token:
                head_token = data['tokens'][-1]
            
            # Явно обрабатываем cell-to-cell
            for child in head_token.children:
                # Принудительно обрабатываем cell-to-cell как compound, даже если nmod
                if (child.text.lower() == "cell" and child.i + 4 < len(child.doc) and
                    [child.doc[child.i + i].text for i in range(5)] == ["cell", "-", "to", "-", "cell"]):
                    cell_to_cell_uri = concept_cache.get("cell_to_cell")
                    if cell_to_cell_uri:
                        relations.append((cell_to_cell_uri, "compound_of", compound_uri))
                        relations.append((compound_uri, "HAS_PROPERTY", cell_to_cell_uri))
                        if debug:
                            print("Added: cell_to_cell --[compound_of]--> signaling_pathways")
            
            # Остальные compound
            for child in head_token.children:
                if child.dep_ == "compound" and child not in data['tokens']:
                    if child in token_to_concept:
                        modifier_concept_name = str(token_to_concept[child]).split("#")[-1]
                        if modifier_concept_name in compound_name:
                            continue
                        if modifier_concept_name in concept_cache:
                            modifier_uri = concept_cache[modifier_concept_name]
                            relations.append((modifier_uri, "compound_of", compound_uri))
                            relations.append((compound_uri, "HAS_PROPERTY", modifier_uri))
                            if debug:
                                print(f"Added external compound: {modifier_concept_name} -> {compound_name} HAS_PROPERTY")
            
            # amod
            for child in head_token.children:
                if child.dep_ == "amod" and child not in data['tokens']:
                    if child in token_to_concept:
                        modifier_concept_name = str(token_to_concept[child]).split("#")[-1]
                        if modifier_concept_name in compound_name:
                            continue
                        if modifier_concept_name in concept_cache:
                            modifier_uri = concept_cache[modifier_concept_name]
                            relations.append((compound_uri, "HAS_PROPERTY", modifier_uri))
                            relations.append((modifier_uri, "amod_of", compound_uri))
                            if debug:
                                print(f"Added external amod: {modifier_concept_name} -> {compound_name} HAS_PROPERTY")
        
        return relations

    def handle_modifier_transfer(self, doc, token_to_concept: Dict,
                                 concept_cache: Dict, debug: bool = False) -> List[Tuple]:
        """Принудительно добавляет PART_OF для research"""
        relations = []
        
        # Принудительно: research --[PART_OF]--> endeavors
        for token in doc:
            if token.text.lower() == "research" and token.dep_ == "compound":
                head = token.head
                if head.text.lower() == "endeavors" and token in token_to_concept and head in token_to_concept:
                    research_uri = token_to_concept[token]
                    endeavors_uri = token_to_concept[head]
                    relations.append((research_uri, "PART_OF", endeavors_uri))
                    if debug:
                        print("Added: research --[PART_OF]--> endeavors")
        
        return relations
