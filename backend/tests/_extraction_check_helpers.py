"""Shared anchor-word-coverage checking, extracted out of test_pdf_extraction.py so
test_mineru_extraction.py can reuse the same verification strategy against a
different extraction backend's output instead of duplicating it.

The strategy itself (why tokens, why coverage, why the neighbour argmax) is explained
in test_pdf_extraction.py's module docstring -- nothing about the *reasoning* changed
by moving the code here, only its location.
"""

from __future__ import annotations

import re

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
    particular spill over a page break, and the schema has a single answer_source_page,
    so the start page alone will not contain the whole entry. Scoring the pair keeps
    the check honest without pretending each entry fits on one page.

    `pages` maps page_number -> an object with a `.raw_text` attribute -- either
    backend's PageExtraction satisfies this.
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
