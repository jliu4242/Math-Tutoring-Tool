"""Content-block extraction (ARCHITECTURE.md section 8, section 18 schema).

Mechanical, per the scope agreed for this swap: this stage maps MinerU's own
type/text_level onto content_blocks.block_type with no interpretation of what a block
of prose actually *is*. Real semantic classification (explanation vs. definition vs.
theorem vs. ...) is a judgment stage per ARCHITECTURE.md section 4.1 -- it needs
hand-annotated fixture ground truth and a diff gate before it can be trusted at
pipeline scale -- and is deliberately deferred to a documented follow-up, not built
here. Every block this stage emits uses the single generic 'body_text' block_type
added by 20260822120000_content_block_generic_type.sql.

Routing, not classification, is what this stage actually decides:

    text, code            -> a body_text content_blocks row
    equation               -> folded into the preceding body_text row's content
                              (or starts a new one if nothing precedes it)
    title                  -> dropped here; feeds structure_agent's heading signal,
                              which runs over the raw block stream separately
    list                   -> dropped here; routed to problem_extraction.py instead
    header/footer/etc.      -> dropped; page furniture (mineru_extraction.NOISE_TEXT_TYPES)

Input is a section's blocks in reading order, already filtered to that section's page
range by the caller (background.py) -- this module never re-reads MinerU output or
touches page ranges itself.
"""

from __future__ import annotations

from typing import Any

from .mineru_extraction import NOISE_TEXT_TYPES, Block

# MinerU types that fold into the previous body_text block rather than starting a row
# of their own -- an equation is part of the surrounding prose, not a standalone unit.
FOLD_INTO_PREVIOUS = frozenset({"equation"})

# Routed elsewhere; never become a content_blocks row from this module.
ROUTED_ELSEWHERE = frozenset({"title", "list"})

BODY_TEXT_BLOCK_TYPE = "body_text"


def extract_content_blocks(page_blocks: list[tuple[int, Block]]) -> list[dict[str, Any]]:
    """Build content_blocks rows (minus section_id, added by the caller on write) from
    a section's (page_number, Block) stream in reading order.
    """
    rows: list[dict[str, Any]] = []

    for page_number, block in page_blocks:
        if block.type in NOISE_TEXT_TYPES or block.type in ROUTED_ELSEWHERE:
            continue
        if not block.text.strip():
            continue

        if block.type in FOLD_INTO_PREVIOUS and rows and rows[-1]["page_end"] == page_number:
            rows[-1]["content"] = f"{rows[-1]['content']}\n{block.text}".strip()
            continue

        rows.append(
            {
                "ordinal": len(rows),
                "block_type": BODY_TEXT_BLOCK_TYPE,
                "page_start": page_number,
                "page_end": page_number,
                "content": block.text,
                "source_ref": {
                    "page_number": page_number,
                    "block_ordinal_on_page": block.ordinal,
                    "mineru_type": block.type,
                    "bbox": list(block.bbox) if block.bbox else None,
                },
            }
        )

    return rows
