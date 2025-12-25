

## Запуск тестов

- `pytest` (лучше чем `unittest`)

- Запустить все тесты
  - `poetry run python -m pytest`
- Запустить все тесты с подробным выводом
  - `poetry run python -m pytest -v`
- Запустить конкретный файл
  - `poetry run python -m pytest tests/unit/test_demo`
- Запустить с подробностями
  - `poetry run python -m pytest -v -s tests/unit/test_text_to_ontology.py`

