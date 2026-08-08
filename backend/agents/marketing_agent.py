import os
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from typing import TypedDict
from db.models import LessonPlan

llm = ChatOpenAI(model="gpt-4o", api_key=os.getenv("LLM_API_KEY", ""))


class MarketingState(TypedDict):
    plan: dict
    copy: str


def generate_copy(state: MarketingState) -> MarketingState:
    plan = state["plan"]
    prompt = f"""You are a marketing copywriter for a math tutoring service. Based on this lesson plan, write a compelling, parent/student-facing course description for advertising.

Topic: {plan['topic']}
Grade Level: {plan['grade_level']}
Duration: {plan['duration_min']} minutes
Objectives: {plan['objectives']}

The description should:
- Be 150-250 words
- Highlight what students will learn and be able to do
- Use encouraging, accessible language (no jargon)
- Include a brief outline of the session
- End with a call to action

Return ONLY the marketing description text, no formatting markers."""

    response = llm.invoke(prompt)
    content = response.content
    if isinstance(content, list):
        content = content[0].get("text", "") if content else ""
    state["copy"] = str(content).strip()
    return state


graph = StateGraph(MarketingState)
graph.add_node("generate", generate_copy)
graph.add_edge(START, "generate")
graph.add_edge("generate", END)
marketing_graph = graph.compile()


async def run_marketing(plan: LessonPlan) -> str:
    result = marketing_graph.invoke({"plan": plan.model_dump(mode="json"), "copy": ""})
    return result["copy"]
