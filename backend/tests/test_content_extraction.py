"""Verification that content_extraction.py does not save "Your Turn" follow-up
exercises as content_blocks rows (2026-11-15 product decision; see
fixtures/golden_chapter.json annotation notes)."""

from __future__ import annotations

from ingestion.content_extraction import extract_content_blocks
from ingestion.mineru_extraction import Block


def _heading(text: str, level: int = 2) -> Block:
    return Block(ordinal=0, type="text", text=text, text_level=level)


def _text(text: str) -> Block:
    return Block(ordinal=0, type="text", text=text)


def test_your_turn_content_is_not_saved():
    rows = extract_content_blocks(
        [
            (18, _heading("Example 1")),
            (18, _text("Graph y = |x - 4| + 3.")),
            (18, _heading("Solution")),
            (18, _text("Translate 4 right and 3 up.")),
            (19, _heading("Your Turn")),
            (19, _text("Graph y = |x + 2| - 1.")),
            (19, _heading("Did You Know?")),
            (19, _text("Still inside Your Turn.")),
            (19, _heading("Example 2")),
            (19, _text("Determine the equation.")),
            (20, _heading("Your Turn")),
            (20, _text("Second your-turn prompt.")),
            (20, _heading("Key Ideas")),
            (20, _text("Key ideas prose.")),
            (21, _heading("Apply")),
            (21, _text("1. An exercise.")),
        ]
    )

    contents = [row["content"] for row in rows]
    assert contents == [
        "Graph y = |x - 4| + 3.",
        "Translate 4 right and 3 up.",
        "Determine the equation.",
        "Key ideas prose.",
    ]
    assert [row["ordinal"] for row in rows] == [0, 1, 2, 3]
