"""Legacy statement writer using the canonical Document.uid and typed role edges."""
from __future__ import annotations
import hashlib
import json
from neo4j import AsyncGraphDatabase
from src.config import settings
from src.domain.models import Concept, Literal, Statement

class Neo4jWriter:
    def __init__(self,uri=None,user=None,password=None):
        self._uri=uri or settings.neo4j_uri
        self._user=user or settings.neo4j_user
        self._password=password or settings.neo4j_password
        self._driver=None
    async def __aenter__(self):
        self._driver=AsyncGraphDatabase.driver(self._uri,auth=(self._user,self._password))
        return self
    async def __aexit__(self,*args):
        if self._driver:
            await self._driver.close()
    async def ensure_indexes(self):
        if not self._driver: raise RuntimeError("Not connected")
        async with self._driver.session() as session:
            for query in ("CREATE INDEX IF NOT EXISTS FOR (s:Statement) ON (s.fingerprint)",
                          "CREATE INDEX IF NOT EXISTS FOR (s:SubgraphFingerprint) ON (s.wl_hash)"):
                await (await session.run(query)).consume()
    def _compute_fingerprint(self,stmt):
        raw=json.dumps([stmt.subject_type.value,stmt.subject_id,stmt.predicate,stmt.object_type.value,
                        stmt.object_id,stmt.arity,stmt.negated,stmt.modality,stmt.context],sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()
    async def write_graph(self,statements,doc_id=""):
        if not self._driver: raise RuntimeError("Not connected")
        async with self._driver.session() as session:
            return await session.execute_write(self._write_graph,statements,doc_id)
    async def _write_graph(self,tx,statements,doc_id):
        if doc_id:
            row=await (await tx.run("MATCH (d:Document {uid:$id}) RETURN d.uid",id=doc_id)).single()
            if row is None: raise ValueError("Document not found")
        concepts={}
        for stmt in statements:
            if stmt.arity not in (1,2) or (stmt.object is None)!=(stmt.arity==1):
                raise ValueError("Predicate arity mismatch")
            for term in (stmt.subject,stmt.object):
                if isinstance(term,Concept): concepts[term.id]=term
        for concept in concepts.values():
            await (await tx.run("""MERGE (c:Concept:KnowledgeConcept {uid:$id})
                SET c.id=$id,c.text=$text,c.normalized_text=$normalized""",
                id=concept.id,text=concept.text,normalized=concept.normalized_text or concept.text)).consume()
        # All statements exist before recursive roles are connected.
        for stmt in statements:
            await (await tx.run("""MERGE (s:Statement:KnowledgeStatement {uid:$id})
                SET s.id=$id,s.type=$type,s.predicate=$predicate,s.status=$status,s.arity=$arity,
                    s.negated=$negated,s.modality=$modality,s.context_json=$context,
                    s.provenance_json=$provenance,s.confidence=$confidence,s.sentence=$sentence,
                    s.fingerprint=$fingerprint""",
                id=str(stmt.id),type=stmt.type.value,predicate=stmt.predicate,status=stmt.status,
                arity=stmt.arity,negated=stmt.negated,modality=stmt.modality,context=json.dumps(stmt.context),
                provenance=json.dumps(stmt.provenance),confidence=stmt.confidence,sentence=stmt.sentence_text,
                fingerprint=self._compute_fingerprint(stmt))).consume()
        for stmt in statements:
            if doc_id:
                await (await tx.run("""MATCH (d:Document {uid:$doc}),(s:Statement {uid:$id})
                    MERGE (d)-[:HAS_STATEMENT]->(s)""",doc=doc_id,id=str(stmt.id))).consume()
            for role,term in (("SUBJECT",stmt.subject),("OBJECT",stmt.object)):
                await (await tx.run(f"MATCH (s:Statement {{uid:$id}})-[r:{role}]->() DELETE r",id=str(stmt.id))).consume()
                if term is None: continue
                if isinstance(term,Literal):
                    literal_id=hashlib.sha256(json.dumps([term.type,term.value]).encode()).hexdigest()
                    await (await tx.run("MERGE (l:Literal {uid:$id}) SET l.value=$value,l.type=$type",
                                       id=literal_id,value=term.value,type=term.type)).consume()
                    label,target="Literal",literal_id
                else:
                    label="Concept" if isinstance(term,Concept) else "Statement"
                    target=term.id if isinstance(term,Concept) else str(term.id)
                row=await (await tx.run(f"""MATCH (s:Statement {{uid:$id}}),(t:{label} {{uid:$target}})
                    MERGE (s)-[:{role}]->(t) RETURN t.uid""",id=str(stmt.id),target=target)).single()
                if row is None: raise ValueError("Unresolved statement reference")
        return {"statements_written":len(statements),"concepts_written":len(concepts),"errors":[]}
