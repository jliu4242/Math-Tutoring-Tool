-- Phase 1 — link pages to their section (ARCHITECTURE.md section 17).
--
-- textbook_pages has no column tying a page back to the section it belongs to
-- today -- that link only exists indirectly, by comparing page_number against
-- chapters.page_start/page_end and sections.page_start/page_end ranges.
-- section_id makes it a real, queryable relationship without removing the
-- range columns (a page can still be located by range before structure has
-- run for it).
--
-- Nullable and on delete set null, matching problems.section_id /
-- worked_examples.section_id (20260808120400_phase1_content.sql): raw pages
-- are immutable source data and must survive a section being deleted or
-- re-identified, not cascade away with it.

alter table public.textbook_pages
    add column section_id uuid references public.sections (id) on delete set null;

create index textbook_pages_section_id_idx
    on public.textbook_pages (section_id);
