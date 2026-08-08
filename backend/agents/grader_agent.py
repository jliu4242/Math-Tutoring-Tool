import os
import json
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from typing import TypedDict
from db.models import GradeRequest, GradingSession, Problem

llm = ChatOpenAI(model="gpt-4o", api_key=os.getenv("LLM_API_KEY", ""))


class GraderState(TypedDict):
    problem: dict
    student_work: str
    student_label: str
    diagnosis: dict


def diagnose(state: GraderState) -> GraderState:
    problem = state["problem"]
    prompt = f"""You are a diagnostic math grader. Analyze the student's work step-by-step. Do NOT just give a score — identify specific errors and misconceptions.

PROBLEM:
{problem['body']}

CORRECT SOLUTION:
{problem['solution']}

STUDENT'S WORK:
{state['student_work']}

Analyze each step the student took. For each step, determine if it's correct or has an error.

Return a JSON object with:
- score: points earned out of total (e.g., "1/3")
- total_steps: number of steps analyzed
- error_type: primary error category (one of: "Sign", "Arithmetic", "Conceptual", "Procedural", "Setup", "None")
- confidence: your confidence as a percentage (e.g., 98.5)
- steps: array of objects with:
  - step_number: int
  - description: what this step does (e.g., "Setup", "Substitution", "Simplification")
  - work: what the student wrote
  - correct: boolean
  - error_detail: explanation of the error if incorrect, empty string if correct
- feedback: 2-3 sentences of constructive feedback for the student
- remedial_topics: array of topic strings the student should review

Return ONLY the JSON object, no markdown formatting."""

    response = llm.invoke(prompt)
    content = response.content
    if isinstance(content, list):
        content = content[0].get("text", "") if content else ""
    text = str(content).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    try:
        state["diagnosis"] = json.loads(text)
    except json.JSONDecodeError:
        state["diagnosis"] = {"error": "Failed to parse diagnosis", "raw": text}
    return state


graph = StateGraph(GraderState)
graph.add_node("diagnose", diagnose)
graph.add_edge(START, "diagnose")
graph.add_edge("diagnose", END)
grader_graph = graph.compile()


async def run_grader(problem: Problem, req: GradeRequest) -> GradingSession:
    result = grader_graph.invoke({
        "problem": problem.model_dump(mode="json"),
        "student_work": req.work_input,
        "student_label": req.student_label,
        "diagnosis": {},
    })
    return GradingSession(
        problem_id=req.problem_id,
        student_label=req.student_label,
        work_input=req.work_input,
        diagnosis=result["diagnosis"],
    )
