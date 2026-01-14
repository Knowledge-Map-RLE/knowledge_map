"""
=============================================================================
ФАЙЛ 3: src/ontology/extractors/compound_extractor.py
=============================================================================
Извлечение составных терминов
"""
import json
from typing import Dict, List, Optional
import spacy
from ..utils.term_utils import safe_lemma_check, normalize_name


class CompoundTermExtractor:
    """Извлекает составные термины по паттернам из конфигурации"""
    
    def __init__(self, config_path: str):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.compound_terms = self.config.get('compound_terms', {})
    
    def extract_all(self, doc: spacy.tokens.Doc, debug: bool = False) -> Dict[str, Dict]:
        """Извлекает все составные термины"""
        results = {}
        
        results.update(self._extract_configured_compounds(doc, debug))
        results.update(self._extract_based_compounds(doc, debug))
        results.update(self._extract_hyphenated(doc, debug))
        results.update(self._extract_cell_to_cell(doc, debug))  # ← Новое
        results.update(self._extract_temporal(doc, debug))
        results.update(self._extract_pd_alias(doc, debug))
        
        return results
    
    def _extract_cell_to_cell(self, doc, debug) -> Dict:
        """Извлекает 'cell-to-cell' как составной термин"""
        results = {}
        for i in range(len(doc) - 4):
            if (doc[i].text.lower() == "cell" and
                doc[i+1].text == "-" and
                doc[i+2].text.lower() == "to" and
                doc[i+3].text == "-" and
                doc[i+4].text.lower() == "cell"):
                tokens = [doc[i], doc[i+1], doc[i+2], doc[i+3], doc[i+4]]
                name = "cell_to_cell"
                normalized = normalize_name(name)
                if debug:
                    print(f"Found cell-to-cell: {' '.join([t.text for t in tokens])}")
                results[normalized] = {
                    'tokens': tokens,
                    'name': normalized,
                    'label': "cell-to-cell",
                    'modifiers': []
                }
                return results
        return results

    def _extract_configured_compounds(self, doc: spacy.tokens.Doc, debug: bool) -> Dict:
        results = {}
        
        for compound_name, config in self.compound_terms.items():
            parts = config['parts']
            label = config['label']
            
            if len(parts) == 2:
                if compound_name == "Parkinsons_disease":
                    result = self._match_parkinsons_disease(doc, parts, compound_name, label, debug)
                else:
                    result = self._match_two_part_compound(doc, parts, compound_name, label, debug)
            elif len(parts) == 3 and parts[1] == "of":
                result = self._match_prep_phrase(doc, parts, compound_name, label, debug)
            else:
                continue
            
            if result:
                results[compound_name] = result
        
        return results

    def _match_parkinsons_disease(self, doc, parts, name, label, debug) -> Optional[Dict]:
        text_lower = doc.text.lower()
        
        if "parkinson" in text_lower:
            for i, token in enumerate(doc):
                if "parkinson" in token.text.lower():
                    tokens_found = [token]
                    for j in range(i + 1, min(i + 4, len(doc))):
                        if doc[j].lemma_ == "disease":
                            tokens_found.append(doc[j])
                            if debug:
                                print(f"Found {name}: {' '.join([t.text for t in tokens_found])}")
                            return {
                                'tokens': tokens_found,
                                'name': name,
                                'label': label,
                                'modifiers': []
                            }
                        if doc[j].text in ["'s", "'", "s"]:
                            tokens_found.append(doc[j])
        
        return None

    def _match_two_part_compound(self, doc, parts, name, label, debug) -> Optional[Dict]:
        part1_text, part2_text = parts
        
        for token in doc:
            if safe_lemma_check(token, part2_text) and token.pos_ in ["NOUN", "PROPN"]:
                found_part1 = None
                
                for child in token.children:
                    if child.dep_ == "amod" and safe_lemma_check(child, part1_text):
                        found_part1 = child
                        break
                
                if not found_part1 and name == "environmental_factors":
                    for sibling in token.children:
                        if sibling.dep_ == "amod":
                            for conj_child in sibling.children:
                                if conj_child.dep_ == "conj" and safe_lemma_check(conj_child, part1_text):
                                    found_part1 = conj_child
                                    break
                            if not found_part1 and sibling.head == token:
                                for parent_sibling in sibling.head.children:
                                    if parent_sibling.dep_ == "conj" and safe_lemma_check(parent_sibling, part1_text):
                                        found_part1 = parent_sibling
                                        break
                
                if not found_part1:
                    for child in token.children:
                        if child.dep_ == "compound" and safe_lemma_check(child, part1_text):
                            found_part1 = child
                            break
                
                if not found_part1 and name == "signaling_pathways":
                    for i in range(max(0, token.i - 5), token.i):
                        candidate = doc[i]
                        if safe_lemma_check(candidate, part1_text):
                            found_part1 = candidate
                            break
                
                if found_part1:
                    modifiers = self._find_modifiers(token, found_part1, doc)
                    if debug:
                        print(f"Found {name}: {found_part1.text} + {token.text}")
                    return {
                        'tokens': [found_part1, token],
                        'name': name,
                        'label': label,
                        'modifiers': modifiers
                    }
        return None

    def _find_modifiers(self, token, exclude_token, doc) -> List[spacy.tokens.Token]:
        modifiers = []
        
        for child in token.children:
            if child != exclude_token and child.dep_ in ["amod", "compound"]:
                if child.pos_ in ["ADJ", "PROPN", "VERB"]:
                    modifiers.append(child)
        
        return modifiers

    def _match_prep_phrase(self, doc, parts, name, label, debug) -> Optional[Dict]:
        head_text, prep_text, obj_text = parts
        
        for token in doc:
            if safe_lemma_check(token, head_text):
                for child in token.children:
                    if child.dep_ == "prep" and child.lemma_ == prep_text:
                        for pobj in child.children:
                            if pobj.dep_ == "pobj" and safe_lemma_check(pobj, obj_text):
                                if debug:
                                    print(f"Found {name}: {token.text} {child.text} {pobj.text}")
                                return {
                                    'tokens': [token, child, pobj],
                                    'name': name,
                                    'label': label,
                                    'modifiers': []
                                }
        return None

    def _extract_based_compounds(self, doc, debug) -> Dict:
        results = {}
        
        for token in doc:
            if token.text.lower() == "based" and token.dep_ == "amod":
                modifier = None
                
                for child in token.children:
                    if child.dep_ in ["npadvmod", "compound"]:
                        modifier = child
                        break
                
                if not modifier:
                    for i in range(max(0, token.i - 3), token.i):
                        candidate = doc[i]
                        if candidate.text.lower() in ["systems", "system", "cell"]:
                            modifier = candidate
                            break
                
                if modifier:
                    compound_name = f"{modifier.text}_based"
                    normalized = normalize_name(compound_name)
                    if debug:
                        print(f"Found X-based: {modifier.text} + {token.text}")
                    results[normalized] = {
                        'tokens': [modifier, token],
                        'name': normalized,
                        'label': f"{modifier.text}-based",
                        'modifiers': []
                    }
        
        return results

    def _extract_hyphenated(self, doc, debug) -> Dict:
        results = {}
        
        for token in doc:
            if "-" in token.text and token.text.lower() not in ["age-related"]:
                normalized = normalize_name(token.text)
                if debug:
                    print(f"Found hyphenated: {token.text}")
                results[normalized] = {
                    'tokens': [token],
                    'name': normalized,
                    'label': token.text,
                    'modifiers': []
                }
        
        for token in doc:
            if token.text.lower() == "related" and token.dep_ == "amod":
                for child in token.children:
                    if child.dep_ == "npadvmod" and child.text.lower() == "age":
                        if debug:
                            print(f"Found age-related: {child.text} + {token.text}")
                        results["age_related"] = {
                            'tokens': [child, token],
                            'name': "age_related",
                            'label': "age-related",
                            'modifiers': []
                        }
        
        return results

    def _extract_temporal(self, doc, debug) -> Dict:
        results = {}
        
        for token in doc:
            if "1950" in token.text:
                if debug:
                    print(f"Found temporal: {token.text}")
                results["1950s"] = {
                    'tokens': [token],
                    'name': "1950s",
                    'label': "1950s",
                    'modifiers': []
                }
        
        return results

    def _extract_pd_alias(self, doc, debug) -> Dict:
        results = {}
        
        for token in doc:
            if token.text == "PD":
                if debug:
                    print(f"Found PD alias")
                results["PD"] = {
                    'tokens': [token],
                    'name': "PD",
                    'label': "PD",
                    'modifiers': []
                }
        
        return results
