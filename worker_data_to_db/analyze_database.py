#!/usr/bin/env python3
"""
Анализ содержимого базы данных Neo4j после загрузки PubMed данных
"""
from neo4j import GraphDatabase
import logging

# Подключение к Neo4j
NEO4J_URI = "bolt://127.0.0.1:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"

def analyze_database():
    """Анализирует содержимое базы данных"""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    try:
        with driver.session() as session:
            print("🔍 АНАЛИЗ БАЗЫ ДАННЫХ PubMed")
            print("=" * 50)
            
            # Общая статистика
            result = session.run('MATCH (n:Article) RETURN count(n) as total_articles')
            total_articles = result.single()['total_articles']
            print(f'📊 Общее количество статей: {total_articles:,}')
            
            # Статистика по связям
            result = session.run('MATCH ()-[r:BIBLIOGRAPHIC_LINK]->() RETURN count(r) as total_links')
            total_links = result.single()['total_links']
            print(f'🔗 Общее количество связей: {total_links:,}')
            
            # Статистика по журналам
            result = session.run('MATCH (n:Article) WHERE n.journal IS NOT NULL RETURN n.journal as journal, count(*) as count ORDER BY count DESC LIMIT 10')
            print(f'\n📚 Топ-10 журналов:')
            for record in result:
                print(f'  {record["journal"]}: {record["count"]:,} статей')
            
            # Статистика по годам
            result = session.run('MATCH (n:Article) WHERE n.publication_time IS NOT NULL RETURN n.publication_time as year, count(*) as count ORDER BY year DESC LIMIT 10')
            print(f'\n📅 Топ-10 годов публикации:')
            for record in result:
                print(f'  {record["year"]}: {record["count"]:,} статей')
            
            # Статистика по авторам
            result = session.run('MATCH (n:Article) WHERE n.authors IS NOT NULL AND size(n.authors) > 0 RETURN size(n.authors) as author_count, count(*) as article_count ORDER BY author_count DESC LIMIT 5')
            print(f'\n👥 Статистика по количеству авторов:')
            for record in result:
                print(f'  {record["author_count"]} авторов: {record["article_count"]:,} статей')
            
            # Статистика по ключевым словам
            result = session.run('MATCH (n:Article) WHERE n.keywords IS NOT NULL AND size(n.keywords) > 0 RETURN size(n.keywords) as keyword_count, count(*) as article_count ORDER BY keyword_count DESC LIMIT 5')
            print(f'\n🏷️ Статистика по количеству ключевых слов:')
            for record in result:
                print(f'  {record["keyword_count"]} ключевых слов: {record["article_count"]:,} статей')
            
            # Статистика по связям (исходящие/входящие)
            result = session.run('MATCH (n:Article)-[r:BIBLIOGRAPHIC_LINK]->() RETURN count(r) as outgoing_links')
            outgoing = result.single()['outgoing_links']
            result = session.run('MATCH ()-[r:BIBLIOGRAPHIC_LINK]->(n:Article) RETURN count(r) as incoming_links')
            incoming = result.single()['incoming_links']
            print(f'\n🔗 Статистика связей:')
            print(f'  Исходящие ссылки: {outgoing:,}')
            print(f'  Входящие ссылки: {incoming:,}')
            
            # Статьи с наибольшим количеством ссылок
            result = session.run('MATCH (n:Article)-[r:BIBLIOGRAPHIC_LINK]->() RETURN n.title as title, n.journal as journal, count(r) as link_count ORDER BY link_count DESC LIMIT 5')
            print(f'\n📖 Статьи с наибольшим количеством ссылок:')
            for record in result:
                title = record['title'][:60] + '...' if record['title'] and len(record['title']) > 60 else record['title']
                print(f'  {title} ({record["journal"]}): {record["link_count"]} ссылок')
            
            # Статьи с наибольшим количеством входящих ссылок
            result = session.run('MATCH ()-[r:BIBLIOGRAPHIC_LINK]->(n:Article) RETURN n.title as title, n.journal as journal, count(r) as link_count ORDER BY link_count DESC LIMIT 5')
            print(f'\n📖 Статьи с наибольшим количеством входящих ссылок:')
            for record in result:
                title = record['title'][:60] + '...' if record['title'] and len(record['title']) > 60 else record['title']
                print(f'  {title} ({record["journal"]}): {record["link_count"]} ссылок')
            
            # Статистика по DOI
            result = session.run('MATCH (n:Article) WHERE n.doi IS NOT NULL RETURN count(n) as doi_count')
            doi_count = result.single()['doi_count']
            print(f'\n🔗 Статьи с DOI: {doi_count:,} ({doi_count/total_articles*100:.1f}%)')
            
            # Статистика по абстрактам
            result = session.run('MATCH (n:Article) WHERE n.abstract IS NOT NULL RETURN count(n) as abstract_count')
            abstract_count = result.single()['abstract_count']
            print(f'📝 Статьи с абстрактами: {abstract_count:,} ({abstract_count/total_articles*100:.1f}%)')
            
            # Статистика по ключевым словам MeSH
            result = session.run('MATCH (n:Article) WHERE n.keywords IS NOT NULL AND size(n.keywords) > 0 RETURN count(n) as mesh_count')
            mesh_count = result.single()['mesh_count']
            print(f'🏷️ Статьи с ключевыми словами MeSH: {mesh_count:,} ({mesh_count/total_articles*100:.1f}%)')
            
            print(f'\n✅ Анализ завершен!')
            
    except Exception as e:
        print(f'❌ Ошибка: {e}')
    finally:
        driver.close()

if __name__ == "__main__":
    analyze_database()
