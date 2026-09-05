"""Problem images -- the read side of problem_images (ARCHITECTURE.md section 6, 19).

textbook-images is a private Supabase Storage bucket (20260905120000_problem_images.sql):
nothing in it is reachable from a bare storage_path. A client that wants to actually
display a problem's figures needs a signed URL minted for it, which is all this
router does -- it never touches problem text/content, and it is not the ingestion
write path (that's ingestion.background/persistence).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ingestion.persistence import create_signed_image_url

router = APIRouter(prefix="/problems", tags=["problems"])

# 1 hour: long enough for a single tutoring session to load a problem's figures
# without needing to re-mint, short enough that a leaked link doesn't stay live.
SIGNED_URL_EXPIRES_IN = 3600


class ProblemImage(BaseModel):
    id: str
    ordinal: int
    caption: Optional[str] = None
    signed_url: Optional[str] = None


@router.get("/{problem_id}/images", response_model=list[ProblemImage])
async def get_problem_images(problem_id: str) -> list[ProblemImage]:
    from db.client import supabase

    result = (
        supabase.table("problem_images")
        .select("id, ordinal, caption, storage_path")
        .eq("problem_id", problem_id)
        .order("ordinal")
        .execute()
    )

    return [
        ProblemImage(
            id=row["id"],
            ordinal=row["ordinal"],
            caption=row.get("caption"),
            signed_url=create_signed_image_url(row["storage_path"], SIGNED_URL_EXPIRES_IN),
        )
        for row in (result.data or [])
    ]
