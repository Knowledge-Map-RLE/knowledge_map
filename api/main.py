from fastapi import FastAPI, HTTPException, Request
from fastapi import UploadFile, File, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from strawberry.fastapi import GraphQLRouter
from schema import schema
from models import User, Block, Tag, LinkMetadata, PDFDocument, PDFAnnotation, LabelStudioProject
from layout_client import get_layout_client, LayoutOptions, LayoutConfig
from config import settings
from s3_client import get_s3_client
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
import logging
import hashlib
import asyncio
import tempfile
import shutil
import subprocess
from pathlib import Path as SysPath
import re
from neomodel import config as neomodel_config, db, UniqueIdProperty, DoesNotExist
import uuid
import json
from datetime import datetime

from auth_client import auth_client
from schemas import (
    UserRegisterRequest, UserLoginRequest, UserRecoveryRequest, 
    UserPasswordResetRequest, User2FASetupRequest, User2FAVerifyRequest,
    AuthResponse, TokenVerifyResponse
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка подключения к Neo4j
neomodel_config.DATABASE_URL = settings.get_database_url()
logger.info(f"Neo4j connection configured: {settings.NEO4J_URI}")

# Настройка CORS
origins = [
    "http://localhost:5173",  # Vite dev server
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

logger.info(f"Configuring CORS with origins: {origins}")

# Создаем приложение FastAPI
app = FastAPI(
    title="Knowledge Map API",
    description="API для карты знаний с конвертацией PDF",
    version="1.0.0"
)

# Настраиваем CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,  # Кэшируем CORS ответы на 1 час
)

# Middleware для логирования запросов
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    logger.info(f"Headers: {dict(request.headers)}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

# Middleware для добавления CORS заголовков
@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    response = await call_next(request)
    if request.headers.get("origin") in origins:
        response.headers["Access-Control-Allow-Origin"] = request.headers["origin"]
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "*"
    return response

# Pydantic модели для API запросов
class BlockInput(BaseModel):
    content: str

class LinkInput(BaseModel):
    source: str
    target: str

class LayoutRequest(BaseModel):
    blocks: List[BlockInput]
    links: List[LinkInput]
    sublevel_spacing: Optional[int] = 200
    layer_spacing: Optional[int] = 250
    optimize_layout: bool = True

class CreateAndLinkInput(BaseModel):
    source_block_id: str
    new_block_content: str = "Новый блок"
    link_direction: str = Field(..., pattern="^(from_source|to_source)$") # 'from_source' или 'to_source'

class MoveToLevelInput(BaseModel):
    target_level: int

class PinWithScaleInput(BaseModel):
    physical_scale: int  # степень 10 в метрах

# Pydantic модели для S3 запросов
class S3UploadResponse(BaseModel):
    success: bool
    object_key: Optional[str] = None
    error: Optional[str] = None

class S3FileResponse(BaseModel):
    content: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None
    last_modified: Optional[str] = None
    error: Optional[str] = None

# ==========================
#  Data Extraction (Marker)
# ==========================

class DataExtractionResponse(BaseModel):
    success: bool
    doc_id: Optional[str] = None
    message: Optional[str] = None
    files: Optional[Dict[str, str]] = None


def _compute_md5(data: bytes) -> str:
    md5 = hashlib.md5()
    md5.update(data)
    return md5.hexdigest()


async def _run_marker_on_pdf(tmp_dir: SysPath) -> SysPath:
    """Запускает marker CLI на папке и возвращает путь к директории с результатами."""
    logger.info(f"[marker] Запуск конвертации: tmp_dir={tmp_dir}")
    
    # Проверяем что PDF файл есть
    pdf_files = list(tmp_dir.glob("*.pdf"))
    if not pdf_files:
        raise RuntimeError("PDF файл не найден в временной директории")
    
    logger.info(f"[marker] Найден PDF файл: {pdf_files[0]}")
    
    # Запускаем marker CLI с правильными параметрами
    try:
        logger.info(f"[marker] Запускаем marker для папки: {tmp_dir}")
        
        # Используем правильные параметры для Marker
        cmd = [
            "marker", 
            str(tmp_dir),
            "--DocumentBuilder_disable_ocr",  # Отключаем OCR для скорости
            "--MarkdownRenderer_extract_images", "False",  # Отключаем извлечение изображений
            "--LayoutBuilder_disable_tqdm",  # Отключаем прогресс-бар
            "--LineBuilder_disable_tqdm",  # Отключаем прогресс-бар
            "--OcrBuilder_disable_tqdm",  # Отключаем прогресс-бар
            "--TableProcessor_disable_tqdm"  # Отключаем прогресс-бар
        ]
        
        logger.info(f"[marker] Команда: {' '.join(cmd)}")
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        # Ждем завершения с таймаутом (2 минуты)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        
        if stdout:
            try:
                logger.info(f"[marker][stdout] {stdout.decode('utf-8', errors='ignore')[:2000]}")
            except Exception:
                pass
        if stderr:
            try:
                logger.warning(f"[marker][stderr] {stderr.decode('utf-8', errors='ignore')[:2000]}")
            except Exception:
                pass
                
        if proc.returncode != 0:
            raise RuntimeError(f"Marker failed with code {proc.returncode}: {stderr.decode('utf-8', errors='ignore')}")
            
        logger.info(f"[marker] Marker завершился успешно")
            
    except asyncio.TimeoutError:
        logger.error(f"[marker] Marker превысил таймаут (2 минуты)")
        proc.kill()
        await proc.wait()
        raise RuntimeError("Marker timeout: процесс не завершился за 2 минуты")
    except Exception as e:
        logger.error(f"[marker] Ошибка запуска Marker: {e}")
        raise

    # Marker создает результаты в той же папке
    conv_dir = tmp_dir
    logger.info(f"[marker] Найдена папка результатов: {conv_dir}")
    return conv_dir


async def _collect_marker_outputs(conv_dir: SysPath, pdf_stem: str) -> Dict[str, SysPath]:
    """Собирает результаты Marker из папки конвертации"""
    logger.info(f"[marker] Поиск результатов в: {conv_dir}")
    
    outputs: Dict[str, SysPath] = {}
    
    # Marker создает результаты в той же папке
    result_dir = conv_dir
    
    # Ищем Markdown файлы
    md_files = list(result_dir.glob("*.md"))
    if md_files:
        outputs["markdown"] = md_files[0]
        logger.info(f"[marker] Найден Markdown файл: {md_files[0]}")
    else:
        logger.warning(f"[marker] Markdown файлы не найдены в {result_dir}")
    
    # Ищем JSON метаданные
    json_meta = list(result_dir.glob("*_meta.json"))
    if json_meta:
        outputs["meta"] = json_meta[0]
        logger.info(f"[marker] Найден meta файл: {json_meta[0]}")
    
    # Ищем изображения
    image_files = list(result_dir.glob("*.png")) + list(result_dir.glob("*.jpg")) + list(result_dir.glob("*.jpeg"))
    if image_files:
        logger.info(f"[marker] Найдено изображений: {len(image_files)}")
    
    outputs["images_dir"] = result_dir
    return outputs


def _build_markdown_annotator_html(markdown_text: str, doc_title: str) -> str:
    # Преобразуем изображения в <img src> с относительными путями (имена сохраняем как есть)
    def repl_img(m: re.Match) -> str:
        alt = m.group(1)
        src = m.group(2)
        fname = SysPath(src).name
        return f'<img src="./{fname}" alt="{alt}" style="max-width:100%;height:auto;border-radius:8px;margin:12px 0;" />'

    processed = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', repl_img, markdown_text)
    # Простейшие заголовки
    processed = re.sub(r'^# (.*)$', r'<h1>\1</h1>', processed, flags=re.MULTILINE)
    processed = re.sub(r'^## (.*)$', r'<h2>\1</h2>', processed, flags=re.MULTILINE)
    processed = re.sub(r'^### (.*)$', r'<h3>\1</h3>', processed, flags=re.MULTILINE)
    # Параграфы
    processed = processed.replace('\r\n', '\n')
    processed = re.sub(r'\n\n+', '</p><p>', processed)
    processed = f'<p>{processed}</p>'

    html = f"""<!DOCTYPE html>
<html lang=\"ru\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>{doc_title} — Markdown Annotator</title>
  <style>
    body {{ margin:0; font-family: Segoe UI, Arial, sans-serif; background:#f5f6fa; }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
    .header {{ background: linear-gradient(135deg,#667eea,#764ba2); color:#fff; padding:20px; border-radius:10px; margin-bottom:16px; }}
    .controls {{ display:flex; gap:8px; margin: 12px 0; }}
    .btn {{ padding:10px 14px; border:0; border-radius:6px; cursor:pointer; color:#fff; background:#667eea; }}
    .content {{ background:#fff; padding:24px; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.06); }}
    .annotation {{ background: rgba(102,126,234,0.2); border-radius:4px; padding:2px 4px; }}
  </style>
</head>
<body>
  <div class=\"container\">
    <div class=\"header\"><h2>📝 Markdown Annotator</h2><div>{doc_title}</div></div>
    <div class=\"controls\">
      <button class=\"btn\" onclick=\"exportAnnotations()\">Экспорт аннотаций</button>
      <input id=\"importInput\" type=\"file\" accept=\"application/json\" style=\"display:none\" />
      <button class=\"btn\" onclick=\"document.getElementById('importInput').click()\">Импорт аннотаций</button>
    </div>
    <div id=\"content\" class=\"content\">{processed}</div>
  </div>
  <script>
    const annotations = [];
    document.addEventListener('mouseup', () => {{
      const sel = window.getSelection();
      const text = sel.toString().trim();
      if (!text) return;
      try {{
        const range = sel.getRangeAt(0);
        const span = document.createElement('span');
        span.className = 'annotation';
        span.textContent = text;
        range.deleteContents();
        range.insertNode(span);
        annotations.push({{ id: Date.now(), text }});
        sel.removeAllRanges();
      }} catch(e) {{}}
    }});
    function exportAnnotations() {{
      const blob = new Blob([JSON.stringify({{ annotations }}, null, 2)], {{type:'application/json'}});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'annotations.json';
      a.click();
      URL.revokeObjectURL(a.href);
    }}
    document.getElementById('importInput').addEventListener('change', async (e) => {{
      const f = e.target.files?.[0];
      if (!f) return;
      const txt = await f.text();
      try {{ const data = JSON.parse(txt); console.log('Импортировано', data); }} catch(e) {{}}
    }});
  </script>
</body>
</html>"""
    return html


@app.post("/data_extraction", response_model=DataExtractionResponse)
async def data_extraction_upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Загрузка PDF, MD5-дедупликация, Marker→Markdown, загрузка md+изображений+json в S3."""
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Ожидается PDF файл")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Пустой файл")

    doc_id = _compute_md5(raw)
    bucket = settings.S3_BUCKET_NAME
    prefix = f"documents/{doc_id}/"
    pdf_key = f"{prefix}{doc_id}.pdf"

    s3 = get_s3_client()
    pdf_exists = await s3.object_exists(bucket, pdf_key)

    async def process_marker_and_upload(pdf_bytes: bytes):
        tmp_dir = SysPath(tempfile.mkdtemp(prefix="km_marker_"))
        try:
            logger.info(f"[marker] План обработки doc_id={doc_id}, tmp_dir={tmp_dir}")
            pdf_name = f"{doc_id}.pdf"
            tmp_pdf = tmp_dir / pdf_name
            with open(tmp_pdf, "wb") as f:
                f.write(pdf_bytes)

            conv_dir = await _run_marker_on_pdf(tmp_dir)
            outputs = await _collect_marker_outputs(conv_dir, pdf_stem=doc_id)

            html_key = None
            if "markdown" in outputs:
                md_bytes = outputs["markdown"].read_bytes()
                md_key = f"{prefix}{doc_id}.md"
                await s3.upload_bytes(md_bytes, bucket, md_key, content_type="text/markdown; charset=utf-8")
                logger.info(f"[marker] Загружен markdown: s3://{bucket}/{md_key}")

                # Сгенерируем HTML аннотатор и сохраним рядом
                md_text = md_bytes.decode('utf-8', errors='ignore')
                html = _build_markdown_annotator_html(md_text, doc_title=doc_id)
                html_key = f"{prefix}{doc_id}_annotator.html"
                await s3.upload_bytes(html.encode('utf-8'), bucket, html_key, content_type="text/html; charset=utf-8")
                logger.info(f"[marker] Загружен html-аннотатор: s3://{bucket}/{html_key}")

            if "meta" in outputs:
                meta_bytes = outputs["meta"].read_bytes()
                meta_key = f"{prefix}{doc_id}_meta.json"
                await s3.upload_bytes(meta_bytes, bucket, meta_key, content_type="application/json")
                logger.info(f"[marker] Загружен meta: s3://{bucket}/{meta_key}")

            img_exts = ("*.jpeg", "*.jpg", "*.png")
            for pattern in img_exts:
                for img in outputs["images_dir"].glob(pattern):
                    await s3.upload_bytes(img.read_bytes(), bucket, f"{prefix}{img.name}", content_type=mimetypes.guess_type(img.name)[0] or "image/jpeg")
                    logger.info(f"[marker] Загружено изображение: {img.name}")
        except Exception as e:
            logger.exception(f"Marker processing failed: {e}")
        finally:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    if pdf_exists:
        # если markdown отсутствует, запускаем конвертацию
        md_key = f"{prefix}{doc_id}.md"
        if not await s3.object_exists(bucket, md_key):
            # скачиваем существующий pdf и запускаем маркер
            existing_pdf = await s3.download_bytes(bucket, pdf_key)
            if not existing_pdf:
                raise HTTPException(status_code=500, detail="Не удалось прочитать существующий PDF из S3")
            background_tasks.add_task(process_marker_and_upload, existing_pdf)
            logger.info(f"[marker] Переобработка запущена для существующего PDF: doc_id={doc_id}")
            return DataExtractionResponse(success=True, doc_id=doc_id, message="Конвертация запущена для существующего PDF", files={"pdf": pdf_key})
        return DataExtractionResponse(success=True, doc_id=doc_id, message="Дубликат: уже существует", files={"pdf": pdf_key})

    uploaded = await s3.upload_bytes(raw, bucket, pdf_key, content_type="application/pdf")
    if not uploaded:
        raise HTTPException(status_code=500, detail="Не удалось сохранить PDF в S3")

    background_tasks.add_task(process_marker_and_upload, raw)

    return DataExtractionResponse(success=True, doc_id=doc_id, message="Файл принят, конвертация запущена", files={"pdf": pdf_key})


@app.get("/annotations/export")
async def export_annotations(doc_id: str):
    bucket = settings.S3_BUCKET_NAME
    prefix = f"documents/{doc_id}/"
    key = f"{prefix}{doc_id}_annotations.json"
    s3 = get_s3_client()
    if not await s3.object_exists(bucket, key):
        raise HTTPException(status_code=404, detail="Аннотации не найдены")
    data = await s3.download_bytes(bucket, key)
    return StreamingResponse(iter([data]), media_type="application/json")


class ImportAnnotationsRequest(BaseModel):
    doc_id: str
    annotations_json: Dict[str, Any]


@app.post("/annotations/import")
async def import_annotations(payload: ImportAnnotationsRequest):
    if not payload.doc_id:
        raise HTTPException(status_code=400, detail="doc_id обязателен")
    bucket = settings.S3_BUCKET_NAME
    prefix = f"documents/{payload.doc_id}/"
    key = f"{prefix}{payload.doc_id}_annotations.json"
    s3 = get_s3_client()
    ok = await s3.upload_bytes(
        json.dumps(payload.annotations_json, ensure_ascii=False).encode("utf-8"),
        bucket,
        key,
        content_type="application/json"
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Не удалось сохранить аннотации")
    return {"success": True, "key": key}


class DocumentAssetsResponse(BaseModel):
    success: bool
    doc_id: str
    markdown: Optional[str] = None
    images: List[str] = []
    image_urls: Dict[str, str] = {}


@app.get("/documents/{doc_id}/assets", response_model=DocumentAssetsResponse)
async def get_document_assets(doc_id: str):
    """Возвращает markdown и список изображений (ключей) для документа."""
    bucket = settings.S3_BUCKET_NAME
    prefix = f"documents/{doc_id}/"
    s3 = get_s3_client()

    md_key = f"{prefix}{doc_id}.md"
    markdown_text = None
    if await s3.object_exists(bucket, md_key):
        markdown_text = await s3.download_text(bucket, md_key)

    # перечислим изображения
    contents = await s3.list_objects(bucket, prefix)
    images: List[str] = []
    image_urls: Dict[str, str] = {}
    for obj in contents:
        key = obj.get('Key') or obj.get('Key'.lower()) or ''
        if key.lower().endswith(('.jpeg', '.jpg', '.png')):
            images.append(key)
            # presigned url
            url = await s3.get_object_url(bucket, key)
            if url:
                image_urls[SysPath(key).name] = url

    return DocumentAssetsResponse(success=True, doc_id=doc_id, markdown=markdown_text, images=images, image_urls=image_urls)


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Удаляет документ и все его файлы из S3 (префикс documents/{doc_id}/)."""
    bucket = settings.S3_BUCKET_NAME
    prefix = f"documents/{doc_id}/"
    s3 = get_s3_client()
    contents = await s3.list_objects(bucket, prefix)
    deleted = 0
    for obj in contents:
        key = obj.get('Key') or obj.get('Key'.lower()) or ''
        if key:
            ok = await s3.delete_object(bucket, key)
            if ok:
                deleted += 1
    return {"success": True, "deleted": deleted}


class DocumentItem(BaseModel):
    doc_id: str
    has_markdown: bool = False
    files: Dict[str, str] = {}


@app.get("/documents")
async def list_documents():
    """Список документов по префиксу documents/ из S3."""
    bucket = settings.S3_BUCKET_NAME
    s3 = get_s3_client()
    contents = await s3.list_objects(bucket, "documents/")
    doc_map: Dict[str, DocumentItem] = {}
    for obj in contents:
        key = obj.get('Key') or obj.get('key') or ''
        if not key.startswith('documents/'):
            continue
        parts = key.split('/')
        if len(parts) < 3:
            continue
        doc_id = parts[1]
        item = doc_map.get(doc_id)
        if not item:
            item = DocumentItem(doc_id=doc_id, has_markdown=False, files={})
            doc_map[doc_id] = item
        # track files
        if key.endswith('.md'):
            item.has_markdown = True
            item.files['markdown'] = key
        elif key.endswith('.pdf'):
            item.files['pdf'] = key
        elif key.endswith('.json'):
            item.files['json'] = key
    return {"success": True, "documents": [i.model_dump() for i in doc_map.values()]}

class S3ListResponse(BaseModel):
    objects: List[Dict[str, Any]]
    count: int

# ===== New: viewport edges endpoint models =====
class ViewportBounds(BaseModel):
    left: float
    right: float
    top: float
    bottom: float

class ViewportEdgesResponse(BaseModel):
    blocks: List[Dict[str, Any]]
    links: List[Dict[str, Any]]

# Эндпоинты для проверки здоровья
@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Проверяет здоровье API"""
    return {"status": "ok", "message": "API is healthy"}


@app.get("/layout/health")
async def check_layout_health():
    """Проверяет здоровье сервиса укладки"""
    try:
        client = get_layout_client()
        is_healthy = await client.health_check()
        if is_healthy:
            return {"status": "ok", "message": "Layout service is healthy"}
        else:
            return {"status": "error", "message": "Layout service is not healthy"}, 503
    except Exception as e:
        logger.error(f"Layout health check error: {e}")
        return {"status": "error", "message": str(e)}, 503


# Эндпоинт для получения укладки
@app.post("/layout")
async def calculate_layout(request: LayoutRequest) -> Dict[str, Any]:
    """Рассчитывает укладку для заданного графа"""
    try:
        client = get_layout_client()
        
        # Преобразуем запрос в формат для сервиса укладки
        blocks = [
            {
                "id": block.id,
                "content": block.content,
                "metadata": block.metadata
            }
            for block in request.blocks
        ]
        
        links = [
            {
                "id": link.id,
                "source_id": link.source_id,
                "target_id": link.target_id,
                "metadata": link.metadata
            }
            for link in request.links
        ]
        
        # Настройки алгоритма
        options = LayoutOptions(
            sublevel_spacing=request.sublevel_spacing,
            layer_spacing=request.layer_spacing,
            optimize_layout=request.optimize_layout
        )
        
        # Получаем укладку
        result = await client.calculate_layout(blocks, links, options)
        
        # Проверяем результат
        if not result.get("success", False):
            error_msg = result.get("error", "Неизвестная ошибка при расчете укладки")
            logger.error(f"Layout calculation error: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
        
        return result
        
    except Exception as e:
        logger.error(f"Layout calculation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    return {
        "message": "Knowledge Map API", 
        "graphql": "/graphql",
        "docs": "/docs",
        "layout": "/layout/calculate",
        "layout_health": "/layout/health",
        "neo4j_browser": "http://localhost:7474"
    }

@app.get("/layout/articles")
async def get_articles_layout() -> Dict[str, Any]:
    """Получает укладку только для статей (блоков с типом "Article")"""
    try:
        logger.info("Starting articles layout calculation from Neo4j")
        
        # Читаем граф из Neo4j: узлы помечены как Article, связи - BIBLIOGRAPHIC_LINK
        logger.info("Querying articles from Neo4j")
        blocks_query = """
        MATCH (n:Article)
        WHERE n.layout_status IN ['in_longest_path','placed_layers','placed']
          AND n.x IS NOT NULL AND n.y IS NOT NULL
          AND (
            EXISTS((n)-[:BIBLIOGRAPHIC_LINK]->(:Article)) OR 
            EXISTS((:Article)-[:BIBLIOGRAPHIC_LINK]->(n))
          )
        RETURN n.uid as id,
               n.content as content,
               n.layer as layer,
               n.level as level,
               n.sublevel_id as sublevel_id,
               n.is_pinned as is_pinned,
               n.physical_scale as physical_scale,
               n.x as x,
               n.y as y
        """
        blocks_result, _ = db.cypher_query(blocks_query)
        logger.info(f"Found {len(blocks_result)} articles total")
        
        if not blocks_result:
            logger.warning("No articles found in Neo4j")
            raise HTTPException(status_code=404, detail="В базе данных нет статей Article. Загрузите данные.")
        
        links_query = """
        MATCH (s:Article)-[r:BIBLIOGRAPHIC_LINK]->(t:Article)
        RETURN s.uid as source_id, t.uid as target_id
        """
        links_result, _ = db.cypher_query(links_query)
        
        # Используем настоящие ID из базы данных
        blocks = []
        for row in blocks_result:
            layer_val = int(row[2] or 0)
            level_val = int(row[3] or 0)
            
            # Используем реальные координаты из базы данных или вычисляем их
            if row[7] is not None and row[8] is not None:
                # Координаты уже заданы в базе данных
                x_coord = float(row[7])
                y_coord = float(row[8])
            else:
                # Вычисляем координаты на основе layer и level
                # Используем те же коэффициенты, что и в алгоритме укладки
                LAYER_SPACING = 240  # BLOCK_WIDTH (200) + HORIZONTAL_GAP (40)
                LEVEL_SPACING = 130  # BLOCK_HEIGHT (80) + VERTICAL_GAP (50)
                
                x_coord = float(layer_val * LAYER_SPACING)
                y_coord = float(level_val * LEVEL_SPACING)
            
            block_data = {
                "id": str(row[0]),
                "content": str(row[1] or ""),
                "layer": layer_val,
                "level": level_val,
                "sublevel_id": int(row[4] or 0),
                "is_pinned": bool(row[5]) if row[5] is not None else False,
                "physical_scale": int(row[6] or 0) if row[6] is not None else 0,
                "x": x_coord,
                "y": y_coord,
                "metadata": {}
            }
            if block_data.get("is_pinned"):
                logger.info(f"Found pinned node in DB: {block_data['id']} - is_pinned: {block_data['is_pinned']}")
            blocks.append(block_data)
        
        # Преобразуем связи
        links_for_layout = []
        for row in links_result:
            link_id = f"{row[0]}-{row[1]}"  # Генерируем ID из source и target
            source_id = str(row[0])
            target_id = str(row[1])
            links_for_layout.append(
                {"id": link_id, "source_id": source_id, "target_id": target_id}
            )

        if not blocks:
            raise HTTPException(status_code=404, detail="В базе данных нет статей.")
        
        # Удаляем потенциальные циклы: оставляем рёбра только вперёд по слоям/уровням
        # TODO это должно делаться на стороне бэкенда
        level_index = {b["id"]: (b.get("layer", 0), b.get("level", 0)) for b in blocks}
        filtered_links = []
        for l in links_for_layout:
            s = l["source_id"]; t = l["target_id"]
            if s in level_index and t in level_index:
                sl, sv = level_index[s]
                tl, tv = level_index[t]
                if (tl > sl) or (tl == sl and tv > sv):
                    filtered_links.append(l)
        if len(filtered_links) < len(links_for_layout):
            logger.info(f"Filtered potential cycles: kept {len(filtered_links)} of {len(links_for_layout)} links")
        
        # Получаем укладку
        client = get_layout_client()
        try:
            result = await client.calculate_layout(
                blocks=blocks,
                links=filtered_links,
                options=LayoutOptions(
                    sublevel_spacing=200,
                    layer_spacing=250,
                    optimize_layout=False
                )
            )
            return result
        except Exception as e:
            logger.error(f"Error in articles layout calculation: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Ошибка при расчете укладки статей: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error calculating articles layout from Neo4j: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при получении данных статей из Neo4j: {str(e)}")


# ===== New: edges-by-viewport endpoint =====
@app.post("/api/articles/edges_by_viewport", response_model=ViewportEdgesResponse)
async def get_edges_by_viewport(bounds: ViewportBounds, limit_per_node: int = 200):
    """Возвращает узлы в окне и рёбра, у которых хотя бы один конец попадает в окно.
    Для второй вершины возвращаем координаты (если x,y отсутствуют — вычисляем из layer/level).
    """
    try:
        LAYER_SPACING = 240
        LEVEL_SPACING = 130

        # Узлы в окне - только со связями
        nodes_query = (
            "MATCH (n:Article) "
            "WHERE coalesce(n.x, toFloat(coalesce(n.layer,0))*$LAYER_SPACING) >= $left "
            "  AND coalesce(n.x, toFloat(coalesce(n.layer,0))*$LAYER_SPACING) <= $right "
            "  AND coalesce(n.y, toFloat(coalesce(n.level,0))*$LEVEL_SPACING) >= $top "
            "  AND coalesce(n.y, toFloat(coalesce(n.level,0))*$LEVEL_SPACING) <= $bottom "
            "  AND ("
            "    EXISTS((n)-[:BIBLIOGRAPHIC_LINK]->(:Article)) OR "
            "    EXISTS((:Article)-[:BIBLIOGRAPHIC_LINK]->(n))"
            "  ) "
            "RETURN n.uid as id, n.layer as layer, n.level as level, n.x as x, n.y as y"
        )
        params = {
            "left": bounds.left,
            "right": bounds.right,
            "top": bounds.top,
            "bottom": bounds.bottom,
            "LAYER_SPACING": LAYER_SPACING,
            "LEVEL_SPACING": LEVEL_SPACING,
        }
        nodes_result, _ = db.cypher_query(nodes_query, params)
        ids_in_view = [str(r[0]) for r in nodes_result]

        # Рёбра, где хотя бы один конец в окне, с ограничением fan-out
        edges_query = (
            "UNWIND $ids AS vid "
            "MATCH (s:Article {uid: vid})-[:BIBLIOGRAPHIC_LINK]->(t:Article) "
            "WITH s, t ORDER BY t.uid LIMIT $limit_per_node "
            "RETURN s.uid as sid, s.layer as sl, s.level as sv, s.x as sx, s.y as sy, "
            "       t.uid as tid, t.layer as tl, t.level as tv, t.x as tx, t.y as ty "
            "UNION "
            "UNWIND $ids AS vid "
            "MATCH (s:Article)-[:BIBLIOGRAPHIC_LINK]->(t:Article {uid: vid}) "
            "WITH s, t ORDER BY s.uid LIMIT $limit_per_node "
            "RETURN s.uid as sid, s.layer as sl, s.level as sv, s.x as sx, s.y as sy, "
            "       t.uid as tid, t.layer as tl, t.level as tv, t.x as tx, t.y as ty"
        )
        edges_result, _ = db.cypher_query(edges_query, {"ids": ids_in_view, "limit_per_node": limit_per_node})

        # Собираем выдачу
        blocks_map: dict[str, dict] = {}
        def pack_block(uid, layer, level, x, y):
            if uid in blocks_map:
                return
            if x is None:
                x = float((layer or 0) * LAYER_SPACING)
            if y is None:
                y = float((level or 0) * LEVEL_SPACING)
            blocks_map[uid] = {
                "id": str(uid),
                "layer": int(layer or 0),
                "level": int(level or 0),
                "x": float(x),
                "y": float(y),
            }

        # Добавляем видимые узлы
        for r in nodes_result:
            pack_block(r[0], r[1], r[2], r[3], r[4])

        links: list[dict] = []
        seen = set()
        for r in edges_result:
            sid, sl, sv, sx, sy, tid, tl, tv, tx, ty = r
            pack_block(sid, sl, sv, sx, sy)
            pack_block(tid, tl, tv, tx, ty)
            key = f"{sid}->{tid}"
            if key in seen:
                continue
            seen.add(key)
            links.append({"id": key, "source_id": str(sid), "target_id": str(tid)})

        return ViewportEdgesResponse(blocks=list(blocks_map.values()), links=links)
    except Exception as e:
        logger.error(f"edges_by_viewport failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/layout/articles_all")
async def get_all_articles_layout() -> Dict[str, Any]:
    """Возвращает все блоки и связи из графа статей."""
    try:
        logger.info("Loading all articles and links")

        # Запрос всех статей - только со связями
        nodes_query = """
        MATCH (n:Article)
        WHERE n.layout_status IN ['in_longest_path','placed_layers','placed']
          AND n.x IS NOT NULL AND n.y IS NOT NULL
          AND (
            EXISTS((n)-[:BIBLIOGRAPHIC_LINK]->(:Article)) OR 
            EXISTS((:Article)-[:BIBLIOGRAPHIC_LINK]->(n))
          )
        RETURN n.uid as id,
               coalesce(n.title, n.name, n.content, toString(n.uid)) as title,
               n.layer as layer,
               n.level as level,
               n.sublevel_id as sublevel_id,
               n.is_pinned as is_pinned,
               n.physical_scale as physical_scale,
               n.x as x,
               n.y as y,
               n.layout_status as layout_status
        """
        blocks_result, _ = db.cypher_query(nodes_query)

        if not blocks_result:
            return {
                "success": True,
                "blocks": [],
                "links": [],
                "levels": [],
                "sublevels": [],
                "total": 0
            }

        blocks: list[dict] = []
        for row in blocks_result:
            block = {
                "id": str(row[0]),
                "content": str(row[1] or ""),
                "layer": int(row[2]) if row[2] is not None else None,
                "level": int(row[3]) if row[3] is not None else None,
                "sublevel_id": int(row[4] or 0),
                "is_pinned": bool(row[5]) if row[5] is not None else False,
                "physical_scale": int(row[6] or 0) if row[6] is not None else 0,
                "x": float(row[7]) if row[7] is not None else 0.0,
                "y": float(row[8]) if row[8] is not None else 0.0,
                "layout_status": str(row[9] or ""),
                "metadata": {},
            }
            blocks.append(block)

        # Запрос всех связей
        links_query = """
        MATCH (s:Article)-[r:BIBLIOGRAPHIC_LINK]->(t:Article)
        RETURN s.uid as source_id, t.uid as target_id
        """
        links_result, _ = db.cypher_query(links_query)
        
        links: list[dict] = []
        for row in links_result:
            link_id = f"{row[0]}-{row[1]}"  # Генерируем ID из source и target
            links.append({
                "id": link_id,
                "source_id": str(row[0]),
                "target_id": str(row[1]),
            })

        logger.info(f"Loaded {len(blocks)} blocks and {len(links)} links")

        return {
            "success": True,
            "blocks": blocks,
            "links": links,
            "levels": [],
            "sublevels": [],
            "total": len(blocks)
        }
    except Exception as e:
        logger.error(f"Error loading all articles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/layout/articles_page")
async def get_articles_layout_page(
    offset: int = 0,
    limit: int = 2000,
    center_x: float = 0.0,
    center_y: float = 0.0,
) -> Dict[str, Any]:
    """Возвращает часть графа статей, упорядоченную по близости к (center_x, center_y).

    - Узлы и связи берутся из Neo4j (`Node`, `BIBLIOGRAPHIC_LINK`).
    - Связи фильтруются, чтобы не допустить циклов (вперёд по (layer, level)).
    - Укладка считается только для выбранной партии.
    """
    try:
        logger.info(
            f"Articles page requested: offset={offset}, limit={limit}, center=({center_x},{center_y})"
        )
        print(f"DEBUG: Articles page requested: offset={offset}, limit={limit}, center=({center_x},{center_y})")

        # Всего статей (для прогресса) - только со связями
        total_query = """
        MATCH (n:Article)
        WHERE n.layout_status IN ['in_longest_path','placed_layers','placed']
          AND n.x IS NOT NULL AND n.y IS NOT NULL
          AND (
            EXISTS((n)-[:BIBLIOGRAPHIC_LINK]->(:Article)) OR 
            EXISTS((:Article)-[:BIBLIOGRAPHIC_LINK]->(n))
          )
        RETURN count(n) as total
        """
        total_res, _ = db.cypher_query(total_query)
        logger.info(f"Total query result: {total_res}")
        total_articles = int(total_res[0][0]) if total_res and total_res[0] and total_res[0][0] is not None else 0
        logger.info(f"Total articles: {total_articles}")

        # Запрос с учетом center_x и center_y для фильтрации по близости
        # ИСПРАВЛЕНИЕ: Загружаем только статьи, которые имеют связи (исходящие или входящие)
        nodes_query = """
        MATCH (n:Article)
        WHERE n.layout_status IN ['in_longest_path','placed_layers','placed']
          AND n.x IS NOT NULL AND n.y IS NOT NULL
          AND (
            EXISTS((n)-[:BIBLIOGRAPHIC_LINK]->(:Article)) OR 
            EXISTS((:Article)-[:BIBLIOGRAPHIC_LINK]->(n))
          )
        RETURN n.uid as id,
               coalesce(n.title, n.name, n.content, toString(n.uid)) as title,
               n.layer as layer,
               n.level as level,
               coalesce(n.sublevel_id, 0) as sublevel_id,
               coalesce(n.is_pinned, false) as is_pinned,
               coalesce(n.physical_scale, 0) as physical_scale,
               n.x as x,
               n.y as y,
               n.layout_status as layout_status,
               coalesce(n.topo_order, 0) as topo_order,
               sqrt((n.x - $center_x) * (n.x - $center_x) + (n.y - $center_y) * (n.y - $center_y)) as distance
        ORDER BY distance ASC, n.layer ASC, n.topo_order ASC
        SKIP $offset LIMIT $limit
        """
        blocks_result, _ = db.cypher_query(
            nodes_query,
            {
                "offset": offset,
                "limit": limit,
                "center_x": center_x,
                "center_y": center_y,
            },
        )
        logger.info(f"Blocks query result: {len(blocks_result) if blocks_result else 0} rows")

        if not blocks_result:
            return {
                "success": True,
                "blocks": [],
                "links": [],
                "levels": [],
                "sublevels": [],
                "page": {"offset": offset, "limit": limit, "returned": 0, "total": total_articles},
            }

        blocks: list[dict] = []
        selected_ids: set[str] = set()
        for row in blocks_result:
            block = {
                "id": str(row[0]),
                "content": str(row[1] or ""),
                "layer": int(row[2]) if row[2] is not None else None,
                "level": int(row[3]) if row[3] is not None else None,
                "sublevel_id": int(row[4] or 0),
                "is_pinned": bool(row[5]) if row[5] is not None else False,
                "physical_scale": int(row[6] or 0) if row[6] is not None else 0,
                "x": float(row[7]) if row[7] is not None else 0.0,
                "y": float(row[8]) if row[8] is not None else 0.0,
                "metadata": {},
            }
            blocks.append(block)
            selected_ids.add(block["id"])

        # ИСПРАВЛЕНИЕ: Загружаем ВСЕ связи для выбранных статей, включая целевые статьи
        # Это гарантирует, что все связи будут видны, даже если целевая статья не в текущей странице
        links_query = """
        MATCH (s:Article)-[r:BIBLIOGRAPHIC_LINK]->(t:Article)
        WHERE s.uid IN $ids OR t.uid IN $ids
        RETURN s.uid as source_id, t.uid as target_id
        """
        links_result, _ = db.cypher_query(links_query, {"ids": list(selected_ids)})
        links_for_layout: list[dict] = []
        for row in links_result:
            link_id = f"{row[0]}-{row[1]}"  # Генерируем ID из source и target
            links_for_layout.append(
                {
                    "id": link_id,
                    "source_id": str(row[0]),
                    "target_id": str(row[1]),
                }
            )

        # ИСПРАВЛЕНИЕ: Загружаем целевые статьи, которые не попали в текущую страницу, но имеют связи
        target_ids = set()
        for link in links_for_layout:
            target_ids.add(link["target_id"])
            target_ids.add(link["source_id"])
        
        # Находим целевые статьи, которых нет в текущей странице
        missing_target_ids = target_ids - selected_ids
        
        if missing_target_ids:
            # Загружаем недостающие целевые статьи
            missing_targets_query = """
            MATCH (n:Article)
            WHERE n.uid IN $missing_ids
              AND n.layout_status IN ['in_longest_path','placed_layers','placed']
              AND n.x IS NOT NULL AND n.y IS NOT NULL
            RETURN n.uid as id,
                   coalesce(n.title, n.name, n.content, toString(n.uid)) as title,
                   n.layer as layer,
                   n.level as level,
                   coalesce(n.sublevel_id, 0) as sublevel_id,
                   coalesce(n.is_pinned, false) as is_pinned,
                   coalesce(n.physical_scale, 0) as physical_scale,
                   n.x as x,
                   n.y as y,
                   n.layout_status as layout_status
            """
            missing_targets_result, _ = db.cypher_query(missing_targets_query, {"missing_ids": list(missing_target_ids)})
            
            # Добавляем недостающие статьи к блокам
            for row in missing_targets_result:
                block = {
                    "id": str(row[0]),
                    "content": str(row[1] or ""),
                    "layer": int(row[2]) if row[2] is not None else None,
                    "level": int(row[3]) if row[3] is not None else None,
                    "sublevel_id": int(row[4] or 0),
                    "is_pinned": bool(row[5]) if row[5] is not None else False,
                    "physical_scale": int(row[6] or 0) if row[6] is not None else 0,
                    "x": float(row[7]) if row[7] is not None else 0.0,
                    "y": float(row[8]) if row[8] is not None else 0.0,
                    "metadata": {},
                }
                blocks.append(block)
                selected_ids.add(block["id"])
            
            logger.info(f"Added {len(missing_targets_result)} missing target articles to ensure all connections are visible")

        # API просто возвращает все связи как есть - разворот циклов делается в алгоритме укладки
        filtered_links = links_for_layout

        # Возвращаем напрямую без вызова gRPC укладки (уровни/подуровни уже в БД)
        return {
            "success": True,
            "blocks": blocks,
            "links": filtered_links,
            "levels": [],
            "sublevels": [],
            "page": {
                "offset": offset,
                "limit": limit,
                "returned": len(blocks),
                "total": total_articles,
            },
        }
    except Exception as e:
        logger.error(f"Error in paged articles layout: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/layout/neo4j")
async def get_layout_from_neo4j(user_id: str | None = None) -> Dict[str, Any]:
    try:
        logger.info("Starting layout calculation from Neo4j")
        
        # Запрос блоков из Neo4j
        logger.info("Querying blocks from Neo4j")
        blocks_query = """
        MATCH (b:Block)
        RETURN b.uid as id, b.content as content, b.layer as layer, b.level as level, b.is_pinned as is_pinned, b.physical_scale as physical_scale
        """
        blocks_result, _ = db.cypher_query(blocks_query)
        logger.info(f"Found {len(blocks_result)} blocks total")
        
        if not blocks_result:
            logger.warning("No blocks found in Neo4j")
            raise HTTPException(status_code=404, detail="В базе данных нет блоков. Пожалуйста, запустите скрипт заполнения тестовыми данными.")
        
        # Запрос связей из Neo4j (упрощённый без проверки циклов)
        links_query = """
        MATCH (b1:Block)-[r:LINK_TO]->(b2:Block)
        RETURN r.uid as id, b1.uid as source_id, b2.uid as target_id
        """
        links_result, _ = db.cypher_query(links_query)
        
        # Используем настоящие ID из базы данных
        blocks = []
        for row in blocks_result:
            block_data = {
                "id": str(row[0]),
                "content": str(row[1] or ""),
                "layer": int(row[2] or 0),
                "level": int(row[3] or 0),
                "is_pinned": bool(row[4]) if row[4] is not None else False,
                "physical_scale": int(row[5] or 0) if row[5] is not None else 0,
                "metadata": {}
            }
            if block_data["is_pinned"]:
                logger.info(f"Found pinned block in DB: {block_data['id']} - is_pinned: {block_data['is_pinned']}")
            blocks.append(block_data)
        
        # Преобразуем связи
        links_for_layout = []
        for row in links_result:
            link_id = f"{row[0]}-{row[1]}"  # Генерируем ID из source и target
            source_id = str(row[0])
            target_id = str(row[1])
            links_for_layout.append(
                {"id": link_id, "source_id": source_id, "target_id": target_id}
            )

        if not blocks:
            raise HTTPException(status_code=404, detail="В базе данных нет блоков.")
        
        # Получаем укладку
        client = get_layout_client()
        try:
            result = await client.calculate_layout(
                blocks=blocks,
                links=links_for_layout,
                options=LayoutOptions(
                    sublevel_spacing=200,
                    layer_spacing=250,
                    optimize_layout=True
                )
            )

            
            # Сохраняем обновлённые уровни и подуровни обратно в базу данных
            if result.get('success') and result.get('blocks'):
                logger.info("🔥 СОХРАНЯЕМ ОБНОВЛЁННЫЕ УРОВНИ БЛОКОВ В БАЗУ ДАННЫХ...")
                
                # Сначала покажем что пришло из алгоритма
                pinned_in_result = [b for b in result['blocks'] if b.get('is_pinned', False)]
                logger.info(f"🔥 ЗАКРЕПЛЁННЫХ БЛОКОВ В РЕЗУЛЬТАТЕ: {len(pinned_in_result)}")
                for block_info in pinned_in_result:
                    logger.info(f"   🔥 PINNED RESULT: {block_info['id'][:8]}... level={block_info['level']}, sublevel={block_info['sublevel_id']}")
                
                with db.transaction:
                    updates_count = 0
                    for block_info in result['blocks']:
                        try:
                            block = Block.nodes.get(uid=block_info['id'])
                            # Обновляем уровень и подуровень только если они изменились
                            old_level = block.level
                            old_sublevel = block.sublevel_id
                            new_level = block_info['level']
                            new_sublevel = block_info['sublevel_id']
                            
                            if old_level != new_level or old_sublevel != new_sublevel:
                                block.level = new_level
                                block.sublevel_id = new_sublevel
                                block.save()
                                updates_count += 1
                                
                                if block.is_pinned:
                                    logger.info(f"🔥 PINNED UPDATED: {block_info['id'][:8]}... level {old_level}->{new_level}, sublevel {old_sublevel}->{new_sublevel}")
                                else:
                                    logger.info(f"Updated block {block_info['id'][:8]}...: level {old_level}->{new_level}, sublevel {old_sublevel}->{new_sublevel}")
                                
                        except DoesNotExist:
                            logger.warning(f"Block {block_info['id']} not found in database")
                        except Exception as e:
                            logger.error(f"Error updating block {block_info['id']}: {e}")
                            
                logger.info(f"🔥 ✓ ОБНОВЛЕНО {updates_count} БЛОКОВ В БАЗЕ ДАННЫХ")
            
            return result
        except Exception as e:
            logger.error(f"Error in layout calculation: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Ошибка при расчете укладки: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error calculating layout from Neo4j: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при получении данных из Neo4j: {str(e)}")


# === CRUD Эндпоинты для блоков и связей ===

@app.post("/api/blocks", response_model=Dict[str, Any])
async def create_block(block_input: BlockInput):
    """Создает новый блок в Neo4j."""
    try:
        # Используем транзакцию для атомарности
        with db.transaction:
            b = Block(content=block_input.content)
            b.save()
            b.refresh()
        
        response_block = {
            "id": b.uid,
            "content": b.content,
            "level": b.level,
            "layer": b.layer,
            "sublevel_id": b.sublevel_id,
            "is_pinned": b.is_pinned,
            "physical_scale": getattr(b, 'physical_scale', 0),
        }
        return {"success": True, "block": response_block}
    except Exception as e:
        logger.error(f"Error creating block: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/blocks/{block_id}", response_model=Dict[str, Any])
async def update_block(block_id: str, block_input: BlockInput):
    """Обновляет содержимое блока в Neo4j."""
    try:
        with db.transaction:
            block = Block.nodes.get(uid=block_id)
            block.content = block_input.content
            block.save()
            
        response_block = {
            "id": block.uid,
            "content": block.content,
            "level": block.level,
            "layer": block.layer,
            "sublevel_id": block.sublevel_id,
            "is_pinned": block.is_pinned,
            "physical_scale": getattr(block, 'physical_scale', 0),
        }
        return {"success": True, "block": response_block}
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Block not found")
    except Exception as e:
        logger.error(f"Error updating block: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/links", response_model=Dict[str, Any])
async def create_link(link_input: LinkInput):
    """Создает новую связь между блоками."""
    try:
        # Используем транзакцию для надежности
        with db.transaction:
            source_block = Block.nodes.get(uid=link_input.source)
            target_block = Block.nodes.get(uid=link_input.target)

            # connect теперь возвращает экземпляр LinkRel, который мы можем сохранить
            rel = source_block.target.connect(target_block)
            rel.save() # <-- Явно сохраняем саму связь
        
        response_link = {
            "id": rel.uid,
            "source_id": source_block.uid,
            "target_id": target_block.uid
        }
        return {"success": True, "link": response_link}

    except DoesNotExist:
        logger.error(f"Attempted to create link with non-existent block. Source: {link_input.source}, Target: {link_input.target}")
        raise HTTPException(status_code=404, detail="Один из блоков для создания связи не найден.")
    except Exception as e:
        logger.error(f"Error creating link: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка при создании связи: {e}")

@app.post("/api/blocks/create_and_link", response_model=Dict[str, Any])
async def create_block_and_link(data: CreateAndLinkInput):
    """Атомарно создает новый блок и связь с существующим блоком."""
    try:
        source_block = Block.nodes.get(uid=data.source_block_id)
        
        # Создаем новый блок
        new_block = Block(content=data.new_block_content, layer=source_block.layer + 1).save()
        
        # Создаем связь
        if data.link_direction == 'from_source':
            link = source_block.target.connect(new_block)
        else: # to_source
            link = new_block.target.connect(source_block)
        
        # Получаем полный обновленный граф из Neo4j
        # (Эта логика дублирует /layout/neo4j, но необходима для получения координат)
        blocks_query = "MATCH (b:Block) RETURN b.uid as id, b.content as content, b.layer as layer, b.level as level, b.is_pinned as is_pinned, b.physical_scale as physical_scale"
        blocks_result, _ = db.cypher_query(blocks_query)
        
        links_query = "MATCH (b1:Block)-[r:LINK_TO]->(b2:Block) RETURN r.uid as id, b1.uid as source_id, b2.uid as target_id"
        links_result, _ = db.cypher_query(links_query)

        blocks_for_layout = [{"id": str(r[0]), "content": str(r[1] or ""), "layer": int(r[2] or 0), "level": int(r[3] or 0), "is_pinned": bool(r[4]) if r[4] is not None else False, "physical_scale": int(r[5] or 0) if r[5] is not None else 0, "metadata": {}} for r in blocks_result]
        links_for_layout = [{"id": str(r[0]) if r[0] else None, "source_id": str(r[1]), "target_id": str(r[2])} for r in links_result]
        
        # Вызываем сервис укладки
        client = get_layout_client()
        layout_result = await client.calculate_layout(blocks_for_layout, links_for_layout)
        
        if not layout_result.get("success"):
            raise HTTPException(status_code=500, detail="Layout service failed after creating block and link.")

        # Находим данные нового блока в результатах укладки
        final_new_block_data = next((b for b in layout_result.get("blocks", []) if b["id"] == new_block.uid), None)

        if not final_new_block_data:
            raise HTTPException(status_code=500, detail="Could not find new block in layout result.")

        return {
            "success": True,
            "new_block": final_new_block_data,
            "new_link": {
                "id": link.uid,
                "source_id": link.start_node().uid,
                "target_id": link.end_node().uid,
            }
        }
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Source block not found")
    except Exception as e:
        logger.error(f"Error creating block and link: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/blocks/{block_id}", response_model=Dict[str, Any])
async def delete_block(block_id: str):
    """Удаляет блок и все связанные с ним связи."""
    try:
        with db.transaction:
            block = Block.nodes.get(uid=block_id)
            
            # Удаляем все связи, где этот блок является источником или целью
            # Сначала удаляем исходящие связи
            outgoing_query = """
            MATCH (source:Block {uid: $block_id})-[r:LINK_TO]->(target:Block)
            DELETE r
            """
            db.cypher_query(outgoing_query, {"block_id": block_id})
            
            # Затем удаляем входящие связи
            incoming_query = """
            MATCH (source:Block)-[r:LINK_TO]->(target:Block {uid: $block_id})
            DELETE r
            """
            db.cypher_query(incoming_query, {"block_id": block_id})
            
            # Удаляем сам блок
            block.delete()
            
        return {"success": True, "message": f"Block {block_id} deleted successfully"}
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Block not found")
    except Exception as e:
        logger.error(f"Error deleting block: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/links/{link_id}", response_model=Dict[str, Any])
async def delete_link(link_id: str):
    """Удаляет связь по её ID."""
    try:
        with db.transaction:
            # Находим и удаляем связь по её UID
            delete_query = """
            MATCH ()-[r:LINK_TO {uid: $link_id}]->()
            DELETE r
            RETURN count(r) as deleted_count
            """
            result, _ = db.cypher_query(delete_query, {"link_id": link_id})
            deleted_count = result[0][0] if result else 0
            
            if deleted_count == 0:
                raise HTTPException(status_code=404, detail="Link not found")
                
        return {"success": True, "message": f"Link {link_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting link: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/blocks/{block_id}/pin", response_model=Dict[str, Any])
async def pin_block(block_id: str):
    """Закрепляет блок за уровнем с сохранением его текущего уровня."""
    logger.info(f"🔥 PIN_BLOCK CALLED: {block_id} - НОВАЯ ВЕРСИЯ КОДА!")
    try:
        with db.transaction:
            block = Block.nodes.get(uid=block_id)
            logger.info(f"📊 Before pinning: block {block_id} is_pinned = {block.is_pinned}, level = {block.level}")
            
            # Если у блока нет уровня, устанавливаем его текущий level из позиции в графе
            if block.level == 0:
                # Получаем все блоки для определения текущего уровня
                blocks_query = "MATCH (b:Block) RETURN b.uid as id, b.content as content, b.layer as layer, b.level as level, b.is_pinned as is_pinned, b.physical_scale as physical_scale"
                blocks_result, _ = db.cypher_query(blocks_query)
                
                links_query = "MATCH (b1:Block)-[r:LINK_TO]->(b2:Block) RETURN r.uid as id, b1.uid as source_id, b2.uid as target_id"
                links_result, _ = db.cypher_query(links_query)

                blocks_for_layout = [{"id": str(r[0]), "content": str(r[1] or ""), "layer": int(r[2] or 0), "level": int(r[3] or 0), "is_pinned": bool(r[4]) if r[4] is not None else False, "physical_scale": int(r[5] or 0) if r[5] is not None else 0, "metadata": {}} for r in blocks_result]
                links_for_layout = [{"id": str(r[0]) if r[0] else None, "source_id": str(r[1]), "target_id": str(r[2])} for r in links_result]
                
                # Получаем текущую укладку для определения уровня блока
                client = get_layout_client()
                layout_result = await client.calculate_layout(blocks_for_layout, links_for_layout)
                
                if layout_result.get('success') and layout_result.get('blocks'):
                    # Находим уровень текущего блока в результатах укладки
                    current_block_level = 0
                    for block_info in layout_result['blocks']:
                        if block_info['id'] == block_id:
                            current_block_level = block_info['level']
                            break
                    
                    block.level = current_block_level
                    logger.info(f"Setting block {block_id} level to {current_block_level} based on current layout")
            
            block.is_pinned = True
            block.save()
            block.refresh()
            logger.info(f"After pinning: block {block_id} is_pinned = {block.is_pinned}, level = {block.level}")
            
        return {"success": True, "message": f"Block {block_id} pinned successfully at level {block.level}"}
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Block not found")
    except Exception as e:
        logger.error(f"Error pinning block: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/blocks/{block_id}/unpin", response_model=Dict[str, Any])
async def unpin_block(block_id: str):
    """Открепляет блок от уровня."""
    try:
        with db.transaction:
            block = Block.nodes.get(uid=block_id)
            block.is_pinned = False
            block.save()
            
        return {"success": True, "message": f"Block {block_id} unpinned successfully"}
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Block not found")
    except Exception as e:
        logger.error(f"Error unpinning block: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/blocks/{block_id}/pin_with_scale", response_model=Dict[str, Any])
async def pin_block_with_scale(block_id: str, data: PinWithScaleInput):
    """Закрепляет блок за уровнем с указанным физическим масштабом."""
    logger.info(f"🔥 PIN_BLOCK_WITH_SCALE CALLED: {block_id} with scale {data.physical_scale}")
    try:
        with db.transaction:
            block = Block.nodes.get(uid=block_id)
            logger.info(f"📊 Before pinning with scale: block {block_id} is_pinned = {block.is_pinned}, level = {block.level}, physical_scale = {getattr(block, 'physical_scale', 'not set')}")
            
            # Если у блока нет уровня, устанавливаем его текущий level из позиции в графе
            if block.level == 0:
                # Получаем все блоки для определения текущего уровня
                blocks_query = "MATCH (b:Block) RETURN b.uid as id, b.content as content, b.layer as layer, b.level as level, b.is_pinned as is_pinned, b.physical_scale as physical_scale"
                blocks_result, _ = db.cypher_query(blocks_query)
                
                links_query = "MATCH (b1:Block)-[r:LINK_TO]->(b2:Block) RETURN r.uid as id, b1.uid as source_id, b2.uid as target_id"
                links_result, _ = db.cypher_query(links_query)

                blocks_for_layout = [{"id": str(r[0]), "content": str(r[1] or ""), "layer": int(r[2] or 0), "level": int(r[3] or 0), "is_pinned": bool(r[4]) if r[4] is not None else False, "physical_scale": int(r[5] or 0) if r[5] is not None else 0, "metadata": {}} for r in blocks_result]
                links_for_layout = [{"id": str(r[0]) if r[0] else None, "source_id": str(r[1]), "target_id": str(r[2])} for r in links_result]
                
                # Получаем текущую укладку для определения уровня блока
                client = get_layout_client()
                layout_result = await client.calculate_layout(blocks_for_layout, links_for_layout)
                
                if layout_result.get('success') and layout_result.get('blocks'):
                    # Находим уровень текущего блока в результатах укладки
                    current_block_level = 0
                    for block_info in layout_result['blocks']:
                        if block_info['id'] == block_id:
                            current_block_level = block_info['level']
                            break
                    
                    block.level = current_block_level
                    logger.info(f"Setting block {block_id} level to {current_block_level} based on current layout")
            
            # Устанавливаем физический масштаб и закрепляем
            block.is_pinned = True
            block.physical_scale = data.physical_scale
            block.save()
            block.refresh()
            logger.info(f"After pinning with scale: block {block_id} is_pinned = {block.is_pinned}, level = {block.level}, physical_scale = {block.physical_scale}")
            
        return {"success": True, "message": f"Block {block_id} pinned successfully at level {block.level} with physical scale {data.physical_scale}"}
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Block not found")
    except Exception as e:
        logger.error(f"Error pinning block with scale: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/blocks/{block_id}/move_to_level", response_model=Dict[str, Any])
async def move_block_to_level(block_id: str, data: MoveToLevelInput):
    """Перемещает закрепленный блок на указанный уровень."""
    logger.info(f"🔄 MOVE_BLOCK_TO_LEVEL CALLED: {block_id} -> level {data.target_level}")
    try:
        with db.transaction:
            block = Block.nodes.get(uid=block_id)
            
            # Проверяем, что блок закреплен
            if not block.is_pinned:
                raise HTTPException(status_code=400, detail="Block must be pinned to move between levels")
            
            logger.info(f"📊 Before moving: block {block_id} level = {block.level}")
            
            # Обновляем уровень блока
            block.level = data.target_level
            block.save()
            block.refresh()
            
            logger.info(f"✅ After moving: block {block_id} level = {block.level}")
            
        return {"success": True, "message": f"Block {block_id} moved to level {data.target_level} successfully"}
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Block not found")
    except Exception as e:
        logger.error(f"Error moving block to level: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# S3 эндпоинты
@app.get("/api/s3/buckets/{bucket_name}/objects", response_model=S3ListResponse)
async def list_s3_objects(bucket_name: str, prefix: str = ""):
    """Получает список объектов в S3 bucket."""
    try:
        # s3_client = get_s3_client()
        # objects = await s3_client.list_objects(bucket_name, prefix)
        objects = []
        
        return S3ListResponse(
            objects=objects,
            count=len(objects)
        )
        
    except Exception as e:
        logger.error(f"Error listing S3 objects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/s3/buckets/{bucket_name}/objects/{object_key:path}", response_model=S3FileResponse)
async def get_s3_object(bucket_name: str, object_key: str):
    """Получает содержимое объекта из S3."""
    try:
        # s3_client = get_s3_client()
        
        # Проверяем существование объекта
        # if not await s3_client.object_exists(bucket_name, object_key):
        if False:
            raise HTTPException(status_code=404, detail="Object not found")
        
        # Скачиваем содержимое
        # content = await s3_client.download_text(bucket_name, object_key)
        content = ""
        
        if content is None:
            raise HTTPException(status_code=500, detail="Failed to download object")
        
        return S3FileResponse(
            content=content,
            content_type="text/markdown" if object_key.endswith('.md') else "text/plain"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting S3 object: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/s3/buckets/{bucket_name}/objects/{object_key:path}", response_model=S3UploadResponse)
async def upload_s3_object(bucket_name: str, object_key: str, content: Optional[str] = None):
    """Загружает объект в S3."""
    try:
        if not content:
            raise HTTPException(status_code=400, detail="Content is required")
        
        # s3_client = get_s3_client()
        
        # Определяем MIME тип
        content_type = "text/markdown" if object_key.endswith('.md') else "text/plain"
        
        # Загружаем объект
        # success = await s3_client.upload_bytes(
        success = True
        #     data=content.encode('utf-8'),
        #     bucket_name=bucket_name,
        #     object_key=object_key,
        #     content_type=content_type,
        #     metadata={
        #         "uploaded_by": "knowledge_map_api",
        #         "encoding": "utf-8"
        #     }
        # )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to upload object")
        
        return S3UploadResponse(
            success=True,
            object_key=object_key
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading S3 object: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/s3/buckets/{bucket_name}/objects/{object_key:path}")
async def delete_s3_object(bucket_name: str, object_key: str):
    """Удаляет объект из S3."""
    try:
        # s3_client = get_s3_client()
        
        # Проверяем существование объекта
        # if not await s3_client.object_exists(bucket_name, object_key):
        if False:
            raise HTTPException(status_code=404, detail="Object not found")
        
        # Удаляем объект
        # success = await s3_client.delete_object(bucket_name, object_key)
        success = True
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete object")
        
        return {"success": True, "message": f"Object {object_key} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting S3 object: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/s3/buckets/{bucket_name}/objects/{object_key:path}/url")
async def get_s3_object_url(bucket_name: str, object_key: str, expires_in: int = 3600):
    """Генерирует временный URL для доступа к объекту."""
    try:
        # s3_client = get_s3_client()
        
        # Проверяем существование объекта
        # if not await s3_client.object_exists(bucket_name, object_key):
        if False:
            raise HTTPException(status_code=404, detail="Object not found")
        
        # Генерируем URL
        # url = await s3_client.get_object_url(bucket_name, object_key, expires_in)
        url = "http://localhost:8000/placeholder"
        
        if not url:
            raise HTTPException(status_code=500, detail="Failed to generate URL")
        
        return {"url": url, "expires_in": expires_in}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating S3 object URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Специальный эндпоинт для загрузки markdown файлов для NLP компонента
@app.get("/api/nlp/markdown/{filename}", response_model=S3FileResponse)
async def get_nlp_markdown(filename: str):
    """Получает markdown файл из bucket 'markdown' для NLP компонента."""
    try:
        # s3_client = get_s3_client()
        
        # Проверяем существование файла
        # if not await s3_client.object_exists("markdown", filename):
        if False:
            raise HTTPException(status_code=404, detail=f"Markdown file '{filename}' not found")
        
        # Скачиваем содержимое
        # content = await s3_client.download_text("markdown", filename)
        content = ""
        
        if content is None:
            raise HTTPException(status_code=500, detail="Failed to download markdown file")
        
        return S3FileResponse(
            content=content,
            content_type="text/markdown"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting NLP markdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Подключаем GraphQL
graphql_app = GraphQLRouter(schema)
app.include_router(graphql_app, prefix="/graphql")



# ===== Auth endpoints =====
@app.post("/api/auth/register", response_model=AuthResponse)
async def register_user(request: UserRegisterRequest):
    """Регистрирует нового пользователя"""
    try:
        result = auth_client.register(
            login=request.login,
            password=request.password,
            nickname=request.nickname,
            captcha=request.captcha
        )
        
        if result["success"]:
            return AuthResponse(
                success=True,
                message=result["message"],
                user=result["user"],
                recovery_keys=result["recovery_keys"]
            )
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/login", response_model=AuthResponse)
async def login_user(request: UserLoginRequest):
    """Аутентифицирует пользователя"""
    try:
        result = auth_client.login(
            login=request.login,
            password=request.password,
            captcha=request.captcha,
            device_info=request.device_info or "",
            ip_address=request.ip_address or ""
        )
        
        if result["success"]:
            return AuthResponse(
                success=True,
                message=result["message"],
                token=result["token"],
                user=result["user"],
                requires_2fa=result["requires_2fa"]
            )
        else:
            raise HTTPException(status_code=401, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/logout")
async def logout_user(token: str, logout_all: bool = False):
    """Выходит из системы"""
    try:
        result = auth_client.logout(token, logout_all)
        
        if result["success"]:
            return {"success": True, "message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/verify", response_model=TokenVerifyResponse)
async def verify_user_token(token: str):
    """Проверяет токен пользователя"""
    try:
        result = auth_client.verify_token(token)
        
        if result["valid"]:
            return TokenVerifyResponse(
                valid=True,
                user=result["user"],
                message=result["message"]
            )
        else:
            raise HTTPException(status_code=401, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/recovery", response_model=AuthResponse)
async def recovery_request(request: UserRecoveryRequest):
    """Проверяет ключ восстановления"""
    try:
        result = auth_client.recovery_request(
            recovery_key=request.recovery_key,
            captcha=request.captcha
        )
        
        if result["success"]:
            return AuthResponse(
                success=True,
                message=result["message"],
                user={"uid": result["user_id"]}
            )
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/reset-password")
async def reset_password(request: UserPasswordResetRequest):
    """Сбрасывает пароль пользователя"""
    try:
        result = auth_client.reset_password(
            user_id=request.user_id,
            new_password=request.new_password
        )
        
        if result["success"]:
            return {"success": True, "message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/2fa/setup", response_model=AuthResponse)
async def setup_2fa(request: User2FASetupRequest):
    """Настраивает 2FA для пользователя"""
    try:
        result = auth_client.setup_2fa(request.user_id)
        
        if result["success"]:
            return AuthResponse(
                success=True,
                message=result["message"],
                user={"uid": request.user_id},
                recovery_keys=result["backup_codes"]
            )
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/2fa/verify")
async def verify_2fa(request: User2FAVerifyRequest):
    """Проверяет код 2FA"""
    try:
        result = auth_client.verify_2fa(
            user_id=request.user_id,
            code=request.code
        )
        
        if result["success"]:
            return {"success": True, "message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/auth/captcha")
async def get_captcha():
    """Генерирует капчу (заглушка)"""
    # В реальной реализации здесь будет генерация капчи
    return {
        "captcha_id": "test_captcha_123",
        "captcha_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    }
# ===== Auth endpoints END =====

# ===== PDF Document endpoints START =====

import mimetypes

class PDFUploadResponse(BaseModel):
    success: bool
    message: str
    document_id: Optional[str] = None
    md5_hash: Optional[str] = None
    already_exists: bool = False

class PDFDocumentResponse(BaseModel):
    uid: str
    original_filename: str
    md5_hash: str
    file_size: Optional[int]
    upload_date: datetime
    title: Optional[str]
    authors: Optional[List[str]]
    abstract: Optional[str]
    keywords: Optional[List[str]]
    processing_status: str
    is_processed: bool

class PDFAnnotationResponse(BaseModel):
    uid: str
    annotation_type: str
    content: str
    confidence: Optional[float]
    page_number: Optional[int]
    bbox: Optional[Dict[str, float]]
    metadata: Optional[Dict[str, Any]]

@app.post("/api/pdf/upload", response_model=PDFUploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    user_id: str = Form(...)
):
    """Загружает PDF файл в S3 и создает запись в Neo4j"""
    try:
        # Проверяем тип файла
        if not file.content_type or not file.content_type.startswith('application/pdf'):
            raise HTTPException(status_code=400, detail="Файл должен быть PDF")
        
        # Читаем содержимое файла
        file_content = await file.read()
        file_size = len(file_content)
        
        # Вычисляем MD5 хеш
        md5_hash = hashlib.md5(file_content).hexdigest()
        
        # Проверяем, существует ли уже такой файл
        try:
            existing_doc = PDFDocument.nodes.get(md5_hash=md5_hash)
            return PDFUploadResponse(
                success=True,
                message="Файл уже существует в системе",
                document_id=existing_doc.uid,
                md5_hash=md5_hash,
                already_exists=True
            )
        except DoesNotExist:
            pass  # Файл не существует, продолжаем загрузку
        
        # Создаем S3 ключ
        s3_key = f"pdfs/{md5_hash}.pdf"
        
        # Загружаем в S3
        # s3_client = get_s3_client()
        # success = await s3_client.upload_bytes(
        success = True
        #     data=file_content,
        #     bucket_name="knowledge-map-pdfs",
        #     object_key=s3_key,
        #     content_type="application/pdf",
        #     metadata={
        #         "original_filename": file.filename,
        #         "upload_date": datetime.utcnow().isoformat(),
        #         "user_id": user_id
        #     }
        # )
        
        if not success:
            raise HTTPException(status_code=500, detail="Ошибка загрузки файла в S3")
        
        # Создаем запись в Neo4j
        try:
            user = User.nodes.get(uid=user_id)
        except DoesNotExist:
            # Для тестового пользователя создаем его автоматически
            if user_id == "test_user":
                user = User(
                    uid="test_user",
                    login="test_user",
                    password="test_password",
                    nickname="Test User",
                    email="test@example.com",
                    full_name="Test User"
                ).save()
            else:
                raise HTTPException(status_code=404, detail="Пользователь не найден")
        
        pdf_doc = PDFDocument(
            original_filename=file.filename,
            md5_hash=md5_hash,
            s3_bucket="knowledge-map-pdfs",
            s3_key=s3_key,
            file_size=file_size
        ).save()
        
        # Связываем с пользователем
        user.uploaded.connect(pdf_doc)
        
        return PDFUploadResponse(
            success=True,
            message="Файл успешно загружен",
            document_id=pdf_doc.uid,
            md5_hash=md5_hash,
            already_exists=False
        )
        
    except Exception as e:
        logger.error(f"Ошибка загрузки PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/pdf/documents", response_model=List[PDFDocumentResponse])
async def get_pdf_documents(user_id: str):
    """Получает список PDF документов пользователя"""
    try:
        user = User.nodes.get(uid=user_id)
        documents = user.uploaded.all()
        
        return [
            PDFDocumentResponse(
                uid=doc.uid,
                original_filename=doc.original_filename,
                md5_hash=doc.md5_hash,
                file_size=doc.file_size,
                upload_date=doc.upload_date,
                title=doc.title,
                authors=doc.authors,
                abstract=doc.abstract,
                keywords=doc.keywords,
                processing_status=doc.processing_status,
                is_processed=doc.is_processed
            )
            for doc in documents
        ]
        
    except DoesNotExist:
        # Для тестового пользователя создаем его и возвращаем пустой список
        if user_id == "test_user":
            user = User(
                uid="test_user",
                login="test_user",
                password="test_password",
                nickname="Test User",
                email="test@example.com",
                full_name="Test User"
            ).save()
            return []
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    except Exception as e:
        logger.error(f"Ошибка получения документов: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/pdf/document/{document_id}", response_model=PDFDocumentResponse)
async def get_pdf_document(document_id: str):
    """Получает информацию о PDF документе"""
    try:
        doc = PDFDocument.nodes.get(uid=document_id)
        
        return PDFDocumentResponse(
            uid=doc.uid,
            original_filename=doc.original_filename,
            md5_hash=doc.md5_hash,
            file_size=doc.file_size,
            upload_date=doc.upload_date,
            title=doc.title,
            authors=doc.authors,
            abstract=doc.abstract,
            keywords=doc.keywords,
            processing_status=doc.processing_status,
            is_processed=doc.is_processed
        )
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Документ не найден")
    except Exception as e:
        logger.error(f"Ошибка получения документа: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/pdf/document/{document_id}/view")
async def view_pdf_document(document_id: str):
    """Просматривает PDF документ в браузере"""
    try:
        doc = PDFDocument.nodes.get(uid=document_id)
        
        # s3_client = get_s3_client()
        # file_content = await s3_client.download_bytes(
        file_content = b""
        #     bucket_name=doc.s3_bucket,
        #     object_key=doc.s3_key
        # )
        
        if not file_content:
            raise HTTPException(status_code=404, detail="Файл не найден в S3")
        
        from fastapi.responses import Response
        return Response(
            content=file_content,
            media_type="application/pdf",
            headers={"Content-Disposition": "inline"}
        )
    except PDFDocument.DoesNotExist:
        raise HTTPException(status_code=404, detail="Документ не найден")
    except Exception as e:
        logger.error(f"Ошибка просмотра PDF документа {document_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/pdf/document/{document_id}/download")
async def download_pdf_document(document_id: str):
    """Скачивает PDF документ из S3"""
    try:
        doc = PDFDocument.nodes.get(uid=document_id)
        
        # s3_client = get_s3_client()
        # file_content = await s3_client.download_bytes(
        file_content = b""
        #     bucket_name=doc.s3_bucket,
        #     object_key=doc.s3_key
        # )
        
        if not file_content:
            raise HTTPException(status_code=404, detail="Файл не найден в S3")
        
        from fastapi.responses import Response
        return Response(
            content=file_content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={doc.original_filename}"}
        )
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Документ не найден")
    except Exception as e:
        logger.error(f"Ошибка скачивания документа: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/pdf/document/{document_id}/annotations", response_model=List[PDFAnnotationResponse])
async def get_pdf_annotations(document_id: str):
    """Получает аннотации PDF документа"""
    try:
        doc = PDFDocument.nodes.get(uid=document_id)
        annotations = doc.annotations.all()
        
        return [
            PDFAnnotationResponse(
                uid=ann.uid,
                annotation_type=ann.annotation_type,
                content=ann.content,
                confidence=ann.confidence,
                page_number=ann.page_number,
                bbox=ann.get_bbox() if ann.bbox_x is not None else None,
                metadata=ann.metadata
            )
            for ann in annotations
        ]
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Документ не найден")
    except Exception as e:
        logger.error(f"Ошибка получения аннотаций: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/pdf/document/{document_id}/annotate")
async def start_pdf_annotation(document_id: str, user_id: str = Form(...)):
    """Запускает процесс автоматической аннотации PDF документа"""
    try:
        doc = PDFDocument.nodes.get(uid=document_id)
        
        if doc.processing_status == "processing":
            raise HTTPException(status_code=400, detail="Документ уже обрабатывается")
        
        # Обновляем статус
        doc.processing_status = "processing"
        doc.save()
        
        # Скачиваем PDF файл из S3
        # s3_client = get_s3_client()
        # pdf_content = await s3_client.download_bytes(
        pdf_content = b""
        #     bucket_name=doc.s3_bucket,
        #     object_key=doc.s3_key
        # )
        
        if not pdf_content:
            doc.processing_status = "error"
            doc.error_message = "Файл не найден в S3"
            doc.save()
            raise HTTPException(status_code=404, detail="Файл не найден в S3")
        
        # Вызываем AI сервис для аннотации
        try:
            import aiohttp
            
            # Создаем временный файл для отправки в AI сервис
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_file.write(pdf_content)
                temp_file_path = temp_file.name
            
            try:
                # Отправляем файл в AI сервис
                async with aiohttp.ClientSession() as session:
                    with open(temp_file_path, 'rb') as f:
                        data = aiohttp.FormData()
                        data.add_field('file', f, filename=doc.original_filename, content_type='application/pdf')
                        data.add_field('user_id', user_id)
                        
                        async with session.post('http://ai:8001/api/annotate/pdf', data=data) as response:
                            if response.status == 200:
                                result = await response.json()
                                
                                if 'annotations' in result:
                                    # Сохраняем аннотации в Neo4j
                                    for ann_data in result['annotations']:
                                        annotation = PDFAnnotation(
                                            annotation_type=ann_data['type'],
                                            content=ann_data['content'],
                                            confidence=ann_data.get('confidence'),
                                            page_number=ann_data.get('page_number'),
                                            metadata=ann_data.get('metadata', {})
                                        )
                                        
                                        # Устанавливаем bounding box если есть
                                        if ann_data.get('bbox'):
                                            bbox = ann_data['bbox']
                                            annotation.set_bbox(
                                                bbox.get('x', 0),
                                                bbox.get('y', 0),
                                                bbox.get('width', 0),
                                                bbox.get('height', 0)
                                            )
                                        
                                        annotation.save()
                                        
                                        # Связываем с документом
                                        doc.annotations.connect(annotation)
                                    
                                    # Обновляем статус документа
                                    doc.processing_status = "annotated"
                                    doc.is_processed = True
                                    doc.save()
                                    
                                    logger.info(f"Документ {document_id} успешно аннотирован. Найдено {result['annotations_count']} аннотаций")
                                    
                                else:
                                    doc.processing_status = "error"
                                    doc.error_message = result.get('message', 'Ошибка аннотации')
                                    doc.save()
                            else:
                                error_text = await response.text()
                                doc.processing_status = "error"
                                doc.error_message = f"Ошибка AI сервиса: {error_text}"
                                doc.save()
                                logger.error(f"Ошибка AI сервиса: {response.status} - {error_text}")
                                
            finally:
                # Удаляем временный файл
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as ai_error:
            logger.error(f"Ошибка вызова AI сервиса: {ai_error}")
            doc.processing_status = "error"
            doc.error_message = f"Ошибка AI сервиса: {str(ai_error)}"
            doc.save()
        
        return {"success": True, "message": "Процесс аннотации завершен"}
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Документ не найден")
    except Exception as e:
        logger.error(f"Ошибка запуска аннотации: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/pdf/document/{document_id}/reset")
async def reset_document_status(document_id: str):
    """Сбрасывает статус документа для повторной обработки"""
    try:
        doc = PDFDocument.nodes.get(uid=document_id)
        doc.processing_status = "uploaded"
        doc.error_message = None
        doc.is_processed = False
        doc.save()
        
        return {"success": True, "message": "Статус документа сброшен"}
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Документ не найден")
    except Exception as e:
        logger.error(f"Ошибка сброса статуса документа: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/pdf/document/{document_id}")
async def delete_document(document_id: str):
    """Удаляет документ из системы"""
    try:
        doc = PDFDocument.nodes.get(uid=document_id)
        
        # Удаляем файл из S3, если он есть
        if doc.s3_key:
            # s3_client = get_s3_client()
            # await s3_client.delete_object(doc.s3_bucket, doc.s3_key)
            pass
        
        # Удаляем аннотации
        for annotation in doc.annotations.all():
            annotation.delete()
        
        # Удаляем документ
        doc.delete()
        
        return {"success": True, "message": "Документ удален"}
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Документ не найден")
    except Exception as e:
        logger.error(f"Ошибка удаления документа: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== PDF Document endpoints END =====


logger.info("Application startup complete.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

@app.get("/api/static/pdf/{filename}")
async def get_static_pdf(filename: str):
    """Получение статического PDF файла"""
    try:
        # Путь к PDF файлу
        pdf_path = f"personal_folder/{filename}"
        
        import os
        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail="PDF файл не найден")
        
        # Возвращаем PDF файл
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=filename,
            headers={"Content-Disposition": "inline"}
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения PDF файла: {e}")
        raise HTTPException(status_code=500, detail=str(e))
