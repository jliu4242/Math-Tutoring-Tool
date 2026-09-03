"""Raw problem extraction (ARCHITECTURE.md section 10.1) -- mechanical, per section 4.1:
pull problem number and text, decide nothing about what a problem teaches or how it
groups. No LLM call belongs in this module.

MinerU types an exercise set as a `list`-typed block (mineru_extraction.Block, MinerU's
own `sub_type` distinguishing ordinary vs. reference-style lists), but that block's
`text` is a flattened string, not pre-split per item -- MinerU delineates *where* the
exercise set is, not where each numbered item starts and ends. That split happens here.

NOTE on the split heuristic: the exact way MinerU flattens list items (one per line
vs. one continuous paragraph; whether inline formulas keep $...$ delimiters or plain
Unicode) has not yet been confirmed against real output -- see the swap plan's Step 0
spike, deliberately deferred. _split_list_items and the body_latex heuristic below are
written against MinerU's documented content_list.json schema and are the most likely
place this module needs adjusting once the spike runs against a real chapter.

Numbering shapes, both confirmed against fixtures/golden_chapter.example.json:

    "1. Describe how... a) f(x)=7x^2  b) ..."   -> ONE row, problem_number="1",
                                                    lettered parts stay inside body_plain
    "17a. ...\n17b. ..."                          -> TWO rows, problem_number="17a"
                                                    and "17b" -- the ambiguous-numbering
                                                    case fixtures/README.md requires,
                                                    where the answer key later collapses
                                                    these to a single printed "17."
"""

from __future__ import annotations

import re
from typing import Any

from .mineru_extraction import Block

LIST_BLOCK_TYPE = "list"

# Top-level item start: digits, optionally a single lowercase letter directly against
# them (no space -- "17a", not "17 a"), then a separator and whitespace. A bare
# lettered sub-part ("a)", "b)") has no leading digit and so never matches this.
_ITEM_START_LINE_RE = re.compile(r"(?m)^\s*(\d+)([a-z])?[.)]\s+")
# Fallback for a list block MinerU flattened onto a single line with no newlines
# between items: same shape, but anchored to "start of string or preceded by
# whitespace" instead of "start of line".
_ITEM_START_INLINE_RE = re.compile(r"(?:^|\s)(\d+)([a-z])?[.)]\s+")

# Best-effort signal that a chunk's text already carries LaTeX-ish markup (either a
# $...$ delimiter or a backslash command) rather than plain Unicode math. Whether
# MinerU's inline-formula merge actually produces this, vs. plain-text math symbols,
# is exactly what the Step 0 spike needs to confirm -- see module docstring.
_LATEX_MARKER_RE = re.compile(r"\$[^$]+\$|\\[a-zA-Z]+")


def _split_list_items(text: str) -> list[tuple[str, str]]:
    """Split one list block's flattened text into (problem_number, body) chunks."""
    matches = list(_ITEM_START_LINE_RE.finditer(text))
    if not matches:
        matches = list(_ITEM_START_INLINE_RE.finditer(text))

    chunks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        number = match.group(1) + (match.group(2) or "")
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            chunks.append((number, body))
    return chunks


def extract_problems(page_blocks: list[tuple[int, Block]]) -> list[dict[str, Any]]:
    """Build problems rows (minus textbook_id/chapter_id/section_id, added by the
    caller on write) from a section's (page_number, Block) stream in reading order.
    """
    rows: list[dict[str, Any]] = []

    for page_number, block in page_blocks:
        if block.type != LIST_BLOCK_TYPE or not block.text.strip():
            continue

        for problem_number, body in _split_list_items(block.text):
            has_latex = bool(_LATEX_MARKER_RE.search(body))
            rows.append(
                {
                    "ordinal": len(rows),
                    "problem_number": problem_number,
                    "page_number": page_number,
                    "body_plain": body,
                    "body_latex": body if has_latex else None,
                    "source_ref": {
                        "page_number": page_number,
                        "block_ordinal_on_page": block.ordinal,
                        "bbox": list(block.bbox) if block.bbox else None,
                    },
                }
            )

    return rows


def numbering_gaps(problem_numbers: list[str]) -> list[str]:
    """Extraction-error check (ARCHITECTURE.md section 10.1), not a blocking rule:
    which base printed numbers are missing from an otherwise contiguous run.

    A lettered number (17a/17b) counts as covering its base ("17") -- a section that
    prints 17a/17b instead of a plain 17 has not skipped problem 17, it split it, and
    that split must not read as a gap at 17.

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
