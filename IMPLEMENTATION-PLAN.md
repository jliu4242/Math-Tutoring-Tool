Phase 1 Implementation Prompt — Textbook Ingestion Pipeline

Reference: architecture.md in this repo is the full architecture spec. Read it before starting — this document tells you the order and verification discipline to follow while implementing it. Do not implement Phase 2 (variation generation) as part of this work; this covers Phase 1 only.

Core rule for this whole implementation: do not move to the next step until the current step's verification criteria pass against the golden fixture (built in Step 2). Deterministic stages (PDF extraction, raw problem extraction, schema, orchestration) can be generated in full confidently. AI-dependent stages (structure identification, concept extraction, variation clustering, answer matching) must be checked against ground truth before being trusted — they will produce plausible-looking output even when wrong, and errors here are expensive to catch later.

Step 1 — Turn the schema into real migrations first

Convert the schema in architecture.md sections 17–25 directly into Supabase migrations before writing any pipeline code:

textbooks, textbook_sources, textbook_pages
chapters, sections (flat list within a chapter — no parent_section_id, spec section 17)
content_blocks (generic content table, block_type enum: explanation, definition, theorem, rule, example, exercise_intro, note, summary)
problems, worked_examples
concepts, section_concepts, problem_concepts (including variation_key and is_representative, spec section 22)
problem_answers, problem_solutions (problem_solutions.source is required — textbook or generated, spec section 24)
ingestion_runs (status + stage tracking, including the variation_clustering stage)

Deliverable: applied migrations, schema matches spec exactly, foreign keys and composite primary keys in place (e.g. problem_concepts(problem_id, concept_id)), plus the partial unique index enforcing one representative per variation: UNIQUE (concept_id, variation_key) WHERE is_representative.

Verification: every table in section 17–25 exists with the specified columns; no pipeline code depends on tables that don't exist yet.

Step 2 — Build a template for one golden fixture

Pick a single real textbook chapter to use as ground truth for every stage below. Prefer a chapter with:

A mix of answer-only and fully-worked-solution answer key entries
At least one case of ambiguous problem/answer numbering (e.g. 17a/17b vs 17) to exercise the matching hierarchy in spec section 14

Hand-annotate (manually, not with AI) the correct:

Chapter/section boundaries and page ranges
Every problem number, page, and body text
Every worked example
Concept assignments per section
Variation grouping per concept, and which problem represents each variation (this is the ground truth Step 4c is diffed against)
Correct answer-to-problem mapping, including which entries are answer-only vs. have full solutions

Deliverable: a fixture file (e.g. fixtures/golden_chapter.json) with this ground truth, plus the source PDF pages it covers.

Verification: this fixture is what every later step's automated tests run against — treat mismatches against it as bugs, not as "close enough."

Step 3 — Implement PDF extraction alone, verify against the fixture

Build the extraction stage per spec section 6:

pdfplumber as primary parser, pypdf as fallback
Extract raw text, image/figure references, layout info per page
Preserve page number, extracted text, source coordinates where useful, text ordering, original PDF reference
No LLM at this stage unless OCR is required

Deliverable: extraction runs on the fixture's PDF pages and writes to textbook_pages.

Verification: extracted raw text for the fixture's pages matches the source PDF (spot-check against the fixture); no LLM calls made in this stage.

Step 4 — Implement structure + concept identification, one stage at a time

Implement as separate, independently runnable steps — do not combine with problem extraction:

Chapter identification (spec section 7)
Section identification as a flat list — a printed "3.2.1" heading is either its own top-level section or folded into 3.2 (spec section 17)
Concept identification per section (spec section 9), populating concepts and section_concepts

Batch concept identification into one call for the whole chapter if you like — but keep the output attributed per section (spec section 9.1). The verification gate below is a per-section diff, and a chapter-level blob cannot be diffed section by section, so a concept attached to the wrong section would pass unnoticed.

Deliverable: each sub-step callable independently, writing to its own tables, without requiring the next sub-step to run.

Verification: run each sub-step against the fixture and diff its output against the hand-annotated chapter/section/concept structure before moving to the next sub-step. A wrong chapter boundary must be caught here — not discovered later via broken problem-to-section links.

Step 4b — Raw problem and worked-example extraction (mechanical, no gate)

This is a deterministic extraction stage (spec sections 10.1, 4.1), not a judgment stage, and it is independent of Step 4's concept identification — both depend only on structure identification, neither depends on the other, so they can run in either order or concurrently.

Problems → problems table (number, body_latex, body_plain, page, ordinal, source_ref)
Worked examples → worked_examples table (kept separate from problems per spec section 11)

Pull the problem number and text and nothing else. No clustering, no concept tagging, no ranking — those are Step 4c.

Deliverable: every problem and worked example in the fixture chapter present in its table.

Verification: this stage gets extraction-error checks, not a ground-truth judgment diff — there is no judgment being made. Count problems against the printed exercise set: nothing missing, nothing empty or truncated, numbering contiguous or the break explainable, sub-parts (17a/17b) preserved as printed rather than merged.

Step 4c — Variation clustering

Requires both Step 4 and Step 4b. Per spec section 10.2.

For each section, send that section's concepts (canonical name + local_name) and that section's raw problem list together in one batched call. Get back the problems grouped by concept, then by variation within concept, with one representative problem per variation.

Write the result as a draft problem_concepts tagging for the representatives only (problem_id, concept_id, relationship_type, confidence, variation_key, is_representative). Non-representative problems are not tagged here.

Keep it O(1) calls — per section or chapter-wide, both fine. One call per problem, or per pair of problems, defeats the point.

Deliverable: representatives selected and draft problem_concepts rows written for the fixture chapter, with confidence set on every row.

Verification: this is a judgment stage, so it takes the same gate as concept identification — diff both the variation grouping and the draft concept tags against the fixture's hand-annotated ground truth. Confirm low-confidence cases are flagged rather than silently accepted: ambiguous variation boundaries, uncertain groupings, and problems that plausibly exercise more than one concept.

Step 5 — Implement answer matching and worked-example matching, with confidence checks live from day one

This is the highest-risk stage (spec sections 12–14).

Extraction already happened in Step 4b. This step is matching, and it runs only against the representative problems from Step 4c — not the full exercise list.

Answer matching, in this exact priority order:

Deterministic — exact chapter/problem-number match to answer-key entry
Structural — chapter/section/ordering/numbering-pattern match when numbering differs slightly
LLM — only when genuinely ambiguous (e.g. 17a/17b vs 17)

Store matching_method (deterministic / structural / llm / manual) and a confidence score on every problem_answers row from the start — do not add this after the fact.

Lookup stays a page lookup against answer_key_page_start/end with page_offset applied (spec section 14.1) — never re-solving the problem to check what the answer should be. The answer is whatever the book prints, including when the book is wrong.

Store answer and solution as distinct fields per spec section 13 (answer-only entries must have solution = null, not a guessed solution).

Worked-example matching, per spec section 11.1, also representatives only:

Prefer the section's own worked examples — if one demonstrates the variation, use it and set source = "textbook"
Generate a solution only when no worked example in the section covers that variation, and set source = "generated"

Deliverable: problem_answers and problem_solutions populated for the fixture chapter's representative problems, with matching_method and confidence set on every answer row and source set on every solution row.

Verification: every representative problem/answer pair matches the fixture's hand-annotated ground truth; the ambiguous-numbering case in the fixture is correctly resolved via the LLM tier and flagged with a lower confidence score, not silently treated as certain; every generated solution is flagged for review rather than presented as the textbook's own.

Step 6 — Wire orchestration and validation once individual stages are trustworthy

Only after Steps 3, 4, 4b, 4c and 5 each pass independently against the fixture:

Connect stages into the background job pipeline (spec section 25: ingestion_runs status/stage tracking — queued → processing → completed, with per-stage progress)
Implement the automated validation checks from spec section 26 (structural checks, answer checks, source checks, AI checks)
Ensure the API returns immediately on upload (spec section 5) and processing happens fully in the background

Deliverable: uploading the fixture PDF end-to-end produces a fully populated, validated textbook record with no manual intervention, and ingestion_runs.status reaches completed only when validation passes.

Verification: re-run the full pipeline on the fixture from a clean database and confirm output still matches the ground truth; confirm a deliberately broken/malformed input causes validation to fail rather than silently marking ingestion complete.

Step 7 — Don't start Phase 2 until Phase 1's success criteria are actually met

Before any variation-generation work begins, confirm every item in spec section 39 against a real, non-fixture textbook (not just the golden chapter):

Every chapter/section identifiable
Explanatory content, worked examples, and problems preserved with source pages
Concepts associated with relevant sections/problems
Answer key detected, answers extracted and matched, solutions stored separately when present
Uncertain matches flagged, not silently accepted
Original PDF remains as immutable source
Entire process runs as a background job
UI can determine when ingestion is complete

Do not scaffold Phase 2 (facet extraction, variation synthesis, tutor refinement) in parallel with Phase 1 work — Phase 2 quality depends entirely on Phase 1 data being trustworthy, so early parallel work will need to be redone.

Deliverable: a written confirmation (or automated check) that each success criterion in section 39 holds for a real textbook upload.

Verification: this step is a gate, not a deliverable to build — treat it as the explicit go/no-go before touching Phase 2 code.