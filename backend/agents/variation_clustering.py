"""Variation clustering (ARCHITECTURE.md section 10.2 / IMPLEMENTATION-PLAN.md Step 4c).

Concept identification (concept_agent.py, section 9) and raw problem extraction
(ingestion/problem_extraction.py, section 10.1) are independent branches. This module
is where they meet: given one section's already-identified concepts and its raw
problem list, group the problems first by which concept they test, then by variation
within that concept, and choose one representative problem per variation.

This is a judgment stage (section 4.1), in the same category as concept
identification -- its output is a draft, not a published taxonomy (section 10.2's
"Relationship to Phase 2"), and a call failure must never silently degrade to an
empty list, the same discipline concept_agent.ConceptIdentificationError enforces.

Only representative problems are reported here. Non-representative problems are not
tagged at this stage (section 10.2) -- the caller (background.py) never writes a
problem_concepts row for a problem this module didn't name as a representative.
"""

from __future__ import annotations

import os
import re
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("LLM_API_KEY", ""))

_VARIATION_KEY_RE = re.compile(r"[^a-z0-9]+")


class VariationOut(BaseModel):
    variation_key: str
    representative_problem_number: str
    member_problem_numbers: list[str] = []
    confidence: float = 0.5


class ConceptGroupingOut(BaseModel):
    concept_slug: str
    variations: list[VariationOut] = []


class VariationClusteringResult(BaseModel):
    groupings: list[ConceptGroupingOut] = []


class VariationClusteringError(Exception):
    """Raised on an LLM call error or a malformed response.

    Zero groupings from a well-formed response is not itself an error -- a section's
    problems can legitimately fail to cluster under any of its concepts. But a call
    failure must never silently degrade to an empty list.
    """


def _slugify(text: str) -> str:
    return _VARIATION_KEY_RE.sub("-", text.strip().lower()).strip("-")


def _format_concepts(concepts: list[dict[str, Any]]) -> str:
    lines = []
    for concept in concepts:
        local_name = concept.get("local_name") or concept.get("canonical_name")
        lines.append(f"- slug: {concept['slug']} | canonical: {concept['canonical_name']} | this textbook calls it: {local_name}")
    return "\n".join(lines)


def _format_problems(problems: list[dict[str, Any]]) -> str:
    lines = []
    for problem in problems:
        body = (problem.get("body_plain") or "").strip().replace("\n", " ")
        lines.append(f"{problem['problem_number']}. {body}")
    return "\n".join(lines)


def cluster_variations(
    chapter_title: str,
    section_title: str,
    concepts: list[dict[str, Any]],
    problems: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group one section's raw problems by concept, then by variation, choosing one
    representative problem per variation.

    concepts: this section's already-identified concepts, [{"slug", "canonical_name",
    "local_name"}, ...] (concept_agent.identify_concepts' row shape, or
    persistence.get_section_concepts' read-back shape).

    problems: this section's already-extracted raw problems, [{"problem_number",
    "body_plain"}, ...] (ingestion.problem_extraction.extract_problems' row shape, or
    persistence.get_section_problems' read-back shape).

    Returns one dict per variation: {"concept_slug", "variation_key",
    "representative_problem_number", "member_problem_numbers", "confidence"}. This is
    the full grouping (for a future ground-truth diff against
    fixtures/golden_chapter.json, per IMPLEMENTATION-PLAN.md Step 4c) -- the caller
    decides which fields become a problem_concepts row. Never returns a non-empty
    list on a call failure -- raises VariationClusteringError instead.
    """
    if not concepts or not problems:
        return []

    prompt = f"""You are grouping a math textbook section's exercise problems by which concept
each one tests, and then by which structural variation of that concept it represents.

Chapter: {chapter_title}
Section: {section_title}

This section teaches the following concept(s):
{_format_concepts(concepts)}

Here are the section's exercise problems, in printed order:
{_format_problems(problems)}

For each concept, group its problems into variations -- distinct structural forms of
the same skill (e.g. "solving with a fraction coefficient" vs. "solving with the
variable on both sides"). Problems in the same variation should require the same
solution procedure; a problem that merely looks different on the surface (different
numbers, different letters) but needs the same steps belongs in the same variation
as one that looks similar but needs different steps.

A problem may belong to more than one concept (report it under each). A problem that
does not clearly test any of the listed concepts should simply not appear in any
grouping.

For each variation, report:
- variation_key: a stable, kebab-case label unique within this concept (e.g. "fraction-coefficient")
- representative_problem_number: the one problem number from this variation that best represents it (prefer a self-contained, unambiguous example)
- member_problem_numbers: every problem number (including the representative) you placed in this variation
- confidence: 0.0-1.0, how confident you are in BOTH the variation boundary and the representative choice -- use a lower value for an ambiguous boundary or an uncertain grouping, never default to a high value out of convenience

Only report a concept_slug from the list above, exactly as printed. Only report
problem numbers that actually appear above."""

    try:
        structured_llm = llm.with_structured_output(VariationClusteringResult)
        result = structured_llm.invoke(prompt)
    except Exception as error:
        raise VariationClusteringError(f"LLM call failed: {error}") from error

    if not isinstance(result, VariationClusteringResult):
        raise VariationClusteringError("LLM returned an unexpected response shape")

    known_slugs = {concept["slug"] for concept in concepts}
    known_numbers = {problem["problem_number"] for problem in problems}

    rows: list[dict[str, Any]] = []
    for grouping in result.groupings:
        if grouping.concept_slug not in known_slugs:
            continue

        seen_keys: set[str] = set()
        for variation in grouping.variations:
            key = _slugify(variation.variation_key)
            if not key or key in seen_keys:
                continue
            if variation.representative_problem_number not in known_numbers:
                continue

            members = [n for n in variation.member_problem_numbers if n in known_numbers]
            if variation.representative_problem_number not in members:
                members.append(variation.representative_problem_number)

            seen_keys.add(key)
            rows.append(
                {
                    "concept_slug": grouping.concept_slug,
                    "variation_key": key,
                    "representative_problem_number": variation.representative_problem_number,
                    "member_problem_numbers": members,
                    "confidence": max(0.0, min(1.0, variation.confidence)),
                }
            )

    return rows
