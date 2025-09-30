#!/usr/bin/env python3
"""
Считает все строки во всех файлах текущей папки (и вложенных),
исключая пути, соответствующие правилам из .gitignore в этой же папке.

Без сторонних библиотек.
"""
from pathlib import Path
import os
import re
import sys
from typing import List, Tuple, Optional, Pattern, Any, Sequence

BASE = Path(__file__).parent.resolve()


def load_gitignore(base: Path) -> List[Tuple[bool, bool, bool, Any, str]]:
    """Загружает правила из .gitignore и компилирует в регулярные выражения.
    Возвращает список паттернов в порядке файла: [(negate, dir_only, has_slash, re_obj, raw_pattern), ...]
    """
    gitignore = base / ".gitignore"
    patterns_raw: List[str] = []
    compiled: List[Tuple[bool, bool, bool, Any, str]] = []
    if not gitignore.exists():
        return compiled

    with gitignore.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line:
                continue
            # пропускаем комментарии (начинающиеся с '#'), учитываем возможные пробелы в начале
            if line.lstrip().startswith("#"):
                continue
            patterns_raw.append(line)
    for pat in patterns_raw:
        negate = pat.startswith("!")
        p = pat[1:] if negate else pat

        # нормализуем: уберём ведущую ./ если есть (часто встречается)
        if p.startswith("./"):
            p = p[2:]

        dir_only = p.endswith("/")
        if dir_only:
            p = p.rstrip("/")

        # признак: содержит ли паттерн слэш (тогда это path-паттерн), иначе — basename-паттерн
        has_slash = "/" in p

        # если пустой после обработки — пропускаем
        if p == "":
            # например "!" или "/"
            compiled.append((negate, dir_only, has_slash, None, pat))
            continue

        # конвертация git-паттерна в регулярное выражение (приближённо)
        # поведение:
        #  - '**' -> '.*'
        #  - '*' -> '[^/]*'
        #  - '?' -> '[^/]'
        #  - остальное — экранируется
        regex_parts = []
        i = 0
        L = len(p)
        while i < L:
            if p[i:i+2] == "**":
                regex_parts.append(".*")
                i += 2
            else:
                c = p[i]
                if c == "*":
                    regex_parts.append("[^/]*")
                elif c == "?":
                    regex_parts.append("[^/]")
                else:
                    if c in ".^$+{}[]()|\\":  # экранируем regex-метасимволы
                        regex_parts.append("\\" + c)
                    else:
                        regex_parts.append(c)
                i += 1
        regex_body = "".join(regex_parts)

        # Формируем финальный паттерн:
        #  - Для паттернов с '/' (path-pattern): будем искать совпадение в относительном пути (posix)
        #    Если паттерн начинается с '/', будем привязывать к началу пути (repo-root).
        #    В общем случае ставим "(.*/)?<body>$" чтобы покрыть случаи в глубине.
        #  - Для паттернов без '/' (basename-pattern): будем сравнивать с basename (полное совпадение).
        if has_slash:
            # если паттерн явно начинается с '/', то мы привязываем к началу
            anchored_to_root = p.startswith("/") or pat.startswith("/")
            if anchored_to_root:
                regex = r"^" + regex_body + r"$"
            else:
                # разрешаем совпадение на любом уровне: "(.*/)?body$"
                regex = r"(?:.*/)?"+ regex_body + r"$"
        else:
            # паттерн без слэшей — сравнение с basename, полное совпадение
            regex = r"^" + regex_body + r"$"

        try:
            cre: Optional[Pattern[str]] = re.compile(regex)
        except re.error:
            cre = None
        compiled.append((negate, dir_only, has_slash, cre, pat))
    return compiled


def match_gitignore(
    rel_path_posix: str,
    is_dir: bool,
    patterns: Sequence[Tuple[bool, bool, bool, Any, str]],
) -> bool:
    """Возвращает True если путь должен быть проигнорирован (по правилам patterns).
    rel_path_posix — путь относительно BASE в posix-формате (без ведущего ./).
    patterns — список, полученный из load_gitignore.
    Алгоритм: применяются паттерны по порядку; последний подходящий паттерн решает.
    """
    if not patterns:
        return False

    ignored = False
    basename = rel_path_posix.split("/")[-1]

    for negate, dir_only, has_slash, cre, raw in patterns:
        # если паттерн пустой или некорректен — пропускаем
        if cre is None:
            continue
        if dir_only and not is_dir:
            continue

        matched = False
        if has_slash:
            # тестируем на весь относительный путь
            if cre.search(rel_path_posix):
                matched = True
        else:
            # тестируем только basename
            if cre.search(basename):
                matched = True

        if matched:
            if negate:
                ignored = False
            else:
                ignored = True
    return ignored


def count_lines_in_file(path: Path) -> int:
    """Безопасно считает строки в файле, открывая в бинарном режиме (чтобы не ломаться на кодировках)."""
    try:
        cnt = 0
        with path.open("rb") as fh:
            for raw in fh:
                # Пропускаем строки, где содержится только одна фигурная скобка без кода
                # Разрешаем только пробелы/табуляции/переводы строк вокруг
                s = raw.strip()
                if s in (b"{", b"}"):
                    continue
                cnt += 1
        return cnt
    except Exception as e:
        # Не прерываем весь процесс из-за одного файла; логируем и считаем 0
        print(f"⚠ Ошибка чтения {path}: {e}", file=sys.stderr)
        return 0


def main():
    base = BASE
    patterns: List[Tuple[bool, bool, bool, Any, str]] = load_gitignore(base)

    total_files = 0
    total_lines = 0
    skipped_by_gitignore = 0

    # на всякий случай пропускаем саму папку .git (обычно не хотим её сканировать)
    git_dirname = ".git"
    # доп. исключение: не считать содержимое каталога logs
    skip_dirname_logs = "logs"

    for root, dirs, files in os.walk(base):
        root_path = Path(root)
        # вычислим относительный путь (posix)
        try:
            rel_root = root_path.relative_to(base).as_posix()
        except Exception:
            rel_root = ""

        # изменяем dirs на месте, чтобы os.walk не входил в игнорируемые каталоги
        # проходим копию списка, чтобы можно было удалять элементы
        for d in list(dirs):
            if d == git_dirname or d == skip_dirname_logs:
                # всегда пропускаем .git и logs
                dirs.remove(d)
                continue
            child_rel = (Path(rel_root) / d).as_posix() if rel_root != "" else d
            if match_gitignore(child_rel, is_dir=True, patterns=patterns):
                dirs.remove(d)

        for f in files:
            file_rel = (Path(rel_root) / f).as_posix() if rel_root != "" else f
            # не считаем сам .gitignore файл (он может быть включён; решение — не считать конфигурационный файл)
            if file_rel == ".gitignore":
                continue
            # доп. исключения по имени/расширению
            if f == "poetry.lock" or f.endswith(".log") or f.endswith(".txt"):
                continue
            if match_gitignore(file_rel, is_dir=False, patterns=patterns):
                skipped_by_gitignore += 1
                continue
            file_path = root_path / f
            # считаем строки (файлы открываем только для чтения в бинарном режиме)
            lines = count_lines_in_file(file_path)
            total_lines += lines
            total_files += 1

    print(f"Папка: {base}")
    print(f"Файлов обработано: {total_files}")
    print(f"Файлов пропущено по .gitignore: {skipped_by_gitignore}")
    print(f"Всего строк: {total_lines}")


if __name__ == "__main__":
    main()
