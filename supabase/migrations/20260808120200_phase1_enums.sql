-- Phase 1 ingestion enums.
--
-- Value sets are taken verbatim from ARCHITECTURE.md where the spec enumerates them.

-- ARCHITECTURE.md section 18 — content_blocks.block_type
create type public.block_type as enum (
    'explanation',
    'definition',
    'theorem',
    'rule',
    'example',
    'exercise_intro',
    'note',
    'summary'
);

-- ARCHITECTURE.md section 23 — problem_answers.matching_method
create type public.matching_method as enum (
    'deterministic',
    'structural',
    'llm',
    'manual'
);

-- ARCHITECTURE.md section 25 — ingestion_runs.status
create type public.ingestion_status as enum (
    'queued',
    'processing',
    'paused',
    'failed',
    'completed'
);

-- ARCHITECTURE.md section 25 — ingestion_runs.current_stage
create type public.ingestion_stage as enum (
    'upload',
    'pdf_extraction',
    'structure',
    'content_extraction',
    'problem_extraction',
    'concept_extraction',
    'answer_key',
    'answer_matching',
    'validation',
    'completed'
);

-- textbook_pages.extraction_status (ARCHITECTURE.md section 17).
--
-- NOTE: the spec names this column but does not enumerate its values. These are
-- inferred from section 6, which makes extraction deterministic (pdfplumber, with
-- pypdf as fallback) and reaches for OCR only when a page requires it.
create type public.extraction_status as enum (
    'pending',
    'extracted',
    'ocr_required',
    'failed'
);
