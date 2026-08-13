Implementation Plan — Textbook Ingestion & On-Demand Question Variation System
1. Overall Goal

Build a system that takes a textbook PDF and turns it into a fully structured, queryable textbook database.

The system has two major phases:

PHASE 1
Textbook Upload
      ↓
Complete Background Ingestion
      ↓
Fully Structured Textbook in Supabase
      ↓
READY

Then, independently:

PHASE 2
User selects a concept
      ↓
"Generate Question Variations"
      ↓
Analyze that concept's problems
      ↓
Generate structural variations
      ↓
Tutor refinement
      ↓
Publish

Variation generation is never automatically triggered by textbook upload.

The textbook must first be completely ingested and saved before any variation-generation work occurs.

2. Core Architecture
                         PDF UPLOAD
                             │
                             ▼
                 ┌──────────────────────┐
                 │   BACKGROUND JOB     │
                 │                      │
                 │ COMPLETE INGESTION   │
                 └──────────┬───────────┘
                            │
             ┌──────────────┼──────────────┐
             ▼              ▼              ▼
          Chapters       Sections       Problems
             │              │              │
             │              │              ├── Answers
             │              │              ├── Solutions
             │              │              └── Source pages
             │              │
             │              ├── Explanations
             │              ├── Definitions
             │              ├── Worked Examples
             │              └── Concepts
             │
             └──────────────┬───────────────
                            ▼
                    SUPABASE POSTGRESQL
                            │
                            │
                    INGESTION COMPLETE
                            │
                            ▼
                  ┌─────────────────────┐
                  │     USER SELECTS    │
                  │       CONCEPT       │
                  └──────────┬──────────┘
                             │
                             ▼
                  Generate Question
                      Variations
                             │
                             ▼
                    FACET EXTRACTION
                             │
                             ▼
                   VARIATION SYNTHESIS
                             │
                             ▼
                     TUTOR REFINEMENT
                             │
                             ▼
                       BLIND REFIT
                             │
                             ▼
                         PUBLISH
3. Phase 1 — Complete Textbook Ingestion

This is the first implementation phase.

The goal is:

Upload a textbook once and completely reconstruct its contents into structured database records.

After ingestion finishes, the application should be able to access the textbook without needing to repeatedly interpret the original PDF.

The ingestion pipeline should extract and save:

textbook metadata
chapters
sections
explanations
definitions
rules/theorems
worked examples
exercises
individual problems
problem numbering
page references
concepts
answer-key sections
answers
solutions/explanations when provided
relationships between all of these objects
4. Ingestion Philosophy

The ingestion system should distinguish between:

Source data

What actually exists in the textbook.

Examples:

PDF pages
extracted text
problem statements
answer-key entries
examples
section headings
Derived data

What the AI determines about the textbook.

Examples:

concept assignments
problem → concept relationships
semantic classification
answer-key matching when numbering is ambiguous

The original source should remain immutable.

SOURCE
──────
PDF
Pages
Raw text
Images
Original problem text
Original answer text

        ↓

DERIVED
───────
Sections
Concepts
Problem relationships
Answer relationships
Metadata

This allows derived information to be corrected without modifying the underlying textbook.

4.1 Judgment Stages vs. Mechanical Stages

The source/derived split above also decides which stages need a ground-truth verification gate.

A stage is mechanical if a careful human reading the same page would produce the same output every time. A stage is a judgment stage if two careful humans could reasonably disagree.

MECHANICAL                          JUDGMENT
──────────                          ────────
PDF text extraction                 Concept identification
Raw problem extraction              Variation clustering
Answer-key entry extraction         Answer matching when ambiguous
Deterministic answer matching       Semantic classification

The distinction matters because the two failure modes are different.

Mechanical stages fail loudly and locally: a problem is missing, text is garbled, a page is blank. Checking them means checking for extraction errors, not for correctness of interpretation — there is no interpretation.

Judgment stages fail quietly. They produce output that is well-formed, plausible, and wrong. Nothing downstream notices.

Therefore:

Mechanical stages need extraction-error checks (nothing missed, nothing garbled).
Judgment stages need a diff against hand-annotated ground truth before their output is trusted at pipeline scale, and must flag low-confidence output rather than emitting it silently.

This is the rule already stated in IMPLEMENTATION-PLAN.md. It is restated here because the following sections split what used to be a single "extract problems and figure out what they teach" stage into a mechanical branch and a judgment branch, which only makes sense if it is clear why they are being separated.

5. Step 1 — Upload

When the user uploads a PDF:

POST /textbooks

The system:

Stores the original PDF.
Creates a textbook record.
Calculates a file hash.
Creates an ingestion job.
Returns immediately to the UI.
Processes the textbook in the background.

The user should not need to keep the page open while ingestion happens.

6. Step 2 — PDF Extraction

The first processing stage should be deterministic.

Use:

pdfplumber as the primary parser
pypdf as a fallback

Extract:

Page 1
  raw text
  images/figure references
  layout information

Page 2
  raw text
  ...

Page N
  raw text

Preserve:

page number
extracted text
source coordinates where useful
ordering of text
original PDF reference

This stage should not use an LLM unless the PDF requires OCR or another specialized process.

7. Step 3 — Identify Textbook Structure

Now the system reconstructs the textbook's hierarchy.

The AI can identify:

Textbook
 ├── Chapter 1
 │    ├── Section 1.1
 │    │    ├── Explanation
 │    │    ├── Definition
 │    │    ├── Example 1
 │    │    └── Problems
 │    │
 │    └── Section 1.2
 │
 ├── Chapter 2
 │    └── ...
 │
 └── Answer Key

The important point is that this is ingestion, not variation generation.

The AI's job is to understand:

"What pieces make up this textbook?"

It is not yet trying to determine:

"What types of questions exist within this concept?"

That comes later.

8. Step 4 — Sections, Explanations, Examples, and Problems

Each section should be decomposed into its meaningful components.

For example:

Section 3.2 — Solving Linear Equations

Introduction
    ↓
Explanation
    ↓
Worked Example 1
    ↓
Explanation
    ↓
Worked Example 2
    ↓
Exercises
    ├── Problem 1
    ├── Problem 2
    ├── Problem 3
    └── ...

The system should preserve the relationship between these objects.

For example:

Problem 7
   ↓
belongs to
   ↓
Section 3.2
   ↓
belongs to
   ↓
Chapter 3

And:

Example 2
   ↓
appears in
   ↓
Section 3.2
9. Step 5 — Concepts

The ingestion system should identify the concepts taught in each section.

For example:

Chapter 3
│
├── Section 3.1
│     └── Solving Linear Equations
│
├── Section 3.2
│     └── Literal Equations
│
└── Section 3.3
      └── Applications of Linear Equations

These concepts are stored during ingestion so that the UI can later present:

Chapter 3

Solving Linear Equations
[Generate Question Variations]

Literal Equations
[Generate Question Variations]

Applications of Linear Equations
[Generate Question Variations]

The existence of the concept does not mean variations have been generated.

9.1 Batching and Section Scoping

Concept identification is a judgment stage (section 4.1), but it is cheap to batch.

The whole chapter can go into a single LLM call. What must not collapse is the output: each section's concepts have to come back attributed to that section, not as one undifferentiated chapter-level list.

ONE CALL                      SECTION-SCOPED OUTPUT
────────                      ─────────────────────
Chapter 3, all sections  →    3.1 → [solving-linear-equations]
                              3.2 → [literal-equations]
                              3.3 → [applications-of-linear-equations]

The reason is verification, not tidiness. The gate on this stage is a diff against the fixture's hand-annotated concept assignments, and that diff is per-section. A chapter-level blob cannot be diffed section by section, so a concept attached to the wrong section would pass unnoticed — which is exactly the failure this gate exists to catch.

Batching is therefore an implementation detail of how the call is made. It must not become a change to what the stage outputs.

Known gap: fixtures/validate_fixture.py checks that concepts[].section_keys resolve to sections that exist, but it does not check that a concept's declared section is the section it would actually have been derived from. A concept annotated against the wrong section is internally consistent and passes validation today. Until that check exists, per-section concept correctness rests on the annotator, not the validator.

10. Step 6 — Problems

Every individual textbook problem should become its own database record.

For example:

Problem #17
Chapter: 3
Section: 3.2
Page: 124

Body:
Solve 3x + 7 = 19.

The database should preserve the original problem as closely as possible.

Store:

problem number
problem text
LaTeX representation when appropriate
plain-text representation
chapter
section
page
source reference
problem type if deterministically identifiable
original ordering

Problems should be independent records rather than being stored only inside a chapter text blob.

10.1 Raw Problem Extraction Is Mechanical

Extracting the exercise list is a mechanical stage (section 4.1). It pulls the problem number and the problem text, and nothing else.

It does not decide what a problem teaches. It does not group problems. It does not rank them. Those are judgment calls and they belong to section 10.2.

Section 3.2 Exercises
  ↓
17a. Solve P = 2l + 2w for l.
17b. Solve P = 2l + 2w for w.
18.  Solve C = 2πr for r.
...

Because there is no interpretation here, there is no ground-truth diff gate on this stage. What it needs instead is extraction-error checking:

no problem in the printed exercise set is missing
no problem body is empty or truncated
problem numbering is contiguous, or the break is explainable
sub-parts (17a/17b) are preserved as printed rather than merged

A missed problem is a bug that shows up as an absence, so it has to be checked by counting against the source page — not by asking whether the output looks reasonable.

10.2 Step 6b — Variation Clustering

Concept identification (section 9) and raw problem extraction (section 10.1) are independent branches. Both depend only on structure identification, neither depends on the other, and they can run in either order or concurrently.

Variation clustering is where they meet.

  Structure identification
        │
   ┌────┴────┐
   ▼         ▼
Concepts   Raw problems      (independent branches)
   │         │
   └────┬────┘
        ▼
Variation clustering          (one batched call)
        ▼
Representative problems
        ▼
Answer lookup + worked-example matching

Input, per section: that section's already-identified concepts (canonical name plus local_name), and that section's raw problem list.

Process: a single batched LLM call — per section, or chapter-wide, either is fine — that groups the section's problems first by which concept they test, then by variation within that concept, and returns one representative problem per variation. The requirement is O(1) calls, not one call per problem and certainly not one per pair of problems.

Output: the chosen representatives, plus a first-pass draft of problem_concepts (problem_id, concept_id, relationship_type, confidence) for those representatives only. Non-representative problems are not tagged at this stage, because only representatives are carried into answer lookup and worked-example matching.

Cost rationale

The point of this step is that downstream work stops scaling with exercise count.

A 40-exercise section holding 3 concepts at 3–4 variations each carries roughly 9–12 representatives forward, not 40. The clustering itself is one call regardless. Pairwise comparison of all 40 problems would be ~800 comparisons; per-problem judgment would be 40 calls. Both are avoided.

Downstream cost therefore tracks concept-count × variations-per-concept, which stays roughly constant per section at this grade band, rather than tracking how many exercises the publisher happened to print.

Verification discipline

This is a judgment stage, in the same category as concept identification and ambiguous answer matching. Its output is a draft.

Both halves of the output need confidence, and low confidence must be flagged rather than silently accepted:

the grouping itself — an ambiguous variation boundary, or an uncertain cluster
the draft concept tags — particularly a problem that plausibly exercises more than one concept

Before this stage is trusted at pipeline scale, its output is diffed against the fixture's hand-annotated ground truth, the same gate concept identification passes through.

Relationship to Phase 2

Note the boundary this moves. Section 7 says ingestion is not yet asking "what types of questions exist within this concept?", and section 40 assigns that question to Phase 2. This step asks a narrow version of it during Phase 1.

The two are not the same artifact and must not be conflated:

PHASE 1 — variation clustering       PHASE 2 — variation taxonomy
──────────────────────────────       ────────────────────────────
one cheap batched call               facet extraction + synthesis
draft, always revisable              tutor-refined, then frozen
purpose: pick representatives        purpose: generate new questions
                                     so downstream work is bounded

Phase 1's grouping exists only to bound the cost of answer lookup and worked-example matching. It is not the published taxonomy, it is never frozen, and Phase 2 does not treat it as an input it must agree with. If the two disagree, Phase 2 wins.

11. Step 7 — Worked Examples

Worked examples should also be stored separately.

For example:

Example 4
Chapter 3
Section 3.2
Page 121

Question:
Solve 2x + 5 = 17.

Solution:
...

This allows future features to distinguish:

TEXTBOOK PROBLEMS

from:

WORKED EXAMPLES

without having to re-parse the textbook.

11.1 Matching Worked Examples to Representatives

Extracting worked examples from the section is mechanical and covers all of them, exactly as above.

Matching a worked example to a problem is a separate thing, and it runs only against the representative problems chosen in section 10.2 — not against the full exercise list.

For each representative, prefer what the textbook already demonstrates:

First: the section's own worked examples

If a worked example in the section demonstrates that variation, use it.

    source = "textbook"

Second: generate, only if nothing demonstrates it

If no worked example in the section covers the variation, a solution may be generated.

    source = "generated"

The source field is not optional and not cosmetic. A textbook-sourced solution is source data; a generated one is derived data the AI produced, and section 4 requires those stay distinguishable. Generated solutions must also be flagged for review — a variation the textbook never demonstrates is precisely the case where a generated solution is least likely to match how the book teaches it.

This ordering is also what keeps the step cheap: most variations are demonstrated somewhere in the section, so generation is the exception rather than the default path.

12. Step 8 — Answer-Key Extraction

The ingestion pipeline should specifically look for an answer section.

For example:

Answers

Chapter 3

1. x = 4
2. x = -2
3. x = 7/3
...

The system should:

Detect the answer-key section.
Extract individual answers.
Determine which chapter/section/problem they correspond to.
Match each answer to the appropriate problem.
Store the relationship in Supabase.
13. Answer vs. Solution

These should be treated as separate pieces of information.

If the textbook says:

17. x = 4

store:

answer = "x = 4"
solution = null

If the textbook provides a worked solution:

17.
Subtract 7 from both sides...
Divide by 3...
Therefore x = 4.

store:

answer = "x = 4"

solution =
"Subtract 7 from both sides...
 Divide by 3..."

Do not mistake an answer key for a full solution.

14. Answer-Key Matching

Use a hierarchy of methods.

First: deterministic matching

If the textbook clearly says:

Chapter 3
17. x = 4

and there is a Chapter 3 Problem 17:

Problem 17 → Answer "x = 4"

No LLM is needed.

Second: structural matching

Use chapter, section, ordering, and numbering when numbering is slightly different.

Third: AI matching

Only use an LLM when the relationship is genuinely ambiguous.

For example:

Problem 17a
Problem 17b
Problem 18

Answer:
17. ...
18. ...

The LLM can determine the likely mapping.

This keeps ingestion costs down.

14.1 Answer Lookup Runs Against Representatives

Answer-key extraction (section 12) reads the whole answer key, because the key is extracted as printed.

Matching answers to problems runs only against the representative problems from section 10.2.

Lookup itself stays deterministic. It is a page lookup — find the entry under the right chapter/problem number within answer_key_page_start through answer_key_page_end, applying page_offset to convert printed page numbers to PDF page indices — followed by the matching hierarchy above.

It is never a matter of re-solving the problem to check the answer. The answer is whatever the book prints, including when the book is wrong. Section 13 still holds: an answer-key entry is an answer, not a solution, and an absent solution stays null.

15. Step 9 — Preserve Source References

Every extracted object should maintain a link back to the PDF.

For example:

Problem 17
    ↓
page 124
    ↓
textbook_001.pdf

Likewise:

Answer 17
    ↓
page 687
    ↓
textbook_001.pdf

This is important because the source and answer may be hundreds of pages apart.

It also makes debugging possible:

"Why does the system think this is Problem 17?"

The application can show the original source page.

16. Step 10 — Save Everything to Supabase

Supabase PostgreSQL becomes the source of truth for the structured textbook.

The original PDF should remain in Supabase Storage or equivalent object storage.

PostgreSQL stores the structured representation.

17. Core Database Schema
Textbooks
textbooks (
    id,
    title,
    edition,
    publisher,
    subject,
    grade_band,
    created_at
)
Sources
textbook_sources (
    id,
    textbook_id,
    file_hash,
    storage_path,
    page_count,
    uploaded_at
)
Pages
textbook_pages (
    id,
    source_id,
    page_number,
    raw_text,
    extraction_status,
    created_at
)
Chapters
chapters (
    id,
    textbook_id,
    number,
    title,
    page_start,
    page_end,
    ordinal
)
Sections
sections (
    id,
    chapter_id,
    title,
    ordinal,
    page_start,
    page_end,
    content
)

Sections are a flat list within a chapter, ordered by ordinal. There is no nesting.

A heading printed as "3.2.1" is not automatically a section. If it has its own exercise set it becomes its own top-level section row; if it is only a named sub-heading inside 3.2's prose, it is folded into 3.2 and its content lives in content_blocks. This keeps section identification a boundary question rather than a hierarchy question.

18. Textbook Content

Rather than putting every type of content into one table, use a generic content relationship where appropriate.

content_blocks (
    id,
    section_id,
    block_type,
    ordinal,
    page_start,
    page_end,
    content,
    source_ref
)

Possible block_type values:

explanation
definition
theorem
rule
example
exercise_intro
note
summary

Problems and worked examples can have their own specialized tables when they need additional fields.

This preserves the order of the textbook while still allowing structured querying.

19. Problems
problems (
    id,
    textbook_id,
    chapter_id,
    section_id,
    source_ref,
    page_number,
    problem_number,
    body_latex,
    body_plain,
    ordinal,
    created_at
)
20. Worked Examples
worked_examples (
    id,
    textbook_id,
    chapter_id,
    section_id,
    source_ref,
    page_number,
    example_number,
    problem_text,
    solution_text,
    ordinal,
    created_at
)
21. Concepts

Concepts should be stored separately from textbook sections.

concepts (
    id,
    slug,
    canonical_name,
    description,
    grade_band,
    parent_concept_id,
    created_at
)

Then associate them with textbook chapters/sections:

section_concepts (
    section_id,
    concept_id,
    local_name,
    ordinal,

    PRIMARY KEY(section_id, concept_id)
)

This means multiple textbooks can eventually reference the same canonical concept.

22. Problem → Concept

A problem can potentially exercise multiple concepts.

problem_concepts (
    problem_id,
    concept_id,
    relationship_type,
    confidence,
    variation_key,
    is_representative,

    PRIMARY KEY(problem_id, concept_id)
)

For example:

Problem 17
 ├── Solving Linear Equations
 └── Fractions

This relationship is useful later when selecting problems for variation generation.

variation_key and is_representative

The first four columns cannot express the output of section 10.2 — there is nowhere to record which variation a problem belongs to, or that it was chosen to represent one. These two columns are the minimum needed.

variation_key is a nullable stable label for a variation, unique within a concept. Two problems sharing a concept_id and a variation_key were judged to test the same variation. Null means the clustering stage has not run, or ran and could not place the problem.

is_representative marks the one problem carried downstream for that variation.

Because the primary key is already (problem_id, concept_id), both columns are naturally per-concept: a problem tagged with two concepts gets one row per concept and can sit in a different variation under each, which is the correct behaviour.

At most one representative per variation should be enforced in the database rather than by convention:

UNIQUE (concept_id, variation_key) WHERE is_representative

Two constraints on interpretation:

These columns hold a Phase 1 draft, not the Phase 2 taxonomy (section 10.2). Phase 2 writes its own frozen variation records and does not update these. Anything that reads variation_key expecting a published taxonomy is reading the wrong table.

confidence applies to this row as a whole — both the concept tag and the variation placement. A low-confidence row is a flag for review, not a fact (section 27).

23. Answers

Store answers independently because they originate from a separate section of the textbook.

problem_answers (
    id,
    problem_id,
    answer_text,
    answer_source_page,
    answer_source_ref,
    matching_method,
    confidence,
    created_at
)

matching_method might be:

deterministic
structural
llm
manual

This gives you a clear audit trail.

24. Solutions

If the textbook provides solutions, store them separately from the answer.

problem_solutions (
    id,
    problem_id,
    solution_text,
    source,
    source_page,
    source_ref,
    created_at
)

source is either textbook or generated, per section 11.1.

textbook means the solution was printed in the book — source data, with a real source_page.
generated means the AI produced it because no worked example in the section demonstrated that variation — derived data, with source_page null.

The column is required. Without it the table mixes what the textbook said with what the AI wrote, and section 4's rule that source data stays immutable and separable is quietly broken. A generated solution is also never a substitute for an absent answer: section 13 still applies, and an answer with no key entry stays null rather than being backfilled from a generated solution.

A problem therefore can have:

Problem
 ├── Body
 ├── Answer
 └── Solution

with Answer and Solution both optional.

25. Ingestion Jobs

Because the textbook is processed in the background, ingestion needs durable job tracking.

ingestion_runs (
    id,
    textbook_id,
    status,
    current_stage,
    progress,
    error,
    started_at,
    completed_at,
    updated_at
)

Possible statuses:

queued
processing
paused
failed
completed

Stages:

upload
pdf_extraction
structure
content_extraction
problem_extraction
concept_extraction
variation_clustering
answer_key
answer_matching
validation
completed

problem_extraction and concept_extraction are the two independent branches of section 10.2 and may run in either order or concurrently. variation_clustering requires both.

The UI can therefore display:

Processing textbook...

✓ PDF extracted
✓ Chapters identified
✓ Sections identified
✓ Problems extracted
✓ Examples extracted
✓ Concepts identified
✓ Variations clustered
✓ Answer key processed
✓ Answers matched

Textbook ready.
26. Ingestion Validation

Before marking the textbook as complete, run automated checks.

Examples:

Structural checks
Every chapter has valid page ranges.
Sections belong to a chapter.
Problems belong to a section/chapter.
Problem numbers are not unexpectedly duplicated.
Answer checks
Answer references point to existing problems.
Unexpected answer-key entries are flagged.
Unmatched problems are allowed but recorded.
Source checks
Every problem has a source page.
Every answer has an answer-key source page.
Extracted text is not empty.
AI checks
Required structured fields are present.
LLM output conforms to schema.
Low-confidence relationships are flagged.

The goal isn't to guarantee that AI is perfect.

The goal is to prevent obviously broken ingestion from being marked as complete.

27. Handling Uncertainty

The ingestion pipeline should not pretend to know something it doesn't know.

For example:

Problem 17
answer = "x = 4"
answer_match_confidence = 0.99

versus:

Problem 17
answer = "x = 4"
answer_match_confidence = 0.54

Low-confidence items can be flagged for later review.

Similarly:

concept assignment
confidence = low

should not silently become an unquestioned fact.

28. Background Processing

The entire ingestion pipeline should run asynchronously.

Conceptually:

User
 │
 │ Upload PDF
 ▼
API
 │
 ├── Save PDF
 ├── Create textbook
 └── Queue ingestion job
             │
             ▼
       Background Worker
             │
             ├── Extract PDF
             ├── Structure
             ├── Extract content
             ├── Extract problems
             ├── Extract concepts
             ├── Find answer key
             ├── Match answers
             └── Validate
                     │
                     ▼
                  Supabase
                     │
                     ▼
              Ingestion complete

The web server should not be responsible for holding the HTTP request open throughout the entire process.

29. Phase 2 — On-Demand Variation Generation

Once Phase 1 is complete, the textbook is considered ready.

The user can browse:

Textbook
  ↓
Chapter
  ↓
Section
  ↓
Concept

For example:

Chapter 3 — Linear Equations

Solving Linear Equations
42 problems

[ Generate Question Variations ]

Clicking that button begins Phase 2.

30. Variation Generation Pipeline
User selects concept
        ↓
Fetch relevant problems
        ↓
Facet extraction
        ↓
Variation synthesis
        ↓
Tutor review
        ↓
Refinement
        ↓
Freeze
        ↓
Blind refit
        ↓
Publish

Only this pipeline deals with question variations.

31. Facet Extraction

Analyze only problems relevant to the selected concept.

Do not analyze every problem in the textbook.

Batch problems into LLM requests to reduce API calls.

Output structured records such as:

{
  "problem_id": "problem_17",

  "solution_procedure": [
    "distribute",
    "collect variable terms",
    "divide by coefficient"
  ],

  "structural_features": {
    "has_fractions": false,
    "variable_both_sides": true,
    "requires_distribution": true
  },

  "presentation": "bare_symbolic"
}
32. Variation Synthesis

Use one strong LLM call by default.

Input:

concept
problem facets
relevant textbook context
active tutor principles

Output:

proposed variations
defining facets
discriminators
boundary notes
memberships
representative examples

Do not automatically run three synthesis calls.

Additional synthesis runs are optional diagnostic tools.

33. Tutor Refinement

The tutor can:

accept
rename
merge
split
redefine
move problems
add variations
remove variations
mark outliers
change examples
reorder variations

AI feedback should become structured operations.

Tutor:
"Merge V2 and V3."

        ↓

LLM

        ↓

{
  "op": "merge",
  "targets": ["V2", "V3"]
}

        ↓

Application code applies operation

The LLM proposes the change.

The application owns the mutation.

34. Freeze

Accepted variations become frozen.

frozen = true

Later changes should not silently modify frozen variations.

This prevents taxonomy drift during refinement.

35. Blind Refit

After acceptance, optionally run a blind refit:

Problem
   +
Variation definitions
   ↓
Model chooses:
   V1
   V2
   V3
   None

The model is not shown the original assignment.

Disagreements are surfaced to the tutor rather than automatically rewriting the taxonomy.

36. Decoy Test

Keep the decoy test from the original design.

It specifically tests whether the system is recognizing mathematical structure rather than surface similarity.

Test 1

Two problems look similar but require different procedures.

Expected:

Different variations
Test 2

Two problems look different but require the same procedure.

Expected:

Same variation

This remains one of the primary development sanity checks.

37. Vector Storage

Do not introduce vector storage initially.

Supabase PostgreSQL is the primary source of truth.

Embeddings can be added later for features such as:

semantic problem retrieval
finding similar examples
searching textbook content

But embeddings should not determine variations.

The taxonomy remains:

Problem
 ↓
Facets
 ↓
Structural reasoning
 ↓
Variation

If vector search becomes useful later, PostgreSQL + pgvector is preferable to introducing a separate vector database initially.

38. Final Architecture

The finished system should conceptually look like:

                         ┌──────────────┐
                         │  TEXTBOOK    │
                         │     PDF      │
                         └──────┬───────┘
                                │
                                ▼
                    ╔══════════════════════╗
                    ║ PHASE 1: INGESTION   ║
                    ║                      ║
                    ║ PDF extraction       ║
                    ║ Structure            ║
                    ║ Sections              ║
                    ║ Examples              ║
                    ║ Problems              ║
                    ║ Concepts              ║
                    ║ Answer key            ║
                    ║ Answer matching       ║
                    ║ Validation             ║
                    ╚══════════╤═══════════╝
                               │
                               ▼
                    ┌──────────────────────┐
                    │ SUPABASE POSTGRESQL  │
                    │                      │
                    │ COMPLETE TEXTBOOK   │
                    │ REPRESENTATION      │
                    └──────────┬───────────┘
                               │
                         User browses
                               │
                               ▼
                     Selects a concept
                               │
                               ▼
                    Generate Variations
                               │
                               ▼
                    ╔══════════════════════╗
                    ║ PHASE 2: TAXONOMY    ║
                    ║                      ║
                    ║ Facet extraction     ║
                    ║ Variation synthesis  ║
                    ║ Tutor refinement     ║
                    ║ Freeze               ║
                    ║ Blind refit          ║
                    ╚══════════╤═══════════╝
                               │
                               ▼
                    Published taxonomy
39. Phase 1 Success Criteria

Phase 1 is complete when the system can take a real textbook PDF and produce a complete structured representation in Supabase where:

every chapter is identifiable;
every section is identifiable;
explanatory content is preserved;
worked examples are identifiable;
individual problems are identifiable;
problems retain their original source pages;
concepts are associated with relevant sections/problems;
an answer-key section is detected when present;
answers are extracted;
answers are matched to problems;
solutions are stored separately when available;
uncertain matches are flagged;
the original PDF remains available as the immutable source;
the entire process runs as a background job;
the UI can determine when ingestion is complete.

Only after these conditions are met should the textbook be considered ready for question-variation generation.

40. Core Principle

The architecture now has a very clean separation:

Phase 1 answers: "What is in this textbook?"

Phase 2 answers: "What different kinds of questions exist within this concept?"

One qualification, added with section 10.2. Phase 1's variation clustering does ask a narrow version of Phase 2's question, but only to decide which problems are worth spending downstream calls on. It produces a disposable draft, never a published taxonomy. The separation that matters is unchanged: Phase 1 never generates a question, and Phase 2 never re-reads the PDF.

Phase 1 happens once when the textbook is uploaded.

Phase 2 happens only when the tutor explicitly requests it.