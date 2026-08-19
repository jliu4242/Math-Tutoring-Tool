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

from agents.structure_agent import StructureIdentificationError, identify_structure
from ingestion import pdf_extraction, persistence


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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

        if persistence.pages_already_extracted(source_id, start_page, end_page):
            page_rows = persistence.read_pages(source_id, start_page, end_page)
            progress["pdf_extraction"] = {"status": "skipped", "reason": "already extracted"}
        else:
            pages = list(pdf_extraction.extract_pages(pdf_path, start_page, end_page))
            persistence.write_pages(source_id, pages)
            page_rows = [{"page_number": p.page_number, "raw_text": p.raw_text} for p in pages]
            progress["pdf_extraction"] = {"status": "done", "pages_written": len(pages)}

        persistence.set_run_status(run_id, current_stage="structure", progress=progress)

        if persistence.structure_already_exists(textbook_id, start_page, end_page):
            progress["structure"] = {
                "status": "skipped",
                "reason": "overlapping structure already exists",
            }
        else:
            try:
                chapters = identify_structure(title, page_rows, start_page, end_page)
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
                sections_written += persistence.write_sections(chapter_id, section_dicts)

            progress["structure"] = {
                "status": "done",
                "chapters_written": len(written_chapters),
                "sections_written": sections_written,
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
