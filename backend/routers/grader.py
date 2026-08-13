from fastapi import APIRouter
from db.models import GradeRequest, GradingSession, Problem
from db.client import supabase
from agents.grader_agent import run_grader

router = APIRouter(prefix="/grade", tags=["grader"])


@router.post("", response_model=GradingSession)
async def grade_submission(req: GradeRequest):
    problem_result = supabase.table("generated_problems").select("*").eq("id", req.problem_id).single().execute()
    problem = Problem(**problem_result.data)
    session = await run_grader(problem, req)
    supabase.table("grading_sessions").insert(session.model_dump(mode="json")).execute()
    return session


@router.get("/{session_id}", response_model=GradingSession)
async def get_session(session_id: str):
    result = supabase.table("grading_sessions").select("*").eq("id", session_id).single().execute()
    return GradingSession(**result.data)
