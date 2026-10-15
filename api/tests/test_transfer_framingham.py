"""Реальный контроль проверяется тем же оценщиком, что и прежние отказы."""
from copy import deepcopy
from pathlib import Path
import pytest
from domain.article_maps import ArticleMapError
from domain.transfer_control import audit_control
from infrastructure.transfer_control import FileControlInputs

ROOT = Path(__file__).resolve().parents[2] / 'eval/free_prediction/frozen-neutral-expansion-v1'

def inputs():
    return FileControlInputs(ROOT / 'prepared/framingham2024/manifest.json').read_inputs()

def test_real_age_pattern_and_unaddressed_nonmemory_education():
    data = inputs()
    result = audit_control(data['forecast'], data['control'])
    assert result['independent_pattern_matches'] == 1
    assert result['modes']['semantic']['counts'] == {'qualitative_pattern_match': 1, 'not_addressed': 1}
    assert result['modes']['known_union']['counts']['qualitative_pattern_match'] == 1
    assert result['modes']['frequency']['counts']['qualitative_pattern_match'] == 1
    assert result['graph_gain'] is None and not result['scientific_success']
    assert not result['graph_advantage_demonstrated']

@pytest.mark.parametrize('field', ['general_older_adults', 'baseline_free_of_mci_and_dementia', 'prospective_incidence'])
def test_same_direction_cannot_override_unknown_context(field):
    data = inputs()
    data['control']['hard_context'][field] = None
    assert audit_control(data['forecast'], data['control'])['independent_pattern_matches'] == 0

def test_source_change_is_rejected(tmp_path):
    data = inputs()
    import json
    from domain.article_maps import fingerprint
    control = deepcopy(data['control'])
    source = tmp_path / 'article.txt'
    source.write_text('tampered source', encoding='utf8')
    control['documents'][0]['path'] = str(source)
    control_path = tmp_path / 'control.json'
    control_path.write_text(json.dumps(control), encoding='utf8')
    manifest = json.loads((ROOT / 'prepared/framingham2024/manifest.json').read_text(encoding='utf8'))
    manifest['control'] = {'path': str(control_path), 'sha256': fingerprint(control)}
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest), encoding='utf8')
    with pytest.raises(ArticleMapError):
        FileControlInputs(path).read_inputs()

def test_incomplete_fulltext_cannot_confirm_match():
    data = inputs()
    data['control']['full_source_review'] = False
    assert audit_control(data['forecast'], data['control'])['independent_pattern_matches'] == 0
