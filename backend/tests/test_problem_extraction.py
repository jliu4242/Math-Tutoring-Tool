"""Verification for problem_extraction.py's numbering-split logic.

This is the genuinely new mechanical parsing this swap adds (ARCHITECTURE.md section
10.1). Rewritten 2026-09-03 after running the real MinerU pipeline backend against
Pre-Calculus 12 section 1.1: MinerU never emits a `list`-typed block, and reuses the
same digit-dot numbering for both guided-discovery steps and real exercises -- see
problem_extraction.py's module docstring. These are literal-text unit tests, not
fixture-driven ones: the anchor-word-coverage check against
fixtures/golden_chapter.example.json's problems[] is already exercised by
test_mineru_extraction.py::test_problem_bodies_appear_on_their_recorded_pages (which
runs over real extracted pages), so it is not duplicated here.
"""

from __future__ import annotations

from ingestion.mineru_extraction import Block
from ingestion.problem_extraction import extract_problems, numbering_gaps


def _heading(text: str, level: int = 2) -> Block:
    return Block(ordinal=0, type="text", text=text, text_level=level)


def _text(text: str) -> Block:
    return Block(ordinal=0, type="text", text=text)


def _practice_blocks(*texts: str, page: int = 168) -> list[tuple[int, Block]]:
    """A practice-tier heading (as real MinerU output tags it -- text_level on a
    `text` block, never a `title`-typed block) followed by one block per text line.
    """
    blocks = [(page, _heading("Apply"))]
    blocks.extend((page, _text(text)) for text in texts)
    return blocks


def test_inline_lettered_sub_parts_stay_in_one_row():
    """Matches fixtures/golden_chapter.example.json's p-3.1-1: one printed number,
    lettered parts a)/b)/c)/d) inline, all belonging to a single problem row.
    """
    rows = extract_problems(
        _practice_blocks(
            "1. Describe how you can obtain the graph of each function from the graph "
            "of f(x) = x^2. a) f(x) = 7x^2 b) f(x) = (1/6)x^2 c) f(x) = -4x^2 "
            "d) f(x) = -0.2x^2",
            "2. Describe how the graphs of the functions in each pair are related.",
        )
    )

    assert [row["problem_number"] for row in rows] == ["1", "2"]
    assert "a) f(x) = 7x^2" in rows[0]["body_plain"]
    assert "d) f(x) = -0.2x^2" in rows[0]["body_plain"]
    assert "2. Describe" not in rows[0]["body_plain"]


def test_lettered_sub_parts_as_separate_blocks_join_the_open_problem():
    """The common real shape (confirmed against the spike run): MinerU splits each
    lettered sub-part into its own block rather than keeping them inline with the
    stem. They must still land in the stem's row, not become their own problems.
    """
    rows = extract_problems(
        _practice_blocks(
            "3. Describe, using mapping notation, how the graphs are obtained.",
            "a) y = f(x + 10)",
            "b) y + 6 = f(x)",
            "4. Given the graph of y = f(x), sketch the transformed function.",
        )
    )

    assert [row["problem_number"] for row in rows] == ["3", "4"]
    assert "a) y = f(x + 10)" in rows[0]["body_plain"]
    assert "b) y + 6 = f(x)" in rows[0]["body_plain"]


def test_separate_lettered_numbers_become_their_own_rows():
    """fixtures/README.md's ambiguous-numbering case: the exercise set prints 17a/17b
    as separate items (the answer key later collapses them to a single printed "17.").
    """
    rows = extract_problems(
        _practice_blocks(
            "17a. Solve P = 2l + 2w for l.",
            "17b. Solve P = 2l + 2w for w.",
            "18. Solve C = 2*pi*r for r.",
        )
    )

    assert [row["problem_number"] for row in rows] == ["17a", "17b", "18"]
    assert "l" in rows[0]["body_plain"]
    assert "w" in rows[1]["body_plain"]


def test_create_connections_uses_letter_number_style():
    """"Create Connections" numbers its items C1/C2/... instead of digits -- confirmed
    against the spike run's page 24."""
    rows = extract_problems(
        [(24, _heading("Create Connections"))]
        + [
            (24, _text("C1 Show that the order of translations does not matter.")),
            (24, _text("a) Explain why this is true.")),
            (24, _text("C2 Complete the square for each function.")),
        ]
    )

    assert [row["problem_number"] for row in rows] == ["C1", "C2"]
    assert "a) Explain why" in rows[0]["body_plain"]


def test_body_latex_only_set_when_latex_markers_present():
    rows = extract_problems(
        _practice_blocks(
            "1. Solve 3x + 7 = 19 in plain text.",
            "2. Solve $3x + 7 = 19$ for x.",
        )
    )

    assert rows[0]["body_latex"] is None
    assert rows[1]["body_latex"] == rows[1]["body_plain"]


def test_ordinal_is_sequential_reading_order():
    rows = extract_problems(_practice_blocks("1. First.", "2. Second.", "3. Third."))
    assert [row["ordinal"] for row in rows] == [0, 1, 2]


def test_numbered_text_before_a_practice_heading_is_ignored():
    """The core finding from the spike: Investigate/Reflect and Respond steps reuse
    plain digit-dot numbering with no type signal distinguishing them from real
    problems. Only a recognized practice-tier heading (Apply/Extend/Practise/Create
    Connections/Check Your Understanding) opens problem collection.
    """
    blocks = [
        (16, _heading("Reflect and Respond")),
        (16, _text("9. Describe how the parameters h and k affect the graph.")),
    ]
    assert extract_problems(blocks) == []


def test_a_heading_outside_the_allowlist_does_not_open_practice_tier():
    blocks = [
        (16, _heading("Did You Know?")),
        (16, _text("1. This looks numbered but sits under a non-practice heading.")),
    ]
    assert extract_problems(blocks) == []


def test_practice_tier_stays_open_across_an_unrelated_aside_heading():
    """A "Did You Know?" box dropped mid-Apply (confirmed on the spike's page 23) must
    not end problem collection for what follows -- Apply resumes without repeating
    its own heading.
    """
    rows = extract_problems(
        [
            (23, _heading("Apply")),
            (23, _text("14. This Pow Wow belt shows a frieze pattern.")),
            (23, _text("a) Create your own frieze pattern.")),
            (23, _heading("Did You Know?")),
            (23, _text("Traditional dances are performed by men, women, and children.")),
            (24, _text("15. Michele Lake and Coral Lake are the only lakes with trout.")),
        ]
    )

    assert [row["problem_number"] for row in rows] == ["14", "15"]
    assert "Traditional dances" not in rows[0]["body_plain"]
    assert "Traditional dances" not in rows[1]["body_plain"]


def test_source_ref_carries_page_and_block_provenance():
    rows = extract_problems(_practice_blocks("1. Solve for x.", page=168))
    assert rows[0]["source_ref"]["page_number"] == 168
    assert rows[0]["source_ref"]["block_ordinal_on_page"] == 0


def test_numbering_gaps_reports_missing_numeric_entries():
    assert numbering_gaps(["1", "2", "3", "4", "6", "7", "11"]) == ["5", "8", "9", "10"]


def test_numbering_gaps_does_not_flag_a_lettered_pairs_own_base_number():
    """15, 16, [17a, 17b], 18, 19 -- 17 is not missing, it was printed as two parts."""
    assert numbering_gaps(["15", "16", "17a", "17b", "18", "19"]) == []


def test_numbering_gaps_empty_for_a_contiguous_run():
    assert numbering_gaps(["1", "2", "3"]) == []
