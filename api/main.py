from fastapi import FastAPI, HTTPException
from strawberry.fastapi import GraphQLRouter
from schema import schema
from models import User, Block, Tag, LinkMetadata


app = FastAPI(
    title="Knowledge Map API",
    description="GraphQL API для карты знаний",
    version="1.0.0"
)

# GraphQL роутер
graphql_app = GraphQLRouter(schema)

# Подключаем GraphQL endpoint
app.include_router(graphql_app, prefix="/graphql")

@app.get("/")
async def root():
    return {
        "message": "Knowledge Map API", 
        "graphql": "/graphql",
        "docs": "/docs",
        "neo4j_browser": "http://localhost:7474"
    }

@app.get("/health")
async def health():
    try:
        from neomodel import db
        db.cypher_query("RETURN 1")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)