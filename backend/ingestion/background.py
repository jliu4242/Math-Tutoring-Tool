"""Background orchestration for POST /textbooks (ARCHITECTURE.md section 5).

The BackgroundTasks target scheduled by the router. Runs pdf_extraction (mechanical,
existing) then structure (new, LLM-based), updating ingestion_runs between stages so
the UI can poll progress instead of the job being a black box.

The two stages are independent outcomes: if structure fails after pdf_extraction
succeeded, the already-upserted textbook_pages rows are not touched or rolled back --
only ingestion_runs records the failure.

Deliberately a plain `def`, not `async def`: Starlette runs sync BackgroundTasks
callables via run_in_threadpool and awaits async ones directly. extract_pages,
write_pages, identify_structure and the Supabase client are all blocking calls --
an `async def` here would block the single event loop for the whole job, silently
defeating "non-blocking" under load.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from agents.structure_agent import (
    ChapterValidationError,
    StructureIdentificationError,
    identify_structure,
)
from ingestion import pdf_extraction, persistence

# Pages of surrounding text handed to the structure LLM so it can tell "this range
# starts/ends at a real chapter boundary" from "this range is a fragment of a
# chapter" -- see agents/structure_agent.py. Context only: never persisted, never
# reported as structure.
CONTEXT_PAGES = 2

# ingestion_runs.error is a single free-text column (no error_code field), so a
# rejection from ChapterValidationError is distinguished from every other failure
# by this prefix. The frontend matches on it verbatim to show a dedicated notice
# instead of the generic failure text -- keep the two in sync.
NOT_A_CHAPTER_PREFIX = "NOT_A_CHAPTER: "


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _page_rows_with_lines(pages: list[pdf_extraction.PageExtraction]) -> list[dict[str, Any]]:
    return [
        {
            "page_number": page.page_number,
            "raw_text": page.raw_text,
            "lines": [{"text": line.text, "size": line.size} for line in page.lines],
        }
        for page in pages
    ]


def _context_page_rows(pdf_path: str, first: int, last: int) -> list[dict[str, Any]]:
    """Fresh, unpersisted extraction of a small padding range for LLM context only."""
    if first > last:
        return []
    return _page_rows_with_lines(list(pdf_extraction.extract_pages(pdf_path, first, last)))


def run_textbook_ingestion(
    pdf_path: str,
    title: str,
    start_page: int,
    end_page: int,
    run_id: str,
    textbook_id: str,
    source_id: str,
) -> None:
    """Never raises: an exception escaping a BackgroundTasks callback is not
    surfaced to the client and may only show up as a log line, so every failure
    path here writes onto ingestion_runs instead.
    """
    progress: dict[str, Any] = {}
    try:
        persistence.set_run_status(
            run_id, status="processing", current_stage="pdf_extraction", started_at=_now()
        )

        # Always re-extract and overwrite: write_pages upserts on (source_id,
        # page_number), so a page already saved from an earlier run is simply
        # replaced rather than skipped.
        pages = list(pdf_extraction.extract_pages(pdf_path, start_page, end_page))
        persistence.write_pages(source_id, pages)
        page_rows = _page_rows_with_lines(pages)
        progress["pdf_extraction"] = {"status": "done", "pages_written": len(pages)}

        persistence.set_run_status(run_id, current_stage="structure", progress=progress)

        if persistence.structure_already_exists(textbook_id, start_page, end_page):
            progress["structure"] = {
                "status": "skipped",
                "reason": "overlapping structure already exists",
            }
        else:
            try:
                total_pages = pdf_extraction.page_count(pdf_path)
            except Exception:
                total_pages = end_page  # no boundary-context beyond the requested range

            context_before = _context_page_rows(pdf_path, max(1, start_page - CONTEXT_PAGES), start_page - 1)
            context_after = _context_page_rows(pdf_path, end_page + 1, min(total_pages, end_page + CONTEXT_PAGES))

            try:
                chapters = identify_structure(
                    title,
                    page_rows,
                    start_page,
                    end_page,
                    context_before=context_before,
                    context_after=context_after,
                )
            except ChapterValidationError as error:
                persistence.set_run_status(
                    run_id,
                    status="failed",
                    error=f"{NOT_A_CHAPTER_PREFIX}{error.reason}",
                    progress=progress,
                )
                return
            except StructureIdentificationError as error:
                persistence.set_run_status(
                    run_id,
                    status="failed",
                    error=f"structure identification failed: {error}",
                    progress=progress,
                )
                return

            chapter_dicts = [
                {
                    "number": chapter.number,
                    "title": chapter.title,
                    "page_start": chapter.page_start,
                    "page_end": chapter.page_end,
                    "ordinal": chapter.ordinal,
                }
                for chapter in chapters
            ]
            written_chapters = persistence.write_chapters(textbook_id, chapter_dicts)
            chapter_id_by_ordinal = {row["ordinal"]: row["id"] for row in written_chapters}

            sections_written = 0
            pages_linked = 0
            for chapter in chapters:
                chapter_id = chapter_id_by_ordinal.get(chapter.ordinal)
                if chapter_id is None:
                    continue
                section_dicts = [
                    {
                        "title": section.title,
                        "ordinal": section.ordinal,
                        "page_start": section.page_start,
                        "page_end": section.page_end,
                    }
                    for section in chapter.sections
                ]
                written_sections = persistence.write_sections(chapter_id, section_dicts)
                sections_written += len(written_sections)
                for section_row in written_sections:
                    pages_linked += persistence.link_pages_to_section(
                        source_id,
                        section_row["id"],
                        section_row.get("page_start"),
                        section_row.get("page_end"),
                    )

            progress["structure"] = {
                "status": "done",
                "chapters_written": len(written_chapters),
                "sections_written": sections_written,
                "pages_linked": pages_linked,
            }

        persistence.set_run_status(
            run_id,
            status="completed",
            current_stage="completed",
            completed_at=_now(),
            progress=progress,
        )
    except Exception as error:  # noqa: BLE001 -- must never escape a background task
        persistence.set_run_status(run_id, status="failed", error=str(error), progress=progress)
    finally:
        try:
            os.unlink(pdf_path)
        except OSError:
            pass
