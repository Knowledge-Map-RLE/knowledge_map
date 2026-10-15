"""Сценарий адресного поиска источниковых посылок для ручной логической разметки."""
from domain.article_maps import fingerprint
from domain.categorical_candidate_discovery import inspect_maps, render_ru


class RunCategoricalCandidateDiscovery:
    def __init__(self, inputs, store, implementation):
        self.inputs, self.store, self.implementation = inputs, store, implementation

    def execute(self):
        loaded = self.inputs.load()
        maps = loaded["maps"]
        audit = inspect_maps(maps)
        binding = {
            "version": audit["version"],
            "base_run_id": loaded["base_run_id"],
            "base_prediction_sha256": loaded["base_prediction_sha256"],
            "manifest_sha256": loaded["manifest_sha256"],
            "map_hashes": [fingerprint(m) for m in maps],
            "implementation": self.implementation,
        }
        run_id = fingerprint(binding)
        artifact = {
            "run_id": run_id,
            "binding": binding,
            "source_count": len(maps),
            "audit": audit,
            "report_ru_md": render_ru(audit, loaded["base_run_id"]),
        }
        self.store.seal(run_id, artifact)
        return self.store.read_seal(run_id)
