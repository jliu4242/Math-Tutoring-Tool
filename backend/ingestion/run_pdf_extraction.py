"""Run Phase 1 Step 3 (PDF extraction) on its own.

IMPLEMENTATION-PLAN.md Step 4 requires each stage to be independently runnable
without the next stage having to run. This is that entry point for extraction.

Run from the backend/ directory:

    python -m ingestion.run_pdf_extraction --fixture ../fixtures/golden_chapter.example.json
    python -m ingestion.run_pdf_extraction --pdf ../fixtures/source/book.pdf --start 151 --end 214
    python -m ingestion.run_pdf_extraction --fixture ... --json pages.json

Persisting is opt-in. Without --persist this touches no database at all, which is
what makes it usable before Supabase credentials exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .pdf_extraction import (
    STATUS_FAILED,
    STATUS_OCR_REQUIRED,
    PageExtraction,
    compute_sha256,
    extract_pages,
    page_count,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "fixtures"


def _load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _ranges_from_fixture(fixture: dict) -> tuple[list[tuple[int, int]], Path]:
    """The chapter and the answer key, as two separate ranges.

    They must stay separate. The answer key sits hundreds of pages past the chapter
    (section 15), so spanning from one to the other would extract the entire second
    half of the book to reach fourteen pages of answers.
    """
    chapter = fixture.get("chapter", {})
    source = fixture.get("source", {})

    ranges: list[tuple[int, int]] = []
    if isinstance(chapter.get("page_start"), int) and isinstance(chapter.get("page_end"), int):
        ranges.append((chapter["page_start"], chapter["page_end"]))

    key_start = source.get("answer_key_page_start")
    if isinstance(key_start, int):
        key_end = source.get("answer_key_page_end")
        ranges.append((key_start, key_end if isinstance(key_end, int) else key_start))

    if not ranges:
        raise SystemExit("fixture has no usable page ranges")

    pdf_path = FIXTURE_DIR / "source" / source.get("pdf_filename", "")
    return ranges, pdf_path


def _summarise(pages: list[PageExtraction]) -> None:
    by_status = Counter(p.status for p in pages)
    by_parser = Counter(p.parser or "none" for p in pages)
    total_chars = sum(p.char_count for p in pages)
    total_images = sum(len(p.images) for p in pages)
    empty = [p.page_number for p in pages if not (p.raw_text or "").strip()]

    print(f"\npages extracted : {len(pages)}")
    print(f"characters      : {total_chars:,}")
    print(f"images/figures  : {total_images}")
    print(f"status          : {dict(by_status)}")
    print(f"parser          : {dict(by_parser)}")

    if empty:
        shown = ", ".join(str(n) for n in empty[:15])
        more = f" (+{len(empty) - 15} more)" if len(empty) > 15 else ""
        print(f"empty pages     : {shown}{more}")

    problems = [p for p in pages if p.status in (STATUS_FAILED, STATUS_OCR_REQUIRED)]
    for page in problems[:20]:
        detail = f" -- {page.error}" if page.error else ""
        print(f"  page {page.page_number}: {page.status}{detail}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Phase 1 Step 3 — PDF extraction")
    parser.add_argument("--pdf", type=Path, help="path to the source PDF")
    parser.add_argument(
        "--fixture",
        type=Path,
        nargs="?",
        const=FIXTURE_DIR / "golden_chapter.json",
        help="take the PDF and page range from a fixture file",
    )
    parser.add_argument("--start", type=int, help="first PDF page (1-based, inclusive)")
    parser.add_argument("--end", type=int, help="last PDF page (1-based, inclusive)")
    parser.add_argument("--json", type=Path, help="write extracted pages to this file")
    parser.add_argument("--persist", action="store_true", help="write to textbook_pages")
    parser.add_argument("--textbook-id", help="required with --persist")
    parser.add_argument("--storage-path", default="", help="object-storage path of the PDF")
    args = parser.parse_args(argv[1:])

    pdf_path = args.pdf
    ranges: list[tuple[int, int]] = []

    if args.fixture:
        if not args.fixture.exists():
            print(f"FAIL  fixture not found: {args.fixture}")
            return 2
        fixture_ranges, fixture_pdf = _ranges_from_fixture(_load_fixture(args.fixture))
        pdf_path = pdf_path or fixture_pdf
        ranges = fixture_ranges

    # An explicit range wins over whatever the fixture said.
    if args.start is not None or args.end is not None:
        ranges = [(args.start or 1, args.end or 10**9)]

    if pdf_path is None:
        print("FAIL  give --pdf or --fixture")
        return 2
    if not Path(pdf_path).exists():
        print(f"FAIL  PDF not found: {pdf_path}")
        return 2

    if args.persist and not args.textbook_id:
        print("FAIL  --persist needs --textbook-id")
        return 2

    total = page_count(pdf_path)
    if not ranges:
        ranges = [(1, total)]
    ranges = [(start, min(end, total)) for start, end in ranges]

    print(f"pdf             : {pdf_path}")
    print(f"pages in file   : {total}")
    print("extracting      : " + ", ".join(f"{s}-{e}" for s, e in ranges))

    pages: list[PageExtraction] = []
    for start, end in ranges:
        pages.extend(extract_pages(pdf_path, start, end))
    _summarise(pages)

    if args.json:
        args.json.write_text(
            json.dumps([p.to_row(source_id="") for p in pages], indent=2),
            encoding="utf-8",
        )
        print(f"\nwrote {args.json}")

    if args.persist:
        from .persistence import ensure_source, write_pages

        digest = compute_sha256(pdf_path)
        source_id = ensure_source(
            textbook_id=args.textbook_id,
            file_hash=digest,
            storage_path=args.storage_path or str(pdf_path),
            page_count=total,
        )
        written = write_pages(source_id, pages)
        print(f"\nsource_id       : {source_id}")
        print(f"rows written    : {written}")

    return 1 if any(p.status == STATUS_FAILED for p in pages) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
