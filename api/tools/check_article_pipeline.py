import asyncio, json
import httpx
from infrastructure.article_pipeline import LinguisticGateway
from knowledge_pipeline.pipeline import source_revision, linguistic_profile
from infrastructure.config import settings
from neo4j import GraphDatabase

async def main():
    for url in ("http://127.0.0.1:50059/health","http://127.0.0.1:50059/v1/models"):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r=await client.get(url)
                print(url,r.status_code,r.text[:1200])
        except Exception as e: print(type(e).__name__, str(e))
    text="Clusterin may inhibit inflammation. Aged mice do not show fibrosis."
    try:
        doc=await LinguisticGateway()(text)
        print("NLP",json.dumps(doc)[:6000])
        linguistic_profile(source_revision("test",text),doc)
        print("NLP spans valid")
    except Exception as e: print("NLP_ERROR",type(e).__name__,str(e))
    driver=GraphDatabase.driver(settings.NEO4J_URI,auth=(settings.NEO4J_USER,settings.NEO4J_PASSWORD))
    try:
        driver.verify_connectivity()
        with driver.session() as s:
            print("DB",s.run("MATCH (d:Document) RETURN count(d) AS count").single()["count"])
    finally: driver.close()
asyncio.run(main())
