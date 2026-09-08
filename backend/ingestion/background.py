"""Background orchestration for POST /textbooks (ARCHITECTURE.md section 5).

The BackgroundTasks target scheduled by the router. Runs mineru_extraction (mechanical,
MinerU-backed), then structure (LLM-based), then per section: concept_extraction
(LLM-based, independent of the other two -- see run_concept_extraction_for_section),
content_extraction/problem_extraction (mechanical, MinerU-typed-block-based), then
variation_clustering (LLM-based, depends on both concept_extraction and
problem_extraction having already run for that section -- see
run_variation_clustering_for_section), updating ingestion_runs between stages so the
UI can poll progress instead of the job being a black box.

Content/problem/worked-example/variation-clustering extraction only run when
structure was actually identified *this* call -- when structure_already_exists
short-circuits the structure stage, everything downstream of it is skipped too,
matching how the pre-MinerU version of this module already treated a structure-skip
as terminal for that call. Re-deriving content/problems against pre-existing
structure from an earlier run is not something this pipeline does; it would need to
read sections back from persistence rather than use the ones just written, and is out
of scope for this swap.

A content_extraction/problem_extraction/variation_clustering failure, after structure
already succeeded, still flips the whole run to status="failed" -- a run without
problems is not "ready" for what this project is actually for, so
ingestion_runs.status=completed keeps meaning what a caller polling
/textbooks/runs/{run_id} would expect it to mean.

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

from agents.concept_agent import identify_concepts
from agents.structure_agent import (
    ChapterValidationError,
    StructureIdentificationError,
    identify_structure,
)
from agents.variation_clustering import cluster_variations
from ingestion import content_extraction, mineru_extraction, persistence, problem_extraction, worked_example_extraction
from ingestion.mineru_extraction import Block, ImageBlock, PageExtraction

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


def _section_page_items(
    pages: list[PageExtraction], page_start: int | None, page_end: int | None
) -> list[tuple[int, Block | ImageBlock]]:
    """Like _section_page_blocks, but also interleaves each page's images back in at
    their real reading-order position (Block/ImageBlock.page_position) rather than
    grouping all of a page's images after all of its blocks. problem_extraction needs
    that real interleaving to tell which problem a figure visually falls under --
    dropping images here (as _section_page_blocks does) or appending them after every
    block would make every figure look like it came after the whole page's text.
    """
    if page_start is None or page_end is None:
        return []
    result: list[tuple[int, Block | ImageBlock]] = []
    for page in pages:
        if page_start <= page.page_number <= page_end:
            items: list[Block | ImageBlock] = [*page.blocks, *page.images]
            items.sort(key=lambda item: item.page_position if item.page_position is not None else -1)
            result.extend((page.page_number, item) for item in items)
    return result


def run_concept_extraction_for_section(section_id: str) -> list[dict[str, Any]]:
    """Identify and persist concepts for one section, given only its id.

    Self-contained: reads the section/chapter title and this section's
    already-extracted pages straight from Supabase (persistence.link_pages_to_section
    must have already run so textbook_pages.section_id is set) rather than depending
    on this module's in-memory extraction state. That makes it independently callable
    -- a future POST /sections/{id}/concepts route, or a backfill script -- without
    re-running ingestion, not just a step wired into this one pipeline's loop.
    """
    section = persistence.get_section_with_chapter(section_id)
    pages = persistence.get_section_pages(section_id)
    concept_rows = identify_concepts(
        chapter_title=section["chapter_title"],
        section_title=section["title"],
        pages=pages,
        page_start=section.get("page_start"),
        page_end=section.get("page_end"),
    )
    return persistence.write_section_concepts(section_id, concept_rows)


def run_variation_clustering_for_section(section_id: str) -> list[dict[str, Any]]:
    """Cluster and persist draft problem_concepts tagging for one section, given only
    its id (ARCHITECTURE.md section 10.2 / IMPLEMENTATION-PLAN.md Step 4c).

    Self-contained like run_concept_extraction_for_section: reads this section's
    already-written concepts and problems straight from Supabase (concept_extraction
    and problem_extraction must have already run for this section) rather than
    depending on this module's in-memory extraction state. Requires both -- an empty
    result if either hasn't run yet, since variation_clustering.cluster_variations
    itself no-ops when either input is empty.
    """
    section = persistence.get_section_with_chapter(section_id)
    concepts = persistence.get_section_concepts(section_id)
    problems = persistence.get_section_problems(section_id)

    groupings = cluster_variations(
        chapter_title=section["chapter_title"],
        section_title=section["title"],
        concepts=concepts,
        problems=problems,
    )

    concept_id_by_slug = {c["slug"]: c["concept_id"] for c in concepts}
    problem_id_by_number = {p["problem_number"]: p["id"] for p in problems}

    rows: list[dict[str, Any]] = []
    for grouping in groupings:
        concept_id = concept_id_by_slug.get(grouping["concept_slug"])
        problem_id = problem_id_by_number.get(grouping["representative_problem_number"])
        if concept_id is None or problem_id is None:
            continue
        rows.append(
            {
                "problem_id": problem_id,
                "concept_id": concept_id,
                "relationship_type": "primary",
                "confidence": grouping["confidence"],
                "variation_key": grouping["variation_key"],
                "is_representative": True,
            }
        )

    problem_ids = [p["id"] for p in problems]
    return persistence.write_problem_concepts(problem_ids, rows)


def run_textbook_ingestion(
    pdf_path: str,
    title: str,
    start_page: int,
    end_page: int,
    run_id: str,
    textbook_id: str,
    source_id: str,
    force_reindex: bool = False,
) -> None:
    """Never raises: an exception escaping a BackgroundTasks callback is not
    surfaced to the client and may only show up as a log line, so every failure
    path here writes onto ingestion_runs instead.

    force_reindex bypasses structure_already_exists' overlap check -- the only way
    to re-run content/problem/worked-example/problem_image/variation_clustering
    extraction over a chapter that was already structured by an earlier call (see
    this module's docstring: that stage is skipped entirely otherwise). Meant for "I
    fixed a bug in one of those extraction stages, now re-derive this chapter's
    downstream rows" -- it still
    re-runs structure identification (another LLM call), not just the mechanical
    stages, since chapters/sections have to exist again to attach anything to.
    """
    progress: dict[str, Any] = {}
    try:
        persistence.set_run_status(
            run_id, status="processing", current_stage="pdf_extraction", started_at=_now()
        )

        skip_structure = not force_reindex and persistence.structure_already_exists(
            textbook_id, start_page, end_page
        )

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
            problem_images_written = 0
            concepts_written = 0
            problem_concepts_written = 0

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

                        written_concepts = run_concept_extraction_for_section(section_row["id"])
                        concepts_written += len(written_concepts)

                        section_blocks = _section_page_blocks(
                            requested_pages, section_row.get("page_start"), section_row.get("page_end")
                        )
                        section_items = _section_page_items(
                            requested_pages, section_row.get("page_start"), section_row.get("page_end")
                        )

                        content_rows = content_extraction.extract_content_blocks(section_blocks)
                        written_content = persistence.write_content_blocks(section_row["id"], content_rows)
                        content_blocks_written += len(written_content)

                        # extract_problems' rows carry a caller-only "images" key
                        # (the figures encountered while that problem was open) --
                        # popped off here, keyed by ordinal, since `problems` has no
                        # images column of its own; matched back up after the write
                        # below via each written row's own ordinal (write_problems'
                        # upsert response, not list position, since Supabase doesn't
                        # guarantee the response preserves input order).
                        problem_rows = problem_extraction.extract_problems(section_items)
                        images_by_ordinal = {row["ordinal"]: row.pop("images") for row in problem_rows}
                        written_problems = persistence.write_problems(
                            textbook_id, chapter_id, section_row["id"], problem_rows
                        )
                        problems_written += len(written_problems)

                        # Called for every problem, even one with zero images this
                        # run: write_problem_images always clears whatever was
                        # previously written for it first (its own docstring), which
                        # is what keeps a force_reindex that stops matching an image
                        # to a problem from leaving that problem's old image behind.
                        for written_problem in written_problems:
                            problem_images = images_by_ordinal.get(written_problem["ordinal"], [])
                            written_images = persistence.write_problem_images(
                                textbook_id, written_problem["id"], problem_images
                            )
                            problem_images_written += len(written_images)

                        example_rows = worked_example_extraction.extract_worked_examples(section_blocks)
                        written_examples = persistence.write_worked_examples(
                            textbook_id, chapter_id, section_row["id"], example_rows
                        )
                        worked_examples_written += len(written_examples)

                        # Requires both concepts (above) and problems (just written)
                        # for this section -- see run_variation_clustering_for_section.
                        written_problem_concepts = run_variation_clustering_for_section(
                            section_row["id"]
                        )
                        problem_concepts_written += len(written_problem_concepts)
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
                "problem_images_written": problem_images_written,
            }
            persistence.set_run_status(run_id, current_stage="concept_extraction", progress=progress)
            progress["concept_extraction"] = {"status": "done", "concepts_written": concepts_written}
            persistence.set_run_status(run_id, current_stage="variation_clustering", progress=progress)
            progress["variation_clustering"] = {
                "status": "done",
                "problem_concepts_written": problem_concepts_written,
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
