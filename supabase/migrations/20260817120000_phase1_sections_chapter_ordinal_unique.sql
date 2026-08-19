-- Phase 1 — unique constraint for idempotent section upserts (ARCHITECTURE.md section 17).
--
-- chapters already has unique(textbook_id, ordinal), so write_pages-style upserts
-- have something to key off. sections does not: the flatten migration
-- (20260810120100_phase1_sections_flatten.sql) dropped parent_section_id but left no
-- natural key behind for a flat per-chapter list. Without this, write_sections()
-- has no on_conflict target and every re-run would duplicate rows instead of
-- upserting, unlike write_pages and the chapters upsert this mirrors.

alter table public.sections
    add constraint sections_chapter_ordinal_key unique (chapter_id, ordinal);
