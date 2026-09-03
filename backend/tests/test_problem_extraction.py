"""Verification for problem_extraction.py's numbering-split logic.

This is the genuinely new mechanical parsing this swap adds (ARCHITECTURE.md section
10.1): MinerU delineates *where* an exercise set is (a `list`-typed block) but not
where each numbered item starts and ends -- see problem_extraction.py's module
docstring. These are literal-text unit tests, not fixture-driven ones: the anchor-word-
coverage check against fixtures/golden_chapter.example.json's problems[] is already
exercised by test_mineru_extraction.py::test_problem_bodies_appear_on_their_recorded_pages
(which runs over real extracted pages), so it is not duplicated here.
"""

from __future__ import annotations

from ingestion.mineru_extraction import Block
from ingestion.problem_extraction import extract_problems, numbering_gaps


def _list_block(text: str) -> list[tuple[int, Block]]:
    return [(168, Block(ordinal=0, type="list", text=text, sub_type="ordinary"))]


def test_inline_lettered_sub_parts_stay_in_one_row():
    """Matches fixtures/golden_chapter.example.json's p-3.1-1: one printed number,
    lettered parts a)/b)/c)/d) inline, all belonging to a single problem row.
    """
    text = (
        "1. Describe how you can obtain the graph of each function from the graph "
        "of f(x) = x^2. a) f(x) = 7x^2 b) f(x) = (1/6)x^2 c) f(x) = -4x^2 "
        "d) f(x) = -0.2x^2\n"
        "2. Describe how the graphs of the functions in each pair are related."
    )
    rows = extract_problems(_list_block(text))

    assert [row["problem_number"] for row in rows] == ["1", "2"]
    assert "a) f(x) = 7x^2" in rows[0]["body_plain"]
    assert "d) f(x) = -0.2x^2" in rows[0]["body_plain"]
    assert "2. Describe" not in rows[0]["body_plain"]


def test_separate_lettered_numbers_become_their_own_rows():
    """fixtures/README.md's ambiguous-numbering case: the exercise set prints 17a/17b
    as separate items (the answer key later collapses them to a single printed "17.").
    """
    text = (
        "17a. Solve P = 2l + 2w for l.\n"
        "17b. Solve P = 2l + 2w for w.\n"
        "18. Solve C = 2*pi*r for r."
    )
    rows = extract_problems(_list_block(text))

    assert [row["problem_number"] for row in rows] == ["17a", "17b", "18"]
    assert "l" in rows[0]["body_plain"]
    assert "w" in rows[1]["body_plain"]


def test_body_latex_only_set_when_latex_markers_present():
    text = "1. Solve 3x + 7 = 19 in plain text.\n2. Solve $3x + 7 = 19$ for x."
    rows = extract_problems(_list_block(text))

    assert rows[0]["body_latex"] is None
    assert rows[1]["body_latex"] == rows[1]["body_plain"]


def test_ordinal_is_sequential_reading_order():
    text = "1. First.\n2. Second.\n3. Third."
    rows = extract_problems(_list_block(text))
    assert [row["ordinal"] for row in rows] == [0, 1, 2]


def test_non_list_blocks_are_ignored():
    blocks = [(100, Block(ordinal=0, type="text", text="1. This looks numbered but is prose."))]
    assert extract_problems(blocks) == []


def test_source_ref_carries_page_and_block_provenance():
    rows = extract_problems(_list_block("1. Solve for x."))
    assert rows[0]["source_ref"]["page_number"] == 168
    assert rows[0]["source_ref"]["block_ordinal_on_page"] == 0


def test_numbering_gaps_reports_missing_numeric_entries():
    assert numbering_gaps(["1", "2", "3", "4", "6", "7", "11"]) == ["5", "8", "9", "10"]


def test_numbering_gaps_does_not_flag_a_lettered_pairs_own_base_number():
    """15, 16, [17a, 17b], 18, 19 -- 17 is not missing, it was printed as two parts."""
    assert numbering_gaps(["15", "16", "17a", "17b", "18", "19"]) == []


def test_numbering_gaps_empty_for_a_contiguous_run():
    assert numbering_gaps(["1", "2", "3"]) == []
