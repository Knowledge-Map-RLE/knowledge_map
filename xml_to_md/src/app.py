"""REST API для xml_to_md сервиса (health check)."""
from fastapi import FastAPI

app = FastAPI(title="xml_to_md Service", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "xml_to_md", "grpc_port": 50054}
