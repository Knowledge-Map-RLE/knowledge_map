"""Автономный CLI полного скрытого графа и инвентаризации структурных мотивов."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.semantic_operator_graph import SealSemanticOperatorGraph
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE = ('domain/semantic_operator_graph.py', 'application/semantic_operator_graph.py',
        'domain/operator_frame_routing.py',
        'domain/comparison_normalization.py', 'domain/whole_map_context.py', 'domain/development_prediction.py',
        'domain/article_maps.py', 'application/compare_article_maps.py', 'infrastructure/free_prediction_snapshots.py',
        'infrastructure/development_prediction_store.py', 'infrastructure/immutable_files.py',
        'tools/run_free_prediction.py', 'tools/build_semantic_operator_graph.py')


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--sources', required=True)
    parser.add_argument('--context-audit', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args(); disable_network()
    raw = Path(args.sources).read_bytes(); manifest = json.loads(raw)
    audit = json.loads(Path(args.context_audit).read_bytes())
    maps = FileForecastMaps(manifest['sources']); store = FilePredictionStore(args.output)
    api = Path(__file__).resolve().parents[1]; implementation = {name: sha256((api / name).read_bytes()).hexdigest() for name in CODE}
    result = SealSemanticOperatorGraph(maps, store).execute([r['reference'] for r in manifest['sources']], maps.owner,
        {r['reference']['article_id']: r['family'] for r in manifest['sources']},
        {**manifest['metadata'], 'model_calls': 0, 'source_manifest_sha256': sha256(raw).hexdigest(),
         'source_dates': {r['reference']['article_id']: r['published_on'] for r in manifest['sources']}}, implementation, audit)
    folder = store.path(result['run_id'])
    write_immutable(folder / 'source-manifest.json', raw); write_immutable(folder / 'context-audit.json', store.encode(audit))
    write_immutable(folder / 'reads.json', store.encode({'reads': maps.reads, 'network_disabled': True, 'model_calls': 0, 'target_read': False}))
    for name in CODE: write_immutable(folder / 'implementation' / name, (api / name).read_bytes())
    graph = result['semantic_graph']; motifs = result['motif_inventory']; routing = result['operator_routing']
    print(json.dumps({'run_id': result['run_id'], 'blocks': graph['canonical_blocks'], 'statements': graph['statement_count'],
        'nodes': len(graph['nodes']), 'edges': len(graph['edges']), 'cyclic_components': len(graph['hidden_semantic_cycles']),
        'patterns': len(motifs['patterns']), 'patterns_in_multiple_publications': motifs['patterns_in_multiple_publications'],
        'routing_counts': routing['counts'], 'family_patterns_in_multiple_publications': result['family_motif_inventory']['patterns_in_multiple_publications'],
        'predictions': 0, 'scientific_success': False}))


if __name__ == '__main__': main()
