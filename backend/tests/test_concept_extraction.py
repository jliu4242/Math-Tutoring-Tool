"""Unit tests for concept_agent.py's block filtering/formatting (ARCHITECTURE.md
section 9). identify_concepts' LLM call is mocked; _filter_teaching_blocks and
_format_teaching_blocks are pure functions over the same dict shape
structure_agent.py's identify_structure already consumes ({"page_number":,
"blocks": [{"text":, "text_level":, "type":}, ...]}), so no fixture PDF is needed.
"""

from __future__ import annotations

import os
from unittest.mock import patch

# concept_agent.py instantiates ChatOpenAI at import time (same pattern as
# structure_agent.py), which requires a non-empty api_key even though every test
# here mocks agents.concept_agent.llm directly and never makes a real call.
os.environ.setdefault("LLM_API_KEY", "test-key-for-unit-tests")

from agents.concept_agent import (
    ConceptExtractionResult,
    ConceptIdentificationError,
    ConceptOut,
    _filter_teaching_blocks,
    _format_teaching_blocks,
    identify_concepts,
)


def _block(text: str, text_level: int | None = None, block_type: str = "text") -> dict:
    return {"text": text, "text_level": text_level, "type": block_type}


def _page(page_number: int, *blocks: dict) -> dict:
    return {"page_number": page_number, "blocks": list(blocks)}


def test_keeps_headings_and_body_text():
    pages = [
        _page(
            17,
            _block("Translations", text_level=1),
            _block("A translation shifts a graph without changing its shape."),
        )
    ]
    kept = _filter_teaching_blocks(pages)
    assert [b["text"] for _, b in kept] == [
        "Translations",
        "A translation shifts a graph without changing its shape.",
    ]


def test_stops_at_first_practice_tier_heading_across_pages():
    pages = [
        _page(20, _block("Key Ideas", text_level=1), _block("Summary of translations.")),
        _page(21, _block("Practise", text_level=1), _block("1. Solve for x.")),
        _page(22, _block("More practice text that must not appear.")),
    ]
    kept = _filter_teaching_blocks(pages)
    assert [b["text"] for _, b in kept] == ["Key Ideas", "Summary of translations."]


def test_drops_noise_types():
    pages = [
        _page(
            5,
            _block("Chapter 3", block_type="header"),
            _block("Real explanatory content."),
            _block("42", block_type="page_number"),
        )
    ]
    kept = _filter_teaching_blocks(pages)
    assert [b["text"] for _, b in kept] == ["Real explanatory content."]


def test_all_practice_tier_input_yields_nothing():
    pages = [_page(21, _block("Apply", text_level=1), _block("1. Do the thing."))]
    assert _filter_teaching_blocks(pages) == []


def test_format_teaching_blocks_annotates_headings_and_pages():
    pages = [_page(17, _block("Translations", text_level=1), _block("Body text."))]
    kept = _filter_teaching_blocks(pages)
    rendered = _format_teaching_blocks(kept)
    assert "--- PAGE 17 ---" in rendered
    assert "[HEADING level=1] Translations" in rendered
    assert "Body text." in rendered


def test_identify_concepts_returns_empty_without_llm_call_when_no_teaching_content():
    pages = [_page(21, _block("Practise", text_level=1), _block("1. Solve for x."))]
    with patch("agents.concept_agent.llm") as mock_llm:
        result = identify_concepts("Chapter 3", "3.1 Translations", pages, 21, 21)
    assert result == []
    mock_llm.with_structured_output.assert_not_called()


def test_identify_concepts_sanitizes_and_dedupes():
    pages = [_page(17, _block("Translations", text_level=1), _block("Body text."))]
    response = ConceptExtractionResult(
        concepts=[
            ConceptOut(
                slug="Horizontal & Vertical Translations!",
                canonical_name="Horizontal and Vertical Translations",
                local_name="Translations",
                description="Shifting a graph.",
            ),
            ConceptOut(
                slug="horizontal & vertical translations",
                canonical_name="Duplicate",
                local_name="Duplicate",
                description="",
            ),
        ]
    )
    with patch("agents.concept_agent.llm") as mock_llm:
        mock_llm.with_structured_output.return_value.invoke.return_value = response
        rows = identify_concepts("Chapter 3", "3.1 Translations", pages, 17, 17)

    assert len(rows) == 1
    assert rows[0]["slug"] == "horizontal-vertical-translations"
    assert rows[0]["canonical_name"] == "Horizontal and Vertical Translations"
    assert rows[0]["ordinal"] == 0


def test_identify_concepts_raises_on_llm_failure_never_silently_empty():
    pages = [_page(17, _block("Translations", text_level=1), _block("Body text."))]
    with patch("agents.concept_agent.llm") as mock_llm:
        mock_llm.with_structured_output.return_value.invoke.side_effect = RuntimeError("boom")
        try:
            identify_concepts("Chapter 3", "3.1 Translations", pages, 17, 17)
            assert False, "expected ConceptIdentificationError"
        except ConceptIdentificationError:
            pass
