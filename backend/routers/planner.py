from fastapi import APIRouter
from db.models import LessonPlanCreate, LessonPlan, MarketingRequest
from db.client import supabase
from agents.planner_agent import run_planner
from agents.marketing_agent import run_marketing

router = APIRouter(prefix="/plan", tags=["planner"])


@router.post("", response_model=LessonPlan)
async def create_plan(req: LessonPlanCreate):
    plan = await run_planner(req)
    supabase.table("lesson_plans").insert(plan.model_dump(mode="json")).execute()
    return plan


@router.get("/{plan_id}", response_model=LessonPlan)
async def get_plan(plan_id: str):
    result = supabase.table("lesson_plans").select("*").eq("id", plan_id).single().execute()
    return LessonPlan(**result.data)


@router.get("", response_model=list[LessonPlan])
async def list_plans():
    result = supabase.table("lesson_plans").select("*").order("created_at", desc=True).execute()
    return [LessonPlan(**r) for r in result.data]


@router.post("/marketing", response_model=LessonPlan)
async def generate_marketing(req: MarketingRequest):
    plan_result = supabase.table("lesson_plans").select("*").eq("id", req.lesson_plan_id).single().execute()
    plan = LessonPlan(**plan_result.data)
    copy = await run_marketing(plan)
    supabase.table("lesson_plans").update({"marketing_copy": copy}).eq("id", plan.id).execute()
    plan.marketing_copy = copy
    return plan
