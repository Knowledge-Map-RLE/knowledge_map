from neo4j import GraphDatabase

class Neo4jConnector:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def execute_query(self, query, parameters=None):
        with self.driver.session() as session:
            result = session.run(query, parameters)
            return result.data()

    def call_procedure(self, procedure_name, parameters=None):
        """
        Calls a Neo4j procedure.
        """
        query = f"CALL {procedure_name}($parameters)"
        with self.driver.session() as session:
            result = session.run(query, parameters=parameters)
            return result.data()

# Example usage:
if __name__ == '__main__':
    connector = Neo4jConnector("bolt://neo4j:7687", "neo4j", "password")
    # Example of calling a procedure (replace 'my.procedure' with your actual procedure name)
    # result = connector.call_procedure("my.procedure", {"param1": "value1"})
    # print(result)
    connector.close()
