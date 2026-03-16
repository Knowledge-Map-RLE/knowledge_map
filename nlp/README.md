# Обработка естественного языка. NLP

Микросервис для многоуровневого лингвистического анализа текста через gRPC. Извлекает из текста графовую лингвистическую структуру и представляет сущности, действия и смыслы, содержащиеся в нём.

## Запуск

Локальный хост
- `poetry run python src/main.py`

2. Загрузите языковые модели:
```bash
# spaCy
poetry run python -m spacy download en_core_sci_scibert
poetry run spacy download en_core_sci_scibert
.venv/Scripts/python.exe -m pip install "https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_scibert-0.5.4.tar.gz" --no-deps 2>&1 | tail -5

# Stanza
python -c "import stanza; stanza.download('ru')"

# NLTK
python -m nltk.downloader punkt averaged_perceptron_tagger
```

3. Запустите сервер:
```bash
```

Сервер будет доступен на `localhost:50055`

## Тестирование

```bash
# Unit тесты
poetry run pytest tests/unit/

# Integration тесты
poetry run pytest tests/integration/

# E2E тесты
poetry run pytest tests/e2e/
```

### Генерация proto файлов

```bash
python -m grpc_tools.protoc \
    -I./proto \
    --python_out=./src \
    --grpc_python_out=./src \
    ./proto/nlp.proto
```
