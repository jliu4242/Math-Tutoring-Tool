import os
import json
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from typing import TypedDict
from db.models import GenerateRequest, Problem

llm = ChatOpenAI(model="gpt-4o", api_key=os.getenv("LLM_API_KEY", ""))


class GeneratorState(TypedDict):
    request: dict
    problems: list[dict]


def generate_problems(state: GeneratorState) -> GeneratorState:
    req = state["request"]
    style_note = ""
    if req.get("style_reference"):
        style_note = f"\nMatch the style and formatting of this reference problem:\n{req['style_reference']}"

    prompt = f"""You are a math problem author. Generate exactly {req['count']} math problems.

Topic: {req['topic']}
Grade Level: {req['grade_level']}
Difficulty: {req['difficulty']}{style_note}

For each problem, provide:
- body: the problem statement (use LaTeX notation for math like $x^2$)
- solution: complete worked solution with final answer
- subtopic: a specific subtopic tag (e.g., "Factoring", "Quadratic Formula")

Return a JSON array of objects with keys: body, solution, subtopic.
Return ONLY the JSON array, no markdown formatting."""

    response = llm.invoke(prompt)
    content = response.content
    if isinstance(content, list):
        content = content[0].get("text", "") if content else ""
    text = str(content).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    state["problems"] = json.loads(text)
    return state


graph = StateGraph(GeneratorState)
graph.add_node("generate", generate_problems)
graph.add_edge(START, "generate")
graph.add_edge("generate", END)
generator_graph = graph.compile()


async def run_generator(req: GenerateRequest) -> list[Problem]:
    result = generator_graph.invoke({"request": req.model_dump(), "problems": []})
    problems = []
    for p in result["problems"]:
        problems.append(Problem(
            source="generated",
            topic=req.topic,
            grade_level=req.grade_level,
            difficulty=req.difficulty,
            body=p.get("body", ""),
            solution=p.get("solution", ""),
        ))
    return problems
