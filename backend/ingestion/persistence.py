"""Writing extracted pages to Supabase (ARCHITECTURE.md sections 16-17).

Kept apart from pdf_extraction so that extraction stays importable and testable
without a database, credentials, or a network. db.client builds its Supabase
client at import time, so that import happens inside the functions here rather
than at module level -- importing this module is always safe.
"""

from __future__ import annotations

from typing import Any, Iterable

from .pdf_extraction import PageExtraction

# Supabase rejects very large request bodies; pages carrying full layout JSON add up.
DEFAULT_BATCH_SIZE = 25


def _client() -> Any:
    from db.client import supabase  # imported late: see module docstring

    return supabase


def ensure_textbook(title: str, **fields: Any) -> str:
    """Return a textbooks row id, creating one if this title is new.

    textbook_sources.textbook_id is NOT NULL, so a textbook has to exist before any
    page can be stored. Matching on title is deliberately crude -- ARCHITECTURE.md
    section 17 gives textbooks no natural key, and the real identity of an upload is
    the file hash on textbook_sources, which ensure_source already handles.
    """
    client = _client()

    existing = client.table("textbooks").select("id").eq("title", title).limit(1).execute()
    if existing.data:
        return existing.data[0]["id"]

    payload = {"title": title, **{k: v for k, v in fields.items() if v is not None}}
    created = client.table("textbooks").insert(payload).execute()
    return created.data[0]["id"]


def ensure_source(
    textbook_id: str,
    file_hash: str,
    storage_path: str,
    page_count: int,
) -> str:
    """Return the textbook_sources row id for this file, creating it if needed.

    file_hash is unique, so re-ingesting the same PDF reuses the existing source
    rather than creating a duplicate.
    """
    client = _client()

    existing = (
        client.table("textbook_sources")
        .select("id")
        .eq("file_hash", file_hash)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    created = (
        client.table("textbook_sources")
        .insert(
            {
                "textbook_id": textbook_id,
                "file_hash": file_hash,
                "storage_path": storage_path,
                "page_count": page_count,
            }
        )
        .execute()
    )
    return created.data[0]["id"]


def write_pages(
    source_id: str,
    pages: Iterable[PageExtraction],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Upsert pages into textbook_pages. Returns how many rows were written.

    Upsert on (source_id, page_number) makes re-running extraction idempotent:
    a fixed parser bug can be re-run over the same pages without first deleting
    them, and without ending up with two rows for page 151.
    """
    client = _client()
    batch: list[dict[str, Any]] = []
    written = 0

    for page in pages:
        batch.append(page.to_row(source_id))
        if len(batch) >= batch_size:
            client.table("textbook_pages").upsert(
                batch, on_conflict="source_id,page_number"
            ).execute()
            written += len(batch)
            batch = []

    if batch:
        client.table("textbook_pages").upsert(
            batch, on_conflict="source_id,page_number"
        ).execute()
        written += len(batch)

    return written


def pages_already_extracted(source_id: str, start_page: int, end_page: int) -> bool:
    """True if every page in [start_page, end_page] already has a textbook_pages row.

    Pages have a natural per-row unit (page_number), so this is an exact coverage
    check -- unlike structure_already_exists below, which can only check overlap.
    """
    client = _client()
    result = (
        client.table("textbook_pages")
        .select("page_number", count="exact")
        .eq("source_id", source_id)
        .gte("page_number", start_page)
        .lte("page_number", end_page)
        .execute()
    )
    return (result.count or 0) >= (end_page - start_page + 1)


def read_pages(source_id: str, start_page: int, end_page: int) -> list[dict[str, Any]]:
    """Read back page_number + raw_text for a range.

    Used when pdf_extraction is skipped because the range is already covered, but
    the structure stage still needs the page text to run against.
    """
    client = _client()
    result = (
        client.table("textbook_pages")
        .select("page_number, raw_text")
        .eq("source_id", source_id)
        .gte("page_number", start_page)
        .lte("page_number", end_page)
        .order("page_number")
        .execute()
    )
    return result.data or []


def structure_already_exists(textbook_id: str, page_start: int, page_end: int) -> bool:
    """True if any existing chapter for this textbook overlaps the requested range.

    This is an overlap check, not a full-coverage check: chapters don't have a
    per-page row the way textbook_pages does, so "already saved" can only mean
    "something here already exists," not "every page is accounted for." Correct
    for the common case (the same range submitted twice) but will skip rather than
    fill a gap if a later request expands an already-structured range.
    """
    client = _client()
    result = (
        client.table("chapters")
        .select("id")
        .eq("textbook_id", textbook_id)
        .lte("page_start", page_end)
        .gte("page_end", page_start)
        .limit(1)
        .execute()
    )
    return bool(result.data)


def write_chapters(textbook_id: str, chapters: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Upsert chapters for a textbook. Returns the written rows, including ids.

    Upsert on (textbook_id, ordinal) -- chapters_textbook_ordinal_key -- same
    pattern as write_pages' (source_id, page_number). Full rows come back (not a
    count) because write_sections needs each chapter's id to attach its sections.
    """
    client = _client()
    rows = [{**chapter, "textbook_id": textbook_id} for chapter in chapters]
    if not rows:
        return []
    result = client.table("chapters").upsert(rows, on_conflict="textbook_id,ordinal").execute()
    return result.data or []


def create_ingestion_run(textbook_id: str) -> str:
    """Insert an ingestion_runs row (status='queued', current_stage='upload') and
    return its id. Durable job state so the UI can poll progress (ARCHITECTURE.md
    section 25) instead of the background job being a black box.
    """
    client = _client()
    created = (
        client.table("ingestion_runs")
        .insert({"textbook_id": textbook_id, "status": "queued", "current_stage": "upload"})
        .execute()
    )
    return created.data[0]["id"]


def set_run_status(run_id: str, **fields: Any) -> None:
    """Update an ingestion_runs row. updated_at is auto-touched by a DB trigger,
    so callers only ever pass the fields that actually changed (status,
    current_stage, progress, error, started_at, completed_at).
    """
    client = _client()
    client.table("ingestion_runs").update(fields).eq("id", run_id).execute()


def write_sections(chapter_id: str, sections: Iterable[dict[str, Any]]) -> int:
    """Upsert sections for one chapter. Returns rows written.

    Upsert on (chapter_id, ordinal) -- sections_chapter_ordinal_key
    (20260817120000_phase1_sections_chapter_ordinal_unique.sql). content is never
    set here: it stays null until the later section-decomposition stage
    (ARCHITECTURE.md section 8), which this pipeline does not implement.
    """
    client = _client()
    rows = [{**section, "chapter_id": chapter_id} for section in sections]
    if not rows:
        return 0
    client.table("sections").upsert(rows, on_conflict="chapter_id,ordinal").execute()
    return len(rows)
