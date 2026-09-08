"""Concept identification (ARCHITECTURE.md section 9).

This stage's job is only "what concept(s) does this section teach," derived from
the section's own explanatory content -- not from its exercises. Concept
identification (section 9) and raw problem extraction (section 10.1) are
independent branches per section 10.2: this module never reads problem_extraction's
output, and problem_extraction never reads this module's.

Input is always a section's pages read back from persistence (textbook_pages.layout,
see mineru_extraction.PageExtraction.to_row), so -- like structure_agent.py -- this
works on plain dicts (`{"page_number": int, "blocks": [{"text":, "text_level":,
"type":}, ...]}`), not mineru_extraction.Block instances.

The persisted content_blocks table (content_extraction.py) is deliberately NOT the
input here, even though it already excludes problem/practice-tier text: it also
drops every heading (any block with text_level set), because content_extraction's
job is body prose only -- structure_agent handles headings separately. Headings
carry real concept signal here (an Example's own subtitle often names the
sub-skill), so this module re-derives its own teaching-content filter from the raw
block stream instead of consuming content_blocks.
"""

from __future__ import annotations

import os
import re
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from ingestion.mineru_extraction import NOISE_TEXT_TYPES
from ingestion.problem_extraction import is_practice_heading

llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("LLM_API_KEY", ""))


class ConceptOut(BaseModel):
    slug: str
    canonical_name: str
    local_name: str
    description: str = ""


class ConceptExtractionResult(BaseModel):
    concepts: list[ConceptOut] = []


class ConceptIdentificationError(Exception):
    """Raised on an LLM call error or a malformed response.

    Zero concepts from a well-formed response is not itself an error -- a section
    can legitimately teach no new named concept. But a call failure must never
    silently degrade to an empty list, the same discipline structure_agent.py's
    StructureIdentificationError enforces.
    """


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.strip().lower()).strip("-")


def _filter_teaching_blocks(pages: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    """Flatten a section's pages into (page_number, block) pairs in reading order,
    keeping headings and body text but stopping entirely -- not just for the rest of
    that page -- at the first practice-tier heading (Practise/Apply/Extend/Create
    Connections/Check Your Understanding). Everything from there on is exercise
    content, out of scope for this stage.
    """
    kept: list[tuple[int, dict[str, Any]]] = []
    for page in pages:
        page_number = page.get("page_number")
        for block in page.get("blocks") or []:
            block_type = block.get("type")
            text = block.get("text") or ""
            if block_type in NOISE_TEXT_TYPES or not text.strip():
                continue
            level = block.get("text_level")
            if level is not None and is_practice_heading(text):
                return kept
            kept.append((page_number, block))
    return kept


def _format_teaching_blocks(blocks: list[tuple[int, dict[str, Any]]]) -> str:
    """Render kept blocks with the same [HEADING level=N] annotation convention as
    structure_agent._format_page_blocks, grouped under page markers.
    """
    parts: list[str] = []
    current_page: int | None = None
    for page_number, block in blocks:
        if page_number != current_page:
            parts.append(f"--- PAGE {page_number} ---")
            current_page = page_number
        text = block.get("text") or ""
        level = block.get("text_level")
        parts.append(f"[HEADING level={level}] {text}" if level else text)
    return "\n".join(parts)


def identify_concepts(
    chapter_title: str,
    section_title: str,
    pages: list[dict[str, Any]],
    page_start: int | None,
    page_end: int | None,
) -> list[dict[str, Any]]:
    """Identify the concept(s) taught in one section.

    pages: this section's already-extracted pages, [{"page_number": int, "blocks":
    [{"text": str, "text_level": int | None, "type": str}, ...]}, ...].

    Returns row dicts shaped for persistence.write_section_concepts: {"slug",
    "canonical_name", "local_name", "description", "ordinal"}. Never returns a
    non-empty list on a failure -- raises ConceptIdentificationError instead.
    """
    teaching_blocks = _filter_teaching_blocks(pages)
    if not teaching_blocks:
        return []

    prompt = f"""You are identifying the mathematical concept(s) taught in one section of a textbook.

Chapter: {chapter_title}
Section: {section_title} (pages {page_start}-{page_end})

Read the explanatory content below (exercises/practice problems have already been
removed -- this is teaching content only: introductions, definitions, worked
examples, key ideas). Identify each distinct mathematical skill or sub-concept this
content teaches, at a fine enough grain to tell real variations of a technique
apart -- do not collapse the whole section into one broad umbrella concept.

A worked example's own subtitle usually names the specific skill it demonstrates.
Treat two examples as teaching the same concept only when they demonstrate the
literal same skill; examples that demonstrate different variations of a technique,
or a different kind of task entirely (e.g. performing a transformation vs.
determining the equation of an already-transformed graph), are different concepts
even under the same section heading. For instance, a section titled "Translations"
might teach four separate concepts -- "horizontal translations", "vertical
translations", "combined translations", and "determining the equation of a
translated function" -- rather than one umbrella "translations" concept. Still
avoid the opposite extreme of a new concept per sentence: only split when the
content is genuinely teaching a distinguishable skill, not merely rephrasing one.

Blocks are marked "[HEADING level=N]" when MinerU's layout model assigned them a
heading depth; increasing numbers are progressively deeper headings.

For each concept, provide:
- slug: a stable, kebab-case identifier (e.g. "horizontal-translations")
- canonical_name: a textbook-independent name for the concept
- local_name: how THIS textbook/section actually refers to it
- description: one sentence describing the concept

Only report concepts you can actually see taught in the text below.

--- SECTION CONTENT ---

{_format_teaching_blocks(teaching_blocks)}"""

    try:
        structured_llm = llm.with_structured_output(ConceptExtractionResult)
        result = structured_llm.invoke(prompt)
    except Exception as error:
        raise ConceptIdentificationError(f"LLM call failed: {error}") from error

    if not isinstance(result, ConceptExtractionResult):
        raise ConceptIdentificationError("LLM returned an unexpected response shape")

    rows: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for concept in result.concepts:
        slug = _slugify(concept.slug) or _slugify(concept.canonical_name)
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        rows.append(
            {
                "ordinal": len(rows),
                "slug": slug,
                "canonical_name": concept.canonical_name.strip(),
                "local_name": concept.local_name.strip() or concept.canonical_name.strip(),
                "description": concept.description.strip(),
            }
        )

    return rows
