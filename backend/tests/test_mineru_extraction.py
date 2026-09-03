"""Verification for the MinerU-backed extraction stage (mirrors test_pdf_extraction.py,
see its module docstring for the anchor-word-coverage strategy both files share via
_extraction_check_helpers.py).

Two things have to hold, same as the pdfplumber-backed stage:

    1. extracted raw text for the fixture's pages matches the source PDF
    2. no LLM calls are made in this stage -- local CV/OCR/layout inference is fine
       (ARCHITECTURE.md section 4.1's mechanical/judgment split is about billed model
       APIs and interpretation, not about whether local ML models are involved), a
       ChatOpenAI/langchain/openai/anthropic import is not

This file requires the `mineru` CLI to actually be installed and on PATH (see
backend/requirements-mineru.txt) and the fixture PDF to be present locally
(fixtures/source/, git-ignored) -- both are skipped gracefully via the `pages`
fixture when unavailable, same pattern as test_pdf_extraction.py's `pdf_path` fixture.
The two import-guard tests below need neither and always run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion import mineru_extraction
from ingestion.mineru_extraction import STATUS_FAILED, compute_sha256, extract_pages

from _extraction_check_helpers import check_placement, normalise

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "fixtures" / "golden_chapter.example.json"

# Same guard as test_pdf_extraction.py -- reaffirmed here because this module now
# involves local ML models, which makes it worth re-checking that "mechanical" still
# means "no billed model API call" and not "no ML at all".
FORBIDDEN_IMPORTS = ("langchain", "openai", "anthropic", "agents", "db.client")


@pytest.fixture(scope="session")
def fixture() -> dict:
    if not FIXTURE_PATH.exists():
        pytest.skip(f"fixture not found: {FIXTURE_PATH}")
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def pdf_path(fixture: dict) -> Path:
    path = REPO_ROOT / "fixtures" / "source" / fixture["source"]["pdf_filename"]
    if not path.exists():
        pytest.skip(f"source PDF not present (git-ignored): {path}")
    return path


@pytest.fixture(scope="session")
def pages(fixture: dict, pdf_path: Path) -> dict[int, mineru_extraction.PageExtraction]:
    """Extract the chapter and the answer key once, keyed by PDF page number."""
    chapter = fixture["chapter"]
    source = fixture["source"]

    extracted: dict[int, mineru_extraction.PageExtraction] = {}
    ranges = [(chapter["page_start"], chapter["page_end"])]
    if source.get("answer_key_page_start"):
        ranges.append((source["answer_key_page_start"], source["answer_key_page_end"]))

    for start, end in ranges:
        for page in extract_pages(pdf_path, start, end):
            extracted[page.page_number] = page

    if all(page.status == STATUS_FAILED for page in extracted.values()):
        pytest.skip(
            "every page failed extraction -- likely the mineru CLI is not installed "
            "(see backend/requirements-mineru.txt), not a real regression"
        )
    return extracted


# --- (2) no LLM in this stage ------------------------------------------------


def test_extraction_module_imports_nothing_that_calls_a_model():
    source = Path(mineru_extraction.__file__).read_text(encoding="utf-8")
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from ")) and "#" not in line.split("import")[0]
    ]
    joined = "\n".join(import_lines).lower()

    for forbidden in FORBIDDEN_IMPORTS:
        assert forbidden not in joined, (
            f"mineru_extraction imports {forbidden!r}. This stays a mechanical stage "
            f"(ARCHITECTURE.md section 4.1) -- local CV/OCR inference via a subprocess "
            f"CLI call is fine, a billed model API call is not."
        )


def test_importing_extraction_does_not_pull_in_a_model_client():
    """Import side effects count too -- a transitive import is still a dependency."""
    import subprocess
    import sys

    script = (
        "import sys; sys.path.insert(0, r'%s');"
        "import ingestion.mineru_extraction;"
        "bad=[m for m in sys.modules if m.split('.')[0] in ('langchain','openai','anthropic')];"
        "print(','.join(bad))" % str(REPO_ROOT / "backend")
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", f"model client imported: {result.stdout.strip()}"


# --- (1) extracted text matches the source PDF -------------------------------


def test_source_pdf_hash_matches_fixture(fixture: dict, pdf_path: Path):
    declared = fixture["source"]["pdf_sha256"]
    if set(declared) == {"0"}:
        pytest.skip("fixture has a placeholder hash")
    assert compute_sha256(pdf_path) == declared, (
        "the PDF on disk is not the one the fixture was annotated against"
    )


def test_no_page_failed_to_extract(pages: dict):
    failed = {n: p.error for n, p in pages.items() if p.status == STATUS_FAILED}
    assert not failed, f"pages failed extraction: {failed}"


def test_every_chapter_page_has_text(fixture: dict, pages: dict):
    chapter = fixture["chapter"]
    empty = [
        n
        for n in range(chapter["page_start"], chapter["page_end"] + 1)
        if not (pages[n].raw_text or "").strip()
    ]
    assert not empty, f"chapter pages extracted no text: {empty}"


def test_page_offset_converts_printed_to_pdf_index(fixture: dict, pages: dict):
    """printed + offset = pdf index. The printed number is on the page; look for it."""
    offset = fixture["source"].get("page_offset", 0)
    chapter = fixture["chapter"]
    pdf_index = chapter["page_start"]
    printed = pdf_index - offset

    text = normalise(pages[pdf_index].raw_text)
    assert str(printed) in text.split(), (
        f"PDF page {pdf_index} should carry printed page number {printed} "
        f"(page_offset={offset}), but that number is not on the page"
    )


def test_chapter_title_appears_on_its_opening_page(fixture: dict, pages: dict):
    chapter = fixture["chapter"]
    anchor = normalise(chapter["title"])
    window = range(chapter["page_start"], min(chapter["page_start"] + 3, chapter["page_end"]) + 1)
    found = any(anchor in normalise(pages[n].raw_text) for n in window)
    assert found, f"chapter title {chapter['title']!r} not found on pages {list(window)}"


def test_section_titles_appear_near_their_start_pages(fixture: dict, pages: dict):
    misses = []
    for section in fixture["sections"]:
        anchor = normalise(section["title"])
        window = range(section["page_start"], min(section["page_start"] + 2, section["page_end"]) + 1)
        if not any(anchor in normalise(pages[n].raw_text) for n in window if n in pages):
            misses.append((section["key"], section["title"], section["page_start"]))
    assert not misses, f"section titles not found near their start pages: {misses}"


def test_problem_bodies_appear_on_their_recorded_pages(fixture: dict, pages: dict):
    check_placement(
        [(p["key"], p["body_plain"], p["page_number"]) for p in fixture["problems"]],
        pages,
        "problem",
    )


def test_worked_examples_appear_on_their_recorded_pages(fixture: dict, pages: dict):
    check_placement(
        [(e["key"], e["problem_text"], e["page_number"]) for e in fixture["worked_examples"]],
        pages,
        "worked example",
    )


def test_answers_appear_on_their_source_pages(fixture: dict, pages: dict):
    """Answers sit hundreds of pages from the problem (section 15) -- verify separately."""
    check_placement(
        [(a["problem_key"], a["answer_text"], a["answer_source_page"]) for a in fixture["answers"]],
        pages,
        "answer",
    )


# --- section 6: layout, coordinates, ordering, figures -----------------------


def test_blocks_carry_bbox_and_order(fixture: dict, pages: dict):
    page = pages[fixture["chapter"]["page_start"]]
    assert page.blocks, "no blocks captured; section 6 requires layout information"
    assert [block.ordinal for block in page.blocks] == list(range(len(page.blocks))), (
        "blocks are not in reading order"
    )
    for block in page.blocks:
        if block.bbox is not None:
            x0, y0, x1, y1 = block.bbox
            assert x1 >= x0 and y1 >= y0, f"malformed bbox on block {block.ordinal}: {block.bbox}"


def test_figure_references_are_recorded(fixture: dict, pages: dict):
    """This chapter is full of parabola graphs; finding none means images were dropped."""
    chapter = fixture["chapter"]
    total = sum(
        len(pages[n].images) for n in range(chapter["page_start"], chapter["page_end"] + 1)
    )
    assert total > 0, "no image/figure references captured across the chapter"


def test_the_spot_check_actually_detects_a_page_shift(fixture: dict, pages: dict):
    """Guard against the verification above quietly becoming vacuous.

    A spot-check that passes no matter what is worse than none, because it reads as
    evidence. Shifting every problem two pages along must fail -- if it does not,
    the coverage threshold has been loosened until it stopped testing anything.
    """
    shifted = [
        (problem["key"], problem["body_plain"], problem["page_number"] + 2)
        for problem in fixture["problems"]
    ]
    with pytest.raises(AssertionError):
        check_placement(shifted, pages, "deliberately shifted problem")


def test_rows_match_the_textbook_pages_schema(fixture: dict, pages: dict):
    row = pages[fixture["chapter"]["page_start"]].to_row(source_id="00000000-0000-0000-0000-000000000000")
    assert set(row) == {
        "source_id",
        "page_number",
        "raw_text",
        "extraction_status",
        "parser",
        "layout",
        "images",
    }
    # ocr_required is deliberately absent from this set -- MinerU's pipeline backend
    # OCRs internally, so nothing is ever deferred to a later OCR pass (see
    # mineru_extraction.py's module docstring).
    assert row["extraction_status"] in {"pending", "extracted", "failed"}
    assert row["parser"] in {"mineru-pipeline", None}
