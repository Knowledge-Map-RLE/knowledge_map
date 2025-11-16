import spacy
from spacy.tokens import Doc, Token, Span

import pandas as pd

nlp = spacy.load("en_core_web_trf")


text = """Since the discovery of dopamine as a neurotransmitter in the 1950s, Parkinson's disease (PD) research has generated a rich and complex body of knowledge, revealing PD to be an age-related multifactorial disease, influenced by both genetic and environmental factors. The tremendous complexity of the disease is increased by a nonlinear progression of the pathogenesis between molecular, cellular and organic systems. In this minireview, we explore the complexity of PD and propose a systems-based approach, organizing the available information around cellular disease hallmarks. We encourage our peers to adopt this cell-based view with the aim of improving communication in interdisciplinary research endeavors targeting the molecular events, modulatory cell-to-cell signaling pathways and emerging clinical phenotypes related to PD."""

text = "The house was built by Jack."

doc = nlp(text)

print('Исходный текст:')
print(doc)
print()

sentence = [sent for sent in doc.sents][0]
print('Предложение:')
print(sentence)
print()

# NER сущности
print(f'NER: {sentence.ents}')

def translate_rus(pos_or_dep: str) -> str:
    match pos_or_dep:
        case 'VERB': return 'глагол'
        case 'AUX': return 'вспомогательный_глагол'
        case 'NOUN': return 'существительное'
        case 'DET': return 'определитель'
        case 'ADP': return 'предлог'
        case 'PROPN': return 'имя_собственное'
        case 'ROOT': return 'КОРЕНЬ'
        case 'det': return 'связь_определитель'
        case 'nsubjpass': return 'подлежащее_страдательный_залог'
        case 'auxpass': return 'вспомогательный_глагол_страдательного_залога'
        case 'agent': return 'агент'
        case 'pobj': return 'объект_предлога'
    return pos_or_dep

for token in sentence:
    # Получение в spaCy
    # получение_расшифровка = [
    #     ['token.pos_', 'Part of Speech', 'Часть речи'],
    #     'token.tag_', # И дальше продолжить ❗
    #     'token.dep_',
    #     'token.head.text',
    #     'token.children',
    #     'child.text',
    #     'token.morph.to_json()',
    #     '',
    #     '',
    # ]

    # Части речи
    # print(f'{token}\t{token.pos_}')
    # print(f'{token}\t{token.pos_}\t{token.tag_}')
    # print(f'{token}\t{token.tag_}')

    # Синтаксические связи
    # print(f'({token.head}) {token.head.pos_}-{token.dep_}→{token.pos_} ({token})')
    print(f'({translate_rus(token.head.text)}) {translate_rus(token.head.pos_)}-{translate_rus(token.dep_)}→{translate_rus(token.pos_)} ({translate_rus(token.text)})')
    
    # print(f'{token}\t{token.head.text}')
    # print(f'{token}\t{[child.text for child in token.children]}')

    

    # Морфология
    # print(f'{token}\t{token.morph.to_json()}')

# print(pd.DataFrame({
#     'token': [1, 2],
#     'token_name': [3, 2],
# }))