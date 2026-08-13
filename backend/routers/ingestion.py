"""Phase 1 ingestion API.

This exposes Step 3 (PDF extraction) over HTTP so it can be driven from the UI.

Two honest caveats about where this sits in the plan:

1. It runs synchronously. ARCHITECTURE.md section 5 says upload should return
   immediately and process in the background, and IMPLEMENTATION-PLAN.md puts that
   in Step 6 along with ingestion_runs tracking. Extraction is fast enough to wait
   on for a chapter, so this endpoint blocks and returns the result -- which is what
   makes it useful for a smoke test. MAX_SYNC_PAGES keeps that honest.

2. The PDF is not uploaded to object storage. Section 16 wants the original kept as
   the immutable source; wiring a Supabase Storage bucket is Step 6 work. Until then
   storage_path records where the file came from, not somewhere it can be fetched.

Only extraction runs here. No structure identification, no problems, no concepts --
those are Steps 4 onward and have their own verification gates.
"""

from __future__ import annotations

import os
import tempfile
from collections import Counter
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ingestion.pdf_extraction import (
    PageExtraction,
    compute_sha256,
    extract_pages,
    page_count,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

# A synchronous request should not sit on a 600-page book. Past this, narrow the
# range or wait for the Step 6 background job.
MAX_SYNC_PAGES = 200
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
PREVIEW_CHARS = 800


class PageSummary(BaseModel):
    page_number: int
    status: str
    parser: Optional[str]
    char_count: int
    line_count: int
    image_count: int
    text_preview: str
    error: Optional[str] = None


class ExtractionResult(BaseModel):
    filename: str
    pdf_sha256: str
    page_count: int
    range_start: int
    range_end: int
    pages_extracted: int
    characters: int
    images: int
    status_counts: dict[str, int]
    parser_counts: dict[str, int]
    persisted: bool
    textbook_id: Optional[str] = None
    source_id: Optional[str] = None
    rows_written: int = 0
    pages: list[PageSummary]


def _summarise(page: PageExtraction) -> PageSummary:
    text = page.raw_text or ""
    return PageSummary(
        page_number=page.page_number,
        status=page.status,
        parser=page.parser,
        char_count=len(text),
        line_count=len(page.lines),
        image_count=len(page.images),
        text_preview=text[:PREVIEW_CHARS],
        error=page.error,
    )


@router.post("/extract", response_model=ExtractionResult)
async def extract_pdf(
    file: UploadFile = File(...),
    title: str = Form(...),
    start_page: Optional[int] = Form(None),
    end_page: Optional[int] = Form(None),
    persist: bool = Form(False),
    edition: Optional[str] = Form(None),
    publisher: Optional[str] = Form(None),
) -> ExtractionResult:
    """Extract a page range from an uploaded PDF, optionally writing textbook_pages.

    Page numbers are 1-based PDF indices, not the numbers printed on the page. For
    the McGraw-Hill fixture chapter that means 151-214, not 140-203.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file is {len(content) // (1024 * 1024)} MB; limit is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    # pdfplumber and pypdf both want a real path, and the fallback reopens the file.
    handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        handle.write(content)
        handle.close()

        try:
            total = page_count(handle.name)
        except Exception as error:
            raise HTTPException(
                status_code=400, detail=f"could not read this file as a PDF: {error}"
            ) from error

        first = max(1, start_page or 1)
        last = min(total, end_page or total)
        if first > last:
            raise HTTPException(
                status_code=400,
                detail=f"empty page range {first}-{last}; the PDF has {total} pages",
            )
        if last - first + 1 > MAX_SYNC_PAGES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{last - first + 1} pages requested; this endpoint extracts at most "
                    f"{MAX_SYNC_PAGES} at a time because it runs synchronously. "
                    f"Narrow the page range."
                ),
            )

        pages = list(extract_pages(handle.name, first, last))
        digest = compute_sha256(handle.name)

        result = ExtractionResult(
            filename=file.filename or "upload.pdf",
            pdf_sha256=digest,
            page_count=total,
            range_start=first,
            range_end=last,
            pages_extracted=len(pages),
            characters=sum(page.char_count for page in pages),
            images=sum(len(page.images) for page in pages),
            status_counts=dict(Counter(page.status for page in pages)),
            parser_counts=dict(Counter(page.parser or "none" for page in pages)),
            persisted=False,
            pages=[_summarise(page) for page in pages],
        )

        if persist:
            # Imported here so extraction still works when Supabase is unconfigured.
            from ingestion.persistence import ensure_source, ensure_textbook, write_pages

            try:
                textbook_id = ensure_textbook(title, edition=edition, publisher=publisher)
                source_id = ensure_source(
                    textbook_id=textbook_id,
                    file_hash=digest,
                    storage_path=f"upload://{file.filename or 'upload.pdf'}",
                    page_count=total,
                )
                result.rows_written = write_pages(source_id, pages)
            except Exception as error:
                raise HTTPException(
                    status_code=502, detail=f"extraction succeeded but the database write failed: {error}"
                ) from error

            result.persisted = True
            result.textbook_id = textbook_id
            result.source_id = source_id

        return result
    finally:
        os.unlink(handle.name)


@router.get("/sources/{source_id}/pages")
async def list_persisted_pages(source_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Read back what was stored, so the UI can prove the rows actually landed."""
    from db.client import supabase

    result = (
        supabase.table("textbook_pages")
        .select("page_number, extraction_status, parser, raw_text")
        .eq("source_id", source_id)
        .order("page_number")
        .limit(limit)
        .execute()
    )

    return [
        {
            "page_number": row["page_number"],
            "extraction_status": row["extraction_status"],
            "parser": row["parser"],
            "char_count": len(row.get("raw_text") or ""),
            "text_preview": (row.get("raw_text") or "")[:PREVIEW_CHARS],
        }
        for row in (result.data or [])
    ]
