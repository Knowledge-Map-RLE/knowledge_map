"""Условная перестановка подписей не становится исправлением научного источника."""
from domain.partition_label_constraints import infer_labels

ASSUMPTIONS = dict(mutually_exclusive=True, exhaustive=True, common_phase=True, counts_correct=True)


def test_unique_assignment_by_multiple_aligned_counts():
    result = infer_labels({'memory': [8, 9], 'other': [10, 12]}, {'memory': [[3, 4]], 'other': [[3, 4], [4, 5]]},
                          {'r1': [5, 5], 'r2': [3, 3]}, ASSUMPTIONS)
    assert result['assignments'] == [{'r1': 'memory', 'r2': 'other'}]
    assert not result['source_correction_authorized']


def test_unknown_partition_does_not_license_a_label():
    result = infer_labels({'a': [5]}, {'a': []}, {'r': [5]}, {**ASSUMPTIONS, 'counts_correct': False})
    assert result['status'] == 'blocked_missing_assumption'


def test_equal_residuals_leave_multiple_assignments():
    result = infer_labels({'a': [5], 'b': [5]}, {'a': [], 'b': []}, {'r1': [5], 'r2': [5]}, ASSUMPTIONS)
    assert result['status'] == 'ambiguous_conditional_assignment'


def test_inconsistent_cells_do_not_produce_correction():
    result = infer_labels({'a': [5]}, {'a': [[6]]}, {'r': [1]}, ASSUMPTIONS)
    assert result['status'] == 'inconsistent_under_assumptions'
