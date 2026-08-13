-- Phase 1 — page layout capture (ARCHITECTURE.md sections 6 and 17).
--
-- Section 6 requires the extraction stage to preserve image/figure references,
-- layout information, source coordinates and text ordering. The textbook_pages
-- table in section 17 lists only raw_text, so there was nowhere to put any of it.
--
-- These columns close that gap. They stay on textbook_pages rather than becoming
-- their own table because they are per-page source data with the same lifetime as
-- raw_text -- immutable once extracted, per section 4.

alter table public.textbook_pages
    -- Ordered text lines with bounding boxes. Preserves both reading order and
    -- source coordinates, so a later stage can answer "where on the page did this
    -- come from?" without re-parsing the PDF (section 15).
    add column layout jsonb,

    -- Image and figure references with bounding boxes. Extraction records that a
    -- figure exists and where; it does not attempt to interpret it.
    add column images jsonb,

    -- Which parser produced this row: 'pdfplumber' (primary) or 'pypdf' (fallback).
    -- Part of the audit trail -- a page that fell back to pypdf has weaker layout
    -- data, and that should be visible rather than inferred.
    add column parser text;

comment on column public.textbook_pages.layout is
    'Ordered text lines with bboxes: [{"ordinal":0,"text":"...","x0":..,"top":..,"x1":..,"bottom":..}]. Null when the parser could not supply layout.';

comment on column public.textbook_pages.images is
    'Image/figure references: [{"ordinal":0,"x0":..,"top":..,"x1":..,"bottom":..,"width":..,"height":..}].';

comment on column public.textbook_pages.parser is
    'pdfplumber | pypdf. Section 6 makes pdfplumber primary and pypdf the fallback.';
