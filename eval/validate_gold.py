"""Валидатор золотых эталонов разбора статей (eval/gold).

Проверяет целостность набора эталонов:
  1. manifest.json соответствует фактическим каталогам кейсов;
  2. у каждого кейса есть article.md, meta.json, structural_lines.json;
  3. meta.json содержит обязательные поля, slug совпадает с каталогом,
     schema_version поддерживается;
  4. каждый блок проходит pydantic-схему (UUID instanceId, blockType 1..59,
     непустой data, целочисленный order);
  5. instanceId уникальны; UUID-ссылки не «висячие» (dangling_refs == 0);
  6. checksums.sha256 совпадает с фактическим содержимым файлов.

Режим --update-checksums пересобирает checksums.sha256 после добавления или
изменения кейса; после этого изменения проходят только через code review
(CODEOWNERS на /eval/gold/).

Запуск из окружения api:
    poetry run python ../eval/validate_gold.py
    poetry run python ../eval/validate_gold.py --update-checksums
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

API_DIR = Path(__file__).resolve().parent.parent / "api"
sys.path.insert(0, str(API_DIR))

from src.schemas.gold import (  # noqa: E402
    CASE_FILES,
    CHECKSUMS_NAME,
    MANIFEST_NAME,
    REQUIRED_META_FIELDS,
    SUPPORTED_SCHEMA_VERSIONS,
)
from services.gold_case_service import (  # noqa: E402
    compute_checksum_lines,
    iter_gold_files,
    sha256_of,
    validate_gold_blocks,
)

DEFAULT_GOLD_DIR = Path(__file__).resolve().parent / "gold"


class Validator:
    def __init__(self, gold_dir: Path) -> None:
        self.gold_dir = gold_dir
        self.errors: List[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    # ── Обнаружение кейсов ────────────────────────────────────────────────

    def discover_case_dirs(self) -> List[Path]:
        if not self.gold_dir.is_dir():
            self.error(f"Каталог эталонов не найден: {self.gold_dir}")
            return []
        cases = sorted(
            d for d in self.gold_dir.iterdir()
            if d.is_dir() and (d / "structural_lines.json").exists()
        )
        if not cases:
            self.error(f"В {self.gold_dir} нет ни одного кейса со structural_lines.json")
        return cases

    # ── Манифест ──────────────────────────────────────────────────────────

    def validate_manifest(self, case_dirs: List[Path]) -> List[str]:
        manifest_path = self.gold_dir / MANIFEST_NAME
        if not manifest_path.exists():
            self.error(f"Отсутствует {MANIFEST_NAME}")
            return []
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.error(f"{MANIFEST_NAME} не читается: {exc}")
            return []

        version = manifest.get("version")
        if version != 1:
            self.error(f"{MANIFEST_NAME}: неподдерживаемая версия {version!r}")

        declared = [c.get("slug") for c in manifest.get("cases", [])]
        actual = [d.name for d in case_dirs]
        for slug in declared:
            if slug not in actual:
                self.error(f"{MANIFEST_NAME}: кейс '{slug}' объявлен, но каталога нет")
        for name in actual:
            if name not in declared:
                self.error(f"{MANIFEST_NAME}: каталог '{name}' не объявлен в cases")
        if len(set(declared)) != len(declared):
            self.error(f"{MANIFEST_NAME}: дубликаты slug в cases")
        return [s for s in declared if s in actual]

    # ── Отдельный кейс ────────────────────────────────────────────────────

    def validate_case(self, case_dir: Path) -> None:
        slug = case_dir.name
        for name in CASE_FILES:
            if not (case_dir / name).exists():
                self.error(f"[{slug}] отсутствует файл {name}")

        meta = self._load_meta(case_dir, slug)
        blocks = self._load_blocks(case_dir, slug)
        if blocks is None or meta is None:
            return

        self._validate_meta(meta, slug)
        self._validate_blocks(blocks, slug)

    def _load_json(self, path: Path, label: str) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            self.error(f"{label} не читается: {exc}")
            return None

    def _load_meta(self, case_dir: Path, slug: str) -> Dict[str, Any]:
        raw = self._load_json(case_dir / "meta.json", f"[{slug}] meta.json")
        if not isinstance(raw, dict):
            self.error(f"[{slug}] meta.json должен быть объектом")
            return {}
        return raw

    def _load_blocks(self, case_dir: Path, slug: str) -> List[Dict[str, Any]]:
        payload = self._load_json(
            case_dir / "structural_lines.json", f"[{slug}] structural_lines.json"
        )
        if not isinstance(payload, dict):
            self.error(f"[{slug}] structural_lines.json должен быть объектом с полем blocks")
            return []
        version = payload.get("schema_version")
        if version not in SUPPORTED_SCHEMA_VERSIONS:
            self.error(f"[{slug}] неподдерживаемая schema_version: {version!r}")
        blocks = payload.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            self.error(f"[{slug}] blocks должен быть непустым списком")
            return []
        return blocks

    def _validate_meta(self, meta: Dict[str, Any], slug: str) -> None:
        for field in REQUIRED_META_FIELDS:
            if meta.get(field) in (None, ""):
                self.error(f"[{slug}] meta.json: отсутствует обязательное поле '{field}'")
        if meta.get("slug") != slug:
            self.error(f"[{slug}] meta.json: slug='{meta.get('slug')}' не совпадает с именем каталога")
        version = meta.get("schema_version")
        if version not in SUPPORTED_SCHEMA_VERSIONS:
            self.error(f"[{slug}] meta.json: неподдерживаемая schema_version={version!r}")

    def _validate_blocks(self, blocks: List[Dict[str, Any]], slug: str) -> None:
        for message in validate_gold_blocks(blocks):
            self.error(f"[{slug}] {message}")

    # ── Контрольные суммы ─────────────────────────────────────────────────

    def _iter_files(self) -> List[Path]:
        return iter_gold_files(self.gold_dir)

    def update_checksums(self) -> None:
        lines = compute_checksum_lines(self.gold_dir)
        (self.gold_dir / CHECKSUMS_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def validate_checksums(self) -> None:
        checksums_path = self.gold_dir / CHECKSUMS_NAME
        if not checksums_path.exists():
            self.error(f"Отсутствует {CHECKSUMS_NAME} (запустите с --update-checksums)")
            return

        expected: Dict[str, str] = {}
        for line in checksums_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2 or len(parts[0]) != 64:
                self.error(f"{CHECKSUMS_NAME}: некорректная строка '{line[:80]}'")
                continue
            expected[parts[1]] = parts[0]

        actual = {
            p.relative_to(self.gold_dir).as_posix(): sha256_of(p)
            for p in self._iter_files()
        }
        for rel, digest in expected.items():
            if rel not in actual:
                self.error(f"{CHECKSUMS_NAME}: файл '{rel}' отсутствует в наборе")
            elif actual[rel] != digest:
                self.error(f"{CHECKSUMS_NAME}: изменён файл '{rel}' (ожидался другой хеш)")
        for rel in actual:
            if rel not in expected:
                self.error(f"{CHECKSUMS_NAME}: файл '{rel}' не покрыт контрольными суммами")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gold-dir", type=Path, default=DEFAULT_GOLD_DIR)
    parser.add_argument(
        "--update-checksums",
        action="store_true",
        help="Пересобрать checksums.sha256 (после добавления/правки эталона)",
    )
    args = parser.parse_args()

    validator = Validator(args.gold_dir)
    if args.update_checksums:
        validator.update_checksums()
        print(f"checksums обновлены: {args.gold_dir / CHECKSUMS_NAME}")

    case_dirs = validator.discover_case_dirs()
    slugs = validator.validate_manifest(case_dirs)
    for case_dir in case_dirs:
        validator.validate_case(case_dir)
    validator.validate_checksums()

    if validator.errors:
        print(f"ПРОВАЛЕНО: {len(validator.errors)} ошибок(и):")
        for message in validator.errors:
            print(f"  - {message}")
        sys.exit(1)

    print(f"ОК: кейсов {len(slugs)}, все проверки пройдены ({args.gold_dir})")


if __name__ == "__main__":
    main()
