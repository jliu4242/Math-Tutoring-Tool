"""PDF extraction — Phase 1 Step 3 (ARCHITECTURE.md section 6).

The first processing stage, and a deterministic one. pdfplumber is the primary
parser and pypdf the fallback, chosen per page rather than per document: a single
malformed page should not force the whole chapter onto the weaker parser.

This module deliberately imports nothing from db/ and nothing from agents/. It has
no LLM call in it and must not acquire one -- section 6 reaches for a model only
when a page needs OCR, and that is a later decision made from `ocr_required`, not
something this stage does inline. IMPLEMENTATION-PLAN.md Step 3 verifies the
absence, so an import added here will fail the test suite.

What gets preserved, per section 6:

    page number          -> PageExtraction.page_number (1-based PDF index)
    extracted text       -> raw_text
    text ordering        -> lines[], in reading order
    source coordinates   -> each line's bbox
    heading signal        -> each line's font size (points), for heading detection
    image/figure refs    -> images[], with bboxes
    original PDF ref     -> pdf_sha256 + pdf_filename

Nothing here interprets the page. Deciding what a heading means, where a chapter
starts, or which problem is which is Step 4's job.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import pdfplumber
from pypdf import PdfReader

# Column handling. pdfplumber's extract_text() walks the page in raster order, so on
# a two-column page it reads straight across the gutter and interleaves both columns:
#
#     4. C            b) The shapes of the      ->   "4. C b) The shapes of the"
#     5. D            graphs are the same            "5. D graphs are the same"
#
# Textbook exercise sets and answer keys are almost always multi-column, so taking
# that text at face value would corrupt every downstream stage. Instead we use the
# line bounding boxes -- which is what pdfplumber is actually good at -- to find the
# vertical gutters and reassemble the page in reading order.
MIN_GUTTER_WIDTH = 10.0
# A line wider than this fraction of the text area spans columns (a header, a footer,
# a full-width heading) and must not be treated as evidence against a gutter.
MAX_COLUMN_LINE_RATIO = 0.6
# Fraction of rows allowed to cross a band and still call it a gutter. Demanding a
# completely empty band fails on pages with figures: a parabola's axis labels and
# tick numbers scatter across the gutter and plug the gap, even though the body text
# never crosses it. Counting rows rather than words keeps one busy figure from
# outvoting thirty rows of text.
GUTTER_ROW_TOLERANCE = 0.15
# Ignore quiet bands this close to either edge -- those are margins and indents.
GUTTER_EDGE_MARGIN = 0.12

# textbook_pages.extraction_status (supabase/migrations/..._phase1_enums.sql).
STATUS_EXTRACTED = "extracted"
STATUS_OCR_REQUIRED = "ocr_required"
STATUS_FAILED = "failed"

PARSER_PRIMARY = "pdfplumber"
PARSER_FALLBACK = "pypdf"


@dataclass(frozen=True)
class TextLine:
    """One line of text with the box it occupied on the page."""

    ordinal: int
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    size: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "text": self.text,
            "x0": round(self.x0, 2),
            "top": round(self.top, 2),
            "x1": round(self.x1, 2),
            "bottom": round(self.bottom, 2),
            "size": round(self.size, 1),
        }


@dataclass(frozen=True)
class ImageRef:
    """An image or figure on the page. Recorded, not interpreted."""

    ordinal: int
    x0: float
    top: float
    x1: float
    bottom: float

    def to_json(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "x0": round(self.x0, 2),
            "top": round(self.top, 2),
            "x1": round(self.x1, 2),
            "bottom": round(self.bottom, 2),
            "width": round(self.x1 - self.x0, 2),
            "height": round(self.bottom - self.top, 2),
        }


@dataclass(frozen=True)
class PageExtraction:
    """Everything Step 3 knows about one page."""

    page_number: int
    raw_text: str | None
    status: str
    parser: str | None
    lines: list[TextLine] = field(default_factory=list)
    images: list[ImageRef] = field(default_factory=list)
    error: str | None = None

    @property
    def char_count(self) -> int:
        return len(self.raw_text or "")

    def to_row(self, source_id: str) -> dict[str, Any]:
        """Shape this as a textbook_pages insert."""
        return {
            "source_id": source_id,
            "page_number": self.page_number,
            "raw_text": self.raw_text,
            "extraction_status": self.status,
            "parser": self.parser,
            "layout": [line.to_json() for line in self.lines] or None,
            "images": [image.to_json() for image in self.images] or None,
        }


def compute_sha256(pdf_path: str | Path) -> str:
    """Hash the source PDF. This is what pins extracted pages to a specific file."""
    digest = hashlib.sha256()
    with open(pdf_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def page_count(pdf_path: str | Path) -> int:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def _rows_from_words(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group words into visual rows by vertical position, ignoring columns."""
    rows: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    for word in sorted(words, key=lambda word: (word["top"], word["x0"])):
        if not current:
            current = [word]
            continue
        reference = current[0]
        tolerance = max(2.0, (reference["bottom"] - reference["top"]) * 0.6)
        if abs(word["top"] - reference["top"]) <= tolerance:
            current.append(word)
        else:
            rows.append(current)
            current = [word]

    if current:
        rows.append(current)
    return rows


def _detect_gutters(rows: list[list[dict[str, Any]]]) -> list[tuple[float, float]]:
    """Find vertical bands that almost no row crosses. Those are the column gutters.

    Works on a projection profile: for each 1pt column of the page, count how many
    rows have a word overlapping it. Body text in a two-column layout leaves a deep
    trough at the gutter. Counting rows rather than words is what makes this survive
    figures -- a graph's tick labels may straddle the gutter, but they belong to a
    handful of rows and cannot outvote the rest of the page.
    """
    words = [word for row in rows for word in row]
    if len(rows) < 8 or len(words) < 20:
        return []

    left = min(word["x0"] for word in words)
    right = max(word["x1"] for word in words)
    width = right - left
    if width <= 0:
        return []

    bins = int(math.ceil(width)) + 1
    counts = [0] * bins

    for row in rows:
        touched = bytearray(bins)
        # A row spanning nearly the whole width is a header or full-width heading.
        # It legitimately crosses the gutter, so it should not vote against one.
        span = max(word["x1"] for word in row) - min(word["x0"] for word in row)
        if span > MAX_COLUMN_LINE_RATIO * width and len(row) > 3:
            continue
        for word in row:
            start = max(0, int(word["x0"] - left))
            end = min(bins, int(math.ceil(word["x1"] - left)))
            for i in range(start, end):
                touched[i] = 1
        for i in range(bins):
            if touched[i]:
                counts[i] += 1

    threshold = max(1, int(len(rows) * GUTTER_ROW_TOLERANCE))
    margin = int(width * GUTTER_EDGE_MARGIN)

    gutters: list[tuple[float, float]] = []
    run_start: int | None = None

    for i in range(bins + 1):
        quiet = i < bins and counts[i] <= threshold
        if quiet:
            if run_start is None:
                run_start = i
        elif run_start is not None:
            inside = run_start > margin and i < bins - margin
            if inside and (i - run_start) >= MIN_GUTTER_WIDTH:
                gutters.append((left + run_start, left + i))
            run_start = None

    return gutters


def _column_index(line: dict[str, Any], gutters: list[tuple[float, float]]) -> int:
    midpoint = (line["x0"] + line["x1"]) / 2
    return sum(1 for start, end in gutters if midpoint > (start + end) / 2)


def _spans_gutter(line: dict[str, Any], gutters: list[tuple[float, float]]) -> bool:
    return any(line["x0"] < start and line["x1"] > end for start, end in gutters)


def _order_lines(
    lines: list[dict[str, Any]], gutters: list[tuple[float, float]]
) -> list[dict[str, Any]]:
    """Reading order: down each column, left to right, split at full-width lines.

    Splitting at spanning lines matters -- a mid-page heading or a footer would
    otherwise be sorted into whichever column its midpoint happened to fall in,
    and everything below it would be read in the wrong order.
    """
    if not gutters:
        return sorted(lines, key=lambda line: (line["top"], line["x0"]))

    def by_column(block: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(block, key=lambda line: (_column_index(line, gutters), line["top"], line["x0"]))

    ordered: list[dict[str, Any]] = []
    block: list[dict[str, Any]] = []

    for line in sorted(lines, key=lambda line: line["top"]):
        if _spans_gutter(line, gutters):
            ordered.extend(by_column(block))
            block = []
            ordered.append(line)
        else:
            block.append(line)

    ordered.extend(by_column(block))
    return ordered


def _merge_words(words: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(words, key=lambda word: word["x0"])
    return {
        "text": " ".join(word["text"] for word in ordered),
        "x0": min(word["x0"] for word in ordered),
        "x1": max(word["x1"] for word in ordered),
        "top": min(word["top"] for word in ordered),
        "bottom": max(word["bottom"] for word in ordered),
        # Headings are rarely mixed-size within one line, so the max across the
        # line's words is a safe stand-in for "this line's font size".
        "size": max((word.get("size") or 0.0) for word in ordered),
    }


def _lines_from_words(
    rows: list[list[dict[str, Any]]], gutters: list[tuple[float, float]]
) -> list[dict[str, Any]]:
    """Turn rows into lines, never letting one line straddle a gutter.

    Each row is cut at the gutters, so a row of two-column text becomes one line per
    column rather than a single line reading straight across the page.
    """
    lines: list[dict[str, Any]] = []
    for row in rows:
        if not gutters:
            lines.append(_merge_words(row))
            continue
        by_column: dict[int, list[dict[str, Any]]] = {}
        for word in row:
            by_column.setdefault(_column_index(word, gutters), []).append(word)
        for column in sorted(by_column):
            lines.append(_merge_words(by_column[column]))

    return lines


def _extract_with_pdfplumber(page: Any) -> tuple[str, list[TextLine], list[ImageRef]]:
    words: list[dict[str, Any]] = []
    try:
        words = [
            {
                "text": word.get("text", ""),
                "x0": float(word["x0"]),
                "top": float(word["top"]),
                "x1": float(word["x1"]),
                "bottom": float(word["bottom"]),
                "size": float(word.get("size") or 0.0),
            }
            # extra_attrs=["size"] pulls font size onto each word (pdfplumber splits
            # a word at a size change, which is exactly what we want at a heading
            # boundary). Chapter/section titles are reliably the largest text on
            # their page, which is the signal structure_agent uses to tell a chapter
            # heading apart from body text.
            for word in page.extract_words(extra_attrs=["size"])
        ]
    except Exception:
        words = []

    if words:
        rows = _rows_from_words(words)
        gutters = _detect_gutters(rows)
        ordered = _order_lines(_lines_from_words(rows, gutters), gutters)
        text = "\n".join(line["text"] for line in ordered)
    else:
        # No line geometry available -- fall back to whatever raster-order text there is.
        ordered = []
        text = page.extract_text() or ""

    lines = [
        TextLine(
            ordinal=ordinal,
            text=line["text"],
            x0=line["x0"],
            top=line["top"],
            x1=line["x1"],
            bottom=line["bottom"],
            size=line.get("size", 0.0),
        )
        for ordinal, line in enumerate(ordered)
    ]

    images: list[ImageRef] = []
    for ordinal, image in enumerate(page.images or []):
        images.append(
            ImageRef(
                ordinal=ordinal,
                x0=float(image.get("x0", 0.0)),
                top=float(image.get("top", 0.0)),
                x1=float(image.get("x1", 0.0)),
                bottom=float(image.get("bottom", 0.0)),
            )
        )

    return text, lines, images


def _status_for(text: str, images: list[ImageRef]) -> str:
    """A page with figures but no text is the OCR case; a genuinely blank page is not."""
    if text.strip():
        return STATUS_EXTRACTED
    return STATUS_OCR_REQUIRED if images else STATUS_EXTRACTED


def extract_pages(
    pdf_path: str | Path,
    start_page: int | None = None,
    end_page: int | None = None,
) -> Iterator[PageExtraction]:
    """Extract a 1-based, inclusive page range. Omit both bounds for the whole PDF.

    Yields lazily so a 600-page textbook does not have to sit in memory at once.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    fallback_reader: PdfReader | None = None

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        first = 1 if start_page is None else max(1, start_page)
        last = total if end_page is None else min(total, end_page)

        if first > last:
            raise ValueError(f"empty page range: {first}-{last} (PDF has {total} pages)")

        for page_number in range(first, last + 1):
            try:
                text, lines, images = _extract_with_pdfplumber(pdf.pages[page_number - 1])
                yield PageExtraction(
                    page_number=page_number,
                    raw_text=text,
                    status=_status_for(text, images),
                    parser=PARSER_PRIMARY,
                    lines=lines,
                    images=images,
                )
                continue
            except Exception as primary_error:
                primary_message = f"{type(primary_error).__name__}: {primary_error}"

            # Fall back for this page only. Text without layout beats no page at all.
            try:
                if fallback_reader is None:
                    fallback_reader = PdfReader(str(pdf_path))
                text = fallback_reader.pages[page_number - 1].extract_text() or ""
                yield PageExtraction(
                    page_number=page_number,
                    raw_text=text,
                    status=_status_for(text, []),
                    parser=PARSER_FALLBACK,
                    error=f"pdfplumber failed, used pypdf ({primary_message})",
                )
            except Exception as fallback_error:
                yield PageExtraction(
                    page_number=page_number,
                    raw_text=None,
                    status=STATUS_FAILED,
                    parser=None,
                    error=(
                        f"both parsers failed -- pdfplumber: {primary_message}; "
                        f"pypdf: {type(fallback_error).__name__}: {fallback_error}"
                    ),
                )
