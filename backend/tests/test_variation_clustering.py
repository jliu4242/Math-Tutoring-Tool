"""Unit tests for variation_clustering.py (ARCHITECTURE.md section 10.2 /
IMPLEMENTATION-PLAN.md Step 4c). cluster_variations' LLM call is mocked; these test
the sanitization discipline -- unknown slugs/numbers dropped, duplicate variation
keys within a concept deduped, confidence clamped -- the same way
test_concept_extraction.py tests identify_concepts' sanitization.
"""

from __future__ import annotations

import os
from unittest.mock import patch

# variation_clustering.py instantiates ChatOpenAI at import time (same pattern as
# concept_agent.py/structure_agent.py), which requires a non-empty api_key even
# though every test here mocks agents.variation_clustering.llm directly.
os.environ.setdefault("LLM_API_KEY", "test-key-for-unit-tests")

from agents.variation_clustering import (
    ConceptGroupingOut,
    VariationClusteringError,
    VariationClusteringResult,
    VariationOut,
    cluster_variations,
)

CONCEPTS = [{"slug": "solving-linear-equations", "canonical_name": "Solving Linear Equations", "local_name": "Linear Equations"}]
PROBLEMS = [
    {"problem_number": "1", "body_plain": "Solve 3x + 7 = 19."},
    {"problem_number": "2", "body_plain": "Solve 5x - 2 = 13."},
    {"problem_number": "3", "body_plain": "Solve (x/2) + 1 = 4."},
]


def _response(*groupings: ConceptGroupingOut) -> VariationClusteringResult:
    return VariationClusteringResult(groupings=list(groupings))


def test_returns_empty_without_llm_call_when_no_problems():
    with patch("agents.variation_clustering.llm") as mock_llm:
        result = cluster_variations("Chapter 3", "3.2 Linear Equations", CONCEPTS, [])
    assert result == []
    mock_llm.with_structured_output.assert_not_called()


def test_returns_empty_without_llm_call_when_no_concepts():
    with patch("agents.variation_clustering.llm") as mock_llm:
        result = cluster_variations("Chapter 3", "3.2 Linear Equations", [], PROBLEMS)
    assert result == []
    mock_llm.with_structured_output.assert_not_called()


def test_basic_grouping_passes_through():
    response = _response(
        ConceptGroupingOut(
            concept_slug="solving-linear-equations",
            variations=[
                VariationOut(
                    variation_key="whole-number-coefficient",
                    representative_problem_number="1",
                    member_problem_numbers=["1", "2"],
                    confidence=0.9,
                ),
                VariationOut(
                    variation_key="fraction-coefficient",
                    representative_problem_number="3",
                    member_problem_numbers=["3"],
                    confidence=0.6,
                ),
            ],
        )
    )
    with patch("agents.variation_clustering.llm") as mock_llm:
        mock_llm.with_structured_output.return_value.invoke.return_value = response
        rows = cluster_variations("Chapter 3", "3.2 Linear Equations", CONCEPTS, PROBLEMS)

    assert len(rows) == 2
    assert rows[0]["concept_slug"] == "solving-linear-equations"
    assert rows[0]["variation_key"] == "whole-number-coefficient"
    assert rows[0]["representative_problem_number"] == "1"
    assert rows[0]["member_problem_numbers"] == ["1", "2"]
    assert rows[1]["representative_problem_number"] == "3"


def test_drops_grouping_for_unknown_concept_slug():
    response = _response(
        ConceptGroupingOut(
            concept_slug="not-a-real-concept",
            variations=[VariationOut(variation_key="v1", representative_problem_number="1", confidence=0.9)],
        )
    )
    with patch("agents.variation_clustering.llm") as mock_llm:
        mock_llm.with_structured_output.return_value.invoke.return_value = response
        rows = cluster_variations("Chapter 3", "3.2 Linear Equations", CONCEPTS, PROBLEMS)
    assert rows == []


def test_drops_variation_with_unknown_representative_number():
    response = _response(
        ConceptGroupingOut(
            concept_slug="solving-linear-equations",
            variations=[
                VariationOut(variation_key="v1", representative_problem_number="99", confidence=0.9)
            ],
        )
    )
    with patch("agents.variation_clustering.llm") as mock_llm:
        mock_llm.with_structured_output.return_value.invoke.return_value = response
        rows = cluster_variations("Chapter 3", "3.2 Linear Equations", CONCEPTS, PROBLEMS)
    assert rows == []


def test_dedupes_duplicate_variation_keys_within_a_concept():
    response = _response(
        ConceptGroupingOut(
            concept_slug="solving-linear-equations",
            variations=[
                VariationOut(variation_key="Whole Number!", representative_problem_number="1", confidence=0.9),
                VariationOut(variation_key="whole number", representative_problem_number="2", confidence=0.8),
            ],
        )
    )
    with patch("agents.variation_clustering.llm") as mock_llm:
        mock_llm.with_structured_output.return_value.invoke.return_value = response
        rows = cluster_variations("Chapter 3", "3.2 Linear Equations", CONCEPTS, PROBLEMS)

    assert len(rows) == 1
    assert rows[0]["variation_key"] == "whole-number"
    assert rows[0]["representative_problem_number"] == "1"


def test_member_numbers_filtered_to_known_and_representative_always_included():
    response = _response(
        ConceptGroupingOut(
            concept_slug="solving-linear-equations",
            variations=[
                VariationOut(
                    variation_key="v1",
                    representative_problem_number="1",
                    member_problem_numbers=["1", "2", "does-not-exist"],
                    confidence=0.9,
                )
            ],
        )
    )
    with patch("agents.variation_clustering.llm") as mock_llm:
        mock_llm.with_structured_output.return_value.invoke.return_value = response
        rows = cluster_variations("Chapter 3", "3.2 Linear Equations", CONCEPTS, PROBLEMS)

    assert rows[0]["member_problem_numbers"] == ["1", "2"]


def test_confidence_is_clamped_to_zero_one():
    response = _response(
        ConceptGroupingOut(
            concept_slug="solving-linear-equations",
            variations=[
                VariationOut(variation_key="v1", representative_problem_number="1", confidence=1.5),
                VariationOut(variation_key="v2", representative_problem_number="2", confidence=-0.2),
            ],
        )
    )
    with patch("agents.variation_clustering.llm") as mock_llm:
        mock_llm.with_structured_output.return_value.invoke.return_value = response
        rows = cluster_variations("Chapter 3", "3.2 Linear Equations", CONCEPTS, PROBLEMS)

    assert rows[0]["confidence"] == 1.0
    assert rows[1]["confidence"] == 0.0


def test_raises_on_llm_failure_never_silently_empty():
    with patch("agents.variation_clustering.llm") as mock_llm:
        mock_llm.with_structured_output.return_value.invoke.side_effect = RuntimeError("boom")
        try:
            cluster_variations("Chapter 3", "3.2 Linear Equations", CONCEPTS, PROBLEMS)
            assert False, "expected VariationClusteringError"
        except VariationClusteringError:
            pass
