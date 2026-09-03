-- MinerU ingestion swap -- idempotency keys for the newly-populated tables.
--
-- content_blocks/problems/worked_examples have never had rows written to them before
-- this swap, so none of them had a conflict target for an upsert. Same pattern as
-- write_pages/write_chapters/write_sections already use: re-running extraction over
-- the same range replaces rows instead of duplicating them.

-- content_blocks: one row per (section, reading-order position), same shape as
-- sections' own (chapter_id, ordinal) key.
alter table public.content_blocks
    add constraint content_blocks_section_id_ordinal_key unique (section_id, ordinal);

-- problems/worked_examples: keyed on (textbook_id, page_number, <printed number>)
-- rather than (section_id, ordinal). section_id is nullable on both tables by design
-- (ARCHITECTURE.md section 19/20 -- an unplaced problem must still be recordable), so
-- it cannot anchor a dedupe key; (textbook_id, page_number, problem_number) is what
-- "the same problem" means across a re-extraction of the same page range regardless
-- of whether it has been placed into a section yet.
alter table public.problems
    add constraint problems_textbook_page_number_key unique (textbook_id, page_number, problem_number);

alter table public.worked_examples
    add constraint worked_examples_textbook_page_number_key unique (textbook_id, page_number, example_number);
