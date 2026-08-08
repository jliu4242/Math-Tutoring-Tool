import os
import json
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from typing import TypedDict
from db.models import LessonPlanCreate, LessonPlan

llm = ChatOpenAI(model="gpt-4o", api_key=os.getenv("LLM_API_KEY", ""))


class PlannerState(TypedDict):
    request: dict
    plan: dict


def generate_plan(state: PlannerState) -> PlannerState:
    req = state["request"]
    prompt = f"""You are an expert math curriculum designer. Create a detailed lesson plan.

Topic: {req['topic']}
Grade Level: {req['grade_level']}
Duration: {req['duration_min']} minutes

Return a JSON object with these keys:
- objectives: 2-3 specific, measurable learning objectives
- warm_up: A 5-minute warm-up activity related to the topic
- explanation: Main teaching content with key concepts explained step-by-step
- examples: 2-3 worked examples with full solutions
- practice: 4-5 practice problems of varying difficulty
- assessment: A brief exit-ticket style assessment (1-2 problems)

Return ONLY the JSON object, no markdown formatting."""

    response = llm.invoke(prompt)
    content = response.content
    if isinstance(content, list):
        content = content[0].get("text", "") if content else ""
    text = str(content).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    plan_data = json.loads(text)
    state["plan"] = plan_data
    return state


graph = StateGraph(PlannerState)
graph.add_node("generate", generate_plan)
graph.add_edge(START, "generate")
graph.add_edge("generate", END)
planner_graph = graph.compile()


async def run_planner(req: LessonPlanCreate) -> LessonPlan:
    result = planner_graph.invoke({"request": req.model_dump(), "plan": {}})
    plan_data = result["plan"]
    return LessonPlan(
        topic=req.topic,
        grade_level=req.grade_level,
        duration_min=req.duration_min,
        objectives=plan_data.get("objectives", ""),
        warm_up=plan_data.get("warm_up", ""),
        explanation=plan_data.get("explanation", ""),
        examples=plan_data.get("examples", ""),
        practice=plan_data.get("practice", ""),
        assessment=plan_data.get("assessment", ""),
    )
