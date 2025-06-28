# 🗄️ S3 Интеграция в Knowledge Map API

## 📦 Установка зависимостей

```powershell
cd api
poetry install
```

Новые зависимости:
- `aioboto3` - асинхронный клиент для AWS S3/MinIO
- `aiofiles` - для асинхронной работы с файлами

## ⚙️ Настройка

### Переменные окружения

Добавьте в `.env` файл API:

```env
# S3/MinIO настройки
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=minio
S3_SECRET_KEY=minio123456
S3_REGION=us-east-1
```

### Docker Compose

MinIO уже настроен в `docker-compose.yml`:

```yaml
s3:
  image: minio/minio:RELEASE.2024-01-01T16-36-33Z
  ports:
    - "9000:9000"   # S3 API
    - "9001:9001"   # MinIO Console
  environment:
    MINIO_ROOT_USER: minio
    MINIO_ROOT_PASSWORD: minio123456
```

## 🚀 Запуск

1. **Запустите MinIO:**
```powershell
docker-compose up -d s3
```

2. **Создайте bucket "markdown":**
   - Откройте http://localhost:9001
   - Войдите: `minio` / `minio123456`
   - Создайте bucket с именем `markdown`

3. **Загрузите файл "Пример статьи.md":**
   - В веб-интерфейсе MinIO загрузите markdown файл
   - Или используйте API эндпоинт `POST /api/s3/buckets/markdown/objects/Пример статьи.md`

4. **Запустите API:**
```powershell
poetry run python main.py
```

## 🌐 API Эндпоинты

### Основные S3 операции

**Список объектов:**
```http
GET /api/s3/buckets/{bucket_name}/objects?prefix=
```

**Получить объект:**
```http
GET /api/s3/buckets/{bucket_name}/objects/{object_key}
```

**Загрузить объект:**
```http
POST /api/s3/buckets/{bucket_name}/objects/{object_key}
Content-Type: application/json
{
    "content": "текстовое содержимое"
}
```

**Удалить объект:**
```http
DELETE /api/s3/buckets/{bucket_name}/objects/{object_key}
```

**Генерировать временный URL:**
```http
GET /api/s3/buckets/{bucket_name}/objects/{object_key}/url?expires_in=3600
```

### Специальный эндпоинт для NLP

**Получить markdown для NLP компонента:**
```http
GET /api/nlp/markdown/{filename}
```

Этот эндпоинт автоматически ищет файл в bucket `markdown`.

## 🧪 Тестирование

### Через curl

```bash
# Загрузить файл
curl -X POST "http://localhost:8000/api/s3/buckets/markdown/objects/test.md" \
     -H "Content-Type: application/json" \
     -d '{"content": "# Тестовый файл\n\nЭто тест markdown файла."}'

# Получить файл
curl "http://localhost:8000/api/s3/buckets/markdown/objects/test.md"

# Для NLP компонента
curl "http://localhost:8000/api/nlp/markdown/Пример статьи.md"
```

### Через фронтенд

Компонент NLP автоматически загружает `Пример статьи.md` при монтировании.

## 🔧 Использование в коде

### В API (Python)

```python
from s3_client import get_s3_client

# Получаем клиент
s3 = get_s3_client()

# Загружаем файл
await s3.upload_bytes(
    data=content.encode('utf-8'),
    bucket_name="markdown",
    object_key="example.md",
    content_type="text/markdown"
)

# Скачиваем файл
content = await s3.download_text("markdown", "example.md")
```

### В фронтенде (TypeScript)

```typescript
import { getNLPMarkdown } from '../services/api'

// Загружаем markdown файл
const response = await getNLPMarkdown('Пример статьи.md')
if (response.content) {
    console.log(response.content)
}
```

## 🔍 Отладка

### Логи API

S3 клиент логирует все операции:

```
INFO:__main__:S3 клиент инициализирован для http://localhost:9000
INFO:__main__:Bucket 'markdown' уже существует
INFO:__main__:Данные загружены: s3://markdown/example.md
```

### Проверка MinIO

1. **Веб-интерфейс:** http://localhost:9001
2. **Healthcheck:** `curl http://localhost:9000/minio/health/live`
3. **Список buckets:** `curl http://localhost:9000`

### Типичные проблемы

**Ошибка подключения к S3:**
- Убедитесь, что MinIO запущен: `docker-compose ps s3`
- Проверьте порты: `netstat -an | grep 9000`

**Bucket не найден:**
- Создайте bucket через веб-интерфейс MinIO
- Или используйте API: `POST /api/s3/buckets/markdown/objects/test.txt`

**Файл не найден:**
- Проверьте имя файла (регистр важен!)
- Убедитесь, что файл загружен в правильный bucket

## 🎯 Интеграция с NLP компонентом

Компонент NLP автоматически:

1. **Загружает** файл `Пример статьи.md` из bucket `markdown`
2. **Отображает** содержимое в `div.nlp_text`
3. **Показывает** индикатор загрузки
4. **Обрабатывает** ошибки с полезными подсказками

### Формат файла

Markdown файл должен быть в кодировке UTF-8. Поддерживаются:
- Заголовки (#, ##, ###)
- Параграфы
- Списки
- Выделение текста
- Ссылки

### Пример содержимого

```markdown
# Пример статьи

## Введение

Это пример markdown статьи для демонстрации возможностей **Knowledge Map**.

### Основные возможности:

- Загрузка из S3
- Отображение в реальном времени
- Обработка ошибок
- Красивое форматирование

## Заключение

Интеграция с S3 позволяет гибко управлять контентом проекта.
```

## 📚 Дополнительная информация

- [MinIO Documentation](https://docs.min.io/)
- [aioboto3 Documentation](https://aioboto3.readthedocs.io/)
- [FastAPI File Uploads](https://fastapi.tiangolo.com/tutorial/request-files/) 