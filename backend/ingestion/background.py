"""Background orchestration for POST /textbooks (ARCHITECTURE.md section 5).

The BackgroundTasks target scheduled by the router. Runs mineru_extraction (mechanical,
MinerU-backed), then structure (LLM-based), then content_extraction/problem_extraction
(mechanical, MinerU-typed-block-based), updating ingestion_runs between stages so the
UI can poll progress instead of the job being a black box.

Content/problem/worked-example extraction only run when structure was actually
identified *this* call -- when structure_already_exists short-circuits the structure
stage, everything downstream of it is skipped too, matching how the pre-MinerU version
of this module already treated a structure-skip as terminal for that call. Re-deriving
content/problems against pre-existing structure from an earlier run is not something
this pipeline does; it would need to read sections back from persistence rather than
use the ones just written, and is out of scope for this swap.

A content_extraction/problem_extraction failure, after structure already succeeded,
still flips the whole run to status="failed" -- a run without problems is not "ready"
for what this project is actually for, so ingestion_runs.status=completed keeps
meaning what a caller polling /textbooks/runs/{run_id} would expect it to mean.

Deliberately a plain `def`, not `async def`: Starlette runs sync BackgroundTasks
callables via run_in_threadpool and awaits async ones directly. mineru_extraction
shells out to a subprocess and blocks on it; write_pages and the Supabase client are
all blocking calls too -- an `async def` here would block the single event loop for
the whole job, silently defeating "non-blocking" under load.
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
from ingestion import content_extraction, mineru_extraction, persistence, problem_extraction, worked_example_extraction
from ingestion.mineru_extraction import Block, PageExtraction

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


def _page_rows_with_blocks(pages: list[PageExtraction]) -> list[dict[str, Any]]:
    return [
        {
            "page_number": page.page_number,
            "raw_text": page.raw_text,
            "blocks": [block.to_json() for block in page.blocks],
        }
        for page in pages
    ]


def _section_page_blocks(
    pages: list[PageExtraction], page_start: int | None, page_end: int | None
) -> list[tuple[int, Block]]:
    """Flatten every kept block from pages [page_start, page_end] into one
    (page_number, Block) stream in reading order, for the extraction modules that
    operate on a single section's content rather than a whole page range.
    """
    if page_start is None or page_end is None:
        return []
    result: list[tuple[int, Block]] = []
    for page in pages:
        if page_start <= page.page_number <= page_end:
            result.extend((page.page_number, block) for block in page.blocks)
    return result


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

        skip_structure = persistence.structure_already_exists(textbook_id, start_page, end_page)

        # One MinerU pass covers everything this call needs -- the officially
        # requested range, plus (when structure will actually run) a little padding
        # on either side for chapter-boundary context. MinerU pays real
        # model-load/inference cost per invocation, so this call is never split into
        # separate extractions for "the chapter" vs. "the context pages" the way the
        # pre-MinerU pdfplumber version could afford to.
        if skip_structure:
            extract_start, extract_end = start_page, end_page
        else:
            try:
                total_pages = mineru_extraction.page_count(pdf_path)
            except Exception:
                total_pages = end_page  # no boundary-context beyond the requested range
            extract_start = max(1, start_page - CONTEXT_PAGES)
            extract_end = min(total_pages, end_page + CONTEXT_PAGES)

        # Always re-extract and overwrite: write_pages upserts on (source_id,
        # page_number), so a page already saved from an earlier run is simply
        # replaced rather than skipped.
        all_pages = list(mineru_extraction.extract_pages(pdf_path, extract_start, extract_end))
        requested_pages = [p for p in all_pages if start_page <= p.page_number <= end_page]

        persistence.write_pages(source_id, requested_pages)
        progress["pdf_extraction"] = {"status": "done", "pages_written": len(requested_pages)}

        persistence.set_run_status(run_id, current_stage="structure", progress=progress)

        if skip_structure:
            progress["structure"] = {
                "status": "skipped",
                "reason": "overlapping structure already exists",
            }
        else:
            page_rows = _page_rows_with_blocks(requested_pages)
            context_before = _page_rows_with_blocks(
                [p for p in all_pages if p.page_number < start_page]
            )
            context_after = _page_rows_with_blocks(
                [p for p in all_pages if p.page_number > end_page]
            )

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
            content_blocks_written = 0
            problems_written = 0
            worked_examples_written = 0

            try:
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

                        section_blocks = _section_page_blocks(
                            requested_pages, section_row.get("page_start"), section_row.get("page_end")
                        )

                        content_rows = content_extraction.extract_content_blocks(section_blocks)
                        written_content = persistence.write_content_blocks(section_row["id"], content_rows)
                        content_blocks_written += len(written_content)

                        problem_rows = problem_extraction.extract_problems(section_blocks)
                        written_problems = persistence.write_problems(
                            textbook_id, chapter_id, section_row["id"], problem_rows
                        )
                        problems_written += len(written_problems)

                        example_rows = worked_example_extraction.extract_worked_examples(section_blocks)
                        written_examples = persistence.write_worked_examples(
                            textbook_id, chapter_id, section_row["id"], example_rows
                        )
                        worked_examples_written += len(written_examples)
            except Exception as error:
                progress["structure"] = {
                    "status": "done",
                    "chapters_written": len(written_chapters),
                    "sections_written": sections_written,
                    "pages_linked": pages_linked,
                }
                persistence.set_run_status(
                    run_id,
                    status="failed",
                    error=f"content/problem extraction failed: {error}",
                    progress=progress,
                )
                return

            progress["structure"] = {
                "status": "done",
                "chapters_written": len(written_chapters),
                "sections_written": sections_written,
                "pages_linked": pages_linked,
            }
            persistence.set_run_status(run_id, current_stage="content_extraction", progress=progress)
            progress["content_extraction"] = {"status": "done", "content_blocks_written": content_blocks_written}
            persistence.set_run_status(run_id, current_stage="problem_extraction", progress=progress)
            progress["problem_extraction"] = {
                "status": "done",
                "problems_written": problems_written,
                "worked_examples_written": worked_examples_written,
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
