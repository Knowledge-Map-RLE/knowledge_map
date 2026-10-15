"""Условные силлогизмы не предполагают существование и не переносят чужую непустоту."""
from copy import deepcopy

import pytest

from domain.article_maps import ArticleMapError, prepare_source
from domain.categorical_logic import check
from domain.source_count_witness import positive_count_witness, check_with_witness


def inputs(n='5'):
    source = prepare_source('synthetic', n + '\n\n# References\nNone')
    scope = {'interpretation': 'synthetic same-visit classification'}
    cell = {'kind': 'count', 'unit': 'cases', 'value': n, 'printed_value': n,
            'source_span': {'start': 0, 'end': len(n)}, 'source_unit_id': 'U1'}
    annotation = {'subject': 'S', 'source_unit_id': 'U1', 'author': 'Codex', 'source_row_id': 'synthetic'}
    premises = [{'form': 'E', 'subject': 'M', 'object': 'P', 'scope': scope},
                {'form': 'A', 'subject': 'S', 'object': 'M', 'scope': scope}]
    conclusion = {'form': 'O', 'subject': 'S', 'object': 'P', 'scope': scope}
    return source, cell, scope, annotation, premises, conclusion


def test_eao_requires_positive_count_and_fails_when_removed():
    source, cell, scope, annotation, premises, conclusion = inputs()
    witness = positive_count_witness(source, cell, 'S', scope, annotation)
    assert check_with_witness(premises, conclusion, witness)['entailed']
    assert not check(premises, conclusion)['entailed']


def test_zero_count_does_not_assert_nonempty_class():
    source, cell, scope, annotation, premises, conclusion = inputs('0')
    witness = positive_count_witness(source, cell, 'S', scope, annotation)
    assert not check_with_witness(premises, conclusion, witness)['entailed']


def test_rate_cannot_be_used_as_patient_witness():
    source, cell, scope, annotation, _, _ = inputs()
    cell.update(kind='estimate', unit='per 100 person-years')
    with pytest.raises(ArticleMapError):
        positive_count_witness(source, cell, 'S', scope, annotation)


def test_other_context_or_class_is_rejected():
    source, cell, scope, annotation, premises, conclusion = inputs()
    witness = positive_count_witness(source, cell, 'S', scope, annotation)
    witness['scope'] = {'interpretation': 'a later visit'}
    with pytest.raises(ArticleMapError):
        check_with_witness(premises, conclusion, witness)


def test_nonempty_parent_does_not_imply_nonempty_subtype():
    source, cell, scope, annotation, premises, conclusion = inputs()
    annotation['subject'] = 'M'
    witness = positive_count_witness(source, cell, 'M', scope, annotation)
    assert not check_with_witness(premises, conclusion, witness)['entailed']


def test_darapti_can_use_witness_of_middle_class():
    source, cell, scope, annotation, _, _ = inputs()
    annotation['subject'] = 'M'
    witness = positive_count_witness(source, cell, 'M', scope, annotation)
    premises = [{'form': 'A', 'subject': 'M', 'object': p, 'scope': scope} for p in ('P', 'S')]
    conclusion = {'form': 'I', 'subject': 'S', 'object': 'P', 'scope': scope}
    assert check_with_witness(premises, conclusion, witness)['entailed']
    assert not check(premises, conclusion)['entailed']
