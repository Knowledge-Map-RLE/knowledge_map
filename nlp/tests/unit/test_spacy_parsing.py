import spacy
nlp = spacy.load("en_core_web_sm")

text = "revealing PD to be an age-related multifactorial disease"
doc = nlp(text)

for token in doc:
    print(f"{token.text:20} {token.pos_:10} {token.dep_:15} HEAD: {token.head.text}")