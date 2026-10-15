"""Неизменяемый полный семантический срез читает только явно выбранные версии карт."""
from datetime import date

from application.compare_article_maps import validate_reference
from domain.article_maps import require, fingerprint, ArticleMapNotFound
from domain.semantic_operator_graph import build_graph, inventory_patterns, VERSION, LIMITS
from domain.operator_frame_routing import route_graph, family_motifs


class SealSemanticOperatorGraph:
    def __init__(self, maps, snapshots):
        self.maps, self.snapshots = maps, snapshots

    def execute(self, references, owner, families, metadata, implementation, context_audit=None):
        require(len(references) >= 2 and len({r['article_id'] for r in references}) == len(references), 'Explicit distinct map registry required')
        require(metadata['question'] is None and metadata['model_calls'] == 0, 'Source-only free analysis required')
        cutoff = metadata['training_cutoff']; dates = metadata['source_dates']
        require(date.fromisoformat(cutoff).isoformat() == cutoff and set(dates) == set(families) == {r['article_id'] for r in references},
                'Exact source dates and families required')
        require(all(date.fromisoformat(d).isoformat() == d and d <= cutoff for d in dates.values()), 'Future source forbidden')
        maps = []
        for ref in references:
            validate_reference(ref); m = self.maps.get(ref['article_id'], ref['pipeline_id'], owner, ref['run_id'])
            if m is None: raise ArticleMapNotFound('Semantic source missing')
            require(m['article_id'] == ref['article_id'] and m['run_id'] == ref['run_id'], 'Semantic map identity differs')
            maps.append(m)
        binding = {'references': references, 'map_hashes': [fingerprint(m) for m in maps], 'families': families,
                   'metadata': metadata, 'implementation': implementation, 'version': VERSION, 'limits': LIMITS,
                   'context_audit_sha256': fingerprint(context_audit)}
        run = fingerprint(binding); previous = self.snapshots.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Semantic snapshot binding differs'); return previous
        graph = build_graph(maps, context_audit)
        patterns = inventory_patterns(graph, families)
        routing = route_graph(graph)
        family_inventory = family_motifs(graph, routing, families)
        artifact = {'run_id': run, 'binding': binding, 'semantic_graph': graph, 'motif_inventory': patterns,
                    'operator_routing': routing, 'family_motif_inventory': family_inventory,
                    'model_calls': 0, 'target_read': False, 'scientific_success': False, 'graph_advantage_demonstrated': False}
        self.snapshots.seal(run, artifact)
        return self.snapshots.read_seal(run)
