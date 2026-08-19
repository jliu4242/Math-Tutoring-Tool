"""Save a textbook (ARCHITECTURE.md section 5 -- "Step 1 -- Upload").

POST /textbooks stores the PDF, computes a hash, creates a textbook + ingestion_runs
record, and returns immediately -- the actual work (page extraction, then chapter/
section identification) runs in the background via ingestion.background. This is
deliberately separate from POST /ingestion/extract, which stays as the synchronous
smoke-test endpoint it already documents itself as being, and from POST /extract
(the LLM flat-problem-extraction flow), which this endpoint never calls or touches.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ingestion.background import run_textbook_ingestion
from ingestion.pdf_extraction import compute_sha256, page_count
from ingestion.persistence import create_ingestion_run, ensure_source, ensure_textbook
from routers.ingestion import MAX_UPLOAD_BYTES

router = APIRouter(prefix="/textbooks", tags=["textbooks"])

# A single Save Textbook request also feeds one structure-identification LLM call
# over the whole range. 200 pages (not the 1000 a purely mechanical parse could
# tolerate) keeps that call comfortably inside context-window and cost budget --
# see agents/structure_agent.py for the model choice this is sized around.
MAX_BACKGROUND_PAGES = 200
MAX_TITLE_LENGTH = 300
MAX_METADATA_LENGTH = 100

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_UNSAFE_FILENAME_CHARS = re.compile(r"[^\w.\- ]")


class SaveTextbookResponse(BaseModel):
    textbook_id: str
    source_id: str
    run_id: str
    status: str
    message: str


class IngestionRunStatus(BaseModel):
    id: str
    textbook_id: str
    status: str
    current_stage: str
    progress: dict[str, Any]
    error: Optional[str] = None


def _sanitize_text(value: Optional[str], max_len: int) -> Optional[str]:
    if value is None:
        return None
    cleaned = _CONTROL_CHARS.sub("", value).strip()
    if not cleaned:
        return None
    return cleaned[:max_len]


def _safe_filename(name: str) -> str:
    base = Path(name).name  # strips any directory components
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", base).strip()
    return (cleaned or "upload.pdf")[:200]


@router.post("", response_model=SaveTextbookResponse, status_code=202)
async def save_textbook(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    start_page: Optional[int] = Form(None),
    end_page: Optional[int] = Form(None),
    edition: Optional[str] = Form(None),
    publisher: Optional[str] = Form(None),
) -> SaveTextbookResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file is {len(content) // (1024 * 1024)} MB; limit is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    if content[:5] != b"%PDF-":
        raise HTTPException(status_code=400, detail="not a valid PDF")

    clean_title = _sanitize_text(title, MAX_TITLE_LENGTH)
    if not clean_title:
        raise HTTPException(status_code=400, detail="title is required")
    clean_edition = _sanitize_text(edition, MAX_METADATA_LENGTH)
    clean_publisher = _sanitize_text(publisher, MAX_METADATA_LENGTH)

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
        if last - first + 1 > MAX_BACKGROUND_PAGES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{last - first + 1} pages requested; a single save is capped at "
                    f"{MAX_BACKGROUND_PAGES} pages so the structure-identification LLM "
                    f"call stays inside a sane context/cost budget. Narrow the page range."
                ),
            )

        digest = compute_sha256(handle.name)
        safe_name = _safe_filename(file.filename or "upload.pdf")

        try:
            textbook_id = ensure_textbook(clean_title, edition=clean_edition, publisher=clean_publisher)
            source_id = ensure_source(
                textbook_id=textbook_id,
                file_hash=digest,
                storage_path=f"upload://{safe_name}",
                page_count=total,
            )
            run_id = create_ingestion_run(textbook_id)
        except Exception as error:
            raise HTTPException(
                status_code=502, detail=f"could not create textbook/source/run records: {error}"
            ) from error
    except Exception:
        os.unlink(handle.name)
        raise

    # The background task owns this temp file from here on -- it deletes it itself
    # once the job finishes. Do NOT delete it here: BackgroundTasks runs after this
    # function returns, so an unlink in a `finally` on this request would remove the
    # file out from under the job before it ever reads it.
    background_tasks.add_task(
        run_textbook_ingestion,
        handle.name,
        clean_title,
        first,
        last,
        run_id,
        textbook_id,
        source_id,
    )

    return SaveTextbookResponse(
        textbook_id=textbook_id,
        source_id=source_id,
        run_id=run_id,
        status="queued",
        message=f"saving pages {first}-{last} in the background",
    )


@router.get("/runs/{run_id}", response_model=IngestionRunStatus)
async def get_ingestion_run(run_id: str) -> IngestionRunStatus:
    from db.client import supabase

    result = supabase.table("ingestion_runs").select("*").eq("id", run_id).limit(1).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="ingestion run not found")
    return IngestionRunStatus(**result.data[0])
