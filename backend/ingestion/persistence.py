"""Writing extracted pages to Supabase (ARCHITECTURE.md sections 16-17).

Kept apart from pdf_extraction so that extraction stays importable and testable
without a database, credentials, or a network. db.client builds its Supabase
client at import time, so that import happens inside the functions here rather
than at module level -- importing this module is always safe.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Iterable, Protocol

# Supabase rejects very large request bodies; pages carrying full layout JSON add up.
DEFAULT_BATCH_SIZE = 25

# Private bucket (20260905120000_problem_images.sql) -- no public access, no anon-key
# read policy. The only way to see an image is a signed URL minted on request (see
# create_signed_image_url), which is what makes "private" actually mean something
# here rather than just being a label on an otherwise-public bucket.
IMAGE_BUCKET = "textbook-images"


class _RowConvertible(Protocol):
    """write_pages takes pdf_extraction.PageExtraction (line-shaped, the synchronous
    /ingestion/extract path) or mineru_extraction.PageExtraction (block-shaped, the
    background /textbooks path) -- either works, since both just need to_row().
    """

    def to_row(self, source_id: str) -> dict[str, Any]: ...


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
    pages: Iterable[_RowConvertible],
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


def write_sections(chapter_id: str, sections: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Upsert sections for one chapter. Returns the written rows, including ids.

    Upsert on (chapter_id, ordinal) -- sections_chapter_ordinal_key
    (20260817120000_phase1_sections_chapter_ordinal_unique.sql). content is never
    set here: it stays null until the later section-decomposition stage
    (ARCHITECTURE.md section 8), which this pipeline does not implement.

    Returns rows (not a count) because link_pages_to_section needs each
    section's id and page range to attach textbook_pages rows to it.
    """
    client = _client()
    rows = [{**section, "chapter_id": chapter_id} for section in sections]
    if not rows:
        return []
    result = client.table("sections").upsert(rows, on_conflict="chapter_id,ordinal").execute()
    return result.data or []


def write_content_blocks(section_id: str, blocks: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Upsert content blocks for one section. Returns the written rows.

    Upsert on (section_id, ordinal) -- content_blocks_section_id_ordinal_key
    (20260822120100_content_extraction_unique_keys.sql) -- same idempotent-rerun
    pattern as write_chapters/write_sections.
    """
    client = _client()
    rows = [{**block, "section_id": section_id} for block in blocks]
    if not rows:
        return []
    result = client.table("content_blocks").upsert(rows, on_conflict="section_id,ordinal").execute()
    return result.data or []


def write_problems(
    textbook_id: str, chapter_id: str | None, section_id: str | None, problems: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Upsert problems for one section. Returns the written rows.

    Upsert on (textbook_id, page_number, problem_number) --
    problems_textbook_page_number_key -- not (section_id, ordinal): section_id is
    nullable (ARCHITECTURE.md section 19), so it cannot anchor a dedupe key.
    """
    client = _client()
    rows = [
        {**problem, "textbook_id": textbook_id, "chapter_id": chapter_id, "section_id": section_id}
        for problem in problems
    ]
    if not rows:
        return []
    result = (
        client.table("problems")
        .upsert(rows, on_conflict="textbook_id,page_number,problem_number")
        .execute()
    )
    return result.data or []


def write_worked_examples(
    textbook_id: str, chapter_id: str | None, section_id: str | None, examples: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Upsert worked examples for one section. Returns the written rows.

    Upsert on (textbook_id, page_number, example_number) --
    worked_examples_textbook_page_number_key -- mirrors write_problems.
    """
    client = _client()
    rows = [
        {**example, "textbook_id": textbook_id, "chapter_id": chapter_id, "section_id": section_id}
        for example in examples
    ]
    if not rows:
        return []
    result = (
        client.table("worked_examples")
        .upsert(rows, on_conflict="textbook_id,page_number,example_number")
        .execute()
    )
    return result.data or []


def write_problem_images(
    textbook_id: str, problem_id: str, images: Iterable[tuple[int, Any]]
) -> list[dict[str, Any]]:
    """Upload each figure's captured bytes to the private textbook-images bucket and
    upsert its problem_images row. Returns the written rows.

    `images` is (page_number, mineru_extraction.ImageBlock) pairs -- kept untyped
    (Any) here the same way write_pages avoids importing pdf_extraction/
    mineru_extraction at module level (module docstring): this module stays
    importable without either extraction stage.

    Upsert on (problem_id, ordinal) -- problem_images_problem_id_ordinal_key
    (20260905120000_problem_images.sql) -- same idempotent-rerun pattern as every
    other write_* here: re-running extraction over the same pages replaces a
    problem's images instead of duplicating them. An image with no captured bytes
    (mineru_extraction couldn't find the file MinerU recorded) is skipped rather
    than writing a row that points at nothing in storage.
    """
    client = _client()
    rows: list[dict[str, Any]] = []

    for ordinal, (page_number, image) in enumerate(images):
        if not image.image_bytes:
            continue
        suffix = Path(image.img_path).suffix if image.img_path else ""
        storage_path = f"{textbook_id}/{problem_id}/{ordinal}{suffix or '.jpg'}"
        content_type = mimetypes.guess_type(storage_path)[0] or "image/jpeg"

        client.storage.from_(IMAGE_BUCKET).upload(
            storage_path,
            image.image_bytes,
            {"content-type": content_type, "upsert": "true"},
        )
        rows.append(
            {
                "problem_id": problem_id,
                "ordinal": ordinal,
                "storage_path": storage_path,
                "caption": image.caption,
                "source_ref": {
                    "page_number": page_number,
                    "block_ordinal_on_page": image.ordinal,
                    "bbox": list(image.bbox) if image.bbox else None,
                },
            }
        )

    if not rows:
        return []
    result = (
        client.table("problem_images")
        .upsert(rows, on_conflict="problem_id,ordinal")
        .execute()
    )
    return result.data or []


def create_signed_image_url(storage_path: str, expires_in: int = 3600) -> str | None:
    """Mint a temporary signed URL for a private-bucket image. The bucket has no
    public access (module docstring), so a bare storage_path is useless to a
    browser -- display always goes through this. expires_in defaults to 1 hour;
    callers needing a longer-lived link can pass a larger value. Returns None if
    Supabase reports no URL (e.g. the object was deleted out from under the row).
    """
    client = _client()
    result = client.storage.from_(IMAGE_BUCKET).create_signed_url(storage_path, expires_in)
    return result.get("signedURL") or result.get("signedUrl")


def link_pages_to_section(
    source_id: str, section_id: str, page_start: int | None, page_end: int | None
) -> int:
    """Point every already-extracted page in [page_start, page_end] at section_id.

    write_pages always runs before this (pdf_extraction precedes structure in
    background.py), so the target rows already exist -- this only ever
    updates, never inserts.
    """
    if page_start is None or page_end is None:
        return 0
    client = _client()
    result = (
        client.table("textbook_pages")
        .update({"section_id": section_id})
        .eq("source_id", source_id)
        .gte("page_number", page_start)
        .lte("page_number", page_end)
        .execute()
    )
    return len(result.data or [])
