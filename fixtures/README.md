# Golden chapter fixture

Ground truth for Phase 1. Every later stage of the ingestion pipeline is verified by
diffing its output against this fixture. Per `IMPLEMENTATION-PLAN.md`, a mismatch is a
bug — not "close enough".

## Files

| File | Purpose |
| --- | --- |
| `golden_chapter.json` | The real ground truth. **Does not exist yet** — create it from the template. |
| `golden_chapter.template.json` | Empty skeleton to copy and fill in. |
| `golden_chapter.example.json` | Illustrative only. Shows the shape of every field. Never use as ground truth. |
| `golden_chapter.schema.json` | JSON Schema, for editor autocomplete and validation. |
| `validate_fixture.py` | Structural + cross-reference validator. No third-party dependencies. |
| `source/` | The source PDF. Git-ignored — see below. |

## Annotate by hand, not with AI

`IMPLEMENTATION-PLAN.md` Step 2 requires manual annotation, and the validator enforces
`annotation.method == "manual"`.

The reason is not process purism. This fixture is the only check on the AI-dependent
stages (structure identification, concept extraction, answer matching). Those stages
produce plausible-looking output when they are wrong. If the ground truth is generated
the same way, both sides make the same mistake and the test passes while the pipeline is
broken.

## Choosing a chapter

Step 2 asks for a chapter with both of these. The validator fails without them:

1. **A mix of answer-only and fully-worked answer key entries** — at least one `answers[]`
   entry with `solution_text: null` and at least one with real solution text. Per
   `ARCHITECTURE.md` section 13, an answer key entry is not a solution and must never be
   backfilled with a guess.
2. **An ambiguous numbering case** — e.g. the exercise set prints `17a`/`17b` while the
   answer key prints a single `17.`. Mark it `expected_matching_method: "llm"` with an
   `expected_confidence_max` below 1.0, so Step 5 can assert the pipeline resolved it via
   the LLM tier *and* flagged it as uncertain rather than silently claiming certainty.

## Adding the PDF

Put the PDF in `fixtures/source/`, then record its name and hash in the fixture:

```bash
python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" fixtures/source/YOUR.pdf
```

`fixtures/source/` is git-ignored — textbook PDFs are copyrighted and should not be
committed. Keep the file locally and share it out of band. The `pdf_sha256` in the
fixture is what pins the annotations to a specific file, so anyone re-running the tests
can confirm they have the same PDF.

## Page numbers

**Every page number in the fixture is a 1-based PDF page index**, not the number printed
on the page. Record the difference once in `source.page_offset`, where:

```
printed_page_number + page_offset = pdf_page_index
```

This matters because the extraction stage only ever sees PDF indices, and an answer key
is often hundreds of pages away from the problem it answers.

## Validating

```bash
python fixtures/validate_fixture.py
```

It checks internal consistency: cross-references resolve, page ranges nest inside the
chapter, section parents form no cycles, no duplicate problem numbers within a section,
the Step 2 required cases are present, and the declared `pdf_sha256` matches the file on
disk.

It **cannot** check that your annotations match what the PDF actually says. That part is
the whole point of doing it by hand.
