import os
import json
import base64
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from typing import TypedDict
from db.models import ExtractRequest, Problem

llm = ChatOpenAI(model="gpt-4o", api_key=os.getenv("LLM_API_KEY", ""))


class ExtractorState(TypedDict):
    file_content_b64: str
    filename: str
    request: dict
    problems: list[dict]


def extract_problems(state: ExtractorState) -> ExtractorState:
    req = state["request"]
    page_note = ""
    if req.get("start_page") or req.get("end_page"):
        page_note = f"\nFocus on pages {req.get('start_page', 'start')} to {req.get('end_page', 'end')}."

    solution_note = "\nExtract solutions/answers if present." if req.get("extract_solutions") else ""
    tag_note = "\nAuto-tag each problem with topic, difficulty (easy/medium/hard), and grade level." if req.get("auto_tag") else ""

    prompt = f"""You are a math problem extractor. Analyze the provided document and extract all math problems you can find.{page_note}{solution_note}{tag_note}

For each problem found, return:
- body: the problem text (preserve mathematical notation)
- solution: the solution if available, otherwise empty string
- topic: the math topic (e.g., "Algebra", "Calculus", "Geometry")
- difficulty: easy, medium, or hard
- grade_level: estimated grade level (e.g., "grade-9", "calc-1")

The document is: {state['filename']}
Document content (base64): {state['file_content_b64'][:500]}...

Return a JSON array of problem objects.
Return ONLY the JSON array, no markdown formatting."""

    response = llm.invoke(prompt)
    content = response.content
    if isinstance(content, list):
        content = content[0].get("text", "") if content else ""
    text = str(content).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    try:
        state["problems"] = json.loads(text)
    except json.JSONDecodeError:
        state["problems"] = []
    return state


graph = StateGraph(ExtractorState)
graph.add_node("extract", extract_problems)
graph.add_edge(START, "extract")
graph.add_edge("extract", END)
extractor_graph = graph.compile()


async def run_extractor(file_content: bytes, filename: str, req: ExtractRequest) -> list[Problem]:
    b64 = base64.b64encode(file_content).decode()
    result = extractor_graph.invoke({
        "file_content_b64": b64,
        "filename": filename,
        "request": req.model_dump(),
        "problems": [],
    })
    problems = []
    for p in result["problems"]:
        problems.append(Problem(
            source=f"extracted ({filename})",
            topic=p.get("topic", "Unknown"),
            grade_level=p.get("grade_level", "unknown"),
            difficulty=p.get("difficulty", "medium"),
            body=p.get("body", ""),
            solution=p.get("solution", ""),
        ))
    return problems
