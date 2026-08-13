from fastapi import APIRouter
from db.models import GenerateRequest, Problem
from db.client import supabase
from agents.generator_agent import run_generator

router = APIRouter(prefix="/generate", tags=["generator"])


@router.post("", response_model=list[Problem])
async def generate_problems(req: GenerateRequest):
    problems = await run_generator(req)
    for p in problems:
        supabase.table("generated_problems").insert(p.model_dump(mode="json")).execute()
    return problems
