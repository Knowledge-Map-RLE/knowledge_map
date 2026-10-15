"""Явные графы и цепочки источников без AI-клиентов и общей базы документов."""
from hashlib import sha256
import json
from pathlib import Path
from domain.article_maps import fingerprint,require
from domain.first_administration_clock import analyze_clocks
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.first_administration_clock import FileClockInputs
from infrastructure.treatment_episode_context import load_episode_sources


class FileTimedHypothesisInputs:
    def __init__(self,review):self.review=Path(review).resolve()

    def load(self):
        verification=json.loads((self.review/'verification.json').read_bytes())
        for f,d in verification['files'].items():require(sha256((self.review/f).read_bytes()).hexdigest()==d,'Timed review bytes differ')
        review=json.loads((self.review/'audit.json').read_bytes());root=Path(verification['clock_path'])
        api_root=Path(__file__).resolve().parents[1]
        preparer=api_root/'tools'/'prepare_timed_clinical_review.py'
        helper=api_root/'tools'/'render_template_barrier_audit.py'
        require(review['preparer_sha256']==verification['preparer_sha256']==sha256(preparer.read_bytes()).hexdigest()
            and verification['helper_sha256']==sha256(helper.read_bytes()).hexdigest(),
            'Timed source review preparer or rendering helper differs')
        clock=FilePredictionStore(root.parent).read_seal(root.name);require(clock is not None,'Missing clock seal')
        for f,d in clock['binding']['implementation'].items():require(sha256((root/'implementation'/f).read_bytes()).hexdigest()==d,'Clock implementation differs')
        pointer=json.loads((root/'input-corpus.json').read_bytes());episode_root=Path(pointer['episodes'])
        episode=FileClockInputs(episode_root).load()
        require(fingerprint(episode)==clock['binding']['episode_sha256']
            and all(clock[k]==v for k,v in analyze_clocks(episode).items()),'Clock source replay differs')
        ep=json.loads((episode_root/'input-corpus.json').read_bytes());functional,frozen,maps,cases=load_episode_sources(ep['functional'])
        require(review['clock_sha256']==fingerprint(clock)==verification['clock_sha256'],'Review references another source clock')
        return review,clock,functional,frozen,maps
