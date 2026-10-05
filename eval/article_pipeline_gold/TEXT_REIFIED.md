# Пять источников эксперимента в GOLD-корпусе

Реестр новых кейсов: manifest.text_reified.json. Исходный manifest.json по-прежнему описывает 20 DSL-кейсов.
Новые кейсы относятся к маршруту текст → карта знаний (text_reified).

Каждый кейс содержит полный английский article.md, исходный article.xml, meta.json, исходный source.meta.json,
source_units.json с координатами Unicode code points, document_sections.json,
готовый knowledge_map.text_reified.json и отдельный translation.text_reified.ru.json.

Карта и перевод скопированы побайтно из готового прогона без смены идентификаторов и новых LLM-вызовов.
Русские подписи относятся к блокам карты; полный русский перевод статьи отсутствует и при импорте не создавался.
References остаются в article.md и исключены из извлечения. Координаты U-блоков относятся к полному article.md.

Автоматические карты требуют экспертной проверки: needs_expert_review=true, expert_validated=false.
Новые gold.dsl и gold.json не создавались. Существующие эталоны и их инструменты сохранены.

Архив eval/reference_pilots/pmc10000452 сохранён по прежним путям, включая источники, кэш, прогнозы и отчёты.
Neo4j и S3 не изменялись. Контроль сохранности записан в import.text_reified.json.
