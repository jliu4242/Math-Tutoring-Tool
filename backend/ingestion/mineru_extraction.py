"""MinerU-backed PDF extraction (replaces pdfplumber/pypdf as the Step 3 mechanical
stage -- ARCHITECTURE.md section 6 -- for the real ingestion path; pdf_extraction.py
is kept as a working fallback/reference and is untouched by this module).

Deliberately mechanical, same rule as pdf_extraction.py's own docstring: this module
imports nothing from db/ or agents/ and must never acquire an LLM call. MinerU's
`pipeline` backend is local CV/OCR/layout inference (a fixed model checkpoint, not a
billed model API), so it stays inside the mechanical/judgment split from
ARCHITECTURE.md section 4.1 -- see test_mineru_extraction.py's import guard.

Invocation is via subprocess to the `mineru` CLI, not a Python import of the mineru
package. Two reasons: the CLI's flag surface is the stable contract across MinerU's
own internal churn between major versions, and subprocess isolation keeps a crash/OOM
in the ML stack (torch/onnxruntime/PaddleOCR) from taking the FastAPI worker down.
MinerU is expected to be installed in its own environment (see
backend/requirements-mineru.txt) with its CLI on PATH, or pointed at via
MINERU_CLI_PATH -- it does not need to share this app's venv.

Page numbers: the whole upload flow is range-scoped (routers/textbooks.py caps a
single Save Textbook call at MAX_BACKGROUND_PAGES). MinerU has no notion of "pages
151-214 of this PDF"; it parses whatever file you hand it from page 1. So the
requested range is first sliced out with pypdf into its own temp PDF, and MinerU's
0-based `page_idx` (relative to that slice) is remapped back to a true 1-based PDF
page number in exactly one place: _true_page_number(). Nothing outside this module
ever sees a slice-relative index.

Unit of failure: pdf_extraction.py falls back per page (pdfplumber -> pypdf) because
each page is parsed independently. MinerU parses the whole requested range in one
subprocess call, so failure here is all-or-nothing for that call -- if the subprocess
fails or content_list.json can't be parsed, every page in the requested range comes
back with status=STATUS_FAILED rather than the call raising, so callers (background.py)
keep working with the same "iterate PageExtraction rows, check .status" pattern
pdf_extraction.py already established.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from pypdf import PdfReader, PdfWriter

# Re-exported, not reimplemented -- both extraction modules hash/count the same way.
from .pdf_extraction import compute_sha256, page_count  # noqa: F401

MINERU_CLI = os.getenv("MINERU_CLI_PATH", "mineru")
MINERU_BACKEND = "pipeline"  # CPU-capable, no GPU required -- see ARCHITECTURE.md discussion.
MINERU_TIMEOUT_SECONDS = int(os.getenv("MINERU_TIMEOUT_SECONDS", "1800"))

PARSER_NAME = "mineru-pipeline"

# textbook_pages.extraction_status. STATUS_OCR_REQUIRED does not exist here: MinerU's
# pipeline backend runs OCR internally as part of the same call, so nothing is ever
# deferred to a later OCR pass the way pdf_extraction.py signals it.
STATUS_EXTRACTED = "extracted"
STATUS_FAILED = "failed"

# content_list.json "type" values (see docs/en/reference/output_files.md upstream).
# Dropped entirely, not even kept for debugging: out of scope per the user's explicit
# "I don't care about tables" -- and for these target textbooks the answer key is
# confirmed to be plain sequential text, not a typeset table, so nothing load-bearing
# is lost by dropping this type.
DROPPED_BLOCK_TYPES = frozenset({"table"})

# Bucketed separately from `blocks` into `images`, not inserted as content_blocks rows
# (content_blocks.content is `text not null`, which doesn't fit an image). Kept so a
# problem's source_ref can still point at "there is a figure here" -- matters for
# geometry/graphing problems that depend on a figure the text alone doesn't carry.
IMAGE_BLOCK_TYPES = frozenset({"image", "chart"})

# Page furniture: real content_list.json entries, kept in `blocks` (the layout/debug
# payload) but excluded from the flattened `raw_text` string, since they're noise for
# both the structure-identification prompt and the anchor-word-coverage tests.
NOISE_TEXT_TYPES = frozenset({"header", "footer", "page_number", "aside_text", "page_footnote"})


class MinerUExtractionError(Exception):
    """Raised when the requested range could not be sliced or handed to MinerU at all
    (a bad PDF, pypdf failure). Failures inside MinerU itself (subprocess exit code,
    unparsable output) are NOT raised -- see module docstring -- they come back as
    STATUS_FAILED PageExtraction rows instead, matching pdf_extraction.py's contract.
    """


@dataclass(frozen=True)
class Block:
    """One content_list.json entry, page-relative ordinal reassigned on our side.

    `type` is MinerU's own vocabulary (text, title, list, equation, code, header,
    footer, page_number, aside_text, page_footnote, ...) -- unchanged, not yet mapped
    onto this app's block_type enum. That mapping is content_extraction.py's job, not
    this module's: this stage stays mechanical and preserves what MinerU reported.
    """

    ordinal: int
    type: str
    text: str
    text_level: int | None = None
    text_format: str | None = None  # "latex" on equation blocks
    sub_type: str | None = None  # e.g. list "sub_type": ordinary vs reference-style
    bbox: tuple[float, float, float, float] | None = None
    # Position among ALL kept entries on the page (blocks and images share one
    # counter), unlike `ordinal` which is tracked per-type so page.blocks stays a
    # contiguous 0..N-1 sequence (test_blocks_carry_bbox_and_order relies on this).
    # problem_extraction needs this shared counter to tell whether a figure fell
    # between problem 12's block and problem 13's -- `ordinal` alone can't answer
    # that once blocks and images are interleaved back into one reading-order stream.
    page_position: int | None = None

    def to_json(self) -> dict[str, Any]:
        row: dict[str, Any] = {"ordinal": self.ordinal, "type": self.type, "text": self.text}
        if self.text_level is not None:
            row["text_level"] = self.text_level
        if self.text_format is not None:
            row["text_format"] = self.text_format
        if self.sub_type is not None:
            row["sub_type"] = self.sub_type
        if self.bbox is not None:
            row["bbox"] = list(self.bbox)
        if self.page_position is not None:
            row["page_position"] = self.page_position
        return row


@dataclass(frozen=True)
class ImageBlock:
    """An image/chart region. Recorded, not interpreted -- same philosophy as
    pdf_extraction.ImageRef, just sourced from MinerU's typed output instead of
    pdfplumber's raw image list.
    """

    ordinal: int
    type: str  # "image" | "chart"
    img_path: str | None
    caption: str | None
    bbox: tuple[float, float, float, float] | None = None
    page_position: int | None = None  # see Block.page_position
    # The actual image bytes, read off disk while output_dir still exists (see
    # _read_image_bytes) -- MinerU's own temp dir is rmtree'd once extract_pages
    # finishes, so this is the only chance to capture them. None when the file
    # MinerU recorded in img_path could not be found. Never put in to_json(): this
    # is a debug/layout JSONB column, not a place for raw binary.
    image_bytes: bytes | None = None

    def to_json(self) -> dict[str, Any]:
        row: dict[str, Any] = {"ordinal": self.ordinal, "type": self.type}
        if self.img_path is not None:
            row["img_path"] = self.img_path
        if self.caption is not None:
            row["caption"] = self.caption
        if self.bbox is not None:
            row["bbox"] = list(self.bbox)
        if self.page_position is not None:
            row["page_position"] = self.page_position
        return row


@dataclass(frozen=True)
class PageExtraction:
    """Everything this stage knows about one page. Same role as
    pdf_extraction.PageExtraction, block-shaped instead of line-shaped.
    """

    page_number: int
    raw_text: str
    status: str
    parser: str | None
    blocks: list[Block] = field(default_factory=list)
    images: list[ImageBlock] = field(default_factory=list)
    error: str | None = None

    @property
    def char_count(self) -> int:
        return len(self.raw_text or "")

    def to_row(self, source_id: str) -> dict[str, Any]:
        """Shape this as a textbook_pages insert (ARCHITECTURE.md section 17).

        `layout` is repurposed from pdf_extraction's TextLine[] payload to hold this
        page's raw MinerU blocks -- same role (per-page debug/geometry payload), new
        shape. `parser` records 'mineru-pipeline' so a page's provenance stays visible
        in the audit trail the same way 'pdfplumber' vs 'pypdf' did before.
        """
        return {
            "source_id": source_id,
            "page_number": self.page_number,
            "raw_text": self.raw_text,
            "extraction_status": self.status,
            "parser": self.parser,
            "layout": [block.to_json() for block in self.blocks] or None,
            "images": [image.to_json() for image in self.images] or None,
        }


def _slice_pdf(pdf_path: str | Path, start_page: int, end_page: int) -> Path:
    """Write pages [start_page, end_page] (1-based, inclusive) to a fresh temp PDF.

    MinerU has no page-range flag; it parses whatever file it's given from page 1.
    Slicing first is what keeps a single Save Textbook call bounded to the chapter the
    user actually asked for, and what makes page_idx remapping a fixed offset rather
    than something that depends on what else is in the source PDF.
    """
    try:
        reader = PdfReader(str(pdf_path))
        writer = PdfWriter()
        for index in range(start_page - 1, end_page):
            writer.add_page(reader.pages[index])

        handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        with open(handle.name, "wb") as out:
            writer.write(out)
        return Path(handle.name)
    except Exception as error:
        raise MinerUExtractionError(
            f"could not slice pages {start_page}-{end_page} out of {pdf_path}: {error}"
        ) from error


def _run_mineru(sliced_pdf: Path, output_dir: Path) -> tuple[bool, str]:
    """Invoke the mineru CLI. Returns (ok, message) -- never raises for a subprocess
    failure, since a whole-call failure has to come back as per-page STATUS_FAILED
    rows (module docstring), not an exception that skips writing anything.
    """
    cmd = [MINERU_CLI, "-p", str(sliced_pdf), "-o", str(output_dir), "-b", MINERU_BACKEND]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=MINERU_TIMEOUT_SECONDS,
            env=os.environ.copy(),
        )
    except FileNotFoundError:
        return False, (
            f"'{MINERU_CLI}' was not found on PATH -- see backend/requirements-mineru.txt "
            "for the separate install step MinerU needs"
        )
    except subprocess.TimeoutExpired:
        return False, f"mineru did not finish within {MINERU_TIMEOUT_SECONDS}s"

    if result.returncode != 0:
        tail = (result.stderr or "")[-4000:]
        return False, f"mineru exited {result.returncode}: {tail}"
    return True, ""


def _find_content_list(output_dir: Path) -> Path | None:
    """Locate the *_content_list.json MinerU wrote somewhere under output_dir.

    Globbed rather than a hardcoded path: MinerU nests output under a
    backend/method-specific subdirectory whose exact layout has not yet been
    confirmed against a real run (IMPLEMENTATION-PLAN.md Step 0 spike, still
    pending -- see mineru_extraction's entry in the swap plan). A glob survives a
    layout we have not verified; a hardcoded path would silently break the day
    MinerU's directory convention differs from what was assumed here.
    """
    matches = sorted(output_dir.rglob("*_content_list.json"))
    return matches[0] if matches else None


def _true_page_number(entry: dict[str, Any], start_page: int) -> int:
    """content_list.json's page_idx is 0-based, relative to the sliced PDF. The
    slice's page 0 is the original PDF's `start_page`, so this is the one and only
    place that offset gets applied -- see module docstring."""
    return int(entry["page_idx"]) + start_page


def _read_image_bytes(base_dir: Path, img_path: str) -> bytes | None:
    """Read a figure crop's bytes off disk, before extract_pages' `finally` rmtree's
    output_dir out from under us -- this is the only point in the pipeline where the
    file MinerU wrote still exists. img_path is relative to the directory
    content_list.json itself lives in (MinerU's own convention, typically
    "images/<hash>.jpg"); if that exact join doesn't resolve, fall back to searching
    output_dir for a file with the same name rather than giving up, since the exact
    nesting has not been pinned down against every MinerU version.
    """
    candidate = base_dir / img_path
    if not candidate.exists():
        matches = list(base_dir.rglob(Path(img_path).name))
        candidate = matches[0] if matches else None
    if candidate is None or not candidate.exists():
        return None
    try:
        return candidate.read_bytes()
    except OSError:
        return None


def _parse_content_list(content_list_path: Path, start_page: int) -> dict[int, dict[str, list]]:
    """Group content_list.json entries by true page number into {"blocks": [...],
    "images": [...]} buckets, dropping table-typed entries per DROPPED_BLOCK_TYPES.
    """
    raw = json.loads(content_list_path.read_text(encoding="utf-8"))
    base_dir = content_list_path.parent

    by_page: dict[int, dict[str, list]] = {}
    block_ordinal_on_page: dict[int, int] = {}
    image_ordinal_on_page: dict[int, int] = {}
    position_on_page: dict[int, int] = {}

    for entry in raw:
        entry_type = entry.get("type", "")
        if entry_type in DROPPED_BLOCK_TYPES:
            continue

        page_number = _true_page_number(entry, start_page)
        bucket = by_page.setdefault(page_number, {"blocks": [], "images": []})
        bbox = tuple(entry["bbox"]) if entry.get("bbox") else None
        position = position_on_page.get(page_number, 0)
        position_on_page[page_number] = position + 1

        if entry_type in IMAGE_BLOCK_TYPES:
            ordinal = image_ordinal_on_page.get(page_number, 0)
            image_ordinal_on_page[page_number] = ordinal + 1
            caption_list = entry.get("image_caption") or entry.get("chart_caption") or []
            img_path = entry.get("img_path")
            bucket["images"].append(
                ImageBlock(
                    ordinal=ordinal,
                    type=entry_type,
                    img_path=img_path,
                    caption=" ".join(caption_list) if caption_list else None,
                    bbox=bbox,
                    page_position=position,
                    image_bytes=_read_image_bytes(base_dir, img_path) if img_path else None,
                )
            )
            continue

        ordinal = block_ordinal_on_page.get(page_number, 0)
        block_ordinal_on_page[page_number] = ordinal + 1
        bucket["blocks"].append(
            Block(
                ordinal=ordinal,
                type=entry_type,
                text=entry.get("text", ""),
                text_level=entry.get("text_level"),
                text_format=entry.get("text_format"),
                sub_type=entry.get("sub_type"),
                bbox=bbox,
                page_position=position,
            )
        )

    return by_page


def _raw_text_for_page(blocks: list[Block]) -> str:
    """The flattened string used for structure-identification and the anchor-word-
    coverage tests. Excludes NOISE_TEXT_TYPES (header/footer/page_number/aside_text/
    page_footnote) -- page furniture that would only dilute both.
    """
    return "\n".join(block.text for block in blocks if block.type not in NOISE_TEXT_TYPES and block.text)


def extract_pages(
    pdf_path: str | Path,
    start_page: int | None = None,
    end_page: int | None = None,
) -> Iterator[PageExtraction]:
    """Extract a 1-based, inclusive page range via MinerU's pipeline backend.

    Mirrors pdf_extraction.extract_pages' signature and STATUS_* contract so
    background.py can swap the import with no other changes to its call site.
    Materializes all pages at once (not a lazy per-page generator like
    pdf_extraction's, since one subprocess call produces the whole range together)
    but is still typed as an Iterator for interface parity.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    total = page_count(pdf_path)
    first = 1 if start_page is None else max(1, start_page)
    last = total if end_page is None else min(total, end_page)
    if first > last:
        raise ValueError(f"empty page range: {first}-{last} (PDF has {total} pages)")

    sliced_pdf = _slice_pdf(pdf_path, first, last)
    output_dir = Path(tempfile.mkdtemp(prefix="mineru_out_"))

    try:
        ok, message = _run_mineru(sliced_pdf, output_dir)
        if ok:
            content_list_path = _find_content_list(output_dir)
            if content_list_path is None:
                ok, message = False, f"mineru ran but no *_content_list.json was found under {output_dir}"

        if not ok:
            for page_number in range(first, last + 1):
                yield PageExtraction(
                    page_number=page_number,
                    raw_text="",
                    status=STATUS_FAILED,
                    parser=PARSER_NAME,
                    error=message,
                )
            return

        by_page = _parse_content_list(content_list_path, first)
        for page_number in range(first, last + 1):
            bucket = by_page.get(page_number, {"blocks": [], "images": []})
            yield PageExtraction(
                page_number=page_number,
                raw_text=_raw_text_for_page(bucket["blocks"]),
                status=STATUS_EXTRACTED,
                parser=PARSER_NAME,
                blocks=bucket["blocks"],
                images=bucket["images"],
            )
    finally:
        try:
            os.unlink(sliced_pdf)
        except OSError:
            pass
        import shutil

        shutil.rmtree(output_dir, ignore_errors=True)
