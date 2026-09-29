from pathlib import Path

from knowledge_contracts.block_dsl import DSL_FIELDS
from knowledge_contracts.block_types import ALL_TYPES, KEY_TO_LEGACY_INT
from knowledge_pipeline.prompts import DSL_SYSTEM, PROMPT_VERSION, type_doc_with_codes
from knowledge_pipeline.semantic_extraction import CORRECTION_TEMPLATE


def test_prompt_field_catalog_covers_every_registered_type_with_dsl_keys():
    catalog = type_doc_with_codes()

    for block_type in ALL_TYPES:
        code = KEY_TO_LEGACY_INT[block_type]
        line = next(
            (item for item in catalog.splitlines()
             if item.startswith(f"  T{code} {block_type}:")),
            None,
        )
        assert line is not None, f"Missing DSL field catalog for T{code} {block_type}"
        for dsl_key in DSL_FIELDS[block_type]:
            assert f"{dsl_key}=" in line, (
                f"Missing canonical DSL key {dsl_key}= for T{code} {block_type}"
            )


def test_t14_guidance_distinguishes_protocols_from_other_scientific_roles():
    prompt = " ".join(DSL_SYSTEM.split())
    assert PROMPT_VERSION == "148"
    assert "T14 `experiment` identifies a concrete, source-described investigation" in prompt
    assert "one row per independently identifiable investigation" in prompt
    assert "observational investigation can qualify without an intervention/control" in prompt
    assert "Never omit an entire already-covered source unit" in prompt
    assert "T11 describes design, T21 procedures, T55 groups, T56 steps, and T36 findings" in prompt
    assert "In a review, do not imply that its authors conducted cited research" in prompt
    assert "T11" in prompt and "T21" in prompt and "T36" in prompt
    assert "PMC10000452" not in prompt


def test_prompt_retypes_objectless_empirical_findings_without_inventing_obj():
    prompt = " ".join(DSL_SYSTEM.split())
    assert "do not invent an object or leave obj= empty: use T36 `sum=`" in prompt


def test_prompt_does_not_fill_required_object_with_adverbial_adjuncts():
    prompt = " ".join(DSL_SYSTEM.split())
    assert "Never fill required `obj=` with one of these adjuncts" in prompt
    assert "Keep the adjunct in `ctx=`" in prompt
    assert "choose the type that expresses the source's actual role" in prompt


def test_explicit_paper_purpose_is_a_goal_not_only_editorial_signposting():
    prompt = " ".join(DSL_SYSTEM.split())
    assert "classify the main predicate's function before choosing T3" in prompt
    assert "do not emit the same sentence as T3 `content=`" in prompt
    assert "do not extract a relation from a modifier" in prompt


def test_prompt_keeps_list_members_atomic_and_preserves_means_vs_agent_roles():
    prompt = " ".join(DSL_SYSTEM.split())

    assert "separately named, independently identifiable members are separate rows" in prompt
    assert "coordinated predicates express independently verifiable actions, states, or findings" in prompt
    assert "A phrase such as “by means of X” names a means, not an agent" in prompt
    assert "T41 `side_effects` (`effects=`)" in prompt
    assert "Do not create T3 rows for empty units" in prompt


def test_prompt_preserves_argument_scope_in_lists_and_appositive_examples():
    prompt = " ".join(DSL_SYSTEM.split())

    assert "Resolve coordination by scope, not by punctuation alone" in prompt
    assert "preserve a collective/grouped argument" in prompt
    assert "must not become claims about A and B alone" in prompt


def test_prompt_resolves_controlled_relative_infinitives_and_types_follow_up_procedures():
    prompt = " ".join(DSL_SYSTEM.split())

    assert "which the authors expect to cause Y" in prompt
    assert "X is expected to cause Y" in prompt
    assert "make “which” a standalone subject" in prompt
    assert "follow-up assessment, or re-evaluation of participants is a T21 procedure" in prompt
    assert "use T36 for the resulting state, measurement, or group comparison" in prompt


def test_prompt_does_not_duplicate_pipeline_owned_captions_and_keeps_claims():
    prompt = " ".join(DSL_SYSTEM.split())

    assert "Do not emit T3 merely to repeat a caption" in prompt
    assert "Emit semantic rows only for explicit propositions in the caption" in prompt
    assert "if it has no proposition, emit no model row for it" in prompt
    assert "caption-navigation fragments with no proposition are covered by pipeline-generated T49" in prompt


def test_prompt_resolves_unambiguous_anaphora_and_types_explicit_research_aims():
    prompt = " ".join(DSL_SYSTEM.split())

    assert "nearest preceding source context only to resolve a uniquely identifiable" in prompt
    assert "T2 `goal`" in prompt
    assert "classify the main predicate's function before choosing T3" in prompt
    assert "T46 `future_research_suggestions`" in prompt
    assert "Epistemic modality (such as may/could) does not make a factual claim" in prompt
    assert "Resolve the antecedent only when it is unique" in prompt


def test_prompt_types_explicit_relations_without_guessing_anaphoric_referents():
    prompt = " ".join(DSL_SYSTEM.split())

    assert "Uncertainty about a referent alone" in prompt
    assert "preserve the source pronoun/demonstrative literally in its argument field" in prompt
    assert "not merely because an entity reference is unresolved" in prompt
    assert "emit the typed relation and preserve any unresolved pronoun literally" in prompt


def test_russian_prompt_reference_tracks_the_runtime_prompt_version_and_rules():
    russian_prompt = (
        Path(__file__).parents[2]
        / "pipeline"
        / "knowledge_pipeline"
        / "prompts.ru.md"
    ).read_text(encoding="utf-8")

    assert "версия 148" in russian_prompt
    assert "Не заполняйте обязательное `obj=` условием, временем, местом" in russian_prompt
    assert "сначала определите функцию главного предиката" in russian_prompt
    assert "не выдумывайте объект и не оставляйте обязательное поле пустым" in russian_prompt
    assert "Не выводите T3 только для повторения `caption_required`-единицы" in russian_prompt
    assert "Навигационная единица подписи без пропозиции покрывается автоматически добавляемой T49" in russian_prompt
    assert "если источник независимо утверждает отношение для каждого" in russian_prompt
    assert "отдельно названные, самостоятельно различимые элементы оформляйте отдельными строками" in russian_prompt
    assert "координированные предикаты выражают независимо проверяемые действия, состояния или результаты" in russian_prompt
    assert "подставьте однозначный антецедент как смысловое подлежащее инфинитивного предиката" in russian_prompt
    assert "повторная оценка участников — процедура T21" in russian_prompt
    assert "Оборот «посредством X» называет средство/способ, а не деятеля" in russian_prompt
    assert "T41 `side_effects` (`effects=`)" in russian_prompt
    assert "Не создавайте T3 для пустых единиц" in russian_prompt
    assert "T2 `goal`" in russian_prompt and "T46 `future_research_suggestions`" in russian_prompt
    assert "сохранив исходное местоимение/указание буквально в поле аргумента" in russian_prompt


def test_prompt_uses_canonical_dsl_keys_and_preserves_valid_rows_during_correction():
    prompt = " ".join(DSL_SYSTEM.split())
    correction = " ".join(CORRECTION_TEMPLATE.split())

    assert "storage/JSON property names are not DSL keys" in prompt
    assert "Include every required key" in prompt
    assert "compare the corrected output with the prior candidate" in correction
    assert "must not silently delete or weaken another fact" in correction
    assert "PMC10000452" not in prompt

