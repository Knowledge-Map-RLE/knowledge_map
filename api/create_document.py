#!/usr/bin/env python
"""Скрипт для создания PDFDocument в Neo4j"""

from src.models import PDFDocument
from neomodel import config

# Подключаемся к Neo4j
config.DATABASE_URL = 'bolt://neo4j:password@localhost:7687'

# Создаем документ для существующего PDF
doc_id = '886f1448799d4aba1076c65e059a3d58'

try:
    # Проверяем существование
    existing = PDFDocument.nodes.get_or_none(uid=doc_id)
    if existing:
        print(f'Документ {doc_id} уже существует')
        print(f'  uid: {existing.uid}')
        print(f'  filename: {existing.original_filename}')
    else:
        # Создаем новый документ
        pdf_doc = PDFDocument(
            uid=doc_id,
            original_filename=f'{doc_id}.pdf',
            md5_hash=doc_id,
            s3_key=f'pdfs/{doc_id}.pdf',
            processing_status='annotated',
            is_processed=True
        ).save()
        print(f'✓ Документ {doc_id} создан в Neo4j')
        print(f'  uid: {pdf_doc.uid}')
        print(f'  filename: {pdf_doc.original_filename}')
        print(f'  status: {pdf_doc.processing_status}')
except Exception as e:
    print(f'Ошибка: {e}')
    import traceback
    traceback.print_exc()
