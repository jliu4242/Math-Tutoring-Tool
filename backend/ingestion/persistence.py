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
