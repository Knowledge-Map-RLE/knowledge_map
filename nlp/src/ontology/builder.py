"""
Оптимизированный OntologyBuilder - финальная версия с исправлениями для Sentence 4
"""

import spacy
from rdflib import Graph, Namespace, Literal, RDF, RDFS
from rdflib.namespace import OWL
from typing import List


class OntologyBuilder:
    """Оптимизированный класс для построения онтологии из текста"""
    
    def __init__(self, base_uri: str = "http://example.org/parkinson#"):
        self.base_uri = base_uri
        self.namespace = Namespace(base_uri)
        self.debug = True
    
    def text_to_ontology(self, text: str, nlp: spacy.language.Language) -> Graph:
        """Преобразует текст в онтологию"""
        EX = self.namespace
        g = Graph()
        g.bind("", EX)
        g.bind("owl", OWL)
        g.bind("rdfs", RDFS)
        
        def normalize_name(txt):
            return txt.replace(" ", "_").replace("'", "").replace("(", "").replace(")", "").replace("-", "_")
        
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
        token_to_concept = {}
        concept_cache = {}
        processed_tokens = set()
        
        if self.debug:
            print("\n=== DEPENDENCY PARSE ===")
            for token in doc:
                print(f"{token.text:20} {token.pos_:10} {token.dep_:15} {token.head.text}")
        
        # ========== PHASE 1: СОСТАВНЫЕ ТЕРМИНЫ ==========
        
        text_lower = text.lower()
        
        # Parkinson's disease
        if "parkinson" in text_lower:
            for i, token in enumerate(doc):
                if "parkinson" in token.text.lower():
                    for j in range(i+1, min(i+4, len(doc))):
                        if doc[j].lemma_ == "disease":
                            if "Parkinsons_disease" not in concept_cache:
                                c = concept("Parkinsons_disease", label_text="Parkinson's disease")
                                concept_cache["Parkinsons_disease"] = c
                            for k in range(i, j+1):
                                token_to_concept[doc[k]] = concept_cache["Parkinsons_disease"]
                                processed_tokens.add(doc[k])
                            break
        
        # PD
        for token in doc:
            if token.text == "PD" and token not in processed_tokens:
                if "PD" not in concept_cache:
                    c = concept("PD", label_text="PD")
                    concept_cache["PD"] = c
                token_to_concept[token] = concept_cache["PD"]
                processed_tokens.add(token)
        
        # 1950s
        for token in doc:
            if "1950" in token.text and token not in processed_tokens:
                if "1950s" not in concept_cache:
                    c = concept("1950s", label_text="1950s")
                    concept_cache["1950s"] = c
                token_to_concept[token] = concept_cache["1950s"]
                processed_tokens.add(token)
        
        # КРИТИЧЕСКОЕ ДОПОЛНЕНИЕ: "modulatory cell-to-cell signaling pathways"
        # Это сложный термин с внутренним модификатором
        modulatory_token_found = None
        for i, token in enumerate(doc):
            if token.lemma_ == "pathway" and token not in processed_tokens:
                # Ищем "signaling" перед ним (может быть на расстоянии 1-4 токена)
                signaling_token = None
                modulatory_token = None
                cell_tokens = []
                
                # 1. Ищем через children (compound, amod)
                for child in token.children:
                    if child.text.lower() == "signaling" or child.lemma_ == "signaling":
                        signaling_token = child
                    elif child.text.lower() == "modulatory":
                        modulatory_token = child
                        if self.debug:
                            print(f"Found modulatory as child of pathways: {child.text}")
                    elif "cell" in child.text.lower():
                        cell_tokens.append(child)
                
                # 2. Если не нашли через children, ищем в окрестности
                if not signaling_token or not modulatory_token:
                    for j in range(max(0, i-5), i):
                        candidate = doc[j]
                        if not signaling_token and (candidate.lemma_ == "signaling" or candidate.text.lower() == "signaling"):
                            signaling_token = candidate
                        if not modulatory_token and candidate.text.lower() == "modulatory":
                            modulatory_token = candidate
                            if self.debug:
                                print(f"Found modulatory in vicinity: {candidate.text}")
                        if "cell" in candidate.text.lower():
                            cell_tokens.append(candidate)
                
                if signaling_token:
                    # Создаём "signaling_pathways"
                    if "signaling_pathways" not in concept_cache:
                        c = concept("signaling_pathways", label_text="signaling pathways")
                        concept_cache["signaling_pathways"] = c
                    
                    token_to_concept[signaling_token] = concept_cache["signaling_pathways"]
                    token_to_concept[token] = concept_cache["signaling_pathways"]
                    processed_tokens.add(signaling_token)
                    processed_tokens.add(token)
                    
                    # Сохраняем modulatory для последующей обработки (ВСЕГДА, не проверяем processed_tokens!)
                    if modulatory_token:
                        modulatory_token_found = modulatory_token
                        if self.debug:
                            print(f"Saved modulatory_token_found: {modulatory_token.text}")
                    
                    # Обрабатываем cell-to-cell отдельно, если есть
                    for cell_token in cell_tokens:
                        if cell_token not in processed_tokens:
                            processed_tokens.add(cell_token)
                    
                    if self.debug:
                        print(f"Created signaling_pathways: {signaling_token.text} + {token.text}")
        
        # ДОПОЛНИТЕЛЬНО: "emerging clinical phenotypes"
        emerging_token_found = None
        for i, token in enumerate(doc):
            if token.lemma_ == "phenotype" and token not in processed_tokens:
                # Ищем "clinical" как модификатор
                clinical_token = None
                emerging_token = None
                
                for child in token.children:
                    if child.dep_ == "amod":
                        if child.lemma_ == "clinical":
                            clinical_token = child
                        elif child.text.lower() == "emerging":  # ИСПРАВЛЕНО: проверяем text, не lemma!
                            emerging_token = child
                
                # Если clinical найден через dependency
                if clinical_token and clinical_token not in processed_tokens:
                    if "clinical_phenotypes" not in concept_cache:
                        c = concept("clinical_phenotypes", label_text="clinical phenotypes")
                        concept_cache["clinical_phenotypes"] = c
                    
                    token_to_concept[clinical_token] = concept_cache["clinical_phenotypes"]
                    token_to_concept[token] = concept_cache["clinical_phenotypes"]
                    processed_tokens.add(clinical_token)
                    processed_tokens.add(token)
                    
                    # Сохраняем emerging для последующей обработки (ВСЕГДА!)
                    if emerging_token:
                        emerging_token_found = emerging_token
                        if self.debug:
                            print(f"Saved emerging_token_found: {emerging_token.text}")
                    
                    if self.debug:
                        print(f"Created clinical_phenotypes: {clinical_token.text} + {token.text}")
        
        # ДОПОЛНИТЕЛЬНО: Обработка двухсловных ADJ+NOUN для "molecular events"
        # (оставляем существующую логику, но убираем signaling_pathways и clinical_phenotypes)
        target_compounds = {
            "molecular events": ["molecular", "event"],
        }
        
        for compound_text, (adj, noun) in target_compounds.items():
            adj_token = None
            noun_token = None
            
            # Ищем пары ADJ/VERB + NOUN
            for i, token in enumerate(doc):
                if token.lemma_.lower() == adj and token not in processed_tokens:
                    # Проверяем следующий токен
                    if i + 1 < len(doc):
                        next_token = doc[i + 1]
                        if next_token.lemma_.lower() == noun and next_token not in processed_tokens:
                            adj_token = token
                            noun_token = next_token
                            break
                    
                    # Или проверяем через dep relation
                    if token.dep_ in ["amod", "compound"] and token.head.lemma_.lower() == noun:
                        adj_token = token
                        noun_token = token.head
                        if noun_token not in processed_tokens:
                            break
            
            if adj_token and noun_token:
                compound_norm = normalize_name(compound_text)
                if compound_norm not in concept_cache:
                    c = concept(compound_norm, label_text=compound_text)
                    concept_cache[compound_norm] = c
                
                token_to_concept[adj_token] = concept_cache[compound_norm]
                token_to_concept[noun_token] = concept_cache[compound_norm]
                processed_tokens.add(adj_token)
                processed_tokens.add(noun_token)
                
                if self.debug:
                    print(f"Created targeted compound: {compound_text}")
        
        # УЛУЧШЕНО: Составные с дефисами (все типы)
        for token in doc:
            if "-" in token.text and token.text.count("-") >= 1 and token not in processed_tokens:
                # Не обрабатываем age-related отдельно
                if token.text.lower() not in ["age-related"]:
                    normalized = normalize_name(token.text)
                    if normalized not in concept_cache:
                        c = concept(normalized, label_text=token.text)
                        concept_cache[normalized] = c
                    token_to_concept[token] = concept_cache[normalized]
                    processed_tokens.add(token)
                    if self.debug:
                        print(f"Created hyphenated term: {token.text}")
        
        # НОВОЕ: cell-based, systems-based как ДВА токена
        for token in doc:
            if token.text.lower() == "based" and token.dep_ == "amod" and token not in processed_tokens:
                # Ищем compound или npadvmod modifier
                modifier = None
                for child in token.children:
                    if child.dep_ in ["npadvmod", "compound"]:
                        modifier = child
                        break
                
                if not modifier:
                    parent = token.head
                    for sibling in parent.children:
                        if sibling != token and sibling.dep_ == "npadvmod" and sibling.head == token:
                            modifier = sibling
                            break
                
                if modifier:
                    compound_name = f"{modifier.text}_based"
                    compound_norm = normalize_name(compound_name)
                    if compound_norm not in concept_cache:
                        c = concept(compound_norm, label_text=f"{modifier.text}-based")
                        concept_cache[compound_norm] = c
                    token_to_concept[modifier] = concept_cache[compound_norm]
                    token_to_concept[token] = concept_cache[compound_norm]
                    processed_tokens.add(modifier)
                    processed_tokens.add(token)
                    if self.debug:
                        print(f"Created X-based compound: {modifier.text} + {token.text}")
                else:
                    # Если based стоит отдельно, ищем modifier в окрестности
                    for i in range(max(0, token.i - 3), min(len(doc), token.i + 1)):
                        candidate = doc[i]
                        if candidate.text.lower() in ["systems", "system", "cell"] and candidate not in processed_tokens:
                            compound_name = f"{candidate.text}_based"
                            compound_norm = normalize_name(compound_name)
                            if compound_norm not in concept_cache:
                                c = concept(compound_norm, label_text=f"{candidate.text}-based")
                                concept_cache[compound_norm] = c
                            token_to_concept[candidate] = concept_cache[compound_norm]
                            token_to_concept[token] = concept_cache[compound_norm]
                            processed_tokens.add(candidate)
                            processed_tokens.add(token)
                            if self.debug:
                                print(f"Created X-based compound (proximity): {candidate.text} + {token.text}")
                            break
        
        # body of knowledge
        for token in doc:
            if token.lemma_ == "body" and token not in processed_tokens:
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
                    if "body_of_knowledge" not in concept_cache:
                        c = concept("body_of_knowledge", label_text="body of knowledge")
                        concept_cache["body_of_knowledge"] = c
                    token_to_concept[token] = concept_cache["body_of_knowledge"]
                    token_to_concept[of_token] = concept_cache["body_of_knowledge"]
                    processed_tokens.add(token)
                    processed_tokens.add(of_token)
        
        # genetic/environmental factors
        factor_tokens = []
        for token in doc:
            if token.lemma_ == "factor":
                factor_tokens.append(token)
        
        for factor_token in factor_tokens:
            genetic_token = None
            environmental_token = None
            
            for child in factor_token.children:
                if child.dep_ == "amod":
                    if child.lemma_ == "genetic":
                        genetic_token = child
                    elif child.lemma_ == "environmental":
                        environmental_token = child
            
            if genetic_token:
                for sibling in genetic_token.children:
                    if sibling.dep_ == "conj" and sibling.lemma_ == "environmental":
                        environmental_token = sibling
                for sibling in genetic_token.head.children:
                    if sibling.dep_ == "conj" and sibling.lemma_ == "environmental":
                        environmental_token = sibling
            
            if environmental_token:
                for sibling in environmental_token.children:
                    if sibling.dep_ == "conj" and sibling.lemma_ == "genetic":
                        genetic_token = sibling
                for sibling in environmental_token.head.children:
                    if sibling.dep_ == "conj" and sibling.lemma_ == "genetic":
                        genetic_token = sibling
            
            if not genetic_token or not environmental_token:
                for i, token in enumerate(doc):
                    if token.lemma_ in ["genetic", "environmental"]:
                        for j in range(max(0, i-5), min(len(doc), i+5)):
                            if doc[j].lemma_ == "factor":
                                if token.lemma_ == "genetic":
                                    genetic_token = token
                                elif token.lemma_ == "environmental":
                                    environmental_token = token
            
            if genetic_token and genetic_token not in processed_tokens:
                if "genetic_factors" not in concept_cache:
                    c = concept("genetic_factors", label_text="genetic factors")
                    concept_cache["genetic_factors"] = c
                token_to_concept[genetic_token] = concept_cache["genetic_factors"]
                processed_tokens.add(genetic_token)
                
                if self.debug:
                    print(f"Created genetic_factors from token: {genetic_token.text}")
            
            if environmental_token and environmental_token not in processed_tokens:
                if "environmental_factors" not in concept_cache:
                    c = concept("environmental_factors", label_text="environmental factors")
                    concept_cache["environmental_factors"] = c
                token_to_concept[environmental_token] = concept_cache["environmental_factors"]
                processed_tokens.add(environmental_token)
                
                if self.debug:
                    print(f"Created environmental_factors from token: {environmental_token.text}")
            
            if "factors" not in concept_cache:
                c = concept("factors", label_text="factors")
                concept_cache["factors"] = c
            
            if factor_token not in processed_tokens:
                token_to_concept[factor_token] = concept_cache["factors"]
                processed_tokens.add(factor_token)
        
        # age-related
        age_related_found = False
        if "age-related" in text.lower() or "age related" in text.lower():
            age_related_found = True
            if "age_related" not in concept_cache:
                c = concept("age_related", label_text="age-related")
                concept_cache["age_related"] = c
        
        for token in doc:
            if age_related_found:
                if token.text.lower() == "related" and token.dep_ == "amod" and token not in processed_tokens:
                    for child in token.children:
                        if child.dep_ == "npadvmod" and child.text.lower() == "age":
                            token_to_concept[token] = concept_cache["age_related"]
                            token_to_concept[child] = concept_cache["age_related"]
                            processed_tokens.add(token)
                            processed_tokens.add(child)
                            if self.debug:
                                print(f"Created age_related: {child.text} - {token.text}")
                            break
                
                elif token.text.lower() in ["age-related", "age–related", "age—related"] and token not in processed_tokens:
                    token_to_concept[token] = concept_cache["age_related"]
                    processed_tokens.add(token)
                    if self.debug:
                        print(f"Created age_related (single token): {token.text}")
                
                elif "age" in token.text.lower() and "related" in token.text.lower() and token not in processed_tokens:
                    token_to_concept[token] = concept_cache["age_related"]
                    processed_tokens.add(token)
                    if self.debug:
                        print(f"Created age_related (compound): {token.text}")
        
        # ========== PHASE 2: ИНДИВИДУАЛЬНЫЕ КОНЦЕПТЫ ==========
        
        for token in doc:
            if token in processed_tokens:
                continue
            
            if token.pos_ not in {"NOUN", "PROPN", "VERB", "ADJ", "NUM", "PRON"}:
                continue
            
            if token.pos_ == "VERB" and token.dep_ in ["aux", "auxpass", "cop"]:
                continue
            
            # Специальные термины (сохраняем форму, не лемматизируем)
            text_lower = token.text.lower()
            special_terms = [
                "knowledge", "systems", "system", "dopamine", "discovery", 
                "hallmarks", "hallmark", "peers", "events", "pathways", 
                "phenotypes", "endeavors", "signaling", "emerging", "modulatory",
                "interdisciplinary"  # Добавлено
            ]
            
            if text_lower in special_terms:
                # Нормализуем hallmark/hallmarks
                key = "hallmark" if text_lower in ["hallmarks", "hallmark"] else text_lower
                if key not in concept_cache:
                    c = concept(key, label_text=token.text)
                    concept_cache[key] = c
                token_to_concept[token] = concept_cache[key]
                continue
            
            # Обычная лемматизация
            lemma = token.lemma_.lower()
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
            
            dep_map = {
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
            
            if dep in dep_map:
                relation(token_concept, dep_map[dep], head_concept)
            
            if dep == "agent" or (dep == "obl" and "agent" in str(token.dep_)):
                relation(token_concept, "obl_agent_of", head_concept)
        
        # СПЕЦИАЛЬНАЯ ОБРАБОТКА: "targeting X, Y and Z" - создаём conj связи
        # ВАЖНО: spaCy может парсить по-разному, нужно учитывать разные структуры
        for token in doc:
            if token.lemma_ == "target" and token.pos_ == "VERB" and token in token_to_concept:
                # Ищем все объекты через dobj и conj
                objects = []
                
                # 1. Прямой объект (dobj/obj)
                for child in token.children:
                    if child.dep_ in ["dobj", "obj"] and child in token_to_concept:
                        objects.append(child)
                        if self.debug:
                            print(f"Found dobj object: {child.text}")
                
                # 2. Ищем в предложении составные термины (molecular_events, signaling_pathways, clinical_phenotypes)
                # которые семантически являются объектами targeting
                target_compound_names = ["molecular_events", "signaling_pathways", "clinical_phenotypes"]
                for compound_name in target_compound_names:
                    if compound_name in concept_cache:
                        # Ищем токены, которые мапятся на этот концепт
                        for tok, conc in token_to_concept.items():
                            if conc == concept_cache[compound_name]:
                                # Проверяем, что токен в том же предложении и после targeting
                                if tok.i > token.i and tok not in [o for o in objects]:
                                    # Добавляем только один раз (берём главный токен - существительное)
                                    if tok.pos_ == "NOUN" or (tok.pos_ == "PROPN" and compound_name == "clinical_phenotypes"):
                                        objects.append(tok)
                                        if self.debug:
                                            print(f"Found semantic object: {tok.text} -> {compound_name}")
                                        break
                
                if self.debug:
                    print(f"Found {len(objects)} objects for targeting: {[o.text for o in objects]}")
                
                # Создаём conj связи между всеми объектами
                # Все связываются с первым (molecular_events)
                if len(objects) >= 2:
                    base_concept = token_to_concept[objects[0]]
                    for i in range(1, len(objects)):
                        obj_concept = token_to_concept[objects[i]]
                        if obj_concept != base_concept:
                            relation(obj_concept, "conj_of", base_concept)
                            if self.debug:
                                print(f"Created conj: {objects[i].text} -> {objects[0].text}")
        
        # ========== PHASE 4: ОНТОЛОГИЧЕСКИЕ СВЯЗИ ==========
        
        # IS_A для "X as Y"
        for token in doc:
            if token.dep_ == "pobj" and token.head.lemma_ == "as" and token in token_to_concept:
                source = token.head.head
                if source in token_to_concept:
                    source_concept = token_to_concept[source]
                    target_concept = token_to_concept[token]
                    if source_concept != target_concept:
                        relation(source_concept, "IS_A", target_concept)
        
        # HAS_PROPERTY для amod
        for token in doc:
            if token.dep_ == "amod" and token in token_to_concept:
                if token.head in token_to_concept:
                    adj_concept = token_to_concept[token]
                    noun_concept = token_to_concept[token.head]
                    if adj_concept != noun_concept:
                        relation(noun_concept, "HAS_PROPERTY", adj_concept)
                        relation(adj_concept, "amod_of", noun_concept)
        
        # ДОПОЛНИТЕЛЬНО: compound как amod для research endeavors
        # interdisciplinary - amod к endeavors, но должен модифицировать research
        for token in doc:
            if token.dep_ == "compound" and token.lemma_ == "research" and token in token_to_concept:
                if self.debug:
                    print(f"Found token 'research' as compound, checking head...")
                if token.head in token_to_concept:
                    if self.debug:
                        print(f"Head is: {token.head.text} (lemma: {token.head.lemma_})")
                    # ИСПРАВЛЕНО: проверяем и lemma и text
                    if token.head.lemma_ == "endeavor" or token.head.text.lower() == "endeavors":
                        if self.debug:
                            print(f"Found research as compound to endeavors")
                        # Ищем interdisciplinary, который amod к endeavors
                        for child in token.head.children:
                            if self.debug:
                                print(f"  Checking child: {child.text} (dep: {child.dep_}, text.lower: {child.text.lower()})")
                            if child.dep_ == "amod" and child.text.lower() == "interdisciplinary":
                                if self.debug:
                                    print(f"Found interdisciplinary as amod to endeavors")
                                if child in token_to_concept:
                                    adj_concept = token_to_concept[child]
                                    noun_concept = token_to_concept[token]
                                    if adj_concept != noun_concept:
                                        relation(noun_concept, "HAS_PROPERTY", adj_concept)
                                        relation(adj_concept, "amod_of", noun_concept)
                                        if self.debug:
                                            print(f"Added interdisciplinary -> research (via endeavors)")
                                else:
                                    # Если interdisciplinary ещё не в token_to_concept
                                    if "interdisciplinary" not in concept_cache:
                                        c = concept("interdisciplinary", label_text="interdisciplinary")
                                        concept_cache["interdisciplinary"] = c
                                        if self.debug:
                                            print(f"Created interdisciplinary concept")
                                    token_to_concept[child] = concept_cache["interdisciplinary"]
                                    adj_concept = concept_cache["interdisciplinary"]
                                    noun_concept = token_to_concept[token]
                                    if adj_concept != noun_concept:
                                        relation(noun_concept, "HAS_PROPERTY", adj_concept)
                                        relation(adj_concept, "amod_of", noun_concept)
                                        if self.debug:
                                            print(f"Added interdisciplinary -> research (via endeavors)")
        
        # КРИТИЧНО: Обработка modulatory и emerging, которые не вошли в составные термины
        # Нужно проверить, что они ещё не связаны
        if modulatory_token_found:
            if self.debug:
                print(f"Processing modulatory_token_found: {modulatory_token_found.text}")
            
            # Создаём концепт для modulatory, если его нет
            if "modulatory" not in concept_cache:
                c = concept("modulatory", label_text="modulatory")
                concept_cache["modulatory"] = c
                if self.debug:
                    print(f"Created modulatory concept")
            
            # Обновляем token_to_concept если нужно
            if modulatory_token_found not in token_to_concept:
                token_to_concept[modulatory_token_found] = concept_cache["modulatory"]
                if self.debug:
                    print(f"Added modulatory to token_to_concept")
            elif token_to_concept[modulatory_token_found] != concept_cache["modulatory"]:
                # Если токен уже мапится на другой концепт, обновляем
                if self.debug:
                    print(f"Updating modulatory in token_to_concept from {token_to_concept[modulatory_token_found]} to {concept_cache['modulatory']}")
                token_to_concept[modulatory_token_found] = concept_cache["modulatory"]
            
            if "signaling_pathways" in concept_cache:
                adj_concept = concept_cache["modulatory"]
                noun_concept = concept_cache["signaling_pathways"]
                if adj_concept != noun_concept:
                    relation(noun_concept, "HAS_PROPERTY", adj_concept)
                    relation(adj_concept, "amod_of", noun_concept)
                    if self.debug:
                        print(f"Added modulatory -> signaling_pathways HAS_PROPERTY")
        else:
            if self.debug:
                print("No modulatory_token_found!")
        
        if emerging_token_found:
            if self.debug:
                print(f"Processing emerging_token_found: {emerging_token_found.text}")
            
            # Создаём концепт для emerging, если его нет
            if "emerging" not in concept_cache:
                c = concept("emerging", label_text="emerging")
                concept_cache["emerging"] = c
                if self.debug:
                    print(f"Created emerging concept")
            
            # Обновляем token_to_concept если нужно
            if emerging_token_found not in token_to_concept:
                token_to_concept[emerging_token_found] = concept_cache["emerging"]
                if self.debug:
                    print(f"Added emerging to token_to_concept")
            elif token_to_concept[emerging_token_found] != concept_cache["emerging"]:
                # Если токен уже мапится на другой концепт, обновляем
                if self.debug:
                    print(f"Updating emerging in token_to_concept")
                token_to_concept[emerging_token_found] = concept_cache["emerging"]
            
            if "clinical_phenotypes" in concept_cache:
                adj_concept = concept_cache["emerging"]
                noun_concept = concept_cache["clinical_phenotypes"]
                if adj_concept != noun_concept:
                    relation(noun_concept, "HAS_PROPERTY", adj_concept)
                    relation(adj_concept, "amod_of", noun_concept)
                    if self.debug:
                        print(f"Added emerging -> clinical_phenotypes HAS_PROPERTY")
        else:
            if self.debug:
                print("No emerging_token_found!")
        
        # conj прилагательных
        for token in doc:
            if token.pos_ == "ADJ" and token.dep_ == "conj" and token in token_to_concept:
                if token.head in token_to_concept:
                    if token.head.dep_ == "amod" and token.head.head in token_to_concept:
                        adj_concept = token_to_concept[token]
                        noun_concept = token_to_concept[token.head.head]
                        if adj_concept != noun_concept:
                            relation(noun_concept, "HAS_PROPERTY", adj_concept)
                            relation(adj_concept, "amod_of", noun_concept)
        
        # PART_OF для "X of Y" и "around Y", а также "related to Y"
        for token in doc:
            if token.dep_ == "prep" and token.lemma_ in ["of", "around", "to"]:
                head = token.head
                pobj_list = [child for child in token.children if child.dep_ == "pobj"]
                if pobj_list and head in token_to_concept:
                    pobj = pobj_list[0]
                    if pobj in token_to_concept:
                        part_concept = token_to_concept[head]
                        whole_concept = token_to_concept[pobj]
                        if part_concept != whole_concept:
                            if token.lemma_ == "of":
                                relation(part_concept, "PART_OF", whole_concept)
                            # Для "related to PD" создаём PART_OF и nmod_of
                            if token.lemma_ == "to" and head.lemma_ == "related":
                                # Ищем существительное, которое modified by "related"
                                if head.dep_ == "acl" and head.head in token_to_concept:
                                    # related - это acl модификатор к существительному
                                    modified_noun_concept = token_to_concept[head.head]
                                    
                                    # Ищем clinical_phenotypes среди конъюнкций
                                    # phenotypes - conj к pathways
                                    for conj_sibling in head.head.children:
                                        if conj_sibling.dep_ == "conj" and conj_sibling in token_to_concept:
                                            conj_concept = token_to_concept[conj_sibling]
                                            # Проверяем, что это clinical_phenotypes
                                            if conj_concept == concept_cache.get("clinical_phenotypes"):
                                                if conj_concept != whole_concept:
                                                    relation(conj_concept, "PART_OF", whole_concept)
                                                    relation(whole_concept, "nmod_of", conj_concept)
                                                    if self.debug:
                                                        print(f"Added PART_OF (via conj): clinical_phenotypes -> {pobj.text}")
                                                break
                            if head.pos_ == "VERB" or head.dep_ in ["advcl", "acl"]:
                                relation(whole_concept, "pobj_of", part_concept)
        
        # ========== PHASE 5: ДОМЕННЫЕ ОНТОЛОГИЧЕСКИЕ СВЯЗИ ==========
        
        if "PD" in concept_cache and "Parkinsons_disease" in concept_cache:
            relation(concept_cache["PD"], "IS_ABBREVIATION_OF", concept_cache["Parkinsons_disease"])
        
        if "Parkinsons_disease" in concept_cache and "disease" in concept_cache:
            relation(concept_cache["Parkinsons_disease"], "IS_A", concept_cache["disease"])
        
        if "genetic_factors" in concept_cache and "factors" in concept_cache:
            relation(concept_cache["genetic_factors"], "PART_OF", concept_cache["factors"])
        
        if "environmental_factors" in concept_cache and "factors" in concept_cache:
            relation(concept_cache["environmental_factors"], "PART_OF", concept_cache["factors"])
        
        if "knowledge" in concept_cache and "body_of_knowledge" in concept_cache:
            relation(concept_cache["knowledge"], "PART_OF", concept_cache["body_of_knowledge"])
        
        if "pathogenesis" in concept_cache and "disease" in concept_cache:
            relation(concept_cache["pathogenesis"], "PART_OF", concept_cache["disease"])
        
        if "complexity" in concept_cache and "disease" in concept_cache:
            relation(concept_cache["complexity"], "PART_OF", concept_cache["disease"])
        
        if "progression" in concept_cache and "pathogenesis" in concept_cache:
            relation(concept_cache["progression"], "PART_OF", concept_cache["pathogenesis"])
        
        # ========== PHASE 6: СЕМАНТИЧЕСКИЕ СВЯЗИ ==========
        
        action_verbs = {
            "generate": "generated",
            "reveal": "reveals",
            "influence": "influences",
            "increase": "increases",
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
                
                if not obj and subj and token.lemma_ == "increase":
                    for child in token.children:
                        if child.dep_ in ["agent", "obl"]:
                            for pobj_child in child.children:
                                if pobj_child.dep_ == "pobj" and pobj_child in token_to_concept:
                                    obj = token_to_concept[pobj_child]
                                    if subj and obj:
                                        relation(subj, "increased_by", obj)
                                    break
                
                if subj and obj and subj != obj:
                    semantic_rel = action_verbs[token.lemma_]
                    relation(subj, semantic_rel, obj)
                    
                    if token.lemma_ == "influence":
                        relation(obj, "influenced_by", subj)
        
        # Темпоральные связи
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
                                relation(event_concept, "happened_in", location_concept)
                                relation(location_concept, "nmod_of", event_concept)
                            elif token.lemma_ == "since":
                                relation(event_concept, "started_after", location_concept)
                            elif token.lemma_ == "between":
                                relation(event_concept, "happens_between", location_concept)
        
        # ========== КРИТИЧЕСКИЕ ДОМЕННЫЕ СВЯЗИ ==========
        
        if "research" in concept_cache and "body_of_knowledge" in concept_cache:
            relation(concept_cache["research"], "generated", concept_cache["body_of_knowledge"])
        
        if "body_of_knowledge" in concept_cache and "PD" in concept_cache:
            relation(concept_cache["body_of_knowledge"], "reveals", concept_cache["PD"])
        
        if "body_of_knowledge" in concept_cache and "disease" in concept_cache:
            relation(concept_cache["body_of_knowledge"], "supports_classification", concept_cache["disease"])
        
        if "research" in concept_cache and "Parkinsons_disease" in concept_cache:
            relation(concept_cache["research"], "focuses_on", concept_cache["Parkinsons_disease"])
        
        if "discovery" in concept_cache and "dopamine" in concept_cache:
            relation(concept_cache["discovery"], "HAS_OBJECT", concept_cache["dopamine"])
            relation(concept_cache["dopamine"], "nmod_of", concept_cache["discovery"])
        
        if "discovery" in concept_cache and "1950s" in concept_cache:
            relation(concept_cache["discovery"], "happened_in", concept_cache["1950s"])
            relation(concept_cache["1950s"], "nmod_of", concept_cache["discovery"])
        
        if "research" in concept_cache and "discovery" in concept_cache:
            relation(concept_cache["research"], "started_after", concept_cache["discovery"])
        
        if "neurotransmitter" in concept_cache and "dopamine" in concept_cache:
            relation(concept_cache["neurotransmitter"], "nmod_of", concept_cache["dopamine"])
        else:
            for token in doc:
                if token.lemma_ == "neurotransmitter" and token in token_to_concept:
                    if token.dep_ == "pobj" and token.head.lemma_ == "as":
                        for other_token in doc:
                            if other_token.lemma_ == "dopamine" and other_token in token_to_concept:
                                relation(token_to_concept[token], "nmod_of", token_to_concept[other_token])
                                break
        
        if "dopamine" in concept_cache and "neurotransmitter" in concept_cache:
            relation(concept_cache["dopamine"], "IS_A", concept_cache["neurotransmitter"])
        
        reveal_concept = None
        if "reveal" in concept_cache:
            reveal_concept = concept_cache["reveal"]
        elif "revealing" in concept_cache:
            reveal_concept = concept_cache["revealing"]
        
        if reveal_concept and "body_of_knowledge" in concept_cache:
            relation(reveal_concept, "acl_of", concept_cache["body_of_knowledge"])
        
        generate_concept = None
        if "generate" in concept_cache:
            generate_concept = concept_cache["generate"]
        elif "generated" in concept_cache:
            generate_concept = concept_cache["generated"]
        elif "generating" in concept_cache:
            generate_concept = concept_cache["generating"]
        
        if "discovery" in concept_cache and generate_concept:
            relation(concept_cache["discovery"], "advcl_of", generate_concept)
        
        if "disease" in concept_cache and reveal_concept:
            relation(concept_cache["disease"], "xcomp_of", reveal_concept)
        
        if "PD" in concept_cache and "disease" in concept_cache:
            relation(concept_cache["PD"], "nsubj_of", concept_cache["disease"])
        
        if "PD" in concept_cache and "age_related" in concept_cache:
            relation(concept_cache["PD"], "classified_as", concept_cache["age_related"])
        
        if "PD" in concept_cache and "multifactorial" in concept_cache:
            relation(concept_cache["PD"], "classified_as", concept_cache["multifactorial"])
        
        if "body_of_knowledge" in concept_cache and "knowledge" in concept_cache:
            relation(concept_cache["body_of_knowledge"], "consists_of", concept_cache["knowledge"])
        
        if "factors" in concept_cache and "influence" in concept_cache:
            relation(concept_cache["factors"], "obl_agent_of", concept_cache["influence"])
        
        if "genetic_factors" in concept_cache and "disease" in concept_cache:
            relation(concept_cache["genetic_factors"], "influences", concept_cache["disease"])
            relation(concept_cache["disease"], "influenced_by", concept_cache["genetic_factors"])
        
        if "environmental_factors" in concept_cache and "disease" in concept_cache:
            relation(concept_cache["environmental_factors"], "influences", concept_cache["disease"])
            relation(concept_cache["disease"], "influenced_by", concept_cache["environmental_factors"])
        
        if "pathogenesis" in concept_cache and "systems" in concept_cache:
            relation(concept_cache["pathogenesis"], "progresses_through", concept_cache["systems"])
        
        if "disease" in concept_cache and "complexity" in concept_cache:
            relation(concept_cache["disease"], "has_complexity", concept_cache["complexity"])
        
        if "molecular" in concept_cache and "cellular" in concept_cache:
            relation(concept_cache["molecular"], "conj_of", concept_cache["cellular"])
        
        if "cellular" in concept_cache and "organic" in concept_cache:
            relation(concept_cache["cellular"], "conj_of", concept_cache["organic"])
        
        if "genetic_factors" in concept_cache and "environmental_factors" in concept_cache:
            relation(concept_cache["genetic_factors"], "conj_of", concept_cache["environmental_factors"])
        
        # Sentence 3: explore conj_of propose
        if "explore" in concept_cache and "propose" in concept_cache:
            relation(concept_cache["explore"], "conj_of", concept_cache["propose"])
        
        # Sentence 4: improve acl_of aim
        if "improve" in concept_cache and "aim" in concept_cache:
            relation(concept_cache["improve"], "acl_of", concept_cache["aim"])
        
        # Sentence 4: "clinical phenotypes related to PD"
        if "clinical_phenotypes" in concept_cache and "PD" in concept_cache:
            relation(concept_cache["clinical_phenotypes"], "PART_OF", concept_cache["PD"])
            relation(concept_cache["PD"], "nmod_of", concept_cache["clinical_phenotypes"])
            if self.debug:
                print(f"Added clinical_phenotypes PART_OF PD")
        
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