"""Фиксация аналогических гипотез до доступа к будущим исходам."""
from datetime import date

from application.compare_article_maps import validate_reference
from domain.article_maps import fingerprint,require,ArticleMapNotFound
from domain.mechanistic_opportunities import generate,VERSION,LIMITS
from domain.whole_map_forecast import project
from domain.whole_map_ablation import known_baselines
from domain.whole_map_input_audit import audit_corpus


class SealMechanisticOpportunities:
    def __init__(self,maps,store):self.maps,self.store=maps,store

    def execute(self,sources,families,owner,metadata,implementation,audit):
        require(len(sources)>=2 and len({r['article_id'] for r in sources})==len(sources),'Explicit distinct source maps required')
        require(metadata.get('question') is None,'Free forecast must not use a question')
        cutoff=metadata['training_cutoff'];dates=metadata['source_dates']
        require(date.fromisoformat(cutoff).isoformat()==cutoff and set(dates)=={r['article_id'] for r in sources},'Exact dated source registry required')
        require(all(date.fromisoformat(v).isoformat()==v and v<=cutoff for v in dates.values()),'Future source forbidden')
        require(set(families)==set(dates),'Explicit source families required')
        maps=[]
        for ref in sources:
            validate_reference(ref);m=self.maps.get(ref['article_id'],ref['pipeline_id'],owner,ref['run_id'])
            if m is None:raise ArticleMapNotFound('Mechanistic source missing')
            require(m['article_id']==ref['article_id'] and m['run_id']==ref['run_id'],'Mechanistic source identity differs')
            maps.append(m)
        require(len({m['source']['sha256'] for m in maps})==len(maps),'Duplicate source is not independent evidence')
        binding={'sources':sources,'families':families,'metadata':metadata,'map_hashes':[fingerprint(m) for m in maps],
                 'version':VERSION,'limits':LIMITS,'audit_sha256':fingerprint(audit),'implementation':implementation}
        run=fingerprint(binding);previous=self.store.read_seal(run)
        if previous is not None:
            require(previous['binding']==binding,'Immutable mechanistic binding differs');return previous
        result=generate(maps,audit)
        records,_,_=project(maps);baseline,diagnostic=known_baselines(records,families,LIMITS['candidate_limit'])
        result['known_baselines']=baseline;result['baseline_diagnostics']=diagnostic
        artifact={'run_id':run,'binding':binding,'input_corpus_audit':audit_corpus(maps,metadata),**result}
        self.store.seal(run,artifact);return self.store.read_seal(run)
