"""Worked-example extraction (ARCHITECTURE.md sections 11, 11.1) -- mechanical, per
section 4.1: pull the example number, problem statement, and (when printed) its
solution. Kept separate from problem_extraction.py because the detection shape is
genuinely different -- a worked example is "Example N" heading + prose + optional
"Solution" prose, not a numbered list -- not because the two stages disagree on what
counts as mechanical.

NOTE: like problem_extraction.py, the exact way MinerU represents an "Example N"
heading (a title-typed block vs. a bolded prefix inside a text-typed block, and
whether a text_level is assigned to it at all) has not been confirmed against real
output -- see the swap plan's Step 0 spike. _EXAMPLE_HEADING_RE and _SOLUTION_RE below
match on text content regardless of block type for that reason, and are the most
likely place this module needs adjusting once the spike runs.
"""

from __future__ import annotations

import re
from typing import Any

from .mineru_extraction import NOISE_TEXT_TYPES, Block

_EXAMPLE_HEADING_RE = re.compile(r"(?i)^\s*example\s+(\d+[a-z]?)\b\.?\s*(.*)$", re.DOTALL)
_SOLUTION_RE = re.compile(r"(?im)^\s*solution\s*:?\s*$")


def _finalize(
    example_number: str, page_number: int, problem_parts: list[str], solution_parts: list[str]
) -> dict[str, Any] | None:
    problem_text = "\n".join(part for part in problem_parts if part.strip()).strip()
    solution_text = "\n".join(part for part in solution_parts if part.strip()).strip() or None
    if not problem_text:
        return None
    return {
        "example_number": example_number,
        "page_number": page_number,
        "problem_text": problem_text,
        "solution_text": solution_text,
    }


def extract_worked_examples(page_blocks: list[tuple[int, Block]]) -> list[dict[str, Any]]:
    """Build worked_examples rows (minus textbook_id/chapter_id/section_id/ordinal,
    added by the caller on write) from a section's (page_number, Block) stream.
    """
    rows: list[dict[str, Any]] = []

    current_number: str | None = None
    current_page: int | None = None
    problem_parts: list[str] = []
    solution_parts: list[str] = []
    in_solution = False

    for page_number, block in page_blocks:
        if block.type in NOISE_TEXT_TYPES or not block.text.strip():
            continue

        heading = _EXAMPLE_HEADING_RE.match(block.text)
        if heading:
            if current_number is not None:
                row = _finalize(current_number, current_page, problem_parts, solution_parts)
                if row:
                    rows.append(row)
            current_number = heading.group(1)
            current_page = page_number
            problem_parts, solution_parts, in_solution = [], [], False
            remainder = heading.group(2).strip()
            if remainder:
                problem_parts.append(remainder)
            continue

        if current_number is None:
            continue  # prose before the first "Example N" heading in this section

        if _SOLUTION_RE.match(block.text):
            in_solution = True
            continue

        (solution_parts if in_solution else problem_parts).append(block.text)

    if current_number is not None:
        row = _finalize(current_number, current_page, problem_parts, solution_parts)
        if row:
            rows.append(row)

    for ordinal, row in enumerate(rows):
        row["ordinal"] = ordinal

    return rows
