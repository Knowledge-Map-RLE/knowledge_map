#!/usr/bin/env python3
"""
Считает строки кода в проекте.
Исключает: бинарники, датасеты, скомпилированные артефакты, .gitignore-правила.
Поддерживает предварительное сканирование с подтверждением.

Запуск:
  python count_lines.py           — полный режим с подтверждением
  python count_lines.py --yes     — без подтверждения
  python count_lines.py --scan    — только сканирование, без подсчёта строк
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

BASE = Path(__file__).parent.parent.resolve()

# Директории, которые всегда пропускаются (независимо от .gitignore)
SKIP_DIRS: set = {
    ".git",
    ".dvc",
    ".venv",
    ".pytest_cache",
    ".cache",
    ".mypy_cache",
    "__pycache__",
    "node_modules",
    "target",        # Rust/cargo build artifacts
    "dist",
    "data",          # датасеты, не код
    "logs",
    "models",
    "personal_folder",
    "test_output",
    "test_input",
}

# Расширения файлов, которые не считаем (бинарники, данные, медиа)
SKIP_EXTENSIONS: set = {
    # бинарники / скомпилированное
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe", ".bin", ".whl",
    # архивы
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    # медиа
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".ico",
    ".mp3", ".mp4", ".wav", ".avi", ".mkv",
    # документы / офис
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ods", ".odt", ".ppt",
    # данные (большие)
    ".parquet", ".feather", ".arrow", ".h5", ".hdf5", ".pickle", ".pkl",
    ".npy", ".npz", ".pt", ".pth", ".ckpt", ".safetensors",
    # базы данных
    ".db", ".sqlite", ".sqlite3",
    # данные / разметка
    ".json",     # данные и outputs jupyter notebooks
    ".csv",
    ".tsv",
    ".ttl",      # RDF/ontology файлы
    ".html",     # сгенерированные визуализации
    ".ipynb",    # Jupyter notebooks (JSON с outputs)
    # прочее
    ".log", ".bkp",
    ".gml",
    ".graphml",
    ".md",       # документация, не код
}

# Конкретные имена файлов, которые пропускаем
SKIP_FILENAMES: set = {
    ".gitignore",
    "poetry.lock",
    "Cargo.lock",
    "package-lock.json",
    "yarn.lock",
}


# ---------------------------------------------------------------------------
# .gitignore парсинг
# ---------------------------------------------------------------------------

Pattern = Tuple[bool, bool, bool, Any, str]  # (negate, dir_only, has_slash, re_obj, raw)


def load_gitignore(base: Path) -> List[Pattern]:
    gitignore = base / ".gitignore"
    if not gitignore.exists():
        return []

    patterns_raw: List[str] = []
    with gitignore.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line or line.lstrip().startswith("#"):
                continue
            patterns_raw.append(line)

    compiled: List[Pattern] = []
    for pat in patterns_raw:
        negate = pat.startswith("!")
        p = pat[1:] if negate else pat
        if p.startswith("./"):
            p = p[2:]
        dir_only = p.endswith("/")
        if dir_only:
            p = p.rstrip("/")
        has_slash = "/" in p
        if not p:
            compiled.append((negate, dir_only, has_slash, None, pat))
            continue

        regex_parts: List[str] = []
        i = 0
        while i < len(p):
            if p[i: i + 2] == "**":
                regex_parts.append(".*")
                i += 2
            else:
                c = p[i]
                if c == "*":
                    regex_parts.append("[^/]*")
                elif c == "?":
                    regex_parts.append("[^/]")
                elif c in ".^$+{}[]()|\\":
                    regex_parts.append("\\" + c)
                else:
                    regex_parts.append(c)
                i += 1

        regex_body = "".join(regex_parts)
        if has_slash:
            anchored = p.startswith("/") or pat.startswith("/")
            regex = (r"^" + regex_body + r"$") if anchored else (r"(?:.*/)?") + regex_body + r"$"
        else:
            regex = r"^" + regex_body + r"$"

        try:
            cre = re.compile(regex)
        except re.error:
            cre = None
        compiled.append((negate, dir_only, has_slash, cre, pat))

    return compiled


def match_gitignore(
    rel_path_posix: str,
    is_dir: bool,
    patterns: Sequence[Pattern],
) -> bool:
    if not patterns:
        return False
    ignored = False
    basename = rel_path_posix.split("/")[-1]
    for negate, dir_only, has_slash, cre, _ in patterns:
        if cre is None:
            continue
        if dir_only and not is_dir:
            continue
        matched = cre.search(rel_path_posix) if has_slash else cre.search(basename)
        if matched:
            ignored = not negate
    return ignored


# ---------------------------------------------------------------------------
# Подсчёт строк
# ---------------------------------------------------------------------------

def count_lines_in_file(path: Path) -> int:
    try:
        cnt = 0
        with path.open("rb") as fh:
            for raw in fh:
                s = raw.strip()
                if s and s not in (b"{", b"}"):
                    cnt += 1
        return cnt
    except Exception as e:
        print(f"  ! Ошибка чтения {path}: {e}", file=sys.stderr)
        return 0


# ---------------------------------------------------------------------------
# Сканирование
# ---------------------------------------------------------------------------

def scan(base: Path, gitignore_patterns: List[Pattern]) -> List[Path]:
    """Возвращает список файлов, которые будут обработаны."""
    result: List[Path] = []

    for root, dirs, files in os.walk(base):
        root_path = Path(root)
        try:
            rel_root = root_path.relative_to(base).as_posix()
        except ValueError:
            rel_root = ""

        # Фильтруем директории на месте
        for d in list(dirs):
            if d in SKIP_DIRS:
                dirs.remove(d)
                continue
            child_rel = (f"{rel_root}/{d}") if rel_root else d
            if match_gitignore(child_rel, is_dir=True, patterns=gitignore_patterns):
                dirs.remove(d)

        for f in files:
            file_rel = (f"{rel_root}/{f}") if rel_root else f
            path = root_path / f

            if f in SKIP_FILENAMES:
                continue
            if path.suffix.lower() in SKIP_EXTENSIONS:
                continue
            if match_gitignore(file_rel, is_dir=False, patterns=gitignore_patterns):
                continue

            result.append(path)

    return result


def group_by_top_dir(files: List[Path], base: Path) -> Dict[str, int]:
    """Группирует файлы по верхнеуровневой директории."""
    groups: Dict[str, int] = {}
    for f in files:
        try:
            rel = f.relative_to(base)
            top = rel.parts[0] if len(rel.parts) > 1 else "(корень)"
        except ValueError:
            top = "(корень)"
        groups[top] = groups.get(top, 0) + 1
    return dict(sorted(groups.items(), key=lambda x: -x[1]))


# ---------------------------------------------------------------------------
# Основная логика
# ---------------------------------------------------------------------------

def main() -> None:
    args = set(sys.argv[1:])
    auto_yes = "--yes" in args or "-y" in args
    scan_only = "--scan" in args

    print(f"Проект: {BASE}")
    print("Сканирование файлов...\n")

    gitignore_patterns = load_gitignore(BASE)
    files = scan(BASE, gitignore_patterns)

    # Группировка для предпросмотра
    groups = group_by_top_dir(files, BASE)

    print(f"{'Директория':<35} {'Файлов':>8}")
    print("-" * 45)
    for top, count in groups.items():
        print(f"  {top:<33} {count:>8}")
    print("-" * 45)
    print(f"  {'ИТОГО':<33} {len(files):>8} файлов\n")

    if scan_only:
        return

    if not auto_yes:
        try:
            answer = input("Подсчитать строки в этих файлах? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nОтменено.")
            return
        if answer and answer not in ("y", "yes", "д", "да"):
            print("Отменено.")
            return

    print("\nПодсчёт строк...")
    total_lines = 0
    lines_by_group: Dict[str, int] = {}

    for path in files:
        try:
            rel = path.relative_to(BASE)
            top = rel.parts[0] if len(rel.parts) > 1 else "(корень)"
        except ValueError:
            top = "(корень)"

        lines = count_lines_in_file(path)
        total_lines += lines
        lines_by_group[top] = lines_by_group.get(top, 0) + lines

    # Итоговый отчёт
    print(f"\n{'Директория':<35} {'Файлов':>8} {'Строк':>12}")
    print("-" * 57)
    for top in sorted(lines_by_group, key=lambda x: -lines_by_group[x]):
        print(f"  {top:<33} {groups.get(top, 0):>8} {lines_by_group[top]:>12,}")
    print("-" * 57)
    print(f"  {'ИТОГО':<33} {len(files):>8} {total_lines:>12,}")
    print()


if __name__ == "__main__":
    main()
