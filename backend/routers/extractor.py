from fastapi import APIRouter, UploadFile, File, Form
from db.models import ExtractRequest, Problem
from db.client import supabase
from agents.extractor_agent import run_extractor
from typing import Optional

router = APIRouter(prefix="/extract", tags=["extractor"])


@router.post("", response_model=list[Problem])
async def extract_problems(
    file: UploadFile = File(...),
    start_page: Optional[int] = Form(None),
    end_page: Optional[int] = Form(None),
    extract_solutions: bool = Form(True),
    auto_tag: bool = Form(True),
    convert_latex: bool = Form(False),
):
    content = await file.read()
    req = ExtractRequest(
        start_page=start_page,
        end_page=end_page,
        extract_solutions=extract_solutions,
        auto_tag=auto_tag,
        convert_latex=convert_latex,
    )
    problems = await run_extractor(content, file.filename or "upload.pdf", req)
    return problems


@router.post("/approve", response_model=list[Problem])
async def approve_problems(problems: list[Problem]):
    for p in problems:
        supabase.table("generated_problems").insert(p.model_dump(mode="json")).execute()
    return problems
