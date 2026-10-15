"""Сохранение свободных гипотез отдельно от исходных карт и будущего оценщика."""
from domain.article_maps import require, fingerprint
from domain.selective_perturbation import generate, VERSION, LIMITS


class SealSelectivePerturbation:
    def __init__(self, snapshots):
        self.snapshots = snapshots

    def execute(self, source_run, audit, implementation):
        require(source_run['target_read'] is False and source_run['model_calls'] == 0, 'Source-only graph required')
        binding = {'semantic_run_id': source_run['run_id'], 'source_run_sha256': fingerprint(source_run),
                   'license_sha256': fingerprint(audit), 'implementation': implementation, 'version': VERSION, 'limits': LIMITS}
        run = fingerprint(binding); old = self.snapshots.read_seal(run)
        if old is not None:
            require(old['binding'] == binding, 'Selective seal differs'); return old
        result = {'run_id': run, 'binding': binding, **generate(source_run['semantic_graph'], audit)}
        self.snapshots.seal(run, result)
        return self.snapshots.read_seal(run)
