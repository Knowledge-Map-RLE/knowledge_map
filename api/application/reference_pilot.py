"""Накопительный сценарий: карты источников → прогноз → изолированная оценка."""
from __future__ import annotations

import json
import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from application.ports.reference_pilot import ExperimentStore, PilotMapBuilder, ReferenceSourceProvider
from domain.article_maps import fingerprint, require
from domain.reference_prediction import (
    VERSION, canonicalize, evaluate, fit_aliases, learn_rules, merge_corpora, predict, source_priority,
)

log = logging.getLogger(__name__)


def cost_summary(calls: list[dict]) -> dict:
    totals = {}
    for call in calls:
        stage = call["stage"]
        counts = totals.setdefault(stage, {"new_calls": 0, "reused": 0, "input_tokens": 0,
                                           "output_tokens": 0, "calls_without_usage": 0})
        if call["reused"]:
            counts["reused"] += 1
            continue
        counts["new_calls"] += 1
        usage = call.get("usage", {})
        input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
        output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
        if input_tokens is None or output_tokens is None:
            counts["calls_without_usage"] += 1
        counts["input_tokens"] += input_tokens or 0
        counts["output_tokens"] += output_tokens or 0
    return totals


def map_version(result: dict) -> dict:
    binding = result.get("experiment_binding", {})
    return {"schema_version": result["graph"]["schema_version"],
            "builder_version": result.get("builder_version"), "prompt": result.get("prompt"),
            "dependency_prompt": result.get("dependency_prompt"),
            "validator": binding.get("validator"), "settings": binding.get("settings"),
            "dependency_settings": binding.get("dependency_settings"),
            "scenario": binding.get("scenario")}


def markdown_report(report: dict) -> str:
    lines = ["# Пилот предсказания PMC10000452", "",
             f"Прогон: `{report['run_id']}`. Источников: {report['source_count']}.", "",
             f"Лимит одновременно строящихся карт: {report['execution']['map_concurrency']}.", "",
             "Маршрут: полный текст → карта знаний (`text_reified`).",
             "Результат автоматический; научная точность требует последующего разбора.", "",
             "## Корпус", "", "| Ссылка | Идентификатор | Название |", "| --- | --- | --- |"]
    for source in report["sources"]:
        title = source["title"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {source['reference_number']} | {source['source_id']} | {title} |")
    labels = {"known_union": "Объединение известных знаний", "semantic": "Прогноз без связей",
              "graph": "Прогноз с dependency-связями"}
    lines += ["", "## Сравнение режимов", "",
              "| Режим | Утверждений / прогнозов | Совпадений | Контекст не совпал | Явных противоречий |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for name, result in report["evaluation"].items():
        statuses = result["status_counts"]
        lines.append(f"| {labels[name]} | {result['predictions']} | {result['matched']} | "
                     f"{statuses['context_or_kind_mismatch']} | {statuses['explicit_contradiction']} |")
    lines += ["", "Совпадение измерено с автоматической формализацией цели, а не с экспертным эталоном.",
              "Отсутствие утверждения в цели не считается опровержением. Совпадения объединения известных знаний "
              "считаются повторением; совпадения двух предикторов — новыми гипотезами относительно корпуса.",
              "PMC10000452 уже использовалась при разработке правил: этот пилот не является независимым испытанием.",
              "", "## Прогнозы и основания", ""]
    for mode in ("semantic", "graph"):
        lines += [f"### {labels[mode]}", ""]
        if not report["predictions"][mode]:
            lines.append("Новых гипотез нет. Пустой прогноз допустим при недостаточной поддержке шаблонов.")
        for index, prediction in enumerate(report["predictions"][mode], 1):
            atom = prediction["atom"]
            roles = "; ".join(f"{role}={term}" for role, term in atom["roles"])
            lines += [f"{index}. `{atom['predicate']}` ({roles}), отрицание: {atom['negated']}.",
                      f"   Шаблон `{prediction['rule_id']}`; поддержка: {prediction['support']} различных источников.",
                      f"   Ограничения: `{atom['scope']}`."]
            for premise in prediction["premises"]:
                lines.append(f"   - {premise['source_id']} / {premise['node_id']}: {premise['display_text']}")
        lines.append("")
    lines += ["## LLM и повторное использование", "",
              "| Этап | Модель | Переиспользован | Input tokens | Output tokens |", "| --- | --- | --- | ---: | ---: |"]
    for call in report["model_calls"]:
        usage = call.get("usage", {})
        lines.append(f"| {call['stage']} | {call.get('model')} | {'да' if call['reused'] else 'нет'} | "
                     f"{usage.get('prompt_tokens', 'не сообщено') if not call['reused'] else 0} | "
                     f"{usage.get('completion_tokens', 'не сообщено') if not call['reused'] else 0} |")
    lines += ["", "Накопленный расход включает отклонённые вызовы и повторные попытки. "
              "Синтетические проверки учтены отдельными этапами diagnostic_transport и diagnostic_dependencies; "
              "их данные не входят в обучение или сравнение научных утверждений. "
              "Отсутствующие данные usage не считаются нулевым расходом.", "",
              "| Этап | Новых вызовов всего | Input tokens | Output tokens | Без usage |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for stage, costs in report["costs"]["cumulative"].items():
        lines.append(f"| {stage} | {costs['new_calls']} | {costs['input_tokens']} | "
                     f"{costs['output_tokens']} | {costs['calls_without_usage']} |")
    lines += ["", "Причины переиспользования и пересборки записаны для каждого вызова в JSON-отчёте.",
              "", "### Отклонённые вызовы", "",
              "| Этап | Идентификатор попытки | Причина |", "| --- | --- | --- |"]
    for call in report["diagnostics"]["rejected_calls"]:
        reason = (call.get("refusal_reason") or call.get("error") or "см. исходный журнал").replace("|", "\\|")
        lines.append(f"| {call['stage']} | {call['attempt_id']} | {reason} |")
    lines.append("")
    for incident in report["diagnostics"]["pipeline_incidents"]:
        lines.append(f"- {incident['description']}")
    lines += ["",
              "", "## Версии и структура карт", "", "```json",
              json.dumps(report["versions"], ensure_ascii=False, indent=2), "```", "",
              f"Хеш анализа: `{report['analysis_revision']}`.",
              f"Хеш реестра: `{report['registry_sha256']}`.",
              f"Зафиксированный прогноз: `{report['prediction_artifact_sha256']}`.",
              f"Исходная GOLD-карта: `{report['initial_gold_run_id']}`.", "",
              "| Источник | Блоков | Связей | Глубина |", "| --- | ---: | ---: | ---: |"]
    for item in report["map_analysis"]:
        analysis = item["analysis"]
        lines.append(f"| {item['source_id']} | {item['nodes']} | {item['edges']} | "
                     f"{analysis.get('depth', 'см. JSON')} |")
    target_analysis = report["target_analysis"]
    lines.append(f"| Цель PMC10000452 | {target_analysis['nodes']} | {target_analysis['edges']} | "
                 f"{target_analysis['analysis'].get('depth', 'см. JSON')} |")
    lines += ["", "## Диагностика", "", "```json",
              json.dumps({mode: report["diagnostics"][mode] for mode in ("semantic", "graph")},
                         ensure_ascii=False, indent=2), "```", "",
              "Канонизация консервативная: неоднозначные сокращения не объединяются; "
              "неизвестные предикаты и ссылки на знания перечислены в JSON. "
              "Строгие контексты могут уменьшить число совпадений.", "",
              "## Недоступные источники", "",
              "Статусы отражают проверку указанных OA-ресурсов, а не утверждение, что полный текст нигде недоступен.", "",
              "| Ссылка | Статус | Причина |", "| --- | --- | --- |"]
    for source in report["diagnostics"]["unavailable"]:
        lines.append(f"| {source['number']} | {source['status']} | {source.get('reason', '')} |")
    lines += ["",
              "## Следующий шаг", "",
              "Разобрать ошибки и при необходимости повторить этот состав корпуса с новой версией правил.",
              "Следующие пять источников автоматически не добавляются.", ""]
    return "\n".join(lines)


class ReferencePilot:
    def __init__(self, provider: ReferenceSourceProvider, builder: PilotMapBuilder, store: ExperimentStore,
                 *, analysis_revision: str | None = None, map_concurrency: int = 1):
        self.provider, self.builder, self.store = provider, builder, store
        self.analysis_revision = analysis_revision
        require(1 <= map_concurrency <= 5, "Invalid map concurrency limit")
        self.map_concurrency = map_concurrency

    async def run(self, size: int = 5) -> dict:
        require(size >= 1, "Checkpoint size must be positive")
        previous = self.store.read("state.json") or {"completed_size": 0}
        require(size <= previous["completed_size"] + 5, "Cannot skip a five-source checkpoint")
        registry = await self.provider.registry()
        by_number = {r["number"]: r for r in registry["references"]}
        require(set(registry["order"]) == set(by_number) and len(registry["order"]) == len(by_number),
                "Frozen bibliography order is invalid")
        references = [by_number[n] for n in registry["order"] if by_number[n]["status"] == "open_access"]
        require(bool(references), "No verified Open Access full texts available")
        count = min(size, len(references))
        require(count >= previous["completed_size"], "Corpus cannot shrink silently")
        chosen = references[:count]
        chosen_ids = [r.get("pmcid") or r.get("doi") or f"source-{r['number']}" for r in chosen]
        if previous.get("source_ids"):
            require(chosen_ids[:previous["completed_size"]] == previous["source_ids"],
                    "Previous checkpoint corpus changed; do not combine rule and corpus changes")
        sources, failures = [], []
        seen = set()
        for reference in chosen:
            source = await self.provider.materialize(reference)
            require(source["source_id"] not in {registry["target_pmc_id"], registry["target_doi"]},
                    "Target identity found in source registry")
            require(source["source_id"] not in seen, "Duplicate scientific source in checkpoint")
            seen.add(source["source_id"])
            sources.append(source)

        semaphore, stopped = asyncio.Semaphore(self.map_concurrency), asyncio.Event()

        async def build_source(source):
            async with semaphore:
                if stopped.is_set():
                    raise ValueError("Batch paused after a failed map; source was not sent to LLM")
                try:
                    return await self.builder.build(source)
                except BaseException as exc:
                    stopped.set()
                    failures.append({"source_id": source["source_id"], "reason": type(exc).__name__})
                    raise

        # Лимит одновременных документов задаётся явно; порядок корпуса не меняется.
        # При отказе уже начатая карта завершается; новые запросы не стартуют.
        tasks = [asyncio.create_task(build_source(source)) for source in sources]
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        if failures:
            self.store.write(f"failures/{uuid4()}.json", {"size": count, "failures": failures,
                                                       "model_calls": list(self.builder.calls)})
            raise next(result for result in results if isinstance(result, BaseException)
                       and str(result) != "Batch paused after a failed map; source was not sent to LLM")
        maps = results

        versions = [map_version(result) for result in maps]
        require(len({fingerprint(version) for version in versions}) == 1,
                "Incompatible map versions cannot enter the same prediction corpus")

        # Словарь обучается до загрузки карты цели и только на обучающем корпусе.
        aliases = fit_aliases(result["graph"] for result in maps)
        corpus = merge_corpora(canonicalize(source["source_id"], result["graph"], aliases)
                               for source, result in zip(sources, maps))
        corpus.assert_isolated({registry["target_pmc_id"], registry["target_doi"]})
        predictions, rules, diagnostics = {}, {}, {}
        for mode in ("semantic", "graph"):
            learned, stats = learn_rules(corpus, graph_mode=mode == "graph")
            predicted, prediction_stats = predict(corpus, learned)
            predictions[mode], rules[mode] = predicted, [r.to_dict() for r in learned]
            diagnostics[mode] = {**stats, **prediction_stats}
        known = {o.atom.key: {"id": o.atom.key, "atom": {
            "predicate": o.atom.predicate, "kind": o.atom.kind, "roles": o.atom.roles,
            "scope": o.atom.scope, "negated": o.atom.negated}} for o in corpus.occurrences}
        predictions["known_union"] = [known[key] for key in sorted(known)]
        run_id = str(uuid4())
        relative = f"runs/{run_id}"
        frozen = {"run_id": run_id, "source_count": count, "sources": sources,
                  "execution": {"map_concurrency": self.map_concurrency},
                  "map_runs": [m["run_id"] for m in maps], "canonicalizer_version": VERSION,
                  "map_version": versions[0], "analysis_revision": self.analysis_revision,
                  "registry_sha256": fingerprint(registry),
                  "aliases": aliases, "rules": rules, "predictions": predictions}
        self.store.write(relative + "/predictions.json", frozen)
        frozen_sha = fingerprint(frozen)
        log.info("reference_pilot predictions_sealed run=%s count=%s hash=%s", run_id, count, frozen_sha)

        # Цель впервые входит в сценарий после фиксации прогнозов.
        target_source = await self.provider.target()
        target_map = await self.builder.build(target_source)
        require(map_version(target_map) == versions[0], "Target map version differs from source maps")
        target = canonicalize(registry["target_pmc_id"], target_map["graph"], aliases)
        self.store.write("target/anchor.json", target_map) if self.store.read("target/anchor.json") is None else None
        anchor = self.store.read("target/anchor.json")
        anchor_corpus = canonicalize(registry["target_pmc_id"], anchor["graph"], aliases)
        initial = self.store.read("target/initial_existing_gold_map.json")
        initial_corpus = (canonicalize(registry["target_pmc_id"], initial["graph"], aliases)
                          if initial and initial["graph"].get("schema_version") == 5 else None)
        scientific_calls = (self.store.read("cost_ledger.json") or {}).get("attempts", [])
        diagnostic_calls = (self.store.read("diagnostic_calls.json") or {}).get("attempts", [])
        report = {"run_id": run_id, "created_at": datetime.now(timezone.utc).isoformat(),
                  "pipeline_id": "text_reified", "source_count": count, "sources": sources,
                  "execution": {"map_concurrency": self.map_concurrency},
                  "target_run_id": target_map["run_id"], "prediction_artifact_sha256": frozen_sha,
                  "target_analysis": {"nodes": len(target_map["graph"]["nodes"]),
                                      "edges": len(target_map["graph"]["edges"]),
                                      "analysis": target_map["graph"].get("analysis", {}),
                                      "validation": target_map.get("validation", {})},
                  "versions": versions[0], "analysis_revision": self.analysis_revision,
                  "registry_sha256": fingerprint(registry),
                  "map_analysis": [{"source_id": source["source_id"], "run_id": result["run_id"],
                                    "nodes": len(result["graph"]["nodes"]), "edges": len(result["graph"]["edges"]),
                                    "analysis": result["graph"].get("analysis", {}),
                                    "validation": result.get("validation", {})}
                                   for source, result in zip(sources, maps)],
                  "predictions": predictions, "rules": rules,
                  "evaluation": {mode: evaluate(items, target) for mode, items in predictions.items()},
                  "anchor_evaluation": {mode: evaluate(items, anchor_corpus) for mode, items in predictions.items()},
                  "initial_gold_evaluation": ({mode: evaluate(items, initial_corpus)
                                               for mode, items in predictions.items()} if initial_corpus else None),
                  "initial_gold_run_id": initial["run_id"] if initial else None,
                  "costs": {"current": cost_summary(self.builder.calls),
                            "cumulative": cost_summary([*scientific_calls, *diagnostic_calls]),
                            "scientific": cost_summary(scientific_calls),
                            "diagnostic": cost_summary(diagnostic_calls)},
                  "model_calls": list(self.builder.calls), "diagnostics": diagnostics | {
                      "rejected_calls": [call for call in [*scientific_calls, *diagnostic_calls]
                                         if call.get("validated") is False],
                      "synthetic_controls": diagnostic_calls,
                      "pipeline_incidents": self.store.read("pipeline_incidents.json") or [],
                      "canonicalization": corpus.diagnostics, "unavailable": [r for r in registry["references"]
                                                                                 if r["status"] != "open_access"],
                      "scientific_review": "not_performed", "target_role": "development_case"},
                  "previous_run_id": previous.get("run_id"), "automatic_advance": False}
        # Возвращаем тот же JSON-контракт, который записывается на диск (без tuple).
        report = json.loads(json.dumps(report, ensure_ascii=False, allow_nan=False))
        self.store.write(relative + "/report.json", report)
        self.store.write_bytes(relative + "/report.ru.md", markdown_report(report).encode("utf-8"))
        self.store.write("state.json", {"completed_size": count, "run_id": run_id,
                                       "source_ids": chosen_ids}, immutable=False)
        return report
