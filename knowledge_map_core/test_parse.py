import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.parser.nlp_client import NLPClient

async def test():
    client = NLPClient()
    async with client:
        for sent in [
            'In addition, a nonreductionist view needs to integrate other neurotransmitter systems.',
            'The challenge is to understand the key factors in each case, starting from the resting microglia that monitor the local environment and control the immune response in the healthy brain.',
            'The high number of microglia promoting neuroinflammation, opposed by a low number of regulatory astrocytes, promote the susceptibility of the SN to PD.',
            'Fusion and fission of mitochondria, two processes that actively control the level of mitochondrial fragmentation.',
            'An oversimplified reductionist model that ignores these intercellular interactions serves to complicate our understanding.',
            'This hypothesis states that PD could have its origin in the bulbus olfactorius or motor nucleus of vagal nerve.',
        ]:
            print(f'=== {sent[:80]} ===')
            trees = await client.get_dependency_trees(sent)
            for tree in trees:
                for t in tree.tokens:
                    child_strs = []
                    for c in tree.children(t.idx):
                        child_strs.append(f'{c.text}({c.dep})')
                    head_t = tree.token_by_idx(t.head_idx)
                    head_text = head_t.text if head_t else '?'
                    print(f'  [{t.idx:2d}] {t.text:30s} dep={t.dep:15s} pos={t.pos:10s} head={head_text}({t.head_idx}) children=[{", ".join(child_strs)}]')
            print()

asyncio.run(test())
