"""Debug article sentence 187 matching."""
import asyncio
import sys
sys.path.insert(0, "D:\\Knowledge_Map\\knowledge_map_core")
from src.services.pipeline import Pipeline
from tests.articles.conftest import find_matching_statement, Triplet, load_article_text, split_sentences


async def main():
    # Load article and find sentence 187
    text = load_article_text("the hallmarks of parkinsons disease")
    sentences = split_sentences(text)[:222]
    
    print(f"Total sentences: {len(sentences)}")
    
    target_sentence = None
    for i, s in enumerate(sentences):
        if "neuroinflammation is at least" in s:
            target_sentence = s
            print(f"Sentence {i}: {s}")
            break
    
    if not target_sentence:
        print("Target sentence not found!")
        return
    
    pipeline = Pipeline()
    resp = await pipeline.process(target_sentence, doc_id="debug")
    
    statements = resp.get("statements", [])
    concepts = {c.id: c.text for c in resp.get("concepts", [])}
    
    print(f"\nPipeline output ({len(statements)} statements):")
    for stmt in statements:
        subj = concepts.get(stmt.subject_id, "?")
        obj = concepts.get(stmt.object_id, "?")
        print(f"  [{stmt.type}] {subj} -> {stmt.predicate} -> {obj}")
    
    # Test matching
    # This is the GT triplet
    class FakeEntry:
        def __init__(self, subj, pred, obj):
            self.subject = subj
            self.predicate = pred
            self.object = obj
        def resolved_triplet(self, lookup):
            return Triplet(self.subject, self.predicate, self.object)
    
    entry = FakeEntry("neuroinflammation", "be", "modulator of disease progression in PD")
    result = find_matching_statement(entry.resolved_triplet({}), [resp])
    print(f"\nGT match: {result} (expected: True)")
    
    # Also check: what about the response with no statements?
    print(f"\nHas tree: {resp.get('tree') is not None}")


if __name__ == "__main__":
    asyncio.run(main())
