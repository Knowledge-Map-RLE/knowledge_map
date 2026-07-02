import asyncio
import sys
sys.path.insert(0, 'D:\\Knowledge_Map\\knowledge_map_core')

from src.services.pipeline import Pipeline

async def test_sentence(sent: str):
    pipeline = Pipeline()
    resp = await pipeline.process(sent, doc_id='test')
    print(f'Sentence: {sent[:80]}')
    print(f'Total statements: {resp["total_statements"]}')
    concepts = {}
    for c in resp['concepts']:
        if hasattr(c, 'id'):
            concepts[c.id] = c.normalized_text or c.text
        else:
            concepts[c.get('id')] = c.get('normalized_text') or c.get('text')
    for stmt in resp['statements']:
        sid = stmt.subject_id if hasattr(stmt, 'subject_id') else stmt.get('subject_id')
        oid = stmt.object_id if hasattr(stmt, 'object_id') else stmt.get('object_id')
        pred = stmt.predicate if hasattr(stmt, 'predicate') else stmt.get('predicate')
        subj = concepts.get(sid, '?')
        obj = concepts.get(oid, '?')
        print(f'  {subj} -> {pred} -> {obj}')
    print()

async def main():
    await test_sentence('The challenge is to understand the key factors in each case, starting from the resting microglia that monitor the local environment and control the immune response in the healthy brain.')
    await test_sentence('An oversimplified reductionist model that ignores these intercellular interactions serves to complicate our understanding.')
    await test_sentence('In addition, a nonreductionist view needs to integrate other neurotransmitter systems, nonmotor symptoms and clinical phenotypes in order to understand global features of PD.')

asyncio.run(main())
