from fastapi import APIRouter
from db.models import Problem, ProblemCreate, ProblemFilter
from db.client import supabase

router = APIRouter(prefix="/problems", tags=["bank"])


@router.get("", response_model=list[Problem])
async def list_problems(
    topic: str | None = None,
    grade_level: str | None = None,
    difficulty: str | None = None,
    source: str | None = None,
    search: str | None = None,
):
    query = supabase.table("problems").select("*")
    if topic:
        query = query.eq("topic", topic)
    if grade_level:
        query = query.eq("grade_level", grade_level)
    if difficulty:
        query = query.eq("difficulty", difficulty)
    if source:
        query = query.eq("source", source)
    if search:
        query = query.ilike("body", f"%{search}%")
    result = query.order("created_at", desc=True).execute()
    return [Problem(**r) for r in result.data]


@router.post("", response_model=Problem)
async def create_problem(req: ProblemCreate):
    problem = Problem(**req.model_dump())
    supabase.table("problems").insert(problem.model_dump(mode="json")).execute()
    return problem


@router.get("/{problem_id}", response_model=Problem)
async def get_problem(problem_id: str):
    result = supabase.table("problems").select("*").eq("id", problem_id).single().execute()
    return Problem(**result.data)


@router.put("/{problem_id}", response_model=Problem)
async def update_problem(problem_id: str, req: ProblemCreate):
    supabase.table("problems").update(req.model_dump(mode="json")).eq("id", problem_id).execute()
    result = supabase.table("problems").select("*").eq("id", problem_id).single().execute()
    return Problem(**result.data)


@router.delete("/{problem_id}")
async def delete_problem(problem_id: str):
    supabase.table("problems").delete().eq("id", problem_id).execute()
    return {"deleted": True}
