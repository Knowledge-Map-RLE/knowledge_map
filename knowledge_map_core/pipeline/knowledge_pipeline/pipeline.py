"""Loss-preserving transformations; IO is injected through application ports.

Variant A: the whole article is typed in ONE LLM call that returns structural
DSL rows (``B T<код> B<тег> | ... | unit=S<n>``). A structural row may support
zero or more atomic Assertions during deterministic adaptation.
"""
from __future__ import annotations
import copy
import hashlib
import logging
import re
import time
import uuid

from knowledge_contracts.uuidv8 import uuid8_str
from knowledge_contracts.block_dsl import DIRECT_ASSERTION_TYPES, DSL_FIELDS
from knowledge_contracts.validation import (require, validate_linguistic,
                                            validate_map, validate_structural)
from .knowledge_map_builder import build_knowledge_map
from .caption_units import caption_unit_ids
from .quality_metrics import evaluate_article_transformation
from .reference_stripping import strip_references_info
from .renumbering import remap_local_tags
from .dsl_rows import missing_required_fields
from .semantic_extraction import (
    is_layout_only_fragment,
    _semantic_warning_findings,
    extract_structural_rows,
)
from .prompts import PROMPT_ID, PROMPT_VERSION

log = logging.getLogger(__name__)

def uid():
    return uuid8_str()

def checksum(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def source_revision(doc_id, text):
    require(bool(text.strip()), "Empty article")
    digest = checksum(text)
    return {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, doc_id + ":" + digest)),
            "article_id": doc_id, "text": text, "sha256": digest,
            "offset_encoding": "unicode_codepoints"}

def linguistic_profile(source, document):
    """Adapt the NLP document into the self-contained linguistic reference layer.

    The profile retains tokens, sentences, dependencies, phrases and markdown
    sections (full lexical/syntactic provenance) but no semantic nodes/links.
    """
    text = source["text"]
    result = {"source_revision_id": source["id"], "tokens": [], "sentences": [],
              "dependencies": [], "phrases": [], "sections": []}
    require(document.get("text") == text, "NLP changed original text")
    for sent in document["sentences"]:
        sid = uid()
        start, end = sent.get("start_char", 0), sent["end_char"]
        require(isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text),
                "NLP sentence has invalid span")
        result["sentences"].append({"id": sid, "start": start, "end": end})
        token_map = {}
        for token in sent.get("tokens", []):
            tid = uid()
            token_map[token.get("idx", 0)] = tid
            result["tokens"].append({"id": tid, "sentence_id": sid, "text": token["text"],
                                     "start": token.get("start_char", 0), "end": token["end_char"],
                                     "lemma": token.get("lemma", ""), "pos": token.get("pos", ""),
                                     "morph": token.get("morph", {})})
        for dep in sent.get("dependencies", []):
            h, d = dep.get("head_idx", 0), dep.get("dependent_idx", 0)
            require(h in token_map and d in token_map, "NLP dependency has unknown token")
            result["dependencies"].append({"source": token_map[h], "target": token_map[d],
                                           "relation": dep["relation"]})
        for phrase in sent.get("phrases", []):
            members = [token_map[t.get("idx", 0)] for t in phrase.get("tokens", [])
                       if t.get("idx", 0) in token_map]
            if members:
                result["phrases"].append({"id": uid(), "sentence_id": sid, "token_ids": members,
                                          "phrase_type": phrase.get("phrase_type", "")})
    headings = list(re.finditer(r"(?m)^#{1,6} +([^\r\n]+)", text))
    boundaries = ([(0, headings[0].group(1))] if headings and headings[0].start() == 0
                  else [(0, "Preamble")])
    boundaries += [(m.start(), m.group(1)) for m in headings if m.start() != 0]
    result["sections"] = [{"id": uid(), "start": a,
                           "end": boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text),
                           "title": title} for i, (a, title) in enumerate(boundaries)]
    for sentence in result["sentences"]:
        section = next(s for s in reversed(result["sections"]) if s["start"] <= sentence["start"])
        sentence["section_id"] = section["id"]
    validate_linguistic(result, source)
    return result

def source_units(profile, text):
    return [{"id": "S" + str(i + 1), "start": s["start"], "end": s["end"],
             "text": text[s["start"]:s["end"]]} for i, s in enumerate(profile["sentences"])]


def _metadata_value_identity(value):
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    return value


def consolidate_metadata_rows(rows):
    """Collapse unit-local T1 candidates to the article's singleton metadata row.

    Metadata fields are collected only from T1 candidates. List fields are
    stably unioned; repeated scalar values are deduplicated, while contradictory
    scalar values fail explicitly instead of silently discarding source data.
    Source units are retained as internal provenance for materialization.
    """
    field_kinds = {
        spec.json_field: spec.kind
        for spec in DSL_FIELDS["metadata"].values()
    }
    indexed_metadata = [(index, row) for index, row in enumerate(rows)
                        if row.get("blockType") == "metadata"]
    for _, row in indexed_metadata:
        require(any(
            field in field_kinds and row["data"].get(field) not in (None, "", [])
            for field in row["data"]
        ), f"Metadata row {row.get('tag')} has no explicit T1 field")
        authors = row["data"].get("authors") or []
        orcids = row["data"].get("authorsOrcid") or []
        require(not orcids or (authors and len(orcids) == len(authors)),
                f"Metadata row {row.get('tag')} has unaligned authorsOrcid and authors")
    if len(indexed_metadata) < 2:
        return rows

    rows = copy.deepcopy(rows)
    indexed_metadata = [(index, row) for index, row in enumerate(rows)
                        if row.get("blockType") == "metadata"]
    ordered_metadata = sorted(
        indexed_metadata,
        key=lambda item: (
            int(item[1]["data"]["unit"][1:])
            if re.fullmatch(r"S[1-9][0-9]*", item[1]["data"].get("unit", ""))
            else float("inf"),
            item[0],
        ),
    )
    canonical_index, canonical = ordered_metadata[0]
    canonical_tag = canonical["tag"]
    merged_data = dict(canonical["data"])
    source_units: list[str] = []
    seen_by_field: dict[str, set] = {}
    field_sources: dict[str, str] = {}
    aliases: dict[str, str] = {}

    for _, row in ordered_metadata:
        data = row["data"]
        tag = row["tag"]
        unit = data.get("unit")
        require(isinstance(unit, str) and re.fullmatch(r"S[1-9][0-9]*", unit),
                f"Metadata row {tag} has invalid unit")
        if unit not in source_units:
            source_units.append(unit)
        if tag != canonical_tag:
            aliases[tag] = canonical_tag

        for field, value in data.items():
            if field in {"tag", "unit"} or value is None or value == "" or value == []:
                continue
            kind = field_kinds.get(field)
            if kind == "strs":
                require(isinstance(value, list),
                        f"Metadata list field {field} must be a list")
                combined = merged_data.setdefault(field, [])
                seen = seen_by_field.setdefault(
                    field, {_metadata_value_identity(item) for item in combined}
                )
                for item in value:
                    identity = _metadata_value_identity(item)
                    if identity not in seen:
                        combined.append(item)
                        seen.add(identity)
                continue

            if field not in merged_data or merged_data[field] in (None, "", []):
                merged_data[field] = value
                field_sources[field] = unit
                continue
            if _metadata_value_identity(merged_data[field]) != _metadata_value_identity(value):
                first_unit = field_sources.get(field, canonical["data"].get("unit", "unknown"))
                require(False,
                        f"Conflicting T1 metadata field {field!r} in {first_unit} and {unit}")

    merged_data["tag"] = canonical_tag
    merged_data["unit"] = source_units[0]
    authors = merged_data.get("authors") or []
    orcids = merged_data.get("authorsOrcid") or []
    require(not orcids or (authors and len(orcids) == len(authors)),
            "Merged T1 authorsOrcid must remain positionally aligned with authors")
    consolidated = {
        **canonical,
        "tag": canonical_tag,
        "data": merged_data,
        "_source_units": source_units,
    }
    removed_indexes = {index for index, _ in indexed_metadata} - {canonical_index}
    output = []
    for index, row in enumerate(rows):
        if index == canonical_index:
            output.append(consolidated)
        elif index not in removed_indexes:
            output.append(row)

    if aliases:
        for row in output:
            data = row["data"]
            for spec in DSL_FIELDS.get(row["blockType"], {}).values():
                field = spec.json_field
                if field not in data:
                    continue
                if spec.kind == "ref":
                    data[field] = aliases.get(data[field], data[field])
                elif spec.kind == "refs":
                    data[field] = list(dict.fromkeys(aliases.get(value, value)
                                                     for value in data[field]))
    # Removing candidate rows can leave tag gaps; restore canonical physical
    # order and update every surviving DSL-tag reference at the same time.
    return remap_local_tags(output, 1)


def materialize_rows(rows, source, profile):
    """Materialize parsed DSL rows into persisted structural blocks.

    Assigns ``instanceId``/``order`` and resolves each row's ``unit=S<n>`` to the
    sentence span; ``data["provenance"]`` records the source span and unit ids
    (the verbatim fragment is derived from ``source.text`` + the span, never
    duplicated into ``data``, which can legitimately own a ``source`` field).

    ``text`` blocks own a mandatory ``content`` whose canonical value is the
    verbatim source text of the unit; when the model drops it, the value is
    restored deterministically from ``source.text`` (identical to the
    provenance span), never guessed or fabricated.
    """
    rows = consolidate_metadata_rows(rows)
    sentences = profile["sentences"]
    # DSL B-tags are batch-local transport identifiers. Persist the explicit
    # statement reference as a UUID, never as a tag or copied source text.
    instance_by_tag = {row["tag"]: uid() for row in rows}
    require(len(instance_by_tag) == len(rows), "Duplicate structural row tags")
    row_by_tag = {row["tag"]: row for row in rows}
    blocks = []
    for order, row in enumerate(rows):
        data = dict(row["data"])
        subject_ref = data.get("subjectStatementRef")
        if subject_ref:
            target = row_by_tag.get(subject_ref)
            require(target is not None,
                    f"Row {row['tag']} subref= cites undeclared row {subject_ref}")
            require(target["tag"] != row["tag"],
                    f"Row {row['tag']} subref= cannot cite itself")
            require(target["blockType"] in DIRECT_ASSERTION_TYPES,
                    f"Row {row['tag']} subref= must cite one direct assertion")
            data["subjectStatementRef"] = instance_by_tag[subject_ref]
        unit = data["unit"]
        match = re.match(r"^S([1-9][0-9]*)$", unit)
        require(bool(match), f"Row {row['tag']} has invalid unit {unit!r}")
        index = int(match.group(1)) - 1
        require(0 <= index < len(sentences), f"Row {row['tag']} references unknown unit {unit}")
        sentence = sentences[index]
        source_unit_ids = row.get("_source_units") or [unit]
        require(source_unit_ids[0] == unit,
                f"Row {row['tag']} primary unit must be its first provenance unit")
        require(row["blockType"] == "metadata" or source_unit_ids == [unit],
                f"Only metadata rows may aggregate source units ({row['tag']})")
        spans = []
        for source_unit in source_unit_ids:
            source_match = re.fullmatch(r"S([1-9][0-9]*)", source_unit)
            require(bool(source_match),
                    f"Row {row['tag']} has invalid provenance unit {source_unit!r}")
            source_index = int(source_match.group(1)) - 1
            require(0 <= source_index < len(sentences),
                    f"Row {row['tag']} references unknown provenance unit {source_unit}")
            source_sentence = sentences[source_index]
            spans.append({"revision_id": source["id"],
                          "start": source_sentence["start"],
                          "end": source_sentence["end"]})
        if row["blockType"] == "text" and not data.get("content"):
            data["content"] = source["text"][sentence["start"]:sentence["end"]]
        data["provenance"] = {"unit_ids": source_unit_ids, "source_spans": spans}
        blocks.append({"instanceId": instance_by_tag[row["tag"]], "schemaVersion": 2, "blockType": row["blockType"],
                       "data": data, "order": order})
    validate_structural(blocks, source, sentences)
    return blocks

def knowledge_map(blocks):
    """Alias: the Knowledge Map is derived purely from structural rows."""
    return build_knowledge_map(blocks)

class ArticlePipeline:
    def __init__(self, nlp, llm, chunk_chars=None, batch_sentences=None,
                 structural_builder=None):
        del structural_builder
        require(batch_sentences is None or (isinstance(batch_sentences, int) and batch_sentences > 0),
                "batch_sentences must be a positive integer or None")
        require(chunk_chars is None, "Character chunking is not supported; use batch_sentences")
        self.nlp, self.llm = nlp, llm
        self.batch_sentences = batch_sentences

    async def _extract_rows_batched(self, units, stripped_text, caption_units, result,
                                    linguistic_profile_data, checkpoint=None):
        """Run deterministic sentence batches through extraction and semantic audit.

        Tag ids are local inside a call and are renumbered deterministically to
        a global sequence, so the result is equivalent to one whole-article
        typing but stays within the model's per-call row budget.

        Every successfully parsed batch is checkpointed (together with its rows)
        and ``model_steps``; on resume the pipeline recovers the completed
        batches from the checkpoint and only re-runs the LLM for the rest.
        Rows are persisted per step so partial progress survives a mid-run fail.
        Recovered batches whose rows miss a structural required field are not
        trusted: they are re-extracted from the first defective batch onward,
        so the model (not a silent heuristic) repairs the contract.
        """
        batches = ([units[i:i + self.batch_sentences]
                    for i in range(0, len(units), self.batch_sentences)]
                   if self.batch_sentences else [units])
        rows_all: list = []
        steps = result.setdefault("model_steps", [])
        start_batch = len(steps)
        for step_index, step in enumerate(steps):
            if any(missing_required_fields(row) for row in (step.get("rows") or [])):
                del steps[step_index:]
                rows_all = []
                for kept in steps:
                    rows_all.extend(kept.get("rows") or [])
                start_batch = len(steps)
                break
            rows_all.extend(step.get("rows") or [])
        total_llm_seconds = 0.0
        for batch_index in range(start_batch, len(batches)):
            batch = batches[batch_index]
            request = {
                "context": "",
                "source": stripped_text,
                "source_units": [{"id": u["id"], "text": u["text"],
                                  "start": u["start"], "end": u["end"]}
                                 for u in batch],
                "linguistic_profile": linguistic_profile_data,
                "caption_unit_ids": [u["id"] for u in batch if u["id"] in caption_units],
            }
            llm_started_at = time.perf_counter()
            rows, model_steps = await extract_structural_rows(
                self.llm, request, [u["id"] for u in batch])
            batch_elapsed = time.perf_counter() - llm_started_at
            total_llm_seconds += batch_elapsed
            if len(batches) > 1:
                rows = remap_local_tags(rows, len(rows_all) + 1)
            rows_all.extend(rows)
            steps.append({
                "chunk": batch_index,
                "start": batch[0]["start"], "end": batch[-1]["end"], "rows": rows,
                **model_steps})
            if checkpoint is not None and len(batches) > 1:
                result.update(processed=batch_index + 1, total=len(batches))
                await checkpoint(copy.deepcopy(result))
        return rows_all, total_llm_seconds

    async def run(self, doc_id, text, checkpoint, run_id=None, resume=None):
        started_at = time.perf_counter()
        timing = {"mode": "whole_article"}
        stripped_text, refinfo = strip_references_info(text)
        source = source_revision(doc_id, stripped_text)
        result = {"schemaVersion": 2, "run_id": run_id or uid(), "version_id": uid(),
                  "article_id": doc_id, "source": source, "stage": "source", "status": "running"}
        processing = {"references_removed": refinfo} if refinfo is not None else {}
        if resume is not None:
            require(resume["source"] == source, "Cannot resume a different source revision")
            require(resume["article_id"] == doc_id, "Cannot resume another article")
            result = copy.deepcopy(resume)
            result.update(status="running", success=False)
            result.pop("error", None)
        execution = {"chunk_chars": None, "mode": "batched_sentences" if self.batch_sentences else "whole_article",
                     "batch_sentences": self.batch_sentences,
                     "prompt_id": PROMPT_ID, "prompt_version": PROMPT_VERSION}
        result["processing"] = processing
        if resume is not None:
            require(resume.get("execution") == execution, "Cannot resume with older extraction mode")
            if resume.get("success") and resume.get("stage") == "complete":
                result.update(status=resume.get("status", "completed"), success=True)
                result.pop("error", None)
                log.info("article_pipeline resume of completed version run=%s", result["run_id"])
                return result
        result["execution"] = execution
        await checkpoint(copy.deepcopy(result))
        profile = result.get("linguistic_profile") if "linguistic_profile" in result else None
        blocks = result.get("blocks") if result.get("stage") in ("structural", "complete") else None
        if resume is not None and blocks is not None and profile is not None:
            map_started_at = time.perf_counter()
            validate_linguistic(profile, source)
            self._set_semantic_warnings(result, profile, stripped_text, blocks)
            graph = knowledge_map(blocks)
            quality_metrics = evaluate_article_transformation(source, profile, blocks, graph)
            coverage = self._coverage(profile, blocks, source["text"])
            timing["map_and_metrics_seconds"] = round(time.perf_counter() - map_started_at, 6)
            timing["total_seconds"] = round(time.perf_counter() - started_at, 6)
            result["timing"] = timing
            result = self._complete(result, profile, blocks, graph, coverage, quality_metrics)
            await checkpoint(copy.deepcopy(result))
            log.info("article_pipeline re-evaluated blocks article=%s run=%s", doc_id, result["run_id"])
            return result
        if profile is not None:
            validate_linguistic(profile, source)
        else:
            document = result.get("linguistic_document")
            if document is None:
                nlp_started_at = time.perf_counter()
                document = await self.nlp(stripped_text)
                timing["nlp_seconds"] = round(time.perf_counter() - nlp_started_at, 6)
                result.update(stage="linguistic", linguistic_document=document)
                await checkpoint(copy.deepcopy(result))
            profile = linguistic_profile(source, document)
            result.pop("linguistic_document", None)
        result.update(stage="linguistic_profile", linguistic_profile=profile)
        await checkpoint(copy.deepcopy(result))
        units = source_units(profile, stripped_text)
        rows, total_llm_seconds = await self._extract_rows_batched(
            units, stripped_text, caption_unit_ids(profile, stripped_text), result,
            profile, checkpoint)
        timing["llm_seconds"] = round(total_llm_seconds, 6)
        map_started_at = time.perf_counter()
        blocks = materialize_rows(rows, source, profile)
        self._set_semantic_warnings(result, profile, stripped_text, blocks)
        result.update(stage="structural", blocks=blocks)
        await checkpoint(copy.deepcopy(result))
        graph = knowledge_map(blocks)
        quality_metrics = evaluate_article_transformation(source, profile, blocks, graph)
        coverage = self._coverage(profile, blocks, source["text"])
        timing["map_and_metrics_seconds"] = round(time.perf_counter() - map_started_at, 6)
        timing["total_seconds"] = round(time.perf_counter() - started_at, 6)
        result["timing"] = timing
        result = self._complete(result, profile, blocks, graph, coverage, quality_metrics)
        await checkpoint(copy.deepcopy(result))
        log.info("article_pipeline completed article=%s run=%s", doc_id, result["run_id"])
        return result

    @staticmethod
    def _coverage(profile, blocks, source_text):
        covered = {t["id"] for block in blocks
                   for span in block["data"]["provenance"]["source_spans"]
                   for t in profile["tokens"]
                   if t["start"] < span["end"] and t["end"] > span["start"]}
        layout_spans = [
            (sentence["start"], sentence["end"])
            for sentence in profile["sentences"]
            if is_layout_only_fragment(
                source_text[sentence["start"]:sentence["end"]]
            )
        ]
        covered.update(
            token["id"] for token in profile["tokens"]
            if any(start < token["end"] and token["start"] < end
                   for start, end in layout_spans)
        )
        covered_indexes, uncovered_ids = ArticlePipeline._sentence_coverage(
            profile, blocks, source_text,
        )
        caption_units = caption_unit_ids(profile, source_text)
        caption_image_units = {
            unit for block in blocks if block.get("blockType") == "image"
            for unit in block.get("data", {}).get("provenance", {}).get("unit_ids", []) or []
            if unit in caption_units
        }
        return {
            "token_preservation": 1.0,
            "semantic_token_fraction": len(covered) / max(1, len(profile["tokens"])),
            "unrepresented_token_ids": [t["id"] for t in profile["tokens"] if t["id"] not in covered],
            "sentence_count": len(profile["sentences"]),
            "covered_sentence_count": len(covered_indexes),
            "uncovered_sentence_ids": uncovered_ids,
            "caption_unit_count": len(caption_units),
            "caption_image_covered_unit_count": len(caption_image_units),
            "uncovered_caption_unit_ids": sorted(caption_units - caption_image_units,
                                                   key=lambda unit: int(unit[1:])),
        }

    @staticmethod
    def _set_semantic_warnings(result, profile, source_text, blocks):
        """Store diagnostics against final, globally remapped structural rows."""
        review_warnings = [
            finding
            for step in result.get("model_steps", [])
            for finding in step.get("warnings", [])
            if isinstance(finding, dict)
            and finding.get("code") == "objectless_t4_retyped"
        ]
        rows = [
            {"blockType": block["blockType"], "tag": block["data"].get("tag"),
             "data": block["data"]}
            for block in blocks
        ]
        warnings = _semantic_warning_findings(
            rows, source_units(profile, source_text), profile,
        )
        known = {
            (finding.get("code"), finding.get("unit"), finding.get("tag"),
             finding.get("message"))
            for finding in warnings
        }
        warnings.extend(
            finding for finding in review_warnings
            if (finding.get("code"), finding.get("unit"), finding.get("tag"),
                finding.get("message")) not in known
        )
        steps = result.setdefault("model_steps", [])
        for step in steps:
            step["warnings"] = []
        if steps:
            steps[-1]["warnings"] = warnings
        if warnings:
            log.warning("article_pipeline semantic warnings=%d", len(warnings))

    @staticmethod
    def _sentence_coverage(profile, blocks, source_text):
        covered_indexes = set()
        for block in blocks:
            for unit in block.get("data", {}).get("provenance", {}).get("unit_ids", []) or []:
                match = re.match(r"^S([1-9][0-9]*)$", unit)
                if match:
                    covered_indexes.add(int(match.group(1)) - 1)
        for index, sentence in enumerate(profile["sentences"]):
            fragment = source_text[sentence["start"]:sentence["end"]]
            if is_layout_only_fragment(fragment):
                covered_indexes.add(index)
        total = len(profile["sentences"])
        uncovered_ids = [f"S{i + 1}" for i in range(total) if i not in covered_indexes]
        return covered_indexes, uncovered_ids

    @staticmethod
    def _complete(result, profile, blocks, graph, coverage, quality_metrics):
        evidence = quality_metrics.get("evidence", {}) or {}
        fidelity = evidence.get("evidence_fraction")
        semantic_fidelity = round(fidelity, 6) if isinstance(fidelity, (int, float)) else "requires_review"
        validation = {"linguistic": "passed", "structural": "passed", "map": "passed",
                      "semantic_fidelity": semantic_fidelity}
        if coverage["uncovered_sentence_ids"] or coverage["uncovered_caption_unit_ids"]:
            missing = ", ".join(coverage["uncovered_sentence_ids"][:50])
            missing_captions = ", ".join(coverage["uncovered_caption_unit_ids"][:50])
            detail = f"uncovered: {missing}" if missing else ""
            if missing_captions:
                detail = f"{detail}; " if detail else ""
                detail += f"caption image rows missing for: {missing_captions}"
            result.update(stage="complete", status="failed", success=False,
                          error=f"coverage_gate: {detail}",
                          coverage=coverage, graph=graph, validation=validation,
                          quality_metrics=quality_metrics)
            log.warning("article_pipeline coverage gate failed article=%s uncovered=%d",
                        result["article_id"], len(coverage["uncovered_sentence_ids"]))
        else:
            result.update(stage="complete", status="completed", success=True,
                          coverage=coverage, graph=graph, validation=validation,
                          quality_metrics=quality_metrics)
        return result
