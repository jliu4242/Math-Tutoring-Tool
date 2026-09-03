-- MinerU ingestion swap -- generic content_blocks.block_type bucket.
--
-- block_type (20260808120200_phase1_enums.sql) has no catch-all value: only
-- explanation|definition|theorem|rule|example|exercise_intro|note|summary, all of
-- which require deciding *what a block of prose actually is* -- a judgment call per
-- ARCHITECTURE.md section 4.1 (two careful humans could disagree on "is this a rule
-- or an explanation"), which needs hand-annotated fixture ground truth and a diff
-- gate before it can be trusted at pipeline scale.
--
-- MinerU's content_extraction stage is deliberately mechanical for this swap: it maps
-- MinerU's own type/text_level onto block_type with no interpretation. body_text is
-- the target of that mechanical mapping for ordinary prose ("text"-typed MinerU
-- blocks not otherwise routed elsewhere -- lists become problems, titles feed
-- structure identification, standalone equations fold into neighbouring text).
-- Real semantic classification into the existing enum values stays a documented
-- follow-up phase, not part of this swap.

alter type public.block_type add value 'body_text';
