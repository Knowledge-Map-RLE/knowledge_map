"""
Диагностический скрипт: проверка документов в Neo4j и наличие markdown в S3.

Запуск: python scripts/diagnose_documents.py
"""
import os
import sys
import time
from collections import defaultdict

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL", "http://192.168.1.38:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minio")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minio123456")
S3_BUCKET = os.getenv("S3_BUCKET_NAME", "knowledge-map-data")


def main():
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), connection_timeout=10)

    print("=" * 70)
    print("  ДИАГНОСТИКА ДОКУМЕНТОВ В БАЗЕ ДАННЫХ")
    print("=" * 70)

    # 1. Общее количество
    with driver.session() as s:
        total = s.run("MATCH (d:Document) RETURN count(d) AS cnt").single()["cnt"]
    print(f"\nВсего документов в Neo4j: {total}")

    # 2. По source
    with driver.session() as s:
        rows = s.run("""
            MATCH (d:Document)
            RETURN d.source AS source, count(d) AS cnt
            ORDER BY cnt DESC
        """).data()
    print("\n── По источнику (source) ──")
    for r in rows:
        print(f"  {r['source'] or '(пусто)':>10s}  —  {r['cnt']}")

    # 3. По статусу обработки
    with driver.session() as s:
        rows = s.run("""
            MATCH (d:Document)
            RETURN d.processing_status AS status, count(d) AS cnt
            ORDER BY cnt DESC
        """).data()
    print("\n── По статусу обработки ──")
    for r in rows:
        print(f"  {r['status'] or '(пусто)':>25s}  —  {r['cnt']}")

    # 4. Разбивка по source + наличие ключей markdown
    with driver.session() as s:
        rows = s.run("""
            MATCH (d:Document)
            RETURN
                d.source AS source,
                count(d) AS total,
                count(d.docling_raw_md_s3_key) AS has_raw_key,
                count(d.formatted_md_s3_key) AS has_fmt_key,
                count(d.user_md_s3_key) AS has_user_key
            ORDER BY d.source
        """).data()
    print("\n── Ключи Markdown (в Neo4j) ──")
    print(f"  {'source':>10s}  {'всего':>7s}  {'raw_key':>8s}  {'fmt_key':>8s}  {'user_key':>9s}")
    print(f"  {'-'*10}  {'-'*7}  {'-'*8}  {'-'*8}  {'-'*9}")
    for r in rows:
        src = r['source'] or '(пусто)'
        print(f"  {src:>10s}  {r['total']:>7d}  {r['has_raw_key']:>8d}  {r['has_fmt_key']:>8d}  {r['has_user_key']:>9d}")

    # 5. Проверка S3 — выборочная (по 200 на каждый source)
    print("\n── Проверка S3 (выборочная: по 200 на source) ──")
    try:
        import boto3
        from botocore.exceptions import ClientError
        s3 = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            connect_timeout=5,
        )
        s3.head_bucket(Bucket=S3_BUCKET)

        with driver.session() as s:
            sources = s.run("""
                MATCH (d:Document) RETURN DISTINCT d.source AS source
            """).data()

        for src_row in sources:
            source = src_row["source"] or "(пусто)"
            with driver.session() as s:
                docs = s.run("""
                    MATCH (d:Document)
                    WHERE d.source = $source
                    RETURN d.uid AS uid,
                           d.docling_raw_md_s3_key AS raw_key,
                           d.formatted_md_s3_key AS fmt_key,
                           d.user_md_s3_key AS user_key
                    LIMIT 200
                """, source=src_row["source"]).data()

            if not docs:
                continue

            exists_count = 0
            no_key_count = 0
            t0 = time.time()
            for doc in docs:
                raw_key = doc["raw_key"]
                fmt_key = doc["fmt_key"]
                user_key = doc["user_key"]

                if not raw_key and not fmt_key:
                    no_key_count += 1
                    continue

                # Проверяем в порядке приоритета: user -> fmt -> raw
                found = False
                for key in [user_key, fmt_key, raw_key]:
                    if key:
                        try:
                            s3.head_object(Bucket=S3_BUCKET, Key=key)
                            exists_count += 1
                            found = True
                            break
                        except ClientError:
                            pass

            elapsed = time.time() - t0
            sample_total = len(docs)
            pct = exists_count * 100 // max(sample_total, 1)
            no_file = sample_total - exists_count - no_key_count
            print(f"  {source:>10s}  образец={sample_total}  файл_в_S3={exists_count} ({pct}%)  "
                  f"без_ключа={no_key_count}  ключ_есть_файла_нет={no_file}  [{elapsed:.1f}s]")

            # Показать 3 примера PubMed без файлов
            if source == "pubmed" and no_file > 0:
                with driver.session() as s:
                    missing = s.run("""
                        MATCH (d:Document)
                        WHERE d.source = 'pubmed'
                          AND d.docling_raw_md_s3_key IS NOT NULL
                        RETURN d.uid AS uid, d.title AS title, d.docling_raw_md_s3_key AS key
                        LIMIT 3
                    """).data()
                if missing:
                    print(f"    ПримерыPubMed без файлов в S3:")
                    for doc in missing:
                        title_short = (doc["title"] or "")[:55]
                        print(f"      PMID={doc['uid']}  key={doc['key']}")
                        print(f"        title: {title_short}")

    except Exception as e:
        print(f"  Ошибка подключения к S3: {e}")
        print(f"  (S3 endpoint: {S3_ENDPOINT})")

    driver.close()
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
