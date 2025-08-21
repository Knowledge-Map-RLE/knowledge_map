import pytest
from unittest.mock import patch
from src import tasks

@pytest.mark.celery(app=tasks.celery_app)
def test_process_large_graph_layout(celery_app, celery_worker):
    # Mock the distributed_layout.calculate_distributed_layout method
    with patch("src.tasks.distributed_layout.calculate_distributed_layout") as mock_calculate_distributed_layout:
        # Configure the mock method to return a successful result
        mock_calculate_distributed_layout.return_value = {"success": True, "statistics": {}}

        # Call the process_large_graph_layout task
        result = tasks.process_large_graph_layout.delay(node_labels=["Test"], filters={"test": "filter"}).get()

        # Assert that the result is successful
        assert result["success"] is True


@pytest.mark.celery(app=tasks.celery_app)
def test_process_large_graph_layout_failure(celery_app, celery_worker):
    # Mock the distributed_layout.calculate_distributed_layout method to return a failure
    with patch("src.tasks.distributed_layout.calculate_distributed_layout") as mock_calculate_distributed_layout:
        # Configure the mock method to return a failure result
        mock_calculate_distributed_layout.return_value = {"success": False, "error": "Layout failed"}

        # Call the process_large_graph_layout task
        result = tasks.process_large_graph_layout.delay(node_labels=["Test"], filters={"test": "filter"}).get()

        # Assert that the result is not successful
        assert result["success"] is False


@pytest.mark.celery(app=tasks.celery_app)
def test_process_graph_chunk(celery_app, celery_worker):
    # Mock the distributed_layout._apply_layout_algorithm method
    with patch("src.tasks.distributed_layout._apply_layout_algorithm") as mock_apply_layout_algorithm:
        # Configure the mock method to return a successful result
        mock_apply_layout_algorithm.return_value = {"success": True}

        # Call the process_graph_chunk task
        result = tasks.process_graph_chunk.delay(nodes=[{"id": 1}], edges=[{"source": 1, "target": 2}], chunk_id="test_chunk").get()

        # Assert that the result is successful
        assert result["success"] is True


@pytest.mark.celery(app=tasks.celery_app)
def test_process_graph_chunk_failure(celery_app, celery_worker):
    # Mock the distributed_layout._apply_layout_algorithm method to return a failure
    with patch("src.tasks.distributed_layout._apply_layout_algorithm") as mock_apply_layout_algorithm:
        # Configure the mock method to return a failure result
        mock_apply_layout_algorithm.return_value = {"success": False, "error": "Apply layout failed"}

        # Call the process_graph_chunk task
        result = tasks.process_graph_chunk.delay(nodes=[{"id": 1}], edges=[{"source": 1, "target": 2}], chunk_id="test_chunk").get()

        # Assert that the result is not successful
        assert result["success"] is False


@pytest.mark.celery(app=tasks.celery_app)
def test_optimize_layout(celery_app, celery_worker):
    # Call the optimize_layout task
    layout_data = {"blocks": [1], "layers": {1: 1}}
    result = tasks.optimize_layout.delay(layout_data).get()

    # Assert that the result is successful
    assert result["optimized"] is True


@pytest.mark.celery(app=tasks.celery_app)
def test_save_results(celery_app, celery_worker):
    # Mock the distributed_layout._save_layout_results method
    with patch("src.tasks.distributed_layout._save_layout_results") as mock_save_layout_results:
        # Configure the mock method to return a successful result
        mock_save_layout_results.return_value = {"success": True}

        # Call the save_results task
        layout_result = {"blocks": [1], "layers": {1: 1}}
        result = tasks.save_results.delay(layout_result).get()

        # Assert that the result is successful
        assert result["success"] is True


@pytest.mark.celery(app=tasks.celery_app)
def test_save_results_failure(celery_app, celery_worker):
    # Mock the distributed_layout._save_layout_results method to return a failure
    with patch("src.tasks.distributed_layout._save_layout_results") as mock_save_layout_results:
        # Configure the mock method to return a failure result
        mock_save_layout_results.return_value = {"success": False, "error": "Save failed"}

        # Call the save_results task
        layout_result = {"blocks": [1], "layers": {1: 1}}
        result = tasks.save_results.delay(layout_result).get()

        # Assert that the result is not successful
        assert result["success"] is False
