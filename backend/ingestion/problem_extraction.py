"""Raw problem extraction (ARCHITECTURE.md section 10.1) -- mechanical, per section 4.1:
pull problem number and text, decide nothing about what a problem teaches or how it
groups. No LLM call belongs in this module.

Rewritten 2026-09-03 after running the real MinerU pipeline backend against Pre-Calculus
12 section 1.1 (the Step 0 spike the original version deferred). Two things the original
docstring assumed turned out not to hold:

    1. MinerU's pipeline backend never emits a `list`-typed block. Every numbered
       item -- down to lettered sub-parts -- comes through as its own (or occasionally
       combined) `text`-typed block, indistinguishable by type from ordinary prose.
       So detection can't gate on block.type == "list" the way the schema doc implies;
       it has to look at each block's own text.

    2. The same digit-dot numbering is reused for two pedagogically different things
       within one section: the Investigate/Reflect and Respond guided-discovery steps,
       and the actual assigned Practise/Apply/Extend/Create Connections exercises --
       and their numbers collide (section 1.1 has a "9." under Reflect and Respond AND
       an unrelated "9." under Apply). The only signal telling them apart is the
       subsection heading text itself, which MinerU tags via text_level rather than a
       "title" block type. So this module only starts collecting problems once it has
       seen a practice-tier heading (PRACTICE_TIER_HEADINGS) -- everything numbered
       before that point is a guided-discovery step, not a problem, and is dropped.

    "Create Connections" also numbers its items "C1"/"C2"/... instead of plain digits,
    which needed its own pattern (_CREATE_CONNECTIONS_START_RE).

Once inside the practice tier, this streams the section's blocks in reading order like
worked_example_extraction.py does: a block whose own text starts with a number closes
out whatever problem was accumulating and opens a new one; a block that doesn't match
extends the open problem's body; a block with no open problem to attach to (a "Did You
Know?" aside dropped into the middle of Apply, say) is dropped rather than silently
glued onto the wrong problem.
"""

from __future__ import annotations

import re
from typing import Any

from .mineru_extraction import NOISE_TEXT_TYPES, Block

# Subsection headings (McGraw-Hill's fixed three-part-lesson structure) that mark the
# start of graded practice content, as opposed to Investigate/Reflect and
# Respond/Link the Ideas/Key Ideas, which are guided-discovery or explanatory and never
# contain problems. Matched case-insensitively against a heading block's full text.
PRACTICE_TIER_HEADINGS = frozenset(
    {"practise", "practice", "apply", "extend", "create connections", "check your understanding"}
)

# Ordinary numbering: digits, optionally one lowercase letter directly against them (no
# space -- "17a", not "17 a"), then a separator. A bare lettered sub-part ("a)", "b)")
# has no leading digit and so never matches this -- it extends the open problem instead.
_ITEM_START_RE = re.compile(r"^\s*(\d+)([a-z])?[.)]\s+")
# "Create Connections" numbers its items C1, C2, ... instead of digits.
_CREATE_CONNECTIONS_START_RE = re.compile(r"^\s*(C\d+)\b\.?\s*")

# Best-effort signal that a chunk's text already carries LaTeX-ish markup (either a
# $...$ delimiter or a backslash command) rather than plain Unicode math -- confirmed
# against the spike run: MinerU's formula recognizer does wrap real equations in $$...$$.
_LATEX_MARKER_RE = re.compile(r"\$[^$]+\$|\\[a-zA-Z]+")


def is_practice_heading(text: str) -> bool:
    """Whether a heading block's text marks the start of the practice tier."""
    return text.strip().rstrip(":").strip().lower() in PRACTICE_TIER_HEADINGS


def _match_item_start(text: str) -> tuple[str, str] | None:
    """If text opens a new numbered item, return (problem_number, remaining body)."""
    match = _ITEM_START_RE.match(text)
    if match:
        return match.group(1) + (match.group(2) or ""), text[match.end():].strip()
    match = _CREATE_CONNECTIONS_START_RE.match(text)
    if match:
        return match.group(1), text[match.end():].strip()
    return None


def extract_problems(page_blocks: list[tuple[int, Block]]) -> list[dict[str, Any]]:
    """Build problems rows (minus textbook_id/chapter_id/section_id, added by the
    caller on write) from a section's (page_number, Block) stream in reading order.
    """
    rows: list[dict[str, Any]] = []
    in_practice = False

    current_number: str | None = None
    current_page: int | None = None
    current_start_block: Block | None = None
    parts: list[str] = []

    def flush() -> None:
        nonlocal current_number, current_page, current_start_block, parts
        if current_number is not None:
            body = "\n".join(part for part in parts if part.strip()).strip()
            if body:
                has_latex = bool(_LATEX_MARKER_RE.search(body))
                rows.append(
                    {
                        "ordinal": len(rows),
                        "problem_number": current_number,
                        "page_number": current_page,
                        "body_plain": body,
                        "body_latex": body if has_latex else None,
                        "source_ref": {
                            "page_number": current_page,
                            "block_ordinal_on_page": current_start_block.ordinal,
                            "bbox": list(current_start_block.bbox) if current_start_block.bbox else None,
                        },
                    }
                )
        current_number, current_page, current_start_block, parts = None, None, None, []

    for page_number, block in page_blocks:
        if block.type in NOISE_TEXT_TYPES:
            continue
        text = block.text.strip()
        if not text:
            continue

        if block.text_level is not None:
            flush()
            if is_practice_heading(text):
                in_practice = True
            continue

        if not in_practice:
            continue

        start = _match_item_start(text)
        if start:
            flush()
            current_number, remainder = start
            current_page = page_number
            current_start_block = block
            parts = [remainder] if remainder else []
            continue

        if current_number is not None:
            parts.append(text)
        # else: stray text with no open problem (e.g. an aside dropped into the
        # practice tier) -- dropped rather than glued onto the wrong problem.

    flush()
    return rows


def numbering_gaps(problem_numbers: list[str]) -> list[str]:
    """Extraction-error check (ARCHITECTURE.md section 10.1), not a blocking rule:
    which base printed numbers are missing from an otherwise contiguous run.

    A lettered number (17a/17b) counts as covering its base ("17") -- a section that
    prints 17a/17b instead of a plain 17 has not skipped problem 17, it split it, and
    that split must not read as a gap at 17. "Create Connections" numbers (C1, C2, ...)
    are a separate sequence and are not counted as part of the digit run.

    A gap is not automatically a bug: a graph-only exercise with no text layer is a
    legitimate, explainable absence (see fixtures/golden_chapter.example.json's
    annotation note on problems 5 and 8). This is a signal for a human/test to look
    at, not something extract_problems itself treats as failure.
    """
    bases: set[int] = set()
    for number in problem_numbers:
        if number.isdigit():
            bases.add(int(number))
        elif number[:-1].isdigit() and number[-1:].isalpha():
            bases.add(int(number[:-1]))

    if len(bases) < 2:
        return []
    full_run = range(min(bases), max(bases) + 1)
    return [str(n) for n in full_run if n not in bases]
