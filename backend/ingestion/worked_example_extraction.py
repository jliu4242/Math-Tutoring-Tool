"""Worked-example extraction (ARCHITECTURE.md sections 11, 11.1) -- mechanical, per
section 4.1: pull the example number, problem statement, and (when printed) its
solution. Kept separate from problem_extraction.py because the detection shape is
genuinely different -- a worked example is "Example N" heading + prose + optional
"Solution" prose, not a numbered list -- not because the two stages disagree on what
counts as mechanical.

Updated 2026-09-03 after running the real MinerU pipeline backend against Pre-Calculus
12 section 1.1 (the Step 0 spike the original version deferred). "Example N" headings
come through exactly like every other heading in this book -- a `text`-typed block
carrying `text_level`, never a `title`-typed block -- and the real shape turned out
more structured than the original version assumed:

    "Example 1"                          <- _EXAMPLE_HEADING_RE match, opens the example
    "Graph Translations of the Form..."  <- its own heading block too: the example's
                                             subtitle, immediately following "Example N"
                                             with no other content in between
    "a) Graph the functions..."          <- plain text, the problem statement
    "Solution"                            <- its own heading block, not plain text
    ...solution content...
    "Your Turn"                           <- its own heading block: a follow-up prompt
                                             for the same example, not a new problem
    ...your-turn content...
    "Example 2"                          <- next example

So three things needed fixing from the original version's single "match the next
Example N heading" rule:

    1. It never closed an example on anything BUT the next "Example N" -- confirmed
       against real output, that let one example's solution silently swallow
       everything after it for the rest of the section (Key Ideas, Check Your
       Understanding, every Practise/Apply/Extend/Create Connections problem).
    2. "Solution" and "Your Turn" are heading blocks, not plain text -- a naive "any
       other heading ends the example" fix (tried first, reverted) broke this the
       other way: it ended every example at its own subtitle block, before any
       content was ever collected.
    3. Margin/glossary asides (e.g. "Did You Know?", or a term like "image point"
       defined mid-solution) are also heading blocks, structurally indistinguishable
       from a real section boundary by text_level alone, and can land *inside* an
       example's solution (confirmed: "image point" appears between "Solution" and
       the actual worked derivation in example 3). Only recognized section-level
       headings (_SECTION_TERMINATOR_HEADINGS, reusing problem_extraction.py's
       practice-tier allowlist plus "Key Ideas") end an example; any other heading is
       folded into whichever part is currently open rather than guessed at, since
       there is no reliable signal here to tell "section boundary" from "margin box."
"""

from __future__ import annotations

import re
from typing import Any

from .mineru_extraction import NOISE_TEXT_TYPES, Block
from .problem_extraction import PRACTICE_TIER_HEADINGS

_EXAMPLE_HEADING_RE = re.compile(r"(?i)^\s*example\s+(\d+[a-z]?)\b\.?\s*(.*)$", re.DOTALL)
_SOLUTION_RE = re.compile(r"(?im)^\s*solution\s*:?\s*$")

# Section-level headings that legitimately end a worked example -- reuses
# problem_extraction.py's practice-tier allowlist (Practise/Apply/Extend/Create
# Connections/Check Your Understanding) plus "Key Ideas", the heading that marks the
# end of "Link the Ideas" (where worked examples live) in this book's fixed
# three-part-lesson structure. Any OTHER heading (a margin aside, a glossary term) is
# treated as in-flow content instead -- see module docstring, point 3.
_SECTION_TERMINATOR_HEADINGS = PRACTICE_TIER_HEADINGS | {"key ideas"}


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
    # True immediately after an "Example N" heading with no body text of its own yet --
    # the very next heading-level block, if any, is that example's own subtitle rather
    # than a marker or a terminator. Cleared the moment any other block is seen.
    awaiting_subtitle = False

    def close_current() -> None:
        nonlocal current_number
        if current_number is not None:
            row = _finalize(current_number, current_page, problem_parts, solution_parts)
            if row:
                rows.append(row)
        current_number = None

    for page_number, block in page_blocks:
        if block.type in NOISE_TEXT_TYPES or not block.text.strip():
            continue
        text = block.text.strip()

        heading = _EXAMPLE_HEADING_RE.match(text)
        if heading:
            close_current()
            current_number = heading.group(1)
            current_page = page_number
            problem_parts, solution_parts, in_solution = [], [], False
            remainder = heading.group(2).strip()
            if remainder:
                problem_parts.append(remainder)
                awaiting_subtitle = False
            else:
                awaiting_subtitle = True
            continue

        if block.text_level is not None:
            label = text.rstrip(":").strip().lower()

            if label == "solution" or label == "your turn":
                # "Your Turn" is a follow-up prompt for the same example, not a new
                # problem -- both share the solution bucket.
                in_solution = True
                awaiting_subtitle = False
                continue

            if awaiting_subtitle and current_number is not None:
                problem_parts.append(text)
                awaiting_subtitle = False
                continue

            if label in _SECTION_TERMINATOR_HEADINGS:
                close_current()
                continue

            # An unrecognized heading (a margin aside like "Did You Know?", a glossary
            # term) -- fold its label text into whichever part is open rather than
            # guess whether it ends the example. See module docstring, point 3.
            if current_number is not None:
                (solution_parts if in_solution else problem_parts).append(text)
            continue

        awaiting_subtitle = False

        if current_number is None:
            continue  # prose before the first "Example N" heading in this section

        if not in_solution and _SOLUTION_RE.match(text):
            in_solution = True
            continue

        (solution_parts if in_solution else problem_parts).append(text)

    close_current()

    for ordinal, row in enumerate(rows):
        row["ordinal"] = ordinal

    return rows
