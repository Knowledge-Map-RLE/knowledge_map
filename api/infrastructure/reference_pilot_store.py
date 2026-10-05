"""Неизменяемые артефакты эксперимента и проверяемый кэш LLM-этапов."""
from __future__ import annotations

import copy
import ast
import json
import logging
import os
import re
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from domain.article_maps import ArticleMapError, digest, fingerprint, parse_json_response, prepare_source, require
from domain.knowledge_map import apply_dependency_review, knowledge_text_keys, parse_knowledge_map, validate_knowledge_map
from domain.knowledge_map_schema import dependency_review_json_schema

log = logging.getLogger(__name__)


class PilotStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        require(self.root in path.parents, "Artifact path escapes experiment directory")
        return path

    def read(self, relative: str):
        path = self.path(relative)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def write(self, relative: str, value, *, immutable: bool = True) -> None:
        self.write_bytes(relative, json.dumps(value, ensure_ascii=False, sort_keys=True,
                                             indent=2, allow_nan=False).encode("utf-8"), immutable=immutable)

    def write_bytes(self, relative: str, data: bytes, *, immutable: bool = True) -> None:
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        if immutable:
            temporary = path.with_name(path.name + "." + str(uuid4()) + ".tmp")
            try:
                with temporary.open("xb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    # Публикуем готовый файл атомарно и никогда не заменяем существующее имя.
                    os.link(temporary, path)
                except FileExistsError:
                    require(path.read_bytes() == data, "Immutable experiment artifact differs")
            finally:
                temporary.unlink(missing_ok=True)
        else:
            temporary = path.with_name(path.name + "." + str(uuid4()) + ".tmp")
            try:
                with temporary.open("xb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)

    def record_attempt(self, call: dict, binding: dict) -> None:
        """Полный журнал затрат; запись вызова неизменяема, индекс обновляется под writer.lock."""
        self.write(f"attempts/{call['attempt_id']}.json", call | {"binding": binding})
        ledger = self.read("cost_ledger.json") or {"attempts": []}
        ledger["attempts"].append(call)
        self.write("cost_ledger.json", ledger, immutable=False)

    @contextmanager
    def lock(self):
        path = self.path("writer.lock")
        try:
            handle = path.open("x", encoding="utf-8")
        except FileExistsError as exc:
            raise ValueError("Experiment writer is locked; inspect writer.lock before explicit recovery") from exc
        try:
            with handle:
                handle.write(json.dumps({"pid": os.getpid()}))
            yield
        finally:
            path.unlink(missing_ok=True)


def validator_fingerprint(stage: str = "complete") -> str:
    api = Path(__file__).resolve().parents[1]
    if stage == "translation_ru":
        syntax = ast.parse((api / "application/text_to_map.py").read_text(encoding="utf-8"))
        translator = next(node for node in syntax.body if getattr(node, "name", None) == "TranslateArticleMap")
        parser = ast.parse((api / "domain/article_maps.py").read_text(encoding="utf-8"))
        return fingerprint({"translator": ast.dump(translator, include_attributes=False),
                            "parser": ast.dump(parser, include_attributes=False)})
    excluded = {"apply_dependency_review", "dependency_review_json_schema", "knowledge_text_keys",
                "dependency_review_view"} if stage == "extraction" else set()
    modules = {}
    for name in ("article_maps.py", "knowledge_map.py", "knowledge_map_schema.py"):
        syntax = ast.parse((api / "domain" / name).read_text(encoding="utf-8"))
        # Изменение исключительно аудита связей не инвалидирует извлечение знаний.
        syntax.body = [node for node in syntax.body if getattr(node, "name", None) not in excluded]
        modules[name] = digest(ast.dump(syntax, include_attributes=False))
    return fingerprint(modules)


def gateway_settings(gateway) -> dict:
    result = {key: getattr(gateway, key) for key in (
        "model", "provider", "context_length", "max_tokens", "timeout", "reasoning_effort", "url", "strict_schema")}
    if getattr(gateway, "json_object", False):
        result["response_format"] = "json_object"
    return result


class CachedStageModel:
    """Переиспользует только полный, проверенный ответ того же этапа и конфигурации."""

    def __init__(self, gateway, store: PilotStore, source_text: str, *, stage: str):
        require(stage in {"extraction", "dependencies", "translation_ru"}, "Unknown map stage")
        self.gateway, self.store, self.source_text, self.stage = gateway, store, source_text, stage
        self.last_call = {}
        self.calls = []

    def _validate(self, raw, request):
        if self.stage == "translation_ru":
            translated = parse_json_response(raw)
            require(isinstance(translated, dict) and set(translated) == set(request),
                    "Translation node ids changed")
            require(all(isinstance(text, str) and text.strip() for text in translated.values()),
                    "Empty translated label")
            return
        source = prepare_source(request["article_id"], self.source_text)
        if self.stage == "extraction":
            graph = parse_knowledge_map(raw, source)
            require(not graph["edges"] and all(not n["semantic"]["inputs"] for n in graph["nodes"]),
                    "Extraction checkpoint contains dependencies")
        else:
            graph = validate_knowledge_map(request["knowledge_map"], source)
            scope = request.get("dependency_target_keys")
            if scope is not None:
                completed = request["completed_target_keys"]
                known = set(knowledge_text_keys(graph["nodes"]).values())
                require(isinstance(completed, list)
                        and all(isinstance(key, str) and key in known for key in completed)
                        and len(completed) == len(set(completed)), "Invalid completed dependency scope")
                require(not set(completed) & set(scope), "Dependency batch repeats a completed target")
                accepted = request["accepted_dependencies"]
                require(isinstance(accepted, list) and all(isinstance(item, dict)
                        and item.get("target") in completed for item in accepted),
                        "Accepted dependency targets differ from completed scope")
                graph = apply_dependency_review(json.dumps({"dependencies": accepted}), graph, source)
            apply_dependency_review(raw, graph, source, target_keys=scope)

    def _binding(self, system: str, user: str) -> tuple[dict, dict]:
        request = json.loads(user)
        schema = (self.gateway.output_schema if self.stage in {"extraction", "translation_ru"}
                  else dependency_review_json_schema(request["knowledge_map"]["nodes"],
                                                     request.get("dependency_target_keys"),
                                                     request.get("accepted_dependencies")))
        return {"version": 1, "stage": self.stage, "source_sha256": digest(self.source_text),
                "prompt_sha256": digest(system), "request_sha256": digest(user),
                "settings": gateway_settings(self.gateway), "schema_sha256": fingerprint(schema),
                "validator_sha256": validator_fingerprint(self.stage)}, schema

    def revalidate_attempt(self, attempt_id: str) -> dict:
        """Явное повторное принятие исходного ответа только после изменения валидатора."""
        require(str(UUID(attempt_id)) == attempt_id, "Invalid attempt id")
        attempt = self.store.read(f"attempts/{attempt_id}.json")
        require(attempt is not None and attempt["stage"] == self.stage, "Stage attempt not found")
        original = self.store.read(f"requests/{self.stage}/{attempt['cache_key']}.json")
        require(original is not None, "Exact original request is missing")
        binding, schema = self._binding(original["system"], original["user"])
        require({k: v for k, v in binding.items() if k != "validator_sha256"} ==
                {k: v for k, v in original["binding"].items() if k != "validator_sha256"},
                "Revalidation requires unchanged source, prompt, exact request, schema and model settings")
        candidates = [path for path in self.store.path(
            f"responses/{self.stage}/{attempt['cache_key']}/{attempt_id}").glob("*.txt")
                      if re.fullmatch(r"[a-f0-9]{64}\.txt", path.name)]
        require(len(candidates) == 1, "Complete original response is missing or ambiguous")
        raw = candidates[0].read_bytes().decode("utf-8")
        require(candidates[0].stem == digest(raw), "Original response hash differs")
        metadata = self.store.read(str(candidates[0].relative_to(self.store.root)) + ".metadata.json")
        require(metadata is not None and metadata["binding"] == original["binding"], "Response binding differs")
        self._validate(raw, json.loads(original["user"]))
        key = fingerprint(binding)
        model_call = metadata["model_call"] | {"checkpoint_revalidated": True,
                       "original_validator_sha256": original["binding"]["validator_sha256"],
                       "checkpoint_response_sha256": digest(raw)}
        self.store.write(f"requests/{self.stage}/{key}.json", {
            "binding": binding, "system": original["system"], "user": original["user"], "output_schema": schema})
        self.store.write(f"stage_cache/{self.stage}/{key}.json", {"binding": binding, "raw": raw,
                         "response_sha256": digest(raw), "model_call": model_call})
        receipt = {"attempt_id": attempt_id, "original_cache_key": attempt["cache_key"],
                   "new_cache_key": key, "response_sha256": digest(raw), "validation": "passed", "llm_calls": 0}
        self.store.write(f"revalidations/{attempt_id}/{key}.json", receipt)
        return receipt

    async def __call__(self, system: str, user: str) -> str:
        request = json.loads(user)
        binding, schema = self._binding(system, user)
        key = fingerprint(binding)
        relative = f"stage_cache/{self.stage}/{key}.json"
        # Точный запрос и промпт остаются воспроизводимыми после правки файлов проекта.
        self.store.write(f"requests/{self.stage}/{key}.json", {
            "binding": binding, "system": system, "user": user, "output_schema": schema})
        cached = self.store.read(relative)
        reused = cached is not None
        if reused:
            require(cached["binding"] == binding, "Stage checkpoint binding differs")
            raw = cached["raw"]
            require(digest(raw) == cached["response_sha256"], "Stage checkpoint response changed")
            self._validate(raw, request)
            self.last_call = copy.deepcopy(cached["model_call"]) | {
                "checkpoint_replayed": True, "checkpoint_response_sha256": digest(raw)}
        else:
            attempt_id = str(uuid4())
            error, refusal_reason = None, None
            try:
                raw = await self.gateway(system, user)
                raw_key = f"responses/{self.stage}/{key}/{attempt_id}/{digest(raw)}.txt"
                self.store.write_bytes(raw_key, raw.encode("utf-8"))
                self.last_call = dict(self.gateway.last_call)
                self.store.write(raw_key + ".metadata.json", {"binding": binding,
                                                            "model_call": self.last_call})
                self._validate(raw, request)
                self.store.write(relative, {"binding": binding, "raw": raw,
                                           "response_sha256": digest(raw), "model_call": self.last_call})
            except BaseException as exc:
                error = type(exc).__name__
                refusal_reason = str(exc)[:300] if isinstance(exc, ArticleMapError) else error
                partial = getattr(self.gateway, "last_response", "")
                if partial:
                    partial_key = f"responses/{self.stage}/{key}/{attempt_id}/transport_response.txt"
                    self.store.write_bytes(partial_key, partial.encode("utf-8"))
                    self.store.write(partial_key + ".metadata.json", {
                        "binding": binding, "model_call": dict(self.gateway.last_call)})
                raise
            finally:
                self.last_call = dict(self.gateway.last_call)
                call = {"attempt_id": attempt_id, "stage": self.stage, "cache_key": key, "reused": False,
                                   "usage": self.last_call.get("usage", {}),
                                   "original_usage": self.last_call.get("usage", {}),
                                   "model": self.last_call.get("resolved_model") or self.gateway.model,
                                   "model_call": copy.deepcopy(self.last_call),
                                   "reason": "no_compatible_checkpoint", "validated": error is None,
                                   "error": error, "refusal_reason": refusal_reason}
                self.calls.append(call)
                self.store.record_attempt(call, binding)
        if reused:
            self.calls.append({"stage": self.stage, "cache_key": key, "reused": True, "usage": {},
                               "original_usage": self.last_call.get("usage", {}),
                               "model": self.last_call.get("resolved_model") or self.last_call.get("model"),
                               "reason": ("revalidated_response_after_validator_change"
                                          if self.last_call.get("checkpoint_revalidated") else "verified_checkpoint"),
                               "validated": True})
        else:
            self.calls[-1]["validated"] = True
        log.info("reference_pilot stage=%s cache_key=%s reused=%s model=%s",
                 self.stage, key, reused, self.calls[-1]["model"])
        return raw
