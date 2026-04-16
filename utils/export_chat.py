"""
export_chat.py — экспорт чата Claude Code из JSONL в Markdown.

Использование:
    python export_chat.py                        # текущая сессия (последний JSONL)
    python export_chat.py <session_id>           # конкретная сессия по ID
    python export_chat.py <path/to/file.jsonl>   # конкретный файл

Сохраняет MD в: personal_folder\Истории чатов с ИИ\
"""
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ── Пути ──────────────────────────────────────────────────────────────────────
PROJECTS_DIR = Path(r'C:\Users\dimka\.claude\projects\d--Knowledge-Map')
OUTPUT_DIR = Path(r'd:\Knowledge_Map\personal_folder\Истории чатов с ИИ')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def find_jsonl(arg: str | None) -> Path:
    """Найти JSONL файл по аргументу или взять последний."""
    if arg is None:
        # Последний изменённый файл в папке проекта
        files = sorted(PROJECTS_DIR.glob('*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            raise FileNotFoundError(f'Нет JSONL файлов в {PROJECTS_DIR}')
        return files[0]
    p = Path(arg)
    if p.exists():
        return p
    # Попробуем как session_id
    candidate = PROJECTS_DIR / f'{arg}.jsonl'
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f'Файл не найден: {arg}')


def extract_text(content) -> str:
    """Извлечь текст из content (список блоков или строка)."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get('type', '')
        if btype == 'text':
            parts.append(block.get('text', ''))
        elif btype == 'tool_use':
            name = block.get('name', '')
            inp = block.get('input', {})
            # Показываем только имя инструмента и ключевые параметры
            key_params = []
            for k in ('file_path', 'pattern', 'command', 'description', 'prompt'):
                if k in inp:
                    val = str(inp[k])
                    if len(val) > 120:
                        val = val[:120] + '…'
                    key_params.append(f'{k}={val!r}')
            params_str = ', '.join(key_params) if key_params else ''
            parts.append(f'`[tool: {name}({params_str})]`')
        elif btype == 'tool_result':
            result_content = block.get('content', '')
            result_text = extract_text(result_content)
            if result_text.strip():
                # Обрезаем длинные результаты
                if len(result_text) > 800:
                    result_text = result_text[:800] + '\n…(обрезано)'
                parts.append(f'<details><summary>результат инструмента</summary>\n\n```\n{result_text.strip()}\n```\n</details>')
    return '\n'.join(parts)


def parse_jsonl(path: Path) -> tuple[str, list[dict]]:
    """Парсит JSONL, возвращает (title, messages)."""
    title = ''
    messages = []

    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            t = obj.get('type', '')

            if t == 'ai-title':
                title = obj.get('aiTitle', '')

            elif t == 'user':
                msg = obj.get('message', {})
                content = msg.get('content', '')
                text = extract_text(content).strip()
                if not text:
                    continue
                ts = obj.get('timestamp', '')
                messages.append({'role': 'user', 'text': text, 'ts': ts})

            elif t == 'assistant':
                msg = obj.get('message', {})
                content = msg.get('content', [])
                text = extract_text(content).strip()
                if not text:
                    continue
                ts = obj.get('timestamp', '')
                messages.append({'role': 'assistant', 'text': text, 'ts': ts})

    return title, messages


def format_ts(ts: str) -> str:
    """Форматирует ISO timestamp в читаемый вид."""
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return dt.astimezone().strftime('%Y-%m-%d %H:%M')
    except Exception:
        return ts


def build_md(title: str, messages: list[dict], session_id: str) -> str:
    lines = []
    lines.append(f'# {title or "Чат с Claude Code"}')
    lines.append(f'\n**Сессия:** `{session_id}`  ')
    if messages:
        lines.append(f'**Начало:** {format_ts(messages[0]["ts"])}  ')
        lines.append(f'**Конец:** {format_ts(messages[-1]["ts"])}  ')
        lines.append(f'**Сообщений:** {len(messages)}')
    lines.append('\n---\n')

    for msg in messages:
        role = msg['role']
        text = msg['text']
        ts = format_ts(msg['ts'])

        if role == 'user':
            lines.append(f'## 👤 Пользователь  <sub>{ts}</sub>\n')
            lines.append(text)
        else:
            lines.append(f'## 🤖 Claude  <sub>{ts}</sub>\n')
            lines.append(text)
        lines.append('\n---\n')

    return '\n'.join(lines)


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    jsonl_path = find_jsonl(arg)
    session_id = jsonl_path.stem

    print(f'Читаю: {jsonl_path}')
    title, messages = parse_jsonl(jsonl_path)
    print(f'Заголовок: {title or "(нет)"}')
    print(f'Сообщений: {len(messages)}')

    md = build_md(title, messages, session_id)

    # Имя файла: дата + заголовок
    date_str = datetime.now().strftime('%Y-%m-%d')
    safe_title = (title or 'chat').replace('/', '-').replace('\\', '-').replace(':', '-')
    safe_title = ''.join(c for c in safe_title if c.isprintable() and c not in '<>"|?*')[:60].strip()
    out_filename = f'{date_str} {safe_title}.md'
    out_path = OUTPUT_DIR / out_filename

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(md)

    print(f'Сохранено: {out_path}')
    print(f'Размер: {out_path.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
