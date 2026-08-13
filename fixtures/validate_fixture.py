"""Validate the golden chapter fixture.

The fixture is ground truth for every Phase 1 stage, so it has to be internally
consistent before any pipeline code is diffed against it. This checks structure and
cross-references only -- it cannot tell you whether the annotations match the PDF.
That part is on the human annotator.

Deliberately dependency-free so it runs without touching requirements.txt.

Usage:
    python fixtures/validate_fixture.py [path/to/golden_chapter.json]
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent
DEFAULT_FIXTURE = FIXTURE_DIR / "golden_chapter.json"
SOURCE_DIR = FIXTURE_DIR / "source"

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MATCHING_METHODS = {"deterministic", "structural", "llm", "manual"}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _require_keys(obj: dict, keys: list[str], where: str, report: Report) -> None:
    for key in keys:
        if key not in obj:
            report.error(f"{where}: missing required field '{key}'")


def validate(fixture: dict, report: Report) -> None:
    _require_keys(
        fixture,
        ["fixture_version", "annotation", "source", "chapter", "sections",
         "concepts", "worked_examples", "problems", "answers"],
        "root",
        report,
    )

    _validate_annotation(fixture.get("annotation", {}), report)
    chapter = fixture.get("chapter", {})
    source = fixture.get("source", {})
    _validate_source(source, report)
    _validate_chapter(chapter, report)

    section_keys = _validate_sections(fixture.get("sections", []), chapter, report)
    _validate_concepts(fixture.get("concepts", []), section_keys, report)
    _validate_worked_examples(fixture.get("worked_examples", []), section_keys, chapter, report)
    problem_keys = _validate_problems(
        fixture.get("problems", []), section_keys,
        {c.get("slug") for c in fixture.get("concepts", [])}, chapter, report,
    )
    _validate_answers(fixture.get("answers", []), problem_keys, source, report)
    _validate_expectations(fixture, report)


def _validate_annotation(annotation: dict, report: Report) -> None:
    _require_keys(annotation, ["annotated_by", "annotated_at", "method"], "annotation", report)

    # IMPLEMENTATION-PLAN.md Step 2: ground truth must be hand-annotated. AI-generated
    # annotations cannot serve as a check on AI pipeline stages.
    if annotation.get("method") != "manual":
        report.error(
            "annotation.method must be 'manual' -- the fixture is the check on AI stages, "
            "so it cannot itself be AI-generated"
        )
    if not (annotation.get("annotated_by") or "").strip():
        report.error("annotation.annotated_by is empty -- record who did the annotation")


def _validate_source(source: dict, report: Report) -> None:
    _require_keys(
        source,
        ["pdf_filename", "pdf_sha256", "textbook_title"],
        "source",
        report,
    )

    filename = source.get("pdf_filename")
    if filename:
        pdf_path = SOURCE_DIR / filename
        if not pdf_path.exists():
            report.error(f"source: PDF not found at {pdf_path}")
        else:
            digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            declared = source.get("pdf_sha256")
            if declared and declared != digest:
                report.error(
                    f"source: pdf_sha256 mismatch for {filename}\n"
                    f"    declared: {declared}\n"
                    f"    actual:   {digest}"
                )

    ak_start = source.get("answer_key_page_start")
    if ak_start is None:
        report.warn(
            "source.answer_key_page_start is null -- the fixture should cover an answer key "
            "so answer matching (Step 5) has something to verify against"
        )


def _validate_chapter(chapter: dict, report: Report) -> None:
    _require_keys(chapter, ["number", "title", "page_start", "page_end", "ordinal"], "chapter", report)
    start, end = chapter.get("page_start"), chapter.get("page_end")
    if isinstance(start, int) and isinstance(end, int) and end < start:
        report.error(f"chapter: page_end ({end}) is before page_start ({start})")


def _in_chapter(page: object, chapter: dict) -> bool:
    start, end = chapter.get("page_start"), chapter.get("page_end")
    if not all(isinstance(v, int) for v in (page, start, end)):
        return True
    return start <= page <= end


def _validate_sections(sections: list, chapter: dict, report: Report) -> set[str]:
    keys: set[str] = set()
    for i, section in enumerate(sections):
        where = f"sections[{i}]"
        _require_keys(section, ["key", "title", "ordinal", "page_start", "page_end"], where, report)
        key = section.get("key")
        if key in keys:
            report.error(f"{where}: duplicate section key '{key}'")
        if key:
            keys.add(key)

        start, end = section.get("page_start"), section.get("page_end")
        if isinstance(start, int) and isinstance(end, int) and end < start:
            report.error(f"{where} ('{key}'): page_end ({end}) is before page_start ({start})")
        for field in ("page_start", "page_end"):
            if not _in_chapter(section.get(field), chapter):
                report.error(f"{where} ('{key}'): {field}={section.get(field)} falls outside the chapter page range")

    if not sections:
        report.error("no sections annotated -- Step 4 verifies section identification against this list")

    # Sections are a flat list; nesting was removed deliberately, so there is no
    # parent_key to resolve and no cycle to detect.
    return keys


def _validate_concepts(concepts: list, section_keys: set[str], report: Report) -> None:
    slugs: set[str] = set()
    for i, concept in enumerate(concepts):
        where = f"concepts[{i}]"
        _require_keys(concept, ["slug", "canonical_name", "section_keys"], where, report)
        slug = concept.get("slug")
        if slug in slugs:
            report.error(f"{where}: duplicate concept slug '{slug}'")
        if slug:
            slugs.add(slug)
            if not SLUG_RE.match(slug):
                report.error(f"{where}: slug '{slug}' is not kebab-case")
        for section_key in concept.get("section_keys") or []:
            if section_key not in section_keys:
                report.error(f"{where} ('{slug}'): section_keys references unknown section '{section_key}'")

    if not concepts:
        report.error("no concepts annotated -- Step 4 verifies concept identification against this list")

    covered = {sk for c in concepts for sk in (c.get("section_keys") or [])}
    for missing in sorted(section_keys - covered):
        report.warn(f"section '{missing}' has no concept assigned")


def _validate_worked_examples(examples: list, section_keys: set[str], chapter: dict, report: Report) -> None:
    keys: set[str] = set()
    for i, example in enumerate(examples):
        where = f"worked_examples[{i}]"
        _require_keys(
            example,
            ["key", "section_key", "example_number", "page_number", "ordinal", "problem_text"],
            where, report,
        )
        key = example.get("key")
        if key in keys:
            report.error(f"{where}: duplicate worked example key '{key}'")
        if key:
            keys.add(key)
        if example.get("section_key") not in section_keys:
            report.error(f"{where} ('{key}'): unknown section_key '{example.get('section_key')}'")
        if not _in_chapter(example.get("page_number"), chapter):
            report.error(f"{where} ('{key}'): page_number {example.get('page_number')} is outside the chapter page range")

    if not examples:
        report.warn("no worked examples annotated -- Step 5 keeps these separate from problems (spec section 11)")


def _validate_problems(
    problems: list, section_keys: set[str], concept_slugs: set[str], chapter: dict, report: Report,
) -> set[str]:
    keys: set[str] = set()
    seen_numbers: dict[tuple, str] = {}

    for i, problem in enumerate(problems):
        where = f"problems[{i}]"
        _require_keys(
            problem,
            ["key", "section_key", "problem_number", "page_number", "ordinal", "body_plain"],
            where, report,
        )
        key = problem.get("key")
        if key in keys:
            report.error(f"{where}: duplicate problem key '{key}'")
        if key:
            keys.add(key)

        section_key = problem.get("section_key")
        if section_key not in section_keys:
            report.error(f"{where} ('{key}'): unknown section_key '{section_key}'")

        if not _in_chapter(problem.get("page_number"), chapter):
            report.error(f"{where} ('{key}'): page_number {problem.get('page_number')} is outside the chapter page range")

        if not (problem.get("body_plain") or "").strip():
            report.error(f"{where} ('{key}'): body_plain is empty")

        number = problem.get("problem_number")
        if number is not None:
            slot = (section_key, number)
            if slot in seen_numbers:
                report.error(
                    f"{where} ('{key}'): problem_number '{number}' already used in section "
                    f"'{section_key}' by '{seen_numbers[slot]}'"
                )
            else:
                seen_numbers[slot] = key or ""

        for slug in problem.get("concept_slugs") or []:
            if slug not in concept_slugs:
                report.error(f"{where} ('{key}'): concept_slugs references unknown concept '{slug}'")

    if not problems:
        report.error("no problems annotated -- the fixture cannot verify Step 5 without them")
    return keys


def _validate_answers(answers: list, problem_keys: set[str], source: dict, report: Report) -> None:
    seen: set[str] = set()
    has_answer_only = False
    has_full_solution = False
    has_ambiguous = False

    for i, answer in enumerate(answers):
        where = f"answers[{i}]"
        _require_keys(
            answer,
            ["problem_key", "answer_text", "answer_source_page", "solution_text", "expected_matching_method"],
            where, report,
        )

        problem_key = answer.get("problem_key")
        if problem_key not in problem_keys:
            report.error(f"{where}: problem_key '{problem_key}' does not match any annotated problem")
        elif problem_key in seen:
            report.error(f"{where}: problem '{problem_key}' has more than one answer entry")
        else:
            seen.add(problem_key)

        method = answer.get("expected_matching_method")
        if method not in MATCHING_METHODS:
            report.error(f"{where}: expected_matching_method '{method}' is not one of {sorted(MATCHING_METHODS)}")

        if answer.get("solution_text") is None:
            has_answer_only = True
        else:
            has_full_solution = True

        confidence_max = answer.get("expected_confidence_max")
        if method == "llm":
            has_ambiguous = True
            # Step 5: the ambiguous case must be flagged with lower confidence, not
            # silently treated as certain. Without a ceiling the test cannot catch that.
            if confidence_max is None:
                report.error(
                    f"{where} ('{problem_key}'): expected_matching_method is 'llm' but "
                    "expected_confidence_max is null -- set a ceiling so an over-confident match fails"
                )
            elif confidence_max >= 1.0:
                report.error(f"{where} ('{problem_key}'): expected_confidence_max must be below 1.0 for an LLM match")

        if confidence_max is not None and not (0 <= confidence_max <= 1):
            report.error(f"{where}: expected_confidence_max {confidence_max} is outside [0, 1]")

        page = answer.get("answer_source_page")
        ak_start, ak_end = source.get("answer_key_page_start"), source.get("answer_key_page_end")
        if isinstance(page, int) and isinstance(ak_start, int) and isinstance(ak_end, int):
            if not ak_start <= page <= ak_end:
                report.warn(
                    f"{where} ('{problem_key}'): answer_source_page {page} is outside the "
                    f"declared answer key range {ak_start}-{ak_end}"
                )

    # IMPLEMENTATION-PLAN.md Step 2 requires all three of these in the fixture.
    if not has_answer_only:
        report.error("fixture has no answer-only entry (solution_text: null) -- Step 2 requires a mix")
    if not has_full_solution:
        report.error("fixture has no fully-worked solution entry -- Step 2 requires a mix")
    if not has_ambiguous:
        report.error(
            "fixture has no entry with expected_matching_method 'llm' -- Step 2 requires an "
            "ambiguous numbering case (e.g. 17a/17b vs 17) to exercise the section 14 hierarchy"
        )

    unanswered = sorted(problem_keys - seen)
    if unanswered:
        report.warn(f"{len(unanswered)} problem(s) have no answer entry: {', '.join(unanswered[:10])}")


def _validate_expectations(fixture: dict, report: Report) -> None:
    expectations = fixture.get("expectations")
    if not expectations:
        return

    answers = fixture.get("answers", [])
    actual = {
        "problem_count": len(fixture.get("problems", [])),
        "worked_example_count": len(fixture.get("worked_examples", [])),
        "answer_only_count": sum(1 for a in answers if a.get("solution_text") is None),
        "full_solution_count": sum(1 for a in answers if a.get("solution_text") is not None),
    }
    for field, expected in expectations.items():
        if field in actual and expected != actual[field]:
            report.error(f"expectations.{field} says {expected} but the fixture contains {actual[field]}")


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_FIXTURE

    if not path.exists():
        print(f"FAIL  fixture not found: {path}")
        return 2

    try:
        fixture = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL  {path} is not valid JSON: {exc}")
        return 2

    report = Report()
    validate(fixture, report)

    for warning in report.warnings:
        print(f"WARN  {warning}")
    for error in report.errors:
        print(f"ERROR {error}")

    print()
    if report.errors:
        print(f"FAIL  {path.name}: {len(report.errors)} error(s), {len(report.warnings)} warning(s)")
        return 1

    print(f"OK    {path.name}: valid ({len(report.warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
