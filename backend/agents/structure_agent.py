"""Chapter/section structure identification (ARCHITECTURE.md section 7).

"The AI can identify: Textbook -> Chapter -> Section -> ..." -- this stage's job is
only the hierarchy and page ranges, not decomposing a section into explanations,
examples, or problems (section 8) and not identifying concepts (section 9). Both
are separate, later, out-of-scope stages.

Two things extractor_agent.py gets wrong that this module deliberately does not
repeat: it sends only the first 500 characters of a *base64-encoded* file as "the
document" (not real content), and it silently degrades to an empty result on a
JSON parse failure instead of surfacing the failure to its caller.

Save Textbook only accepts whole chapters (ARCHITECTURE.md section 5 discussion):
a range that is really just a section, or that starts/ends mid-chapter, must be
rejected rather than silently saved as a fake chapter. Judging that needs two
things the caller supplies here that plain body text does not carry:

  - heading size (pdf_extraction.py's TextLine.size) so a chapter-level heading can
    be told apart from a section heading by more than wording alone -- see
    _format_page_lines.
  - a few pages of context immediately outside the requested range, so the model
    can check whether the range actually starts/ends at a chapter transition
    instead of guessing from the requested pages alone, which look the same
    whether they're a whole chapter or a fragment of one.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("LLM_API_KEY", ""))

# A line whose font size is at least this much larger than the page's most common
# (body-text) size reads as a heading rather than body text. 1.15 tolerates minor
# rendering noise (e.g. bold variants of the body font reporting a slightly
# different size) while still catching a genuinely larger heading.
HEADING_SIZE_MARGIN = 1.15


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
    is_valid_chapter_range: bool = True
    reason: str = ""
    chapters: list[ChapterOut] = []


class StructureIdentificationError(Exception):
    """Raised on zero chapters, a malformed/refused response, or an LLM call error.

    Never silently degrades to an empty result -- a caller must see the failure so
    the background job can record it onto ingestion_runs rather than marking the
    run complete with nothing written.
    """


class ChapterValidationError(Exception):
    """Raised when the requested range is not one or more complete chapters --
    e.g. it is only a section, or it starts or ends partway through a chapter.

    Kept distinct from StructureIdentificationError so a caller can show the user
    a specific, actionable message ("this isn't a chapter") instead of a generic
    processing failure.
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _body_size(sizes: list[float]) -> float:
    """The most common line size on a page -- a stand-in for "body text size"."""
    counts: dict[float, int] = {}
    for size in sizes:
        counts[size] = counts.get(size, 0) + 1
    return max(counts, key=lambda size: counts[size]) if counts else 0.0


def _format_page_lines(page: dict[str, Any]) -> str:
    """Render a page's text, flagging lines whose font size stands out from the
    page's body text as probable headings. Falls back to plain raw_text when no
    line/size data is available (e.g. rows persisted before this field existed).
    """
    lines = page.get("lines") or None
    if not lines:
        return page.get("raw_text") or ""

    body_size = _body_size([line["size"] for line in lines if line.get("size")])
    threshold = body_size * HEADING_SIZE_MARGIN

    rendered = []
    for line in lines:
        text = line.get("text", "")
        size = line.get("size") or 0.0
        if body_size and size >= threshold:
            rendered.append(f"[HEADING size={size:.1f}] {text}")
        else:
            rendered.append(text)
    return "\n".join(rendered)


def _format_pages(pages: list[dict[str, Any]]) -> str:
    parts = [f"--- PAGE {page['page_number']} ---\n{_format_page_lines(page)}" for page in pages]
    return "\n\n".join(parts)


def _format_context_pages(pages: list[dict[str, Any]], label: str) -> str:
    if not pages:
        return f"(no {label} context -- the requested range touches the edge of the PDF)"
    parts = [
        f"--- {label.upper()} CONTEXT PAGE {page['page_number']} (outside the requested range) ---\n"
        f"{_format_page_lines(page)}"
        for page in pages
    ]
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
    context_before: list[dict[str, Any]] | None = None,
    context_after: list[dict[str, Any]] | None = None,
) -> list[ChapterOut]:
    """Identify chapter/section boundaries within [requested_start, requested_end].

    pages: [{"page_number": int, "raw_text": str | None, "lines": [{"text": str,
    "size": float}, ...] | None}, ...], already extracted. context_before/after are
    the same shape, covering a few pages immediately outside the requested range --
    context only, never reported as structure.

    Raises ChapterValidationError if the range is not one or more complete
    chapters (e.g. it's only a section, or starts/ends mid-chapter).
    Raises StructureIdentificationError on any other failure -- an LLM error, a
    refusal, or a response with zero chapters despite being marked valid. Never
    returns an empty list silently.
    """
    prompt = f"""You are identifying the chapter/section structure of a math textbook titled "{textbook_title}".

Save Textbook only accepts COMPLETE chapters. Before reporting any structure, decide:
is_valid_chapter_range = true only if the requested range (pages {requested_start}-{requested_end})
starts exactly where a chapter begins and ends exactly where that chapter (or the last
of several consecutive chapters) ends. Set it to false, with a one-sentence "reason", if:
  - the range covers only a single section or a subsection of a chapter (no chapter-level
    heading appears in it at all), or
  - the range starts partway through a chapter (the BEFORE CONTEXT below shows the same
    chapter continuing right up to the start of the range, with no chapter heading in between), or
  - the range ends partway through a chapter (the AFTER CONTEXT below shows the same
    chapter continuing right after the range, with no new chapter heading in between).

Lines are marked "[HEADING size=N]" when their font is noticeably larger than the page's
body text -- chapter titles are reliably the single largest heading size in a chapter;
section titles are consistently smaller. Use this, not just wording, to tell a chapter
heading apart from a section heading (a heading need not literally contain the word
"Chapter" to be one).

If is_valid_chapter_range is true, identify for the requested range only:
- Each chapter that appears in this range: its printed number (if any), title, the page range it spans, and its sections.
- Each section within a chapter: its title and the page range it spans. A subsection heading like "3.2.1" is either its own section (if it has its own exercise set) or should be folded into its parent section (e.g. "3.2") -- do not invent a separate section for every minor heading.

Only report structure you can actually see evidence for in the text below. Page numbers you report must fall within {requested_start}-{requested_end}. Never report structure for the context pages -- they exist only so you can judge the chapter boundary.

{_format_context_pages(context_before or [], "before")}

--- REQUESTED RANGE (pages {requested_start}-{requested_end}) ---

{_format_pages(pages)}

{_format_context_pages(context_after or [], "after")}"""

    try:
        structured_llm = llm.with_structured_output(StructureResult)
        result = structured_llm.invoke(prompt)
    except Exception as error:
        raise StructureIdentificationError(f"LLM call failed: {error}") from error

    if not isinstance(result, StructureResult):
        raise StructureIdentificationError("LLM returned an unexpected response shape")

    if not result.is_valid_chapter_range:
        raise ChapterValidationError(
            result.reason or "the requested page range does not correspond to one or more complete chapters"
        )

    chapters = _sanitize(result, requested_start, requested_end)
    if not chapters:
        raise StructureIdentificationError("no valid chapters identified in the requested range")

    return chapters
