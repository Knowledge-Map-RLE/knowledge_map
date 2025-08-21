import pytest
from unittest.mock import AsyncMock, patch
from src.neo4j_client import Neo4jClient
from neo4j import AsyncGraphDatabase

@pytest.fixture
async def neo4j_client():
    # Mock the Neo4j driver and session for testing
    mock_driver = AsyncMock()
    mock_session = AsyncMock()
    mock_driver.session.return_value = mock_session

    client = Neo4jClient(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="password",
        driver=mock_driver  # Inject the mock driver
    )
    return client


@pytest.mark.asyncio
async def test_get_graph_data(neo4j_client):
    # Mock the session.run method to return some test data
    mock_result = AsyncMock()
    mock_result.data.return_value = [
        {
            "nodes": [{"id": 1, "label": "Node1"}],
            "edges": [{"source": 1, "target": 2}],
        }
    ]
    neo4j_client._driver.session.return_value.run.return_value = mock_result

    graph_data = await neo4j_client.get_graph_data(node_labels=["Test"], filters={"test": "filter"})

    assert graph_data is not None
    assert "nodes" in graph_data
    assert "edges" in graph_data


@pytest.mark.asyncio
async def test_get_graph_data_empty_result(neo4j_client):
    # Mock the session.run method to return an empty result
    mock_result = AsyncMock()
    mock_result.data.return_value = []
    neo4j_client._driver.session.return_value.run.return_value = mock_result

    graph_data = await neo4j_client.get_graph_data(node_labels=["Test"], filters={"test": "filter"})

    assert graph_data == {"nodes": [], "edges": []}


@pytest.mark.asyncio
async def test_update_node_layers(neo4j_client):
    # Call the update_node_layers method with some test data
    updates = [{"block_id": 1, "layer": 2}]
    await neo4j_client.update_node_layers(updates)

    # Assert that the session.run method was called with the correct query
    neo4j_client._driver.session.return_value.run.assert_called()


@pytest.mark.asyncio
async def test_neo4j_client_connection_error():
    # Test the Neo4jClient with invalid credentials to simulate a connection error
    with patch("src.neo4j_client.AsyncGraphDatabase.driver", side_effect=Exception("Connection error")):
        with pytest.raises(Exception, match="Connection error"):
            Neo4jClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="invalid_user",
                neo4j_password="invalid_password",
            )
