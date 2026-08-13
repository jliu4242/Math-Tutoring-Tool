"""Verification for Phase 1 Step 3 (IMPLEMENTATION-PLAN.md).

Two things have to hold:

    1. extracted raw text for the fixture's pages matches the source PDF
    2. no LLM calls are made in this stage

(1) is a spot-check driven by the fixture rather than a golden-file diff. The
fixture records, for a set of real pages, what the page says -- a problem body, an
answer, a section title. If extraction put the right text on the right page number,
those anchors are all findable. If the page range is off by the page_offset, or
pages are shifted by one, the anchors land on the wrong page and these fail.

Matching is done on normalised prose, not raw strings. The PDF text layer renders
maths as things like "  1 _ 6  x2", so comparing formulae character-by-character
would test pypdf's spacing rather than whether extraction works. The anchors are
runs of ordinary words, which survive that mangling intact.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ingestion import pdf_extraction
from ingestion.pdf_extraction import (
    STATUS_FAILED,
    compute_sha256,
    extract_pages,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "fixtures" / "golden_chapter.example.json"

# Anything that would make this stage non-deterministic or bill an API call.
FORBIDDEN_IMPORTS = ("langchain", "openai", "anthropic", "agents", "db.client")

# Fraction of an item's distinctive words that must appear on its recorded page.
MIN_COVERAGE = 0.8
# How far either side to look when checking the recorded page is the best match.
NEIGHBOUR_WINDOW = 2
MIN_TOKENS = 4

STOPWORDS = frozenset(
    "the and for are but not you all any can has have his her its our out was were "
    "with this that then than each from into more most some such only other over".split()
)


def normalise(text: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace, so prose compares cleanly."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


def content_tokens(text: str) -> set[str]:
    """Distinctive words, as a set.

    Deliberately not a contiguous-phrase match. Textbook pages wrap answer text
    around embedded figures, and the figures' axis labels land in the middle of the
    prose -- "the shapes of the *y* graphs are the same". No word-for-word run
    survives that, but the vocabulary of the page is still decisive about whether
    the right text landed on the right page.
    """
    return {
        token
        for token in normalise(text).split()
        if len(token) >= 3 and token.isalpha() and token not in STOPWORDS
    }


def coverage(tokens: set[str], pages: dict, start: int) -> float:
    """Coverage for an entry starting on `start`, allowing it to run onto the next page.

    Page numbers in the fixture mark where an entry *begins*. Answer-key entries in
    particular spill over a page break -- p-3.1-6's parts a-c sit on one page and
    d-f on the next -- and the schema has a single answer_source_page, so the start
    page alone will not contain the whole entry. Scoring the pair keeps the check
    honest without pretending each entry fits on one page.
    """
    if not tokens:
        return 1.0
    page_tokens: set[str] = set()
    for number in (start, start + 1):
        page = pages.get(number)
        if page is not None:
            page_tokens |= set(normalise(page.raw_text).split())
    return len(tokens & page_tokens) / len(tokens)


def check_placement(items, pages: dict, label: str) -> None:
    """Every item must be well covered by its page, and better than by its neighbours.

    The coverage floor catches text that did not survive extraction. The argmax
    catches the failure that actually matters here -- text extracted correctly but
    filed under the wrong page number, which is what a page_offset mistake looks
    like and what every later stage would silently inherit.
    """
    weak, misplaced = [], []

    for key, text, page_number in items:
        tokens = content_tokens(text)
        if len(tokens) < MIN_TOKENS:
            continue

        assert page_number in pages, f"{label} {key}: page {page_number} was not extracted"

        score = coverage(tokens, pages, page_number)
        if score < MIN_COVERAGE:
            weak.append((key, page_number, round(score, 2)))
            continue

        neighbours = {
            n: coverage(tokens, pages, n)
            for n in range(page_number - NEIGHBOUR_WINDOW, page_number + NEIGHBOUR_WINDOW + 1)
            if n != page_number and n in pages
        }
        best = max(neighbours.values(), default=0.0)
        if best > score:
            winner = max(neighbours, key=neighbours.__getitem__)
            misplaced.append((key, page_number, round(score, 2), winner, round(best, 2)))

    assert not weak, f"{label} not found on its recorded page (key, page, coverage): {weak}"
    assert not misplaced, (
        f"{label} matches a neighbouring page better than its own "
        f"(key, recorded, score, better_page, better_score): {misplaced}"
    )


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
def pages(fixture: dict, pdf_path: Path) -> dict[int, pdf_extraction.PageExtraction]:
    """Extract the chapter and the answer key once, keyed by PDF page number."""
    chapter = fixture["chapter"]
    source = fixture["source"]

    extracted: dict[int, pdf_extraction.PageExtraction] = {}
    ranges = [(chapter["page_start"], chapter["page_end"])]
    if source.get("answer_key_page_start"):
        ranges.append((source["answer_key_page_start"], source["answer_key_page_end"]))

    for start, end in ranges:
        for page in extract_pages(pdf_path, start, end):
            extracted[page.page_number] = page
    return extracted


# --- (2) no LLM in this stage ------------------------------------------------


def test_extraction_module_imports_nothing_that_calls_a_model():
    source = Path(pdf_extraction.__file__).read_text(encoding="utf-8")
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from ")) and "#" not in line.split("import")[0]
    ]
    joined = "\n".join(import_lines).lower()

    for forbidden in FORBIDDEN_IMPORTS:
        assert forbidden not in joined, (
            f"pdf_extraction imports {forbidden!r}. Section 6 makes this stage "
            f"deterministic; OCR is signalled with status 'ocr_required' and handled later."
        )


def test_importing_extraction_does_not_pull_in_a_model_client():
    """Import side effects count too -- a transitive import is still a dependency."""
    import subprocess
    import sys

    script = (
        "import sys; sys.path.insert(0, r'%s');"
        "import ingestion.pdf_extraction;"
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


def test_layout_lines_carry_coordinates_and_order(fixture: dict, pages: dict):
    page = pages[fixture["chapter"]["page_start"]]
    assert page.lines, "no layout lines captured; section 6 requires layout information"
    assert [line.ordinal for line in page.lines] == list(range(len(page.lines))), (
        "layout lines are not in reading order"
    )
    assert all(line.x1 >= line.x0 for line in page.lines), "line bboxes are malformed"


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
    assert row["extraction_status"] in {"pending", "extracted", "ocr_required", "failed"}
    assert row["parser"] in {"pdfplumber", "pypdf", None}
