"""Verification for worked_example_extraction.py's example/solution splitting, in
particular that "Your Turn" follow-up prompts are dropped rather than folded into the
example's solution (fixtures/golden_chapter.json convention, 2026-11-15).
"""

from __future__ import annotations

from ingestion.mineru_extraction import Block
from ingestion.worked_example_extraction import extract_worked_examples


def _heading(text: str, level: int = 2) -> Block:
    return Block(ordinal=0, type="text", text=text, text_level=level)


def _text(text: str) -> Block:
    return Block(ordinal=0, type="text", text=text)


def test_your_turn_is_excluded_from_solution():
    rows = extract_worked_examples(
        [
            (18, _heading("Example 1")),
            (18, _heading("Graph Translations")),
            (18, _text("a) Graph y = |x - 4| + 3.")),
            (18, _heading("Solution")),
            (18, _text("Translate 4 right and 3 up.")),
            (19, _heading("Your Turn")),
            (19, _text("Graph y = |x + 2| - 1.")),
            (19, _heading("Example 2")),
            (19, _text("Determine the equation.")),
            (19, _heading("Solution")),
            (19, _text("y = f(x - 2).")),
            (20, _heading("Your Turn")),
            (20, _heading("Did You Know?")),
            (20, _text("Another your-turn line.")),
            (20, _heading("Key Ideas")),
            (20, _text("Key ideas prose.")),
        ]
    )

    assert [row["example_number"] for row in rows] == ["1", "2"]
    assert rows[0]["solution_text"] == "Translate 4 right and 3 up."
    assert rows[1]["solution_text"] == "y = f(x - 2)."
    assert "Graph Translations" in rows[0]["problem_text"]
    for row in rows:
        assert "your-turn" not in (row["solution_text"] or "")
        assert "|x + 2|" not in (row["solution_text"] or "")
        assert "Did You Know" not in row["problem_text"]


def test_example_without_your_turn_keeps_full_solution():
    rows = extract_worked_examples(
        [
            (18, _heading("Example 1")),
            (18, _text("Solve it.")),
            (18, _heading("Solution")),
            (18, _text("Step one.")),
            (18, _text("Step two.")),
            (18, _heading("Apply")),
            (18, _text("1. Not part of the example.")),
        ]
    )

    assert rows[0]["solution_text"] == "Step one.\nStep two."
