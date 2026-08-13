-- Phase 1 — flatten sections (ARCHITECTURE.md section 17).
--
-- Sections are now a flat list within a chapter. A heading printed as "3.2.1" is
-- either its own top-level section (if it has its own exercise set) or folded into
-- its parent's page range with its content in content_blocks.
--
-- This drops the nesting the original schema carried. The fixture no longer
-- exercises parent_section_id, and an untested nullable self-reference is a
-- liability rather than a feature.

drop index if exists public.sections_parent_section_id_idx;

alter table public.sections
    drop constraint if exists sections_not_own_parent_check;

alter table public.sections
    drop column if exists parent_section_id;
