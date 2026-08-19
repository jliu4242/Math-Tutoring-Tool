"""Chapter/section structure identification (ARCHITECTURE.md section 7).

"The AI can identify: Textbook -> Chapter -> Section -> ..." -- this stage's job is
only the hierarchy and page ranges, not decomposing a section into explanations,
examples, or problems (section 8) and not identifying concepts (section 9). Both
are separate, later, out-of-scope stages.

Two things extractor_agent.py gets wrong that this module deliberately does not
repeat: it sends only the first 500 characters of a *base64-encoded* file as "the
document" (not real content), and it silently degrades to an empty result on a
JSON parse failure instead of surfacing the failure to its caller.

Model is gpt-4o-mini, not gpt-4o: boundary-finding from headings and page breaks is
closer to pattern recognition than deep reasoning, and mini is ~17x cheaper on
input tokens, which is what this stage is dominated by (the page text, not the
small JSON response).
"""

from __future__ import annotations

import os
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("LLM_API_KEY", ""))


class SectionOut(BaseModel):
    title: str
    ordinal: int
    page_start: int
    page_end: int


class ChapterOut(BaseModel):
    number: Optional[str] = None
    title: str
    page_start: int
    page_end: int
    ordinal: int
    sections: list[SectionOut] = []


class StructureResult(BaseModel):
    chapters: list[ChapterOut] = []


class StructureIdentificationError(Exception):
    """Raised on zero chapters, a malformed/refused response, or an LLM call error.

    Never silently degrades to an empty result -- a caller must see the failure so
    the background job can record it onto ingestion_runs rather than marking the
    run complete with nothing written.
    """


def _format_pages(pages: list[dict[str, Any]]) -> str:
    parts = []
    for page in pages:
        text = page.get("raw_text") or ""
        parts.append(f"--- PAGE {page['page_number']} ---\n{text}")
    return "\n\n".join(parts)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _sanitize(result: StructureResult, requested_start: int, requested_end: int) -> list[ChapterOut]:
    """Never trust the model's raw output: clamp ranges, drop invalid entries, and
    reassign ordinals ourselves. The (textbook_id, ordinal) / (chapter_id, ordinal)
    unique constraints are keyed on ordinal -- a model-supplied duplicate would
    silently overwrite one chapter/section with another's data on upsert, so
    ordinals here are always derived from sorted, clamped output, never trusted.
    """
    clamped_chapters: list[ChapterOut] = []

    for chapter in result.chapters:
        if chapter.page_start > chapter.page_end:
            continue
        if not chapter.title.strip():
            continue

        chapter_start = _clamp(chapter.page_start, requested_start, requested_end)
        chapter_end = _clamp(chapter.page_end, requested_start, requested_end)
        if chapter_start > chapter_end:
            continue

        clamped_sections: list[SectionOut] = []
        for section in chapter.sections:
            if section.page_start > section.page_end:
                continue
            if not section.title.strip():
                continue
            section_start = _clamp(section.page_start, chapter_start, chapter_end)
            section_end = _clamp(section.page_end, chapter_start, chapter_end)
            if section_start > section_end:
                continue
            clamped_sections.append(
                section.model_copy(update={"page_start": section_start, "page_end": section_end})
            )

        clamped_sections.sort(key=lambda s: s.page_start)
        for ordinal, section in enumerate(clamped_sections):
            clamped_sections[ordinal] = section.model_copy(update={"ordinal": ordinal})

        clamped_chapters.append(
            chapter.model_copy(
                update={
                    "page_start": chapter_start,
                    "page_end": chapter_end,
                    "sections": clamped_sections,
                }
            )
        )

    clamped_chapters.sort(key=lambda c: c.page_start)
    for ordinal, chapter in enumerate(clamped_chapters):
        clamped_chapters[ordinal] = chapter.model_copy(update={"ordinal": ordinal})

    return clamped_chapters


def identify_structure(
    textbook_title: str,
    pages: list[dict[str, Any]],
    requested_start: int,
    requested_end: int,
) -> list[ChapterOut]:
    """Identify chapter/section boundaries within [requested_start, requested_end].

    pages: [{"page_number": int, "raw_text": str | None}, ...], already extracted.
    Raises StructureIdentificationError on any failure -- an LLM error, a refusal,
    or a response with zero chapters. Never returns an empty list silently.
    """
    prompt = f"""You are identifying the chapter/section structure of a math textbook titled "{textbook_title}".

Below is the raw extracted text for pages {requested_start} to {requested_end}. Identify:
- Each chapter that appears in this range: its printed number (if any), title, the page range it spans, and its sections.
- Each section within a chapter: its title and the page range it spans. A subsection heading like "3.2.1" is either its own section (if it has its own exercise set) or should be folded into its parent section (e.g. "3.2") -- do not invent a separate section for every minor heading.

Only report structure you can actually see evidence for in the text below. Page numbers you report must fall within {requested_start}-{requested_end}.

{_format_pages(pages)}"""

    try:
        structured_llm = llm.with_structured_output(StructureResult)
        result = structured_llm.invoke(prompt)
    except Exception as error:
        raise StructureIdentificationError(f"LLM call failed: {error}") from error

    if not isinstance(result, StructureResult):
        raise StructureIdentificationError("LLM returned an unexpected response shape")

    chapters = _sanitize(result, requested_start, requested_end)
    if not chapters:
        raise StructureIdentificationError("no valid chapters identified in the requested range")

    return chapters
