"""Контрольные пары выбираются только для совпадающих фиксированных запусков."""
import json
from pathlib import Path

from domain.article_maps import fingerprint

PATH = Path(__file__).with_name("article_comparison_controls.v1.json")


class FixedComparisonControls:
    def select(self, references):
        if not PATH.exists():
            # Сравнение произвольных запусков не имеет научно размеченного контроля.
            return {"version": "unannotated", "references": references, "pairs": []}
        control = json.loads(PATH.read_text(encoding="utf-8"))
        if fingerprint(control["references"]) != fingerprint(references):
            return {"version": "unannotated", "references": references, "pairs": []}
        return control
